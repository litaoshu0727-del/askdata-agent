"""
上下文 Query 改写（指代消解）。

多轮对话里用户会说"它们的退款金额呢"、"这些店铺的买家数"。
指代对象不在当前 Query 里，只存在于会话记忆中。

原来的做法是把会话记忆拼在 Query 前面一起送进 CoT，指望模型顺手解决。
实测不行，两种失败都会出现：

    关键词抽取拿到的是原始 Query，把"它们"当成了检索词，
    真正的指代对象（店铺名）根本没进检索。

    CoT 看到了上下文，但没被要求先解指代，
    结果要么忽略限定条件查了全表，要么从店铺名"臻品自营店15"里
    抠出数字 15 当成 shop_id，凭空造出一个过滤条件。

所以把指代消解拆成显式的一步：先把追问改写成**自包含**的问题，
再送进后面的关键词抽取和 CoT。这就是检索增强里常说的 query rewriting。
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from askdata_diagnostics import Codes, OnceEmitter, emit
from llm_config import resolve_chat_provider

# 出现这些词才认为可能有指代，避免每轮都白白多调一次模型。
REFERENCE_MARKERS = (
    "它们", "他们", "她们", "它", "这些", "那些", "这几个", "那几个",
    "这个", "那个", "刚才", "上面", "前面", "上述", "该", "其中",
    "同样", "再看", "还有呢", "以上",
)

REWRITE_PROMPT = """你是一个对话式数据查询系统的 Query 改写模块。

任务：根据会话历史，把用户当前这句话改写成一个**自包含**的查询问题。

要求：
1. 把所有指代词（它们、这些、刚才那几个……）替换成会话历史中对应的具体对象。
2. 指代对象要用历史结果里出现过的**原始值**，例如店铺名称就用店铺名称原文。
3. 绝对不要凭空推断任何 ID。比如店铺名叫"臻品自营店15"，不代表它的 ID 是 15。
4. 只补充指代信息，不要改变用户的查询意图，不要添加历史里没有的筛选条件。
5. 如果当前问题本身已经自包含，原样返回。
6. 只输出改写后的问题，不要解释，不要加引号。

会话历史：
{context}

用户当前问题：{query}

改写后的问题："""


@dataclass
class RewriteResult:
    """改写结果。"""

    original: str
    rewritten: str
    changed: bool = False
    skipped_reason: str = ""

    @property
    def effective(self) -> str:
        """后续环节应该使用的 Query。"""
        return self.rewritten or self.original


@dataclass
class QueryRewriterConfig:
    """改写器配置。"""

    api_key: str = ""
    chat_url: str = ""
    model: str = ""
    timeout: int = 60
    max_context_chars: int = 2000
    extra_payload: Dict[str, Any] = field(default_factory=dict)


class ContextualQueryRewriter:
    """
    把带指代的追问改写成自包含 Query。

    没有 API Key 时原样返回并上报一次降级——多轮追问在这种情况下
    本来就不可能正确工作，不该让它悄悄退化成"查全表"。
    """

    def __init__(self, config: Optional[QueryRewriterConfig] = None):
        self.config = config or QueryRewriterConfig()

        # 改写要的是忠实转述，不是发散推理，DeepSeek 下关闭思考模式。
        provider = resolve_chat_provider(thinking=False)

        if not self.config.api_key:
            self.config.api_key = provider.api_key

        if not self.config.chat_url:
            self.config.chat_url = provider.chat_url

        if not self.config.model:
            self.config.model = provider.model

        if not self.config.extra_payload:
            self.config.extra_payload = dict(provider.extra_payload)

        self._degrade = OnceEmitter()

    @staticmethod
    def looks_contextual(query: str) -> bool:
        """当前 Query 里是否出现了疑似指代词。"""
        return any(marker in query for marker in REFERENCE_MARKERS)

    def rewrite(self, query: str, conversation_context: str) -> RewriteResult:
        """
        改写当前 Query。

        Args:
            query: 用户原始问题。
            conversation_context: 会话记忆文本。

        Returns:
            RewriteResult: 改写结果，失败时回退为原 Query。
        """
        if not conversation_context.strip():
            return RewriteResult(original=query, rewritten=query, skipped_reason="无会话上下文")

        if not self.looks_contextual(query):
            return RewriteResult(original=query, rewritten=query, skipped_reason="未检测到指代词")

        if not self.config.api_key:
            self._degrade.emit(
                Codes.QUERY_REWRITE_SKIPPED,
                "检测到指代词但未配置 API Key，无法做指代消解，"
                "本轮会按字面查询，多轮追问结果大概率不正确",
                原问题=query,
            )
            return RewriteResult(original=query, rewritten=query, skipped_reason="无 API Key")

        context = conversation_context.strip()
        if len(context) > self.config.max_context_chars:
            context = context[-self.config.max_context_chars:]

        try:
            rewritten = self._call_model(
                REWRITE_PROMPT.format(context=context, query=query)
            )
        except Exception as exc:
            emit(
                Codes.QUERY_REWRITE_FAILED,
                "指代消解调用失败，回退为原始 Query，本轮多轮追问可能不正确",
                原因=str(exc)[:80],
            )
            return RewriteResult(original=query, rewritten=query, skipped_reason="调用失败")

        rewritten = rewritten.strip().strip('"').strip("“”").strip()

        if not rewritten:
            return RewriteResult(original=query, rewritten=query, skipped_reason="模型返回为空")

        return RewriteResult(
            original=query,
            rewritten=rewritten,
            changed=rewritten != query,
        )

    def _call_model(self, prompt: str) -> str:
        """调用 Chat Completions 接口。"""
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "stream": False,
        }
        payload.update(self.config.extra_payload)

        request = urllib.request.Request(
            self.config.chat_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))

        return result["choices"][0]["message"]["content"]
