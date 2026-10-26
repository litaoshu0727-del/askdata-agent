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


# ---------------------------------------------------------------------------
# 分组比题目要的细：SQL 按一个更细的粒度分了组，结果数的、列的不是题目要的那一级。
#
# 两种形态，都只看 SQL 的最外层结构和执行结果，不解析整条 SQL（库里没有 SQL 解析器，也不为它加依赖）：
#
#   A. 数了组合，没数对象（H9S13）："有多少位客户曾在同一天租了 5 张以上"，
#      SELECT COUNT(*) FROM (SELECT customer_id FROM rental GROUP BY customer_id, DATE(rental_date) HAVING …)
#      子查询按（客户, 日期）分组，同一位客户出现好几次，外层 COUNT(*) 数的是组合数。
#      判定：最外层只有 COUNT(*) FROM (子查询)，子查询只输出一列，这一列有重复值。
#   B. 同一个维度出现好几行（H7E21 一类）：问"每个渠道"，SQL 却 GROUP BY 渠道, 订单号，每个渠道几十行。
#      判定：最外层有 GROUP BY，结果在非聚合列上有重复的行——分组里多了结果没输出的列。
# ---------------------------------------------------------------------------

_AGGREGATE = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX|TOTAL|GROUP_CONCAT)\s*\(", re.I)
_CLAUSES = ("SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "UNION", "INTERSECT", "EXCEPT")


def _top_level(sql: str):
    """
    逐字符扫一遍，跳过引号和括号里的内容，返回最外层出现的子句关键字位置 [(关键字, 起点, 终点)]
    和最外层逗号的位置。只认最外层，子查询、函数参数、CTE 正文都在括号里，自然跳过。
    """
    keywords, commas = [], []
    depth, i, n = 0, 0, len(sql)
    upper = sql.upper()
    while i < n:
        ch = sql[i]
        if ch in "'\"`":
            end = sql.find(ch, i + 1)
            i = n if end < 0 else end + 1
            continue
        if ch == "[":
            end = sql.find("]", i + 1)
            i = n if end < 0 else end + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            if ch == ",":
                commas.append(i)
            elif (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] == "_")):
                for word in _CLAUSES:
                    if upper.startswith(word.split()[0], i):
                        match = re.match(r"\s+".join(word.split()) + r"\b", upper[i:])
                        if match:
                            keywords.append((word, i, i + match.end()))
                            break
        i += 1
    return keywords, commas


def _split_main_query(sql: str):
    """
    拆出主查询：去掉结尾分号；WITH 开头时，CTE 正文都在括号里，最外层第一个 SELECT 就是主查询。
    返回 (CTE 前缀, 主查询的各子句 {关键字: 正文}, 最外层逗号位置)；有 UNION 之类的复合查询返回 None。
    """
    sql = sql.strip().rstrip(";").strip()
    keywords, commas = _top_level(sql)
    selects = [k for k in keywords if k[0] == "SELECT"]
    if not selects or any(k[0] in ("UNION", "INTERSECT", "EXCEPT") for k in keywords):
        return None
    start = selects[0][1]
    prefix = sql[:start]
    clauses = [k for k in keywords if k[1] >= start]
    parts = {}
    for index, (word, begin, end) in enumerate(clauses):
        stop = clauses[index + 1][1] if index + 1 < len(clauses) else len(sql)
        parts[word] = sql[end:stop].strip()
    return prefix, parts, [c for c in commas if c > start]


def _select_items(sql: str):
    """主查询 SELECT 列表按最外层逗号切开。"""
    sql = sql.strip().rstrip(";").strip()
    split = _split_main_query(sql)
    if not split:
        return None
    keywords, commas = _top_level(sql)
    selects = [k for k in keywords if k[0] == "SELECT"]
    froms = [k for k in keywords if k[0] == "FROM" and k[1] > selects[0][1]]
    if not froms:
        return None
    begin, stop = selects[0][2], froms[0][1]
    cuts = [begin] + [c + 1 for c in commas if begin < c < stop] + [stop + 1]
    return [sql[a:b - 1].strip() for a, b in zip(cuts, cuts[1:])]


