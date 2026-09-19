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

    sql_repair_attempts: int = 1
    """
    SQL 执行失败时的回调修正次数，0 表示关闭。

    把执行器的报错喂回模型重新生成。原项目 README 标注的
    "暂不包含结果校验与回调修正"，补的就是这一块。
    """

    self_consistency_runs: int = 1
    """
    自洽性投票次数，1 表示关闭。

    实测同一个 prompt、temperature=0，DeepSeek 4 次给出 4 种不同输出——
    这不是本项目的 bug，是 LLM 推理服务的固有性质：temperature=0 只保证
    贪心解码，不保证跨请求确定性。源头的不确定性消除不掉，
    只能让下游容忍：同一个问题跑 N 次，按执行结果取多数。

    代价是 N 倍的 CoT 与 SQL 生成开销，检索结果复用不重跑。
    """

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
