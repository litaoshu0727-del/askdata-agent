"""
第八套留出评测集：更难的一套，题面可以靠口径约定。由独立出题人在未见过被测系统表现和已有题目的情况下编写。
ecommerce 30 题（H8E01–H8E30，陷阱 3），Chinook 20 题（H8C01–H8C20，陷阱 3）。

**已用过一次。**这套题于 33fc728 冻结并推送后第一次运行，三个版本一起跑，都用冻结时的
评测器判分，结果见 docs/实验记录.md「第八套留出集：口径约定和第七套之后的改动在陌生题上」：

    版本                                              ecommerce   Chinook   运行通过（90 + 60）
    ed67219  第七套封存时的状态                         27/30       20/20     80 + 59
    6102f50  再加时间差、全都是同一个 X、挂单规则、       27/30       20/20     82 + 60
             订单结构说明、IncompleteRead 重试
    33fc728  再加口径约定                               29/30       20/20     86 + 59
    33fc728  压测库（ecommerce_big）                    28/30       —         84

基线已经很高，版本之间逐题变化都不显著。口径约定的 13 道题 29 → 31 → 35 / 39 次，H8E01、H8E23
从 0/3 到 2/3，SQL 从只算已支付、已完成（或不加条件）改成了按付款时间算；订单结构说明让 H8E01 不再
拒答。涉及退款、支付表的 6 道题三个版本全对，挂单规则没有可帮的题。没有发现可证明没法判分的题，
冻结版就是最终版。

出题规范在第六套那份上改了两处（eval/blind_materials/出题规范_第八套.md）：一是允许题面用数据字典里
「口径约定」的说法、不写订单状态，ecommerce 至少 4 道这样出（标 考点:默认口径，实际 13 道）——
原规范要求题面交代状态，口径约定在新题上测不到；二是给两层聚合、相对时间、否定集合三类考点各补了
一个例子。材料里 ecommerce 的数据字典按当前元数据同步了四处描述（订单结构、口径约定、order_status、
pay_time、退款表），两个库本身与第三到七套相同。不读 README、docs/、eval/ 已有题目和 git 历史，
不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本完成，只输出题号和检查项；
出题人的回报里也不含题目内容。组装进仓库时只换了导入、加了这段文件头。

候选路径的验证 SQL 在 eval/cases_holdout8_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

第八套盲写评测题（holdout8）：ecommerce 30 题、chinook 20 题。"""

from eval.cases import EvalCase

# 店铺主营类目与商品类目两条路径等价（每家店的商品都属于它的主营类目）
_CAT_PATH = ["dim_shop.main_category_id", "dim_product.category_id"]

