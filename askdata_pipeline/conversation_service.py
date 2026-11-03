from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from askdata_memory import ConversationMemoryContext, ConversationMemoryService, LongTermMemory

from .objects import PipelineResult
from .text2sql_pipeline import AskDataText2SQLPipeline


# 查库回答写进会话记忆的上限。追问的改写和 CoT 读到的上一轮结果就是这一段。
ANSWER_PREVIEW_CHARS = 1500


def answer_preview(execution_results: List[Dict[str, Any]]) -> str:
    """
    查库回答写进会话记忆的样子：列名只写一次，每行一个数组。

    原来每一行都是带列名的字典，1500 字一半花在重复的列名上，10 行就放不下，从中间截断成半截 JSON：
    第一套多轮题 M1C07-3 列了 10 家公司，第 10 行被截掉，追问"消费最高的那家公司"时改写器看不全，挑不了。
    行还是放不下时按整行截，写明一共几行、列出了前几行，改写器知道自己没看全。
    """
    steps = []
    for result in execution_results:
        step = dict(result)
        columns = list(step.get("columns") or [])
        step["rows"] = [
            [row.get(column) for column in columns] if isinstance(row, dict) else row
            for row in step.get("rows") or []
        ]
        steps.append(step)

    text = json.dumps(steps, ensure_ascii=False, default=str)
    if len(text) <= ANSWER_PREVIEW_CHARS:
        return text

    # 先算不带行时的长度，剩下的预算一行一行放；每个被截的步骤多一句说明，预留 40 字。
    # 多步规划时最后一步才是这一轮的答案，先放它。
    budget = ANSWER_PREVIEW_CHARS - len(json.dumps([{**step, "rows": []} for step in steps], ensure_ascii=False, default=str))
    budget -= 40 * len(steps)
    for step in reversed(steps):
        rows, kept = step["rows"], []
        for row in rows:
            size = len(json.dumps(row, ensure_ascii=False, default=str)) + 2
            if size > budget:
                break
            kept.append(row)
            budget -= size
        if len(kept) < len(rows):
            step["rows"] = kept
            step["rows_note"] = f"共 {len(rows)} 行，只列出前 {len(kept)} 行"

    text = json.dumps(steps, ensure_ascii=False, default=str)
    # SQL 本身就超长时行再少也放不下，退回按字截。
    if len(text) > ANSWER_PREVIEW_CHARS:
        text = text[: ANSWER_PREVIEW_CHARS - 10] + "……"
    return text


@dataclass
class ConversationPipelineResult:
    pipeline_result: PipelineResult
    memory_context: ConversationMemoryContext
    answer: str = ""


class MemoryAwareAskDataService:
    """把记忆上下文接入现有 Text2SQL 流程的轻量会话编排层。"""

    def __init__(
        self,
        pipeline: AskDataText2SQLPipeline,
        memory: ConversationMemoryService,
    ):
        self.pipeline = pipeline
        self.memory = memory

    def run(
        self,
        *,
        user_id: str,
        session_id: str,
        query: str,
        enable_long_term: bool = False,
        long_term_top_k: Optional[int] = None,
    ) -> ConversationPipelineResult:
        context = self.memory.begin_user_turn(
            user_id=user_id,
            session_id=session_id,
            query=query,
            enable_long_term=enable_long_term,
            long_term_top_k=long_term_top_k,
        )
        return self.run_with_context(
            user_id=user_id,
            session_id=session_id,
            query=query,
            context=context,
        )

    def run_with_context(
        self,
        *,
        user_id: str,
        session_id: str,
        query: str,
        context: ConversationMemoryContext,
        assistant_metadata: Optional[dict] = None,
    ) -> ConversationPipelineResult:
        """使用已准备的记忆上下文执行查询，供动态路由服务复用。"""
        result = self.pipeline.run(
            query,
            conversation_context=context.to_prompt_context(),
        )
        payload = result.to_dict()
        result_preview = answer_preview([log.execution_result for log in result.step_logs])
        answer = f"已完成数据库查询。查询结果：{result_preview}"
        metadata = {
            "sql": [log.sql for log in result.step_logs],
            "database": [log.database for log in result.step_logs],
        }
        metadata.update(assistant_metadata or {})
        self.memory.record_assistant_message(
            user_id=user_id,
            session_id=session_id,
            content=answer,
            message_type="sql_result",
            payload=payload,
            metadata=metadata,
        )
        return ConversationPipelineResult(
            pipeline_result=result,
            memory_context=context,
            answer=answer,
        )

    def save_result_to_personal_knowledge_base(
        self, *, user_id: str, result: PipelineResult
    ) -> LongTermMemory:
        """UI 中的“保存到个人知识库”动作应调用此方法。"""
        return self.memory.save_pipeline_result(user_id=user_id, result=result)
