from __future__ import annotations

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

# 当前步骤CoT
处理对象：{cot_step.processing_objects}
操作指令：{cot_step.operation_instruction}
输出目标：{cot_step.output_target}

# Schema信息
{schema_context}
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
3. 如果报错提示某个字段或表不存在，说明它确实不在Schema中，
   请改用Schema里真实存在的字段，不要臆造，也不要沿用原来的写法。
4. 表名直接写表名，不要加数据库名前缀。
5. 不要输出Markdown代码块。
6. 时间字段先看样例值。样例值带时分秒（如 2024-05-10 20:25:00）的字段，按日期范围筛选时
   写成 DATE(字段) BETWEEN '起始日' AND '结束日'，或左闭右开 字段 >= '起始日' AND 字段 < '结束日次日'。
   不要写 字段 BETWEEN '起始日' AND '结束日'——那是字符串比较，结束日当天 00:00 之后的记录会被全部漏掉。
7. 日期字面量一律写成 'YYYY-MM-DD'，年份以样例值为准。不要写 '5月21日' 这样的中文日期。

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
"""
