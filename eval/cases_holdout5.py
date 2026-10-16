"""
第五套留出评测集：由独立出题人在未见过被测系统表现和已有题目的情况下编写。
ecommerce 30 题（H5E01–H5E30，陷阱 3），Chinook 20 题（H5C01–H5C20，陷阱 3）。

**已冻结，尚未运行。**冻结后第一次运行三个版本，都用冻结时的评测器判分：

    93f9a98   第四套封存时的状态
    35ab795   再加检索桥接表、复核长度预算、模型调用重试、时间保底两处改动、
              筛选值守卫只查相关表和跳过嵌在字段别名里的取值
    冻结时 HEAD 再加一对多连接规则、结果行数上限

压测库（ecommerce_big）只跑冻结时 HEAD，和小库同一套题对比。

出题条件和第三、四套相同：材料逐字沿用 eval/blind_materials/（出题规范只换了题号和文件名）；
不读 README、docs/、eval/ 已有题目和 git 历史，不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本完成，只输出题号和检查项；
出题人的回报里也不含题目内容。组装进仓库时只换了导入、加了这段文件头。

候选路径的验证 SQL 在 eval/cases_holdout5_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

第五套盲写评测题（holdout5）。

只依据本目录下的 ecommerce.md / chinook.md 数据字典与 ecommerce.db / chinook.db 编写，
参考 SQL 均已在对应库上执行验证。
"""

from eval.cases import EvalCase

TRAP_SQL = "SELECT 1 WHERE 0"


