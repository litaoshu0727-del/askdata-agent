"""
电商数据集评测题库。

标准答案不写死成 SQL 字符串，而是写一条**参考 SQL**，
跑评测时现场执行、拿执行结果当标准答案。原因：
同一个问题有无数种正确写法（JOIN 条件左右互换、列别名不同、子查询 vs JOIN），
比字符串没有意义；**执行结果只有一个**。

每道题还标注 must_hit_columns —— 这道题必须被检索召回的字段。
它让"检索没召回"和"SQL 生成错"两类失败可以分开归因。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class EvalCase:
    """一道评测题。"""

    id: str
    query: str
    reference_sql: str
    must_hit_columns: List[Any] = field(default_factory=list)
    """
    这道题必须被召回的字段。

    元素可以是一个字段名，也可以是一个**候选列表**——表示这几个字段
    命中任意一个即可。因为同一个问题常有多条同样正确的路径：
    "某天的订单量"既能数 fact_order.create_time，也能用
    dws_shop_daily.stat_date 加 order_count，两者结果一致。
    只认一条路径，测的就不是系统而是出题人的预设。
    """
    tags: List[str] = field(default_factory=list)
    note: str = ""
    ordered: bool = False
    """结果是否要求有序。默认按集合比对，避免因排序写法不同误判。"""

    expect_unanswerable: bool = False
    """
    这道题 Schema 根本支撑不了，正确行为是**说明缺失**而不是编一个答案。

    判分标准只看一件事：有没有编。明确说缺失、或干脆不生成 SQL，都算通过；
    一本正经地返回一个结果集，算失败。

    能诚实说"我没有这个数据"的系统，比什么都敢答的系统可靠得多。
    """


CASES: List[EvalCase] = [
    EvalCase(
        id="E01",
        query="销售额最高的三个店铺是哪些",
        reference_sql="""
            SELECT s.shop_name, ROUND(SUM(d.gmv), 2) AS gmv
            FROM dws_shop_daily d
            JOIN dim_shop s ON s.shop_id = d.shop_id
            GROUP BY d.shop_id, s.shop_name
            ORDER BY SUM(d.gmv) DESC
            LIMIT 3
        """,
        must_hit_columns=[
            ["dws_shop_daily.gmv", "fact_order.order_amount"],
            "dim_shop.shop_name",
        ],
        tags=["单表聚合", "近义金额干扰"],
        note="“销售额”对应 gmv，库里还有 8 个金额字段干扰；输出要的是店铺名不是 ID",
    ),
    EvalCase(
        id="E02",
        query="累计消费金额超过30000的用户来自哪些城市",
        reference_sql="""
            SELECT DISTINCT u.city
            FROM dws_user_summary s
            JOIN dim_user u ON u.user_id = s.user_id
            WHERE s.total_pay_amount > 30000
        """,
        must_hit_columns=["dws_user_summary.total_pay_amount", "dim_user.city"],
        tags=["跨表关联", "同名字段干扰"],
        note="city 在 dim_user 和 dim_shop 里都有，必须选用户那个",
    ),
    EvalCase(
        id="E03",
        query="客单价最高的10个用户，他们的用户ID和客单价分别是多少",
        reference_sql="""
            SELECT user_id, ROUND(avg_order_amount, 2) AS avg_order_amount
            FROM dws_user_summary
            ORDER BY avg_order_amount DESC
            LIMIT 10
        """,
        must_hit_columns=[
            "dws_user_summary.avg_order_amount",
            "dws_user_summary.user_id",
        ],
        tags=["纯口径词"],
        note=(
            "“客单价”与字段名 avg_order_amount 字面零重合，只能靠别名和语义召回。"
            "问法特意写明要输出哪两列——输出列不明确的题目没法客观判分。"
        ),
    ),
    EvalCase(
        id="E04",
        query="因为商品质量问题退款的总金额是多少",
        reference_sql="""
            SELECT ROUND(SUM(refund_amount), 2) AS total
            FROM fact_refund
            WHERE refund_reason = '商品质量问题'
        """,
        must_hit_columns=["fact_refund.refund_amount", "fact_refund.refund_reason"],
        tags=["条件聚合", "枚举值匹配"],
        note="要同时命中筛选字段和输出字段，且不能被其他金额字段带偏",
    ),
    EvalCase(
        id="E05",
        query="所有已支付订单的实付金额合计是多少",
        reference_sql="""
            SELECT ROUND(SUM(pay_amount), 2) AS total
            FROM fact_order
            WHERE pay_time IS NOT NULL
        """,
        must_hit_columns=[["fact_order.pay_amount", "fact_payment.pay_amount"]],
        tags=["金额字段辨析"],
        note="实付金额是 fact_order.pay_amount，不是 order_amount，也不需要关联 fact_payment",
    ),
    EvalCase(
        id="E06",
        query="2024年5月15日一共有多少笔订单",
        reference_sql="""
            SELECT COUNT(*) AS order_count
            FROM fact_order
            WHERE DATE(create_time) = '2024-05-15'
        """,
        must_hit_columns=[["fact_order.create_time", "dws_shop_daily.stat_date"]],
        tags=["时间过滤"],
        note="两条路径都对：数 fact_order 的下单时间，或用 dws_shop_daily 的日汇总",
    ),
    EvalCase(
        id="E07",
        query="美妆护肤类目下一共有多少个商品",
        reference_sql="""
            SELECT COUNT(*) AS product_count
            FROM dim_product p
            JOIN dim_category c ON c.category_id = p.category_id
            WHERE c.parent_category_id = 1 OR c.category_id = 1
        """,
        must_hit_columns=["dim_product.category_id", "dim_category.category_name"],
        tags=["跨表关联", "层级类目"],
        note="美妆护肤是一级类目，商品挂在二级类目上，需要走父子关系",
    ),
    EvalCase(
        id="E08",
        query="有多少家店铺是正常营业状态",
        reference_sql="""
            SELECT COUNT(*) AS shop_count
            FROM dim_shop
            WHERE shop_status = '正常营业'
        """,
        must_hit_columns=["dim_shop.shop_status"],
        tags=["单表过滤", "枚举值匹配"],
        note="最简单的一题，作为基线对照",
    ),
    EvalCase(
        id="E09",
        query="用户的加购行为一共有多少次",
        reference_sql="""
            SELECT COUNT(*) AS behavior_count
            FROM fact_user_behavior
            WHERE behavior_type = '加购'
        """,
        must_hit_columns=["fact_user_behavior.behavior_type"],
        tags=["单表过滤", "枚举值匹配"],
        note="“加购”是枚举值，样例值能不能进索引直接影响召回",
    ),
    EvalCase(
        id="E10",
        query="钻石会员有多少人，他们的平均客单价是多少",
        reference_sql="""
            SELECT COUNT(*) AS user_count,
                   ROUND(AVG(s.avg_order_amount), 2) AS avg_price
            FROM dim_user u
            JOIN dws_user_summary s ON s.user_id = u.user_id
            WHERE u.member_level = '钻石会员'
        """,
        must_hit_columns=[
            "dim_user.member_level",
            "dws_user_summary.avg_order_amount",
        ],
        tags=["跨表关联", "多输出", "纯口径词"],
        note="一句话里两个指标，且其中一个是纯口径词",
    ),
]
