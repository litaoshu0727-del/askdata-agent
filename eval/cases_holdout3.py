"""
第三套留出评测集：由独立出题人在未见过被测系统表现和已有题目的情况下编写。
ecommerce 30 题（H3E01–H3E30，陷阱 3），Chinook 20 题（H3C01–H3C20，陷阱 3）。

**已用过一次。**这套题于 a2707a3 冻结，在时间字段修复（2a4ccc4）之后第一次运行，
三个版本一起跑，结果见 docs/实验记录.md「第三套留出集：两个改动在没见过的题上」：

    版本                      ecommerce   Chinook   150 次运行中通过
    删精排文本之前 c40528a      27/30       20/20     138
    删精排文本之后 1c9c039      29/30       20/20     145
    时间字段修复后 2a4ccc4      27/30       19/20     138

删精排文本在陌生题上成立；时间修复在这里没有可帮的题，取值范围写进提示词的那一半
随后撤掉、只留保底——这个改法是看了这套题的结果才定的，不能再用这套题验证。

冻结后没有修改任何题目。

出题条件和前两套相同：只给 Schema 与数据字典（表描述、字段描述）和两个库，材料存档在
eval/blind_materials/；不读 README、docs/、eval/ 已有题目和 git 历史，不运行被测系统。

修时间字段的人在冻结前没有读过题目：去重和机械校验全由脚本完成，只输出题号和是否通过。

候选路径的验证 SQL 在 eval/cases_holdout3_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

第三套盲写评测题（holdout3）。

ecommerce 30 题（H3E01–H3E30，陷阱题 3 道），chinook 20 题（H3C01–H3C20，陷阱题 3 道）。
出题只依据本目录下的 ecommerce.md / chinook.md 数据字典和两个 SQLite 库本身。
有候选路径的题，验证用的其他路径 SQL 见同目录 alt_sql.json。
"""

from eval.cases import EvalCase

UNANSWERABLE_SQL = "SELECT 1 WHERE 0"


# ---------------------------------------------------------------------------
# ecommerce
# ---------------------------------------------------------------------------

