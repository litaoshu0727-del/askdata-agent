"""
本地 Rerank 客户端。

DeepSeek 没有 Rerank 服务，精排这一路改用本地 Cross-Encoder。
默认使用 BAAI/bge-reranker-base：中文精排效果稳定、模型体积约 1.1GB，
完全离线运行。

对外接口与 AliyunRerankClient 完全一致（rerank），
可以直接替换进 HybridSchemaRetrievalService。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from .rerank_client import RerankDocument, RerankResult


@dataclass
class LocalRerankConfig:
    """本地 Rerank 模型配置。"""

    model_name: str = "BAAI/bge-reranker-base"
    """模型名称。为空时读取环境变量 ASKDATA_RERANK_MODEL。"""

    batch_size: int = 16
    """批量打分大小。"""

    device: str = ""
    """推理设备。为空时读取环境变量 ASKDATA_DEVICE，仍为空则自动选择。"""

    cache_folder: str = ""
    """模型缓存目录。为空时使用 HuggingFace 默认缓存路径。"""


class LocalBGERerankClient:
    """
    基于 sentence-transformers CrossEncoder 的本地 Rerank 客户端。

    与向量召回的双塔结构不同，Cross-Encoder 把 Query 和候选字段文本
    拼成一对送进模型联合编码，因此相关性判断更准，代价是无法预先建索引，
    只能对召回后的少量候选做精排——这正是两阶段检索里精排环节的定位。

    模型采用懒加载。
    """

    def __init__(self, config: Optional[LocalRerankConfig] = None):
        self.config = config or LocalRerankConfig()

        if not self.config.model_name:
            self.config.model_name = os.getenv(
                "ASKDATA_RERANK_MODEL",
                "BAAI/bge-reranker-base",
            )

        if not self.config.device:
            self.config.device = os.getenv("ASKDATA_DEVICE", "")

        self._model = None

    def _load_model(self):
        """懒加载 CrossEncoder 模型。"""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "使用本地 Rerank 需要安装 sentence-transformers："
                "pip install sentence-transformers torch"
            ) from exc

        kwargs = {}

        if self.config.device:
            kwargs["device"] = self.config.device

        if self.config.cache_folder:
            kwargs["cache_folder"] = self.config.cache_folder

        self._model = CrossEncoder(self.config.model_name, **kwargs)

        return self._model

    def rerank(
        self,
        query: str,
        documents: List[RerankDocument],
        top_n: int,
    ) -> List[RerankResult]:
        """
        对候选字段进行精排。

        Args:
            query: 用户原始 Query。
            documents: RRF 融合后的候选字段。
            top_n: 返回数量。

        Returns:
            List[RerankResult]: 按相关性从高到低排序的结果。
        """
        if not documents:
            return []

        model = self._load_model()

        pairs = [(query, doc.text) for doc in documents]

        scores = model.predict(
            pairs,
            batch_size=self.config.batch_size,
            show_progress_bar=False,
        )

        results = [
            RerankResult(
                doc_index=doc.doc_index,
                rerank_score=float(score),
                text=doc.text,
            )
            for doc, score in zip(documents, scores)
        ]

        results.sort(key=lambda item: item.rerank_score, reverse=True)

        return results[:top_n]
