"""
第一套多轮追问留出集：三个库（ecommerce、Chinook、Sakila），验证会话里的追问——指代、省略、加条件、换角度、
跨轮、依赖结果。由独立出题人在未见过被测系统表现和已有题目的情况下编写。ecommerce 12 组 43 轮（M1E01–M1E12，
陷阱轮 2），Chinook 8 组 32 轮（M1C01–M1C08，陷阱轮 1），Sakila 8 组 31 轮（M1S01–M1S08，陷阱轮 1）。

**已用过一次。**这套题于 08520c4 冻结并推送后第一次运行，每组 3 次，结果见 docs/实验记录.md「第一套多轮追问留出集：
会话记忆把上一轮的回答挤出了窗口」：

    版本                         第 1 轮       追问              整组全对
    08520c4  冻结版              83/84         90/222（41%）     2/84
    修复短期记忆窗口之后         83/84         181/222（82%）    54/84

冻结版的追问几乎都错在第 2 轮：一条查库回答连同整条链路的产物被算成 4000–6000 token，比记忆窗口还大，刚写进去就被
挤出窗口，第 2 轮看不到上一轮。修复版是照着这套题的失败修的，它的分数不算泛化证据。没有发现可证明没法判分的题，
冻结版就是最终版；问法可能有两种理解的四轮（M1E10-2、M1E02-4、M1S08-2、M1S08-4）记在实验记录里，没改。

每一组在一个新会话里按顺序问，每一轮单独判分（eval/multiturn.py）。出题规范是 eval/blind_materials/出题规范_多轮.md：
第 1 轮自包含，之后每一轮单看答不了、又必须去库里查新数据；每一轮的参考 SQL 自包含，表达"结合前面的问答这一轮真正问的
是什么"。材料（三份数据字典、三个库）逐字沿用 eval/blind_materials/ 和 runtime_data/；不读 README、docs/、eval/
已有题目和 git 历史，不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本（eval/blind_materials/check_holdout.py）完成，只输出题号和检查项；
出题人的回报里也不含题目内容。两轮替换：第一轮 5 组的第 1 轮和已有题目结果集相同、3 组问法太像、本套内 2 对开头太像，
另有 12 轮 TopN 并列需人工核对、15 轮取了整却没写小数位；第二轮 3 组第 1 轮问法仍像。之后去重为 0；排序依据不是输出列、
脚本判定不了并列的 10 轮，出题人按原始排序值逐一核过。组装进仓库时只换了导入、加了这段文件头和末尾的 MULTITURN1_BANKS。

候选路径的验证 SQL 在 eval/cases_multiturn1_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

多轮追问评测题（三个库）。

每组在一个新会话里按顺序问，每一轮单独判分。每一轮的 reference_sql 单独就能在对应库上执行，
表达的是"结合前面的问答，这一轮真正问的是什么"。
"""

from eval.cases import EvalCase, MultiTurnCase

TRAP_SQL = "SELECT 1 WHERE 0"

# 常用片段（ecommerce）
_MAY_ORDER = "o.create_time >= '2024-05-01' AND o.create_time < '2024-06-01'"


# =====================================================================================
# ecommerce
# =====================================================================================