HOLDOUT3_ECOMMERCE_CASES = [
    EvalCase(
        id="H3E01",
        query="平台用户按注册来源渠道分组，每个注册渠道各有多少位用户？返回注册渠道和用户数。",
        reference_sql="""
SELECT register_channel, COUNT(*) AS user_cnt
FROM dim_user
GROUP BY register_channel
""",
        must_hit_columns=["dim_user.register_channel"],
        tags=["难度:简单", "单表分组计数", "注册渠道与下单渠道辨析"],
        note="考注册渠道 dim_user.register_channel，不能用订单的下单渠道 fact_order.channel；"
             "dim_user 一行一个用户，按渠道直接计数，4 个渠道各一行。",
    ),
    EvalCase(
        id="H3E02",
        query="营业状态不是“正常营业”的店铺有哪些？返回店铺名称、店铺类型和营业状态。",
        reference_sql="""
SELECT shop_name, shop_type, shop_status
FROM dim_shop
WHERE shop_status <> '正常营业'
""",
        must_hit_columns=["dim_shop.shop_status", "dim_shop.shop_name", "dim_shop.shop_type"],
        tags=["难度:简单", "枚举筛选", "否定条件"],
        note="按 shop_status 取非“正常营业”的店铺（休假中、已关店各一家），共 2 行；"
             "店铺名称里的“旗舰店/自营店”字样不是店铺类型，类型取 shop_type。",
    ),
    EvalCase(
        id="H3E03",
        query="年龄段为“18-24”的用户中，男性和女性各有多少人？返回性别和人数。",
        reference_sql="""
SELECT gender, COUNT(*) AS user_cnt
FROM dim_user
WHERE age_group = '18-24'
GROUP BY gender
""",
        must_hit_columns=["dim_user.age_group", "dim_user.gender"],
        tags=["难度:简单", "枚举筛选", "单表分组计数"],
        note="age_group 取原值“18-24”筛选后按 gender 分组计数；该年龄段没有性别为空的用户，结果 2 行。",
    ),
    EvalCase(
        id="H3E04",
        query="下单渠道为“直播间”、并且支付渠道为“花呗分期”的订单有多少笔？这些订单的支付金额合计是多少"
              "（保留 2 位小数）？返回订单笔数和支付金额合计两列。",
        reference_sql="""
SELECT COUNT(DISTINCT o.order_id) AS order_cnt,
       ROUND(SUM(p.pay_amount), 2) AS pay_amt
FROM fact_order o
JOIN fact_payment p ON p.order_id = o.order_id
WHERE o.channel = '直播间'
  AND p.pay_channel = '花呗分期'
""",
        must_hit_columns=[
            "fact_order.channel",
            "fact_payment.pay_channel",
            ["fact_payment.pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:中等", "多表关联", "下单渠道与支付渠道辨析"],
        note="下单渠道在 fact_order.channel，支付渠道在 fact_payment.pay_channel，两者都要用；"
             "每笔已支付订单恰有一条支付流水且金额与订单实付金额相等，两种取金额的路径结果一致。",
    ),
    EvalCase(
        id="H3E05",
        query="按店铺类型统计 2024 年 5 月（5 月 1 日至 31 日，按下单日期）的 GMV，GMV 指订单商品总金额之和，"
              "所有订单状态都算在内。返回店铺类型和 GMV（保留 2 位小数）。",
        reference_sql="""
SELECT s.shop_type, ROUND(SUM(d.gmv), 2) AS gmv
FROM dws_shop_daily d
JOIN dim_shop s ON s.shop_id = d.shop_id
WHERE d.stat_date BETWEEN '2024-05-01' AND '2024-05-31'
GROUP BY s.shop_type
""",
        must_hit_columns=["dim_shop.shop_type", ["dws_shop_daily.gmv", "fact_order.order_amount"]],
        tags=["难度:中等", "多表关联", "GMV口径", "店铺类型字段辨析"],
        note="店铺类型必须用 dim_shop.shop_type：店铺名称里的“旗舰店/专营店/自营店”字样与实际类型对不上，"
             "按名称模糊匹配分组会错。GMV 取 dws_shop_daily.gmv 或对 fact_order.order_amount 求和，已验证两条路径一致。",
    ),
    EvalCase(
        id="H3E06",
        query="累计实付金额最高的 5 位用户是谁？累计实付金额指该用户历史上所有支付过的订单（支付时间不为空，"
              "包括后来退款的订单）的实付金额之和。按累计实付金额从高到低排列，返回用户昵称和累计实付金额（保留 2 位小数）。",
        reference_sql="""
SELECT u.user_name, ROUND(s.total_pay_amount, 2) AS total_pay_amount
FROM dws_user_summary s
JOIN dim_user u ON u.user_id = s.user_id
ORDER BY s.total_pay_amount DESC
LIMIT 5
""",
        must_hit_columns=["dim_user.user_name", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
        tags=["难度:中等", "TopN", "汇总表优先", "排序"],
        note="口径与 dws_user_summary.total_pay_amount 一致（含已退款订单）；若只算“已完成/已支付”状态，排名会变，"
             "所以题干写明含退款订单。第 5、6 名金额不同，无并列；从 fact_order 按支付时间非空求和结果相同。",
        ordered=True,
    ),
    EvalCase(
        id="H3E07",
        query="被“收藏”次数最多的 2 个商品是哪两个？收藏次数按收藏行为记录的条数计算。返回商品ID、商品名称和收藏次数。",
        reference_sql="""
SELECT p.product_id, p.product_name, COUNT(*) AS fav_cnt
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
WHERE b.behavior_type = '收藏'
GROUP BY p.product_id, p.product_name
ORDER BY fav_cnt DESC
LIMIT 2
""",
        must_hit_columns=["fact_user_behavior.behavior_type", "dim_product.product_name"],
        tags=["难度:中等", "TopN", "行为数据", "枚举筛选"],
        note="behavior_type 取“收藏”，按商品计行为条数；第 2、3 名次数不同，无并列。"
             "商品名称有重名，所以要求同时返回商品ID，并按商品ID分组。",
    ),
    EvalCase(
        id="H3E08",
        query="2024 年 5 月各店铺的商品好评率分别是多少？好评率 = 好评条数 ÷ 评价总条数。"
              "返回店铺名称和好评率（保留 4 位小数）。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失识别"],
        note="库里 11 张表都没有评价、评分、好评/差评之类的数据，好评率无从计算；"
             "正确行为是说明缺少评价数据，而不是拿退款率、转化率等指标代替。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H3E09",
        query="只看订单状态为“已完成”的订单，各一级类目一共卖出了多少件商品（销量按购买件数求和）？"
              "返回一级类目名称和销量。",
        reference_sql="""
SELECT c1.category_name, SUM(i.quantity) AS sales_qty
FROM fact_order_item i
JOIN fact_order o ON o.order_id = i.order_id
JOIN dim_product p ON p.product_id = i.product_id
JOIN dim_category c2 ON c2.category_id = p.category_id
JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
WHERE o.order_status = '已完成'
GROUP BY c1.category_id, c1.category_name
""",
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:中等", "类目上卷", "销量口径", "多表关联"],
        note="商品只挂二级类目，要经 parent_category_id 上卷到一级类目；销量是 quantity 求和，不是明细行数。"
             "结果 3 行。",
    ),
    EvalCase(
        id="H3E10",
        query="在订单状态为“已完成”或“已支付”的订单中，毛利最高的 3 个二级类目是哪些？"
              "毛利 = 商品行成交金额之和 −（商品成本价 × 购买数量）之和。返回二级类目名称和毛利（保留 2 位小数）。",
        reference_sql="""
SELECT c.category_name,
       ROUND(SUM(i.item_amount - p.cost_price * i.quantity), 2) AS gross_profit
FROM fact_order_item i
JOIN fact_order o ON o.order_id = i.order_id
JOIN dim_product p ON p.product_id = i.product_id
JOIN dim_category c ON c.category_id = p.category_id
WHERE o.order_status IN ('已完成', '已支付')
GROUP BY c.category_id, c.category_name
ORDER BY gross_profit DESC
LIMIT 3
""",
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order_item.item_amount",
            "fact_order_item.quantity",
            "dim_product.cost_price",
            "dim_product.category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "TopN", "毛利计算", "多表关联"],
        note="成交金额取明细行 item_amount（已扣行优惠），成本 = cost_price × quantity；按二级类目汇总。"
             "第 3、4 名毛利相差约 3.9 万，无并列。",
    ),
    EvalCase(
        id="H3E11",
        query="按退款申请时间算，2024 年 6 月 1 日至 6 月 30 日（含首尾）申请的退款，各退款原因分别有多少条、"
              "退款金额合计多少？不限退款状态。返回退款原因、退款条数和退款金额合计（保留 2 位小数）。",
        reference_sql="""
SELECT refund_reason, COUNT(*) AS refund_cnt, ROUND(SUM(refund_amount), 2) AS refund_amt
FROM fact_refund
WHERE date(apply_time) BETWEEN '2024-06-01' AND '2024-06-30'
GROUP BY refund_reason
""",
        must_hit_columns=["fact_refund.apply_time", "fact_refund.refund_reason", "fact_refund.refund_amount"],
        tags=["难度:中等", "时间区间", "退款日期口径"],
        note="按 fact_refund.apply_time 筛 6 月；dws_shop_daily 的退款按下单日期归属且只有 5 月数据，不能用。"
             "6 月申请的退款覆盖全部 5 种原因，结果 5 行。",
    ),
    EvalCase(
        id="H3E12",
        query="退款状态为“退款成功”的退款记录，从申请退款到退款完成平均用了几天（退款完成时间减去申请时间，以天为单位）？"
              "按退款原因分组，返回退款原因和平均天数（保留 2 位小数）。",
        reference_sql="""
SELECT refund_reason,
       ROUND(AVG(julianday(finish_time) - julianday(apply_time)), 2) AS avg_days
FROM fact_refund
WHERE refund_status = '退款成功'
GROUP BY refund_reason
""",
        must_hit_columns=[
            "fact_refund.refund_status",
            "fact_refund.apply_time",
            "fact_refund.finish_time",
            "fact_refund.refund_reason",
        ],
        tags=["难度:中等", "日期差计算", "同名字段辨析"],
        note="用的是退款表自己的 finish_time，不是订单表的 finish_time；退款成功的记录完成时间都不为空，"
             "且申请到完成恰为整天数，按天相减无歧义。",
    ),
    EvalCase(
        id="H3E13",
        query="已支付过的订单（支付时间不为空）从下单到支付平均用了多少分钟？按下单渠道分组，"
              "返回下单渠道和平均分钟数（保留 1 位小数）。",
        reference_sql="""
SELECT channel,
       ROUND(AVG((strftime('%s', pay_time) - strftime('%s', create_time)) / 60.0), 1) AS avg_minutes
FROM fact_order
WHERE pay_time IS NOT NULL
GROUP BY channel
""",
        must_hit_columns=[
            "fact_order.channel",
            "fact_order.create_time",
            ["fact_order.pay_time", "fact_payment.pay_time"],
        ],
        tags=["难度:难", "日期差计算", "分组聚合"],
        note="时长 = 支付时间 − 下单时间（分钟）；时间精确到分钟，julianday 与 strftime 两种算法保留 1 位小数后一致。"
             "fact_payment.pay_time 与 fact_order.pay_time 逐单相等，两条路径结果相同。",
    ),
    EvalCase(
        id="H3E14",
        query="各会员等级的人均累计下单笔数是多少？累计下单笔数含所有状态的订单；人均 = 该等级所有用户的累计下单笔数之和 ÷ "
              "该等级的用户总数（从没下过单的用户也算在分母里）。返回会员等级和人均下单笔数（保留 3 位小数）。",
        reference_sql="""
SELECT u.member_level,
       ROUND(SUM(s.total_order_count) * 1.0 / COUNT(*), 3) AS avg_order_cnt
FROM dim_user u
JOIN dws_user_summary s ON s.user_id = u.user_id
GROUP BY u.member_level
""",
        must_hit_columns=["dim_user.member_level", ["dws_user_summary.total_order_count", "fact_order.order_id"]],
        tags=["难度:中等", "人均指标", "分母口径", "汇总表优先"],
        note="分母是该等级全部用户（含 2 位从未下单的用户），漏掉他们会改变普通会员和金卡会员的结果；"
             "保留 3 位小数是为了避开 2 位小数时恰好落在 .5 上的取整歧义。从 fact_order 左关联计数结果相同。",
    ),
    EvalCase(
        id="H3E15",
        query="不同会员等级的用户所下的订单里，运费金额为 0 的订单分别占多大比例？所有订单状态都算，"
              "占比 = 运费为 0 的订单数 ÷ 该等级用户的订单总数。返回会员等级和占比（0 到 1 之间的小数，保留 4 位小数）。",
        reference_sql="""
SELECT u.member_level,
       ROUND(SUM(CASE WHEN o.freight_amount = 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS free_freight_ratio
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
GROUP BY u.member_level
""",
        must_hit_columns=["dim_user.member_level", "fact_order.freight_amount"],
        tags=["难度:中等", "比率口径", "多表关联", "运费字段"],
        note="会员等级取下单用户的 dim_user.member_level，运费看 fact_order.freight_amount 是否为 0"
             "（库里运费只有 0、8、12 三种取值）；分母是该等级用户的全部订单，4 个等级各一行。",
    ),
    EvalCase(
        id="H3E16",
        query="最近一次下单时间早于 2024 年 5 月 10 日（不含 5 月 10 日当天）的用户有哪些？从未下过单的用户不算。"
              "返回用户昵称和最近一次下单时间。",
        reference_sql="""
SELECT u.user_name, s.last_order_time
FROM dws_user_summary s
JOIN dim_user u ON u.user_id = s.user_id
WHERE s.last_order_time < '2024-05-10'
""",
        must_hit_columns=["dim_user.user_name", ["dws_user_summary.last_order_time", "fact_order.create_time"]],
        tags=["难度:简单", "汇总表优先", "时间边界"],
        note="最近一次下单时间即 dws_user_summary.last_order_time（等于该用户订单 create_time 的最大值，两条路径已验证一致）；"
             "不含 5 月 10 日当天，含当天会多出 3 人；从未下单的用户该字段为空，自然不在结果里。结果 5 行。",
    ),
    EvalCase(
        id="H3E17",
        query="5 月份平台一共发放了多少张优惠券？优惠券核销率（已核销张数 ÷ 发放张数）是多少？返回发放张数和核销率。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失识别"],
        note="库里没有优惠券的发放、领取、核销记录；fact_order.discount_amount 只是商品折扣与优惠券抵扣混在一起的金额，"
             "既没有张数也拆不出单张券，发放量和核销率都答不了。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H3E18",
        query="每个店铺先按天算支付转化率（当天已支付买家数 ÷ 当天下单买家数；买家都按人去重，"
              "已支付买家指当天下的订单里至少有一笔支付时间不为空的买家），再对该店铺 2024 年 5 月里有订单的那些天取简单平均。"
              "平均转化率最低的 3 个店铺是哪些？返回店铺名称和平均转化率（0 到 1 之间的小数，保留 4 位小数）。",
        reference_sql="""
SELECT s.shop_name, ROUND(AVG(d.conversion_rate), 4) AS avg_conversion_rate
FROM dws_shop_daily d
JOIN dim_shop s ON s.shop_id = d.shop_id
WHERE d.stat_date BETWEEN '2024-05-01' AND '2024-05-31'
GROUP BY s.shop_id, s.shop_name
ORDER BY avg_conversion_rate ASC
LIMIT 3
""",
        must_hit_columns=["dim_shop.shop_name", ["dws_shop_daily.conversion_rate", "fact_order.pay_time"]],
        tags=["难度:难", "TopN", "比率口径", "汇总表优先"],
        note="题干给出的日转化率口径就是 dws_shop_daily.conversion_rate，取各天简单平均（不是按买家数加权）；"
             "从 fact_order 逐日重算结果相同。第 3、4 名为 0.7436 与 0.7603，无并列。",
    ),
    EvalCase(
        id="H3E19",
        query="停留时长超过 300 秒（不含 300 秒）的“浏览”行为，按被浏览商品所属的二级类目统计，各有多少条？"
              "返回二级类目名称和行为条数。",
        reference_sql="""
SELECT c.category_name, COUNT(*) AS behavior_cnt
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
JOIN dim_category c ON c.category_id = p.category_id
WHERE b.behavior_type = '浏览'
  AND b.stay_seconds > 300
GROUP BY c.category_id, c.category_name
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.stay_seconds",
            "dim_product.category_id",
            "dim_category.category_name",
        ],
        tags=["难度:中等", "行为数据", "边界条件", "多表关联"],
        note="严格大于 300 秒（恰为 300 秒的行为有几条，含不含会影响结果），只算 behavior_type=浏览；"
             "商品的 category_id 就是二级类目，9 个二级类目各一行。",
    ),
    EvalCase(
        id="H3E20",
        query="有下单行为的天数不少于 8 天的用户有哪些？同一天下多笔订单只算 1 天，所有订单状态都算。"
              "返回用户昵称和有下单行为的天数。",
        reference_sql="""
SELECT u.user_name, s.active_days
FROM dws_user_summary s
JOIN dim_user u ON u.user_id = s.user_id
WHERE s.active_days >= 8
""",
        must_hit_columns=["dim_user.user_name", ["dws_user_summary.active_days", "fact_order.create_time"]],
        tags=["难度:中等", "汇总表优先", "去重计数"],
        note="即 dws_user_summary.active_days ≥ 8；也可按 fact_order.create_time 的日期去重计数，已验证结果一致，共 8 位用户。",
    ),
    EvalCase(
        id="H3E21",
        query="按店铺所在城市汇总：各城市的店铺在 2024 年 5 月（按下单日期）收到的实付金额合计是多少？"
              "只算已支付订单（支付时间不为空，包括后来退款的订单）。返回店铺所在城市和实付金额合计（保留 2 位小数）。",
        reference_sql="""
SELECT s.city, ROUND(SUM(d.pay_amount), 2) AS pay_amt
FROM dws_shop_daily d
JOIN dim_shop s ON s.shop_id = d.shop_id
WHERE d.stat_date BETWEEN '2024-05-01' AND '2024-05-31'
GROUP BY s.city
""",
        must_hit_columns=["dim_shop.city", ["dws_shop_daily.pay_amount", "fact_order.pay_amount"]],
        tags=["难度:难", "城市字段辨析", "实付口径", "多表关联"],
        note="城市取店铺所在地 dim_shop.city，不是买家所在地 dim_user.city（两者分布完全不同）；"
             "金额口径与 dws_shop_daily.pay_amount 一致，从 fact_order 按支付时间非空求和结果相同。店铺分布在 7 个城市。",
    ),
    EvalCase(
        id="H3E22",
        query="订单状态为“已完成”的订单，按下单用户所在省份统计订单笔数和实付金额合计。"
              "返回省份、订单笔数和实付金额合计（保留 2 位小数）。",
        reference_sql="""
SELECT u.province, COUNT(*) AS order_cnt, ROUND(SUM(o.pay_amount), 2) AS pay_amt
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.order_status = '已完成'
GROUP BY u.province
""",
        must_hit_columns=["dim_user.province", "fact_order.order_status", "fact_order.pay_amount"],
        tags=["难度:中等", "多表关联", "枚举筛选", "地域字段辨析"],
        note="省份取买家 dim_user.province（店铺表没有省份）；实付金额是 fact_order.pay_amount，不是 order_amount。结果 8 行。",
    ),
    EvalCase(
        id="H3E23",
        query="哪些用户从来没有下过单（任何状态的订单都没有）？返回用户昵称和注册日期。",
        reference_sql="""
SELECT u.user_name, u.register_time
FROM dim_user u
WHERE NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.user_id = u.user_id)
""",
        must_hit_columns=[
            "dim_user.user_name",
            "dim_user.register_time",
            ["fact_order.user_id", "dws_user_summary.total_order_count"],
        ],
        tags=["难度:简单", "反连接", "注册时间与下单时间辨析"],
        note="用户表里有而订单表里没有的用户，共 2 位；也可用 dws_user_summary.total_order_count = 0 判断，结果一致。"
             "注册日期是 dim_user.register_time。",
    ),
    EvalCase(
        id="H3E24",
        query="店铺先按主营类目归入一级类目；每个一级类目里，哪家店铺状态为“已完成”的订单实付金额加起来最多？"
              "结果给出一级类目名称、店铺名称、该店铺实付金额总和（保留 2 位小数）三列。",
        reference_sql="""
WITH shop_amt AS (
    SELECT p.category_id AS l1_id, p.category_name AS l1_name,
           s.shop_id, s.shop_name, SUM(o.pay_amount) AS amt
    FROM fact_order o
    JOIN dim_shop s ON s.shop_id = o.shop_id
    JOIN dim_category c ON c.category_id = s.main_category_id
    JOIN dim_category p ON p.category_id = c.parent_category_id
    WHERE o.order_status = '已完成'
    GROUP BY p.category_id, p.category_name, s.shop_id, s.shop_name
), ranked AS (
    SELECT l1_name, shop_name, amt,
           RANK() OVER (PARTITION BY l1_id ORDER BY amt DESC) AS rk
    FROM shop_amt
)
SELECT l1_name, shop_name, ROUND(amt, 2) AS pay_amt
FROM ranked
WHERE rk = 1
""",
        must_hit_columns=[
            "dim_shop.main_category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
            "dim_shop.shop_name",
            "fact_order.order_status",
            "fact_order.pay_amount",
        ],
        tags=["难度:难", "分组取最大", "窗口函数", "类目上卷"],
        note="店铺经 main_category_id（二级类目）→ parent_category_id 归到一级类目，组内按已完成订单 pay_amount 之和取第 1 名；"
             "3 个一级类目各一行，组内第 1、2 名差距都在 8 万以上，无并列。",
    ),
    EvalCase(
        id="H3E25",
        query="每个下过单的用户，其首笔订单（下单时间最早的那一笔，任何订单状态都算）是从哪个下单渠道下的？"
              "按下单渠道统计首单用户数。返回下单渠道和用户数。",
        reference_sql="""
WITH ranked AS (
    SELECT user_id, channel,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time, order_id) AS rn
    FROM fact_order
)
SELECT channel, COUNT(*) AS user_cnt
FROM ranked
WHERE rn = 1
GROUP BY channel
""",
        must_hit_columns=["fact_order.channel", "fact_order.create_time", "fact_order.user_id"],
        tags=["难度:难", "窗口函数", "首单分析"],
        note="每个用户取 create_time 最早的订单的 channel；已验证没有用户在同一最早时刻下两笔单，首单唯一。"
             "4 个渠道合计 198 位下过单的用户。",
    ),
    EvalCase(
        id="H3E26",
        query="上架日期在 2024 年 5 月的新品有哪些？返回商品名称和上架日期。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失识别"],
        note="dim_product 只有当前上架状态 shelf_status，没有上架日期；dim_shop.open_time 是店铺开业日期，"
             "不能拿来当商品上架日期，库里没有任何字段能回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H3E27",
        query="有多少个“用户-商品”组合满足：该用户对该商品有过“加购”行为，并且至少有一笔该用户下的、包含该商品的订单，"
              "其下单时间晚于该用户对该商品最早一次加购的时间（订单状态不限）？返回一个数。",
        reference_sql="""
