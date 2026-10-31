from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_pipeline.objects import PipelineResult, StepExecutionLog  # noqa: E402
from eval.cases import EvalCase, MultiTurnCase  # noqa: E402
from eval.multiturn import run_chain, summarize  # noqa: E402


def turn(case_id, query, tags=(), trap=False):
    return EvalCase(id=case_id, query=query, reference_sql="", tags=list(tags), expect_unanswerable=trap)


CHAIN = MultiTurnCase(id="T01", turns=[
    turn("T01-1", "销售额最高的三家店"),
    turn("T01-2", "它们的退款呢", ["追问:指代"]),
    turn("T01-3", "它们的毛利呢", ["追问:指代", "陷阱题"], trap=True),
    turn("T01-4", "那第一问里的店，上个月呢", ["追问:跨轮", "追问:省略"]),
])
EXPECTED = {"T01-1": [{"v": 1}], "T01-2": [{"v": 2}], "T01-3": [], "T01-4": [{"v": 4}]}


class FakeService:
    """按问题给固定答案：行就当查了库，"qa" 当会话问答；failures 里的问题前几次先超时。"""

    def __init__(self, answers, failures=None):
        self.answers = answers
        self.failures = dict(failures or {})
        self.sessions = []

    def run(self, *, user_id, session_id, query, enable_long_term):
        self.sessions.append(session_id)
        if self.failures.get(query):
            self.failures[query] -= 1
            raise TimeoutError("timed out")
        answer = self.answers[query]
        if answer == "qa":
            return SimpleNamespace(decision=SimpleNamespace(route=SimpleNamespace(value="data_qa")), answer="见上一轮", pipeline_result=None)
        result = PipelineResult(
            query=query, keywords=[], schema_context="", cot_output="", rewritten_query="改写" if "它们" in query else "",
            step_logs=[StepExecutionLog(database="db", cot_step=None, local_schema="", sql="SELECT ...",
                                        execution_request={}, execution_result={"success": True, "rows": answer})],
        )
        return SimpleNamespace(decision=SimpleNamespace(route=SimpleNamespace(value="database_query")), answer="", pipeline_result=result)


class RunChainTest(unittest.TestCase):
    def test_turns_are_judged_one_by_one_in_one_session(self):
        service = FakeService({"销售额最高的三家店": [{"v": 1}], "它们的退款呢": [{"v": 9}],
                               "它们的毛利呢": "qa", "那第一问里的店，上个月呢": [{"v": 4}]})
        run = run_chain(service, CHAIN, EXPECTED, repeat=1, retries=0)
        self.assertEqual([t.outcome.status for t in run.turns], ["pass", "wrong_result", "pass", "pass"])
        self.assertEqual(len(set(service.sessions)), 1)
        self.assertEqual(run.turns[1].rewritten, "改写")

    def test_follow_up_answered_from_memory_is_a_failure(self):
        service = FakeService({"销售额最高的三家店": [{"v": 1}], "它们的退款呢": "qa",
                               "它们的毛利呢": [], "那第一问里的店，上个月呢": [{"v": 4}]})
        run = run_chain(service, CHAIN, EXPECTED, repeat=1, retries=0)
        self.assertEqual(run.turns[1].outcome.status, "routed_qa")

    def test_transient_crash_reruns_the_whole_chain_in_a_new_session(self):
        answers = {"销售额最高的三家店": [{"v": 1}], "它们的退款呢": [{"v": 2}],
                   "它们的毛利呢": [], "那第一问里的店，上个月呢": [{"v": 4}]}
        service = FakeService(answers, failures={"它们的退款呢": 1})
        run = run_chain(service, CHAIN, EXPECTED, repeat=1, retries=1)
        self.assertTrue(run.completed)
        self.assertEqual(run.attempts, 2)
        # 第一次崩在第 2 轮，重跑换了新会话，从第 1 轮问起
        self.assertEqual(len(set(service.sessions)), 2)
        self.assertEqual(len(service.sessions), 2 + 4)

    def test_crash_without_retries_stops_the_chain(self):
        answers = {"销售额最高的三家店": [{"v": 1}], "它们的退款呢": [{"v": 2}],
                   "它们的毛利呢": [], "那第一问里的店，上个月呢": [{"v": 4}]}
        run = run_chain(FakeService(answers, failures={"它们的退款呢": 1}), CHAIN, EXPECTED, repeat=1, retries=0)
        self.assertFalse(run.completed)
        self.assertEqual([t.outcome.status for t in run.turns], ["pass", "crash"])
        self.assertEqual(summarize([run])["incomplete"], 1)


class SummarizeTest(unittest.TestCase):
    def test_conditional_accuracy_drops_follow_ups_after_an_earlier_miss(self):
        good = FakeService({"销售额最高的三家店": [{"v": 1}], "它们的退款呢": [{"v": 2}],
                            "它们的毛利呢": [], "那第一问里的店，上个月呢": [{"v": 4}]})
        bad = FakeService({"销售额最高的三家店": [{"v": 0}], "它们的退款呢": [{"v": 2}],
                           "它们的毛利呢": [{"v": 1}], "那第一问里的店，上个月呢": [{"v": 0}]})
        runs = [run_chain(good, CHAIN, EXPECTED, 1, 0), run_chain(bad, CHAIN, EXPECTED, 2, 0)]
        s = summarize(runs)
        self.assertEqual((s["first"][True], s["first"][False]), (1, 1))
        self.assertEqual((s["follow"][True], s["follow"][False]), (3, 1))
        # 第二次运行第 1 轮就错了，它的追问不算进条件正确率
        self.assertEqual((s["conditional"][True], s["conditional"][False]), (2, 0))
        self.assertEqual((s["traps"][True], s["traps"][False]), (1, 1))
        self.assertEqual((s["chains_ok"], s["chains_total"]), (1, 2))
        self.assertEqual(s["by_tag"]["追问:跨轮"][True], 1)


if __name__ == "__main__":
    unittest.main()
