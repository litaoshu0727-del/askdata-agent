from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from .objects import FieldDocument, TableRelation


@dataclass
class MilvusSchemaIndexConfig:
    """Milvus Schema 索引配置。"""

    # 目前milvus不启用服务，保存在本地生成一个db文件
    uri: str = "./schema_index_demo.db"
    token: str = ""

    field_collection_name: str = "schema_field_index_demo"
    relation_collection_name: str = "schema_relation_index_demo"

    embedding_dim: int = 1024
    recreate_collection: bool = True
    metric_type: str = "COSINE"


class MilvusSchemaIndexClient:
    """
    Milvus Schema 索引 Client。

    这里拆成两个 Collection：
    - field_collection：字段级索引，用于两阶段召回字段。
    - relation_collection：表关系索引，用于根据表名 pair 反查关联键。

    两阶段召回只召回字段。
    SchemaGraph 的边，需要在拿到字段所属表之后，再从 relation_collection 中查。
    """

    def __init__(self, config: MilvusSchemaIndexConfig):
        self.config = config

        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise ImportError("缺少 pymilvus，请先安装：pip install pymilvus milvus-lite") from exc

        self.client = MilvusClient(
            uri=self.config.uri,
            token=self.config.token or None,
        )

    def prepare_collections(self) -> None:
        """创建字段 Collection 和关系 Collection。"""
        self.prepare_field_collection()
        self.prepare_relation_collection()

    def prepare_field_collection(self) -> None:
        """创建字段索引 Collection。"""
        from pymilvus import DataType, MilvusClient

        name = self.config.field_collection_name

        if self.client.has_collection(name):
            if self.config.recreate_collection:
                self.client.drop_collection(name)
            else:
                return

        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )

        schema.add_field("doc_id", DataType.VARCHAR, is_primary=True, max_length=512)
        schema.add_field("database", DataType.VARCHAR, max_length=128)
        schema.add_field("table_name", DataType.VARCHAR, max_length=128)
        schema.add_field("column_name", DataType.VARCHAR, max_length=128)
        schema.add_field("data_type", DataType.VARCHAR, max_length=128)
        schema.add_field("semantic_role", DataType.VARCHAR, max_length=128)
        schema.add_field("keyword_text", DataType.VARCHAR, max_length=4096)
        schema.add_field("vector_text", DataType.VARCHAR, max_length=4096)
        schema.add_field("rerank_text", DataType.VARCHAR, max_length=8192)

        # 完整的 ColumnSchema / TableSchema 序列化载荷。
        #
        # 上面那几个标量字段够用来做检索，但不够用来还原提示词上下文——
        # description、aliases、samples、business_usage、value_range
        # 全都不在里面，而它们恰恰是渲染进 CoT 和 SQL 提示词的业务语义。
        #
        # 少了它们，从索引加载出来的 SchemaGraph 会退化成只剩字段名和类型，
        # 链路照样能跑，提示词质量却悄悄塌了一半——又一个静默失败。
        # 所以索引必须自包含：存进去的东西要足以完整还原查询时需要的一切。
        schema.add_field("column_json", DataType.VARCHAR, max_length=32768)
        schema.add_field("table_json", DataType.VARCHAR, max_length=8192)

        schema.add_field(
            "embedding",
            DataType.FLOAT_VECTOR,
            dim=self.config.embedding_dim,
        )

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type=self.config.metric_type,
        )

        self.client.create_collection(
            collection_name=name,
            schema=schema,
            index_params=index_params,
        )

    def prepare_relation_collection(self) -> None:
        """
        创建表关系 Collection。

        relation_key 是核心索引字段，格式：
            database:table_a__table_b

        例如：
            trade_db:interest_info__trade_summary
        """
        from pymilvus import DataType, MilvusClient

        name = self.config.relation_collection_name

        if self.client.has_collection(name):
            if self.config.recreate_collection:
                self.client.drop_collection(name)
            else:
                return

        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )

        schema.add_field("relation_key", DataType.VARCHAR, is_primary=True, max_length=512)
        schema.add_field("database", DataType.VARCHAR, max_length=128)
        schema.add_field("source_table", DataType.VARCHAR, max_length=128)
        schema.add_field("source_column", DataType.VARCHAR, max_length=128)
        schema.add_field("target_table", DataType.VARCHAR, max_length=128)
        schema.add_field("target_column", DataType.VARCHAR, max_length=128)
        schema.add_field("relation_type", DataType.VARCHAR, max_length=128)
        schema.add_field("join_condition", DataType.VARCHAR, max_length=512)
        schema.add_field("description", DataType.VARCHAR, max_length=1024)
        schema.add_field("relation_json", DataType.VARCHAR, max_length=4096)

        self.client.create_collection(
            collection_name=name,
            schema=schema,
        )

    def insert_field_documents(
        self,
        documents: List[FieldDocument],
        embeddings: List[List[float]],
        tables: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        写入字段级索引文档和向量。

        Args:
            documents: 字段级索引文档。
            embeddings: 与 documents 一一对应的向量。
            tables: 表名到 TableSchema 的映射。传入后索引即可自包含，
                从索引加载时能完整还原 SchemaGraph；不传则只存字段，
                加载出来的表信息会缺描述和别名。
        """
        if len(documents) != len(embeddings):
            raise ValueError("documents 和 embeddings 数量不一致。")

        tables = tables or {}
        rows = []

        for doc, embedding in zip(documents, embeddings):
            col = doc.column
            table = tables.get(col.table_name)

            rows.append(
                {
                    "doc_id": doc.doc_id,
                    "database": col.database,
                    "table_name": col.table_name,
                    "column_name": col.column_name,
                    "data_type": col.data_type,
                    "semantic_role": col.semantic_role,
                    "keyword_text": doc.keyword_text,
                    "vector_text": doc.vector_text,
                    "rerank_text": doc.rerank_text,
                    "column_json": json.dumps(asdict(col), ensure_ascii=False),
                    "table_json": (
                        json.dumps(asdict(table), ensure_ascii=False) if table else ""
                    ),
                    "embedding": embedding,
                }
            )

        self.client.insert(
            collection_name=self.config.field_collection_name,
            data=rows,
        )

        self.client.flush(
            collection_name=self.config.field_collection_name,
        )

    @staticmethod
    def _join_condition(relation) -> str:
        """
        取关系的 join 条件。

        schema_indexing 和 schema_retrieval 各自定义了一份 TableRelation，
        字段完全相同，但只有前者带 join_condition 这个 property——
        **字段一样、行为不一样**，这正是两个模块一直没能接起来的深层原因：
        类型看着兼容，实际一调就炸。

        这里按鸭子类型取值，取不到就按关联键现拼一个。
        """
        value = getattr(relation, "join_condition", None)

        if value:
            return str(value)

        return (
            f"{relation.source_table}.{relation.source_column}"
            f" = {relation.target_table}.{relation.target_column}"
        )

    def _relation_key(self, relation) -> str:
        """
        取关系主键。和 join_condition 同样的问题：
        它也是 schema_indexing 那份 TableRelation 独有的 property。
        """
        value = getattr(relation, "relation_key", None)

        if value:
            return str(value)

        return self.build_relation_key(
            database=relation.database,
            table_a=relation.source_table,
            table_b=relation.target_table,
        )

    def insert_relations(self, relations: List[TableRelation]) -> None:
        """
        写入表间关系。

        注意：
        关系不是字段召回的对象，而是 SchemaGraph 构建阶段的边信息。
        """
        rows = []

        for relation in relations:
            relation_payload = {
                "database": relation.database,
                "source_table": relation.source_table,
                "source_column": relation.source_column,
                "target_table": relation.target_table,
                "target_column": relation.target_column,
                "relation_type": relation.relation_type,
                "join_condition": self._join_condition(relation),
                "description": relation.description,
            }

            rows.append(
                {
                    "relation_key": self._relation_key(relation),
                    "database": relation.database,
                    "source_table": relation.source_table,
                    "source_column": relation.source_column,
                    "target_table": relation.target_table,
                    "target_column": relation.target_column,
                    "relation_type": relation.relation_type,
                    "join_condition": self._join_condition(relation),
                    "description": relation.description,
                    "relation_json": json.dumps(relation_payload, ensure_ascii=False),
                }
            )

        if not rows:
            return

        self.client.insert(
            collection_name=self.config.relation_collection_name,
            data=rows,
        )

        self.client.flush(
            collection_name=self.config.relation_collection_name,
        )

    def load_all_fields(self) -> Tuple[List[FieldDocument], List[List[float]], Dict[str, Any]]:
        """
        把整个字段索引读回来，用于在查询侧直接从索引重建检索服务。

        Returns:
            (documents, embeddings, tables)
            documents 与 embeddings 一一对应，tables 为表名到 TableSchema 的映射。
        """
        from .objects import ColumnSchema, FieldDocument, IndexTextBundle, TableSchema

        rows = self.client.query(
            collection_name=self.config.field_collection_name,
            filter="",
            output_fields=[
                "doc_id", "keyword_text", "vector_text", "rerank_text",
                "column_json", "table_json", "embedding",
            ],
            limit=16384,
        )

        rows.sort(key=lambda row: row.get("doc_id", ""))

        documents: List[FieldDocument] = []
        embeddings: List[List[float]] = []
        tables: Dict[str, Any] = {}

        for row in rows:
            payload = json.loads(row["column_json"])
            payload.pop("index_texts", None)

            column = ColumnSchema(
                **payload,
                index_texts=IndexTextBundle(
                    keyword_text=row["keyword_text"],
                    vector_text=row["vector_text"],
                    rerank_text=row["rerank_text"],
                ),
            )

            documents.append(
                FieldDocument(
                    doc_id=row["doc_id"],
                    column=column,
                    keyword_text=row["keyword_text"],
                    vector_text=row["vector_text"],
                    rerank_text=row["rerank_text"],
                )
            )
            embeddings.append(list(row["embedding"]))

            table_json = row.get("table_json") or ""
            if table_json and column.table_name not in tables:
                tables[column.table_name] = TableSchema(**json.loads(table_json))

        return documents, embeddings, tables

    def load_all_relations(self) -> List[TableRelation]:
        """把表关系索引整个读回来。"""
        rows = self.client.query(
            collection_name=self.config.relation_collection_name,
            filter="",
            output_fields=["relation_json"],
            limit=16384,
        )

        relations: List[TableRelation] = []

        for row in rows:
            payload = json.loads(row["relation_json"])
            relations.append(
                TableRelation(
                    database=payload.get("database", ""),
                    source_table=payload.get("source_table", ""),
                    source_column=payload.get("source_column", ""),
                    target_table=payload.get("target_table", ""),
                    target_column=payload.get("target_column", ""),
                    relation_type=payload.get("relation_type", "foreign_key"),
                    description=payload.get("description", ""),
                )
            )

        relations.sort(
            key=lambda r: (r.source_table, r.source_column, r.target_table, r.target_column)
        )
        return relations

    def search_fields(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """简单字段向量检索验证。"""
        results = self.client.search(
            collection_name=self.config.field_collection_name,
            data=[query_embedding],
            anns_field="embedding",
            limit=top_k,
            output_fields=[
                "doc_id",
                "database",
                "table_name",
                "column_name",
                "keyword_text",
                "vector_text",
                "rerank_text",
            ],
        )

        return results[0]

    def query_relations_by_table_pairs(
        self,
        database: str,
        table_pairs: List[tuple[str, str]],
    ) -> List[TableRelation]:
        """
        根据表名组合查询表间关系。

        输入：
            [(suppliers, purchase_orders), (purchase_orders, payments)]

        查询：
            relation_key in [
                "db:purchase_orders__suppliers",
                "db:payments__purchase_orders"
            ]
        """
        if not table_pairs:
            return []

        relation_keys = [
            self.build_relation_key(database, left, right)
            for left, right in table_pairs
        ]

        quoted_keys = ", ".join([f'"{key}"' for key in relation_keys])
        filter_expr = f"relation_key in [{quoted_keys}]"

        rows = self.client.query(
            collection_name=self.config.relation_collection_name,
            filter=filter_expr,
            output_fields=[
                "relation_json",
            ],
        )

        relations: List[TableRelation] = []

        for row in rows:
            payload = json.loads(row["relation_json"])
            relations.append(
                TableRelation(
                    database=payload["database"],
                    source_table=payload["source_table"],
                    source_column=payload["source_column"],
                    target_table=payload["target_table"],
                    target_column=payload["target_column"],
                    relation_type=payload.get("relation_type", "foreign_key"),
                    description=payload.get("description", ""),
                )
            )

        return relations

    def build_relation_key(
        self,
        database: str,
        table_a: str,
        table_b: str,
    ) -> str:
        """构建无向表关系 key。"""
        left, right = sorted([table_a, table_b])
        return f"{database}:{left}__{right}"
