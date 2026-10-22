from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from askdata_pipeline.ecommerce_data import create_ecommerce_demo_database  # noqa: E402
from eval.cases_probes import PROBE_BANKS, WRONG_SQL  # noqa: E402
from eval.runner import BANKS, DATASETS, case_ndigits, load_expected, normalize_rows  # noqa: E402

BATCH_TAGS = {"探针:整数除法", "探针:整数除法二", "探针:一对多", "探针:一对多二", "探针:每组前N", "探针:每组前N二", "探针:时间差", "探针:时间差二", "探针:唯一与挂单", "探针:唯一与挂单二", "探针:口径", "探针:口径二"}
NO_WRONG_SQL = {"对照", "窗口筛选"}
CHINOOK_DB = ROOT / "runtime_data" / "chinook.db"


def answer(db_path: Path, case, sql: str) -> list:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute(sql)]
    finally:
        conn.close()
    return normalize_rows(rows, case.ordered, case_ndigits(case))


class ProbeBankShapeTest(unittest.TestCase):
    """探针题库的结构：题号不撞、每道属于一个批次、该出错的题都附了错误写法。"""

    def all_probes(self):
        return [case for cases in PROBE_BANKS.values() for case in cases]

    def test_ids_are_unique_and_do_not_collide_with_other_banks(self):
        probe_ids = [case.id for case in self.all_probes()]
        self.assertEqual(len(probe_ids), len(set(probe_ids)))

        other_ids = {case.id for cases, _, _ in DATASETS.values() for case in cases}
        other_ids |= {
            case.id
            for name, banks in BANKS.items() if name != "probes"
            for cases in banks.values() for case in cases
        }
        self.assertFalse(set(probe_ids) & other_ids)

    def test_every_probe_belongs_to_exactly_one_batch(self):
        for case in self.all_probes():
            with self.subTest(case=case.id):
                self.assertEqual(len(BATCH_TAGS & set(case.tags)), 1)

    def test_wrong_sql_exactly_for_non_control_probes(self):
        """对照题本来就该那样写，窗口筛选题的失败是报错，都没有"错误写法"；其余每道都要有。"""
        for case in self.all_probes():
            with self.subTest(case=case.id):
                self.assertEqual(case.id in WRONG_SQL, not NO_WRONG_SQL & set(case.tags))
        self.assertEqual(set(WRONG_SQL), {case.id for case in self.all_probes() if not NO_WRONG_SQL & set(case.tags)})


class ProbeDiscriminationTest(unittest.TestCase):
    """
    每道探针的参考 SQL 能跑出结果，错误写法的答案和它不同。

    答案相同的探针量不出规则的作用：整数相除碰巧整除、连接碰巧一对一，规则加不加都对。
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        # 固定随机种子，和评测用的那份逐行一致
        cls.ecommerce_db = create_ecommerce_demo_database(Path(cls._tmp.name) / "ecommerce.db")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def check(self, db_path: Path, cases):
        for case in cases:
            with self.subTest(case=case.id):
                expected = load_expected(db_path, case)
                self.assertTrue(expected, "参考 SQL 没有返回任何行")

                if case.id in WRONG_SQL:
                    self.assertNotEqual(
                        answer(db_path, case, WRONG_SQL[case.id]),
                        answer(db_path, case, case.reference_sql),
                    )

    def test_ecommerce_probes(self):
        self.check(self.ecommerce_db, PROBE_BANKS["ecommerce"])

    @unittest.skipUnless(CHINOOK_DB.is_file(), "没有 runtime_data/chinook.db（不进仓库，CI 上没有）")
    def test_chinook_probes(self):
        self.check(CHINOOK_DB, PROBE_BANKS["chinook"])


if __name__ == "__main__":
    unittest.main()
