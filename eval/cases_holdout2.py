"""
第二套 Chinook 留出评测集：由独立出题人在未见过被测系统表现和已有题目的情况下编写。

**已用过一次。**这套题于 7fa2033 冻结，用来验证 1dbc23d（Chinook 精排文本与检索配置）
在陌生问题上的效果，同时测了改前（e95c875）和改后两个版本，结果见 README
「第二套留出集：修 Chinook 精排，在没见过的题上验证」：

    首轮检索召回率  88% → 98%
    复核救回        16/60 → 5/60
    端到端          19/20 → 19/20（逐题相同）

HB16 暴露的弱点（精排对按年份表达的时间筛选打分偏低）是从这套题上诊断出来的。
照着它去修，就不能再用这套题验证——需要新的盲写题。

冻结后没有修改任何题目。
"""
from __future__ import annotations
from typing import List
from eval.cases import EvalCase

HOLDOUT2_CHINOOK_CASES: List[EvalCase] = [
    # ------------------------------------------------------------------
    # 简单
    # ------------------------------------------------------------------
    EvalCase(
        id="HB01",
        query="歌单列表里有些歌单名称出现了不止一次。请列出这些重复出现的名称，以及每个名称各出现了几次。",
        reference_sql="""
SELECT Name, COUNT(*) AS occurrences
FROM Playlist
GROUP BY Name
HAVING COUNT(*) > 1
""",
        must_hit_columns=["Playlist.Name"],
        tags=["难度:简单", "单表", "分组统计", "HAVING过滤"],
        note="考按名称分组后用 HAVING 筛出重名歌单；口径是 Playlist 表里同名记录的条数（Music、Movies、TV Shows、Audiobooks 各 2 条）。",
    ),
    EvalCase(
        id="HB02",
        query="有多少位客户没有留传真号码？返回一个数。",
        reference_sql="""
SELECT COUNT(*) AS customer_count
FROM Customer
WHERE Fax IS NULL
""",
        must_hit_columns=["Customer.Fax"],
        tags=["难度:简单", "单表过滤", "空值判断"],
        note="考空值判断（IS NULL），且要落在客户表而不是员工表；库里没有空字符串的传真，口径就是 Customer.Fax 为 NULL 的人数。",
    ),
    EvalCase(
        id="HB03",
        query="2022年3月1日到2022年5月31日（含首尾两天）开出的发票，平均每张发票金额是多少？返回一个数，保留两位小数。",
        reference_sql="""
SELECT ROUND(AVG(Total), 2) AS avg_invoice_amount
FROM Invoice
WHERE DATE(InvoiceDate) BETWEEN '2022-03-01' AND '2022-05-31'
""",
        must_hit_columns=[["Invoice.Total", "InvoiceLine.UnitPrice"], "Invoice.InvoiceDate"],
        tags=["难度:简单", "单表", "时间过滤", "聚合"],
        note="考闭区间日期过滤加平均值；口径是窗口内发票 Total 的算术平均（21 张）。用明细行金额合计 ÷ 发票张数结果相同。",
    ),
    EvalCase(
        id="HB04",
        query="哪些员工入职的时候已经年满 40 周岁？名和姓分两列返回。",
        reference_sql="""
SELECT FirstName, LastName
FROM Employee
WHERE DATE(BirthDate, '+40 years') <= DATE(HireDate)
""",
        must_hit_columns=["Employee.FirstName", "Employee.LastName", "Employee.BirthDate", "Employee.HireDate"],
        tags=["难度:简单", "单表过滤", "日期计算"],
        note="考两个日期字段之间的年龄计算；口径是入职日当天周岁 >= 40。按精确周岁、年份相减或天数/365.25 计算，结果都是同样 3 人。",
    ),
    EvalCase(
        id="HB05",
        query="曲库里有多少首歌是用葡萄牙语演唱的？返回一个数。",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:简单", "陷阱题", "不存在的属性"],
        note="库里没有曲目语言字段。Genre 里的 Latin、Bossa Nova，歌单 Brazilian Music（里面甚至有 Eric Clapton 的曲目），还有客户国家 Brazil/Portugal 都只是看起来沾边，不能当作“葡萄牙语演唱”。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="HB06",
        query="曲库中没有登记作曲者的曲目占全部曲目的百分之多少？返回一个数，用百分数的数值表示（例如 12.34 表示 12.34%），保留两位小数。",
        reference_sql="""
SELECT ROUND(100.0 * SUM(CASE WHEN Composer IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_without_composer
FROM Track
""",
        must_hit_columns=["Track.Composer"],
        tags=["难度:简单", "单表", "比率计算", "空值判断"],
        note="考空值计数和比率；分母是全部 3503 首曲目，分子是 Composer 为 NULL 的 977 首（库里没有空字符串）。",
    ),
    EvalCase(
        id="HB07",
        query="曲库里哪些作曲者名下的曲目超过 30 首？作曲者按曲库里登记的原文算（多人合写的那一栏整体算一个，不拆开），没有登记作曲者的曲目不算。返回作曲者和曲目数。",
        reference_sql="""
SELECT Composer, COUNT(*) AS track_count
FROM Track
WHERE Composer IS NOT NULL
GROUP BY Composer
HAVING COUNT(*) > 30
""",
        must_hit_columns=["Track.Composer"],
        tags=["难度:简单", "单表", "分组统计", "HAVING过滤", "空值判断"],
        note="考单表分组加 HAVING，并且要排除作曲者为空的曲目（空值那一组有 977 首，不排除会多出一行）；口径按 Composer 原文分组、合写不拆分，结果为 Steve Harris 80、U2 44、Jagger/Richards 35、Billy Corgan 31，门槛写成 >=30 结果也一样。",
    ),
    # ------------------------------------------------------------------
    # 中等
    # ------------------------------------------------------------------
    EvalCase(
        id="HB08",
        query="哪些客户在2024年1月1日至2024年12月31日期间一张发票都没有？名和姓分两列返回。",
        reference_sql="""
SELECT c.FirstName, c.LastName
FROM Customer c
WHERE NOT EXISTS (
    SELECT 1
    FROM Invoice i
    WHERE i.CustomerId = c.CustomerId
      AND DATE(i.InvoiceDate) BETWEEN '2024-01-01' AND '2024-12-31'
)
""",
        must_hit_columns=["Customer.FirstName", "Customer.LastName", "Invoice.InvoiceDate"],
        tags=["难度:中等", "跨表关联", "反连接", "时间过滤"],
        note="考带时间窗口的反连接（NOT EXISTS / LEFT JOIN IS NULL）；口径是 2024 全年没有任何发票的客户，共 12 位。时间条件必须放在子查询或 JOIN 条件里，不能放在外层 WHERE。",
    ),
    EvalCase(
        id="HB09",
        query="有哪些专辑收录的曲目分属两个或以上不同的流派？返回专辑名称和该专辑涉及的流派个数。",
        reference_sql="""
SELECT a.Title, COUNT(DISTINCT t.GenreId) AS genre_count
FROM Album a
JOIN Track t ON t.AlbumId = a.AlbumId
GROUP BY a.AlbumId, a.Title
HAVING COUNT(DISTINCT t.GenreId) >= 2
""",
        must_hit_columns=["Album.Title", "Track.GenreId"],
        tags=["难度:中等", "跨表关联", "分组统计", "去重计数", "HAVING过滤"],
        note="考按专辑分组后对流派去重计数再用 HAVING 过滤；共 11 张专辑，其中 Greatest Hits 涉及 3 个流派。专辑名在库里不重复。",
    ),
    EvalCase(
        id="HB10",
        query="登记了所属公司的客户（即企业客户），在2023年1月1日至2023年12月31日期间的开票金额一共是多少？返回一个数，保留两位小数。",
        reference_sql="""
SELECT ROUND(SUM(i.Total), 2) AS corporate_revenue_2023
FROM Invoice i
JOIN Customer c ON c.CustomerId = i.CustomerId
WHERE c.Company IS NOT NULL
  AND DATE(i.InvoiceDate) BETWEEN '2023-01-01' AND '2023-12-31'
""",
        must_hit_columns=["Customer.Company", "Invoice.InvoiceDate", ["Invoice.Total", "InvoiceLine.UnitPrice"]],
        tags=["难度:中等", "跨表关联", "时间过滤", "空值判断", "聚合"],
        note="考客户属性过滤加发票时间窗口求和；企业客户的口径是 Customer.Company 非空（10 位），金额是 2023 年发票 Total 之和。改用明细行金额求和结果相同。",
    ),
    EvalCase(
        id="HB11",
        query="2024年1月1日至2024年12月31日，每位销售支持员工各处理了多少张客户投诉工单？返回员工的名、姓和工单数。",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题", "不存在的业务对象"],
        note="库里没有投诉、工单或客服记录。Customer.SupportRepId 只表示客户的负责员工，Employee.Title 里的 Sales Support Agent 只是职位，发票是购买记录，都不能当作投诉工单来数。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="HB12",
        query="对每一位名下有客户的员工，统计他/她负责的客户分布在多少个不同的国家。返回员工的名、姓和国家数。",
        reference_sql="""
SELECT e.FirstName, e.LastName, COUNT(DISTINCT c.Country) AS country_count
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=["Employee.FirstName", "Employee.LastName", "Customer.SupportRepId", "Customer.Country"],
        tags=["难度:中等", "跨表关联", "分组统计", "去重计数"],
        note="考经 SupportRepId 关联员工与客户，再对客户所在国家去重计数；只有 3 位员工名下有客户，没有客户的员工不应出现。",
    ),
    EvalCase(
        id="HB13",
        query="Classical、Classical 101 - Deep Cuts、Classical 101 - Next Steps、Classical 101 - The Basics 这四个歌单合起来，一共收录了多少首不同的曲目？同一首曲目被多个歌单收录只算一次，返回一个数。",
        reference_sql="""
SELECT COUNT(DISTINCT pt.TrackId) AS distinct_tracks
FROM PlaylistTrack pt
JOIN Playlist p ON p.PlaylistId = pt.PlaylistId
WHERE p.Name IN ('Classical', 'Classical 101 - Deep Cuts', 'Classical 101 - Next Steps', 'Classical 101 - The Basics')
""",
        must_hit_columns=["Playlist.Name", "PlaylistTrack.TrackId"],
        tags=["难度:中等", "跨表关联", "去重计数"],
        note="考多对多关系表上的去重计数；四个歌单共有 150 条收录记录，但 Classical 恰好是三个 Classical 101 歌单的并集，去重后是 75 首。",
    ),
    # ------------------------------------------------------------------
    # 难
    # ------------------------------------------------------------------
    EvalCase(
        id="HB14",
        query="有哪些员工比自己的直属上级入职还早？返回这名员工的名、姓，以及其直属上级的名、姓（共四列）。",
        reference_sql="""
SELECT e.FirstName, e.LastName, m.FirstName AS ManagerFirstName, m.LastName AS ManagerLastName
FROM Employee e
JOIN Employee m ON m.EmployeeId = e.ReportsTo
WHERE DATE(e.HireDate) < DATE(m.HireDate)
""",
        must_hit_columns=["Employee.FirstName", "Employee.LastName", "Employee.HireDate", "Employee.ReportsTo"],
        tags=["难度:难", "自关联", "日期比较"],
        note="考员工表自关联后比较上下级的入职日期；结果是 Nancy Edwards（上级 Andrew Adams）和 Jane Peacock（上级 Nancy Edwards）。总经理没有上级，不参与比较。",
    ),
    EvalCase(
        id="HB15",
        query="对每一位名下有客户的员工，统计他/她负责的客户买过的曲目一共覆盖了多少种不同的音乐流派。返回员工的名、姓和流派数。",
        reference_sql="""
SELECT e.FirstName, e.LastName, COUNT(DISTINCT t.GenreId) AS genre_count
FROM Employee e
JOIN Customer c ON c.SupportRepId = e.EmployeeId
JOIN Invoice i ON i.CustomerId = c.CustomerId
JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
JOIN Track t ON t.TrackId = il.TrackId
GROUP BY e.EmployeeId, e.FirstName, e.LastName
""",
        must_hit_columns=["Employee.FirstName", "Employee.LastName", "Customer.SupportRepId", "Track.GenreId"],
        tags=["难度:难", "多跳JOIN", "去重计数", "分组统计"],
        note="考员工→客户→发票→明细→曲目的五表链路，再对流派去重计数；结果是 Jane Peacock 23、Margaret Park 22、Steve Johnson 22。",
    ),
    EvalCase(
        id="HB16",
        query="按曲目所属的音乐流派统计销售额（按发票明细里每首曲目的实际成交金额累加）。与2023年（1月1日至12月31日）相比，2024年（1月1日至12月31日）销售额增加最多的3个流派是哪些？返回流派名称和增加的金额（2024年销售额减2023年销售额，保留两位小数）。",
        reference_sql="""
WITH genre_sales AS (
    SELECT g.Name AS genre,
           SUM(CASE WHEN DATE(i.InvoiceDate) BETWEEN '2024-01-01' AND '2024-12-31'
                    THEN il.UnitPrice * il.Quantity ELSE 0 END) AS sales_2024,
           SUM(CASE WHEN DATE(i.InvoiceDate) BETWEEN '2023-01-01' AND '2023-12-31'
                    THEN il.UnitPrice * il.Quantity ELSE 0 END) AS sales_2023
    FROM InvoiceLine il
    JOIN Invoice i ON i.InvoiceId = il.InvoiceId
    JOIN Track t ON t.TrackId = il.TrackId
    JOIN Genre g ON g.GenreId = t.GenreId
    GROUP BY g.GenreId, g.Name
)
SELECT genre, ROUND(sales_2024 - sales_2023, 2) AS increase
FROM genre_sales
ORDER BY sales_2024 - sales_2023 DESC
LIMIT 3
""",
        must_hit_columns=["Genre.Name", "InvoiceLine.UnitPrice", "Invoice.InvoiceDate"],
        tags=["难度:难", "多跳JOIN", "区间对比", "排序取TopN", "分组统计"],
        note="考流派级销售额的同比差额加 TopN，金额必须来自明细行（不能用发票 Total，否则会重复计算）；结果是 Metal 39.60、Comedy 9.95、Classical 6.93，第 3、4 名（6.93 / 5.97）不并列。",
    ),
    EvalCase(
        id="HB17",
        query="哪些艺术家的曲目被 20 位及以上不同的客户买过？同一位客户买过该艺术家多首曲目只算一次。返回艺术家名称和买过其曲目的客户数。",
        reference_sql="""
SELECT ar.Name, COUNT(DISTINCT i.CustomerId) AS customer_count
FROM Artist ar
JOIN Album al ON al.ArtistId = ar.ArtistId
JOIN Track t ON t.AlbumId = al.AlbumId
JOIN InvoiceLine il ON il.TrackId = t.TrackId
JOIN Invoice i ON i.InvoiceId = il.InvoiceId
GROUP BY ar.ArtistId, ar.Name
HAVING COUNT(DISTINCT i.CustomerId) >= 20
""",
        must_hit_columns=["Artist.Name", ["Invoice.CustomerId", "Customer.CustomerId"]],
        tags=["难度:难", "多跳JOIN", "去重计数", "分组统计", "HAVING过滤"],
        note="考艺术家→专辑→曲目→明细→发票的五表链路，再对客户去重计数；艺术家按专辑所属艺术家归属（不是 Composer 字段）。结果为 U2 29、Led Zeppelin 28、Iron Maiden 27、Metallica 27（第 5 名只有 16，门槛附近没有边界值）；不去重、按购买行数计会有 33 位艺术家达标。",
    ),
    EvalCase(
        id="HB18",
        query="先算全体客户的人均消费额（全部发票金额合计 ÷ 全部客户人数），再算各国客户的人均消费额（该国客户的发票金额合计 ÷ 该国客户人数）。哪些国家的人均消费额高于全体水平？返回国家名称和该国人均消费额（保留两位小数）。",
        reference_sql="""
SELECT c.Country,
       ROUND(SUM(i.Total) * 1.0 / COUNT(DISTINCT c.CustomerId), 2) AS avg_spend_per_customer
FROM Customer c
JOIN Invoice i ON i.CustomerId = c.CustomerId
GROUP BY c.Country
HAVING SUM(i.Total) * 1.0 / COUNT(DISTINCT c.CustomerId)
     > (SELECT SUM(Total) FROM Invoice) * 1.0 / (SELECT COUNT(*) FROM Customer)
""",
        must_hit_columns=[
            ["Customer.Country", "Invoice.BillingCountry"],
            ["Invoice.Total", "InvoiceLine.UnitPrice"],
            ["Customer.CustomerId", "Invoice.CustomerId"],
        ],
        tags=["难度:难", "嵌套聚合", "高于平均", "跨表关联", "分组统计"],
        note="考分组指标与全局基准比较的嵌套聚合；基准为 2328.60 ÷ 59 ≈ 39.47，共 9 个国家高于基准。本库每位客户都有发票，且开票国家与客户国家完全一致，所以两种国家口径的结果相同。",
    ),
    EvalCase(
        id="HB19",
        query="按媒体格式统计：每种格式的曲目里，至少被卖出过一次的曲目占该格式全部曲目的百分比是多少？返回格式名称和百分比（百分数的数值，例如 12.34 表示 12.34%，保留两位小数）。",
        reference_sql="""
SELECT m.Name,
       ROUND(100.0 * COUNT(DISTINCT il.TrackId) / COUNT(DISTINCT t.TrackId), 2) AS sold_track_pct
FROM MediaType m
JOIN Track t ON t.MediaTypeId = m.MediaTypeId
LEFT JOIN InvoiceLine il ON il.TrackId = t.TrackId
GROUP BY m.MediaTypeId, m.Name
""",
        must_hit_columns=["MediaType.Name", "InvoiceLine.TrackId"],
        tags=["难度:难", "多跳JOIN", "比率计算", "去重计数", "外连接"],
        note="考按格式计算动销率：分子是出现在明细行里的不同曲目数（有 256 首曲目被卖出过两次，必须去重），分母是该格式全部曲目数。",
    ),
    EvalCase(
        id="HB20",
        query="2024年1月1日至2024年12月31日期间，有多少张发票用了优惠券？优惠券一共抵扣了多少金额？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:难", "陷阱题", "不存在的业务对象"],
        note="库里没有优惠券、促销或折扣记录。InvoiceLine.UnitPrice（成交价）与 Track.UnitPrice（标价）看起来可以用来推算折扣，但价差不等于用了优惠券（本库两者也完全相同）；Invoice.Total 也只是明细合计。",
        expect_unanswerable=True,
    ),
]
