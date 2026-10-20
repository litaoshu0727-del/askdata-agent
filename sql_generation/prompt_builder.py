from __future__ import annotations

import re

from .objects import SqlGenerationRequest


class SqlPromptBuilder:
    """
    SQL 生成 Prompt 构建器。

    注意：
    - Prompt 中不放数据库名称，数据库名称只用于后续执行路由。
    - 第 8、9 条日期规则来自 E44 的实测：apply_time 是带时分秒的 TEXT，
      模型 5 次里 4 次写 apply_time BETWEEN '2024-05-01' AND '2024-05-10'，
      字符串比较把 10 号 00:00 之后的记录全部排除，差值从 268979.27 变成
      241871.02，零告警。当时 SQL 这一步连样例值都看不到，规则要配合
      局部 Schema 里的样例值一起用。
    - 第 10 条整数除法规则来自第三套留出集的 H3E14：SUM(下单笔数) / COUNT(用户)
      在 SQLite 里被截断成整数，三个版本 9 次里错了 6 次。后半句是试出来的：只写
      前半句时，"发票总数 ÷ 客户总数"被写成 COUNT(a) * 1.0 / COUNT(b) FROM A, B，
      两张表一连接，答案成了 1.0。13 道探针上，规则前 29/39，只写前半句 35/39，
      两句都写 39/39。
    - 第 11 条一对多规则来自第四套留出集的 H4E27："明细件数合计不少于 6 件的订单，按状态
      数笔数"，CoT 写对了先按明细汇总、再连订单表，SQL 却把两层压成一层，10 次错 3 次。
      探针上还有两种同源的错：COUNT(DISTINCT) 去了重、SUM(订单金额) 没去；订单金额和明细
      件数在同一层里汇总。"COUNT(DISTINCT) 救不了 SUM"那句是看着第一版的失败加的。
      29 道探针上这类失败 14/87 → 5/87，对照题不受影响；H4E27 本身测不出差别。
    - 第 12、13 条（每组前 N、窗口函数的结果不能在同一层 WHERE 里用）来自第六套留出集：问"每个流派卖得最多的
      前两位"，CoT 写了组内取前 2，SQL 写成整体排序或全局 LIMIT 2（三个版本 12 次）。模板那段是看着第一版的
      失败加的：模型在原始行上编号、外层再 SUM。第 13 条是第二版之后补的：修好了作用域，又在 WHERE 里写 LAG(...)。
      探针上这几类失败 8 → 1 次（两批 31 道）。
    - 修正提示的「报错分析」（_error_analysis）也来自第六套：见下。
    """

    def build(self, request: SqlGenerationRequest) -> str:
        """
        构建 Coder 模型 Prompt。
        """
        cot_step = request.cot_step
        schema_context = request.local_schema.to_prompt_context()

        return f"""你是一个SQL生成助手。

请根据当前步骤的CoT规划和相关Schema信息生成SQL语句。

要求：
1. 只能使用Schema中提供的表、字段和表关联关系。
2. 严格按照CoT中的操作指令生成SQL。
3. 不得编造不存在的表、字段或关联关系。
4. 只输出SQL语句，不输出解释性内容。
5. SQL需要符合{request.sql_dialect}语法。
6. 不要输出Markdown代码块，不要输出```sql。
7. 表名直接写表名，不要加数据库名前缀。写 fact_order，不要写 xxx_db.fact_order。
8. 时间字段先看样例值。样例值带时分秒（如 2024-05-10 20:25:00）的字段，按日期范围筛选时
   写成 DATE(字段) BETWEEN '起始日' AND '结束日'，或左闭右开 字段 >= '起始日' AND 字段 < '结束日次日'。
   不要写 字段 BETWEEN '起始日' AND '结束日'——那是字符串比较，结束日当天 00:00 之后的记录会被全部漏掉。
9. 日期字面量一律写成 'YYYY-MM-DD'，年份以样例值为准。不要写 '5月21日' 这样的中文日期。
10. SQLite 里两个整数相除，结果也是整数，小数部分直接丢掉（7 / 2 得 3）。
    算平均值、人均、比例、占比时，把被除数乘以 1.0 或用 CAST(… AS REAL) 再除；用 AVG() 时不受影响。
    分子分母来自不同的表时，各自用子查询算好再相除；不要把两张表连接（或用逗号并列）之后再 COUNT，连接会把行数放大。
11. 一对多连接会把"一"那一侧的行复制多份：一笔订单有 3 条明细，连上明细表就是 3 行，订单金额也跟着被加 3 次。
    数明细本身（明细条数、件数）连接后直接统计没问题；主表的笔数和主表字段的合计，不能在连着明细表的那一层里
    COUNT / SUM——COUNT(DISTINCT) 只救得了笔数，救不了 SUM：
    - 按明细筛选主表（如"包含某类商品的订单"）：主键 IN (子查询)
    - 按明细的汇总值筛选（如"明细的某项合计超过某个值的订单"）：先在子查询里按关联键 GROUP BY … HAVING，
      外层再按题目要的维度分组统计。不要把两层 GROUP BY 压成一层
    - 主表和明细两边都要汇总：明细先按关联键汇总成子查询（每个主键一行），再和主表连接，外层照常按题目要的维度分组
    写完检查：对主表字段 SUM / COUNT 的那一层，FROM 里有没有直接连着明细表。
12. "每个 X 里前 N 个 / 最高的那个"是组内取前 N：每个 X 各取 N 行。不是整体 LIMIT N，也不是把每组的全部行
    都列出来、只排个序。汇总和编号写在同一层子查询里，外层只筛编号：
      SELECT 分组列, 对象列, 指标 FROM (
        SELECT 分组列, 对象列, SUM(…) AS 指标,
               ROW_NUMBER() OVER (PARTITION BY 分组列 ORDER BY SUM(…) DESC) AS rn
        FROM … GROUP BY 分组列, 对象列
      ) WHERE rn <= N
    外层不再 GROUP BY、不再 SUM，外层的 SELECT 只用子查询输出的列名。题目说并列的都算时用 RANK() 代替 ROW_NUMBER()。
13. 窗口函数（LAG、LEAD、ROW_NUMBER、RANK 等）算出来的值，不能在同一层的 WHERE、GROUP BY、HAVING 里用，
    也不能在 WHERE 里引用同一层 SELECT 起的别名：要按它筛选，先在子查询里算好、起别名，再在外层 WHERE 里筛。

# 当前步骤CoT
处理对象：{cot_step.processing_objects}
操作指令：{cot_step.operation_instruction}
输出目标：{cot_step.output_target}

# Schema信息
{schema_context}
"""

    @staticmethod
    def _error_analysis(local_schema, error: str) -> str:
        """
        报错点名的字段如果在 Schema 里确实存在，就不是"字段不存在"，而是外层看不到它。

        第六套留出集的 H6E07、H6C03：子查询把 DATE(create_time) 起了别名，外层又写 DATE(create_time)，
        报 no such column: create_time。原先第 3 条说"报这个错说明它确实不在 Schema 中"，模型对着
        Schema 一看字段明明在，就把原 SQL 一字不改交回来，修正白做——三个版本里修正失败的 7 次全是这样。

        misuse of window function 同理：探针上修好了作用域，接着在 WHERE 里直接写 LAG(...)。
        """
        if "misuse of window function" in (error or ""):
            return """
# 报错分析
窗口函数（LAG、ROW_NUMBER 等）的结果用在了同一层的 WHERE、GROUP BY 或 HAVING 里，SQLite 不允许。
改法：把窗口函数放进子查询的 SELECT 里起别名，在外层 WHERE 里按这个别名筛选。不要把原 SQL 原样交回。
"""

        match = re.search(r"no such column:\s*(?:([\w\u4e00-\u9fff]+)\.)?([\w\u4e00-\u9fff]+)", error or "")
        if not match:
            return ""

        qualifier, column = match.groups()
        owners = [
            table.table_name
            for table in local_schema.tables.values()
            if any(item.column_name == column for item in table.columns)
        ]
        if not owners:
            return ""

        name = f"{qualifier}.{column}" if qualifier else column
        return f"""
# 报错分析
报错的字段 {name} 在 Schema 里是存在的（{"、".join(owners)}），所以不是字段写错了，而是这一层查询看不到它：
- 外层查询（含外层的 SELECT、WHERE、ORDER BY）只能用子查询 SELECT 里输出的列名；子查询把它算成了别名（如 DATE(…) AS d），
  外层就要用那个别名，不要再写原始字段
- 表别名只在定义它的那一层有效：外层不能引用子查询内部的表别名
改法：外层改用子查询输出的列名，或者把需要的原始字段加进子查询的输出。不要把原 SQL 原样交回。
"""

    def build_repair(
        self,
        request: SqlGenerationRequest,
        failed_sql: str,
        error: str,
    ) -> str:
        """
        构建修正 Prompt。

        把执行器的真实报错喂回模型——报错里往往直接点名了问题
        （no such column: xxx），比让模型凭空重想一遍有效得多。
        """
        cot_step = request.cot_step
        schema_context = request.local_schema.to_prompt_context()

        return f"""你之前生成的SQL执行失败了，请根据报错修正。

要求：
1. 只输出修正后的SQL语句，不输出解释性内容。
2. 只能使用Schema中提供的表、字段和表关联关系。
3. 如果报错提示某个字段或表不存在，先看它在不在下面的Schema里：不在，就改用Schema里真实存在的字段，
   不要臆造，也不要沿用原来的写法；在，就是作用域问题，见最后的「报错分析」。
4. 表名直接写表名，不要加数据库名前缀。
5. 不要输出Markdown代码块。
6. 时间字段先看样例值。样例值带时分秒（如 2024-05-10 20:25:00）的字段，按日期范围筛选时
   写成 DATE(字段) BETWEEN '起始日' AND '结束日'，或左闭右开 字段 >= '起始日' AND 字段 < '结束日次日'。
   不要写 字段 BETWEEN '起始日' AND '结束日'——那是字符串比较，结束日当天 00:00 之后的记录会被全部漏掉。
7. 日期字面量一律写成 'YYYY-MM-DD'，年份以样例值为准。不要写 '5月21日' 这样的中文日期。
8. SQLite 里两个整数相除，结果也是整数，小数部分直接丢掉（7 / 2 得 3）。
   算平均值、人均、比例、占比时，把被除数乘以 1.0 或用 CAST(… AS REAL) 再除；用 AVG() 时不受影响。
   分子分母来自不同的表时，各自用子查询算好再相除；不要把两张表连接（或用逗号并列）之后再 COUNT，连接会把行数放大。
9. 一对多连接会把"一"那一侧的行复制多份：一笔订单有 3 条明细，连上明细表就是 3 行，订单金额也跟着被加 3 次。
   数明细本身（明细条数、件数）连接后直接统计没问题；主表的笔数和主表字段的合计，不能在连着明细表的那一层里
   COUNT / SUM——COUNT(DISTINCT) 只救得了笔数，救不了 SUM：
   - 按明细筛选主表（如"包含某类商品的订单"）：主键 IN (子查询)
   - 按明细的汇总值筛选（如"明细的某项合计超过某个值的订单"）：先在子查询里按关联键 GROUP BY … HAVING，
     外层再按题目要的维度分组统计。不要把两层 GROUP BY 压成一层
   - 主表和明细两边都要汇总：明细先按关联键汇总成子查询（每个主键一行），再和主表连接，外层照常按题目要的维度分组
   写完检查：对主表字段 SUM / COUNT 的那一层，FROM 里有没有直接连着明细表。
10. "每个 X 里前 N 个 / 最高的那个"是组内取前 N：每个 X 各取 N 行。不是整体 LIMIT N，也不是把每组的全部行
   都列出来、只排个序。汇总和编号写在同一层子查询里，外层只筛编号：
     SELECT 分组列, 对象列, 指标 FROM (
       SELECT 分组列, 对象列, SUM(…) AS 指标,
              ROW_NUMBER() OVER (PARTITION BY 分组列 ORDER BY SUM(…) DESC) AS rn
       FROM … GROUP BY 分组列, 对象列
     ) WHERE rn <= N
   外层不再 GROUP BY、不再 SUM，外层的 SELECT 只用子查询输出的列名。题目说并列的都算时用 RANK() 代替 ROW_NUMBER()。
11. 窗口函数（LAG、LEAD、ROW_NUMBER、RANK 等）算出来的值，不能在同一层的 WHERE、GROUP BY、HAVING 里用，
   也不能在 WHERE 里引用同一层 SELECT 起的别名：要按它筛选，先在子查询里算好、起别名，再在外层 WHERE 里筛。

# 当前步骤CoT
处理对象：{cot_step.processing_objects}
操作指令：{cot_step.operation_instruction}
输出目标：{cot_step.output_target}

# Schema信息
{schema_context}

# 之前生成的SQL
{failed_sql}

# 执行报错
{error}
{self._error_analysis(request.local_schema, error)}"""
