from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from cot_planning import CotPlanner, ThinkingModelClient, ThinkingModelConfig
from askdata_diagnostics import Codes, collect, emit
from llm_config import has_chat_provider, use_local_models
from mcp_router import MCPRouter, SQLiteMCPExecutor
from schema_retrieval.hybrid_schema_retrieval_service import (
    HybridSchemaRetrievalConfig,
    HybridSchemaRetrievalService,
)
from schema_retrieval.rerank_client import AliyunRerankClient, AliyunRerankConfig
from schema_retrieval.rrf_fusion_client import RRFFusionConfig
from sql_generation import (
    CoderModelClient,
    CoderModelConfig,
    CotStep,
    LocalSchemaStore,
    SqlGenerator,
)

from .demo_data import create_trade_demo_database, get_trade_business_meta
from .ecommerce_data import (
    create_ecommerce_demo_database,
    get_ecommerce_business_meta,
)
from .local_clients import LocalHashEmbeddingClient, SimpleKeywordExtractor
from .query_rewriter import ContextualQueryRewriter
from .objects import PipelineConfig, PipelineResult, StepExecutionLog


# CoT 判定"Schema 支撑不了"时会在四元组里留下的标记
MISSING_SCHEMA_MARKERS = ("缺失", "无法支撑", "不存在", "未找到", "没有该字段", "不支持")


def _is_missing_schema_step(cot_step) -> bool:
    """
    判断 CoT 是否已经判定 Schema 支撑不了这个问题。

    只看"数据库"和"输出目标"两项——这两项按约定应该填具体的库名和字段，
    一旦出现"缺失"字样，说明 CoT 自己已经得出了无法回答的结论。
    不看"操作指令"，因为那段自然语言里提到"缺失"未必代表整体不可答。
    """
    for field_value in (cot_step.database, cot_step.output_target):
        text = (field_value or "").strip()

        if any(marker in text for marker in MISSING_SCHEMA_MARKERS):
            return True

    return False


