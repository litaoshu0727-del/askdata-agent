"""
第二套多轮追问留出集：三个库（ecommerce、Chinook、Sakila），验证会话里的追问——指代、省略、加条件、换角度、
跨轮、依赖结果。由独立出题人在未见过被测系统表现和已有题目（包括第一套多轮题）的情况下编写。ecommerce 12 组 48 轮
（M2E01–M2E12，陷阱轮 2），Chinook 8 组 32 轮（M2C01–M2C08，陷阱轮 1），Sakila 8 组 32 轮（M2S01–M2S08，陷阱轮 1）。

**已用过两次，第二次之前照它的失败修过。**第一套多轮题已经照着它的失败修了三轮（短期记忆窗口、四处修复、改写器），分数不再是泛化证据；这一套
用来量这些修复在没见过的追问上还剩多少。这套题于 fd0876a 冻结并推送后第一次运行，每组 3 次，结果见 docs/实验记录.md
「第二套多轮追问留出集：修复在没见过的追问上」：

    版本                         第 1 轮       追问              整组全对
    fd0876a  冻结版              81/84         217/240（90%）    61/84
    修正 M2C08-1 之后            83/84         217/240（90%）    63/84
    再修两类共性错误             83/84         233/240（97%）    76/84

最后一行是照这套题和第一套的失败修的，不算泛化证据，涨幅大部分来源也没有量，见 docs/实验记录.md「两类共性错误：改写的用词和
规划的分组」。题目没有再改。

冻结之后修了一道可证明没法判分的题，其他题没动：M2C08-1 原来问"2025年每个季度的开票金额分别是多少？保留两位小数。"，
没规定季度怎么写。参考答案写 1–4，系统 3 次金额全对、写成 Q1 或 2025-Q1，判错。题面加了"季度用 1 到 4 表示"，参考 SQL
不变，这一组用同一份代码补跑 3 次。

出题规范是 eval/blind_materials/出题规范_多轮第二套.md，和第一套的规范只差三处：题号前缀、交付的文件名，以及第 2 条
判分规则里加了一句——问一批对象的数量、金额、次数时，写明是逐个列出还是合在一起。第一套的 M1E02-4、M1E10-2 没写，
参考答案按个拆开，系统给了合计，只能按一种理解判。材料（三份数据字典、三个库）和第一套出题时逐字节相同。

冻结前我没有读过题目：机械校验和去重由脚本（eval/blind_materials/check_holdout.py）完成，只输出题号和检查项；这一套
起去重也和已有的多轮题比（只比第 1 轮）。出题人的回报里不含题目内容。三轮修改：

    第一轮  13 组换第 1 轮：和第一套多轮题撞 6 组（其中 1 组问法相似度 1.00、2 组结果集相同），和单轮题库、探针撞
            7 组（其中 3 组结果集相同）；6 轮补写小数位；1 轮"指代"改标"跨轮"（它指的是更早、不超过 10 行的那一轮，
            不是上一轮）
    第二轮  ecommerce 3 组仍撞（2 组结果集和已有题相同、1 组问法像），再换
    第三轮  本套内一对第 1 轮开头相似（0.63），只改其中一轮的措辞，参考答案不变

之后去重为 0。同一个出题设置、同样的库，第一轮有 6 组的开头和第一套撞上，其中一组几乎逐字相同。

例外，如实记下：
- 三轮修改都没有用逐题哈希核对改动范围：前两轮没存快照；第三轮的快照比出题人写回晚了 9 秒，存下的已经是改后的版本。
  改动范围以出题人的回报为准（每轮回报都列了改了哪几组、哪些组没动），每轮之后三个库都重跑了机械校验和去重
- 出题人第二轮的回报里写了换上的三组第 1 轮各用了哪几类筛选条件（没有取值、问题和 SQL）
- 出题人的会话环境自动带了记忆索引、一个 git 仓库的状态快照、用户身份和环境信息，报告说没有据此出题；列出题目录时
  看到了上一级目录本身的权限和时间戳，没有看其内容
- 出题人在换题时自己另改了几轮的措辞或写法（消掉两种理解、去掉一处只用来取整的 ROUND），回报说参考答案不变

每一组在一个新会话里按顺序问，每一轮单独判分（eval/multiturn.py --bank multiturn2）。第一次运行：冻结时的 HEAD，
每组 3 次，最多 4 个进程（ecommerce 两份、chinook、sakila），每个进程放在独立的进程组里，ecommerce 的两个进程各用一份
自己的库。合并规则和第一套相同，在看任何一组的成败之前写定：一组有 3 次完整运行且没有中途崩的，保留首次运行的结果；
其余的组用同一份代码补跑完整的 3 次，用补跑结果替换。

候选路径的验证 SQL 在 eval/cases_multiturn2_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

多轮追问评测题（第二套）：ecommerce / chinook / sakila。

每组在一个新会话里按顺序问，每一轮单独判分；每一轮的 reference_sql 单独就能在对应库上执行。
"""

from eval.cases import EvalCase, MultiTurnCase

TRAP_SQL = "SELECT 1 WHERE 0"

# ---------------------------------------------------------------------------
# ecommerce
# ---------------------------------------------------------------------------

