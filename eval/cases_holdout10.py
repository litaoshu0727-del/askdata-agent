"""
第十套留出评测集：三个库（ecommerce、Chinook、Sakila），验证四项结果检查在陌生题上的效果。
由独立出题人在未见过被测系统表现和已有题目的情况下编写。ecommerce 30 题（H10E01–H10E30，陷阱 3），
Chinook 20 题（H10C01–H10C20，陷阱 3），Sakila 20 题（H10S01–H10S20，陷阱 2）。

**已用过一次。**这套题于 04041c2 冻结并推送后第一次运行，两个版本同时跑，都用冻结时的评测器判分，每题 3 次，
结果见 docs/实验记录.md「第十套留出集：四项结果检查在陌生题上」：

    版本                    ecommerce        Chinook          Sakila           合计
    2f7d63d  只有形状       29/30（88/90）   20/20（58/60）   19/20（54/60）   200/210
    04041c2  四项检查       29/30（85/90）   20/20（57/60）   19/20（57/60）   199/210

逐题变好 4、变差 5，分不出差别。三项新检查触发 5 次，原 SQL 都是错的，改对 4 次，没有误报、没有改坏。
没有发现可证明没法判分的题，冻结版就是最终版。

当时的运行方案：

    2f7d63d    第九套封存时：结果检查只有形状一项
    冻结时 HEAD 再加分组粒度、窗口的上一期、每组前 N 三项结果检查（32a2123、ef21acd）

这三项检查的证据都来自用过的题，而且大多是已知会出这类错的题。这一套看它们在陌生题上触发多少次、改对多少次，
有没有改坏。出题规范同第八、九套（eval/blind_materials/出题规范_第十套.md），三个库合在一起，没有引导出题人写
检查针对的那几类题。材料（三份数据字典、三个库）逐字沿用 eval/blind_materials/ 和 runtime_data/；不读 README、
docs/、eval/ 已有题目和 git 历史，不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本（eval/blind_materials/check_holdout.py）完成，只输出题号和检查项；
出题人的回报里也不含题目内容。组装进仓库时只换了导入、加了这段文件头。

候选路径的验证 SQL 在 eval/cases_holdout10_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

第十套盲写评测题（holdout10）：ecommerce 30 题、chinook 20 题、sakila 20 题。"""

from eval.cases import EvalCase


# ---------------------------------------------------------------------------
# ecommerce（30 题，其中陷阱题 3 道）
# ---------------------------------------------------------------------------

