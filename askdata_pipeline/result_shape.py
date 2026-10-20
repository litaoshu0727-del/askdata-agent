"""
结果形状检查：问题只要一个数，SQL 却返回了好几行。

第六套留出集里"两层聚合压成一层"失败 8 次，形状都一样："有多少张专辑，专辑里的每一首曲目都卖过"，
SQL 按专辑分了组、外层没有再数一次，每张专辑一行，返回 48 行。SQL 能执行、不报错，修正碰不到它。

判定只看问题文本和结果的形状，不解析 SQL：

    问题问的是"有多少……""一共……""返回一个数"
    且结果不止一行
    且（问题里没有"每、各、按、分别、哪些、列出、前 N、最高的"这类分组或列举的说法
        或者结果只有一列——分组的问题至少还有一列分组键）

离线核对：全部题库 382 道题的参考答案，一道都不会被误判；近期运行记录里"期望 1 行、实际多行"的错误
运行 7 次，全部命中。
"""

from __future__ import annotations

import re
from typing import Optional

_ASKS_FOR_A_NUMBER = re.compile(r"有多少|多少[位个张笔件次天人家首种条]|几[位个张笔件次天人家首种条]|一共|总共|合计是多少|返回一个数")
_GROUPED_OR_LISTED = re.compile(r"每|各|按|分别|哪些|列出|分组|排名|前\s*[0-9一二两三四五六七八九十]+|最高的|最多的|最低的|最少的")


def single_value_mismatch(query: str, columns, row_count: int) -> Optional[str]:
    """问题只要一个数、结果却不止一行时，返回给修正提示用的说明；否则返回 None。"""
    if row_count <= 1 or not query or not _ASKS_FOR_A_NUMBER.search(query):
        return None

    single_column = len(columns or []) == 1
    if _GROUPED_OR_LISTED.search(query) and not single_column:
        return None

    shape = f"{row_count} 行" + ("、只有一列" if single_column else "")
    return (
        f"SQL 能执行，但结果的形状不对：问题只要一个数，结果却有 {shape}。"
        "多半是外层的汇总丢了——按某个粒度分组（GROUP BY）之后，没有在外面再数一次或再汇总一次，"
        "结果成了每组一行。把分组的那一层写成子查询，外层再 COUNT(*) 或 SUM(…)，最终只返回一行。"
    )
