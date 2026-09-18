from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict

from askdata_diagnostics import Codes, OnceEmitter, emit
from llm_config import resolve_chat_provider


@dataclass
class CoderModelConfig:
    """
    Coder 模型配置。

    使用 OpenAI compatible 格式调用模型。
    没有 API Key 时默认走 Mock，方便先跑通流程。
    """

    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.0
    timeout: int = 60
    use_mock_when_no_api_key: bool = True
    extra_payload: Dict[str, Any] = field(default_factory=dict)
    """供应商特有的请求体字段，例如 DeepSeek 的 thinking 开关。"""


class CoderModelClient:
    """
    Coder 模型 Client。
    """

    def __init__(self, config: CoderModelConfig | None = None):
        self.config = config or CoderModelConfig()

        # SQL 生成要的是确定性输出，不是发散推理。
        # DeepSeek 在思考模式下会忽略 temperature，所以这里显式关掉思考，
        # 让 temperature=0.0 真正生效。
        provider = resolve_chat_provider(thinking=False)

        if not self.config.api_key:
            self.config.api_key = provider.api_key

        if not self.config.base_url:
            self.config.base_url = provider.chat_url

        if not self.config.model:
            self.config.model = provider.model

        if not self.config.extra_payload:
            self.config.extra_payload = dict(provider.extra_payload)

        self._degrade = OnceEmitter()

    def generate_sql(self, prompt: str) -> str:
        """
        生成 SQL。
        """
        if self.config.api_key:
            return self._call_model(prompt)

        if self.config.use_mock_when_no_api_key:
            self._degrade.emit(
                Codes.MODEL_MOCK_FALLBACK,
                "未配置 API Key，SQL 生成降级为写死的 Mock 结果，"
                "非内置 Demo Query 会直接返回 SELECT 1",
                环节="SQL生成",
            )
            return self._mock_generate(prompt)

        raise ValueError(
            "缺少大模型 API Key（DEEPSEEK_API_KEY 或 DASHSCOPE_API_KEY），"
            "无法调用 Coder 模型。"
        )

    def _call_model(self, prompt: str) -> str:
        """
        调用 Coder 模型。
        """
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": self.config.temperature,
            "stream": False,
        }

        payload.update(self.config.extra_payload)

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        request = urllib.request.Request(
            self.config.base_url,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body)
        except Exception as exc:
            raise RuntimeError(f"调用 Coder 模型失败: {exc}") from exc

        try:
            return result["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise RuntimeError(f"解析 Coder 模型返回失败，原始返回：{result}") from exc

    def _mock_generate(self, prompt: str) -> str:
        """
        Mock SQL 生成。

        只用于本地跑通流程。
        真实效果以 Coder 模型输出为准。
        """
        if (
            "trade_summary" in prompt
            and "interest_info" in prompt
            and "total_trade_count" in prompt
            and "interest_rate" in prompt
        ):
            return """SELECT interest_info.interest_rate
FROM trade_summary
JOIN interest_info
  ON trade_summary.user_id = interest_info.user_id
WHERE trade_summary.total_trade_count > 50000;"""

        return "SELECT 1;"

    def clean_sql(self, text: str, database: str = "") -> str:
        """
        清理模型输出，只保留 SQL。

        处理：
        - 去掉 Markdown 代码块
        - 去掉“输出SQL语句：”之类的前缀
        - 提取 SELECT/WITH 开头的 SQL
        - 剥掉表名上的数据库名前缀

        Args:
            text: 模型原始输出。
            database: 当前数据库名。传入时会剥掉 SQL 里的 `<database>.` 前缀。
        """
        text = text.strip()

        text = re.sub(
            r"^```(?:sql)?\s*",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
            flags=re.I,
        )

        text = re.sub(
            r"^(输出SQL语句|SQL语句|SQL)\s*[:：]\s*",
            "",
            text,
            flags=re.I,
        ).strip()

        match = re.search(
            r"((?:SELECT|WITH)\b[\s\S]*?;?)\s*$",
            text,
            flags=re.I,
        )

        if match:
            sql = match.group(1).strip()
        else:
            sql = text

        sql = self._strip_database_prefix(sql, database)

        if sql and not sql.endswith(";"):
            sql += ";"

        return sql

    @staticmethod
    def _strip_database_prefix(sql: str, database: str) -> str:
        """
        剥掉表名上的数据库名前缀。

        模型偶尔会写成 `ecommerce_db.fact_user_behavior`——这个前缀是从
        CoT 四元组的「数据库: ecommerce_db」里捡来的（SQL Prompt 本身不含库名）。
        SQLite 只挂载一个库，这种限定符必然报 no such table。

        Prompt 里已经加了规则，但 Prompt 约束不到 100%，所以这里再兜一层。
        因为执行器只有一个库，凡是等于库名的限定符一律是错的，剥掉总是安全的。
        """
        if not database or not sql:
            return sql

        pattern = re.compile(
            rf"\b{re.escape(database)}\s*\.\s*(?=[\"\'`\[]?[A-Za-z_])",
            flags=re.I,
        )

        cleaned, count = pattern.subn("", sql)

        if count:
            emit(
                Codes.SQL_DB_PREFIX_STRIPPED,
                "模型给表名加了数据库名前缀，已自动剥除",
                数据库=database,
                出现次数=count,
            )

        return cleaned
