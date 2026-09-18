"""
多轮追问场景 Demo。

单轮问答只考验 Text2SQL，多轮真正难的是**指代消解**：
用户第二句说"它们的退款金额呢"，"它们"指的是上一轮 SQL 查出来的那三家店铺——
这个信息不在当前 Query 里，只存在于会话记忆中。

这个 Demo 串起五轮对话，覆盖四种典型形态：

    1. 新数据查询          → 走 Text2SQL 链路
    2. 指代 + 新数据       → 走 Text2SQL，但必须先从记忆里解出"它们"
    3. 追问上一轮结果      → 不查库，直接复用已有结果
    4. 指标口径问答        → 不查库，属于业务知识问答
    5. 跨会话召回          → 从个人知识库里捞回历史查询

执行：
    python -m askdata_pipeline.multi_turn_demo
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from askdata_memory import (  # noqa: E402
    ConversationMemoryService,
    MemoryServiceConfig,
    ShortTermMemoryConfig,
)
from askdata_pipeline.dynamic_service import DynamicAskDataService  # noqa: E402
from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402

LINE = "─" * 88

# (Query, 这一轮想验证什么)
TURNS = [
    (
        "销售额最高的三个店铺是哪些",
        "基线轮。没有任何上下文，纯 Text2SQL。",
    ),
    (
        "它们的退款金额分别是多少",
        "指代消解。“它们”不在本句里，只存在于上一轮的查询结果中；"
        "同时这是一次全新的数据需求，必须重新查库。",
    ),
    (
        "刚才第一名的店铺叫什么名字",
        "追问历史结果。答案上一轮已经查到了，不应该再打一次数据库。",
    ),
    (
        "客单价这个指标是怎么算的",
        "指标口径问答。属于业务知识，跟具体数据无关，也不该查库。",
    ),
    (
        "帮我查一下这些店铺的买家数",
        "指代 + 新数据，且此时最早那轮已经滑出短期窗口，"
        "要靠摘要或长期记忆把“这些店铺”找回来。",
    ),
]


def show(label: str, value: str, indent: int = 12) -> None:
    """对齐打印一行。"""
    pad = " " * indent
    lines = str(value).splitlines() or [""]
    print(f"{label:<{indent}}{lines[0]}")
    for extra in lines[1:]:
        print(pad + extra)


def preview(text: str, limit: int = 220) -> str:
    compact = " ".join(str(text).split())
    return compact if len(compact) <= limit else compact[:limit] + "……"


def run_turn(service, *, user_id, session_id, index, query, note, enable_long_term):
    """跑一轮并打印关键环节。"""
    print("\n" + LINE)
    print(f"轮次 {index}　用户：{query}")
    print(LINE)
    print(f"考点：{note}\n")

    result = service.run(
        user_id=user_id,
        session_id=session_id,
        query=query,
        enable_long_term=enable_long_term,
    )

    route = result.decision.route.value
    show("路由", f"{route}　│　查库：{'是' if result.queried_database else '否'}")
    show("理由", result.decision.reason)

    context_text = result.memory_context.to_prompt_context().strip()
    if context_text:
        show("记忆上下文", preview(context_text, 320))

    if result.pipeline_result:
        pipeline_result = result.pipeline_result

        if pipeline_result.rewritten_query:
            show("指代消解", f"→ {pipeline_result.rewritten_query}")

        show("检索关键词", "，".join(pipeline_result.keywords))

        for log in pipeline_result.step_logs:
            show("SQL", " ".join(log.sql.split()))
            execution = log.execution_result

            if not execution.get("success"):
                show("执行", f"❌ {execution.get('error')}")
                continue

            rows = execution.get("rows") or []
            show("执行", f"返回 {execution.get('row_count')} 行")
            for row in rows[:5]:
                show("", "  " + json.dumps(row, ensure_ascii=False))

        if pipeline_result.diagnostics:
            for item in pipeline_result.diagnostics:
                show("降级", "⚠️ " + item.render())
    else:
        show("回答", preview(result.answer, 400))

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AskData 多轮追问 Demo")
    parser.add_argument("--user-id", default="", help="不传则自动生成")
    parser.add_argument("--session-id", default="", help="不传则自动生成")
    parser.add_argument(
        "--memory-db",
        default=str(Path("runtime_data") / "multi_turn_memory.db"),
    )
    parser.add_argument(
        "--db-path",
        default=str(Path("runtime_data") / "ecommerce_demo.db"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    # 降级记录跟在每轮后面展示，这里关掉 logging 避免和正文交错。
    logging.getLogger("askdata").disabled = True

    run_id = uuid.uuid4().hex[:8]
    user_id = args.user_id or f"mt-user-{run_id}"
    session_id = args.session_id or f"mt-session-{run_id}"

    memory = ConversationMemoryService(
        MemoryServiceConfig(
            db_path=Path(args.memory_db),
            # 窗口只留 6 条（3 轮），到第 4、5 轮时最早的对话会被挤出窗口，
            # 正好用来检验摘要和长期记忆能不能把指代对象找回来。
            short_term=ShortTermMemoryConfig(
                max_window_messages=6,
                max_window_tokens=4000,
                async_summary=True,
            ),
        )
    )

    pipeline = AskDataText2SQLPipeline(
        PipelineConfig(
            dataset="ecommerce",
            database_name="ecommerce_db",
            db_path=Path(args.db_path),
            sample_size=5,
        )
    )

    service = DynamicAskDataService(pipeline=pipeline, memory=memory)

    print(LINE)
    print("AskData 多轮追问 Demo　·　电商数据集")
    print(LINE)
    print(f"user_id    {user_id}")
    print(f"session_id {session_id}")

    results = []

    try:
        for index, (query, note) in enumerate(TURNS, start=1):
            # 第一轮结束后把结果存进个人知识库，供后面跨窗口召回。
            if index == 2 and results and results[0].pipeline_result:
                saved = service.save_result_to_personal_knowledge_base(
                    user_id=user_id,
                    result=results[0].pipeline_result,
                )
                print(f"\n［已把轮次 1 的结果存入个人知识库，memory_id={saved.id[:8]}…］")

            results.append(
                run_turn(
                    service,
                    user_id=user_id,
                    session_id=session_id,
                    index=index,
                    query=query,
                    note=note,
                    # 后两轮开启长期记忆召回，补足滑出窗口的上下文。
                    enable_long_term=index >= 4,
                )
            )

        print("\n" + LINE)
        print("小结")
        print(LINE)
        print(f"{'轮次':<6}{'路由':<18}{'查库':<8}问题")
        for index, (result, (query, _)) in enumerate(zip(results, TURNS), start=1):
            route = result.decision.route.value
            hit = "是" if result.queried_database else "否"
            print(f"{index:<7}{route:<19}{hit:<9}{query}")

        queried = sum(1 for item in results if item.queried_database)
        print(
            f"\n{len(TURNS)} 轮对话中 {queried} 轮查了数据库，"
            f"{len(TURNS) - queried} 轮直接用记忆回答，省掉了对应的数据库开销。"
        )

    finally:
        memory.close()


if __name__ == "__main__":
    main()