HOLDOUT10_ECOMMERCE_CASES = [
    EvalCase(
        id="H10E01",
        query="按一级类目看，买家和店铺在同一个城市的订单，实付金额占这个类目全部实付金额的百分之几？保留两位小数。",
        reference_sql="""
SELECT c1.category_name,
       ROUND(100.0 * SUM(CASE WHEN u.city = s.city THEN o.pay_amount ELSE 0 END) / SUM(o.pay_amount), 2)
           AS same_city_pct
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN dim_category c2 ON c2.category_id = s.main_category_id
JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
WHERE o.pay_time IS NOT NULL
GROUP BY c1.category_id, c1.category_name
""",
        must_hit_columns=[
            "dim_user.city",
            "dim_shop.city",
            "fact_order.pay_amount",
            "fact_order.pay_time",
            ["dim_shop.main_category_id", "dim_product.category_id"],
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:默认口径", "考点:多表连接"],
        note="同城指买家所在城市等于店铺所在城市；实付金额按口径约定只算已付款订单，分子分母都限定在同一个一级类目内；"
             "订单归类目可走店铺主营类目或明细商品类目（需按订单去重），结果一致。",
    ),
    EvalCase(
        id="H10E02",
        query="同一个用户在两笔及以上不同的订单里都买过某个品牌，就算这个品牌的一位回头客。有回头客的品牌各有几位回头客？",
        reference_sql="""
WITH ub AS (
    SELECT o.user_id, p.brand, COUNT(DISTINCT o.order_id) AS order_cnt
    FROM fact_order o
    JOIN fact_order_item i ON i.order_id = o.order_id
    JOIN dim_product p ON p.product_id = i.product_id
    WHERE o.pay_time IS NOT NULL
    GROUP BY o.user_id, p.brand
)
SELECT brand, COUNT(*) AS repeat_users
FROM ub
WHERE order_cnt >= 2
GROUP BY brand
""",
        must_hit_columns=[
            "dim_product.brand",
            "fact_order.user_id",
            "fact_order.pay_time",
            "fact_order_item.product_id",
        ],
        tags=["难度:难", "考点:默认口径", "考点:两层聚合"],
        note="「买过」按口径约定只算已付款订单；先按用户×品牌数不同订单数，至少 2 单才算回头客，再按品牌数人；"
             "同一笔订单里买同品牌多件只算一单；没有回头客的品牌不列。",
    ),
    EvalCase(
        id="H10E03",
        query="按每个用户第一次下单时用的渠道来分（第一单不管什么状态），每个渠道带来的这批用户人均消费多少钱？"
              "没付过款的用户也算在人数里，保留两位小数。",
        reference_sql="""
WITH f AS (
    SELECT user_id, channel,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time) AS rn
    FROM fact_order
)
SELECT f.channel, ROUND(AVG(s.total_pay_amount), 2) AS avg_spend
FROM f
JOIN dws_user_summary s ON s.user_id = f.user_id
WHERE f.rn = 1
GROUP BY f.channel
""",
        must_hit_columns=[
            "fact_order.channel",
            "fact_order.create_time",
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:难", "考点:相对时间", "考点:两层聚合"],
        note="首单按下单时间取、不限状态，同一用户没有同一时刻的两笔订单；消费按口径约定只算已付款订单的实付金额，"
             "先到用户粒度再按首单渠道平均，分母含零消费用户。用户汇总表与按订单聚合结果一致。",
    ),
    EvalCase(
        id="H10E04",
        query="各个会员等级的用户，从注册那天到第一次付款那天平均隔了多少天？按日期算、不看几点，保留一位小数。",
        reference_sql="""
WITH f AS (
    SELECT user_id, MIN(pay_time) AS first_pay
    FROM fact_order
    WHERE pay_time IS NOT NULL
    GROUP BY user_id
)
SELECT u.member_level,
       ROUND(AVG(julianday(date(f.first_pay)) - julianday(u.register_time)), 1) AS avg_days
FROM dim_user u
JOIN f ON f.user_id = u.user_id
GROUP BY u.member_level
""",
        must_hit_columns=[
            "dim_user.member_level",
            "dim_user.register_time",
            ["fact_order.pay_time", "fact_payment.pay_time"],
        ],
        tags=["难度:难", "考点:默认口径", "考点:相对时间"],
        note="第一次付款取用户已付款订单里最早的支付时间（支付流水的支付时间与之相同）；只统计付过款的用户；"
             "题面写明按日期相减，避免带时分秒造成的小数差异。",
    ),
    EvalCase(
        id="H10E05",
        query="金卡会员在数码电器这个大类里买的东西，按品牌看各卖了多少件？只算已完成的订单。",
        reference_sql="""
SELECT p.brand, SUM(i.quantity) AS qty
FROM dim_user u
JOIN fact_order o ON o.user_id = u.user_id
JOIN fact_order_item i ON i.order_id = o.order_id
JOIN dim_product p ON p.product_id = i.product_id
JOIN dim_category c2 ON c2.category_id = p.category_id
JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
WHERE u.member_level = '金卡会员'
  AND c1.category_name = '数码电器'
  AND o.order_status = '已完成'
GROUP BY p.brand
""",
        must_hit_columns=[
            "dim_user.member_level",
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.brand",
            ["dim_product.category_id", "dim_shop.main_category_id"],
        ],
        tags=["难度:难", "考点:多表连接"],
        note="件数是明细数量求和；商品挂在二级类目，要经父类目落到一级类目「数码电器」；状态题面点名为已完成。",
    ),
    EvalCase(
        id="H10E06",
        query="每个下单渠道里，一单买了两种及以上不同商品的订单占这个渠道订单数的百分之几？订单什么状态都算，保留两位小数。",
        reference_sql="""
WITH oi AS (
    SELECT order_id, COUNT(DISTINCT product_id) AS product_kinds
    FROM fact_order_item
    GROUP BY order_id
)
SELECT o.channel,
       ROUND(100.0 * SUM(CASE WHEN oi.product_kinds >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS multi_pct
FROM fact_order o
JOIN oi ON oi.order_id = o.order_id
GROUP BY o.channel
""",
        must_hit_columns=[
            "fact_order.channel",
            "fact_order_item.product_id",
            "fact_order_item.order_id",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先到订单粒度数商品种数，再按下单渠道算占比；每笔订单都有明细，且同一订单里没有重复的商品行，"
             "按明细行数或去重商品数结果一致。",
    ),
    EvalCase(
        id="H10E07",
        query="只算已完成的订单，每个二级类目里卖得最多（按件数）的是哪件商品？同名但编号不同的算不同商品。"
              "列出类目、商品编号、商品名称和件数。",
        reference_sql="""
WITH q AS (
    SELECT p.product_id, p.product_name, p.category_id, SUM(i.quantity) AS qty
    FROM fact_order_item i
    JOIN fact_order o ON o.order_id = i.order_id
    JOIN dim_product p ON p.product_id = i.product_id
    WHERE o.order_status = '已完成'
    GROUP BY p.product_id, p.product_name, p.category_id
), r AS (
    SELECT c.category_name, q.product_id, q.product_name, q.qty,
           RANK() OVER (PARTITION BY q.category_id ORDER BY q.qty DESC) AS rk
    FROM q
    JOIN dim_category c ON c.category_id = q.category_id
)
SELECT category_name, product_id, product_name, qty
FROM r
WHERE rk = 1
""",
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.product_name",
            "dim_product.category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:多表连接", "考点:窗口排名"],
        note="库里有同名不同编号的商品，题面写明按编号区分；每个二级类目第一名无并列。",
    ),
    EvalCase(
        id="H10E08",
        query="有多少条加购记录，是同一个用户在加购之后 7 天（168 小时）以内就下单买了这件商品的？"
              "下单时间要晚于加购时间，订单后来付没付款都算。",
        reference_sql="""
SELECT COUNT(*) AS cnt
FROM fact_user_behavior b
WHERE b.behavior_type = '加购'
  AND EXISTS (
      SELECT 1
      FROM fact_order o
      JOIN fact_order_item i ON i.order_id = o.order_id
      WHERE o.user_id = b.user_id
        AND i.product_id = b.product_id
        AND o.create_time > b.behavior_time
        AND julianday(o.create_time) - julianday(b.behavior_time) <= 7
  )
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.behavior_time",
            "fact_user_behavior.product_id",
            "fact_order.create_time",
            "fact_order_item.product_id",
        ],
        tags=["难度:难", "考点:相对时间"],
        note="按加购记录计数，一条加购后面跟几笔订单也只算一次；时间窗按精确时长 168 小时，下单须晚于加购，不限订单状态。",
    ),
    EvalCase(
        id="H10E09",
        query="哪些店铺从来没有因为发错货被申请过退款？列出店铺名。",
        reference_sql="""
SELECT s.shop_name
FROM dim_shop s
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_order o
    JOIN fact_refund r ON r.order_id = o.order_id
    WHERE o.shop_id = s.shop_id AND r.refund_reason = '发错货'
)
""",
        must_hit_columns=[
            "dim_shop.shop_name",
            "fact_refund.refund_reason",
            "fact_order.shop_id",
        ],
        tags=["难度:中等", "考点:否定集合"],
        note="退款挂在订单上，经订单找到店铺；只要有发错货的退款申请就算有（不论退款状态）。",
    ),
    EvalCase(
        id="H10E10",
        query="下过至少 3 笔订单（什么状态都算）、而且每一笔都是从同一个渠道下的用户有哪些？"
              "列出用户昵称、那个渠道和他的订单数。",
        reference_sql="""
SELECT u.user_name, MIN(o.channel) AS channel, COUNT(*) AS order_cnt
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
GROUP BY o.user_id, u.user_name
HAVING COUNT(*) >= 3 AND COUNT(DISTINCT o.channel) = 1
""",
        must_hit_columns=[
            "dim_user.user_name",
            "fact_order.channel",
        ],
        tags=["难度:中等", "考点:否定集合"],
        note="「全都是同一个渠道」：按用户汇总后要求渠道去重数为 1、订单数至少 3；渠道指下单渠道。",
    ),
    EvalCase(
        id="H10E11",
        query="看每个用户最近的一次下单，那笔订单现在处于什么状态？按状态数一下各有多少个用户。",
        reference_sql="""
WITH t AS (
    SELECT o.user_id, o.order_status,
           ROW_NUMBER() OVER (PARTITION BY o.user_id ORDER BY o.create_time DESC) AS rn
    FROM fact_order o
)
SELECT order_status, COUNT(*) AS user_cnt
FROM t
WHERE rn = 1
GROUP BY order_status
""",
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order.create_time",
        ],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="最近一次按下单时间取，同一用户没有同一时刻的两笔订单；也可用用户汇总表的最近下单时间回连订单，结果一致。",
    ),
    EvalCase(
        id="H10E12",
        query="每种退款原因下，退款金额合计占这些订单实付金额合计的百分之几？退款中的也算，百分比保留两位小数。",
        reference_sql="""
SELECT r.refund_reason,
       ROUND(100.0 * SUM(r.refund_amount) / SUM(o.pay_amount), 2) AS refund_pct
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
GROUP BY r.refund_reason
""",
        must_hit_columns=[
            "fact_refund.refund_reason",
            "fact_refund.refund_amount",
            "fact_order.pay_amount",
        ],
        tags=["难度:中等"],
        note="一笔订单最多一条退款记录，按原因把退款金额与对应订单的实付金额分别合计再相除；题面写明含退款中。",
    ),
    EvalCase(
        id="H10E13",
        query="三个大类里，各自是哪种支付方式付的钱最多？列出大类、支付方式和金额（保留两位小数）。",
        reference_sql="""
WITH t AS (
    SELECT c1.category_name, p.pay_channel, SUM(p.pay_amount) AS amt
    FROM fact_payment p
    JOIN fact_order o ON o.order_id = p.order_id
    JOIN dim_shop s ON s.shop_id = o.shop_id
    JOIN dim_category c2 ON c2.category_id = s.main_category_id
    JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
    GROUP BY c1.category_name, p.pay_channel
), r AS (
    SELECT category_name, pay_channel, amt,
           RANK() OVER (PARTITION BY category_name ORDER BY amt DESC) AS rk
    FROM t
)
SELECT category_name, pay_channel, ROUND(amt, 2) AS amt
FROM r
WHERE rk = 1
""",
        must_hit_columns=[
            "fact_payment.pay_channel",
            ["fact_payment.pay_amount", "fact_order.pay_amount"],
            ["dim_shop.main_category_id", "dim_product.category_id"],
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:多表连接", "考点:窗口排名"],
        note="支付方式在支付流水表；流水全部支付成功、一单一条，金额与订单实付一致；"
             "订单归一级类目可走店铺主营类目或明细商品类目（需去重），结果一致。每个大类第一名无并列。",
    ),
    EvalCase(
        id="H10E14",
        query="按付款日期一天天往上累计，全平台的实付金额是在哪一天第一次超过 500 万的？",
        reference_sql="""
WITH d AS (
    SELECT date(pay_time) AS pay_date, SUM(pay_amount) AS amt
    FROM fact_order
    WHERE pay_time IS NOT NULL
    GROUP BY date(pay_time)
), c AS (
    SELECT pay_date, SUM(amt) OVER (ORDER BY pay_date) AS cum_amt
    FROM d
)
SELECT MIN(pay_date) AS first_day
FROM c
WHERE cum_amt > 5000000
""",
        must_hit_columns=[
            ["fact_order.pay_time", "fact_payment.pay_time"],
            ["fact_order.pay_amount", "fact_payment.pay_amount"],
        ],
        tags=["难度:难", "考点:默认口径", "考点:窗口排名"],
        note="实付金额按口径约定只算已付款订单；按支付日期累计，前一天累计约 478.6 万、当天约 505.9 万，阈值附近不敏感。"
             "用支付流水表结果相同。",
    ),
    EvalCase(
        id="H10E15",
        query="按店铺类型看，买家确认收货之后平均隔几天才申请退款？不管退款有没有办完都算，保留一位小数。",
        reference_sql="""
SELECT s.shop_type,
       ROUND(AVG(julianday(r.apply_time) - julianday(o.finish_time)), 1) AS avg_days
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
JOIN dim_shop s ON s.shop_id = o.shop_id
GROUP BY s.shop_type
""",
        must_hit_columns=[
            "fact_refund.apply_time",
            "fact_order.finish_time",
            "dim_shop.shop_type",
        ],
        tags=["难度:中等", "考点:相对时间"],
        note="确认收货时间是订单完成时间（退款订单都有），与退款申请时间相减；含退款中的记录。"
             "数据里两者相差都是整天数，按日期或精确时长结果相同。",
    ),
    EvalCase(
        id="H10E16",
        query="每个年龄段人均消费多少钱？人均按这个年龄段的全部注册用户算，没消费过的也算在内，保留两位小数。",
        reference_sql="""
SELECT u.age_group, ROUND(AVG(s.total_pay_amount), 2) AS avg_spend
FROM dim_user u
JOIN dws_user_summary s ON s.user_id = u.user_id
GROUP BY u.age_group
""",
        must_hit_columns=[
            "dim_user.age_group",
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:中等", "考点:默认口径", "考点:两层聚合"],
        note="消费按口径约定只算已付款订单；先到用户粒度再按年龄段平均，分母写明含零消费用户。"
             "用户汇总表与按订单聚合（左连接补 0）结果一致。",
    ),
    EvalCase(
        id="H10E17",
        query="美妆护肤和数码电器两个大类都买过东西的用户有多少位？",
        reference_sql="""
WITH uc AS (
    SELECT DISTINCT o.user_id, c1.category_name
    FROM fact_order o
    JOIN dim_shop s ON s.shop_id = o.shop_id
    JOIN dim_category c2 ON c2.category_id = s.main_category_id
    JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
    WHERE o.pay_time IS NOT NULL
)
SELECT COUNT(*) AS user_cnt
FROM (
    SELECT user_id
    FROM uc
    WHERE category_name IN ('美妆护肤', '数码电器')
    GROUP BY user_id
    HAVING COUNT(DISTINCT category_name) = 2
) x
""",
        must_hit_columns=[
            "fact_order.pay_time",
            "fact_order.user_id",
            ["dim_shop.main_category_id", "dim_product.category_id"],
            "dim_category.category_name",
        ],
        tags=["难度:中等", "考点:默认口径", "考点:否定集合"],
        note="「买过」按口径约定只算已付款订单；「同时」要求两个一级类目都出现；类目可经店铺主营类目或明细商品类目，结果一致。",
    ),
    EvalCase(
        id="H10E18",
        query="5 月里哪几天全平台下单的人数达到了 30 人及以上？同一个人一天在几家店下单只算一个人，订单什么状态都算。"
              "列出日期和人数。",
        reference_sql="""
SELECT date(create_time) AS order_date, COUNT(DISTINCT user_id) AS buyer_cnt
FROM fact_order
GROUP BY date(create_time)
HAVING COUNT(DISTINCT user_id) >= 30
""",
        must_hit_columns=[
            "fact_order.create_time",
            "fact_order.user_id",
        ],
        tags=["难度:难", "考点:两层聚合"],
        note="全平台按天去重用户；店铺日汇总的买家数是按店去重的，跨店相加会重复计人（会多出一天），不能直接加总。",
    ),
    EvalCase(
        id="H10E19",
        query="好物专营店14 有哪几天的成交额达到了它上一个有下单的日子的两倍及以上？列出日期和当天的成交额（保留两位小数）。",
        reference_sql="""
WITH t AS (
    SELECT d.stat_date, d.gmv,
           LAG(d.gmv) OVER (ORDER BY d.stat_date) AS prev_gmv
    FROM dws_shop_daily d
    JOIN dim_shop s ON s.shop_id = d.shop_id
    WHERE s.shop_name = '好物专营店14'
)
SELECT stat_date, ROUND(gmv, 2) AS gmv
FROM t
WHERE prev_gmv IS NOT NULL AND gmv >= 2 * prev_gmv
""",
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "考点:窗口排名"],
        note="和上一条记录比较：上一个有下单的日子即该店前一条日汇总记录；成交额为 GMV。按订单按下单日聚合结果一致。",
    ),
    EvalCase(
        id="H10E20",
        query="按大类看，商品被加购的次数相当于被浏览次数的百分之多少？保留一位小数。",
        reference_sql="""
SELECT c1.category_name,
       ROUND(100.0 * SUM(CASE WHEN b.behavior_type = '加购' THEN 1 ELSE 0 END)
             / SUM(CASE WHEN b.behavior_type = '浏览' THEN 1 ELSE 0 END), 1) AS cart_pct
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
JOIN dim_category c2 ON c2.category_id = p.category_id
JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
GROUP BY c1.category_name
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            ["dim_product.category_id", "dim_shop.main_category_id"],
            "dim_category.category_name",
        ],
        tags=["难度:中等"],
        note="按一级类目分别数加购、浏览行为条数再相除；行为挂在商品上，经二级类目落到一级类目。",
    ),
    EvalCase(
        id="H10E21",
        query="只看已完成的订单，哪 3 个品牌的毛利最高？毛利按商品实际成交的钱（已经扣掉优惠、不含运费）"
              "减去这些件数的成本价来算。列出品牌和毛利，保留两位小数。",
        reference_sql="""
SELECT p.brand, ROUND(SUM(i.item_amount - p.cost_price * i.quantity), 2) AS gross_profit
FROM fact_order_item i
JOIN dim_product p ON p.product_id = i.product_id
JOIN fact_order o ON o.order_id = i.order_id
WHERE o.order_status = '已完成'
GROUP BY p.brand
ORDER BY gross_profit DESC
LIMIT 3
""",
        must_hit_columns=[
            "dim_product.brand",
            "dim_product.cost_price",
            "fact_order_item.item_amount",
            "fact_order_item.quantity",
            "fact_order.order_status",
        ],
        tags=["难度:中等"],
        note="题面写明按实际成交金额（扣优惠、不含运费）减成本价×件数，即明细行成交金额减成本，排除了按标价或按含运费的"
             "订单实付来算的理解；第 3、4 名相差约 4.5 万，无并列。",
    ),
    EvalCase(
        id="H10E22",
        query="按店铺类型看，平均每家店 5 月的成交额是多少？保留两位小数。",
        reference_sql="""
SELECT s.shop_type, ROUND(AVG(t.shop_gmv), 2) AS avg_gmv_per_shop
FROM dim_shop s
JOIN (
    SELECT shop_id, SUM(gmv) AS shop_gmv
    FROM dws_shop_daily
    GROUP BY shop_id
) t ON t.shop_id = s.shop_id
GROUP BY s.shop_type
""",
        must_hit_columns=[
            "dim_shop.shop_type",
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先到店铺粒度汇总 5 月 GMV，再按店铺类型平均；15 家店 5 月都有订单，分母就是该类型的店铺数。按订单聚合结果一致。",
    ),
    EvalCase(
        id="H10E23",
        query="每家店铺 5 月下半月（16 日到月底）的成交额比上半月（1 日到 15 日）涨了百分之几？跌了就写负数，保留两位小数。"
              "列出店铺名和涨幅。",
        reference_sql="""
SELECT s.shop_name,
       ROUND(100.0 * (SUM(CASE WHEN d.stat_date >= '2024-05-16' THEN d.gmv ELSE 0 END)
                      - SUM(CASE WHEN d.stat_date <= '2024-05-15' THEN d.gmv ELSE 0 END))
             / SUM(CASE WHEN d.stat_date <= '2024-05-15' THEN d.gmv ELSE 0 END), 2) AS change_pct
FROM dws_shop_daily d
JOIN dim_shop s ON s.shop_id = d.shop_id
GROUP BY s.shop_id, s.shop_name
""",
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:中等", "考点:相对时间"],
        note="前后两个时段对比，时段按下单日期、两头都算；成交额为 GMV（全部订单商品总金额）；每家店两个半月都有成交。"
             "按订单按下单日聚合结果一致。",
    ),
    EvalCase(
        id="H10E24",
        query="按会员等级看，大家买的东西里，标价 3000 元及以上的商品件数占买的总件数的百分之几？保留两位小数。",
        reference_sql="""
SELECT u.member_level,
       ROUND(100.0 * SUM(CASE WHEN p.list_price >= 3000 THEN i.quantity ELSE 0 END) / SUM(i.quantity), 2)
           AS high_price_pct
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
JOIN fact_order_item i ON i.order_id = o.order_id
JOIN dim_product p ON p.product_id = i.product_id
WHERE o.pay_time IS NOT NULL
GROUP BY u.member_level
""",
        must_hit_columns=[
            "dim_user.member_level",
            ["dim_product.list_price", "fact_order_item.item_price"],
            "fact_order_item.quantity",
            "fact_order.pay_time",
        ],
        tags=["难度:难", "考点:默认口径", "考点:多表连接"],
        note="「买」按口径约定只算已付款订单；件数按明细数量求和；标价是商品挂牌价，本库下单单价与标价相同，"
             "两条路径结果一致；3000 元附近没有商品，边界不敏感。",
    ),
    EvalCase(
        id="H10E25",
        query="在食品生鲜大类里收藏过商品、却从来没在这个大类买过东西的用户有多少位？",
        reference_sql="""
SELECT COUNT(DISTINCT b.user_id) AS user_cnt
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
JOIN dim_category c2 ON c2.category_id = p.category_id
JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
WHERE b.behavior_type = '收藏'
  AND c1.category_name = '食品生鲜'
  AND b.user_id NOT IN (
      SELECT o.user_id
      FROM fact_order o
      JOIN dim_shop s ON s.shop_id = o.shop_id
      JOIN dim_category c3 ON c3.category_id = s.main_category_id
      JOIN dim_category c4 ON c4.category_id = c3.parent_category_id
      WHERE o.pay_time IS NOT NULL AND c4.category_name = '食品生鲜'
  )
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.user_id",
            "fact_order.pay_time",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:默认口径", "考点:否定集合", "考点:多表连接"],
        note="「买过」按口径约定只算已付款订单；收藏和购买都限定在食品生鲜一级类目下；订单类目经店铺主营类目或明细商品类目，结果一致。",
    ),
    EvalCase(
        id="H10E26",
        query="退款的订单占到自己下单总笔数一半及以上的用户有哪些？列出昵称、下单笔数和退款订单数。",
        reference_sql="""
SELECT u.user_name, s.total_order_count, s.refund_order_count
FROM dws_user_summary s
JOIN dim_user u ON u.user_id = s.user_id
WHERE s.total_order_count > 0
  AND s.refund_order_count * 2 >= s.total_order_count
""",
        must_hit_columns=[
            "dim_user.user_name",
            ["dws_user_summary.refund_order_count", "fact_order.order_status", "fact_refund.order_id"],
        ],
        tags=["难度:中等"],
        note="下单笔数含所有状态；退款订单数即有退款的订单（状态已退款与退款记录一一对应）；用户汇总表与按订单统计结果一致。",
    ),
    EvalCase(
        id="H10E27",
        query="直播间下的单里，有多少笔是用花呗分期付的钱？",
        reference_sql="""
SELECT COUNT(*) AS order_cnt
FROM fact_order o
JOIN fact_payment p ON p.order_id = o.order_id
WHERE o.channel = '直播间' AND p.pay_channel = '花呗分期'
""",
        must_hit_columns=[
            "fact_order.channel",
            "fact_payment.pay_channel",
        ],
        tags=["难度:简单"],
        note="下单渠道在订单表、支付方式在支付流水表，一单一条流水。",
    ),
    EvalCase(
        id="H10E28",
        query="5 月里各个商品收到的用户评价平均打了几星？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里没有评价、评分或星级数据，行为表只有浏览、加购、收藏。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H10E29",
        query="5 月各家店铺投放广告花了多少推广费？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里没有广告投放、推广费用等营销成本数据；优惠金额是给买家的让利，不是推广费。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H10E30",
        query="用户在 APP 里搜得最多的前 10 个关键词是什么？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里没有搜索日志或搜索关键词，行为类型只有浏览、加购、收藏。",
        expect_unanswerable=True,
    ),
]


# ---------------------------------------------------------------------------
# chinook（20 题，其中陷阱题 3 道）
# ---------------------------------------------------------------------------

HOLDOUT10_CHINOOK_CASES = [
    EvalCase(
        id="H10C01",
        query="老板想看看三位销售支持各自负责的客户买 Rock 的歌一共花了多少钱，列出员工的名、姓和金额（保留两位小数）。",
        reference_sql="""
SELECT e.FirstName, e.LastName, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS rock_sales
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
JOIN Invoice i ON i.CustomerId = c.CustomerId
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
WHERE g.Name = 'Rock'
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "Employee.FirstName",
            "Employee.LastName",
            "Customer.SupportRepId",
            "Genre.Name",
            "InvoiceLine.UnitPrice",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="员工到客户只能走 SupportRepId；按流派算金额必须落到发票明细；Rock 是流派原文，不含 Rock And Roll。",
    ),
    EvalCase(
        id="H10C02",
        query="客户不少于 4 位的国家里，每个国家消费最多的是哪位客户？列出国家、客户的名和姓，以及他一共花了多少钱（保留两位小数）。",
        reference_sql="""
WITH cs AS (
    SELECT c.CustomerId, c.Country, c.FirstName, c.LastName, SUM(i.Total) AS spend
    FROM Customer c
    JOIN Invoice i ON i.CustomerId = c.CustomerId
    GROUP BY c.CustomerId, c.Country, c.FirstName, c.LastName
), big AS (
    SELECT Country FROM Customer GROUP BY Country HAVING COUNT(*) >= 4
), r AS (
    SELECT cs.*, RANK() OVER (PARTITION BY Country ORDER BY spend DESC) AS rk
    FROM cs
    WHERE Country IN (SELECT Country FROM big)
)
SELECT Country, FirstName, LastName, ROUND(spend, 2) AS spend
FROM r
WHERE rk = 1
""",
        must_hit_columns=[
            ["Customer.Country", "Invoice.BillingCountry"],
            "Customer.FirstName",
            "Customer.LastName",
            "Invoice.Total",
        ],
        tags=["难度:难", "考点:两层聚合", "考点:窗口排名"],
        note="先按国家数客户筛出 5 个国家，再在国家内按客户消费排名；这些国家第一名无并列。"
             "本库开票国家与客户国家一致，两条路径结果相同。",
    ),
    EvalCase(
        id="H10C03",
        query="有哪些国家买过 Blues 的歌、却一首 Jazz 都没买过？",
        reference_sql="""
SELECT DISTINCT i.BillingCountry
FROM Invoice i
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
WHERE g.Name = 'Blues'
  AND i.BillingCountry NOT IN (
      SELECT i2.BillingCountry
      FROM Invoice i2
      JOIN InvoiceLine il2 ON il2.InvoiceId = i2.InvoiceId
      JOIN Track t2 ON t2.TrackId = il2.TrackId
      JOIN Genre g2 ON g2.GenreId = t2.GenreId
      WHERE g2.Name = 'Jazz'
  )
""",
        must_hit_columns=[
            ["Invoice.BillingCountry", "Customer.Country"],
            "Genre.Name",
            "InvoiceLine.TrackId",
        ],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="国家粒度的「买过 A、没买过 B」；流派经明细→曲目落到流派原文。本库开票国家与客户国家一致，两条路径结果相同。",
    ),
    EvalCase(
        id="H10C04",
        query="按年份看，每年卖出去的份数里，Protected AAC audio file 和 Protected MPEG-4 video file "
              "这两种受保护格式加起来占百分之几？保留两位小数。",
        reference_sql="""
SELECT strftime('%Y', i.InvoiceDate) AS yr,
       ROUND(100.0 * SUM(CASE WHEN m.Name IN ('Protected AAC audio file', 'Protected MPEG-4 video file')
                              THEN 1 ELSE 0 END) / COUNT(*), 2) AS protected_pct
FROM Invoice i
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
GROUP BY yr
""",
        must_hit_columns=[
            "Invoice.InvoiceDate",
            "MediaType.Name",
            "Track.MediaTypeId",
        ],
        tags=["难度:中等", "考点:多表连接"],
        note="按开票年份分组；份数按发票明细行（数量全为 1，按数量求和结果相同）；格式取值为原文，经曲目落到媒体格式。",
    ),
    EvalCase(
        id="H10C05",
        query="Heavy Metal Classic 这个歌单里，有哪些歌一次都没卖出去过？列出歌名。",
        reference_sql="""
SELECT t.Name
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t ON t.TrackId = pt.TrackId
WHERE p.Name = 'Heavy Metal Classic'
  AND NOT EXISTS (SELECT 1 FROM InvoiceLine il WHERE il.TrackId = t.TrackId)
""",
        must_hit_columns=[
            "Playlist.Name",
            "PlaylistTrack.TrackId",
            "Track.Name",
            "InvoiceLine.TrackId",
        ],
        tags=["难度:中等", "考点:否定集合", "考点:多表连接"],
        note="歌单收录只用来圈定范围，是否卖出看发票明细；该歌单名唯一。",
    ),
    EvalCase(
        id="H10C06",
        query="整张专辑所有曲目加起来超过 2 小时的专辑，各卖出去了多少份？列出专辑名、专辑总时长（分钟，保留一位小数）和卖出的份数。",
        reference_sql="""
WITH al AS (
    SELECT a.AlbumId, a.Title, SUM(t.Milliseconds) AS total_ms
    FROM Album a
    JOIN Track t ON t.AlbumId = a.AlbumId
    GROUP BY a.AlbumId, a.Title
    HAVING SUM(t.Milliseconds) > 2 * 60 * 60 * 1000
), sold AS (
    SELECT t.AlbumId, COUNT(*) AS sold_cnt
    FROM Track t
    JOIN InvoiceLine il ON il.TrackId = t.TrackId
    GROUP BY t.AlbumId
)
SELECT al.Title, ROUND(al.total_ms / 60000.0, 1) AS total_minutes, COALESCE(sold.sold_cnt, 0) AS sold_cnt
FROM al
LEFT JOIN sold ON sold.AlbumId = al.AlbumId
""",
        must_hit_columns=[
            "Album.Title",
            "Track.Milliseconds",
            "Track.AlbumId",
            "InvoiceLine.TrackId",
        ],
        tags=["难度:难", "考点:两层聚合"],
        note="专辑时长要在曲目粒度上单独汇总，若先连发票明细再求和会把时长按销量放大；份数按明细行数（数量全为 1）。"
             "超过 2 小时的专辑都有销量，且 100 到 131 分钟之间没有专辑，阈值不敏感；专辑名无重复。",
    ),
    EvalCase(
        id="H10C07",
        query="每位带团队的员工，直接和间接归他管的一共有几个人？下属的下属也算。列出名、姓和人数。",
        reference_sql="""
WITH RECURSIVE sub(mgr_id, emp_id) AS (
    SELECT ReportsTo, EmployeeId FROM Employee WHERE ReportsTo IS NOT NULL
    UNION ALL
    SELECT s.mgr_id, e.EmployeeId
    FROM sub s
    JOIN Employee e ON e.ReportsTo = s.emp_id
)
SELECT m.FirstName, m.LastName, COUNT(*) AS team_size
FROM sub
JOIN Employee m ON m.EmployeeId = sub.mgr_id
GROUP BY m.EmployeeId, m.FirstName, m.LastName
""",
        must_hit_columns=[
            "Employee.ReportsTo",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:难"],
        note="上下级是员工表的自引用层级，要沿汇报链一直往下数（递归），不只是直接下属；只列有下属的员工，"
             "层级无环、每人只有一个上级，不会重复计人。",
    ),
    EvalCase(
        id="H10C08",
        query="2024 年每个季度卖了多少钱，比上一个季度涨了百分之几？第一季度跟 2023 年第四季度比。"
              "季度用 1 到 4 表示，金额和百分比都保留两位小数。",
        reference_sql="""
WITH q AS (
    SELECT CAST(strftime('%Y', InvoiceDate) AS INTEGER) AS yr,
           (CAST(strftime('%m', InvoiceDate) AS INTEGER) + 2) / 3 AS qtr,
           SUM(Total) AS amt
    FROM Invoice
    GROUP BY yr, qtr
), l AS (
    SELECT yr, qtr, amt, LAG(amt) OVER (ORDER BY yr, qtr) AS prev_amt
    FROM q
)
SELECT qtr, ROUND(amt, 2) AS amt, ROUND(100.0 * (amt - prev_amt) / prev_amt, 2) AS growth_pct
FROM l
WHERE yr = 2024
""",
        must_hit_columns=[
            "Invoice.InvoiceDate",
            "Invoice.Total",
        ],
        tags=["难度:难", "考点:窗口排名"],
        note="环比要跨年取上一季度，题面写明 Q1 对比 2023 年 Q4；销售额直接对发票总额求和。",
    ),
    EvalCase(
        id="H10C09",
        query="Led Zeppelin 每张专辑里最长的是哪首歌，有几分钟？列出专辑名、歌名和分钟数（保留两位小数）。",
        reference_sql="""
WITH t AS (
    SELECT a.AlbumId, a.Title, tr.Name, tr.Milliseconds,
           RANK() OVER (PARTITION BY a.AlbumId ORDER BY tr.Milliseconds DESC) AS rk
    FROM Artist ar
    JOIN Album a ON a.ArtistId = ar.ArtistId
    JOIN Track tr ON tr.AlbumId = a.AlbumId
    WHERE ar.Name = 'Led Zeppelin'
)
SELECT Title, Name, ROUND(Milliseconds / 60000.0, 2) AS minutes
FROM t
WHERE rk = 1
""",
        must_hit_columns=[
            "Artist.Name",
            "Album.Title",
            "Track.Name",
            "Track.Milliseconds",
        ],
        tags=["难度:中等", "考点:窗口排名"],
        note="每张专辑内按时长取第一，14 张专辑各一首、无并列；时长毫秒换算分钟。",
    ),
    EvalCase(
        id="H10C10",
        query="买过的歌全都是 0.99 美元成交的客户有多少位？",
        reference_sql="""
SELECT COUNT(*) AS customer_cnt
FROM Customer c
WHERE EXISTS (SELECT 1 FROM Invoice i WHERE i.CustomerId = c.CustomerId)
  AND NOT EXISTS (
      SELECT 1
      FROM Invoice i
      JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
      WHERE i.CustomerId = c.CustomerId AND il.UnitPrice <> 0.99
  )
""",
        must_hit_columns=[
            "InvoiceLine.UnitPrice",
            "Invoice.CustomerId",
        ],
        tags=["难度:中等", "考点:否定集合"],
        note="「全都是」：客户的所有明细行成交价都为 0.99，等价于从没以 1.99 成交过；成交价用明细行单价。",
    ),
    EvalCase(
        id="H10C11",
        query="Iron Maiden 的歌都卖到了哪些国家？列出国家、卖出的份数和金额（保留两位小数）。",
        reference_sql="""
SELECT i.BillingCountry, COUNT(*) AS sold_cnt, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS amt
FROM Artist ar
JOIN Album a ON a.ArtistId = ar.ArtistId
JOIN Track t ON t.AlbumId = a.AlbumId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
JOIN Invoice i ON i.InvoiceId = il.InvoiceId
WHERE ar.Name = 'Iron Maiden'
GROUP BY i.BillingCountry
""",
        must_hit_columns=[
            "Artist.Name",
            ["Invoice.BillingCountry", "Customer.Country"],
            "InvoiceLine.UnitPrice",
        ],
        tags=["难度:中等", "考点:多表连接"],
        note="艺术家→专辑→曲目→明细→发票；销售地域按开票国家，本库与客户国家一致；所有明细数量为 1，"
             "且同一国家没有重复买同一首，份数与曲目数相同。",
    ),
    EvalCase(
        id="H10C12",
        query="三位销售支持各自负责的客户，平均隔多少天会再买一次？按同一位客户相邻两次购买之间隔的天数算，保留一位小数。"
              "列出员工的名、姓和天数。",
        reference_sql="""
WITH g AS (
    SELECT c.SupportRepId, i.InvoiceDate,
           LAG(i.InvoiceDate) OVER (PARTITION BY i.CustomerId ORDER BY i.InvoiceDate) AS prev_date
    FROM Invoice i
    JOIN Customer c ON c.CustomerId = i.CustomerId
)
SELECT e.FirstName, e.LastName,
       ROUND(AVG(julianday(g.InvoiceDate) - julianday(g.prev_date)), 1) AS avg_gap_days
FROM g
JOIN Employee e ON e.EmployeeId = g.SupportRepId
WHERE g.prev_date IS NOT NULL
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "Invoice.InvoiceDate",
            "Invoice.CustomerId",
            "Customer.SupportRepId",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="每张发票和同一客户上一张发票比较取间隔天数，再按负责员工平均；同一客户没有同日两张发票；"
             "把所有间隔一起平均与先按客户平均再平均，保留一位小数后结果相同。",
    ),
    EvalCase(
        id="H10C13",
        query="买过的歌来自不同艺术家最多的 3 位客户是谁？列出客户的名、姓和他买过的艺术家个数。",
        reference_sql="""
SELECT c.FirstName, c.LastName, COUNT(DISTINCT a.ArtistId) AS artist_cnt
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN Album a ON a.AlbumId = t.AlbumId
GROUP BY c.CustomerId, c.FirstName, c.LastName
ORDER BY artist_cnt DESC
LIMIT 3
""",
        must_hit_columns=[
            "Customer.FirstName",
            "Customer.LastName",
            "Album.ArtistId",
            "Track.AlbumId",
        ],
        tags=["难度:中等", "考点:多表连接"],
        note="艺术家要经明细→曲目→专辑得到，按不同艺术家去重计数；第 3、4 名（21 与 20）不并列。",
    ),
    EvalCase(
        id="H10C14",
        query="曲目数最多的 5 个流派是哪些，各有多少首？",
        reference_sql="""
SELECT g.Name, COUNT(*) AS track_cnt
FROM Genre g
JOIN Track t ON t.GenreId = g.GenreId
GROUP BY g.GenreId, g.Name
ORDER BY track_cnt DESC
LIMIT 5
""",
        must_hit_columns=[
            "Genre.Name",
            "Track.GenreId",
        ],
        tags=["难度:简单"],
        note="第 5、6 名（130 与 93 首）不并列。",
    ),
    EvalCase(
        id="H10C15",
        query="按流派看，买过这个流派的客户平均每人买了几首？只看至少有 20 位客户买过的流派，保留两位小数。",
        reference_sql="""
WITH cg AS (
    SELECT g.GenreId, g.Name, i.CustomerId, COUNT(*) AS n
    FROM Genre g
    JOIN Track t ON t.GenreId = g.GenreId
    JOIN InvoiceLine il ON il.TrackId = t.TrackId
    JOIN Invoice i ON i.InvoiceId = il.InvoiceId
    GROUP BY g.GenreId, g.Name, i.CustomerId
)
SELECT Name, ROUND(AVG(n), 2) AS avg_tracks
FROM cg
GROUP BY GenreId, Name
HAVING COUNT(*) >= 20
""",
        must_hit_columns=[
            "Genre.Name",
            "Invoice.CustomerId",
            "InvoiceLine.TrackId",
        ],
        tags=["难度:难", "考点:两层聚合", "考点:多表连接"],
        note="先到「流派×客户」粒度数购买首数，再按流派平均并按买过的客户数筛选；没有客户重复买同一首，按明细行数或去重曲目数结果一致。",
    ),
    EvalCase(
        id="H10C16",
        query="每位客户是在第几次购买时，累计消费第一次超过 30 美元的？统计一下第 3 次、第 4 次……各有多少位客户。",
        reference_sql="""
WITH t AS (
    SELECT CustomerId, InvoiceDate,
           ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate) AS rn,
           SUM(Total) OVER (PARTITION BY CustomerId ORDER BY InvoiceDate
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_amt
    FROM Invoice
), f AS (
    SELECT CustomerId, MIN(rn) AS k
    FROM t
    WHERE cum_amt > 30
    GROUP BY CustomerId
)
SELECT k, COUNT(*) AS customer_cnt
FROM f
GROUP BY k
""",
        must_hit_columns=[
            "Invoice.InvoiceDate",
            "Invoice.Total",
            "Invoice.CustomerId",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:两层聚合"],
        note="客户内按开票日期累计，取首次超过 30 的序号再按序号计数；同一客户没有同日两张发票，所有客户累计都超过 30，且没有累计值恰好在 30 附近。",
    ),
    EvalCase(
        id="H10C17",
        query="消费总额高于全体客户人均消费的客户，三位销售支持手下各有几位？列出员工的名、姓和人数。",
        reference_sql="""
WITH cs AS (
    SELECT c.CustomerId, c.SupportRepId, SUM(i.Total) AS spend
    FROM Customer c
    JOIN Invoice i ON i.CustomerId = c.CustomerId
    GROUP BY c.CustomerId, c.SupportRepId
)
SELECT e.FirstName, e.LastName, COUNT(*) AS customer_cnt
FROM cs
JOIN Employee e ON e.EmployeeId = cs.SupportRepId
WHERE cs.spend > (SELECT AVG(spend) FROM cs)
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "Customer.SupportRepId",
            "Invoice.Total",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先到客户粒度算消费，再与全体客户平均（约 39.47）比较后按负责员工计数；59 位客户都有消费，没有客户恰好等于平均值。",
    ),
    EvalCase(
        id="H10C18",
        query="三位销售支持现在每个月的工资各是多少？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="员工表只有姓名、职位、上下级、日期和联系方式，没有工资、薪酬数据。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H10C19",
        query="2000 年以后发行的专辑一共有多少张？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="专辑表只有名称和艺术家，没有发行日期或发行年份；开票日期是销售时间，不能代替。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H10C20",
        query="用信用卡付款的发票占全部发票的比例是多少？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="发票表只有开票地址和金额，库里没有支付方式、付款渠道信息。",
        expect_unanswerable=True,
    ),
]


# ---------------------------------------------------------------------------
# sakila（20 题，其中陷阱题 2 道）
# ---------------------------------------------------------------------------

HOLDOUT10_SAKILA_CASES = [
    EvalCase(
        id="H10S01",
        query="住在 Canada 的客户，在两家店（用门店所在城市称呼）各租了多少次？租借算在租出去的拷贝所在的店。",
        reference_sql="""
SELECT sc.city AS store_city, COUNT(*) AS rental_cnt
FROM rental r
JOIN customer c ON c.customer_id = r.customer_id
JOIN address ca ON ca.address_id = c.address_id
JOIN city cc ON cc.city_id = ca.city_id
JOIN country co ON co.country_id = cc.country_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN store s ON s.store_id = i.store_id
JOIN address sa ON sa.address_id = s.address_id
JOIN city sc ON sc.city_id = sa.city_id
WHERE co.country = 'Canada'
GROUP BY s.store_id, sc.city
""",
        must_hit_columns=[
            "country.country",
            "customer.address_id",
            "inventory.store_id",
            "store.address_id",
            "city.city",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="地址表要用两次：客户国家经 customer→address→city→country，门店城市经 store→address→city；"
             "门店按拷贝所在门店，不是客户注册门店。",
    ),
    EvalCase(
        id="H10S02",
        query="有多少位客户把同一部片子租过两次及以上？不一定是同一张拷贝。",
        reference_sql="""
SELECT COUNT(DISTINCT x.customer_id) AS customer_cnt
FROM (
    SELECT r.customer_id, i.film_id
    FROM rental r
    JOIN inventory i ON i.inventory_id = r.inventory_id
    GROUP BY r.customer_id, i.film_id
    HAVING COUNT(*) >= 2
) x
""",
        must_hit_columns=[
            "rental.customer_id",
            "rental.inventory_id",
            "inventory.film_id",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="租借挂在拷贝上，要经拷贝找到影片；先按客户×影片计数筛出至少 2 次，再数客户（一位客户重复租多部只算一位）。",
    ),
    EvalCase(
        id="H10S03",
        query="已经还回来的租借里，按影片分类看，逾期归还比例最高的 3 个分类是哪些？逾期指从借出到归还的实际时长超过了"
              "这部片子规定的租期，正好等于租期不算。比例用百分比，保留两位小数。",
        reference_sql="""
WITH x AS (
    SELECT cat.category_id, cat.name,
           CASE WHEN julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
                THEN 1 ELSE 0 END AS overdue
    FROM rental r
    JOIN inventory i ON i.inventory_id = r.inventory_id
    JOIN film f ON f.film_id = i.film_id
    JOIN film_category fc ON fc.film_id = f.film_id
    JOIN category cat ON cat.category_id = fc.category_id
    WHERE r.return_date IS NOT NULL
)
SELECT name, ROUND(100.0 * SUM(overdue) / COUNT(*), 2) AS overdue_pct
FROM x
GROUP BY category_id, name
ORDER BY overdue_pct DESC
LIMIT 3
""",
        must_hit_columns=[
            "rental.return_date",
            "rental.rental_date",
            "film.rental_duration",
            "category.name",
        ],
        tags=["难度:难", "考点:相对时间", "考点:多表连接"],
        note="实际时长按归还时间减借出时间精确算，与规定租期（天）比较；分母只含已归还的租借；第 3、4 名（54.91 与 54.75）不并列。",
    ),
    EvalCase(
        id="H10S04",
        query="有多少对演员一起合作过至少 5 部片子？两个人算一对，不分先后。",
        reference_sql="""
SELECT COUNT(*) AS pair_cnt
FROM (
    SELECT a1.actor_id AS actor_a, a2.actor_id AS actor_b
    FROM film_actor a1
    JOIN film_actor a2 ON a2.film_id = a1.film_id AND a1.actor_id < a2.actor_id
    GROUP BY a1.actor_id, a2.actor_id
    HAVING COUNT(*) >= 5
) x
""",
        must_hit_columns=[
            "film_actor.actor_id",
            "film_actor.film_id",
        ],
        tags=["难度:难", "考点:两层聚合"],
        note="出演关联表自连接成对，先按对数合作片数再筛选至少 5 部，最后数对数；一对只算一次（按有序对数会翻倍）；"
             "按演员编号区分，不受同名演员影响。",
    ),
    EvalCase(
        id="H10S05",
        query="按租出去的拷贝所在门店分别算，2005 年 6 月到 8 月，两家店每个月的营业额比上个月涨了百分之几？"
              "列出门店编号、月份（写成 2005-06 这种格式）和涨幅，百分比保留两位小数。",
        reference_sql="""
WITH m AS (
    SELECT i.store_id, strftime('%Y-%m', p.payment_date) AS ym, SUM(p.amount) AS amt
    FROM payment p
    JOIN rental r ON r.rental_id = p.rental_id
    JOIN inventory i ON i.inventory_id = r.inventory_id
    GROUP BY i.store_id, ym
), l AS (
    SELECT store_id, ym, amt, LAG(amt) OVER (PARTITION BY store_id ORDER BY ym) AS prev_amt
    FROM m
)
SELECT store_id, ym, ROUND(100.0 * (amt - prev_amt) / prev_amt, 2) AS growth_pct
FROM l
WHERE ym BETWEEN '2005-06' AND '2005-08'
""",
        must_hit_columns=[
            "inventory.store_id",
            "payment.amount",
            ["payment.payment_date", "rental.rental_date"],
        ],
        tags=["难度:难", "考点:窗口排名"],
        note="门店按拷贝所在门店（不是客户注册门店或收款员工门店）；月份按付款时间，本库每笔付款时间与租出时间相同，两条路径一致。",
    ),
    EvalCase(
        id="H10S06",
        query="哪些演员出演的片子，在 Woodridge 店的拷贝比在 Lethbridge 店多出 20 张及以上？"
              "列出演员的名、姓，以及在 Lethbridge 店、Woodridge 店各有几张拷贝。",
        reference_sql="""
SELECT a.first_name, a.last_name,
       SUM(CASE WHEN sc.city = 'Lethbridge' THEN 1 ELSE 0 END) AS lethbridge_copies,
       SUM(CASE WHEN sc.city = 'Woodridge' THEN 1 ELSE 0 END) AS woodridge_copies
FROM actor a
JOIN film_actor fa ON fa.actor_id = a.actor_id
JOIN inventory i ON i.film_id = fa.film_id
JOIN store s ON s.store_id = i.store_id
JOIN address sa ON sa.address_id = s.address_id
JOIN city sc ON sc.city_id = sa.city_id
GROUP BY a.actor_id, a.first_name, a.last_name
HAVING SUM(CASE WHEN sc.city = 'Woodridge' THEN 1 ELSE 0 END)
     - SUM(CASE WHEN sc.city = 'Lethbridge' THEN 1 ELSE 0 END) >= 20
""",
        must_hit_columns=[
            "actor.first_name",
            "actor.last_name",
            "film_actor.film_id",
            "inventory.store_id",
            "city.city",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="门店没有名字，要经 store→address→city 把城市对到门店；一张拷贝算给它那部片子的每位演员；按演员编号分组。",
    ),
    EvalCase(
        id="H10S07",
        query="两位店员各自收的款里，有多少笔对应的那次租借不是他本人办理的？列出店员的名、姓和笔数。",
        reference_sql="""
SELECT s.first_name, s.last_name, COUNT(*) AS cnt
FROM payment p
JOIN staff s ON s.staff_id = p.staff_id
JOIN rental r ON r.rental_id = p.rental_id
WHERE r.staff_id <> p.staff_id
GROUP BY s.staff_id, s.first_name, s.last_name
""",
        must_hit_columns=[
            "payment.staff_id",
            "rental.staff_id",
            "staff.first_name",
            "staff.last_name",
        ],
        tags=["难度:中等"],
        note="收款员工与办理员工是两个字段；没有租借关联的 5 笔付款自然排除。",
    ),
    EvalCase(
        id="H10S08",
        query="第一次来租碟之后 72 小时以内又租了第二次的客户有多少位？",
        reference_sql="""
WITH t AS (
    SELECT customer_id, rental_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY rental_date) AS rn
    FROM rental
)
SELECT COUNT(*) AS customer_cnt
FROM t a
JOIN t b ON b.customer_id = a.customer_id AND a.rn = 1 AND b.rn = 2
WHERE julianday(b.rental_date) - julianday(a.rental_date) <= 3
""",
        must_hit_columns=[
            "rental.rental_date",
            "rental.customer_id",
        ],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="以首次租借为基准看第二次的间隔，按精确时长 72 小时；首次租借时间每位客户唯一，72 小时附近无恰好落在边界的记录。",
    ),
    EvalCase(
        id="H10S09",
        query="两家店（用门店所在城市称呼）平均每张拷贝被租了多少次？保留两位小数。",
        reference_sql="""
SELECT ci.city,
       ROUND(1.0 * COUNT(r.rental_id) / COUNT(DISTINCT i.inventory_id), 2) AS rentals_per_copy
FROM store s
JOIN address a ON a.address_id = s.address_id
JOIN city ci ON ci.city_id = a.city_id
JOIN inventory i ON i.store_id = s.store_id
LEFT JOIN rental r ON r.inventory_id = i.inventory_id
GROUP BY s.store_id, ci.city
""",
        must_hit_columns=[
            "store.address_id",
            "address.city_id",
            "city.city",
            "inventory.store_id",
            "rental.inventory_id",
        ],
        tags=["难度:中等", "考点:多表连接", "考点:两层聚合"],
        note="门店没有名字，用地址所在城市称呼；分母是门店全部拷贝（含一张从没租出过的），出租按拷贝所在门店算。",
    ),
    EvalCase(
        id="H10S10",
        query="哪些客户把所有影片分类都租过一遍？列出名和姓。",
        reference_sql="""
SELECT c.first_name, c.last_name
FROM customer c
JOIN rental r ON r.customer_id = c.customer_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
GROUP BY c.customer_id, c.first_name, c.last_name
HAVING COUNT(DISTINCT fc.category_id) = (SELECT COUNT(*) FROM category)
""",
        must_hit_columns=[
            "customer.first_name",
            "customer.last_name",
            "film_category.category_id",
            "inventory.film_id",
        ],
        tags=["难度:难", "考点:否定集合"],
        note="「全都租过」：客户租过的分类去重数等于分类总数（16）；客户姓名无重复。",
    ),
    EvalCase(
        id="H10S11",
        query="按分类看，平均每部片子被租了多少次？只算店里至少有一张拷贝的片子，取最高的 3 个分类，保留两位小数。",
        reference_sql="""
WITH fr AS (
    SELECT i.film_id, COUNT(r.rental_id) AS n
    FROM inventory i
    LEFT JOIN rental r ON r.inventory_id = i.inventory_id
    GROUP BY i.film_id
)
SELECT cat.name, ROUND(AVG(fr.n), 2) AS avg_rentals
FROM fr
JOIN film_category fc ON fc.film_id = fr.film_id
JOIN category cat ON cat.category_id = fc.category_id
GROUP BY cat.category_id, cat.name
ORDER BY avg_rentals DESC
LIMIT 3
""",
        must_hit_columns=[
            "inventory.film_id",
            "rental.inventory_id",
            "film_category.category_id",
            "category.name",
        ],
        tags=["难度:难", "考点:两层聚合", "考点:多表连接"],
        note="先到影片粒度数出租次数，再按分类平均；题面排除没有拷贝的 42 部片子；第 3、4 名（18.22 与 17.39）不并列。",
    ),
    EvalCase(
        id="H10S12",
        query="两家店（用门店所在城市称呼）各自出租次数最多的前 3 个分类是哪些？出租算在租出去的拷贝所在的店。"
              "列出城市、分类和出租次数。",
        reference_sql="""
WITH t AS (
    SELECT s.store_id, ci.city, cat.name, COUNT(*) AS n
    FROM rental r
    JOIN inventory i ON i.inventory_id = r.inventory_id
    JOIN store s ON s.store_id = i.store_id
    JOIN address a ON a.address_id = s.address_id
    JOIN city ci ON ci.city_id = a.city_id
    JOIN film_category fc ON fc.film_id = i.film_id
    JOIN category cat ON cat.category_id = fc.category_id
    GROUP BY s.store_id, ci.city, cat.category_id, cat.name
), r AS (
    SELECT city, name, n, RANK() OVER (PARTITION BY store_id ORDER BY n DESC) AS rk
    FROM t
)
SELECT city, name, n
FROM r
WHERE rk <= 3
""",
        must_hit_columns=[
            "inventory.store_id",
            "city.city",
            "category.name",
            "rental.inventory_id",
        ],
        tags=["难度:难", "考点:多表连接", "考点:窗口排名"],
        note="门店按拷贝所在门店、用城市称呼；两家店第 3、4 名（568/557、598/580）都不并列。",
    ),
    EvalCase(
        id="H10S13",
        query="每个分级里带删减片段（Deleted Scenes）的片子各有多少部？",
        reference_sql="""
SELECT rating, COUNT(*) AS film_cnt
FROM film
WHERE special_features LIKE '%Deleted Scenes%'
GROUP BY rating
""",
        must_hit_columns=[
            "film.rating",
            "film.special_features",
        ],
        tags=["难度:简单"],
        note="附赠内容是逗号分隔的组合，要用包含匹配；分级为美国电影分级。",
    ),
    EvalCase(
        id="H10S14",
        query="哪些片子每次被租出去都是按时还回来的？还没还的那几次不算；按时指从借出到归还的实际时长没有超过这部片子规定的租期。"
              "列出片名。",
        reference_sql="""
SELECT f.title
FROM film f
WHERE EXISTS (
    SELECT 1
    FROM inventory i
    JOIN rental r ON r.inventory_id = i.inventory_id
    WHERE i.film_id = f.film_id AND r.return_date IS NOT NULL
)
  AND NOT EXISTS (
    SELECT 1
    FROM inventory i
    JOIN rental r ON r.inventory_id = i.inventory_id
    WHERE i.film_id = f.film_id
      AND r.return_date IS NOT NULL
      AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
)
""",
        must_hit_columns=[
            "film.title",
            "film.rental_duration",
            "rental.return_date",
            "rental.rental_date",
            "inventory.film_id",
        ],
        tags=["难度:难", "考点:否定集合", "考点:相对时间"],
        note="「全都按时」即已归还的租借里没有一次逾期；实际时长按归还时间减借出时间精确算，与规定租期（天）比较；"
             "把「正好等于租期」算作逾期也得到同样 6 部，边界不敏感。",
    ),
    EvalCase(
        id="H10S15",
        query="客户不少于 30 位的国家，人均消费各是多少？保留两位小数。",
        reference_sql="""
WITH cs AS (
    SELECT c.customer_id, co.country_id, co.country
    FROM customer c
    JOIN address a ON a.address_id = c.address_id
    JOIN city ci ON ci.city_id = a.city_id
    JOIN country co ON co.country_id = ci.country_id
), big AS (
    SELECT country_id FROM cs GROUP BY country_id HAVING COUNT(*) >= 30
)
SELECT cs.country, ROUND(SUM(p.amount) / COUNT(DISTINCT cs.customer_id), 2) AS avg_spend
FROM cs
JOIN payment p ON p.customer_id = cs.customer_id
WHERE cs.country_id IN (SELECT country_id FROM big)
GROUP BY cs.country_id, cs.country
""",
        must_hit_columns=[
            "country.country",
            "city.country_id",
            "address.city_id",
            "customer.address_id",
            "payment.amount",
        ],
        tags=["难度:难", "考点:两层聚合", "考点:多表连接"],
        note="先按国家数客户筛选（不少于 30 含 30，Mexico 恰好 30 位），再算国家消费总额除以客户数；所有客户都有付款。",
    ),
    EvalCase(
        id="H10S16",
        query="按影片分级看，实收金额比片子租借标价高的租借占多少？百分比保留两位小数。",
        reference_sql="""
SELECT f.rating,
       ROUND(100.0 * SUM(CASE WHEN p.amount > f.rental_rate THEN 1 ELSE 0 END) / COUNT(*), 2) AS over_pct
FROM payment p
JOIN rental r ON r.rental_id = p.rental_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
GROUP BY f.rating
""",
        must_hit_columns=[
            "payment.amount",
            "film.rental_rate",
            "film.rating",
        ],
        tags=["难度:中等", "考点:多表连接"],
        note="每笔租借恰好对应一笔付款，按租借计数；实收与标价逐笔比较，严格大于。",
    ),
    EvalCase(
        id="H10S17",
        query="每位客户第一次来租的片子属于哪个分类？按分类统计人数，列出人数最多的 3 个分类和人数。",
        reference_sql="""
WITH f AS (
    SELECT r.customer_id, r.inventory_id,
           ROW_NUMBER() OVER (PARTITION BY r.customer_id ORDER BY r.rental_date) AS rn
    FROM rental r
)
SELECT cat.name, COUNT(*) AS customer_cnt
FROM f
JOIN inventory i ON i.inventory_id = f.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
JOIN category cat ON cat.category_id = fc.category_id
WHERE f.rn = 1
GROUP BY cat.category_id, cat.name
ORDER BY customer_cnt DESC
LIMIT 3
""",
        must_hit_columns=[
            "rental.rental_date",
            "rental.customer_id",
            "inventory.film_id",
            "category.name",
        ],
        tags=["难度:难", "考点:相对时间", "考点:多表连接"],
        note="首次租借按租出时间取，每位客户首租时间唯一；第 3、4 名（44 与 43）不并列。",
    ),
    EvalCase(
        id="H10S18",
        query="不活跃的客户里，2006 年还来租过碟的有哪几位？列出名和姓。",
        reference_sql="""
SELECT c.first_name, c.last_name
FROM customer c
WHERE c.active = '0'
  AND EXISTS (
      SELECT 1 FROM rental r
      WHERE r.customer_id = c.customer_id AND r.rental_date >= '2006-01-01'
  )
""",
        must_hit_columns=[
            "customer.active",
            "customer.first_name",
            "customer.last_name",
            "rental.rental_date",
        ],
        tags=["难度:中等"],
        note="不活跃对应 active 为字符 '0'；按租出时间判断 2006 年（库里 2006 年只有 2 月）。",
    ),
    EvalCase(
        id="H10S19",
        query="哪位导演拍的片子总共被租的次数最多？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里只有演员和影片的关联，没有导演信息。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H10S20",
        query="两位店员每个月的工资分别是多少？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["陷阱题"],
        note="员工表只有姓名、门店、邮箱、账号等，没有工资或薪酬数据。",
        expect_unanswerable=True,
    ),
]
