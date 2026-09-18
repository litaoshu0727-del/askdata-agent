from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from askdata_diagnostics import Diagnostic


@dataclass
class PipelineConfig:
    """端到端流程配置。"""

    database_name: str = "trade_db"
    db_path: str | Path = "runtime_data/trade_demo.db"
    sample_size: int = 5

    dataset: str = "trade"
    """
    使用哪套数据集。

    trade      —— 原始的两张交易表，字段少，适合快速跑通链路。
    ecommerce  —— 电商数据集，11 张表 81 个字段，分 dim/fact/dws 三层，
                  近义字段密集，才真正考验两阶段检索的区分能力。
    """


@dataclass
class StepExecutionLog:
    """单个 CoT 步骤执行日志。"""

    database: str
    cot_step: object
    local_schema: str
    sql: str
    execution_request: Dict[str, str]
    execution_result: Dict[str, Any]


@dataclass
class PipelineResult:
    """端到端流程结果。"""

    query: str
    keywords: List[str]
    schema_context: str
    cot_output: str
    step_logs: List[StepExecutionLog] = field(default_factory=list)

    rewritten_query: str = ""
    """
    指代消解后的 Query。

    多轮追问里用户会说"它们的退款金额呢"，这里存的是改写成自包含之后的问题。
    与 query 相同或为空表示没有发生改写。
    """

    diagnostics: List[Diagnostic] = field(default_factory=list)
    """
    本次运行发生的静默降级记录。

    空列表表示链路上每一环都在满配置下跑完；非空说明有环节降级了，
    结果可能看着正常但实际已经打了折扣。
    """

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "query": self.query,
            "rewritten_query": self.rewritten_query,
            "keywords": self.keywords,
            "schema_context": self.schema_context,
            "cot_output": self.cot_output,
            "diagnostics": [item.render() for item in self.diagnostics],
            "step_logs": [
                {
                    "database": log.database,
                    "sql": log.sql,
                    "execution_request": log.execution_request,
                    "execution_result": log.execution_result,
                }
                for log in self.step_logs
            ],
        }
