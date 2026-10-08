"""
第四套留出评测集：由独立出题人在未见过被测系统表现和已有题目的情况下编写。
ecommerce 30 题（H4E01–H4E30，陷阱 3），Chinook 20 题（H4C01–H4C20，陷阱 3）。

**已用过一次。**这套题于 0518ab7 冻结并推送后第一次运行，三个版本一起跑，都用冻结时的
评测器判分，结果见 docs/实验记录.md「第四套留出集：四处改动在没见过的题上」：

    版本                         ecommerce   Chinook   运行通过（90 + 60）
    2a4ccc4  取值范围 + 保底        28/30       20/20     86 + 59
    c401d21  只留保底               29/30       20/20     86 + 59
    0518ab7  再加后三处改动         29/30       20/20     88 + 60

整数除法规则在陌生题上成立（H4E14 1/3 → 3/3，整数除法造成的失败 2 次 → 0 次）；
只留保底、守卫口径豁免、候选池保底在这套题上都没有可帮的题，也没测出代价。
首次运行因 DeepSeek 余额耗尽被熔断中止，按事先写定的规则补跑合并。
没有发现可证明没法判分的题，冻结版就是最终版。

出题条件和第三套相同：材料逐字沿用 eval/blind_materials/（出题规范只换了题号和文件名）；
不读 README、docs/、eval/ 已有题目和 git 历史，不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本完成，只输出题号和检查项；
出题人的回报里也不含题目内容。组装进仓库时只换了导入、加了这段文件头。

候选路径的验证 SQL 在 eval/cases_holdout4_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

第四套盲写评测题（holdout4）。

ecommerce 30 题（H4E01–H4E30，陷阱题 3 道），chinook 20 题（H4C01–H4C20，陷阱题 3 道）。
只依据本目录下的数据字典与两个 SQLite 库编写。
"""

from eval.cases import EvalCase

UNANSWERABLE_SQL = "SELECT 1 WHERE 0"


