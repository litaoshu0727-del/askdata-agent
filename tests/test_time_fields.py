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

import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_diagnostics import Codes, collect, silenced  # noqa: E402
from askdata_pipeline.local_clients import LocalHashEmbeddingClient  # noqa: E402
from schema_retrieval.hybrid_schema_retrieval_service import (  # noqa: E402
    HybridSchemaRetrievalConfig,
    HybridSchemaRetrievalService,
)
from schema_retrieval.objects import SchemaHit  # noqa: E402
from schema_retrieval.rerank_client import RerankResult  # noqa: E402
from schema_retrieval.sqlite_loader import SQLiteSchemaLoader  # noqa: E402


def make_db(script: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "test.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(script)
    conn.commit()
    conn.close()
    return path


# 仿 Chinook 的三个时间字段：出生日期、入职日期远早于发票日期。
# 表名按字母序 employee 在 invoice 前面，不按年份筛的话，排在最前的是出生日期。
SALES_DB = """
CREATE TABLE employee (employee_id INTEGER PRIMARY KEY, name TEXT, birth_date DATETIME, hire_date DATETIME);
INSERT INTO employee VALUES (1, 'Andrew', '1958-12-08 00:00:00', '2002-08-14 00:00:00');
INSERT INTO employee VALUES (2, 'Nancy', '1962-02-18 00:00:00', '2003-05-01 00:00:00');
CREATE TABLE invoice (invoice_id INTEGER PRIMARY KEY, total REAL, invoice_date DATETIME);
INSERT INTO invoice VALUES (1, 1.98, '2021-01-01 00:00:00');
INSERT INTO invoice VALUES (2, 3.96, '2023-06-15 00:00:00');
INSERT INTO invoice VALUES (3, 5.94, '2025-12-22 00:00:00');
"""


class TimeCoverageLoaderTestCase(unittest.TestCase):
    """
    回归守卫：时间字段的样例值只取表里前几个不同值。

    Chinook 开票日期的 5 个样例全是 2021 年 1 月上旬，问"2024年"时，精排看到的
    时间字段文本里一个 2024 都没有。加载器从数据算出取值范围和覆盖年份，作为 value_range。
    """

    def load(self, script: str) -> dict:
        _, columns, _ = SQLiteSchemaLoader(db_path=make_db(script), database_name="db").load()
        return {f"{c.table_name}.{c.column_name}": c.value_range for c in columns}

    def test_date_columns_get_range_and_years(self):
        ranges = self.load(SALES_DB)

        self.assertEqual(
            ranges["invoice.invoice_date"],
            "2021-01-01 至 2025-12-22，覆盖 2021年、2023年、2025年",
        )
        self.assertEqual(ranges["employee.hire_date"], "2002-08-14 至 2003-05-01，覆盖 2002年、2003年")
        self.assertEqual(ranges["invoice.total"], "")
        self.assertEqual(ranges["employee.name"], "")

    def test_short_span_is_written_by_month(self):
        """一个季度以内写到月：ecommerce 的订单全在 2024 年 5 月，只写"2024年"太粗。"""
        ranges = self.load(
            "CREATE TABLE o (create_time TEXT);"
            "INSERT INTO o VALUES ('2024-05-01 08:03:00'), ('2024-05-30 23:27:00'), ('2024-06-02 10:00:00');"
        )

        self.assertEqual(ranges["o.create_time"], "2024-05-01 至 2024-06-02，覆盖 2024年5月、2024年6月")

    def test_text_dates_are_detected_by_value(self):
        """声明类型是 TEXT，取值形如日期，照样算——ecommerce 的注册日期就是这样存的。"""
        ranges = self.load(
            "CREATE TABLE u (register_time TEXT);"
            "INSERT INTO u VALUES ('2023-10-27'), ('2021-11-19'), ('2024-03-27'), ('2022-05-27');"
        )

        self.assertEqual(
            ranges["u.register_time"],
            "2021-11-19 至 2024-03-27，覆盖 2021年、2022年、2023年、2024年",
        )

    def test_values_that_are_not_dates_are_left_alone(self):
        ranges = self.load(
            "CREATE TABLE t (ts DATETIME, odd DATE, note TEXT, n INTEGER);"
            "INSERT INTO t VALUES (1714521600, '2024-5-1', '备注', 3);"
            "INSERT INTO t VALUES (1714608000, '2024-06-01', '2024年', 4);"
            "CREATE TABLE empty (dt DATETIME);"
        )

        self.assertEqual(set(ranges.values()), {""})

    def test_malformed_value_between_min_and_max_is_skipped(self):
        """最早、最晚都像日期，中间混着 2024-1-15 这种写法时，不能让整个加载流程挂掉。"""
        ranges = self.load(
            "CREATE TABLE t (d DATE);"
            "INSERT INTO t VALUES ('2024-01-05'), ('2024-1-15'), ('2024-10-01');"
        )

        self.assertEqual(ranges["t.d"], "2024-01-05 至 2024-10-01，覆盖 2024年")

    def test_sparse_dates_over_years_are_written_by_year(self):
        """只有三条记录、却跨了五年：按跨度判断，写年份，不写成三个零散的月份。"""
        ranges = self.load(SALES_DB)

        self.assertEqual(ranges["invoice.invoice_date"], "2021-01-01 至 2025-12-22，覆盖 2021年、2023年、2025年")


class InOrderRerankClient:
    """按传入顺序打分的精排桩：排在最前的就是第一名，结果完全由调用方决定。"""

    def rerank(self, query, documents, top_n):
        return [
            RerankResult(doc_index=document.doc_index, rerank_score=1.0 - rank / 100, text=document.text)
            for rank, document in enumerate(documents)
        ][:top_n]


class TimeFieldGuardTestCase(unittest.TestCase):
    """
    回归守卫：时间约束保底。

    精排按"和整个问题有多相关"打分，时间是约束不是主题——HB16 里 InvoiceDate
    排在 60 个候选的第 41。问题里有时间约束时，从数据覆盖了所提年份的时间字段里
    补回最贴题的一个。不带元数据，验证的是纯数据驱动的那条路径。
    """

    def setUp(self):
        with silenced():
            self.service = HybridSchemaRetrievalService.from_sqlite(
                db_path=make_db(SALES_DB),
                database_name="db",
                business_meta={},
                embedding_client=LocalHashEmbeddingClient(dimensions=32),
                rerank_client=InOrderRerankClient(),
                config=HybridSchemaRetrievalConfig(),
            )

    def hit(self, table: str, column: str) -> SchemaHit:
        document = next(
            d for d in self.service.documents
            if (d.column.table_name, d.column.column_name) == (table, column)
        )
        return SchemaHit(doc_id=document.doc_id, score=1.0, column=document.column)

    def guard(self, query: str, hits: list):
        with silenced(), collect() as diagnostics:
            result = self.service._add_time_field_hits(query=query, schema_hits=list(hits))
        names = [f"{h.column.table_name}.{h.column.column_name}" for h in result]
        rescued = [d for d in diagnostics if d.code == Codes.TIME_FIELD_RESCUED]
        return names, rescued

    def test_adds_the_time_field_that_covers_the_year(self):
        """问 2024 年：出生日期、入职日期都不覆盖 2024 年，只能是发票日期——哪怕它排在最后。"""
        names, rescued = self.guard("2024年一共开了多少张发票", [self.hit("invoice", "total")])

        self.assertIn("invoice.invoice_date", names)
        self.assertEqual(len(rescued), 1)
        self.assertEqual(rescued[0].context["字段"], "invoice.invoice_date")
        self.assertEqual(rescued[0].context["候选数"], 1)

    def test_year_filter_picks_the_older_field_when_asked(self):
        names, _ = self.guard("1960年以前出生的员工有哪些", [self.hit("employee", "name")])

        self.assertIn("employee.birth_date", names)
        self.assertNotIn("invoice.invoice_date", names)

    def test_year_without_data_still_gets_a_time_field(self):
        """问的年份没有数据：照样补一个时间字段，让模型查出"没有数据"，而不是丢掉条件。"""
        names, rescued = self.guard("2030年一共开了多少张发票", [self.hit("invoice", "total")])

        self.assertEqual(len(rescued), 1)
        self.assertEqual(rescued[0].context["候选数"], 3)
        self.assertEqual(len(names), 2)

    def test_month_and_day_count_as_time_constraints(self):
        for query in ("12月开了多少张发票", "5月15日到5月20日的发票", "第一季度的发票", "下半年的发票"):
            with self.subTest(问题=query):
                _, rescued = self.guard(query, [self.hit("invoice", "total")])
                self.assertEqual(len(rescued), 1)

    def test_no_time_constraint_is_a_no_op(self):
        """"最近一次""每个月"不是筛选条件，不触发。"""
        for query in ("一共开了多少张发票", "最近一次开票是哪位员工经手的", "每个月的开票金额"):
            with self.subTest(问题=query):
                names, rescued = self.guard(query, [self.hit("invoice", "total")])
                self.assertEqual(names, ["invoice.total"])
                self.assertEqual(rescued, [])

    def test_time_field_already_present_is_not_added_again(self):
        names, rescued = self.guard(
            "2024年一共开了多少张发票",
            [self.hit("invoice", "total"), self.hit("invoice", "invoice_date")],
        )

        self.assertEqual(names, ["invoice.total", "invoice.invoice_date"])
        self.assertEqual(rescued, [])

    def test_guard_can_be_switched_off(self):
        self.service.config.time_field_guard = False
        names, rescued = self.guard("2024年一共开了多少张发票", [self.hit("invoice", "total")])

        self.assertEqual(names, ["invoice.total"])
        self.assertEqual(rescued, [])


if __name__ == "__main__":
    unittest.main()
