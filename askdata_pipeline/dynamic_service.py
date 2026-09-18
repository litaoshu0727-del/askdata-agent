from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from askdata_memory import ConversationMemoryContext, ConversationMemoryService, LongTermMemory
from cot_planning import ThinkingModelClient, ThinkingModelConfig

from .conversation_service import MemoryAwareAskDataService
from .data_qa import DataQAClient, ModelDataQAClient, RuleBasedDataQAClient
from .objects import PipelineResult
from .routing import (
    DynamicIntentRouter,
    ModelIntentClassifier,
    RouteDecision,
    RouteType,
)
from .text2sql_pipeline import AskDataText2SQLPipeline


@dataclass
class RoutedAskDataResult:
    decision: RouteDecision
    answer: str
    memory_context: ConversationMemoryContext
    pipeline_result: Optional[PipelineResult] = None

    @property
    def queried_database(self) -> bool:
        return self.pipeline_result is not None


class DynamicAskDataService:
    """记忆感知的动态路由入口：按意图选择 Text2SQL 或数据问答。"""

    def __init__(
        self,
        pipeline: AskDataText2SQLPipeline,
        memory: ConversationMemoryService,
        *,
        router: Optional[DynamicIntentRouter] = None,
        data_qa_client: Optional[DataQAClient] = None,
        use_model_when_available: bool = True,
    ):
        self.pipeline = pipeline
        self.memory = memory
        self.memory_pipeline = MemoryAwareAskDataService(pipeline, memory)
        model_client = self._build_model_client() if use_model_when_available else None
        self.router = router or DynamicIntentRouter(
            model_classifier=(ModelIntentClassifier(model_client) if model_client else None)
        )
        self.data_qa_client = data_qa_client or (
            ModelDataQAClient(model_client, business_meta=getattr(pipeline, "business_meta", None))
            if model_client
            else RuleBasedDataQAClient()
        )

    def run(
        self,
        *,
        user_id: str,
        session_id: str,
        query: str,
        enable_long_term: bool = False,
        long_term_top_k: Optional[int] = None,
    ) -> RoutedAskDataResult:
        context = self.memory.begin_user_turn(
            user_id=user_id,
            session_id=session_id,
            query=query,
            enable_long_term=enable_long_term,
            long_term_top_k=long_term_top_k,
        )
        decision = self.router.route(query, context)

        if decision.route == RouteType.DATABASE_QUERY:
            response = self.memory_pipeline.run_with_context(
                user_id=user_id,
                session_id=session_id,
                query=query,
                context=context,
                assistant_metadata={"route_decision": decision.to_dict()},
            )
            return RoutedAskDataResult(
                decision=decision,
                answer=response.answer,
                memory_context=context,
                pipeline_result=response.pipeline_result,
            )

        answer = self.data_qa_client.answer(query, context)
        self.memory.record_assistant_message(
            user_id=user_id,
            session_id=session_id,
            content=answer,
            message_type="data_qa",
            metadata={"route_decision": decision.to_dict()},
        )
        return RoutedAskDataResult(
            decision=decision,
            answer=answer,
            memory_context=context,
        )

    def save_result_to_personal_knowledge_base(
        self, *, user_id: str, result: PipelineResult
    ) -> LongTermMemory:
        return self.memory.save_pipeline_result(user_id=user_id, result=result)

    @staticmethod
    def _build_model_client():
        from llm_config import has_chat_provider

        if not has_chat_provider():
            return None
        return ThinkingModelClient(
            ThinkingModelConfig(
                temperature=0.0,
                use_mock_when_no_api_key=False,
            )
        )
