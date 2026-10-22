from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.cases import EvalCase  # noqa: E402
from eval.cases_probes import PROBE_BANKS  # noqa: E402
from eval.probe_regression import (  # noqa: E402
    case_index,
    compare,
    fingerprint,
    latest_baseline,
    plan_jobs,
    render,
    summarize,
)


def probe(case_id, batch, control=False, reference="SELECT 1"):
    tags = [batch, "对照"] if control else [batch]
    return EvalCase(id=case_id, query=f"问题 {case_id}", reference_sql=reference, tags=tags)


BANKS = {
    "ecommerce": [probe("X01", "探针:甲"), probe("X02", "探针:甲"), probe("XC1", "探针:甲", control=True),
                  probe("Y01", "探针:乙")],
    "chinook": [probe("Z01", "探针:甲")],
}


def write_runs(run_dir: Path, dataset: str, batch: str, statuses: dict) -> None:
    """按评测器 --save-runs 的格式写几行记录。"""
    with (run_dir / f"{dataset}__{batch.replace(':', '_')}.jsonl").open("a", encoding="utf-8") as file:
        for case_id, runs in statuses.items():
            for index, status in enumerate(runs, start=1):
                file.write(json.dumps({"dataset": dataset, "case_id": case_id, "repeat": index, "status": status},
                                      ensure_ascii=False) + "\n")


def summary(passes: dict, repeat=3, commit="abc1234", fingerprints=None) -> dict:
    """直接造一份 summary.json 的内容：题 → 通过次数。"""
    index = case_index(BANKS)
    cases = {}
    for key, n in passes.items():
        item = dict(index[key])
        if fingerprints and key in fingerprints:
            item["fingerprint"] = fingerprints[key]
        cases[key] = {**item, "passes": n, "runs": repeat, "statuses": ["pass"] * n + ["wrong_result"] * (repeat - n)}
    return {"meta": {"commit": commit, "repeat": repeat, "complete": True, "incomplete": [], "crashes": 0},
            "cases": cases}


class PlanTest(unittest.TestCase):
    def test_real_bank_every_probe_planned_exactly_once(self):
        jobs = plan_jobs()
        planned = [(job.dataset, case_id) for job in jobs for case_id in job.case_ids]
        expected = [(dataset, case.id) for dataset, cases in PROBE_BANKS.items() for case in cases]
        self.assertEqual(sorted(planned), sorted(expected))

    def test_one_job_per_dataset_and_batch_largest_first(self):
        jobs = plan_jobs(BANKS)
        self.assertEqual([(job.dataset, job.batch, len(job.case_ids)) for job in jobs],
                         [("ecommerce", "探针:甲", 3), ("chinook", "探针:甲", 1), ("ecommerce", "探针:乙", 1)])

    def test_batch_filter_and_unknown_batch(self):
        self.assertEqual([job.batch for job in plan_jobs(BANKS, ["探针:乙"])], ["探针:乙"])
        with self.assertRaises(SystemExit):
            plan_jobs(BANKS, ["探针:丙"])


class SummarizeTest(unittest.TestCase):
    def test_counts_passes_and_flags_missing_runs(self):
        jobs = plan_jobs(BANKS)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_runs(run_dir, "ecommerce", "探针:甲", {"X01": ["pass", "pass", "wrong_result"],
                                                         "X02": ["pass", "crash"],  # 熔断，少一次
                                                         "XC1": ["pass"] * 3})
            write_runs(run_dir, "chinook", "探针:甲", {"Z01": ["pass"] * 3})
            # ecommerce 探针:乙 的进程没跑出任何记录
            result = summarize(run_dir, case_index(BANKS), jobs, 3, {"commit": "abc1234"})

        cases = result["cases"]
        self.assertEqual((cases["ecommerce/X01"]["passes"], cases["ecommerce/X01"]["runs"]), (2, 3))
        self.assertEqual(cases["ecommerce/XC1"]["role"], "对照")
        self.assertEqual(cases["chinook/Z01"]["batch"], "探针:甲")
        self.assertFalse(result["meta"]["complete"])
        self.assertEqual(result["meta"]["incomplete"], ["ecommerce/X02", "ecommerce/Y01"])
        self.assertEqual(result["meta"]["crashes"], 1)


