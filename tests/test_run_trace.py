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

import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_diagnostics import silenced  # noqa: E402
from askdata_pipeline.filter_guard import DroppedFilter  # noqa: E402
from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from eval.cases import EvalCase  # noqa: E402
from eval.runner import RunRecorder, run_case  # noqa: E402
from mcp_router.objects import MCPExecutionResult  # noqa: E402

# 没有 Key 时 CoT 和 SQL 走 Mock，这道是 Mock 内置的题，离线就能跑完整条链路
QUERY = "查询总交易笔数大于50000的利率是多少"


class _DropOnce:
    """第一次报"丢了筛选值"，之后不再报——逼出一次守卫重规划。"""

    def __init__(self):
        self.calls = 0

    def find_dropped(self, query, sqls):
        self.calls += 1
        return [DroppedFilter(value="已支付", columns=["fact_order.order_status"])] if self.calls == 1 else []


class SqlTraceTest(unittest.TestCase):
    """
    sql_trace 要留下每一条执行过的 SQL，包括后来被替换掉的。

    H3E13 当时没法确认是不是守卫把模型带错的，就是因为守卫重规划前的首轮 SQL
    没有留存，step_logs 里只有最终那一版。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        with silenced():
            self.pipeline = AskDataText2SQLPipeline(
                PipelineConfig(db_path=Path(self._tmp.name) / "trade.db")
            )

    def tearDown(self):
        self._tmp.cleanup()

    def run_pipeline(self):
        with silenced():
            return self.pipeline.run(QUERY)

    def test_single_run_records_one_entry(self):
        result = self.run_pipeline()

        self.assertEqual(len(result.sql_trace), 1)
        entry = result.sql_trace[0]
        self.assertEqual((entry["attempt"], entry["phase"], entry["kind"]), (1, "首轮", "生成"))
        self.assertTrue(entry["success"])
        self.assertEqual(entry["sql"], " ".join(result.step_logs[-1].sql.split()))

    def test_guard_retry_keeps_the_first_sql(self):
        self.pipeline.filter_guard = _DropOnce()
        result = self.run_pipeline()

        phases = [entry["phase"] for entry in result.sql_trace]
        self.assertEqual(phases, ["首轮", "守卫重规划"])
        self.assertTrue(result.sql_trace[1]["full_schema"])
        # step_logs 只剩重规划之后那一版
        self.assertEqual(len(result.step_logs), 1)
        self.assertEqual(result.sql_trace[-1]["sql"], " ".join(result.step_logs[-1].sql.split()))

    def test_repair_keeps_the_failed_sql(self):
        router = self.pipeline.mcp_router
        original = router.execute
        calls = []

        def fail_first(request):
            calls.append(request)
            if len(calls) == 1:
                # 链路传给路由的是 dict（execution_request）
                return MCPExecutionResult(
                    database=request["database"], sql=request["sql"],
                    success=False, error="no such column: x",
                )
            return original(request)

        router.execute = fail_first
        result = self.run_pipeline()

        kinds = [(entry["kind"], entry["success"]) for entry in result.sql_trace]
        self.assertEqual(kinds, [("生成", False), ("修正", True)])
        self.assertEqual(result.sql_trace[0]["error"], "no such column: x")

    def test_self_consistency_keeps_every_attempt(self):
        self.pipeline.config.self_consistency_runs = 3
        result = self.run_pipeline()

        self.assertEqual([entry["attempt"] for entry in result.sql_trace], [1, 2, 3])

    def test_to_dict_includes_trace(self):
        payload = self.run_pipeline().to_dict()
        self.assertEqual(len(payload["sql_trace"]), 1)


class RunRecorderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "runs" / "trace.jsonl"
        with silenced():
            self.pipeline = AskDataText2SQLPipeline(
                PipelineConfig(db_path=Path(self._tmp.name) / "trade.db")
            )
        self.case = EvalCase(
            id="T01",
            query=QUERY,
            reference_sql=(
                "SELECT interest_info.interest_rate FROM trade_summary JOIN interest_info "
                "ON trade_summary.user_id = interest_info.user_id "
                "WHERE trade_summary.total_trade_count > 50000"
            ),
        )

    def tearDown(self):
        self._tmp.cleanup()

    def outcome(self):
        with silenced():
            return run_case(self.pipeline, Path(self.pipeline.config.db_path), self.case)

    def read_lines(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def test_record_carries_trace_and_meta(self):
        recorder = RunRecorder(self.path, {"run_id": "r1", "commit": "abc"})
        recorder.write(self.outcome(), arm="full", repeat_index=2)

        # 逐行 flush：没 close 也已经落盘，评测中途熔断时记录不丢
        line = self.read_lines()[0]
        recorder.close()

        self.assertEqual((line["run_id"], line["commit"], line["case_id"]), ("r1", "abc", "T01"))
        self.assertEqual((line["arm"], line["repeat"]), ("full", 2))
        self.assertEqual(len(line["sql_trace"]), 1)
        self.assertIn("cot_output", line)
        self.assertTrue(line["diagnostics"])
        self.assertEqual(line["expected_rows"], len(line["expected_sample"]))

    def test_appends_instead_of_overwriting(self):
        for run_id in ("r1", "r2"):
            recorder = RunRecorder(self.path, {"run_id": run_id})
            recorder.write(self.outcome(), arm="full", repeat_index=1)
            recorder.close()

        self.assertEqual([line["run_id"] for line in self.read_lines()], ["r1", "r2"])


if __name__ == "__main__":
    unittest.main()