MULTITURN1_ECOMMERCE_CASES = [
    # ---------------------------------------------------------------- M1E01
    MultiTurnCase(
        id="M1E01",
        tags=["难度:中等"],
        note="店铺成交额前5 → 这几家的退款（含退款中）→ 只看退款成功。考指代上一轮的店铺集合、在退款口径上加条件并省略其余部分。",
        turns=[
            EvalCase(
                id="M1E01-1",
                query="2024年5月成交额排前5的店铺是哪几家？列出店铺名和成交额，金额保留两位小数。",
                reference_sql=(
                    "SELECT s.shop_name, ROUND(SUM(o.order_amount), 2) AS gmv "
                    "FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id "
                    f"WHERE {_MAY_ORDER} "
                    "GROUP BY s.shop_id, s.shop_name ORDER BY SUM(o.order_amount) DESC LIMIT 5"
                ),
                must_hit_columns=[
                    "dim_shop.shop_name",
                    ["fact_order.order_amount", "dws_shop_daily.gmv"],
                ],
                note="成交额按数据字典即 GMV：全部订单的商品总金额（不限状态）；也可走 dws_shop_daily.gmv，两条路径结果一致。第5名 957534.57 与第6名 862516.06 不并列。",
            ),
            EvalCase(
                id="M1E01-2",
                query="这几家各退了多少钱？还在退款中的也算上，保留两位小数。",
                reference_sql=(
                    "SELECT s.shop_name, ROUND(SUM(r.refund_amount), 2) AS refund_amount "
                    "FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
                    "JOIN dim_shop s ON s.shop_id = o.shop_id "
                    "WHERE s.shop_name IN ('臻品自营店15','优选旗舰店1','旗舰旗舰店7','臻品旗舰店4','旗舰自营店12') "
                    "GROUP BY s.shop_id, s.shop_name"
                ),
                must_hit_columns=[
                    "dim_shop.shop_name",
                    ["fact_refund.refund_amount", "dws_shop_daily.refund_amount"],
                ],
                tags=["追问:指代"],
                note="'这几家'= 上一轮成交额前5 的5家店。退款按订单所属店铺归属，退款成功和退款中都算。dws_shop_daily.refund_amount 按下单日归属，全月合计与 fact_refund 一致。5家都有退款，结果5行。",
            ),
            EvalCase(
                id="M1E01-3",
                query="只算已经退款成功的呢？顺便给下笔数，金额同样保留两位小数。",
                reference_sql=(
                    "SELECT s.shop_name, ROUND(SUM(r.refund_amount), 2) AS refund_amount, COUNT(*) AS refund_cnt "
                    "FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
                    "JOIN dim_shop s ON s.shop_id = o.shop_id "
                    "WHERE s.shop_name IN ('臻品自营店15','优选旗舰店1','旗舰旗舰店7','臻品旗舰店4','旗舰自营店12') "
                    "AND r.refund_status = '退款成功' "
                    "GROUP BY s.shop_id, s.shop_name"
                ),
                must_hit_columns=["dim_shop.shop_name", "fact_refund.refund_status", "fact_refund.refund_amount"],
                tags=["追问:加条件", "追问:省略"],
                note="沿用上一轮的5家店和退款金额，只加'退款成功'条件，并补退款笔数（一笔订单最多一条退款，笔数=退款记录数）。5家都有退款成功的记录，结果5行。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E02
    MultiTurnCase(
        id="M1E02",
        tags=["难度:中等"],
        note="一级类目销量 → 销量最高的一级类目拆二级 → 电脑办公按品牌拆 → 这三个品牌的加购次数。考依赖上一轮结果确定类目、省略指标、换分组和换行为指标。",
        turns=[
            EvalCase(
                id="M1E02-1",
                query="已付款的订单里，三个一级类目各卖出去多少件？",
                reference_sql=(
                    "SELECT c1.category_name, SUM(i.quantity) AS qty "
                    "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
                    "JOIN dim_product p ON p.product_id = i.product_id "
                    "JOIN dim_category c2 ON c2.category_id = p.category_id "
                    "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
                    "WHERE o.pay_time IS NOT NULL "
                    "GROUP BY c1.category_id, c1.category_name"
                ),
                must_hit_columns=[
                    "fact_order_item.quantity",
                    ["fact_order.pay_time", "fact_order.order_status"],
                    ["dim_product.category_id", "dim_shop.main_category_id"],
                    "dim_category.parent_category_id",
                ],
                note="已付款 = pay_time 不为空（含已支付、已完成、已退款）；销量 = 件数求和。商品挂二级类目，需经 parent_category_id 归到一级。按店铺主营类目归类结果相同。",
            ),
            EvalCase(
                id="M1E02-2",
                query="卖得最多的那个，按二级类目拆开看看。",
                reference_sql=(
                    "SELECT c2.category_name, SUM(i.quantity) AS qty "
                    "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
                    "JOIN dim_product p ON p.product_id = i.product_id "
                    "JOIN dim_category c2 ON c2.category_id = p.category_id "
                    "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
                    "WHERE o.pay_time IS NOT NULL AND c1.category_name = '数码电器' "
                    "GROUP BY c2.category_id, c2.category_name"
                ),
                must_hit_columns=[
                    "fact_order_item.quantity",
                    ["fact_order.pay_time", "fact_order.order_status"],
                    ["dim_product.category_id", "dim_shop.main_category_id"],
                    "dim_category.category_name",
                ],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮销量最高的一级类目是数码电器（1049 件，第二名美妆护肤 994 件），沿用已付款、件数口径，拆成其下3个二级类目。",
            ),
            EvalCase(
                id="M1E02-3",
                query="电脑办公按品牌再拆一下呢？",
                reference_sql=(
                    "SELECT p.brand, SUM(i.quantity) AS qty "
                    "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
                    "JOIN dim_product p ON p.product_id = i.product_id "
                    "JOIN dim_category c2 ON c2.category_id = p.category_id "
                    "WHERE o.pay_time IS NOT NULL AND c2.category_name = '电脑办公' "
                    "GROUP BY p.brand"
                ),
                must_hit_columns=[
                    "dim_product.brand",
                    "fact_order_item.quantity",
                    ["fact_order.pay_time", "fact_order.order_status"],
                    ["dim_product.category_id", "dim_shop.main_category_id"],
                ],
                tags=["追问:加条件", "追问:换角度"],
                note="收窄到上一轮结果里的二级类目'电脑办公'，指标仍是已付款订单的销量件数，分组换成品牌：戴尔、华硕、联想3行。",
            ),
            EvalCase(
                id="M1E02-4",
                query="这三个品牌的商品5月被加购了多少次？",
                reference_sql=(
                    "SELECT p.brand, COUNT(*) AS cart_cnt "
                    "FROM fact_user_behavior b JOIN dim_product p ON p.product_id = b.product_id "
                    "WHERE b.behavior_type = '加购' AND p.brand IN ('戴尔','华硕','联想') "
                    "AND b.behavior_time >= '2024-05-01' AND b.behavior_time < '2024-06-01' "
                    "GROUP BY p.brand"
                ),
                must_hit_columns=["dim_product.brand", "fact_user_behavior.behavior_type"],
                tags=["追问:指代", "追问:换角度"],
                note="'这三个品牌'= 上一轮的戴尔、华硕、联想；这三个品牌的商品全部在电脑办公类目下，限不限类目结果一样。加购次数按加购行为记录数。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E03
    MultiTurnCase(
        id="M1E03",
        tags=["难度:难"],
        note="会员等级的用户数和累计消费 → 钻石会员消费前5 → 这5人里谁退过款 → 回到这5人看最近一次下单的店铺。考省略指标、指代、跨轮回指更早一轮的5个人。",
        turns=[
            EvalCase(
                id="M1E03-1",
                query="每个会员等级各有多少用户？各等级的用户累计一共花了多少钱？金额保留两位小数。",
                reference_sql=(
                    "SELECT u.member_level, COUNT(*) AS user_cnt, ROUND(SUM(s.total_pay_amount), 2) AS total_pay "
                    "FROM dim_user u JOIN dws_user_summary s ON s.user_id = u.user_id "
                    "GROUP BY u.member_level"
                ),
                must_hit_columns=["dim_user.member_level", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
                note="累计花了多少钱 = 已付款订单的实付金额合计（dws_user_summary.total_pay_amount），用户数按全部注册用户。走 fact_order 已付款订单聚合结果一致。",
            ),
            EvalCase(
                id="M1E03-2",
                query="那钻石会员里排前5的是谁？各花了多少？同样保留两位小数。",
                reference_sql=(
                    "SELECT u.user_name, ROUND(s.total_pay_amount, 2) AS total_pay "
                    "FROM dim_user u JOIN dws_user_summary s ON s.user_id = u.user_id "
                    "WHERE u.member_level = '钻石会员' "
                    "ORDER BY s.total_pay_amount DESC LIMIT 5"
                ),
                must_hit_columns=[
                    "dim_user.user_name",
                    "dim_user.member_level",
                    ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"],
                ],
                tags=["追问:加条件", "追问:省略"],
                note="'排前5'沿用上一轮的累计消费口径，收窄到钻石会员。第5名 47152.24 与第6名 44387.84 不并列。",
            ),
            EvalCase(
                id="M1E03-3",
                query="他们当中谁退过款？各退了多少钱？保留两位小数。",
                reference_sql=(
                    "SELECT u.user_name, ROUND(SUM(r.refund_amount), 2) AS refund_amount "
                    "FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
                    "JOIN dim_user u ON u.user_id = o.user_id "
                    "WHERE u.user_name IN ('用户10105','用户10068','用户10118','用户10035','用户10021') "
                    "GROUP BY u.user_id, u.user_name"
                ),
                must_hit_columns=["dim_user.user_name", "fact_refund.refund_amount"],
                tags=["追问:指代", "追问:加条件"],
                note="'他们'= 上一轮的5位钻石会员，只返回有退款记录的人（3位）。这3笔退款都是退款成功，算不算退款中结果都一样。",
            ),
            EvalCase(
                id="M1E03-4",
                query="回到那5位钻石会员，他们各自最近一次下单是在哪家店？",
                reference_sql=(
                    "SELECT u.user_name, sh.shop_name "
                    "FROM fact_order o JOIN dim_user u ON u.user_id = o.user_id "
                    "JOIN dim_shop sh ON sh.shop_id = o.shop_id "
                    "WHERE u.user_name IN ('用户10105','用户10068','用户10118','用户10035','用户10021') "
                    "AND o.create_time = (SELECT MAX(o2.create_time) FROM fact_order o2 WHERE o2.user_id = o.user_id)"
                ),
                must_hit_columns=[
                    "dim_user.user_name",
                    "dim_shop.shop_name",
                    ["fact_order.create_time", "dws_user_summary.last_order_time"],
                ],
                tags=["追问:跨轮", "追问:指代"],
                note="'那5位'指第2轮的5人（第3轮只剩3人）。最近一次下单按下单时间 create_time（不限订单状态），与 dws_user_summary.last_order_time 一致；5人各自的最近一笔订单唯一，无同一时刻多单。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E04
    MultiTurnCase(
        id="M1E04",
        tags=["难度:中等"],
        note="下单第二天才付款的订单用了哪些支付渠道 → 只看直播间 → 陷阱：问主播（库里没有）→ 回到第1轮那批订单，花呗分期按年龄段拆。考跨天付款的判断、加条件、陷阱识别、陷阱后跨轮。",
        turns=[
            EvalCase(
                id="M1E04-1",
                query="2024年5月有些订单是下单第二天才付的款（付款日期和下单日期不在同一天），这些订单分别用的什么支付渠道？各几笔、付了多少钱？金额保留两位小数。",
                reference_sql=(
                    "SELECT p.pay_channel, COUNT(*) AS pay_cnt, ROUND(SUM(p.pay_amount), 2) AS pay_total "
                    "FROM fact_payment p JOIN fact_order o ON o.order_id = p.order_id "
                    f"WHERE {_MAY_ORDER} AND date(o.pay_time) <> date(o.create_time) "
                    "GROUP BY p.pay_channel"
                ),
                must_hit_columns=[
                    "fact_payment.pay_channel",
                    "fact_order.create_time",
                    ["fact_order.pay_time", "fact_payment.pay_time"],
                    ["fact_payment.pay_amount", "fact_order.pay_amount"],
                ],
                note="下单到付款最长2小时，付款日期≠下单日期即跨零点、第二天才付。支付流水的支付时间、金额与订单上的一致，两种取法结果相同。4个渠道都有。",
            ),
            EvalCase(
                id="M1E04-2",
                query="只看直播间下的单呢？同样保留两位小数。",
                reference_sql=(
                    "SELECT p.pay_channel, COUNT(*) AS pay_cnt, ROUND(SUM(p.pay_amount), 2) AS pay_total "
                    "FROM fact_payment p JOIN fact_order o ON o.order_id = p.order_id "
                    f"WHERE {_MAY_ORDER} AND date(o.pay_time) <> date(o.create_time) AND o.channel = '直播间' "
                    "GROUP BY p.pay_channel"
                ),
                must_hit_columns=[
                    "fact_payment.pay_channel",
                    "fact_order.channel",
                    ["fact_order.pay_time", "fact_payment.pay_time"],
                    ["fact_payment.pay_amount", "fact_order.pay_amount"],
                ],
                tags=["追问:加条件", "追问:省略"],
                note="沿用'第二天才付款的订单、按支付渠道看笔数和金额'，只加下单渠道=直播间，4行。",
            ),
            EvalCase(
                id="M1E04-3",
                query="这些直播间的单，分别是哪位主播带的货？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里只有下单渠道=直播间，没有主播/带货人信息，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M1E04-4",
                query="回到第一问那批跨天付款的订单，花呗分期那几笔按买家年龄段拆开看看，金额同样保留两位小数。",
                reference_sql=(
                    "SELECT u.age_group, COUNT(*) AS pay_cnt, ROUND(SUM(p.pay_amount), 2) AS pay_total "
                    "FROM fact_payment p JOIN fact_order o ON o.order_id = p.order_id "
                    "JOIN dim_user u ON u.user_id = o.user_id "
                    f"WHERE {_MAY_ORDER} AND date(o.pay_time) <> date(o.create_time) AND p.pay_channel = '花呗分期' "
                    "GROUP BY u.age_group"
                ),
                must_hit_columns=[
                    "fact_payment.pay_channel",
                    "dim_user.age_group",
                    ["fact_order.pay_time", "fact_payment.pay_time"],
                    ["fact_payment.pay_amount", "fact_order.pay_amount"],
                ],
                tags=["追问:跨轮", "追问:换角度"],
                note="回到第1轮（跨天付款、不限直播间），只看花呗分期，按下单用户年龄段拆笔数和金额，5个年龄段都有。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E05
    MultiTurnCase(
        id="M1E05",
        tags=["难度:难"],
        note="退款原因分布 → 商品质量问题按一级类目 → 笔数最多的类目涉及哪些店 → 七天无理由也按一级类目。考退款归属类目的路径、依赖结果、跨轮沿用第2轮的问法。",
        turns=[
            EvalCase(
                id="M1E05-1",
                query="每种退款原因各有多少笔退款、一共退了多少钱？退款中的也算，金额保留两位小数。",
                reference_sql=(
                    "SELECT refund_reason, COUNT(*) AS refund_cnt, ROUND(SUM(refund_amount), 2) AS refund_total "
                    "FROM fact_refund GROUP BY refund_reason"
                ),
                must_hit_columns=["fact_refund.refund_reason", "fact_refund.refund_amount"],
                note="退款成功和退款中都算；口径在本轮交代，后面沿用。",
            ),
            EvalCase(
                id="M1E05-2",
                query="商品质量问题的那些，按一级类目分一下，金额同样保留两位小数。",
                reference_sql=(
                    "SELECT c1.category_name, COUNT(*) AS refund_cnt, ROUND(SUM(r.refund_amount), 2) AS refund_total "
                    "FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
                    "JOIN dim_shop s ON s.shop_id = o.shop_id "
                    "JOIN dim_category c2 ON c2.category_id = s.main_category_id "
                    "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
                    "WHERE r.refund_reason = '商品质量问题' "
                    "GROUP BY c1.category_id, c1.category_name"
                ),
                must_hit_columns=[
                    "fact_refund.refund_reason",
                    "fact_refund.refund_amount",
                    ["dim_shop.main_category_id", "dim_product.category_id"],
                    "dim_category.parent_category_id",
                ],
                tags=["追问:加条件", "追问:换角度"],
                note="沿用笔数和金额两个指标。一笔订单的商品只属于一个类目，退款归到订单的类目；经店铺主营类目或经订单明细→商品类目（按订单去重）结果一致。",
            ),
            EvalCase(
                id="M1E05-3",
                query="笔数最多的那个类目，具体涉及哪几家店？各几笔、多少钱？金额保留两位小数。",
                reference_sql=(
                    "SELECT s.shop_name, COUNT(*) AS refund_cnt, ROUND(SUM(r.refund_amount), 2) AS refund_total "
                    "FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
                    "JOIN dim_shop s ON s.shop_id = o.shop_id "
                    "JOIN dim_category c2 ON c2.category_id = s.main_category_id "
                    "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
                    "WHERE r.refund_reason = '商品质量问题' AND c1.category_name = '美妆护肤' "
                    "GROUP BY s.shop_id, s.shop_name"
                ),
                must_hit_columns=[
                    "dim_shop.shop_name",
                    "fact_refund.refund_reason",
                    "fact_refund.refund_amount",
                    ["dim_shop.main_category_id", "dim_product.category_id"],
                ],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮笔数最多的是美妆护肤（9笔，第二名数码电器8笔；金额也最高），仍限商品质量问题，按店铺拆开，6家店。",
            ),
            EvalCase(
                id="M1E05-4",
                query="七天无理由的呢？也按一级类目看，金额同样保留两位小数。",
                reference_sql=(
                    "SELECT c1.category_name, COUNT(*) AS refund_cnt, ROUND(SUM(r.refund_amount), 2) AS refund_total "
                    "FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id "
                    "JOIN dim_shop s ON s.shop_id = o.shop_id "
                    "JOIN dim_category c2 ON c2.category_id = s.main_category_id "
                    "JOIN dim_category c1 ON c1.category_id = c2.parent_category_id "
                    "WHERE r.refund_reason = '七天无理由' "
                    "GROUP BY c1.category_id, c1.category_name"
                ),
                must_hit_columns=[
                    "fact_refund.refund_reason",
                    "fact_refund.refund_amount",
                    ["dim_shop.main_category_id", "dim_product.category_id"],
                    "dim_category.parent_category_id",
                ],
                tags=["追问:省略", "追问:跨轮"],
                note="'也按一级类目看'明确沿用第2轮的问法（笔数+金额、按一级类目），只把退款原因换成七天无理由，不沿用第3轮的美妆护肤限定。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E06
    MultiTurnCase(
        id="M1E06",
        tags=["难度:中等"],
        note="浏览平均停留超过300秒的二级类目 → 它们的已付款销量 → 陷阱：用户评分（库里没有）→ 回到浏览，看浏览次数。考指代、陷阱识别、陷阱后跨轮。",
        turns=[
            EvalCase(
                id="M1E06-1",
                query="2024年5月，哪些二级类目的商品被浏览时平均每次停留超过300秒？列出类目和平均停留秒数，保留1位小数。",
                reference_sql=(
                    "SELECT c.category_name, ROUND(AVG(b.stay_seconds), 1) AS avg_stay "
                    "FROM fact_user_behavior b JOIN dim_product p ON p.product_id = b.product_id "
                    "JOIN dim_category c ON c.category_id = p.category_id "
                    "WHERE b.behavior_type = '浏览' "
                    "AND b.behavior_time >= '2024-05-01' AND b.behavior_time < '2024-06-01' "
                    "GROUP BY c.category_id, c.category_name HAVING AVG(b.stay_seconds) > 300"
                ),
                must_hit_columns=[
                    "fact_user_behavior.behavior_type",
                    "fact_user_behavior.stay_seconds",
                    ["dim_product.category_id", "dim_shop.main_category_id"],
                    "dim_category.category_name",
                ],
                note="只算浏览行为的停留秒数平均值，按未取整的平均值与300比较。家用电器、生鲜果蔬、休闲零食3个；最接近门槛的洗护发品是299.2，不会因取整进出。",
            ),
            EvalCase(
                id="M1E06-2",
                query="它们5月各卖出去多少件？只算付了款的订单。",
                reference_sql=(
                    "SELECT c.category_name, SUM(i.quantity) AS qty "
                    "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
                    "JOIN dim_product p ON p.product_id = i.product_id "
                    "JOIN dim_category c ON c.category_id = p.category_id "
                    f"WHERE o.pay_time IS NOT NULL AND {_MAY_ORDER} "
                    "AND c.category_name IN ('家用电器','生鲜果蔬','休闲零食') "
                    "GROUP BY c.category_id, c.category_name"
                ),
                must_hit_columns=[
                    "fact_order_item.quantity",
                    ["fact_order.pay_time", "fact_order.order_status"],
                    ["dim_product.category_id", "dim_shop.main_category_id"],
                ],
                tags=["追问:指代", "追问:换角度"],
                note="'它们'= 上一轮的家用电器、生鲜果蔬、休闲零食；指标换成已付款订单的销量件数。",
            ),
            EvalCase(
                id="M1E06-3",
                query="这几个类目的商品，用户打分平均是多少？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里没有商品评价/评分数据（行为只有浏览、加购、收藏），应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M1E06-4",
                query="回到浏览那个问题，这三个类目5月各被浏览了多少次？",
                reference_sql=(
                    "SELECT c.category_name, COUNT(*) AS view_cnt "
                    "FROM fact_user_behavior b JOIN dim_product p ON p.product_id = b.product_id "
                    "JOIN dim_category c ON c.category_id = p.category_id "
                    "WHERE b.behavior_type = '浏览' "
                    "AND b.behavior_time >= '2024-05-01' AND b.behavior_time < '2024-06-01' "
                    "AND c.category_name IN ('家用电器','生鲜果蔬','休闲零食') "
                    "GROUP BY c.category_id, c.category_name"
                ),
                must_hit_columns=[
                    "fact_user_behavior.behavior_type",
                    ["dim_product.category_id", "dim_shop.main_category_id"],
                ],
                tags=["追问:跨轮", "追问:指代"],
                note="回到第1轮的三个类目和浏览行为，浏览次数=浏览行为记录数。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E07
    MultiTurnCase(
        id="M1E07",
        tags=["难度:中等"],
        note="按店铺所在城市数订单 → 成都的几家店 → 其中买家也在成都的订单 → 回到第1问改按买家所在城市。考店铺城市与买家城市的区分、加条件、跨轮换分组。",
        turns=[
            EvalCase(
                id="M1E07-1",
                query="按店铺所在城市，2024年5月各城市的订单数是多少？",
                reference_sql=(
                    "SELECT s.city, COUNT(*) AS order_cnt "
                    "FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id "
                    f"WHERE {_MAY_ORDER} GROUP BY s.city"
                ),
                must_hit_columns=["dim_shop.city", ["fact_order.shop_id", "dws_shop_daily.order_count"]],
                note="订单数不加状态条件（口径约定）。店铺分布在7个城市。",
            ),
            EvalCase(
                id="M1E07-2",
                query="成都的那几家店分别是多少？",
                reference_sql=(
                    "SELECT s.shop_name, COUNT(*) AS order_cnt "
                    "FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id "
                    f"WHERE {_MAY_ORDER} AND s.city = '成都' "
                    "GROUP BY s.shop_id, s.shop_name"
                ),
                must_hit_columns=[
                    "dim_shop.shop_name",
                    "dim_shop.city",
                    ["fact_order.shop_id", "dws_shop_daily.order_count"],
                ],
                tags=["追问:加条件", "追问:省略"],
                note="沿用'店铺所在城市、订单数'，收窄到成都并拆到店铺：3家。",
            ),
            EvalCase(
                id="M1E07-3",
                query="这几家店的订单里，买家本身也在成都的各有几笔？",
                reference_sql=(
                    "SELECT s.shop_name, COUNT(*) AS order_cnt "
                    "FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id "
                    "JOIN dim_user u ON u.user_id = o.user_id "
                    f"WHERE {_MAY_ORDER} AND s.city = '成都' AND u.city = '成都' "
                    "GROUP BY s.shop_id, s.shop_name"
                ),
                must_hit_columns=["dim_shop.shop_name", "dim_shop.city", "dim_user.city"],
                tags=["追问:指代", "追问:加条件"],
                note="'这几家店'= 上一轮成都的3家；再加买家所在城市=成都。3家都非零。",
            ),
            EvalCase(
                id="M1E07-4",
                query="回到第一个问题，改成按买家所在城市来统计呢？",
                reference_sql=(
                    "SELECT u.city, COUNT(*) AS order_cnt "
                    "FROM fact_order o JOIN dim_user u ON u.user_id = o.user_id "
                    f"WHERE {_MAY_ORDER} GROUP BY u.city"
                ),
                must_hit_columns=["dim_user.city", "fact_order.user_id"],
                tags=["追问:跨轮", "追问:换角度"],
                note="回到第1轮：全部店铺、5月订单数，只把分组从店铺所在城市换成买家所在城市，10个城市。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E08
    MultiTurnCase(
        id="M1E08",
        tags=["难度:中等"],
        note="全平台成交额最高的一天 → 那天成交额前三的店 → 这三家那天被取消或未付款的订单。考指代具体日期、依赖结果、加条件。",
        turns=[
            EvalCase(
                id="M1E08-1",
                query="2024年5月哪一天全平台的成交额最高？那天成交额是多少？金额保留两位小数。",
                reference_sql=(
                    "SELECT stat_date, ROUND(SUM(gmv), 2) AS gmv FROM dws_shop_daily "
                    "WHERE stat_date BETWEEN '2024-05-01' AND '2024-05-31' "
                    "GROUP BY stat_date ORDER BY SUM(gmv) DESC LIMIT 1"
                ),
                must_hit_columns=[
                    ["dws_shop_daily.gmv", "fact_order.order_amount"],
                    ["dws_shop_daily.stat_date", "fact_order.create_time"],
                ],
                note="成交额即 GMV，按下单日期归属（全部订单商品总金额）。最高 2024-05-26（752462.79），第二 05-14（600857.67），不并列。也可从 fact_order 按下单日期聚合，结果一致。",
            ),
            EvalCase(
                id="M1E08-2",
                query="那天成交额排前三的店铺是哪几家？各多少？同样保留两位小数。",
                reference_sql=(
                    "SELECT s.shop_name, ROUND(d.gmv, 2) AS gmv "
                    "FROM dws_shop_daily d JOIN dim_shop s ON s.shop_id = d.shop_id "
                    "WHERE d.stat_date = '2024-05-26' ORDER BY d.gmv DESC LIMIT 3"
                ),
                must_hit_columns=[
                    "dim_shop.shop_name",
                    ["dws_shop_daily.gmv", "fact_order.order_amount"],
                    ["dws_shop_daily.stat_date", "fact_order.create_time"],
                ],
                tags=["追问:指代", "追问:依赖结果"],
                note="'那天'= 上一轮答案 2024-05-26。第3名 99474.76 与第4名 99028.69 不并列。",
            ),
            EvalCase(
                id="M1E08-3",
                query="这三家那天下的单里，有已取消或者待支付的吗？列出订单号、店铺和订单状态。",
                reference_sql=(
                    "SELECT o.order_id, s.shop_name, o.order_status "
                    "FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id "
                    "WHERE o.create_time >= '2024-05-26' AND o.create_time < '2024-05-27' "
                    "AND s.shop_name IN ('优选旗舰店1','臻品旗舰店4','旗舰旗舰店7') "
                    "AND o.order_status IN ('已取消','待支付')"
                ),
                must_hit_columns=["fact_order.order_id", "fact_order.order_status", "fact_order.create_time", "dim_shop.shop_name"],
                tags=["追问:指代", "追问:加条件"],
                note="三家店、5月26日下单，订单状态为已取消或待支付（两者合起来正好是 pay_time 为空的订单）。结果2行，都在旗舰旗舰店7。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E09
    MultiTurnCase(
        id="M1E09",
        tags=["难度:简单"],
        note="按店铺类型数店和订单 → 自营店拆到每家 → 这两家在售商品数。考店铺类型字段（店名里的'自营'不代表类型）、省略指标、指代。",
        turns=[
            EvalCase(
                id="M1E09-1",
                query="各店铺类型分别有几家店？2024年5月各下了多少单？",
                reference_sql=(
                    "SELECT s.shop_type, COUNT(DISTINCT s.shop_id) AS shop_cnt, COUNT(o.order_id) AS order_cnt "
                    "FROM dim_shop s LEFT JOIN fact_order o ON o.shop_id = s.shop_id "
                    "AND o.create_time >= '2024-05-01' AND o.create_time < '2024-06-01' "
                    "GROUP BY s.shop_type"
                ),
                must_hit_columns=["dim_shop.shop_type"],
                note="店铺类型取 shop_type 原值（旗舰店、专营店、自营店、个人店）；订单数不加状态条件。",
            ),
            EvalCase(
                id="M1E09-2",
                query="把自营店拆到每家店看看。",
                reference_sql=(
                    "SELECT s.shop_name, COUNT(*) AS order_cnt "
                    "FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id "
                    f"WHERE {_MAY_ORDER} AND s.shop_type = '自营店' "
                    "GROUP BY s.shop_id, s.shop_name"
                ),
                must_hit_columns=["dim_shop.shop_type", "dim_shop.shop_name"],
                tags=["追问:加条件", "追问:省略"],
                note="【存疑】指标没说，按上一轮唯一有意义的逐店指标即5月订单数；有人可能顺带输出别的列。自营店按 shop_type='自营店' 取，是京选自营店3、好物专营店14（店名带'自营'的其他店类型并不是自营店）。",
            ),
            EvalCase(
                id="M1E09-3",
                query="这两家店现在在售的商品各有几个？",
                reference_sql=(
                    "SELECT s.shop_name, COUNT(*) AS on_sale_cnt "
                    "FROM dim_product p JOIN dim_shop s ON s.shop_id = p.shop_id "
                    "WHERE s.shop_name IN ('京选自营店3','好物专营店14') AND p.shelf_status = '在售' "
                    "GROUP BY s.shop_id, s.shop_name"
                ),
                must_hit_columns=["dim_product.shelf_status", "dim_shop.shop_name"],
                tags=["追问:指代", "追问:换角度"],
                note="'这两家'= 上一轮的两家自营店；在售=上架状态'在售'（不含预售、已下架）。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E10
    MultiTurnCase(
        id="M1E10",
        tags=["难度:中等"],
        note="已下架商品里单件毛利前3 → 它们的已付款销量 → 卖得最多的那个按会员等级拆。考同名商品按商品ID区分、指代、依赖结果。",
        turns=[
            EvalCase(
                id="M1E10-1",
                query="已下架的商品里，按标价算的单件毛利最高的3个是哪些？列出商品ID、商品名和毛利，毛利保留两位小数。",
                reference_sql=(
                    "SELECT product_id, product_name, ROUND(list_price - cost_price, 2) AS unit_margin "
                    "FROM dim_product WHERE shelf_status = '已下架' "
                    "ORDER BY list_price - cost_price DESC LIMIT 3"
                ),
                must_hit_columns=["dim_product.shelf_status", "dim_product.list_price", "dim_product.cost_price"],
                note="单件毛利按标价与成本价之差。第3名 2382.33 与第4名 1967.30 不并列。",
            ),
            EvalCase(
                id="M1E10-2",
                query="这3个5月卖出去多少件？只算付了款的订单。",
                reference_sql=(
                    "SELECT i.product_id, p.product_name, SUM(i.quantity) AS qty "
                    "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
                    "JOIN dim_product p ON p.product_id = i.product_id "
                    f"WHERE o.pay_time IS NOT NULL AND {_MAY_ORDER} "
                    "AND i.product_id IN (30041, 30031, 30023) "
                    "GROUP BY i.product_id, p.product_name"
                ),
                must_hit_columns=[
                    "fact_order_item.quantity",
                    "fact_order_item.product_id",
                    ["fact_order.pay_time", "fact_order.order_status"],
                ],
                tags=["追问:指代", "追问:换角度"],
                note="'这3个'按商品ID（30041、30031、30023）。其中'都乐 海南芒果 3斤'另有一个同名商品，必须按ID算，不能按名称合并。",
            ),
            EvalCase(
                id="M1E10-3",
                query="卖得最多的那个，按买家的会员等级拆一下件数。",
                reference_sql=(
                    "SELECT u.member_level, SUM(i.quantity) AS qty "
                    "FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id "
                    "JOIN dim_user u ON u.user_id = o.user_id "
                    f"WHERE o.pay_time IS NOT NULL AND {_MAY_ORDER} AND i.product_id = 30023 "
                    "GROUP BY u.member_level"
                ),
                must_hit_columns=[
                    "dim_user.member_level",
                    "fact_order_item.quantity",
                    ["fact_order.pay_time", "fact_order.order_status"],
                ],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮卖得最多的是商品30023（51件，其余44、42），沿用已付款口径，按下单用户会员等级拆，4个等级都有。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E11
    MultiTurnCase(
        id="M1E11",
        tags=["难度:简单"],
        note="各下单渠道的订单取消率 → 直播间按年龄段拆 → 小程序的呢。考比率口径沿用、加条件换分组、省略。",
        turns=[
            EvalCase(
                id="M1E11-1",
                query="2024年5月各下单渠道的订单取消率分别是多少？按订单笔数算，用小数表示，保留4位。",
                reference_sql=(
                    "SELECT o.channel, ROUND(1.0 * SUM(CASE WHEN o.order_status = '已取消' THEN 1 ELSE 0 END) / COUNT(*), 4) AS cancel_rate "
                    f"FROM fact_order o WHERE {_MAY_ORDER} GROUP BY o.channel"
                ),
                must_hit_columns=["fact_order.channel", "fact_order.order_status"],
                note="取消率=已取消订单笔数/该渠道全部订单笔数（订单数不加状态条件）。下单渠道是订单上的 channel，不是用户注册渠道。",
            ),
            EvalCase(
                id="M1E11-2",
                query="直播间的，按下单用户的年龄段拆开看看，同样保留4位小数。",
                reference_sql=(
                    "SELECT u.age_group, ROUND(1.0 * SUM(CASE WHEN o.order_status = '已取消' THEN 1 ELSE 0 END) / COUNT(*), 4) AS cancel_rate "
                    "FROM fact_order o JOIN dim_user u ON u.user_id = o.user_id "
                    f"WHERE {_MAY_ORDER} AND o.channel = '直播间' GROUP BY u.age_group"
                ),
                must_hit_columns=["fact_order.channel", "fact_order.order_status", "dim_user.age_group"],
                tags=["追问:加条件", "追问:换角度"],
                note="沿用取消率口径，只看直播间订单，按下单用户年龄段分组，分母是该年龄段在直播间的全部订单。5个年龄段都有取消，取消率都非零。",
            ),
            EvalCase(
                id="M1E11-3",
                query="小程序的呢？也保留4位小数。",
                reference_sql=(
                    "SELECT u.age_group, ROUND(1.0 * SUM(CASE WHEN o.order_status = '已取消' THEN 1 ELSE 0 END) / COUNT(*), 4) AS cancel_rate "
                    "FROM fact_order o JOIN dim_user u ON u.user_id = o.user_id "
                    f"WHERE {_MAY_ORDER} AND o.channel = '小程序' GROUP BY u.age_group"
                ),
                must_hit_columns=["fact_order.channel", "fact_order.order_status", "dim_user.age_group"],
                tags=["追问:省略"],
                note="完全沿用上一轮（取消率、按年龄段），只把下单渠道换成小程序。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1E12
    MultiTurnCase(
        id="M1E12",
        tags=["难度:中等"],
        note="累计下单笔数前4的用户 → 他们的浏览次数 → 浏览最多的那位收藏了什么 → 回到4人看谁退过款。考指代、依赖结果、跨轮回到第1轮的4人。",
        turns=[
            EvalCase(
                id="M1E12-1",
                query="累计下单笔数最多的4位用户是谁？各下了几单？",
                reference_sql=(
                    "SELECT u.user_name, s.total_order_count "
                    "FROM dws_user_summary s JOIN dim_user u ON u.user_id = s.user_id "
                    "ORDER BY s.total_order_count DESC LIMIT 4"
                ),
                must_hit_columns=["dim_user.user_name", ["dws_user_summary.total_order_count", "fact_order.user_id"]],
                note="下单笔数不加状态条件。11、10、10、9，第5名是8单，不并列。",
            ),
            EvalCase(
                id="M1E12-2",
                query="他们5月各浏览了多少次商品？",
                reference_sql=(
                    "SELECT u.user_name, COUNT(*) AS view_cnt "
                    "FROM fact_user_behavior b JOIN dim_user u ON u.user_id = b.user_id "
                    "WHERE b.behavior_type = '浏览' AND u.user_name IN ('用户10016','用户10122','用户10129','用户10173') "
                    "AND b.behavior_time >= '2024-05-01' AND b.behavior_time < '2024-06-01' "
                    "GROUP BY u.user_id, u.user_name"
                ),
                must_hit_columns=["dim_user.user_name", "fact_user_behavior.behavior_type"],
                tags=["追问:指代", "追问:换角度"],
                note="'他们'= 上一轮4人；浏览次数=浏览行为记录数。",
            ),
            EvalCase(
                id="M1E12-3",
                query="浏览最多的那位，收藏过哪些商品？",
                reference_sql=(
                    "SELECT p.product_name FROM fact_user_behavior b "
                    "JOIN dim_product p ON p.product_id = b.product_id "
                    "JOIN dim_user u ON u.user_id = b.user_id "
                    "WHERE u.user_name = '用户10122' AND b.behavior_type = '收藏'"
                ),
                must_hit_columns=["fact_user_behavior.behavior_type", "dim_product.product_name"],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮浏览最多的是用户10122（13次，其余12、11、11）。收藏了2个不同商品，名称不重名。",
            ),
            EvalCase(
                id="M1E12-4",
                query="这4个人里谁退过款？各退了几笔？",
                reference_sql=(
                    "SELECT u.user_name, s.refund_order_count "
                    "FROM dws_user_summary s JOIN dim_user u ON u.user_id = s.user_id "
                    "WHERE u.user_name IN ('用户10016','用户10122','用户10129','用户10173') "
                    "AND s.refund_order_count > 0"
                ),
                must_hit_columns=["dim_user.user_name", ["dws_user_summary.refund_order_count", "fact_refund.order_id"]],
                tags=["追问:跨轮", "追问:指代"],
                note="'这4个人'回到第1轮的4位用户（第3轮只涉及1人）。只返回退过款的2人；用 fact_refund 关联订单计数结果一致。",
            ),
        ],
    ),
]


# =====================================================================================
# chinook
# =====================================================================================

MULTITURN1_CHINOOK_CASES = [
    # ---------------------------------------------------------------- M1C01
    MultiTurnCase(
        id="M1C01",
        tags=["难度:中等"],
        note="平均每首超过5分钟的流派 → 这些流派的卖出份数 → 卖得最多的流派里卖得最多的两位艺术家 → 回到这些流派看曲库曲目数。考指代、依赖结果、跨轮。",
        turns=[
            EvalCase(
                id="M1C01-1",
                query="曲库里平均每首时长超过5分钟的流派有哪些？各自平均多少分钟？保留两位小数。",
                reference_sql=(
                    "SELECT g.Name, ROUND(AVG(t.Milliseconds) / 60000.0, 2) AS avg_minutes "
                    "FROM Track t JOIN Genre g ON g.GenreId = t.GenreId "
                    "GROUP BY g.GenreId, g.Name HAVING AVG(t.Milliseconds) > 300000"
                ),
                must_hit_columns=["Track.Milliseconds", "Genre.Name", "Track.GenreId"],
                note="按曲库全部曲目算平均时长（毫秒换算成分钟），按未取整的平均值与5分钟比较。7个流派；最接近门槛的是 Electronica/Dance 5.05 和 Heavy Metal 4.96，不会因取整进出。",
            ),
            EvalCase(
                id="M1C01-2",
                query="这些流派各卖出去多少份？",
                reference_sql=(
                    "SELECT g.Name, COUNT(*) AS sold "
                    "FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId "
                    "JOIN Genre g ON g.GenreId = t.GenreId "
                    "WHERE g.Name IN ('Sci Fi & Fantasy','Science Fiction','Drama','TV Shows','Comedy','Metal','Electronica/Dance') "
                    "GROUP BY g.GenreId, g.Name"
                ),
                must_hit_columns=["Genre.Name", "Track.GenreId", "InvoiceLine.TrackId"],
                tags=["追问:指代", "追问:换角度"],
                note="'这些流派'= 上一轮7个流派；卖出份数=发票明细行数（每行数量都是1）。7个都有销量。",
            ),
            EvalCase(
                id="M1C01-3",
                query="卖得最多的那个流派里，卖出份数最多的两位艺术家是谁？各多少份？",
                reference_sql=(
                    "SELECT ar.Name, COUNT(*) AS sold "
                    "FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId "
                    "JOIN Genre g ON g.GenreId = t.GenreId "
                    "JOIN Album al ON al.AlbumId = t.AlbumId "
                    "JOIN Artist ar ON ar.ArtistId = al.ArtistId "
                    "WHERE g.Name = 'Metal' GROUP BY ar.ArtistId, ar.Name ORDER BY sold DESC LIMIT 2"
                ),
                must_hit_columns=["Artist.Name", "Album.ArtistId", "Track.AlbumId", "Genre.Name", "InvoiceLine.TrackId"],
                tags=["追问:依赖结果", "追问:换角度"],
                note="上一轮卖得最多的是 Metal（264份，第二 TV Shows 47）。只算这些艺术家的 Metal 曲目：Metallica 91、Iron Maiden 70，第3名 12，前2不并列。",
            ),
            EvalCase(
                id="M1C01-4",
                query="回到第一问那些流派，曲库里各有多少首曲目？",
                reference_sql=(
                    "SELECT g.Name, COUNT(*) AS track_cnt FROM Track t JOIN Genre g ON g.GenreId = t.GenreId "
                    "WHERE g.Name IN ('Sci Fi & Fantasy','Science Fiction','Drama','TV Shows','Comedy','Metal','Electronica/Dance') "
                    "GROUP BY g.GenreId, g.Name"
                ),
                must_hit_columns=["Genre.Name", "Track.GenreId"],
                tags=["追问:跨轮", "追问:指代"],
                note="回到第1轮的7个流派（第3轮只涉及 Metal），数曲库曲目（不论是否卖出）。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1C02
    MultiTurnCase(
        id="M1C02",
        tags=["难度:中等"],
        note="开票金额前5国家 → 各国客户数 → 客户最多的国家里消费前3的客户 → 他们的专属销售支持。考指代、依赖结果、客户与员工的关联。",
        turns=[
            EvalCase(
                id="M1C02-1",
                query="开票金额最高的5个国家是哪些？各开了多少钱？保留两位小数。",
                reference_sql=(
                    "SELECT BillingCountry, ROUND(SUM(Total), 2) AS total "
                    "FROM Invoice GROUP BY BillingCountry ORDER BY SUM(Total) DESC LIMIT 5"
                ),
                must_hit_columns=[["Invoice.BillingCountry", "Customer.Country"], "Invoice.Total"],
                note="按开票国家汇总 Total；本库开票国家与客户登记国家全部一致，两条路径结果相同。第5名 Germany 156.48 与第6名 United Kingdom 112.86 不并列。",
            ),
            EvalCase(
                id="M1C02-2",
                query="这几个国家各有多少位客户？",
                reference_sql=(
                    "SELECT Country, COUNT(*) AS customer_cnt FROM Customer "
                    "WHERE Country IN ('USA','Canada','France','Brazil','Germany') GROUP BY Country"
                ),
                must_hit_columns=[["Customer.Country", "Invoice.BillingCountry"]],
                tags=["追问:指代", "追问:换角度"],
                note="'这几个国家'= 上一轮的 USA、Canada、France、Brazil、Germany。",
            ),
            EvalCase(
                id="M1C02-3",
                query="客户最多的那个国家，消费最高的3位客户是谁？各消费多少？保留两位小数。",
                reference_sql=(
                    "SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS spent "
                    "FROM Customer c JOIN Invoice i ON i.CustomerId = c.CustomerId "
                    "WHERE c.Country = 'USA' GROUP BY c.CustomerId, c.FirstName, c.LastName "
                    "ORDER BY SUM(i.Total) DESC LIMIT 3"
                ),
                must_hit_columns=[
                    "Customer.FirstName",
                    "Customer.LastName",
                    "Invoice.Total",
                    ["Customer.Country", "Invoice.BillingCountry"],
                ],
                tags=["追问:依赖结果", "追问:指代"],
                note="客户最多的是 USA（13位）。消费=该客户全部发票 Total 之和。第2、3名同为 43.62，第4名 42.62，前3集合唯一。",
            ),
            EvalCase(
                id="M1C02-4",
                query="他们的专属销售支持分别是谁？",
                reference_sql=(
                    "SELECT c.FirstName AS customer_first, c.LastName AS customer_last, "
                    "e.FirstName AS rep_first, e.LastName AS rep_last "
                    "FROM Customer c JOIN Employee e ON e.EmployeeId = c.SupportRepId "
                    "WHERE c.CustomerId IN (26, 24, 28)"
                ),
                must_hit_columns=["Customer.SupportRepId", "Employee.FirstName", "Employee.LastName"],
                tags=["追问:指代"],
                note="'他们'= 上一轮3位客户（Richard Cunningham、Frank Ralston、Julia Barnett）；专属销售支持经 SupportRepId 关联员工表，三人各不相同。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1C03
    MultiTurnCase(
        id="M1C03",
        tags=["难度:难"],
        note="对接客户的同事里最年轻的一位及其客户数 → 这些客户每年带来的销售额 → 业绩最好那年谁花钱最多 → 换成 Margaret Park 按年看。考员工→客户关联、连续依赖结果、跨轮沿用第2轮问法。",
        turns=[
            EvalCase(
                id="M1C03-1",
                query="负责对接客户的那几位同事当中，岁数最小的是哪一位？这位同事手里一共管着多少个客户？",
                reference_sql=(
                    "SELECT e.FirstName, e.LastName, COUNT(c.CustomerId) AS customer_cnt "
                    "FROM Employee e JOIN Customer c ON c.SupportRepId = e.EmployeeId "
                    "WHERE e.BirthDate = (SELECT MAX(e2.BirthDate) FROM Employee e2 "
                    "WHERE e2.EmployeeId IN (SELECT SupportRepId FROM Customer)) "
                    "GROUP BY e.EmployeeId, e.FirstName, e.LastName"
                ),
                must_hit_columns=["Employee.BirthDate", "Customer.SupportRepId"],
                note="对接客户的同事=被 Customer.SupportRepId 指向的员工（3位），出生日期各不相同，最年轻的是 Jane Peacock（1973-08-29，也是全体员工里最年轻的，限不限对接客户结果一样），负责21位客户。",
            ),
            EvalCase(
                id="M1C03-2",
                query="这些客户每年各带来多少销售额？金额保留两位小数。",
                reference_sql=(
                    "SELECT strftime('%Y', i.InvoiceDate) AS yr, ROUND(SUM(i.Total), 2) AS sales "
                    "FROM Invoice i JOIN Customer c ON c.CustomerId = i.CustomerId "
                    "WHERE c.SupportRepId = 3 GROUP BY yr"
                ),
                must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total", "Customer.SupportRepId"],
                tags=["追问:指代", "追问:换角度"],
                note="【存疑】年份列的表示（'2021' 字符串还是整数）可能影响比对。'这些客户'= Jane Peacock 负责的21位客户，按开票年份汇总发票金额，2021–2025 共5行。",
            ),
            EvalCase(
                id="M1C03-3",
                query="业绩最好的那一年，这些客户里谁花钱最多？花了多少？保留两位小数。",
                reference_sql=(
                    "SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS spent "
                    "FROM Invoice i JOIN Customer c ON c.CustomerId = i.CustomerId "
                    "WHERE c.SupportRepId = 3 AND i.InvoiceDate >= '2022-01-01' AND i.InvoiceDate < '2023-01-01' "
                    "GROUP BY c.CustomerId, c.FirstName, c.LastName ORDER BY SUM(i.Total) DESC LIMIT 1"
                ),
                must_hit_columns=[
                    "Customer.FirstName",
                    "Customer.LastName",
                    "Invoice.InvoiceDate",
                    "Invoice.Total",
                    "Customer.SupportRepId",
                ],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮业绩最好的是 2022 年（221.92，第二 2023 年 184.34）。那年这些客户里 Ladislav Kovács 32.75 最多，第二名 26.75，唯一。",
            ),
            EvalCase(
                id="M1C03-4",
                query="换成 Margaret Park 负责的客户，也按年看看呢？同样保留两位小数。",
                reference_sql=(
                    "SELECT strftime('%Y', i.InvoiceDate) AS yr, ROUND(SUM(i.Total), 2) AS sales "
                    "FROM Invoice i JOIN Customer c ON c.CustomerId = i.CustomerId "
                    "JOIN Employee e ON e.EmployeeId = c.SupportRepId "
                    "WHERE e.FirstName = 'Margaret' AND e.LastName = 'Park' GROUP BY yr"
                ),
                must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total", "Customer.SupportRepId"],
                tags=["追问:省略", "追问:跨轮"],
                note="'也按年看'沿用第2轮的问法（负责客户每年带来的销售额），只把员工换成 Margaret Park，5行。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1C04
    MultiTurnCase(
        id="M1C04",
        tags=["难度:中等"],
        note="10首及以上且每首都卖出过的专辑 → 所属艺术家和卖出份数 → 陷阱：发行年份（库里没有）→ 回到这3张专辑看平均每首时长。考'每一首都卖出过'的全称条件、指代、陷阱识别、陷阱后跨轮。",
        turns=[
            EvalCase(
                id="M1C04-1",
                query="有没有曲目在10首及以上、而且每一首都至少卖出去过一次的专辑？列出专辑名和曲目数。",
                reference_sql=(
                    "SELECT al.Title, COUNT(*) AS track_cnt FROM Track t JOIN Album al ON al.AlbumId = t.AlbumId "
                    "GROUP BY al.AlbumId, al.Title "
                    "HAVING COUNT(*) >= 10 "
                    "AND SUM(CASE WHEN EXISTS (SELECT 1 FROM InvoiceLine il WHERE il.TrackId = t.TrackId) THEN 0 ELSE 1 END) = 0"
                ),
                must_hit_columns=["Album.Title", "Track.AlbumId", "InvoiceLine.TrackId"],
                note="曲目数含10首；每首在发票明细里至少出现一次。3张：Chemical Wedding（11）、News Of The World（11）、BBC Sessions [Disc 2] [Live]（10）。",
            ),
            EvalCase(
                id="M1C04-2",
                query="它们分别是哪位艺术家的？各卖出去多少份？",
                reference_sql=(
                    "SELECT al.Title, ar.Name, COUNT(*) AS sold "
                    "FROM Album al JOIN Artist ar ON ar.ArtistId = al.ArtistId "
                    "JOIN Track t ON t.AlbumId = al.AlbumId "
                    "JOIN InvoiceLine il ON il.TrackId = t.TrackId "
                    "WHERE al.AlbumId IN (19, 186, 127) GROUP BY al.AlbumId, al.Title, ar.Name"
                ),
                must_hit_columns=["Artist.Name", "Album.ArtistId", "InvoiceLine.TrackId"],
                tags=["追问:指代", "追问:换角度"],
                note="'它们'= 上一轮3张专辑；卖出份数=这些专辑曲目的发票明细行数（同一曲目卖多次按多份算，与去重曲目数不同）。",
            ),
            EvalCase(
                id="M1C04-3",
                query="这三张专辑分别是哪一年发行的？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="专辑表只有名称和艺术家，库里没有发行日期；开票日期不是发行时间，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M1C04-4",
                query="回到那三张专辑，它们的曲目平均每首多长？按分钟算，保留两位小数。",
                reference_sql=(
                    "SELECT al.Title, ROUND(AVG(t.Milliseconds) / 60000.0, 2) AS avg_minutes "
                    "FROM Track t JOIN Album al ON al.AlbumId = t.AlbumId "
                    "WHERE al.AlbumId IN (19, 186, 127) GROUP BY al.AlbumId, al.Title"
                ),
                must_hit_columns=["Album.Title", "Track.Milliseconds", "Track.AlbumId"],
                tags=["追问:跨轮", "追问:换角度"],
                note="陷阱轮之后回到第1、2轮的3张专辑，按整张专辑的全部曲目算平均时长。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1C05
    MultiTurnCase(
        id="M1C05",
        tags=["难度:中等"],
        note="Grunge 歌单的歌按原专辑归类、贡献最多的专辑 → 这张专辑的艺术家在全库的销量 → 回到这个歌单看全部曲目的媒体格式 → Heavy Metal Classic 呢。考歌单收录与销量的区分、依赖结果、跨轮、省略。",
        turns=[
            EvalCase(
                id="M1C05-1",
                query="把 Grunge 那份歌单里的歌按原专辑归一下，哪张原专辑贡献得最多？贡献了几首？",
                reference_sql=(
                    "SELECT al.Title, COUNT(*) AS track_cnt "
                    "FROM PlaylistTrack pt JOIN Playlist p ON p.PlaylistId = pt.PlaylistId "
                    "JOIN Track t ON t.TrackId = pt.TrackId "
                    "JOIN Album al ON al.AlbumId = t.AlbumId "
                    "WHERE p.Name = 'Grunge' GROUP BY al.AlbumId, al.Title ORDER BY track_cnt DESC LIMIT 1"
                ),
                must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Track.AlbumId", "Album.Title"],
                note="歌单名唯一，15首。按曲目所属专辑计数，Nevermind 6首最多，第二名3首，唯一。",
            ),
            EvalCase(
                id="M1C05-2",
                query="这张专辑是哪位艺术家的？这位艺术家的歌在整个曲库里一共卖出去多少份？",
                reference_sql=(
                    "SELECT ar.Name, COUNT(*) AS sold "
                    "FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId "
                    "JOIN Album al ON al.AlbumId = t.AlbumId "
                    "JOIN Artist ar ON ar.ArtistId = al.ArtistId "
                    "WHERE ar.ArtistId = (SELECT ArtistId FROM Album WHERE Title = 'Nevermind') "
                    "GROUP BY ar.ArtistId, ar.Name"
                ),
                must_hit_columns=["Artist.Name", "Album.ArtistId", "InvoiceLine.TrackId"],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮的专辑是 Nevermind，艺术家 Nirvana；'整个曲库里'表示这位艺术家所有专辑的曲目（不限歌单），卖出份数按发票明细行数（不是去重曲目数）。",
            ),
            EvalCase(
                id="M1C05-3",
                query="回到这张歌单，它收录的全部曲目都是什么媒体格式？各几首？",
                reference_sql=(
                    "SELECT m.Name, COUNT(*) AS track_cnt "
                    "FROM PlaylistTrack pt JOIN Playlist p ON p.PlaylistId = pt.PlaylistId "
                    "JOIN Track t ON t.TrackId = pt.TrackId "
                    "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
                    "WHERE p.Name = 'Grunge' GROUP BY m.MediaTypeId, m.Name"
                ),
                must_hit_columns=["MediaType.Name", "Track.MediaTypeId", "Playlist.Name"],
                tags=["追问:跨轮", "追问:指代", "追问:换角度"],
                note="回到第1轮的 Grunge 歌单，'全部曲目'表示不限于 Nevermind 的那几首，按媒体格式数15首收录曲目，2行。",
            ),
            EvalCase(
                id="M1C05-4",
                query="Heavy Metal Classic 呢？",
                reference_sql=(
                    "SELECT m.Name, COUNT(*) AS track_cnt "
                    "FROM PlaylistTrack pt JOIN Playlist p ON p.PlaylistId = pt.PlaylistId "
                    "JOIN Track t ON t.TrackId = pt.TrackId "
                    "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
                    "WHERE p.Name = 'Heavy Metal Classic' GROUP BY m.MediaTypeId, m.Name"
                ),
                must_hit_columns=["MediaType.Name", "Track.MediaTypeId", "Playlist.Name"],
                tags=["追问:省略"],
                note="完全沿用上一轮（歌单全部收录曲目按媒体格式计数），只换成 Heavy Metal Classic 歌单（歌单名唯一），2行。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1C06
    MultiTurnCase(
        id="M1C06",
        tags=["难度:中等"],
        note="2024年Q3金额超过10的发票 → 2023年同季度 → 这几张发票的客户那季度一共花了多少 → 回到2024年那几张看客户。考省略年份、指代发票到客户、跨轮沿用第3轮问法。",
        turns=[
            EvalCase(
                id="M1C06-1",
                query="2024年第三季度（7到9月），金额超过10的发票有哪几张？列出发票号、开票城市和金额。",
                reference_sql=(
                    "SELECT InvoiceId, BillingCity, Total FROM Invoice "
                    "WHERE InvoiceDate >= '2024-07-01' AND InvoiceDate < '2024-10-01' AND Total > 10"
                ),
                must_hit_columns=["Invoice.Total", "Invoice.InvoiceDate", ["Invoice.BillingCity", "Customer.City"]],
                note="金额=发票 Total，没有正好等于10的发票。5张。本库开票城市与客户城市全部一致。",
            ),
            EvalCase(
                id="M1C06-2",
                query="2023年同一季度呢？",
                reference_sql=(
                    "SELECT InvoiceId, BillingCity, Total FROM Invoice "
                    "WHERE InvoiceDate >= '2023-07-01' AND InvoiceDate < '2023-10-01' AND Total > 10"
                ),
                must_hit_columns=["Invoice.Total", "Invoice.InvoiceDate", ["Invoice.BillingCity", "Customer.City"]],
                tags=["追问:省略"],
                note="沿用'金额超过10的发票、列发票号城市金额'，时间换成2023年7–9月，3张。",
            ),
            EvalCase(
                id="M1C06-3",
                query="这几张发票分别是哪些客户的？他们那个季度一共花了多少？保留两位小数。",
                reference_sql=(
                    "SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS spent "
                    "FROM Invoice i JOIN Customer c ON c.CustomerId = i.CustomerId "
                    "WHERE i.InvoiceDate >= '2023-07-01' AND i.InvoiceDate < '2023-10-01' "
                    "AND c.CustomerId IN (SELECT CustomerId FROM Invoice WHERE InvoiceId IN (215, 222, 229)) "
                    "GROUP BY c.CustomerId, c.FirstName, c.LastName"
                ),
                must_hit_columns=["Customer.FirstName", "Customer.LastName", "Invoice.Total", "Invoice.InvoiceDate", "Invoice.CustomerId"],
                tags=["追问:指代", "追问:换角度"],
                note="'这几张发票'= 上一轮2023年Q3的3张（215、222、229），对应3位不同客户；'那个季度一共花了多少'算这些客户在2023年Q3的全部发票（不只那一张大单）。",
            ),
            EvalCase(
                id="M1C06-4",
                query="回到2024年那几张，也看看是哪些客户、他们那个季度一共花了多少，同样保留两位小数。",
                reference_sql=(
                    "SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS spent "
                    "FROM Invoice i JOIN Customer c ON c.CustomerId = i.CustomerId "
                    "WHERE i.InvoiceDate >= '2024-07-01' AND i.InvoiceDate < '2024-10-01' "
                    "AND c.CustomerId IN (SELECT CustomerId FROM Invoice WHERE InvoiceId IN (299, 306, 292, 311, 298)) "
                    "GROUP BY c.CustomerId, c.FirstName, c.LastName"
                ),
                must_hit_columns=["Customer.FirstName", "Customer.LastName", "Invoice.Total", "Invoice.InvoiceDate", "Invoice.CustomerId"],
                tags=["追问:跨轮", "追问:省略"],
                note="回到第1轮2024年Q3的5张发票，对应5位不同客户，沿用第3轮问法算他们在2024年Q3的全部发票金额。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1C07
    MultiTurnCase(
        id="M1C07",
        tags=["难度:难"],
        note="直接向 Nancy Edwards 汇报的员工 → 他们负责的有公司客户数 → 这些公司客户的消费 → 消费最高的公司买了哪些流派。考员工自引用层级、员工→客户关联、依赖结果。",
        turns=[
            EvalCase(
                id="M1C07-1",
                query="直接向 Nancy Edwards 汇报的员工有哪些？",
                reference_sql=(
                    "SELECT e.FirstName, e.LastName FROM Employee e "
                    "JOIN Employee m ON m.EmployeeId = e.ReportsTo "
                    "WHERE m.FirstName = 'Nancy' AND m.LastName = 'Edwards'"
                ),
                must_hit_columns=["Employee.ReportsTo", "Employee.FirstName", "Employee.LastName"],
                note="经 ReportsTo 自关联，3人：Jane Peacock、Margaret Park、Steve Johnson。",
            ),
            EvalCase(
                id="M1C07-2",
                query="他们负责的客户里，有公司的各有几位？",
                reference_sql=(
                    "SELECT e.FirstName, e.LastName, COUNT(*) AS company_customer_cnt "
                    "FROM Customer c JOIN Employee e ON e.EmployeeId = c.SupportRepId "
                    "WHERE e.EmployeeId IN (3, 4, 5) AND c.Company IS NOT NULL "
                    "GROUP BY e.EmployeeId, e.FirstName, e.LastName"
                ),
                must_hit_columns=["Customer.SupportRepId", "Customer.Company"],
                tags=["追问:指代", "追问:加条件"],
                note="'他们'= 上一轮3名员工；有公司=Company 不为空（库里没有空字符串）。4、3、3。",
            ),
            EvalCase(
                id="M1C07-3",
                query="这些有公司的客户分别是哪家公司？各累计消费多少？保留两位小数。",
                reference_sql=(
                    "SELECT c.Company, ROUND(SUM(i.Total), 2) AS spent "
                    "FROM Customer c JOIN Invoice i ON i.CustomerId = c.CustomerId "
                    "WHERE c.Company IS NOT NULL AND c.SupportRepId IN (3, 4, 5) "
                    "GROUP BY c.CustomerId, c.Company"
                ),
                must_hit_columns=["Customer.Company", "Invoice.Total"],
                tags=["追问:指代", "追问:换角度"],
                note="上一轮那10位有公司的客户，各自全部发票 Total 之和；10家公司名互不相同。",
            ),
            EvalCase(
                id="M1C07-4",
                query="消费最高的那家公司，买过哪些流派的曲目？各买了几首？",
                reference_sql=(
                    "SELECT g.Name, COUNT(*) AS track_cnt "
                    "FROM Invoice i JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId "
                    "JOIN Track t ON t.TrackId = il.TrackId "
                    "JOIN Genre g ON g.GenreId = t.GenreId "
                    "JOIN Customer c ON c.CustomerId = i.CustomerId "
                    "WHERE c.Company = 'JetBrains s.r.o.' GROUP BY g.GenreId, g.Name"
                ),
                must_hit_columns=["Genre.Name", "InvoiceLine.TrackId", "Invoice.CustomerId"],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮消费最高的是 JetBrains s.r.o.（40.62，第二 39.62），按它的发票明细统计各流派曲目数，8个流派；该客户没有重复购买同一曲目，按明细行数或去重曲目数结果相同。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1C08
    MultiTurnCase(
        id="M1C08",
        tags=["难度:简单"],
        note="曲目最少的文件格式 → 这几首是什么歌、谁的 → 其中 Classical 的平均时长 → 倒数第二少的格式也列歌名和艺术家。考依据结果定位格式、指代、加条件、跨轮沿用第2轮问法。",
        turns=[
            EvalCase(
                id="M1C08-1",
                query="曲库里有一种文件格式几乎没怎么用，曲目数是所有格式里最少的——是哪一种？一共才几首？",
                reference_sql=(
                    "SELECT m.Name, COUNT(*) AS track_cnt FROM Track t JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
                    "GROUP BY m.MediaTypeId, m.Name ORDER BY track_cnt ASC LIMIT 1"
                ),
                must_hit_columns=["MediaType.Name", "Track.MediaTypeId"],
                note="文件格式即媒体格式。最少的是 Purchased AAC audio file（7首），倒数第二是 AAC audio file（11首），唯一。",
            ),
            EvalCase(
                id="M1C08-2",
                query="这几首都是什么歌？分别是哪位艺术家的？",
                reference_sql=(
                    "SELECT t.Name AS track_name, ar.Name AS artist_name FROM Track t "
                    "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
                    "JOIN Album al ON al.AlbumId = t.AlbumId "
                    "JOIN Artist ar ON ar.ArtistId = al.ArtistId "
                    "WHERE m.Name = 'Purchased AAC audio file'"
                ),
                must_hit_columns=["Track.Name", "Artist.Name", "Album.ArtistId", "Track.MediaTypeId"],
                tags=["追问:指代", "追问:换角度"],
                note="'这几首'= 上一轮 Purchased AAC audio file 格式的7首；艺术家经专辑关联（不是作曲者字段），7行，曲名不重复。",
            ),
            EvalCase(
                id="M1C08-3",
                query="其中 Classical 流派的那几首，平均每首多长？按分钟算，保留两位小数。",
                reference_sql=(
                    "SELECT ROUND(AVG(t.Milliseconds) / 60000.0, 2) AS avg_minutes FROM Track t "
                    "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
                    "JOIN Genre g ON g.GenreId = t.GenreId "
                    "WHERE m.Name = 'Purchased AAC audio file' AND g.Name = 'Classical'"
                ),
                must_hit_columns=["Track.Milliseconds", "Genre.Name", "Track.MediaTypeId"],
                tags=["追问:加条件", "追问:指代"],
                note="'其中'= 上一轮那7首（Purchased AAC audio file 格式），再限流派 Classical：6首。不沿用格式条件会变成全库 Classical 曲目，答案不同。",
            ),
            EvalCase(
                id="M1C08-4",
                query="曲目数倒数第二的那种格式呢？也把歌名和艺术家列出来。",
                reference_sql=(
                    "SELECT t.Name AS track_name, ar.Name AS artist_name FROM Track t "
                    "JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId "
                    "JOIN Album al ON al.AlbumId = t.AlbumId "
                    "JOIN Artist ar ON ar.ArtistId = al.ArtistId "
                    "WHERE m.Name = 'AAC audio file'"
                ),
                must_hit_columns=["Track.Name", "Artist.Name", "Album.ArtistId", "Track.MediaTypeId"],
                tags=["追问:省略", "追问:跨轮"],
                note="'也把歌名和艺术家列出来'沿用第2轮的问法，格式换成曲目数倒数第二的 AAC audio file（11首，与最少的7首、第三少的214首都不并列），不沿用第3轮的 Classical 限定。11行，后面没有轮次再指代。",
            ),
        ],
    ),
]


# =====================================================================================
# sakila
# =====================================================================================

_OVERDUE = "julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration"

MULTITURN1_SAKILA_CASES = [
    # ---------------------------------------------------------------- M1S01
    MultiTurnCase(
        id="M1S01",
        tags=["难度:中等"],
        note="租金收入前5的分类 → 各分类影片数 → 收入第一的分类里出租最多的4部片 → 这4部片在两家店的拷贝数。考付款→租借→拷贝→影片→分类的长路径、指代、依赖结果。",
        turns=[
            EvalCase(
                id="M1S01-1",
                query="租金收入最高的5个影片分类是哪些？各收了多少钱？金额保留两位小数。",
                reference_sql=(
                    "SELECT c.name, ROUND(SUM(p.amount), 2) AS revenue "
                    "FROM payment p JOIN rental r ON r.rental_id = p.rental_id "
                    "JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film_category fc ON fc.film_id = i.film_id "
                    "JOIN category c ON c.category_id = fc.category_id "
                    "GROUP BY c.category_id, c.name ORDER BY SUM(p.amount) DESC LIMIT 5"
                ),
                must_hit_columns=[
                    "payment.amount",
                    "payment.rental_id",
                    "inventory.film_id",
                    "film_category.category_id",
                    "category.name",
                ],
                note="收入=实收金额 payment.amount（不是标价 rental_rate）。第5名 Comedy 4383.58 与第6名 Action 4375.85 不并列。",
            ),
            EvalCase(
                id="M1S01-2",
                query="这5类各有多少部影片？",
                reference_sql=(
                    "SELECT c.name, COUNT(*) AS film_cnt FROM film_category fc "
                    "JOIN category c ON c.category_id = fc.category_id "
                    "WHERE c.name IN ('Sports','Sci-Fi','Animation','Drama','Comedy') "
                    "GROUP BY c.category_id, c.name"
                ),
                must_hit_columns=["film_category.category_id", "category.name"],
                tags=["追问:指代", "追问:换角度"],
                note="'这5类'= 上一轮的 Sports、Sci-Fi、Animation、Drama、Comedy；每部影片恰属一个分类。",
            ),
            EvalCase(
                id="M1S01-3",
                query="收入第一的那类里，被租次数最多的4部片是哪些？各被租了几次？",
                reference_sql=(
                    "SELECT f.title, COUNT(*) AS rental_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film f ON f.film_id = i.film_id "
                    "JOIN film_category fc ON fc.film_id = f.film_id "
                    "JOIN category c ON c.category_id = fc.category_id "
                    "WHERE c.name = 'Sports' GROUP BY f.film_id, f.title ORDER BY rental_cnt DESC LIMIT 4"
                ),
                must_hit_columns=["film.title", "rental.inventory_id", "inventory.film_id", "category.name"],
                tags=["追问:依赖结果", "追问:指代"],
                note="收入第一是 Sports。29、29、28、28，第5名 27，前4不并列。",
            ),
            EvalCase(
                id="M1S01-4",
                query="这4部片在两家店各有几张拷贝？",
                reference_sql=(
                    "SELECT f.title, i.store_id, COUNT(*) AS copy_cnt "
                    "FROM inventory i JOIN film f ON f.film_id = i.film_id "
                    "WHERE f.title IN ('TALENTED HOMICIDE','GLEAMING JAWBREAKER','SATURDAY LAMBS','ROSES TREASURE') "
                    "GROUP BY f.film_id, f.title, i.store_id"
                ),
                must_hit_columns=["inventory.store_id", "inventory.film_id", "film.title"],
                tags=["追问:指代", "追问:换角度"],
                note="'这4部片'= 上一轮4部；按影片×门店数拷贝，8行（每部在两家店都有）。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1S02
    MultiTurnCase(
        id="M1S02",
        tags=["难度:中等"],
        note="两家门店城市与拷贝数 → 各租出多少次 → 只看2005年8月 → 回到拷贝看不同影片数。考门店→地址→城市、出租门店按拷贝所在门店、省略和跨轮。",
        turns=[
            EvalCase(
                id="M1S02-1",
                query="两家门店分别在哪个城市？各有多少张拷贝？列出门店编号、城市和拷贝数。",
                reference_sql=(
                    "SELECT s.store_id, ci.city, COUNT(i.inventory_id) AS copy_cnt "
                    "FROM store s JOIN address a ON a.address_id = s.address_id "
                    "JOIN city ci ON ci.city_id = a.city_id "
                    "JOIN inventory i ON i.store_id = s.store_id "
                    "GROUP BY s.store_id, ci.city"
                ),
                must_hit_columns=["store.address_id", "address.city_id", "city.city", "inventory.store_id"],
                note="门店城市经 store→address→city；拷贝数按 inventory.store_id。",
            ),
            EvalCase(
                id="M1S02-2",
                query="那各租出去多少次？",
                reference_sql=(
                    "SELECT i.store_id, COUNT(*) AS rental_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id GROUP BY i.store_id"
                ),
                must_hit_columns=["inventory.store_id", "rental.inventory_id"],
                tags=["追问:省略", "追问:换角度"],
                note="沿用'两家门店各自'，指标换成出租次数；在哪家店租出按租出拷贝所在门店（不是客户注册门店，也不是经办员工所在门店）。",
            ),
            EvalCase(
                id="M1S02-3",
                query="只看2005年8月呢？",
                reference_sql=(
                    "SELECT i.store_id, COUNT(*) AS rental_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "WHERE r.rental_date >= '2005-08-01' AND r.rental_date < '2005-09-01' GROUP BY i.store_id"
                ),
                must_hit_columns=["inventory.store_id", "rental.rental_date"],
                tags=["追问:加条件", "追问:省略"],
                note="沿用上一轮各门店出租次数，加租出时间在2005年8月。",
            ),
            EvalCase(
                id="M1S02-4",
                query="回到拷贝那个问题，两家店各有多少部不同的影片？",
                reference_sql=(
                    "SELECT store_id, COUNT(DISTINCT film_id) AS film_cnt FROM inventory GROUP BY store_id"
                ),
                must_hit_columns=["inventory.store_id", "inventory.film_id"],
                tags=["追问:跨轮", "追问:换角度"],
                note="回到第1轮的库存（不限时间），把拷贝张数换成去重后的影片数。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1S03
    MultiTurnCase(
        id="M1S03",
        tags=["难度:中等"],
        note="客户最多的5个国家 → 各国客户付款 → 付款最多的国家里消费前3客户 → 他们各租过多少部不同影片。考客户→地址→城市→国家三层关联、依赖结果、指代。",
        turns=[
            EvalCase(
                id="M1S03-1",
                query="客户最多的5个国家是哪些？各有多少位客户？",
                reference_sql=(
                    "SELECT co.country, COUNT(*) AS customer_cnt FROM customer c "
                    "JOIN address a ON a.address_id = c.address_id "
                    "JOIN city ci ON ci.city_id = a.city_id "
                    "JOIN country co ON co.country_id = ci.country_id "
                    "GROUP BY co.country_id, co.country ORDER BY customer_cnt DESC LIMIT 5"
                ),
                must_hit_columns=["customer.address_id", "address.city_id", "city.country_id", "country.country"],
                note="60、53、36、31、30，第6名 28，不并列。",
            ),
            EvalCase(
                id="M1S03-2",
                query="这几个国家的客户各付了多少钱？金额保留两位小数。",
                reference_sql=(
                    "SELECT co.country, ROUND(SUM(p.amount), 2) AS paid FROM payment p "
                    "JOIN customer c ON c.customer_id = p.customer_id "
                    "JOIN address a ON a.address_id = c.address_id "
                    "JOIN city ci ON ci.city_id = a.city_id "
                    "JOIN country co ON co.country_id = ci.country_id "
                    "WHERE co.country IN ('India','China','United States','Japan','Mexico') "
                    "GROUP BY co.country_id, co.country"
                ),
                must_hit_columns=["payment.amount", "payment.customer_id", "country.country"],
                tags=["追问:指代", "追问:换角度"],
                note="'这几个国家'= 上一轮5国；付款=payment.amount 合计（含无关联租借的付款）。",
            ),
            EvalCase(
                id="M1S03-3",
                query="付款最多的那个国家，消费最高的3位客户是谁？各付了多少？保留两位小数。",
                reference_sql=(
                    "SELECT c.first_name, c.last_name, ROUND(SUM(p.amount), 2) AS paid FROM payment p "
                    "JOIN customer c ON c.customer_id = p.customer_id "
                    "JOIN address a ON a.address_id = c.address_id "
                    "JOIN city ci ON ci.city_id = a.city_id "
                    "JOIN country co ON co.country_id = ci.country_id "
                    "WHERE co.country = 'India' GROUP BY c.customer_id, c.first_name, c.last_name "
                    "ORDER BY SUM(p.amount) DESC LIMIT 3"
                ),
                must_hit_columns=["customer.first_name", "customer.last_name", "payment.amount", "country.country"],
                tags=["追问:依赖结果", "追问:指代"],
                note="付款最多的是 India（6630.27）。175.61、170.67、166.65，第4名 161.68，不并列。",
            ),
            EvalCase(
                id="M1S03-4",
                query="这三位各租过多少部不同的影片？",
                reference_sql=(
                    "SELECT c.first_name, c.last_name, COUNT(DISTINCT i.film_id) AS film_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN customer c ON c.customer_id = r.customer_id "
                    "WHERE c.customer_id IN (468, 259, 403) GROUP BY c.customer_id, c.first_name, c.last_name"
                ),
                must_hit_columns=["rental.customer_id", "inventory.film_id"],
                tags=["追问:指代", "追问:换角度"],
                note="'这三位'= 上一轮 TIM CARY、LENA JENSEN、MIKE WAY；租借经拷贝找到影片后按影片去重。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1S04
    MultiTurnCase(
        id="M1S04",
        tags=["难度:中等"],
        note="参演最多的3位演员 → 他们的片子被租次数 → 陷阱：导演（库里没有）→ 回到这3位看 R 级片数。考演员→影片→拷贝→租借路径、陷阱识别、陷阱后跨轮。",
        turns=[
            EvalCase(
                id="M1S04-1",
                query="参演影片最多的3位演员是谁？各演了几部？",
                reference_sql=(
                    "SELECT a.first_name, a.last_name, COUNT(*) AS film_cnt "
                    "FROM film_actor fa JOIN actor a ON a.actor_id = fa.actor_id "
                    "GROUP BY a.actor_id, a.first_name, a.last_name ORDER BY film_cnt DESC LIMIT 3"
                ),
                must_hit_columns=["actor.first_name", "actor.last_name", "film_actor.actor_id"],
                note="42、41、40，第4名 39，不并列。",
            ),
            EvalCase(
                id="M1S04-2",
                query="他们演的片子各被租了多少次？",
                reference_sql=(
                    "SELECT a.first_name, a.last_name, COUNT(*) AS rental_cnt "
                    "FROM film_actor fa JOIN actor a ON a.actor_id = fa.actor_id "
                    "JOIN inventory i ON i.film_id = fa.film_id "
                    "JOIN rental r ON r.inventory_id = i.inventory_id "
                    "WHERE a.actor_id IN (107, 102, 198) GROUP BY a.actor_id, a.first_name, a.last_name"
                ),
                must_hit_columns=["film_actor.film_id", "inventory.film_id", "rental.inventory_id"],
                tags=["追问:指代", "追问:换角度"],
                note="'他们'= 上一轮 GINA DEGENERES、WALTER TORN、MARY KEITEL；每人参演的全部影片的出租次数合计。",
            ),
            EvalCase(
                id="M1S04-3",
                query="这些片子的导演分别是谁？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里只有演员，没有导演信息，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M1S04-4",
                query="回到这3位演员，他们演的 R 级片各有几部？",
                reference_sql=(
                    "SELECT a.first_name, a.last_name, COUNT(*) AS r_film_cnt "
                    "FROM film_actor fa JOIN actor a ON a.actor_id = fa.actor_id "
                    "JOIN film f ON f.film_id = fa.film_id "
                    "WHERE a.actor_id IN (107, 102, 198) AND f.rating = 'R' "
                    "GROUP BY a.actor_id, a.first_name, a.last_name"
                ),
                must_hit_columns=["film.rating", "film_actor.actor_id"],
                tags=["追问:跨轮", "追问:加条件"],
                note="陷阱轮之后回到第1轮的3位演员，加分级 R 的条件，三人都有。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1S05
    MultiTurnCase(
        id="M1S05",
        tags=["难度:难"],
        note="各分级逾期归还笔数 → 逾期最多的分级按门店拆 → 这个分级里逾期最多的3部片。考逾期口径（实际时长与影片租期比较）、依赖结果、指代。",
        turns=[
            EvalCase(
                id="M1S05-1",
                query="已经归还的租借里，各个分级的影片分别有多少笔是逾期还的？实际租借时长精确到秒算，超过这部片的租期才算逾期，正好等于不算。",
                reference_sql=(
                    "SELECT f.rating, COUNT(*) AS overdue_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film f ON f.film_id = i.film_id "
                    f"WHERE r.return_date IS NOT NULL AND {_OVERDUE} GROUP BY f.rating"
                ),
                must_hit_columns=["rental.return_date", "rental.rental_date", "film.rental_duration", "film.rating"],
                note="【存疑】逾期判断依赖'精确到秒、严格大于'的口径：按日期取整算会少很多，按大于等于算会多2笔（R、PG-13 各1笔正好等于租期）。题面已写明，仍可能有系统按日期差取整。",
            ),
            EvalCase(
                id="M1S05-2",
                query="逾期最多的那个分级，按租出的门店拆开看看。",
                reference_sql=(
                    "SELECT i.store_id, COUNT(*) AS overdue_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film f ON f.film_id = i.film_id "
                    f"WHERE r.return_date IS NOT NULL AND {_OVERDUE} AND f.rating = 'PG-13' "
                    "GROUP BY i.store_id"
                ),
                must_hit_columns=["inventory.store_id", "film.rating", "film.rental_duration"],
                tags=["追问:依赖结果", "追问:换角度"],
                note="上一轮逾期最多的是 PG-13（1814，第二 R 1666）。租出门店按拷贝所在门店，2行。",
            ),
            EvalCase(
                id="M1S05-3",
                query="这个分级里逾期笔数最多的3部片是哪些？各几笔？",
                reference_sql=(
                    "SELECT f.title, COUNT(*) AS overdue_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film f ON f.film_id = i.film_id "
                    f"WHERE r.return_date IS NOT NULL AND {_OVERDUE} AND f.rating = 'PG-13' "
                    "GROUP BY f.film_id, f.title ORDER BY overdue_cnt DESC LIMIT 3"
                ),
                must_hit_columns=["film.title", "film.rating", "film.rental_duration", "rental.return_date"],
                tags=["追问:指代", "追问:换角度"],
                note="'这个分级'= PG-13，两家店合起来（不沿用上一轮的门店拆分）。27、26、22，第4名 20，不并列。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1S06
    MultiTurnCase(
        id="M1S06",
        tags=["难度:中等"],
        note="未归还租借按门店 → 未还拷贝的赔偿价 → 未还最多的客户及片名 → 这位客户住哪。考未归还口径、赔偿价字段、客户→地址→城市→国家。",
        turns=[
            EvalCase(
                id="M1S06-1",
                query="还没归还的租借有多少笔？按租出的门店分别算。",
                reference_sql=(
                    "SELECT i.store_id, COUNT(*) AS unreturned_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "WHERE r.return_date IS NULL GROUP BY i.store_id"
                ),
                must_hit_columns=["rental.return_date", "inventory.store_id"],
                note="未归还=归还时间为空；租出门店按拷贝所在门店。92、91。",
            ),
            EvalCase(
                id="M1S06-2",
                query="这些没还的拷贝，赔偿价加起来各是多少？保留两位小数。",
                reference_sql=(
                    "SELECT i.store_id, ROUND(SUM(f.replacement_cost), 2) AS replacement_total "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film f ON f.film_id = i.film_id "
                    "WHERE r.return_date IS NULL GROUP BY i.store_id"
                ),
                must_hit_columns=["film.replacement_cost", "rental.return_date", "inventory.store_id"],
                tags=["追问:指代", "追问:换角度"],
                note="沿用按门店分；每笔未还租借对应一张拷贝，赔偿价取影片的 replacement_cost 求和。",
            ),
            EvalCase(
                id="M1S06-3",
                query="没还的笔数最多的是哪位客户？列出这位客户没还的片名。",
                reference_sql=(
                    "SELECT c.first_name, c.last_name, f.title "
                    "FROM rental r JOIN customer c ON c.customer_id = r.customer_id "
                    "JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film f ON f.film_id = i.film_id "
                    "WHERE r.return_date IS NULL AND r.customer_id = "
                    "(SELECT customer_id FROM rental WHERE return_date IS NULL "
                    "GROUP BY customer_id ORDER BY COUNT(*) DESC LIMIT 1)"
                ),
                must_hit_columns=["rental.customer_id", "rental.return_date", "film.title", "customer.first_name"],
                tags=["追问:指代", "追问:换角度"],
                note="范围沿用'没还的租借'（两家店合计），按客户计数：TAMMY SANDERS 3笔，其余最多2笔，唯一；3部片各不相同。",
            ),
            EvalCase(
                id="M1S06-4",
                query="这位客户住在哪个城市、哪个国家？",
                reference_sql=(
                    "SELECT ci.city, co.country FROM customer c "
                    "JOIN address a ON a.address_id = c.address_id "
                    "JOIN city ci ON ci.city_id = a.city_id "
                    "JOIN country co ON co.country_id = ci.country_id "
                    "WHERE c.customer_id = 75"
                ),
                must_hit_columns=["customer.address_id", "city.city", "country.country"],
                tags=["追问:指代"],
                note="'这位客户'= 上一轮的 TAMMY SANDERS（customer_id 75）。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1S07
    MultiTurnCase(
        id="M1S07",
        tags=["难度:中等"],
        note="两位员工收款 → 2005年7月 → 那个月 Jon Stephens 经手付款最多的3位客户 → 他们那个月租了几次。考收款员工(payment.staff_id)、省略时间、换到租借表。",
        turns=[
            EvalCase(
                id="M1S07-1",
                query="两位员工各收了多少笔付款、一共多少钱？金额保留两位小数。",
                reference_sql=(
                    "SELECT s.first_name, s.last_name, COUNT(*) AS pay_cnt, ROUND(SUM(p.amount), 2) AS pay_total "
                    "FROM payment p JOIN staff s ON s.staff_id = p.staff_id "
                    "GROUP BY s.staff_id, s.first_name, s.last_name"
                ),
                must_hit_columns=["payment.staff_id", "payment.amount", "staff.first_name"],
                note="收款员工是 payment.staff_id，不是办理租借的 rental.staff_id。",
            ),
            EvalCase(
                id="M1S07-2",
                query="2005年7月呢？金额同样保留两位小数。",
                reference_sql=(
                    "SELECT s.first_name, s.last_name, COUNT(*) AS pay_cnt, ROUND(SUM(p.amount), 2) AS pay_total "
                    "FROM payment p JOIN staff s ON s.staff_id = p.staff_id "
                    "WHERE p.payment_date >= '2005-07-01' AND p.payment_date < '2005-08-01' "
                    "GROUP BY s.staff_id, s.first_name, s.last_name"
                ),
                must_hit_columns=["payment.staff_id", "payment.amount", "payment.payment_date"],
                tags=["追问:省略", "追问:加条件"],
                note="沿用上一轮，按付款时间限定2005年7月。",
            ),
            EvalCase(
                id="M1S07-3",
                query="那个月 Jon Stephens 经手的付款里，付钱最多的3位客户是谁？各付了多少？保留两位小数。",
                reference_sql=(
                    "SELECT c.first_name, c.last_name, ROUND(SUM(p.amount), 2) AS paid "
                    "FROM payment p JOIN customer c ON c.customer_id = p.customer_id "
                    "JOIN staff s ON s.staff_id = p.staff_id "
                    "WHERE s.first_name = 'Jon' AND s.last_name = 'Stephens' "
                    "AND p.payment_date >= '2005-07-01' AND p.payment_date < '2005-08-01' "
                    "GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY SUM(p.amount) DESC LIMIT 3"
                ),
                must_hit_columns=["payment.staff_id", "payment.customer_id", "payment.payment_date", "customer.first_name"],
                tags=["追问:加条件", "追问:换角度"],
                note="'那个月'= 2005年7月；只算 Jon Stephens 收的款。68.88、64.87、63.89，第4名 60.89，不并列。",
            ),
            EvalCase(
                id="M1S07-4",
                query="不管是谁经手的，他们三位那个月各租了几次？",
                reference_sql=(
                    "SELECT c.first_name, c.last_name, COUNT(*) AS rental_cnt "
                    "FROM rental r JOIN customer c ON c.customer_id = r.customer_id "
                    "WHERE c.customer_id IN (144, 494, 522) "
                    "AND r.rental_date >= '2005-07-01' AND r.rental_date < '2005-08-01' "
                    "GROUP BY c.customer_id, c.first_name, c.last_name"
                ),
                must_hit_columns=["rental.customer_id", "rental.rental_date"],
                tags=["追问:指代", "追问:换角度"],
                note="'他们三位'= 上一轮 CLARA SHAW、RAMON CHOATE、ARNOLD HAVENS；按租出时间在2005年7月数租借次数，不限经办员工。三人恰好都是18次（按7月付款笔数数也是18）。",
            ),
        ],
    ),
    # ---------------------------------------------------------------- M1S08
    MultiTurnCase(
        id="M1S08",
        tags=["难度:简单"],
        note="各分级影片数和平均片长 → NC-17 按租借标价拆（沿用两个指标）→ 其中标价4.99出租最多的5部 → PG-13 也按标价拆。考省略指标、加条件、指代、跨轮沿用第2轮问法。",
        turns=[
            EvalCase(
                id="M1S08-1",
                query="各个分级分别有多少部影片？平均片长多少分钟？保留1位小数。",
                reference_sql=(
                    "SELECT rating, COUNT(*) AS film_cnt, ROUND(AVG(length), 1) AS avg_length FROM film GROUP BY rating"
                ),
                must_hit_columns=["film.rating", "film.length"],
                note="5个分级。",
            ),
            EvalCase(
                id="M1S08-2",
                query="NC-17 的那些，按租借标价拆开看看，平均片长同样保留1位小数。",
                reference_sql=(
                    "SELECT rental_rate, COUNT(*) AS film_cnt, ROUND(AVG(length), 1) AS avg_length "
                    "FROM film WHERE rating = 'NC-17' GROUP BY rental_rate"
                ),
                must_hit_columns=["film.rating", "film.rental_rate", "film.length"],
                tags=["追问:加条件", "追问:换角度", "追问:省略"],
                note="'NC-17 的那些'= 上一轮 NC-17 的210部；指标沿用上一轮的影片数和平均片长（保留1位小数），按租借标价分组，3行。",
            ),
            EvalCase(
                id="M1S08-3",
                query="标价4.99的那些里，被租次数最多的5部是哪些？各被租了几次？",
                reference_sql=(
                    "SELECT f.title, COUNT(*) AS rental_cnt "
                    "FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
                    "JOIN film f ON f.film_id = i.film_id "
                    "WHERE f.rating = 'NC-17' AND f.rental_rate = 4.99 "
                    "GROUP BY f.film_id, f.title ORDER BY rental_cnt DESC LIMIT 5"
                ),
                must_hit_columns=["film.title", "film.rating", "film.rental_rate", "rental.inventory_id", "inventory.film_id"],
                tags=["追问:加条件", "追问:指代"],
                note="仍限 NC-17，再限标价4.99。32、31、31、31、30，第6名 29，不并列。",
            ),
            EvalCase(
                id="M1S08-4",
                query="PG-13 的呢？也按租借标价拆开看看，平均片长同样保留1位小数。",
                reference_sql=(
                    "SELECT rental_rate, COUNT(*) AS film_cnt, ROUND(AVG(length), 1) AS avg_length "
                    "FROM film WHERE rating = 'PG-13' GROUP BY rental_rate"
                ),
                must_hit_columns=["film.rating", "film.rental_rate", "film.length"],
                tags=["追问:省略", "追问:跨轮"],
                note="'也按租借标价拆开看'明确沿用第2轮的问法（影片数+平均片长，按标价分），只把分级换成 PG-13；不沿用第3轮的出租排行。",
            ),
        ],
    ),
]


MULTITURN1_BANKS = {
    "ecommerce": MULTITURN1_ECOMMERCE_CASES,
    "chinook": MULTITURN1_CHINOOK_CASES,
    "sakila": MULTITURN1_SAKILA_CASES,
}