MULTITURN2_ECOMMERCE_CASES = [
    MultiTurnCase(
        id="M2E01",
        tags=["难度:中等"],
        note="5月28日–30日金卡会员的已付款订单（带支付方式）→ 其中退了款的退款情况 → 这两笔订单买了什么 → 追问优惠券明细（库里没有）。考日期区间+会员等级+付款状态的组合筛选、订单与支付/退款/明细的关联、指代和识别缺失。",
        turns=[
            EvalCase(
                id="M2E01-1",
                query="5月28日到30日（两头都算）这三天下单的订单里，金卡会员付过款的有哪几笔？列出订单号、店铺名称、订单状态、实付金额和支付方式。",
                reference_sql="""
SELECT o.order_id, s.shop_name, o.order_status, o.pay_amount, p.pay_channel
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN fact_payment p ON p.order_id = o.order_id
WHERE u.member_level = '金卡会员'
  AND date(o.create_time) BETWEEN '2024-05-28' AND '2024-05-30'
  AND o.pay_time IS NOT NULL
""",
                must_hit_columns=["dim_user.member_level", "fact_order.create_time", "fact_order.pay_amount", "fact_payment.pay_channel", "dim_shop.shop_name"],
                note="按下单日期 5月28日–30日、下单用户会员等级为金卡会员、付过款（pay_time 不为空，含已支付、已完成、已退款）筛选，共 5 笔；同期还有 1 笔待支付的不算。每笔订单恰有一条支付流水。",
            ),
            EvalCase(
                id="M2E01-2",
                query="这几笔里退了款的，每笔列出订单号、退款原因、退款金额和退款状态。",
                reference_sql="""
SELECT r.order_id, r.refund_reason, r.refund_amount, r.refund_status
FROM fact_refund r
WHERE r.order_id IN (50228, 50512, 50669, 50432, 50242)
""",
                must_hit_columns=["fact_refund.order_id", "fact_refund.refund_reason", "fact_refund.refund_amount", "fact_refund.refund_status"],
                tags=["追问:指代", "追问:加条件"],
                note="上一轮 5 笔中有退款记录的 2 笔（订单状态也都是已退款），逐笔列出。",
            ),
            EvalCase(
                id="M2E01-3",
                query="这两笔订单里各买了哪些商品、各几件？列出订单号、商品ID、商品名称和件数。",
                reference_sql="""
SELECT i.order_id, p.product_id, p.product_name, i.quantity
FROM fact_order_item i
JOIN dim_product p ON p.product_id = i.product_id
WHERE i.order_id IN (50669, 50432)
""",
                must_hit_columns=["fact_order_item.order_id", "fact_order_item.quantity", "dim_product.product_name"],
                tags=["追问:指代", "追问:依赖结果", "追问:换角度"],
                note="「这两笔订单」= 上一轮退了款的 50669、50432，共 6 个明细行；其中有两个同名不同ID的商品，所以要求带商品ID。",
            ),
            EvalCase(
                id="M2E01-4",
                query="这两笔订单当初各用了哪张优惠券？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里只有订单级、商品行级的优惠金额，没有优惠券维度（券名、券码、券面额都没有），无法回答用的是哪张券，应说明缺失。",
                expect_unanswerable=True,
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E02",
        tags=["难度:中等"],
        note="钻石会员消费 Top5 → 各自最近下单时间 → 第一名在各二级类目的花费 → 第二名同样问。考指代、跨轮引用排名、依赖结果、省略。",
        turns=[
            EvalCase(
                id="M2E02-1",
                query="钻石会员里，累计消费金额最高的5位用户是谁？各消费了多少，保留两位小数。",
                reference_sql="""
SELECT u.user_name, ROUND(d.total_pay_amount, 2) AS total_pay_amount
FROM dim_user u
JOIN dws_user_summary d ON d.user_id = u.user_id
WHERE u.member_level = '钻石会员'
ORDER BY total_pay_amount DESC
LIMIT 5
""",
                must_hit_columns=["dim_user.member_level", "dim_user.user_name", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
                note="消费按口径约定只算已付款订单的实付金额；用户汇总表累计实付与订单表按 pay_time 非空求和一致。第5名 47152.24，第6名 44387.84，无并列。",
            ),
            EvalCase(
                id="M2E02-2",
                query="他们各自最近一次下单是什么时候？",
                reference_sql="""
SELECT u.user_name, d.last_order_time
FROM dim_user u
JOIN dws_user_summary d ON d.user_id = u.user_id
WHERE u.user_id IN (10105, 10068, 10118, 10035, 10021)
""",
                must_hit_columns=["dim_user.user_name", ["dws_user_summary.last_order_time", "fact_order.create_time"]],
                tags=["追问:指代", "追问:换角度"],
                note="「他们」= 上一轮 5 位钻石会员。「下单」按下单时间、不限订单状态；汇总表最近下单时间与订单表 create_time 取最大一致。",
            ),
            EvalCase(
                id="M2E02-3",
                query="排第一的那位，在各个二级类目上分别花了多少钱？按订单实付金额算，保留两位小数。",
                reference_sql="""
SELECT c.category_name, ROUND(SUM(o.pay_amount), 2) AS pay_amount
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN dim_category c ON c.category_id = s.main_category_id
WHERE o.user_id = 10105
  AND o.pay_time IS NOT NULL
GROUP BY c.category_id, c.category_name
""",
                must_hit_columns=["dim_category.category_name", ["dim_shop.main_category_id", "dim_product.category_id"], "fact_order.pay_amount"],
                tags=["追问:依赖结果", "追问:跨轮"],
                note="「排第一的那位」指第 1 轮排名第一的用户10105（不是上一轮）。花钱只算已付款订单；一笔订单只属于一个二级类目，经店铺主营类目或经商品类目归类结果一致（后者需按订单去重）。题面写明按订单实付金额（含运费）。",
            ),
            EvalCase(
                id="M2E02-4",
                query="第二名呢？金额同样保留两位小数。",
                reference_sql="""
SELECT c.category_name, ROUND(SUM(o.pay_amount), 2) AS pay_amount
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN dim_category c ON c.category_id = s.main_category_id
WHERE o.user_id = 10068
  AND o.pay_time IS NOT NULL
GROUP BY c.category_id, c.category_name
""",
                must_hit_columns=["dim_category.category_name", ["dim_shop.main_category_id", "dim_product.category_id"], "fact_order.pay_amount"],
                tags=["追问:省略", "追问:依赖结果", "追问:跨轮"],
                note="第 1 轮排名第二的用户10068，问题沿用上一轮：各二级类目的订单实付金额，保留两位小数。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E03",
        tags=["难度:中等"],
        note="美的、海尔两个品牌里在售且标价高于3000元的商品 → 各自加购、收藏次数 → 加购最多那个的买家城市分布 → 加购最少那个同样问。考品牌+上架状态+价格的组合筛选、指代、依赖结果和省略。",
        turns=[
            EvalCase(
                id="M2E03-1",
                query="美的、海尔这两个品牌里，目前在售、而且标价高于3000元的商品有哪些？列出商品ID、品牌、商品名称和标价。",
                reference_sql="""
SELECT product_id, brand, product_name, list_price
FROM dim_product
WHERE brand IN ('美的', '海尔')
  AND shelf_status = '在售'
  AND list_price > 3000
""",
                must_hit_columns=["dim_product.brand", "dim_product.shelf_status", "dim_product.list_price"],
                note="两个品牌共 8 个商品，其中在售且标价严格高于 3000 的 5 个（没有正好 3000 的）。商品名有重名，要求带商品ID。",
            ),
            EvalCase(
                id="M2E03-2",
                query="它们各自被加购过多少次、收藏过多少次？",
                reference_sql="""
SELECT b.product_id,
       SUM(CASE WHEN b.behavior_type = '加购' THEN 1 ELSE 0 END) AS cart_cnt,
       SUM(CASE WHEN b.behavior_type = '收藏' THEN 1 ELSE 0 END) AS fav_cnt
FROM fact_user_behavior b
WHERE b.product_id IN (30030, 30060, 30015, 30021, 30045)
GROUP BY b.product_id
""",
                must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.product_id"],
                tags=["追问:指代", "追问:换角度"],
                note="「它们」= 上一轮 5 个商品，按行为记录数分别统计加购、收藏，5 个都有。加购最多 30021（17 次，次多 13），最少 30060（10 次，次少 11），都无并列；收藏最多有并列，所以后面不按收藏追问。",
            ),
            EvalCase(
                id="M2E03-3",
                query="其中被加购次数最多的那个，买过它的用户分布在哪些城市？各几人？",
                reference_sql="""
SELECT u.city, COUNT(DISTINCT o.user_id) AS buyer_cnt
FROM fact_order_item i
JOIN fact_order o ON o.order_id = i.order_id
JOIN dim_user u ON u.user_id = o.user_id
WHERE i.product_id = 30021
  AND o.pay_time IS NOT NULL
GROUP BY u.city
""",
                must_hit_columns=["fact_order_item.product_id", "dim_user.city", "fact_order.user_id"],
                tags=["追问:依赖结果", "追问:指代"],
                note="加购最多的是商品30021（美的 电饭煲 4L，鲜生自营店6）。「买过」按口径约定只算已付款订单，按下单用户所在城市去重计人数，9 个城市。",
            ),
            EvalCase(
                id="M2E03-4",
                query="加购次数最少的那个呢？",
                reference_sql="""
SELECT u.city, COUNT(DISTINCT o.user_id) AS buyer_cnt
FROM fact_order_item i
JOIN fact_order o ON o.order_id = i.order_id
JOIN dim_user u ON u.user_id = o.user_id
WHERE i.product_id = 30060
  AND o.pay_time IS NOT NULL
GROUP BY u.city
""",
                must_hit_columns=["fact_order_item.product_id", "dim_user.city", "fact_order.user_id"],
                tags=["追问:省略", "追问:依赖结果"],
                note="第 2 轮里加购最少的是商品30060（海尔 破壁机），沿用上一轮：已付款买家按城市去重计人数，10 个城市。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E04",
        tags=["难度:中等"],
        note="手机通讯类目的商品 → 各自销量 → 销量最高那个的加购人数 → 收藏人数。考指代、依赖结果、行为表的省略追问。",
        turns=[
            EvalCase(
                id="M2E04-1",
                query="「手机通讯」类目下有哪些商品？列出商品ID、商品名称和标价。",
                reference_sql="""
SELECT p.product_id, p.product_name, p.list_price
FROM dim_product p
JOIN dim_category c ON c.category_id = p.category_id
WHERE c.category_name = '手机通讯'
""",
                must_hit_columns=["dim_category.category_name", "dim_product.product_name", "dim_product.list_price"],
                note="共 8 个商品（不论上架状态）。商品名有重名（4 个「华为 快充充电器 67W」），所以要求带商品ID。",
            ),
            EvalCase(
                id="M2E04-2",
                query="这些商品各卖出了多少件？只算已付款的订单。",
                reference_sql="""
SELECT p.product_id, p.product_name, SUM(i.quantity) AS sold_qty
FROM dim_product p
JOIN dim_category c ON c.category_id = p.category_id
JOIN fact_order_item i ON i.product_id = p.product_id
JOIN fact_order o ON o.order_id = i.order_id
WHERE c.category_name = '手机通讯'
  AND o.pay_time IS NOT NULL
GROUP BY p.product_id, p.product_name
""",
                must_hit_columns=["fact_order_item.quantity", "fact_order_item.product_id"],
                tags=["追问:指代", "追问:换角度"],
                note="「这些商品」= 上一轮 8 个商品；销量按件数（数量求和），8 个都有销量。最高为 30049 华为 蓝牙耳机 52 件，次高 46，无并列。",
            ),
            EvalCase(
                id="M2E04-3",
                query="销量最高的那个，有多少个不同的用户加购过它？",
                reference_sql="""
SELECT COUNT(DISTINCT user_id) AS user_cnt
FROM fact_user_behavior
WHERE product_id = 30049
  AND behavior_type = '加购'
""",
                must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.user_id"],
                tags=["追问:指代", "追问:依赖结果"],
                note="销量最高的是商品30049（华为 蓝牙耳机）。按用户去重计数，结果 12。",
            ),
            EvalCase(
                id="M2E04-4",
                query="收藏过它的呢？",
                reference_sql="""
SELECT COUNT(DISTINCT user_id) AS user_cnt
FROM fact_user_behavior
WHERE product_id = 30049
  AND behavior_type = '收藏'
""",
                must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.user_id"],
                tags=["追问:省略"],
                note="同一商品，把行为从加购换成收藏，仍按不同用户计数，结果 2。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E05",
        tags=["难度:难"],
        note="商品质量问题的退款 → 按店铺类型拆 → 追问买家评分（库里没有）→ 回到店铺类型拆分、看旗舰店具体是哪几家。考省略、识别缺失、陷阱后跨轮回指。",
        turns=[
            EvalCase(
                id="M2E05-1",
                query="退款原因是「商品质量问题」的退款一共有多少笔、金额合计多少？不管退款有没有完成都算，保留两位小数。",
                reference_sql="""
SELECT COUNT(*) AS refund_cnt, ROUND(SUM(refund_amount), 2) AS refund_amount
FROM fact_refund
WHERE refund_reason = '商品质量问题'
""",
                must_hit_columns=["fact_refund.refund_reason", "fact_refund.refund_amount"],
                note="退款成功、退款中都算：22 笔，249430.27。",
            ),
            EvalCase(
                id="M2E05-2",
                query="按店铺类型拆开看呢？金额同样保留两位小数。",
                reference_sql="""
SELECT s.shop_type, COUNT(*) AS refund_cnt, ROUND(SUM(r.refund_amount), 2) AS refund_amount
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE r.refund_reason = '商品质量问题'
GROUP BY s.shop_type
""",
                must_hit_columns=["fact_refund.refund_reason", "dim_shop.shop_type"],
                tags=["追问:省略", "追问:换角度"],
                note="沿用上一轮的范围和两项指标（笔数、金额），按退款订单所属店铺的店铺类型分组，4 种类型都有。",
            ),
            EvalCase(
                id="M2E05-3",
                query="这些出质量问题的商品，买家给打的评分各是多少？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里没有商品评价、评分数据（行为表只有浏览、加购、收藏），无法回答，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M2E05-4",
                query="回到按店铺类型拆的那个结果：旗舰店那部分具体是哪几家店？各几笔、金额多少，保留两位小数。",
                reference_sql="""
SELECT s.shop_name, COUNT(*) AS refund_cnt, ROUND(SUM(r.refund_amount), 2) AS refund_amount
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE r.refund_reason = '商品质量问题'
  AND s.shop_type = '旗舰店'
GROUP BY s.shop_id, s.shop_name
""",
                must_hit_columns=["fact_refund.refund_reason", "dim_shop.shop_type", "dim_shop.shop_name"],
                tags=["追问:跨轮", "追问:加条件"],
                note="指回第 2 轮：商品质量问题退款里店铺类型为旗舰店的 14 笔，按店铺列出（8 家）。注意店铺名里带「自营店」「专营店」的也可能是旗舰店类型，要按店铺类型字段判断。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E06",
        tags=["难度:中等"],
        note="广东用户按城市 → 深圳消费前三 → 他们的浏览情况 → 换成广州前三看同样两项。考加条件、指代、把第 2 轮的排名和第 3 轮的指标组合起来的跨轮省略。",
        turns=[
            EvalCase(
                id="M2E06-1",
                query="广东的用户按城市分，各城市有多少人、累计消费合计多少？保留两位小数。",
                reference_sql="""
SELECT u.city, COUNT(*) AS user_cnt, ROUND(SUM(d.total_pay_amount), 2) AS total_pay_amount
FROM dim_user u
JOIN dws_user_summary d ON d.user_id = u.user_id
WHERE u.province = '广东'
GROUP BY u.city
""",
                must_hit_columns=["dim_user.province", "dim_user.city", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
                note="用户所在省份为广东：广州 21 人、深圳 18 人。消费按口径约定只算已付款订单实付；汇总表与订单表左连接求和一致。",
            ),
            EvalCase(
                id="M2E06-2",
                query="深圳的这些用户里，消费最多的3位是谁？各花了多少，保留两位小数。",
                reference_sql="""
SELECT u.user_name, ROUND(d.total_pay_amount, 2) AS total_pay_amount
FROM dim_user u
JOIN dws_user_summary d ON d.user_id = u.user_id
WHERE u.city = '深圳'
ORDER BY total_pay_amount DESC
LIMIT 3
""",
                must_hit_columns=["dim_user.city", "dim_user.user_name", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
                tags=["追问:加条件", "追问:指代"],
                note="收窄到用户所在城市为深圳；第3名 77958.27，第4名 57473.63，无并列。",
            ),
            EvalCase(
                id="M2E06-3",
                query="这三个人分别浏览了多少次商品、浏览时累计停留了多少秒？",
                reference_sql="""
SELECT u.user_name, COUNT(*) AS browse_cnt, SUM(b.stay_seconds) AS stay_seconds
FROM fact_user_behavior b
JOIN dim_user u ON u.user_id = b.user_id
WHERE b.behavior_type = '浏览'
  AND b.user_id IN (10057, 10132, 10166)
GROUP BY u.user_id, u.user_name
""",
                must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.stay_seconds"],
                tags=["追问:指代", "追问:换角度"],
                note="「这三个人」= 用户10057、10132、10166；只算浏览行为的次数和停留秒数，每人分别列出。",
            ),
            EvalCase(
                id="M2E06-4",
                query="广州那边消费前三的三位呢？同样看这两项。",
                reference_sql="""
SELECT u.user_name, COUNT(*) AS browse_cnt, SUM(b.stay_seconds) AS stay_seconds
FROM fact_user_behavior b
JOIN dim_user u ON u.user_id = b.user_id
WHERE b.behavior_type = '浏览'
  AND b.user_id IN (
      SELECT d.user_id
      FROM dws_user_summary d
      JOIN dim_user u2 ON u2.user_id = d.user_id
      WHERE u2.city = '广州'
      ORDER BY d.total_pay_amount DESC
      LIMIT 3
  )
GROUP BY u.user_id, u.user_name
""",
                must_hit_columns=["dim_user.city", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"], "fact_user_behavior.behavior_type", "fact_user_behavior.stay_seconds"],
                tags=["追问:省略", "追问:跨轮"],
                note="「消费前三」沿用第 2 轮的排名口径，城市换成广州（用户10157、10083、10068，第3名 74066.62 与第4名 70072.95 不并列）；「这两项」= 第 3 轮的浏览次数和浏览停留秒数。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E07",
        tags=["难度:中等"],
        note="5月1日–3日直播间下单后被取消的订单 → 下单用户及会员等级 → 这几位用户 5 月付过款的订单 → 换成小程序渠道同样这三天被取消的订单。考日期区间+渠道+状态的组合筛选、指代、跨轮省略。",
        turns=[
            EvalCase(
                id="M2E07-1",
                query="直播间渠道里，哪些订单是五一那三天（1日、2日、3日）下的、最后又取消了？给我订单号、对应的店铺和订单商品总金额。",
                reference_sql="""
SELECT o.order_id, s.shop_name, o.order_amount
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE o.channel = '直播间'
  AND o.order_status = '已取消'
  AND date(o.create_time) BETWEEN '2024-05-01' AND '2024-05-03'
""",
                must_hit_columns=["fact_order.channel", "fact_order.order_status", "fact_order.create_time", "fact_order.order_amount"],
                note="按下单日期、下单渠道直播间、订单状态已取消筛选，共 4 笔。订单商品总金额即按标价算的商品总额（未扣优惠、未加运费）。",
            ),
            EvalCase(
                id="M2E07-2",
                query="下这几笔订单的用户分别是谁、什么会员等级？",
                reference_sql="""
SELECT u.user_name, u.member_level
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.order_id IN (50204, 50236, 50418, 50640)
""",
                must_hit_columns=["fact_order.user_id", "dim_user.user_name", "dim_user.member_level"],
                tags=["追问:指代", "追问:换角度"],
                note="4 笔订单对应 4 位不同用户，逐个列出。",
            ),
            EvalCase(
                id="M2E07-3",
                query="这几位用户5月里付过款的订单各有几笔？实付金额各自合计多少，保留两位小数。",
                reference_sql="""
SELECT u.user_name, COUNT(*) AS paid_order_cnt, ROUND(SUM(o.pay_amount), 2) AS pay_amount
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.user_id IN (10048, 10016, 10115, 10181)
  AND o.pay_time IS NOT NULL
GROUP BY u.user_id, u.user_name
""",
                must_hit_columns=["fact_order.user_id", "fact_order.pay_amount"],
                tags=["追问:指代", "追问:换角度"],
                note="「这几位用户」= 上一轮 4 位；付过款按 pay_time 不为空（含已退款），每人一行，4 位都有已付款订单。",
            ),
            EvalCase(
                id="M2E07-4",
                query="换成小程序渠道，同样是这三天下单后被取消的订单呢？",
                reference_sql="""
SELECT o.order_id, s.shop_name, o.order_amount
FROM fact_order o
JOIN dim_shop s ON s.shop_id = o.shop_id
WHERE o.channel = '小程序'
  AND o.order_status = '已取消'
  AND date(o.create_time) BETWEEN '2024-05-01' AND '2024-05-03'
""",
                must_hit_columns=["fact_order.channel", "fact_order.order_status", "fact_order.create_time"],
                tags=["追问:省略", "追问:跨轮"],
                note="指回第 1 轮的问法（订单号、店铺名称、订单商品总金额），只把下单渠道换成小程序：1 笔。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E08",
        tags=["难度:中等"],
        note="浏览最多的 5 个商品 → 加购次数 → 销量 → 销量最少那个所在店铺的订单数。考连续指代和换指标，最后一轮依赖结果跨到店铺。",
        turns=[
            EvalCase(
                id="M2E08-1",
                query="被浏览次数最多的5个商品是哪几个？列出商品ID、商品名称和浏览次数。",
                reference_sql="""
SELECT p.product_id, p.product_name, COUNT(*) AS browse_cnt
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
WHERE b.behavior_type = '浏览'
GROUP BY p.product_id, p.product_name
ORDER BY browse_cnt DESC
LIMIT 5
""",
                must_hit_columns=["fact_user_behavior.behavior_type", "dim_product.product_name"],
                note="按浏览行为记录数计。第5名 45 次，第6名 43 次，无并列。有两个同名「华为 快充充电器 67W」，所以要求带商品ID。",
            ),
            EvalCase(
                id="M2E08-2",
                query="它们各自被加购了多少次？",
                reference_sql="""
SELECT p.product_id, p.product_name, COUNT(*) AS cart_cnt
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
WHERE b.behavior_type = '加购'
  AND b.product_id IN (30018, 30019, 30004, 30005, 30011)
GROUP BY p.product_id, p.product_name
""",
                must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.product_id"],
                tags=["追问:指代", "追问:换角度"],
                note="「它们」= 上一轮 5 个商品；按加购记录数计，5 个都有。",
            ),
            EvalCase(
                id="M2E08-3",
                query="这5个商品分别卖出了多少件？只算已付款的订单。",
                reference_sql="""
SELECT p.product_id, p.product_name, SUM(i.quantity) AS sold_qty
FROM fact_order_item i
JOIN fact_order o ON o.order_id = i.order_id
JOIN dim_product p ON p.product_id = i.product_id
WHERE i.product_id IN (30018, 30019, 30004, 30005, 30011)
  AND o.pay_time IS NOT NULL
GROUP BY p.product_id, p.product_name
""",
                must_hit_columns=["fact_order_item.quantity", "fact_order_item.product_id"],
                tags=["追问:指代", "追问:换角度"],
                note="销量按件数。最少的是 30018 阿道夫 头皮精华 37 件，次少 38 件，无并列。",
            ),
            EvalCase(
                id="M2E08-4",
                query="卖得最少的那个是哪家店铺的？那家店一共有多少笔订单？",
                reference_sql="""
SELECT s.shop_name, COUNT(o.order_id) AS order_cnt
FROM dim_shop s
JOIN fact_order o ON o.shop_id = s.shop_id
WHERE s.shop_id = (SELECT shop_id FROM dim_product WHERE product_id = 30018)
GROUP BY s.shop_id, s.shop_name
""",
                must_hit_columns=["dim_product.shop_id", "dim_shop.shop_name", ["fact_order.order_id", "dws_shop_daily.order_count"]],
                tags=["追问:指代", "追问:依赖结果"],
                note="商品30018 属于京选自营店3。订单数按口径约定不加状态条件，算全部订单：39 笔。店铺日汇总订单量求和一致。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E09",
        tags=["难度:中等"],
        note="50以上年龄段按性别的人数 → 按性别的累计消费 → 女性付过款订单最多的二级类目 → 男性同样问。考年龄段与性别画像、指代、加条件和省略。",
        turns=[
            EvalCase(
                id="M2E09-1",
                query="年龄段为「50以上」的用户，男女各有多少人？",
                reference_sql="""
SELECT gender, COUNT(*) AS user_cnt
FROM dim_user
WHERE age_group = '50以上'
GROUP BY gender
""",
                must_hit_columns=["dim_user.age_group", "dim_user.gender"],
                note="女 13 人、男 11 人。",
            ),
            EvalCase(
                id="M2E09-2",
                query="按性别分别算，他们一共消费了多少钱？保留两位小数。",
                reference_sql="""
SELECT u.gender, ROUND(SUM(d.total_pay_amount), 2) AS total_pay_amount
FROM dim_user u
JOIN dws_user_summary d ON d.user_id = u.user_id
WHERE u.age_group = '50以上'
GROUP BY u.gender
""",
                must_hit_columns=["dim_user.gender", ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
                tags=["追问:指代", "追问:换角度"],
                note="「他们」= 上一轮 24 位 50以上用户，每个性别一行合计。消费按口径约定只算已付款订单实付；汇总表与订单表求和一致。",
            ),
            EvalCase(
                id="M2E09-3",
                query="其中女性用户付过款的订单，最多的二级类目是哪个？有几笔？",
                reference_sql="""
SELECT c.category_name, COUNT(*) AS order_cnt
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN dim_category c ON c.category_id = s.main_category_id
WHERE u.age_group = '50以上'
  AND u.gender = '女'
  AND o.pay_time IS NOT NULL
GROUP BY c.category_id, c.category_name
ORDER BY order_cnt DESC
LIMIT 1
""",
                must_hit_columns=["dim_user.gender", "dim_category.category_name", ["dim_shop.main_category_id", "dim_product.category_id"]],
                tags=["追问:加条件", "追问:换角度"],
                note="50以上女性用户的已付款订单按二级类目计订单笔数（一笔订单只属于一个二级类目）：家用电器 6 笔，第二 5 笔，无并列。经店铺主营类目或经商品类目（按订单去重）结果一致。",
            ),
            EvalCase(
                id="M2E09-4",
                query="男性的呢？",
                reference_sql="""
SELECT c.category_name, COUNT(*) AS order_cnt
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
JOIN dim_shop s ON s.shop_id = o.shop_id
JOIN dim_category c ON c.category_id = s.main_category_id
WHERE u.age_group = '50以上'
  AND u.gender = '男'
  AND o.pay_time IS NOT NULL
GROUP BY c.category_id, c.category_name
ORDER BY order_cnt DESC
LIMIT 1
""",
                must_hit_columns=["dim_user.gender", "dim_category.category_name", ["dim_shop.main_category_id", "dim_product.category_id"]],
                tags=["追问:省略"],
                note="只把性别换成男，仍限 50以上：家用电器 9 笔，第二 6 笔，无并列。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E10",
        tags=["难度:难"],
        note="退款金额最多的 3 位用户 → 每笔退款的原因和状态 → 其中退款成功的处理天数 → 第一名的累计实付。考指代、加条件、跨轮依赖结果。",
        turns=[
            EvalCase(
                id="M2E10-1",
                query="退款金额最多的3位用户是谁？各自的退款金额是多少？退款中的也算，保留两位小数。",
                reference_sql="""
SELECT u.user_name, ROUND(SUM(r.refund_amount), 2) AS refund_amount
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
JOIN dim_user u ON u.user_id = o.user_id
GROUP BY u.user_id, u.user_name
ORDER BY refund_amount DESC
LIMIT 3
""",
                must_hit_columns=["fact_refund.refund_amount", "fact_order.user_id", "dim_user.user_name"],
                note="退款按订单归到下单用户，退款中、退款成功都算。第3名 29026.63，第4名 27941.92，无并列。结果：用户10156、10173、10088。",
            ),
            EvalCase(
                id="M2E10-2",
                query="他们的这几笔退款分别是什么原因、现在什么状态？每笔列出用户、订单号、退款原因和退款状态。",
                reference_sql="""
SELECT u.user_name, r.order_id, r.refund_reason, r.refund_status
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.user_id IN (10156, 10173, 10088)
""",
                must_hit_columns=["fact_refund.refund_reason", "fact_refund.refund_status"],
                tags=["追问:指代", "追问:换角度"],
                note="「他们」= 上一轮 3 位用户，共 5 笔退款，逐笔列出。",
            ),
            EvalCase(
                id="M2E10-3",
                query="其中已经「退款成功」的，从申请到退款完成各用了几天？列出订单号和天数。",
                reference_sql="""
SELECT r.order_id, (strftime('%s', r.finish_time) - strftime('%s', r.apply_time)) / 86400 AS days
FROM fact_refund r
JOIN fact_order o ON o.order_id = r.order_id
WHERE o.user_id IN (10156, 10173, 10088)
  AND r.refund_status = '退款成功'
""",
                must_hit_columns=["fact_refund.refund_status", "fact_refund.apply_time", "fact_refund.finish_time"],
                tags=["追问:加条件", "追问:指代"],
                note="上一轮 5 笔中退款成功的 4 笔。这几笔申请与完成的时分完全相同，按精确时长或按日期相减天数都是整数且一致（2、1、1、4）。",
            ),
            EvalCase(
                id="M2E10-4",
                query="退款金额排第一的那位，他所有付过款的订单实付金额一共多少？保留两位小数。",
                reference_sql="""
SELECT ROUND(total_pay_amount, 2) AS total_pay_amount
FROM dws_user_summary
WHERE user_id = 10156
""",
                must_hit_columns=[["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
                tags=["追问:依赖结果", "追问:跨轮"],
                note="第 1 轮排第一的是用户10156。付过款 = 已付款订单（含已退款状态），合计 87883.52；用户汇总表与订单表求和一致。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E11",
        tags=["难度:中等"],
        note="非正常营业的店铺 → 其中仍在售的商品 → 这些商品被收藏次数 → 回到两家店看付款买家的注册渠道。考指代、加条件、跨轮和去重口径。",
        turns=[
            EvalCase(
                id="M2E11-1",
                query="目前不是「正常营业」状态的店铺有哪几家？列出店铺名称、营业状态和各自的已付款订单数。",
                reference_sql="""
SELECT s.shop_name, s.shop_status, COUNT(o.order_id) AS paid_order_cnt
FROM dim_shop s
JOIN fact_order o ON o.shop_id = s.shop_id
WHERE s.shop_status <> '正常营业'
  AND o.pay_time IS NOT NULL
GROUP BY s.shop_id, s.shop_name, s.shop_status
""",
                must_hit_columns=["dim_shop.shop_status", "dim_shop.shop_name"],
                note="两家：鲜生自营店6（休假中）、旗舰自营店12（已关店）。已付款按 pay_time 不为空。",
            ),
            EvalCase(
                id="M2E11-2",
                query="这两家店里，还处于「在售」状态的商品有哪些？列出店铺名称、商品ID和商品名称。",
                reference_sql="""
SELECT s.shop_name, p.product_id, p.product_name
FROM dim_product p
JOIN dim_shop s ON s.shop_id = p.shop_id
WHERE s.shop_status <> '正常营业'
  AND p.shelf_status = '在售'
""",
                must_hit_columns=["dim_product.shelf_status", "dim_product.shop_id", "dim_product.product_name"],
                tags=["追问:指代", "追问:加条件"],
                note="「这两家店」= 上一轮两家；上架状态为在售的共 5 个商品（不含已下架、预售）。",
            ),
            EvalCase(
                id="M2E11-3",
                query="这几个商品各被收藏过多少次？",
                reference_sql="""
SELECT p.product_id, p.product_name, COUNT(*) AS fav_cnt
FROM fact_user_behavior b
JOIN dim_product p ON p.product_id = b.product_id
WHERE b.behavior_type = '收藏'
  AND b.product_id IN (30012, 30021, 30027, 30036, 30051)
GROUP BY p.product_id, p.product_name
""",
                must_hit_columns=["fact_user_behavior.behavior_type", "fact_user_behavior.product_id"],
                tags=["追问:指代", "追问:换角度"],
                note="「这几个商品」= 上一轮 5 个在售商品；按收藏记录数计，5 个都有。",
            ),
            EvalCase(
                id="M2E11-4",
                query="回到第一个问题那两家店：在这两家店付过款的买家，按注册渠道分各有几个人？两家合在一起算，同一个人只算一次。",
                reference_sql="""
SELECT u.register_channel, COUNT(DISTINCT o.user_id) AS buyer_cnt
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.shop_id IN (2006, 2012)
  AND o.pay_time IS NOT NULL
GROUP BY u.register_channel
""",
                must_hit_columns=["dim_user.register_channel", "fact_order.user_id"],
                tags=["追问:跨轮", "追问:指代", "追问:换角度"],
                note="两家店（2006、2012）已付款订单的下单用户，合并去重后按用户注册渠道分组。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2E12",
        tags=["难度:中等"],
        note="2024 年注册的新用户按注册渠道 → 小程序来的那几位是谁 → 他们的下单和实付 → 回到全部新用户看各渠道加购次数。考注册时间筛选、指代、加条件和跨轮。",
        turns=[
            EvalCase(
                id="M2E12-1",
                query="2024年注册的用户，按注册渠道分各有几位？",
                reference_sql="""
SELECT register_channel, COUNT(*) AS user_cnt
FROM dim_user
WHERE register_time >= '2024-01-01' AND register_time < '2025-01-01'
GROUP BY register_channel
""",
                must_hit_columns=["dim_user.register_time", "dim_user.register_channel"],
                note="按注册日期在 2024 年筛选（共 19 位，最晚 2024-03-27），4 个渠道都有。",
            ),
            EvalCase(
                id="M2E12-2",
                query="其中通过小程序注册的那几位，分别是谁、在哪个城市、现在是什么会员等级？",
                reference_sql="""
SELECT user_name, city, member_level
FROM dim_user
WHERE register_time >= '2024-01-01' AND register_time < '2025-01-01'
  AND register_channel = '小程序'
""",
                must_hit_columns=["dim_user.register_channel", "dim_user.user_name", "dim_user.city", "dim_user.member_level"],
                tags=["追问:加条件", "追问:指代"],
                note="上一轮 2024 年新用户里注册渠道为小程序的 7 位。",
            ),
            EvalCase(
                id="M2E12-3",
                query="他们各自一共下过几笔订单、实付金额多少？保留两位小数。",
                reference_sql="""
SELECT u.user_name, d.total_order_count, ROUND(d.total_pay_amount, 2) AS total_pay_amount
FROM dim_user u
JOIN dws_user_summary d ON d.user_id = u.user_id
WHERE u.register_time >= '2024-01-01' AND u.register_time < '2025-01-01'
  AND u.register_channel = '小程序'
""",
                must_hit_columns=[["dws_user_summary.total_order_count", "fact_order.order_id"], ["dws_user_summary.total_pay_amount", "fact_order.pay_amount"]],
                tags=["追问:指代", "追问:换角度"],
                note="「他们」= 上一轮 7 位。订单笔数不加状态条件；实付金额只算已付款订单。7 位都有订单；汇总表与订单表聚合一致。",
            ),
            EvalCase(
                id="M2E12-4",
                query="回到第一个问题的那些新用户，按注册渠道分，各加购过多少次商品？",
                reference_sql="""
SELECT u.register_channel, COUNT(*) AS cart_cnt
FROM fact_user_behavior b
JOIN dim_user u ON u.user_id = b.user_id
WHERE u.register_time >= '2024-01-01' AND u.register_time < '2025-01-01'
  AND b.behavior_type = '加购'
GROUP BY u.register_channel
""",
                must_hit_columns=["dim_user.register_channel", "fact_user_behavior.behavior_type"],
                tags=["追问:跨轮", "追问:换角度"],
                note="指回第 1 轮的全部 19 位 2024 年新用户（不是上一轮的 7 位），按注册渠道统计加购行为记录数，4 个渠道都有。",
            ),
        ],
    ),
]

# ---------------------------------------------------------------------------
# chinook
# ---------------------------------------------------------------------------

MULTITURN2_CHINOOK_CASES = [
    MultiTurnCase(
        id="M2C01",
        tags=["难度:中等"],
        note="歌名与专辑名相同的曲目按流派 → 最多那个流派的销量和销售额 → 追问排行榜名次（库里没有）→ 回到第 1 轮换成按艺术家。考曲目与专辑名比较、依赖结果、识别缺失、陷阱后跨轮。",
        turns=[
            EvalCase(
                id="M2C01-1",
                query="歌名和所在专辑名一字不差（连大小写都一样）的曲目，按流派分各有几首？",
                reference_sql="""
SELECT g.Name, COUNT(*) AS track_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Genre g ON g.GenreId = t.GenreId
WHERE t.Name = al.Title
GROUP BY g.GenreId, g.Name
""",
                must_hit_columns=["Track.Name", "Album.Title", "Genre.Name"],
                note="曲目名与所属专辑名完全相同（区分大小写）的共 50 首，10 个流派；题面写明大小写也要一致，是因为有 1 首 Rock 曲目只差大小写，忽略大小写会变成 51 首、Rock 17 首。按题面口径 Rock 16 首最多，Metal 12 首第二。",
            ),
            EvalCase(
                id="M2C01-2",
                query="其中最多的那个流派，这些曲目一共卖出去多少份、销售额多少？保留两位小数。",
                reference_sql="""
SELECT COUNT(*) AS sold_cnt, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS sales
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
WHERE t.Name = al.Title
  AND t.GenreId = 1
""",
                must_hit_columns=["Track.Name", "Album.Title", "InvoiceLine.UnitPrice"],
                tags=["追问:依赖结果", "追问:加条件"],
                note="最多的流派是 Rock（GenreId 1）；这 16 首合在一起的销量和成交金额（13 份、12.87）。",
            ),
            EvalCase(
                id="M2C01-3",
                query="这些歌当年在排行榜上最高排到第几名？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里没有任何排行榜、榜单名次数据，应说明缺失，不能拿销量排名代替。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M2C01-4",
                query="回到第一个问题，换成按艺术家分，这类曲目最多的两位艺术家是谁？各几首？",
                reference_sql="""
SELECT ar.Name, COUNT(*) AS track_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
WHERE t.Name = al.Title
GROUP BY ar.ArtistId, ar.Name
ORDER BY track_cnt DESC
LIMIT 2
""",
                must_hit_columns=["Track.Name", "Album.Title", "Artist.Name"],
                tags=["追问:跨轮", "追问:省略", "追问:换角度"],
                note="范围回到第 1 轮的 50 首（不限流派，沿用区分大小写的口径），按专辑所属艺术家分组：Iron Maiden 7、Metallica 4，第3名 3 首，无并列。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2C02",
        tags=["难度:中等"],
        note="作曲署名含 Chris Cornell 的曲目出自哪些艺术家 → 各自销量 → 卖得最多那位的销售国家 → 换成 Audioslave。考作曲者与艺术家的区分（作曲者是自由文本）、指代、依赖结果、省略。",
        turns=[
            EvalCase(
                id="M2C02-1",
                query="作曲者署名里出现「Chris Cornell」这个全名的曲目，分别出自哪些艺术家？各几首？",
                reference_sql="""
SELECT ar.Name, COUNT(*) AS track_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
WHERE t.Composer LIKE '%Chris Cornell%'
GROUP BY ar.ArtistId, ar.Name
""",
                must_hit_columns=["Track.Composer", "Artist.Name", "Album.ArtistId"],
                note="作曲者是自由文本，署名里包含全名 Chris Cornell（含与他人合写）的 43 首，分属 Audioslave、Soundgarden、Chris Cornell 三位艺术家；不能只按艺术家名 Chris Cornell 找。另有 12 首 Audioslave 曲目只署姓「Cornell」，题面限定全名，所以不算。",
            ),
            EvalCase(
                id="M2C02-2",
                query="这些曲目按艺术家分，各卖出去多少份？",
                reference_sql="""
SELECT ar.Name, COUNT(*) AS sold_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
WHERE t.Composer LIKE '%Chris Cornell%'
GROUP BY ar.ArtistId, ar.Name
""",
                must_hit_columns=["Track.Composer", "InvoiceLine.TrackId"],
                tags=["追问:指代", "追问:换角度"],
                note="「这些曲目」= 上一轮 43 首；三位艺术家都有销量：Soundgarden 14 最多，Audioslave 6，Chris Cornell 3。",
            ),
            EvalCase(
                id="M2C02-3",
                query="卖得最多的那位艺术家，这些曲目卖到了哪些国家？各几份？",
                reference_sql="""
SELECT i.BillingCountry, COUNT(*) AS sold_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
JOIN Invoice i ON i.InvoiceId = il.InvoiceId
WHERE t.Composer LIKE '%Chris Cornell%'
  AND al.ArtistId = 132
GROUP BY i.BillingCountry
""",
                must_hit_columns=["Track.Composer", ["Invoice.BillingCountry", "Customer.Country"]],
                tags=["追问:依赖结果", "追问:指代"],
                note="卖得最多的是 Soundgarden（ArtistId 132），只看它名下作曲含 Chris Cornell 的曲目，按国家计份数（4 个国家）。开票国家与客户国家在库中逐张一致。",
            ),
            EvalCase(
                id="M2C02-4",
                query="Audioslave 的呢？",
                reference_sql="""
SELECT i.BillingCountry, COUNT(*) AS sold_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
JOIN Invoice i ON i.InvoiceId = il.InvoiceId
WHERE t.Composer LIKE '%Chris Cornell%'
  AND al.ArtistId = 8
GROUP BY i.BillingCountry
""",
                must_hit_columns=["Track.Composer", ["Invoice.BillingCountry", "Customer.Country"]],
                tags=["追问:省略"],
                note="只把艺术家换成 Audioslave（ArtistId 8），仍限作曲含 Chris Cornell 的曲目，按国家计份数（3 个国家）。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2C03",
        tags=["难度:中等"],
        note="用 gmail.com 邮箱的客户 → 各自最近一次购买日期 → 最晚那位那次买的曲目按流派 → 那次买的视频花了多少。考按邮箱筛选、指代、依赖结果、加条件。",
        turns=[
            EvalCase(
                id="M2C03-1",
                query="用 gmail.com 邮箱的客户分布在哪些国家？各几位？",
                reference_sql="""
SELECT Country, COUNT(*) AS customer_cnt
FROM Customer
WHERE Email LIKE '%@gmail.com'
GROUP BY Country
""",
                must_hit_columns=["Customer.Email", "Customer.Country"],
                note="客户邮箱域名为 gmail.com 的共 8 位，按客户登记国家分组 5 个国家（员工邮箱都是公司域名，不涉及）。",
            ),
            EvalCase(
                id="M2C03-2",
                query="这几位客户各自最近一次买东西是哪天？列出姓名和日期。",
                reference_sql="""
SELECT c.FirstName, c.LastName, MAX(i.InvoiceDate) AS last_invoice_date
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
WHERE c.Email LIKE '%@gmail.com'
GROUP BY c.CustomerId, c.FirstName, c.LastName
""",
                must_hit_columns=["Invoice.InvoiceDate", "Invoice.CustomerId"],
                tags=["追问:指代", "追问:换角度"],
                note="「这几位客户」= 上一轮统计的 8 位 gmail.com 客户，每人一行；最近一次 = 开票日期最大值。最晚的是 Helena Holý（2025-11-13），第二晚 2025-09-20，无并列。",
            ),
            EvalCase(
                id="M2C03-3",
                query="最近一次买得最晚的那位，那次买的曲目按流派分各几首？",
                reference_sql="""
SELECT g.Name, COUNT(*) AS track_cnt
FROM InvoiceLine il
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
WHERE il.InvoiceId = 404
GROUP BY g.GenreId, g.Name
""",
                must_hit_columns=["InvoiceLine.InvoiceId", "Genre.Name"],
                tags=["追问:依赖结果", "追问:指代"],
                note="Helena Holý 在 2025-11-13 只有一张发票（InvoiceId 404，14 首），按流派计数 5 个流派。",
            ),
            EvalCase(
                id="M2C03-4",
                query="那次买的曲目里，视频格式的一共花了多少钱？保留两位小数。",
                reference_sql="""
SELECT ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS amount
FROM InvoiceLine il
JOIN Track t ON t.TrackId = il.TrackId
WHERE il.InvoiceId = 404
  AND t.MediaTypeId = 3
""",
                must_hit_columns=["Track.MediaTypeId", "InvoiceLine.UnitPrice"],
                tags=["追问:加条件", "追问:指代"],
                note="同一张发票 404 里媒体格式为视频（Protected MPEG-4 video file，唯一的视频格式）的 12 首，按成交单价合计 23.88。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2C04",
        tags=["难度:中等"],
        note="曲目最多的 4 位艺术家 → 各自卖出份数 → 卖得最少那位最畅销的专辑 → 这张专辑的平均时长。考依赖结果和单位换算。",
        turns=[
            EvalCase(
                id="M2C04-1",
                query="曲库里曲目数最多的4位艺术家是谁？各有多少首曲目？",
                reference_sql="""
SELECT ar.Name, COUNT(*) AS track_cnt
FROM Track t
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
GROUP BY ar.ArtistId, ar.Name
ORDER BY track_cnt DESC
LIMIT 4
""",
                must_hit_columns=["Artist.Name", "Album.ArtistId", "Track.AlbumId"],
                note="Iron Maiden 213、U2 135、Led Zeppelin 114、Metallica 112；第5名 92（两位并列），所以取前 4，第4与第5不并列。",
            ),
            EvalCase(
                id="M2C04-2",
                query="他们的曲目各卖出去多少份？",
                reference_sql="""
SELECT ar.Name, COUNT(il.InvoiceLineId) AS sold_cnt
FROM Artist ar
JOIN Album al ON al.ArtistId = ar.ArtistId
JOIN Track t ON t.AlbumId = al.AlbumId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
WHERE ar.ArtistId IN (90, 150, 22, 50)
GROUP BY ar.ArtistId, ar.Name
""",
                must_hit_columns=["InvoiceLine.TrackId", "Album.ArtistId"],
                tags=["追问:指代", "追问:换角度"],
                note="「他们」= 上一轮 4 位艺术家，按艺术家分别统计。Led Zeppelin 87 最少，次少 Metallica 91。",
            ),
            EvalCase(
                id="M2C04-3",
                query="卖得最少的那位，他哪张专辑卖出去的份数最多？卖了多少份？",
                reference_sql="""
SELECT al.Title, COUNT(*) AS sold_cnt
FROM Album al
JOIN Track t ON t.AlbumId = al.AlbumId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
WHERE al.ArtistId = 22
GROUP BY al.AlbumId, al.Title
ORDER BY sold_cnt DESC
LIMIT 1
""",
                must_hit_columns=["Album.Title", "Album.ArtistId", "InvoiceLine.TrackId"],
                tags=["追问:依赖结果", "追问:指代"],
                note="Led Zeppelin（ArtistId 22）。最畅销专辑 BBC Sessions [Disc 2] [Live] 10 份，第二名 9 份，无并列。",
            ),
            EvalCase(
                id="M2C04-4",
                query="这张专辑的曲目平均时长是多少分钟？保留两位小数。",
                reference_sql="""
SELECT ROUND(AVG(Milliseconds) / 60000.0, 2) AS avg_minutes
FROM Track
WHERE AlbumId = 127
""",
                must_hit_columns=["Track.Milliseconds", "Track.AlbumId"],
                tags=["追问:指代", "追问:换角度"],
                note="专辑 127 的全部曲目（不只是卖出去的），时长毫秒换成分钟取平均。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2C05",
        tags=["难度:难"],
        note="同一天入职的员工 → 两人的直属上级 → 其中负责客户那位的客户逐年消费 → 消费最高那年他名下花得最多的客户。考员工自关联、员工-客户关联、依赖结果。",
        turns=[
            EvalCase(
                id="M2C05-1",
                query="有没有员工是同一天入职的？列出他们的姓名、职位和入职日期。",
                reference_sql="""
SELECT FirstName, LastName, Title, HireDate
FROM Employee
WHERE HireDate IN (SELECT HireDate FROM Employee GROUP BY HireDate HAVING COUNT(*) > 1)
""",
                must_hit_columns=["Employee.HireDate", "Employee.Title"],
                note="只有 2003-10-17 有两人入职：Steve Johnson（Sales Support Agent）和 Michael Mitchell（IT Manager）。",
            ),
            EvalCase(
                id="M2C05-2",
                query="他们俩的直属上级分别是谁？",
                reference_sql="""
SELECT e.FirstName, e.LastName, m.FirstName AS manager_first_name, m.LastName AS manager_last_name
FROM Employee e
JOIN Employee m ON m.EmployeeId = e.ReportsTo
WHERE e.EmployeeId IN (5, 6)
""",
                must_hit_columns=["Employee.ReportsTo"],
                tags=["追问:指代", "追问:换角度"],
                note="Steve Johnson → Nancy Edwards，Michael Mitchell → Andrew Adams，经 ReportsTo 自关联。",
            ),
            EvalCase(
                id="M2C05-3",
                query="两人里负责客户的那位，名下客户每年分别消费了多少？保留两位小数。",
                reference_sql="""
SELECT strftime('%Y', i.InvoiceDate) AS year, ROUND(SUM(i.Total), 2) AS total
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
WHERE c.SupportRepId = 5
GROUP BY strftime('%Y', i.InvoiceDate)
""",
                must_hit_columns=["Customer.SupportRepId", "Invoice.Total", "Invoice.InvoiceDate"],
                tags=["追问:加条件", "追问:换角度"],
                note="两人中只有 Steve Johnson（EmployeeId 5）有客户；按开票年份汇总其名下客户的发票总额，2021–2025 五年。2021 年 164.34 最高，第二 159.47。",
            ),
            EvalCase(
                id="M2C05-4",
                query="消费最高的那一年，他名下哪位客户花得最多？花了多少，保留两位小数？",
                reference_sql="""
SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS spent
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
WHERE c.SupportRepId = 5
  AND i.InvoiceDate >= '2021-01-01' AND i.InvoiceDate < '2022-01-01'
GROUP BY c.CustomerId, c.FirstName, c.LastName
ORDER BY spent DESC
LIMIT 1
""",
                must_hit_columns=["Customer.SupportRepId", "Invoice.Total", "Invoice.InvoiceDate"],
                tags=["追问:依赖结果", "追问:指代"],
                note="2021 年 Steve Johnson 名下客户里 Leonie Köhler 24.75 最高，第二 15.84，无并列。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2C06",
        tags=["难度:中等"],
        note="Germany 的客户 → 各自累计消费 → 花得最多那位买过的流派分布 → 他的专属销售支持员工的入职日期和上级。考指代、依赖结果、员工自关联。",
        turns=[
            EvalCase(
                id="M2C06-1",
                query="国家是 Germany 的客户有哪几位？列出姓名和所在城市。",
                reference_sql="""
SELECT FirstName, LastName, City
FROM Customer
WHERE Country = 'Germany'
""",
                must_hit_columns=["Customer.Country", "Customer.City", "Customer.FirstName", "Customer.LastName"],
                note="客户登记国家为 Germany，4 位。",
            ),
            EvalCase(
                id="M2C06-2",
                query="他们各自累计消费了多少钱？保留两位小数。",
                reference_sql="""
SELECT c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS total
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
WHERE c.Country = 'Germany'
GROUP BY c.CustomerId, c.FirstName, c.LastName
""",
                must_hit_columns=["Invoice.Total", "Invoice.CustomerId"],
                tags=["追问:指代", "追问:换角度"],
                note="「他们」= 上一轮 4 位客户，每人一行。Fynn Zimmermann 43.62 最高，其余均 37.62。",
            ),
            EvalCase(
                id="M2C06-3",
                query="花得最多的那位，买过的曲目按流派分各有几首？",
                reference_sql="""
SELECT g.Name, COUNT(*) AS track_cnt
FROM Invoice i
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
WHERE i.CustomerId = 37
GROUP BY g.GenreId, g.Name
""",
                must_hit_columns=["Genre.Name", "InvoiceLine.TrackId", "Invoice.CustomerId"],
                tags=["追问:依赖结果", "追问:指代"],
                note="Fynn Zimmermann（CustomerId 37）。按购买明细计数（该客户没有重复购买同一曲目，按明细数和按不同曲目数一致）。",
            ),
            EvalCase(
                id="M2C06-4",
                query="他的专属销售支持是哪位员工？这位员工哪天入职、直属上级是谁？",
                reference_sql="""
SELECT e.FirstName, e.LastName, e.HireDate, m.FirstName AS manager_first_name, m.LastName AS manager_last_name
FROM Customer c
JOIN Employee e ON e.EmployeeId = c.SupportRepId
JOIN Employee m ON m.EmployeeId = e.ReportsTo
WHERE c.CustomerId = 37
""",
                must_hit_columns=["Customer.SupportRepId", "Employee.HireDate", "Employee.ReportsTo"],
                tags=["追问:指代", "追问:换角度"],
                note="Fynn Zimmermann 的支持员工是 Jane Peacock，入职 2002-04-01，上级 Nancy Edwards。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2C07",
        tags=["难度:简单"],
        note="Classical 歌单的曲目数和总时长 → 按媒体格式分 → 按格式看销量 → 其中一种格式的曲目和艺术家。考歌单收录关系与销量的区分、指代和加条件。",
        turns=[
            EvalCase(
                id="M2C07-1",
                query="「Classical」这个歌单收录了多少首曲目？总时长一共多少分钟，保留两位小数。",
                reference_sql="""
SELECT COUNT(*) AS track_cnt, ROUND(SUM(t.Milliseconds) / 60000.0, 2) AS total_minutes
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t ON t.TrackId = pt.TrackId
WHERE p.Name = 'Classical'
""",
                must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Track.Milliseconds"],
                note="名为 Classical 的歌单只有一个（PlaylistId 12，其他 Classical 101 系列名字不同），75 首。",
            ),
            EvalCase(
                id="M2C07-2",
                query="这些曲目按媒体格式分各有几首？",
                reference_sql="""
SELECT m.Name, COUNT(*) AS track_cnt
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t ON t.TrackId = pt.TrackId
JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
WHERE p.Name = 'Classical'
GROUP BY m.MediaTypeId, m.Name
""",
                must_hit_columns=["MediaType.Name", "Track.MediaTypeId", "PlaylistTrack.TrackId"],
                tags=["追问:指代", "追问:换角度"],
                note="「这些曲目」= 歌单 Classical 的 75 首，两种格式：Protected AAC audio file 69、Purchased AAC audio file 6。",
            ),
            EvalCase(
                id="M2C07-3",
                query="按格式分开，它们各卖出去多少份？",
                reference_sql="""
SELECT m.Name, COUNT(il.InvoiceLineId) AS sold_cnt
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t ON t.TrackId = pt.TrackId
JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
WHERE p.Name = 'Classical'
GROUP BY m.MediaTypeId, m.Name
""",
                must_hit_columns=["InvoiceLine.TrackId", "PlaylistTrack.TrackId", "MediaType.Name"],
                tags=["追问:指代", "追问:换角度"],
                note="销量看发票明细，不是歌单收录次数。两种格式都有销量：37 和 4。",
            ),
            EvalCase(
                id="M2C07-4",
                query="Purchased AAC audio file 的那6首，分别是什么曲目、出自哪位艺术家？",
                reference_sql="""
SELECT t.Name AS track_name, ar.Name AS artist_name
FROM Playlist p
JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId
JOIN Track t ON t.TrackId = pt.TrackId
JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId
JOIN Album al ON al.AlbumId = t.AlbumId
JOIN Artist ar ON ar.ArtistId = al.ArtistId
WHERE p.Name = 'Classical'
  AND m.Name = 'Purchased AAC audio file'
""",
                must_hit_columns=["Track.Name", "Artist.Name", "MediaType.Name"],
                tags=["追问:加条件", "追问:指代"],
                note="「那6首」= 歌单 Classical 里 Purchased AAC audio file 格式的 6 首（不论卖没卖出），艺术家经专辑关联。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2C08",
        tags=["难度:难"],
        note="2025 年各季度开票额 → 最低季度最畅销流派 → 最高季度同样问 → 那个季度买这个流派最多的客户。考依赖结果、组合前两轮的跨轮省略。",
        turns=[
            EvalCase(
                id="M2C08-1",
                query="2025年每个季度的开票金额分别是多少？季度用 1 到 4 表示，保留两位小数。",
                reference_sql="""
SELECT (CAST(strftime('%m', InvoiceDate) AS INTEGER) + 2) / 3 AS quarter, ROUND(SUM(Total), 2) AS total
FROM Invoice
WHERE InvoiceDate >= '2025-01-01' AND InvoiceDate < '2026-01-01'
GROUP BY quarter
""",
                must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
                note="自然季度（1–3 月为第一季度）。最低 Q1 102.96，最高 Q4 125.86，都唯一。",
            ),
            EvalCase(
                id="M2C08-2",
                query="金额最低的那个季度，卖出去的曲目里哪个流派最多？卖了多少份？",
                reference_sql="""
SELECT g.Name, COUNT(*) AS sold_cnt
FROM Invoice i
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
WHERE i.InvoiceDate >= '2025-01-01' AND i.InvoiceDate < '2025-04-01'
GROUP BY g.GenreId, g.Name
ORDER BY sold_cnt DESC
LIMIT 1
""",
                must_hit_columns=["Genre.Name", "Invoice.InvoiceDate", "InvoiceLine.TrackId"],
                tags=["追问:依赖结果", "追问:换角度"],
                note="2025 年第一季度：Latin 35 份，第二 Rock 30。",
            ),
            EvalCase(
                id="M2C08-3",
                query="最高的那个季度呢？",
                reference_sql="""
SELECT g.Name, COUNT(*) AS sold_cnt
FROM Invoice i
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
JOIN Genre g ON g.GenreId = t.GenreId
WHERE i.InvoiceDate >= '2025-10-01' AND i.InvoiceDate < '2026-01-01'
GROUP BY g.GenreId, g.Name
ORDER BY sold_cnt DESC
LIMIT 1
""",
                must_hit_columns=["Genre.Name", "Invoice.InvoiceDate", "InvoiceLine.TrackId"],
                tags=["追问:省略", "追问:跨轮", "追问:依赖结果"],
                note="按第 1 轮金额最高的季度（2025 年第四季度）问上一轮同样的问题：Rock 55 份，第二 27。",
            ),
            EvalCase(
                id="M2C08-4",
                query="那个季度里，买这个流派最多的客户是谁？买了几份？",
                reference_sql="""
SELECT c.FirstName, c.LastName, COUNT(*) AS bought_cnt
FROM Invoice i
JOIN Customer c ON c.CustomerId = i.CustomerId
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
WHERE t.GenreId = 1
  AND i.InvoiceDate >= '2025-10-01' AND i.InvoiceDate < '2026-01-01'
GROUP BY c.CustomerId, c.FirstName, c.LastName
ORDER BY bought_cnt DESC
LIMIT 1
""",
                must_hit_columns=["Customer.FirstName", "Customer.LastName", "Track.GenreId", "Invoice.InvoiceDate"],
                tags=["追问:指代", "追问:依赖结果", "追问:加条件"],
                note="2025 年第四季度、Rock 流派：Patrick Gray 11 份，第二 9 份。",
            ),
        ],
    ),
]

# ---------------------------------------------------------------------------
# sakila
# ---------------------------------------------------------------------------

MULTITURN2_SAKILA_CASES = [
    MultiTurnCase(
        id="M2S01",
        tags=["难度:中等"],
        note="不活跃客户按注册门店 → 他们累计付款 → 追问流失原因（库里没有）→ 回到这些客户看谁租得最多。考 active 字段的字符取值、注册门店口径、识别缺失、陷阱后跨轮。",
        turns=[
            EvalCase(
                id="M2S01-1",
                query="目前不活跃的客户有几位？按注册门店分各几位？",
                reference_sql="""
SELECT store_id, COUNT(*) AS customer_cnt
FROM customer
WHERE active = '0'
GROUP BY store_id
""",
                must_hit_columns=["customer.active", "customer.store_id"],
                note="不活跃 = active 为字符 '0'，共 15 位；按客户注册门店分组：门店1 8 位、门店2 7 位。",
            ),
            EvalCase(
                id="M2S01-2",
                query="他们累计付过多少钱？按注册门店分别算，保留两位小数。",
                reference_sql="""
SELECT c.store_id, ROUND(SUM(p.amount), 2) AS paid
FROM customer c
JOIN payment p ON p.customer_id = c.customer_id
WHERE c.active = '0'
GROUP BY c.store_id
""",
                must_hit_columns=["customer.active", "customer.store_id", "payment.amount"],
                tags=["追问:指代", "追问:换角度"],
                note="「他们」= 上一轮 15 位不活跃客户，付款实收金额求和，仍按客户注册门店分两行。",
            ),
            EvalCase(
                id="M2S01-3",
                query="这些客户当初是因为什么原因不再活跃的？",
                reference_sql=TRAP_SQL,
                must_hit_columns=[],
                tags=["追问:指代", "陷阱题"],
                note="库里只有是否活跃的标记，没有流失原因、注销记录或状态变更时间，应说明缺失。",
                expect_unanswerable=True,
            ),
            EvalCase(
                id="M2S01-4",
                query="回到第一个问题那些不活跃客户，谁租的次数最多？租了几次？",
                reference_sql="""
SELECT c.first_name, c.last_name, COUNT(r.rental_id) AS rental_cnt
FROM customer c
JOIN rental r ON r.customer_id = c.customer_id
WHERE c.active = '0'
GROUP BY c.customer_id, c.first_name, c.last_name
ORDER BY rental_cnt DESC
LIMIT 1
""",
                must_hit_columns=["customer.active", "rental.customer_id"],
                tags=["追问:跨轮", "追问:指代"],
                note="指回第 1 轮的 15 位不活跃客户：HARRY ARCE 35 次最多，第二 34 次，无并列。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2S02",
        tags=["难度:中等"],
        note="单笔最高付款金额及笔数 → 这几笔是谁付的、租的什么片 → 这些片的标价和租期 → 这几笔租借在哪家店租出。考依赖上一轮的金额值、付款-租借-拷贝-影片链路、去重。",
        turns=[
            EvalCase(
                id="M2S02-1",
                query="单笔付款金额最高的是多少钱？这个金额的付款一共有几笔？",
                reference_sql="""
SELECT amount, COUNT(*) AS payment_cnt
FROM payment
WHERE amount = (SELECT MAX(amount) FROM payment)
GROUP BY amount
""",
                must_hit_columns=["payment.amount"],
                note="最高单笔 11.99，共 10 笔。",
            ),
            EvalCase(
                id="M2S02-2",
                query="这几笔分别是哪位客户付的、租的是哪部影片？",
                reference_sql="""
SELECT c.first_name, c.last_name, f.title
FROM payment p
JOIN customer c ON c.customer_id = p.customer_id
JOIN rental r ON r.rental_id = p.rental_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
WHERE p.amount = 11.99
""",
                must_hit_columns=["payment.customer_id", "payment.rental_id", "inventory.film_id", "film.title"],
                tags=["追问:指代", "追问:依赖结果", "追问:换角度"],
                note="「这几笔」= 金额 11.99 的 10 笔付款，都关联了租借；逐笔列客户和影片（SCORPION APOLLO 出现两次）。",
            ),
            EvalCase(
                id="M2S02-3",
                query="这几部影片的租借标价和规定租期各是多少？同一部片只列一次。",
                reference_sql="""
SELECT DISTINCT f.title, f.rental_rate, f.rental_duration
FROM payment p
JOIN rental r ON r.rental_id = p.rental_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
WHERE p.amount = 11.99
""",
                must_hit_columns=["film.rental_rate", "film.rental_duration"],
                tags=["追问:指代", "追问:换角度"],
                note="「这几部影片」= 上一轮 10 笔涉及的 9 部不同影片（SCORPION APOLLO 两次），题面要求同一部只列一次。全部是标价 4.99、租期 3 天，可见 11.99 含逾期费。",
            ),
            EvalCase(
                id="M2S02-4",
                query="这几笔租借分别是在哪家门店租出去的？两家店各几笔？",
                reference_sql="""
SELECT i.store_id, COUNT(*) AS rental_cnt
FROM payment p
JOIN rental r ON r.rental_id = p.rental_id
JOIN inventory i ON i.inventory_id = r.inventory_id
WHERE p.amount = 11.99
GROUP BY i.store_id
""",
                must_hit_columns=["inventory.store_id", "payment.rental_id"],
                tags=["追问:指代", "追问:换角度"],
                note="这 10 笔付款对应的租借，按租出拷贝所在门店（不是客户注册门店、也不是收款员工）计数：门店1 4 笔、门店2 6 笔。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2S03",
        tags=["难度:中等"],
        note="四种附赠内容全带的影片按分级 → 按租借标价 → 标价 4.99 里租得最多的那部 → 它在两家店的拷贝数。考多值文本字段的匹配、省略、加条件和依赖结果。",
        turns=[
            EvalCase(
                id="M2S03-1",
                query="四种附赠内容（Trailers、Commentaries、Deleted Scenes、Behind the Scenes）全都带的影片，按分级分各有多少部？",
                reference_sql="""
SELECT rating, COUNT(*) AS film_cnt
FROM film
WHERE special_features LIKE '%Trailers%'
  AND special_features LIKE '%Commentaries%'
  AND special_features LIKE '%Deleted Scenes%'
  AND special_features LIKE '%Behind the Scenes%'
GROUP BY rating
""",
                must_hit_columns=["film.special_features", "film.rating"],
                note="附赠内容是逗号分隔的组合，四种都包含的 61 部，5 个分级都有。",
            ),
            EvalCase(
                id="M2S03-2",
                query="按租借标价分呢？",
                reference_sql="""
SELECT rental_rate, COUNT(*) AS film_cnt
FROM film
WHERE special_features LIKE '%Trailers%'
  AND special_features LIKE '%Commentaries%'
  AND special_features LIKE '%Deleted Scenes%'
  AND special_features LIKE '%Behind the Scenes%'
GROUP BY rental_rate
""",
                must_hit_columns=["film.special_features", "film.rental_rate"],
                tags=["追问:省略", "追问:换角度"],
                note="同一批 61 部影片，改按租借标价分组：0.99、2.99、4.99 三档。",
            ),
            EvalCase(
                id="M2S03-3",
                query="其中标价 4.99 的那些，被租次数最多的是哪部？租了几次？",
                reference_sql="""
SELECT f.title, COUNT(r.rental_id) AS rental_cnt
FROM film f
JOIN inventory i ON i.film_id = f.film_id
JOIN rental r ON r.inventory_id = i.inventory_id
WHERE f.special_features LIKE '%Trailers%'
  AND f.special_features LIKE '%Commentaries%'
  AND f.special_features LIKE '%Deleted Scenes%'
  AND f.special_features LIKE '%Behind the Scenes%'
  AND f.rental_rate = 4.99
GROUP BY f.film_id, f.title
ORDER BY rental_cnt DESC
LIMIT 1
""",
                must_hit_columns=["film.rental_rate", "rental.inventory_id", "inventory.film_id"],
                tags=["追问:加条件", "追问:指代"],
                note="四种附赠内容全带且标价 4.99 的 18 部里：TITANIC BOONDOCK 23 次最多，第二 21 次，无并列。",
            ),
            EvalCase(
                id="M2S03-4",
                query="这部片在两家门店各有几张拷贝？",
                reference_sql="""
SELECT i.store_id, COUNT(*) AS copy_cnt
FROM inventory i
WHERE i.film_id = 892
GROUP BY i.store_id
""",
                must_hit_columns=["inventory.store_id", "inventory.film_id"],
                tags=["追问:指代", "追问:依赖结果", "追问:换角度"],
                note="TITANIC BOONDOCK（film_id 892）：门店1 3 张、门店2 4 张。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2S04",
        tags=["难度:难"],
        note="姓 TEMPLE 的演员及出演数 → 他们的影片按分级去重统计 → 出演最多那位收入最高的影片 → 这部片的演员表。考演员同姓筛选、跨演员去重、跨轮依赖结果。",
        turns=[
            EvalCase(
                id="M2S04-1",
                query="姓 TEMPLE 的演员有哪几位？各演过多少部影片？",
                reference_sql="""
SELECT a.first_name, a.last_name, COUNT(*) AS film_cnt
FROM actor a
JOIN film_actor fa ON fa.actor_id = a.actor_id
WHERE a.last_name = 'TEMPLE'
GROUP BY a.actor_id, a.first_name, a.last_name
""",
                must_hit_columns=["actor.last_name", "film_actor.actor_id"],
                note="4 位：MENA 30、RUSSELL 31、BURT 23、THORA 20。RUSSELL TEMPLE 最多，无并列。",
            ),
            EvalCase(
                id="M2S04-2",
                query="他们演过的影片按分级分各有多少部？四位合在一起算，同一部影片只算一次。",
                reference_sql="""
SELECT f.rating, COUNT(DISTINCT f.film_id) AS film_cnt
FROM film_actor fa
JOIN actor a ON a.actor_id = fa.actor_id
JOIN film f ON f.film_id = fa.film_id
WHERE a.last_name = 'TEMPLE'
GROUP BY f.rating
""",
                must_hit_columns=["film.rating", "film_actor.film_id"],
                tags=["追问:指代", "追问:换角度"],
                note="四人共 104 次出演、97 部不同影片（有 7 部是两位 TEMPLE 同演），按影片去重后按分级计数。",
            ),
            EvalCase(
                id="M2S04-3",
                query="演过影片最多的那位，他演的影片里收入最高的是哪部？收入多少，保留两位小数。",
                reference_sql="""
SELECT f.title, ROUND(SUM(p.amount), 2) AS revenue
FROM film_actor fa
JOIN film f ON f.film_id = fa.film_id
JOIN inventory i ON i.film_id = f.film_id
JOIN rental r ON r.inventory_id = i.inventory_id
JOIN payment p ON p.rental_id = r.rental_id
WHERE fa.actor_id = 149
GROUP BY f.film_id, f.title
ORDER BY revenue DESC
LIMIT 1
""",
                must_hit_columns=["film_actor.actor_id", "payment.amount", "film.title"],
                tags=["追问:依赖结果", "追问:跨轮"],
                note="「演过影片最多的那位」按第 1 轮是 RUSSELL TEMPLE（actor_id 149）。收入按付款实收：PELICAN COMFORTS 188.74，第二 172.72，无并列。",
            ),
            EvalCase(
                id="M2S04-4",
                query="这部片都有哪些演员出演？",
                reference_sql="""
SELECT a.first_name, a.last_name
FROM film_actor fa
JOIN actor a ON a.actor_id = fa.actor_id
WHERE fa.film_id = 670
""",
                must_hit_columns=["film_actor.film_id", "actor.first_name", "actor.last_name"],
                tags=["追问:指代", "追问:换角度"],
                note="PELICAN COMFORTS（film_id 670）的全部演员，包含 RUSSELL TEMPLE 本人。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2S05",
        tags=["难度:难"],
        note="2005 年 8 月已归还租借里的逾期笔数 → 按分级拆 → 这些逾期租借的收款 → 回到分级拆分看 NC-17 的客户国家。考逾期口径交代后的沿用、省略和跨轮加条件。",
        turns=[
            EvalCase(
                id="M2S05-1",
                query="2005年8月租出去、并且已经还回来的租借里，逾期的有多少笔？逾期按实际租借时长（精确到时分秒）超过该影片规定的租期来算。",
                reference_sql="""
SELECT COUNT(*) AS overdue_cnt
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
WHERE r.rental_date >= '2005-08-01' AND r.rental_date < '2005-09-01'
  AND r.return_date IS NOT NULL
  AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
""",
                must_hit_columns=["rental.rental_date", "rental.return_date", "film.rental_duration"],
                note="题面交代了逾期口径（精确时长 > 租期天数），按日期相减会得到不同结果，所以写明。结果 2942。",
            ),
            EvalCase(
                id="M2S05-2",
                query="按影片分级拆开看，各级分别多少笔？",
                reference_sql="""
SELECT f.rating, COUNT(*) AS overdue_cnt
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
WHERE r.rental_date >= '2005-08-01' AND r.rental_date < '2005-09-01'
  AND r.return_date IS NOT NULL
  AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
GROUP BY f.rating
""",
                must_hit_columns=["film.rating", "film.rental_duration", "rental.return_date"],
                tags=["追问:省略", "追问:换角度"],
                note="沿用上一轮范围和逾期口径，按影片分级分组（5 级都有）。",
            ),
            EvalCase(
                id="M2S05-3",
                query="这些逾期的租借，对应的付款一共收了多少钱？保留两位小数。",
                reference_sql="""
SELECT ROUND(SUM(p.amount), 2) AS amount
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
JOIN payment p ON p.rental_id = r.rental_id
WHERE r.rental_date >= '2005-08-01' AND r.rental_date < '2005-09-01'
  AND r.return_date IS NOT NULL
  AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
""",
                must_hit_columns=["payment.amount", "payment.rental_id"],
                tags=["追问:指代", "追问:换角度"],
                note="「这些逾期的租借」= 第 1 轮的全部 2942 笔（「一共」= 合计一个数）；每笔租借恰有一笔付款。",
            ),
            EvalCase(
                id="M2S05-4",
                query="回到按分级拆的结果，NC-17 那部分的逾期租借，客户来自哪些国家？列出笔数最多的前3个国家和各自的笔数。",
                reference_sql="""
SELECT co.country, COUNT(*) AS overdue_cnt
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
JOIN customer cu ON cu.customer_id = r.customer_id
JOIN address a ON a.address_id = cu.address_id
JOIN city ci ON ci.city_id = a.city_id
JOIN country co ON co.country_id = ci.country_id
WHERE r.rental_date >= '2005-08-01' AND r.rental_date < '2005-09-01'
  AND r.return_date IS NOT NULL
  AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration
  AND f.rating = 'NC-17'
GROUP BY co.country_id, co.country
ORDER BY overdue_cnt DESC
LIMIT 3
""",
                must_hit_columns=["film.rating", "country.country", "rental.customer_id"],
                tags=["追问:跨轮", "追问:加条件"],
                note="第 2 轮里 NC-17 的 610 笔逾期租借，按租借客户住址国家计数。India 65、China 53、United States 44，第4名 35。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2S06",
        tags=["难度:中等"],
        note="片长最长的影片 → 各自拷贝数 → 拷贝最多那部的演员 → 这些演员各演过几部 R 级片。考指代、依赖结果、加条件。",
        turns=[
            EvalCase(
                id="M2S06-1",
                query="片长最长的影片有哪几部？片长多少分钟？",
                reference_sql="""
SELECT title, length
FROM film
WHERE length = (SELECT MAX(length) FROM film)
""",
                must_hit_columns=["film.title", "film.length"],
                note="最长片长 185 分钟，正好 10 部并列最长，全部列出。",
            ),
            EvalCase(
                id="M2S06-2",
                query="它们各有几张拷贝？",
                reference_sql="""
SELECT f.title, COUNT(i.inventory_id) AS copy_cnt
FROM film f
JOIN inventory i ON i.film_id = f.film_id
WHERE f.length = (SELECT MAX(length) FROM film)
GROUP BY f.film_id, f.title
""",
                must_hit_columns=["inventory.film_id", "inventory.inventory_id"],
                tags=["追问:指代", "追问:换角度"],
                note="「它们」= 上一轮 10 部，两家店合计。10 部都有拷贝（2–8 张）；最多的 MUSCLE BRIGHT 8 张，唯一。",
            ),
            EvalCase(
                id="M2S06-3",
                query="其中拷贝最多的那部，有哪些演员出演？",
                reference_sql="""
SELECT a.first_name, a.last_name
FROM film_actor fa
JOIN actor a ON a.actor_id = fa.actor_id
WHERE fa.film_id = 609
""",
                must_hit_columns=["film_actor.film_id", "actor.first_name", "actor.last_name"],
                tags=["追问:依赖结果", "追问:指代"],
                note="MUSCLE BRIGHT（film_id 609），5 位演员。",
            ),
            EvalCase(
                id="M2S06-4",
                query="这几位演员各演过几部 R 级的影片？",
                reference_sql="""
SELECT a.first_name, a.last_name, COUNT(*) AS r_film_cnt
FROM film_actor fa
JOIN actor a ON a.actor_id = fa.actor_id
JOIN film f ON f.film_id = fa.film_id
WHERE fa.actor_id IN (SELECT actor_id FROM film_actor WHERE film_id = 609)
  AND f.rating = 'R'
GROUP BY a.actor_id, a.first_name, a.last_name
""",
                must_hit_columns=["film.rating", "film_actor.actor_id"],
                tags=["追问:指代", "追问:加条件"],
                note="「这几位演员」= 上一轮 5 位；每位演员出演的分级为 R 的影片数，5 位都至少 2 部。MUSCLE BRIGHT 本身是 G 级，算不算它不影响结果。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2S07",
        tags=["难度:中等"],
        note="未归还租借按办理员工 → 按拷贝所在门店 → 欠得最多的客户 → 她欠的影片和赔偿价。考指代、换角度、依赖结果。",
        turns=[
            EvalCase(
                id="M2S07-1",
                query="到现在还没归还的租借，按办理的员工分各有多少笔？",
                reference_sql="""
SELECT s.first_name, s.last_name, COUNT(*) AS unreturned_cnt
FROM rental r
JOIN staff s ON s.staff_id = r.staff_id
WHERE r.return_date IS NULL
GROUP BY s.staff_id, s.first_name, s.last_name
""",
                must_hit_columns=["rental.return_date", "rental.staff_id", "staff.first_name", "staff.last_name"],
                note="没还 = 归还时间为空（183 笔）；办理员工看租借记录上的员工，不是收款员工。",
            ),
            EvalCase(
                id="M2S07-2",
                query="这些没还的拷贝分别属于哪家门店？各几张？",
                reference_sql="""
SELECT i.store_id, COUNT(*) AS copy_cnt
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
WHERE r.return_date IS NULL
GROUP BY i.store_id
""",
                must_hit_columns=["rental.return_date", "inventory.store_id"],
                tags=["追问:指代", "追问:换角度"],
                note="按拷贝所在门店；183 笔未归还对应 183 张不同拷贝，按笔数或按拷贝去重结果一致。",
            ),
            EvalCase(
                id="M2S07-3",
                query="这些没还的里面，哪位客户欠得最多？欠了几张？",
                reference_sql="""
SELECT cu.first_name, cu.last_name, COUNT(*) AS unreturned_cnt
FROM rental r
JOIN customer cu ON cu.customer_id = r.customer_id
WHERE r.return_date IS NULL
GROUP BY cu.customer_id, cu.first_name, cu.last_name
ORDER BY unreturned_cnt DESC
LIMIT 1
""",
                must_hit_columns=["rental.return_date", "rental.customer_id", "customer.first_name", "customer.last_name"],
                tags=["追问:指代", "追问:换角度"],
                note="TAMMY SANDERS 3 张，其余最多 2 张，唯一。",
            ),
            EvalCase(
                id="M2S07-4",
                query="她欠的那几张分别是什么影片、赔偿价各多少？",
                reference_sql="""
SELECT f.title, f.replacement_cost
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f ON f.film_id = i.film_id
WHERE r.return_date IS NULL
  AND r.customer_id = 75
""",
                must_hit_columns=["film.title", "film.replacement_cost"],
                tags=["追问:依赖结果", "追问:指代"],
                note="TAMMY SANDERS（customer_id 75）的 3 笔未归还，3 部不同影片；赔偿价不是租金。",
            ),
        ],
    ),
    MultiTurnCase(
        id="M2S08",
        tags=["难度:中等"],
        note="2005 年 7 月付款前五客户 → 8 月前五 → 两个月都在的那位的租借分类分布 → 她这两个月在两家店的租借次数。考省略、比较两轮结果的跨轮依赖。",
        turns=[
            EvalCase(
                id="M2S08-1",
                query="2005年7月付款金额最高的5位客户是谁？各付了多少，保留两位小数。",
                reference_sql="""
SELECT cu.first_name, cu.last_name, ROUND(SUM(p.amount), 2) AS paid
FROM payment p
JOIN customer cu ON cu.customer_id = p.customer_id
WHERE p.payment_date >= '2005-07-01' AND p.payment_date < '2005-08-01'
GROUP BY cu.customer_id, cu.first_name, cu.last_name
ORDER BY paid DESC
LIMIT 5
""",
                must_hit_columns=["payment.payment_date", "payment.amount", "customer.first_name", "customer.last_name"],
                note="按付款时间。第5名 CLARA SHAW 93.82，第6名 89.82，无并列。",
            ),
            EvalCase(
                id="M2S08-2",
                query="那8月呢？金额同样保留两位小数。",
                reference_sql="""
SELECT cu.first_name, cu.last_name, ROUND(SUM(p.amount), 2) AS paid
FROM payment p
JOIN customer cu ON cu.customer_id = p.customer_id
WHERE p.payment_date >= '2005-08-01' AND p.payment_date < '2005-09-01'
GROUP BY cu.customer_id, cu.first_name, cu.last_name
ORDER BY paid DESC
LIMIT 5
""",
                must_hit_columns=["payment.payment_date", "payment.amount", "customer.first_name", "customer.last_name"],
                tags=["追问:省略"],
                note="只换月份（2005 年 8 月），沿用付款金额。第5名 79.82，第6名 77.82。",
            ),
            EvalCase(
                id="M2S08-3",
                query="两个月都进了前五的那位，这两个月里租的影片按分类分各几次？",
                reference_sql="""
SELECT c.name, COUNT(*) AS rental_cnt
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
JOIN category c ON c.category_id = fc.category_id
WHERE r.customer_id = 148
  AND r.rental_date >= '2005-07-01' AND r.rental_date < '2005-09-01'
GROUP BY c.category_id, c.name
""",
                must_hit_columns=["rental.customer_id", "rental.rental_date", "category.name"],
                tags=["追问:跨轮", "追问:依赖结果"],
                note="两个月都在前五的只有 ELEANOR HUNT（customer_id 148）。按租出时间 2005 年 7–8 月统计租借次数（本库付款与租出同日，按付款时间界定结果相同）。",
            ),
            EvalCase(
                id="M2S08-4",
                query="这两个月她在两家门店各租了多少次？",
                reference_sql="""
SELECT i.store_id, COUNT(*) AS rental_cnt
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
WHERE r.customer_id = 148
  AND r.rental_date >= '2005-07-01' AND r.rental_date < '2005-09-01'
GROUP BY i.store_id
""",
                must_hit_columns=["rental.customer_id", "inventory.store_id"],
                tags=["追问:跨轮", "追问:换角度"],
                note="「她」是由第 1、2 轮结果确定的 ELEANOR HUNT（两轮各 5 行），「这两个月」也来自第 1、2 轮；不是指上一轮的分类明细。在哪家店租按租出拷贝所在门店，不是客户注册门店。门店1 18 次、门店2 22 次。",
            ),
        ],
    ),
]


MULTITURN2_BANKS = {
    "ecommerce": MULTITURN2_ECOMMERCE_CASES,
    "chinook": MULTITURN2_CHINOOK_CASES,
    "sakila": MULTITURN2_SAKILA_CASES,
}
