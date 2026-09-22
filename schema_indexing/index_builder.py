from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .embedding_client import AliyunEmbeddingClient
from .milvus_client import MilvusSchemaIndexClient
from .objects import ColumnSchema, FieldDocument, TableRelation
from .text_builder import SchemaIndexTextBuilder


@dataclass
class SchemaIndexBuildResult:
    """索引构建结果。"""

    field_collection_name: str
    relation_collection_name: str
    field_document_count: int
    relation_count: int


class SchemaIndexBuilder:
    """
    Schema 索引构建主流程。

    离线写入两类数据：
    1. 字段级索引：用于两阶段召回字段。
    2. 表关系索引：用于根据命中字段所属表构建 SchemaGraph。
    """

    def __init__(
        self,
        text_builder: SchemaIndexTextBuilder,
        embedding_client: AliyunEmbeddingClient,
        milvus_client: MilvusSchemaIndexClient,
    ):
        self.text_builder = text_builder
        self.embedding_client = embedding_client
        self.milvus_client = milvus_client

    def build(
        self,
        columns: List[ColumnSchema],
        relations: List[TableRelation],
        tables: Optional[Dict[str, Any]] = None,
        documents: Optional[List[Any]] = None,
    ) -> SchemaIndexBuildResult:
        """执行索引构建。"""
        if not columns and not documents:
            raise ValueError("columns 和 documents 都为空，无法构建字段索引。")

        # documents 优先。
        #
        # schema_indexing 和 schema_retrieval 各自实现了一套三级索引文本构建，
        # 两套产出的文本 81 个字段全都不一样——这才是两个模块一直没能接起来的
        # 根本原因：不只对象定义重复，核心逻辑也是重复的。
        #
        # 权威的是检索服务那一套，因为只有它会读取 business_meta 里手写的
        # keyword_text / rerank_text 覆盖项，而那些手写文本是这个项目最值钱的资产。
        # 所以索引的职责是**持久化检索服务的产出**，而不是自己再造一遍。
        documents = list(documents) if documents else self.text_builder.build_many(columns)

        vector_texts = [doc.vector_text for doc in documents]
        embeddings = self.embedding_client.embed_texts(vector_texts)

        self.milvus_client.prepare_collections()

        self.milvus_client.insert_field_documents(
            documents=documents,
            embeddings=[
                embedding.astype(float).tolist()
                for embedding in embeddings
            ],
            tables=tables,
        )

        self.milvus_client.insert_relations(relations)

        return SchemaIndexBuildResult(
            field_collection_name=self.milvus_client.config.field_collection_name,
            relation_collection_name=self.milvus_client.config.relation_collection_name,
            field_document_count=len(documents),
            relation_count=len(relations),
        )

    def build_documents_only(
        self,
        columns: List[ColumnSchema],
    ) -> List[FieldDocument]:
        """只构建字段文档，不写入 Milvus。"""
        return self.text_builder.build_many(columns)
