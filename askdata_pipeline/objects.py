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
    chinook    —— 公开的音乐商店库，Schema 不是我设计的，用来做外部验证。
    """

    business_meta_mode: str = "full"
    """
    业务元数据开关，full / none。

    none 会把手写的表描述、字段别名、近义字段辨析全部丢掉，
    只留库里自带的字段名、类型和样例值——这是元数据消融实验的对照组。

    "元数据质量决定召回准确率"这句话，在自己造的数据集上说不算数：
    库是我建的、题是我出的、元数据也是我写的。要证伪它，
    得在一个陌生 Schema 上把元数据这一个变量单独拔掉，看分数掉多少。
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

    retrieval_context: str = ""
    """
    **首轮检索**交出来的 Schema，没经过全量复核。

    与 schema_context 的差别只在拒答复核触发时才显现：那时 schema_context
    已经被换成全库 64 个字段，拿它算召回率，等于在问"全量 Schema 里有没有
    这个字段"——答案恒为是。检索到底漏没漏，只有首轮这份看得见。
    """

    sql_trace: List[Dict[str, Any]] = field(default_factory=list)
    """
    这次运行真正执行过的每一条 SQL，按执行顺序，包括后来被替换掉的。

    step_logs 只留最终交出去的那一版；守卫重规划前的首轮 SQL、回调修正前报错的
    SQL、自洽性投票落选的几次，都只在这里。字段含义见 text2sql_pipeline._trace_entry。
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
            "retrieval_context": self.retrieval_context,
            "cot_output": self.cot_output,
            "sql_trace": self.sql_trace,
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
