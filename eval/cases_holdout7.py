"""
第七套留出评测集：更难的一套（规范同第六套）。由独立出题人在未见过被测系统表现和已有题目的情况下编写。
ecommerce 30 题（H7E01–H7E30，陷阱 3），Chinook 20 题（H7C01–H7C20，陷阱 3）。

**已用过一次。**这套题于 927e51b 冻结并推送后第一次运行，三个版本一起跑，都用冻结时的
评测器判分，结果见 docs/实验记录.md「第七套留出集：第六套之后的改动在陌生难题上」：

    版本                                          ecommerce   Chinook   运行通过（90 + 60）
    1d7781b  第六套封存时的状态                     24/30       18/20     74 + 52
    e5f80e8  再加每组前 N、窗口函数规则、报错分析     27/30       20/20     80 + 59
    927e51b  再加修正最多 2 次、结果形状检查         27/30       19/20     77 + 57
    927e51b  压测库（ecommerce_big）                27/30       —         81

1d7781b → e5f80e8 逐题 12 道变好、0 道变差（两个库各 6 / 0，p≈0.03）：每组前 N 被丢掉 6 → 0、
两层压成一层 2 → 0。e5f80e8 → 927e51b 在波动范围内：第二次修正一次都没用到，形状检查触发 1 次。
没有发现可证明没法判分的题，冻结版就是最终版。

出题规范逐字沿用第六套的（eval/blind_materials/出题规范_第六套.md），只换了题号和文件名：题面用业务说法、
不点字段，至少一半的非陷阱题要多表连接、两层聚合、窗口排名、相对时间或否定集合。第六套之后的几处改动
正是对着第六套的失败形态做的，这一套用同一份规范，测的是它们在同一类陌生题上灵不灵。材料（数据字典、
两个库）逐字沿用 eval/blind_materials/；不读 README、docs/、eval/ 已有题目和 git 历史，不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本完成，只输出题号和检查项；
出题人的回报里也不含题目内容。组装进仓库时只换了导入、加了这段文件头。

候选路径的验证 SQL 在 eval/cases_holdout7_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

第七套盲写评测题（holdout7）：ecommerce 30 题，chinook 20 题。
"""

from eval.cases import EvalCase

TRAP_SQL = "SELECT 1 WHERE 0"

