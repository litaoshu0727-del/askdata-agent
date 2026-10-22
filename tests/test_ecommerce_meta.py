from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"

import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_pipeline.ecommerce_data import create_ecommerce_demo_database, get_ecommerce_business_meta  # noqa: E402


class OrderStructureClaimsTest(unittest.TestCase):
    """
    业务元数据里写了库的结构："一笔订单只包含一家店铺的商品，每家店的商品都属于它的主营类目，所以一笔订单只
    属于一个类目""一笔订单最多一条退款"。CoT 靠这几句才不会因为"退款没法分摊到商品"而拒答（第七套 H7E10）。

    这几句是对数据的断言，改了建库代码它们就可能变成假话——这里在生成的库上逐条核实。
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db = create_ecommerce_demo_database(Path(cls._tmp.name) / "ecommerce.db")
        cls.conn = sqlite3.connect(str(cls.db))
        cls.meta = get_ecommerce_business_meta()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls._tmp.cleanup()

    def scalar(self, sql):
        return self.conn.execute(sql).fetchone()[0]

    def test_the_claims_are_in_the_metadata(self):
        self.assertIn("一笔订单里的商品只属于一个二级类目", self.meta["fact_order"]["description"])
        self.assertIn("一笔订单最多一条退款记录", self.meta["fact_refund"]["description"])

    def test_items_of_an_order_come_from_the_order_shop(self):
        self.assertEqual(self.scalar(
            "SELECT COUNT(*) FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id "
            "JOIN dim_product p ON p.product_id = i.product_id WHERE p.shop_id <> o.shop_id"), 0)

    def test_products_belong_to_the_shop_main_category(self):
        self.assertEqual(self.scalar(
            "SELECT COUNT(*) FROM dim_product p JOIN dim_shop s ON s.shop_id = p.shop_id "
            "WHERE p.category_id <> s.main_category_id"), 0)

    def test_an_order_has_one_category(self):
        self.assertEqual(self.scalar(
            "SELECT COUNT(*) FROM (SELECT i.order_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id "
            "GROUP BY i.order_id HAVING COUNT(DISTINCT p.category_id) > 1)"), 0)

    def test_at_most_one_refund_per_order(self):
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM (SELECT order_id FROM fact_refund GROUP BY order_id HAVING COUNT(*) > 1)"), 0)



class DefaultDefinitionTest(unittest.TestCase):
    """
    题目没写订单状态时的默认口径（2026-10-22 定）："买过、已付款、实付、花了多少、消费"只算已付款的订单，即 pay_time
    不为空；"订单数"不加条件。模型原先常把"已付款"写成 order_status = '已支付'，把已完成、已退款的订单漏掉。
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.conn = sqlite3.connect(str(create_ecommerce_demo_database(Path(cls._tmp.name) / "ecommerce.db")))
        cls.meta = get_ecommerce_business_meta()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls._tmp.cleanup()

    def test_the_convention_is_in_the_metadata(self):
        self.assertIn("口径约定（题目没写订单状态时）", self.meta["fact_order"]["description"])
        self.assertIn("不等于「已付款」", self.meta["fact_order"]["columns"]["order_status"]["description"])
        self.assertIn("判断「已付款」就用它", self.meta["fact_order"]["columns"]["pay_time"]["description"])

    def test_pay_time_matches_the_paid_statuses(self):
        """元数据说"pay_time 不为空 = 已支付、已完成、已退款"：改了建库代码这句就可能变成假话。"""
        rows = dict(self.conn.execute(
            "SELECT order_status, SUM(pay_time IS NOT NULL) * 1.0 / COUNT(*) FROM fact_order GROUP BY order_status"
        ).fetchall())
        self.assertEqual({k for k, v in rows.items() if v == 1.0}, {"已支付", "已完成", "已退款"})
        self.assertEqual({k for k, v in rows.items() if v == 0.0}, {"待支付", "已取消"})


if __name__ == "__main__":
    unittest.main()