WITH cart AS (
    SELECT user_id, product_id, MIN(behavior_time) AS first_cart_time
    FROM fact_user_behavior
    WHERE behavior_type = '加购'
    GROUP BY user_id, product_id
)
SELECT COUNT(*) AS pair_cnt
FROM cart c
WHERE EXISTS (
    SELECT 1
    FROM fact_order o
    JOIN fact_order_item i ON i.order_id = o.order_id
    WHERE o.user_id = c.user_id
      AND i.product_id = c.product_id
      AND o.create_time > c.first_cart_time
)
""",
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.behavior_time",
            "fact_order.create_time",
            "fact_order_item.product_id",
        ],
        tags=["难度:难", "行为到购买转化", "相关子查询", "时间先后"],
        note="【存疑】题干条件多、对措辞敏感：不看时间先后是 71，按“晚于最早一次加购”是 40，"
             "若误读成“晚于最后一次加购”是 39，题干已写明取最早一次，但仍是本库最容易读偏的一题。"
             "以（用户, 商品）去重，要求存在一笔包含该商品、下单时间晚于首次加购时间的订单（严格晚于与不早于结果相同）。",
    ),
    EvalCase(
        id="H3E28",
        query="主营类目属于一级类目“数码电器”的店铺有哪些？返回店铺名称和主营类目的名称。",
        reference_sql="""
