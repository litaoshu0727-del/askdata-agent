"""
第六套留出评测集：更难的一套。由独立出题人在未见过被测系统表现和已有题目的情况下编写。
ecommerce 30 题（H6E01–H6E30，陷阱 3），Chinook 20 题（H6C01–H6C20，陷阱 3）。

**已用过一次。**这套题于 ba7d1b7 冻结并推送后第一次运行，三个版本一起跑，都用冻结时的
评测器判分，结果见 docs/实验记录.md「第六套留出集：更难的题」：

    版本                                       ecommerce   Chinook   运行通过（90 + 60）
    93f9a98  第四套封存时的状态                  28/30       18/20     84 + 52
    35ab795  再加检索、复核、重试、时间保底、守卫  30/30       17/20     88 + 50
    ba7d1b7  再加一对多连接规则、结果行数上限      29/30       20/20     86 + 56
    ba7d1b7  压测库（ecommerce_big）             30/30       —         89

比第五套难得多，失败几乎全在 SQL 生成；三个版本的差别在波动范围内（93f9a98 和 35ab795
的生成提示词完全相同，"两层压成一层"一个 1 次、一个 6 次）。没有发现可证明没法判分的题，
冻结版就是最终版；H6C01 有一处口径可议（是否列出销售额为 0 的艺术家），记在实验记录里。

和前几套不同，出题规范改了（eval/blind_materials/出题规范_第六套.md）：题面用业务人员的说法，
不出现表名、字段名、计算公式，答案仍须唯一；至少一半非陷阱题要用到多表连接（4 张以上）、
两层聚合、窗口排名、相对时间、否定集合之一；"难"的比例更高。其中两层聚合、多表连接恰好
是之前几处改动针对的失败形态，这一套比前几套更有针对性。材料（数据字典、两个库）逐字沿用
eval/blind_materials/；不读 README、docs/、eval/ 已有题目和 git 历史，不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本完成，只输出题号和检查项；
出题人的回报里也不含题目内容。组装进仓库时只换了导入、加了这段文件头。

候选路径的验证 SQL 在 eval/cases_holdout6_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。


---- 以下是出题人写的说明 ----

第六套盲写评测题（holdout6）：ecommerce 30 题、chinook 20 题。
"""

from eval.cases import EvalCase

TRAP_SQL = "SELECT 1 WHERE 0"

# 二级类目 -> 一级类目 的公共连接片段（只在本文件里拼 SQL 用）
_L1_JOIN = (
    "JOIN dim_product p ON p.product_id = i.product_id "
    "JOIN dim_category c2 ON c2.category_id = p.category_id "
    "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
)

