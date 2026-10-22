"""
探针：对着某一类已知的生成错误写的小题，用来量一条规则管不管用，改规则时回归。

**不是留出集。**每一批都是看着一类失败写的，分数不能当泛化能力的证据。四批：

    探针:整数除法    P01–P12       SQLite 两个整数相除被截断。在选规则措辞之前写，
                                   文档里的"13 道"是这 12 道加 H3E14（在留出集三里）
    探针:整数除法二  Q01–Q08       措辞定了以后才写，一半是"A 表总数 ÷ B 表总数"
    探针:一对多      F01–F12       连上明细表之后再数主表的笔数、加主表的金额
                     N01–N04       对照：连接后直接统计本来就对
    探针:一对多二    G01–G09       措辞定了以后才写，换了表和问法
                     M01–M04       对照
    探针:每组前N     K01–K15       每个 X 里取前 N（第六套之后）；K10–K15 是"连多张表聚合再组内取前 N"
                     L01–L02       对照：全局前 N
                     S01–S03       窗口筛选：外层要用窗口函数算出来的值
    探针:每组前N二   R01–R05       措辞定了以后才写
                     W01–W04       窗口筛选
                     L03–L04       对照
    探针:时间差      D01–D04       时间差正好落在 1 小时、30 分钟上，julianday 的浮点误差会分错（第七套之后）
                     Y01–Y02       对照：按整天比较，julianday 本来就准
    探针:时间差二    D05–D07       措辞定了以后才写
                     Y03           对照
    探针:唯一与挂单  U01–U07       全都是同一个 X（第七套之后）；U05–U07 的 X 要经过一两张表才拿得到
                     V01–V03       退款、支付挂在订单上，按明细的维度（类目）汇总
                     UC1、VC1      对照
    探针:唯一与挂单二 U08–U10、V04–V06  措辞定了以后才写
                     UC2、VC2      对照
    探针:口径        J01–J04       题目没写订单状态时的默认口径（只算已付款的订单）
                     JC1–JC2       对照：不带修饰的订单数不加条件；点名状态的按题面
    探针:口径二      J05–J08       口径写进元数据之后才写
                     JC3–JC5       对照
    探针:全称        A01–A11       "那些 X 全都 / 一个都没有……"（第八套之后）；A01–A06 电商，A07–A11 Chinook
                     A12–A19       补的：X 的集合和条件在两张表里，要逐对反连接再整体否定（A01、H8E16 的结构）
                     AC1–AC5       对照：问的本来就是"至少有一个"
                                   这一批量过两版 SQL 规则，都没有收益，规则撤掉了；探针留作测量

口径定下来时，F03、F04、F06、G02、G05、M01、K01、K05、L01、K11 的参考答案（和错误写法）改成了只算已付款的订单：
它们原先默认算全部订单，和定下的口径不一致。改之前的版本留在 git 历史里，之前记录的这几道题的分数是按旧参考答案量的。

每道"该出错"的题在 WRONG_SQL 里附一条错误写法：整数相除的那几批是把参考 SQL 的
`* 1.0`、`100.0` 去掉；一对多的是直接连接之后再统计；每组前 N 的是不在组内截断；时间差的是 julianday 相减再乘 24 / 1440；全都是同一个 X 的是把 X 也放进 GROUP BY；挂单的是直接连明细再 SUM；全称的是逐对判断、有一个满足就算（存在量词）。窗口筛选的题
没有错误写法：它们的失败是 SQL 报错（外层看不到内层的列、WHERE 里用了窗口函数）。tests/test_probes.py 检查错误写法
的答案和参考答案确实不同——否则这道探针区分不出规则有没有起作用。对照题没有错误写法，
它们用来确认规则没把模型带偏。

    python -m eval.runner --bank probes --tag 探针:一对多 --repeat 3
    python -m eval.runner --bank probes --dataset chinook --repeat 3

整数除法两批原先只存在临时目录里，被系统清理了，从当时的会话记录里原样找回。
结果见 docs/实验记录.md「整数相除，和跨表比例」「一对多连接：订单被数了几遍」「每组前 N，和修正看不懂的报错」「时间差：正好 1 小时被算成超过 1 小时」「全都是同一个 X，和挂在订单上的退款」「口径漂移」「全称：一个都没有写成有一个没有」。
"""

from eval.cases import EvalCase

