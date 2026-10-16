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

每道"该出错"的题在 WRONG_SQL 里附一条错误写法：整数相除的那几批是把参考 SQL 的
`* 1.0`、`100.0` 去掉；一对多的是直接连接之后再统计。tests/test_probes.py 检查错误写法
的答案和参考答案确实不同——否则这道探针区分不出规则有没有起作用。对照题没有错误写法，
它们用来确认规则没把模型带偏。

    python -m eval.runner --bank probes --tag 探针:一对多 --repeat 3
    python -m eval.runner --bank probes --dataset chinook --repeat 3

整数除法两批原先只存在临时目录里，被系统清理了，从当时的会话记录里原样找回。
结果见 docs/实验记录.md「整数相除，和跨表比例」「一对多连接：订单被数了几遍」。
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
            " FROM fact_order"
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
            " WHERE u.user_id IN (SELECT o.user_id FROM fact_order o JOIN fact_order_item i ON o.order_id = i.order_id JOIN dim_product p ON i.product_id = p.product_id JOIN dim_category c ON p.category_id = c.category_id WHERE c.category_name = '休闲零食')"
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
            "SELECT o.channel, ROUND(SUM(o.pay_amount), 2), (SELECT SUM(i.quantity) FROM fact_order_item i JOIN fact_order o2 ON i.order_id = o2.order_id WHERE o2.channel = o.channel)"
            " FROM fact_order o"
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
            " WHERE user_id IN (SELECT user_id FROM fact_order WHERE pay_amount > 3000 GROUP BY user_id HAVING COUNT(*) >= 5)"
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
            " JOIN fact_order o ON u.user_id = o.user_id"
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
            " FROM fact_order o"
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
        " FROM fact_order o"
        " JOIN fact_order_item i ON o.order_id = i.order_id"
        " JOIN dim_product p ON i.product_id = p.product_id"
        " JOIN dim_category c ON p.category_id = c.category_id"
        " WHERE c.category_name = '手机通讯'"
        " GROUP BY o.channel"
    ),
    "F04": (
        "SELECT u.member_level, COUNT(*)"
        " FROM dim_user u"
        " JOIN fact_order o ON u.user_id = o.user_id"
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
        " FROM fact_order o"
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
        " JOIN fact_order o ON u.user_id = o.user_id"
        " WHERE o.pay_amount > 3000 AND u.user_id IN (SELECT user_id FROM fact_order WHERE pay_amount > 3000 GROUP BY user_id HAVING COUNT(*) >= 5)"
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
        " JOIN fact_order o ON u.user_id = o.user_id"
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


WRONG_SQL = {
    **{case.id: _integer_division(case.reference_sql) for case in _INT_DIV_ECOMMERCE + _INT_DIV_CHINOOK},
    **FAN_OUT_SQL,
}

PROBE_BANKS = {
    "ecommerce": _INT_DIV_ECOMMERCE + _FAN_OUT_ECOMMERCE,
    "chinook": _INT_DIV_CHINOOK + _FAN_OUT_CHINOOK,
}
