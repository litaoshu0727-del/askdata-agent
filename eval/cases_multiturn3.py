"""
第三套多轮追问留出集：三个库（ecommerce、Chinook、Sakila），验证会话里的追问：指代、省略、加条件、换角度、跨轮、
依赖结果。由独立出题人在未见过被测系统表现和已有题目（包括前两套多轮题）的情况下编写。ecommerce 12 组 47 轮
（M3E01–M3E12，陷阱轮 2），Chinook 8 组 32 轮（M3C01–M3C08，陷阱轮 1），Sakila 8 组 32 轮（M3S01–M3S08，陷阱轮 1）。

**冻结版，还没有运行过。**前两套多轮题都已经照着失败修过，分数不再是泛化证据；这一套用来量这些修复在没见过的追问上
还剩多少。可以比的是第二套第一次运行的分数（追问 217/240，90%），当时第二套也没被调过。

出题规范是 eval/blind_materials/出题规范_多轮第三套.md，和第二套的规范只差三处：题号前缀、交付的文件名，以及第 4 条判分
规则里加了一句：结果里的值有几种同样正确的写法时，在题面写明用哪一种。第二套的 M2C08-1 没写季度怎么表示，系统金额全对
也判错，冻结后只能改题。材料（三份数据字典、三个库）和第二套出题时逐字节相同。

第二套有 9 次失败是数值都对、只差标识列（给了 ID 没给名字，只有名没有姓）。规范没有为此加规则：加了之后这一套去掉一种
第二套有的失败，两个分数就没法直接比。这类失败在结果里单独报。

冻结前我没有读过题目：机械校验和去重由脚本（eval/blind_materials/check_holdout.py）完成，只输出题号和检查项，去重和全部
已有题库、探针、前两套多轮题比（多轮题只比第 1 轮）。两轮修改：

    第一轮  14 组换第 1 轮：和前两套多轮题撞 8 组，和单轮题库、探针撞 6 组；14 组里有 8 组结果集和已有题相同，最像的
            问法相似度 0.93。7 轮核实小数位：4 轮补写，3 轮换题后不再用 ROUND。本套内相似度 0.60 的两对，各改一轮的措辞，
            参考答案不变。M3E12-1 也和本套其他组相似，那两组换掉之后不再相似，没有动。1 轮存疑（M3S05-2）改到只有一种
            理解，参考答案不变；另外 2 轮存疑随换题消失，冻结时没有存疑题
    第二轮  Chinook 2 轮问法相似（0.63、0.64，结果集不同），只改措辞，参考答案不变

之后去重为 0，机械校验问题为 0。第一轮有 8 组的开头和前两套撞上，其中一组问法相似度 0.91、结果集相同：同样的出题设置和
同样的库，容易写出同样的问题，题库越多撞得越多。

改动范围这次用逐组哈希核对过（eval/blind_materials/hash_cases.py，第二套没有做到）：每轮发修改之前存快照，存快照时出题人
已经写完。第一轮变的正好是 20 组，其余 8 组没动；第二轮变的正好是 M3C01、M3C07。哈希一组一个，组内改了哪几轮以出题人的回报
为准。这次顺手修了这个脚本：原来多轮题的哈希没有算进每一轮的候选路径。

例外，如实记下：
- 第一轮的修改要求里，我把"别用全量分组统计这类标准切入点，带上具体的筛选、时间范围或组合条件"一开始就写给了出题人。第二套
  是第二轮才写的。这 14 组的第 1 轮可能比第二套更偏向带条件
- 同一条要求里我写得矛盾：既写了"M3S05 不要动"，又要求改 M3S05-2。出题人按后者改，只动了这一轮的题面和 note，改动范围核对时
  算在该变的组里
- 出题人的回报里带了一点结构信息：哪几组有陷阱轮（M3E06、M3E11、M3C02，以及 M3E06 的陷阱在最后一轮）、M3E01 从 3 轮变成
  4 轮、M3E02 的难度标签变了、M3S05-2 另用一条按秒计算的路径核对过。没有问题、SQL 和字段。冻结前我没有据此改过代码
- 第一轮有条命令误带了 git -C /tmp status，在出题目录外执行，出题人报告输出被丢弃，没有看到内容，也没有碰项目仓库
- 出题人的会话环境自动带了 git 状态（报告说从文件名看是另一个项目的仓库）、5 条记忆索引（其中一条提到 askdata 评测的并行数
  限制，不含题目或库的内容）、路径和工具清单，报告说没有据此出题；列出题目录时看到了上一级目录本身的权限和时间戳，没有看其内容

每一组在一个新会话里按顺序问，每一轮单独判分（eval/multiturn.py --bank multiturn3）。第一次运行：冻结时的 HEAD，每组 3 次，
最多 4 个进程（ecommerce 两份、chinook、sakila），每个进程放在独立的进程组里，ecommerce 的两个进程各用一份自己的库。合并
规则和前两套相同，在看任何一组的成败之前写定：一组有 3 次完整运行且没有中途崩的，保留首次运行的结果；其余的组用同一份代码
补跑完整的 3 次，用补跑结果替换。

候选路径的验证 SQL 在 eval/cases_multiturn3_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

多轮追问评测题：ecommerce 12 组、chinook 8 组、sakila 8 组。

每一轮的 reference_sql 单独就能在对应的库上执行。候选路径的验证 SQL 在同目录的 alt_sql.json。
"""

from __future__ import annotations

from eval.cases import EvalCase, MultiTurnCase

# 判断“已付款”的三条等价路径（已验证：pay_time 不为空的 650 笔，正好是三种状态的订单，也正好是有支付流水的订单）
_PAID = ["fact_order.pay_time", "fact_order.order_status", "fact_payment.order_id"]
# 用户累计消费的三条等价路径（已验证：汇总表与订单、支付流水逐用户一致）
_USER_PAY = ["dws_user_summary.total_pay_amount", "fact_order.pay_amount", "fact_payment.pay_amount"]
# 店铺实付金额的三条等价路径（已验证：店铺日汇总与订单、支付流水逐店一致）
_SHOP_PAY = ["fact_order.pay_amount", "dws_shop_daily.pay_amount", "fact_payment.pay_amount"]
# 订单实付金额的两条等价路径（已验证：支付流水与订单逐笔一致）
_ORDER_PAY = ["fact_order.pay_amount", "fact_payment.pay_amount"]
# 商品归到二级类目的两条等价路径（已验证：每个商品的类目都等于其所属店铺的主营类目）
_CATEGORY_PATH = ["dim_product.category_id", "dim_shop.main_category_id"]
# 成交总额、下单日期的两条等价路径（已验证：店铺日汇总与订单按下单日期聚合逐行一致）
_GMV = ["dws_shop_daily.gmv", "fact_order.order_amount"]
_STAT_DATE = ["dws_shop_daily.stat_date", "fact_order.create_time"]
# chinook 的销售额：发票合计等于明细行合计（已验证：412 张发票逐张一致）
_SALES = ["Invoice.Total", "InvoiceLine.UnitPrice"]
# chinook 的国家、城市：开票地址与客户地址（已验证：全部发票都一致）
_COUNTRY = ["Invoice.BillingCountry", "Customer.Country"]
_CITY = ["Invoice.BillingCity", "Customer.City"]

_TRAP_SQL = "SELECT 1 WHERE 0"