HOLDOUT5_ECOMMERCE_CASES = [
    EvalCase(
        id="H5E01",
        query=(
            "按订单的运费金额分组（不限订单状态），每一种运费金额各有多少笔订单、平均实付金额是多少？"
            "返回运费金额、订单数和平均实付金额，平均实付金额保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT freight_amount, COUNT(*) AS order_cnt, ROUND(AVG(pay_amount), 2) AS avg_pay "
            "FROM fact_order GROUP BY freight_amount"
        ),
        must_hit_columns=["fact_order.freight_amount", "fact_order.pay_amount"],
        tags=["难度:简单", "单表", "分组汇总"],
        note="运费金额只有 3 种取值，按取值分组；平均实付按订单粒度求均值，含所有状态。",
    ),
    EvalCase(
        id="H5E02",
        query="一级类目「食品生鲜」下面有哪些二级类目？返回二级类目名称。",
        reference_sql=(
            "SELECT c2.category_name FROM dim_category c2 "
            "JOIN dim_category c1 ON c2.parent_category_id = c1.category_id "
            "WHERE c1.category_name = '食品生鲜'"
        ),
        must_hit_columns=["dim_category.category_name", "dim_category.parent_category_id"],
        tags=["难度:简单", "自关联", "类目层级"],
        note="考类目表自关联：二级类目通过 parent_category_id 指向一级类目，结果为 3 个二级类目名称。",
    ),
    EvalCase(
        id="H5E03",
        query=(
            "按下单日期是星期几统计订单数（不限订单状态）。星期几用 0 到 6 的整数表示，0 表示星期日、6 表示星期六。"
            "返回星期几（整数）和订单数。"
        ),
        reference_sql=(
            "SELECT CAST(strftime('%w', create_time) AS INTEGER) AS weekday, COUNT(*) AS cnt "
            "FROM fact_order GROUP BY weekday"
        ),
        must_hit_columns=[["fact_order.create_time", "dws_shop_daily.stat_date"]],
        tags=["难度:中等", "时间切片", "分组计数"],
        note="按下单时间取星期（SQLite %w 即 0=星期日）；用店铺日汇总表按 stat_date 取星期再对 order_count 求和结果一致（已验证），结果 7 行。",
    ),
    EvalCase(
        id="H5E04",
        query="品牌为「华为」、上架状态为「在售」的商品有哪些？返回商品ID、商品名称和标价。",
        reference_sql=(
            "SELECT product_id, product_name, list_price FROM dim_product "
            "WHERE brand = '华为' AND shelf_status = '在售'"
        ),
        must_hit_columns=["dim_product.brand", "dim_product.shelf_status", "dim_product.list_price"],
        tags=["难度:简单", "单表", "枚举筛选"],
        note="两个枚举条件同时筛选；华为有一件已下架商品需被排除，商品名存在重名所以要求带商品ID。",
    ),
    EvalCase(
        id="H5E05",
        query="商品名称里包含「充电器」三个字的商品有哪些？返回商品ID、品牌和标价。",
        reference_sql=(
            "SELECT product_id, brand, list_price FROM dim_product "
            "WHERE product_name LIKE '%充电器%'"
        ),
        must_hit_columns=["dim_product.product_name", "dim_product.brand", "dim_product.list_price"],
        tags=["难度:简单", "单表", "模糊匹配"],
        note="按商品名称子串匹配，不限上架状态；同名商品分属不同商品ID，结果 6 行。",
    ),
    EvalCase(
        id="H5E06",
        query=(
            "2024-05-20 至 2024-05-26（按下单时间，含首尾两天）下单、且已经付过款的订单"
            "（订单状态为已完成、已支付或已退款），按下单渠道统计实付金额合计。"
            "返回下单渠道和实付金额合计，金额保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT channel, ROUND(SUM(pay_amount), 2) AS pay_sum FROM fact_order "
            "WHERE date(create_time) BETWEEN '2024-05-20' AND '2024-05-26' "
            "AND order_status IN ('已完成', '已支付', '已退款') "
            "GROUP BY channel"
        ),
        must_hit_columns=[
            "fact_order.channel",
            "fact_order.pay_amount",
            "fact_order.create_time",
            ["fact_order.order_status", "fact_order.pay_time"],
        ],
        tags=["难度:中等", "日期区间", "状态口径", "分组汇总"],
        note="已付款 = 三种状态，等价于 pay_time 非空（已验证两条路径结果一致）；日期按下单日期含首尾，金额用实付 pay_amount。",
    ),
    EvalCase(
        id="H5E07",
        query=(
            "只看订单状态为「已完成」的订单，按下单渠道统计平均每笔订单购买多少件商品"
            "（该渠道订单明细的购买件数之和 ÷ 该渠道订单笔数）。返回下单渠道和平均每单件数，保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT o.channel, ROUND(SUM(i.quantity) * 1.0 / COUNT(DISTINCT o.order_id), 2) AS avg_qty "
            "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
            "WHERE o.order_status = '已完成' GROUP BY o.channel"
        ),
        must_hit_columns=["fact_order_item.quantity", "fact_order.channel", "fact_order.order_status"],
        tags=["难度:中等", "比率", "多表关联", "销量口径"],
        note="分子为件数（quantity 之和）而非明细行数，分母为订单数需对订单去重；每笔订单都有明细。",
    ),
    EvalCase(
        id="H5E08",
        query="下单渠道为「直播间」的订单，各支付渠道的支付流水分别有多少笔？返回支付渠道和流水笔数。",
        reference_sql=(
            "SELECT p.pay_channel, COUNT(*) AS cnt FROM fact_payment p "
            "JOIN fact_order o ON p.order_id = o.order_id "
            "WHERE o.channel = '直播间' GROUP BY p.pay_channel"
        ),
        must_hit_columns=["fact_payment.pay_channel", "fact_order.channel"],
        tags=["难度:中等", "多表关联", "渠道区分"],
        note="区分下单渠道（fact_order.channel）与支付渠道（fact_payment.pay_channel）；每笔订单至多一条支付流水。",
    ),
    EvalCase(
        id="H5E09",
        query=(
            "退款状态为「退款成功」的退款记录，按退款原因统计笔数和退款金额合计。"
            "返回退款原因、退款笔数和退款金额合计，金额保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT refund_reason, COUNT(*) AS cnt, ROUND(SUM(refund_amount), 2) AS amt "
            "FROM fact_refund WHERE refund_status = '退款成功' GROUP BY refund_reason"
        ),
        must_hit_columns=[
            "fact_refund.refund_reason",
            "fact_refund.refund_status",
            "fact_refund.refund_amount",
        ],
        tags=["难度:中等", "单表", "分组汇总"],
        note="只算退款成功，排除退款中；5 个原因各一行。",
    ),
    EvalCase(
        id="H5E10",
        query=(
            "只看订单状态为「已完成」的订单，按商品所属的二级类目计算明细优惠率："
            "明细行优惠金额之和 ÷（明细单价 × 购买件数）之和。返回二级类目名称和优惠率，"
            "用 0 到 1 之间的小数表示，保留 4 位小数。"
        ),
        reference_sql=(
            "SELECT c.category_name, "
            "ROUND(SUM(i.item_discount_amount) / SUM(i.item_price * i.quantity), 4) AS disc_rate "
            "FROM fact_order_item i "
            "JOIN fact_order o ON i.order_id = o.order_id "
            "JOIN dim_product p ON i.product_id = p.product_id "
            "JOIN dim_category c ON p.category_id = c.category_id "
            "WHERE o.order_status = '已完成' GROUP BY c.category_id, c.category_name"
        ),
        must_hit_columns=[
            "fact_order_item.item_discount_amount",
            "fact_order_item.item_price",
            "fact_order_item.quantity",
            "fact_order.order_status",
            "dim_category.category_name",
        ],
        tags=["难度:难", "比率", "多表关联", "类目层级"],
        note="比率按“先求和再相除”计算，不是逐行比率的平均；商品直接挂二级类目，结果 9 行。",
    ),
    EvalCase(
        id="H5E11",
        query=(
            "有过退款订单（退款订单笔数大于 0）的用户，按注册渠道统计人数，以及这些用户累计下单笔数"
            "（含所有状态的订单）的平均值。返回注册渠道、用户数和平均累计下单笔数，平均值保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT u.register_channel, COUNT(*) AS user_cnt, "
            "ROUND(AVG(s.total_order_count), 2) AS avg_orders "
            "FROM dws_user_summary s JOIN dim_user u ON s.user_id = u.user_id "
            "WHERE s.refund_order_count > 0 GROUP BY u.register_channel"
        ),
        must_hit_columns=[
            "dim_user.register_channel",
            ["dws_user_summary.refund_order_count", "fact_order.order_status"],
            ["dws_user_summary.total_order_count", "fact_order.user_id"],
        ],
        tags=["难度:中等", "汇总表", "用户画像", "分组平均"],
        note="可直接用用户汇总表的退款订单数与累计下单笔数，也可从订单表按用户聚合（退款订单 = 状态为已退款），两条路径已验证一致；平均按用户粒度。",
    ),
    EvalCase(
        id="H5E12",
        query=(
            "2024-05-01 至 2024-05-07（按订单下单日期，含首尾两天）期间，GMV（订单商品总金额之和，"
            "不限订单状态）合计最高的前 3 家店铺是哪些？返回店铺名称和 GMV 合计，保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT s.shop_name, ROUND(SUM(d.gmv), 2) AS gmv_sum "
            "FROM dws_shop_daily d JOIN dim_shop s ON d.shop_id = s.shop_id "
            "WHERE d.stat_date BETWEEN '2024-05-01' AND '2024-05-07' "
            "GROUP BY d.shop_id, s.shop_name ORDER BY gmv_sum DESC LIMIT 3"
        ),
        must_hit_columns=[
            "dim_shop.shop_name",
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            ["dws_shop_daily.stat_date", "fact_order.create_time"],
        ],
        tags=["难度:中等", "TopN", "汇总表", "日期区间"],
        note="店铺日汇总表 gmv 与订单表 order_amount 按下单日期聚合结果一致（已验证）；第 3、4 名不并列。",
    ),
    EvalCase(
        id="H5E13",
        query=(
            "只看订单状态为「已完成」的订单，每个二级类目的商品分别被多少位不同的用户买过？"
            "同一用户多次购买同一类目只算一次。返回二级类目名称和购买用户数。"
        ),
        reference_sql=(
            "SELECT c.category_name, COUNT(DISTINCT o.user_id) AS buyer_cnt "
            "FROM fact_order_item i "
            "JOIN fact_order o ON i.order_id = o.order_id "
            "JOIN dim_product p ON i.product_id = p.product_id "
            "JOIN dim_category c ON p.category_id = c.category_id "
            "WHERE o.order_status = '已完成' GROUP BY c.category_id, c.category_name"
        ),
        must_hit_columns=[
            "fact_order.user_id",
            "fact_order.order_status",
            "dim_product.category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "去重计数", "多表关联", "类目层级"],
        note="明细→订单取买家、明细→商品→二级类目，按类目对用户去重计数；不去重会得到明细行数。结果 9 行。",
    ),
    EvalCase(
        id="H5E14",
        query=(
            "支付流水按支付发生时间所在的小时（0 到 23 的整数）统计笔数，笔数最多的前 3 个小时是哪几个？"
            "返回小时（整数）和流水笔数。"
        ),
        reference_sql=(
            "SELECT CAST(strftime('%H', pay_time) AS INTEGER) AS pay_hour, COUNT(*) AS cnt "
            "FROM fact_payment GROUP BY pay_hour ORDER BY cnt DESC LIMIT 3"
        ),
        must_hit_columns=[["fact_payment.pay_time", "fact_order.pay_time"]],
        tags=["难度:中等", "TopN", "时间切片"],
        note="按支付流水计数；订单表 pay_time 与支付流水 pay_time 逐笔一致，按订单表已付款订单统计结果相同（已验证）；第 3 名 45 笔、第 4 名 44 笔。",
    ),
    EvalCase(
        id="H5E15",
        query="有多少笔订单的买家所在城市与下单店铺所在城市相同？不限订单状态，返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) FROM fact_order o "
            "JOIN dim_user u ON o.user_id = u.user_id "
            "JOIN dim_shop s ON o.shop_id = s.shop_id "
            "WHERE u.city = s.city"
        ),
        must_hit_columns=["dim_user.city", "dim_shop.city"],
        tags=["难度:中等", "多表关联", "同名字段区分"],
        note="买家城市取 dim_user.city，店铺城市取 dim_shop.city，两个同名字段含义不同，需各自关联。",
    ),
    EvalCase(
        id="H5E16",
        query=(
            "退款申请日期在 2024-05-10 至 2024-05-20 之间（含首尾两天）、且退款状态为「退款成功」的退款，"
            "退款金额合计是多少？返回一个数，保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT ROUND(SUM(refund_amount), 2) FROM fact_refund "
            "WHERE refund_status = '退款成功' "
            "AND date(apply_time) BETWEEN '2024-05-10' AND '2024-05-20'"
        ),
        must_hit_columns=[
            "fact_refund.apply_time",
            "fact_refund.refund_status",
            "fact_refund.refund_amount",
        ],
        tags=["难度:中等", "日期区间", "退款口径"],
        note="按退款申请日期切分必须用 fact_refund.apply_time；店铺日汇总表的 refund_amount 按订单下单日期归属，不能用来回答。",
    ),
    EvalCase(
        id="H5E17",
        query=(
            "退款状态为「退款成功」的退款，按对应订单当初使用的支付渠道统计退款笔数和退款金额合计。"
            "返回支付渠道、退款笔数和退款金额合计，金额保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT p.pay_channel, COUNT(*) AS cnt, ROUND(SUM(r.refund_amount), 2) AS amt "
            "FROM fact_refund r JOIN fact_payment p ON r.order_id = p.order_id "
            "WHERE r.refund_status = '退款成功' GROUP BY p.pay_channel"
        ),
        must_hit_columns=[
            "fact_payment.pay_channel",
            "fact_refund.refund_status",
            "fact_refund.refund_amount",
        ],
        tags=["难度:难", "多表关联", "退款口径", "渠道区分"],
        note="退款表与支付流水经 order_id 关联，每笔退款订单恰有一条支付流水，不会重复计数；支付渠道不是下单渠道。",
    ),
    EvalCase(
        id="H5E18",
        query=(
            "在店铺日汇总数据里，每家店铺有多少天的支付转化率低于 1（即当天有下单买家没有付款）？"
            "只统计汇总表里有记录的日期。返回店铺名称和天数。"
        ),
        reference_sql=(
            "SELECT s.shop_name, COUNT(*) AS days "
            "FROM dws_shop_daily d JOIN dim_shop s ON d.shop_id = s.shop_id "
            "WHERE d.conversion_rate < 1 GROUP BY d.shop_id, s.shop_name"
        ),
        must_hit_columns=["dws_shop_daily.conversion_rate", "dim_shop.shop_name"],
        tags=["难度:中等", "汇总表", "条件计数"],
        note="conversion_rate 是 0 到 1 的小数，等于 1 表示当天所有下单买家都已付款；每家店铺都有这样的天数，结果 15 行。",
    ),
    EvalCase(
        id="H5E19",
        query=(
            "行为类型为「加购」的行为记录，按产生行为的用户所在年龄段统计记录数和平均页面停留秒数。"
            "返回年龄段、加购记录数和平均停留秒数，平均值保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT u.age_group, COUNT(*) AS cnt, ROUND(AVG(b.stay_seconds), 2) AS avg_stay "
            "FROM fact_user_behavior b JOIN dim_user u ON b.user_id = u.user_id "
            "WHERE b.behavior_type = '加购' GROUP BY u.age_group"
        ),
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "fact_user_behavior.stay_seconds",
            "dim_user.age_group",
        ],
        tags=["难度:中等", "行为分析", "用户画像", "分组平均"],
        note="平均停留按行为记录粒度计算；年龄段取原文分组，5 个年龄段各一行。",
    ),
    EvalCase(
        id="H5E20",
        query=(
            "最近一次下单时间在 2024-05-25 00:00:00 及以后的用户，按用户所在省份统计人数。"
            "返回省份和用户数。"
        ),
        reference_sql=(
            "SELECT u.province, COUNT(*) AS user_cnt "
            "FROM dws_user_summary s JOIN dim_user u ON s.user_id = u.user_id "
            "WHERE s.last_order_time >= '2024-05-25' GROUP BY u.province"
        ),
        must_hit_columns=[
            "dim_user.province",
            ["dws_user_summary.last_order_time", "fact_order.create_time"],
        ],
        tags=["难度:中等", "汇总表", "用户画像", "时间筛选"],
        note="可用用户汇总表 last_order_time，也可从订单表按用户取 MAX(create_time)，两者已验证一致；省份取买家所在省份，结果 8 行。",
    ),
    EvalCase(
        id="H5E21",
        query=(
            "行为类型为「浏览」的行为记录，按被浏览商品所属的二级类目统计浏览次数，"
            "次数最多的前 3 个二级类目是哪些？返回类目名称和浏览次数。"
        ),
        reference_sql=(
            "SELECT c.category_name, COUNT(*) AS cnt FROM fact_user_behavior b "
            "JOIN dim_product p ON b.product_id = p.product_id "
            "JOIN dim_category c ON p.category_id = c.category_id "
            "WHERE b.behavior_type = '浏览' "
            "GROUP BY c.category_id, c.category_name ORDER BY cnt DESC LIMIT 3"
        ),
        must_hit_columns=[
            "fact_user_behavior.behavior_type",
            "dim_product.category_id",
            "dim_category.category_name",
        ],
        tags=["难度:难", "TopN", "行为分析", "多表关联"],
        note="行为→商品→二级类目三表关联，浏览次数按记录行数计；第 3 名 281、第 4 名 278，无并列。",
    ),
    EvalCase(
        id="H5E22",
        query=(
            "按下单日期统计全平台每天的订单量（不限订单状态），哪一天订单量最多？"
            "返回日期（YYYY-MM-DD 格式）和当天订单量。"
        ),
        reference_sql=(
            "SELECT stat_date, SUM(order_count) AS cnt FROM dws_shop_daily "
            "GROUP BY stat_date ORDER BY cnt DESC LIMIT 1"
        ),
        must_hit_columns=[["dws_shop_daily.stat_date", "fact_order.create_time"]],
        tags=["难度:中等", "TopN", "按日汇总"],
        note="店铺日汇总表按日求和与订单表按 date(create_time) 计数结果一致（已验证）；第 1 名 41 单、第 2 名 38 单。",
    ),
    EvalCase(
        id="H5E23",
        query="开业日期早于 2020-01-01 的店铺，在库中一共有多少笔订单？不限订单状态，返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) FROM fact_order o JOIN dim_shop s ON o.shop_id = s.shop_id "
            "WHERE s.open_time < '2020-01-01'"
        ),
        must_hit_columns=["dim_shop.open_time"],
        tags=["难度:中等", "日期筛选", "多表关联"],
        note="按店铺开业日期筛店铺，再数这些店铺的全部订单；用店铺日汇总表 order_count 求和结果相同。",
    ),
    EvalCase(
        id="H5E24",
        query=(
            "按店铺类型统计退款订单率：订单状态为「已退款」的订单数 ÷ 该类型店铺的全部订单数（不限状态）。"
            "返回店铺类型和退款订单率，用 0 到 1 之间的小数表示，保留 4 位小数。"
        ),
        reference_sql=(
            "SELECT s.shop_type, "
            "ROUND(SUM(CASE WHEN o.order_status = '已退款' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS rate "
            "FROM fact_order o JOIN dim_shop s ON o.shop_id = s.shop_id GROUP BY s.shop_type"
        ),
        must_hit_columns=["dim_shop.shop_type", "fact_order.order_status"],
        tags=["难度:难", "比率", "条件计数", "多表关联"],
        note="分子分母都按订单计；分母含所有状态；需整数转小数避免整除。",
    ),
    EvalCase(
        id="H5E25",
        query="订单优惠金额为 0（没有享受任何优惠）的订单，按订单状态统计各有多少笔。返回订单状态和订单数。",
        reference_sql=(
            "SELECT order_status, COUNT(*) AS cnt FROM fact_order "
            "WHERE discount_amount = 0 GROUP BY order_status"
        ),
        must_hit_columns=["fact_order.discount_amount", "fact_order.order_status"],
        tags=["难度:简单", "单表", "分组计数"],
        note="按订单级 discount_amount = 0 筛选；5 种订单状态各一行。",
    ),
    EvalCase(
        id="H5E26",
        query=(
            "有多少位用户在同一家店铺下过至少 2 笔订单（不限订单状态）？"
            "同一用户若在多家店铺都满足条件，只算一次。返回一个数。"
        ),
        reference_sql=(
            "SELECT COUNT(DISTINCT user_id) FROM ("
            "SELECT user_id, shop_id FROM fact_order "
            "GROUP BY user_id, shop_id HAVING COUNT(*) >= 2)"
        ),
        must_hit_columns=["fact_order.user_id", "fact_order.shop_id"],
        tags=["难度:难", "子查询", "去重计数", "复购"],
        note="先按用户×店铺计数筛出≥2 的组合，再对用户去重；不去重会得到组合数而不是用户数。",
    ),
    EvalCase(
        id="H5E27",
        query=(
            "品牌为「珀莱雅」的每件商品，在订单状态为「已完成」的订单里各卖出多少件、成交金额多少？"
            "商品按商品ID区分（存在重名商品），返回商品ID、商品名称、销量（件数）和成交金额（明细行成交金额之和，保留 2 位小数）。"
        ),
        reference_sql=(
            "SELECT i.product_id, p.product_name, SUM(i.quantity) AS qty, ROUND(SUM(i.item_amount), 2) AS amt "
            "FROM fact_order_item i "
            "JOIN fact_order o ON i.order_id = o.order_id "
            "JOIN dim_product p ON i.product_id = p.product_id "
            "WHERE p.brand = '珀莱雅' AND o.order_status = '已完成' "
            "GROUP BY i.product_id, p.product_name"
        ),
        must_hit_columns=[
            "dim_product.brand",
            "fact_order_item.quantity",
            "fact_order_item.item_amount",
            "fact_order.order_status",
        ],
        tags=["难度:中等", "多表关联", "销量口径", "品牌"],
        note="珀莱雅 4 件商品中 3 件同名，必须按商品ID分组；销量为 quantity 之和，金额为 item_amount 之和。",
    ),
    EvalCase(
        id="H5E28",
        query="2024 年 5 月用户给商品打的评分里，平均评分最低的 3 个商品是哪些？返回商品名称和平均评分（保留 2 位小数）。",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失:商品评分"],
        note="库中没有任何商品评价或评分数据（行为表只有浏览、加购、收藏），应说明缺失，不能拿退款原因等数据替代。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H5E29",
        query="2024 年 5 月用户在站内搜索次数最多的 5 个搜索关键词是什么？返回关键词和搜索次数。",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失:搜索记录"],
        note="库中没有搜索日志或搜索关键词字段，行为类型只有浏览、加购、收藏，应说明缺失。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H5E30",
        query="各店铺 2024 年 5 月的广告推广花费分别是多少？返回店铺名称和推广花费合计。",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失:营销费用"],
        note="库中没有广告、推广或营销费用数据；优惠金额是让利给买家的折扣，不是推广花费，应说明缺失。",
        expect_unanswerable=True,
    ),
]


