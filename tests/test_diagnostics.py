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

import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_diagnostics import (  # noqa: E402
    Codes,
    OnceEmitter,
    collect,
    emit,
    silenced,
)
from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from cot_planning.cot_planner import CotPlanner  # noqa: E402
from cot_planning.thinking_client import ThinkingModelClient  # noqa: E402


def codes_of(diagnostics) -> set:
    return {item.code for item in diagnostics}


class DiagnosticsCoreTestCase(unittest.TestCase):
    """collect / emit / OnceEmitter 的基本行为。"""

    def test_collect_gathers_emitted_diagnostics(self):
        with silenced(), collect() as diagnostics:
            emit(Codes.COT_PARSE_EMPTY, "测试", 字段="a")

        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, Codes.COT_PARSE_EMPTY)
        self.assertIn("字段=a", diagnostics[0].render())

    def test_emit_outside_collect_does_not_raise(self):
        """没有活动的 collect 时 emit 不应该炸，只写日志。"""
        with silenced():
            emit(Codes.COT_PARSE_EMPTY, "没有 collect 也要能调用")

    def test_once_emitter_reports_each_code_only_once(self):
        with silenced(), collect() as diagnostics:
            once = OnceEmitter()
            once.emit(Codes.MODEL_MOCK_FALLBACK, "第一次")
            once.emit(Codes.MODEL_MOCK_FALLBACK, "第二次")
            once.emit(Codes.RERANK_MOCK_FALLBACK, "换个码")

        self.assertEqual(len(diagnostics), 2)


class CotParseDiagnosticTestCase(unittest.TestCase):
    """
    回归守卫：docs/排查记录.md 问题二。

    CoT 解析失败曾经完全静默，导致"四元组看着正常、却一条 SQL 都不生成"。
    """

    def setUp(self):
        self.planner = CotPlanner(thinking_client=ThinkingModelClient())

    def test_unparseable_output_emits_diagnostic(self):
        with silenced(), collect() as diagnostics:
            steps = self.planner.parse_steps("模型这次没按格式输出，只回了一段自然语言。")

        self.assertEqual(steps, [])
        self.assertIn(Codes.COT_PARSE_EMPTY, codes_of(diagnostics))

    def test_empty_output_does_not_emit(self):
        """模型什么都没返回是另一类问题，不在这个探针的职责范围。"""
        with silenced(), collect() as diagnostics:
            self.planner.parse_steps("   ")

        self.assertNotIn(Codes.COT_PARSE_EMPTY, codes_of(diagnostics))

    def test_punctuation_variants_all_parse(self):
        """
        问题二的直接回归守卫。

        正则曾经要求"操作指令"后面必须是半角逗号，
        模型换成句号就整条链路静默中断。这里锁死四种写法都能解析。
        """
        variants = {
            "句号结尾": "操作指令: 先筛选再关联。\n  输出目标: c.d",
            "半角逗号": "操作指令: 先筛选再关联,\n  输出目标: c.d",
            "全角逗号": "操作指令: 先筛选再关联，\n  输出目标: c.d",
            "无标点": "操作指令: 先筛选再关联\n  输出目标: c.d",
        }

        for name, tail in variants.items():
            with self.subTest(写法=name):
                text = f"步骤1：\n(\n  数据库: db,\n  处理对象: a.b,\n  {tail}\n)"

                with silenced(), collect() as diagnostics:
                    steps = self.planner.parse_steps(text)

                self.assertEqual(len(steps), 1, f"{name} 应该解析出 1 个步骤")
                self.assertEqual(steps[0].output_target, "c.d")
                self.assertNotIn(Codes.COT_PARSE_EMPTY, codes_of(diagnostics))


class RecallCapDiagnosticTestCase(unittest.TestCase):
    """
    回归守卫：docs/排查记录.md 问题一。

    精排名额没随 Schema 规模放大，曾经导致静默漏召回输出字段。
    """

    QUERY = "销售额最高的三个店铺是哪些"
    KEYWORDS = ["销售额", "店铺"]

    def _build(self, narrow: bool):
        original = AskDataText2SQLPipeline._build_retrieval_config

        def narrowed(pipeline_self):
            config = original(pipeline_self)
            config.rerank_top_multiplier = 2   # 出事时的参数
            config.rerank_min_top_n = 2
            return config

        if narrow:
            AskDataText2SQLPipeline._build_retrieval_config = narrowed

        try:
            with silenced():
                return AskDataText2SQLPipeline(
                    PipelineConfig(
                        dataset="ecommerce",
                        database_name="ecommerce_db",
                        db_path=Path(tempfile.mkdtemp()) / "ecommerce.db",
                    )
                )
        finally:
            AskDataText2SQLPipeline._build_retrieval_config = original

    def test_narrow_config_emits_recall_capped(self):
        pipeline = self._build(narrow=True)

        with silenced():
            result = pipeline.run(self.QUERY, keywords=self.KEYWORDS)

        self.assertIn(Codes.SCHEMA_RECALL_CAPPED, codes_of(result.diagnostics))

    def test_current_config_does_not_emit_recall_capped(self):
        pipeline = self._build(narrow=False)

        with silenced():
            result = pipeline.run(self.QUERY, keywords=self.KEYWORDS)

        self.assertNotIn(Codes.SCHEMA_RECALL_CAPPED, codes_of(result.diagnostics))


