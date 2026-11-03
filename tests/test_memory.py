from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型，不加载本地大模型。
# 必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in (
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_WORKSPACE_ID",
    "ASKDATA_LOCAL_MODELS",
):
    os.environ.pop(_key, None)

# 降级告警在测试里是预期行为，不需要刷到 stderr；断言仍然基于 collect() 的结果。
import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import json
import tempfile
import threading
import unittest
from pathlib import Path

from askdata_memory import (
    ConversationMemoryService,
    ExtractiveMemorySummarizer,
    LocalMemoryEmbeddingClient,
    MemoryKind,
    MemoryServiceConfig,
    MessageRole,
    ShortTermMemoryConfig,
    ShortTermMemoryService,
    SQLiteMemoryStore,
)
from askdata_memory.long_term import LongTermMemoryService
from askdata_pipeline import (
    AskDataText2SQLPipeline,
    MemoryAwareAskDataService,
    PipelineConfig,
)
from askdata_pipeline.conversation_service import ANSWER_PREVIEW_CHARS, answer_preview


class BlockingSummarizer(ExtractiveMemorySummarizer):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def summarize_conversation(self, previous_summary, messages):
        self.started.set()
        self.release.wait(timeout=5)
        return super().summarize_conversation(previous_summary, messages)


class MemoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_async_summary_never_blocks_context_read(self) -> None:
        store = SQLiteMemoryStore(self.db_path)
        summarizer = BlockingSummarizer()
        service = ShortTermMemoryService(
            store=store,
            summarizer=summarizer,
            config=ShortTermMemoryConfig(
                max_window_messages=2,
                max_window_tokens=1000,
                async_summary=True,
            ),
        )
        try:
            service.add_message(user_id="u1", session_id="s1", role="user", content="第一问")
            service.add_message(user_id="u1", session_id="s1", role="assistant", content="第一答")
            service.add_message(user_id="u1", session_id="s1", role="user", content="第二问")
            self.assertTrue(summarizer.started.wait(timeout=2))

            context_while_running = service.get_context(user_id="u1", session_id="s1")
            self.assertTrue(context_while_running.summary_pending)
            self.assertIsNone(context_while_running.summary)
            self.assertEqual([m.content for m in context_while_running.messages], ["第一答", "第二问"])

            summarizer.release.set()
            service.wait_for_summary(user_id="u1", session_id="s1", timeout=5)
            completed = service.get_context(user_id="u1", session_id="s1")
            self.assertIn("第一问", completed.summary.content)
            self.assertEqual(completed.summary.through_message_id, 1)
        finally:
            summarizer.release.set()
            service.close()

    def test_token_limit_keeps_latest_message(self) -> None:
        store = SQLiteMemoryStore(self.db_path)
        service = ShortTermMemoryService(
            store=store,
            config=ShortTermMemoryConfig(
                max_window_messages=10,
                max_window_tokens=2,
                async_summary=False,
            ),
        )
        try:
            service.add_message(user_id="u1", session_id="s1", role=MessageRole.USER, content="很长的一条消息")
            service.add_message(user_id="u1", session_id="s1", role=MessageRole.ASSISTANT, content="最新消息")
            context = service.get_context(user_id="u1", session_id="s1")
            self.assertEqual([message.content for message in context.messages], ["最新消息"])
            self.assertIsNotNone(context.summary)
        finally:
            service.close()

    def test_payload_does_not_count_toward_the_window(self) -> None:
        """窗口只拼 content。查库回答带着整条链路的 payload，不能因为它被挤出窗口，否则紧接着的追问看不到上一轮。"""
        store = SQLiteMemoryStore(self.db_path)
        service = ShortTermMemoryService(
            store=store,
            config=ShortTermMemoryConfig(max_window_messages=10, max_window_tokens=200, async_summary=False),
        )
        try:
            service.add_message(user_id="u1", session_id="s1", role=MessageRole.USER, content="销售额最高的三家店")
            service.add_message(
                user_id="u1", session_id="s1", role=MessageRole.ASSISTANT,
                content="已完成数据库查询。查询结果：店1、店2、店3", message_type="sql_result",
                payload={"schema_context": "字段说明" * 5000},
            )
            # 旧版本写进库的消息，token_count 把 payload 也算了进去；窗口要按 content 现算
            store.add_message(
                user_id="u1", session_id="s1", role=MessageRole.ASSISTANT, content="上一轮的旧回答",
                message_type="sql_result", payload={}, metadata={}, token_count=99999,
            )
            service.add_message(user_id="u1", session_id="s1", role=MessageRole.USER, content="它们的退款呢")
            context = service.get_context(user_id="u1", session_id="s1")
            self.assertEqual(
                [m.content for m in context.messages],
                ["销售额最高的三家店", "已完成数据库查询。查询结果：店1、店2、店3", "上一轮的旧回答", "它们的退款呢"],
            )
        finally:
            service.close()

    def test_long_term_recall_is_user_isolated_and_filterable(self) -> None:
        store = SQLiteMemoryStore(self.db_path)
        service = LongTermMemoryService(
            store=store,
            embedding_client=LocalMemoryEmbeddingClient(dimensions=128),
        )
        trade = service.save_structured(
            user_id="u1",
            query="查询交易利率",
            result={"interest_rate": 0.035},
            database="trade_db",
            tables=["interest_info"],
        )
        service.save_unstructured(
            user_id="u1",
            title="客服口径",
            content="退款审核通常需要三个工作日",
        )
        service.save_unstructured(
            user_id="u2",
            title="私有信息",
            content="交易利率是百分之九十九",
        )

        hits = service.recall(user_id="u1", query="之前查询的交易利率", top_k=2)
        self.assertEqual(hits[0].memory.id, trade.id)
        self.assertTrue(all(hit.memory.user_id == "u1" for hit in hits))

        filtered = service.recall(
            user_id="u1",
            query="交易",
            top_k=5,
            kinds=[MemoryKind.STRUCTURED],
            metadata_filters={"database": "trade_db", "tables": ["interest_info"]},
        )
        self.assertEqual([hit.memory.id for hit in filtered], [trade.id])

    def test_long_term_is_only_written_by_explicit_save(self) -> None:
        memory = ConversationMemoryService(
            MemoryServiceConfig(
                db_path=self.db_path,
                embedding_dimensions=128,
                use_model_summarizer_when_available=False,
                short_term=ShortTermMemoryConfig(max_window_messages=4),
            )
        )
        try:
            memory.begin_user_turn(user_id="u1", session_id="s1", query="解释这个结果")
            memory.record_assistant_message(
                user_id="u1", session_id="s1", content="这是结果解释"
            )
            self.assertEqual(memory.store.list_long_term_memories(user_id="u1"), [])

            saved = memory.save_unstructured_content(
                user_id="u1", title="结果解释", content="这是结果解释"
            )
            self.assertEqual(
                memory.store.get_long_term_memory(user_id="u1", memory_id=saved.id).id,
                saved.id,
            )
        finally:
            memory.close()

    def test_memory_aware_pipeline_records_turn_and_supports_explicit_save(self) -> None:
        memory = ConversationMemoryService(
            MemoryServiceConfig(
                db_path=self.db_path,
                embedding_dimensions=128,
                use_model_summarizer_when_available=False,
                use_reranker_when_available=False,
            )
        )
        pipeline = AskDataText2SQLPipeline(
            PipelineConfig(db_path=Path(self.temp_dir.name) / "trade.db")
        )
        service = MemoryAwareAskDataService(pipeline, memory)
        try:
            response = service.run(
                user_id="u1",
                session_id="s1",
                query="查询总交易笔数大于50000的利率是多少",
                enable_long_term=False,
            )
            messages = memory.store.list_messages(user_id="u1", session_id="s1")
            self.assertEqual([message.role for message in messages], [MessageRole.USER, MessageRole.ASSISTANT])
            self.assertTrue(response.pipeline_result.step_logs[0].execution_result["success"])
            self.assertEqual(memory.store.list_long_term_memories(user_id="u1"), [])

            saved = service.save_result_to_personal_knowledge_base(
                user_id="u1", result=response.pipeline_result
            )
            self.assertEqual(saved.kind, MemoryKind.STRUCTURED)
            self.assertTrue(saved.metadata["sql"])
            self.assertEqual(saved.metadata["database"], "trade_db")
            self.assertIn("total_trade_count > 50000", saved.metadata["filters"]["sql_where"][0])

            follow_up = service.run(
                user_id="u1",
                session_id="s1",
                query="之前查询的交易利率是多少",
                enable_long_term=True,
            )
            self.assertEqual(follow_up.memory_context.long_term_hits[0].memory.id, saved.id)
        finally:
            memory.close()