HOLDOUT6_ECOMMERCE_CASES = [
    EvalCase(
        id="H6E01",
        query="老板想看看：金卡会员在直播间下的、已经完成的订单里，三个一级大类的商品各卖出去了多少件？列出大类名称和件数。",
        reference_sql=(
            "SELECT c1.category_name, SUM(i.quantity) AS qty "
            "FROM fact_order o "
            "JOIN dim_user u ON u.user_id = o.user_id "
            "JOIN fact_order_item i ON i.order_id = o.order_id "
            + _L1_JOIN +
            "WHERE u.member_level = '金卡会员' AND o.channel = '直播间' AND o.order_status = '已完成' "
            "GROUP BY c1.category_id, c1.category_name"
        ),
        must_hit_columns=[
            "dim_user.member_level",
            "fact_order.channel",
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="连接订单、用户、明细、商品、类目（自连接）共 5 张表；件数=明细数量求和；商品只挂二级类目，需经父类目上卷到一级。",
    ),
    EvalCase(
        id="H6E02",
        query="每个一级类目里，销量最高的两款商品分别是哪两款？已取消的订单不算。因为有同名商品，请列出类目名称、商品编号、商品名称和销量。",
        reference_sql=(
            "SELECT category_name, product_id, product_name, qty FROM ("
            "SELECT c1.category_name, p.product_id, p.product_name, SUM(i.quantity) AS qty, "
            "RANK() OVER (PARTITION BY c1.category_id ORDER BY SUM(i.quantity) DESC) AS rk "
            "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
            + _L1_JOIN +
            "WHERE o.order_status <> '已取消' "
            "GROUP BY c1.category_id, c1.category_name, p.product_id, p.product_name"
            ") WHERE rk <= 2"
        ),
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.product_id",
            "dim_product.product_name",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接"],
        note="按商品编号分组（库里有同名商品，按名称分组会合并不同商品）；销量=件数求和；各组第2、第3名不并列（食品生鲜前两名并列 64 件，均入选，第3名 61 件）。",
    ),
    EvalCase(
        id="H6E03",
        query="有多少位用户曾经在同一天里下过不止一单？什么状态的订单都算。",
        reference_sql=(
            "SELECT COUNT(DISTINCT user_id) FROM ("
            "SELECT user_id, date(create_time) AS d FROM fact_order "
            "GROUP BY user_id, date(create_time) HAVING COUNT(*) > 1)"
        ),
        must_hit_columns=[["fact_order.create_time", "dws_user_summary.active_days"]],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按用户+下单日汇总，再数单日多单的用户；也可用用户汇总表的下单天数小于下单笔数，两条路径结果一致（44）。",
    ),
    EvalCase(
        id="H6E04",
        query="按会员等级看，各等级用户第一次下单的那笔订单，商品总金额（按标价算、还没扣优惠的那个金额）平均是多少？第一笔订单不管后来是什么状态都算，保留2位小数。",
        reference_sql=(
            "SELECT u.member_level, ROUND(AVG(o.order_amount), 2) FROM ("
            "SELECT user_id, order_amount, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time) AS rn "
            "FROM fact_order) o JOIN dim_user u ON u.user_id = o.user_id "
            "WHERE o.rn = 1 GROUP BY u.member_level"
        ),
        must_hit_columns=[
            "fact_order.create_time",
            "fact_order.order_amount",
            "fact_order.user_id",
            "dim_user.member_level",
        ],
        tags=["难度:中等", "考点:相对时间", "考点:窗口排名"],
        note="每位用户首单按下单时间取（用户内下单时间无重复），再按会员等级求首单商品总金额的平均；金额是订单商品总金额而非实付；各组平均值不在四舍五入边界上。",
    ),
    EvalCase(
        id="H6E05",
        query="有没有用户加购过商品，但一笔订单都没下过（任何状态的订单都没有）？把这些用户的昵称列出来。",
        reference_sql=(
            "SELECT u.user_name FROM dim_user u "
            "WHERE u.user_id IN (SELECT user_id FROM fact_user_behavior WHERE behavior_type = '加购') "
            "AND u.user_id NOT IN (SELECT user_id FROM fact_order)"
        ),
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.user_id",
            ["fact_order.user_id", "dws_user_summary.total_order_count"],
            "dim_user.user_name",
        ],
        tags=["难度:中等", "考点:否定集合"],
        note="行为表里有加购、订单表里没有任何订单的用户；也可用用户汇总表下单笔数为 0 判断，结果一致。",
    ),
    EvalCase(
        id="H6E06",
        query="从下单那一刻算起，72小时之内（含72小时）就提交了退款申请的退款记录一共有多少条？",
        reference_sql=(
            "SELECT COUNT(*) FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
            "WHERE (strftime('%s', r.apply_time) - strftime('%s', o.create_time)) <= 72 * 3600"
        ),
        must_hit_columns=["fact_refund.apply_time", "fact_order.create_time"],
        tags=["难度:中等", "考点:相对时间"],
        note="退款申请时间减下单时间不超过 72 小时；没有恰好等于 72 小时的记录，边界不影响结果；每笔订单最多一条退款记录。",
    ),
    EvalCase(
        id="H6E07",
        query="按全平台每天的销售额算（当天下的所有订单都算，包括后来取消的），哪一天比前一天跌得最多（按少了多少钱算，不按比例）？给出日期和比前一天少了多少钱，保留2位小数。",
        reference_sql=(
            "SELECT stat_date, ROUND(prev - g, 2) AS drop_amt FROM ("
            "SELECT stat_date, g, LAG(g) OVER (ORDER BY stat_date) AS prev FROM ("
            "SELECT stat_date, SUM(gmv) AS g FROM dws_shop_daily GROUP BY stat_date)) "
            "WHERE prev IS NOT NULL ORDER BY prev - g DESC LIMIT 1"
        ),
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "考点:窗口排名", "考点:两层聚合"],
        note="销售额即商品总金额（GMV），按下单日汇总全平台后与前一天比较；30 天每天都有订单，前一天即日历前一天；跌幅第一与第二相差约 1.1 万，不并列；按比例算会是另一天，所以题面写明按金额。店铺日汇总与订单表两条路径一致。",
    ),
    EvalCase(
        id="H6E08",
        query="商品评价里好评率最高的是哪款商品？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里没有商品评价、评分或好评数据，无法回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H6E09",
        query="有些用户只在一个渠道下过单、从来没在别的渠道下过（取消的订单不算，待支付的算下过单）。按这个唯一的下单渠道分，这些用户一共付了多少钱？付过款的订单都算，包括后来退款的，保留2位小数。",
        reference_sql=(
            "SELECT o.channel, ROUND(SUM(o.pay_amount), 2) FROM fact_order o "
            "WHERE o.pay_time IS NOT NULL AND o.user_id IN ("
            "SELECT user_id FROM fact_order WHERE order_status <> '已取消' "
            "GROUP BY user_id HAVING COUNT(DISTINCT channel) = 1) "
            "GROUP BY o.channel"
        ),
        must_hit_columns=[
            "fact_order.channel",
            "fact_order.order_status",
            "fact_order.user_id",
            ["fact_order.pay_amount", "fact_payment.pay_amount"],
        ],
        tags=["难度:中等", "考点:否定集合", "考点:两层聚合"],
        note="“只在一个渠道”先按用户数非取消订单的渠道种数筛选，再汇总这些用户付过款订单的实付金额；已付订单都不是取消状态，是否再排除取消不影响结果；用支付流水金额结果一致。",
    ),
    EvalCase(
        id="H6E10",
        query="在店铺类型为旗舰店的店里下单、并且用花呗分期付款的订单，按买家的会员等级分，各等级一共付了多少钱？保留2位小数。",
        reference_sql=(
            "SELECT u.member_level, ROUND(SUM(p.pay_amount), 2) FROM fact_payment p "
            "JOIN fact_order o ON o.order_id = p.order_id "
            "JOIN dim_user u ON u.user_id = o.user_id "
            "JOIN dim_shop s ON s.shop_id = o.shop_id "
            "WHERE p.pay_channel = '花呗分期' AND s.shop_type = '旗舰店' "
            "GROUP BY u.member_level"
        ),
        must_hit_columns=[
            "fact_payment.pay_channel",
            "dim_shop.shop_type",
            "dim_user.member_level",
            ["fact_payment.pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:中等", "考点:多表连接"],
        note="【存疑】多家店铺名称里带“旗舰店”但类型不是旗舰店（也有类型是旗舰店、名字里没有的），题面已写明按店铺类型，但仍可能被按店名模糊匹配。支付方式在支付流水表，店铺类型在店铺表，会员等级在用户表，共 4 张表；每笔已付订单恰有一条支付流水且金额与订单实付一致，两种金额口径结果相同。",
    ),
    EvalCase(
        id="H6E11",
        query="每种支付方式里，金额最大的那一笔付款是在哪家店铺下的单？列出支付方式、店铺名称和这笔付款的金额。",
        reference_sql=(
            "SELECT pay_channel, shop_name, pay_amount FROM ("
            "SELECT p.pay_channel, s.shop_name, p.pay_amount, "
            "RANK() OVER (PARTITION BY p.pay_channel ORDER BY p.pay_amount DESC) AS rk "
            "FROM fact_payment p JOIN fact_order o ON o.order_id = p.order_id "
            "JOIN dim_shop s ON s.shop_id = o.shop_id) WHERE rk = 1"
        ),
        must_hit_columns=[
            "fact_payment.pay_channel",
            ["fact_payment.pay_amount", "fact_order.pay_amount"],
            "dim_shop.shop_name",
        ],
        tags=["难度:中等", "考点:窗口排名"],
        note="每组取单笔金额最大的一条，各组第一名不并列；金额用支付流水或订单实付结果一致。",
    ),
    EvalCase(
        id="H6E12",
        query="哪些店铺平均每笔订单里包含的不同商品超过2款？所有订单都算。列出店铺名称和平均每单的商品款数，保留2位小数。",
        reference_sql=(
            "SELECT s.shop_name, ROUND(AVG(x.cnt), 2) FROM ("
            "SELECT order_id, COUNT(DISTINCT product_id) AS cnt FROM fact_order_item GROUP BY order_id) x "
            "JOIN fact_order o ON o.order_id = x.order_id JOIN dim_shop s ON s.shop_id = o.shop_id "
            "GROUP BY s.shop_id, s.shop_name HAVING AVG(x.cnt) > 2"
        ),
        must_hit_columns=[
            "fact_order_item.order_id",
            "fact_order_item.product_id",
            ["fact_order.shop_id", "dim_product.shop_id"],
            "dim_shop.shop_name",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先算每单不同商品款数再按店铺求平均（题面用“款”避免被理解成类目）；订单内无重复商品行，款数=明细行数；有一家店恰好平均 2.00（90/45），按“超过”不入选。",
    ),
    EvalCase(
        id="H6E13",
        query="看每位用户最近的一笔订单（按下单时间），这笔订单现在还是待支付状态的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            "SELECT order_status, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time DESC) AS rn "
            "FROM fact_order) WHERE rn = 1 AND order_status = '待支付'"
        ),
        must_hit_columns=[
            "fact_order.order_status",
            ["fact_order.create_time", "dws_user_summary.last_order_time"],
        ],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="每位用户最后一笔订单按下单时间取，用户内下单时间无重复；也可用用户汇总表的最近下单时间回连订单表，结果一致（17）。",
    ),
    EvalCase(
        id="H6E14",
        query="目前不在正常营业的店铺（休假中的和已关店的），5月份卖出去的商品按品牌算各卖了多少件？取消的订单不算。列出店铺名称、品牌和件数。",
        reference_sql=(
            "SELECT s.shop_name, p.brand, SUM(i.quantity) FROM fact_order o "
            "JOIN dim_shop s ON s.shop_id = o.shop_id "
            "JOIN fact_order_item i ON i.order_id = o.order_id "
            "JOIN dim_product p ON p.product_id = i.product_id "
            "WHERE s.shop_status IN ('休假中', '已关店') AND o.order_status <> '已取消' "
            "GROUP BY s.shop_id, s.shop_name, p.brand"
        ),
        must_hit_columns=[
            "dim_shop.shop_status",
            "dim_shop.shop_name",
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.brand",
        ],
        tags=["难度:中等", "考点:多表连接"],
        note="店铺营业状态筛选后经订单、明细、商品取品牌，共 4 张表；件数=数量求和；同一品牌在不同店铺各算各的（按店铺+品牌分组）。",
    ),
    EvalCase(
        id="H6E15",
        query="臻品旗舰店4 在5月份的销售额（当天所有订单都算，包括取消的）按天往上累加，是在哪一天累计第一次超过50万元的？",
        reference_sql=(
            "SELECT stat_date FROM ("
            "SELECT d.stat_date, SUM(d.gmv) OVER (ORDER BY d.stat_date) AS cum "
            "FROM dws_shop_daily d JOIN dim_shop s ON s.shop_id = d.shop_id "
            "WHERE s.shop_name = '臻品旗舰店4') WHERE cum > 500000 ORDER BY stat_date LIMIT 1"
        ),
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "考点:窗口排名", "考点:相对时间"],
        note="累计销售额（GMV）首次超过 50 万的日期；前一个有订单的日子累计约 48.7 万，当天约 51.7 万，离阈值都不近。店铺日汇总与订单表两条路径一致。",
    ),
    EvalCase(
        id="H6E16",
        query="在5家及以上不同店铺下过单的用户，按会员等级分各有多少位？取消的订单不算。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*) FROM ("
            "SELECT user_id FROM fact_order WHERE order_status <> '已取消' "
            "GROUP BY user_id HAVING COUNT(DISTINCT shop_id) >= 5) x "
            "JOIN dim_user u ON u.user_id = x.user_id GROUP BY u.member_level"
        ),
        must_hit_columns=["fact_order.shop_id", "fact_order.order_status", "dim_user.member_level"],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按用户数不同店铺数并筛选，再按会员等级计数。",
    ),
    EvalCase(
        id="H6E17",
        query="用户在 APP 里搜索次数最多的关键词是哪几个？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="行为表只有浏览、加购、收藏，没有搜索记录和关键词，无法回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H6E18",
        query="对下过至少两单的用户，按下单时间排（不管订单状态），第二单是在第一单之后72小时以内（含72小时）下的，这样的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            "SELECT create_time, LAG(create_time) OVER (PARTITION BY user_id ORDER BY create_time) AS prev, "
            "ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time) AS rn FROM fact_order) "
            "WHERE rn = 2 AND (strftime('%s', create_time) - strftime('%s', prev)) <= 72 * 3600"
        ),
        must_hit_columns=["fact_order.create_time", "fact_order.user_id"],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="每位用户第 1、2 单的间隔；没有恰好等于 72 小时的情况，边界不影响结果。",
    ),
    EvalCase(
        id="H6E19",
        query="退款成功的那些退款，按退款原因分，平均从申请到退款完成花了几天？保留1位小数。",
        reference_sql=(
            "SELECT refund_reason, ROUND(AVG(julianday(finish_time) - julianday(apply_time)), 1) "
            "FROM fact_refund WHERE refund_status = '退款成功' GROUP BY refund_reason"
        ),
        must_hit_columns=[
            "fact_refund.refund_reason",
            "fact_refund.refund_status",
            "fact_refund.apply_time",
            "fact_refund.finish_time",
        ],
        tags=["难度:简单"],
        note="每条退款的处理时长都是整天数，各组平均值不在四舍五入边界上。",
    ),
    EvalCase(
        id="H6E20",
        query="钻石会员里，消费总额最高的前3位用户是谁？消费总额指付过款的订单都算（包括后来退款的）。列出昵称和消费总额。",
        reference_sql=(
            "SELECT u.user_name, s.total_pay_amount FROM dws_user_summary s "
            "JOIN dim_user u ON u.user_id = s.user_id "
            "WHERE u.member_level = '钻石会员' ORDER BY s.total_pay_amount DESC LIMIT 3"
        ),
        must_hit_columns=[
            "dim_user.member_level",
            "dim_user.user_name",
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:简单"],
        note="用户汇总表的累计实付金额即消费总额；按订单表对已支付订单实付求和结果一致；第3、4名（57473.63 / 53225.95）不并列。",
    ),
    EvalCase(
        id="H6E21",
        query="因为「商品质量问题」申请过退款的订单（不管退款有没有办完），里面的商品涉及哪些一级类目？每个一级类目涉及多少笔这样的订单？一笔订单在同一个类目下只算一次。",
        reference_sql=(
            "SELECT c1.category_name, COUNT(DISTINCT r.order_id) FROM fact_refund r "
            "JOIN fact_order_item i ON i.order_id = r.order_id "
            + _L1_JOIN +
            "WHERE r.refund_reason = '商品质量问题' GROUP BY c1.category_id, c1.category_name"
        ),
        must_hit_columns=[
            "fact_refund.refund_reason",
            "fact_order_item.product_id",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="退款表、明细、商品、类目（自连接）共 4 张表；按订单去重计数；每笔订单最多一条退款记录。",
    ),
    EvalCase(
        id="H6E22",
        query="每家店铺在5月份销售额最高的是哪一天？销售额按当天所有订单算，包括取消的。列出店铺名称、日期和当天销售额。",
        reference_sql=(
            "SELECT shop_name, stat_date, gmv FROM ("
            "SELECT s.shop_name, d.stat_date, d.gmv, "
            "RANK() OVER (PARTITION BY d.shop_id ORDER BY d.gmv DESC) AS rk "
            "FROM dws_shop_daily d JOIN dim_shop s ON s.shop_id = d.shop_id) WHERE rk = 1"
        ),
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:中等", "考点:窗口排名"],
        note="每店取单日 GMV 最高的一天，15 家店各一行，无并列；店铺日汇总与订单表按下单日汇总两条路径一致。",
    ),
    EvalCase(
        id="H6E23",
        query="用户浏览不同一级大类的商品时，平均每次停留多少秒？只看浏览，不算加购和收藏，保留1位小数。",
        reference_sql=(
            "SELECT c1.category_name, ROUND(AVG(b.stay_seconds), 1) FROM fact_user_behavior b "
            "JOIN dim_product p ON p.product_id = b.product_id "
            "JOIN dim_category c2 ON c2.category_id = p.category_id "
            "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
            "WHERE b.behavior_type = '浏览' GROUP BY c1.category_id, c1.category_name"
        ),
        must_hit_columns=[
            "fact_user_behavior.stay_seconds",
            "fact_user_behavior.behavior_type",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:中等"],
        note="行为表经商品、二级类目上卷到一级类目，只取浏览行为求平均停留秒数。",
    ),
    EvalCase(
        id="H6E24",
        query="用户把一件商品加购之后，168小时以内（含）又下单买了这件商品（取消的订单不算），这样的加购记录有多少条？",
        reference_sql=(
            "SELECT COUNT(*) FROM fact_user_behavior b WHERE b.behavior_type = '加购' AND EXISTS ("
            "SELECT 1 FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
            "WHERE o.user_id = b.user_id AND i.product_id = b.product_id AND o.order_status <> '已取消' "
            "AND (strftime('%s', o.create_time) - strftime('%s', b.behavior_time)) BETWEEN 0 AND 168 * 3600)"
        ),
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.behavior_time",
            "fact_user_behavior.product_id",
            "fact_order.create_time",
            "fact_order.order_status",
            "fact_order_item.product_id",
        ],
        tags=["难度:难", "考点:相对时间"],
        note="【存疑】时间窗口按精确的 168 小时计，若被理解成按自然日“7天内”会得到 20。同一用户、同一商品，下单时间落在加购后 0~168 小时内的加购记录条数（按加购记录计，不按订单计）；收紧到开区间、按（用户,商品）去重、按命中订单计数，结果都是 17。",
    ),
    EvalCase(
        id="H6E25",
        query="直播间渠道下的订单里，包邮（没收运费）的有多少笔？取消的不算。",
        reference_sql=(
            "SELECT COUNT(*) FROM fact_order "
            "WHERE channel = '直播间' AND freight_amount = 0 AND order_status <> '已取消'"
        ),
        must_hit_columns=["fact_order.channel", "fact_order.freight_amount", "fact_order.order_status"],
        tags=["难度:简单"],
        note="包邮即运费为 0；渠道是下单渠道。",
    ),
    EvalCase(
        id="H6E26",
        query="直播间里哪位主播带货的成交额最高？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="只有“直播间”这个下单渠道，没有主播信息，无法按主播统计。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H6E27",
        query="同时在 APP 和直播间都下过单（取消的不算）、但从来没有过退款的用户有多少位？只要申请过退款就算有过，不管退款办没办完。",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            "SELECT user_id FROM fact_order WHERE order_status <> '已取消' GROUP BY user_id "
            "HAVING SUM(channel = 'APP') > 0 AND SUM(channel = '直播间') > 0) x "
            "WHERE x.user_id NOT IN (SELECT o.user_id FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id)"
        ),
        must_hit_columns=[
            "fact_order.channel",
            "fact_order.order_status",
            ["fact_refund.order_id", "dws_user_summary.refund_order_count"],
        ],
        tags=["难度:难", "考点:否定集合"],
        note="“同时”+“从没”；退款记录、订单状态“已退款”、用户汇总表退款订单数三条路径结果一致（37）。",
    ),
    EvalCase(
        id="H6E28",
        query="5月里，哪些店铺出现过至少3天“当天下单的买家一个都没付款”的情况？列出店铺名称。",
        reference_sql=(
            "SELECT s.shop_name FROM dws_shop_daily d JOIN dim_shop s ON s.shop_id = d.shop_id "
            "WHERE d.conversion_rate = 0 GROUP BY s.shop_id, s.shop_name HAVING COUNT(*) >= 3"
        ),
        must_hit_columns=[
            ["dws_shop_daily.conversion_rate", "fact_order.pay_time", "fact_order.order_status"],
            "dim_shop.shop_name",
        ],
        tags=["难度:难", "考点:两层聚合"],
        note="当天支付转化率为 0 即有下单但无人付款；也可按订单表店铺+下单日汇总，已付订单数为 0 的天数≥3，结果一致（4 家）。",
    ),
    EvalCase(
        id="H6E29",
        query="按用户的注册渠道分，每个渠道里消费总额排前两名的用户是谁？消费总额指付过款的订单都算（包括后来退款的）。列出注册渠道、用户昵称和消费总额。",
        reference_sql=(
            "SELECT register_channel, user_name, total_pay_amount FROM ("
            "SELECT u.register_channel, u.user_name, s.total_pay_amount, "
            "RANK() OVER (PARTITION BY u.register_channel ORDER BY s.total_pay_amount DESC) AS rk "
            "FROM dws_user_summary s JOIN dim_user u ON u.user_id = s.user_id) WHERE rk <= 2"
        ),
        must_hit_columns=[
            "dim_user.register_channel",
            "dim_user.user_name",
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:中等", "考点:窗口排名"],
        note="注册渠道而非下单渠道；各渠道第2、第3名不并列；用户汇总表与订单表聚合结果一致。",
    ),
    EvalCase(
        id="H6E30",
        query="买过东西的用户里（只看已完成和已支付这两种状态的订单），从来没买过食品生鲜大类商品的有多少位？按会员等级分别列出人数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*) FROM dim_user u "
            "WHERE u.user_id IN (SELECT user_id FROM fact_order WHERE order_status IN ('已完成', '已支付')) "
            "AND u.user_id NOT IN ("
            "SELECT o.user_id FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
            "JOIN dim_product p ON p.product_id = i.product_id "
            "JOIN dim_category c2 ON c2.category_id = p.category_id "
            "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
            "WHERE c1.category_name = '食品生鲜' AND o.order_status IN ('已完成', '已支付')) "
            "GROUP BY u.member_level"
        ),
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order_item.product_id",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
            "dim_user.member_level",
        ],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="“买过”和“没买过”都只看已完成、已支付订单；食品生鲜是一级类目，商品挂二级类目，需经父类目判断；用户、订单、明细、商品、类目共 5 张表。",
    ),
]