HOLDOUT8_ECOMMERCE_CASES = [
    EvalCase(
        id="H8E01",
        query="老板想看看美妆护肤、数码电器、食品生鲜这三个一级大类，各自的实付金额一共是多少？保留两位小数。",
        reference_sql="""
SELECT p.category_name, ROUND(SUM(o.pay_amount), 2) AS pay_amount
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN dim_category c ON c.category_id = s.main_category_id
JOIN dim_category p ON p.category_id = c.parent_category_id
WHERE o.pay_time IS NOT NULL
GROUP BY p.category_id, p.category_name
""",
        must_hit_columns=[
            "fact_order.pay_amount",
            "fact_order.pay_time",
            _CAT_PATH,
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:中等", "考点:两层聚合", "考点:默认口径"],
        note="订单级实付金额归到一级类目：一单只属于一个类目，经店铺主营类目或商品类目上卷到一级，商品路径须按订单去重；"
             "「实付金额」按口径约定只算 pay_time 非空的订单（含已完成、已退款），金额取订单 pay_amount（含运费）。",
    ),
    EvalCase(
        id="H8E02",
        query="5 月里，每家店铺最长连续多少天、每天都有人下单？列出店铺名和最长连续天数。",
        reference_sql="""
WITH d AS (
    SELECT DISTINCT shop_id, date(create_time) AS dt FROM fact_order
), g AS (
    SELECT shop_id, dt,
           julianday(dt) - ROW_NUMBER() OVER (PARTITION BY shop_id ORDER BY dt) AS grp
    FROM d
), s AS (
    SELECT shop_id, grp, COUNT(*) AS streak FROM g GROUP BY shop_id, grp
)
SELECT sh.shop_name, MAX(s.streak) AS max_streak
FROM s JOIN dim_shop sh ON sh.shop_id = s.shop_id
GROUP BY sh.shop_id, sh.shop_name
""",
        must_hit_columns=[
            ["fact_order.create_time", "dws_shop_daily.stat_date"],
            ["fact_order.shop_id", "dws_shop_daily.shop_id"],
            "dim_shop.shop_name",
        ],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名", "考点:默认口径"],
        note="「下单」按口径约定不限订单状态；按店铺取有订单的日期，用日期减行号找连续段，取最长段天数。"
             "店铺日汇总表每行即一个有订单的店铺日，用它算结果一致；若只算已付款订单，部分店铺的结果会变。",
    ),
    EvalCase(
        id="H8E03",
        query="下过两单及以上的用户，从第一单到第二单平均隔了多少天？不管订单是什么状态都算，按下单时刻精确算（不是只看日期），保留两位小数。",
        reference_sql="""
WITH t AS (
    SELECT user_id, create_time,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time) AS rn
    FROM fact_order
)
SELECT ROUND(AVG(julianday(b.create_time) - julianday(a.create_time)), 2) AS avg_gap_days
FROM t a
JOIN t b ON a.user_id = b.user_id AND a.rn = 1 AND b.rn = 2
""",
        must_hit_columns=["fact_order.user_id", "fact_order.create_time"],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="每个用户按下单时间排序取第 1、2 单，算两者时间差（小数天）再对用户求平均；全部状态都算，"
             "同一用户没有同一时刻的两单，排序无歧义。",
    ),
    EvalCase(
        id="H8E04",
        query="有没有那种在平台上逛过商品（浏览、加购、收藏都算）、却从来没付过钱买东西的用户？把他们的昵称列出来。",
        reference_sql="""
SELECT u.user_name
FROM dim_user u
WHERE EXISTS (SELECT 1 FROM fact_user_behavior b WHERE b.user_id = u.user_id)
  AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.user_id = u.user_id AND o.pay_time IS NOT NULL)
""",
        must_hit_columns=[
            "fact_user_behavior.user_id",
            ["fact_order.pay_time", "dws_user_summary.total_pay_amount"],
            "dim_user.user_name",
        ],
        tags=["难度:中等", "考点:否定集合", "考点:默认口径"],
        note="有行为记录、但没有任何 pay_time 非空订单的用户；「付过钱」按口径约定看 pay_time，"
             "只下过待支付/已取消订单的用户也算没付过钱。也可用用户汇总表累计实付为 0 判断，结果一致。",
    ),
    EvalCase(
        id="H8E05",
        query="把每天全平台的成交额加起来看，5 月里哪一天比前一天涨得最多？给出日期和涨了多少（保留两位小数）。",
        reference_sql="""
WITH d AS (
    SELECT stat_date, SUM(gmv) AS g FROM dws_shop_daily GROUP BY stat_date
), l AS (
    SELECT stat_date, g - LAG(g) OVER (ORDER BY stat_date) AS diff FROM d
)
SELECT stat_date, ROUND(diff, 2) AS increase
FROM l
WHERE diff IS NOT NULL
ORDER BY diff DESC
LIMIT 1
""",
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "考点:窗口排名", "考点:两层聚合"],
        note="【存疑】「成交额」按数据字典即 GMV（订单商品总金额），但明细表的行金额也叫「成交金额」，若按明细行金额汇总涨幅数值不同（日期相同）。先按天汇总全平台，再与前一天比较取涨幅最大的一天；"
             "5 月 30 天每天都有数据，前一天无缺口；第一名与第二名差距很大，无并列。",
    ),
    EvalCase(
        id="H8E06",
        query="5 月里，单日成交额超过 5 万元的天数达到 5 天及以上的店铺有哪些？列出店铺名和达标的天数。",
        reference_sql="""
SELECT s.shop_name, COUNT(*) AS days
FROM dws_shop_daily d
JOIN dim_shop s ON s.shop_id = d.shop_id
WHERE d.gmv > 50000
GROUP BY s.shop_id, s.shop_name
HAVING COUNT(*) >= 5
""",
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
            "dim_shop.shop_name",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="【存疑】「成交额」按数据字典取 GMV，明细行金额也叫「成交金额」，存在混用可能。先按店铺×天得到成交额（GMV），再数超过 5 万的天数并筛选 ≥5 天；用订单表按下单日期汇总 order_amount 结果相同。",
    ),
    EvalCase(
        id="H8E07",
        query="按退款原因看，退款金额正好等于这笔订单实付金额的退款，占该原因全部退款笔数的百分之多少？不管退款成没成功都算，保留两位小数。",
        reference_sql="""
SELECT r.refund_reason,
       ROUND(100.0 * SUM(CASE WHEN ABS(r.refund_amount - o.pay_amount) < 0.005 THEN 1 ELSE 0 END) / COUNT(*), 2) AS full_pct
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
GROUP BY r.refund_reason
""",
        must_hit_columns=["fact_refund.refund_reason", "fact_refund.refund_amount", "fact_order.pay_amount"],
        tags=["难度:中等"],
        note="逐笔比较退款金额与订单实付金额（含运费），相等的占比；有一部分退款恰好等于实付减运费，题面明确以实付金额为准。金额比较用 0.005 容差，结果与精确相等一致。",
    ),
    EvalCase(
        id="H8E08",
        query="不同会员等级的用户，各自付款金额最多的是哪种支付方式？列出会员等级和支付方式。",
        reference_sql="""
WITH t AS (
    SELECT u.member_level, p.pay_channel, SUM(p.pay_amount) AS amt
    FROM fact_payment p
    JOIN fact_order o ON o.order_id = p.order_id
    JOIN dim_user u ON u.user_id = o.user_id
    GROUP BY u.member_level, p.pay_channel
), r AS (
    SELECT t.*, ROW_NUMBER() OVER (PARTITION BY member_level ORDER BY amt DESC) AS rk FROM t
)
SELECT member_level, pay_channel FROM r WHERE rk = 1
""",
        must_hit_columns=[
            "dim_user.member_level",
            "fact_payment.pay_channel",
            ["fact_payment.pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:中等", "考点:窗口排名"],
        note="按会员等级×支付渠道汇总支付金额，每个等级取第一；四个等级的第一、二名都不并列（按笔数会有并列，所以题面明确按金额）。"
             "支付流水金额与订单实付金额逐单相等。",
    ),
    EvalCase(
        id="H8E09",
        query="相邻两次下单之间隔得最久的前 3 位用户是谁？列出昵称和这段最长间隔的天数，按下单时刻精确算（不是只看日期），保留两位小数。",
        reference_sql="""
WITH t AS (
    SELECT user_id,
           julianday(create_time) - julianday(LAG(create_time) OVER (PARTITION BY user_id ORDER BY create_time)) AS gap
    FROM fact_order
), m AS (
    SELECT user_id, MAX(gap) AS max_gap FROM t WHERE gap IS NOT NULL GROUP BY user_id
)
SELECT u.user_name, ROUND(m.max_gap, 2) AS max_gap_days
FROM m JOIN dim_user u ON u.user_id = m.user_id
ORDER BY m.max_gap DESC
LIMIT 3
""",
        must_hit_columns=["fact_order.user_id", "fact_order.create_time", "dim_user.user_name"],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名", "考点:默认口径"],
        note="「下单」按口径约定不限订单状态；每位用户按下单时间与上一单比较求最长间隔（小数天），再取全体前 3。"
             "第 3、4 名为 22.91 与 20.99 天，无并列。",
    ),
    EvalCase(
        id="H8E10",
        query="5 月 10 日到 20 日（两头都算），下单笔数最多的前 4 家店铺是哪几家？列出店铺名和笔数。",
        reference_sql="""
SELECT s.shop_name, COUNT(*) AS order_cnt
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE date(o.create_time) BETWEEN '2024-05-10' AND '2024-05-20'
GROUP BY s.shop_id, s.shop_name
ORDER BY order_cnt DESC
LIMIT 4
""",
        must_hit_columns=[
            ["fact_order.create_time", "dws_shop_daily.stat_date"],
            ["fact_order.order_id", "dws_shop_daily.order_count"],
            "dim_shop.shop_name",
        ],
        tags=["难度:简单", "考点:默认口径"],
        note="「下单笔数」按口径约定不加状态条件，算全部订单；按下单日期 5/10–5/20 闭区间。第 4 名 23 单、第 5 名 21 单，无并列。",
    ),
    EvalCase(
        id="H8E11",
        query="各省份消费过的用户，人均消费多少钱？没消费过的人不算进人数，保留两位小数。",
        reference_sql="""
SELECT u.province, ROUND(SUM(o.pay_amount) / COUNT(DISTINCT o.user_id), 2) AS avg_spend
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.pay_time IS NOT NULL
GROUP BY u.province
""",
        must_hit_columns=[
            "dim_user.province",
            ["fact_order.pay_amount", "dws_user_summary.total_pay_amount"],
        ],
        tags=["难度:中等", "考点:两层聚合", "考点:默认口径"],
        note="「消费」按口径约定只算已付款订单的实付金额；先得每位用户消费额，再按用户所在省份对消费过的用户求平均。"
             "用用户汇总表累计实付金额（>0 的用户）求平均，结果一致。",
    ),
    EvalCase(
        id="H8E12",
        query="哪些二级类目从来没有出现过「七天无理由」的退款申请？不管退款最后成没成功，都算申请过。",
        reference_sql="""
SELECT c.category_name
FROM dim_category c
WHERE c.category_level = 2
  AND NOT EXISTS (
      SELECT 1
      FROM fact_refund r
      JOIN fact_order o ON o.order_id = r.order_id
      JOIN dim_shop s ON s.shop_id = o.shop_id
      WHERE s.main_category_id = c.category_id AND r.refund_reason = '七天无理由'
  )
""",
        must_hit_columns=[
            "fact_refund.refund_reason",
            _CAT_PATH,
            "dim_category.category_name",
            "dim_category.category_level",
        ],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="在全部 9 个二级类目中找没有任何「七天无理由」退款记录的类目，退款按订单所属类目归属（店铺主营类目或商品类目，两条路径结果一致）；"
             "不限退款状态。",
    ),
    EvalCase(
        id="H8E13",
        query="5 月 1 日到 7 日，全平台每天的成交额从 1 号开始一路累计下来是多少？按日期从早到晚列出日期和累计成交额，保留两位小数。",
        reference_sql="""
SELECT stat_date,
       ROUND(SUM(SUM(gmv)) OVER (ORDER BY stat_date), 2) AS cum_gmv
FROM dws_shop_daily
WHERE stat_date BETWEEN '2024-05-01' AND '2024-05-07'
GROUP BY stat_date
ORDER BY stat_date
""",
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:中等", "考点:窗口排名"],
        note="【存疑】「成交额」按数据字典取 GMV，明细行金额也叫「成交金额」，存在混用可能。先按天汇总全平台，再从 5/1 起做累计和，共 7 行按日期升序。用订单表按下单日期汇总 order_amount 结果一致。",
        ordered=True,
    ),
    EvalCase(
        id="H8E14",
        query="住在上海的用户，在开在深圳的店铺里买过哪些品牌的商品？",
        reference_sql="""
SELECT DISTINCT p.brand
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN fact_order_item i ON i.order_id = o.order_id
JOIN dim_product p ON p.product_id = i.product_id
WHERE u.city = '上海' AND s.city = '深圳' AND o.pay_time IS NOT NULL
""",
        must_hit_columns=[
            "dim_user.city",
            "dim_shop.city",
            "fact_order.pay_time",
            "fact_order_item.product_id",
            "dim_product.brand",
        ],
        tags=["难度:难", "考点:多表连接", "考点:默认口径"],
        note="用户城市与店铺城市是两个不同字段；「买过」按口径约定只算 pay_time 非空的订单（若误写成 order_status='已支付' 只剩 2 个品牌）。"
             "商品所属店铺与订单店铺一致，店铺城市用订单店铺或商品店铺结果相同。",
    ),
    EvalCase(
        id="H8E15",
        query="5 月 25 日到 31 日（两头都算）这几天里提交的退款申请，每家店铺一共申请退多少钱？不管退款成没成功都算，列出店铺名和金额，保留两位小数。",
        reference_sql="""
SELECT s.shop_name, ROUND(SUM(r.refund_amount), 2) AS refund_amount
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE date(r.apply_time) BETWEEN '2024-05-25' AND '2024-05-31'
GROUP BY s.shop_id, s.shop_name
""",
        must_hit_columns=[
            "fact_refund.apply_time",
            "fact_refund.refund_amount",
            "fact_order.shop_id",
            "dim_shop.shop_name",
        ],
        tags=["难度:中等"],
        note="按退款申请时间筛选，不能用店铺日汇总表的退款金额（那是按订单下单日期归属的）；不限退款状态，按申请日期闭区间。",
    ),
    EvalCase(
        id="H8E16",
        query="收藏过商品、但收藏的那些商品一件都没买过的用户，按会员等级各有多少人？",
        reference_sql="""
SELECT u.member_level, COUNT(*) AS user_cnt
FROM dim_user u
WHERE EXISTS (
    SELECT 1 FROM fact_user_behavior b WHERE b.user_id = u.user_id AND b.behavior_type = '收藏'
)
AND NOT EXISTS (
    SELECT 1
    FROM fact_user_behavior b
    JOIN fact_order_item i ON i.product_id = b.product_id
    JOIN fact_order o ON o.order_id = i.order_id AND o.user_id = b.user_id
    WHERE b.user_id = u.user_id AND b.behavior_type = '收藏' AND o.pay_time IS NOT NULL
)
GROUP BY u.member_level
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.product_id",
            "fact_order_item.product_id",
            "fact_order.pay_time",
            "dim_user.member_level",
        ],
        tags=["难度:中等", "考点:否定集合", "考点:多表连接", "考点:默认口径"],
        note="对每位收藏过商品的用户，检查他收藏的商品中有没有被他本人在已付款订单里买过；「买过」按口径约定只算 pay_time 非空订单"
             "（不加付款条件时四个等级的人数都会变少）。不限收藏与购买的先后。",
    ),
    EvalCase(
        id="H8E17",
        query="只看已完成的订单，每个一级类目里销量最高的两个品牌是谁？列出一级类目、品牌和销量。",
        reference_sql="""
WITH t AS (
    SELECT pc.category_name AS l1, p.brand, SUM(i.quantity) AS qty
    FROM fact_order_item i
    JOIN fact_order o ON o.order_id = i.order_id
    JOIN dim_product p ON p.product_id = i.product_id
    JOIN dim_category c ON c.category_id = p.category_id
    JOIN dim_category pc ON pc.category_id = c.parent_category_id
    WHERE o.order_status = '已完成'
    GROUP BY pc.category_id, pc.category_name, p.brand
), r AS (
    SELECT t.*, ROW_NUMBER() OVER (PARTITION BY l1 ORDER BY qty DESC) AS rk FROM t
)
SELECT l1, brand, qty FROM r WHERE rk <= 2
""",
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.brand",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接"],
        note="销量按数据字典是件数（quantity 求和）；品牌都只属于一个一级类目；三个一级类目第 2、3 名分别为 122/92、118/115、70/44，无并列。",
    ),
    EvalCase(
        id="H8E18",
        query="按会员等级看，客单价高于本等级用户客单价平均值的用户各有多少人？没下过单的用户不算。",
        reference_sql="""
WITH t AS (
    SELECT u.member_level, s.avg_order_amount AS a
    FROM dws_user_summary s
    JOIN dim_user u ON u.user_id = s.user_id
    WHERE s.total_order_count > 0
)
SELECT member_level, COUNT(*) AS user_cnt
FROM t
WHERE a > (SELECT AVG(t2.a) FROM t t2 WHERE t2.member_level = t.member_level)
GROUP BY member_level
""",
        must_hit_columns=[
            "dim_user.member_level",
            ["dws_user_summary.avg_order_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:难", "考点:两层聚合"],
        note="【存疑】「本等级平均」若理解为等级整体客单价（等级总金额/总订单数），普通会员、银卡会员的人数会变；题面已写明是用户客单价的平均值。客单价取用户汇总表的平均订单金额；先算每个等级内用户客单价的均值，再数高于均值的人数。"
             "从订单表按用户求实付金额平均（全部状态）可复现同一结果。",
    ),
    EvalCase(
        id="H8E19",
        query="钻石会员在主营家用电器的店铺里付的钱，按支付方式分各是多少？保留两位小数。",
        reference_sql="""
SELECT p.pay_channel, ROUND(SUM(p.pay_amount), 2) AS amt
FROM fact_payment p
JOIN fact_order o ON o.order_id = p.order_id
JOIN dim_user u ON u.user_id = o.user_id
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN dim_category c ON c.category_id = s.main_category_id
WHERE u.member_level = '钻石会员' AND c.category_name = '家用电器'
GROUP BY p.pay_channel
""",
        must_hit_columns=[
            "dim_user.member_level",
            "fact_payment.pay_channel",
            "fact_payment.pay_amount",
            "dim_shop.main_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:中等", "考点:多表连接"],
        note="支付流水→订单→用户/店铺→类目；只有支付流水的订单才有支付方式，流水金额与订单实付逐单相等。结果 3 行（没有花呗分期）。",
    ),
    EvalCase(
        id="H8E20",
        query="按下单日期把 5 月分成上半月（1–15 日）和下半月（16–30 日），下半月实付金额比上半月涨幅最大的前 3 家店铺是哪几家？列出店铺名和涨幅百分比（保留两位小数）。",
        reference_sql="""
WITH t AS (
    SELECT o.shop_id,
           SUM(CASE WHEN date(o.create_time) BETWEEN '2024-05-01' AND '2024-05-15' THEN o.pay_amount ELSE 0 END) AS h1,
           SUM(CASE WHEN date(o.create_time) BETWEEN '2024-05-16' AND '2024-05-30' THEN o.pay_amount ELSE 0 END) AS h2
    FROM fact_order o
    WHERE o.pay_time IS NOT NULL
    GROUP BY o.shop_id
)
SELECT s.shop_name, ROUND(100.0 * (t.h2 - t.h1) / t.h1, 2) AS growth_pct
FROM t JOIN dim_shop s ON s.shop_id = t.shop_id
ORDER BY (t.h2 - t.h1) / t.h1 DESC
LIMIT 3
""",
        must_hit_columns=[
            ["fact_order.pay_amount", "dws_shop_daily.pay_amount"],
            ["fact_order.create_time", "dws_shop_daily.stat_date"],
            "dim_shop.shop_name",
        ],
        tags=["难度:难", "考点:相对时间", "考点:两层聚合", "考点:默认口径"],
        note="「实付金额」按口径约定只算已付款订单；按下单日期切两段分别汇总再算环比涨幅，取前 3。第 3、4 名为 42.82% 与 39.38%，无并列。"
             "用店铺日汇总表的实付金额按统计日期切分结果一致。",
    ),
    EvalCase(
        id="H8E21",
        query="付过款的订单至少有两单、而且这些付了款的订单全都是在同一家店铺下的用户有哪些？列出昵称。",
        reference_sql="""
SELECT u.user_name
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.pay_time IS NOT NULL
GROUP BY o.user_id, u.user_name
HAVING COUNT(*) >= 2 AND COUNT(DISTINCT o.shop_id) = 1
""",
        must_hit_columns=["fact_order.pay_time", "fact_order.shop_id", "dim_user.user_name"],
        tags=["难度:难", "考点:否定集合", "考点:默认口径"],
        note="「付过款」按口径约定看 pay_time 非空（含已完成、已退款）；只看付过款的订单，至少 2 单且店铺唯一。",
    ),
    EvalCase(
        id="H8E22",
        query="退款原因是「七天无理由」的退款里，申请退款时离下单已经超过 7 天的有几笔？从下单时刻到申请时刻按分钟精确算。",
        reference_sql="""
SELECT COUNT(*) AS refund_cnt
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
WHERE r.refund_reason = '七天无理由'
  AND r.apply_time > datetime(o.create_time, '+7 days')
""",
        must_hit_columns=["fact_refund.refund_reason", "fact_refund.apply_time", "fact_order.create_time"],
        tags=["难度:中等", "考点:相对时间"],
        note="比较退款申请时刻与订单下单时刻，超过 7×24 小时才算；有两笔约 7 天零半小时、7 天零一小时，若只按日期差算会少算，题面已写明按时刻精确算。",
    ),
    EvalCase(
        id="H8E23",
        query="现在已经下架的商品，5 月里按品牌分，各被买走了多少件？",
        reference_sql="""
SELECT p.brand, SUM(i.quantity) AS qty
FROM fact_order_item i
JOIN fact_order o ON o.order_id = i.order_id
JOIN dim_product p ON p.product_id = i.product_id
WHERE p.shelf_status = '已下架' AND o.pay_time IS NOT NULL
GROUP BY p.brand
""",
        must_hit_columns=[
            "dim_product.shelf_status",
            "dim_product.brand",
            "fact_order_item.quantity",
            "fact_order.pay_time",
        ],
        tags=["难度:中等", "考点:默认口径"],
        note="「买」按口径约定只算已付款订单（pay_time 非空）；件数按 quantity 求和；上架状态取商品表当前状态。",
    ),
    EvalCase(
        id="H8E24",
        query="现在没在正常营业的店铺，5 月各接了多少单？列出店铺名、营业状态和下单笔数。",
        reference_sql="""
SELECT s.shop_name, s.shop_status, COUNT(o.order_id) AS order_cnt
FROM dim_shop s
JOIN fact_order o ON o.shop_id = s.shop_id
WHERE s.shop_status <> '正常营业'
GROUP BY s.shop_id, s.shop_name, s.shop_status
""",
        must_hit_columns=[
            "dim_shop.shop_status",
            "dim_shop.shop_name",
            ["fact_order.order_id", "dws_shop_daily.order_count"],
        ],
        tags=["难度:简单", "考点:默认口径"],
        note="「下单笔数」按口径约定算全部订单；不在正常营业的是休假中、已关店各一家。用店铺日汇总表订单量求和结果一致。",
    ),
    EvalCase(
        id="H8E25",
        query="按注册年份看，各年注册的用户平均每人下了几单？没下过单的用户也算进人数，保留两位小数。",
        reference_sql="""
SELECT strftime('%Y', u.register_time) AS reg_year,
       ROUND(1.0 * COUNT(o.order_id) / COUNT(DISTINCT u.user_id), 2) AS avg_orders
FROM dim_user u
LEFT JOIN fact_order o ON o.user_id = u.user_id
GROUP BY reg_year
""",
        must_hit_columns=[
            "dim_user.register_time",
            ["fact_order.order_id", "dws_user_summary.total_order_count"],
        ],
        tags=["难度:中等", "考点:两层聚合", "考点:默认口径"],
        note="「下单」按口径约定算全部订单；按用户注册日期的年份分组，人数含没下过单的用户。"
             "用用户汇总表累计下单笔数求平均结果一致。",
    ),
    EvalCase(
        id="H8E26",
        query="只看浏览行为，每个二级类目的商品平均每次浏览停留多少秒？保留一位小数。",
        reference_sql="""
SELECT c.category_name, ROUND(AVG(b.stay_seconds), 1) AS avg_stay
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
JOIN dim_category c ON c.category_id = p.category_id
WHERE b.behavior_type = '浏览'
GROUP BY c.category_id, c.category_name
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.stay_seconds",
            "dim_product.category_id",
            "dim_category.category_name",
        ],
        tags=["难度:简单"],
        note="行为表按商品关联到二级类目，对浏览记录的停留秒数取平均。",
    ),
    EvalCase(
        id="H8E27",
        query="按下单日期算，每家店铺实付金额最高的是哪一天？列出店铺名、日期和那天的实付金额（保留两位小数）。",
        reference_sql="""
WITH r AS (
    SELECT shop_id, stat_date, pay_amount,
           ROW_NUMBER() OVER (PARTITION BY shop_id ORDER BY pay_amount DESC) AS rk
    FROM dws_shop_daily
)
SELECT s.shop_name, r.stat_date, ROUND(r.pay_amount, 2) AS pay_amount
FROM r JOIN dim_shop s ON s.shop_id = r.shop_id
WHERE r.rk = 1
""",
        must_hit_columns=[
            ["dws_shop_daily.pay_amount", "fact_order.pay_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
            "dim_shop.shop_name",
        ],
        tags=["难度:中等", "考点:窗口排名"],
        note="店铺日汇总表按下单日期归属、实付金额只算已付款订单；每店取实付最高的一天，15 家店第一、二名均不并列。"
             "用订单表按下单日期汇总已付款订单的实付金额结果一致。",
    ),
    EvalCase(
        id="H8E28",
        query="想看看大家给各家店铺打的分：5 月每家店铺的好评率是多少？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="库里没有评价、评分或好评相关的表和字段，无法回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H8E29",
        query="用苹果手机下单的用户和用安卓手机下单的用户，各有多少人？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="订单只记录下单渠道（APP、小程序等），没有设备类型、操作系统或手机品牌信息，无法回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H8E30",
        query="用户在平台上搜得最多的十个关键词是什么？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="行为表只记录浏览、加购、收藏，没有搜索日志或搜索词字段，无法回答。",
        expect_unanswerable=True,
    ),
]


HOLDOUT8_CHINOOK_CASES = [
    EvalCase(
        id="H8C01",
        query="美国（USA）客户买走的曲目里，各种媒体格式分别占卖出份数的百分之多少？列出媒体格式和百分比，保留两位小数。",
        reference_sql="""
WITH t AS (
    SELECT m.Name AS media, SUM(il.Quantity) AS units
    FROM Customer c
    JOIN Invoice i ON i.CustomerId = c.CustomerId
    JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
    JOIN Track t ON t.TrackId = il.TrackId
    JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
    WHERE c.Country = 'USA'
    GROUP BY m.MediaTypeId, m.Name
)
SELECT media, ROUND(100.0 * units / (SELECT SUM(units) FROM t), 2) AS pct FROM t
""",
        must_hit_columns=[
            ["Customer.Country", "Invoice.BillingCountry"],
            "InvoiceLine.TrackId",
            "Track.MediaTypeId",
            "MediaType.Name",
        ],
        tags=["难度:难", "考点:两层聚合", "考点:多表连接"],
        note="先按媒体格式汇总美国客户的卖出份数，再除以美国客户总份数；份数按明细行（数量都是 1）。"
             "开票国家与客户国家逐张一致，两个国家字段结果相同；只列美国客户买过的 4 种格式。",
    ),
    EvalCase(
        id="H8C02",
        query="2022 到 2025 年，每年的销售额比上一年增长了百分之几？按年份从早到晚列出年份和增长率，百分比保留两位小数，下降就写成负数。",
        reference_sql="""
WITH y AS (
    SELECT strftime('%Y', InvoiceDate) AS yr, SUM(Total) AS s FROM Invoice GROUP BY yr
), g AS (
    SELECT yr, ROUND(100.0 * (s - LAG(s) OVER (ORDER BY yr)) / LAG(s) OVER (ORDER BY yr), 2) AS growth_pct
    FROM y
)
SELECT yr, growth_pct FROM g WHERE yr BETWEEN '2022' AND '2025' ORDER BY yr
""",
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:中等", "考点:窗口排名"],
        note="按开票年份汇总销售额，同比上一年（2022 与 2021 比），增长率以百分数表示；4 行按年份升序。",
        ordered=True,
    ),
    EvalCase(
        id="H8C03",
        query="客户从第一次购买到第二次购买，平均隔了多少天？算所有客户的平均值，保留两位小数。",
        reference_sql="""
WITH t AS (
    SELECT CustomerId, InvoiceDate,
           ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate) AS rn
    FROM Invoice
)
SELECT ROUND(AVG(julianday(b.InvoiceDate) - julianday(a.InvoiceDate)), 2) AS avg_gap_days
FROM t a JOIN t b ON a.CustomerId = b.CustomerId AND a.rn = 1 AND b.rn = 2
""",
        must_hit_columns=["Invoice.CustomerId", "Invoice.InvoiceDate"],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="每位客户按开票日期取第 1、2 张发票求间隔天数，再对客户求平均；59 位客户都至少有 2 张发票，同一客户没有同日两张发票。"
             "开票时间都是零点，按日期或按时刻算结果相同。",
    ),
    EvalCase(
        id="H8C04",
        query="加拿大（Canada）的客户从来没买过哪些流派的曲目？",
        reference_sql="""
SELECT g.Name
FROM Genre g
WHERE NOT EXISTS (
    SELECT 1
    FROM Track t
    JOIN InvoiceLine il ON il.TrackId = t.TrackId
    JOIN Invoice i ON i.InvoiceId = il.InvoiceId
    JOIN Customer c ON c.CustomerId = i.CustomerId
    WHERE t.GenreId = g.GenreId AND c.Country = 'Canada'
)
""",
        must_hit_columns=[
            "Genre.Name",
            "Track.GenreId",
            "InvoiceLine.TrackId",
            ["Customer.Country", "Invoice.BillingCountry"],
        ],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="在全部 25 个流派中排除加拿大客户买过的流派，包括全库都没人买过的流派；开票国家与客户国家一致，两条路径结果相同。",
    ),
    EvalCase(
        id="H8C05",
        query="名下专辑不少于 3 张的艺术家里，平均每张专辑卖出去多少份？取最高的前 3 位，列出艺术家和平均份数（保留两位小数）。",
        reference_sql="""
WITH s AS (
    SELECT al.ArtistId, al.AlbumId, COUNT(il.InvoiceLineId) AS units
    FROM Album al
    JOIN Track t ON t.AlbumId = al.AlbumId
    LEFT JOIN InvoiceLine il ON il.TrackId = t.TrackId
    GROUP BY al.ArtistId, al.AlbumId
), a AS (
    SELECT ArtistId, 1.0 * SUM(units) / COUNT(*) AS avg_units
    FROM s GROUP BY ArtistId HAVING COUNT(*) >= 3
)
SELECT ar.Name, ROUND(a.avg_units, 2) AS avg_units
FROM a JOIN Artist ar ON ar.ArtistId = a.ArtistId
ORDER BY a.avg_units DESC
LIMIT 3
""",
        must_hit_columns=["Album.ArtistId", "Track.AlbumId", "InvoiceLine.TrackId", "Artist.Name"],
        tags=["难度:难", "考点:两层聚合", "考点:多表连接"],
        note="先按专辑数卖出份数，再按艺术家对专辑求平均，只看专辑数 ≥3 的艺术家；第 3、4 名为 12.33 与 12.00，无并列。"
             "没卖出过的专辑按 0 计入或不计入，前 3 名结果都相同。",
    ),
    EvalCase(
        id="H8C06",
        query="看每位客户第一次购买时买的曲目：按流派数一数，有多少位客户的第一次购买里包含这个流派？一单里有几个流派就分别算，列出流派和客户数。",
        reference_sql="""
WITH f AS (
    SELECT CustomerId, InvoiceId
    FROM (
        SELECT CustomerId, InvoiceId,
               ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate) AS rn
        FROM Invoice
    ) WHERE rn = 1
)
SELECT g.Name, COUNT(DISTINCT f.CustomerId) AS customer_cnt
FROM f
JOIN InvoiceLine il ON il.InvoiceId = f.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
GROUP BY g.GenreId, g.Name
""",
        must_hit_columns=[
            "Invoice.CustomerId",
            "Invoice.InvoiceDate",
            "InvoiceLine.InvoiceId",
            "Track.GenreId",
            "Genre.Name",
        ],
        tags=["难度:难", "考点:相对时间", "考点:多表连接"],
        note="每位客户按开票日期取第一张发票（同一客户无同日两张），再看这张发票里的曲目流派，按流派数去重客户；只列出现过的流派。",
    ),
    EvalCase(
        id="H8C07",
        query="每位销售支持员工从入职那天起，到他负责的客户开出第一张发票，中间隔了多少天？列出员工的名、姓和天数。",
        reference_sql="""
SELECT e.FirstName, e.LastName,
       CAST(julianday(MIN(i.InvoiceDate)) - julianday(e.HireDate) AS INTEGER) AS days
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
JOIN Invoice i ON i.CustomerId = c.CustomerId
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "Employee.HireDate",
            "Customer.SupportRepId",
            "Invoice.InvoiceDate",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:中等", "考点:相对时间"],
        note="员工入职日期与其名下客户最早开票日期之差；两个日期都是零点，天数为整数。只有销售支持员工名下有客户。",
    ),
    EvalCase(
        id="H8C08",
        query="名字以 Classical 开头的那几个歌单，每个歌单里的曲目来自几位不同的艺术家？列出歌单名和艺术家数。",
        reference_sql="""
SELECT p.Name, COUNT(DISTINCT al.ArtistId) AS artist_cnt
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t ON t.TrackId = pt.TrackId
JOIN Album al ON al.AlbumId = t.AlbumId
WHERE p.Name LIKE 'Classical%'
GROUP BY p.PlaylistId, p.Name
""",
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Track.AlbumId", "Album.ArtistId"],
        tags=["难度:中等", "考点:多表连接"],
        note="歌单→收录关系→曲目→专辑，按歌单数不同艺术家；以 Classical 开头的 4 个歌单名称各不相同。",
    ),
    EvalCase(
        id="H8C09",
        query="有多少首曲目，作曲者那一栏写的和它所属的艺术家名字一模一样？",
        reference_sql="""
SELECT COUNT(*) AS track_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
WHERE t.Composer = ar.Name
""",
        must_hit_columns=["Track.Composer", "Track.AlbumId", "Album.ArtistId", "Artist.Name"],
        tags=["难度:中等"],
        note="作曲者是自由文本、不是艺术家外键，需经专辑找到艺术家后做完全相等比较；作曲者为空的曲目不相等，不计入。",
    ),
    EvalCase(
        id="H8C10",
        query="曲目不少于 30 首的流派里，平均每首曲目被几个歌单收录？取最高的前 3 个流派，列出流派和平均收录歌单数（保留两位小数）。",
        reference_sql="""
WITH pc AS (
    SELECT t.TrackId, t.GenreId, COUNT(pt.PlaylistId) AS n
    FROM Track t
    LEFT JOIN PlaylistTrack pt ON pt.TrackId = t.TrackId
    GROUP BY t.TrackId, t.GenreId
), g AS (
    SELECT GenreId, AVG(n) AS avg_n FROM pc GROUP BY GenreId HAVING COUNT(*) >= 30
)
SELECT ge.Name, ROUND(g.avg_n, 2) AS avg_playlists
FROM g JOIN Genre ge ON ge.GenreId = g.GenreId
ORDER BY g.avg_n DESC
LIMIT 3
""",
        must_hit_columns=["PlaylistTrack.TrackId", "Track.GenreId", "Genre.Name"],
        tags=["难度:难", "考点:两层聚合"],
        note="先按曲目数被收录的歌单数（同名歌单算不同歌单），再按流派求平均并筛选曲目数 ≥30；每首曲目都至少在一个歌单里。"
             "第 3、4 名为 2.58 与 2.51，无并列。",
    ),
    EvalCase(
        id="H8C11",
        query="作曲者署名里出现了 Bono 的曲目，一共卖了多少钱？保留两位小数。",
        reference_sql="""
SELECT ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS sales
FROM InvoiceLine il
JOIN Track t ON t.TrackId = il.TrackId
WHERE t.Composer LIKE '%Bono%'
""",
        must_hit_columns=["Track.Composer", "InvoiceLine.TrackId", ["InvoiceLine.UnitPrice", "Track.UnitPrice"]],
        tags=["难度:中等"],
        note="作曲者为多人自由文本，按包含 Bono 匹配（库里所有含该串的署名都确为 Bono）；金额按明细行成交价，与目录标价逐行相等。",
    ),
    EvalCase(
        id="H8C12",
        query="2023 年每个月的销售额，以及从 1 月累计到当月的销售额各是多少？按月份顺序列出（月份写成 01、02 这样的两位数），金额保留两位小数。",
        reference_sql="""
SELECT strftime('%m', InvoiceDate) AS mon,
       ROUND(SUM(Total), 2) AS sales,
       ROUND(SUM(SUM(Total)) OVER (ORDER BY strftime('%m', InvoiceDate)), 2) AS cum_sales
FROM Invoice
WHERE InvoiceDate >= '2023-01-01' AND InvoiceDate < '2024-01-01'
GROUP BY mon
ORDER BY mon
""",
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:中等", "考点:窗口排名"],
        note="按开票月份汇总 2023 年销售额并做年内累计，12 个月都有发票，按月份升序。",
        ordered=True,
    ),
    EvalCase(
        id="H8C13",
        query="有直接下属的员工，每人手下直接带着几个人？列出名、姓和人数。",
        reference_sql="""
SELECT m.FirstName, m.LastName, COUNT(e.EmployeeId) AS direct_reports
FROM Employee m
JOIN Employee e ON e.ReportsTo = m.EmployeeId
GROUP BY m.EmployeeId, m.FirstName, m.LastName
""",
        must_hit_columns=["Employee.ReportsTo", "Employee.FirstName", "Employee.LastName"],
        tags=["难度:简单"],
        note="员工表自连接，只数直接汇报关系（不含下属的下属）。",
    ),
    EvalCase(
        id="H8C14",
        query="有公司名的客户，按公司看各消费了多少钱？列出公司名和金额，金额保留两位小数。",
        reference_sql="""
SELECT c.Company, ROUND(SUM(i.Total), 2) AS spend
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
WHERE c.Company IS NOT NULL
GROUP BY c.Company
""",
        must_hit_columns=["Customer.Company", "Invoice.Total"],
        tags=["难度:简单"],
        note="只看公司字段非空的 10 位客户，按公司汇总发票金额；10 家公司各不相同。",
    ),
    EvalCase(
        id="H8C15",
        query="客户不少于 3 位的国家里，平均每位客户消费了多少钱？列出国家和人均消费，保留两位小数。",
        reference_sql="""
SELECT c.Country, ROUND(SUM(i.Total) / COUNT(DISTINCT c.CustomerId), 2) AS avg_spend
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
GROUP BY c.Country
HAVING COUNT(DISTINCT c.CustomerId) >= 3
""",
        must_hit_columns=[
            ["Customer.Country", "Invoice.BillingCountry"],
            "Invoice.Total",
            "Invoice.CustomerId",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按客户算消费总额，再按国家对客户求平均并筛选客户数 ≥3 的国家；所有客户都有发票，且开票国家与客户国家逐张一致，两种国家字段结果相同。",
    ),
    EvalCase(
        id="H8C16",
        query="每位销售支持员工负责的客户，2024 年一共消费的钱比 2023 年多了多少？少了就写负数，列出员工的名、姓和变化金额，保留两位小数。",
        reference_sql="""
SELECT e.FirstName, e.LastName,
       ROUND(SUM(CASE WHEN i.InvoiceDate >= '2024-01-01' AND i.InvoiceDate < '2025-01-01' THEN i.Total ELSE 0 END)
           - SUM(CASE WHEN i.InvoiceDate >= '2023-01-01' AND i.InvoiceDate < '2024-01-01' THEN i.Total ELSE 0 END), 2) AS change_amt
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
JOIN Invoice i ON i.CustomerId = c.CustomerId
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "Customer.SupportRepId",
            "Invoice.InvoiceDate",
            "Invoice.Total",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:中等", "考点:相对时间"],
        note="按开票年份分别汇总每位员工名下客户的消费额，2024 年减 2023 年；三位销售支持员工结果有正有负。",
    ),
    EvalCase(
        id="H8C17",
        query="买过视频格式（Protected MPEG-4 video file）曲目的客户，按负责他们的销售支持员工来分，每位员工名下各有几位？列出员工的名、姓和客户数。",
        reference_sql="""
SELECT e.FirstName, e.LastName, COUNT(DISTINCT c.CustomerId) AS customer_cnt
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
JOIN Invoice i ON i.CustomerId = c.CustomerId
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
WHERE m.Name = 'Protected MPEG-4 video file'
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "MediaType.Name",
            "Track.MediaTypeId",
            "InvoiceLine.TrackId",
            "Customer.SupportRepId",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="六表连接，按员工数去重客户（同一客户买过多首视频只算一次）。",
    ),
    EvalCase(
        id="H8C18",
        query="哪一年发行的专辑最多？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="专辑表只有名称和艺术家，没有发行日期或年份；开票日期是销售时间，不是发行时间，无法回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H8C19",
        query="销售支持的几位员工，每人每月的工资加提成是多少？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="员工表只有姓名、职位、上下级、日期和联系方式，没有薪资、提成字段，无法回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H8C20",
        query="2024 年开出的发票里，用信用卡付款的占几成？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="发票表只有开票日期、开票地址和金额，没有付款方式字段，无法回答。",
        expect_unanswerable=True,
    ),
]