HOLDOUT4_ECOMMERCE_CASES = [
    EvalCase(
        id="H4E01",
        query="注册日期在 2023 年内（2023-01-01 至 2023-12-31，含首尾两天）的用户，按注册渠道统计各有多少人？返回注册渠道和用户数。",
        reference_sql=(
            "SELECT register_channel, COUNT(*) AS user_cnt\n"
            "FROM dim_user\n"
            "WHERE register_time BETWEEN '2023-01-01' AND '2023-12-31'\n"
            "GROUP BY register_channel"
        ),
        must_hit_columns=["dim_user.register_channel", "dim_user.register_time"],
        tags=["难度:简单", "考点:日期区间筛选", "考点:分组计数"],
        note="register_time 为 YYYY-MM-DD 文本，区间含首尾；按注册渠道（不是下单渠道）分组计数。",
    ),
    EvalCase(
        id="H4E02",
        query="店铺状态为「正常营业」的店铺中，每种店铺类型各有几家？返回店铺类型和店铺数量。",
        reference_sql=(
            "SELECT shop_type, COUNT(*) AS shop_cnt\n"
            "FROM dim_shop\n"
            "WHERE shop_status = '正常营业'\n"
            "GROUP BY shop_type"
        ),
        must_hit_columns=["dim_shop.shop_type", "dim_shop.shop_status"],
        tags=["难度:简单", "考点:枚举筛选", "考点:分组计数"],
        note="单表筛选 shop_status 后按 shop_type 计数，四种类型都有正常营业的店铺。",
    ),
    EvalCase(
        id="H4E03",
        query="按标价给全部商品分四档，统计每档的商品个数：标价低于 1000、1000（含）至 3000（不含）、3000（含）至 5000（不含）、5000 及以上。返回一行四个数，依次对应这四档。",
        reference_sql=(
            "SELECT SUM(CASE WHEN list_price < 1000 THEN 1 ELSE 0 END) AS band_lt_1000,\n"
            "       SUM(CASE WHEN list_price >= 1000 AND list_price < 3000 THEN 1 ELSE 0 END) AS band_1000_3000,\n"
            "       SUM(CASE WHEN list_price >= 3000 AND list_price < 5000 THEN 1 ELSE 0 END) AS band_3000_5000,\n"
            "       SUM(CASE WHEN list_price >= 5000 THEN 1 ELSE 0 END) AS band_ge_5000\n"
            "FROM dim_product"
        ),
        must_hit_columns=["dim_product.list_price"],
        tags=["难度:简单", "考点:分档统计", "考点:条件聚合"],
        note="全部商品，不区分上架状态；分档左闭右开，库里没有标价恰好等于 1000、3000、5000 的商品，边界写法不影响结果。",
    ),
    EvalCase(
        id="H4E04",
        query="各店铺类型的订单优惠率是多少？优惠率 = 优惠金额合计 ÷ 订单商品总金额合计（订单状态不限），用百分数表示并保留两位小数（例如 12.34 表示 12.34%）。返回店铺类型和优惠率。",
        reference_sql=(
            "SELECT s.shop_type, ROUND(100.0 * SUM(o.discount_amount) / SUM(o.order_amount), 2) AS discount_pct\n"
            "FROM fact_order o\n"
            "JOIN dim_shop s ON o.shop_id = s.shop_id\n"
            "GROUP BY s.shop_type"
        ),
        must_hit_columns=[
            "dim_shop.shop_type",
            ["fact_order.discount_amount", "fact_order_item.item_discount_amount"],
            ["fact_order.order_amount", "fact_order_item.item_price"],
        ],
        tags=["难度:中等", "考点:比率计算", "考点:两表关联"],
        note="先分别求和再相除（不是逐单优惠率的平均）；订单级金额与明细级金额汇总一致，两条路径结果相同（见 alt_sql.json）。",
    ),
    EvalCase(
        id="H4E05",
        query="通过「直播间」渠道下单、且订单状态为「已取消」的订单有多少笔？返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) AS order_cnt\n"
            "FROM fact_order\n"
            "WHERE channel = '直播间' AND order_status = '已取消'"
        ),
        must_hit_columns=["fact_order.channel", "fact_order.order_status"],
        tags=["难度:简单", "考点:多条件筛选", "考点:计数"],
        note="两个枚举条件同时成立的订单计数；一行一笔订单，无需去重。",
    ),
    EvalCase(
        id="H4E06",
        query="只看订单状态为「已完成」的订单，各下单渠道的实付金额合计是多少？返回下单渠道和实付金额合计，保留两位小数。",
        reference_sql=(
            "SELECT channel, ROUND(SUM(pay_amount), 2) AS pay_total\n"
            "FROM fact_order\n"
            "WHERE order_status = '已完成'\n"
            "GROUP BY channel"
        ),
        must_hit_columns=["fact_order.channel", "fact_order.pay_amount", "fact_order.order_status"],
        tags=["难度:中等", "考点:金额口径", "考点:分组求和"],
        note="实付金额用 fact_order.pay_amount（不是 order_amount），只算已完成订单，按下单渠道 channel 分组。",
    ),
    EvalCase(
        id="H4E07",
        query="只统计订单状态为「已完成」的订单，销量（购买件数之和）最高的 3 个商品是哪些？同名商品按商品 ID 分开算，返回商品 ID、商品名称和销量。",
        reference_sql=(
            "SELECT p.product_id, p.product_name, SUM(i.quantity) AS sales_qty\n"
            "FROM fact_order_item i\n"
            "JOIN fact_order o ON i.order_id = o.order_id\n"
            "JOIN dim_product p ON i.product_id = p.product_id\n"
            "WHERE o.order_status = '已完成'\n"
            "GROUP BY p.product_id, p.product_name\n"
            "ORDER BY sales_qty DESC\n"
            "LIMIT 3"
        ),
        must_hit_columns=[
            "fact_order_item.quantity",
            "fact_order_item.product_id",
            "dim_product.product_name",
            "fact_order.order_status",
        ],
        tags=["难度:中等", "考点:销量口径", "考点:TopN", "考点:多表关联"],
        note="销量是 quantity 求和而非明细行数；状态在订单主表上。库里有同名商品，题面要求按商品 ID 区分；第 3、4 名销量不同。",
    ),
    EvalCase(
        id="H4E08",
        query="运费金额大于 0 的订单有多少笔、运费合计多少（订单状态不限）？返回订单笔数和运费合计（保留两位小数）。",
        reference_sql=(
            "SELECT COUNT(*) AS order_cnt, ROUND(SUM(freight_amount), 2) AS freight_total\n"
            "FROM fact_order\n"
            "WHERE freight_amount > 0"
        ),
        must_hit_columns=["fact_order.freight_amount"],
        tags=["难度:简单", "考点:数值筛选", "考点:聚合"],
        note="单表按运费字段 freight_amount 筛选后计数、求和；一行一笔订单，无需去重。",
    ),
    EvalCase(
        id="H4E09",
        query="2024 年 5 月里，每一张优惠券（按优惠券 ID）分别被核销了多少次？返回优惠券 ID 和核销次数。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "考点:数据缺失"],
        note="库里只有订单级优惠总金额 discount_amount，没有优惠券 ID、券模板或核销记录，无法按券统计。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H4E10",
        query="退款状态为「退款成功」的退款记录，按退款原因汇总退款金额，并按金额从高到低排列。返回退款原因和退款金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT refund_reason, ROUND(SUM(refund_amount), 2) AS refund_total\n"
            "FROM fact_refund\n"
            "WHERE refund_status = '退款成功'\n"
            "GROUP BY refund_reason\n"
            "ORDER BY refund_total DESC"
        ),
        must_hit_columns=["fact_refund.refund_reason", "fact_refund.refund_amount", "fact_refund.refund_status"],
        tags=["难度:中等", "考点:枚举筛选", "考点:排序"],
        note="只算退款成功的记录；五个原因的合计金额互不相等，排序唯一，因此要求有序。",
        ordered=True,
    ),
    EvalCase(
        id="H4E11",
        query="各行为类型的平均页面停留秒数是多少？返回行为类型和平均停留秒数，保留 1 位小数。",
        reference_sql=(
            "SELECT behavior_type, ROUND(AVG(stay_seconds), 1) AS avg_stay\n"
            "FROM fact_user_behavior\n"
            "GROUP BY behavior_type"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.stay_seconds"],
        tags=["难度:简单", "考点:分组平均"],
        note="单表按 behavior_type 求 stay_seconds 平均值，三种行为类型各一行。",
    ),
    EvalCase(
        id="H4E12",
        query="累计实付金额（用户消费总额）最高的 3 位用户是谁？返回用户昵称和累计实付金额（保留两位小数）。",
        reference_sql=(
            "SELECT u.user_name, ROUND(s.total_pay_amount, 2) AS total_pay\n"
            "FROM dws_user_summary s\n"
            "JOIN dim_user u ON s.user_id = u.user_id\n"
            "ORDER BY s.total_pay_amount DESC\n"
            "LIMIT 3"
        ),
        must_hit_columns=["dim_user.user_name", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
        tags=["难度:中等", "考点:汇总表", "考点:TopN"],
        note="字典定义累计实付金额为所有已支付订单（pay_time 非空）实付金额之和，汇总表与明细聚合结果一致（见 alt_sql.json）；第 3、4 名不并列。",
    ),
    EvalCase(
        id="H4E13",
        query="每家店铺的商品里，上架状态为「在售」「已下架」「预售」的各有几个？返回店铺名称，以及依次为在售、已下架、预售的三个商品数（某状态没有商品记为 0）。",
        reference_sql=(
            "SELECT s.shop_name,\n"
            "       SUM(CASE WHEN p.shelf_status = '在售' THEN 1 ELSE 0 END) AS on_sale_cnt,\n"
            "       SUM(CASE WHEN p.shelf_status = '已下架' THEN 1 ELSE 0 END) AS off_shelf_cnt,\n"
            "       SUM(CASE WHEN p.shelf_status = '预售' THEN 1 ELSE 0 END) AS presale_cnt\n"
            "FROM dim_shop s\n"
            "JOIN dim_product p ON p.shop_id = s.shop_id\n"
            "GROUP BY s.shop_id, s.shop_name"
        ),
        must_hit_columns=["dim_shop.shop_name", "dim_product.shelf_status", "dim_product.shop_id"],
        tags=["难度:中等", "考点:行转列", "考点:条件聚合"],
        note="行转列的条件计数，每家店铺一行三列；每家店铺都有商品，内连接与左连接结果相同。",
    ),
    EvalCase(
        id="H4E14",
        query="按一级类目统计用户对商品的行为：返回一级类目名称、浏览次数、加购次数，以及加购次数 ÷ 浏览次数（保留四位小数）。",
        reference_sql=(
            "SELECT c1.category_name,\n"
            "       SUM(CASE WHEN b.behavior_type = '浏览' THEN 1 ELSE 0 END) AS view_cnt,\n"
            "       SUM(CASE WHEN b.behavior_type = '加购' THEN 1 ELSE 0 END) AS cart_cnt,\n"
            "       ROUND(1.0 * SUM(CASE WHEN b.behavior_type = '加购' THEN 1 ELSE 0 END)\n"
            "             / SUM(CASE WHEN b.behavior_type = '浏览' THEN 1 ELSE 0 END), 4) AS cart_view_ratio\n"
            "FROM fact_user_behavior b\n"
            "JOIN dim_product p ON b.product_id = p.product_id\n"
            "JOIN dim_category c2 ON p.category_id = c2.category_id\n"
            "JOIN dim_category c1 ON c2.parent_category_id = c1.category_id\n"
            "GROUP BY c1.category_id, c1.category_name"
        ),
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.product_id",
            "dim_product.category_id",
            "dim_category.parent_category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "考点:行为分析", "考点:类目层级", "考点:条件聚合"],
        note="行为次数按行为记录数计；商品只挂二级类目，需上卷到一级类目；比值是两个次数直接相除（不是用户数之比）。",
    ),
    EvalCase(
        id="H4E15",
        query="每家店铺在 2024 年 5 月 1 日至 15 日、5 月 16 日至 30 日两个时段（按下单日期，均含首尾）的实付金额合计分别是多少？实付金额只算有支付时间的订单（含后来退款的）。返回店铺名称、前一时段实付金额、后一时段实付金额（保留两位小数）。",
        reference_sql=(
            "SELECT s.shop_name,\n"
            "       ROUND(SUM(CASE WHEN d.stat_date BETWEEN '2024-05-01' AND '2024-05-15' THEN d.pay_amount ELSE 0 END), 2) AS first_half,\n"
            "       ROUND(SUM(CASE WHEN d.stat_date BETWEEN '2024-05-16' AND '2024-05-30' THEN d.pay_amount ELSE 0 END), 2) AS second_half\n"
            "FROM dws_shop_daily d\n"
            "JOIN dim_shop s ON d.shop_id = s.shop_id\n"
            "GROUP BY s.shop_id, s.shop_name"
        ),
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.pay_amount", "fact_order.pay_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:难", "考点:行转列", "考点:日期区间筛选", "考点:汇总表"],
        note="两个时段各成一列；日汇总的实付金额按下单日期归属、只算有支付时间的订单，与订单表按 create_time 聚合结果一致（见 alt_sql.json）。",
    ),
    EvalCase(
        id="H4E16",
        query="按用户会员等级统计，订单状态为「已完成」的订单平均实付金额是多少？返回会员等级和平均实付金额（保留两位小数）。",
        reference_sql=(
            "SELECT u.member_level, ROUND(AVG(o.pay_amount), 2) AS avg_pay\n"
            "FROM fact_order o\n"
            "JOIN dim_user u ON o.user_id = u.user_id\n"
            "WHERE o.order_status = '已完成'\n"
            "GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level", "fact_order.pay_amount", "fact_order.order_status"],
        tags=["难度:中等", "考点:多表关联", "考点:分组平均"],
        note="按订单粒度求平均（每笔已完成订单权重相同），不是用汇总表的客单价再平均。",
    ),
    EvalCase(
        id="H4E17",
        query="按用户年龄段统计复购率：复购率 = 订单状态为「已完成」的订单不少于 2 笔的用户数 ÷ 至少有 1 笔「已完成」订单的用户数，用百分数表示并保留两位小数。返回年龄段和复购率。",
        reference_sql=(
            "SELECT age_group,\n"
            "       ROUND(100.0 * SUM(CASE WHEN done_cnt >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repurchase_pct\n"
            "FROM (\n"
            "    SELECT u.age_group, o.user_id, COUNT(*) AS done_cnt\n"
            "    FROM fact_order o\n"
            "    JOIN dim_user u ON o.user_id = u.user_id\n"
            "    WHERE o.order_status = '已完成'\n"
            "    GROUP BY u.age_group, o.user_id\n"
            ")\n"
            "GROUP BY age_group"
        ),
        must_hit_columns=["dim_user.age_group", "fact_order.order_status", "fact_order.user_id"],
        tags=["难度:难", "考点:比率计算", "考点:两层聚合"],
        note="分子分母都只看已完成订单，分母是有已完成订单的用户（不是全部用户）；年龄段直接按 age_group 区间分组。",
    ),
    EvalCase(
        id="H4E18",
        query="「直播间」渠道的订单中，哪位主播带来的实付金额最高？返回主播名称和实付金额合计。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "考点:数据缺失"],
        note="订单只记录下单渠道为直播间，库里没有主播、直播场次之类的字段或表，无法归属到主播。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H4E19",
        query="注册渠道为「小程序」的用户，通过「小程序」下单渠道一共下了多少笔订单（订单状态不限）？返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) AS order_cnt\n"
            "FROM fact_order o\n"
            "JOIN dim_user u ON o.user_id = u.user_id\n"
            "WHERE u.register_channel = '小程序' AND o.channel = '小程序'"
        ),
        must_hit_columns=["dim_user.register_channel", "fact_order.channel"],
        tags=["难度:中等", "考点:易混字段", "考点:多表关联"],
        note="注册渠道在用户表、下单渠道在订单表，两个条件分别落在各自字段上。",
    ),
    EvalCase(
        id="H4E20",
        query="各下单渠道的退款订单占比是多少？占比 = 该渠道订单状态为「已退款」的订单数 ÷ 该渠道全部订单数（所有状态），用百分数表示并保留两位小数（例如 12.34 表示 12.34%）。返回下单渠道和占比。",
        reference_sql=(
            "SELECT channel,\n"
            "       ROUND(100.0 * SUM(CASE WHEN order_status = '已退款' THEN 1 ELSE 0 END) / COUNT(*), 2) AS refund_pct\n"
            "FROM fact_order\n"
            "GROUP BY channel"
        ),
        must_hit_columns=["fact_order.channel", ["fact_order.order_status", "fact_refund.order_id"]],
        tags=["难度:难", "考点:比率计算", "考点:条件聚合"],
        note="分母为该渠道全部订单；已退款订单与退款记录一一对应，用退款表判定结果相同（见 alt_sql.json）。",
    ),
    EvalCase(
        id="H4E21",
        query="支付渠道为「花呗分期」、且下单渠道为「直播间」的订单，实付金额合计是多少？返回一个数，保留两位小数。",
        reference_sql=(
            "SELECT ROUND(SUM(o.pay_amount), 2) AS pay_total\n"
            "FROM fact_order o\n"
            "JOIN fact_payment p ON o.order_id = p.order_id\n"
            "WHERE p.pay_channel = '花呗分期' AND o.channel = '直播间'"
        ),
        must_hit_columns=[
            "fact_payment.pay_channel",
            "fact_order.channel",
            ["fact_order.pay_amount", "fact_payment.pay_amount"],
        ],
        tags=["难度:中等", "考点:易混字段", "考点:多表关联"],
        note="支付渠道与下单渠道是两个字段；每笔订单只有一条支付流水且金额与订单实付一致，两条金额路径结果相同（见 alt_sql.json）。",
    ),
    EvalCase(
        id="H4E22",
        query="只看订单状态为「已完成」的订单，按二级类目计算毛利：毛利 = 订单明细成交金额 − 商品成本价 × 购买数量。毛利合计最高的 3 个二级类目是哪些？返回二级类目名称和毛利合计（保留两位小数）。",
        reference_sql=(
            "SELECT c.category_name, ROUND(SUM(i.item_amount - p.cost_price * i.quantity), 2) AS gross_profit\n"
            "FROM fact_order_item i\n"
            "JOIN fact_order o ON i.order_id = o.order_id\n"
            "JOIN dim_product p ON i.product_id = p.product_id\n"
            "JOIN dim_category c ON p.category_id = c.category_id\n"
            "WHERE o.order_status = '已完成'\n"
            "GROUP BY c.category_id, c.category_name\n"
            "ORDER BY gross_profit DESC\n"
            "LIMIT 3"
        ),
        must_hit_columns=[
            "fact_order_item.item_amount",
            "fact_order_item.quantity",
            "dim_product.cost_price",
            "dim_category.category_name",
            "fact_order.order_status",
        ],
        tags=["难度:难", "考点:派生指标", "考点:多表关联", "考点:TopN"],
        note="毛利公式在题面给定；商品直接挂二级类目。第 3、4 名毛利差距明显，无并列。",
    ),
    EvalCase(
        id="H4E23",
        query="会员等级为「金卡会员」的用户中，客单价（平均订单金额）最高的是哪位？返回用户昵称和客单价。",
        reference_sql=(
            "SELECT u.user_name, s.avg_order_amount\n"
            "FROM dws_user_summary s\n"
            "JOIN dim_user u ON s.user_id = u.user_id\n"
            "WHERE u.member_level = '金卡会员'\n"
            "ORDER BY s.avg_order_amount DESC\n"
            "LIMIT 1"
        ),
        must_hit_columns=["dim_user.user_name", "dim_user.member_level", "dws_user_summary.avg_order_amount"],
        tags=["难度:中等", "考点:汇总表", "考点:Top1"],
        note="【存疑】客单价按字典取 dws_user_summary.avg_order_amount，该值是全部状态订单实付金额的平均；若改用明细只算已支付订单，用户相同但数值不同，判分依赖系统遵循字典口径。第 1、2 名不并列。",
    ),
    EvalCase(
        id="H4E24",
        query="订单状态为「已完成」的订单，从支付到买家确认收货平均用了多少小时？返回一个数，保留两位小数。",
        reference_sql=(
            "SELECT ROUND(AVG((julianday(finish_time) - julianday(pay_time)) * 24), 2) AS avg_hours\n"
            "FROM fact_order\n"
            "WHERE order_status = '已完成'"
        ),
        must_hit_columns=[
            ["fact_order.pay_time", "fact_payment.pay_time"],
            "fact_order.finish_time",
            "fact_order.order_status",
        ],
        tags=["难度:中等", "考点:时间差计算"],
        note="【存疑】字典提醒该时长不能当物流/配送时效用，系统可能因此误拒；本题问的正是字典写明的“支付到确认收货”时长，应正常作答。已退款订单也有 finish_time，必须按状态过滤。支付时间两条路径一致（见 alt_sql.json）。",
    ),
    EvalCase(
        id="H4E25",
        query="最近一次下单时间在 2024-05-25 及之后的用户，按会员等级统计：每个等级有多少位这样的用户、他们的累计实付金额平均是多少？返回会员等级、用户数和平均累计实付金额（保留两位小数）。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*) AS user_cnt, ROUND(AVG(s.total_pay_amount), 2) AS avg_total_pay\n"
            "FROM dws_user_summary s\n"
            "JOIN dim_user u ON s.user_id = u.user_id\n"
            "WHERE s.last_order_time >= '2024-05-25'\n"
            "GROUP BY u.member_level"
        ),
        must_hit_columns=[
            "dim_user.member_level",
            ["dws_user_summary.last_order_time", "fact_order.create_time"],
            ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
        ],
        tags=["难度:中等", "考点:汇总表", "考点:分组聚合"],
        note="最近下单时间带时分，从 05-25 00:00 起算；累计实付金额按字典口径（所有有支付时间订单的实付之和），汇总表与订单表聚合结果一致（见 alt_sql.json）。",
    ),
    EvalCase(
        id="H4E26",
        query="在店铺日汇总数据中，统计每家店铺支付转化率低于 1 的天数，天数最多的 3 家店铺是哪些？返回店铺名称和天数。",
        reference_sql=(
            "SELECT s.shop_name, COUNT(*) AS day_cnt\n"
            "FROM dws_shop_daily d\n"
            "JOIN dim_shop s ON d.shop_id = s.shop_id\n"
            "WHERE d.conversion_rate < 1\n"
            "GROUP BY s.shop_id, s.shop_name\n"
            "ORDER BY day_cnt DESC\n"
            "LIMIT 3"
        ),
        must_hit_columns=["dws_shop_daily.conversion_rate", "dim_shop.shop_name"],
        tags=["难度:中等", "考点:汇总表", "考点:TopN"],
        note="一行是店铺-天，按转化率 < 1 的行数计天数；第 3、4 名天数不同，无并列。",
    ),
    EvalCase(
        id="H4E27",
        query="一笔订单内所有商品的购买件数合计不少于 6 件的订单，按订单状态分别有多少笔？返回订单状态和订单笔数。",
        reference_sql=(
            "SELECT o.order_status, COUNT(*) AS order_cnt\n"
            "FROM fact_order o\n"
            "JOIN (SELECT order_id, SUM(quantity) AS qty FROM fact_order_item GROUP BY order_id) q\n"
            "  ON o.order_id = q.order_id\n"
            "WHERE q.qty >= 6\n"
            "GROUP BY o.order_status"
        ),
        must_hit_columns=["fact_order_item.quantity", "fact_order_item.order_id", "fact_order.order_status"],
        tags=["难度:中等", "考点:两层聚合", "考点:HAVING筛选"],
        note="先按订单汇总明细件数再筛选（≥ 6），再按订单状态计数；不是按单条明细的件数筛选。",
    ),
    EvalCase(
        id="H4E28",
        query="按用户性别统计，有过至少一笔「已退款」状态订单的用户各有多少位？返回性别和用户数。",
        reference_sql=(
            "SELECT u.gender, COUNT(DISTINCT o.user_id) AS user_cnt\n"
            "FROM fact_order o\n"
            "JOIN dim_user u ON o.user_id = u.user_id\n"
            "WHERE o.order_status = '已退款'\n"
            "GROUP BY u.gender"
        ),
        must_hit_columns=[
            "dim_user.gender",
            ["fact_order.order_status", "dws_user_summary.refund_order_count", "fact_refund.order_id"],
        ],
        tags=["难度:中等", "考点:去重计数", "考点:两表关联"],
        note="按用户去重；用已退款订单、汇总表退款订单数、退款记录三条路径判定结果一致（见 alt_sql.json）。性别字段无空值。",
    ),
    EvalCase(
        id="H4E29",
        query="有多少条退款记录属于部分退款，即退款金额小于对应订单的实付金额？不区分退款状态，返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) AS partial_cnt\n"
            "FROM fact_refund r\n"
            "JOIN fact_order o ON r.order_id = o.order_id\n"
            "WHERE r.refund_amount < o.pay_amount"
        ),
        must_hit_columns=["fact_refund.refund_amount", "fact_order.pay_amount"],
        tags=["难度:难", "考点:跨表比较"],
        note="退款金额与订单实付金额逐笔比较；全额退款的金额与实付完全相等，严格小于即为部分退款。",
    ),
    EvalCase(
        id="H4E30",
        query="各二级类目商品的平均用户评分是多少？返回二级类目名称和平均评分（保留 1 位小数）。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "考点:数据缺失"],
        note="库里没有评价、评分或好评相关的表和字段，无法计算评分。",
        expect_unanswerable=True,
    ),
]