HOLDOUT6_CHINOOK_CASES = [
    EvalCase(
        id="H6C01",
        query="Heavy Metal Classic 这个歌单里收录的曲目，按艺术家算各卖了多少钱？列出艺术家和销售额，保留2位小数。",
        reference_sql=(
            "SELECT ar.Name, ROUND(SUM(il.UnitPrice * il.Quantity), 2) FROM Playlist p "
            "JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId "
            "JOIN Track t ON t.TrackId = pt.TrackId "
            "JOIN Album al ON al.AlbumId = t.AlbumId "
            "JOIN Artist ar ON ar.ArtistId = al.ArtistId "
            "JOIN InvoiceLine il ON il.TrackId = t.TrackId "
            "WHERE p.Name = 'Heavy Metal Classic' GROUP BY ar.ArtistId, ar.Name"
        ),
        must_hit_columns=[
            "Playlist.Name",
            "PlaylistTrack.TrackId",
            "Track.AlbumId",
            "Album.ArtistId",
            "Artist.Name",
            "InvoiceLine.UnitPrice",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="歌单—收录—曲目—专辑—艺术家—发票明细 6 张表；歌单名唯一；按曲目拆销售额只能用明细成交单价×数量；只列有销售的艺术家。",
    ),
    EvalCase(
        id="H6C02",
        query="在 Rock、Metal、Blues、Latin 这四个流派里，各自卖出份数最多的前两位艺术家是谁？列出流派、艺术家和卖出的份数。",
        reference_sql=(
            "SELECT genre, artist, n FROM ("
            "SELECT g.Name AS genre, ar.Name AS artist, SUM(il.Quantity) AS n, "
            "RANK() OVER (PARTITION BY g.GenreId ORDER BY SUM(il.Quantity) DESC) AS rk "
            "FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId "
            "JOIN Genre g ON g.GenreId = t.GenreId "
            "JOIN Album al ON al.AlbumId = t.AlbumId "
            "JOIN Artist ar ON ar.ArtistId = al.ArtistId "
            "WHERE g.Name IN ('Rock', 'Metal', 'Blues', 'Latin') "
            "GROUP BY g.GenreId, g.Name, ar.ArtistId, ar.Name) WHERE rk <= 2"
        ),
        must_hit_columns=[
            "Genre.Name",
            "Artist.Name",
            "Album.ArtistId",
            "Track.AlbumId",
            "InvoiceLine.TrackId",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接"],
        note="按流派分组取艺术家销量前 2，四个流派第2、第3名都不并列（Metal 第3名并列但不影响前 2）；份数=明细数量求和（均为 1）。",
    ),
    EvalCase(
        id="H6C03",
        query="按开票月份看销售额，哪些月份比上一个月卖得少？列出月份（年-月）和比上个月少了多少，保留2位小数。第一个有销售的月份不用比较。",
        reference_sql=(
            "SELECT m, ROUND(prev - s, 2) FROM ("
            "SELECT m, s, LAG(s) OVER (ORDER BY m) AS prev FROM ("
            "SELECT strftime('%Y-%m', InvoiceDate) AS m, SUM(Total) AS s FROM Invoice GROUP BY 1)) "
            "WHERE prev IS NOT NULL AND ROUND(prev - s, 2) > 0"
        ),
        must_hit_columns=[["Invoice.Total", "InvoiceLine.UnitPrice"], "Invoice.InvoiceDate"],
        tags=["难度:难", "考点:窗口排名", "考点:相对时间"],
        note="月度销售额环比；60 个月连续都有销售，上一条即日历上一个月；很多月份金额相同，比较时按 2 位小数取差，避免浮点误差把持平算成下降。用明细单价×数量汇总结果一致。",
    ),
    EvalCase(
        id="H6C04",
        query="名下有专辑、但一首曲目都没卖出去过的艺术家有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM Artist a "
            "WHERE a.ArtistId IN (SELECT ArtistId FROM Album) "
            "AND a.ArtistId NOT IN (SELECT al.ArtistId FROM InvoiceLine il "
            "JOIN Track t ON t.TrackId = il.TrackId JOIN Album al ON al.AlbumId = t.AlbumId)"
        ),
        must_hit_columns=["Album.ArtistId", "Track.AlbumId", "InvoiceLine.TrackId"],
        tags=["难度:中等", "考点:否定集合"],
        note="限定有专辑的艺术家（另有 71 位没有专辑，不计入）；销量看发票明细而非歌单收录。",
    ),
    EvalCase(
        id="H6C05",
        query="Grunge 这个歌单里，哪些曲目从来没有卖出去过？列出曲目名称。",
        reference_sql=(
            "SELECT t.Name FROM Playlist p JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId "
            "JOIN Track t ON t.TrackId = pt.TrackId "
            "WHERE p.Name = 'Grunge' AND t.TrackId NOT IN (SELECT TrackId FROM InvoiceLine)"
        ),
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Track.Name", "InvoiceLine.TrackId"],
        tags=["难度:中等", "考点:否定集合"],
        note="歌单名 Grunge 唯一；歌单内 15 首曲目名称互不相同；“卖出去”看发票明细。",
    ),
    EvalCase(
        id="H6C06",
        query="哪些客户的消费总额高于跟他同一个国家（按客户登记的国家）的客户的平均消费总额？列出客户的名和姓。",
        reference_sql=(
            "WITH cs AS (SELECT c.CustomerId, c.FirstName, c.LastName, c.Country, SUM(i.Total) AS s "
            "FROM Customer c JOIN Invoice i ON i.CustomerId = c.CustomerId "
            "GROUP BY c.CustomerId, c.FirstName, c.LastName, c.Country), "
            "ca AS (SELECT Country, AVG(s) AS a FROM cs GROUP BY Country) "
            "SELECT cs.FirstName, cs.LastName FROM cs JOIN ca ON ca.Country = cs.Country "
            "WHERE ROUND(cs.s, 2) > ROUND(ca.a, 2)"
        ),
        must_hit_columns=[
            "Customer.Country",
            "Customer.FirstName",
            "Customer.LastName",
            ["Invoice.Total", "InvoiceLine.UnitPrice"],
        ],
        tags=["难度:难", "考点:两层聚合"],
        note="先算客户消费总额，再按客户国家求平均并比较；所有客户都有购买记录；与平均值相等的客户（单人国家、同额国家）不算高于，比较按 2 位小数避免浮点误差；用 Customer.Country 而非开票国家（本库两者一致）。",
    ),
    EvalCase(
        id="H6C07",
        query="2024年一共有多少张发票后来被客户申请退款了？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里没有退款、退货或发票状态信息，无法回答。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H6C08",
        query="比较每位客户最后一次和第一次购买的发票金额，最后一次比第一次花得多的客户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            "SELECT CustomerId, "
            "MAX(CASE WHEN rf = 1 THEN Total END) AS first_total, "
            "MAX(CASE WHEN rl = 1 THEN Total END) AS last_total FROM ("
            "SELECT CustomerId, Total, "
            "ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate) AS rf, "
            "ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate DESC) AS rl "
            "FROM Invoice) GROUP BY CustomerId) WHERE last_total > first_total"
        ),
        must_hit_columns=["Invoice.CustomerId", "Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名"],
        note="首次、最近一次都按开票日期取，同一客户没有同日两张发票，首末唯一。",
    ),
    EvalCase(
        id="H6C09",
        query="有多少张专辑，专辑里的每一首曲目都至少卖出去过一次？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            "SELECT t.AlbumId FROM Track t GROUP BY t.AlbumId "
            "HAVING SUM(CASE WHEN t.TrackId IN (SELECT TrackId FROM InvoiceLine) THEN 0 ELSE 1 END) = 0)"
        ),
        must_hit_columns=["Track.AlbumId", "InvoiceLine.TrackId"],
        tags=["难度:难", "考点:两层聚合", "考点:否定集合"],
        note="“全部都卖过”=不存在没卖过的曲目；每张专辑都有曲目，不会出现空专辑被误算。",
    ),
    EvalCase(
        id="H6C10",
        query="每位客户第一次购买的那张发票里买了几首曲目？按买的曲目数分组，看看各有多少位客户。列出曲目数和客户数。",
        reference_sql=(
            "SELECT n, COUNT(*) FROM ("
            "SELECT i.CustomerId, "
            "(SELECT COUNT(*) FROM InvoiceLine il WHERE il.InvoiceId = i.InvoiceId) AS n, "
            "ROW_NUMBER() OVER (PARTITION BY i.CustomerId ORDER BY i.InvoiceDate) AS rn "
            "FROM Invoice i) WHERE rn = 1 GROUP BY n"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.CustomerId", "InvoiceLine.InvoiceId"],
        tags=["难度:难", "考点:相对时间", "考点:两层聚合"],
        note="首单按开票日期取（同一客户没有同日两张发票）；先算首张发票的明细行数，再按行数分组数客户；明细数量都是 1，按数量求和结果一致。",
    ),
    EvalCase(
        id="H6C11",
        query="每种媒体文件格式的曲目，平均时长是多少分钟？保留2位小数。",
        reference_sql=(
            "SELECT m.Name, ROUND(AVG(t.Milliseconds) / 60000.0, 2) FROM Track t "
            "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["MediaType.Name", "Track.Milliseconds", "Track.MediaTypeId"],
        tags=["难度:简单"],
        note="时长单位毫秒，换算成分钟；媒体格式名唯一。",
    ),
    EvalCase(
        id="H6C12",
        query="没有登记作曲者的那些曲目，按音乐流派分，各卖出去多少份？只列有销量的流派，列出流派和份数。",
        reference_sql=(
            "SELECT g.Name, SUM(il.Quantity) FROM Track t "
            "JOIN InvoiceLine il ON il.TrackId = t.TrackId "
            "JOIN Genre g ON g.GenreId = t.GenreId "
            "WHERE t.Composer IS NULL GROUP BY g.GenreId, g.Name"
        ),
        must_hit_columns=["Track.Composer", "Track.GenreId", "Genre.Name", "InvoiceLine.TrackId"],
        tags=["难度:中等"],
        note="作曲者为空即未登记（库里没有空字符串，只有 NULL）；份数=明细数量求和（均为 1），按明细计数一致；内连接自然只留下有销量的流派。",
    ),
    EvalCase(
        id="H6C13",
        query="第一次购买之后，不到60天就买了第二次的客户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            "SELECT InvoiceDate, LAG(InvoiceDate) OVER (PARTITION BY CustomerId ORDER BY InvoiceDate) AS prev, "
            "ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate) AS rn FROM Invoice) "
            "WHERE rn = 2 AND julianday(InvoiceDate) - julianday(prev) < 60"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.CustomerId"],
        tags=["难度:中等", "考点:相对时间", "考点:窗口排名"],
        note="首单与第二单的间隔只有 41、94、233 天等少数取值，离 60 天很远，含不含边界都一样。",
    ),
    EvalCase(
        id="H6C14",
        query="听众打分最高的10首曲目是哪些？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="库里没有任何评分、打分或评论数据，无法回答；销量或歌单收录次数不是评分。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H6C15",
        query="2023年7月1日到12月31日（两头都算）一次都没买过东西的客户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM Customer WHERE CustomerId NOT IN ("
            "SELECT CustomerId FROM Invoice WHERE date(InvoiceDate) BETWEEN '2023-07-01' AND '2023-12-31')"
        ),
        must_hit_columns=["Customer.CustomerId", "Invoice.CustomerId", "Invoice.InvoiceDate"],
        tags=["难度:中等", "考点:否定集合"],
        note="时间段由题面给定；从全部客户中排除该期间有发票的客户。",
    ),
    EvalCase(
        id="H6C16",
        query="直接向 Nancy Edwards 汇报的那几位员工，各自负责的客户在2025年一共开了多少钱的发票？列出员工的名、姓和金额，保留2位小数。",
        reference_sql=(
            "SELECT e.FirstName, e.LastName, ROUND(SUM(i.Total), 2) FROM Employee m "
            "JOIN Employee e ON e.ReportsTo = m.EmployeeId "
            "JOIN Customer c ON c.SupportRepId = e.EmployeeId "
            "JOIN Invoice i ON i.CustomerId = c.CustomerId "
            "WHERE m.FirstName = 'Nancy' AND m.LastName = 'Edwards' "
            "AND strftime('%Y', i.InvoiceDate) = '2025' "
            "GROUP BY e.EmployeeId, e.FirstName, e.LastName"
        ),
        must_hit_columns=[
            "Employee.ReportsTo",
            "Customer.SupportRepId",
            ["Invoice.Total", "InvoiceLine.UnitPrice"],
            "Invoice.InvoiceDate",
            "Employee.FirstName",
            "Employee.LastName",
        ],
        tags=["难度:中等"],
        note="员工表自连接找直接下属，再经客户的专属销售关联发票；只算直接下属。",
    ),
    EvalCase(
        id="H6C17",
        query="名下有5张及以上专辑的艺术家，他们的曲目一共各卖出去多少份？列出艺术家和卖出的份数。",
        reference_sql=(
            "SELECT ar.Name, SUM(il.Quantity) FROM Artist ar "
            "JOIN Album al ON al.ArtistId = ar.ArtistId "
            "JOIN Track t ON t.AlbumId = al.AlbumId "
            "JOIN InvoiceLine il ON il.TrackId = t.TrackId "
            "WHERE ar.ArtistId IN (SELECT ArtistId FROM Album GROUP BY ArtistId HAVING COUNT(*) >= 5) "
            "GROUP BY ar.ArtistId, ar.Name"
        ),
        must_hit_columns=["Album.ArtistId", "Artist.Name", "Track.AlbumId", "InvoiceLine.TrackId"],
        tags=["难度:中等", "考点:两层聚合", "考点:多表连接"],
        note="先按艺术家数专辑并筛选，再汇总其曲目销量；专辑数要在单独的汇总里算，直接连明细后数专辑会被放大；份数=明细数量求和（均为 1）；连接 4 张表。",
    ),
    EvalCase(
        id="H6C18",
        query="Classical 这个歌单里收录的曲目，按文件格式分，各有几首？",
        reference_sql=(
            "SELECT m.Name, COUNT(*) FROM Playlist p "
            "JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId "
            "JOIN Track t ON t.TrackId = pt.TrackId "
            "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
            "WHERE p.Name = 'Classical' GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Track.MediaTypeId", "MediaType.Name"],
        tags=["难度:中等", "考点:多表连接"],
        note="是歌单 Classical（唯一，不含 Classical 101 系列），不是流派 Classical；文件格式是媒体格式。",
    ),
    EvalCase(
        id="H6C19",
        query="每一年里，销售额排前两名的音乐流派是哪两个？列出年份、流派和销售额，保留2位小数。",
        reference_sql=(
            "SELECT y, genre, s FROM ("
            "SELECT strftime('%Y', i.InvoiceDate) AS y, g.Name AS genre, "
            "ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS s, "
            "RANK() OVER (PARTITION BY strftime('%Y', i.InvoiceDate) "
            "ORDER BY ROUND(SUM(il.UnitPrice * il.Quantity), 2) DESC) AS rk "
            "FROM Invoice i JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId "
            "JOIN Track t ON t.TrackId = il.TrackId JOIN Genre g ON g.GenreId = t.GenreId "
            "GROUP BY 1, g.GenreId, g.Name) WHERE rk <= 2"
        ),
        must_hit_columns=[
            "Invoice.InvoiceDate",
            "InvoiceLine.UnitPrice",
            "InvoiceLine.TrackId",
            "Track.GenreId",
            "Genre.Name",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接"],
        note="按流派拆销售额只能用明细成交单价×数量（发票总额无法拆到流派）；各年第2、第3名不并列（2025 年第3名并列不影响前 2）。",
    ),
    EvalCase(
        id="H6C20",
        query="来自英国的艺术家一共卖出了多少首曲目？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["陷阱题"],
        note="艺术家表只有名称，没有国籍或所在国家；客户/开票国家不是艺术家的国籍，无法回答。",
        expect_unanswerable=True,
    ),
]