class MockFallbackDiagnosticTestCase(unittest.TestCase):
    """无 Key 时，结果里必须留下"这是 Mock"的痕迹。"""

    def test_pipeline_reports_mock_fallbacks_without_api_key(self):
        with silenced():
            pipeline = AskDataText2SQLPipeline(
                PipelineConfig(db_path=Path(tempfile.mkdtemp()) / "trade.db")
            )
            result = pipeline.run("查询总交易笔数大于50000的利率是多少")

        codes = codes_of(result.diagnostics)

        self.assertIn(Codes.MODEL_MOCK_FALLBACK, codes)
        self.assertIn(Codes.EMBEDDING_MOCK_FALLBACK, codes)
        self.assertIn(Codes.RERANK_MOCK_FALLBACK, codes)

    def test_diagnostics_are_serialized_in_to_dict(self):
        with silenced():
            pipeline = AskDataText2SQLPipeline(
                PipelineConfig(db_path=Path(tempfile.mkdtemp()) / "trade.db")
            )
            payload = pipeline.run("查询总交易笔数大于50000的利率是多少").to_dict()

        self.assertTrue(payload["diagnostics"])
        self.assertTrue(all(isinstance(item, str) for item in payload["diagnostics"]))


class DatabasePrefixTestCase(unittest.TestCase):
    """
    回归守卫：评测 E09。

    模型偶尔把表名写成 `ecommerce_db.fact_user_behavior`，SQLite 直接报
    no such table。这个 bug 是间歇性的——同一道题连过两轮、第三轮才挂，
    靠手跑单条 Query 基本发现不了。
    """

    def setUp(self):
        from sql_generation.coder_client import CoderModelClient

        self.client = CoderModelClient()

    def clean(self, sql: str, database: str = "ecommerce_db"):
        with silenced(), collect() as diagnostics:
            cleaned = self.client.clean_sql(sql, database=database)
        return cleaned, {item.code for item in diagnostics}

    def test_strips_database_prefix_and_reports(self):
        cleaned, codes = self.clean(
            "SELECT COUNT(behavior_id) FROM ecommerce_db.fact_user_behavior "
            "WHERE behavior_type = '加购';"
        )

        self.assertNotIn("ecommerce_db.", cleaned)
        self.assertIn("FROM fact_user_behavior", cleaned)
        self.assertIn(Codes.SQL_DB_PREFIX_STRIPPED, codes)

    def test_strips_every_occurrence(self):
        cleaned, _ = self.clean(
            "SELECT a.x FROM ecommerce_db.t1 a JOIN ecommerce_db.t2 b ON a.id=b.id;"
        )

        self.assertNotIn("ecommerce_db", cleaned)

    def test_case_insensitive(self):
        cleaned, codes = self.clean("SELECT x FROM ECOMMERCE_DB.t;")

        self.assertNotIn("ECOMMERCE_DB", cleaned)
        self.assertIn(Codes.SQL_DB_PREFIX_STRIPPED, codes)

    def test_table_dot_column_is_not_damaged(self):
        """最要紧的一条：正常的 表.字段 限定不能被误伤。"""
        cleaned, codes = self.clean(
            "SELECT fact_order.pay_amount FROM fact_order "
            "JOIN dim_user ON dim_user.user_id = fact_order.user_id;"
        )

        self.assertIn("fact_order.pay_amount", cleaned)
        self.assertIn("dim_user.user_id", cleaned)
        self.assertNotIn(Codes.SQL_DB_PREFIX_STRIPPED, codes)

    def test_no_database_name_is_noop(self):
        cleaned, codes = self.clean("SELECT x FROM t;", database="")

        self.assertEqual(cleaned, "SELECT x FROM t;")
        self.assertNotIn(Codes.SQL_DB_PREFIX_STRIPPED, codes)


if __name__ == "__main__":
    unittest.main()