HOLDOUT4_CHINOOK_CASES = [
    EvalCase(
        id="H4C01",
        query="出生日期在 1960 年代（1960-01-01 至 1969-12-31）的员工有哪些？返回员工的名和姓。",
        reference_sql=(
            "SELECT FirstName, LastName\n"
            "FROM Employee\n"
            "WHERE BirthDate >= '1960-01-01' AND BirthDate < '1970-01-01'"
        ),
        must_hit_columns=["Employee.BirthDate", "Employee.FirstName", "Employee.LastName"],
        tags=["难度:简单", "考点:日期区间筛选"],
        note="出生日期只有员工表有；BirthDate 带 00:00:00 时间部分，区间上界写成 1970-01-01 之前。",
    ),
    EvalCase(
        id="H4C02",
        query="流派为「Jazz」的曲目一共有多少首？返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) AS track_cnt\n"
            "FROM Track t\n"
            "JOIN Genre g ON t.GenreId = g.GenreId\n"
            "WHERE g.Name = 'Jazz'"
        ),
        must_hit_columns=["Genre.Name", "Track.GenreId"],
        tags=["难度:简单", "考点:枚举筛选", "考点:两表关联"],
        note="流派名在 Genre 表，经 Track.GenreId 关联后计数。",
    ),
    EvalCase(
        id="H4C03",
        query="按媒体格式统计曲目：每种格式有多少首曲目、平均时长多少秒？返回媒体格式名称、曲目数和平均时长（单位秒，保留两位小数）。",
        reference_sql=(
            "SELECT m.Name, COUNT(*) AS track_cnt, ROUND(AVG(t.Milliseconds) / 1000.0, 2) AS avg_seconds\n"
            "FROM Track t\n"
            "JOIN MediaType m ON t.MediaTypeId = m.MediaTypeId\n"
            "GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["MediaType.Name", "Track.MediaTypeId", "Track.Milliseconds"],
        tags=["难度:中等", "考点:单位换算", "考点:分组聚合"],
        note="时长字段单位是毫秒，需要除以 1000 换算成秒；媒体格式是文件编码格式，不是流派。",
    ),
    EvalCase(
        id="H4C04",
        query="哪家唱片公司（厂牌）发行的专辑数量最多？返回唱片公司名称和专辑数。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "考点:数据缺失"],
        note="Album 表只有专辑名和所属艺术家，库里没有唱片公司、厂牌或发行方信息，无法统计。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H4C05",
        query="按专辑内所有曲目的时长之和计算专辑总时长，总时长最长的 3 张专辑是哪些？返回专辑名称和总时长（单位分钟，保留两位小数）。",
        reference_sql=(
            "SELECT al.Title, ROUND(SUM(t.Milliseconds) / 60000.0, 2) AS total_minutes\n"
            "FROM Track t\n"
            "JOIN Album al ON t.AlbumId = al.AlbumId\n"
            "GROUP BY al.AlbumId, al.Title\n"
            "ORDER BY total_minutes DESC\n"
            "LIMIT 3"
        ),
        must_hit_columns=["Album.Title", "Track.AlbumId", "Track.Milliseconds"],
        tags=["难度:中等", "考点:单位换算", "考点:TopN"],
        note="专辑名用 Album.Title（不是员工职位 Title）；毫秒换算分钟除以 60000。第 3、4 名不并列。",
    ),
    EvalCase(
        id="H4C06",
        query="按每张发票包含的明细行数分组：明细行数为多少的发票各有多少张？返回明细行数和发票张数。",
        reference_sql=(
            "SELECT line_cnt, COUNT(*) AS invoice_cnt\n"
            "FROM (SELECT InvoiceId, COUNT(*) AS line_cnt FROM InvoiceLine GROUP BY InvoiceId)\n"
            "GROUP BY line_cnt"
        ),
        must_hit_columns=["InvoiceLine.InvoiceId"],
        tags=["难度:中等", "考点:两层聚合"],
        note="先数每张发票的明细行，再按行数分组数发票；每张发票都至少有 1 行明细，不存在 0 行的发票。",
    ),
    EvalCase(
        id="H4C07",
        query="按客户邮箱的域名（@ 后面的部分）统计客户数，只返回客户数不少于 2 的域名。返回域名和客户数。",
        reference_sql=(
            "SELECT substr(Email, instr(Email, '@') + 1) AS domain, COUNT(*) AS customer_cnt\n"
            "FROM Customer\n"
            "GROUP BY domain\n"
            "HAVING COUNT(*) >= 2"
        ),
        must_hit_columns=["Customer.Email"],
        tags=["难度:中等", "考点:字符串处理", "考点:HAVING筛选", "考点:易混字段"],
        note="用客户邮箱（不是员工邮箱），截取 @ 之后的部分分组；所有客户邮箱都含 @ 且都是小写。",
    ),
    EvalCase(
        id="H4C08",
        query="开票州/省为空的发票，按开票国家统计发票张数和开票金额合计。返回开票国家、发票张数和开票金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT BillingCountry, COUNT(*) AS invoice_cnt, ROUND(SUM(Total), 2) AS sales\n"
            "FROM Invoice\n"
            "WHERE BillingState IS NULL\n"
            "GROUP BY BillingCountry"
        ),
        must_hit_columns=["Invoice.BillingState", "Invoice.BillingCountry", "Invoice.Total"],
        tags=["难度:中等", "考点:空值筛选", "考点:分组聚合"],
        note="空值判断用 IS NULL（库里没有空字符串的州/省）；用的是发票上的开票州/省与开票国家，不是客户表字段。",
    ),
    EvalCase(
        id="H4C09",
        query="每位销售支持员工负责的客户中，买过流派为「Jazz」的曲目的客户各有几位（按客户去重）？返回员工的名、姓和客户数。",
        reference_sql=(
            "SELECT e.FirstName, e.LastName, COUNT(DISTINCT c.CustomerId) AS customer_cnt\n"
            "FROM Employee e\n"
            "JOIN Customer c ON c.SupportRepId = e.EmployeeId\n"
            "JOIN Invoice i ON i.CustomerId = c.CustomerId\n"
            "JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId\n"
            "JOIN Track t ON t.TrackId = il.TrackId\n"
            "JOIN Genre g ON g.GenreId = t.GenreId\n"
            "WHERE g.Name = 'Jazz'\n"
            "GROUP BY e.EmployeeId, e.FirstName, e.LastName"
        ),
        must_hit_columns=[
            "Customer.SupportRepId",
            "Employee.FirstName",
            "Employee.LastName",
            "Invoice.CustomerId",
            "InvoiceLine.TrackId",
            "Genre.Name",
        ],
        tags=["难度:难", "考点:多表关联", "考点:去重计数", "考点:易混表"],
        note="员工→客户→发票→明细→曲目→流派六表关联，按客户去重；客户与员工只能经 SupportRepId 关联。",
    ),
    EvalCase(
        id="H4C10",
        query="艺术家名称以「The 」开头（The 后面跟一个空格）的艺术家有多少位？返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) AS artist_cnt\n"
            "FROM Artist\n"
            "WHERE Name LIKE 'The %'"
        ),
        must_hit_columns=["Artist.Name"],
        tags=["难度:简单", "考点:模糊匹配"],
        note="对艺术家名称做前缀匹配；区分大小写与否结果相同。",
    ),
    EvalCase(
        id="H4C11",
        query="职位为 Sales Support Agent 的员工，每人的年薪是多少？返回员工的名、姓和年薪。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:简单", "陷阱题", "考点:数据缺失"],
        note="Employee 表只有职位、上下级、日期和联系方式，没有薪资字段；不能用其负责客户的销售额冒充。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H4C12",
        query="在客户数不少于 4 位的国家（按客户所在国家）里，找出每个国家累计开票金额最高的那位客户，并计算其开票金额占该国全部客户开票金额合计的百分比。返回国家、客户的名、姓和占比（百分数，保留两位小数）。",
        reference_sql=(
            "WITH cs AS (\n"
            "    SELECT c.CustomerId, c.FirstName, c.LastName, c.Country, SUM(i.Total) AS amt\n"
            "    FROM Customer c\n"
            "    JOIN Invoice i ON i.CustomerId = c.CustomerId\n"
            "    GROUP BY c.CustomerId, c.FirstName, c.LastName, c.Country\n"
            "),\n"
            "ct AS (\n"
            "    SELECT Country, SUM(amt) AS tot, COUNT(*) AS n, MAX(amt) AS mx\n"
            "    FROM cs\n"
            "    GROUP BY Country\n"
            ")\n"
            "SELECT cs.Country, cs.FirstName, cs.LastName, ROUND(100.0 * cs.amt / ct.tot, 2) AS share_pct\n"
            "FROM cs\n"
            "JOIN ct ON cs.Country = ct.Country\n"
            "WHERE ct.n >= 4 AND cs.amt = ct.mx"
        ),
        must_hit_columns=[
            ["Customer.Country", "Invoice.BillingCountry"],
            "Customer.FirstName",
            "Customer.LastName",
            "Invoice.Total",
        ],
        tags=["难度:难", "考点:分组取最大", "考点:占比计算", "考点:多层聚合"],
        note="三步：按客户汇总开票金额→按国家求合计、客户数与最大值→取每国最高者算占比。每个客户都有发票；符合条件的国家内最高者均无并列；开票国家与客户国家逐张一致，两条路径结果相同（见 alt_sql.json）。",
    ),
    EvalCase(
        id="H4C13",
        query="登记了所属公司（公司字段不为空）的客户分布在哪些国家？每个国家各有几位？返回国家和客户数。",
        reference_sql=(
            "SELECT Country, COUNT(*) AS customer_cnt\n"
            "FROM Customer\n"
            "WHERE Company IS NOT NULL\n"
            "GROUP BY Country"
        ),
        must_hit_columns=["Customer.Company", "Customer.Country"],
        tags=["难度:中等", "考点:空值筛选", "考点:易混字段"],
        note="客户国家用 Customer.Country（不是员工国家或开票国家）；公司字段为空表示个人客户。",
    ),
    EvalCase(
        id="H4C14",
        query="2022 年哪个月的开票金额合计最高？返回月份（写成 2022-01 这种格式）和该月开票金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT strftime('%Y-%m', InvoiceDate) AS month, ROUND(SUM(Total), 2) AS sales\n"
            "FROM Invoice\n"
            "WHERE InvoiceDate >= '2022-01-01' AND InvoiceDate < '2023-01-01'\n"
            "GROUP BY month\n"
            "ORDER BY sales DESC\n"
            "LIMIT 1"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["难度:中等", "考点:按月聚合", "考点:Top1"],
        note="按开票日期取年月分组；第 1、2 名金额不同，无并列。月份格式在题面给定。",
    ),
    EvalCase(
        id="H4C15",
        query="买过流派为「Metal」的曲目的客户有多少位（按客户去重）？返回一个数。",
        reference_sql=(
            "SELECT COUNT(DISTINCT i.CustomerId) AS customer_cnt\n"
            "FROM Invoice i\n"
            "JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId\n"
            "JOIN Track t ON il.TrackId = t.TrackId\n"
            "JOIN Genre g ON t.GenreId = g.GenreId\n"
            "WHERE g.Name = 'Metal'"
        ),
        must_hit_columns=["Genre.Name", "Track.GenreId", "InvoiceLine.TrackId", "Invoice.CustomerId"],
        tags=["难度:难", "考点:去重计数", "考点:多表关联"],
        note="发票→明细→曲目→流派四表关联后按客户去重；流派名精确等于 Metal。",
    ),
    EvalCase(
        id="H4C16",
        query="作曲者里署名包含 Steve Harris 的曲目有多少首？返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) AS track_cnt\n"
            "FROM Track\n"
            "WHERE Composer LIKE '%Steve Harris%'"
        ),
        must_hit_columns=["Track.Composer"],
        tags=["难度:中等", "考点:模糊匹配", "考点:易混字段"],
        note="作曲者是 Track.Composer 自由文本（多人逗号分隔），需包含匹配；不是 Artist 表。大小写敏感与否结果相同。",
    ),
    EvalCase(
        id="H4C17",
        query="歌单「Heavy Metal Classic」收录的曲目里，有多少首从来没有被卖出过（没有出现在任何发票明细里）？返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) AS unsold_cnt\n"
            "FROM PlaylistTrack pt\n"
            "JOIN Playlist p ON pt.PlaylistId = p.PlaylistId\n"
            "WHERE p.Name = 'Heavy Metal Classic'\n"
            "  AND NOT EXISTS (SELECT 1 FROM InvoiceLine il WHERE il.TrackId = pt.TrackId)"
        ),
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "InvoiceLine.TrackId"],
        tags=["难度:难", "考点:反连接", "考点:多表关联"],
        note="歌单名唯一；收录关系看 PlaylistTrack，销售看 InvoiceLine，二者做反连接。",
    ),
    EvalCase(
        id="H4C18",
        query="历史累计开票金额最高的 3 位客户是谁？返回客户的名、姓和开票金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS sales\n"
            "FROM Invoice i\n"
            "JOIN Customer c ON i.CustomerId = c.CustomerId\n"
            "GROUP BY c.CustomerId, c.FirstName, c.LastName\n"
            "ORDER BY sales DESC\n"
            "LIMIT 3"
        ),
        must_hit_columns=["Customer.FirstName", "Customer.LastName", "Invoice.Total"],
        tags=["难度:中等", "考点:TopN", "考点:易混表"],
        note="名和姓取自 Customer 表（不是 Employee）；第 3、4 名金额不同，无并列。",
    ),
    EvalCase(
        id="H4C19",
        query="目录标价为 1.99 的曲目分属哪些流派，各有多少首？返回流派名称和曲目数。",
        reference_sql=(
            "SELECT g.Name, COUNT(*) AS track_cnt\n"
            "FROM Track t\n"
            "JOIN Genre g ON t.GenreId = g.GenreId\n"
            "WHERE t.UnitPrice = 1.99\n"
            "GROUP BY g.GenreId, g.Name"
        ),
        must_hit_columns=["Track.UnitPrice", "Genre.Name", "Track.GenreId"],
        tags=["难度:中等", "考点:易混字段", "考点:分组计数"],
        note="目录标价是 Track.UnitPrice，不是 InvoiceLine 的成交价；问的是曲目数而非销量。",
    ),
    EvalCase(
        id="H4C20",
        query="用信用卡支付的发票有多少张？返回一个数。",
        reference_sql=UNANSWERABLE_SQL,
        must_hit_columns=[],
        tags=["难度:简单", "陷阱题", "考点:数据缺失"],
        note="Invoice 只有开票日期、开票地址和总金额，没有支付方式字段，无法区分信用卡支付。",
        expect_unanswerable=True,
    ),
]