HOLDOUT5_CHINOOK_CASES = [
    EvalCase(
        id="H5C01",
        query="所在国家为「USA」的客户，按客户所在的州统计各有多少位客户。返回州和客户数。",
        reference_sql=(
            "SELECT State, COUNT(*) AS cnt FROM Customer WHERE Country = 'USA' GROUP BY State"
        ),
        must_hit_columns=["Customer.Country", "Customer.State"],
        tags=["难度:简单", "单表", "分组计数", "同名字段区分"],
        note="客户所在州取 Customer.State（员工的 State 全为 AB，开票州是发票快照）；美国客户的州均非空，结果 11 行。",
    ),
    EvalCase(
        id="H5C02",
        query=(
            "文件大小（Bytes 字段）最大的 3 首曲目是哪些？按字节数排序，返回曲目ID、曲目名称和文件大小"
            "（换算成 MB，1 MB = 1048576 字节，保留 2 位小数）。"
        ),
        reference_sql=(
            "SELECT TrackId, Name, ROUND(Bytes / 1048576.0, 2) AS size_mb FROM Track "
            "ORDER BY Bytes DESC LIMIT 3"
        ),
        must_hit_columns=["Track.Bytes", "Track.Name"],
        tags=["难度:简单", "单表", "TopN", "单位换算"],
        note="按 Bytes 排序（输出列是换算后的 MB）；曲目名有重名所以带曲目ID；第 3 名 587051735 字节、第 4 名 577829804 字节，无并列。",
    ),
    EvalCase(
        id="H5C03",
        query="艺术家「Iron Maiden」一共有多少张专辑？返回一个数。",
        reference_sql=(
            "SELECT COUNT(*) FROM Album al JOIN Artist ar ON al.ArtistId = ar.ArtistId "
            "WHERE ar.Name = 'Iron Maiden'"
        ),
        must_hit_columns=["Artist.Name", "Album.ArtistId"],
        tags=["难度:简单", "两表关联", "计数"],
        note="艺术家名称唯一，专辑表按 ArtistId 关联计数。",
    ),
    EvalCase(
        id="H5C04",
        query="所在国家为「Brazil」的客户有哪些？返回客户的名、姓和所在城市。",
        reference_sql=(
            "SELECT FirstName, LastName, City FROM Customer WHERE Country = 'Brazil'"
        ),
        must_hit_columns=[
            "Customer.Country",
            "Customer.FirstName",
            "Customer.LastName",
            "Customer.City",
        ],
        tags=["难度:简单", "单表", "同名字段区分"],
        note="客户属性取 Customer 表，不能落到同名字段的 Employee 表；结果 5 人。",
    ),
    EvalCase(
        id="H5C05",
        query=(
            "哪些艺术家名下有媒体格式为「Protected MPEG-4 video file」的曲目？"
            "返回艺术家名称和该格式的曲目数。"
        ),
        reference_sql=(
            "SELECT ar.Name, COUNT(*) AS cnt FROM Track t "
            "JOIN MediaType m ON t.MediaTypeId = m.MediaTypeId "
            "JOIN Album al ON t.AlbumId = al.AlbumId "
            "JOIN Artist ar ON al.ArtistId = ar.ArtistId "
            "WHERE m.Name = 'Protected MPEG-4 video file' "
            "GROUP BY ar.ArtistId, ar.Name"
        ),
        must_hit_columns=["MediaType.Name", "Track.MediaTypeId", "Album.ArtistId", "Artist.Name"],
        tags=["难度:中等", "四表关联", "分组计数"],
        note="曲目→专辑→艺术家取表演者（不是 Composer），媒体格式按原文筛选；艺术家名唯一，结果 7 行。",
    ),
    EvalCase(
        id="H5C06",
        query=(
            "哪些曲目同时被歌单「Heavy Metal Classic」和歌单「90’s Music」收录？返回曲目ID和曲目名称。"
        ),
        reference_sql=(
            "SELECT t.TrackId, t.Name FROM Track t "
            "WHERE t.TrackId IN (SELECT pt.TrackId FROM PlaylistTrack pt "
            "JOIN Playlist p ON pt.PlaylistId = p.PlaylistId WHERE p.Name = 'Heavy Metal Classic') "
            "AND t.TrackId IN (SELECT pt.TrackId FROM PlaylistTrack pt "
            "JOIN Playlist p ON pt.PlaylistId = p.PlaylistId WHERE p.Name = '90’s Music')"
        ),
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "PlaylistTrack.PlaylistId", "Track.Name"],
        tags=["难度:中等", "多对多", "交集"],
        note="求两个歌单收录曲目的交集；两个歌单名都唯一，“90’s Music”含弯引号需按原文匹配；结果 5 首。",
    ),
    EvalCase(
        id="H5C07",
        query=(
            "职位为「Sales Support Agent」的员工中出生日期最早的那一位，他负责的客户分布在哪些国家？"
            "按客户所在国家统计人数，返回国家和客户数。"
        ),
        reference_sql=(
            "SELECT c.Country, COUNT(*) AS cust_cnt FROM Customer c "
            "WHERE c.SupportRepId = (SELECT e.EmployeeId FROM Employee e "
            "WHERE e.Title = 'Sales Support Agent' ORDER BY e.BirthDate LIMIT 1) "
            "GROUP BY c.Country"
        ),
        must_hit_columns=[
            "Employee.Title",
            "Employee.BirthDate",
            "Customer.SupportRepId",
            "Customer.Country",
        ],
        tags=["难度:难", "子查询", "员工与客户区分"],
        note="出生日期只有员工有；先在销售支持员工中取出生最早者（出生日期无并列），再经 SupportRepId 找其客户，国家取 Customer.Country；结果 12 行。",
    ),
    EvalCase(
        id="H5C08",
        query=(
            "收录曲目数最多的前 3 个歌单是哪些？歌单按歌单ID区分（存在重名歌单），"
            "返回歌单ID、歌单名称和收录曲目数。"
        ),
        reference_sql=(
            "SELECT p.PlaylistId, p.Name, COUNT(*) AS cnt FROM PlaylistTrack pt "
            "JOIN Playlist p ON pt.PlaylistId = p.PlaylistId "
            "GROUP BY p.PlaylistId, p.Name ORDER BY cnt DESC LIMIT 3"
        ),
        must_hit_columns=["PlaylistTrack.PlaylistId", "Playlist.Name"],
        tags=["难度:中等", "TopN", "多对多"],
        note="两个同名“Music”歌单按 ID 分开计；第 3 名 1477 首、第 4 名 213 首，无并列。",
    ),
    EvalCase(
        id="H5C09",
        query=(
            "歌单「90’s Music」收录的曲目里，按音乐流派统计收录曲目数，最多的前 3 个流派是哪些？"
            "返回流派名称和收录曲目数。"
        ),
        reference_sql=(
            "SELECT g.Name, COUNT(*) AS cnt FROM PlaylistTrack pt "
            "JOIN Playlist p ON pt.PlaylistId = p.PlaylistId "
            "JOIN Track t ON pt.TrackId = t.TrackId "
            "JOIN Genre g ON t.GenreId = g.GenreId "
            "WHERE p.Name = '90’s Music' "
            "GROUP BY g.GenreId, g.Name ORDER BY cnt DESC LIMIT 3"
        ),
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Track.GenreId", "Genre.Name"],
        tags=["难度:难", "TopN", "多对多", "四表关联"],
        note="歌单名含弯引号 ’，需按原文匹配；歌单名唯一；第 3 名 193 首、第 4 名 164 首，无并列。",
    ),
    EvalCase(
        id="H5C10",
        query=(
            "曲目名称与其所属专辑名称逐字完全相同（区分大小写）的曲目，按艺术家统计数量，"
            "只列出这类曲目不少于 2 首的艺术家。返回艺术家名称和曲目数。"
        ),
        reference_sql=(
            "SELECT ar.Name, COUNT(*) AS cnt FROM Track t "
            "JOIN Album al ON t.AlbumId = al.AlbumId "
            "JOIN Artist ar ON al.ArtistId = ar.ArtistId "
            "WHERE t.Name = al.Title "
            "GROUP BY ar.ArtistId, ar.Name HAVING COUNT(*) >= 2"
        ),
        must_hit_columns=["Track.Name", "Album.Title", "Album.ArtistId", "Artist.Name"],
        tags=["难度:难", "三表关联", "HAVING", "同名字段区分"],
        note="曲目名 Track.Name 与专辑名 Album.Title 做等值比较（SQLite = 区分大小写）；有一首仅大小写不同，不区分大小写会让 Iron Maiden 多 1 首；结果 7 行。",
    ),
    EvalCase(
        id="H5C11",
        query="列出每位有直属上级的员工及其直属上级。返回员工的名、姓，以及上级的名、姓。",
        reference_sql=(
            "SELECT e.FirstName, e.LastName, m.FirstName AS mgr_first, m.LastName AS mgr_last "
            "FROM Employee e JOIN Employee m ON e.ReportsTo = m.EmployeeId"
        ),
        must_hit_columns=["Employee.ReportsTo", "Employee.FirstName", "Employee.LastName"],
        tags=["难度:难", "自关联", "层级"],
        note="Employee 通过 ReportsTo 自关联；总经理没有上级不出现，结果 7 行。",
    ),
    EvalCase(
        id="H5C12",
        query=(
            "按客户登记的所在国家统计，客户数不少于 3 位的国家，各国客户的人均消费额是多少？"
            "人均消费额 = 该国客户的发票金额合计 ÷ 该国客户数。返回国家、客户数和人均消费额（保留 2 位小数）。"
        ),
        reference_sql=(
            "SELECT c.Country, COUNT(DISTINCT c.CustomerId) AS cust_cnt, "
            "ROUND(SUM(i.Total) / COUNT(DISTINCT c.CustomerId), 2) AS avg_spend "
            "FROM Customer c JOIN Invoice i ON i.CustomerId = c.CustomerId "
            "GROUP BY c.Country HAVING COUNT(DISTINCT c.CustomerId) >= 3"
        ),
        must_hit_columns=["Customer.Country", ["Invoice.Total", "InvoiceLine.UnitPrice"]],
        tags=["难度:中等", "HAVING", "去重计数", "人均指标"],
        note="客户数需在关联发票后去重；每位客户都有发票，故分母与客户表人数一致；金额走 Total 或明细求和结果一致（已验证），结果 6 行。",
    ),
    EvalCase(
        id="H5C13",
        query=(
            "每种媒体文件格式的曲目分别被多少位不同的客户买过？同一客户多次购买同一格式只算一次。"
            "返回媒体格式名称和购买客户数。"
        ),
        reference_sql=(
            "SELECT m.Name, COUNT(DISTINCT i.CustomerId) AS cust_cnt "
            "FROM InvoiceLine il "
            "JOIN Invoice i ON il.InvoiceId = i.InvoiceId "
            "JOIN Track t ON il.TrackId = t.TrackId "
            "JOIN MediaType m ON t.MediaTypeId = m.MediaTypeId "
            "GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["Invoice.CustomerId", "Track.MediaTypeId", "MediaType.Name"],
        tags=["难度:难", "四表关联", "去重计数"],
        note="明细→发票取客户、明细→曲目→媒体格式，按格式对客户去重；5 种格式都有人买过，结果 5 行。",
    ),
    EvalCase(
        id="H5C14",
        query=(
            "专辑数不少于 5 张的艺术家，各有几张专辑、平均每张专辑有多少首曲目"
            "（该艺术家的曲目总数 ÷ 专辑数）？返回艺术家名称、专辑数和平均每张专辑曲目数（保留 2 位小数）。"
        ),
        reference_sql=(
            "SELECT ar.Name, COUNT(DISTINCT al.AlbumId) AS album_cnt, "
            "ROUND(COUNT(t.TrackId) * 1.0 / COUNT(DISTINCT al.AlbumId), 2) AS avg_tracks "
            "FROM Artist ar JOIN Album al ON al.ArtistId = ar.ArtistId "
            "JOIN Track t ON t.AlbumId = al.AlbumId "
            "GROUP BY ar.ArtistId, ar.Name HAVING COUNT(DISTINCT al.AlbumId) >= 5"
        ),
        must_hit_columns=["Album.ArtistId", "Track.AlbumId", "Artist.Name"],
        tags=["难度:难", "三表关联", "HAVING", "去重计数"],
        note="关联曲目后专辑数需去重；库中每张专辑都有曲目，故专辑数与专辑表一致；需整数转小数避免整除；结果 7 行。",
    ),
    EvalCase(
        id="H5C15",
        query=(
            "作曲者（Composer）为空的曲目，一共卖出了多少钱（按发票明细行成交单价 × 购买数量求和）？"
            "返回一个数，保留 2 位小数。"
        ),
        reference_sql=(
            "SELECT ROUND(SUM(il.UnitPrice * il.Quantity), 2) FROM InvoiceLine il "
            "JOIN Track t ON il.TrackId = t.TrackId WHERE t.Composer IS NULL"
        ),
        must_hit_columns=["Track.Composer", "InvoiceLine.UnitPrice", "InvoiceLine.Quantity"],
        tags=["难度:难", "空值判断", "两表关联", "销售额"],
        note="Composer 为 NULL（库中无空串）；金额用成交单价而非目录标价，结果按明细行求和。",
    ),
    EvalCase(
        id="H5C16",
        query=(
            "2025 年（按开票日期）卖出的曲目，按媒体文件格式统计售出份数（发票明细行购买数量之和）。"
            "返回媒体格式名称和售出份数。"
        ),
        reference_sql=(
            "SELECT m.Name, SUM(il.Quantity) AS qty FROM InvoiceLine il "
            "JOIN Invoice i ON il.InvoiceId = i.InvoiceId "
            "JOIN Track t ON il.TrackId = t.TrackId "
            "JOIN MediaType m ON t.MediaTypeId = m.MediaTypeId "
            "WHERE i.InvoiceDate >= '2025-01-01' AND i.InvoiceDate < '2026-01-01' "
            "GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "MediaType.Name", "InvoiceLine.Quantity"],
        tags=["难度:中等", "四表关联", "日期筛选"],
        note="时间取发票开票日期，份数取明细 Quantity 之和（本库每行均为 1，与行数相等）；2025 年只售出 3 种格式。",
    ),
    EvalCase(
        id="H5C17",
        query=(
            "哪些客户在 2025 年（按开票日期，2025-01-01 至 2025-12-31）一张发票都没有？"
            "返回客户的名和姓。"
        ),
        reference_sql=(
            "SELECT c.FirstName, c.LastName FROM Customer c "
            "WHERE NOT EXISTS (SELECT 1 FROM Invoice i WHERE i.CustomerId = c.CustomerId "
            "AND i.InvoiceDate >= '2025-01-01' AND i.InvoiceDate < '2026-01-01')"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.CustomerId", "Customer.FirstName", "Customer.LastName"],
        tags=["难度:难", "反连接", "日期筛选"],
        note="反连接且日期条件要放在子查询/连接条件里，放到外层 WHERE 会把这些客户过滤掉；开票日期带时间部分，用半开区间；结果 13 位客户。",
    ),
    EvalCase(
        id="H5C18",
        query="节奏（BPM）在 120 以上的曲目有多少首？返回一个数。",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失:曲目节奏"],
        note="曲目表只有时长、文件大小、标价等，没有 BPM 或节奏字段；不能用时长或文件大小推算，应说明缺失。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H5C19",
        query="2024 年开具的发票里，税额合计是多少？返回一个数。",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失:税额"],
        note="发票表只有含义为总金额的 Total，没有税额、税率或不含税金额字段，应说明缺失而不是返回发票总额。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H5C20",
        query="会员积分最高的 5 位客户是谁？返回客户的名、姓和积分。",
        reference_sql=TRAP_SQL,
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "缺失:会员积分"],
        note="客户表只有姓名、公司、地址与联系方式，库中没有会员积分或等级体系；不能用消费额冒充积分，应说明缺失。",
        expect_unanswerable=True,
    ),
]
