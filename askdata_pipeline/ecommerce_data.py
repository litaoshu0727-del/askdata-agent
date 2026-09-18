"""
电商数据分析 Demo 数据集。

相比原始的两张交易表，这套 Schema 有 11 张表、70 多个字段，
分 dim / fact / dws 三层，更接近真实数仓，也才真正用得上
"关键词召回 + 向量召回 + RRF 融合 + Rerank 精排"这一整套两阶段检索。

数据用固定随机种子生成，每次结果一致；
dws 汇总层由事实表聚合而来，保证口径与明细对得上。
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

RANDOM_SEED = 20260918

START_DATE = date(2024, 5, 1)
DAYS = 30

CITIES = [
    ("北京", "北京"),
    ("上海", "上海"),
    ("广州", "广东"),
    ("深圳", "广东"),
    ("杭州", "浙江"),
    ("成都", "四川"),
    ("武汉", "湖北"),
    ("西安", "陕西"),
    ("南京", "江苏"),
    ("苏州", "江苏"),
]

MEMBER_LEVELS = ["普通会员", "银卡会员", "金卡会员", "钻石会员"]
REGISTER_CHANNELS = ["APP", "小程序", "H5", "PC官网"]
AGE_GROUPS = ["18-24", "25-30", "31-40", "41-50", "50以上"]
ORDER_CHANNELS = ["APP", "小程序", "PC官网", "直播间"]
PAY_CHANNELS = ["支付宝", "微信支付", "银行卡", "花呗分期"]
REFUND_REASONS = ["七天无理由", "商品质量问题", "发错货", "物流损坏", "拍错了"]

CATEGORIES = [
    (1, "美妆护肤", None, 1),
    (2, "数码电器", None, 1),
    (3, "食品生鲜", None, 1),
    (101, "面部护肤", 1, 2),
    (102, "彩妆香水", 1, 2),
    (103, "洗护发品", 1, 2),
    (201, "手机通讯", 2, 2),
    (202, "电脑办公", 2, 2),
    (203, "家用电器", 2, 2),
    (301, "休闲零食", 3, 2),
    (302, "生鲜果蔬", 3, 2),
    (303, "粮油调味", 3, 2),
]

LEAF_CATEGORY_IDS = [101, 102, 103, 201, 202, 203, 301, 302, 303]

SHOP_NAME_PARTS = [
    "优选", "臻品", "严选", "旗舰", "直营", "甄品", "好物", "尚品",
    "壹号", "潮玩", "京选", "臻选", "云集", "百草", "鲜生",
]

BRANDS = {
    101: ["兰蔻", "雅诗兰黛", "薇诺娜", "珀莱雅"],
    102: ["花西子", "完美日记", "YSL", "colorkey"],
    103: ["潘婷", "卡诗", "阿道夫", "施华蔻"],
    201: ["华为", "小米", "OPPO", "vivo"],
    202: ["联想", "戴尔", "华硕", "苹果"],
    203: ["美的", "格力", "海尔", "西门子"],
    301: ["三只松鼠", "良品铺子", "百草味", "盐津铺子"],
    302: ["百果园", "佳沃", "都乐", "鲜丰"],
    303: ["金龙鱼", "海天", "鲁花", "太太乐"],
}

PRODUCT_SUFFIX = {
    101: ["精华液 30ml", "面霜 50g", "水乳套装", "面膜 10片装"],
    102: ["口红 正橘色", "气垫BB 15g", "眼影盘 12色", "香水 50ml"],
    103: ["洗发水 750ml", "护发素 500ml", "发膜 200g", "头皮精华"],
    201: ["5G手机 12+256G", "手机壳 防摔", "快充充电器 67W", "蓝牙耳机"],
    202: ["笔记本 16寸", "无线鼠标", "机械键盘 87键", "显示器 27寸"],
    203: ["电饭煲 4L", "空气炸锅 5L", "破壁机", "扫地机器人"],
    301: ["坚果礼盒 1kg", "薯片 大包装", "肉脯 200g", "饼干 分享装"],
    302: ["智利车厘子 2斤", "赣南脐橙 5斤", "有机蔬菜礼盒", "海南芒果 3斤"],
    303: ["食用油 5L", "生抽酱油 1L", "五常大米 10斤", "鸡精 500g"],
}


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def create_ecommerce_demo_database(db_path: str | Path) -> Path:
    """
    创建电商 Demo 数据库。

    先执行 sql/create_ecommerce_demo.sql 建表，再用固定种子灌入数据，
    最后由事实表聚合出 dws 汇总层。
    """
    db_path = Path(db_path)

    if db_path.exists():
        db_path.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[1]
    sql_path = project_root / "sql" / "create_ecommerce_demo.sql"

    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql_path.read_text(encoding="utf-8"))

    rng = random.Random(RANDOM_SEED)

    _insert_dimensions(conn, rng)
    _insert_orders(conn, rng)
    _insert_behaviors(conn, rng)
    _build_summary_layer(conn)

    conn.commit()
    conn.close()

    return db_path


def _insert_dimensions(conn: sqlite3.Connection, rng: random.Random) -> None:
    """灌入类目、用户、店铺、商品四张维度表。"""
    conn.executemany(
        "INSERT INTO dim_category VALUES (?, ?, ?, ?)",
        CATEGORIES,
    )

    users = []
    for index in range(200):
        user_id = 10001 + index
        city, province = rng.choice(CITIES)
        register_day = START_DATE - timedelta(days=rng.randint(30, 900))

        users.append(
            (
                user_id,
                f"用户{user_id}",
                register_day.strftime("%Y-%m-%d"),
                city,
                province,
                rng.choice(["男", "女"]),
                rng.choice(AGE_GROUPS),
                rng.choices(MEMBER_LEVELS, weights=[50, 25, 17, 8])[0],
                rng.choice(REGISTER_CHANNELS),
            )
        )

    conn.executemany(
        "INSERT INTO dim_user VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        users,
    )

    shops = []
    for index in range(15):
        shop_id = 2001 + index
        main_category = LEAF_CATEGORY_IDS[index % len(LEAF_CATEGORY_IDS)]
        city, _ = rng.choice(CITIES)
        open_day = START_DATE - timedelta(days=rng.randint(200, 1800))

        shops.append(
            (
                shop_id,
                f"{rng.choice(SHOP_NAME_PARTS)}{['旗舰店', '专营店', '自营店'][index % 3]}{index + 1}",
                rng.choice(["旗舰店", "专营店", "自营店", "个人店"]),
                main_category,
                city,
                open_day.strftime("%Y-%m-%d"),
                rng.choices(["正常营业", "休假中", "已关店"], weights=[85, 10, 5])[0],
            )
        )

    conn.executemany(
        "INSERT INTO dim_shop VALUES (?, ?, ?, ?, ?, ?, ?)",
        shops,
    )

    products = []
    for index in range(60):
        product_id = 30001 + index
        shop = shops[index % 15]
        shop_id = shop[0]
        category_id = shop[3]
        brand = rng.choice(BRANDS[category_id])
        suffix = rng.choice(PRODUCT_SUFFIX[category_id])
        list_price = round(rng.uniform(19, 6999), 2)

        products.append(
            (
                product_id,
                f"{brand} {suffix}",
                category_id,
                shop_id,
                brand,
                list_price,
                round(list_price * rng.uniform(0.35, 0.7), 2),
                rng.choices(["在售", "已下架", "预售"], weights=[80, 15, 5])[0],
            )
        )

    conn.executemany(
        "INSERT INTO dim_product VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        products,
    )


def _insert_orders(conn: sqlite3.Connection, rng: random.Random) -> None:
    """灌入订单、订单明细、支付、退款四张事实表。"""
    user_ids = [row[0] for row in conn.execute("SELECT user_id FROM dim_user")]
    products_by_shop = {}

    for product_id, shop_id, list_price in conn.execute(
        "SELECT product_id, shop_id, list_price FROM dim_product"
    ):
        products_by_shop.setdefault(shop_id, []).append((product_id, list_price))

    shop_ids = sorted(products_by_shop)

    orders, items, payments, refunds = [], [], [], []
    item_id = payment_id = refund_id = 1

    for order_index in range(800):
        order_id = 50001 + order_index
        user_id = rng.choice(user_ids)
        shop_id = rng.choice(shop_ids)

        create_dt = datetime.combine(
            START_DATE + timedelta(days=rng.randrange(DAYS)),
            datetime.min.time(),
        ) + timedelta(hours=rng.randint(8, 23), minutes=rng.randint(0, 59))

        order_amount = 0.0
        order_discount = 0.0
        chosen = rng.sample(
            products_by_shop[shop_id],
            k=min(len(products_by_shop[shop_id]), rng.randint(1, 3)),
        )

        for product_id, list_price in chosen:
            quantity = rng.randint(1, 3)
            item_discount = round(list_price * quantity * rng.choice([0, 0, 0.05, 0.1, 0.2]), 2)
            item_amount = round(list_price * quantity - item_discount, 2)

            items.append(
                (item_id, order_id, product_id, quantity, list_price, item_discount, item_amount)
            )
            item_id += 1

            order_amount += round(list_price * quantity, 2)
            order_discount += item_discount

        order_amount = round(order_amount, 2)
        order_discount = round(order_discount, 2)
        freight = rng.choice([0.0, 0.0, 0.0, 8.0, 12.0])
        pay_amount = round(order_amount - order_discount + freight, 2)

        status = rng.choices(
            ["已完成", "已支付", "待支付", "已取消", "已退款"],
            weights=[55, 15, 10, 10, 10],
        )[0]

        pay_dt = finish_dt = None

        if status in {"已完成", "已支付", "已退款"}:
            pay_dt = create_dt + timedelta(minutes=rng.randint(1, 120))

        if status in {"已完成", "已退款"}:
            finish_dt = pay_dt + timedelta(days=rng.randint(1, 7))

        orders.append(
            (
                order_id,
                user_id,
                shop_id,
                order_amount,
                order_discount,
                freight,
                pay_amount,
                status,
                rng.choice(ORDER_CHANNELS),
                _fmt(create_dt),
                _fmt(pay_dt) if pay_dt else None,
                _fmt(finish_dt) if finish_dt else None,
            )
        )

        if pay_dt is not None:
            payments.append(
                (
                    payment_id,
                    order_id,
                    rng.choice(PAY_CHANNELS),
                    pay_amount,
                    "支付成功",
                    _fmt(pay_dt),
                )
            )
            payment_id += 1

        if status == "已退款":
            apply_dt = (finish_dt or pay_dt) + timedelta(days=rng.randint(0, 3))
            refund_done = rng.random() < 0.8

            refunds.append(
                (
                    refund_id,
                    order_id,
                    pay_amount if rng.random() < 0.7 else round(pay_amount * 0.5, 2),
                    rng.choice(REFUND_REASONS),
                    "退款成功" if refund_done else "退款中",
                    _fmt(apply_dt),
                    _fmt(apply_dt + timedelta(days=rng.randint(1, 5))) if refund_done else None,
                )
            )
            refund_id += 1

    conn.executemany(
        "INSERT INTO fact_order VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", orders
    )
    conn.executemany(
        "INSERT INTO fact_order_item VALUES (?, ?, ?, ?, ?, ?, ?)", items
    )
    conn.executemany("INSERT INTO fact_payment VALUES (?, ?, ?, ?, ?, ?)", payments)
    conn.executemany("INSERT INTO fact_refund VALUES (?, ?, ?, ?, ?, ?, ?)", refunds)


def _insert_behaviors(conn: sqlite3.Connection, rng: random.Random) -> None:
    """灌入用户行为表。"""
    user_ids = [row[0] for row in conn.execute("SELECT user_id FROM dim_user")]
    product_ids = [row[0] for row in conn.execute("SELECT product_id FROM dim_product")]

    behaviors = []

    for behavior_index in range(3000):
        behavior_dt = datetime.combine(
            START_DATE + timedelta(days=rng.randrange(DAYS)),
            datetime.min.time(),
        ) + timedelta(hours=rng.randint(7, 23), minutes=rng.randint(0, 59))

        behaviors.append(
            (
                behavior_index + 1,
                rng.choice(user_ids),
                rng.choice(product_ids),
                rng.choices(["浏览", "加购", "收藏"], weights=[70, 20, 10])[0],
                _fmt(behavior_dt),
                rng.randint(3, 600),
            )
        )

    conn.executemany(
        "INSERT INTO fact_user_behavior VALUES (?, ?, ?, ?, ?, ?)", behaviors
    )


def _build_summary_layer(conn: sqlite3.Connection) -> None:
    """
    由事实表聚合出 dws 汇总层。

    汇总表不另外随机生成，而是从明细算出来，
    这样"用汇总表查"和"用明细表算"两条路的口径是一致的。
    """
    conn.execute(
        """
        INSERT INTO dws_user_summary (
            user_id, total_order_count, total_pay_amount,
            avg_order_amount, refund_order_count, active_days, last_order_time
        )
        SELECT
            u.user_id,
            COUNT(o.order_id),
            ROUND(COALESCE(SUM(CASE WHEN o.pay_time IS NOT NULL
                                    THEN o.pay_amount ELSE 0 END), 0), 2),
            ROUND(COALESCE(AVG(o.pay_amount), 0), 2),
            COALESCE(SUM(CASE WHEN o.order_status = '已退款' THEN 1 ELSE 0 END), 0),
            COUNT(DISTINCT DATE(o.create_time)),
            MAX(o.create_time)
        FROM dim_user u
        LEFT JOIN fact_order o ON o.user_id = u.user_id
        GROUP BY u.user_id
        """
    )

    conn.execute(
        """
        INSERT INTO dws_shop_daily (
            stat_date, shop_id, gmv, pay_amount,
            order_count, buyer_count, refund_amount, conversion_rate
        )
        SELECT
            DATE(o.create_time),
            o.shop_id,
            ROUND(SUM(o.order_amount), 2),
            ROUND(SUM(CASE WHEN o.pay_time IS NOT NULL
                           THEN o.pay_amount ELSE 0 END), 2),
            COUNT(o.order_id),
            COUNT(DISTINCT o.user_id),
            ROUND(COALESCE((
                SELECT SUM(r.refund_amount)
                FROM fact_refund r
                JOIN fact_order ro ON ro.order_id = r.order_id
                WHERE ro.shop_id = o.shop_id
                  AND DATE(ro.create_time) = DATE(o.create_time)
            ), 0), 2),
            ROUND(
                CAST(COUNT(DISTINCT CASE WHEN o.pay_time IS NOT NULL
                                         THEN o.user_id END) AS REAL)
                / NULLIF(COUNT(DISTINCT o.user_id), 0),
                4
            )
        FROM fact_order o
        GROUP BY DATE(o.create_time), o.shop_id
        """
    )


def _dimension_business_meta() -> dict:
    """
    维度层（dim_*）业务元数据。

    这份元数据的质量直接决定 Schema 召回的准确率，是整个项目里
    最值得花时间打磨的部分。重点在三件事：

    1. aliases 覆盖业务口头表达：用户说"销售额"、"客单价"、"退款多少钱"，
       字段名却叫 gmv、avg_order_amount、refund_amount。
    2. 把近义字段的差别写进 description：order_amount 和 pay_amount
       都是"金额"，差在有没有扣优惠、加运费。
    3. 只给最容易混淆的字段手写 keyword_text / rerank_text，
       其余字段由 document_builder 自动生成默认索引文本。
    """
    return {
        # ---------------- 维度层 ----------------
        "dim_user": {
            "description": "用户维度表，记录用户的注册信息、所在城市、会员等级和注册渠道，是所有用户画像类分析的基础表。",
            "aliases": ["用户表", "用户维度表", "会员表", "客户表"],
            "columns": {
                "user_id": {
                    "description": "用户唯一标识。",
                    "aliases": ["用户ID", "客户ID", "会员ID"],
                    "semantic_role": "join_key",
                    "business_usage": "用于关联订单、行为、用户汇总等所有用户相关的表。",
                },
                "user_name": {
                    "description": "用户昵称。当用户问“哪个用户/是谁/用户是谁”时，通常需要输出这个字段而不是 user_id。",
                    "aliases": ["用户名", "昵称", "用户姓名", "用户", "谁"],
                    "semantic_role": "output_dimension",
                    "business_usage": "用户排行、用户明细类查询的展示字段。",
                    "keyword_text": "user_name 用户名 昵称 用户姓名 用户 是谁 哪个用户 哪位用户 用户排行 用户列表",
                    "rerank_text": "字段：dim_user.user_name。含义：用户昵称。用途：当用户问“是谁/哪个用户/哪位用户”时，应该输出用户昵称而不是 user_id。",
                },
                "register_time": {
                    "description": "用户注册日期。注意与订单的下单时间区分，这里描述的是用户何时成为会员。",
                    "aliases": ["注册时间", "注册日期", "入会时间"],
                    "semantic_role": "time",
                    "business_usage": "用于计算用户生命周期、划分新老客。",
                },
                "city": {
                    "description": "用户所在城市。",
                    "aliases": ["城市", "所在城市", "用户城市"],
                    "semantic_role": "dimension",
                    "business_usage": "按城市维度做地域分析时使用。注意店铺表也有 city 字段，指的是店铺所在地。",
                    "keyword_text": "city 城市 所在城市 用户城市 地域 北京 上海 广州 深圳 杭州 用户表",
                    "rerank_text": "字段：dim_user.city。含义：用户所在城市。别名：城市、用户城市。用途：按用户地域做分析。区别：dim_shop.city 指的是店铺所在城市，不是用户城市。",
                },
                "province": {
                    "description": "用户所在省份。",
                    "aliases": ["省份", "所在省份"],
                    "semantic_role": "dimension",
                },
                "gender": {
                    "description": "用户性别。",
                    "aliases": ["性别"],
                    "semantic_role": "dimension",
                },
                "age_group": {
                    "description": "用户年龄段分组。",
                    "aliases": ["年龄段", "年龄分组", "年龄区间"],
                    "semantic_role": "dimension",
                },
                "member_level": {
                    "description": "会员等级，取值为普通会员、银卡会员、金卡会员、钻石会员。",
                    "aliases": ["会员等级", "用户等级", "会员级别", "等级"],
                    "semantic_role": "dimension",
                    "business_usage": "用于会员分层运营，筛选高等级会员。",
                    "keyword_text": "member_level 会员等级 用户等级 会员级别 等级 普通会员 银卡会员 金卡会员 钻石会员 高等级会员 分层",
                },
                "register_channel": {
                    "description": "用户注册来源渠道，取值为 APP、小程序、H5、PC官网。",
                    "aliases": ["注册渠道", "来源渠道", "获客渠道"],
                    "semantic_role": "dimension",
                    "business_usage": "用于渠道拉新效果分析。注意与订单表的 channel（下单渠道）区分。",
                },
            },
        },
        "dim_category": {
            "description": "商品类目表，两级类目结构，一级类目为美妆护肤、数码电器、食品生鲜，下挂二级类目。",
            "aliases": ["类目表", "商品类目表", "品类表"],
            "columns": {
                "category_id": {
                    "description": "类目唯一标识。",
                    "aliases": ["类目ID", "品类ID"],
                    "semantic_role": "join_key",
                },
                "category_name": {
                    "description": "类目名称，例如美妆护肤、面部护肤、手机通讯。问“哪个类目”时输出这个字段而不是 category_id。",
                    "aliases": ["类目名称", "品类名称", "类目", "品类", "哪个类目"],
                    "semantic_role": "output_dimension",
                    "business_usage": "按类目做销售分析时的展示字段。",
                    "keyword_text": "category_name 类目名称 品类名称 类目 品类 美妆护肤 数码电器 食品生鲜 面部护肤 手机通讯",
                },
                "parent_category_id": {
                    "description": "父级类目ID，一级类目该字段为空。",
                    "aliases": ["父类目ID", "上级类目"],
                    "semantic_role": "join_key",
                },
                "category_level": {
                    "description": "类目层级，1 为一级类目，2 为二级类目。",
                    "aliases": ["类目层级", "类目级别"],
                    "semantic_role": "filter",
                },
            },
        },
        "dim_shop": {
            "description": "店铺维度表，记录店铺名称、店铺类型、主营类目、所在城市和营业状态。",
            "aliases": ["店铺表", "店铺维度表", "商家表"],
            "columns": {
                "shop_id": {
                    "description": "店铺唯一标识。",
                    "aliases": ["店铺ID", "商家ID"],
                    "semantic_role": "join_key",
                },
                "shop_name": {
                    "description": "店铺名称。当用户问“哪些店铺/哪个店铺/店铺排行”时，通常需要输出这个字段而不是 shop_id。",
                    "aliases": ["店铺名称", "店铺名", "商家名称", "店名", "店铺"],
                    "semantic_role": "output_dimension",
                    "business_usage": "店铺排行、店铺明细类查询的展示字段。",
                    "keyword_text": "shop_name 店铺名称 店铺名 商家名称 店名 店铺 哪些店铺 哪个店铺 店铺排行 top店铺 店铺列表",
                    "rerank_text": "字段：dim_shop.shop_name。含义：店铺名称。用途：当用户问“哪些店铺/哪个店铺销售额最高/店铺排行”时，应该输出店铺名称而不是 shop_id，因此需要关联 dim_shop 表取出本字段。",
                },
                "shop_type": {
                    "description": "店铺类型，取值为旗舰店、专营店、自营店、个人店。",
                    "aliases": ["店铺类型", "店铺性质"],
                    "semantic_role": "dimension",
                },
                "main_category_id": {
                    "description": "店铺主营类目ID。",
                    "aliases": ["主营类目", "主营品类"],
                    "semantic_role": "join_key",
                },
                "city": {
                    "description": "店铺所在城市。注意这是店铺的经营地，不是买家所在地。",
                    "aliases": ["店铺城市", "店铺所在城市"],
                    "semantic_role": "dimension",
                    "rerank_text": "字段：dim_shop.city。含义：店铺所在城市。区别：如果问的是买家/用户在哪个城市，应该用 dim_user.city，不是这个字段。",
                },
                "open_time": {
                    "description": "店铺开业日期。",
                    "aliases": ["开业时间", "开店时间"],
                    "semantic_role": "time",
                },
                "shop_status": {
                    "description": "店铺营业状态，取值为正常营业、休假中、已关店。",
                    "aliases": ["营业状态", "店铺状态"],
                    "semantic_role": "filter",
                    "business_usage": "统计在营店铺时用于过滤。",
                },
            },
        },
        "dim_product": {
            "description": "商品维度表，记录商品名称、所属类目、所属店铺、品牌、标价和成本价。",
            "aliases": ["商品表", "商品维度表", "货品表", "SKU表"],
            "columns": {
                "product_id": {
                    "description": "商品唯一标识。",
                    "aliases": ["商品ID", "货品ID", "SKU_ID"],
                    "semantic_role": "join_key",
                },
                "product_name": {
                    "description": "商品名称。当用户问“哪个商品/什么商品/商品叫什么”时，通常需要输出这个字段而不是 product_id。",
                    "aliases": ["商品名称", "商品名", "货品名称", "商品", "叫什么"],
                    "semantic_role": "output_dimension",
                    "business_usage": "商品排行、商品明细类查询的展示字段。",
                    "keyword_text": "product_name 商品名称 商品名 货品名称 商品 叫什么 哪个商品 哪些商品 商品排行 爆款",
                },
                "category_id": {
                    "description": "商品所属类目ID。",
                    "aliases": ["类目ID", "商品类目"],
                    "semantic_role": "join_key",
                    "business_usage": "按类目分析销售时的关联键。",
                },
                "shop_id": {
                    "description": "商品所属店铺ID。",
                    "aliases": ["店铺ID"],
                    "semantic_role": "join_key",
                },
                "brand": {
                    "description": "商品品牌。",
                    "aliases": ["品牌", "品牌名称"],
                    "semantic_role": "dimension",
                },
                "list_price": {
                    "description": "商品标价，即商品挂牌单价，未计算任何优惠。",
                    "aliases": ["标价", "商品单价", "挂牌价", "原价", "售价"],
                    "semantic_role": "metric",
                    "business_usage": "用于价格带分析。注意这是单价，不是订单总金额。",
                    "keyword_text": "list_price 标价 商品单价 挂牌价 原价 售价 单价 价格 平均标价 价格带 商品表",
                    "rerank_text": "字段：dim_product.list_price。含义：商品挂牌单价。区别：这是单个商品的价格，不是订单金额；订单层面的金额要用 fact_order.order_amount 或 pay_amount。",
                },
                "cost_price": {
                    "description": "商品成本价。",
                    "aliases": ["成本价", "进货价", "成本"],
                    "semantic_role": "metric",
                    "business_usage": "用于计算毛利。",
                },
                "shelf_status": {
                    "description": "商品上架状态，取值为在售、已下架、预售。",
                    "aliases": ["上架状态", "商品状态", "在售状态"],
                    "semantic_role": "filter",
                },
            },
        },
    }


def _fact_business_meta() -> dict:
    """
    事实层（fact_*）与汇总层（dws_*）业务元数据。

    这一层是近义字段最密集的地方，金额类字段就有 9 个，
    描述里必须写清楚彼此的差别，否则检索只能靠猜。
    """
    return {
        # ---------------- 事实层 ----------------
        "fact_order": {
            "description": "订单主表，一行一笔订单，记录订单的各项金额、订单状态、下单渠道和关键时间节点。是销售分析最核心的事实表。",
            "aliases": ["订单表", "订单主表", "交易订单表"],
            "columns": {
                "order_id": {
                    "description": "订单唯一标识，即订单号。",
                    "aliases": ["订单ID", "订单号", "订单编号"],
                    "semantic_role": "join_key",
                },
                "user_id": {
                    "description": "下单用户ID。",
                    "aliases": ["用户ID", "买家ID", "下单用户"],
                    "semantic_role": "join_key",
                },
                "shop_id": {
                    "description": "下单店铺ID。",
                    "aliases": ["店铺ID", "商家ID"],
                    "semantic_role": "join_key",
                },
                "order_amount": {
                    "description": "订单商品总金额，即订单内所有商品按标价计算的总和，未扣除优惠、未加运费。",
                    "aliases": ["订单金额", "订单总额", "商品总额", "订单原价", "成交金额"],
                    "semantic_role": "metric",
                    "value_range": ">= 0",
                    "business_usage": "衡量订单规模、计算 GMV 的口径字段。问“下单金额/订单金额/成交额”时用这个。",
                    "keyword_text": "order_amount 订单金额 订单总额 商品总额 订单原价 成交金额 下单金额 GMV 订单表",
                    "rerank_text": "字段：fact_order.order_amount。含义：订单商品总金额，按标价累加，未扣优惠、未含运费。别名：订单金额、订单总额、商品总额。区别：扣完优惠、加上运费之后用户真正付的钱是 pay_amount；问“实付/实际支付”要用 pay_amount，问“订单金额/成交额”用本字段。",
                },
                "discount_amount": {
                    "description": "订单优惠总金额，包含商品折扣和优惠券抵扣。",
                    "aliases": ["优惠金额", "折扣金额", "优惠总额", "减免金额"],
                    "semantic_role": "metric",
                    "business_usage": "用于促销力度分析、计算优惠占比。",
                    "keyword_text": "discount_amount 优惠金额 折扣金额 优惠总额 减免金额 促销 优惠券 打折",
                },
                "freight_amount": {
                    "description": "订单运费金额。",
                    "aliases": ["运费", "运费金额", "邮费", "配送费"],
                    "semantic_role": "metric",
                },
                "pay_amount": {
                    "description": "订单实付金额，计算口径为订单商品总金额减去优惠金额再加上运费，即用户实际需要支付的钱。",
                    "aliases": ["实付金额", "实际支付金额", "应付金额", "支付金额", "实收金额"],
                    "semantic_role": "metric",
                    "value_range": ">= 0",
                    "business_usage": "衡量实际收入。问“实付了多少钱/实际支付金额”时用这个字段。",
                    "keyword_text": "pay_amount 实付金额 实际支付金额 应付金额 支付金额 实收金额 订单表 实际收入",
                    "rerank_text": "字段：fact_order.pay_amount。含义：订单实付金额 = 订单商品总金额 - 优惠金额 + 运费。别名：实付金额、实际支付金额。区别：fact_payment.pay_amount 是支付流水的金额，用于分析支付渠道；如果只是想知道订单实付多少，用本字段即可，不需要关联支付表。",
                },
                "order_status": {
                    "description": "订单状态，取值为已完成、已支付、待支付、已取消、已退款。",
                    "aliases": ["订单状态", "状态", "交易状态"],
                    "semantic_role": "filter",
                    "business_usage": "统计有效订单时需要过滤掉已取消订单。",
                    "keyword_text": "order_status 订单状态 状态 交易状态 已完成 已支付 待支付 已取消 已退款 有效订单",
                },
                "channel": {
                    "description": "下单渠道，取值为 APP、小程序、PC官网、直播间。按渠道筛选订单时用这个字段。",
                    "aliases": ["下单渠道", "订单渠道", "交易渠道", "渠道", "直播间", "小程序"],
                    "semantic_role": "filter",
                    "keyword_text": "channel 下单渠道 订单渠道 交易渠道 渠道 APP 小程序 PC官网 直播间 直播 渠道分析",
                    "business_usage": "渠道销售分析。注意与用户表的 register_channel（注册渠道）区分。",
                    "rerank_text": "字段：fact_order.channel。含义：用户下单时使用的渠道。区别：dim_user.register_channel 是用户注册时的来源渠道，两者含义不同。",
                },
                "create_time": {
                    "description": "订单创建时间，即用户下单的时间。",
                    "aliases": ["下单时间", "创建时间", "订单时间", "交易时间"],
                    "semantic_role": "time",
                    "business_usage": "按日期统计订单量、销售额时的主要时间口径。",
                    "keyword_text": "create_time 下单时间 创建时间 订单时间 交易时间 日期 按天统计",
                    "rerank_text": "字段：fact_order.create_time。含义：用户下单时间。区别：pay_time 是支付时间，finish_time 是订单完成时间。日常说的“某天的订单/某天的销售额”一般以下单时间为准。",
                },
                "pay_time": {
                    "description": "订单支付时间。未支付的订单该字段为空，因此常被用来判断订单是否已支付。",
                    "aliases": ["支付时间", "付款时间"],
                    "semantic_role": "time",
                    "business_usage": "判断订单是否支付、计算下单到支付的转化时长。",
                },
                "finish_time": {
                    "description": "订单完成时间，即确认收货时间。",
                    "aliases": ["完成时间", "收货时间", "订单完成时间"],
                    "semantic_role": "time",
                },
            },
        },
        "fact_order_item": {
            "description": "订单明细表，一行一个商品，记录订单中每个商品的购买数量、单价和明细金额。需要按商品或类目分析时要用这张表。",
            "aliases": ["订单明细表", "订单商品表", "订单行表"],
            "columns": {
                "item_id": {
                    "description": "订单明细唯一标识。",
                    "aliases": ["明细ID", "订单行ID"],
                    "semantic_role": "join_key",
                },
                "order_id": {
                    "description": "所属订单ID。",
                    "aliases": ["订单ID", "订单号"],
                    "semantic_role": "join_key",
                },
                "product_id": {
                    "description": "购买的商品ID。",
                    "aliases": ["商品ID", "货品ID"],
                    "semantic_role": "join_key",
                    "business_usage": "按商品或类目分析销售时的关键关联键。",
                },
                "quantity": {
                    "description": "该商品的购买数量（件数）。业务上说的“销量”指的是这个字段求和，不是订单行数。",
                    "aliases": ["购买数量", "数量", "件数", "销量", "销售量", "卖了多少"],
                    "semantic_role": "metric",
                    "business_usage": "统计商品或品牌销量时对这个字段求和。",
                    "keyword_text": "quantity 购买数量 数量 件数 销量 销售量 卖了多少件 卖得最好 热销 畅销 订单明细表",
                    "rerank_text": "字段：fact_order_item.quantity。含义：商品购买件数。别名：销量、销售量。区别：问“销量最高”要对本字段求和（SUM），不是数订单行数（COUNT）——一笔订单可能买了 3 件。",
                },
                "item_price": {
                    "description": "下单时该商品的单价。",
                    "aliases": ["商品单价", "成交单价", "下单单价"],
                    "semantic_role": "metric",
                },
                "item_discount_amount": {
                    "description": "该商品行的优惠金额。",
                    "aliases": ["明细优惠金额", "单品优惠"],
                    "semantic_role": "metric",
                },
                "item_amount": {
                    "description": "该商品行的成交金额，计算口径为单价乘以数量再减去该行优惠。",
                    "aliases": ["明细金额", "单品成交金额", "商品成交额"],
                    "semantic_role": "metric",
                    "business_usage": "按商品或类目统计销售额时求和这个字段。",
                    "rerank_text": "字段：fact_order_item.item_amount。含义：单个商品行的成交金额。区别：fact_order.order_amount 是整笔订单的金额；要按商品/类目/品牌维度拆分销售额时才用本字段。",
                },
            },
        },
        "fact_payment": {
            "description": "支付流水表，记录每笔订单的支付渠道、支付金额和支付状态，用于支付渠道分析。",
            "aliases": ["支付表", "支付流水表", "付款记录表"],
            "columns": {
                "payment_id": {
                    "description": "支付流水唯一标识。",
                    "aliases": ["支付ID", "流水号", "支付流水号"],
                    "semantic_role": "join_key",
                },
                "order_id": {
                    "description": "对应订单ID。",
                    "aliases": ["订单ID", "订单号"],
                    "semantic_role": "join_key",
                },
                "pay_channel": {
                    "description": "支付渠道，取值为支付宝、微信支付、银行卡、花呗分期。",
                    "aliases": ["支付渠道", "支付方式", "付款方式"],
                    "semantic_role": "dimension",
                    "business_usage": "分析各支付方式的占比。",
                    "keyword_text": "pay_channel 支付渠道 支付方式 付款方式 支付宝 微信支付 银行卡 花呗分期",
                },
                "pay_amount": {
                    "description": "本笔支付流水的金额。",
                    "aliases": ["支付流水金额", "付款金额"],
                    "semantic_role": "metric",
                    "rerank_text": "字段：fact_payment.pay_amount。含义：一笔支付流水的金额。区别：这是支付表里的字段，只有在分析支付渠道、支付方式时才需要；如果只是问订单实付了多少，直接用 fact_order.pay_amount，不用关联支付表。",
                },
                "pay_status": {
                    "description": "支付状态。",
                    "aliases": ["支付状态", "付款状态"],
                    "semantic_role": "filter",
                },
                "pay_time": {
                    "description": "支付发生时间。",
                    "aliases": ["支付时间", "付款时间"],
                    "semantic_role": "time",
                },
            },
        },
        "fact_refund": {
            "description": "退款记录表，记录退款金额、退款原因和退款状态，用于售后分析。",
            "aliases": ["退款表", "退款记录表", "售后表"],
            "columns": {
                "refund_id": {
                    "description": "退款记录唯一标识。",
                    "aliases": ["退款ID", "退款单号"],
                    "semantic_role": "join_key",
                },
                "order_id": {
                    "description": "退款对应的订单ID。",
                    "aliases": ["订单ID", "订单号"],
                    "semantic_role": "join_key",
                },
                "refund_amount": {
                    "description": "退款金额，可能是全额退款，也可能是部分退款。",
                    "aliases": ["退款金额", "退款额", "退了多少钱", "售后金额"],
                    "semantic_role": "metric",
                    "business_usage": "统计退款损失、计算退款率。",
                    "keyword_text": "refund_amount 退款金额 退款额 售后金额 退钱 退款损失 退款表",
                    "rerank_text": "字段：fact_refund.refund_amount。含义：订单的退款金额，可能全额也可能部分。别名：退款金额、退款额。用途：问“退了多少钱/退款金额是多少”时输出这个字段。",
                },
                "refund_reason": {
                    "description": "退款原因，取值为七天无理由、商品质量问题、发错货、物流损坏、拍错了。",
                    "aliases": ["退款原因", "售后原因", "退货原因"],
                    "semantic_role": "dimension",
                    "business_usage": "分析退款原因分布，定位质量问题。",
                    "keyword_text": "refund_reason 退款原因 售后原因 退货原因 七天无理由 商品质量问题 发错货 物流损坏",
                },
                "refund_status": {
                    "description": "退款状态，取值为退款成功、退款中。",
                    "aliases": ["退款状态", "售后状态"],
                    "semantic_role": "filter",
                },
                "apply_time": {
                    "description": "退款申请时间。",
                    "aliases": ["退款申请时间", "申请时间"],
                    "semantic_role": "time",
                },
                "finish_time": {
                    "description": "退款完成时间，退款中的记录该字段为空。",
                    "aliases": ["退款完成时间", "退款到账时间"],
                    "semantic_role": "time",
                    "rerank_text": "字段：fact_refund.finish_time。含义：退款完成时间。区别：fact_order.finish_time 是订单确认收货时间，两者完全不同。",
                },
            },
        },
        "fact_user_behavior": {
            "description": "用户行为表，记录用户对商品的浏览、加购、收藏行为及停留时长，用于转化漏斗分析。",
            "aliases": ["行为表", "用户行为表", "埋点表"],
            "columns": {
                "behavior_id": {
                    "description": "行为记录唯一标识。",
                    "aliases": ["行为ID"],
                    "semantic_role": "join_key",
                },
                "user_id": {
                    "description": "产生行为的用户ID。",
                    "aliases": ["用户ID"],
                    "semantic_role": "join_key",
                },
                "product_id": {
                    "description": "被操作的商品ID。",
                    "aliases": ["商品ID"],
                    "semantic_role": "join_key",
                },
                "behavior_type": {
                    "description": "行为类型，取值为浏览、加购、收藏。",
                    "aliases": ["行为类型", "操作类型", "事件类型"],
                    "semantic_role": "filter",
                    "business_usage": "构建浏览到加购到下单的转化漏斗。",
                    "keyword_text": "behavior_type 行为类型 操作类型 事件类型 浏览 加购 收藏 加入购物车 加购次数 收藏次数 浏览次数 漏斗",
                },
                "behavior_time": {
                    "description": "行为发生时间。",
                    "aliases": ["行为时间", "操作时间", "浏览时间"],
                    "semantic_role": "time",
                },
                "stay_seconds": {
                    "description": "本次行为的页面停留秒数。",
                    "aliases": ["停留时长", "停留秒数", "浏览时长"],
                    "semantic_role": "metric",
                    "business_usage": "衡量商品详情页吸引力。",
                },
            },
        },
        # ---------------- 汇总层 ----------------
        "dws_user_summary": {
            "description": "用户汇总表，由订单事实表聚合而来，记录每个用户的累计下单笔数、累计实付金额、客单价和退款订单数。查用户级累计指标时优先用这张表，不用再去聚合订单明细。",
            "aliases": ["用户汇总表", "用户指标表", "用户画像汇总表"],
            "columns": {
                "user_id": {
                    "description": "用户唯一标识。",
                    "aliases": ["用户ID", "客户ID"],
                    "semantic_role": "join_key",
                },
                "total_order_count": {
                    "description": "该用户累计下单笔数，含所有状态的订单。",
                    "aliases": ["累计下单笔数", "订单数", "下单次数", "购买次数"],
                    "semantic_role": "metric_filter",
                    "value_range": "整数，>= 0",
                    "business_usage": "筛选高频购买用户。",
                    "keyword_text": "total_order_count 累计下单笔数 订单数 下单次数 购买次数 下单频次 高频用户 用户汇总表",
                },
                "total_pay_amount": {
                    "description": "该用户累计实付金额，即历史所有已支付订单的实付金额之和，可理解为用户消费总额。",
                    "aliases": ["累计实付金额", "消费总额", "累计消费金额", "总消费", "累计支付金额"],
                    "semantic_role": "metric_filter",
                    "value_range": ">= 0",
                    "business_usage": "识别高价值用户、做用户分层。问“用户一共花了多少钱”时用这个字段。",
                    "keyword_text": "total_pay_amount 累计实付金额 消费总额 累计消费金额 总消费 累计支付金额 高价值用户 用户分层 用户汇总表",
                    "rerank_text": "字段：dws_user_summary.total_pay_amount。含义：用户历史累计实付金额，即消费总额。别名：消费总额、累计消费金额。区别：fact_order.pay_amount 是单笔订单的实付金额；问“某用户一共消费了多少/累计实付超过多少的用户”要用本字段，不需要自己聚合订单表。",
                },
                "avg_order_amount": {
                    "description": "该用户的平均订单金额，也就是通常说的客单价。",
                    "aliases": ["客单价", "平均订单金额", "笔单价", "平均客单价"],
                    "semantic_role": "metric",
                    "business_usage": "衡量用户消费能力。“客单价”是业务口头表达，对应的就是这个字段。",
                    "keyword_text": "avg_order_amount 客单价 平均订单金额 笔单价 平均客单价 消费能力 用户汇总表",
                    "rerank_text": "字段：dws_user_summary.avg_order_amount。含义：用户平均每笔订单的金额，业务上叫客单价。别名：客单价、笔单价。用途：当用户问“客单价是多少”时，直接输出这个字段，不需要自己用总额除以订单数。",
                },
                "refund_order_count": {
                    "description": "该用户的退款订单笔数。",
                    "aliases": ["退款订单数", "退款笔数", "售后单数"],
                    "semantic_role": "metric",
                    "business_usage": "结合总订单数计算用户退款率，识别异常用户。",
                },
                "active_days": {
                    "description": "该用户有下单行为的天数。",
                    "aliases": ["活跃天数", "下单天数"],
                    "semantic_role": "metric",
                },
                "last_order_time": {
                    "description": "该用户最近一次下单时间。",
                    "aliases": ["最近下单时间", "最后下单时间", "最近购买时间"],
                    "semantic_role": "time",
                    "business_usage": "用于计算沉默天数、做流失预警。",
                },
            },
        },
        "dws_shop_daily": {
            "description": "店铺日汇总表，由订单事实表按天聚合而来，记录每个店铺每天的 GMV、实付金额、订单量、买家数、退款金额和支付转化率。做店铺经营日报时用这张表。",
            "aliases": ["店铺日汇总表", "店铺日报表", "店铺日指标表"],
            "columns": {
                "stat_date": {
                    "description": "统计日期，粒度为天。",
                    "aliases": ["统计日期", "日期", "数据日期"],
                    "semantic_role": "time",
                    "business_usage": "按天筛选或分组时使用。",
                    "keyword_text": "stat_date 统计日期 日期 数据日期 按天 每天 日报",
                },
                "shop_id": {
                    "description": "店铺ID。",
                    "aliases": ["店铺ID", "商家ID"],
                    "semantic_role": "join_key",
                },
                "gmv": {
                    "description": "店铺当日成交总额，口径为当天所有订单的商品总金额之和，业务上常说的销售额、成交额指的就是它。",
                    "aliases": ["GMV", "成交总额", "成交额", "销售额", "销售总额", "营业额"],
                    "semantic_role": "metric",
                    "value_range": ">= 0",
                    "business_usage": "店铺经营的核心指标。问“销售额/成交额/GMV 是多少”时用这个字段。",
                    "keyword_text": "gmv GMV 成交总额 成交额 销售额 销售总额 营业额 店铺日汇总表 核心指标 日报",
                    "rerank_text": "字段：dws_shop_daily.gmv。含义：店铺当日成交总额，等于当天订单的商品总金额之和。别名：GMV、成交额、销售额、营业额。区别：pay_amount 是当天实际支付到账的金额，会小于 GMV；问“销售额/成交额/GMV”用本字段。",
                },
                "pay_amount": {
                    "description": "店铺当日实付金额，只统计已支付订单，口径小于等于 GMV。",
                    "aliases": ["实付金额", "日实付金额", "支付金额"],
                    "semantic_role": "metric",
                    "rerank_text": "字段：dws_shop_daily.pay_amount。含义：店铺当天已支付订单的实付金额合计。区别：gmv 统计的是所有订单的商品总金额（含未支付），本字段只统计已支付部分。",
                },
                "order_count": {
                    "description": "店铺当日订单量。",
                    "aliases": ["订单量", "订单数", "成交笔数", "单量"],
                    "semantic_role": "metric",
                    "keyword_text": "order_count 订单量 订单数 成交笔数 单量 日订单量 店铺日汇总表",
                },
                "buyer_count": {
                    "description": "店铺当日下单买家数，同一用户当天多次下单只计一次。",
                    "aliases": ["买家数", "下单人数", "购买人数", "客户数"],
                    "semantic_role": "metric",
                    "business_usage": "衡量店铺的客流规模。",
                },
                "refund_amount": {
                    "description": "店铺当日退款金额合计。",
                    "aliases": ["退款金额", "日退款金额"],
                    "semantic_role": "metric",
                },
                "conversion_rate": {
                    "description": "店铺当日支付转化率，口径为已支付买家数除以下单买家数，取值为 0 到 1 之间的小数。",
                    "aliases": ["转化率", "支付转化率", "成交转化率"],
                    "semantic_role": "metric",
                    "value_range": "0-1",
                    "business_usage": "衡量下单到支付的流失情况。",
                    "keyword_text": "conversion_rate 转化率 支付转化率 成交转化率 下单支付转化 流失",
                },
            },
        },
    }


def get_ecommerce_business_meta() -> dict:
    """
    电商 Demo 完整业务元数据（维度层 + 事实层 + 汇总层）。

    这份元数据的质量直接决定 Schema 召回的准确率，是整个项目里
    最值得花时间打磨的部分。重点在三件事：

    1. aliases 覆盖业务口头表达：用户说“销售额”“客单价”“退了多少钱”，
       字段名却叫 gmv、avg_order_amount、refund_amount。
    2. 把近义字段的差别写进 description 和 rerank_text：
       order_amount 和 pay_amount 都是“金额”，差在有没有扣优惠、加运费。
    3. 只给最容易混淆的字段手写 keyword_text / rerank_text，
       其余字段由 document_builder 自动生成默认索引文本。
    """
    meta = {}
    meta.update(_dimension_business_meta())
    meta.update(_fact_business_meta())
    return meta


def get_ecommerce_relations_meta() -> List[dict]:
    """
    电商 Demo 表关系元数据。

    SQLite 里已经声明了外键，SQLiteSchemaLoader 会自动提取，
    这里额外补一层业务语义说明，便于写入 Milvus 的表关系 Collection。
    """
    database = "ecommerce_db"

    def relation(source_table, source_column, target_table, target_column, description):
        return {
            "database": database,
            "source_table": source_table,
            "source_column": source_column,
            "target_table": target_table,
            "target_column": target_column,
            "description": description,
        }

    return [
        relation("dim_shop", "main_category_id", "dim_category", "category_id",
                 "店铺主营类目关联类目表。"),
        relation("dim_product", "category_id", "dim_category", "category_id",
                 "商品所属类目关联类目表，按类目分析销售时必经此路径。"),
        relation("dim_product", "shop_id", "dim_shop", "shop_id",
                 "商品所属店铺关联店铺表。"),
        relation("fact_order", "user_id", "dim_user", "user_id",
                 "订单关联下单用户，用于按城市、会员等级等用户属性分析销售。"),
        relation("fact_order", "shop_id", "dim_shop", "shop_id",
                 "订单关联店铺，用于按店铺维度分析销售。"),
        relation("fact_order_item", "order_id", "fact_order", "order_id",
                 "订单明细关联订单主表。"),
        relation("fact_order_item", "product_id", "dim_product", "product_id",
                 "订单明细关联商品表，是按商品或类目拆分销售额的关键路径。"),
        relation("fact_payment", "order_id", "fact_order", "order_id",
                 "支付流水关联订单主表。"),
        relation("fact_refund", "order_id", "fact_order", "order_id",
                 "退款记录关联订单主表，用于把退款归因到用户、店铺或商品。"),
        relation("fact_user_behavior", "user_id", "dim_user", "user_id",
                 "用户行为关联用户表。"),
        relation("fact_user_behavior", "product_id", "dim_product", "product_id",
                 "用户行为关联商品表，用于做浏览到成交的转化分析。"),
        relation("dws_user_summary", "user_id", "dim_user", "user_id",
                 "用户汇总指标关联用户表，用于给累计指标补上城市、会员等级等属性。"),
        relation("dws_shop_daily", "shop_id", "dim_shop", "shop_id",
                 "店铺日汇总指标关联店铺表。"),
    ]