class AskDataText2SQLPipeline:
    """
    AskData Text2SQL 端到端流程。

    当前实现串联：
    1. 创建测试数据库和 Schema 元数据
    2. Schema 检索与 SchemaGraph 构建
    3. CoT 四元组规划
    4. SQL 生成
    5. MCP 路由执行

    暂不包含结果校验与回调修正。
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

        # 建索引发生在构造阶段，这时的降级（例如向量客户端是哈希伪向量）
        # 同样会影响每一次查询结果，所以单独收下来，附加到每次 run() 的结果里。
        with collect() as setup_diagnostics:
            self.keyword_extractor = self._build_keyword_extractor()
            self.query_rewriter = ContextualQueryRewriter()
            self.db_path, self.business_meta = self._prepare_dataset()

            self.schema_retrieval_service = self._build_schema_retrieval_service()
            self.cot_planner = self._build_cot_planner()
            self.mcp_router = self._build_mcp_router()

        self.setup_diagnostics = list(setup_diagnostics)

    def run(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        conversation_context: str = "",
    ) -> PipelineResult:
        """
        执行完整 Text2SQL 流程。
        """
        with collect() as diagnostics:
            return self._run_inner(
                query=query,
                keywords=keywords,
                conversation_context=conversation_context,
                diagnostics=diagnostics,
            )

    def _run_inner(
        self,
        query: str,
        keywords: Optional[List[str]],
        conversation_context: str,
        diagnostics: list,
    ) -> PipelineResult:
        """执行流程主体，降级记录由外层 collect() 负责收集。"""
        # 先做指代消解，把"它们的退款金额呢"改写成自包含的问题。
        # 必须放在关键词抽取之前，否则抽出来的是"它们"这种没有检索价值的代词。
        rewrite = self.query_rewriter.rewrite(query, conversation_context)
        effective_query = rewrite.effective

        resolved_keywords = keywords or self.keyword_extractor.extract(effective_query)

        contextual_query = effective_query
        if conversation_context.strip():
            contextual_query = (
                f"以下是与当前问题相关的会话记忆：\n{conversation_context}\n\n"
                f"当前用户问题：{effective_query}"
            )

        retrieval_result = self.schema_retrieval_service.retrieve(
            query=contextual_query,
            keywords=resolved_keywords,
        )

        schema_graph = retrieval_result.schema_graph
        schema_context = schema_graph.to_prompt_context()

        cot_result = self.cot_planner.plan(
            user_query=contextual_query,
            schema_graph=schema_graph,
        )

        # CoT 说"缺失"时，先别急着信。
        #
        # 它只看到了检索交给它的那一小块 Schema——"我没看到"和"库里没有"
        # 是两回事。实测里 "北京用户下了多少单" 被判缺失，理由是
        # "缺少 dim_user 的城市字段"，而 dim_user.city 明明存在，只是这轮没召回。
        #
        # 所以拒答必须建立在完整信息上：把全量 Schema 摆出来重新规划一次，
        # 只有在看过全部字段之后仍然判缺失，这个拒答才可信。
        if any(_is_missing_schema_step(step) for step in cot_result.steps):
            full_graph = self._build_full_schema_graph()

            retry_result = self.cot_planner.plan(
                user_query=contextual_query,
                schema_graph=full_graph,
            )

            if not any(_is_missing_schema_step(step) for step in retry_result.steps):
                # 全量 Schema 下能答 —— 说明刚才是检索漏了，不是库里没有。
                # 模型的"缺失"声明因此成了一个高质量的召回失败信号。
                emit(
                    Codes.SCHEMA_RECALL_MISS,
                    "CoT 判缺失但全量 Schema 下可以回答，实为检索漏召回，已用全量 Schema 重规划",
                    问题=effective_query[:60],
                )
                cot_result = retry_result
                schema_graph = full_graph
                schema_context = schema_graph.to_prompt_context()

        schema_store = LocalSchemaStore.from_schema_graph(schema_graph)

        sql_generator = SqlGenerator(
            schema_store=schema_store,
            coder_client=CoderModelClient(
                CoderModelConfig(
                    use_mock_when_no_api_key=True,
                )
            ),
        )

        step_logs: List[StepExecutionLog] = []

        for cot_step in cot_result.steps:
            # CoT 判定 Schema 支撑不了，就到此为止，不进 SQL 生成。
            #
            # 光靠 Prompt 约束不住：实测抓到过 CoT 明确写了"缺少发货时间"，
            # 下游照样用 finish_time - pay_time 算出 93.6 小时交上去。
            # 嘴上承认、手上照编，比闷头编更有欺骗性——它看起来还挺严谨。
            if _is_missing_schema_step(cot_step):
                emit(
                    Codes.SCHEMA_INSUFFICIENT,
                    "CoT 判定 Schema 无法支撑该问题，已阻断 SQL 生成",
                    缺失说明=cot_step.processing_objects[:100],
                )
                continue

            sql_cot_step = CotStep(
                database=cot_step.database,
                processing_objects=cot_step.processing_objects,
                operation_instruction=cot_step.operation_instruction,
                output_target=cot_step.output_target,
            )

            local_schema = schema_store.extract_local_schema(sql_cot_step)
            sql_result = sql_generator.generate(sql_cot_step)

            execution_request = sql_result.to_execution_request()
            execution_result = self.mcp_router.execute(execution_request)

            # SQL 跑通但一行都没返回，往往不是"确实没有数据"，
            # 而是筛选条件有问题——多轮追问里最常见的就是模型凭空推断了一个 ID。
            if execution_result.success and not execution_result.rows:
                emit(
                    Codes.EMPTY_RESULT_SET,
                    "SQL 执行成功但返回 0 行，请检查筛选条件是否正确"
                    "（多轮追问中常见于凭空推断的 ID）",
                    SQL=" ".join(sql_result.sql.split())[:120],
                )

            step_logs.append(
                StepExecutionLog(
                    database=sql_cot_step.database,
                    cot_step=sql_cot_step,
                    local_schema=local_schema.to_prompt_context(),
                    sql=sql_result.sql,
                    execution_request=execution_request,
                    execution_result=execution_result.to_dict(),
                )
            )

        return PipelineResult(
            query=query,
            rewritten_query=rewrite.rewritten if rewrite.changed else "",
            keywords=resolved_keywords,
            schema_context=schema_context,
            cot_output=cot_result.raw_output,
            step_logs=step_logs,
            diagnostics=self.setup_diagnostics + list(diagnostics),
        )

    def _build_schema_retrieval_service(self) -> HybridSchemaRetrievalService:
        """
        构建 Schema 检索服务。
        """
        if use_local_models():
            # DeepSeek 只有 Chat 接口，向量召回与精排改用本地 bge 开源模型。
            from schema_retrieval.local_embedding_client import LocalBGEEmbeddingClient
            from schema_retrieval.local_rerank_client import LocalBGERerankClient

            embedding_client = LocalBGEEmbeddingClient()
            rerank_client = LocalBGERerankClient()
        else:
            # 未启用本地模型时保持原行为：哈希伪向量 + 规则排序，用于快速跑通链路。
            embedding_client = LocalHashEmbeddingClient(dimensions=1024)

            rerank_client = AliyunRerankClient(
                AliyunRerankConfig(
                    api_key="",
                    workspace_id="",
                    model="qwen-rerank",
                )
            )

        return HybridSchemaRetrievalService.from_sqlite(
            db_path=self.db_path,
            database_name=self.config.database_name,
            business_meta=self.business_meta,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            keyword_extractor=None,
            config=self._build_retrieval_config(),
            sample_size=self.config.sample_size,
        )

    def _build_full_schema_graph(self):
        """
        用库里全部表和字段拼一张完整 SchemaGraph。

        只在复核拒答时使用：81 个字段放进 Prompt 完全放得下，
        而一个拒答如果建立在残缺信息上，就没有任何可信度。
        """
        from collections import defaultdict

        from schema_retrieval.objects import SchemaGraph

        service = self.schema_retrieval_service

        columns_by_table = defaultdict(list)
        for column in service.columns:
            columns_by_table[column.table_name].append(column)

        database = ""
        if service.tables:
            database = next(iter(service.tables.values())).database

        return SchemaGraph(
            database=database,
            tables=dict(service.tables),
            columns=dict(columns_by_table),
            relations=list(service.relations),
        )

    def _build_retrieval_config(self) -> HybridSchemaRetrievalConfig:
        """
        构建 Schema 检索配置。

        召回和精排的 top_k 必须随 Schema 规模一起放大，否则大库上会漏召回。

        以默认参数为例：rerank_top_n = 关键词数 × rerank_top_multiplier，
        2 个关键词只会保留 4 个字段。这个量级对两张表 9 个字段的 trade 库够用，
        但放到 11 张表 81 个字段的电商库上，光是金额类字段就有 9 个，
        4 个名额连候选都装不下，必然漏掉输出字段（例如漏掉 shop_name，
        导致只能返回 shop_id）。
        """
        dataset = (self.config.dataset or "trade").strip().lower()

        if dataset == "ecommerce":
            # 81 个字段的大库：放大召回窗口，给精排留足候选。
            return HybridSchemaRetrievalConfig(
                per_keyword_top_k=30,
                include_join_columns=True,
                rrf_config=RRFFusionConfig(
                    rrf_k=60,
                    truncate_multiplier=6,
                    min_fused_top_k=20,
                    max_fused_top_k=80,
                    final_top_k=60,
                    route_weights={
                        "keyword": 1.0,
                        "vector": 1.0,
                    },
                ),
                rerank_top_multiplier=6,
                rerank_min_top_n=10,
                rerank_max_top_n=30,
            )

        # trade 库字段少，保持原有参数。
        return HybridSchemaRetrievalConfig(
            per_keyword_top_k=20,
            include_join_columns=True,
            rrf_config=RRFFusionConfig(
                rrf_k=60,
                truncate_multiplier=6,
                min_fused_top_k=10,
                max_fused_top_k=50,
                final_top_k=20,
                route_weights={
                    "keyword": 1.0,
                    "vector": 1.0,
                },
            ),
            rerank_top_multiplier=2,
            rerank_min_top_n=2,
            rerank_max_top_n=20,
        )

    def _prepare_dataset(self):
        """
        按 config.dataset 准备测试库和业务元数据。

        Returns:
            tuple: (数据库路径, 业务元数据)
        """
        dataset = (self.config.dataset or "trade").strip().lower()

        if dataset == "ecommerce":
            return (
                create_ecommerce_demo_database(self.config.db_path),
                get_ecommerce_business_meta(),
            )

        if dataset == "trade":
            return (
                create_trade_demo_database(self.config.db_path),
                get_trade_business_meta(),
            )

        raise ValueError(
            f"未知的 dataset：{self.config.dataset}。可选值：trade / ecommerce。"
        )

    def _build_keyword_extractor(self):
        """
        构建关键词抽取器。

        有大模型 Key 时用模型抽词，效果远好于本地规则切词；
        没有 Key 时退回 SimpleKeywordExtractor，保证链路仍可跑通。
        """
        if not has_chat_provider():
            return SimpleKeywordExtractor()

        from schema_retrieval.keyword_extractor_client import (
            AliyunKeywordExtractor,
            AliyunKeywordExtractorConfig,
        )

        return AliyunKeywordExtractor(AliyunKeywordExtractorConfig())

    def _build_cot_planner(self) -> CotPlanner:
        """
        构建 CoT 规划器。
        """
        return CotPlanner(
            thinking_client=ThinkingModelClient(
                ThinkingModelConfig(
                    use_mock_when_no_api_key=True,
                    temperature=0.0,
                    # CoT 规划开着 thinking 模式，默认 60s 会偶发超时。
                    timeout=150,
                )
            )
        )

    def _build_mcp_router(self) -> MCPRouter:
        """
        构建 MCP 路由器。
        """
        router = MCPRouter()

        router.register_executor(
            database=self.config.database_name,
            executor=SQLiteMCPExecutor(
                database=self.config.database_name,
                db_path=self.db_path,
                readonly=True,
            ),
        )

        return router
