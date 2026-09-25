"""
扩展题库：E11–E50。

E01–E10 全部满分之后，评测集就失去区分度了——无论怎么调参分数都是 100%，
看不出任何差异。一个测不出差异的评测集，和没有评测集区别不大。

所以这一批按难度分层，专门加区分度：

    B 组  跨表多跳      要走 2–3 次 JOIN 才能拿到答案
    C 组  嵌套聚合      需要子查询或两次聚合相除
    D 组  时间窗口      区间、分组、对比
    E 组  陷阱题        Schema 根本支撑不了，考的是会不会编
"""

from __future__ import annotations

from typing import List

from eval.cases import EvalCase

EXTRA_CASES: List[EvalCase] = [
    # ==================== A 组：基础覆盖面 ====================
    EvalCase(
        id="E11", query="各个支付渠道分别有多少笔支付记录",
        reference_sql="SELECT pay_channel, COUNT(*) AS cnt FROM fact_payment GROUP BY pay_channel",
        must_hit_columns=["fact_payment.pay_channel"],
        tags=["分组统计"], note="覆盖支付流水表",
    ),
    EvalCase(
        id="E12", query="每个会员等级各有多少用户",
        reference_sql="SELECT member_level, COUNT(*) AS cnt FROM dim_user GROUP BY member_level",
        must_hit_columns=["dim_user.member_level"],
        tags=["分组统计"], note="基础分组",
    ),
    EvalCase(
        id="E13", query="订单的平均运费是多少",
        reference_sql="SELECT ROUND(AVG(freight_amount), 2) AS v FROM fact_order",
        must_hit_columns=["fact_order.freight_amount"],
        tags=["金额字段辨析"], note="运费是 9 个金额字段里最容易被忽略的一个",
    ),
    EvalCase(
        id="E14", query="所有订单的优惠金额总共是多少",
        reference_sql="SELECT ROUND(SUM(discount_amount), 2) AS v FROM fact_order",
        must_hit_columns=["fact_order.discount_amount"],
        tags=["金额字段辨析"], note="不能和 order_amount / pay_amount 混淆",
    ),
    EvalCase(
        id="E15", query="一共有多少个不同的商品品牌",
        reference_sql="SELECT COUNT(DISTINCT brand) AS v FROM dim_product",
        must_hit_columns=["dim_product.brand"],
        tags=["去重计数"], note="DISTINCT 计数",
    ),
    EvalCase(
        id="E16", query="退款状态是退款中的记录有多少条",
        reference_sql="SELECT COUNT(*) AS v FROM fact_refund WHERE refund_status = '退款中'",
        must_hit_columns=["fact_refund.refund_status"],
        tags=["单表过滤", "枚举值匹配"], note="枚举值要能从样例值里召回",
    ),
    EvalCase(
        id="E17", query="已下架的商品有多少个",
        reference_sql="SELECT COUNT(*) AS v FROM dim_product WHERE shelf_status = '已下架'",
        must_hit_columns=["dim_product.shelf_status"],
        tags=["单表过滤", "枚举值匹配"], note="",
    ),
    EvalCase(
        id="E18", query="通过直播间下单的订单有多少笔",
        reference_sql="SELECT COUNT(*) AS v FROM fact_order WHERE channel = '直播间'",
        must_hit_columns=["fact_order.channel"],
        tags=["单表过滤", "同名字段干扰"],
        note="channel 是下单渠道，register_channel 是注册渠道，不能选错",
    ),
    EvalCase(
        id="E19", query="用户浏览行为的平均停留时长是多少秒",
        reference_sql="SELECT ROUND(AVG(stay_seconds), 2) AS v FROM fact_user_behavior WHERE behavior_type = '浏览'",
        must_hit_columns=["fact_user_behavior.stay_seconds", "fact_user_behavior.behavior_type"],
        tags=["条件聚合"], note="要同时命中筛选和输出两个字段",
    ),
    EvalCase(
        id="E20", query="取消的订单一共有多少笔",
        reference_sql="SELECT COUNT(*) AS v FROM fact_order WHERE order_status = '已取消'",
        must_hit_columns=["fact_order.order_status"],
        tags=["单表过滤", "枚举值匹配"], note="",
    ),
    EvalCase(
        id="E21", query="二级类目一共有多少个",
        reference_sql="SELECT COUNT(*) AS v FROM dim_category WHERE category_level = 2",
        must_hit_columns=["dim_category.category_level"],
        tags=["单表过滤"], note="",
    ),
    EvalCase(
        id="E22", query="每种店铺类型各有多少家店",
        reference_sql="SELECT shop_type, COUNT(*) AS cnt FROM dim_shop GROUP BY shop_type",
        must_hit_columns=["dim_shop.shop_type"],
        tags=["分组统计"], note="",
    ),

    # ==================== B 组：跨表多跳 ====================
    EvalCase(
        id="E23", query="每个一级类目的商品成交金额是多少",
        reference_sql="""
            SELECT c1.category_name, ROUND(SUM(i.item_amount), 2) AS amt
            FROM fact_order_item i
            JOIN dim_product p ON p.product_id = i.product_id
            JOIN dim_category c2 ON c2.category_id = p.category_id
            JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
            GROUP BY c1.category_id, c1.category_name
        """,
        must_hit_columns=["fact_order_item.item_amount", "dim_category.category_name", "dim_product.category_id"],
        tags=["跨表关联", "多跳JOIN", "层级类目"],
        note="三跳：明细→商品→二级类目→一级类目",
    ),
    EvalCase(
        id="E24", query="北京用户一共下了多少笔订单",
        reference_sql="""
            SELECT COUNT(*) AS v FROM fact_order o
            JOIN dim_user u ON u.user_id = o.user_id WHERE u.city = '北京'
        """,
        must_hit_columns=["dim_user.city"],
        tags=["跨表关联", "同名字段干扰"], note="必须用 dim_user.city 不是 dim_shop.city",
    ),
    EvalCase(
        id="E25", query="销量最高的三个品牌，品牌名和销量分别是多少",
        reference_sql="""
            SELECT p.brand, SUM(i.quantity) AS q
            FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id
            GROUP BY p.brand ORDER BY SUM(i.quantity) DESC LIMIT 3
        """,
        must_hit_columns=["fact_order_item.quantity", "dim_product.brand"],
        tags=["跨表关联", "排序取TopN"], note="销量指的是件数不是金额",
    ),
    EvalCase(
        id="E26", query="发生过退款的订单，它们的用户来自哪些城市",
        reference_sql="""
            SELECT DISTINCT u.city FROM fact_refund r
            JOIN fact_order o ON o.order_id = r.order_id
            JOIN dim_user u ON u.user_id = o.user_id
        """,
        must_hit_columns=["dim_user.city"],
        tags=["跨表关联", "多跳JOIN"], note="退款→订单→用户，三张表",
    ),
    EvalCase(
        id="E27",
        query="按店铺主营的一级类目统计，每个一级类目的退款金额分别是多少",
        reference_sql="""
            SELECT c1.category_name, ROUND(SUM(r.refund_amount), 2) AS amt
            FROM fact_refund r
            JOIN fact_order o ON o.order_id = r.order_id
            JOIN dim_shop s ON s.shop_id = o.shop_id
            JOIN dim_category c2 ON c2.category_id = s.main_category_id
            JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
            GROUP BY c1.category_id, c1.category_name
        """,
        must_hit_columns=["fact_refund.refund_amount", "dim_category.category_name"],
        tags=["跨表关联", "多跳JOIN"],
        note=(
            "四跳，路径长容易走偏。问法里写明按“店铺主营类目”统计——"
            "原来只写“每个一级类目”，退款既可以归给店铺主营类目，"
            "也可以归给订单里商品的实际类目，两条路径结果不同，题目无法判分。"
        ),
    ),
    EvalCase(
        id="E28", query="买家数最多的城市是哪个",
        reference_sql="""
            SELECT u.city
            FROM fact_order o JOIN dim_user u ON u.user_id = o.user_id
            GROUP BY u.city ORDER BY COUNT(DISTINCT o.user_id) DESC LIMIT 1
        """,
        must_hit_columns=["dim_user.city"],
        tags=["跨表关联", "去重计数"], note="买家数要去重",
    ),
    EvalCase(
        id="E29", query="钻石会员一共贡献了多少实付金额",
        reference_sql="""
            SELECT ROUND(SUM(o.pay_amount), 2) AS v FROM fact_order o
            JOIN dim_user u ON u.user_id = o.user_id
            WHERE u.member_level = '钻石会员' AND o.pay_time IS NOT NULL
        """,
        must_hit_columns=["dim_user.member_level", "fact_order.pay_amount"],
        tags=["跨表关联", "金额字段辨析"], note="",
    ),
    EvalCase(
        id="E30", query="加购次数最多的三个商品叫什么名字",
        reference_sql="""
            SELECT p.product_name FROM fact_user_behavior b
            JOIN dim_product p ON p.product_id = b.product_id
            WHERE b.behavior_type = '加购'
            GROUP BY p.product_id, p.product_name ORDER BY COUNT(*) DESC LIMIT 3
        """,
        must_hit_columns=["fact_user_behavior.behavior_type", "dim_product.product_name"],
        tags=["跨表关联", "排序取TopN"], note="输出要的是商品名不是 ID",
    ),
    EvalCase(
        id="E31", query="用微信支付的订单实付金额合计是多少",
        reference_sql="SELECT ROUND(SUM(pay_amount), 2) AS v FROM fact_payment WHERE pay_channel = '微信支付'",
        must_hit_columns=[["fact_payment.pay_amount", "fact_order.pay_amount"], "fact_payment.pay_channel"],
        tags=["金额字段辨析", "同名字段干扰"],
        note="pay_amount 两张表都有，但按支付渠道筛必须落在 fact_payment",
    ),
    EvalCase(
        id="E32", query="上海的店铺一共有多少个在售商品",
        reference_sql="""
            SELECT COUNT(*) AS v FROM dim_product p
            JOIN dim_shop s ON s.shop_id = p.shop_id
            WHERE s.city = '上海' AND p.shelf_status = '在售'
        """,
        must_hit_columns=["dim_shop.city", "dim_product.shelf_status"],
        tags=["跨表关联", "同名字段干扰"],
        note="这次反过来，city 必须取 dim_shop 的",
    ),

    # ==================== C 组：嵌套 / 多步聚合 ====================
    EvalCase(
        id="E33", query="客单价高于全体平均水平的用户有多少人",
        reference_sql="""
            SELECT COUNT(*) AS v FROM dws_user_summary
            WHERE avg_order_amount > (SELECT AVG(avg_order_amount) FROM dws_user_summary)
        """,
        must_hit_columns=["dws_user_summary.avg_order_amount"],
        tags=["嵌套聚合", "纯口径词"], note="需要子查询算出平均值再比较",
    ),
    EvalCase(
        id="E34", query="下单笔数超过平均值的用户有多少人",
        reference_sql="""
            SELECT COUNT(*) AS v FROM dws_user_summary
            WHERE total_order_count > (SELECT AVG(total_order_count) FROM dws_user_summary)
        """,
        must_hit_columns=["dws_user_summary.total_order_count"],
        tags=["嵌套聚合"], note="",
    ),
    EvalCase(
        id="E35", query="有过退款的用户占全部用户的百分之多少（返回0到100之间的数）",
        reference_sql="""
            SELECT ROUND(
                CAST(SUM(CASE WHEN refund_order_count > 0 THEN 1 ELSE 0 END) AS REAL)
                * 100.0 / COUNT(*), 2) AS pct
            FROM dws_user_summary
        """,
        must_hit_columns=["dws_user_summary.refund_order_count"],
        tags=["嵌套聚合", "比率计算"], note="占比要用百分数，分母是全部用户",
    ),
    EvalCase(
        id="E36", query="退款金额占销售额比例最高的店铺是哪家，只返回店铺名称",
        reference_sql="""
            SELECT s.shop_name
            FROM dws_shop_daily d JOIN dim_shop s ON s.shop_id = d.shop_id
            GROUP BY d.shop_id, s.shop_name
            HAVING SUM(d.gmv) > 0
            ORDER BY SUM(d.refund_amount) / SUM(d.gmv) DESC LIMIT 1
        """,
        must_hit_columns=["dws_shop_daily.refund_amount", "dws_shop_daily.gmv", "dim_shop.shop_name"],
        tags=["嵌套聚合", "比率计算", "跨表关联"], note="两个聚合相除再排序",
    ),
    EvalCase(
        id="E37",
        query=(
            "每家店铺把各天的转化率取平均作为该店转化率，"
            "低于全部店铺全部天数转化率平均值的店铺有多少家"
        ),
        reference_sql="""
            SELECT COUNT(*) AS v FROM (
                SELECT shop_id, AVG(conversion_rate) AS r FROM dws_shop_daily GROUP BY shop_id
            ) t WHERE t.r < (SELECT AVG(conversion_rate) FROM dws_shop_daily)
        """,
        must_hit_columns=["dws_shop_daily.conversion_rate"],
        tags=["嵌套聚合"],
        note=(
            "两层聚合。原问法「转化率低于全店平均的店铺有多少家」没法判分——"
            "实测有 5 种说得通的算法，答案分别是 5 / 7 / 15 / 124 / 15："
            "店铺日均 vs 全部店-天平均（参考答案）、店铺日均 vs 各店日均的平均、"
            "按买家数重算每店转化率、逐行比较数店-天、逐行比较后按店去重。"
            "模型每次挑一种，挑中第一种才算对，repeat 5 下 0/5。现在问法里把两个"
            "「平均」各是什么都写死了"
        ),
    ),
    EvalCase(
        id="E38", query="单笔实付金额最高的那笔订单是哪个用户下的",
        reference_sql="""
            SELECT u.user_name FROM fact_order o
            JOIN dim_user u ON u.user_id = o.user_id
            ORDER BY o.pay_amount DESC LIMIT 1
        """,
        must_hit_columns=["fact_order.pay_amount", "dim_user.user_name"],
        tags=["跨表关联", "排序取TopN"], note="",
    ),
    EvalCase(
        id="E39", query="平均标价最高的一级类目是哪个",
        reference_sql="""
            SELECT c1.category_name FROM dim_product p
            JOIN dim_category c2 ON c2.category_id = p.category_id
            JOIN dim_category c1 ON c1.category_id = c2.parent_category_id
            GROUP BY c1.category_id, c1.category_name
            ORDER BY AVG(p.list_price) DESC LIMIT 1
        """,
        must_hit_columns=["dim_product.list_price", "dim_category.category_name"],
        tags=["跨表关联", "层级类目"], note="",
    ),
    EvalCase(
        id="E40", query="平均每笔订单包含多少个商品明细",
        reference_sql="""
            SELECT ROUND(CAST(COUNT(*) AS REAL) / COUNT(DISTINCT order_id), 2) AS v
            FROM fact_order_item
        """,
        must_hit_columns=["fact_order_item.order_id"],
        tags=["嵌套聚合", "比率计算"], note="两个计数相除",
    ),

    # ==================== D 组：时间窗口 ====================
    EvalCase(
        id="E41", query="2024年5月1日到5月15日之间一共有多少笔订单",
        reference_sql="""
            SELECT COUNT(*) AS v FROM fact_order
            WHERE DATE(create_time) BETWEEN '2024-05-01' AND '2024-05-15'
        """,
        must_hit_columns=[["fact_order.create_time", "dws_shop_daily.stat_date"]],
        tags=["时间过滤", "区间查询"], note="",
    ),
    EvalCase(
        id="E42", query="5月份每一天的销售额分别是多少",
        reference_sql="SELECT stat_date, ROUND(SUM(gmv), 2) AS g FROM dws_shop_daily GROUP BY stat_date",
        must_hit_columns=["dws_shop_daily.stat_date", "dws_shop_daily.gmv"],
        tags=["时间过滤", "分组统计"], note="按天分组",
    ),
    EvalCase(
        id="E43", query="最近一次下单时间最晚的用户是谁",
        reference_sql="""
            SELECT u.user_name FROM dws_user_summary s
            JOIN dim_user u ON u.user_id = s.user_id
            WHERE s.last_order_time IS NOT NULL
            ORDER BY s.last_order_time DESC LIMIT 1
        """,
        must_hit_columns=["dws_user_summary.last_order_time", "dim_user.user_name"],
        tags=["时间过滤", "跨表关联"], note="",
    ),
    EvalCase(
        id="E44",
        query="按退款申请时间算，5月下旬（21日至月底）的退款金额比上旬（1日至10日）多多少，只返回差值",
        reference_sql="""
            SELECT ROUND(
                SUM(CASE WHEN DATE(apply_time) BETWEEN '2024-05-21' AND '2024-05-31'
                         THEN refund_amount ELSE 0 END)
              - SUM(CASE WHEN DATE(apply_time) BETWEEN '2024-05-01' AND '2024-05-10'
                         THEN refund_amount ELSE 0 END), 2) AS diff
            FROM fact_refund
        """,
        must_hit_columns=["fact_refund.refund_amount", "fact_refund.apply_time"],
        tags=["时间过滤", "区间对比"],
        note=(
            "同一列上做两个时间窗口的差值。"
            "问法里写明了旬的起止日期——原来的版本只写“上旬/下旬”，"
            "而我自己把参考答案写成了前半月/后半月（中文历法上旬是1-10不是1-15），"
            "模型用对了口径反被判错。"
            "\n"
            "后来又补了「按退款申请时间算」：按申请时间是 268979.27，"
            "按完成时间是 269772.91，两种都说得通。另外 dws_shop_daily.refund_amount "
            "按订单下单日归属，不是退款发生日，走那条路径会得到 83341.19——"
            "这是元数据的锅，见 dws_shop_daily 的字段说明"
        ),
    ),
    EvalCase(
        id="E45", query="注册时间最早的用户注册于哪一天",
        reference_sql="SELECT MIN(register_time) AS v FROM dim_user",
        must_hit_columns=["dim_user.register_time"],
        tags=["时间过滤", "同名字段干扰"],
        note="register_time 是注册时间，不是下单时间 create_time",
    ),

    # ==================== E 组：陷阱题 ====================
    EvalCase(
        id="E46", query="用户的手机号分别是多少",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[], expect_unanswerable=True,
        tags=["陷阱题"], note="库里没有手机号字段，正确行为是说明缺失",
    ),
    EvalCase(
        id="E47", query="每个商品当前还剩多少库存",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[], expect_unanswerable=True,
        tags=["陷阱题"], note="没有库存字段。dim_product 只有价格和上架状态",
    ),
    EvalCase(
        id="E48", query="每家店铺有多少名员工",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[], expect_unanswerable=True,
        tags=["陷阱题"], note="根本没有员工表",
    ),
    EvalCase(
        id="E49", query="用户的物流签收时效平均是多少小时",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[], expect_unanswerable=True,
        tags=["陷阱题"], note="没有物流表。fact_order.finish_time 是确认收货但没有发货时间",
    ),
    EvalCase(
        id="E50", query="每个用户的具体年龄是多少岁",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[], expect_unanswerable=True,
        tags=["陷阱题"],
        note="只有 age_group 年龄段，没有精确年龄。最容易被将就着答的一题",
    ),
    # ------------------------------------------------------------------
    # F 组：筛选与指标分表
    #
    # 加这一组的起因是 E24 的追查（见 README「追查 E24」）：精排是逐字段
    # 打分的，没有"这组字段合起来能不能回答问题"的概念。当筛选条件和指标
    # 分属不同的表时，它会把名额全押给语义最近的那一张——而那张表往往
    # 答不了问题，因为缺的正是筛选维度。
    #
    # 前 50 题测不出这件事：首轮召回已经 94%，67 个必中字段只剩 4 个没召回，
    # E24 几乎是唯一的整表缺失案例。一个测不出差别的题库，改进和退步长得一样。
    #
    # 所以这一组每道题都刻意把筛选和指标拆到不同表上，并且尽量让"看起来最相关
    # 的那张表"答不了题。
    # ------------------------------------------------------------------
    EvalCase(
        id="E51",
        query="上海的店铺卖给北京用户的已完成订单，实付金额合计是多少",
        reference_sql="""
            SELECT ROUND(SUM(o.pay_amount), 2) AS amt
            FROM fact_order o
            JOIN dim_shop s ON s.shop_id = o.shop_id
            JOIN dim_user u ON u.user_id = o.user_id
            WHERE s.city = '上海'
              AND u.city = '北京'
              AND o.order_status = '已完成'
        """,
        must_hit_columns=[
            "dim_shop.city",
            "dim_user.city",
            "fact_order.pay_amount",
            "fact_order.order_status",
        ],
        tags=["多跳JOIN", "同名字段干扰", "筛选与指标分表", "金额字段辨析"],
        note=(
            "一次把两个 city 都考了：店铺所在地和用户所在地必须同时召回、"
            "而且不能张冠李戴。只召回一个就会算出一个看起来合理的错数字。"
            "\n"
            "原来没写「已完成」，结果这题本身不可判分：模型加了 "
            "pay_time IS NOT NULL（只算真付过款的），得 75502.68，"
            "参考答案 76944.06。两个数都对——「实付金额」到底算不算"
            "待支付和已取消的订单，题目没说。限定已完成之后两种写法结果一致，"
            "因为已完成订单的 pay_time 全部非空。"
        ),
    ),
    EvalCase(
        id="E52",
        query="直播间下单的金卡会员，一共退了多少钱",
        reference_sql="""
            SELECT ROUND(SUM(r.refund_amount), 2) AS amt
            FROM fact_refund r
            JOIN fact_order o ON o.order_id = r.order_id
            JOIN dim_user u ON u.user_id = o.user_id
            WHERE o.channel = '直播间' AND u.member_level = '金卡会员'
        """,
        must_hit_columns=[
            "fact_order.channel",
            "dim_user.member_level",
            "fact_refund.refund_amount",
        ],
        tags=["多跳JOIN", "筛选与指标分表", "枚举值匹配", "纯口径词"],
        note="三张表各出一个字段：两个筛选条件分别在 fact_order 和 dim_user，指标在 fact_refund",
    ),
    EvalCase(
        id="E53",
        query="美妆护肤类目的商品一共被加购了多少次",
        reference_sql="""
            SELECT COUNT(*) AS cnt
            FROM fact_user_behavior b
            JOIN dim_product p ON p.product_id = b.product_id
            JOIN dim_category c ON c.category_id = p.category_id
            WHERE b.behavior_type = '加购'
              AND (c.parent_category_id = 1 OR c.category_id = 1)
        """,
        must_hit_columns=[
            "dim_product.category_id",
            "fact_user_behavior.behavior_type",
            ["dim_category.category_name", "dim_category.parent_category_id"],
        ],
        tags=["多跳JOIN", "层级类目", "筛选与指标分表", "枚举值匹配"],
        note=(
            "类目筛选要走父子关系（商品挂在二级类目上），行为筛选要按 behavior_type，"
            "指标是行为表的计数——三样缺一不可"
        ),
    ),
    EvalCase(
        id="E54",
        query="因为商品质量问题退款的订单，分别来自哪些城市的店铺，各有多少笔",
        reference_sql="""
            SELECT s.city, COUNT(*) AS cnt
            FROM fact_refund r
            JOIN fact_order o ON o.order_id = r.order_id
            JOIN dim_shop s ON s.shop_id = o.shop_id
            WHERE r.refund_reason = '商品质量问题'
            GROUP BY s.city
        """,
        must_hit_columns=["fact_refund.refund_reason", "dim_shop.city"],
        tags=["多跳JOIN", "筛选与指标分表", "分组统计", "同名字段干扰"],
        note=(
            "筛选条件在事实表、输出维度在维表，检索容易只召回一头。"
            "city 还要选店铺那个，不是用户那个"
        ),
    ),
    EvalCase(
        id="E55",
        query="5月下旬（21日到月底）上海店铺的销售额，减去上旬（1日到10日）的差值是多少",
        reference_sql="""
            SELECT ROUND(
                SUM(CASE WHEN d.stat_date >= '2024-05-21' THEN d.gmv ELSE 0 END)
                - SUM(CASE WHEN d.stat_date <= '2024-05-10' THEN d.gmv ELSE 0 END),
                2
            ) AS diff
            FROM dws_shop_daily d
            JOIN dim_shop s ON s.shop_id = d.shop_id
            WHERE s.city = '上海'
        """,
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
            "dim_shop.city",
        ],
        tags=["区间对比", "筛选与指标分表", "多跳JOIN", "纯口径词"],
        note=(
            "两条路径都对：走 dws 汇总层或走 fact 明细层，实测差值都是 -18479.5。"
            "答案是负数，写反了符号就露馅"
        ),
    ),
    EvalCase(
        id="E56",
        query="浏览过商品但从来没有下过单的用户有多少人",
        reference_sql="""
            SELECT COUNT(*) AS cnt FROM (
                SELECT DISTINCT b.user_id
                FROM fact_user_behavior b
                WHERE b.behavior_type = '浏览'
                  AND b.user_id NOT IN (SELECT user_id FROM fact_order)
            )
        """,
        must_hit_columns=[
            ["fact_user_behavior.behavior_type", "fact_user_behavior.user_id"],
            "fact_order.user_id",
        ],
        tags=["嵌套聚合", "筛选与指标分表", "多跳JOIN"],
        note="反连接：两张事实表的 user_id 都要召回，缺一头就无从下手",
    ),
    EvalCase(
        id="E57",
        query=(
            "已完成订单里，金卡会员和钻石会员贡献的实付金额占全部已完成订单的"
            "百分之多少（返回0到100之间的数）"
        ),
        reference_sql="""
            SELECT ROUND(
                100.0 * SUM(
                    CASE WHEN u.member_level IN ('金卡会员', '钻石会员')
                    THEN o.pay_amount ELSE 0 END
                ) / SUM(o.pay_amount),
                2
            ) AS pct
            FROM fact_order o
            JOIN dim_user u ON u.user_id = o.user_id
            WHERE o.order_status = '已完成'
        """,
        must_hit_columns=[
            "fact_order.order_status",
            "dim_user.member_level",
            "fact_order.pay_amount",
        ],
        tags=["条件聚合", "比率计算", "筛选与指标分表", "多跳JOIN"],
        note="分子的筛选条件在维表、分母的范围在事实表，两个条件不能混成一个",
    ),
    EvalCase(
        id="E58",
        query="用微信支付的订单里，有多少笔发生过退款",
        reference_sql="""
            SELECT COUNT(DISTINCT r.order_id) AS cnt
            FROM fact_refund r
            JOIN fact_payment p ON p.order_id = r.order_id
            WHERE p.pay_channel = '微信支付'
        """,
        must_hit_columns=[
            "fact_payment.pay_channel",
            ["fact_refund.order_id", "fact_refund.refund_id"],
        ],
        tags=["多跳JOIN", "筛选与指标分表", "枚举值匹配", "同名字段干扰"],
        note=(
            "两张事实表直接对撞，中间没有维表。"
            "pay_channel 是支付渠道，fact_order.channel 是下单渠道，取错就全错"
        ),
    ),
    EvalCase(
        id="E59",
        query="5月24日到30日直播间的订单，比5月1日到7日多多少笔，只返回差值",
        reference_sql="""
            SELECT
                SUM(CASE WHEN date(create_time) BETWEEN '2024-05-24' AND '2024-05-30'
                         THEN 1 ELSE 0 END)
              - SUM(CASE WHEN date(create_time) BETWEEN '2024-05-01' AND '2024-05-07'
                         THEN 1 ELSE 0 END) AS diff
            FROM fact_order
            WHERE channel = '直播间'
        """,
        must_hit_columns=["fact_order.create_time", "fact_order.channel"],
        tags=["区间对比", "时间过滤", "枚举值匹配"],
        note=(
            "两个不相连的时间窗口各算一次，中间那两周要排除掉。"
            "\n"
            "原问法「5月1日到7日、5月24日到30日，直播间各有多少笔订单」没法判分："
            "参考 SQL 给两段打的标签是我随手编的「第一周 / 最后一周」，"
            "模型写的是「5月1日到7日 / 5月24日到30日」，43 和 49 两个数分毫不差，"
            "却因为标签字符串对不上被判错，repeat 5 下 0/5。"
            "改成问差值，答案收敛成一个数（49 - 43 = 6）"
        ),
    ),
    EvalCase(
        id="E60",
        query="在售商品的平均标价，减去已下架商品的平均标价，差值是多少",
        reference_sql="""
            SELECT ROUND(
                AVG(CASE WHEN shelf_status = '在售' THEN list_price END)
                - AVG(CASE WHEN shelf_status = '已下架' THEN list_price END),
                2
            ) AS diff
            FROM dim_product
        """,
        must_hit_columns=["dim_product.shelf_status", "dim_product.list_price"],
        tags=["条件聚合", "单表聚合", "枚举值匹配"],
        note=(
            "同一列上按条件算两个平均值再相减。"
            "答案是负数——在售商品的均价其实比已下架的低，拍脑袋会写错方向"
        ),
    ),
    EvalCase(
        id="E61",
        query="2024年注册的用户一共下了多少笔订单",
        reference_sql="""
            SELECT COUNT(*) AS cnt
            FROM fact_order o
            JOIN dim_user u ON u.user_id = o.user_id
            WHERE strftime('%Y', u.register_time) = '2024'
        """,
        must_hit_columns=[
            "dim_user.register_time",
            ["fact_order.order_id", "fact_order.user_id"],
        ],
        tags=["筛选与指标分表", "时间过滤", "多跳JOIN"],
        note=(
            "时间条件在维表（注册时间）、指标在事实表。"
            "检索天然偏向 fact_order.create_time，一旦把它当成时间条件，"
            "算出来就是「2024年下的单」——数字合理、口径全错"
        ),
    ),
]