SELECT s.shop_name, c.category_name AS main_category_name
FROM dim_shop s
JOIN dim_category c ON c.category_id = s.main_category_id
JOIN dim_category p ON p.category_id = c.parent_category_id
WHERE p.category_name = '数码电器'
""",
        must_hit_columns=[
            "dim_shop.main_category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
            "dim_shop.shop_name",
        ],
        tags=["难度:中等", "类目上卷", "自关联"],
        note="店铺的 main_category_id 都指向二级类目，需再经 parent_category_id 找到一级类目“数码电器”；"
             "直接拿它等于一级类目 ID 会得到 0 行。结果 6 家店铺，主营类目名称是二级类目名。",
    ),
    EvalCase(
        id="H3E29",
        query="2024 年 5 月 1 日至 5 月 7 日（含首尾），按下单日期统计每天的订单量（所有订单状态都算）。"
              "按日期从早到晚排列，返回日期（YYYY-MM-DD 格式）和订单量。",
        reference_sql="""
SELECT date(create_time) AS order_date, COUNT(*) AS order_cnt
FROM fact_order
WHERE date(create_time) BETWEEN '2024-05-01' AND '2024-05-07'
GROUP BY date(create_time)
ORDER BY order_date
""",
        must_hit_columns=[["fact_order.create_time", "dws_shop_daily.stat_date"]],
        tags=["难度:中等", "时间区间", "按日分组", "排序"],
        note="create_time 带时分，需取日期部分并包含 5 月 7 日全天；用 dws_shop_daily 按 stat_date 对 order_count 求和结果一致。",
        ordered=True,
    ),
    EvalCase(
        id="H3E30",
        query="把全平台每天的成交额（当天下单的所有订单的商品总金额，不论订单状态）从 2024 年 5 月 1 日起依次累加，"
              "累计值最早在哪一天突破 500 万元（含正好 500 万）？给出这一天（YYYY-MM-DD）和截至这天的累计成交额（保留 2 位小数）。",
        reference_sql="""