MULTITURN3_ECOMMERCE_CASES = [
    MultiTurnCase(
        id="M3E01",
        tags=["难度:中等"],
        note="从某一天的大额订单出发，问下单的人、再按会员等级看买了什么；主要考对几笔订单的指代、依赖结果和省略。",
        turns=[
            EvalCase(
                id="M3E01-1",
                query="哪些订单是 2024 年 5 月 20 日当天下的、实付金额又过万？给我订单号、实付金额和下单渠道，金额保留 2 位小数。",
                reference_sql="""
                    SELECT order_id, ROUND(pay_amount, 2) AS pay_amount, channel
                    FROM fact_order
                    WHERE substr(create_time, 1, 10) = '2024-05-20' AND pay_time IS NOT NULL AND pay_amount > 10000
                """,
                must_hit_columns=[
                    ["fact_order.order_id", "fact_payment.order_id"],
                    "fact_order.create_time",
                    "fact_order.channel",
                    _ORDER_PAY,
                ],
                note="按下单时间取当天；实付金额按口径约定只算已付款订单（当天过万的订单都已付款）。共 7 笔。",
            ),
            EvalCase(
                id="M3E01-2",
                query="这几笔分别是谁下的？列出订单号、用户昵称和会员等级。",
                reference_sql="""
                    SELECT o.order_id, u.user_name, u.member_level
                    FROM fact_order o JOIN dim_user u ON o.user_id = u.user_id
                    WHERE o.order_id IN (50595, 50006, 50104, 50732, 50085, 50634, 50582)
                """,
                must_hit_columns=["dim_user.user_name", "dim_user.member_level", "fact_order.user_id"],
                tags=["追问:指代", "追问:换角度"],
                note="“这几笔”是上一轮的 7 笔订单，上一轮没有给出用户信息。",
            ),
            EvalCase(
                id="M3E01-3",
                query="其中钻石会员和金卡会员下的那两笔，都买了什么？列出订单号、商品 ID、商品名称和件数。",
                reference_sql="""
                    SELECT i.order_id, p.product_id, p.product_name, i.quantity
                    FROM fact_order_item i JOIN dim_product p ON i.product_id = p.product_id
                    WHERE i.order_id IN (50006, 50732)
                """,
                must_hit_columns=["dim_product.product_name", "fact_order_item.order_id", "fact_order_item.quantity"],
                tags=["追问:指代", "追问:依赖结果", "追问:加条件"],
                note="要看上一轮的会员等级才知道是哪两笔；有同名商品，题面要求列商品 ID。",
            ),
            EvalCase(
                id="M3E01-4",
                query="普通会员下的那几笔呢？",
                reference_sql="""
                    SELECT i.order_id, p.product_id, p.product_name, i.quantity
                    FROM fact_order_item i JOIN dim_product p ON i.product_id = p.product_id
                    WHERE i.order_id IN (50595, 50104, 50085, 50582)
                """,
                must_hit_columns=["dim_product.product_name", "fact_order_item.order_id", "fact_order_item.quantity"],
                tags=["追问:省略", "追问:依赖结果"],
                note="范围仍是第 1 轮的 7 笔，只换会员等级，问题和输出列沿用上一轮。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E02",
        tags=["难度:中等"],
        note="从预售商品问到加购收藏，再按标价高低看买家城市；主要考指代和跨轮的依赖结果。",
        turns=[
            EvalCase(
                id="M3E02-1",
                query="还在预售的商品有哪几款？标价和所属店铺也一起列一下：商品 ID、商品名称、标价、店铺名称。",
                reference_sql="""
                    SELECT p.product_id, p.product_name, p.list_price, s.shop_name
                    FROM dim_product p JOIN dim_shop s ON p.shop_id = s.shop_id
                    WHERE p.shelf_status = '预售'
                """,
                must_hit_columns=[
                    "dim_product.shelf_status",
                    "dim_product.product_name",
                    "dim_product.list_price",
                    "dim_product.shop_id",
                    "dim_shop.shop_name",
                ],
                note="上架状态为预售的 3 款。",
            ),
            EvalCase(
                id="M3E02-2",
                query="它们分别被加购、收藏过多少次？列出商品 ID、加购次数和收藏次数。",
                reference_sql="""
                    SELECT product_id, SUM(behavior_type = '加购') AS cart_count, SUM(behavior_type = '收藏') AS favorite_count
                    FROM fact_user_behavior
                    WHERE product_id IN (30002, 30037, 30057)
                    GROUP BY product_id
                """,
                must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.product_id"],
                tags=["追问:指代", "追问:换角度"],
                note="每款一行，两个次数各一列；其中一款没有被收藏过，收藏次数为 0。",
            ),
            EvalCase(
                id="M3E02-3",
                query="标价最高的那款，买过它的用户按所在城市分，各有多少位？",
                reference_sql="""
                    SELECT u.city, COUNT(DISTINCT u.user_id) AS user_count
                    FROM fact_order_item i
                    JOIN fact_order o ON i.order_id = o.order_id
                    JOIN dim_user u ON o.user_id = u.user_id
                    WHERE i.product_id = 30057 AND o.pay_time IS NOT NULL
                    GROUP BY u.city
                """,
                must_hit_columns=["dim_user.city", "fact_order_item.product_id", "fact_order.user_id", _PAID],
                tags=["追问:跨轮", "追问:依赖结果", "追问:加条件"],
                note="标价在第 1 轮，最高的是 30057；“买过”按口径约定只算已付款，按人去重。",
            ),
            EvalCase(
                id="M3E02-4",
                query="那标价最低的那款呢？",
                reference_sql="""
                    SELECT u.city, COUNT(DISTINCT u.user_id) AS user_count
                    FROM fact_order_item i
                    JOIN fact_order o ON i.order_id = o.order_id
                    JOIN dim_user u ON o.user_id = u.user_id
                    WHERE i.product_id = 30002 AND o.pay_time IS NOT NULL
                    GROUP BY u.city
                """,
                must_hit_columns=["dim_user.city", "fact_order_item.product_id", "fact_order.user_id", _PAID],
                tags=["追问:省略", "追问:跨轮", "追问:依赖结果"],
                note="回到第 1 轮的标价，最低的是 30002，问题和输出列沿用上一轮。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E03",
        tags=["难度:中等"],
        note="从花呗分期的大额订单问到店铺和件数、这几位用户的其他支付渠道，再换成微信支付；主要考指代和跨轮省略。",
        turns=[
            EvalCase(
                id="M3E03-1",
                query="用花呗分期付的订单里，单笔实付金额前 3 大的是哪几笔？列出订单号、下单用户的昵称和实付金额，金额保留 2 位小数。",
                reference_sql="""
                    SELECT o.order_id, u.user_name, ROUND(p.pay_amount, 2) AS pay_amount
                    FROM fact_payment p
                    JOIN fact_order o ON p.order_id = o.order_id
                    JOIN dim_user u ON o.user_id = u.user_id
                    WHERE p.pay_channel = '花呗分期'
                    ORDER BY p.pay_amount DESC LIMIT 3
                """,
                must_hit_columns=["fact_payment.pay_channel", "dim_user.user_name", "fact_order.user_id", _ORDER_PAY],
                note="第 3、4 笔不并列。",
            ),
            EvalCase(
                id="M3E03-2",
                query="这 3 笔分别是哪家店的、一共有多少件商品？列出订单号、店铺名称和件数。",
                reference_sql="""
                    SELECT o.order_id, s.shop_name, SUM(i.quantity) AS quantity
                    FROM fact_order o
                    JOIN dim_shop s ON o.shop_id = s.shop_id
                    JOIN fact_order_item i ON o.order_id = i.order_id
                    WHERE o.order_id IN (50588, 50291, 50694)
                    GROUP BY o.order_id, s.shop_name
                """,
                must_hit_columns=["dim_shop.shop_name", "fact_order_item.quantity", "fact_order_item.order_id"],
                tags=["追问:指代", "追问:换角度"],
                note="“这 3 笔”是上一轮的订单，每笔一行。",
            ),
            EvalCase(
                id="M3E03-3",
                query="这 3 位用户除了花呗分期，还用过哪些支付渠道？各付过多少笔？列出用户昵称、支付渠道和笔数。",
                reference_sql="""
                    SELECT u.user_name, p.pay_channel, COUNT(*) AS pay_count
                    FROM fact_payment p
                    JOIN fact_order o ON p.order_id = o.order_id
                    JOIN dim_user u ON o.user_id = u.user_id
                    WHERE u.user_name IN ('用户10014', '用户10112', '用户10196') AND p.pay_channel <> '花呗分期'
                    GROUP BY u.user_id, u.user_name, p.pay_channel
                """,
                must_hit_columns=["dim_user.user_name", "fact_payment.pay_channel", "fact_order.user_id"],
                tags=["追问:跨轮", "追问:指代", "追问:换角度"],
                note="用户在第 1 轮的结果里；每位用户的每个其他渠道一行。",
            ),
            EvalCase(
                id="M3E03-4",
                query="换成微信支付，单笔前 3 大的呢？金额保留 2 位小数。",
                reference_sql="""
                    SELECT o.order_id, u.user_name, ROUND(p.pay_amount, 2) AS pay_amount
                    FROM fact_payment p
                    JOIN fact_order o ON p.order_id = o.order_id
                    JOIN dim_user u ON o.user_id = u.user_id
                    WHERE p.pay_channel = '微信支付'
                    ORDER BY p.pay_amount DESC LIMIT 3
                """,
                must_hit_columns=["fact_payment.pay_channel", "dim_user.user_name", "fact_order.user_id", _ORDER_PAY],
                tags=["追问:省略", "追问:跨轮"],
                note="回到第 1 轮的问题，只换支付渠道，输出列沿用；第 3、4 笔不并列。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E04",
        tags=["难度:中等"],
        note="比较两个一级类目下的二级类目销量，再钻到销量最高的二级类目的商品；主要考省略、跨轮和依赖结果。",
        turns=[
            EvalCase(
                id="M3E04-1",
                query="一级类目美妆护肤下面，各二级类目的销量分别是多少件？只算已付款的订单。",
                reference_sql="""
                    SELECT c2.category_name, SUM(i.quantity) AS quantity
                    FROM fact_order_item i
                    JOIN fact_order o ON i.order_id = o.order_id
                    JOIN dim_product p ON i.product_id = p.product_id
                    JOIN dim_category c2 ON p.category_id = c2.category_id
                    JOIN dim_category c1 ON c2.parent_category_id = c1.category_id
                    WHERE c1.category_name = '美妆护肤' AND o.pay_time IS NOT NULL
                    GROUP BY c2.category_id, c2.category_name
                """,
                must_hit_columns=[
                    "dim_category.category_name",
                    "dim_category.parent_category_id",
                    "fact_order_item.quantity",
                    _CATEGORY_PATH,
                    _PAID,
                ],
                note="销量是件数合计；已付款的范围写在题面。",
            ),
            EvalCase(
                id="M3E04-2",
                query="数码电器呢？",
                reference_sql="""
                    SELECT c2.category_name, SUM(i.quantity) AS quantity
                    FROM fact_order_item i
                    JOIN fact_order o ON i.order_id = o.order_id
                    JOIN dim_product p ON i.product_id = p.product_id
                    JOIN dim_category c2 ON p.category_id = c2.category_id
                    JOIN dim_category c1 ON c2.parent_category_id = c1.category_id
                    WHERE c1.category_name = '数码电器' AND o.pay_time IS NOT NULL
                    GROUP BY c2.category_id, c2.category_name
                """,
                must_hit_columns=[
                    "dim_category.category_name",
                    "dim_category.parent_category_id",
                    "fact_order_item.quantity",
                    _CATEGORY_PATH,
                    _PAID,
                ],
                tags=["追问:省略"],
                note="只换一级类目，沿用已付款和按二级类目分组。",
            ),
            EvalCase(
                id="M3E04-3",
                query="这两个一级类目里，销量最高的那个二级类目，卖得最多的 3 个商品是什么？列出商品 ID、商品名称和销量。",
                reference_sql="""
                    SELECT p.product_id, p.product_name, SUM(i.quantity) AS quantity
                    FROM fact_order_item i
                    JOIN fact_order o ON i.order_id = o.order_id
                    JOIN dim_product p ON i.product_id = p.product_id
                    JOIN dim_category c ON p.category_id = c.category_id
                    WHERE c.category_name = '面部护肤' AND o.pay_time IS NOT NULL
                    GROUP BY p.product_id, p.product_name
                    ORDER BY quantity DESC LIMIT 3
                """,
                must_hit_columns=[
                    "dim_product.product_name",
                    "fact_order_item.product_id",
                    "fact_order_item.quantity",
                    _CATEGORY_PATH,
                    _PAID,
                ],
                tags=["追问:跨轮", "追问:依赖结果"],
                note="要把第 1、2 轮的结果放在一起比，才知道是面部护肤；有同名商品，题面要求列商品 ID，按商品 ID 分组。第 3、4 名不并列。",
            ),
            EvalCase(
                id="M3E04-4",
                query="这 3 个商品的标价和成本价分别是多少？列出商品 ID、标价和成本价。",
                reference_sql="""
                    SELECT product_id, list_price, cost_price
                    FROM dim_product
                    WHERE product_id IN (30010, 30016, 30001)
                """,
                must_hit_columns=["dim_product.list_price", "dim_product.cost_price"],
                tags=["追问:指代", "追问:换角度"],
                note="“这 3 个商品”是上一轮结果；标价、成本价上一轮没有给出，要回库查。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E05",
        tags=["难度:简单"],
        note="看两个会员等级的城市分布，再把两个等级放在一起看累计消费和退款；主要考省略和跨轮。",
        turns=[
            EvalCase(
                id="M3E05-1",
                query="钻石会员在各城市分别有多少人？",
                reference_sql="""
                    SELECT city, COUNT(*) AS user_count
                    FROM dim_user
                    WHERE member_level = '钻石会员'
                    GROUP BY city
                """,
                must_hit_columns=["dim_user.member_level", "dim_user.city"],
                note="按用户所在城市计人数。",
            ),
            EvalCase(
                id="M3E05-2",
                query="金卡会员呢？",
                reference_sql="""
                    SELECT city, COUNT(*) AS user_count
                    FROM dim_user
                    WHERE member_level = '金卡会员'
                    GROUP BY city
                """,
                must_hit_columns=["dim_user.member_level", "dim_user.city"],
                tags=["追问:省略"],
                note="只换会员等级，其余沿用。",
            ),
            EvalCase(
                id="M3E05-3",
                query="这两个等级各自的累计消费金额和退款订单数分别是多少？金额保留两位小数。",
                reference_sql="""
                    SELECT u.member_level, ROUND(SUM(d.total_pay_amount), 2) AS total_pay_amount,
                           SUM(d.refund_order_count) AS refund_order_count
                    FROM dim_user u JOIN dws_user_summary d ON u.user_id = d.user_id
                    WHERE u.member_level IN ('钻石会员', '金卡会员')
                    GROUP BY u.member_level
                """,
                must_hit_columns=[
                    "dim_user.member_level",
                    _USER_PAY,
                    ["dws_user_summary.refund_order_count", "fact_refund.order_id", "fact_order.order_status"],
                ],
                tags=["追问:跨轮", "追问:换角度"],
                note="“这两个等级”把第 1、2 轮放在一起；每个等级一行，不合计。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E06",
        tags=["难度:中等"],
        note="看已下架却收藏不少的商品：实际销量、停留时长，最后问一个库里没有的下架时间；主要考指代、依赖结果和陷阱。",
        turns=[
            EvalCase(
                id="M3E06-1",
                query="有些商品虽然已下架，收藏次数却不少：帮我找出收藏 6 次以上的，列出商品 ID、商品名称和收藏次数。",
                reference_sql="""
                    SELECT p.product_id, p.product_name, COUNT(*) AS favorite_count
                    FROM fact_user_behavior b JOIN dim_product p ON b.product_id = p.product_id
                    WHERE p.shelf_status = '已下架' AND b.behavior_type = '收藏'
                    GROUP BY p.product_id, p.product_name
                    HAVING COUNT(*) >= 6
                """,
                must_hit_columns=[
                    "dim_product.product_name",
                    "dim_product.shelf_status",
                    "fact_user_behavior.behavior_type",
                    "fact_user_behavior.product_id",
                ],
                note="已下架商品的收藏次数最多 7 次、其次 5 次，所以“6 次以上”含不含 6 都是这 3 款。",
            ),
            EvalCase(
                id="M3E06-2",
                query="它们分别卖出去多少件？只算已付款的订单，列出商品 ID 和件数。",
                reference_sql="""
                    SELECT i.product_id, SUM(i.quantity) AS quantity
                    FROM fact_order_item i JOIN fact_order o ON i.order_id = o.order_id
                    WHERE o.pay_time IS NOT NULL AND i.product_id IN (30041, 30038, 30031)
                    GROUP BY i.product_id
                """,
                must_hit_columns=["fact_order_item.quantity", "fact_order_item.product_id", _PAID],
                tags=["追问:指代", "追问:换角度"],
                note="“它们”是上一轮的 3 款，逐个列出。",
            ),
            EvalCase(
                id="M3E06-3",
                query="卖得最多的那款，浏览、加购、收藏这几种行为的平均停留时长分别是多少秒？保留 1 位小数。",
                reference_sql="""
                    SELECT behavior_type, ROUND(AVG(stay_seconds), 1) AS avg_seconds
                    FROM fact_user_behavior
                    WHERE product_id = 30038
                    GROUP BY behavior_type
                """,
                must_hit_columns=[
                    "fact_user_behavior.behavior_type",
                    "fact_user_behavior.stay_seconds",
                    "fact_user_behavior.product_id",
                ],
                tags=["追问:依赖结果", "追问:换角度"],
                note="上一轮卖得最多的是 30038；每种行为一行。",
            ),
            EvalCase(
                id="M3E06-4",
                query="这 3 款分别是什么时候下架的？",
                reference_sql=_TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "追问:跨轮", "陷阱题"],
                note="库里只有当前的上架状态，没有下架时间或状态变更记录，应说明缺失。“这 3 款”指第 1 轮的商品。",
                expect_unanswerable=True,
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E07",
        tags=["难度:中等"],
        note="按退款状态和原因看退款，再钻进退款成功里笔数最多的原因；主要考省略和“这里面”的范围继承。",
        turns=[
            EvalCase(
                id="M3E07-1",
                query="目前还在退款中的记录，按退款原因分别有多少笔、多少钱？金额保留两位小数。",
                reference_sql="""
                    SELECT refund_reason, COUNT(*) AS refund_count, ROUND(SUM(refund_amount), 2) AS refund_amount
                    FROM fact_refund
                    WHERE refund_status = '退款中'
                    GROUP BY refund_reason
                """,
                must_hit_columns=["fact_refund.refund_status", "fact_refund.refund_reason", "fact_refund.refund_amount"],
                note="按退款状态筛选，每个原因一行。",
            ),
            EvalCase(
                id="M3E07-2",
                query="退款成功的呢？金额保留 2 位小数。",
                reference_sql="""
                    SELECT refund_reason, COUNT(*) AS refund_count, ROUND(SUM(refund_amount), 2) AS refund_amount
                    FROM fact_refund
                    WHERE refund_status = '退款成功'
                    GROUP BY refund_reason
                """,
                must_hit_columns=["fact_refund.refund_status", "fact_refund.refund_reason", "fact_refund.refund_amount"],
                tags=["追问:省略"],
                note="只换退款状态，其余沿用。",
            ),
            EvalCase(
                id="M3E07-3",
                query="这里面笔数最多的那个原因，这些订单按下单渠道分，各有多少笔？",
                reference_sql="""
                    SELECT o.channel, COUNT(*) AS refund_count
                    FROM fact_refund r JOIN fact_order o ON r.order_id = o.order_id
                    WHERE r.refund_status = '退款成功' AND r.refund_reason = '拍错了'
                    GROUP BY o.channel
                """,
                must_hit_columns=["fact_refund.refund_status", "fact_refund.refund_reason", "fact_order.channel"],
                tags=["追问:依赖结果", "追问:指代", "追问:加条件"],
                note="“这里面”是上一轮的退款成功，笔数最多的是拍错了。脱离上下文看全部退款，最多的会是另一个原因。",
            ),
            EvalCase(
                id="M3E07-4",
                query="换成按用户的会员等级分呢？",
                reference_sql="""
                    SELECT u.member_level, COUNT(*) AS refund_count
                    FROM fact_refund r
                    JOIN fact_order o ON r.order_id = o.order_id
                    JOIN dim_user u ON o.user_id = u.user_id
                    WHERE r.refund_status = '退款成功' AND r.refund_reason = '拍错了'
                    GROUP BY u.member_level
                """,
                must_hit_columns=["fact_refund.refund_status", "fact_refund.refund_reason", "dim_user.member_level"],
                tags=["追问:省略", "追问:换角度"],
                note="范围沿用上一轮这些退款成功且原因为拍错了的订单，只换分组；仍数笔数。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E08",
        tags=["难度:难"],
        note="看一周的全平台日报，钻到成交最高的一天和贡献最大的店，再看这家店的转化；主要考跨轮和依赖结果。",
        turns=[
            EvalCase(
                id="M3E08-1",
                query="2024 年 5 月 1 日到 5 月 7 日（两头都算），全平台每天的成交总额是多少？日期写成 2024-05-01 这样，金额保留两位小数。",
                reference_sql="""
                    SELECT stat_date, ROUND(SUM(gmv), 2) AS gmv
                    FROM dws_shop_daily
                    WHERE stat_date BETWEEN '2024-05-01' AND '2024-05-07'
                    GROUP BY stat_date
                """,
                must_hit_columns=[_GMV, _STAT_DATE],
                note="成交总额即店铺日汇总的成交额，含所有状态的订单，与按下单日期聚合订单商品总金额一致。",
            ),
            EvalCase(
                id="M3E08-2",
                query="每天的订单量呢？",
                reference_sql="""
                    SELECT stat_date, SUM(order_count) AS order_count
                    FROM dws_shop_daily
                    WHERE stat_date BETWEEN '2024-05-01' AND '2024-05-07'
                    GROUP BY stat_date
                """,
                must_hit_columns=[["dws_shop_daily.order_count", "fact_order.create_time"], _STAT_DATE],
                tags=["追问:省略", "追问:换角度"],
                note="日期范围和全平台沿用，只换指标；订单量不加状态条件。",
            ),
            EvalCase(
                id="M3E08-3",
                query="这几天里成交总额最高的那天，哪家店贡献最多？列出店铺名称和它当天的成交总额，金额保留两位小数。",
                reference_sql="""
                    SELECT s.shop_name, ROUND(d.gmv, 2) AS gmv
                    FROM dws_shop_daily d JOIN dim_shop s ON d.shop_id = s.shop_id
                    WHERE d.stat_date = '2024-05-02'
                    ORDER BY d.gmv DESC LIMIT 1
                """,
                must_hit_columns=["dim_shop.shop_name", _GMV, _STAT_DATE],
                tags=["追问:跨轮", "追问:依赖结果"],
                note="成交总额在第 1 轮，最高的是 5 月 2 日；脱离上下文看整月，最高的会是另一天。当天第 1、2 名不并列。",
            ),
            EvalCase(
                id="M3E08-4",
                query="这家店这几天里有下单的日子，每天的买家数和支付转化率呢？日期写法不变，转化率保留 4 位小数。",
                reference_sql="""
                    SELECT d.stat_date, d.buyer_count, ROUND(d.conversion_rate, 4) AS conversion_rate
                    FROM dws_shop_daily d JOIN dim_shop s ON d.shop_id = s.shop_id
                    WHERE s.shop_name = '臻品自营店15' AND d.stat_date BETWEEN '2024-05-01' AND '2024-05-07'
                """,
                must_hit_columns=[
                    "dws_shop_daily.conversion_rate",
                    "dws_shop_daily.stat_date",
                    ["dws_shop_daily.buyer_count", "fact_order.user_id"],
                ],
                tags=["追问:指代", "追问:换角度"],
                note="这家店 5 月 5 日没有订单，题面说只看有下单的日子，所以是 6 行。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E09",
        tags=["难度:中等"],
        note="从不正常营业的店铺问到在售商品，再找同主营类目的其他店铺比较；主要考依赖结果和跨轮合并。",
        turns=[
            EvalCase(
                id="M3E09-1",
                query="目前已关店和休假中的店铺分别是哪几家？列出店铺名称、店铺状态和所在城市。",
                reference_sql="""
                    SELECT shop_name, shop_status, city
                    FROM dim_shop
                    WHERE shop_status IN ('已关店', '休假中')
                """,
                must_hit_columns=["dim_shop.shop_name", "dim_shop.shop_status", "dim_shop.city"],
                note="两种状态各一家，共 2 行。",
            ),
            EvalCase(
                id="M3E09-2",
                query="它们现在各有多少款在售商品？列出店铺名称和商品数。",
                reference_sql="""
                    SELECT s.shop_name, COUNT(*) AS product_count
                    FROM dim_product p JOIN dim_shop s ON p.shop_id = s.shop_id
                    WHERE s.shop_name IN ('旗舰自营店12', '鲜生自营店6') AND p.shelf_status = '在售'
                    GROUP BY s.shop_id, s.shop_name
                """,
                must_hit_columns=["dim_shop.shop_name", "dim_product.shop_id", "dim_product.shelf_status"],
                tags=["追问:指代", "追问:换角度"],
                note="“它们”是上一轮 2 家店，按上架状态为在售计商品数。",
            ),
            EvalCase(
                id="M3E09-3",
                query="跟它们主营类目相同的其他店铺是哪几家？列出店铺名称和实付金额，金额保留两位小数。",
                reference_sql="""
                    SELECT s.shop_name, ROUND(SUM(o.pay_amount), 2) AS pay_amount
                    FROM fact_order o JOIN dim_shop s ON o.shop_id = s.shop_id
                    WHERE o.pay_time IS NOT NULL
                      AND s.main_category_id IN (
                          SELECT main_category_id FROM dim_shop WHERE shop_name IN ('旗舰自营店12', '鲜生自营店6')
                      )
                      AND s.shop_name NOT IN ('旗舰自营店12', '鲜生自营店6')
                    GROUP BY s.shop_id, s.shop_name
                """,
                must_hit_columns=["dim_shop.shop_name", "dim_shop.main_category_id", _SHOP_PAY],
                tags=["追问:依赖结果", "追问:指代", "追问:换角度"],
                note="两家店的主营类目各还有一家其他店铺，共 2 行；“其他”排除这两家本身。",
            ),
            EvalCase(
                id="M3E09-4",
                query="把这两家和前面那两家放一起，各有多少笔退款记录？列出店铺名称和笔数。",
                reference_sql="""
                    SELECT s.shop_name, COUNT(*) AS refund_count
                    FROM fact_refund r
                    JOIN fact_order o ON r.order_id = o.order_id
                    JOIN dim_shop s ON o.shop_id = s.shop_id
                    WHERE s.shop_name IN ('旗舰自营店12', '鲜生自营店6', '京选自营店3', '臻品自营店15')
                    GROUP BY s.shop_id, s.shop_name
                """,
                must_hit_columns=["dim_shop.shop_name", ["fact_refund.order_id", "fact_order.order_status"]],
                tags=["追问:跨轮", "追问:指代"],
                note="第 1 轮的 2 家加第 3 轮的 2 家，共 4 行；退款中的也是退款记录。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E10",
        tags=["难度:中等"],
        note="比较两个品牌的销售，再找两个品牌都买过的钻石会员；主要考省略和跨轮的交集。",
        turns=[
            EvalCase(
                id="M3E10-1",
                query="华为这个牌子的商品卖了多少件、成交金额是多少？只算已付款的订单，金额保留两位小数。",
                reference_sql="""
                    SELECT SUM(i.quantity) AS quantity, ROUND(SUM(i.item_amount), 2) AS item_amount
                    FROM fact_order_item i
                    JOIN fact_order o ON i.order_id = o.order_id
                    JOIN dim_product p ON i.product_id = p.product_id
                    WHERE p.brand = '华为' AND o.pay_time IS NOT NULL
                """,
                must_hit_columns=["dim_product.brand", "fact_order_item.quantity", "fact_order_item.item_amount", _PAID],
                note="品牌级的成交金额只能用商品行的成交金额，已付款的范围写在题面。",
            ),
            EvalCase(
                id="M3E10-2",
                query="vivo 呢？金额保留 2 位小数。",
                reference_sql="""
                    SELECT SUM(i.quantity) AS quantity, ROUND(SUM(i.item_amount), 2) AS item_amount
                    FROM fact_order_item i
                    JOIN fact_order o ON i.order_id = o.order_id
                    JOIN dim_product p ON i.product_id = p.product_id
                    WHERE p.brand = 'vivo' AND o.pay_time IS NOT NULL
                """,
                must_hit_columns=["dim_product.brand", "fact_order_item.quantity", "fact_order_item.item_amount", _PAID],
                tags=["追问:省略"],
                note="只换品牌，其余沿用。",
            ),
            EvalCase(
                id="M3E10-3",
                query="这两个牌子都买过的钻石会员有哪些？列出用户昵称。",
                reference_sql="""
                    SELECT u.user_name
                    FROM dim_user u
                    WHERE u.member_level = '钻石会员'
                      AND u.user_id IN (
                          SELECT o.user_id FROM fact_order o
                          JOIN fact_order_item i ON o.order_id = i.order_id
                          JOIN dim_product p ON i.product_id = p.product_id
                          WHERE p.brand = '华为' AND o.pay_time IS NOT NULL
                      )
                      AND u.user_id IN (
                          SELECT o.user_id FROM fact_order o
                          JOIN fact_order_item i ON o.order_id = i.order_id
                          JOIN dim_product p ON i.product_id = p.product_id
                          WHERE p.brand = 'vivo' AND o.pay_time IS NOT NULL
                      )
                """,
                must_hit_columns=[
                    "dim_user.user_name",
                    "dim_user.member_level",
                    "dim_product.brand",
                    "fact_order_item.product_id",
                    _PAID,
                ],
                tags=["追问:跨轮", "追问:加条件"],
                note="“这两个牌子”把第 1、2 轮放在一起，两个都买过取交集；“买过”按口径约定只算已付款。",
            ),
            EvalCase(
                id="M3E10-4",
                query="他们分别在哪个城市、累计消费了多少？列出用户昵称、城市和消费金额，金额保留两位小数。",
                reference_sql="""
                    SELECT u.user_name, u.city, ROUND(d.total_pay_amount, 2) AS total_pay_amount
                    FROM dim_user u JOIN dws_user_summary d ON u.user_id = d.user_id
                    WHERE u.user_name IN ('用户10012', '用户10045', '用户10107', '用户10118')
                """,
                must_hit_columns=["dim_user.user_name", "dim_user.city", _USER_PAY],
                tags=["追问:指代", "追问:换角度"],
                note="“他们”是上一轮 4 位用户；累计消费是他们的全部消费，不限这两个牌子。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E11",
        tags=["难度:难"],
        note="从在同一家店多次付款的用户问到积分（库里没有），再回到这几位看金额和买过的商品；主要考陷阱后回到有答案的一轮。",
        turns=[
            EvalCase(
                id="M3E11-1",
                query="有没有用户在同一家店付过 3 笔及以上的款？把用户昵称、店铺名称和笔数列出来。",
                reference_sql="""
                    SELECT u.user_name, s.shop_name, COUNT(*) AS order_count
                    FROM fact_order o
                    JOIN dim_user u ON o.user_id = u.user_id
                    JOIN dim_shop s ON o.shop_id = s.shop_id
                    WHERE o.pay_time IS NOT NULL
                    GROUP BY u.user_id, u.user_name, s.shop_id, s.shop_name
                    HAVING COUNT(*) >= 3
                """,
                must_hit_columns=[
                    "dim_user.user_name",
                    "dim_shop.shop_name",
                    "fact_order.user_id",
                    "fact_order.shop_id",
                    _PAID,
                ],
                note="按用户和店铺的组合计已付款订单，共 3 个组合。",
            ),
            EvalCase(
                id="M3E11-2",
                query="他们现在分别有多少会员积分？",
                reference_sql=_TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里只有会员等级，没有积分数据，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M3E11-3",
                query="那回到这几位，他们在这家店分别一共付了多少钱？列出用户昵称、店铺名称和金额，金额保留 2 位小数。",
                reference_sql="""
                    SELECT u.user_name, s.shop_name, ROUND(SUM(o.pay_amount), 2) AS pay_amount
                    FROM fact_order o
                    JOIN dim_user u ON o.user_id = u.user_id
                    JOIN dim_shop s ON o.shop_id = s.shop_id
                    WHERE o.pay_time IS NOT NULL
                      AND (u.user_name, s.shop_name) IN (
                          VALUES ('用户10115', '臻品旗舰店10'), ('用户10122', '旗舰旗舰店7'), ('用户10139', '云集自营店9')
                      )
                    GROUP BY u.user_id, u.user_name, s.shop_id, s.shop_name
                """,
                must_hit_columns=[
                    "dim_user.user_name",
                    "dim_shop.shop_name",
                    "fact_order.user_id",
                    "fact_order.shop_id",
                    _ORDER_PAY,
                ],
                tags=["追问:跨轮", "追问:指代", "追问:换角度"],
                note="指回第 1 轮的 3 个组合，每位用户只算对应的那家店。",
            ),
            EvalCase(
                id="M3E11-4",
                query="付得最多的那位，在这家店都买过哪些商品？列出商品 ID、商品名称和件数。",
                reference_sql="""
                    SELECT p.product_id, p.product_name, SUM(i.quantity) AS quantity
                    FROM fact_order o
                    JOIN dim_user u ON o.user_id = u.user_id
                    JOIN dim_shop s ON o.shop_id = s.shop_id
                    JOIN fact_order_item i ON o.order_id = i.order_id
                    JOIN dim_product p ON i.product_id = p.product_id
                    WHERE u.user_name = '用户10122' AND s.shop_name = '旗舰旗舰店7' AND o.pay_time IS NOT NULL
                    GROUP BY p.product_id, p.product_name
                """,
                must_hit_columns=[
                    "dim_product.product_name",
                    "fact_order_item.quantity",
                    "fact_order_item.product_id",
                    ["fact_order.shop_id", "dim_product.shop_id"],
                ],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮付得最多的是用户10122，“这家店”是他对应的店；同一商品多次购买合计。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3E12",
        tags=["难度:难"],
        note="区分买家城市和店铺城市：两种看法各取前 3，再看第一名买家城市的钱流向哪些店铺城市和店铺；主要考跨轮和依赖结果。",
        turns=[
            EvalCase(
                id="M3E12-1",
                query="哪 3 个城市的用户累计消费金额最高？列出用户所在城市和消费金额，金额保留两位小数。",
                reference_sql="""
                    SELECT u.city, ROUND(SUM(d.total_pay_amount), 2) AS total_pay_amount
                    FROM dim_user u JOIN dws_user_summary d ON u.user_id = d.user_id
                    GROUP BY u.city
                    ORDER BY total_pay_amount DESC LIMIT 3
                """,
                must_hit_columns=["dim_user.city", _USER_PAY],
                note="题面点明用户所在城市；第 3、4 名不并列。",
            ),
            EvalCase(
                id="M3E12-2",
                query="换成按店铺所在城市看呢？金额保留 2 位小数。",
                reference_sql="""
                    SELECT s.city, ROUND(SUM(o.pay_amount), 2) AS pay_amount
                    FROM fact_order o JOIN dim_shop s ON o.shop_id = s.shop_id
                    WHERE o.pay_time IS NOT NULL
                    GROUP BY s.city
                    ORDER BY pay_amount DESC LIMIT 3
                """,
                must_hit_columns=["dim_shop.city", _SHOP_PAY],
                tags=["追问:省略", "追问:换角度"],
                note="指标和前 3 沿用，只把城市换成店铺的经营地；第 3、4 名不并列。",
            ),
            EvalCase(
                id="M3E12-3",
                query="最开始排第一的那个城市，它的用户在这 3 个店铺城市分别花了多少钱？列出店铺城市和金额，金额保留两位小数。",
                reference_sql="""
                    SELECT s.city, ROUND(SUM(o.pay_amount), 2) AS pay_amount
                    FROM fact_order o
                    JOIN dim_user u ON o.user_id = u.user_id
                    JOIN dim_shop s ON o.shop_id = s.shop_id
                    WHERE o.pay_time IS NOT NULL AND u.city = '成都' AND s.city IN ('深圳', '北京', '上海')
                    GROUP BY s.city
                """,
                must_hit_columns=["dim_user.city", "dim_shop.city", "fact_order.user_id", _ORDER_PAY],
                tags=["追问:跨轮", "追问:依赖结果"],
                note="“最开始排第一”是第 1 轮的成都，“这 3 个店铺城市”是第 2 轮结果。",
            ),
            EvalCase(
                id="M3E12-4",
                query="其中花得最多的那个店铺城市，具体在哪几家店各花了多少？列出店铺名称和金额，金额保留两位小数。",
                reference_sql="""
                    SELECT s.shop_name, ROUND(SUM(o.pay_amount), 2) AS pay_amount
                    FROM fact_order o
                    JOIN dim_user u ON o.user_id = u.user_id
                    JOIN dim_shop s ON o.shop_id = s.shop_id
                    WHERE o.pay_time IS NOT NULL AND u.city = '成都' AND s.city = '深圳'
                    GROUP BY s.shop_id, s.shop_name
                """,
                must_hit_columns=["dim_user.city", "dim_shop.city", "dim_shop.shop_name", _ORDER_PAY],
                tags=["追问:依赖结果", "追问:加条件"],
                note="上一轮花得最多的是深圳；买家范围仍是成都的用户。",
            ),
        ],
    ),
]


MULTITURN3_CHINOOK_CASES = [
    MultiTurnCase(
        id="M3C01",
        tags=["难度:中等"],
        note="从同时买过两个流派的客户问到国家和消费，再看他们买的 Classical 来自哪些艺术家；主要考依赖结果和省略。",
        turns=[
            EvalCase(
                id="M3C01-1",
                query="我想找口味比较杂的客户：Reggae 和 Classical 这两种流派的曲目都买过的那些人，给出他们的名和姓，各占一列。",
                reference_sql="""
                    SELECT c.FirstName, c.LastName
                    FROM Customer c
                    WHERE c.CustomerId IN (
                        SELECT i.CustomerId
                        FROM Invoice i
                        JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId
                        JOIN Track t ON il.TrackId = t.TrackId
                        JOIN Genre g ON t.GenreId = g.GenreId
                        WHERE g.Name = 'Reggae'
                    )
                    AND c.CustomerId IN (
                        SELECT i.CustomerId
                        FROM Invoice i
                        JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId
                        JOIN Track t ON il.TrackId = t.TrackId
                        JOIN Genre g ON t.GenreId = g.GenreId
                        WHERE g.Name = 'Classical'
                    )
                """,
                must_hit_columns=[
                    "Customer.FirstName",
                    "Customer.LastName",
                    "Genre.Name",
                    "Track.GenreId",
                    "InvoiceLine.TrackId",
                ],
                note="两个流派都买过才算，共 2 位。",
            ),
            EvalCase(
                id="M3C01-2",
                query="他们分别在哪个国家、一共消费了多少？列出名、姓、国家和消费金额，名和姓同样分两列，金额保留 2 位小数。",
                reference_sql="""
                    SELECT c.FirstName, c.LastName, c.Country, ROUND(SUM(i.Total), 2) AS total
                    FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId
                    WHERE (c.FirstName = 'Luís' AND c.LastName = 'Gonçalves') OR (c.FirstName = 'Marc' AND c.LastName = 'Dubois')
                    GROUP BY c.CustomerId, c.FirstName, c.LastName, c.Country
                """,
                must_hit_columns=["Customer.FirstName", "Customer.LastName", _COUNTRY, _SALES],
                tags=["追问:指代", "追问:换角度"],
                note="消费是这两位的全部消费，不限这两个流派。",
            ),
            EvalCase(
                id="M3C01-3",
                query="消费多的那位，他买的 Classical 曲目都是哪些艺术家的？各几首？",
                reference_sql="""
                    SELECT ar.Name, COUNT(*) AS track_count
                    FROM Customer c
                    JOIN Invoice i ON c.CustomerId = i.CustomerId
                    JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId
                    JOIN Track t ON il.TrackId = t.TrackId
                    JOIN Genre g ON t.GenreId = g.GenreId
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    JOIN Artist ar ON al.ArtistId = ar.ArtistId
                    WHERE c.FirstName = 'Luís' AND c.LastName = 'Gonçalves' AND g.Name = 'Classical'
                    GROUP BY ar.ArtistId, ar.Name
                """,
                must_hit_columns=["Artist.Name", "Genre.Name", "InvoiceLine.TrackId", "Album.ArtistId"],
                tags=["追问:依赖结果", "追问:加条件"],
                note="上一轮消费多的是 Luís Gonçalves；两位的金额不并列。",
            ),
            EvalCase(
                id="M3C01-4",
                query="另一位呢？",
                reference_sql="""
                    SELECT ar.Name, COUNT(*) AS track_count
                    FROM Customer c
                    JOIN Invoice i ON c.CustomerId = i.CustomerId
                    JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId
                    JOIN Track t ON il.TrackId = t.TrackId
                    JOIN Genre g ON t.GenreId = g.GenreId
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    JOIN Artist ar ON al.ArtistId = ar.ArtistId
                    WHERE c.FirstName = 'Marc' AND c.LastName = 'Dubois' AND g.Name = 'Classical'
                    GROUP BY ar.ArtistId, ar.Name
                """,
                must_hit_columns=["Artist.Name", "Genre.Name", "InvoiceLine.TrackId", "Album.ArtistId"],
                tags=["追问:省略", "追问:依赖结果"],
                note="一共只有 2 位，另一位是 Marc Dubois，问题和输出列沿用上一轮。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3C02",
        tags=["难度:难"],
        note="从某年入职的员工问到负责的客户，问到库里没有的薪酬，再回到客户看国家分布；主要考陷阱后回到有答案的一轮。",
        turns=[
            EvalCase(
                id="M3C02-1",
                query="在 Calgary 上班、2003 年入职的员工，名字和职位分别是什么？列出名、姓和职位，名和姓分两列。",
                reference_sql="""
                    SELECT FirstName, LastName, Title
                    FROM Employee
                    WHERE City = 'Calgary' AND strftime('%Y', HireDate) = '2003'
                """,
                must_hit_columns=[
                    "Employee.FirstName",
                    "Employee.LastName",
                    "Employee.Title",
                    "Employee.City",
                    "Employee.HireDate",
                ],
                note="两个条件同时满足的 3 位。",
            ),
            EvalCase(
                id="M3C02-2",
                query="他们各负责多少位客户？没负责客户的不用列，名和姓同样分两列。",
                reference_sql="""
                    SELECT e.FirstName, e.LastName, COUNT(*) AS customer_count
                    FROM Employee e JOIN Customer c ON c.SupportRepId = e.EmployeeId
                    WHERE e.City = 'Calgary' AND strftime('%Y', e.HireDate) = '2003'
                    GROUP BY e.EmployeeId, e.FirstName, e.LastName
                """,
                must_hit_columns=["Employee.FirstName", "Employee.LastName", "Customer.SupportRepId"],
                tags=["追问:指代", "追问:换角度"],
                note="其中一位不负责客户，题面说明不用列，共 2 行。",
            ),
            EvalCase(
                id="M3C02-3",
                query="这两位每个月的底薪和提成分别是多少？",
                reference_sql=_TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="员工表只有职位、上下级、日期和联系方式，没有任何薪酬数据，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M3C02-4",
                query="回到客户这块，负责客户多的那位，这些客户分布在哪些国家？各多少位？",
                reference_sql="""
                    SELECT c.Country, COUNT(*) AS customer_count
                    FROM Customer c JOIN Employee e ON c.SupportRepId = e.EmployeeId
                    WHERE e.FirstName = 'Margaret' AND e.LastName = 'Park'
                    GROUP BY c.Country
                """,
                must_hit_columns=["Customer.SupportRepId", "Customer.Country"],
                tags=["追问:跨轮", "追问:依赖结果"],
                note="指回第 2 轮，客户多的是 Margaret Park；客户分布用客户登记的国家。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3C03",
        tags=["难度:中等"],
        note="从名字带 Greatest 的专辑问到曲目和时长、曲目最多那张的流派，再回到这批专辑的销量；主要考指代和跨轮。",
        turns=[
            EvalCase(
                id="M3C03-1",
                query="名字里带 Greatest 的专辑都有哪些，分别是谁的？列出专辑名称和艺术家名称。",
                reference_sql="""
                    SELECT al.Title, ar.Name
                    FROM Album al JOIN Artist ar ON al.ArtistId = ar.ArtistId
                    WHERE al.Title LIKE '%Greatest%'
                """,
                must_hit_columns=["Album.Title", "Album.ArtistId", "Artist.Name"],
                note="共 8 张，专辑名称不重复。",
            ),
            EvalCase(
                id="M3C03-2",
                query="这几张各有多少首曲目、总时长多少分钟？列出专辑名称、曲目数和分钟数，分钟保留 1 位小数。",
                reference_sql="""
                    SELECT al.Title, COUNT(*) AS track_count, ROUND(SUM(t.Milliseconds) / 60000.0, 1) AS minutes
                    FROM Track t JOIN Album al ON t.AlbumId = al.AlbumId
                    WHERE al.Title LIKE '%Greatest%'
                    GROUP BY al.AlbumId, al.Title
                """,
                must_hit_columns=["Album.Title", "Track.AlbumId", "Track.Milliseconds"],
                tags=["追问:指代", "追问:换角度"],
                note="“这几张”是上一轮 8 张，逐张列出。",
            ),
            EvalCase(
                id="M3C03-3",
                query="曲目最多的那张，按流派分各多少首？",
                reference_sql="""
                    SELECT g.Name, COUNT(*) AS track_count
                    FROM Track t
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    JOIN Genre g ON t.GenreId = g.GenreId
                    WHERE al.Title = 'Greatest Hits'
                    GROUP BY g.GenreId, g.Name
                """,
                must_hit_columns=["Genre.Name", "Track.GenreId", "Track.AlbumId"],
                tags=["追问:依赖结果", "追问:加条件"],
                note="上一轮曲目最多的只有一张，不并列。",
            ),
            EvalCase(
                id="M3C03-4",
                query="回到这 8 张专辑，它们分别卖出去多少份？列出专辑名称和份数。",
                reference_sql="""
                    SELECT al.Title, SUM(il.Quantity) AS sold
                    FROM InvoiceLine il
                    JOIN Track t ON il.TrackId = t.TrackId
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    WHERE al.Title LIKE '%Greatest%'
                    GROUP BY al.AlbumId, al.Title
                """,
                must_hit_columns=["Album.Title", "InvoiceLine.TrackId", "Track.AlbumId"],
                tags=["追问:跨轮", "追问:指代", "追问:换角度"],
                note="对象回到第 1 轮的 8 张；每张都有销售，不存在没卖出去的问题。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3C04",
        tags=["难度:中等"],
        note="从作曲者切入：曲目收在哪些专辑、卖得怎样，换一位作曲者，再把两位放在一起看流派；主要考省略和跨轮。",
        turns=[
            EvalCase(
                id="M3C04-1",
                query="作曲者是 Kurt Cobain 的曲目，收在哪几张专辑里？各有多少首？",
                reference_sql="""
                    SELECT al.Title, COUNT(*) AS track_count
                    FROM Track t JOIN Album al ON t.AlbumId = al.AlbumId
                    WHERE t.Composer = 'Kurt Cobain'
                    GROUP BY al.AlbumId, al.Title
                """,
                must_hit_columns=["Track.Composer", "Track.AlbumId", "Album.Title"],
                note="作曲者是自由文本，题面用库里的原文；模糊匹配和精确匹配结果一致。",
            ),
            EvalCase(
                id="M3C04-2",
                query="这些曲目按专辑分别卖了多少份、多少钱？金额保留 2 位小数。",
                reference_sql="""
                    SELECT al.Title, SUM(il.Quantity) AS sold, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS sales
                    FROM InvoiceLine il
                    JOIN Track t ON il.TrackId = t.TrackId
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    WHERE t.Composer = 'Kurt Cobain'
                    GROUP BY al.AlbumId, al.Title
                """,
                must_hit_columns=["Track.Composer", "Album.Title", "InvoiceLine.TrackId", "InvoiceLine.UnitPrice"],
                tags=["追问:指代", "追问:换角度"],
                note="只算这位作曲者的曲目，不是整张专辑；曲目级的销售额只能从明细行算。",
            ),
            EvalCase(
                id="M3C04-3",
                query="Billy Corgan 写的呢？金额同样保留 2 位小数。",
                reference_sql="""
                    SELECT al.Title, SUM(il.Quantity) AS sold, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS sales
                    FROM InvoiceLine il
                    JOIN Track t ON il.TrackId = t.TrackId
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    WHERE t.Composer = 'Billy Corgan'
                    GROUP BY al.AlbumId, al.Title
                """,
                must_hit_columns=["Track.Composer", "Album.Title", "InvoiceLine.TrackId", "InvoiceLine.UnitPrice"],
                tags=["追问:省略"],
                note="只换作曲者，问题和输出列沿用上一轮。",
            ),
            EvalCase(
                id="M3C04-4",
                query="这两位作曲者的曲目分别属于哪些流派？各多少首？列出作曲者、流派名称和首数。",
                reference_sql="""
                    SELECT t.Composer, g.Name, COUNT(*) AS track_count
                    FROM Track t JOIN Genre g ON t.GenreId = g.GenreId
                    WHERE t.Composer IN ('Kurt Cobain', 'Billy Corgan')
                    GROUP BY t.Composer, g.GenreId, g.Name
                """,
                must_hit_columns=["Track.Composer", "Track.GenreId", "Genre.Name"],
                tags=["追问:跨轮", "追问:换角度"],
                note="“这两位”把前面两位作曲者放在一起，统计全部曲目，不只卖出去的。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3C05",
        tags=["难度:中等"],
        note="三个歌单的收录和销量，再钻到收录最少的歌单的艺术家和他们的专辑；避开库里重名的歌单。",
        turns=[
            EvalCase(
                id="M3C05-1",
                query="Heavy Metal Classic、Grunge、Brazilian Music 这三个歌单分别收录了多少首曲目？",
                reference_sql="""
                    SELECT p.Name, COUNT(*) AS track_count
                    FROM Playlist p JOIN PlaylistTrack pt ON p.PlaylistId = pt.PlaylistId
                    WHERE p.Name IN ('Heavy Metal Classic', 'Grunge', 'Brazilian Music')
                    GROUP BY p.PlaylistId, p.Name
                """,
                must_hit_columns=["Playlist.Name", "PlaylistTrack.PlaylistId"],
                note="这三个歌单名都不重名。",
            ),
            EvalCase(
                id="M3C05-2",
                query="这三个歌单里的曲目，按歌单分别卖出去多少份？",
                reference_sql="""
                    SELECT p.Name, SUM(il.Quantity) AS sold
                    FROM Playlist p
                    JOIN PlaylistTrack pt ON p.PlaylistId = pt.PlaylistId
                    JOIN InvoiceLine il ON pt.TrackId = il.TrackId
                    WHERE p.Name IN ('Heavy Metal Classic', 'Grunge', 'Brazilian Music')
                    GROUP BY p.PlaylistId, p.Name
                """,
                must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "InvoiceLine.TrackId"],
                tags=["追问:指代", "追问:换角度"],
                note="一首曲目卖出几次算几份，按歌单汇总。",
            ),
            EvalCase(
                id="M3C05-3",
                query="收录曲目最少的那个，里面都是哪些艺术家的曲目？各多少首？",
                reference_sql="""
                    SELECT ar.Name, COUNT(*) AS track_count
                    FROM PlaylistTrack pt
                    JOIN Playlist p ON pt.PlaylistId = p.PlaylistId
                    JOIN Track t ON pt.TrackId = t.TrackId
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    JOIN Artist ar ON al.ArtistId = ar.ArtistId
                    WHERE p.Name = 'Grunge'
                    GROUP BY ar.ArtistId, ar.Name
                """,
                must_hit_columns=["Artist.Name", "Playlist.Name", "PlaylistTrack.TrackId"],
                tags=["追问:跨轮", "追问:依赖结果", "追问:加条件"],
                note="收录数在第 1 轮，最少的是 Grunge。",
            ),
            EvalCase(
                id="M3C05-4",
                query="这些艺术家在曲库里分别有多少张专辑？",
                reference_sql="""
                    SELECT ar.Name, COUNT(*) AS album_count
                    FROM Album al JOIN Artist ar ON al.ArtistId = ar.ArtistId
                    WHERE ar.Name IN ('Nirvana', 'Pearl Jam', 'Soundgarden', 'Temple of the Dog',
                                      'Stone Temple Pilots', 'Alice In Chains')
                    GROUP BY ar.ArtistId, ar.Name
                """,
                must_hit_columns=["Artist.Name", "Album.ArtistId"],
                tags=["追问:指代", "追问:换角度"],
                note="“这些艺术家”是上一轮 6 位；“在曲库里”说明不限这个歌单。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3C06",
        tags=["难度:中等"],
        note="从超长的非视频曲目问到专辑和流派、买过的客户和他们的国家；主要考指代链和加条件。",
        turns=[
            EvalCase(
                id="M3C06-1",
                query="不算视频格式，时长超过 15 分钟的曲目有哪些？列出曲目 ID、曲目名称和时长（分钟），时长保留 1 位小数。",
                reference_sql="""
                    SELECT t.TrackId, t.Name, ROUND(t.Milliseconds / 60000.0, 1) AS minutes
                    FROM Track t JOIN MediaType m ON t.MediaTypeId = m.MediaTypeId
                    WHERE m.Name <> 'Protected MPEG-4 video file' AND t.Milliseconds > 900000
                """,
                must_hit_columns=["Track.Name", "Track.Milliseconds", "Track.MediaTypeId"],
                note="视频格式只有一种；结果里有同名曲目，题面要求列曲目 ID。共 7 首。",
            ),
            EvalCase(
                id="M3C06-2",
                query="它们分别在哪张专辑里、属于什么流派？列出曲目 ID、专辑名称和流派名称。",
                reference_sql="""
                    SELECT t.TrackId, al.Title, g.Name
                    FROM Track t
                    JOIN Album al ON t.AlbumId = al.AlbumId
                    JOIN Genre g ON t.GenreId = g.GenreId
                    WHERE t.TrackId IN (610, 620, 621, 1581, 1666, 2429, 2432)
                """,
                must_hit_columns=["Album.Title", "Genre.Name", "Track.AlbumId", "Track.GenreId"],
                tags=["追问:指代", "追问:换角度"],
                note="“它们”是上一轮 7 首，每首一行。",
            ),
            EvalCase(
                id="M3C06-3",
                query="这里面卖出去过的是哪几首、买的客户是谁？列出曲目 ID、客户的名和姓，名和姓分两列。",
                reference_sql="""
                    SELECT il.TrackId, c.FirstName, c.LastName
                    FROM InvoiceLine il
                    JOIN Invoice i ON il.InvoiceId = i.InvoiceId
                    JOIN Customer c ON i.CustomerId = c.CustomerId
                    WHERE il.TrackId IN (610, 620, 621, 1581, 1666, 2429, 2432)
                """,
                must_hit_columns=["InvoiceLine.TrackId", "Invoice.CustomerId", "Customer.FirstName", "Customer.LastName"],
                tags=["追问:指代", "追问:加条件"],
                note="这 7 首里卖出去过的有 4 首，每首卖出一次，共 4 行。",
            ),
            EvalCase(
                id="M3C06-4",
                query="这几位客户分别在哪个国家？列出客户的名、姓和国家，名和姓同样分两列。",
                reference_sql="""
                    SELECT c.FirstName, c.LastName, c.Country
                    FROM Customer c
                    WHERE (c.FirstName = 'Dan' AND c.LastName = 'Miller')
                       OR (c.FirstName = 'Jennifer' AND c.LastName = 'Peterson')
                       OR (c.FirstName = 'Terhi' AND c.LastName = 'Hämäläinen')
                       OR (c.FirstName = 'Robert' AND c.LastName = 'Brown')
                """,
                must_hit_columns=["Customer.FirstName", "Customer.LastName", _COUNTRY],
                tags=["追问:指代", "追问:依赖结果"],
                note="这几位只能从上一轮结果得知，每位一行。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3C07",
        tags=["难度:中等"],
        note="两年年底金额较大的发票，再把两批放在一起看流派和负责的员工；主要考省略和跨轮。",
        turns=[
            EvalCase(
                id="M3C07-1",
                query="帮我拉个清单：只看 2023 年 12 月开出来的发票，把金额超过 5 的挑出来，要发票号、开票国家、金额这三列。",
                reference_sql="""
                    SELECT InvoiceId, BillingCountry, Total
                    FROM Invoice
                    WHERE strftime('%Y-%m', InvoiceDate) = '2023-12' AND Total > 5
                """,
                must_hit_columns=["Invoice.InvoiceId", "Invoice.InvoiceDate", _COUNTRY, _SALES],
                note="按开票日期取月份，单张金额过滤，共 3 张。",
            ),
            EvalCase(
                id="M3C07-2",
                query="2024 年 12 月呢？",
                reference_sql="""
                    SELECT InvoiceId, BillingCountry, Total
                    FROM Invoice
                    WHERE strftime('%Y-%m', InvoiceDate) = '2024-12' AND Total > 5
                """,
                must_hit_columns=["Invoice.InvoiceId", "Invoice.InvoiceDate", _COUNTRY, _SALES],
                tags=["追问:省略"],
                note="只换年份，金额条件和输出列沿用。",
            ),
            EvalCase(
                id="M3C07-3",
                query="这两个月的这 6 张发票放一起，按流派分别买了多少首？",
                reference_sql="""
                    SELECT g.Name, SUM(il.Quantity) AS track_count
                    FROM InvoiceLine il
                    JOIN Track t ON il.TrackId = t.TrackId
                    JOIN Genre g ON t.GenreId = g.GenreId
                    WHERE il.InvoiceId IN (243, 248, 249, 326, 327, 332)
                    GROUP BY g.GenreId, g.Name
                """,
                must_hit_columns=["Genre.Name", "Track.GenreId", "InvoiceLine.InvoiceId", "InvoiceLine.TrackId"],
                tags=["追问:跨轮", "追问:换角度"],
                note="把第 1、2 轮的发票放在一起，只按流派分组。",
            ),
            EvalCase(
                id="M3C07-4",
                query="这 6 张发票的客户分别由哪位员工负责？列出发票号、员工的名和姓，名和姓分两列。",
                reference_sql="""
                    SELECT i.InvoiceId, e.FirstName, e.LastName
                    FROM Invoice i
                    JOIN Customer c ON i.CustomerId = c.CustomerId
                    JOIN Employee e ON c.SupportRepId = e.EmployeeId
                    WHERE i.InvoiceId IN (243, 248, 249, 326, 327, 332)
                """,
                must_hit_columns=["Invoice.InvoiceId", "Customer.SupportRepId", "Employee.FirstName", "Employee.LastName"],
                tags=["追问:指代", "追问:换角度"],
                note="每张发票一行，员工经发票的客户找到。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3C08",
        tags=["难度:简单"],
        note="有公司的客户：消费、负责的员工、员工的上级；主要考指代链。",
        turns=[
            EvalCase(
                id="M3C08-1",
                query="有公司的客户都有谁？列出客户的名、姓和公司名称，名和姓分两列。",
                reference_sql="""
                    SELECT FirstName, LastName, Company
                    FROM Customer
                    WHERE Company IS NOT NULL
                """,
                must_hit_columns=["Customer.FirstName", "Customer.LastName", "Customer.Company"],
                note="公司不为空的 10 位。",
            ),
            EvalCase(
                id="M3C08-2",
                query="他们分别消费了多少钱？列出客户的名、姓和消费金额，名和姓同样分两列，金额保留两位小数。",
                reference_sql="""
                    SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS total
                    FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId
                    WHERE c.Company IS NOT NULL
                    GROUP BY c.CustomerId, c.FirstName, c.LastName
                """,
                must_hit_columns=["Customer.FirstName", "Customer.LastName", _SALES],
                tags=["追问:指代", "追问:换角度"],
                note="“他们”是上一轮 10 位，逐个列出。",
            ),
            EvalCase(
                id="M3C08-3",
                query="消费最高的那位是哪位员工负责的？列出员工的名和姓，分两列。",
                reference_sql="""
                    SELECT e.FirstName, e.LastName
                    FROM Employee e JOIN Customer c ON c.SupportRepId = e.EmployeeId
                    WHERE c.FirstName = 'František' AND c.LastName = 'Wichterlová'
                """,
                must_hit_columns=["Customer.SupportRepId", "Employee.FirstName", "Employee.LastName"],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮这 10 位里消费最高的只有一位，不并列。",
            ),
            EvalCase(
                id="M3C08-4",
                query="这位员工的直属上级是谁？列出上级的名、姓和职位，名和姓分两列。",
                reference_sql="""
                    SELECT m.FirstName, m.LastName, m.Title
                    FROM Employee e JOIN Employee m ON e.ReportsTo = m.EmployeeId
                    WHERE e.FirstName = 'Margaret' AND e.LastName = 'Park'
                """,
                must_hit_columns=["Employee.ReportsTo", "Employee.FirstName", "Employee.LastName", "Employee.Title"],
                tags=["追问:指代", "追问:依赖结果"],
                note="“这位员工”是上一轮结果；要走员工表的上下级关系。",
            ),
        ],
    ),
]


MULTITURN3_SAKILA_CASES = [
    MultiTurnCase(
        id="M3S01",
        tags=["难度:中等"],
        note="从只在一家门店有拷贝的片子切入：被租次数、换分类换门店，再问两家店的店长和城市；主要考指代和跨轮。",
        turns=[
            EvalCase(
                id="M3S01-1",
                query="Horror 分类的片子里，只在 1 号店有拷贝、2 号店一张都没有的是哪些？列出片名和 1 号店的拷贝数。",
                reference_sql="""
                    SELECT f.title, COUNT(*) AS copy_count
                    FROM inventory i
                    JOIN film f ON i.film_id = f.film_id
                    JOIN film_category fc ON f.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE c.name = 'Horror' AND i.store_id = 1
                      AND f.film_id NOT IN (SELECT film_id FROM inventory WHERE store_id = 2)
                    GROUP BY f.film_id, f.title
                """,
                must_hit_columns=["film.title", "category.name", "inventory.store_id", "inventory.film_id"],
                note="共 10 部；片名在库里不重复。",
            ),
            EvalCase(
                id="M3S01-2",
                query="这些片子分别被租过多少次？列出片名和次数。",
                reference_sql="""
                    SELECT f.title, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film f ON i.film_id = f.film_id
                    WHERE f.title IN ('ANALYZE HOOSIERS', 'ANYTHING SAVANNAH', 'ELEPHANT TROJAN', 'LOVE SUICIDES', 'PANIC CLUB',
                                      'SIMON NORTH', 'TARZAN VIDEOTAPE', 'TEXAS WATCH', 'TRAIN BUNCH', 'WATERSHIP FRONTIER')
                    GROUP BY f.film_id, f.title
                """,
                must_hit_columns=["film.title", "rental.inventory_id", "inventory.film_id"],
                tags=["追问:指代", "追问:换角度"],
                note="“这些片子”是上一轮 10 部，这些片子的拷贝都在 1 号店，不存在分店问题。",
            ),
            EvalCase(
                id="M3S01-3",
                query="换成 Music 分类、只在 2 号店有拷贝的片子，同样列片名和这家店的拷贝数。",
                reference_sql="""
                    SELECT f.title, COUNT(*) AS copy_count
                    FROM inventory i
                    JOIN film f ON i.film_id = f.film_id
                    JOIN film_category fc ON f.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE c.name = 'Music' AND i.store_id = 2
                      AND f.film_id NOT IN (SELECT film_id FROM inventory WHERE store_id = 1)
                    GROUP BY f.film_id, f.title
                """,
                must_hit_columns=["film.title", "category.name", "inventory.store_id", "inventory.film_id"],
                tags=["追问:省略", "追问:跨轮"],
                note="回到第 1 轮的问题，换分类、对调两家店，输出列写在题面。",
            ),
            EvalCase(
                id="M3S01-4",
                query="这两家店的店长分别是谁、门店各在哪个城市？列出门店编号、店长的名和姓、城市，名和姓分两列。",
                reference_sql="""
                    SELECT s.store_id, st.first_name, st.last_name, c.city
                    FROM store s
                    JOIN staff st ON s.manager_staff_id = st.staff_id
                    JOIN address a ON s.address_id = a.address_id
                    JOIN city c ON a.city_id = c.city_id
                """,
                must_hit_columns=[
                    "staff.first_name",
                    "staff.last_name",
                    "store.address_id",
                    "city.city",
                    ["store.manager_staff_id", "staff.store_id"],
                ],
                tags=["追问:指代", "追问:换角度"],
                note="城市是门店地址的城市；店长也是各店唯一的员工，两条路径结果一致。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3S02",
        tags=["难度:中等"],
        note="出租最多的影片分类：营业额、第一名分类的影片、影片的演员数；主要考多层关联上的指代和依赖结果。",
        turns=[
            EvalCase(
                id="M3S02-1",
                query="出租次数最多的 3 个影片分类是什么？列出分类名称和出租次数。",
                reference_sql="""
                    SELECT c.name, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    GROUP BY c.category_id, c.name
                    ORDER BY rental_count DESC LIMIT 3
                """,
                must_hit_columns=["category.name", "film_category.category_id", "inventory.film_id", "rental.inventory_id"],
                note="第 3、4 名不并列。",
            ),
            EvalCase(
                id="M3S02-2",
                query="它们的营业额分别是多少？金额保留两位小数。",
                reference_sql="""
                    SELECT c.name, ROUND(SUM(p.amount), 2) AS revenue
                    FROM payment p
                    JOIN rental r ON p.rental_id = r.rental_id
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE c.name IN ('Sports', 'Animation', 'Action')
                    GROUP BY c.category_id, c.name
                """,
                must_hit_columns=["category.name", "payment.amount", "payment.rental_id", "rental.inventory_id"],
                tags=["追问:指代", "追问:换角度"],
                note="营业额是实收，不是标价；“它们”是上一轮 3 个分类。",
            ),
            EvalCase(
                id="M3S02-3",
                query="排第一的那个分类里，被租次数最多的 4 部影片是哪些？列出片名和次数。",
                reference_sql="""
                    SELECT f.title, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film f ON i.film_id = f.film_id
                    JOIN film_category fc ON f.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE c.name = 'Sports'
                    GROUP BY f.film_id, f.title
                    ORDER BY rental_count DESC LIMIT 4
                """,
                must_hit_columns=["film.title", "category.name", "rental.inventory_id", "inventory.film_id"],
                tags=["追问:依赖结果", "追问:加条件"],
                note="第一名是 Sports（前两轮都排第一）；第 4、5 名不并列。",
            ),
            EvalCase(
                id="M3S02-4",
                query="这 4 部影片分别有几位演员？列出片名和演员数。",
                reference_sql="""
                    SELECT f.title, COUNT(*) AS actor_count
                    FROM film f JOIN film_actor fa ON f.film_id = fa.film_id
                    WHERE f.title IN ('TALENTED HOMICIDE', 'GLEAMING JAWBREAKER', 'SATURDAY LAMBS', 'ROSES TREASURE')
                    GROUP BY f.film_id, f.title
                """,
                must_hit_columns=["film.title", "film_actor.film_id"],
                tags=["追问:指代", "追问:换角度"],
                note="“这 4 部”是上一轮结果；片名在库里不重复。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3S03",
        tags=["难度:难"],
        note="姓 NOLTE 的演员在 R 级片上的情况：部数、被租次数、最热门的片，再看这几位同演的片；主要考依赖结果和跨轮。",
        turns=[
            EvalCase(
                id="M3S03-1",
                query="姓 NOLTE 的演员，每人演过多少部 R 级片？列出名、姓和部数，名和姓分两列。",
                reference_sql="""
                    SELECT a.first_name, a.last_name, COUNT(*) AS film_count
                    FROM actor a
                    JOIN film_actor fa ON a.actor_id = fa.actor_id
                    JOIN film f ON fa.film_id = f.film_id
                    WHERE a.last_name = 'NOLTE' AND f.rating = 'R'
                    GROUP BY a.actor_id, a.first_name, a.last_name
                """,
                must_hit_columns=["actor.first_name", "actor.last_name", "film_actor.actor_id", "film.rating"],
                note="这个姓共 4 位演员，每人一行。",
            ),
            EvalCase(
                id="M3S03-2",
                query="这些片子被租过多少次？按人列，名和姓同样分两列。",
                reference_sql="""
                    SELECT a.first_name, a.last_name, COUNT(*) AS rental_count
                    FROM actor a
                    JOIN film_actor fa ON a.actor_id = fa.actor_id
                    JOIN film f ON fa.film_id = f.film_id
                    JOIN inventory i ON f.film_id = i.film_id
                    JOIN rental r ON i.inventory_id = r.inventory_id
                    WHERE a.last_name = 'NOLTE' AND f.rating = 'R'
                    GROUP BY a.actor_id, a.first_name, a.last_name
                """,
                must_hit_columns=["actor.first_name", "actor.last_name", "film.rating", "rental.inventory_id", "inventory.film_id"],
                tags=["追问:指代", "追问:换角度"],
                note="“这些片子”是每人的 R 级片，每人名下合计。",
            ),
            EvalCase(
                id="M3S03-3",
                query="被租次数最多的那位，他的 R 级片里租得最多的 2 部是哪些？列出片名和次数。",
                reference_sql="""
                    SELECT f.title, COUNT(*) AS rental_count
                    FROM actor a
                    JOIN film_actor fa ON a.actor_id = fa.actor_id
                    JOIN film f ON fa.film_id = f.film_id
                    JOIN inventory i ON f.film_id = i.film_id
                    JOIN rental r ON i.inventory_id = r.inventory_id
                    WHERE a.first_name = 'SALMA' AND a.last_name = 'NOLTE' AND f.rating = 'R'
                    GROUP BY f.film_id, f.title
                    ORDER BY rental_count DESC LIMIT 2
                """,
                must_hit_columns=["film.title", "film.rating", "film_actor.actor_id", "rental.inventory_id"],
                tags=["追问:依赖结果", "追问:加条件"],
                note="上一轮最多的是 SALMA NOLTE；第 2、3 部不并列。",
            ),
            EvalCase(
                id="M3S03-4",
                query="不限分级了，这 4 位里至少两人一起演过的片子有哪些？列出片名和其中参演的人数。",
                reference_sql="""
                    SELECT f.title, COUNT(*) AS actor_count
                    FROM film_actor fa
                    JOIN actor a ON fa.actor_id = a.actor_id
                    JOIN film f ON fa.film_id = f.film_id
                    WHERE a.last_name = 'NOLTE'
                    GROUP BY f.film_id, f.title
                    HAVING COUNT(*) >= 2
                """,
                must_hit_columns=["film.title", "film_actor.actor_id", "film_actor.film_id", "actor.last_name"],
                tags=["追问:跨轮", "追问:指代"],
                note="“这 4 位”是第 1 轮的演员；人数只数这 4 位里参演的。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3S04",
        tags=["难度:中等"],
        note="从两个国家的不活跃客户问到消费，再看消费最高和第二高的客户最常租的分类；主要考依赖结果和跨轮省略。",
        turns=[
            EvalCase(
                id="M3S04-1",
                query="不活跃的客户里，住在 China 或 India 的有谁？列出客户的名、姓、城市和国家，名和姓分两列。",
                reference_sql="""
                    SELECT c.first_name, c.last_name, ci.city, co.country
                    FROM customer c
                    JOIN address a ON c.address_id = a.address_id
                    JOIN city ci ON a.city_id = ci.city_id
                    JOIN country co ON ci.country_id = co.country_id
                    WHERE c.active = '0' AND co.country IN ('China', 'India')
                """,
                must_hit_columns=[
                    "customer.active",
                    "customer.first_name",
                    "customer.last_name",
                    "customer.address_id",
                    "city.city",
                    "country.country",
                ],
                note="共 6 位。",
            ),
            EvalCase(
                id="M3S04-2",
                query="他们分别消费了多少？名和姓同样分两列，金额保留 2 位小数。",
                reference_sql="""
                    SELECT c.first_name, c.last_name, ROUND(SUM(p.amount), 2) AS total
                    FROM payment p
                    JOIN customer c ON p.customer_id = c.customer_id
                    JOIN address a ON c.address_id = a.address_id
                    JOIN city ci ON a.city_id = ci.city_id
                    JOIN country co ON ci.country_id = co.country_id
                    WHERE c.active = '0' AND co.country IN ('China', 'India')
                    GROUP BY c.customer_id, c.first_name, c.last_name
                """,
                must_hit_columns=["customer.first_name", "customer.last_name", "payment.amount", "payment.customer_id"],
                tags=["追问:指代", "追问:换角度"],
                note="“他们”是上一轮 6 位，逐个列出，金额互不相同。",
            ),
            EvalCase(
                id="M3S04-3",
                query="消费最高的那位，租得最多的是哪个影片分类？列出分类名称和次数。",
                reference_sql="""
                    SELECT ca.name, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN customer c ON r.customer_id = c.customer_id
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category ca ON fc.category_id = ca.category_id
                    WHERE c.first_name = 'HEIDI' AND c.last_name = 'LARSON'
                    GROUP BY ca.category_id, ca.name
                    ORDER BY rental_count DESC LIMIT 1
                """,
                must_hit_columns=["category.name", "rental.customer_id", "rental.inventory_id", "film_category.category_id"],
                tags=["追问:依赖结果", "追问:指代"],
                note="上一轮最高的是 HEIDI LARSON；她的第 1、2 名分类不并列。",
            ),
            EvalCase(
                id="M3S04-4",
                query="消费第二高的那位呢？",
                reference_sql="""
                    SELECT ca.name, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN customer c ON r.customer_id = c.customer_id
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category ca ON fc.category_id = ca.category_id
                    WHERE c.first_name = 'THEODORE' AND c.last_name = 'CULP'
                    GROUP BY ca.category_id, ca.name
                    ORDER BY rental_count DESC LIMIT 1
                """,
                must_hit_columns=["category.name", "rental.customer_id", "rental.inventory_id", "film_category.category_id"],
                tags=["追问:省略", "追问:跨轮", "追问:依赖结果"],
                note="回到第 2 轮的金额，第二高的是 THEODORE CULP，问题和输出列沿用上一轮；第 1、2 名分类不并列。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3S05",
        tags=["难度:难"],
        note="高消费客户的租借和逾期，问到库里没有的打分，再回到逾期按分类拆；主要考陷阱后回到有答案的一轮。",
        turns=[
            EvalCase(
                id="M3S05-1",
                query="消费总额最高的 3 位客户是谁？列出客户的名、姓和消费总额，名和姓分两列，金额保留两位小数。",
                reference_sql="""
                    SELECT c.first_name, c.last_name, ROUND(SUM(p.amount), 2) AS total
                    FROM payment p JOIN customer c ON p.customer_id = c.customer_id
                    GROUP BY c.customer_id, c.first_name, c.last_name
                    ORDER BY total DESC LIMIT 3
                """,
                must_hit_columns=["customer.first_name", "customer.last_name", "payment.amount", "payment.customer_id"],
                note="第 3、4 名不并列（第 4、5 名并列，但不在边界上）。",
            ),
            EvalCase(
                id="M3S05-2",
                query="他们分别租过多少次？其中逾期归还的有多少次？逾期这样判断：从租出到归还的实际时长，精确到秒，超过这部影片的租期就算。名和姓同样分两列。",
                reference_sql="""
                    SELECT c.first_name, c.last_name, COUNT(*) AS rental_count,
                           SUM(CASE WHEN r.return_date IS NOT NULL
                                     AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
                                    THEN 1 ELSE 0 END) AS overdue_count
                    FROM rental r
                    JOIN customer c ON r.customer_id = c.customer_id
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film f ON i.film_id = f.film_id
                    WHERE c.first_name || ' ' || c.last_name IN ('KARL SEAL', 'ELEANOR HUNT', 'CLARA SHAW')
                    GROUP BY c.customer_id, c.first_name, c.last_name
                """,
                must_hit_columns=[
                    "customer.first_name",
                    "customer.last_name",
                    "rental.customer_id",
                    "rental.return_date",
                    "rental.rental_date",
                    "film.rental_duration",
                ],
                tags=["追问:指代", "追问:换角度"],
                note="逾期按精确到秒的实际时长判断，写在题面，不是日期差；这 3 位没有未归还的记录，未还算不算逾期不影响结果。",
            ),
            EvalCase(
                id="M3S05-3",
                query="他们给租过的片子打的平均分分别是多少？",
                reference_sql=_TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里没有客户打分；影片的分级是美国电影分级，不是分数，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M3S05-4",
                query="回到逾期，逾期次数最多的那位，他逾期的那些租借按影片分类分，各多少次？",
                reference_sql="""
                    SELECT ca.name, COUNT(*) AS overdue_count
                    FROM rental r
                    JOIN customer c ON r.customer_id = c.customer_id
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film f ON i.film_id = f.film_id
                    JOIN film_category fc ON f.film_id = fc.film_id
                    JOIN category ca ON fc.category_id = ca.category_id
                    WHERE c.first_name = 'KARL' AND c.last_name = 'SEAL'
                      AND r.return_date IS NOT NULL
                      AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
                    GROUP BY ca.category_id, ca.name
                """,
                must_hit_columns=["category.name", "rental.return_date", "rental.rental_date", "film.rental_duration"],
                tags=["追问:跨轮", "追问:依赖结果"],
                note="指回第 2 轮，逾期次数最多的是 KARL SEAL，逾期口径沿用第 2 轮。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3S06",
        tags=["难度:中等"],
        note="各分级的影片数，再看没有拷贝的影片：片长、分类和演员数；主要考范围的逐轮继承。",
        turns=[
            EvalCase(
                id="M3S06-1",
                query="各分级的影片分别有多少部？",
                reference_sql="""
                    SELECT rating, COUNT(*) AS film_count
                    FROM film
                    GROUP BY rating
                """,
                must_hit_columns=["film.rating"],
                note="5 个分级，每个一行。",
            ),
            EvalCase(
                id="M3S06-2",
                query="其中一张拷贝都没有的，分别有多少部？",
                reference_sql="""
                    SELECT rating, COUNT(*) AS film_count
                    FROM film
                    WHERE film_id NOT IN (SELECT film_id FROM inventory)
                    GROUP BY rating
                """,
                must_hit_columns=["film.rating", "inventory.film_id"],
                tags=["追问:加条件", "追问:省略"],
                note="沿用按分级分组，收窄到没有拷贝的影片；5 个分级都有。",
            ),
            EvalCase(
                id="M3S06-3",
                query="这些片子里，片长最长的 3 部是什么？列出片名和片长。",
                reference_sql="""
                    SELECT title, length
                    FROM film
                    WHERE film_id NOT IN (SELECT film_id FROM inventory)
                    ORDER BY length DESC LIMIT 3
                """,
                must_hit_columns=["film.title", "film.length", "inventory.film_id"],
                tags=["追问:指代", "追问:加条件"],
                note="“这些片子”是上一轮没有拷贝的影片（不再分分级）；第 3、4 名不并列。",
            ),
            EvalCase(
                id="M3S06-4",
                query="这 3 部分别属于什么分类、有几位演员？列出片名、分类名称和演员数。",
                reference_sql="""
                    SELECT f.title, c.name, COUNT(*) AS actor_count
                    FROM film f
                    JOIN film_category fc ON f.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    JOIN film_actor fa ON f.film_id = fa.film_id
                    WHERE f.title IN ('CRYSTAL BREAKING', 'CATCH AMISTAD', 'GLADIATOR WESTWARD')
                    GROUP BY f.film_id, f.title, c.name
                """,
                must_hit_columns=["film.title", "category.name", "film_actor.film_id"],
                tags=["追问:指代", "追问:换角度"],
                note="“这 3 部”是上一轮结果；每部影片只属于一个分类。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3S07",
        tags=["难度:中等"],
        note="两位员工两个月的收款，再放在一起看办理的租借；主要考收款员工和办理员工的区分，以及跨轮。",
        turns=[
            EvalCase(
                id="M3S07-1",
                query="把 2005 年 7 月的付款按收款员工汇总：每位员工收到多少钱？名、姓各占一列，再加一列金额（保留 2 位小数）。",
                reference_sql="""
                    SELECT st.first_name, st.last_name, ROUND(SUM(p.amount), 2) AS amount
                    FROM payment p JOIN staff st ON p.staff_id = st.staff_id
                    WHERE substr(p.payment_date, 1, 7) = '2005-07'
                    GROUP BY st.staff_id, st.first_name, st.last_name
                """,
                must_hit_columns=[
                    "staff.first_name",
                    "staff.last_name",
                    "payment.staff_id",
                    "payment.payment_date",
                    "payment.amount",
                ],
                note="收款的员工看付款记录上的员工，按付款时间算月份。",
            ),
            EvalCase(
                id="M3S07-2",
                query="8 月呢？金额保留 2 位小数。",
                reference_sql="""
                    SELECT st.first_name, st.last_name, ROUND(SUM(p.amount), 2) AS amount
                    FROM payment p JOIN staff st ON p.staff_id = st.staff_id
                    WHERE substr(p.payment_date, 1, 7) = '2005-08'
                    GROUP BY st.staff_id, st.first_name, st.last_name
                """,
                must_hit_columns=[
                    "staff.first_name",
                    "staff.last_name",
                    "payment.staff_id",
                    "payment.payment_date",
                    "payment.amount",
                ],
                tags=["追问:省略"],
                note="只换月份，年份沿用 2005。",
            ),
            EvalCase(
                id="M3S07-3",
                query="这两个月放一起，他们各办理了多少笔租借？按租出时间算，名和姓同样分两列。",
                reference_sql="""
                    SELECT st.first_name, st.last_name, COUNT(*) AS rental_count
                    FROM rental r JOIN staff st ON r.staff_id = st.staff_id
                    WHERE substr(r.rental_date, 1, 7) IN ('2005-07', '2005-08')
                    GROUP BY st.staff_id, st.first_name, st.last_name
                """,
                must_hit_columns=["staff.first_name", "staff.last_name", "rental.staff_id", "rental.rental_date"],
                tags=["追问:跨轮", "追问:换角度"],
                note="“这两个月”把第 1、2 轮放在一起，每人一行；办理员工看租借记录上的员工，不是收款员工。",
            ),
            EvalCase(
                id="M3S07-4",
                query="办理笔数多的那位，他办理的这些租借里，最多的 3 个影片分类是什么？列出分类名称和笔数。",
                reference_sql="""
                    SELECT c.name, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN staff st ON r.staff_id = st.staff_id
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE st.first_name = 'Mike' AND st.last_name = 'Hillyer'
                      AND substr(r.rental_date, 1, 7) IN ('2005-07', '2005-08')
                    GROUP BY c.category_id, c.name
                    ORDER BY rental_count DESC LIMIT 3
                """,
                must_hit_columns=["category.name", "rental.staff_id", "rental.rental_date", "rental.inventory_id"],
                tags=["追问:依赖结果", "追问:加条件"],
                note="笔数多的是上一轮的 Mike Hillyer；“这些租借”沿用这两个月；第 3、4 名不并列。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M3S08",
        tags=["难度:中等"],
        note="未归还的租借：最多的分类、赔偿金额、门店分布，再看要赔最多的分类涉及哪些国家；主要考指代和跨轮的依赖结果。",
        turns=[
            EvalCase(
                id="M3S08-1",
                query="现在还有不少碟没还回来。这些未归还的租借集中在哪几类影片？给我笔数排前 3 的分类和对应笔数。",
                reference_sql="""
                    SELECT c.name, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE r.return_date IS NULL
                    GROUP BY c.category_id, c.name
                    ORDER BY rental_count DESC LIMIT 3
                """,
                must_hit_columns=["category.name", "rental.return_date", "rental.inventory_id"],
                note="归还时间为空就是没还；第 3、4 名不并列。",
            ),
            EvalCase(
                id="M3S08-2",
                query="这 3 个分类没还的拷贝如果都按赔偿价赔，分别要赔多少钱？金额保留两位小数。",
                reference_sql="""
                    SELECT c.name, ROUND(SUM(f.replacement_cost), 2) AS replacement_total
                    FROM rental r
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film f ON i.film_id = f.film_id
                    JOIN film_category fc ON f.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE r.return_date IS NULL AND c.name IN ('Animation', 'Action', 'Sports')
                    GROUP BY c.category_id, c.name
                """,
                must_hit_columns=["category.name", "rental.return_date", "film.replacement_cost"],
                tags=["追问:指代", "追问:换角度"],
                note="每笔没还的租借对应一张拷贝，按影片赔偿价合计，每个分类一行。",
            ),
            EvalCase(
                id="M3S08-3",
                query="这些没还的，按门店拆开分别有多少笔？列出分类名称、门店编号和笔数。",
                reference_sql="""
                    SELECT c.name, i.store_id, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    WHERE r.return_date IS NULL AND c.name IN ('Animation', 'Action', 'Sports')
                    GROUP BY c.category_id, c.name, i.store_id
                """,
                must_hit_columns=["category.name", "rental.return_date", "inventory.store_id"],
                tags=["追问:指代", "追问:换角度"],
                note="范围沿用这 3 个分类；门店按拷贝所在门店算，共 6 行。",
            ),
            EvalCase(
                id="M3S08-4",
                query="要赔钱最多的那个分类，这些没还的租借按客户所在国家分，各多少笔？",
                reference_sql="""
                    SELECT co.country, COUNT(*) AS rental_count
                    FROM rental r
                    JOIN inventory i ON r.inventory_id = i.inventory_id
                    JOIN film_category fc ON i.film_id = fc.film_id
                    JOIN category c ON fc.category_id = c.category_id
                    JOIN customer cu ON r.customer_id = cu.customer_id
                    JOIN address a ON cu.address_id = a.address_id
                    JOIN city ci ON a.city_id = ci.city_id
                    JOIN country co ON ci.country_id = co.country_id
                    WHERE r.return_date IS NULL AND c.name = 'Action'
                    GROUP BY co.country_id, co.country
                """,
                must_hit_columns=["country.country", "category.name", "rental.return_date", "rental.customer_id"],
                tags=["追问:跨轮", "追问:依赖结果"],
                note="赔偿金额在第 2 轮，最多的是 Action，不是第 1 轮笔数最多的分类。",
            ),
        ],
    ),
]


MULTITURN3_BANKS = {
    "ecommerce": MULTITURN3_ECOMMERCE_CASES,
    "chinook": MULTITURN3_CHINOOK_CASES,
    "sakila": MULTITURN3_SAKILA_CASES,
}
