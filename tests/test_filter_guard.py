from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_pipeline.filter_guard import FilterValueGuard  # noqa: E402


def build_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE fact_order (
            order_id INTEGER, user_id INTEGER, order_status TEXT,
            pay_amount REAL, finish_time TEXT
        );
        CREATE TABLE fact_user_behavior (
            user_id INTEGER, behavior_type TEXT, stay_seconds INTEGER
        );
        CREATE TABLE dim_user (user_id INTEGER, city TEXT, gender TEXT, user_name TEXT);
        CREATE TABLE dim_shop (shop_id INTEGER, city TEXT);
        CREATE TABLE genre (genre_id INTEGER, name TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO fact_order VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, "已完成", 10.0, "2024-05-01 10:00:00"),
            (2, 2, "已支付", 20.0, None),
            (3, 3, "已退款", 30.0, "2024-05-02 10:00:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO fact_user_behavior VALUES (?, ?, ?)",
        [(1, "浏览", 100), (2, "加购", 5), (3, "收藏", 7)],
    )
    conn.executemany(
        "INSERT INTO dim_user VALUES (?, ?, ?, ?)",
        [(i, city, gender, f"用户{i}") for i, (city, gender) in enumerate(
            [("北京", "男"), ("上海", "女"), ("北京市郊", "男")], start=1
        )],
    )
    conn.executemany("INSERT INTO dim_shop VALUES (?, ?)", [(1, "上海"), (2, "北京")])
    conn.executemany("INSERT INTO genre VALUES (?, ?)", [(1, "Pop"), (2, "Rock")])
    conn.commit()
    conn.close()


class FilterValueGuardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "guard.db"
        build_db(db)
        self.guard = FilterValueGuard.from_sqlite(db)

    def tearDown(self):
        self._tmp.cleanup()

    def test_dropped_filter_is_caught(self):
        """E19 的形态：behavior_type 没召回，SQL 直接去掉了筛选。"""
        dropped = self.guard.find_dropped(
            "用户浏览行为的平均停留时长是多少秒",
            ["SELECT AVG(stay_seconds) FROM fact_user_behavior"],
        )
        self.assertEqual([item.value for item in dropped], ["浏览"])
        self.assertEqual(dropped[0].columns, ["fact_user_behavior.behavior_type"])

    def test_proxy_column_does_not_count_as_used(self):
        """E51 的形态：拿 finish_time IS NOT NULL 凑"已完成"，照样要抓出来。"""
        dropped = self.guard.find_dropped(
            "北京用户的已完成订单一共多少钱",
            [
                "SELECT SUM(o.pay_amount) FROM fact_order o JOIN dim_user u "
                "ON u.user_id = o.user_id WHERE u.city = '北京' AND o.finish_time IS NOT NULL"
            ],
        )
        self.assertEqual([item.value for item in dropped], ["已完成"])

    def test_value_literal_counts_as_used(self):
        dropped = self.guard.find_dropped(
            "已完成订单一共多少钱",
            ["SELECT SUM(pay_amount) FROM fact_order WHERE order_status = '已完成'"],
        )
        self.assertEqual(dropped, [])

    def test_owning_column_counts_as_used(self):
        """换一种写法的筛选（IN、<>）只要碰了所属字段，就不算丢。"""
        dropped = self.guard.find_dropped(
            "已完成订单一共多少钱",
            ["SELECT SUM(pay_amount) FROM fact_order WHERE order_status <> '已支付'"],
        )
        self.assertEqual(dropped, [])

    def test_value_shared_by_two_columns_lists_both(self):
        dropped = self.guard.find_dropped(
            "上海一共有多少订单",
            ["SELECT COUNT(*) FROM fact_order"],
        )
        self.assertEqual(dropped[0].columns, ["dim_shop.city", "dim_user.city"])

    def test_longest_value_wins(self):
        """「北京市郊」命中了，就不再拿「北京」算一次。"""
        self.assertEqual(self.guard.mentioned_values("北京市郊的用户有多少"), ["北京市郊"])

    def test_single_character_values_are_not_indexed(self):
        """单字取值（男 / 女）在中文问句里太容易误撞。"""
        self.assertNotIn("男", self.guard.value_columns)
        self.assertEqual(self.guard.mentioned_values("男装类目卖了多少"), [])

    def test_ascii_values_need_word_boundaries(self):
        self.assertEqual(self.guard.mentioned_values("Pop 流派有多少首"), ["Pop"])
        self.assertEqual(self.guard.mentioned_values("Population 是多少"), [])

    def test_high_cardinality_columns_are_skipped(self):
        guard_db = Path(self._tmp.name) / "wide.db"
        conn = sqlite3.connect(str(guard_db))
        conn.execute("CREATE TABLE t (name TEXT)")
        conn.executemany("INSERT INTO t VALUES (?)", [(f"名字{i}",) for i in range(60)])
        conn.commit()
        conn.close()

        guard = FilterValueGuard.from_sqlite(guard_db, max_distinct=50)
        self.assertEqual(guard.value_columns, {})


if __name__ == "__main__":
    unittest.main()