HOLDOUT7_ECOMMERCE_CASES = [
    EvalCase(
        id="H7E01",
        query="钻石会员买的数码电器，按小类（手机通讯、电脑办公、家用电器这一层）看各卖出去多少件？已取消和待支付的订单不算。列出小类名称和件数。",
        reference_sql=(
            "SELECT c.category_name, SUM(i.quantity) AS qty "
            "FROM fact_order_item i "
            "JOIN fact_order o ON o.order_id = i.order_id "
            "JOIN dim_user u ON u.user_id = o.user_id "
            "JOIN dim_product p ON p.product_id = i.product_id "
            "JOIN dim_category c ON c.category_id = p.category_id "
            "JOIN dim_category pc ON pc.category_id = c.parent_category_id "
            "WHERE u.member_level = '钻石会员' AND pc.category_name = '数码电器' "
            "AND o.order_status NOT IN ('已取消', '待支付') "
            "GROUP BY c.category_id, c.category_name"
        ),
        must_hit_columns=[
            "dim_user.member_level",
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="用户-订单-明细-商品-二级类目-一级类目六表连接；销量按件数求和；排除已取消、待支付两种状态，其余三种状态都算。",
    ),
    EvalCase(
        id="H7E02",
        query="每种店铺类型里，哪家店收到的实付金额最多？列出店铺类型、店铺名和金额，保留两位小数。只要付过款的订单都算，后来退款的也算进去。",
        reference_sql=(
            "SELECT shop_type, shop_name, amt FROM ("
            "SELECT s.shop_type, s.shop_name, ROUND(SUM(o.pay_amount), 2) AS amt, "
            "RANK() OVER (PARTITION BY s.shop_type ORDER BY SUM(o.pay_amount) DESC) AS rk "
            "FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id "
            "WHERE o.pay_time IS NOT NULL "
            "GROUP BY s.shop_id, s.shop_type, s.shop_name) t WHERE rk = 1"
        ),
        must_hit_columns=[
            "dim_shop.shop_type",
            "dim_shop.shop_name",
            ["fact_order.pay_amount", "dws_shop_daily.pay_amount"],
        ],
        tags=["难度:难", "考点:窗口排名"],
        note="店铺类型看 shop_type 而不是店名里的字样（店名与类型不一致）；付过款=有支付时间（已完成、已支付、已退款），与店铺日汇总的实付金额口径一致，两条路径结果相同；每组第一名无并列。",
    ),
    EvalCase(
        id="H7E03",
        query="有多少用户在第一次下单之后的 7 天内又下了单？按下单日期算：和第一单同一天再下的不算，第 7 天当天下的算。订单状态不限。",
        reference_sql=(
            "WITH f AS (SELECT user_id, MIN(date(create_time)) AS d FROM fact_order GROUP BY user_id) "
            "SELECT COUNT(DISTINCT f.user_id) FROM f JOIN fact_order o ON o.user_id = f.user_id "
            "AND julianday(date(o.create_time)) - julianday(f.d) BETWEEN 1 AND 7"
        ),
        must_hit_columns=["fact_order.user_id", "fact_order.create_time"],
        tags=["难度:难", "考点:相对时间"],
        note="基准是每个用户自己的首单日期；按日期差 1 到 7 天（含）判断，首单当天的其他订单不算，题面已交代两端。",
    ),
    EvalCase(
        id="H7E04",
        query="按每个用户最近一次下单走的是哪个渠道来分，各渠道分别有多少个用户？不管订单状态，最近一次按下单时间算。",
        reference_sql=(
            "SELECT channel, COUNT(*) AS users FROM ("
            "SELECT user_id, channel, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time DESC) AS rn "
            "FROM fact_order) t WHERE rn = 1 GROUP BY channel"
        ),
        must_hit_columns=[
            "fact_order.channel",
            ["fact_order.create_time", "dws_user_summary.last_order_time"],
        ],
        tags=["难度:中等", "考点:相对时间"],
        note="每个用户取下单时间最晚的一笔订单的下单渠道；同一用户没有同一时刻的两笔订单，最近一单唯一；也可用用户汇总表的最近下单时间去对订单，结果相同。",
    ),
    EvalCase(
        id="H7E05",
        query="每家店铺分别有多少用户把这家店的商品加进过购物车，却从来没在这家店下过一单？订单状态不限，列出店铺名和用户数。",
        reference_sql=(
            "SELECT s.shop_name, COUNT(DISTINCT b.user_id) AS users FROM fact_user_behavior b "
            "JOIN dim_product p ON p.product_id = b.product_id "
            "JOIN dim_shop s ON s.shop_id = p.shop_id "
            "WHERE b.behavior_type = '加购' AND NOT EXISTS ("
            "SELECT 1 FROM fact_order o WHERE o.user_id = b.user_id AND o.shop_id = p.shop_id) "
            "GROUP BY s.shop_id, s.shop_name"
        ),
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.product_id",
            "dim_product.shop_id",
            "fact_order.shop_id",
            "fact_order.user_id",
            "dim_shop.shop_name",
        ],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="行为-商品-店铺-订单四表；按店铺判断“加购过该店商品且在该店没有任何订单”的用户并去重计数；在别的店下过单不影响。",
    ),
    EvalCase(
        id="H7E06",
        query="只看已完成的订单，有些用户买的东西全都来自同一个一级类目（美妆护肤、数码电器、食品生鲜这一层）。按这个一级类目分，这样的用户各有多少个？",
        reference_sql=(
            "WITH t AS (SELECT DISTINCT o.user_id, pc.category_name AS l1 "
            "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
            "JOIN dim_product p ON p.product_id = i.product_id "
            "JOIN dim_category c ON c.category_id = p.category_id "
            "JOIN dim_category pc ON pc.category_id = c.parent_category_id "
            "WHERE o.order_status = '已完成') "
            "SELECT l1, COUNT(*) AS users FROM (SELECT user_id, MIN(l1) AS l1 FROM t GROUP BY user_id "
            "HAVING COUNT(DISTINCT l1) = 1) x GROUP BY l1"
        ),
        must_hit_columns=[
            "fact_order.order_status",
            ["dim_product.category_id", "dim_shop.main_category_id"],
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="“只买过一个一级类目”：先把用户在已完成订单里买过的一级类目去重，再筛只有一个的用户，按该类目计数；没有已完成订单的用户不在范围内。本库每家店的商品都属于其主营类目，走店铺主营类目路径结果相同。",
    ),
    EvalCase(
        id="H7E07",
        query="每家店铺从 5 月 1 日起把每天的成交额往上累加，分别是哪一天第一次累计到 30 万（含 30 万）？列出店铺名和那一天的日期。",
        reference_sql=(
            "WITH c AS (SELECT shop_id, stat_date, "
            "SUM(gmv) OVER (PARTITION BY shop_id ORDER BY stat_date) AS cum FROM dws_shop_daily) "
            "SELECT s.shop_name, MIN(c.stat_date) AS reach_date FROM c JOIN dim_shop s ON s.shop_id = c.shop_id "
            "WHERE c.cum >= 300000 GROUP BY c.shop_id, s.shop_name"
        ),
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "考点:窗口排名"],
        note="成交额按数据字典是 GMV（全部订单的商品总金额）；按下单日期累计，取首次 >= 30 万的日期；所有店铺都能达到，且没有恰好等于 30 万的边界值。直接从订单表按下单日期累计结果相同。",
    ),
    EvalCase(
        id="H7E08",
        query="每家店铺收到的第一笔退款申请（按申请时间最早）是什么时候提的、申请退多少钱？不管退款办完没有都算，列出店铺名、申请时间和退款金额。",
        reference_sql=(
            "SELECT shop_name, apply_time, refund_amount FROM ("
            "SELECT s.shop_name, r.apply_time, r.refund_amount, "
            "ROW_NUMBER() OVER (PARTITION BY o.shop_id ORDER BY r.apply_time) AS rn "
            "FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
            "JOIN dim_shop s ON s.shop_id = o.shop_id) t WHERE rn = 1"
        ),
        must_hit_columns=[
            "fact_refund.apply_time",
            "fact_refund.refund_amount",
            "fact_order.shop_id",
            "dim_shop.shop_name",
        ],
        tags=["难度:中等", "考点:相对时间", "考点:窗口排名"],
        note="退款经订单归到店铺，每店取申请时间最早的一条；各店最早申请时间不并列；“首次”看申请时间而不是退款完成时间或下单时间。",
    ),
    EvalCase(
        id="H7E09",
        query="有多少用户把同一件商品在两笔或以上不同的已完成订单里都买过？同一件商品以商品编号为准，名字一样但编号不同的不算同一件。",
        reference_sql=(
            "SELECT COUNT(DISTINCT user_id) FROM (SELECT o.user_id, i.product_id "
            "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
            "WHERE o.order_status = '已完成' GROUP BY o.user_id, i.product_id "
            "HAVING COUNT(DISTINCT o.order_id) >= 2) t"
        ),
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order.user_id",
            "fact_order_item.product_id",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按用户+商品汇总不同已完成订单数，再数满足 >=2 的用户；库里同名商品很多，按名字算会得到不同答案，题面已限定按编号。",
    ),
    EvalCase(
        id="H7E10",
        query="因为商品质量问题、而且已经退款成功的钱，按商品所属的一级类目分各是多少？列出一级类目和金额，保留两位小数。",
        reference_sql=(
            "SELECT pc.category_name, ROUND(SUM(r.refund_amount), 2) AS amt FROM fact_refund r "
            "JOIN (SELECT DISTINCT i.order_id, c.parent_category_id FROM fact_order_item i "
            "JOIN dim_product p ON p.product_id = i.product_id "
            "JOIN dim_category c ON c.category_id = p.category_id) x ON x.order_id = r.order_id "
            "JOIN dim_category pc ON pc.category_id = x.parent_category_id "
            "WHERE r.refund_reason = '商品质量问题' AND r.refund_status = '退款成功' "
            "GROUP BY pc.category_id, pc.category_name"
        ),
        must_hit_columns=[
            "fact_refund.refund_amount",
            "fact_refund.refund_reason",
            "fact_refund.refund_status",
            ["dim_product.category_id", "dim_shop.main_category_id"],
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="退款挂在订单上，按明细连到商品类目时要按订单去重，否则多商品订单的退款会被重复累加；本库每笔订单的商品都属于同一个一级类目（且等于店铺主营类目所属一级类目），两条路径结果一致。",
    ),
    EvalCase(
        id="H7E11",
        query="用花呗分期付款的订单里，各会员等级下的单各占百分之几？按订单笔数算，结果写成百分数的数值（比如 12.34 表示 12.34%），保留两位小数。",
        reference_sql=(
            "SELECT u.member_level, ROUND(100.0 * COUNT(*) / "
            "(SELECT COUNT(*) FROM fact_payment WHERE pay_channel = '花呗分期'), 2) AS pct "
            "FROM fact_payment p JOIN fact_order o ON o.order_id = p.order_id "
            "JOIN dim_user u ON u.user_id = o.user_id "
            "WHERE p.pay_channel = '花呗分期' GROUP BY u.member_level"
        ),
        must_hit_columns=["fact_payment.pay_channel", "dim_user.member_level"],
        tags=["难度:中等"],
        note="支付方式只在支付流水里；每笔订单只有一条支付流水，按流水数与按订单数相同；分母是全部花呗分期订单。",
    ),
    EvalCase(
        id="H7E12",
        query="有多少个“用户+商品”的组合，是先浏览过某件商品、后来又把同一件商品加购了的？加购时间要晚于其中某一次浏览，同一个用户同一件商品只算一次。",
        reference_sql=(
            "SELECT COUNT(*) FROM (SELECT DISTINCT a.user_id, a.product_id "
            "FROM fact_user_behavior a JOIN fact_user_behavior b "
            "ON a.user_id = b.user_id AND a.product_id = b.product_id "
            "WHERE a.behavior_type = '浏览' AND b.behavior_type = '加购' "
            "AND b.behavior_time > a.behavior_time) t"
        ),
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.behavior_time",
            "fact_user_behavior.user_id",
            "fact_user_behavior.product_id",
        ],
        tags=["难度:中等", "考点:相对时间"],
        note="【存疑】题面按“用户+商品组合”计数（53），若被理解成按用户去重则是 51；行为表自连接，要求加购时间严格晚于某次浏览时间。",
    ),
    EvalCase(
        id="H7E13",
        query="已经退款成功的那些退款，从申请到退完平均要多少个小时？按退款原因分别看，保留一位小数。",
        reference_sql=(
            "SELECT refund_reason, ROUND(AVG((julianday(finish_time) - julianday(apply_time)) * 24), 1) AS hrs "
            "FROM fact_refund WHERE refund_status = '退款成功' GROUP BY refund_reason"
        ),
        must_hit_columns=[
            "fact_refund.refund_reason",
            "fact_refund.refund_status",
            "fact_refund.apply_time",
            "fact_refund.finish_time",
        ],
        tags=["难度:简单"],
        note="退款完成时间减申请时间，换算成小时后按原因求平均；退款中的记录没有完成时间，已排除。",
    ),
    EvalCase(
        id="H7E14",
        query="每个年龄段里，哪个省份的用户人均消费最高？消费指用户历史上累计付过的钱，人均按这个省、这个年龄段的全部用户算，没花过钱的也算人头。列出年龄段、省份和人均消费，保留两位小数。",
        reference_sql=(
            "WITH g AS (SELECT u.age_group, u.province, AVG(s.total_pay_amount) AS a "
            "FROM dim_user u JOIN dws_user_summary s ON s.user_id = u.user_id GROUP BY u.age_group, u.province) "
            "SELECT age_group, province, ROUND(a, 2) FROM ("
            "SELECT *, RANK() OVER (PARTITION BY age_group ORDER BY a DESC) AS rk FROM g) t WHERE rk = 1"
        ),
        must_hit_columns=[
            "dim_user.age_group",
            "dim_user.province",
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:难", "考点:两层聚合", "考点:窗口排名"],
        note="【存疑】“累计付过的钱”按数据字典的消费总额口径，不扣退款；若扣掉退款，41-50 岁组的第一名会变。先按年龄段+省份算人均累计实付（用户汇总表的消费总额，含后来退款的已支付订单），再在每个年龄段内取最高；从订单表按有支付时间的订单汇总再 LEFT JOIN 用户，结果相同；每组第一名无并列，是否计入零消费用户不影响各组第一名。",
    ),
    EvalCase(
        id="H7E15",
        query="各个下单渠道的已付款订单里，下单后超过一个小时才付款的占百分之几？已付款的订单包括后来退款的，结果写成百分数的数值（比如 12.34 表示 12.34%），保留两位小数。",
        reference_sql=(
            "SELECT channel, ROUND(100.0 * SUM((strftime('%s', pay_time) - strftime('%s', create_time)) > 3600) "
            "/ COUNT(*), 2) AS pct FROM fact_order WHERE pay_time IS NOT NULL GROUP BY channel"
        ),
        must_hit_columns=[
            "fact_order.channel",
            "fact_order.create_time",
            ["fact_order.pay_time", "fact_payment.pay_time"],
        ],
        tags=["难度:中等", "考点:相对时间"],
        note="付款时间减下单时间 > 60 分钟；库里没有恰好 60 分钟的订单，不存在边界歧义；分母是该渠道全部有支付时间的订单；支付流水的支付时间与订单支付时间一致。",
    ),
    EvalCase(
        id="H7E16",
        query="有哪些店铺在 5 月里至少有 4 天单日下单量达到 4 单及以上？列出店铺名和这样的天数，订单状态不限。",
        reference_sql=(
            "SELECT s.shop_name, COUNT(*) AS days FROM dws_shop_daily d JOIN dim_shop s ON s.shop_id = d.shop_id "
            "WHERE d.order_count >= 4 GROUP BY d.shop_id, s.shop_name HAVING COUNT(*) >= 4"
        ),
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.order_count", "fact_order.order_id"],
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按店铺+日期得到单日订单量，再数达标天数并筛 >=4；从订单表按下单日期聚合结果相同。",
    ),
    EvalCase(
        id="H7E17",
        query="拿 5 月 21 日到 30 日（两头都算）跟前一段 5 月 11 日到 20 日（两头都算）比，每个下单渠道的订单数多了还是少了，差几单？少了用负数表示，订单状态不限。",
        reference_sql=(
            "SELECT channel, "
            "SUM(date(create_time) BETWEEN '2024-05-21' AND '2024-05-30') - "
            "SUM(date(create_time) BETWEEN '2024-05-11' AND '2024-05-20') AS diff "
            "FROM fact_order GROUP BY channel"
        ),
        must_hit_columns=["fact_order.channel", "fact_order.create_time"],
        tags=["难度:中等", "考点:相对时间"],
        note="两段 10 天的环比，按下单日期划分，两端都含；差值 = 后一段 - 前一段。",
    ),
    EvalCase(
        id="H7E18",
        query="退款订单有两笔及以上的用户，按会员等级分各有多少人？",
        reference_sql=(
            "SELECT u.member_level, COUNT(*) FROM dws_user_summary s JOIN dim_user u ON u.user_id = s.user_id "
            "WHERE s.refund_order_count >= 2 GROUP BY u.member_level"
        ),
        must_hit_columns=[
            "dim_user.member_level",
            ["dws_user_summary.refund_order_count", "fact_refund.order_id", "fact_order.order_status"],
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="用户汇总表的退款订单数；按退款记录去重订单、或按“已退款”状态订单逐用户计数，三条路径结果相同；没有满足条件用户的会员等级不出现。",
    ),
    EvalCase(
        id="H7E19",
        query="只算已完成的订单，每个一级类目里销量排前两名的商品是哪些？列出一级类目、商品编号、商品名称和卖出的件数。名字一样但编号不同的按不同商品算。",
        reference_sql=(
            "WITH t AS (SELECT pc.category_name AS l1, p.product_id, p.product_name, SUM(i.quantity) AS q "
            "FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id "
            "JOIN dim_product p ON p.product_id = i.product_id "
            "JOIN dim_category c ON c.category_id = p.category_id "
            "JOIN dim_category pc ON pc.category_id = c.parent_category_id "
            "WHERE o.order_status = '已完成' GROUP BY pc.category_name, p.product_id, p.product_name) "
            "SELECT l1, product_id, product_name, q FROM ("
            "SELECT *, RANK() OVER (PARTITION BY l1 ORDER BY q DESC) AS rk FROM t) x WHERE rk <= 2"
        ),
        must_hit_columns=[
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_product.product_name",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接"],
        note="销量=件数求和，按商品编号分组（同店同名商品就有好几组，按名字合并会改变排名）；每组第 2、3 名不并列。",
    ),
    EvalCase(
        id="H7E20",
        query="2023 年 5 月 1 日当天及以后注册的用户，在已完成的订单里买得最多（按件数）的是哪个一级类目？买了多少件？",
        reference_sql=(
            "SELECT pc.category_name, SUM(i.quantity) AS q FROM fact_order_item i "
            "JOIN fact_order o ON o.order_id = i.order_id "
            "JOIN dim_user u ON u.user_id = o.user_id "
            "JOIN dim_product p ON p.product_id = i.product_id "
            "JOIN dim_category c ON c.category_id = p.category_id "
            "JOIN dim_category pc ON pc.category_id = c.parent_category_id "
            "WHERE u.register_time >= '2023-05-01' AND o.order_status = '已完成' "
            "GROUP BY pc.category_id, pc.category_name ORDER BY q DESC LIMIT 1"
        ),
        must_hit_columns=[
            "dim_user.register_time",
            "fact_order.order_status",
            "fact_order_item.quantity",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="注册日期筛用户（不是下单日期），连到商品的一级类目按件数汇总取第一；第一名与第二名差距明显。",
    ),
    EvalCase(
        id="H7E21",
        query="已完成的订单里，一单买了 3 种及以上不同商品的，各下单渠道各有多少单？",
        reference_sql=(
            "SELECT o.channel, COUNT(*) FROM fact_order o WHERE o.order_status = '已完成' "
            "AND o.order_id IN (SELECT order_id FROM fact_order_item GROUP BY order_id "
            "HAVING COUNT(DISTINCT product_id) >= 3) GROUP BY o.channel"
        ),
        must_hit_columns=[
            "fact_order.channel",
            "fact_order.order_status",
            "fact_order_item.product_id",
        ],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按订单数不同商品种数（不是件数），再按渠道数订单；本库每笔订单内商品不重复，按明细行数结果相同。",
    ),
    EvalCase(
        id="H7E22",
        query="每个城市里（看用户所在城市），累计消费最多的前两位用户是谁？累计消费指历史上所有付过款订单的实付金额加起来，退款的不扣。列出城市、用户昵称和累计消费。",
        reference_sql=(
            "SELECT city, user_name, total_pay_amount FROM ("
            "SELECT u.city, u.user_name, s.total_pay_amount, "
            "RANK() OVER (PARTITION BY u.city ORDER BY s.total_pay_amount DESC) AS rk "
            "FROM dim_user u JOIN dws_user_summary s ON s.user_id = u.user_id) t WHERE rk <= 2"
        ),
        must_hit_columns=[
            "dim_user.city",
            "dim_user.user_name",
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:难", "考点:窗口排名"],
        note="城市是用户所在城市而非店铺城市；累计消费=用户汇总表的消费总额（有支付时间订单的实付之和），从订单表汇总结果相同；每城第 2、3 名不并列。",
    ),
    EvalCase(
        id="H7E23",
        query="哪些用户下过单，却一次款都没付过？列出用户昵称。",
        reference_sql=(
            "SELECT u.user_name FROM dim_user u WHERE u.user_id IN ("
            "SELECT user_id FROM fact_order GROUP BY user_id HAVING SUM(pay_time IS NOT NULL) = 0)"
        ),
        must_hit_columns=[
            "dim_user.user_name",
            ["fact_order.pay_time", "fact_order.order_status", "dws_user_summary.total_pay_amount"],
        ],
        tags=["难度:中等", "考点:否定集合"],
        note="有订单但全部订单都没有支付时间（只有已取消/待支付）；从没下过单的用户不算；用订单状态或用户汇总表（下单数>0 且消费为 0）判断结果相同。",
    ),
    EvalCase(
        id="H7E24",
        query="哪些商品有人浏览过，却从来没有人收藏过？列出商品名称。",
        reference_sql=(
            "SELECT p.product_name FROM dim_product p WHERE p.product_id IN "
            "(SELECT product_id FROM fact_user_behavior WHERE behavior_type = '浏览') "
            "AND p.product_id NOT IN (SELECT product_id FROM fact_user_behavior WHERE behavior_type = '收藏')"
        ),
        must_hit_columns=[
            "dim_product.product_name",
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.product_id",
        ],
        tags=["难度:中等", "考点:否定集合"],
        note="有浏览行为且没有任何收藏行为的商品；结果商品名在库里不重名。",
    ),
    EvalCase(
        id="H7E25",
        query="金卡会员和钻石会员用微信支付付的钱，按店铺类型分别是多少？列出店铺类型和金额，保留两位小数。",
        reference_sql=(
            "SELECT s.shop_type, ROUND(SUM(p.pay_amount), 2) AS amt FROM fact_payment p "
            "JOIN fact_order o ON o.order_id = p.order_id "
            "JOIN dim_user u ON u.user_id = o.user_id "
            "JOIN dim_shop s ON s.shop_id = o.shop_id "
            "WHERE u.member_level IN ('金卡会员', '钻石会员') AND p.pay_channel = '微信支付' "
            "GROUP BY s.shop_type"
        ),
        must_hit_columns=[
            "fact_payment.pay_channel",
            ["fact_payment.pay_amount", "fact_order.pay_amount"],
            "dim_user.member_level",
            "dim_shop.shop_type",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="支付流水-订单-用户-店铺四表连接；支付方式只在支付流水里；流水金额与订单实付一致，两种取数结果相同；店铺类型看类型字段不看店名。",
    ),
    EvalCase(
        id="H7E26",
        query="只看在售的商品，在售商品有两件及以上的品牌里，每个品牌最贵和最便宜的标价差多少钱？列出品牌和差价，保留两位小数。",
        reference_sql=(
            "SELECT brand, ROUND(MAX(list_price) - MIN(list_price), 2) AS spread FROM dim_product "
            "WHERE shelf_status = '在售' GROUP BY brand HAVING COUNT(*) >= 2"
        ),
        must_hit_columns=["dim_product.brand", "dim_product.list_price", "dim_product.shelf_status"],
        tags=["难度:中等"],
        note="价格看标价而不是成交单价或成本价；已下架、预售的商品不算，在售只有一件的品牌不列出。",
    ),
    EvalCase(
        id="H7E27",
        query="5 月 1 日到 7 日（两头都算）这几天下的订单，后来退款金额最多的前 3 家店铺是哪几家、各退了多少？还在退款中的也算，按金额从多到少排，保留两位小数。",
        reference_sql=(
            "SELECT s.shop_name, ROUND(SUM(d.refund_amount), 2) AS amt FROM dws_shop_daily d "
            "JOIN dim_shop s ON s.shop_id = d.shop_id "
            "WHERE d.stat_date BETWEEN '2024-05-01' AND '2024-05-07' "
            "GROUP BY d.shop_id, s.shop_name ORDER BY SUM(d.refund_amount) DESC LIMIT 3"
        ),
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.refund_amount", "fact_refund.refund_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "考点:相对时间"],
        note="退款按订单下单日期归属（店铺日汇总的退款金额口径），不是按退款申请日期——两种算法前 3 名和金额都不同；从退款表连订单按下单日期筛结果相同；第 3、4 名不并列。",
        ordered=True,
    ),
    EvalCase(
        id="H7E28",
        query="老板想知道各家店铺收到的差评有多少条，差评率最高的是哪家？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="库里没有商品评价、评分或差评数据；退款原因不能代替评价。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H7E29",
        query="直播间这个渠道在广告投放上花了多少钱，投入产出比是多少？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="库里只有订单收入，没有广告、投流或推广费用数据，投入产出比无从计算。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H7E30",
        query="钻石会员手里平均还攒着多少会员积分没用掉？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="库里只有会员等级，没有积分的获取、消耗或余额记录。",
        expect_unanswerable=True,
    ),
]

HOLDOUT7_CHINOOK_CASES = [
    EvalCase(
        id="H7C01",
        query="有哪些专辑收录了至少 5 首曲目，而且其中每一首都至少卖出去过一次？列出专辑名和艺术家名。",
        reference_sql=(
            "SELECT al.Title, ar.Name FROM Album al JOIN Artist ar ON ar.ArtistId = al.ArtistId "
            "JOIN Track t ON t.AlbumId = al.AlbumId GROUP BY al.AlbumId, al.Title, ar.Name "
            "HAVING COUNT(*) >= 5 AND SUM(t.TrackId NOT IN (SELECT TrackId FROM InvoiceLine)) = 0"
        ),
        must_hit_columns=["Album.Title", "Artist.Name", "Track.AlbumId", "InvoiceLine.TrackId"],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="“每一首都卖出过”即专辑里不存在没卖出过的曲目；曲目数按曲库里属于该专辑的曲目算；销售看发票明细，不看歌单收录。",
    ),
    EvalCase(
        id="H7C02",
        query="买过视频格式（Protected MPEG-4 video file）曲目的客户，第一次买到视频是在他自己的第几张发票上？按这个“第几张”统计各有多少位客户。发票按开票日期先后排序。",
        reference_sql=(
            "WITH n AS (SELECT InvoiceId, CustomerId, "
            "ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate, InvoiceId) AS seq FROM Invoice), "
            "v AS (SELECT n.CustomerId, MIN(n.seq) AS first_seq FROM n "
            "JOIN InvoiceLine il ON il.InvoiceId = n.InvoiceId JOIN Track t ON t.TrackId = il.TrackId "
            "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
            "WHERE m.Name = 'Protected MPEG-4 video file' GROUP BY n.CustomerId) "
            "SELECT first_seq, COUNT(*) FROM v GROUP BY first_seq"
        ),
        must_hit_columns=[
            "Invoice.CustomerId",
            "Invoice.InvoiceDate",
            "InvoiceLine.TrackId",
            "Track.MediaTypeId",
            "MediaType.Name",
        ],
        tags=["难度:难", "考点:相对时间", "考点:窗口排名", "考点:多表连接"],
        note="先给每位客户的发票按开票日期编号，再找首次含视频格式曲目的那张发票的序号，按序号计数；同一客户没有同日两张发票，序号唯一；没买过视频的客户不在范围内。",
    ),
    EvalCase(
        id="H7C03",
        query="哪些客户是到 2022 年才第一次买东西的？列出他们的名和姓。",
        reference_sql=(
            "SELECT c.FirstName, c.LastName FROM Customer c WHERE c.CustomerId IN ("
            "SELECT CustomerId FROM Invoice GROUP BY CustomerId HAVING strftime('%Y', MIN(InvoiceDate)) = '2022')"
        ),
        must_hit_columns=["Customer.FirstName", "Customer.LastName", "Invoice.InvoiceDate"],
        tags=["难度:中等", "考点:相对时间"],
        note="每位客户的首张发票日期落在 2022 年；不是“2022 年买过东西”的客户。",
    ),
    EvalCase(
        id="H7C04",
        query="有多少位客户，最近一次买东西花的钱比他自己之前那些发票的平均金额要高？",
        reference_sql=(
            "WITH r AS (SELECT CustomerId, Total, "
            "ROW_NUMBER() OVER (PARTITION BY CustomerId ORDER BY InvoiceDate DESC, InvoiceId DESC) AS rn FROM Invoice) "
            "SELECT COUNT(*) FROM r a WHERE a.rn = 1 AND a.Total > "
            "(SELECT AVG(b.Total) FROM r b WHERE b.CustomerId = a.CustomerId AND b.rn > 1)"
        ),
        must_hit_columns=["Invoice.CustomerId", "Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:难", "考点:相对时间", "考点:两层聚合"],
        note="每位客户按开票日期取最后一张发票，与该客户此前全部发票的平均金额比较；同一客户没有同日两张发票，最后一张唯一；没有恰好相等的情况；平均值含不含最后一张结果都一样。",
    ),
    EvalCase(
        id="H7C05",
        query="哪些客户买过 Rock 流派的曲目，却一首 Metal 流派的都没买过？列出名和姓。",
        reference_sql=(
            "WITH b AS (SELECT DISTINCT i.CustomerId, g.Name AS gn FROM Invoice i "
            "JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId JOIN Track t ON t.TrackId = il.TrackId "
            "JOIN Genre g ON g.GenreId = t.GenreId) "
            "SELECT c.FirstName, c.LastName FROM Customer c "
            "WHERE c.CustomerId IN (SELECT CustomerId FROM b WHERE gn = 'Rock') "
            "AND c.CustomerId NOT IN (SELECT CustomerId FROM b WHERE gn = 'Metal')"
        ),
        must_hit_columns=[
            "Customer.FirstName",
            "Customer.LastName",
            "InvoiceLine.TrackId",
            "Track.GenreId",
            "Genre.Name",
        ],
        tags=["难度:难", "考点:否定集合", "考点:多表连接"],
        note="买过 Rock 且从未买过 Metal；Heavy Metal 是另一个流派，不算 Metal（加上也不改变结果）。",
    ),
    EvalCase(
        id="H7C06",
        query="每年有多少张发票是一次买了 9 首或以上曲目的？",
        reference_sql=(
            "SELECT strftime('%Y', i.InvoiceDate) AS y, COUNT(*) FROM Invoice i WHERE i.InvoiceId IN ("
            "SELECT InvoiceId FROM InvoiceLine GROUP BY InvoiceId HAVING COUNT(*) >= 9) GROUP BY 1"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "InvoiceLine.InvoiceId"],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按发票数明细行（每行 1 首），筛 >=9，再按开票年份计数。",
    ),
    EvalCase(
        id="H7C07",
        query="每一年从 1 月开始把每个月的销售额往上累加，到哪个月累计第一次超过当年全年销售额的一半？列出年份、月份（两位数字，如 07）和到那个月为止的累计销售额，保留两位小数。",
        reference_sql=(
            "WITH m AS (SELECT strftime('%Y', InvoiceDate) AS y, strftime('%m', InvoiceDate) AS mo, SUM(Total) AS s "
            "FROM Invoice GROUP BY 1, 2), "
            "c AS (SELECT y, mo, SUM(s) OVER (PARTITION BY y ORDER BY mo) AS cs, SUM(s) OVER (PARTITION BY y) AS tot FROM m), "
            "f AS (SELECT y, MIN(mo) AS mo FROM c WHERE cs > tot / 2 GROUP BY y) "
            "SELECT c.y, c.mo, ROUND(c.cs, 2) FROM c JOIN f ON f.y = c.y AND f.mo = c.mo"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:难", "考点:窗口排名", "考点:两层聚合"],
        note="年内按月累计，与当年全年合计的一半比较，取首次超过的月份；每年 12 个月都有销售；没有累计值恰好等于一半的情况。",
    ),
    EvalCase(
        id="H7C08",
        query="把每位客户买东西花的钱按开票日期一张张累加，累计第一次达到 20 美元（含）是在哪一年？按年份统计各有多少位客户。",
        reference_sql=(
            "WITH t AS (SELECT CustomerId, InvoiceDate, "
            "SUM(Total) OVER (PARTITION BY CustomerId ORDER BY InvoiceDate, InvoiceId) AS cs FROM Invoice), "
            "f AS (SELECT CustomerId, MIN(InvoiceDate) AS d FROM t WHERE cs >= 20 GROUP BY CustomerId) "
            "SELECT strftime('%Y', d) AS y, COUNT(*) FROM f GROUP BY 1"
        ),
        must_hit_columns=["Invoice.CustomerId", "Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:难", "考点:窗口排名", "考点:两层聚合"],
        note="每位客户按开票日期累计金额，取首次 >= 20 的日期再按年计数；同一客户没有同日两张发票，累计值没有恰好等于 20 的情况。",
    ),
    EvalCase(
        id="H7C09",
        query="被 3 个或更多歌单收录的曲目，按流派分各有多少首？名字相同的不同歌单分开算。列出流派和曲目数。",
        reference_sql=(
            "SELECT g.Name, COUNT(*) FROM (SELECT TrackId FROM PlaylistTrack GROUP BY TrackId HAVING COUNT(*) >= 3) x "
            "JOIN Track t ON t.TrackId = x.TrackId JOIN Genre g ON g.GenreId = t.GenreId GROUP BY g.GenreId, g.Name"
        ),
        must_hit_columns=["PlaylistTrack.PlaylistId", "PlaylistTrack.TrackId", "Track.GenreId", "Genre.Name"],
        tags=["难度:中等", "考点:两层聚合"],
        note="先按曲目数收录它的歌单数（库里有同名歌单，题面已要求按不同歌单分开算），筛 >=3，再按流派计数；收录不是销量。",
    ),
    EvalCase(
        id="H7C10",
        query="整张专辑加起来总时长超过一个小时的专辑有几张？",
        reference_sql=(
            "SELECT COUNT(*) FROM (SELECT AlbumId FROM Track GROUP BY AlbumId HAVING SUM(Milliseconds) > 3600000) t"
        ),
        must_hit_columns=["Track.AlbumId", "Track.Milliseconds"],
        tags=["难度:中等", "考点:两层聚合"],
        note="按专辑汇总曲目时长（毫秒）再筛 > 1 小时；没有恰好 1 小时的专辑。",
    ),
    EvalCase(
        id="H7C11",
        query="卖出去超过 200 份的那些流派里，每个流派卖得最多的艺术家是谁、卖了多少份？列出流派、艺术家和份数。",
        reference_sql=(
            "WITH s AS (SELECT g.GenreId, g.Name AS gn, ar.Name AS an, COUNT(*) AS n "
            "FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId JOIN Genre g ON g.GenreId = t.GenreId "
            "JOIN Album al ON al.AlbumId = t.AlbumId JOIN Artist ar ON ar.ArtistId = al.ArtistId "
            "GROUP BY g.GenreId, g.Name, ar.ArtistId, ar.Name), "
            "big AS (SELECT GenreId FROM s GROUP BY GenreId HAVING SUM(n) > 200) "
            "SELECT gn, an, n FROM (SELECT *, RANK() OVER (PARTITION BY GenreId ORDER BY n DESC) AS rk FROM s "
            "WHERE GenreId IN (SELECT GenreId FROM big)) x WHERE rk = 1"
        ),
        must_hit_columns=[
            "InvoiceLine.TrackId",
            "Track.GenreId",
            "Genre.Name",
            "Track.AlbumId",
            "Album.ArtistId",
            "Artist.Name",
        ],
        tags=["难度:难", "考点:两层聚合", "考点:窗口排名", "考点:多表连接"],
        note="先筛流派总销量 > 200 份（4 个流派），再在流派内按艺术家销量取第一；份数按明细行计；每个流派第一名不并列。",
    ),
    EvalCase(
        id="H7C12",
        query="哪些曲目的时长超过了它所在专辑曲目平均时长的两倍？列出曲目名和专辑名。",
        reference_sql=(
            "SELECT t.Name, al.Title FROM Track t JOIN Album al ON al.AlbumId = t.AlbumId "
            "JOIN (SELECT AlbumId, AVG(Milliseconds) AS av FROM Track GROUP BY AlbumId) a ON a.AlbumId = t.AlbumId "
            "WHERE t.Milliseconds > 2 * a.av"
        ),
        must_hit_columns=["Track.Name", "Track.Milliseconds", "Track.AlbumId", "Album.Title"],
        tags=["难度:中等", "考点:两层聚合"],
        note="先算每张专辑的平均曲目时长（含该曲目本身），再逐首比较；没有接近两倍边界的曲目；有同名曲目，但配上专辑名后各行可区分。",
    ),
    EvalCase(
        id="H7C13",
        query="哪位员工入职的时候年纪最小？列出名、姓和他入职当天的周岁年龄。",
        reference_sql=(
            "SELECT FirstName, LastName, age FROM (SELECT FirstName, LastName, "
            "CAST(strftime('%Y', HireDate) AS INTEGER) - CAST(strftime('%Y', BirthDate) AS INTEGER) "
            "- (strftime('%m-%d', HireDate) < strftime('%m-%d', BirthDate)) AS age FROM Employee) t "
            "ORDER BY age LIMIT 1"
        ),
        must_hit_columns=["Employee.BirthDate", "Employee.HireDate", "Employee.FirstName", "Employee.LastName"],
        tags=["难度:中等"],
        note="周岁=入职日期与出生日期的整年差（未过生日减一）；最小值唯一，且按天数差排序结果相同。",
    ),
    EvalCase(
        id="H7C14",
        query="收录了曲目的歌单里，哪些歌单收的歌全都属于同一个流派？列出歌单编号、歌单名称和那个流派。",
        reference_sql=(
            "SELECT p.PlaylistId, p.Name, MIN(g.Name) FROM Playlist p "
            "JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId JOIN Track t ON t.TrackId = pt.TrackId "
            "JOIN Genre g ON g.GenreId = t.GenreId GROUP BY p.PlaylistId, p.Name HAVING COUNT(DISTINCT t.GenreId) = 1"
        ),
        must_hit_columns=["Playlist.PlaylistId", "Playlist.Name", "PlaylistTrack.TrackId", "Track.GenreId", "Genre.Name"],
        tags=["难度:中等", "考点:否定集合", "考点:多表连接"],
        note="“只有一个流派”：按歌单对流派去重计数等于 1；空歌单不在范围内；按歌单编号判断。",
    ),
    EvalCase(
        id="H7C15",
        query="曲库里每种文件格式各有多少首曲目？列出格式名称和曲目数。",
        reference_sql=(
            "SELECT m.Name, COUNT(*) FROM Track t JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["Track.MediaTypeId", "MediaType.Name"],
        tags=["难度:简单"],
        note="文件格式是媒体格式，不是流派；按曲库曲目计数，不是销量。",
    ),
    EvalCase(
        id="H7C16",
        query="哪位客户买过的音乐流派种类最多？列出名、姓和他买过的流派数。",
        reference_sql=(
            "SELECT c.FirstName, c.LastName, COUNT(DISTINCT t.GenreId) AS n FROM Customer c "
            "JOIN Invoice i ON i.CustomerId = c.CustomerId JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId "
            "JOIN Track t ON t.TrackId = il.TrackId GROUP BY c.CustomerId, c.FirstName, c.LastName "
            "ORDER BY n DESC LIMIT 1"
        ),
        must_hit_columns=[
            "Customer.FirstName",
            "Customer.LastName",
            "InvoiceLine.TrackId",
            "Track.GenreId",
        ],
        tags=["难度:难", "考点:多表连接", "考点:两层聚合"],
        note="客户-发票-明细-曲目四表连接，按客户对流派去重计数取最大；第一名与第二名不并列。",
    ),
    EvalCase(
        id="H7C17",
        query="2024 年全年（1 月 1 日到 12 月 31 日，两头都算），每位销售支持员工负责的客户一共贡献了多少销售额？列出员工的名、姓和金额，保留两位小数。",
        reference_sql=(
            "SELECT e.FirstName, e.LastName, ROUND(SUM(i.Total), 2) FROM Employee e "
            "JOIN Customer c ON c.SupportRepId = e.EmployeeId JOIN Invoice i ON i.CustomerId = c.CustomerId "
            "WHERE i.InvoiceDate >= '2024-01-01' AND i.InvoiceDate < '2025-01-01' "
            "GROUP BY e.EmployeeId, e.FirstName, e.LastName"
        ),
        must_hit_columns=[
            "Customer.SupportRepId",
            "Employee.FirstName",
            "Employee.LastName",
            "Invoice.InvoiceDate",
            "Invoice.Total",
        ],
        tags=["难度:中等"],
        note="按开票日期筛 2024 年，经客户的专属销售支持关联到员工，对发票总额求和。",
    ),
    EvalCase(
        id="H7C18",
        query="客户付款时用信用卡的多还是用 PayPal 的多？各占多少比例？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="发票只记金额和开票地址，库里没有支付方式、支付渠道或支付流水数据。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H7C19",
        query="哪家唱片公司旗下的专辑卖得最好？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="库里没有唱片公司/厂牌信息；艺术家不等于唱片公司。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H7C20",
        query="2024 年客户申请退款退掉了多少张发票，退款金额一共多少？",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="库里没有退款、退货或冲销记录，发票金额全部为正常销售。",
        expect_unanswerable=True,
    ),
]