WITH daily AS (
    SELECT stat_date, SUM(gmv) AS day_gmv
    FROM dws_shop_daily
    WHERE stat_date >= '2024-05-01'
    GROUP BY stat_date
), cum AS (
    SELECT stat_date, SUM(day_gmv) OVER (ORDER BY stat_date) AS cum_gmv
    FROM daily
)
SELECT stat_date, ROUND(cum_gmv, 2) AS cum_gmv
FROM cum
WHERE stat_date = (SELECT MIN(stat_date) FROM cum WHERE cum_gmv >= 5000000)
""",
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "累计求和", "窗口函数", "GMV口径", "候选路径"],
        note="成交额即 GMV（订单商品总金额，含所有状态），按下单日期汇总后做累计和，取累计值首次 ≥ 500 万的日期；"
             "前一天累计约 476 万、当天约 514 万，阈值不在边界附近。汇总表与订单表两条路径已验证一致。",
    ),
]


# ---------------------------------------------------------------------------
# chinook
# ---------------------------------------------------------------------------

HOLDOUT3_CHINOOK_CASES = [
    EvalCase(
        id="H3C01",
        query="曲目文件平均有多大？请按媒体格式分别算出曲目的平均文件大小，单位 MB（1 MB 按 1048576 字节计），保留 2 位小数。"
              "按平均文件大小从大到小排列，返回媒体格式名称和平均文件大小。",
        reference_sql="""