_INT_DIV_ECOMMERCE = [
    EvalCase(
        id="P01",
        query="各城市用户的人均活跃天数是多少？人均 = 该城市用户的活跃天数之和 ÷ 该城市用户数。返回城市和人均天数（保留2位小数）。",
        reference_sql=(
            "SELECT u.city, ROUND(SUM(s.active_days) * 1.0 / COUNT(*), 2)"
            " FROM dim_user u"
            " JOIN dws_user_summary s ON s.user_id = u.user_id"
            " GROUP BY u.city"
        ),
        must_hit_columns=["dim_user.city", "dws_user_summary.active_days"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P02",
        query="平均每笔订单买了几件商品？件数按订单明细的购买数量加总，再除以有明细的订单笔数，保留2位小数。",
        reference_sql="SELECT ROUND(SUM(quantity) * 1.0 / COUNT(DISTINCT order_id), 2) FROM fact_order_item",
        must_hit_columns=["fact_order_item.quantity"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P03",
        query="平均每家店铺有几个在售商品？在售商品个数 ÷ 店铺总数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND((SELECT COUNT(*) FROM dim_product WHERE shelf_status = '在售') * 1.0 / (SELECT COUNT(*) FROM dim_shop), 2)"
        ),
        must_hit_columns=["dim_product.shelf_status"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P04",
        query="订单状态为已退款的订单，占全部订单的百分之多少？返回0到100之间的数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND(SUM(CASE WHEN order_status = '已退款' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)"
            " FROM fact_order"
        ),
        must_hit_columns=["fact_order.order_status"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P05",
        query="每个城市的用户中，钻石会员占该城市用户数的比例是多少？返回城市和比例（0到1之间的小数，保留4位）。",
        reference_sql=(
            "SELECT city, ROUND(SUM(CASE WHEN member_level = '钻石会员' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4)"
            " FROM dim_user"
            " GROUP BY city"
        ),
        must_hit_columns=["dim_user.city", "dim_user.member_level"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P06",
        query="每家店铺的日均下单买家数是多少？日均 = 店铺各天下单买家数之和 ÷ 有数据的天数。返回店铺名称和日均买家数（保留2位小数）。",
        reference_sql=(
            "SELECT s.shop_name, ROUND(SUM(d.buyer_count) * 1.0 / COUNT(*), 2)"
            " FROM dws_shop_daily d"
            " JOIN dim_shop s ON s.shop_id = d.shop_id"
            " GROUP BY d.shop_id, s.shop_name"
        ),
        must_hit_columns=["dws_shop_daily.buyer_count", "dim_shop.shop_name"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P07",
        query="加购过商品的用户，平均每人加购了几次？加购次数 ÷ 加购过的去重用户数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT user_id), 2)"
            " FROM fact_user_behavior"
            " WHERE behavior_type = '加购'"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="Q01",
        query="有过收藏行为的用户，平均每人收藏了几次？收藏行为次数 ÷ 收藏过的去重用户数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT user_id), 2)"
            " FROM fact_user_behavior"
            " WHERE behavior_type = '收藏'"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type"],
        tags=["探针:整数除法二"],
    ),
    EvalCase(
        id="Q02",
        query="平均每个二级类目下有几个商品？商品总数 ÷ 二级类目个数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND((SELECT COUNT(*) FROM dim_product) * 1.0 / (SELECT COUNT(*) FROM dim_category WHERE category_level = 2), 2)"
        ),
        must_hit_columns=["dim_category.category_level"],
        tags=["探针:整数除法二"],
    ),
    EvalCase(
        id="Q03",
        query="订单状态为已取消的订单占全部订单的比例是多少？返回0到1之间的小数，保留4位。",
        reference_sql=(
            "SELECT ROUND(SUM(CASE WHEN order_status = '已取消' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4)"
            " FROM fact_order"
        ),
        must_hit_columns=["fact_order.order_status"],
        tags=["探针:整数除法二"],
    ),
    EvalCase(
        id="Q04",
        query="平均每家店铺有多少笔订单？订单总数 ÷ 店铺总数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND((SELECT COUNT(*) FROM fact_order) * 1.0 / (SELECT COUNT(*) FROM dim_shop), 2)"
        ),
        must_hit_columns=[["fact_order.order_id", "fact_order.shop_id"], "dim_shop.shop_id"],
        tags=["探针:整数除法二"],
    ),
]


_INT_DIV_CHINOOK = [
    EvalCase(
        id="P08",
        query="平均每张专辑有多少首曲目？曲目总数 ÷ 专辑总数，保留2位小数。",
        reference_sql="SELECT ROUND((SELECT COUNT(*) FROM Track) * 1.0 / (SELECT COUNT(*) FROM Album), 2)",
        must_hit_columns=[["Track.TrackId", "Track.AlbumId"], "Album.AlbumId"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P09",
        query="每个流派的曲目数占全部曲目数的百分比是多少？返回流派名称和百分比（0到100之间的数，保留2位小数）。",
        reference_sql=(
            "SELECT g.Name, ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM Track), 2)"
            " FROM Track t"
            " JOIN Genre g ON g.GenreId = t.GenreId"
            " GROUP BY g.GenreId, g.Name"
        ),
        must_hit_columns=["Genre.Name"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P10",
        query="平均每位客户开过几张发票？发票总数 ÷ 客户总数，保留2位小数。",
        reference_sql="SELECT ROUND((SELECT COUNT(*) FROM Invoice) * 1.0 / (SELECT COUNT(*) FROM Customer), 2)",
        must_hit_columns=[["Invoice.InvoiceId", "Invoice.CustomerId"], "Customer.CustomerId"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P11",
        query="每位负责客户的员工，名下客户平均每人开过几张发票？返回员工的名、姓和平均发票数（名下客户的发票总数 ÷ 名下客户数，保留2位小数）。",
        reference_sql=(
            "SELECT e.FirstName, e.LastName, ROUND(COUNT(i.InvoiceId) * 1.0 / COUNT(DISTINCT c.CustomerId), 2)"
            " FROM Employee e"
            " JOIN Customer c ON c.SupportRepId = e.EmployeeId"
            " JOIN Invoice i ON i.CustomerId = c.CustomerId"
            " GROUP BY e.EmployeeId, e.FirstName, e.LastName"
        ),
        must_hit_columns=["Customer.SupportRepId", "Employee.FirstName", "Employee.LastName"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="P12",
        query="所有曲目的平均时长是多少分钟？毫秒数加总 ÷ 曲目数，再换算成分钟，保留2位小数。",
        reference_sql="SELECT ROUND(SUM(Milliseconds) * 1.0 / COUNT(*) / 60000, 2) FROM Track",
        must_hit_columns=["Track.Milliseconds"],
        tags=["探针:整数除法"],
    ),
    EvalCase(
        id="Q05",
        query="平均每个歌单收录了多少首曲目？歌单与曲目的收录记录条数 ÷ 歌单总数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND((SELECT COUNT(*) FROM PlaylistTrack) * 1.0 / (SELECT COUNT(*) FROM Playlist), 2)"
        ),
        must_hit_columns=[["PlaylistTrack.PlaylistId", "PlaylistTrack.TrackId"], "Playlist.PlaylistId"],
        tags=["探针:整数除法二"],
    ),
    EvalCase(
        id="Q06",
        query="平均每位艺术家有几张专辑？专辑总数 ÷ 艺术家总数，保留2位小数。",
        reference_sql="SELECT ROUND((SELECT COUNT(*) FROM Album) * 1.0 / (SELECT COUNT(*) FROM Artist), 2)",
        must_hit_columns=[["Album.AlbumId", "Album.ArtistId"], "Artist.ArtistId"],
        tags=["探针:整数除法二"],
    ),
    EvalCase(
        id="Q07",
        query="平均每张发票有几行明细？明细行总数 ÷ 发票总数，保留2位小数。",
        reference_sql=(
            "SELECT ROUND((SELECT COUNT(*) FROM InvoiceLine) * 1.0 / (SELECT COUNT(*) FROM Invoice), 2)"
        ),
        must_hit_columns=[["InvoiceLine.InvoiceLineId", "InvoiceLine.InvoiceId"], "Invoice.InvoiceId"],
        tags=["探针:整数除法二"],
    ),
    EvalCase(
        id="Q08",
        query="各媒体格式的曲目数占全部曲目数的百分比是多少？返回格式名称和百分比（0到100之间的数，保留2位小数）。",
        reference_sql=(
            "SELECT m.Name, ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM Track), 2)"
            " FROM Track t"
            " JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId"
            " GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["MediaType.Name"],
        tags=["探针:整数除法二"],
    ),
]


_FAN_OUT_ECOMMERCE = [
    EvalCase(
        id="F01",
        query="包含至少 3 条商品明细的订单，按下单渠道分别有多少笔？返回下单渠道和订单笔数。",
        reference_sql=(
            "SELECT channel, COUNT(*)"
            " FROM fact_order"
            " WHERE order_id IN (SELECT order_id FROM fact_order_item GROUP BY order_id HAVING COUNT(*) >= 3)"
            " GROUP BY channel"
        ),
        must_hit_columns=["fact_order.channel", "fact_order_item.order_id"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F02",
        query="商品明细金额合计超过 1000 元的订单，按订单状态统计订单笔数和订单实付金额合计（保留两位小数）。返回订单状态、订单笔数、实付金额合计。",
        reference_sql=(
            "SELECT o.order_status, COUNT(*), ROUND(SUM(o.pay_amount), 2)"
            " FROM fact_order o"
            " JOIN (SELECT order_id FROM fact_order_item GROUP BY order_id HAVING SUM(item_amount) > 1000) t ON o.order_id = t.order_id"
            " GROUP BY o.order_status"
        ),
        must_hit_columns=["fact_order_item.item_amount", "fact_order.order_status", "fact_order.pay_amount"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F03",
        query="包含「手机通讯」类商品的订单，按下单渠道统计订单笔数和实付金额合计（保留两位小数）。返回下单渠道、订单笔数、实付金额合计。",
        reference_sql=(
            "SELECT channel, COUNT(*), ROUND(SUM(pay_amount), 2)"
            " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) fact_order"
            " WHERE order_id IN (SELECT i.order_id FROM fact_order_item i JOIN dim_product p ON i.product_id = p.product_id JOIN dim_category c ON p.category_id = c.category_id WHERE c.category_name = '手机通讯')"
            " GROUP BY channel"
        ),
        must_hit_columns=["dim_category.category_name", "fact_order.channel", "fact_order.pay_amount"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F04",
        query="买过「休闲零食」类商品的用户，按会员等级各有多少人？返回会员等级和用户数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*)"
            " FROM dim_user u"
            " WHERE u.user_id IN (SELECT o.user_id FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o JOIN fact_order_item i ON o.order_id = i.order_id JOIN dim_product p ON i.product_id = p.product_id JOIN dim_category c ON p.category_id = c.category_id WHERE c.category_name = '休闲零食')"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_category.category_name", "dim_user.member_level"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F05",
        query="按店铺类型统计订单笔数和售出的商品件数合计。返回店铺类型、订单笔数、商品件数。",
        reference_sql=(
            "SELECT s.shop_type, COUNT(DISTINCT o.order_id), SUM(i.quantity)"
            " FROM fact_order o"
            " JOIN dim_shop s ON o.shop_id = s.shop_id"
            " JOIN fact_order_item i ON o.order_id = i.order_id"
            " GROUP BY s.shop_type"
        ),
        must_hit_columns=["dim_shop.shop_type", "fact_order_item.quantity"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F06",
        query="按下单渠道统计订单实付金额合计和售出的商品件数合计（金额保留两位小数）。返回下单渠道、实付金额合计、商品件数。",
        reference_sql=(
            "SELECT o.channel, ROUND(SUM(o.pay_amount), 2), (SELECT SUM(i.quantity) FROM fact_order_item i JOIN (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o2 ON i.order_id = o2.order_id WHERE o2.channel = o.channel)"
            " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o"
            " GROUP BY o.channel"
        ),
        must_hit_columns=["fact_order.channel", "fact_order.pay_amount", "fact_order_item.quantity"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="N01",
        query="按订单状态统计订单明细的条数和商品件数合计。返回订单状态、明细条数、商品件数。",
        reference_sql=(
            "SELECT o.order_status, COUNT(*), SUM(i.quantity)"
            " FROM fact_order o"
            " JOIN fact_order_item i ON o.order_id = i.order_id"
            " GROUP BY o.order_status"
        ),
        must_hit_columns=["fact_order.order_status", "fact_order_item.quantity"],
        tags=["探针:一对多", "对照"],
    ),
    EvalCase(
        id="N02",
        query="已完成订单中，按一级品类统计售出的商品件数合计。返回一级品类名称和商品件数。",
        reference_sql=(
            "SELECT pc.category_name, SUM(i.quantity)"
            " FROM fact_order o"
            " JOIN fact_order_item i ON o.order_id = i.order_id"
            " JOIN dim_product p ON i.product_id = p.product_id"
            " JOIN dim_category c ON p.category_id = c.category_id"
            " JOIN dim_category pc ON c.parent_category_id = pc.category_id"
            " WHERE o.order_status = '已完成'"
            " GROUP BY pc.category_name"
        ),
        must_hit_columns=["dim_category.parent_category_id", "fact_order_item.quantity", "fact_order.order_status"],
        tags=["探针:一对多", "对照"],
    ),
    EvalCase(
        id="G01",
        query="订单笔数不少于 55 笔的店铺，按所在城市统计各有几家。返回城市和店铺数。",
        reference_sql=(
            "SELECT city, COUNT(*)"
            " FROM dim_shop"
            " WHERE shop_id IN (SELECT shop_id FROM fact_order GROUP BY shop_id HAVING COUNT(*) >= 55)"
            " GROUP BY city"
        ),
        must_hit_columns=["dim_shop.city", "fact_order.shop_id"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="G02",
        query="实付金额超过 3000 元的订单有 5 笔及以上的用户，按性别统计人数。返回性别和用户数。",
        reference_sql=(
            "SELECT gender, COUNT(*)"
            " FROM dim_user"
            " WHERE user_id IN (SELECT user_id FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) fact_order WHERE pay_amount > 3000 GROUP BY user_id HAVING COUNT(*) >= 5)"
            " GROUP BY gender"
        ),
        must_hit_columns=["dim_user.gender", "fact_order.pay_amount"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="G03",
        query="包含华为品牌商品的订单，按订单状态统计订单笔数和优惠金额合计（保留两位小数）。返回订单状态、订单笔数、优惠金额合计。",
        reference_sql=(
            "SELECT order_status, COUNT(*), ROUND(SUM(discount_amount), 2)"
            " FROM fact_order"
            " WHERE order_id IN (SELECT i.order_id FROM fact_order_item i JOIN dim_product p ON i.product_id = p.product_id WHERE p.brand = '华为')"
            " GROUP BY order_status"
        ),
        must_hit_columns=["dim_product.brand", "fact_order.discount_amount"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="G04",
        query="按店铺统计商品数和订单笔数。返回店铺名称、商品数、订单笔数。",
        reference_sql=(
            "SELECT s.shop_name, (SELECT COUNT(*) FROM dim_product p WHERE p.shop_id = s.shop_id), (SELECT COUNT(*) FROM fact_order o WHERE o.shop_id = s.shop_id)"
            " FROM dim_shop s"
        ),
        must_hit_columns=["dim_shop.shop_name", "dim_product.shop_id", "fact_order.shop_id"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="G05",
        query="按会员等级统计订单实付金额合计和购买的商品件数合计（金额保留两位小数）。返回会员等级、实付金额合计、商品件数。",
        reference_sql=(
            "SELECT u.member_level, ROUND(SUM(o.pay_amount), 2), SUM(q.qty)"
            " FROM dim_user u"
            " JOIN (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o ON u.user_id = o.user_id"
            " JOIN (SELECT order_id, SUM(quantity) AS qty FROM fact_order_item GROUP BY order_id) q ON o.order_id = q.order_id"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level", "fact_order.pay_amount", "fact_order_item.quantity"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="M01",
        query="按店铺所在城市统计订单实付金额合计（保留两位小数）。返回城市和金额合计。",
        reference_sql=(
            "SELECT s.city, ROUND(SUM(o.pay_amount), 2)"
            " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o"
            " JOIN dim_shop s ON o.shop_id = s.shop_id"
            " GROUP BY s.city"
        ),
        must_hit_columns=["dim_shop.city", "fact_order.pay_amount"],
        tags=["探针:一对多二", "对照"],
    ),
    EvalCase(
        id="M02",
        query="按品牌统计售出的商品件数和明细金额合计（保留两位小数）。返回品牌、件数、金额合计。",
        reference_sql=(
            "SELECT p.brand, SUM(i.quantity), ROUND(SUM(i.item_amount), 2)"
            " FROM fact_order_item i"
            " JOIN dim_product p ON i.product_id = p.product_id"
            " GROUP BY p.brand"
        ),
        must_hit_columns=["dim_product.brand", "fact_order_item.quantity", "fact_order_item.item_amount"],
        tags=["探针:一对多二", "对照"],
    ),
]


_FAN_OUT_CHINOOK = [
    EvalCase(
        id="F07",
        query="发票明细不少于 9 条的发票，按账单国家统计各有几张。返回国家和发票张数。",
        reference_sql=(
            "SELECT BillingCountry, COUNT(*)"
            " FROM Invoice"
            " WHERE InvoiceId IN (SELECT InvoiceId FROM InvoiceLine GROUP BY InvoiceId HAVING COUNT(*) >= 9)"
            " GROUP BY BillingCountry"
        ),
        must_hit_columns=["Invoice.BillingCountry", "InvoiceLine.InvoiceId"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F08",
        query="包含 Rock 流派曲目的发票，按账单国家统计发票张数和发票金额合计（保留两位小数）。返回国家、发票张数、金额合计。",
        reference_sql=(
            "SELECT BillingCountry, COUNT(*), ROUND(SUM(Total), 2)"
            " FROM Invoice"
            " WHERE InvoiceId IN (SELECT il.InvoiceId FROM InvoiceLine il JOIN Track t ON il.TrackId = t.TrackId JOIN Genre g ON t.GenreId = g.GenreId WHERE g.Name = 'Rock')"
            " GROUP BY BillingCountry"
        ),
        must_hit_columns=["Genre.Name", "Invoice.BillingCountry", "Invoice.Total"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F09",
        query="买过 Jazz 流派曲目的客户，按客户所在国家各有几位？返回国家和客户数。",
        reference_sql=(
            "SELECT Country, COUNT(*)"
            " FROM Customer"
            " WHERE CustomerId IN (SELECT i.CustomerId FROM Invoice i JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId JOIN Track t ON il.TrackId = t.TrackId JOIN Genre g ON t.GenreId = g.GenreId WHERE g.Name = 'Jazz')"
            " GROUP BY Country"
        ),
        must_hit_columns=["Genre.Name", "Customer.Country"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F10",
        query="按客户所在国家统计客户数和发票张数。返回国家、客户数、发票张数。",
        reference_sql=(
            "SELECT c.Country, COUNT(DISTINCT c.CustomerId), COUNT(i.InvoiceId)"
            " FROM Customer c"
            " JOIN Invoice i ON c.CustomerId = i.CustomerId"
            " GROUP BY c.Country"
        ),
        must_hit_columns=["Customer.Country", "Invoice.InvoiceId"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F11",
        query="曲目数不少于 20 首的专辑，按艺术家统计各有几张。返回艺术家名和专辑数。",
        reference_sql=(
            "SELECT ar.Name, COUNT(*)"
            " FROM Album al"
            " JOIN Artist ar ON al.ArtistId = ar.ArtistId"
            " WHERE al.AlbumId IN (SELECT AlbumId FROM Track GROUP BY AlbumId HAVING COUNT(*) >= 20)"
            " GROUP BY ar.ArtistId, ar.Name"
        ),
        must_hit_columns=["Artist.Name", "Track.AlbumId"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="F12",
        query="按账单国家统计发票金额合计和售出的曲目件数合计（金额保留两位小数）。返回国家、金额合计、曲目件数。",
        reference_sql=(
            "SELECT i.BillingCountry, ROUND(SUM(i.Total), 2), (SELECT SUM(il.Quantity) FROM InvoiceLine il JOIN Invoice i2 ON il.InvoiceId = i2.InvoiceId WHERE i2.BillingCountry = i.BillingCountry)"
            " FROM Invoice i"
            " GROUP BY i.BillingCountry"
        ),
        must_hit_columns=["Invoice.BillingCountry", "Invoice.Total", "InvoiceLine.Quantity"],
        tags=["探针:一对多"],
    ),
    EvalCase(
        id="N03",
        query="按流派统计售出的曲目件数合计。返回流派名称和件数。",
        reference_sql=(
            "SELECT g.Name, SUM(il.Quantity)"
            " FROM InvoiceLine il"
            " JOIN Track t ON il.TrackId = t.TrackId"
            " JOIN Genre g ON t.GenreId = g.GenreId"
            " GROUP BY g.GenreId, g.Name"
        ),
        must_hit_columns=["Genre.Name", "InvoiceLine.Quantity"],
        tags=["探针:一对多", "对照"],
    ),
    EvalCase(
        id="N04",
        query="每位销售支持员工负责的客户，开出的发票明细一共有多少条？返回员工编号和明细条数。",
        reference_sql=(
            "SELECT c.SupportRepId, COUNT(*)"
            " FROM Customer c"
            " JOIN Invoice i ON c.CustomerId = i.CustomerId"
            " JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId"
            " GROUP BY c.SupportRepId"
        ),
        must_hit_columns=["Customer.SupportRepId", "InvoiceLine.InvoiceLineId"],
        tags=["探针:一对多", "对照"],
    ),
    EvalCase(
        id="G06",
        query="发票金额合计超过 45 的客户，按所在国家统计各有几位。返回国家和客户数。",
        reference_sql=(
            "SELECT Country, COUNT(*)"
            " FROM Customer"
            " WHERE CustomerId IN (SELECT CustomerId FROM Invoice GROUP BY CustomerId HAVING SUM(Total) > 45)"
            " GROUP BY Country"
        ),
        must_hit_columns=["Customer.Country", "Invoice.Total"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="G07",
        query="包含 Metal 流派曲目的发票，按开票年份统计发票张数和发票金额合计（保留两位小数）。返回年份、发票张数、金额合计。",
        reference_sql=(
            "SELECT strftime('%Y', InvoiceDate), COUNT(*), ROUND(SUM(Total), 2)"
            " FROM Invoice"
            " WHERE InvoiceId IN (SELECT il.InvoiceId FROM InvoiceLine il JOIN Track t ON il.TrackId = t.TrackId JOIN Genre g ON t.GenreId = g.GenreId WHERE g.Name = 'Metal')"
            " GROUP BY strftime('%Y', InvoiceDate)"
        ),
        must_hit_columns=["Genre.Name", "Invoice.InvoiceDate", "Invoice.Total"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="G08",
        query="按艺术家统计专辑数和曲目总时长（分钟，保留一位小数），只统计有专辑的艺术家。返回艺术家名、专辑数、总时长。",
        reference_sql=(
            "SELECT ar.Name, COUNT(DISTINCT al.AlbumId), ROUND(SUM(t.Milliseconds) / 60000.0, 1)"
            " FROM Artist ar"
            " JOIN Album al ON ar.ArtistId = al.ArtistId"
            " JOIN Track t ON al.AlbumId = t.AlbumId"
            " GROUP BY ar.ArtistId, ar.Name"
        ),
        must_hit_columns=["Artist.Name", "Album.AlbumId", "Track.Milliseconds"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="G09",
        query="每位销售支持员工负责的客户数，以及这些客户的发票金额合计（保留两位小数）。返回员工编号、客户数、金额合计。",
        reference_sql=(
            "SELECT c.SupportRepId, COUNT(DISTINCT c.CustomerId), ROUND(SUM(i.Total), 2)"
            " FROM Customer c"
            " JOIN Invoice i ON c.CustomerId = i.CustomerId"
            " GROUP BY c.SupportRepId"
        ),
        must_hit_columns=["Customer.SupportRepId", "Invoice.Total"],
        tags=["探针:一对多二"],
    ),
    EvalCase(
        id="M03",
        query="按媒体类型统计销售额（单价乘数量的合计，保留两位小数）。返回媒体类型名称和销售额。",
        reference_sql=(
            "SELECT m.Name, ROUND(SUM(il.UnitPrice * il.Quantity), 2)"
            " FROM InvoiceLine il"
            " JOIN Track t ON il.TrackId = t.TrackId"
            " JOIN MediaType m ON t.MediaTypeId = m.MediaTypeId"
            " GROUP BY m.MediaTypeId, m.Name"
        ),
        must_hit_columns=["MediaType.Name", "InvoiceLine.UnitPrice", "InvoiceLine.Quantity"],
        tags=["探针:一对多二", "对照"],
    ),
    EvalCase(
        id="M04",
        query="按流派统计曲目被收录进歌单的次数。返回流派名称和次数。",
        reference_sql=(
            "SELECT g.Name, COUNT(*)"
            " FROM PlaylistTrack pt"
            " JOIN Track t ON pt.TrackId = t.TrackId"
            " JOIN Genre g ON t.GenreId = g.GenreId"
            " GROUP BY g.GenreId, g.Name"
        ),
        must_hit_columns=["Genre.Name", "PlaylistTrack.TrackId"],
        tags=["探针:一对多二", "对照"],
    ),
]


FAN_OUT_SQL = {
    "F01": (
        "SELECT o.channel, COUNT(*)"
        " FROM fact_order o"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " WHERE o.order_id IN (SELECT order_id FROM fact_order_item GROUP BY order_id HAVING COUNT(*) >= 3)"
        " GROUP BY o.channel"
    ),
    "F02": (
        "SELECT o.order_status, COUNT(*), ROUND(SUM(o.pay_amount), 2)"
        " FROM fact_order o"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " WHERE o.order_id IN (SELECT order_id FROM fact_order_item GROUP BY order_id HAVING SUM(item_amount) > 1000)"
        " GROUP BY o.order_status"
    ),
    "F03": (
        "SELECT o.channel, COUNT(*), ROUND(SUM(o.pay_amount), 2)"
        " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " JOIN dim_product p ON i.product_id = p.product_id"
        " JOIN dim_category c ON p.category_id = c.category_id"
        " WHERE c.category_name = '手机通讯'"
        " GROUP BY o.channel"
    ),
    "F04": (
        "SELECT u.member_level, COUNT(*)"
        " FROM dim_user u"
        " JOIN (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o ON u.user_id = o.user_id"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " JOIN dim_product p ON i.product_id = p.product_id"
        " JOIN dim_category c ON p.category_id = c.category_id"
        " WHERE c.category_name = '休闲零食'"
        " GROUP BY u.member_level"
    ),
    "F05": (
        "SELECT s.shop_type, COUNT(*), SUM(i.quantity)"
        " FROM fact_order o"
        " JOIN dim_shop s ON o.shop_id = s.shop_id"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " GROUP BY s.shop_type"
    ),
    "F06": (
        "SELECT o.channel, ROUND(SUM(o.pay_amount), 2), SUM(i.quantity)"
        " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " GROUP BY o.channel"
    ),
    "F07": (
        "SELECT i.BillingCountry, COUNT(*)"
        " FROM Invoice i"
        " JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId"
        " WHERE i.InvoiceId IN (SELECT InvoiceId FROM InvoiceLine GROUP BY InvoiceId HAVING COUNT(*) >= 9)"
        " GROUP BY i.BillingCountry"
    ),
    "F08": (
        "SELECT i.BillingCountry, COUNT(*), ROUND(SUM(i.Total), 2)"
        " FROM Invoice i"
        " JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId"
        " JOIN Track t ON il.TrackId = t.TrackId"
        " JOIN Genre g ON t.GenreId = g.GenreId"
        " WHERE g.Name = 'Rock'"
        " GROUP BY i.BillingCountry"
    ),
    "F09": (
        "SELECT c.Country, COUNT(*)"
        " FROM Customer c"
        " JOIN Invoice i ON c.CustomerId = i.CustomerId"
        " JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId"
        " JOIN Track t ON il.TrackId = t.TrackId"
        " JOIN Genre g ON t.GenreId = g.GenreId"
        " WHERE g.Name = 'Jazz'"
        " GROUP BY c.Country"
    ),
    "F10": (
        "SELECT c.Country, COUNT(*), COUNT(i.InvoiceId)"
        " FROM Customer c"
        " JOIN Invoice i ON c.CustomerId = i.CustomerId"
        " GROUP BY c.Country"
    ),
    "F11": (
        "SELECT ar.Name, COUNT(*)"
        " FROM Album al"
        " JOIN Artist ar ON al.ArtistId = ar.ArtistId"
        " JOIN Track t ON t.AlbumId = al.AlbumId"
        " WHERE al.AlbumId IN (SELECT AlbumId FROM Track GROUP BY AlbumId HAVING COUNT(*) >= 20)"
        " GROUP BY ar.ArtistId, ar.Name"
    ),
    "F12": (
        "SELECT i.BillingCountry, ROUND(SUM(i.Total), 2), SUM(il.Quantity)"
        " FROM Invoice i"
        " JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId"
        " GROUP BY i.BillingCountry"
    ),
    "G01": (
        "SELECT s.city, COUNT(*)"
        " FROM dim_shop s"
        " JOIN fact_order o ON s.shop_id = o.shop_id"
        " WHERE s.shop_id IN (SELECT shop_id FROM fact_order GROUP BY shop_id HAVING COUNT(*) >= 55)"
        " GROUP BY s.city"
    ),
    "G02": (
        "SELECT u.gender, COUNT(*)"
        " FROM dim_user u"
        " JOIN (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o ON u.user_id = o.user_id"
        " WHERE o.pay_amount > 3000 AND u.user_id IN (SELECT user_id FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) fact_order WHERE pay_amount > 3000 GROUP BY user_id HAVING COUNT(*) >= 5)"
        " GROUP BY u.gender"
    ),
    "G03": (
        "SELECT o.order_status, COUNT(DISTINCT o.order_id), ROUND(SUM(o.discount_amount), 2)"
        " FROM fact_order o"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " JOIN dim_product p ON i.product_id = p.product_id"
        " WHERE p.brand = '华为'"
        " GROUP BY o.order_status"
    ),
    "G04": (
        "SELECT s.shop_name, COUNT(DISTINCT p.product_id), COUNT(o.order_id)"
        " FROM dim_shop s"
        " JOIN dim_product p ON s.shop_id = p.shop_id"
        " JOIN fact_order o ON s.shop_id = o.shop_id"
        " GROUP BY s.shop_id, s.shop_name"
    ),
    "G05": (
        "SELECT u.member_level, ROUND(SUM(o.pay_amount), 2), SUM(i.quantity)"
        " FROM dim_user u"
        " JOIN (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o ON u.user_id = o.user_id"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " GROUP BY u.member_level"
    ),
    "G06": (
        "SELECT c.Country, COUNT(*)"
        " FROM Customer c"
        " JOIN Invoice i ON c.CustomerId = i.CustomerId"
        " WHERE c.CustomerId IN (SELECT CustomerId FROM Invoice GROUP BY CustomerId HAVING SUM(Total) > 45)"
        " GROUP BY c.Country"
    ),
    "G07": (
        "SELECT strftime('%Y', i.InvoiceDate), COUNT(DISTINCT i.InvoiceId), ROUND(SUM(i.Total), 2)"
        " FROM Invoice i"
        " JOIN InvoiceLine il ON i.InvoiceId = il.InvoiceId"
        " JOIN Track t ON il.TrackId = t.TrackId"
        " JOIN Genre g ON t.GenreId = g.GenreId"
        " WHERE g.Name = 'Metal'"
        " GROUP BY 1"
    ),
    "G08": (
        "SELECT ar.Name, COUNT(al.AlbumId), ROUND(SUM(t.Milliseconds) / 60000.0, 1)"
        " FROM Artist ar"
        " JOIN Album al ON ar.ArtistId = al.ArtistId"
        " JOIN Track t ON al.AlbumId = t.AlbumId"
        " GROUP BY ar.ArtistId, ar.Name"
    ),
    "G09": (
        "SELECT c.SupportRepId, COUNT(c.CustomerId), ROUND(SUM(i.Total), 2)"
        " FROM Customer c"
        " JOIN Invoice i ON c.CustomerId = i.CustomerId"
        " GROUP BY c.SupportRepId"
    ),
}


def _integer_division(sql: str) -> str:
    """把浮点除法改回整数除法：参考 SQL 里只在除法处出现 * 1.0 和 100.0。"""
    return sql.replace(" * 1.0", "").replace("100.0", "100")




# ---------------------------------------------------------------------------
# 每组前 N 和窗口函数（第六套留出集之后）。运行记录里第一批的题号是 P01–P15、Q01–Q02，收进来时改成
# K01–K15、L01–L02（P、Q 和整数除法探针撞号）；第二批的 Q03、Q04 改成 L03、L04。
# ---------------------------------------------------------------------------

_TOPN_ECOMMERCE = [
    EvalCase(
        id="K01",
        query="每个城市里，累计实付金额最高的 2 位用户是谁？按用户所在城市分，列出城市、用户编号和实付金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT city, user_id, amt"
            " FROM (SELECT u.city, o.user_id, ROUND(SUM(o.pay_amount), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY u.city ORDER BY SUM(o.pay_amount) DESC) AS rn FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o JOIN dim_user u ON u.user_id = o.user_id GROUP BY u.city, o.user_id)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["dim_user.city", "fact_order.pay_amount"],
        tags=["探针:每组前N"],
        note="口径定下来（实付、消费默认只算已付款的订单）之后改了参考答案。原先按全部订单算，模型三个版本都用用户汇总表的 total_pay_amount、被判错——那个字段正好是已付款订单的合计，模型是对的，错的是参考答案。",
    ),
    EvalCase(
        id="K02",
        query="每种店铺类型里，订单笔数最多的是哪家店铺？列出店铺类型、店铺名称和订单笔数。",
        reference_sql=(
            "SELECT shop_type, shop_name, cnt"
            " FROM (SELECT s.shop_type, s.shop_name, COUNT(*) AS cnt, ROW_NUMBER() OVER (PARTITION BY s.shop_type ORDER BY COUNT(*) DESC) AS rn FROM fact_order o JOIN dim_shop s ON s.shop_id = o.shop_id GROUP BY s.shop_type, s.shop_id, s.shop_name)"
            " WHERE rn = 1"
        ),
        must_hit_columns=["dim_shop.shop_type", "dim_shop.shop_name"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K03",
        query="每个会员等级里，累计实付金额排前 3 的用户是谁？按用户汇总表算，列出会员等级、用户编号和累计实付金额。",
        reference_sql=(
            "SELECT member_level, user_id, total_pay_amount"
            " FROM (SELECT u.member_level, s.user_id, s.total_pay_amount, ROW_NUMBER() OVER (PARTITION BY u.member_level ORDER BY s.total_pay_amount DESC) AS rn FROM dws_user_summary s JOIN dim_user u ON u.user_id = s.user_id)"
            " WHERE rn <= 3"
        ),
        must_hit_columns=["dim_user.member_level", "dws_user_summary.total_pay_amount"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K04",
        query="每种支付渠道里，单笔支付金额最大的 2 笔支付是哪几笔？列出支付渠道、支付编号和支付金额。",
        reference_sql=(
            "SELECT pay_channel, payment_id, pay_amount"
            " FROM (SELECT pay_channel, payment_id, pay_amount, ROW_NUMBER() OVER (PARTITION BY pay_channel ORDER BY pay_amount DESC) AS rn FROM fact_payment)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["fact_payment.pay_channel", "fact_payment.pay_amount"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K05",
        query="每个下单渠道里，实付金额最高的 2 笔订单是哪几笔？列出下单渠道、订单编号和实付金额。",
        reference_sql=(
            "SELECT channel, order_id, pay_amount"
            " FROM (SELECT channel, order_id, pay_amount, ROW_NUMBER() OVER (PARTITION BY channel ORDER BY pay_amount DESC) AS rn FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) fact_order)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["fact_order.channel", "fact_order.pay_amount"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="L01",
        query="累计实付金额最高的 5 位用户是谁？按订单表算，列出用户编号和实付金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT user_id, ROUND(SUM(pay_amount), 2)"
            " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) fact_order"
            " GROUP BY user_id"
            " ORDER BY SUM(pay_amount) DESC LIMIT 5"
        ),
        must_hit_columns=["fact_order.pay_amount"],
        tags=["探针:每组前N", "对照"],
    ),
    EvalCase(
        id="S01",
        query="按下单日期看每天的订单笔数，哪一天比前一天多得最多？列出日期和比前一天多了几笔。",
        reference_sql=(
            "SELECT d, cnt - prev"
            " FROM (SELECT d, cnt, LAG(cnt) OVER (ORDER BY d) AS prev FROM (SELECT DATE(create_time) AS d, COUNT(*) AS cnt FROM fact_order GROUP BY DATE(create_time)))"
            " WHERE prev IS NOT NULL"
            " ORDER BY cnt - prev DESC LIMIT 1"
        ),
        must_hit_columns=["fact_order.create_time"],
        tags=["探针:每组前N", "窗口筛选"],
    ),
    EvalCase(
        id="K10",
        query="每个一级类目里，卖出件数最多的 2 个品牌是哪两个？已取消的订单不算。列出一级类目名称、品牌和件数。",
        reference_sql=(
            "SELECT cat, brand, qty"
            " FROM (SELECT c1.category_name AS cat, p.brand, SUM(i.quantity) AS qty, ROW_NUMBER() OVER (PARTITION BY c1.category_id ORDER BY SUM(i.quantity) DESC) AS rn FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c2 ON c2.category_id = p.category_id JOIN dim_category c1 ON c1.category_id = c2.parent_category_id WHERE o.order_status <> '已取消' GROUP BY c1.category_id, c1.category_name, p.brand)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["dim_product.brand", "dim_category.parent_category_id", "fact_order_item.quantity"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K11",
        query="按用户所在省份分，每个省份的用户在哪 2 家店铺花的实付金额最多？列出省份、店铺名称和实付金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT province, shop_name, amt"
            " FROM (SELECT u.province, s.shop_name, ROUND(SUM(o.pay_amount), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY u.province ORDER BY SUM(o.pay_amount) DESC) AS rn FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o JOIN dim_user u ON u.user_id = o.user_id JOIN dim_shop s ON s.shop_id = o.shop_id GROUP BY u.province, s.shop_id, s.shop_name)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["dim_user.province", "dim_shop.shop_name", "fact_order.pay_amount"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K12",
        query="每个注册渠道来的用户，买的件数最多的 2 个二级类目是哪两个？列出注册渠道、二级类目名称和件数。",
        reference_sql=(
            "SELECT ch, cat, qty"
            " FROM (SELECT u.register_channel AS ch, c.category_name AS cat, SUM(i.quantity) AS qty, ROW_NUMBER() OVER (PARTITION BY u.register_channel ORDER BY SUM(i.quantity) DESC) AS rn FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id JOIN dim_user u ON u.user_id = o.user_id JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c ON c.category_id = p.category_id GROUP BY u.register_channel, c.category_id, c.category_name)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["dim_user.register_channel", "dim_category.category_name", "fact_order_item.quantity"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K13",
        query="按店铺所在城市分，每个城市卖得最多的品牌是哪个（按商品明细金额算）？列出城市、品牌和明细金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT city, brand, amt"
            " FROM (SELECT s.city, p.brand, ROUND(SUM(i.item_amount), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY s.city ORDER BY SUM(i.item_amount) DESC) AS rn FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id JOIN dim_shop s ON s.shop_id = o.shop_id JOIN dim_product p ON p.product_id = i.product_id GROUP BY s.city, p.brand)"
            " WHERE rn = 1"
        ),
        must_hit_columns=["dim_shop.city", "dim_product.brand", "fact_order_item.item_amount"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="R01",
        query="按用户所在省份分，每个省份的用户买的件数最多的 2 个品牌是哪两个？已取消的订单不算。列出省份、品牌和件数。",
        reference_sql=(
            "SELECT province, brand, qty"
            " FROM (SELECT u.province, p.brand, SUM(i.quantity) AS qty, ROW_NUMBER() OVER (PARTITION BY u.province ORDER BY SUM(i.quantity) DESC) AS rn FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id JOIN dim_user u ON u.user_id = o.user_id JOIN dim_product p ON p.product_id = i.product_id WHERE o.order_status <> '已取消' GROUP BY u.province, p.brand)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["dim_user.province", "dim_product.brand", "fact_order_item.quantity"],
        tags=["探针:每组前N二"],
    ),
    EvalCase(
        id="R02",
        query="每种店铺类型里，退款金额合计最高的 2 家店铺是哪两家？列出店铺类型、店铺名称和退款金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT shop_type, shop_name, amt"
            " FROM (SELECT s.shop_type, s.shop_name, ROUND(SUM(r.refund_amount), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY s.shop_type ORDER BY SUM(r.refund_amount) DESC) AS rn FROM fact_refund r JOIN fact_order o ON o.order_id = r.order_id JOIN dim_shop s ON s.shop_id = o.shop_id GROUP BY s.shop_type, s.shop_id, s.shop_name)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["dim_shop.shop_type", "dim_shop.shop_name", "fact_refund.refund_amount"],
        tags=["探针:每组前N二"],
    ),
    EvalCase(
        id="R03",
        query="每个年龄段的用户，浏览次数最多的 2 个一级类目是哪两个？列出年龄段、一级类目名称和浏览次数。",
        reference_sql=(
            "SELECT age_group, cat, cnt"
            " FROM (SELECT u.age_group, c1.category_name AS cat, COUNT(*) AS cnt, ROW_NUMBER() OVER (PARTITION BY u.age_group ORDER BY COUNT(*) DESC) AS rn FROM fact_user_behavior b JOIN dim_user u ON u.user_id = b.user_id JOIN dim_product p ON p.product_id = b.product_id JOIN dim_category c2 ON c2.category_id = p.category_id JOIN dim_category c1 ON c1.category_id = c2.parent_category_id WHERE b.behavior_type = '浏览' GROUP BY u.age_group, c1.category_id, c1.category_name)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["dim_user.age_group", "dim_category.parent_category_id", "fact_user_behavior.behavior_type"],
        tags=["探针:每组前N二"],
    ),
    EvalCase(
        id="W01",
        query="按店铺日汇总表看，每家店铺有多少天的销售额（GMV）比自己前一天高？每家店铺的第一天不算。列出店铺名称和天数。",
        reference_sql=(
            "SELECT s.shop_name, COUNT(*)"
            " FROM (SELECT shop_id, gmv, LAG(gmv) OVER (PARTITION BY shop_id ORDER BY stat_date) AS prev FROM dws_shop_daily) d"
            " JOIN dim_shop s ON s.shop_id = d.shop_id"
            " WHERE d.prev IS NOT NULL AND d.gmv > d.prev"
            " GROUP BY s.shop_id, s.shop_name"
        ),
        must_hit_columns=["dws_shop_daily.gmv", "dws_shop_daily.stat_date", "dim_shop.shop_name"],
        tags=["探针:每组前N二", "窗口筛选"],
    ),
    EvalCase(
        id="W02",
        query="每位用户按下单时间排的第二笔订单，比第一笔订单的实付金额多出多少？多出最多的 3 位用户是谁？只有一笔订单的用户不算。列出用户编号和多出的金额（保留两位小数）。",
        reference_sql=(
            "SELECT user_id, ROUND(d, 2)"
            " FROM (SELECT user_id, pay_amount - LAG(pay_amount) OVER (PARTITION BY user_id ORDER BY create_time, order_id) AS d, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY create_time, order_id) AS rn FROM fact_order)"
            " WHERE rn = 2"
            " ORDER BY d DESC LIMIT 3"
        ),
        must_hit_columns=["fact_order.create_time", "fact_order.pay_amount"],
        tags=["探针:每组前N二", "窗口筛选"],
    ),
    EvalCase(
        id="L03",
        query="退款金额合计最高的 3 个退款原因是哪些？列出退款原因和退款金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT refund_reason, ROUND(SUM(refund_amount), 2)"
            " FROM fact_refund"
            " GROUP BY refund_reason"
            " ORDER BY SUM(refund_amount) DESC LIMIT 3"
        ),
        must_hit_columns=["fact_refund.refund_reason", "fact_refund.refund_amount"],
        tags=["探针:每组前N二", "对照"],
    ),
]

_TOPN_CHINOOK = [
    EvalCase(
        id="K06",
        query="每种媒体类型里，时长最长的 2 首曲目是哪两首？列出媒体类型名称、曲目名称和时长（毫秒）。",
        reference_sql=(
            "SELECT mt, name, ms"
            " FROM (SELECT m.Name AS mt, t.Name AS name, t.Milliseconds AS ms, ROW_NUMBER() OVER (PARTITION BY t.MediaTypeId ORDER BY t.Milliseconds DESC) AS rn FROM Track t JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["MediaType.Name", "Track.Milliseconds"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K07",
        query="每位销售支持员工负责的客户里，消费总额最高的 2 位客户是谁？列出员工编号、客户编号和消费总额（保留两位小数）。",
        reference_sql=(
            "SELECT rep, cid, amt"
            " FROM (SELECT c.SupportRepId AS rep, c.CustomerId AS cid, ROUND(SUM(i.Total), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY c.SupportRepId ORDER BY SUM(i.Total) DESC) AS rn FROM Customer c JOIN Invoice i ON i.CustomerId = c.CustomerId GROUP BY c.SupportRepId, c.CustomerId)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["Customer.SupportRepId", "Invoice.Total"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K08",
        query="每一年里，发票金额合计排前 3 的账单国家是哪几个？列出年份、国家和金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT y, country, amt"
            " FROM (SELECT strftime('%Y', InvoiceDate) AS y, BillingCountry AS country, ROUND(SUM(Total), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY strftime('%Y', InvoiceDate) ORDER BY SUM(Total) DESC) AS rn FROM Invoice GROUP BY 1, 2)"
            " WHERE rn <= 3"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.BillingCountry", "Invoice.Total"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K09",
        query="每种媒体类型里，文件最大的 3 首曲目是哪几首？列出媒体类型名称、曲目名称和文件大小（字节）。",
        reference_sql=(
            "SELECT mt, name, b"
            " FROM (SELECT m.Name AS mt, t.Name AS name, t.Bytes AS b, ROW_NUMBER() OVER (PARTITION BY t.MediaTypeId ORDER BY t.Bytes DESC) AS rn FROM Track t JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId)"
            " WHERE rn <= 3"
        ),
        must_hit_columns=["MediaType.Name", "Track.Bytes"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="L02",
        query="曲目数最多的 3 个流派是哪几个？列出流派名称和曲目数。",
        reference_sql=(
            "SELECT g.Name, COUNT(*)"
            " FROM Track t"
            " JOIN Genre g ON g.GenreId = t.GenreId"
            " GROUP BY g.GenreId, g.Name"
            " ORDER BY COUNT(*) DESC LIMIT 3"
        ),
        must_hit_columns=["Genre.Name"],
        tags=["探针:每组前N", "对照"],
    ),
    EvalCase(
        id="S02",
        query="按开票年份看发票金额合计，每一年比上一年多了或少了多少？第一年不用比。列出年份和变化金额（保留两位小数，少了是负数）。",
        reference_sql=(
            "SELECT y, ROUND(s - prev, 2)"
            " FROM (SELECT y, s, LAG(s) OVER (ORDER BY y) AS prev FROM (SELECT strftime('%Y', InvoiceDate) AS y, SUM(Total) AS s FROM Invoice GROUP BY 1))"
            " WHERE prev IS NOT NULL"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["探针:每组前N", "窗口筛选"],
    ),
    EvalCase(
        id="S03",
        query="按开票月份看发票金额合计，哪 3 个月比上个月涨得最多？第一个月不用比。列出月份（年-月）和涨了多少（保留两位小数）。",
        reference_sql=(
            "SELECT m, ROUND(s - prev, 2)"
            " FROM (SELECT m, s, LAG(s) OVER (ORDER BY m) AS prev FROM (SELECT strftime('%Y-%m', InvoiceDate) AS m, SUM(Total) AS s FROM Invoice GROUP BY 1))"
            " WHERE prev IS NOT NULL"
            " ORDER BY s - prev DESC LIMIT 3"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Invoice.Total"],
        tags=["探针:每组前N", "窗口筛选"],
    ),
    EvalCase(
        id="K14",
        query="每位销售支持员工负责的客户，买得最多的 2 个音乐流派是哪两个（按购买份数算）？列出员工编号、流派名称和份数。",
        reference_sql=(
            "SELECT rep, genre, qty"
            " FROM (SELECT c.SupportRepId AS rep, g.Name AS genre, SUM(il.Quantity) AS qty, ROW_NUMBER() OVER (PARTITION BY c.SupportRepId ORDER BY SUM(il.Quantity) DESC) AS rn FROM InvoiceLine il JOIN Invoice i ON i.InvoiceId = il.InvoiceId JOIN Customer c ON c.CustomerId = i.CustomerId JOIN Track t ON t.TrackId = il.TrackId JOIN Genre g ON g.GenreId = t.GenreId GROUP BY c.SupportRepId, g.GenreId, g.Name)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["Customer.SupportRepId", "Genre.Name", "InvoiceLine.Quantity"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="K15",
        query="每一年里，销售额最高的艺术家是谁（按发票明细的单价乘数量算）？列出年份、艺术家名和销售额（保留两位小数）。",
        reference_sql=(
            "SELECT y, artist, amt"
            " FROM (SELECT strftime('%Y', i.InvoiceDate) AS y, ar.Name AS artist, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY strftime('%Y', i.InvoiceDate) ORDER BY SUM(il.UnitPrice * il.Quantity) DESC) AS rn FROM InvoiceLine il JOIN Invoice i ON i.InvoiceId = il.InvoiceId JOIN Track t ON t.TrackId = il.TrackId JOIN Album al ON al.AlbumId = t.AlbumId JOIN Artist ar ON ar.ArtistId = al.ArtistId GROUP BY 1, ar.ArtistId, ar.Name)"
            " WHERE rn = 1"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Artist.Name", "InvoiceLine.UnitPrice"],
        tags=["探针:每组前N"],
    ),
    EvalCase(
        id="R04",
        query="每一年里，卖出份数最多的 2 个音乐流派是哪两个？列出年份、流派名称和份数。",
        reference_sql=(
            "SELECT y, genre, qty"
            " FROM (SELECT strftime('%Y', i.InvoiceDate) AS y, g.Name AS genre, SUM(il.Quantity) AS qty, ROW_NUMBER() OVER (PARTITION BY strftime('%Y', i.InvoiceDate) ORDER BY SUM(il.Quantity) DESC) AS rn FROM InvoiceLine il JOIN Invoice i ON i.InvoiceId = il.InvoiceId JOIN Track t ON t.TrackId = il.TrackId JOIN Genre g ON g.GenreId = t.GenreId GROUP BY 1, g.GenreId, g.Name)"
            " WHERE rn <= 2"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Genre.Name", "InvoiceLine.Quantity"],
        tags=["探针:每组前N二"],
    ),
    EvalCase(
        id="R05",
        query="Rock 和 Jazz 这两个流派里，各自销售额最高的是哪张专辑（按发票明细的单价乘数量算）？列出流派名称、专辑名称和销售额（保留两位小数）。",
        reference_sql=(
            "SELECT genre, title, amt"
            " FROM (SELECT g.Name AS genre, al.Title AS title, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS amt, ROW_NUMBER() OVER (PARTITION BY g.GenreId ORDER BY SUM(il.UnitPrice * il.Quantity) DESC) AS rn FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId JOIN Genre g ON g.GenreId = t.GenreId JOIN Album al ON al.AlbumId = t.AlbumId WHERE g.Name IN ('Rock', 'Jazz') GROUP BY g.GenreId, g.Name, al.AlbumId, al.Title)"
            " WHERE rn = 1"
        ),
        must_hit_columns=["Genre.Name", "Album.Title", "InvoiceLine.UnitPrice"],
        tags=["探针:每组前N二"],
    ),
    EvalCase(
        id="W03",
        query="有多少张发票的金额比同一位客户的上一张发票高？每位客户的第一张发票不算。返回一个数。",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM (SELECT Total, LAG(Total) OVER (PARTITION BY CustomerId ORDER BY InvoiceDate, InvoiceId) AS prev FROM Invoice)"
            " WHERE Total > prev"
        ),
        must_hit_columns=["Invoice.Total", "Invoice.CustomerId", "Invoice.InvoiceDate"],
        tags=["探针:每组前N二", "窗口筛选"],
    ),
    EvalCase(
        id="W04",
        query="按账单国家和开票年份汇总发票金额，每一年有多少个国家的金额比自己上一年高？每个国家的第一年不算。列出年份和国家数。",
        reference_sql=(
            "SELECT y, COUNT(*)"
            " FROM (SELECT BillingCountry, strftime('%Y', InvoiceDate) AS y, SUM(Total) AS s, LAG(SUM(Total)) OVER (PARTITION BY BillingCountry ORDER BY strftime('%Y', InvoiceDate)) AS prev FROM Invoice GROUP BY 1, 2)"
            " WHERE s > prev"
            " GROUP BY y"
        ),
        must_hit_columns=["Invoice.BillingCountry", "Invoice.InvoiceDate", "Invoice.Total"],
        tags=["探针:每组前N二", "窗口筛选"],
        note="【存疑】「比自己上一年高」：参考答案和上一个有数据的年份比（LAG），模型按日历上的前一年比（年份 - 1 自连接）；有的国家中间缺一年，两种算法不同。原样保留，不计入规则的归因。",
    ),
    EvalCase(
        id="L04",
        query="销售额最高的 3 张专辑是哪几张（按发票明细的单价乘数量算）？列出专辑名称和销售额（保留两位小数）。",
        reference_sql=(
            "SELECT al.Title, ROUND(SUM(il.UnitPrice * il.Quantity), 2)"
            " FROM InvoiceLine il"
            " JOIN Track t ON t.TrackId = il.TrackId"
            " JOIN Album al ON al.AlbumId = t.AlbumId"
            " GROUP BY al.AlbumId, al.Title"
            " ORDER BY SUM(il.UnitPrice * il.Quantity) DESC LIMIT 3"
        ),
        must_hit_columns=["Album.Title", "InvoiceLine.UnitPrice"],
        tags=["探针:每组前N二", "对照"],
    ),
]

TOPN_WRONG_SQL = {
    "K01": (
        "SELECT u.city, o.user_id, ROUND(SUM(o.pay_amount), 2)"
        " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " GROUP BY u.city, o.user_id"
        " ORDER BY u.city, SUM(o.pay_amount) DESC"
    ),
    "K02": (
        "SELECT s.shop_type, s.shop_name, COUNT(*)"
        " FROM fact_order o"
        " JOIN dim_shop s ON s.shop_id = o.shop_id"
        " GROUP BY s.shop_type, s.shop_id"
        " ORDER BY COUNT(*) DESC LIMIT 1"
    ),
    "K03": (
        "SELECT u.member_level, s.user_id, s.total_pay_amount"
        " FROM dws_user_summary s"
        " JOIN dim_user u ON u.user_id = s.user_id"
        " ORDER BY s.total_pay_amount DESC LIMIT 3"
    ),
    "K04": (
        "SELECT pay_channel, payment_id, pay_amount"
        " FROM fact_payment"
        " ORDER BY pay_amount DESC LIMIT 2"
    ),
    "K05": (
        "SELECT channel, order_id, pay_amount"
        " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) fact_order"
        " ORDER BY pay_amount DESC LIMIT 2"
    ),
    "K06": (
        "SELECT m.Name, t.Name, t.Milliseconds"
        " FROM Track t"
        " JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId"
        " ORDER BY t.Milliseconds DESC LIMIT 2"
    ),
    "K07": (
        "SELECT c.SupportRepId, c.CustomerId, ROUND(SUM(i.Total), 2)"
        " FROM Customer c"
        " JOIN Invoice i ON i.CustomerId = c.CustomerId"
        " GROUP BY c.SupportRepId, c.CustomerId"
        " ORDER BY c.SupportRepId, SUM(i.Total) DESC"
    ),
    "K08": (
        "SELECT strftime('%Y', InvoiceDate), BillingCountry, ROUND(SUM(Total), 2)"
        " FROM Invoice"
        " GROUP BY 1, 2"
        " ORDER BY SUM(Total) DESC LIMIT 3"
    ),
    "K09": (
        "SELECT m.Name, t.Name, t.Bytes"
        " FROM Track t"
        " JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId"
        " ORDER BY t.Bytes DESC LIMIT 3"
    ),
    "K10": (
        "SELECT c1.category_name, p.brand, SUM(i.quantity)"
        " FROM fact_order_item i"
        " JOIN fact_order o ON o.order_id = i.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c2 ON c2.category_id = p.category_id"
        " JOIN dim_category c1 ON c1.category_id = c2.parent_category_id"
        " WHERE o.order_status <> '已取消'"
        " GROUP BY c1.category_id, p.brand"
        " ORDER BY c1.category_name, SUM(i.quantity) DESC"
    ),
    "K11": (
        "SELECT u.province, s.shop_name, ROUND(SUM(o.pay_amount), 2)"
        " FROM (SELECT * FROM fact_order WHERE pay_time IS NOT NULL) o"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " JOIN dim_shop s ON s.shop_id = o.shop_id"
        " GROUP BY u.province, s.shop_id"
        " ORDER BY SUM(o.pay_amount) DESC LIMIT 2"
    ),
    "K12": (
        "SELECT u.register_channel, c.category_name, SUM(i.quantity)"
        " FROM fact_order_item i"
        " JOIN fact_order o ON o.order_id = i.order_id"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " GROUP BY 1, c.category_id"
        " ORDER BY 1, 3 DESC"
    ),
    "K13": (
        "SELECT s.city, p.brand, ROUND(SUM(i.item_amount), 2)"
        " FROM fact_order_item i"
        " JOIN fact_order o ON o.order_id = i.order_id"
        " JOIN dim_shop s ON s.shop_id = o.shop_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " GROUP BY s.city, p.brand"
        " ORDER BY SUM(i.item_amount) DESC LIMIT 1"
    ),
    "K14": (
        "SELECT c.SupportRepId, g.Name, SUM(il.Quantity)"
        " FROM InvoiceLine il"
        " JOIN Invoice i ON i.InvoiceId = il.InvoiceId"
        " JOIN Customer c ON c.CustomerId = i.CustomerId"
        " JOIN Track t ON t.TrackId = il.TrackId"
        " JOIN Genre g ON g.GenreId = t.GenreId"
        " GROUP BY 1, g.GenreId"
        " ORDER BY 1, 3 DESC"
    ),
    "K15": (
        "SELECT strftime('%Y', i.InvoiceDate), ar.Name, ROUND(SUM(il.UnitPrice * il.Quantity), 2)"
        " FROM InvoiceLine il"
        " JOIN Invoice i ON i.InvoiceId = il.InvoiceId"
        " JOIN Track t ON t.TrackId = il.TrackId"
        " JOIN Album al ON al.AlbumId = t.AlbumId"
        " JOIN Artist ar ON ar.ArtistId = al.ArtistId"
        " GROUP BY 1, ar.ArtistId"
        " ORDER BY 3 DESC LIMIT 1"
    ),
    "R01": (
        "SELECT u.province, p.brand, SUM(i.quantity)"
        " FROM fact_order_item i"
        " JOIN fact_order o ON o.order_id = i.order_id"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " WHERE o.order_status <> '已取消'"
        " GROUP BY 1, 2"
        " ORDER BY 1, 3 DESC"
    ),
    "R02": (
        "SELECT s.shop_type, s.shop_name, ROUND(SUM(r.refund_amount), 2)"
        " FROM fact_refund r"
        " JOIN fact_order o ON o.order_id = r.order_id"
        " JOIN dim_shop s ON s.shop_id = o.shop_id"
        " GROUP BY s.shop_type, s.shop_id"
        " ORDER BY SUM(r.refund_amount) DESC LIMIT 2"
    ),
    "R03": (
        "SELECT u.age_group, c1.category_name, COUNT(*)"
        " FROM fact_user_behavior b"
        " JOIN dim_user u ON u.user_id = b.user_id"
        " JOIN dim_product p ON p.product_id = b.product_id"
        " JOIN dim_category c2 ON c2.category_id = p.category_id"
        " JOIN dim_category c1 ON c1.category_id = c2.parent_category_id"
        " WHERE b.behavior_type = '浏览'"
        " GROUP BY 1, c1.category_id"
        " ORDER BY 1, 3 DESC"
    ),
    "R04": (
        "SELECT strftime('%Y', i.InvoiceDate), g.Name, SUM(il.Quantity)"
        " FROM InvoiceLine il"
        " JOIN Invoice i ON i.InvoiceId = il.InvoiceId"
        " JOIN Track t ON t.TrackId = il.TrackId"
        " JOIN Genre g ON g.GenreId = t.GenreId"
        " GROUP BY 1, g.GenreId"
        " ORDER BY 3 DESC LIMIT 2"
    ),
    "R05": (
        "SELECT g.Name, al.Title, ROUND(SUM(il.UnitPrice * il.Quantity), 2)"
        " FROM InvoiceLine il"
        " JOIN Track t ON t.TrackId = il.TrackId"
        " JOIN Genre g ON g.GenreId = t.GenreId"
        " JOIN Album al ON al.AlbumId = t.AlbumId"
        " WHERE g.Name IN ('Rock', 'Jazz')"
        " GROUP BY g.GenreId, al.AlbumId"
        " ORDER BY 3 DESC LIMIT 1"
    ),
}


# ---------------------------------------------------------------------------
# 时间差（第七套留出集之后）。运行记录里对照题的题号是 E01–E03，收进来时改成 Y01–Y03（E 和主题库撞号）。
# ---------------------------------------------------------------------------

_TIME_DIFF_ECOMMERCE = [
    EvalCase(
        id="D01",
        query="下单后超过 1 小时才付款的订单有多少笔？正好 1 小时的不算。",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM fact_order"
            " WHERE pay_time IS NOT NULL AND strftime('%s', pay_time) - strftime('%s', create_time) > 3600"
        ),
        must_hit_columns=["fact_order.create_time", "fact_order.pay_time"],
        tags=["探针:时间差"],
    ),
    EvalCase(
        id="D02",
        query="下单后 1 小时以内付款的订单有多少笔？正好 1 小时的也算。",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM fact_order"
            " WHERE pay_time IS NOT NULL AND strftime('%s', pay_time) - strftime('%s', create_time) <= 3600"
        ),
        must_hit_columns=["fact_order.create_time", "fact_order.pay_time"],
        tags=["探针:时间差"],
    ),
    EvalCase(
        id="D03",
        query="按支付渠道看，下单后超过 30 分钟才完成支付的支付记录各有多少笔？正好 30 分钟的不算。列出支付渠道和笔数。",
        reference_sql=(
            "SELECT p.pay_channel, COUNT(*)"
            " FROM fact_payment p"
            " JOIN fact_order o ON o.order_id = p.order_id"
            " WHERE p.pay_time IS NOT NULL AND strftime('%s', p.pay_time) - strftime('%s', o.create_time) > 1800"
            " GROUP BY p.pay_channel"
        ),
        must_hit_columns=["fact_payment.pay_channel", "fact_payment.pay_time", "fact_order.create_time"],
        tags=["探针:时间差"],
    ),
    EvalCase(
        id="D04",
        query="下单后不到 30 分钟就付款的订单，按下单渠道各有多少笔？正好 30 分钟的不算在内。列出下单渠道和笔数。",
        reference_sql=(
            "SELECT channel, COUNT(*)"
            " FROM fact_order"
            " WHERE pay_time IS NOT NULL AND strftime('%s', pay_time) - strftime('%s', create_time) < 1800"
            " GROUP BY channel"
        ),
        must_hit_columns=["fact_order.channel", "fact_order.create_time", "fact_order.pay_time"],
        tags=["探针:时间差"],
    ),
    EvalCase(
        id="Y01",
        query="付款之后超过 3 天才完成的订单有多少笔？正好 3 天的不算。",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM fact_order"
            " WHERE finish_time IS NOT NULL AND pay_time IS NOT NULL AND strftime('%s', finish_time) - strftime('%s', pay_time) > 3 * 86400"
        ),
        must_hit_columns=["fact_order.pay_time", "fact_order.finish_time"],
        tags=["探针:时间差", "对照"],
    ),
    EvalCase(
        id="Y02",
        query="申请退款后 3 天以内（正好 3 天也算）就办结的退款有多少笔？",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM fact_refund"
            " WHERE finish_time IS NOT NULL AND strftime('%s', finish_time) - strftime('%s', apply_time) <= 3 * 86400"
        ),
        must_hit_columns=["fact_refund.apply_time", "fact_refund.finish_time"],
        tags=["探针:时间差", "对照"],
    ),
    EvalCase(
        id="D05",
        query="按店铺类型看，已付款的订单里下单后 1 小时以上才付款的占百分之几？正好 1 小时的不算 1 小时以上。结果写成百分数的数值，保留两位小数。列出店铺类型和占比。",
        reference_sql=(
            "SELECT s.shop_type, ROUND(100.0 * SUM(strftime('%s', o.pay_time) - strftime('%s', o.create_time) > 3600) / COUNT(*), 2)"
            " FROM fact_order o"
            " JOIN dim_shop s ON s.shop_id = o.shop_id"
            " WHERE o.pay_time IS NOT NULL"
            " GROUP BY s.shop_type"
        ),
        must_hit_columns=["dim_shop.shop_type", "fact_order.create_time", "fact_order.pay_time"],
        tags=["探针:时间差二"],
    ),
    EvalCase(
        id="D06",
        query="下单后 30 分钟到 1 小时之间付款的订单有多少笔？30 分钟和 1 小时两头都算。",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM fact_order"
            " WHERE pay_time IS NOT NULL AND strftime('%s', pay_time) - strftime('%s', create_time) BETWEEN 1800 AND 3600"
        ),
        must_hit_columns=["fact_order.create_time", "fact_order.pay_time"],
        tags=["探针:时间差二"],
    ),
    EvalCase(
        id="D07",
        query="按会员等级分，有多少位用户至少有一笔订单是下单后 30 分钟以内（正好 30 分钟也算）就付了款的？列出会员等级和用户数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(DISTINCT o.user_id)"
            " FROM fact_order o"
            " JOIN dim_user u ON u.user_id = o.user_id"
            " WHERE o.pay_time IS NOT NULL AND strftime('%s', o.pay_time) - strftime('%s', o.create_time) <= 1800"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level", "fact_order.create_time", "fact_order.pay_time"],
        tags=["探针:时间差二"],
    ),
    EvalCase(
        id="Y03",
        query="已付款的订单，从下单到付款平均隔了多少分钟？保留一位小数。",
        reference_sql=(
            "SELECT ROUND(AVG((strftime('%s', pay_time) - strftime('%s', create_time)) / 60.0), 1)"
            " FROM fact_order"
            " WHERE pay_time IS NOT NULL"
        ),
        must_hit_columns=["fact_order.create_time", "fact_order.pay_time"],
        tags=["探针:时间差二", "对照"],
    ),
]

TIME_DIFF_WRONG_SQL = {
    "D01": (
        "SELECT COUNT(*)"
        " FROM fact_order"
        " WHERE pay_time IS NOT NULL AND (julianday(pay_time) - julianday(create_time)) * 24 > 1"
    ),
    "D02": (
        "SELECT COUNT(*)"
        " FROM fact_order"
        " WHERE pay_time IS NOT NULL AND (julianday(pay_time) - julianday(create_time)) * 24 <= 1"
    ),
    "D03": (
        "SELECT p.pay_channel, COUNT(*)"
        " FROM fact_payment p"
        " JOIN fact_order o ON o.order_id = p.order_id"
        " WHERE p.pay_time IS NOT NULL AND (julianday(p.pay_time) - julianday(o.create_time)) * 1440 > 30"
        " GROUP BY p.pay_channel"
    ),
    "D04": (
        "SELECT channel, COUNT(*)"
        " FROM fact_order"
        " WHERE pay_time IS NOT NULL AND (julianday(pay_time) - julianday(create_time)) * 1440 < 30"
        " GROUP BY channel"
    ),
    "D05": (
        "SELECT s.shop_type, ROUND(100.0 * SUM((julianday(o.pay_time) - julianday(o.create_time)) * 24 > 1) / COUNT(*), 2)"
        " FROM fact_order o"
        " JOIN dim_shop s ON s.shop_id = o.shop_id"
        " WHERE o.pay_time IS NOT NULL"
        " GROUP BY s.shop_type"
    ),
    "D06": (
        "SELECT COUNT(*)"
        " FROM fact_order"
        " WHERE pay_time IS NOT NULL AND (julianday(pay_time) - julianday(create_time)) * 1440 BETWEEN 30 AND 60"
    ),
    "D07": (
        "SELECT u.member_level, COUNT(DISTINCT o.user_id)"
        " FROM fact_order o"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " WHERE o.pay_time IS NOT NULL AND (julianday(o.pay_time) - julianday(o.create_time)) * 1440 <= 30"
        " GROUP BY u.member_level"
    ),
}


# ---------------------------------------------------------------------------
# 全都是同一个 X（U）、挂在订单上的金额连到明细（V）（第七套留出集之后）。
# ---------------------------------------------------------------------------

_UNIQ_ECOMMERCE = [
    EvalCase(
        id="U01",
        query="只看已完成的订单，只在一家店铺下过单的用户，按会员等级各有多少位？列出会员等级和用户数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*)"
            " FROM dim_user u"
            " WHERE u.user_id IN (SELECT user_id FROM fact_order WHERE order_status = '已完成' GROUP BY user_id HAVING COUNT(DISTINCT shop_id) = 1)"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level", "fact_order.shop_id", "fact_order.order_status"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="U02",
        query="订单里的商品全都是同一个品牌的那些订单，按下单渠道各有多少笔？列出下单渠道和笔数。",
        reference_sql=(
            "SELECT o.channel, COUNT(*)"
            " FROM fact_order o"
            " WHERE o.order_id IN (SELECT i.order_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id GROUP BY i.order_id HAVING COUNT(DISTINCT p.brand) = 1)"
            " GROUP BY o.channel"
        ),
        must_hit_columns=["dim_product.brand", "fact_order.channel"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="V01",
        query="退款成功的退款金额，按商品所属的一级类目分各是多少？列出一级类目名称和金额，保留两位小数。",
        reference_sql=(
            "SELECT pc.category_name, ROUND(SUM(r.refund_amount), 2)"
            " FROM fact_refund r"
            " JOIN (SELECT DISTINCT i.order_id, c.parent_category_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c ON c.category_id = p.category_id) x ON x.order_id = r.order_id"
            " JOIN dim_category pc ON pc.category_id = x.parent_category_id"
            " WHERE r.refund_status = '退款成功'"
            " GROUP BY pc.category_id, pc.category_name"
        ),
        must_hit_columns=["fact_refund.refund_amount", "fact_refund.refund_status", "dim_category.parent_category_id"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="V02",
        query="用支付宝付的钱（按支付记录的支付金额），按商品所属的二级类目分各是多少？列出二级类目名称和金额，保留两位小数。",
        reference_sql=(
            "SELECT c.category_name, ROUND(SUM(pm.pay_amount), 2)"
            " FROM fact_payment pm"
            " JOIN (SELECT DISTINCT i.order_id, p.category_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id) x ON x.order_id = pm.order_id"
            " JOIN dim_category c ON c.category_id = x.category_id"
            " WHERE pm.pay_channel = '支付宝'"
            " GROUP BY c.category_id, c.category_name"
        ),
        must_hit_columns=["fact_payment.pay_amount", "fact_payment.pay_channel", "dim_category.category_name"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="V03",
        query="按商品所属的一级类目分，退款记录各有多少笔、退款金额各是多少？列出一级类目名称、退款笔数和金额（保留两位小数）。",
        reference_sql=(
            "SELECT pc.category_name, COUNT(*), ROUND(SUM(r.refund_amount), 2)"
            " FROM fact_refund r"
            " JOIN (SELECT DISTINCT i.order_id, c.parent_category_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c ON c.category_id = p.category_id) x ON x.order_id = r.order_id"
            " JOIN dim_category pc ON pc.category_id = x.parent_category_id"
            " GROUP BY pc.category_id, pc.category_name"
        ),
        must_hit_columns=["fact_refund.refund_amount", "dim_category.parent_category_id"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="VC1",
        query="有过退款的订单，它们的商品明细金额按一级类目分各是多少？列出一级类目名称和明细金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT pc.category_name, ROUND(SUM(i.item_amount), 2)"
            " FROM fact_order_item i"
            " JOIN dim_product p ON p.product_id = i.product_id"
            " JOIN dim_category c ON c.category_id = p.category_id"
            " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
            " WHERE i.order_id IN (SELECT order_id FROM fact_refund)"
            " GROUP BY pc.category_id, pc.category_name"
        ),
        must_hit_columns=["fact_order_item.item_amount", "fact_refund.order_id", "dim_category.parent_category_id"],
        tags=["探针:唯一与挂单", "对照"],
    ),
    EvalCase(
        id="U05",
        query="已付款的订单里，买的商品全都来自同一个一级类目的用户，按性别各有多少位？列出性别和用户数。",
        reference_sql=(
            "SELECT u.gender, COUNT(*)"
            " FROM dim_user u"
            " WHERE u.user_id IN (SELECT o.user_id FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c ON c.category_id = p.category_id WHERE o.pay_time IS NOT NULL GROUP BY o.user_id HAVING COUNT(DISTINCT c.parent_category_id) = 1)"
            " GROUP BY u.gender"
        ),
        must_hit_columns=["dim_user.gender", "dim_category.parent_category_id", "fact_order.pay_time"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="U08",
        query="按支付记录看，只用过一种支付渠道付款的用户，按所在省份各有多少位？列出省份和用户数。",
        reference_sql=(
            "SELECT u.province, COUNT(*)"
            " FROM dim_user u"
            " WHERE u.user_id IN (SELECT o.user_id FROM fact_payment p JOIN fact_order o ON o.order_id = p.order_id GROUP BY o.user_id HAVING COUNT(DISTINCT p.pay_channel) = 1)"
            " GROUP BY u.province"
        ),
        must_hit_columns=["dim_user.province", "fact_payment.pay_channel"],
        tags=["探针:唯一与挂单二"],
    ),
    EvalCase(
        id="V04",
        query="还在退款中的退款金额，按商品所属的二级类目分各是多少？列出二级类目名称和金额，保留两位小数。",
        reference_sql=(
            "SELECT c.category_name, ROUND(SUM(r.refund_amount), 2)"
            " FROM fact_refund r"
            " JOIN (SELECT DISTINCT i.order_id, p.category_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id) x ON x.order_id = r.order_id"
            " JOIN dim_category c ON c.category_id = x.category_id"
            " WHERE r.refund_status = '退款中'"
            " GROUP BY c.category_id, c.category_name"
        ),
        must_hit_columns=["fact_refund.refund_status", "fact_refund.refund_amount", "dim_category.category_name"],
        tags=["探针:唯一与挂单二"],
    ),
    EvalCase(
        id="V05",
        query="支付成功的支付记录，按商品所属的一级类目分各有多少笔、金额多少？列出一级类目名称、笔数和金额（保留两位小数）。",
        reference_sql=(
            "SELECT pc.category_name, COUNT(*), ROUND(SUM(pm.pay_amount), 2)"
            " FROM fact_payment pm"
            " JOIN (SELECT DISTINCT i.order_id, c.parent_category_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c ON c.category_id = p.category_id) x ON x.order_id = pm.order_id"
            " JOIN dim_category pc ON pc.category_id = x.parent_category_id"
            " WHERE pm.pay_status = '支付成功'"
            " GROUP BY pc.category_id, pc.category_name"
        ),
        must_hit_columns=["fact_payment.pay_status", "fact_payment.pay_amount", "dim_category.parent_category_id"],
        tags=["探针:唯一与挂单二"],
    ),
    EvalCase(
        id="V06",
        query="有过退款的订单，它们的订单实付金额按商品所属的一级类目分各是多少？列出一级类目名称和实付金额合计（保留两位小数）。",
        reference_sql=(
            "SELECT pc.category_name, ROUND(SUM(o.pay_amount), 2)"
            " FROM fact_order o"
            " JOIN (SELECT DISTINCT i.order_id, c.parent_category_id FROM fact_order_item i JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c ON c.category_id = p.category_id) x ON x.order_id = o.order_id"
            " JOIN dim_category pc ON pc.category_id = x.parent_category_id"
            " WHERE o.order_id IN (SELECT order_id FROM fact_refund)"
            " GROUP BY pc.category_id, pc.category_name"
        ),
        must_hit_columns=["fact_order.pay_amount", "fact_refund.order_id", "dim_category.parent_category_id"],
        tags=["探针:唯一与挂单二"],
    ),
    EvalCase(
        id="VC2",
        query="有过退款的订单里卖出的商品件数，按一级类目分各是多少？列出一级类目名称和件数。",
        reference_sql=(
            "SELECT pc.category_name, SUM(i.quantity)"
            " FROM fact_order_item i"
            " JOIN dim_product p ON p.product_id = i.product_id"
            " JOIN dim_category c ON c.category_id = p.category_id"
            " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
            " WHERE i.order_id IN (SELECT order_id FROM fact_refund)"
            " GROUP BY pc.category_id, pc.category_name"
        ),
        must_hit_columns=["fact_order_item.quantity", "fact_refund.order_id", "dim_category.parent_category_id"],
        tags=["探针:唯一与挂单二", "对照"],
    ),
]

_UNIQ_CHINOOK = [
    EvalCase(
        id="U03",
        query="发票里买的曲目全都属于同一个流派的那些发票，按账单国家各有多少张？列出国家和发票张数。",
        reference_sql=(
            "SELECT i.BillingCountry, COUNT(*)"
            " FROM Invoice i"
            " WHERE i.InvoiceId IN (SELECT il.InvoiceId FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId GROUP BY il.InvoiceId HAVING COUNT(DISTINCT t.GenreId) = 1)"
            " GROUP BY i.BillingCountry"
        ),
        must_hit_columns=["Invoice.BillingCountry", "Track.GenreId"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="U04",
        query="哪些艺术家名下的曲目全都属于同一个流派？只看有曲目的艺术家，列出艺术家名和那个流派的名称。",
        reference_sql=(
            "SELECT ar.Name, MIN(g.Name)"
            " FROM Artist ar"
            " JOIN Album al ON al.ArtistId = ar.ArtistId"
            " JOIN Track t ON t.AlbumId = al.AlbumId"
            " JOIN Genre g ON g.GenreId = t.GenreId"
            " GROUP BY ar.ArtistId, ar.Name"
            " HAVING COUNT(DISTINCT t.GenreId) = 1"
        ),
        must_hit_columns=["Artist.Name", "Genre.Name", "Track.GenreId"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="UC1",
        query="Brazilian Music 和 Grunge 这两个歌单里，各个流派分别收了几首曲目？列出歌单名称、流派名称和曲目数。",
        reference_sql=(
            "SELECT p.Name, g.Name, COUNT(*)"
            " FROM Playlist p"
            " JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId"
            " JOIN Track t ON t.TrackId = pt.TrackId"
            " JOIN Genre g ON g.GenreId = t.GenreId"
            " WHERE p.Name IN ('Brazilian Music', 'Grunge')"
            " GROUP BY p.PlaylistId, p.Name, g.GenreId, g.Name"
        ),
        must_hit_columns=["Playlist.Name", "Genre.Name"],
        tags=["探针:唯一与挂单", "对照"],
    ),
    EvalCase(
        id="U06",
        query="哪些歌单收的曲目全都出自同一位艺术家？列出歌单名称和那位艺术家的名字。",
        reference_sql=(
            "SELECT p.Name, MIN(ar.Name)"
            " FROM Playlist p"
            " JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId"
            " JOIN Track t ON t.TrackId = pt.TrackId"
            " JOIN Album al ON al.AlbumId = t.AlbumId"
            " JOIN Artist ar ON ar.ArtistId = al.ArtistId"
            " GROUP BY p.PlaylistId, p.Name"
            " HAVING COUNT(DISTINCT al.ArtistId) = 1"
        ),
        must_hit_columns=["Playlist.Name", "Artist.Name", "Album.ArtistId"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="U07",
        query="买过的曲目全都是同一种媒体类型的客户，按客户所在国家各有多少位？列出国家和客户数。",
        reference_sql=(
            "SELECT c.Country, COUNT(*)"
            " FROM Customer c"
            " WHERE c.CustomerId IN (SELECT i.CustomerId FROM Invoice i JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId JOIN Track t ON t.TrackId = il.TrackId GROUP BY i.CustomerId HAVING COUNT(DISTINCT t.MediaTypeId) = 1)"
            " GROUP BY c.Country"
        ),
        must_hit_columns=["Customer.Country", "Track.MediaTypeId"],
        tags=["探针:唯一与挂单"],
    ),
    EvalCase(
        id="U09",
        query="买的曲目全都来自同一张专辑的发票，按开票年份各有多少张？列出年份和发票张数。",
        reference_sql=(
            "SELECT strftime('%Y', i.InvoiceDate), COUNT(*)"
            " FROM Invoice i"
            " WHERE i.InvoiceId IN (SELECT il.InvoiceId FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId GROUP BY il.InvoiceId HAVING COUNT(DISTINCT t.AlbumId) = 1)"
            " GROUP BY strftime('%Y', i.InvoiceDate)"
        ),
        must_hit_columns=["Invoice.InvoiceDate", "Track.AlbumId"],
        tags=["探针:唯一与挂单二"],
    ),
    EvalCase(
        id="U10",
        query="买的曲目全都出自同一位艺术家的发票，按那位艺术家统计各有多少张？列出艺术家名和发票张数。",
        reference_sql=(
            "SELECT ar.Name, COUNT(*)"
            " FROM (SELECT il.InvoiceId, MIN(al.ArtistId) AS ArtistId FROM InvoiceLine il JOIN Track t ON t.TrackId = il.TrackId JOIN Album al ON al.AlbumId = t.AlbumId GROUP BY il.InvoiceId HAVING COUNT(DISTINCT al.ArtistId) = 1) x"
            " JOIN Artist ar ON ar.ArtistId = x.ArtistId"
            " GROUP BY ar.ArtistId, ar.Name"
        ),
        must_hit_columns=["Artist.Name", "Album.ArtistId"],
        tags=["探针:唯一与挂单二"],
    ),
    EvalCase(
        id="UC2",
        query="每位销售支持员工负责的客户，按客户所在国家分别有几位？列出员工编号、国家和客户数。",
        reference_sql="SELECT SupportRepId, Country, COUNT(*) FROM Customer GROUP BY SupportRepId, Country",
        must_hit_columns=["Customer.SupportRepId", "Customer.Country"],
        tags=["探针:唯一与挂单二", "对照"],
    ),
]

UNIQ_WRONG_SQL = {
    "U01": (
        "SELECT u.member_level, COUNT(DISTINCT o.user_id)"
        " FROM fact_order o"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " WHERE o.order_status = '已完成'"
        " GROUP BY u.member_level"
        " HAVING COUNT(DISTINCT o.shop_id) >= 1"
    ),
    "U02": (
        "SELECT channel, COUNT(*)"
        " FROM (SELECT o.channel, o.order_id FROM fact_order o JOIN fact_order_item i ON i.order_id = o.order_id JOIN dim_product p ON p.product_id = i.product_id GROUP BY o.channel, o.order_id, p.brand HAVING COUNT(DISTINCT p.brand) = 1)"
        " GROUP BY channel"
    ),
    "U03": (
        "SELECT BillingCountry, COUNT(*)"
        " FROM (SELECT i.BillingCountry, i.InvoiceId FROM Invoice i JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId JOIN Track t ON t.TrackId = il.TrackId GROUP BY i.BillingCountry, i.InvoiceId, t.GenreId HAVING COUNT(DISTINCT t.GenreId) = 1)"
        " GROUP BY BillingCountry"
    ),
    "U04": (
        "SELECT ar.Name, g.Name"
        " FROM Artist ar"
        " JOIN Album al ON al.ArtistId = ar.ArtistId"
        " JOIN Track t ON t.AlbumId = al.AlbumId"
        " JOIN Genre g ON g.GenreId = t.GenreId"
        " GROUP BY ar.ArtistId, ar.Name, g.GenreId, g.Name"
        " HAVING COUNT(DISTINCT t.GenreId) = 1"
    ),
    "V01": (
        "SELECT pc.category_name, ROUND(SUM(r.refund_amount), 2)"
        " FROM fact_refund r"
        " JOIN fact_order_item i ON i.order_id = r.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
        " WHERE r.refund_status = '退款成功'"
        " GROUP BY pc.category_name"
    ),
    "V02": (
        "SELECT c.category_name, ROUND(SUM(pm.pay_amount), 2)"
        " FROM fact_payment pm"
        " JOIN fact_order_item i ON i.order_id = pm.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " WHERE pm.pay_channel = '支付宝'"
        " GROUP BY c.category_name"
    ),
    "V03": (
        "SELECT pc.category_name, COUNT(*), ROUND(SUM(r.refund_amount), 2)"
        " FROM fact_refund r"
        " JOIN fact_order_item i ON i.order_id = r.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
        " GROUP BY pc.category_name"
    ),
    "U05": (
        "SELECT gender, COUNT(DISTINCT user_id)"
        " FROM (SELECT u.gender, o.user_id FROM fact_order o JOIN dim_user u ON u.user_id = o.user_id JOIN fact_order_item i ON i.order_id = o.order_id JOIN dim_product p ON p.product_id = i.product_id JOIN dim_category c ON c.category_id = p.category_id WHERE o.pay_time IS NOT NULL GROUP BY u.gender, o.user_id, c.parent_category_id HAVING COUNT(DISTINCT c.parent_category_id) = 1)"
        " GROUP BY gender"
    ),
    "U06": (
        "SELECT p.Name, ar.Name"
        " FROM Playlist p"
        " JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId"
        " JOIN Track t ON t.TrackId = pt.TrackId"
        " JOIN Album al ON al.AlbumId = t.AlbumId"
        " JOIN Artist ar ON ar.ArtistId = al.ArtistId"
        " GROUP BY p.PlaylistId, p.Name, ar.ArtistId, ar.Name"
        " HAVING COUNT(DISTINCT al.ArtistId) = 1"
    ),
    "U07": (
        "SELECT Country, COUNT(DISTINCT CustomerId)"
        " FROM (SELECT c.Country, c.CustomerId FROM Customer c JOIN Invoice i ON i.CustomerId = c.CustomerId JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId JOIN Track t ON t.TrackId = il.TrackId GROUP BY c.Country, c.CustomerId, t.MediaTypeId HAVING COUNT(DISTINCT t.MediaTypeId) = 1)"
        " GROUP BY Country"
    ),
    "U08": (
        "SELECT province, COUNT(DISTINCT user_id)"
        " FROM (SELECT u.province, u.user_id FROM fact_payment p JOIN fact_order o ON o.order_id = p.order_id JOIN dim_user u ON u.user_id = o.user_id GROUP BY u.province, u.user_id, p.pay_channel HAVING COUNT(DISTINCT p.pay_channel) = 1)"
        " GROUP BY province"
    ),
    "V04": (
        "SELECT c.category_name, ROUND(SUM(r.refund_amount), 2)"
        " FROM fact_refund r"
        " JOIN fact_order_item i ON i.order_id = r.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " WHERE r.refund_status = '退款中'"
        " GROUP BY c.category_name"
    ),
    "V05": (
        "SELECT pc.category_name, COUNT(*), ROUND(SUM(pm.pay_amount), 2)"
        " FROM fact_payment pm"
        " JOIN fact_order_item i ON i.order_id = pm.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
        " WHERE pm.pay_status = '支付成功'"
        " GROUP BY pc.category_name"
    ),
    "V06": (
        "SELECT pc.category_name, ROUND(SUM(o.pay_amount), 2)"
        " FROM fact_order o"
        " JOIN fact_order_item i ON i.order_id = o.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
        " WHERE o.order_id IN (SELECT order_id FROM fact_refund)"
        " GROUP BY pc.category_name"
    ),
    "U09": (
        "SELECT y, COUNT(*)"
        " FROM (SELECT strftime('%Y', i.InvoiceDate) AS y, i.InvoiceId FROM Invoice i JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId JOIN Track t ON t.TrackId = il.TrackId GROUP BY y, i.InvoiceId, t.AlbumId HAVING COUNT(DISTINCT t.AlbumId) = 1)"
        " GROUP BY y"
    ),
    "U10": (
        "SELECT ar.Name, COUNT(DISTINCT il.InvoiceId)"
        " FROM InvoiceLine il"
        " JOIN Track t ON t.TrackId = il.TrackId"
        " JOIN Album al ON al.AlbumId = t.AlbumId"
        " JOIN Artist ar ON ar.ArtistId = al.ArtistId"
        " GROUP BY ar.ArtistId, ar.Name"
        " HAVING COUNT(DISTINCT al.ArtistId) = 1"
    ),
}


# ---------------------------------------------------------------------------
# 口径（2026-10-22 定）：题目没写订单状态时，"买过、已付款、实付、花了多少、消费"只算已付款的订单（pay_time 不为空），
# "订单数"不加条件。WRONG_SQL 是模型常写的错法：不加条件，或者写成 order_status = '已支付'。
# ---------------------------------------------------------------------------

_KOUJING_ECOMMERCE = [
    EvalCase(
        id="J01",
        query="买过「数码电器」类商品的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(DISTINCT o.user_id)"
            " FROM fact_order o"
            " JOIN fact_order_item i ON i.order_id = o.order_id"
            " JOIN dim_product p ON p.product_id = i.product_id"
            " JOIN dim_category c ON c.category_id = p.category_id"
            " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
            " WHERE o.pay_time IS NOT NULL AND pc.category_name = '数码电器'"
        ),
        must_hit_columns=["fact_order.pay_time", "dim_category.category_name"],
        tags=["探针:口径"],
    ),
    EvalCase(
        id="J02",
        query="已付款的订单，按下单渠道分各有多少笔？列出下单渠道和笔数。",
        reference_sql="SELECT channel, COUNT(*) FROM fact_order WHERE pay_time IS NOT NULL GROUP BY channel",
        must_hit_columns=["fact_order.pay_time", "fact_order.channel"],
        tags=["探针:口径"],
    ),
    EvalCase(
        id="J03",
        query="每个城市的用户一共花了多少钱？按用户所在城市分，列出城市和金额，保留两位小数。",
        reference_sql=(
            "SELECT u.city, ROUND(SUM(o.pay_amount), 2)"
            " FROM fact_order o"
            " JOIN dim_user u ON u.user_id = o.user_id"
            " WHERE o.pay_time IS NOT NULL"
            " GROUP BY u.city"
        ),
        must_hit_columns=["dim_user.city", "fact_order.pay_amount"],
        tags=["探针:口径"],
    ),
    EvalCase(
        id="J04",
        query="按订单表算，消费金额最高的 3 位用户是谁？列出用户编号和消费金额（保留两位小数）。",
        reference_sql=(
            "SELECT user_id, ROUND(SUM(pay_amount), 2)"
            " FROM fact_order"
            " WHERE pay_time IS NOT NULL"
            " GROUP BY user_id"
            " ORDER BY SUM(pay_amount) DESC LIMIT 3"
        ),
        must_hit_columns=["fact_order.pay_amount"],
        tags=["探针:口径"],
    ),
    EvalCase(
        id="JC1",
        query="每个下单渠道各有多少笔订单？列出下单渠道和订单数。",
        reference_sql="SELECT channel, COUNT(*) FROM fact_order GROUP BY channel",
        must_hit_columns=["fact_order.channel"],
        tags=["探针:口径", "对照"],
    ),
    EvalCase(
        id="JC2",
        query="订单状态为「已支付」的订单，按下单渠道各有多少笔？列出下单渠道和笔数。",
        reference_sql="SELECT channel, COUNT(*) FROM fact_order WHERE order_status = '已支付' GROUP BY channel",
        must_hit_columns=["fact_order.order_status", "fact_order.channel"],
        tags=["探针:口径", "对照"],
    ),
    EvalCase(
        id="J05",
        query="付过钱的用户，按会员等级各有多少位？列出会员等级和用户数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(DISTINCT o.user_id)"
            " FROM fact_order o"
            " JOIN dim_user u ON u.user_id = o.user_id"
            " WHERE o.pay_time IS NOT NULL"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level", "fact_order.pay_time"],
        tags=["探针:口径二"],
    ),
    EvalCase(
        id="J06",
        query="购买过「彩妆香水」类商品的订单有多少笔？",
        reference_sql=(
            "SELECT COUNT(DISTINCT o.order_id)"
            " FROM fact_order o"
            " JOIN fact_order_item i ON i.order_id = o.order_id"
            " JOIN dim_product p ON p.product_id = i.product_id"
            " JOIN dim_category c ON c.category_id = p.category_id"
            " WHERE o.pay_time IS NOT NULL AND c.category_name = '彩妆香水'"
        ),
        must_hit_columns=["fact_order.pay_time", "dim_category.category_name"],
        tags=["探针:口径二"],
    ),
    EvalCase(
        id="J07",
        query="按店铺类型看，订单的实付金额合计各是多少？列出店铺类型和金额，保留两位小数。",
        reference_sql=(
            "SELECT s.shop_type, ROUND(SUM(o.pay_amount), 2)"
            " FROM fact_order o"
            " JOIN dim_shop s ON s.shop_id = o.shop_id"
            " WHERE o.pay_time IS NOT NULL"
            " GROUP BY s.shop_type"
        ),
        must_hit_columns=["dim_shop.shop_type", "fact_order.pay_amount"],
        tags=["探针:口径二"],
    ),
    EvalCase(
        id="J08",
        query="已付款订单的平均实付金额是多少？保留两位小数。",
        reference_sql="SELECT ROUND(AVG(pay_amount), 2) FROM fact_order WHERE pay_time IS NOT NULL",
        must_hit_columns=["fact_order.pay_amount", "fact_order.pay_time"],
        tags=["探针:口径二"],
    ),
    EvalCase(
        id="JC3",
        query="按会员等级，下单笔数各是多少？列出会员等级和笔数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*)"
            " FROM fact_order o"
            " JOIN dim_user u ON u.user_id = o.user_id"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level"],
        tags=["探针:口径二", "对照"],
    ),
    EvalCase(
        id="JC4",
        query="不论订单状态，全部订单的实付金额字段加起来是多少？保留两位小数。",
        reference_sql="SELECT ROUND(SUM(pay_amount), 2) FROM fact_order",
        must_hit_columns=["fact_order.pay_amount"],
        tags=["探针:口径二", "对照"],
    ),
    EvalCase(
        id="JC5",
        query="已取消的订单，按下单渠道各有多少笔？列出下单渠道和笔数。",
        reference_sql="SELECT channel, COUNT(*) FROM fact_order WHERE order_status = '已取消' GROUP BY channel",
        must_hit_columns=["fact_order.order_status", "fact_order.channel"],
        tags=["探针:口径二", "对照"],
    ),
]

KOUJING_WRONG_SQL = {
    "J01": (
        "SELECT COUNT(DISTINCT o.user_id)"
        " FROM fact_order o"
        " JOIN fact_order_item i ON i.order_id = o.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " JOIN dim_category pc ON pc.category_id = c.parent_category_id"
        " WHERE pc.category_name = '数码电器'"
    ),
    "J02": (
        "SELECT channel, COUNT(*)"
        " FROM fact_order"
        " WHERE order_status = '已支付'"
        " GROUP BY channel"
    ),
    "J03": (
        "SELECT u.city, ROUND(SUM(o.pay_amount), 2)"
        " FROM fact_order o"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " GROUP BY u.city"
    ),
    "J04": (
        "SELECT user_id, ROUND(SUM(pay_amount), 2)"
        " FROM fact_order"
        " GROUP BY user_id"
        " ORDER BY SUM(pay_amount) DESC LIMIT 3"
    ),
    "J05": (
        "SELECT u.member_level, COUNT(DISTINCT o.user_id)"
        " FROM fact_order o"
        " JOIN dim_user u ON u.user_id = o.user_id"
        " WHERE o.order_status = '已支付'"
        " GROUP BY u.member_level"
    ),
    "J06": (
        "SELECT COUNT(DISTINCT o.order_id)"
        " FROM fact_order o"
        " JOIN fact_order_item i ON i.order_id = o.order_id"
        " JOIN dim_product p ON p.product_id = i.product_id"
        " JOIN dim_category c ON c.category_id = p.category_id"
        " WHERE c.category_name = '彩妆香水'"
    ),
    "J07": (
        "SELECT s.shop_type, ROUND(SUM(o.pay_amount), 2)"
        " FROM fact_order o"
        " JOIN dim_shop s ON s.shop_id = o.shop_id"
        " GROUP BY s.shop_type"
    ),
    "J08": (
        "SELECT ROUND(AVG(pay_amount), 2)"
        " FROM fact_order"
        " WHERE order_status = '已支付'"
    ),
}

# ---------------------------------------------------------------------------
# 全称（第八套之后）："那些 X 全都 / 一个都没有……"要对每个对象检查它名下的全部 X，模型常写成
# "存在一个 X 不满足"——按（对象, X）逐对判断，有一对成立就把对象算进来（H8E16）。
# WRONG_SQL 就是这种逐对、存在量词的写法。
# ---------------------------------------------------------------------------

_ALL_ECOMMERCE = [
    EvalCase(
        id="A01",
        query="加购过商品、但加购的那些商品一件都没买过的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM dim_user u"
            " WHERE EXISTS (SELECT 1 FROM fact_user_behavior b WHERE b.user_id = u.user_id AND b.behavior_type = '加购')"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM fact_user_behavior b"
            "   JOIN fact_order_item i ON i.product_id = b.product_id"
            "   JOIN fact_order o ON o.order_id = i.order_id AND o.user_id = b.user_id"
            "   WHERE b.user_id = u.user_id AND b.behavior_type = '加购' AND o.pay_time IS NOT NULL)"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type", "fact_order_item.product_id", "fact_order.pay_time"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A02",
        query="下过的订单全都付了款的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            " SELECT user_id FROM fact_order GROUP BY user_id HAVING SUM(pay_time IS NULL) = 0)"
        ),
        must_hit_columns=["fact_order.pay_time", "fact_order.user_id"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A03",
        query="买过东西、但名下一笔订单都没申请过退款的用户，按会员等级各有多少位？列出会员等级和人数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*) FROM dim_user u"
            " WHERE EXISTS (SELECT 1 FROM fact_order o WHERE o.user_id = u.user_id AND o.pay_time IS NOT NULL)"
            " AND NOT EXISTS (SELECT 1 FROM fact_order o JOIN fact_refund r ON r.order_id = o.order_id WHERE o.user_id = u.user_id)"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level", "fact_refund.order_id", "fact_order.pay_time"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A04",
        query="店里的商品全都在售的店铺有哪些？列出店铺名。",
        reference_sql=(
            "SELECT s.shop_name FROM dim_shop s"
            " JOIN dim_product p ON p.shop_id = s.shop_id"
            " GROUP BY s.shop_id, s.shop_name"
            " HAVING SUM(p.shelf_status <> '在售') = 0"
        ),
        must_hit_columns=["dim_shop.shop_name", "dim_product.shelf_status"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A05",
        query="收藏过的商品全都已经下架了的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            " SELECT b.user_id FROM fact_user_behavior b JOIN dim_product p ON p.product_id = b.product_id"
            " WHERE b.behavior_type = '收藏'"
            " GROUP BY b.user_id HAVING SUM(p.shelf_status <> '已下架') = 0)"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type", "dim_product.shelf_status"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A06",
        query="付过款的订单，每一笔实付金额都超过 500 元的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            " SELECT user_id FROM fact_order WHERE pay_time IS NOT NULL"
            " GROUP BY user_id HAVING MIN(pay_amount) > 500)"
        ),
        must_hit_columns=["fact_order.pay_amount", "fact_order.pay_time"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="AC1",
        query="至少有一件加购的商品还没买过的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(DISTINCT b.user_id) FROM fact_user_behavior b"
            " WHERE b.behavior_type = '加购' AND NOT EXISTS ("
            "   SELECT 1 FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id"
            "   WHERE o.user_id = b.user_id AND i.product_id = b.product_id AND o.pay_time IS NOT NULL)"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type", "fact_order_item.product_id", "fact_order.pay_time"],
        tags=["探针:全称", "对照"],
    ),
    EvalCase(
        id="AC3",
        query="有订单还没付款的用户有多少位？",
        reference_sql="SELECT COUNT(DISTINCT user_id) FROM fact_order WHERE pay_time IS NULL",
        must_hit_columns=["fact_order.pay_time"],
        tags=["探针:全称", "对照"],
    ),
    EvalCase(
        id="A12",
        query="收藏过商品、而且收藏的商品全都买过的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM dim_user u"
            " WHERE EXISTS (SELECT 1"
            " FROM fact_user_behavior b"
            " WHERE b.user_id = u.user_id AND b.behavior_type = '收藏')"
            " AND NOT EXISTS (SELECT 1"
            " FROM fact_user_behavior b"
            " WHERE b.user_id = u.user_id AND b.behavior_type = '收藏'"
            " AND NOT EXISTS (SELECT 1"
            " FROM fact_order_item i"
            " JOIN fact_order o ON o.order_id = i.order_id"
            " WHERE o.user_id = b.user_id AND i.product_id = b.product_id AND o.pay_time IS NOT NULL))"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type", "fact_order_item.product_id", "fact_order.pay_time"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A13",
        query="浏览过商品、但浏览过的商品一件都没加购过的用户，按性别各有多少位？列出性别和人数。",
        reference_sql=(
            "SELECT u.gender, COUNT(*)"
            " FROM dim_user u"
            " WHERE EXISTS (SELECT 1"
            " FROM fact_user_behavior b"
            " WHERE b.user_id = u.user_id AND b.behavior_type = '浏览')"
            " AND NOT EXISTS (SELECT 1"
            " FROM fact_user_behavior b"
            " JOIN fact_user_behavior c ON c.user_id = b.user_id AND c.product_id = b.product_id AND c.behavior_type = '加购'"
            " WHERE b.user_id = u.user_id AND b.behavior_type = '浏览')"
            " GROUP BY u.gender"
        ),
        must_hit_columns=["dim_user.gender", "fact_user_behavior.behavior_type", "fact_user_behavior.product_id"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A14",
        query="店里的商品全都被人收藏过的店铺有几家？",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM dim_shop s"
            " WHERE EXISTS (SELECT 1"
            " FROM dim_product p"
            " WHERE p.shop_id = s.shop_id)"
            " AND NOT EXISTS (SELECT 1"
            " FROM dim_product p"
            " WHERE p.shop_id = s.shop_id"
            " AND NOT EXISTS (SELECT 1"
            " FROM fact_user_behavior b"
            " WHERE b.product_id = p.product_id AND b.behavior_type = '收藏'))"
        ),
        must_hit_columns=["dim_product.shop_id", "fact_user_behavior.behavior_type"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A15",
        query="加购过商品、但加购的商品一件都没收藏过的用户，按会员等级各有多少位？列出会员等级和人数。",
        reference_sql=(
            "SELECT u.member_level, COUNT(*)"
            " FROM dim_user u"
            " WHERE EXISTS (SELECT 1"
            " FROM fact_user_behavior b"
            " WHERE b.user_id = u.user_id AND b.behavior_type = '加购')"
            " AND NOT EXISTS (SELECT 1"
            " FROM fact_user_behavior b"
            " JOIN fact_user_behavior c ON c.user_id = b.user_id AND c.product_id = b.product_id AND c.behavior_type = '收藏'"
            " WHERE b.user_id = u.user_id AND b.behavior_type = '加购')"
            " GROUP BY u.member_level"
        ),
        must_hit_columns=["dim_user.member_level", "fact_user_behavior.behavior_type", "fact_user_behavior.product_id"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="AC4",
        query="至少有一件收藏的商品已经买过的用户有多少位？",
        reference_sql=(
            "SELECT COUNT(DISTINCT b.user_id)"
            " FROM fact_user_behavior b"
            " WHERE b.behavior_type = '收藏'"
            " AND EXISTS (SELECT 1"
            " FROM fact_order_item i"
            " JOIN fact_order o ON o.order_id = i.order_id"
            " WHERE o.user_id = b.user_id AND i.product_id = b.product_id AND o.pay_time IS NOT NULL)"
        ),
        must_hit_columns=["fact_user_behavior.behavior_type", "fact_order_item.product_id", "fact_order.pay_time"],
        tags=["探针:全称", "对照"],
    ),
]

_ALL_CHINOOK = [
    EvalCase(
        id="A07",
        query="有曲目、但一首 Rock 流派的曲目都没有的歌单有哪些？列出歌单编号和名称。",
        reference_sql=(
            "SELECT p.PlaylistId, p.Name FROM Playlist p"
            " WHERE EXISTS (SELECT 1 FROM PlaylistTrack pt WHERE pt.PlaylistId = p.PlaylistId)"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM PlaylistTrack pt JOIN Track t ON t.TrackId = pt.TrackId JOIN Genre g ON g.GenreId = t.GenreId"
            "   WHERE pt.PlaylistId = p.PlaylistId AND g.Name = 'Rock')"
        ),
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "Genre.Name"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A08",
        query="买过的曲目全都是 MPEG audio file 格式的客户有多少位？",
        reference_sql=(
            "SELECT COUNT(*) FROM ("
            " SELECT i.CustomerId FROM Invoice i"
            " JOIN InvoiceLine l ON l.InvoiceId = i.InvoiceId"
            " JOIN Track t ON t.TrackId = l.TrackId"
            " JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId"
            " GROUP BY i.CustomerId HAVING SUM(m.Name <> 'MPEG audio file') = 0)"
        ),
        must_hit_columns=["MediaType.Name", "InvoiceLine.TrackId", "Invoice.CustomerId"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A09",
        query="没有一张发票金额超过 15 的客户有多少位？",
        reference_sql="SELECT COUNT(*) FROM (SELECT CustomerId FROM Invoice GROUP BY CustomerId HAVING MAX(Total) <= 15)",
        must_hit_columns=["Invoice.Total", "Invoice.CustomerId"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A10",
        query="每首曲目都超过 300000 毫秒的专辑有多少张？",
        reference_sql="SELECT COUNT(*) FROM (SELECT AlbumId FROM Track GROUP BY AlbumId HAVING MIN(Milliseconds) > 300000)",
        must_hit_columns=["Track.Milliseconds", "Track.AlbumId"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A11",
        query="买过的曲目里一首 Jazz 流派的都没有的客户，按负责他们的销售支持员工各有多少位？列出员工的名、姓和客户数。",
        reference_sql=(
            "SELECT e.FirstName, e.LastName, COUNT(*) FROM Customer c"
            " JOIN Employee e ON e.EmployeeId = c.SupportRepId"
            " WHERE NOT EXISTS ("
            "   SELECT 1 FROM Invoice i JOIN InvoiceLine l ON l.InvoiceId = i.InvoiceId"
            "   JOIN Track t ON t.TrackId = l.TrackId JOIN Genre g ON g.GenreId = t.GenreId"
            "   WHERE i.CustomerId = c.CustomerId AND g.Name = 'Jazz')"
            " GROUP BY e.EmployeeId, e.FirstName, e.LastName"
        ),
        must_hit_columns=["Customer.SupportRepId", "Genre.Name", "Employee.FirstName"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="AC2",
        query="有 Rock 流派曲目的歌单有多少个？",
        reference_sql=(
            "SELECT COUNT(DISTINCT pt.PlaylistId) FROM PlaylistTrack pt"
            " JOIN Track t ON t.TrackId = pt.TrackId JOIN Genre g ON g.GenreId = t.GenreId"
            " WHERE g.Name = 'Rock'"
        ),
        must_hit_columns=["PlaylistTrack.PlaylistId", "Genre.Name"],
        tags=["探针:全称", "对照"],
    ),
    EvalCase(
        id="A16",
        query="有曲目、但里面的曲目一首都没卖出去过的歌单有哪些？列出歌单编号和名称。",
        reference_sql=(
            "SELECT p.PlaylistId, p.Name"
            " FROM Playlist p"
            " WHERE EXISTS (SELECT 1"
            " FROM PlaylistTrack pt"
            " WHERE pt.PlaylistId = p.PlaylistId)"
            " AND NOT EXISTS (SELECT 1"
            " FROM PlaylistTrack pt"
            " JOIN InvoiceLine l ON l.TrackId = pt.TrackId"
            " WHERE pt.PlaylistId = p.PlaylistId)"
        ),
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId", "InvoiceLine.TrackId"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A17",
        query="里面的曲目全都卖出去过的专辑有多少张？",
        reference_sql=(
            "SELECT COUNT(*)"
            " FROM Album a"
            " WHERE NOT EXISTS (SELECT 1"
            " FROM Track t"
            " WHERE t.AlbumId = a.AlbumId"
            " AND NOT EXISTS (SELECT 1"
            " FROM InvoiceLine l"
            " WHERE l.TrackId = t.TrackId))"
        ),
        must_hit_columns=["Track.AlbumId", "InvoiceLine.TrackId"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A18",
        query="有曲目、但曲目一首都没卖出去过的艺术家有哪些？列出艺术家名称。",
        reference_sql=(
            "SELECT ar.Name"
            " FROM Artist ar"
            " WHERE EXISTS (SELECT 1"
            " FROM Album a"
            " JOIN Track t ON t.AlbumId = a.AlbumId"
            " WHERE a.ArtistId = ar.ArtistId)"
            " AND NOT EXISTS (SELECT 1"
            " FROM Album a"
            " JOIN Track t ON t.AlbumId = a.AlbumId"
            " JOIN InvoiceLine l ON l.TrackId = t.TrackId"
            " WHERE a.ArtistId = ar.ArtistId)"
        ),
        must_hit_columns=["Artist.Name", "Album.ArtistId", "InvoiceLine.TrackId"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="A19",
        query="这个国家的每一位客户都买过 Jazz 流派曲目的国家有哪些？列出国家。",
        reference_sql=(
            "SELECT DISTINCT c0.Country"
            " FROM Customer c0"
            " WHERE NOT EXISTS (SELECT 1"
            " FROM Customer c"
            " WHERE c.Country = c0.Country"
            " AND NOT EXISTS (SELECT 1"
            " FROM Invoice i"
            " JOIN InvoiceLine l ON l.InvoiceId = i.InvoiceId"
            " JOIN Track t ON t.TrackId = l.TrackId"
            " JOIN Genre g ON g.GenreId = t.GenreId"
            " WHERE i.CustomerId = c.CustomerId AND g.Name = 'Jazz'))"
        ),
        must_hit_columns=["Customer.Country", "Genre.Name", "InvoiceLine.TrackId"],
        tags=["探针:全称"],
    ),
    EvalCase(
        id="AC5",
        query="有曲目卖出去过的专辑有多少张？",
        reference_sql=(
            "SELECT COUNT(DISTINCT t.AlbumId)"
            " FROM Track t"
            " JOIN InvoiceLine l ON l.TrackId = t.TrackId"
        ),
        must_hit_columns=["Track.AlbumId", "InvoiceLine.TrackId"],
        tags=["探针:全称", "对照"],
    ),
]

ALL_WRONG_SQL = {
    "A01": (
        "SELECT COUNT(DISTINCT b.user_id) FROM fact_user_behavior b"
        " WHERE b.behavior_type = '加购' AND NOT EXISTS ("
        "   SELECT 1 FROM fact_order_item i JOIN fact_order o ON o.order_id = i.order_id"
        "   WHERE o.user_id = b.user_id AND i.product_id = b.product_id AND o.pay_time IS NOT NULL)"
    ),
    "A02": "SELECT COUNT(DISTINCT user_id) FROM fact_order WHERE pay_time IS NOT NULL",
    "A03": (
        "SELECT u.member_level, COUNT(DISTINCT u.user_id) FROM dim_user u"
        " JOIN fact_order o ON o.user_id = u.user_id"
        " WHERE o.pay_time IS NOT NULL AND NOT EXISTS (SELECT 1 FROM fact_refund r WHERE r.order_id = o.order_id)"
        " GROUP BY u.member_level"
    ),
    "A04": (
        "SELECT DISTINCT s.shop_name FROM dim_shop s"
        " JOIN dim_product p ON p.shop_id = s.shop_id WHERE p.shelf_status = '在售'"
    ),
    "A05": (
        "SELECT COUNT(DISTINCT b.user_id) FROM fact_user_behavior b JOIN dim_product p ON p.product_id = b.product_id"
        " WHERE b.behavior_type = '收藏' AND p.shelf_status = '已下架'"
    ),
    "A06": "SELECT COUNT(DISTINCT user_id) FROM fact_order WHERE pay_time IS NOT NULL AND pay_amount > 500",
    "A07": (
        "SELECT DISTINCT p.PlaylistId, p.Name FROM Playlist p"
        " JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId"
        " JOIN Track t ON t.TrackId = pt.TrackId JOIN Genre g ON g.GenreId = t.GenreId"
        " WHERE g.Name <> 'Rock'"
    ),
    "A08": (
        "SELECT COUNT(DISTINCT i.CustomerId) FROM Invoice i"
        " JOIN InvoiceLine l ON l.InvoiceId = i.InvoiceId"
        " JOIN Track t ON t.TrackId = l.TrackId"
        " JOIN MediaType m ON m.MediaTypeId = t.MediaTypeId"
        " WHERE m.Name = 'MPEG audio file'"
    ),
    "A09": "SELECT COUNT(DISTINCT CustomerId) FROM Invoice WHERE Total <= 15",
    "A10": "SELECT COUNT(DISTINCT AlbumId) FROM Track WHERE Milliseconds > 300000",
    "A11": (
        "SELECT e.FirstName, e.LastName, COUNT(DISTINCT c.CustomerId) FROM Customer c"
        " JOIN Employee e ON e.EmployeeId = c.SupportRepId"
        " JOIN Invoice i ON i.CustomerId = c.CustomerId"
        " JOIN InvoiceLine l ON l.InvoiceId = i.InvoiceId"
        " JOIN Track t ON t.TrackId = l.TrackId JOIN Genre g ON g.GenreId = t.GenreId"
        " WHERE g.Name <> 'Jazz'"
        " GROUP BY e.EmployeeId, e.FirstName, e.LastName"
    ),
    "A12": (
        "SELECT COUNT(DISTINCT b.user_id)"
        " FROM fact_user_behavior b"
        " WHERE b.behavior_type = '收藏'"
        " AND EXISTS (SELECT 1"
        " FROM fact_order_item i"
        " JOIN fact_order o ON o.order_id = i.order_id"
        " WHERE o.user_id = b.user_id AND i.product_id = b.product_id AND o.pay_time IS NOT NULL)"
    ),
    "A13": (
        "SELECT u.gender, COUNT(DISTINCT b.user_id)"
        " FROM fact_user_behavior b"
        " JOIN dim_user u ON u.user_id = b.user_id"
        " WHERE b.behavior_type = '浏览'"
        " AND NOT EXISTS (SELECT 1"
        " FROM fact_user_behavior c"
        " WHERE c.user_id = b.user_id AND c.product_id = b.product_id AND c.behavior_type = '加购')"
        " GROUP BY u.gender"
    ),
    "A14": (
        "SELECT COUNT(DISTINCT p.shop_id)"
        " FROM dim_product p"
        " JOIN fact_user_behavior b ON b.product_id = p.product_id"
        " WHERE b.behavior_type = '收藏'"
    ),
    "A15": (
        "SELECT u.member_level, COUNT(DISTINCT b.user_id)"
        " FROM fact_user_behavior b"
        " JOIN dim_user u ON u.user_id = b.user_id"
        " WHERE b.behavior_type = '加购'"
        " AND NOT EXISTS (SELECT 1"
        " FROM fact_user_behavior c"
        " WHERE c.user_id = b.user_id AND c.product_id = b.product_id AND c.behavior_type = '收藏')"
        " GROUP BY u.member_level"
    ),
    "A16": (
        "SELECT DISTINCT p.PlaylistId, p.Name"
        " FROM Playlist p"
        " JOIN PlaylistTrack pt ON pt.PlaylistId = p.PlaylistId"
        " WHERE NOT EXISTS (SELECT 1"
        " FROM InvoiceLine l"
        " WHERE l.TrackId = pt.TrackId)"
    ),
    "A17": (
        "SELECT COUNT(DISTINCT t.AlbumId)"
        " FROM Track t"
        " JOIN InvoiceLine l ON l.TrackId = t.TrackId"
    ),
    "A18": (
        "SELECT DISTINCT ar.Name"
        " FROM Artist ar"
        " JOIN Album a ON a.ArtistId = ar.ArtistId"
        " JOIN Track t ON t.AlbumId = a.AlbumId"
        " WHERE NOT EXISTS (SELECT 1"
        " FROM InvoiceLine l"
        " WHERE l.TrackId = t.TrackId)"
    ),
    "A19": (
        "SELECT DISTINCT c.Country"
        " FROM Customer c"
        " JOIN Invoice i ON i.CustomerId = c.CustomerId"
        " JOIN InvoiceLine l ON l.InvoiceId = i.InvoiceId"
        " JOIN Track t ON t.TrackId = l.TrackId"
        " JOIN Genre g ON g.GenreId = t.GenreId"
        " WHERE g.Name = 'Jazz'"
    ),
}


WRONG_SQL = {
    **{case.id: _integer_division(case.reference_sql) for case in _INT_DIV_ECOMMERCE + _INT_DIV_CHINOOK},
    **FAN_OUT_SQL,
    **TOPN_WRONG_SQL,
    **TIME_DIFF_WRONG_SQL,
    **UNIQ_WRONG_SQL,
    **KOUJING_WRONG_SQL,
    **ALL_WRONG_SQL,
}

PROBE_BANKS = {
    "ecommerce": _INT_DIV_ECOMMERCE + _FAN_OUT_ECOMMERCE + _TOPN_ECOMMERCE + _TIME_DIFF_ECOMMERCE + _UNIQ_ECOMMERCE + _KOUJING_ECOMMERCE + _ALL_ECOMMERCE,
    "chinook": _INT_DIV_CHINOOK + _FAN_OUT_CHINOOK + _TOPN_CHINOOK + _UNIQ_CHINOOK + _ALL_CHINOOK,
}