def _counts_finer_groups(sql: str, run_query) -> Optional[str]:
    """形态 A：最外层只有 COUNT(*) FROM (子查询)，子查询只输出一列且有重复值。"""
    split = _split_main_query(sql)
    if not split:
        return None
    prefix, parts, _ = split
    if set(parts) != {"SELECT", "FROM"}:
        return None
    if not re.fullmatch(r"COUNT\s*\(\s*(\*|1)\s*\)(\s+(AS\s+)?\S+)?", parts["SELECT"], re.I):
        return None
    source = parts["FROM"]
    if not source.startswith("("):
        return None
    depth = 0
    for index, ch in enumerate(source):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0:
            break
    inner, rest = source[1:index], source[index + 1:].strip()
    if rest and not re.fullmatch(r"(AS\s+)?\w+", rest, re.I):
        return None
    try:
        rows = run_query(f"{prefix}SELECT * FROM ({inner})")
    except Exception:  # noqa: BLE001 —— 子查询单独跑不通就不判，不影响原结果
        return None
    if not rows or len(rows[0]) != 1:
        return None
    values = [next(iter(row.values())) if isinstance(row, dict) else row[0] for row in rows]
    distinct = len(set(values))
    if distinct == len(values):
        return None
    column = next(iter(rows[0])) if isinstance(rows[0], dict) else "这一列"
    return (
        f"SQL 能执行，但数的可能不是题目要数的对象：外层 COUNT(*) 数的是子查询的行数，子查询只输出 {column} 一列，"
        f"却有重复——{len(values)} 行里只有 {distinct} 个不同的 {column}。子查询的 GROUP BY 比 {column} 细"
        f"（多了别的分组列），同一个 {column} 被数了好几次。题目问有多少个对象，就数不重复的对象："
        f"外层改成 COUNT(DISTINCT {column})，或者让子查询每个 {column} 只出一行。"
    )


_NAME_LIKE = re.compile(r"(name|title)$", re.I)
_ID_LIKE = re.compile(r"_?id$", re.I)


def _column_ref(expression: str):
    """'p.Name AS 歌单' → ('p', 'Name')；不是简单的列引用返回 None。"""
    expression = re.sub(r"\s+AS\s+\S+$", "", expression.strip(), flags=re.I)
    match = re.fullmatch(r"(?:([\w\u4e00-\u9fff]+)\.)?[\"`\[]?([\w\u4e00-\u9fff]+)[\"`\]]?", expression)
    return (match.group(1) or "", match.group(2)) if match else None


def _groups_by_entity_ids(group_by: str, visible: list) -> bool:
    """
    按实体的 ID 分组、结果里输出实体的名称，是正常写法：名称可能重名（Chinook 有两个 Music 歌单，Sakila 有两个
    London），同一个名称出现两行是两个实体，不是分组细了。没输出的分组列全是"某张表的 ID、而这张表的名称或
    标题在结果里"时，不算。H7E21 那种 GROUP BY 渠道, 订单号——订单号没输出、订单表也没有名称列在结果里——照样算。
    """
    keys, commas = _top_level(group_by)
    cuts = [0] + [c + 1 for c in commas] + [len(group_by) + 1]
    groups = [_column_ref(group_by[a:b - 1]) for a, b in zip(cuts, cuts[1:])]
    shown = [_column_ref(item) for item in visible]
    if None in groups:
        return False
    shown_columns = {ref[1].lower() for ref in shown if ref}
    hidden = [ref for ref in groups if ref[1].lower() not in shown_columns]
    named_aliases = {ref[0].lower() for ref in shown if ref and _NAME_LIKE.search(ref[1])}
    return bool(hidden) and all(_ID_LIKE.search(col) and alias.lower() in named_aliases for alias, col in hidden)


def _repeats_group_keys(sql: str, columns, rows) -> Optional[str]:
    """形态 B：最外层有 GROUP BY，结果在非聚合列上有重复的行。"""
    split = _split_main_query(sql)
    if not split or "GROUP BY" not in split[1] or not rows or not columns or len(set(columns)) != len(columns):
        return None
    if re.match(r"DISTINCT\b", split[1]["SELECT"], re.I):
        return None
    items = _select_items(sql)
    if not items or len(items) != len(columns) or any(item == "*" or item.endswith(".*") for item in items):
        return None
    keys = [i for i, item in enumerate(items) if not _AGGREGATE.search(item) and not re.search(r"\bOVER\s*\(", item, re.I)]
    if not keys or len(keys) == len(items):
        return None
    if _groups_by_entity_ids(split[1]["GROUP BY"], [items[i] for i in keys]):
        return None
    names = [columns[i] for i in keys]

    def value(row, i):
        return row[columns[i]] if isinstance(row, dict) else row[i]

    tuples = [tuple(value(row, i) for i in keys) for row in rows]
    distinct = len(set(tuples))
    if distinct == len(tuples):
        return None
    shown = "、".join(names)
    return (
        f"SQL 能执行，但结果里同一个 {shown} 出现了好几行（{len(tuples)} 行里只有 {distinct} 种）："
        f"最外层的 GROUP BY 里多了结果没输出的列，分组比题目要的细。按题目要的维度分组——GROUP BY 只放结果里"
        f"输出的维度列；要先按更细的粒度汇总，就在子查询里汇总，外层再按 {shown} 汇总一次。"
    )


def finer_grain_mismatch(sql: str, columns, rows, run_query) -> Optional[str]:
    """
    分组比题目要的细时，返回给修正提示用的说明；否则返回 None。

    run_query(sql) -> 行列表：形态 A 要单独跑一次子查询。只读、只在结果已经跑通之后调用。
    """
    if not sql:
        return None
    return _counts_finer_groups(sql, run_query) or _repeats_group_keys(sql, columns, rows)


