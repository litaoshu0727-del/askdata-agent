"""
本地 Embedding 客户端。

DeepSeek 只提供 Chat 接口，没有 Embedding 服务，所以向量召回这一路改用本地开源模型。
默认使用 BAAI/bge-small-zh-v1.5：中文检索效果好、512 维、模型体积小（约 95MB），
完全离线运行，没有调用次数和费用限制。

对外接口与 AliyunEmbeddingClient 完全一致（embed_texts），
可以直接替换进 VectorIndex 和 HybridSchemaRetrievalService。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class LocalEmbeddingConfig:
    """本地 Embedding 模型配置。"""

    model_name: str = "BAAI/bge-small-zh-v1.5"
    """模型名称。为空时读取环境变量 ASKDATA_EMBEDDING_MODEL。"""

    batch_size: int = 32
    """批量编码大小。"""

    device: str = ""
    """
    推理设备。为空时读取环境变量 ASKDATA_DEVICE，仍为空则由
    sentence-transformers 自动选择（Apple Silicon 上通常是 mps）。
    """

    cache_folder: str = ""
    """模型缓存目录。为空时使用 HuggingFace 默认缓存路径。"""


class LocalBGEEmbeddingClient:
    """
    基于 sentence-transformers 的本地 Embedding 客户端。

    模型采用懒加载：构造时不加载，第一次调用 embed_texts 时才载入，
    避免无关流程（例如只跑关键词召回）被迫等待模型初始化。
    """

    def __init__(self, config: Optional[LocalEmbeddingConfig] = None):
        self.config = config or LocalEmbeddingConfig()

        if not self.config.model_name:
            self.config.model_name = os.getenv(
                "ASKDATA_EMBEDDING_MODEL",
                "BAAI/bge-small-zh-v1.5",
            )

        if not self.config.device:
            self.config.device = os.getenv("ASKDATA_DEVICE", "")

        self._model = None

    def _load_model(self):
        """懒加载 SentenceTransformer 模型。"""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "使用本地 Embedding 需要安装 sentence-transformers："
                "pip install sentence-transformers torch"
            ) from exc

        kwargs = {}

        if self.config.device:
            kwargs["device"] = self.config.device

        if self.config.cache_folder:
            kwargs["cache_folder"] = self.config.cache_folder

        self._model = SentenceTransformer(self.config.model_name, **kwargs)

        return self._model

    @property
    def dimensions(self) -> int:
        """
        向量维度。bge-small-zh-v1.5 为 512。

        sentence-transformers 6.x 把 get_sentence_embedding_dimension
        改名为 get_embedding_dimension，这里两个版本都兼容。
        """
        model = self._load_model()

        getter = getattr(model, "get_embedding_dimension", None) or getattr(
            model, "get_sentence_embedding_dimension"
        )

        return int(getter())

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        批量生成文本向量。

        返回的向量已做 L2 归一化，因此下游可以直接用点积代替 cosine 相似度，
        这一点与 AliyunEmbeddingClient 的行为保持一致。

        Args:
            texts: 待编码文本列表。

        Returns:
            np.ndarray: 形状为 (len(texts), dimensions) 的 float32 矩阵。
        """
        if not texts:
            return np.empty((0, self.dimensions), dtype=np.float32)

        model = self._load_model()

        vectors = model.encode(
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return np.asarray(vectors, dtype=np.float32)
