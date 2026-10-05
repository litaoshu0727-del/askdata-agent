"""评测题的数据结构。与被测项目里的定义字段、默认值完全一致。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class EvalCase:
    """一道评测题。"""

    id: str
    query: str
    reference_sql: str
    # 答对这道题必须用到的字段，写成 "表名.字段名"。
    # 元素也可以是候选列表 ["表A.字段", "表B.字段"]：几条路径同样正确时，命中任意一个即可。
    must_hit_columns: List[Any] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    note: str = ""
    # 结果是否要求有序。默认按集合比对，不看行序。
    ordered: bool = False
    # 库里根本没有数据能回答这道题，正确行为是说明缺失而不是编一个答案。
    expect_unanswerable: bool = False
