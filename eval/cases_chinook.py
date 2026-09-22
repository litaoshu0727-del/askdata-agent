"""
Chinook 题库：中文提问，英文 Schema。

这是对整套方法论的外部验证。前面 50 道题的问题在于闭环——
数据集、题目、元数据全是我写的。这里 Schema 是别人的，
歧义是它自带的。

难度组合是真实场景：国内团队用英文命名的库，业务同学用中文提问。

同一套题跑两遍，唯一的变量是业务元数据的有无：

    python -m eval.runner --dataset chinook --meta ab --repeat 3

题目本身是照着 Schema 出的，不是照着元数据出的——
出题在先，元数据在后，两边都不知道对方写了什么。
"""

from __future__ import annotations

from typing import List

from eval.cases import EvalCase

CHINOOK_CASES: List[EvalCase] = [
    EvalCase(
        id="C01", query="一共有多少个艺术家",
        reference_sql="SELECT COUNT(*) AS v FROM Artist",
        must_hit_columns=["Artist.ArtistId"],
        tags=["单表计数"], note="最简单的一题，作为地板对照",
    ),
    EvalCase(
        id="C02", query="所有发票的金额合计是多少",
        reference_sql="SELECT ROUND(SUM(Total), 2) AS v FROM Invoice",
        must_hit_columns=["Invoice.Total"],
        tags=["单表聚合", "金额字段辨析"],
        note="Total 在 Invoice；UnitPrice 在 Track 和 InvoiceLine，别混",
    ),
    EvalCase(
        id="C03", query="客户分布在哪些国家",
        reference_sql="SELECT DISTINCT Country FROM Customer ORDER BY Country",
        must_hit_columns=["Customer.Country"],
        tags=["同名字段干扰"],
        note="Country 在 Customer 和 Employee 都有，必须选客户那个",
    ),
    EvalCase(
        id="C04", query="员工分布在哪些城市",
        reference_sql="SELECT DISTINCT City FROM Employee ORDER BY City",
        must_hit_columns=["Employee.City"],
        tags=["同名字段干扰"],
        note="反过来考一次，这次要选 Employee.City",
    ),
    EvalCase(
        id="C05", query="曲目单价最高是多少钱",
        reference_sql="SELECT MAX(UnitPrice) AS v FROM Track",
        must_hit_columns=["Track.UnitPrice"],
        tags=["同名字段干扰", "金额字段辨析"],
        note="UnitPrice 在 Track 和 InvoiceLine 都有，问的是曲目定价",
    ),
    EvalCase(
        id="C06", query="每个音乐流派各有多少首曲目，返回流派名称和数量",
        reference_sql="""
            SELECT g.Name, COUNT(*) AS cnt
            FROM Track t JOIN Genre g ON g.GenreId = t.GenreId
            GROUP BY g.GenreId, g.Name
        """,
        must_hit_columns=["Genre.Name", "Track.GenreId"],
        tags=["跨表关联", "分组统计"],
        note="Name 出现在 5 张表，这里要的是 Genre 那个",
    ),
    EvalCase(
        id="C07", query="专辑数量最多的艺术家叫什么名字",
        reference_sql="""
            SELECT ar.Name FROM Album al
            JOIN Artist ar ON ar.ArtistId = al.ArtistId
            GROUP BY ar.ArtistId, ar.Name
            ORDER BY COUNT(*) DESC LIMIT 1
        """,
        must_hit_columns=["Artist.Name", "Album.ArtistId"],
        tags=["跨表关联", "排序取TopN"],
        note="要的是 Artist.Name，不是 Album.Title",
    ),
    EvalCase(
        id="C08", query="Rock 流派的所有曲目总时长是多少毫秒",
        reference_sql="""
            SELECT SUM(t.Milliseconds) AS v FROM Track t
            JOIN Genre g ON g.GenreId = t.GenreId WHERE g.Name = 'Rock'
        """,
        must_hit_columns=["Track.Milliseconds", "Genre.Name"],
        tags=["跨表关联", "条件聚合"],
        note="需要同时命中筛选字段和指标字段",
    ),
    EvalCase(
        id="C09", query="开票金额合计最高的三个国家，国家和金额分别是多少",
        reference_sql="""
            SELECT BillingCountry, ROUND(SUM(Total), 2) AS amt
            FROM Invoice GROUP BY BillingCountry
            ORDER BY SUM(Total) DESC LIMIT 3
        """,
        must_hit_columns=["Invoice.BillingCountry", "Invoice.Total"],
        tags=["单表聚合", "排序取TopN", "同名字段干扰"],
        note=(
            "BillingCountry 与 Customer.Country、Employee.Country 三者易混。"
            "原来出的是「销量最高的三首曲目」，但库里有 256 首并列销量 2，"
            "前三名无法唯一确定——题目本身就不可判分。"
        ),
    ),
    EvalCase(
        id="C10", query="2023年一共开了多少张发票",
        reference_sql="SELECT COUNT(*) AS v FROM Invoice WHERE strftime('%Y', InvoiceDate) = '2023'",
        must_hit_columns=["Invoice.InvoiceDate"],
        tags=["时间过滤"],
        note=(
            "InvoiceDate 是唯一的业务时间字段。原来写的 2010 年库里没有数据，"
            "答案恒为 0——那样错误的筛选条件也能蒙对，测不出东西。"
        ),
    ),
    EvalCase(
        id="C11", query="消费总额最高的客户，返回他的名和姓",
        reference_sql="""
            SELECT c.FirstName, c.LastName FROM Invoice i
            JOIN Customer c ON c.CustomerId = i.CustomerId
            GROUP BY c.CustomerId, c.FirstName, c.LastName
            ORDER BY SUM(i.Total) DESC LIMIT 1
        """,
        must_hit_columns=["Customer.FirstName", "Invoice.Total"],
        tags=["跨表关联", "排序取TopN", "同名字段干扰"],
        note="FirstName/LastName 在 Customer 和 Employee 都有",
    ),
    EvalCase(
        id="C12", query="平均每张发票包含多少个明细行",
        reference_sql="""
            SELECT ROUND(CAST(COUNT(*) AS REAL) / COUNT(DISTINCT InvoiceId), 2) AS v
            FROM InvoiceLine
        """,
        must_hit_columns=["InvoiceLine.InvoiceId"],
        tags=["嵌套聚合", "比率计算"], note="两个计数相除",
    ),
    EvalCase(
        id="C13", query="有多少名员工需要向上级汇报",
        reference_sql="SELECT COUNT(*) AS v FROM Employee WHERE ReportsTo IS NOT NULL",
        must_hit_columns=["Employee.ReportsTo"],
        tags=["单表过滤", "层级类目"],
        note="ReportsTo 是指向自己表的外键，自引用层级",
    ),
    EvalCase(
        id="C14", query="每首曲目被播放了多少次",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[], expect_unanswerable=True,
        tags=["陷阱题"],
        note="库里没有播放记录。PlaylistTrack 是歌单收录关系，不是播放次数",
    ),
    EvalCase(
        id="C15", query="客户的年龄分别是多少岁",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[], expect_unanswerable=True,
        tags=["陷阱题"],
        note="Customer 没有生日字段。Employee 有 BirthDate，但那是员工不是客户",
    ),
]