SELECT m.Name AS media_type, ROUND(AVG(t.Bytes) / 1048576.0, 2) AS avg_mb
FROM Track t
JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
GROUP BY m.MediaTypeId, m.Name
ORDER BY avg_mb DESC
""",
        must_hit_columns=["MediaType.Name", "Track.Bytes", "Track.MediaTypeId"],
        tags=["难度:简单", "单位换算", "维表关联", "排序"],
        note="文件大小是 Track.Bytes（不是时长 Milliseconds），所有曲目都有值；按 1048576 字节/MB 换算后取平均。"
             "5 种格式的平均值互不相同，排序唯一。",
        ordered=True,
    ),
    EvalCase(
        id="H3C02",
        query="按开票日期算，2024 年全年（1 月 1 日至 12 月 31 日）一共开了多少张发票？发票总金额是多少（保留 2 位小数）？"
              "返回发票张数和总金额两列。",
        reference_sql="""
SELECT COUNT(*) AS invoice_cnt, ROUND(SUM(Total), 2) AS total_amt
FROM Invoice
WHERE InvoiceDate >= '2024-01-01' AND InvoiceDate < '2025-01-01'
""",
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:简单", "时间区间", "聚合"],
        note="金额直接对 Invoice.Total 求和，不必关联明细；InvoiceDate 是带时分秒的文本，按年份区间筛选。",
    ),
    EvalCase(
        id="H3C03",
        query="2023 年（按开票日期）开票金额合计最高的 5 个开票国家是哪些？返回开票国家和开票金额合计（保留 2 位小数）。",
        reference_sql="""
SELECT BillingCountry, ROUND(SUM(Total), 2) AS total_amt
FROM Invoice
WHERE InvoiceDate >= '2023-01-01' AND InvoiceDate < '2024-01-01'
GROUP BY BillingCountry
ORDER BY total_amt DESC
LIMIT 5
""",
        must_hit_columns=["Invoice.BillingCountry", "Invoice.Total", "Invoice.InvoiceDate"],
        tags=["难度:中等", "TopN", "时间区间", "国家字段辨析"],
        note="题目问开票国家，应取 Invoice.BillingCountry（本库中它恰与客户国家一致，但口径上是两个字段）；"
             "第 5、6 名金额为 32.75 与 24.75，无并列。",
    ),
    EvalCase(
        id="H3C04",
        query="职位为“Sales Support Agent”的每位员工，各负责多少位客户？这些客户的发票总金额合计是多少？"
              "返回员工的名、姓（分两列）、负责的客户数和发票总金额（保留 2 位小数）。",
        reference_sql="""
