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

from askdata_pipeline.sakila_data import build_sakila_database, get_sakila_business_meta  # noqa: E402

SAKILA_DB = ROOT / "runtime_data" / "sakila.db"


class BuildTest(unittest.TestCase):
    """建库时的四处改动，用一份迷你脚本测，不需要下载的数据，CI 上也能跑。"""

    SCHEMA = """
    CREATE TABLE actor (actor_id INTEGER PRIMARY KEY, first_name VARCHAR(45), last_update TIMESTAMP);
    CREATE TRIGGER actor_trigger_ai AFTER INSERT ON actor
     BEGIN
      UPDATE actor SET last_update = DATETIME('NOW') WHERE rowid = new.rowid;
     END;
    CREATE TABLE staff (staff_id INTEGER PRIMARY KEY, username VARCHAR(16), password VARCHAR(40));
    CREATE TABLE film_text (film_id INTEGER PRIMARY KEY, title VARCHAR(255));
    CREATE VIEW actor_list AS SELECT first_name FROM actor;
    """
    DATA = """
    Insert into actor (actor_id,first_name,last_update) Values ('1','PENELOPE','2006-02-15 04:34:33.000');
    Insert into staff (staff_id,username,password) Values ('1','Mike','8cb2237d0679ca88db6464eac60da96345513964');
    """

    def test_build_keeps_original_timestamps_and_drops_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "schema.sql").write_text(self.SCHEMA, encoding="utf-8")
            (tmp / "data.sql").write_text(self.DATA, encoding="utf-8")
            out = build_sakila_database(tmp / "schema.sql", tmp / "data.sql", tmp / "sakila.db")
            conn = sqlite3.connect(str(out))
            try:
                kinds = {row[0] for row in conn.execute("SELECT type FROM sqlite_master")}
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                self.assertNotIn("trigger", kinds)
                self.assertNotIn("view", kinds)
                self.assertEqual(tables, {"actor", "staff"})
                # 触发器没删的话，这里会是建库当时的时间
                self.assertEqual(conn.execute("SELECT last_update FROM actor").fetchone()[0], "2006-02-15 04:34:33.000")
                self.assertIsNone(conn.execute("SELECT password FROM staff").fetchone()[0])
            finally:
                conn.close()