def _result(columns, rows, sql="SELECT 1"):
    return {
        "database": "chinook_db", "sql": sql, "success": True, "columns": columns,
        "rows": [dict(zip(columns, row)) for row in rows], "row_count": len(rows), "error": None, "truncated": False,
    }


class AnswerPreviewTestCase(unittest.TestCase):
    """查库回答写进会话记忆的样子：追问的改写和 CoT 读到的上一轮结果。"""

    def test_column_names_are_written_once(self):
        preview = json.loads(answer_preview([_result(["Company", "TotalSpent"], [["JetBrains s.r.o.", 40.62]])]))

        self.assertEqual(preview[0]["columns"], ["Company", "TotalSpent"])
        self.assertEqual(preview[0]["rows"], [["JetBrains s.r.o.", 40.62]])
        self.assertNotIn("rows_note", preview[0])

    def test_ten_companies_fit(self):
        """M1C07-3 那次运行的原样 SQL 和结果：原来的格式 1568 字，第 10 行（Apple Inc.）被截掉。"""
        sql = (
            "SELECT c.FirstName, c.LastName, c.Company, ROUND(SUM(i.Total), 2) AS TotalSpent FROM Customer c "
            "JOIN Employee e ON c.SupportRepId = e.EmployeeId JOIN Invoice i ON i.CustomerId = c.CustomerId "
            "WHERE ((e.FirstName = 'Jane' AND e.LastName = 'Peacock') OR (e.FirstName = 'Margaret' AND e.LastName = 'Park') "
            "OR (e.FirstName = 'Steve' AND e.LastName = 'Johnson')) AND c.Company IS NOT NULL "
            "GROUP BY c.CustomerId, c.FirstName, c.LastName, c.Company;"
        )
        rows = [
            ["Luís", "Gonçalves", "Embraer - Empresa Brasileira de Aeronáutica S.A.", 39.62],
            ["František", "Wichterlová", "JetBrains s.r.o.", 40.62],
            ["Eduardo", "Martins", "Woodstock Discos", 37.62],
            ["Alexandre", "Rocha", "Banco do Brasil S.A.", 37.62],
            ["Roberto", "Almeida", "Riotur", 37.62],
            ["Mark", "Philips", "Telus", 37.62],
            ["Jennifer", "Peterson", "Rogers Canada", 38.62],
            ["Frank", "Harris", "Google Inc.", 37.62],
            ["Jack", "Smith", "Microsoft Corporation", 39.62],
            ["Tim", "Goyer", "Apple Inc.", 38.62],
        ]
        result = _result(["FirstName", "LastName", "Company", "TotalSpent"], rows, sql)

        self.assertGreater(len(json.dumps([result], ensure_ascii=False)), ANSWER_PREVIEW_CHARS)
        preview = json.loads(answer_preview([result]))
        self.assertEqual(preview[0]["rows"], rows)

    def test_long_result_is_cut_at_whole_rows(self):
        rows = [[f"客户{i}", i * 1.5] for i in range(200)]
        text = answer_preview([_result(["name", "spent"], rows)])
        preview = json.loads(text)

        self.assertLessEqual(len(text), ANSWER_PREVIEW_CHARS)
        kept = preview[0]["rows"]
        self.assertGreater(len(kept), 10)
        self.assertEqual(kept, rows[: len(kept)])
        self.assertEqual(preview[0]["rows_note"], f"共 200 行，只列出前 {len(kept)} 行")

    def test_last_step_gets_rows_first(self):
        first = _result(["id"], [[i] for i in range(300)])
        last = _result(["name", "spent"], [["JetBrains s.r.o.", 40.62], ["Embraer", 39.62]])
        preview = json.loads(answer_preview([first, last]))

        self.assertEqual(len(preview[1]["rows"]), 2)
        self.assertIn("rows_note", preview[0])

    def test_overlong_sql_falls_back_to_char_cut(self):
        text = answer_preview([_result(["n"], [[1]], sql="SELECT " + "a" * 3000)])

        self.assertLessEqual(len(text), ANSWER_PREVIEW_CHARS)
        self.assertTrue(text.endswith("……"))


if __name__ == "__main__":
    unittest.main()