class EvalErrorClassificationTestCase(unittest.TestCase):
    """
    回归守卫：评测器的故障分类与熔断。

    一次 150 运行的评测跑到一半断网，后面 26 题全部 0.0 秒失败，
    重试空转 162 次，最后仍吐出格式完整的报告——端到端 42%、陷阱题 0/5、
    "三次运行波动 0 题"。每个数字都是假的，但报告看起来毫无异常。

    一个会输出无效数字的评测器，比没有评测器更危险。
    """

    def classify(self, detail: str) -> str:
        from eval.runner import classify_error

        return classify_error(detail)

    def test_dns_failure_is_persistent(self):
        """真实踩到的那条报错，重试一百次也没用。"""
        self.assertEqual(
            self.classify(
                "调用关键词抽取模型失败: <urlopen error [Errno 8] "
                "nodename nor servname provided, or not known>"
            ),
            "persistent",
        )

    def test_auth_and_balance_are_persistent(self):
        for detail in ["HTTP Error 401: Unauthorized", "HTTP Error 402: Insufficient Balance"]:
            with self.subTest(报错=detail):
                self.assertEqual(self.classify(detail), "persistent")

    def test_timeout_and_rate_limit_are_transient(self):
        for detail in ["The read operation timed out", "HTTP Error 429: Too Many Requests"]:
            with self.subTest(报错=detail):
                self.assertEqual(self.classify(detail), "transient")

    def test_sql_error_is_not_infrastructure(self):
        """SQL 报错是系统的真实失败，不该被当成环境故障计入熔断。"""
        self.assertEqual(
            self.classify("no such column: fact_order.category_id"),
            "unknown",
        )

    def test_aborted_carries_progress(self):
        from eval.runner import EvalAborted

        aborted = EvalAborted(reason="DNS 挂了", completed=23, total=50, consecutive=3)

        self.assertEqual(aborted.completed, 23)
        self.assertEqual(aborted.total, 50)
        self.assertEqual(aborted.consecutive, 3)


class MissingSchemaGuardTestCase(unittest.TestCase):
    """
    回归守卫：CoT 判定 Schema 缺失时，必须阻断 SQL 生成。

    光靠 Prompt 约束不住。实测抓到过 CoT 明确写了"缺少发货时间"，
    下游照样用 finish_time - pay_time 算出 93.6 小时交上去——
    嘴上承认、手上照编，比闷头编更有欺骗性，因为它看起来还挺严谨。
    """

    def step(self, database="ecommerce_db", output_target="x.y", processing_objects="a.b"):
        from sql_generation import CotStep

        return CotStep(
            database=database,
            processing_objects=processing_objects,
            operation_instruction="先筛选再关联",
            output_target=output_target,
        )

    def guard(self, cot_step) -> bool:
        from askdata_pipeline.text2sql_pipeline import _is_missing_schema_step

        return _is_missing_schema_step(cot_step)

    def test_missing_database_is_blocked(self):
        self.assertTrue(self.guard(self.step(database="缺失")))

    def test_missing_output_target_is_blocked(self):
        self.assertTrue(
            self.guard(self.step(output_target="缺失，无法生成明确输出目标"))
        )

    def test_normal_step_passes_through(self):
        self.assertFalse(self.guard(self.step()))

    def test_operation_instruction_mentioning_missing_does_not_block(self):
        """
        只看数据库和输出目标两项。

        操作指令是自然语言，里面提到"没有"未必代表整体不可答——
        例如"筛选没有退款记录的订单"就完全是一个正常问题。
        """
        from sql_generation import CotStep

        step = CotStep(
            database="ecommerce_db",
            processing_objects="fact_order.order_id",
            operation_instruction="筛选没有退款记录的订单，再统计数量",
            output_target="订单数量",
        )

        self.assertFalse(self.guard(step))