@unittest.skipUnless(SAKILA_DB.is_file(), "没有 runtime_data/sakila.db（不进仓库，CI 上没有）")
class MetaMatchesDatabaseTest(unittest.TestCase):
    """
    元数据和库对得上：表和字段一个不多一个不少，描述里写的每个数都在库上核实。

    这份元数据是在没有题的时候写的，里面的数字（几部影片、几笔没还）会被模型当成事实用；
    写错了模型就会照着错。改了建库代码，这些话变成假话时测试会失败。
    """

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(f"file:{SAKILA_DB}?mode=ro", uri=True)
        cls.meta = get_sakila_business_meta()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def one(self, sql):
        return self.conn.execute(sql).fetchone()[0]

    def test_tables_and_columns_match(self):
        tables = {row[0] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
        self.assertEqual(set(self.meta), tables)
        for table in tables:
            with self.subTest(表=table):
                columns = {row[1] for row in self.conn.execute(f'PRAGMA table_info("{table}")')}
                self.assertEqual(set(self.meta[table]["columns"]), columns)

    def test_row_counts_in_descriptions(self):
        for table, count in {"film": 1000, "actor": 200, "film_actor": 5462, "category": 16, "film_category": 1000,
                             "language": 6, "customer": 599, "staff": 2, "store": 2, "address": 603, "city": 600,
                             "country": 109, "inventory": 4581, "rental": 16044, "payment": 16049}.items():
            with self.subTest(表=table):
                self.assertEqual(self.one(f"SELECT COUNT(*) FROM {table}"), count)

    def test_film_claims(self):
        self.assertEqual(self.one("SELECT COUNT(DISTINCT release_year) || MIN(release_year) FROM film"), "12006")
        self.assertEqual(self.one("SELECT COUNT(DISTINCT language_id) || MIN(language_id) FROM film"), "11")
        self.assertEqual(self.one("SELECT COUNT(original_language_id) FROM film"), 0)
        self.assertEqual(self.one("SELECT MIN(rental_duration) || '-' || MAX(rental_duration) FROM film"), "3-7")
        self.assertEqual(self.one("SELECT group_concat(DISTINCT rental_rate) FROM (SELECT rental_rate FROM film ORDER BY 1)"),
                         "0.99,2.99,4.99")
        self.assertEqual(self.one("SELECT MIN(length) || '-' || MAX(length) FROM film"), "46-185")
        self.assertEqual(self.one("SELECT MIN(replacement_cost) || '-' || MAX(replacement_cost) FROM film"), "9.99-29.99")
        self.assertEqual(self.one("SELECT group_concat(DISTINCT rating) FROM (SELECT rating FROM film ORDER BY 1)"),
                         "G,NC-17,PG,PG-13,R")
        self.assertEqual(self.one("SELECT MAX(n) FROM (SELECT COUNT(*) n FROM film_category GROUP BY film_id)"), 1)
        self.assertEqual(self.one(
            "SELECT COUNT(*) FROM film f WHERE NOT EXISTS (SELECT 1 FROM inventory i WHERE i.film_id = f.film_id)"), 42)

    def test_rental_and_payment_claims(self):
        self.assertEqual(self.one("SELECT SUM(return_date IS NULL) FROM rental"), 183)
        self.assertEqual(self.one("SELECT MIN(rental_date) FROM rental"), "2005-05-24 22:53:30.000")
        self.assertTrue(self.one("SELECT MAX(rental_date) FROM rental").startswith("2006-02-14"))
        self.assertEqual(self.one("SELECT COUNT(*) FROM rental WHERE rental_date LIKE '2006-%'"), 182)
        self.assertEqual(self.one("SELECT COUNT(*) FROM rental WHERE substr(rental_date, 1, 7) NOT IN "
                                  "('2005-05','2005-06','2005-07','2005-08','2006-02')"), 0)
        # 每笔租借恰好一笔付款；5 笔付款没有租借
        self.assertEqual(self.one("SELECT MAX(n) FROM (SELECT COUNT(*) n FROM payment WHERE rental_id IS NOT NULL GROUP BY rental_id)"), 1)
        self.assertEqual(self.one(
            "SELECT COUNT(*) FROM rental r WHERE NOT EXISTS (SELECT 1 FROM payment p WHERE p.rental_id = r.rental_id)"), 0)
        self.assertEqual(self.one("SELECT SUM(rental_id IS NULL) FROM payment"), 5)
        self.assertEqual(self.one("SELECT MIN(amount) || '-' || MAX(amount) FROM payment"), "0-11.99")
        # 收款员工和办理租借的员工，一半左右不是同一个人
        mismatch = self.one("SELECT AVG(p.staff_id <> r.staff_id) FROM payment p JOIN rental r ON r.rental_id = p.rental_id")
        self.assertTrue(0.4 < mismatch < 0.6, mismatch)

    def test_people_and_place_claims(self):
        self.assertEqual(self.one("SELECT group_concat(active || ':' || n) FROM (SELECT active, COUNT(*) n FROM customer GROUP BY active)"),
                         "0:15,1:584")
        self.assertEqual(self.one("SELECT COUNT(*) FROM customer WHERE create_date NOT LIKE '2006-02-14 22:04%'"), 0)
        self.assertEqual(self.one("SELECT group_concat(first_name || ' ' || last_name) FROM staff"), "Mike Hillyer,Jon Stephens")
        self.assertEqual(self.one("SELECT COUNT(*) FROM store s JOIN staff t ON t.staff_id = s.manager_staff_id"), 2)
        self.assertEqual(self.one("SELECT COUNT(password) + COUNT(picture) FROM staff"), 0)
        self.assertEqual(self.one("SELECT COUNT(*) FROM address WHERE TRIM(district) <> '' OR TRIM(phone) <> ''"), 0)
        self.assertEqual(self.one("SELECT COUNT(address2) FROM address"), 0)
        self.assertEqual(self.one("SELECT SUM(postal_code IS NULL OR postal_code = '') FROM address"), 4)
        self.assertEqual(self.one(
            "SELECT group_concat(co.country) FROM city c JOIN country co ON co.country_id = c.country_id "
            "WHERE c.city = 'London' ORDER BY 1"), "United Kingdom,Canada")
        self.assertEqual(self.one("SELECT COUNT(*) FROM (SELECT city FROM city GROUP BY city HAVING COUNT(*) > 1)"), 1)
        self.assertEqual(self.one("SELECT group_concat(name) FROM language"), "English,Italian,Japanese,Mandarin,French,German")
        stores = self.one("SELECT group_concat(c.city) FROM store s JOIN address a ON a.address_id = s.address_id "
                          "JOIN city c ON c.city_id = a.city_id ORDER BY s.store_id")
        self.assertEqual(stores, "Lethbridge,Woodridge")

    def test_last_update_is_not_build_time(self):
        """触发器没删的话，last_update 会是建库当时的时间。"""
        for table in self.meta:
            with self.subTest(表=table):
                self.assertLess(self.one(f"SELECT MAX(last_update) FROM {table}"), "2007")


if __name__ == "__main__":
    unittest.main()
