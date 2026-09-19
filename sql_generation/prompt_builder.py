from __future__ import annotations

from .objects import SqlGenerationRequest


class SqlPromptBuilder:
    """
    SQL 生成 Prompt 构建器。

    注意：
    - Prompt 中不放数据库名称，数据库名称只用于后续执行路由。
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
