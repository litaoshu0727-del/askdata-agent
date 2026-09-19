from __future__ import annotations

from .coder_client import CoderModelClient
from .objects import CotStep, SqlGenerationRequest, SqlGenerationResult
from .prompt_builder import SqlPromptBuilder
from .schema_store import LocalSchemaStore


class SqlGenerator:
    """
    SQL 生成服务。

    输入：
    - CoT 四元组
    - SchemaStore 中提取的局部 Schema

    输出：
    - SQL
    - database + sql 执行请求
    """

    def __init__(
        self,
        schema_store: LocalSchemaStore,
        prompt_builder: SqlPromptBuilder | None = None,
        coder_client: CoderModelClient | None = None,
    ):
        self.schema_store = schema_store
        self.prompt_builder = prompt_builder or SqlPromptBuilder()
        self.coder_client = coder_client or CoderModelClient()

    def generate(
        self,
        cot_step: CotStep,
        sql_dialect: str = "标准SQL",
    ) -> SqlGenerationResult:
        """
        根据 CoT 步骤生成 SQL。
        """
        local_schema = self.schema_store.extract_local_schema(cot_step)

        request = SqlGenerationRequest(
            cot_step=cot_step,
            local_schema=local_schema,
            sql_dialect=sql_dialect,
        )

        prompt = self.prompt_builder.build(request)
        raw_output = self.coder_client.generate_sql(prompt)
        sql = self.coder_client.clean_sql(raw_output, database=cot_step.database)

        return SqlGenerationResult(
            database=cot_step.database,
            prompt=prompt,
            raw_output=raw_output,
            sql=sql,
        )

    def repair(
        self,
        cot_step: CotStep,
        failed_sql: str,
        error: str,
        sql_dialect: str = "标准SQL",
    ) -> SqlGenerationResult:
        """
        根据执行报错修正 SQL。

        原项目 README 里写着"暂不包含结果校验与回调修正"，这是补上的那一块。
        执行器的报错是一手信息——"no such column: fact_order.category_id"
        直接点名了问题所在，比让模型重新凭空想一遍有效得多。
        """
        local_schema = self.schema_store.extract_local_schema(cot_step)

        request = SqlGenerationRequest(
            cot_step=cot_step,
            local_schema=local_schema,
            sql_dialect=sql_dialect,
        )

        prompt = self.prompt_builder.build_repair(
            request=request,
            failed_sql=failed_sql,
            error=error,
        )

        raw_output = self.coder_client.generate_sql(prompt)
        sql = self.coder_client.clean_sql(raw_output, database=cot_step.database)

        return SqlGenerationResult(
            database=cot_step.database,
            prompt=prompt,
            raw_output=raw_output,
            sql=sql,
        )