# ---------------------------------------------------------------------------
# 窗口函数的上一期被筛掉了（H9S07、H8C02）："6–8 月每月营业额比上个月多多少"，
#   SELECT month, amount - LAG(amount) OVER (ORDER BY month) FROM (按月汇总) WHERE month BETWEEN '2005-06' AND '2005-08'
# SQLite 先做 WHERE 再算窗口：5 月被筛掉了，6 月的"上个月"不存在，变化成了空值。规则里点过名，模型照样写。
# 判定：最外层 SELECT 里有 LAG / LEAD，最外层的 WHERE 按窗口的排序列筛选，结果里这一列有空值。
# 只按别的列筛选（"1 号店每月比上月"）时不算——那时第一个月本来就没有上一期。
# ---------------------------------------------------------------------------

_WINDOW_SHIFT = re.compile(r"\b(LAG|LEAD)\s*\(", re.I)


def _identifiers(expression: str) -> set:
    return {name.lower() for name in re.findall(r"[A-Za-z_一-鿿][\w一-鿿]*", expression)}


def window_filtered_previous(sql: str, columns, rows) -> Optional[str]:
    """窗口函数和按时间筛选写在同一层、上一期被筛掉时，返回给修正提示用的说明；否则返回 None。"""
    split = _split_main_query(sql or "")
    if not split or "WHERE" not in split[1] or not rows:
        return None
    items = _select_items(sql)
    if not items or len(items) != len(columns or []):
        return None
    where = _identifiers(split[1]["WHERE"])
    for index, item in enumerate(items):
        if not _WINDOW_SHIFT.search(item):
            continue
        orders = re.findall(r"OVER\s*\([^)]*?ORDER\s+BY\s+([^)]*?)\)", item, re.I | re.S)
        keys = set()
        for order in orders:
            keys |= _identifiers(re.sub(r"\b(ASC|DESC|NULLS|FIRST|LAST)\b", " ", order, flags=re.I))
        keys -= {"strftime", "date", "datetime", "substr", "cast", "as", "text", "integer"}
        if not keys or not keys & where:
            continue
        name = columns[index]
        values = [row[name] if isinstance(row, dict) else row[index] for row in rows]
        if any(value is None for value in values):
            return (
                f"SQL 能执行，但 {name} 里有空值：窗口函数（LAG / LEAD）和按 {'、'.join(sorted(keys & where))} 筛选的 WHERE "
                "写在了同一层。SQLite 先做 WHERE 再算窗口，范围外的上一期被筛掉了，范围内第一期的\"上一期\"就成了空值。"
                "把窗口函数放进子查询，在没筛选的全部数据上算好、起别名，外层再按时间范围筛选。"
            )
    return None


# ---------------------------------------------------------------------------
# 每组前 N 没截断（H9S02）："每个类型最能挣钱的两部片子"，SQL 没用窗口函数，结果每个类型几十行。
# 判定：问题里有一个"每个 / 各"的分组和一个"前 N / 最……的 N 个"，结果第一列（分组列）的某个值出现了不止 N 行。
# 问题说并列的都算、或者有两层分组（"每个国家每年"）时不判。
# ---------------------------------------------------------------------------

_CN_NUMBER = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_PER_GROUP = re.compile(r"每(个|一个|种|类|家|位|名|部|张|年|月|天)?|各(个|自|家|位|类)?")
_UNIT = r"(?:个|位|部|家|名|张|首|种|条|笔|款|件|本|支)"
_TOP_N = [
    re.compile(r"(?<![之以提目当])前\s*([0-9]+|[一两二三四五六七八九十])\s*" + _UNIT + r"?"),
    re.compile(r"最[^，。？\s]{0,8}?的\s*([0-9]+|[一两二三四五六七八九十])\s*" + _UNIT),
    re.compile(r"最[^，。？\s]{0,8}?的(?:是)?(?:哪|那)\s*(?:一)?" + _UNIT + r"()"),   # "最多的是哪家"：N = 1
]


def group_topn_overflow(query: str, columns, rows) -> Optional[str]:
    """问每组前 N、结果的分组列却有某个值超过 N 行时，返回给修正提示用的说明；否则返回 None。"""
    if not query or not rows or not columns or "并列" in query:
        return None
    if len(_PER_GROUP.findall(query)) != 1:
        return None
    match = next((m for m in (pattern.search(query) for pattern in _TOP_N) if m), None)
    if not match:
        return None
    raw = match.group(1)
    n = 1 if not raw else int(raw) if raw.isdigit() else _CN_NUMBER[raw]
    first = columns[0]
    counts = {}
    for row in rows:
        value = row[first] if isinstance(row, dict) else row[0]
        counts[value] = counts.get(value, 0) + 1
    worst = max(counts.values())
    if worst <= n:
        return None
    return (
        f"SQL 能执行，但每组前 {n} 没截断：问题要每组只取前 {n} 个，结果里同一个 {first} 出现了 {worst} 行"
        f"（共 {len(rows)} 行）。按组内前 N 写：汇总和 ROW_NUMBER() OVER (PARTITION BY 分组列 ORDER BY 指标 DESC) "
        f"写在同一层子查询里，外层只筛 rn <= {n}；外层不再 GROUP BY。"
    )
