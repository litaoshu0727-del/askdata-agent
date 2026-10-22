"""
Sakila 数据集：第三个库，用来验证泛化。

前八套留出集都出自电商库（我造的）和 Chinook（公开库，但从第二套起反复用、元数据和规则都照着它的失败改过）。
基线已经很高，同一类题分不出版本之间的差别；规则、元数据写法、口径做法能不能搬到一个**没见过的库**上，
在这两个库上测不出来。

Sakila 是 MySQL 官方的示例库：一家 DVD 租赁连锁店，2 家门店、1000 部影片、599 位客户、
约 1.6 万笔租借和付款。16 张表，英文命名，自带的歧义不是我埋的：

    first_name / last_name   演员、客户、员工三张表都有
    name                     影片分类、语言两张表都有
    store_id                 客户（在哪家店注册）、库存（拷贝归哪家店）、员工（在哪家店上班）
    staff_id                 租借（谁办的租借）和付款（谁收的钱），8078 笔不是同一个人
    rental_rate / amount / replacement_cost   标价、实收、赔偿价，都是"钱"

顺序是固定的：**元数据先写完、先提交，再请独立出题人盲写题**；写的时候一道题都没有，
只描述 Schema 和数据本身。

数据来源：https://github.com/jOOQ/sakila 的 sqlite-sakila-db/（BSD-2-Clause），原始数据来自
MySQL 的 Sakila 示例库（BSD）。建库时改了四处，都不碰业务数据：

    1. 先建表、删掉触发器，再灌数据：触发器会把每一行的 last_update 改成建库当时的时间，
       每次建出来都不一样；删掉以后保留数据文件里原来的时间（2006-02-15 前后）
    2. 删掉 5 个视图：链路只读表，参考答案也不该绕过表结构
    3. 删掉空表 film_text：MySQL 全文检索用的影片标题和简介副本，SQLite 版里一行数据都没有
    4. 清空 staff.password：示例数据里是密码的哈希值，不该进提示词的样例值

建库：

    curl -L -O https://raw.githubusercontent.com/jOOQ/sakila/main/sqlite-sakila-db/sqlite-sakila-schema.sql
    curl -L -O https://raw.githubusercontent.com/jOOQ/sakila/main/sqlite-sakila-db/sqlite-sakila-insert-data.sql
    python -m askdata_pipeline.sakila_data --schema sqlite-sakila-schema.sql --data sqlite-sakila-insert-data.sql
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

SAKILA_SOURCE_ENV = "SAKILA_DB"
DEFAULT_PATH = Path("runtime_data") / "sakila.db"


def build_sakila_database(schema_sql: str | Path, data_sql: str | Path, out: str | Path = DEFAULT_PATH) -> Path:
    """从 jOOQ 的两份 SQLite 脚本建库，按模块说明里的四处改动处理。"""
    out = Path(out)
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(out))
    try:
        conn.executescript(Path(schema_sql).read_text(encoding="utf-8"))
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.executescript(Path(data_sql).read_text(encoding="utf-8"))
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'").fetchall():
            conn.execute(f'DROP VIEW "{name}"')
        conn.execute("DROP TABLE IF EXISTS film_text")
        conn.execute("UPDATE staff SET password = NULL")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()
    return out


def create_sakila_database(db_path: str | Path, source: str | Path | None = None) -> Path:
    """
    准备 Sakila 数据库：和 Chinook 一样不生成数据，复制建好的库文件。

    Args:
        db_path: 目标路径。
        source: 源文件路径。为空时读环境变量 SAKILA_DB，再为空则在 runtime_data/sakila.db 找。
    """
    import os

    db_path = Path(db_path)
    for candidate in (source, os.getenv(SAKILA_SOURCE_ENV), DEFAULT_PATH):
        if not candidate:
            continue
        candidate = Path(candidate)
        if candidate.is_file() and candidate.resolve() != db_path.resolve():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, db_path)
            return db_path
        if candidate.is_file():
            return candidate
    if db_path.is_file():
        return db_path

    raise FileNotFoundError(
        "找不到 Sakila 数据库。下载 jOOQ 的两份 SQLite 脚本后建库：\n"
        "  curl -L -O https://raw.githubusercontent.com/jOOQ/sakila/main/sqlite-sakila-db/sqlite-sakila-schema.sql\n"
        "  curl -L -O https://raw.githubusercontent.com/jOOQ/sakila/main/sqlite-sakila-db/sqlite-sakila-insert-data.sql\n"
        "  python -m askdata_pipeline.sakila_data --schema sqlite-sakila-schema.sql --data sqlite-sakila-insert-data.sql"
    )


def get_sakila_business_meta() -> dict:
    """
    15 张表逐一手写。写的时候一道题都没有：只描述 Schema 和数据本身，
    照电商、Chinook 的做法——别名搭中英桥、近义字段在 description 里写清差别、
    只给最容易混的字段手写 keyword_text、精排文本一条不手写（原因见 chinook_data）。
    """
    meta = {}
    meta.update(_catalog_meta())
    meta.update(_people_and_place_meta())
    meta.update(_business_meta())
    return meta


def _last_update(table_cn: str) -> dict:
    """每张表都有 last_update：数据维护时间，不是业务时间。"""
    return {
        "description": (
            f"{table_cn}这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。"
            "不是业务时间：问租借、付款、注册发生在什么时候时不要用它。"
        ),
        "aliases": ["最后更新时间", "修改时间"],
        "semantic_role": "dimension",
    }


def _catalog_meta() -> dict:
    """片库侧：影片、演员、分类、语言，以及两张关联表。"""
    return {
        "film": {
            "description": (
                "影片表，1000 部影片（片名、简介、时长、分级、租借定价）。"
                "一部影片可以有多张实体拷贝放在门店里出租，拷贝在 inventory 表；"
                "租借记录挂在拷贝上，不直接挂在影片上：影片 → inventory → rental。"
                "所有影片的上映年份都是 2006、语言都是英语。"
            ),
            "aliases": ["影片表", "电影表", "片子表", "片库", "DVD 表"],
            "columns": {
                "film_id": {
                    "description": "影片唯一标识。",
                    "aliases": ["影片ID", "电影ID"],
                    "semantic_role": "join_key",
                    "business_usage": "关联 inventory.film_id、film_actor.film_id、film_category.film_id。",
                },
                "title": {
                    "description": "片名，全大写英文，例如 ACADEMY DINOSAUR。问“哪部电影/片名是什么”时输出这个字段。",
                    "aliases": ["片名", "影片名", "电影名", "电影名称", "影片", "电影"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "film.title 片名 影片名 电影名 电影 影片 哪部电影 哪部片子 ACADEMY DINOSAUR",
                },
                "description": {
                    "description": "影片简介，一句英文剧情概要。",
                    "aliases": ["简介", "剧情简介", "影片描述", "内容简介"],
                    "semantic_role": "dimension",
                },
                "release_year": {
                    "description": "上映年份。1000 部影片全是 2006，按年份分组没有区分度。",
                    "aliases": ["上映年份", "发行年份", "出品年份"],
                    "semantic_role": "dimension",
                },
                "language_id": {
                    "description": "影片语言，外键指向 language.language_id。全部影片都是 1（English）。",
                    "aliases": ["语言ID", "影片语言"],
                    "semantic_role": "join_key",
                },
                "original_language_id": {
                    "description": "原始语言，外键指向 language.language_id。全部为空，没有数据。",
                    "aliases": ["原始语言ID", "原声语言"],
                    "semantic_role": "join_key",
                },
                "rental_duration": {
                    "description": (
                        "租期：这部影片一次可以租几天（3 到 7 天），是规定的期限，不是实际租了多久。"
                        "实际租了多久要用 rental.return_date 减 rental.rental_date；超过租期就是逾期。"
                    ),
                    "aliases": ["租期", "可租天数", "规定租期", "租借期限"],
                    "semantic_role": "dimension",
                    "keyword_text": "film.rental_duration 租期 可租天数 规定租期 租借期限 允许租几天 逾期 超期",
                },
                "rental_rate": {
                    "description": (
                        "租借标价：租一次（一个租期）要付多少钱，取值 0.99、2.99、4.99。"
                        "是定价，不是收入；实际收了多少钱看 payment.amount（含逾期费，可能和标价不同）。"
                    ),
                    "aliases": ["租金", "租借价格", "租价", "标价", "定价", "单次租金"],
                    "semantic_role": "measure",
                    "keyword_text": "film.rental_rate 租金 租借价格 租价 标价 定价 租一次多少钱",
                },
                "length": {
                    "description": "片长，单位分钟（46 到 185）。",
                    "aliases": ["片长", "时长", "影片时长", "多少分钟"],
                    "semantic_role": "measure",
                },
                "replacement_cost": {
                    "description": "赔偿价：拷贝丢失或损坏时顾客要赔的钱（9.99 到 29.99）。不是租金，也不是收入。",
                    "aliases": ["赔偿价", "重置成本", "丢失赔偿", "赔偿金额"],
                    "semantic_role": "measure",
                },
                "rating": {
                    "description": "美国电影分级，取值 G、PG、PG-13、R、NC-17。",
                    "aliases": ["分级", "电影分级", "评级", "级别"],
                    "semantic_role": "dimension",
                    "keyword_text": "film.rating 分级 电影分级 评级 级别 G PG PG-13 R NC-17 限制级 儿童",
                },
                "special_features": {
                    "description": (
                        "附赠内容，逗号分隔的组合，取值来自 Trailers、Commentaries、Deleted Scenes、"
                        "Behind the Scenes 四种，例如 Trailers,Commentaries。判断带不带某一种用 LIKE '%Trailers%'。"
                    ),
                    "aliases": ["附赠内容", "特别内容", "花絮", "预告片", "评论音轨", "删减片段", "幕后花絮"],
                    "semantic_role": "dimension",
                },
                "last_update": _last_update("影片"),
            },
        },
        "actor": {
            "description": (
                "演员表，200 位演员。演员和影片是多对多，经 film_actor 关联。"
                "注意与 customer、staff 区分：三张表都有 first_name、last_name，本表是**演员**。"
            ),
            "aliases": ["演员表", "影星表", "艺人表"],
            "columns": {
                "actor_id": {
                    "description": "演员唯一标识。",
                    "aliases": ["演员ID"],
                    "semantic_role": "join_key",
                    "business_usage": "关联 film_actor.actor_id。",
                },
                "first_name": {
                    "description": "演员的名，全大写英文，例如 PENELOPE。customer.first_name 是客户的名，staff.first_name 是员工的名。",
                    "aliases": ["演员名", "演员的名", "名字", "演员姓名"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "actor.first_name 演员 影星 演员名字 演员姓名 演员的名 哪位演员 演员是谁",
                },
                "last_name": {
                    "description": "演员的姓，全大写英文，例如 GUINESS。",
                    "aliases": ["演员姓", "演员的姓", "姓氏", "演员姓名"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "actor.last_name 演员 影星 演员姓 演员姓名 哪位演员 演员是谁",
                },
                "last_update": _last_update("演员"),
            },
        },
        "film_actor": {
            "description": "影片与演员的关联表（多对多），5462 行：一行表示某位演员出演了某部影片。",
            "aliases": ["影片演员关联表", "出演表", "演员阵容"],
            "columns": {
                "actor_id": {
                    "description": "演员，外键指向 actor.actor_id。",
                    "aliases": ["演员ID"],
                    "semantic_role": "join_key",
                },
                "film_id": {
                    "description": "影片，外键指向 film.film_id。",
                    "aliases": ["影片ID"],
                    "semantic_role": "join_key",
                    "business_usage": "数一位演员演过几部影片、一部影片有几位演员，都在这张表上数。",
                },
                "last_update": _last_update("这条出演记录"),
            },
        },
        "category": {
            "description": (
                "影片分类表，16 个类型，例如 Action、Comedy、Horror。"
                "注意 name 字段：本表是分类名，language.name 是语言名。"
            ),
            "aliases": ["分类表", "类型表", "影片类型表", "题材表"],
            "columns": {
                "category_id": {
                    "description": "分类唯一标识。",
                    "aliases": ["分类ID", "类型ID"],
                    "semantic_role": "join_key",
                    "business_usage": "关联 film_category.category_id。",
                },
                "name": {
                    "description": "分类名称，英文，例如 Action、Animation、Children、Comedy、Documentary、Horror。",
                    "aliases": ["分类", "分类名", "类型", "影片类型", "题材", "片种"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "category.name 分类 类型 影片类型 电影类型 题材 片种 按类型 Action Comedy Horror 动作片 喜剧片 恐怖片",
                },
                "last_update": _last_update("分类"),
            },
        },
        "film_category": {
            "description": "影片与分类的关联表，1000 行：每部影片恰好属于一个分类。",
            "aliases": ["影片分类关联表"],
            "columns": {
                "film_id": {
                    "description": "影片，外键指向 film.film_id。",
                    "aliases": ["影片ID"],
                    "semantic_role": "join_key",
                },
                "category_id": {
                    "description": "分类，外键指向 category.category_id。",
                    "aliases": ["分类ID"],
                    "semantic_role": "join_key",
                    "business_usage": "按类型统计影片、租借、收入时，经这张表把影片归到类型上。",
                },
                "last_update": _last_update("这条分类记录"),
            },
        },
        "language": {
            "description": (
                "语言表，6 种语言（English、Italian、Japanese、Mandarin、French、German）。"
                "影片实际只用到 English。注意 name 字段：本表是语言名，category.name 是分类名。"
            ),
            "aliases": ["语言表"],
            "columns": {
                "language_id": {
                    "description": "语言唯一标识。",
                    "aliases": ["语言ID"],
                    "semantic_role": "join_key",
                },
                "name": {
                    "description": "语言名称，英文，例如 English、Japanese。",
                    "aliases": ["语言", "语言名", "语种"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "language.name 语言 语言名 语种 英语 日语 普通话 English Japanese Mandarin",
                },
                "last_update": _last_update("语言"),
            },
        },
    }


def _people_and_place_meta() -> dict:
    """人和地方：客户、员工、门店，以及地址 → 城市 → 国家三层。"""
    return {
        "customer": {
            "description": (
                "客户表，599 位租碟的顾客，记录姓名、邮箱、地址和注册门店。"
                "注意与 staff、actor 区分：三张表都有 first_name、last_name，本表是**租东西的客户**。"
                "客户住在哪个城市、国家，要经 address → city → country 三层关联。"
            ),
            "aliases": ["客户表", "顾客表", "会员表", "租客表"],
            "columns": {
                "customer_id": {
                    "description": "客户唯一标识。",
                    "aliases": ["客户ID", "顾客ID", "会员ID"],
                    "semantic_role": "join_key",
                    "business_usage": "关联 rental.customer_id、payment.customer_id。",
                },
                "store_id": {
                    "description": (
                        "客户注册所在的门店，外键指向 store.store_id。是客户归属哪家店，"
                        "不是每笔租借在哪家店办的：租借在哪家店，看租出去的那张拷贝 inventory.store_id。"
                    ),
                    "aliases": ["注册门店", "所属门店", "客户门店"],
                    "semantic_role": "join_key",
                    "keyword_text": "customer.store_id 客户 注册门店 所属门店 客户归属 哪家店的客户",
                },
                "first_name": {
                    "description": "客户的名，全大写英文，例如 MARY。actor.first_name 是演员的名，staff.first_name 是员工的名。",
                    "aliases": ["客户名", "客户的名", "名字", "客户姓名", "顾客姓名"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "customer.first_name 客户 顾客 会员 客户姓名 客户的名 哪位客户 客户是谁 租得最多的客户",
                },
                "last_name": {
                    "description": "客户的姓，全大写英文，例如 SMITH。",
                    "aliases": ["客户姓", "客户的姓", "姓氏", "客户姓名"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "customer.last_name 客户 顾客 会员 客户姓 客户姓名 哪位客户 客户是谁",
                },
                "email": {
                    "description": "客户邮箱。staff.email 是员工邮箱。",
                    "aliases": ["客户邮箱", "邮箱", "电子邮件"],
                    "semantic_role": "dimension",
                },
                "address_id": {
                    "description": "客户地址，外键指向 address.address_id。",
                    "aliases": ["客户地址ID"],
                    "semantic_role": "join_key",
                    "business_usage": "按城市、国家看客户时，经 address → city → country 关联。",
                },
                "active": {
                    "description": "是否活跃客户，'1' 是活跃（584 位）、'0' 是不活跃（15 位）。存的是字符。",
                    "aliases": ["是否活跃", "活跃状态", "账户状态"],
                    "semantic_role": "dimension",
                },
                "create_date": {
                    "description": "客户记录的创建时间。599 位客户全在 2006-02-14 22:04 这一刻，是导入数据的时间，不能当注册时间做分析。",
                    "aliases": ["创建时间", "建档时间", "注册时间"],
                    "semantic_role": "time",
                },
                "last_update": _last_update("客户"),
            },
        },
        "staff": {
            "description": (
                "员工表，2 位员工（Mike Hillyer、Jon Stephens），各在一家门店上班，也是两家店的店长。"
                "注意与 customer、actor 区分：三张表都有 first_name、last_name，本表是**店员**。"
            ),
            "aliases": ["员工表", "店员表", "职员表"],
            "columns": {
                "staff_id": {
                    "description": "员工唯一标识。",
                    "aliases": ["员工ID", "店员ID"],
                    "semantic_role": "join_key",
                    "business_usage": "rental.staff_id 是办理租借的员工，payment.staff_id 是收款的员工，两者常常不是同一个人。",
                },
                "first_name": {
                    "description": "员工的名，例如 Mike。",
                    "aliases": ["员工名", "员工的名", "店员名字", "员工姓名"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "staff.first_name 员工 店员 职员 员工姓名 员工的名 哪位员工 店长",
                },
                "last_name": {
                    "description": "员工的姓，例如 Hillyer。",
                    "aliases": ["员工姓", "员工的姓", "员工姓名"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "staff.last_name 员工 店员 职员 员工姓 员工姓名 哪位员工 店长",
                },
                "address_id": {
                    "description": "员工住址，外键指向 address.address_id。",
                    "aliases": ["员工地址ID"],
                    "semantic_role": "join_key",
                },
                "picture": {
                    "description": "员工照片，全部为空。",
                    "aliases": ["照片"],
                    "semantic_role": "dimension",
                },
                "email": {
                    "description": "员工邮箱。customer.email 是客户邮箱。",
                    "aliases": ["员工邮箱"],
                    "semantic_role": "dimension",
                },
                "store_id": {
                    "description": "员工上班的门店，外键指向 store.store_id。",
                    "aliases": ["所在门店", "上班门店"],
                    "semantic_role": "join_key",
                },
                "active": {
                    "description": "是否在职，1 是在职。两位员工都在职。",
                    "aliases": ["是否在职", "在职状态"],
                    "semantic_role": "dimension",
                },
                "username": {
                    "description": "员工登录用户名。",
                    "aliases": ["用户名", "登录名"],
                    "semantic_role": "dimension",
                },
                "password": {
                    "description": "登录密码，已清空，不可用。",
                    "aliases": ["密码"],
                    "semantic_role": "dimension",
                },
                "last_update": _last_update("员工"),
            },
        },
        "store": {
            "description": (
                "门店表，2 家门店，各有一位店长（manager_staff_id）和一个地址。"
                "门店本身没有名字，用 store_id（1、2）或门店地址所在城市来称呼。"
            ),
            "aliases": ["门店表", "店铺表", "分店表"],
            "columns": {
                "store_id": {
                    "description": "门店唯一标识，1 或 2。",
                    "aliases": ["门店ID", "门店编号", "店铺ID", "哪家店"],
                    "semantic_role": "join_key",
                    "keyword_text": "store.store_id 门店 门店编号 店铺 分店 哪家店 每家店 按门店",
                },
                "manager_staff_id": {
                    "description": "店长，外键指向 staff.staff_id。",
                    "aliases": ["店长ID", "店长"],
                    "semantic_role": "join_key",
                },
                "address_id": {
                    "description": "门店地址，外键指向 address.address_id。",
                    "aliases": ["门店地址ID"],
                    "semantic_role": "join_key",
                    "business_usage": "门店在哪个城市、国家，经 address → city → country 关联。",
                },
                "last_update": _last_update("门店"),
            },
        },
        "address": {
            "description": (
                "地址表，603 个地址，客户、员工、门店的地址都在这里（customer、staff、store 各有 address_id）。"
                "地址只到街道，城市在 city 表、国家在 country 表。区（district）和电话（phone）这两列没有数据。"
            ),
            "aliases": ["地址表"],
            "columns": {
                "address_id": {
                    "description": "地址唯一标识。",
                    "aliases": ["地址ID"],
                    "semantic_role": "join_key",
                },
                "address": {
                    "description": "街道地址，例如 47 MySakila Drive。",
                    "aliases": ["地址", "街道地址", "详细地址"],
                    "semantic_role": "dimension",
                },
                "address2": {
                    "description": "地址第二行，全部为空。",
                    "aliases": ["地址2", "补充地址"],
                    "semantic_role": "dimension",
                },
                "district": {
                    "description": (
                        "地址所在的区、省或州。这份 SQLite 数据里 603 行全是一个空格，没有数据："
                        "按省、州统计答不了，地域只能到城市（city）和国家（country）。"
                    ),
                    "aliases": ["区", "地区", "省份", "州", "行政区"],
                    "semantic_role": "dimension",
                },
                "city_id": {
                    "description": "所在城市，外键指向 city.city_id。",
                    "aliases": ["城市ID"],
                    "semantic_role": "join_key",
                },
                "postal_code": {
                    "description": "邮编，有 4 个为空。",
                    "aliases": ["邮编", "邮政编码"],
                    "semantic_role": "dimension",
                },
                "phone": {
                    "description": (
                        "联系电话（客户、员工、门店的电话都记在地址上）。这份 SQLite 数据里 603 行全是一个空格，"
                        "没有电话数据。"
                    ),
                    "aliases": ["电话", "联系电话", "手机号"],
                    "semantic_role": "dimension",
                },
                "last_update": _last_update("地址"),
            },
        },
        "city": {
            "description": "城市表，600 个城市，每个城市属于一个国家。客户、门店的城市经 address.city_id 关联到这里。",
            "aliases": ["城市表"],
            "columns": {
                "city_id": {
                    "description": "城市唯一标识。",
                    "aliases": ["城市ID"],
                    "semantic_role": "join_key",
                },
                "city": {
                    "description": (
                        "城市名称，英文，例如 Lethbridge、Woodridge。有一个重名：London 有两个（英国、加拿大），"
                        "按城市分组时连同 city_id 一起分组更稳。"
                    ),
                    "aliases": ["城市", "城市名", "所在城市"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "city.city 城市 城市名 所在城市 哪个城市 按城市",
                },
                "country_id": {
                    "description": "所属国家，外键指向 country.country_id。",
                    "aliases": ["国家ID"],
                    "semantic_role": "join_key",
                },
                "last_update": _last_update("城市"),
            },
        },
        "country": {
            "description": "国家表，109 个国家。客户、门店的国家经 address → city → country 关联到这里。",
            "aliases": ["国家表"],
            "columns": {
                "country_id": {
                    "description": "国家唯一标识。",
                    "aliases": ["国家ID"],
                    "semantic_role": "join_key",
                },
                "country": {
                    "description": "国家名称，英文，例如 Canada、Australia、United States。",
                    "aliases": ["国家", "国家名", "所在国家", "国别"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "country.country 国家 国家名 所在国家 国别 哪个国家 按国家",
                },
                "last_update": _last_update("国家"),
            },
        },
    }


def _business_meta() -> dict:
    """业务侧：库存拷贝、租借、付款。"""
    return {
        "inventory": {
            "description": (
                "库存表，4581 张实体拷贝（DVD）。一部影片可以有多张拷贝，分放在两家门店；"
                "有 42 部影片一张拷贝都没有。租借的是拷贝：rental.inventory_id 指向这里，"
                "要知道租的是哪部影片、在哪家店租的，都要经过本表。"
            ),
            "aliases": ["库存表", "拷贝表", "碟片表", "存货表"],
            "columns": {
                "inventory_id": {
                    "description": "拷贝唯一标识。数“有多少张拷贝/库存多少张”就是数这个字段。",
                    "aliases": ["拷贝ID", "库存ID", "碟片ID"],
                    "semantic_role": "join_key",
                    "keyword_text": "inventory.inventory_id 拷贝 库存 碟片 DVD 有几张 库存数量 多少张拷贝",
                },
                "film_id": {
                    "description": "这张拷贝是哪部影片，外键指向 film.film_id。",
                    "aliases": ["影片ID"],
                    "semantic_role": "join_key",
                    "business_usage": "从租借找到影片：rental.inventory_id → inventory.film_id → film。",
                },
                "store_id": {
                    "description": (
                        "这张拷贝放在哪家门店，外键指向 store.store_id。"
                        "租借在哪家店办的、哪家店的出租量，按租出去的拷贝所在门店算，用这个字段；"
                        "customer.store_id 是客户注册的门店。"
                    ),
                    "aliases": ["所在门店", "库存门店", "拷贝所在门店"],
                    "semantic_role": "join_key",
                    "keyword_text": "inventory.store_id 门店 拷贝所在门店 库存门店 哪家店的库存 哪家店租出 门店出租量",
                },
                "last_update": _last_update("拷贝"),
            },
        },
        "rental": {
            "description": (
                "租借表，16044 笔：一位客户在某个时间租走一张拷贝，归还后记下归还时间。"
                "租借时间从 2005-05-24 到 2006-02-14，集中在 2005 年 5–8 月，2006 年只有 2 月的 182 笔。"
                "每笔租借恰好对应一笔付款（payment.rental_id）。"
                "租的是哪部影片要经 inventory 找到 film，在哪家店租的看 inventory.store_id。"
            ),
            "aliases": ["租借表", "租赁表", "出租记录", "借阅记录", "订单表"],
            "columns": {
                "rental_id": {
                    "description": "租借唯一标识。数“租了多少次/出租量”就是数这个字段。",
                    "aliases": ["租借ID", "租赁ID", "订单ID"],
                    "semantic_role": "join_key",
                    "keyword_text": "rental.rental_id 租借 租赁 出租 租了几次 租借次数 出租量 租借笔数",
                },
                "rental_date": {
                    "description": (
                        "租出时间，带时分秒和毫秒，例如 2005-05-24 22:53:30.000。"
                        "按租借发生的日期、月份统计时用它；payment.payment_date 是付款时间。"
                    ),
                    "aliases": ["租借时间", "租出时间", "租借日期", "借出时间", "下单时间"],
                    "semantic_role": "time",
                    "keyword_text": "rental.rental_date 租借时间 租出时间 租借日期 什么时候租的 按月 每月 哪一天",
                },
                "inventory_id": {
                    "description": "租走的拷贝，外键指向 inventory.inventory_id。",
                    "aliases": ["拷贝ID"],
                    "semantic_role": "join_key",
                },
                "customer_id": {
                    "description": "租借的客户，外键指向 customer.customer_id。",
                    "aliases": ["客户ID"],
                    "semantic_role": "join_key",
                },
                "return_date": {
                    "description": (
                        "归还时间。为空表示还没还（183 笔）。实际租了多久 = 归还时间 − 租出时间；"
                        "超过影片的租期 film.rental_duration 就是逾期。"
                    ),
                    "aliases": ["归还时间", "还碟时间", "归还日期"],
                    "semantic_role": "time",
                    "keyword_text": "rental.return_date 归还时间 归还日期 还了没有 没还 未归还 逾期 超期 实际租了几天",
                },
                "staff_id": {
                    "description": "办理这笔租借的员工，外键指向 staff.staff_id。收款员工是 payment.staff_id，可能是另一位。",
                    "aliases": ["经办员工", "办理员工"],
                    "semantic_role": "join_key",
                },
                "last_update": _last_update("租借记录"),
            },
        },
        "payment": {
            "description": (
                "付款表，16049 笔，本库唯一的收入记录：营业额、收入、客户付了多少钱，都对 amount 求和。"
                "每笔付款对应一笔租借（rental_id），另有 5 笔没有关联租借。"
                "金额是实收，含逾期费，可能和影片标价 rental_rate 不同。"
            ),
            "aliases": ["付款表", "支付表", "收款表", "收入表", "流水表"],
            "columns": {
                "payment_id": {
                    "description": "付款唯一标识。",
                    "aliases": ["付款ID", "支付ID", "流水号"],
                    "semantic_role": "join_key",
                },
                "customer_id": {
                    "description": "付款的客户，外键指向 customer.customer_id。",
                    "aliases": ["客户ID"],
                    "semantic_role": "join_key",
                    "business_usage": "客户消费排行直接按这个字段汇总 amount，不必经过 rental。",
                },
                "staff_id": {
                    "description": (
                        "收款的员工，外键指向 staff.staff_id。办理租借的员工是 rental.staff_id，"
                        "两者有一半左右不是同一个人。"
                    ),
                    "aliases": ["收款员工", "收银员"],
                    "semantic_role": "join_key",
                    "keyword_text": "payment.staff_id 收款员工 收银员 谁收的钱 员工收款 员工营业额",
                },
                "rental_id": {
                    "description": "对应的租借，外键指向 rental.rental_id。有 5 笔为空。",
                    "aliases": ["租借ID"],
                    "semantic_role": "join_key",
                    "business_usage": "按影片、分类、门店拆收入时，经 rental → inventory 关联。",
                },
                "amount": {
                    "description": "实收金额（0 到 11.99），含逾期费。营业额、收入、销售额、客户消费都是对它求和。",
                    "aliases": ["金额", "付款金额", "实收金额", "收入", "营业额", "销售额", "消费金额", "花了多少钱"],
                    "semantic_role": "measure",
                    "keyword_text": "payment.amount 金额 付款金额 实收 收入 营业额 销售额 消费 花了多少钱 付了多少",
                },
                "payment_date": {
                    "description": "付款时间，带时分秒和毫秒。按月统计收入时用它；rental.rental_date 是租出时间。",
                    "aliases": ["付款时间", "支付时间", "付款日期", "收款时间"],
                    "semantic_role": "time",
                    "keyword_text": "payment.payment_date 付款时间 支付时间 付款日期 收款时间 每月收入 按月营业额",
                },
                "last_update": _last_update("付款记录"),
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="从 jOOQ 的 SQLite 脚本建 Sakila 库")
    parser.add_argument("--schema", required=True, help="sqlite-sakila-schema.sql")
    parser.add_argument("--data", required=True, help="sqlite-sakila-insert-data.sql")
    parser.add_argument("--out", default=str(DEFAULT_PATH))
    args = parser.parse_args()
    out = build_sakila_database(args.schema, args.data, args.out)
    print(f"已建好 {out}")


if __name__ == "__main__":
    main()