class CompareTest(unittest.TestCase):
    def test_better_worse_sharp(self):
        base = summary({"ecommerce/X01": 3, "ecommerce/X02": 3, "ecommerce/XC1": 1, "ecommerce/Y01": 2})
        now = summary({"ecommerce/X01": 1, "ecommerce/X02": 2, "ecommerce/XC1": 3, "ecommerce/Y01": 2})
        diff = compare(now, base)
        self.assertEqual([k for k, *_ in diff["better"]], ["ecommerce/XC1"])
        self.assertEqual(sorted(k for k, *_ in diff["worse"]), ["ecommerce/X01", "ecommerce/X02"])
        self.assertEqual([k for k, *_ in diff["sharp"]], ["ecommerce/X01"])  # 3→1 掉一半以上；3→2 不算

    def test_changed_reference_is_not_compared(self):
        """口径定下来那次改过 10 道探针的参考答案，改前改后的分数不能比。"""
        base = summary({"ecommerce/X01": 3}, fingerprints={"ecommerce/X01": "old"})
        now = summary({"ecommerce/X01": 0})
        diff = compare(now, base)
        self.assertEqual(diff["changed"], ["ecommerce/X01"])
        self.assertEqual(diff["worse"], [])

    def test_new_cases_and_rates_across_repeat_counts(self):
        base = summary({"ecommerce/X01": 1}, repeat=1)
        now = summary({"ecommerce/X01": 2, "chinook/Z01": 3}, repeat=3)
        diff = compare(now, base)
        self.assertEqual(diff["new"], ["chinook/Z01"])
        # 次数不同按通过率比：1/1 → 2/3 是变差，掉了三分之一，不算明显变差
        self.assertEqual(diff["worse"], [("ecommerce/X01", "1/1", "2/3")])
        self.assertEqual(diff["sharp"], [])
        diff = compare(summary({"ecommerce/X01": 1}, repeat=3), base)
        self.assertEqual([k for k, *_ in diff["sharp"]], ["ecommerce/X01"])

    def test_fingerprint_tracks_query_and_reference(self):
        self.assertNotEqual(fingerprint(probe("X01", "探针:甲")), fingerprint(probe("X01", "探针:甲", reference="SELECT 2")))
        self.assertEqual(fingerprint(probe("X01", "探针:甲")), fingerprint(probe("X01", "探针:甲")))


class BaselineTest(unittest.TestCase):
    def test_picks_newest_earlier_complete_run_that_covers_this_one(self):
        full = {"ecommerce/X01": 3, "ecommerce/X02": 3}
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)

            def save(name, data):
                (runs / name).mkdir()
                (runs / name / "summary.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            save("20261020-100000_aaa", summary(full))
            incomplete = summary(full)
            incomplete["meta"]["complete"] = False
            save("20261021-100000_bbb", incomplete)
            save("20261022-090000_ccc", summary({"ecommerce/X01": 3}))   # 只跑了一批
            save("20261023-100000_ddd", summary(full))                   # 比这次晚
            current = runs / "20261022-120000_now"

            self.assertEqual(latest_baseline(runs, current, list(full)).name, "20261020-100000_aaa")
            self.assertEqual(latest_baseline(runs, current, ["ecommerce/X01"]).name, "20261022-090000_ccc")
            self.assertIsNone(latest_baseline(runs, runs / "20261019-000000_old", list(full)))


class RenderTest(unittest.TestCase):
    def test_report_lists_sharp_drops_failures_and_incomplete(self):
        base = summary({"ecommerce/X01": 3, "ecommerce/X02": 3, "ecommerce/XC1": 3, "ecommerce/Y01": 3,
                        "chinook/Z01": 3})
        now = summary({"ecommerce/X01": 1, "ecommerce/X02": 3, "ecommerce/XC1": 3, "ecommerce/Y01": 3,
                       "chinook/Z01": 3})
        now["meta"].update(complete=False, incomplete=["ecommerce/Y01"])
        text = render(now, base, compare(now, base))
        self.assertIn("合计 13/15", text)
        self.assertIn("明显变差（通过率掉一半以上）：ecommerce/X01 3/3→1/3", text)
        self.assertIn("本次没有全对的题", text)
        self.assertIn("⚠️ 不完整", text)
        self.assertIn("探针:甲", text)

    def test_report_without_baseline(self):
        now = summary({"ecommerce/X01": 3})
        self.assertIn("没有可比的上一次完整运行", render(now, None, compare(now, None)))


if __name__ == "__main__":
    unittest.main()