SELECT e.FirstName, e.LastName,
       COUNT(DISTINCT c.CustomerId) AS customer_cnt,
       ROUND(SUM(i.Total), 2) AS total_amt
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
JOIN Invoice i ON i.CustomerId = c.CustomerId
WHERE e.Title = 'Sales Support Agent'
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=[
            "Employee.Title",
            "Customer.SupportRepId",
            "Invoice.Total",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:中等", "员工客户关联", "去重计数", "多表关联"],
        note="员工与客户只能经 Customer.SupportRepId 关联；客户数要按客户去重（关联发票后行数会放大）。"
             "每位客户都有发票，3 位员工各一行。",
    ),
    EvalCase(
        id="H3C05",
        query="看每位艺术家名下所有专辑里的曲目，哪些艺术家的曲目横跨了至少 3 种不同的音乐流派？"
              "列出这些艺术家的名称，以及各自涉及的流派个数。",
        reference_sql="""
SELECT ar.Name AS artist_name, COUNT(DISTINCT t.GenreId) AS genre_cnt
FROM Artist ar
JOIN Album al ON al.ArtistId = ar.ArtistId
JOIN Track t ON t.AlbumId = al.AlbumId
GROUP BY ar.ArtistId, ar.Name
HAVING COUNT(DISTINCT t.GenreId) >= 3
""",
        must_hit_columns=["Artist.Name", "Album.ArtistId", "Track.AlbumId", "Track.GenreId"],
        tags=["难度:中等", "去重计数", "HAVING", "三层结构"],
        note="艺术家→专辑→曲目，按 Track.GenreId 去重计数（25 个流派名称互不重复，按名称去重结果相同）；"
             "曲目靠专辑归属艺术家，不能用 Composer。结果 7 位艺术家。",
    ),
    EvalCase(
        id="H3C06",
        query="来自英国（United Kingdom）的艺术家一共有多少位？返回一个数。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失识别"],
        note="Artist 表只有 ArtistId 和 Name，没有国籍或所在国家；Customer.Country、Invoice.BillingCountry "
             "是客户和开票国家，不能用来推断艺术家来自哪里。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H3C07",
        query="按发票明细的成交单价 × 购买数量计算销售额，销售额最高的 5 个音乐流派是哪些？返回流派名称和销售额（保留 2 位小数）。",
        reference_sql="""
SELECT g.Name AS genre_name, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS revenue
FROM InvoiceLine il
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
GROUP BY g.GenreId, g.Name
ORDER BY revenue DESC
LIMIT 5
""",
        must_hit_columns=["Genre.Name", "InvoiceLine.UnitPrice", "InvoiceLine.Quantity", "Track.GenreId"],
        tags=["难度:难", "TopN", "多表关联", "成交价与标价辨析"],
        note="流派销售额只能从 InvoiceLine 出发（Invoice.Total 无法按流派拆分），单价用成交价 InvoiceLine.UnitPrice；"
             "第 5、6 名为 93.53 与 79.20，无并列。",
    ),
    EvalCase(
        id="H3C08",
        query="哪些歌单一首曲目都没有收录？返回歌单ID和歌单名称。",
        reference_sql="""
SELECT p.PlaylistId, p.Name
FROM Playlist p
WHERE NOT EXISTS (SELECT 1 FROM PlaylistTrack pt WHERE pt.PlaylistId = p.PlaylistId)
""",
        must_hit_columns=["Playlist.Name", "PlaylistTrack.PlaylistId"],
        tags=["难度:简单", "反连接"],
        note="Playlist 中在 PlaylistTrack 里没有任何行的歌单，共 4 个；歌单名有重名，所以同时返回歌单ID。",
    ),
    EvalCase(
        id="H3C09",
        query="每位有直属下属的员工，各有几名直属下属？返回该员工的名、姓、职位和直属下属人数。",
        reference_sql="""
SELECT m.FirstName, m.LastName, m.Title, COUNT(*) AS direct_report_cnt
FROM Employee e
JOIN Employee m ON m.EmployeeId = e.ReportsTo
GROUP BY m.EmployeeId, m.FirstName, m.LastName, m.Title
""",
        must_hit_columns=["Employee.ReportsTo", "Employee.FirstName", "Employee.LastName", "Employee.Title"],
        tags=["难度:中等", "自关联", "层级关系"],
        note="Employee.ReportsTo 自引用；只统计直属（一级）下属，不含间接下属。3 位管理者各一行。"
             "职位是 Employee.Title，不是专辑名 Album.Title。",
    ),
    EvalCase(
        id="H3C10",
        query="入职当天已满 40 周岁（入职时的周岁年龄 ≥ 40）的员工有哪些？返回员工的名、姓和入职时的周岁年龄。",
        reference_sql="""
SELECT FirstName, LastName, age_at_hire
FROM (
    SELECT FirstName, LastName,
           (CAST(strftime('%Y', HireDate) AS INTEGER) - CAST(strftime('%Y', BirthDate) AS INTEGER))
           - (strftime('%m-%d', HireDate) < strftime('%m-%d', BirthDate)) AS age_at_hire
    FROM Employee
)
WHERE age_at_hire >= 40
""",
        must_hit_columns=["Employee.BirthDate", "Employee.HireDate", "Employee.FirstName", "Employee.LastName"],
        tags=["难度:难", "日期计算", "周岁年龄"],
        note="周岁 = 入职年份 − 出生年份，入职日期的月日早于生日再减 1；只用年份相减会把其中两人算大 1 岁。"
             "满足条件的有 3 人。出生日期只有员工表有。",
    ),
    EvalCase(
        id="H3C11",
        query="既购买过“Jazz”流派曲目、又购买过“Classical”流派曲目的客户有哪些？返回客户的名和姓（分两列）。",
        reference_sql="""
SELECT c.FirstName, c.LastName
FROM Customer c
WHERE EXISTS (
        SELECT 1
        FROM Invoice i
        JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
        JOIN Track t ON t.TrackId = il.TrackId
        JOIN Genre g ON g.GenreId = t.GenreId
        WHERE i.CustomerId = c.CustomerId AND g.Name = 'Jazz')
  AND EXISTS (
        SELECT 1
        FROM Invoice i
        JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
        JOIN Track t ON t.TrackId = il.TrackId
        JOIN Genre g ON g.GenreId = t.GenreId
        WHERE i.CustomerId = c.CustomerId AND g.Name = 'Classical')
""",
        must_hit_columns=[
            "Genre.Name",
            "InvoiceLine.TrackId",
            "Invoice.CustomerId",
            "Customer.FirstName",
            "Customer.LastName",
        ],
        tags=["难度:难", "交集", "多表关联", "客户与员工辨析"],
        note="同一客户要在两个流派上都有购买记录（交集，不是并集）；购买关系只能走 Invoice→InvoiceLine，"
             "不能用歌单收录。共 5 位客户，姓名无重名。",
    ),
    EvalCase(
        id="H3C12",
        query="2025 年每个月（按开票日期所在月份）的发票金额合计是多少？按月份从早到晚排列，"
              "返回月份（YYYY-MM 格式）和金额合计（保留 2 位小数）。",
        reference_sql="""
SELECT strftime('%Y-%m', InvoiceDate) AS invoice_month, ROUND(SUM(Total), 2) AS total_amt
FROM Invoice
WHERE InvoiceDate >= '2025-01-01' AND InvoiceDate < '2026-01-01'
GROUP BY invoice_month
ORDER BY invoice_month
""",
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:中等", "按月分组", "时间区间", "排序"],
        note="InvoiceDate 是本库唯一的交易时间；2025 年 12 个月每月都有发票，按月份升序 12 行。",
        ordered=True,
    ),
    EvalCase(
        id="H3C13",
        query="2025 年开出的发票中，用信用卡支付的有多少张、金额合计多少？返回发票张数和金额合计。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失识别"],
        note="Invoice 只有客户、开票日期、开票地址和金额，库里任何表都没有支付方式字段，"
             "无法区分信用卡与其他支付方式。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H3C14",
        query="平均曲目时长最长的 3 个音乐流派是哪些？时长换算成分钟（毫秒 ÷ 60000），返回流派名称和平均时长（分钟，保留 2 位小数）。",
        reference_sql="""
SELECT g.Name AS genre_name, ROUND(AVG(t.Milliseconds) / 60000.0, 2) AS avg_minutes
FROM Track t
JOIN Genre g ON g.GenreId = t.GenreId
GROUP BY g.GenreId, g.Name
ORDER BY avg_minutes DESC
LIMIT 3
""",
        must_hit_columns=["Genre.Name", "Track.Milliseconds", "Track.GenreId"],
        tags=["难度:中等", "TopN", "单位换算"],
        note="对每个流派的曲目时长取平均再换算分钟；第 3、4 名为 42.92 与 35.75，无并列。",
    ),
    EvalCase(
        id="H3C15",
        query="被 4 个及以上歌单收录的曲目一共有多少首？歌单按歌单ID区分，同名的不同歌单分别计数。返回一个数。",
        reference_sql="""
SELECT COUNT(*) AS track_cnt
FROM (
    SELECT TrackId
    FROM PlaylistTrack
    GROUP BY TrackId
    HAVING COUNT(DISTINCT PlaylistId) >= 4
)
""",
        must_hit_columns=["PlaylistTrack.TrackId", "PlaylistTrack.PlaylistId"],
        tags=["难度:中等", "HAVING", "收录与销量辨析"],
        note="“被几个歌单收录”看 PlaylistTrack，不是 InvoiceLine 的销量；按 TrackId 分组、歌单数 ≥ 4 的曲目计数。",
    ),
    EvalCase(
        id="H3C16",
        query="曲目数最多的 3 张专辑是哪些？返回专辑名称、所属艺术家名称和曲目数。",
        reference_sql="""
SELECT al.Title AS album_title, ar.Name AS artist_name, COUNT(*) AS track_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
GROUP BY al.AlbumId, al.Title, ar.Name
ORDER BY track_cnt DESC
LIMIT 3
""",
        must_hit_columns=["Album.Title", "Artist.Name", "Track.AlbumId"],
        tags=["难度:中等", "TopN", "三层结构", "同名字段辨析"],
        note="专辑名称是 Album.Title（不是员工职位 Employee.Title）；前 3 名 57、34、30 首，第 4 名 26，无并列。",
    ),
    EvalCase(
        id="H3C17",
        query="有所属公司（公司名称不为空）的客户，他们的发票总金额合计是多少？返回一个数（保留 2 位小数）。",
        reference_sql="""
SELECT ROUND(SUM(i.Total), 2) AS total_amt
FROM Invoice i
JOIN Customer c ON c.CustomerId = i.CustomerId
WHERE c.Company IS NOT NULL
""",
        must_hit_columns=["Customer.Company", "Invoice.Total"],
        tags=["难度:简单", "空值判断", "多表关联"],
        note="Customer.Company 非空的 10 位客户（库里没有空字符串的公司名），对他们的 Invoice.Total 求和。",
    ),
    EvalCase(
        id="H3C18",
        query="所在城市为 Calgary 的员工有哪些？返回员工的名、姓和职位。",
        reference_sql="""
SELECT FirstName, LastName, Title
FROM Employee
WHERE City = 'Calgary'
""",
        must_hit_columns=["Employee.City", "Employee.FirstName", "Employee.LastName", "Employee.Title"],
        tags=["难度:简单", "同名字段辨析", "客户与员工辨析"],
        note="城市取员工所在城市 Employee.City；客户表里没有 Calgary 的客户，误用 Customer.City 会得到 0 行。结果 5 人。",
    ),
    EvalCase(
        id="H3C19",
        query="每个歌单分别是哪位客户创建的？返回歌单名称和创建者的姓名。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:简单", "陷阱题", "缺失识别"],
        note="Playlist 只有 PlaylistId 和 Name，没有创建者、创建时间等字段，歌单与客户之间也没有任何关联路径。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H3C20",
        query="歌单“Grunge”收录的曲目分别来自哪些艺术家？按艺术家统计该歌单中收录的曲目数，返回艺术家名称和曲目数。",
        reference_sql="""
SELECT ar.Name AS artist_name, COUNT(*) AS track_cnt
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t ON t.TrackId = pt.TrackId
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
WHERE p.Name = 'Grunge'
GROUP BY ar.ArtistId, ar.Name
""",
        must_hit_columns=[
            "Playlist.Name",
            "PlaylistTrack.TrackId",
            "Track.AlbumId",
            "Album.ArtistId",
            "Artist.Name",
        ],
        tags=["难度:难", "多跳关联", "歌单收录"],
        note="歌单→收录关系→曲目→专辑→艺术家五表串联；“Grunge”歌单名唯一，结果 6 位艺术家。"
             "曲目通过专辑归属艺术家，Composer 不是艺术家。",
    ),
]
