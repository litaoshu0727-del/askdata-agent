"""留出评测集：由独立出题人在未见过被测系统表现的情况下编写。"""
from __future__ import annotations

from typing import List

from eval.cases import EvalCase

UNANSWERABLE_SQL = "SELECT 1 WHERE 0"

# 付过款的订单：已支付、已完成、已退款三种状态（pay_time 非空）。
PAID_STATUSES = "('已支付', '已完成', '已退款')"


HOLDOUT_ECOMMERCE_CASES: List[EvalCase] = [
    # ------------------------------------------------------------------
    # 简单：单表过滤 / 聚合
    # ------------------------------------------------------------------
    EvalCase(
        id="H01",
        query="直播间这个渠道一共下了多少笔订单？不管订单状态，全部算上，返回一个数。",
        reference_sql="""
SELECT COUNT(*)
FROM fact_order
WHERE channel = '直播间'
""",
        must_hit_columns=["fact_order.channel"],
        tags=["单表过滤", "计数"],
        note="下单渠道=直播间的全部订单数，不按状态过滤。",
    ),
    EvalCase(
        id="H02",
        query="已下架的商品里，标价最高的是哪一个？给出商品名称和标价。",
        reference_sql="""
SELECT product_name, list_price
FROM dim_product
WHERE shelf_status = '已下架'
ORDER BY list_price DESC
LIMIT 1
""",
        must_hit_columns=[
            "dim_product.shelf_status",
            "dim_product.list_price",
            "dim_product.product_name",
        ],
        tags=["单表过滤", "排序取TopN"],
        note="上架状态=已下架的商品中按标价取第一名；第1、2名标价不并列。",
    ),
    EvalCase(
        id="H03",
        query="钻石会员都是从哪些渠道注册进来的？按注册渠道分别给出钻石会员的人数，返回注册渠道和人数。",
        reference_sql="""
SELECT register_channel, COUNT(*)
FROM dim_user
WHERE member_level = '钻石会员'
GROUP BY register_channel
""",
        must_hit_columns=["dim_user.member_level", "dim_user.register_channel"],
        tags=["单表过滤", "分组统计", "字段混淆"],
        note="用户注册渠道（不是订单下单渠道），限定钻石会员。",
    ),
    EvalCase(
        id="H04",
        query="退款原因是商品质量问题、并且已经退款成功的那些退款，金额一共是多少？返回一个数。",
        reference_sql="""
SELECT ROUND(SUM(refund_amount), 2)
FROM fact_refund
WHERE refund_reason = '商品质量问题'
  AND refund_status = '退款成功'
""",
        must_hit_columns=[
            "fact_refund.refund_reason",
            "fact_refund.refund_status",
            "fact_refund.refund_amount",
        ],
        tags=["单表过滤", "聚合求和"],
        note="退款表按原因和状态双条件过滤后求退款金额；不含退款中的记录。",
    ),
    EvalCase(
        id="H05",
        query="按支付渠道统计支付流水：每个支付渠道各有多少笔、金额合计多少？返回支付渠道、笔数和金额合计。",
        reference_sql="""
SELECT pay_channel, COUNT(*), ROUND(SUM(pay_amount), 2)
FROM fact_payment
GROUP BY pay_channel
""",
        must_hit_columns=["fact_payment.pay_channel", "fact_payment.pay_amount"],
        tags=["单表", "分组统计"],
        note="支付流水表按支付渠道分组，计笔数和金额。",
    ),
    EvalCase(
        id="H06",
        query="2021年1月1日及以后开业、目前正常营业的店铺有哪些？给出店铺名称和开业日期。",
        reference_sql="""
SELECT shop_name, open_time
FROM dim_shop
WHERE open_time >= '2021-01-01'
  AND shop_status = '正常营业'
""",
        must_hit_columns=["dim_shop.open_time", "dim_shop.shop_status", "dim_shop.shop_name"],
        tags=["单表过滤", "时间过滤"],
        note="开业日期>=2021-01-01 且营业状态=正常营业；排除休假中和已关店。",
    ),
    EvalCase(
        id="H07",
        query=(
            "2024年5月1日到5月7日（含首尾两天），全平台的GMV一共是多少？"
            "GMV按订单商品总金额算，所有订单状态都算，按下单日期归属，返回一个数。"
        ),
        reference_sql="""
SELECT ROUND(SUM(gmv), 2)
FROM dws_shop_daily
WHERE stat_date BETWEEN '2024-05-01' AND '2024-05-07'
""",
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["时间过滤", "聚合求和", "候选路径"],
        note="店铺日汇总表 gmv 求和；等价路径为订单表 order_amount 按 DATE(create_time) 过滤求和，已验证一致。",
    ),
    EvalCase(
        id="H08",
        query="用户的浏览行为里，页面停留时间超过300秒（不含300秒）的有多少次？返回一个数。",
        reference_sql="""
SELECT COUNT(*)
FROM fact_user_behavior
WHERE behavior_type = '浏览'
  AND stay_seconds > 300
""",
        must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.stay_seconds"],
        tags=["单表过滤", "计数"],
        note="行为类型=浏览且停留秒数>300；库中有恰好300秒的记录，题面已排除。",
    ),
    EvalCase(
        id="H09",
        query="至少有过一笔退款订单的用户一共有多少位？返回一个数。",
        reference_sql="""
SELECT COUNT(*)
FROM dws_user_summary
WHERE refund_order_count > 0
""",
        must_hit_columns=[
            [
                "dws_user_summary.refund_order_count",
                "fact_order.order_status",
                "fact_refund.order_id",
            ],
        ],
        tags=["单表过滤", "去重计数", "候选路径"],
        note="用户汇总表退款订单数>0；等价于订单状态=已退款的去重用户数，或退款表关联订单后的去重用户数，三者已验证一致。",
    ),
    EvalCase(
        id="H10",
        query="会员积分余额最高的10位用户是谁？给出用户名和积分余额。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里只有会员等级，没有任何积分/积分余额字段，应判定为无法回答。",
        expect_unanswerable=True,
    ),
    # ------------------------------------------------------------------
    # 中等：两表关联 / 分组 / 时间窗口
    # ------------------------------------------------------------------
    EvalCase(
        id="H11",
        query="每个一级类目下面一共有多少个商品？同名的不同商品分别计数，给出一级类目名称和商品个数。",
        reference_sql="""
SELECT pc.category_name, COUNT(*)
FROM dim_product p
JOIN dim_category c  ON c.category_id = p.category_id
JOIN dim_category pc ON pc.category_id = c.parent_category_id
GROUP BY pc.category_id, pc.category_name
""",
        must_hit_columns=[
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["层级类目", "自关联", "分组统计"],
        note="商品挂在二级类目上，需经 parent_category_id 上卷到一级类目；按商品记录计数（库中有同名商品）。",
    ),
    EvalCase(
        id="H12",
        query=(
            "按店铺类型汇总，付过款的订单（订单状态为已支付、已完成、已退款的都算）实付金额合计分别是多少？"
            "给出店铺类型和实付金额合计。"
        ),
        reference_sql=f"""
SELECT s.shop_type, ROUND(SUM(o.pay_amount), 2)
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE o.order_status IN {PAID_STATUSES}
GROUP BY s.shop_type
""",
        must_hit_columns=[
            "dim_shop.shop_type",
            ["fact_order.pay_amount", "dws_shop_daily.pay_amount", "fact_payment.pay_amount"],
        ],
        tags=["跨表关联", "分组统计", "候选路径"],
        note="付过款订单的实付金额按店铺类型汇总；订单表、店铺日汇总表 pay_amount、支付流水表三条路径已验证一致。",
    ),
    EvalCase(
        id="H13",
        query=(
            "2024年5月20日到5月26日，全平台每天各下了多少笔订单？"
            "按下单日期统计，所有订单状态都算，给出日期（YYYY-MM-DD）和订单数。"
        ),
        reference_sql="""
SELECT stat_date, SUM(order_count)
FROM dws_shop_daily
WHERE stat_date BETWEEN '2024-05-20' AND '2024-05-26'
GROUP BY stat_date
""",
        must_hit_columns=[
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
            ["dws_shop_daily.order_count", "fact_order.order_id"],
        ],
        tags=["时间过滤", "分组统计", "候选路径"],
        note="按天汇总全平台订单量；等价路径为订单表按 DATE(create_time) 分组计数，已验证一致。",
    ),
    EvalCase(
        id="H14",
        query="金卡会员在直播间下的订单里，已完成的有多少笔？返回一个数。",
        reference_sql="""
SELECT COUNT(*)
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE u.member_level = '金卡会员'
  AND o.channel = '直播间'
  AND o.order_status = '已完成'
""",
        must_hit_columns=["dim_user.member_level", "fact_order.channel", "fact_order.order_status"],
        tags=["跨表关联", "多条件过滤"],
        note="用户会员等级 + 订单下单渠道 + 订单状态三条件。",
    ),
    EvalCase(
        id="H15",
        query="用花呗分期付款的订单，按下单渠道分别有多少笔？给出下单渠道和订单数。",
        reference_sql="""
SELECT o.channel, COUNT(*)
FROM fact_payment p
JOIN fact_order o ON o.order_id = p.order_id
WHERE p.pay_channel = '花呗分期'
GROUP BY o.channel
""",
        must_hit_columns=["fact_payment.pay_channel", "fact_order.channel"],
        tags=["跨表关联", "分组统计", "字段混淆"],
        note="支付渠道在支付流水表，下单渠道在订单表，需关联；每笔订单只有一条支付流水。",
    ),
    EvalCase(
        id="H16",
        query=(
            "2024年5月1日到5月10日（含首尾两天）下单的那些订单，后来一共产生了多少退款金额？"
            "按订单的下单日期圈定订单，不论退款状态都算上，返回一个数。"
        ),
        reference_sql="""
SELECT ROUND(SUM(refund_amount), 2)
FROM dws_shop_daily
WHERE stat_date BETWEEN '2024-05-01' AND '2024-05-10'
""",
        must_hit_columns=[
            ["dws_shop_daily.refund_amount", "fact_refund.refund_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["时间过滤", "口径辨析", "候选路径"],
        note=(
            "退款按订单下单日期归属，而非退款申请日期；等价路径为退款表关联订单表按 DATE(create_time) 过滤，已验证一致。"
            "若误按 apply_time 过滤结果不同。"
        ),
    ),
    EvalCase(
        id="H17",
        query="华为品牌的商品，在已完成的订单里一共卖出了多少件？返回一个数。",
        reference_sql="""
SELECT SUM(i.quantity)
FROM fact_order_item i
JOIN dim_product p ON p.product_id = i.product_id
JOIN fact_order o  ON o.order_id = i.order_id
WHERE p.brand = '华为'
  AND o.order_status = '已完成'
""",
        must_hit_columns=["dim_product.brand", "fact_order_item.quantity", "fact_order.order_status"],
        tags=["多表关联", "销量"],
        note="销量=购买件数求和（不是明细行数），只算已完成订单。",
    ),
    EvalCase(
        id="H18",
        query=(
            "所在省份为浙江的用户，累计实付金额加起来是多少？"
            "只算付过款的订单（已支付、已完成、已退款都算），返回一个数。"
        ),
        reference_sql="""
SELECT ROUND(SUM(s.total_pay_amount), 2)
FROM dws_user_summary s
JOIN dim_user u ON u.user_id = s.user_id
WHERE u.province = '浙江'
""",
        must_hit_columns=[
            "dim_user.province",
            [
                "dws_user_summary.total_pay_amount",
                "fact_order.pay_amount",
                "fact_payment.pay_amount",
            ],
        ],
        tags=["跨表关联", "聚合求和", "候选路径"],
        note="用户汇总表累计实付金额（只含付过款订单）；等价于订单表付过款订单的实付金额或支付流水金额，已验证一致。",
    ),
    EvalCase(
        id="H19",
        query=(
            "注册渠道是小程序的用户中，有多少人在2024年5月15日到5月21日（含首尾两天）期间下过单？"
            "任何订单状态都算，按人去重，返回一个数。"
        ),
        reference_sql="""
SELECT COUNT(DISTINCT o.user_id)
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE u.register_channel = '小程序'
  AND DATE(o.create_time) BETWEEN '2024-05-15' AND '2024-05-21'
""",
        must_hit_columns=["dim_user.register_channel", "fact_order.create_time", "fact_order.user_id"],
        tags=["跨表关联", "时间过滤", "去重计数", "字段混淆"],
        note="注册渠道（用户表）而非下单渠道；create_time 带时分秒，需用 DATE() 保证 5月21日当天被算入。",
    ),
    EvalCase(
        id="H20",
        query="2024年5月，满减券和折扣券分别被核销了多少张？",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里只有订单/明细层面的优惠金额合计，没有优惠券维度（券类型、券张数、核销记录），应判定为无法回答。",
        expect_unanswerable=True,
    ),
    # ------------------------------------------------------------------
    # 难：多跳关联 / 比率 / 嵌套聚合 / TopN / 区间对比 / 去重
    # ------------------------------------------------------------------
    EvalCase(
        id="H21",
        query=(
            "只看已完成的订单，各一级类目的商品成交金额分别是多少？"
            "成交金额按订单明细里每个商品行的成交金额加总，给出一级类目名称和成交金额。"
        ),
        reference_sql="""
SELECT pc.category_name, ROUND(SUM(i.item_amount), 2)
FROM fact_order_item i
JOIN fact_order o    ON o.order_id = i.order_id
JOIN dim_product p   ON p.product_id = i.product_id
JOIN dim_category c  ON c.category_id = p.category_id
JOIN dim_category pc ON pc.category_id = c.parent_category_id
WHERE o.order_status = '已完成'
GROUP BY pc.category_id, pc.category_name
""",
        must_hit_columns=[
            "fact_order_item.item_amount",
            "fact_order.order_status",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["多跳JOIN", "层级类目", "分组统计"],
        note="明细→订单（过滤状态）→商品→二级类目→一级类目，五表关联，按一级类目汇总 item_amount。",
    ),
    EvalCase(
        id="H22",
        query=(
            "只看已完成的订单，按商品计算毛利（商品行成交金额 减去 成本价×购买件数），"
            "毛利最高的前3个商品是哪些？给出商品ID、商品名称和毛利。"
        ),
        reference_sql="""
SELECT p.product_id, p.product_name,
       ROUND(SUM(i.item_amount - p.cost_price * i.quantity), 2) AS gross_profit
FROM fact_order_item i
JOIN fact_order o  ON o.order_id = i.order_id
JOIN dim_product p ON p.product_id = i.product_id
WHERE o.order_status = '已完成'
GROUP BY p.product_id, p.product_name
ORDER BY gross_profit DESC
LIMIT 3
""",
        must_hit_columns=[
            "fact_order_item.item_amount",
            "fact_order_item.quantity",
            "dim_product.cost_price",
            ["dim_product.product_id", "fact_order_item.product_id"],
            "dim_product.product_name",
            "fact_order.order_status",
        ],
        tags=["多表关联", "派生指标", "排序取TopN"],
        note="按商品ID分组（库中有同名商品，所以要求返回ID）；第3、4名毛利不并列。",
    ),
    EvalCase(
        id="H23",
        query=(
            "各店铺的退款率 = 订单状态为已退款的订单数 ÷ 付过款的订单数（已支付、已完成、已退款三种状态的订单数之和）。"
            "退款率最高的3家店铺是哪些？给出店铺名称和退款率（用小数表示，保留两位）。"
        ),
        reference_sql=f"""
SELECT s.shop_name,
       ROUND(1.0 * SUM(o.order_status = '已退款')
             / SUM(o.order_status IN {PAID_STATUSES}), 2) AS refund_rate
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
GROUP BY s.shop_id, s.shop_name
ORDER BY 1.0 * SUM(o.order_status = '已退款') / SUM(o.order_status IN {PAID_STATUSES}) DESC
LIMIT 3
""",
        must_hit_columns=[
            "dim_shop.shop_name",
            ["fact_order.order_status", "fact_refund.order_id"],
        ],
        tags=["比率计算", "排序取TopN", "跨表关联"],
        note="分子分母口径写死在题面里；第3名(0.1556)与第4名(0.1538)原值与两位小数均不并列。",
    ),
    EvalCase(
        id="H24",
        query=(
            "钻石会员里，哪些人的累计实付金额高于钻石会员的平均累计实付金额？"
            "（累计实付金额只算付过款的订单；平均值只在钻石会员内部计算）给出用户名和累计实付金额。"
        ),
        reference_sql="""
SELECT u.user_name, s.total_pay_amount
FROM dws_user_summary s
JOIN dim_user u ON u.user_id = s.user_id
WHERE u.member_level = '钻石会员'
  AND s.total_pay_amount > (
        SELECT AVG(s2.total_pay_amount)
        FROM dws_user_summary s2
        JOIN dim_user u2 ON u2.user_id = s2.user_id
        WHERE u2.member_level = '钻石会员'
  )
""",
        must_hit_columns=[
            "dim_user.member_level",
            "dim_user.user_name",
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["嵌套聚合", "高于平均", "跨表关联", "候选路径"],
        note="组内平均（18位钻石会员，均有下单记录）后筛选高于均值者；用订单表付过款订单自行汇总结果一致。",
    ),
    EvalCase(
        id="H25",
        query=(
            "按下单时间把2024年5月分成两段：5月1日至5月15日、5月16日至5月30日（都含首尾两天）。"
            "各下单渠道在这两段里各有多少笔已完成订单？给出下单渠道、前一段订单数、后一段订单数。"
        ),
        reference_sql="""
SELECT channel,
       SUM(DATE(create_time) BETWEEN '2024-05-01' AND '2024-05-15') AS first_half,
       SUM(DATE(create_time) BETWEEN '2024-05-16' AND '2024-05-30') AS second_half
FROM fact_order
WHERE order_status = '已完成'
GROUP BY channel
""",
        must_hit_columns=["fact_order.channel", "fact_order.create_time", "fact_order.order_status"],
        tags=["区间对比", "条件聚合", "时间过滤"],
        note="同一行给出两个时间段的计数；按下单时间切分，只算订单状态=已完成。",
    ),
    EvalCase(
        id="H26",
        query=(
            "按二级类目看加购转化：浏览过该类目商品的用户里，有多大比例也加购过该类目的商品（不考虑先后顺序）？"
            "比例 = 既浏览过又加购过该类目商品的去重用户数 ÷ 浏览过该类目商品的去重用户数。"
            "给出二级类目名称和比例（用小数表示，保留两位）。"
        ),
        reference_sql="""
WITH v AS (
    SELECT DISTINCT b.user_id, p.category_id
    FROM fact_user_behavior b
    JOIN dim_product p ON p.product_id = b.product_id
    WHERE b.behavior_type = '浏览'
),
a AS (
    SELECT DISTINCT b.user_id, p.category_id
    FROM fact_user_behavior b
    JOIN dim_product p ON p.product_id = b.product_id
    WHERE b.behavior_type = '加购'
)
SELECT c.category_name, ROUND(1.0 * COUNT(a.user_id) / COUNT(*), 2)
FROM v
JOIN dim_category c ON c.category_id = v.category_id
LEFT JOIN a ON a.user_id = v.user_id AND a.category_id = v.category_id
GROUP BY c.category_id, c.category_name
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.user_id",
            "dim_product.category_id",
            "dim_category.category_name",
        ],
        tags=["比率计算", "去重计数", "漏斗", "多表关联"],
        note="类目内用户级交集转化率：分子是浏览∩加购的去重用户，分母是浏览去重用户；加购的商品不必是同一件。",
    ),
    EvalCase(
        id="H27",
        query="有多少位用户在付款时用过两种及以上不同的支付渠道？返回一个数。",
        reference_sql="""
SELECT COUNT(*)
FROM (
    SELECT o.user_id
    FROM fact_payment p
    JOIN fact_order o ON o.order_id = p.order_id
    GROUP BY o.user_id
    HAVING COUNT(DISTINCT p.pay_channel) >= 2
) t
""",
        must_hit_columns=["fact_payment.pay_channel", "fact_order.user_id"],
        tags=["去重计数", "HAVING", "跨表关联"],
        note="支付流水无 user_id，需经订单表拿到用户；按用户数去重后的支付渠道数>=2。",
    ),
    EvalCase(
        id="H28",
        query=(
            "付过款的订单（已支付、已完成、已退款）中，买家所在城市和下单店铺所在城市是同一个城市的订单有多少笔？"
            "返回一个数。"
        ),
        reference_sql=f"""
SELECT COUNT(*)
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE o.order_status IN {PAID_STATUSES}
  AND u.city = s.city
""",
        must_hit_columns=[
            "dim_user.city",
            "dim_shop.city",
            ["fact_order.order_status", "fact_order.pay_time", "fact_payment.order_id"],
        ],
        tags=["多表关联", "字段混淆", "跨表比较"],
        note="用户城市与店铺城市两个同名字段做相等比较；付过款可用状态、pay_time 非空或存在支付流水判断，三者一致。",
    ),
    EvalCase(
        id="H29",
        query=(
            "有多少个“用户-商品”组合，是用户收藏过这个商品、但这个用户的所有订单（不论订单状态）里都没有买过这个商品的？"
            "返回一个数。"
        ),
        reference_sql="""
SELECT COUNT(*)
FROM (
    SELECT DISTINCT b.user_id, b.product_id
    FROM fact_user_behavior b
    WHERE b.behavior_type = '收藏'
      AND NOT EXISTS (
            SELECT 1
            FROM fact_order_item i
            JOIN fact_order o ON o.order_id = i.order_id
            WHERE o.user_id = b.user_id
              AND i.product_id = b.product_id
      )
) t
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.user_id",
            "fact_user_behavior.product_id",
            "fact_order_item.product_id",
            "fact_order.user_id",
        ],
        tags=["反连接", "去重计数", "多表关联"],
        note="(用户,商品) 对去重后做 NOT EXISTS；购买判定需经订单表拿 user_id 再匹配明细里的商品。",
    ),
    EvalCase(
        id="H30",
        query="用户评价里好评率最高的3个商品是哪些？给出商品名称和好评率。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里没有评价/评分数据；收藏、退款原因“商品质量问题”都不等价于好评率，应判定为无法回答。",
        expect_unanswerable=True,
    ),
]


HOLDOUT_CHINOOK_CASES: List[EvalCase] = [
    # ------------------------------------------------------------------
    # 简单
    # ------------------------------------------------------------------
    EvalCase(
        id="HC01",
        query="曲库里时长超过10分钟的曲目有多少首？返回一个数。",
        reference_sql="""
SELECT COUNT(*)
FROM Track
WHERE Milliseconds > 600000
""",
        must_hit_columns=["Track.Milliseconds"],
        tags=["单表过滤", "单位换算"],
        note="10分钟=600000毫秒；库中没有恰好600000毫秒的曲目，所以含不含边界答案相同。",
    ),
    EvalCase(
        id="HC02",
        query="我们的客户分布在多少个不同的国家？返回一个数。",
        reference_sql="""
SELECT COUNT(DISTINCT Country)
FROM Customer
""",
        must_hit_columns=[["Customer.Country", "Invoice.BillingCountry"]],
        tags=["单表", "去重计数", "候选路径"],
        note="客户表国家去重；所有客户都有发票且开票国家与客户国家一致，开票国家去重结果相同。",
    ),
    EvalCase(
        id="HC03",
        query="2023年全年（2023年1月1日至12月31日）的开票总金额是多少？返回一个数。",
        reference_sql="""
SELECT ROUND(SUM(Total), 2)
FROM Invoice
WHERE InvoiceDate >= '2023-01-01' AND InvoiceDate < '2024-01-01'
""",
        must_hit_columns=["Invoice.InvoiceDate", ["Invoice.Total", "InvoiceLine.UnitPrice"]],
        tags=["单表", "时间过滤", "聚合求和"],
        note="按开票日期过滤后对发票总额求和；用明细行单价×数量求和结果相同。",
    ),
    EvalCase(
        id="HC04",
        query="2003年入职的员工有哪些？名和姓分两列返回。",
        reference_sql="""
SELECT FirstName, LastName
FROM Employee
WHERE HireDate >= '2003-01-01' AND HireDate < '2004-01-01'
""",
        must_hit_columns=["Employee.HireDate", "Employee.FirstName", "Employee.LastName"],
        tags=["单表过滤", "时间过滤"],
        note="员工入职日期落在2003年。",
    ),
    EvalCase(
        id="HC05",
        query="2000年及以后发行的专辑一共有多少张？",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="专辑表只有名称和艺术家，没有发行日期；开票日期、入职日期都不是发行时间，应判定为无法回答。",
        expect_unanswerable=True,
    ),
    # ------------------------------------------------------------------
    # 中等
    # ------------------------------------------------------------------
    EvalCase(
        id="HC06",
        query="专辑数量最多的3位艺术家是谁？给出艺术家名称和专辑数。",
        reference_sql="""
SELECT ar.Name, COUNT(*) AS album_cnt
FROM Album al
JOIN Artist ar ON ar.ArtistId = al.ArtistId
GROUP BY ar.ArtistId, ar.Name
ORDER BY album_cnt DESC
LIMIT 3
""",
        must_hit_columns=["Artist.Name", "Album.ArtistId"],
        tags=["跨表关联", "分组统计", "排序取TopN"],
        note="第3名(11)与第4名(10)不并列。",
    ),
    EvalCase(
        id="HC07",
        query="每位销售支持员工各负责多少位客户？给出员工的名、姓（分两列）和负责的客户数。",
        reference_sql="""
SELECT e.FirstName, e.LastName, COUNT(*)
FROM Customer c
JOIN Employee e ON e.EmployeeId = c.SupportRepId
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=["Customer.SupportRepId", "Employee.FirstName", "Employee.LastName"],
        tags=["跨表关联", "分组统计", "字段混淆"],
        note="客户与员工只经 SupportRepId 关联；名字要取员工表而非客户表。",
    ),
    EvalCase(
        id="HC08",
        query="2024年开票金额最高的4个国家是哪些？给出国家和该国2024年的开票金额。",
        reference_sql="""
SELECT BillingCountry, ROUND(SUM(Total), 2) AS amt
FROM Invoice
WHERE InvoiceDate >= '2024-01-01' AND InvoiceDate < '2025-01-01'
GROUP BY BillingCountry
ORDER BY amt DESC
LIMIT 4
""",
        must_hit_columns=[
            "Invoice.InvoiceDate",
            "Invoice.Total",
            ["Invoice.BillingCountry", "Customer.Country"],
        ],
        tags=["时间过滤", "分组统计", "排序取TopN", "候选路径"],
        note="第4名(36.66)与第5名(24.77)不并列；开票国家与客户国家在本库完全一致，两条路径结果相同。",
    ),
    EvalCase(
        id="HC09",
        query="直接向 Michael Mitchell 汇报的员工有哪些？名和姓分两列返回。",
        reference_sql="""
SELECT e.FirstName, e.LastName
FROM Employee e
JOIN Employee m ON m.EmployeeId = e.ReportsTo
WHERE m.FirstName = 'Michael' AND m.LastName = 'Mitchell'
""",
        must_hit_columns=["Employee.ReportsTo", "Employee.FirstName", "Employee.LastName"],
        tags=["自关联", "层级关系"],
        note="员工表按 ReportsTo 自关联，只取直接下属。",
    ),
    # ------------------------------------------------------------------
    # 难
    # ------------------------------------------------------------------
    EvalCase(
        id="HC10",
        query="每位销售支持员工负责的客户，一共带来了多少开票金额？给出员工的名、姓（分两列）和开票金额合计。",
        reference_sql="""
SELECT e.FirstName, e.LastName, ROUND(SUM(i.Total), 2)
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
JOIN Invoice i  ON i.CustomerId = c.CustomerId
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "Customer.SupportRepId",
            "Invoice.Total",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["多跳JOIN", "分组统计"],
        note="员工→客户→发票三表关联后按员工汇总发票总额。",
    ),
    EvalCase(
        id="HC11",
        query="按实际成交金额算，卖得最好的3个音乐流派是哪些？给出流派名称和成交金额。",
        reference_sql="""
SELECT g.Name, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS revenue
FROM InvoiceLine il
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
GROUP BY g.GenreId, g.Name
ORDER BY revenue DESC
LIMIT 3
""",
        must_hit_columns=["Genre.Name", ["InvoiceLine.UnitPrice", "Track.UnitPrice"]],
        tags=["多跳JOIN", "排序取TopN"],
        note="明细→曲目→流派；本库成交价与目录价逐行相同，数量均为1，两种价格口径结果一致。第3名(261.36)与第4名(241.56)不并列。",
    ),
    EvalCase(
        id="HC12",
        query="Grunge 这个歌单里收录的曲目，出自哪些艺术家？给出艺术家名称，去重。",
        reference_sql="""
SELECT DISTINCT ar.Name
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t          ON t.TrackId = pt.TrackId
JOIN Album al         ON al.AlbumId = t.AlbumId
JOIN Artist ar        ON ar.ArtistId = al.ArtistId
WHERE p.Name = 'Grunge'
""",
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Artist.Name"],
        tags=["多跳JOIN", "去重"],
        note="歌单→收录关系→曲目→专辑→艺术家五表链路；艺术家经专辑取得，不是作曲者。",
    ),
    EvalCase(
        id="HC13",
        query="从来没有被卖出过的曲目，按媒体文件格式分别有多少首？给出媒体格式名称和曲目数。",
        reference_sql="""
SELECT m.Name, COUNT(*)
FROM Track t
JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
WHERE NOT EXISTS (
    SELECT 1 FROM InvoiceLine il WHERE il.TrackId = t.TrackId
)
GROUP BY m.MediaTypeId, m.Name
""",
        must_hit_columns=["MediaType.Name", "InvoiceLine.TrackId"],
        tags=["反连接", "分组统计"],
        note="用发票明细判断是否卖出过（不是歌单收录）；五种格式都有未售出曲目。",
    ),
    EvalCase(
        id="HC14",
        query=(
            "消费总额高于全体客户人均消费额的客户有多少位？"
            "人均消费额 = 全部发票金额合计 ÷ 全部客户人数，返回一个数。"
        ),
        reference_sql="""
SELECT COUNT(*)
FROM (
    SELECT CustomerId, SUM(Total) AS spend
    FROM Invoice
    GROUP BY CustomerId
) t
WHERE spend > (SELECT SUM(Total) FROM Invoice) * 1.0 / (SELECT COUNT(*) FROM Customer)
""",
        must_hit_columns=["Invoice.CustomerId", "Invoice.Total"],
        tags=["嵌套聚合", "高于平均"],
        note="先按客户汇总消费额，再与全体人均（59位客户均有发票）比较后计数。",
    ),
    EvalCase(
        id="HC15",
        query="按艺术家的国籍统计，各国艺术家的曲目一共卖了多少钱？给出国籍和销售额。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="艺术家表只有名称，没有国籍/国家；客户国家和开票国家描述的是买家，不能替代，应判定为无法回答。",
        expect_unanswerable=True,
    ),
]