class SchemaIndexRoundTripTestCase(unittest.TestCase):
    """
    回归守卫：索引往返必须完整还原提示词上下文。

    schema_indexing 模块建了 Milvus 三级索引，主链路却每次启动重扫源库——
    模块从没被接进来过。查下去发现三个层层递进的原因：

    1. 索引只存了 9 个标量字段，而 ColumnSchema 有 17 个。
       description / aliases / samples / business_usage 全都不在里面，
       而它们恰恰是渲染进 CoT 和 SQL 提示词的业务语义。
    2. 两个模块各定义了一份 TableRelation，字段相同但只有一份带
       join_condition 和 relation_key 这两个 property——一调就炸。
    3. 两个模块各实现了一套三级索引文本构建，产出的文本 81 个字段全不一样。

    第三条最要命：光接上不校验的话，链路照样能跑，
    提示词里的业务语义却整段丢失——又一个静默失败。
    所以这条测试断言的不是"能加载"，而是"加载出来的东西一模一样"。
    """

    @classmethod
    def setUpClass(cls):
        try:
            import pymilvus  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("未安装 pymilvus，跳过索引往返测试")

    def test_index_round_trip_preserves_prompt_context(self):
        import shutil
        import tempfile

        import numpy as np

        from askdata_pipeline.demo_data import (
            create_trade_demo_database,
            get_trade_business_meta,
        )
        from askdata_pipeline.local_clients import LocalHashEmbeddingClient
        from schema_indexing.index_builder import SchemaIndexBuilder
        from schema_indexing.milvus_client import (
            MilvusSchemaIndexClient,
            MilvusSchemaIndexConfig,
        )
        from schema_indexing.text_builder import SchemaIndexTextBuilder
        from schema_retrieval.hybrid_schema_retrieval_service import (
            HybridSchemaRetrievalConfig,
            HybridSchemaRetrievalService,
        )
        from schema_retrieval.rerank_client import AliyunRerankClient, AliyunRerankConfig
        from schema_retrieval.sqlite_loader import SQLiteSchemaLoader

        workdir = Path(tempfile.mkdtemp())
        db_path = create_trade_demo_database(workdir / "trade.db")
        business_meta = get_trade_business_meta()

        # 用哈希伪向量，测试不依赖模型下载
        embedding_client = LocalHashEmbeddingClient(dimensions=256)
        rerank_client = AliyunRerankClient(AliyunRerankConfig(api_key="", workspace_id=""))

        tables, _columns, relations = SQLiteSchemaLoader(
            db_path=db_path,
            database_name="trade_db",
            business_meta=business_meta,
            sample_size=5,
        ).load()

        with silenced():
            from_db = HybridSchemaRetrievalService.from_sqlite(
                db_path=db_path,
                database_name="trade_db",
                business_meta=business_meta,
                embedding_client=embedding_client,
                rerank_client=rerank_client,
                keyword_extractor=None,
                config=HybridSchemaRetrievalConfig(),
            )

            uri = str(workdir / "index.db")
            shutil.rmtree(uri, ignore_errors=True)

            SchemaIndexBuilder(
                text_builder=SchemaIndexTextBuilder(),
                embedding_client=embedding_client,
                milvus_client=MilvusSchemaIndexClient(
                    MilvusSchemaIndexConfig(
                        uri=uri, embedding_dim=256, recreate_collection=True
                    )
                ),
            ).build(
                columns=from_db.columns,
                relations=relations,
                tables=tables,
                documents=from_db.documents,
            )

            from_index = HybridSchemaRetrievalService.from_milvus(
                uri=uri,
                embedding_client=embedding_client,
                rerank_client=rerank_client,
                config=HybridSchemaRetrievalConfig(),
            )

        self.assertEqual(len(from_index.documents), len(from_db.documents))

        by_id_db = {d.doc_id: d for d in from_db.documents}
        by_id_ix = {d.doc_id: d for d in from_index.documents}
        self.assertEqual(set(by_id_db), set(by_id_ix))

        for doc_id, doc in by_id_db.items():
            for field_name in ("keyword_text", "vector_text", "rerank_text"):
                with self.subTest(字段=doc_id, 文本=field_name):
                    self.assertEqual(
                        getattr(doc, field_name),
                        getattr(by_id_ix[doc_id], field_name),
                    )

            # 时间约束保底靠它挑字段，它不进任何文本，丢了也不会让上面的比对报错
            with self.subTest(字段=doc_id, 属性="time_coverage"):
                self.assertEqual(doc.column.time_coverage, by_id_ix[doc_id].column.time_coverage)

        self.assertTrue(
            any(doc.column.time_coverage for doc in from_index.documents),
            "测试库里有时间字段，往返后却一个 time_coverage 都没有",
        )

        # 向量必须逐元素一致，否则召回排序会悄悄漂移
        emb_db = {d.doc_id: from_db.vector_index.embeddings[i]
                  for i, d in enumerate(from_db.documents)}
        emb_ix = {d.doc_id: from_index.vector_index.embeddings[i]
                  for i, d in enumerate(from_index.documents)}
        for doc_id in emb_db:
            with self.subTest(向量=doc_id):
                self.assertTrue(np.allclose(emb_db[doc_id], emb_ix[doc_id]))

        # 最终断言：同一个查询，两条路径的提示词上下文逐字节一致
        for query, keywords in [
            ("查询总交易笔数大于50000的利率是多少", ["总交易笔数", "利率"]),
            ("用户的活跃天数是多少", ["活跃天数"]),
        ]:
            with self.subTest(查询=query), silenced():
                left = from_db.retrieve(query=query, keywords=keywords)
                right = from_index.retrieve(query=query, keywords=keywords)
                self.assertEqual(
                    left.schema_graph.to_prompt_context(),
                    right.schema_graph.to_prompt_context(),
                )
