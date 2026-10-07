# schema_retrieval

字段级 Schema 检索：从问题里抽关键词，在全部字段里找出这道题要用的那些，组装成 SchemaGraph
（字段 + 表关系）交给 CoT 规划。

主链路用的是 `HybridSchemaRetrievalService`（[hybrid_schema_retrieval_service.py](hybrid_schema_retrieval_service.py)）：

```text
关键词 → BM25 + 向量两路召回 → RRF 融合 → 精排
      → 关键词覆盖：每个关键词至少留一个字段代表
      → 强命中补回：字面压倒性命中却被精排砍掉的字段补回来
      → 时间约束保底：问题有时间约束、结果里却没有时间字段时，补一个数据覆盖该时段的
      → SchemaGraph
```

## 文件

| 文件 | 内容 |
|---|---|
| `hybrid_schema_retrieval_service.py` | 主链路用的检索服务，`from_sqlite` / `from_milvus` 两种构建方式 |
| `sqlite_loader.py` | 解析 SQLite Schema：字段、外键、样例值、时间字段的覆盖年份 |
| `document_builder.py` | 字段级检索文档 |
| `graph_builder.py` | SchemaGraph 构建 |
| `tokenizer.py` `bm25.py` `retriever.py` | 中英文分词与 BM25 召回 |
| `vector_index.py` | 内存向量索引 |
| `rrf_fusion_client.py` | RRF 融合 |
| `keyword_extractor_client.py` | 大模型关键词抽取 |
| `local_embedding_client.py` `local_rerank_client.py` | 本地 bge 向量与精排（主链路在用） |
| `embedding_client.py` `rerank_client.py` | 阿里云百炼向量与精排 |
| `*_demo.py` | 原作者的分步 Demo，见下文 |

## 几条要知道的事

- **检索参数要随 Schema 规模放大。**精排名额 = 关键词数 × multiplier。默认按大库参数，
  只有 9 个字段的 trade 库显式用小参数，见
  [检索参数要随 Schema 规模放大](../docs/实验记录.md#检索参数要随-schema-规模放大)
- **别手写 `rerank_text`。**手写的精排文本会整个替换自动生成的文本，而自动生成的那份带着
  表描述、别名和样例值。两个库手写的都删了，删后召回反而更好，见
  [第二套留出集](../docs/实验记录.md#第二套留出集修-chinook-精排在没见过的题上验证)
- **时间字段的覆盖年份不进任何索引文本和提示词**，只给时间约束保底用，见
  [只留保底](../docs/实验记录.md#只留保底)

## 分步 Demo

原作者的教学 Demo，在 trade 库上一步步演示召回过程，用的是阿里云百炼客户端。没配
`DASHSCOPE_API_KEY` 和 `DASHSCOPE_WORKSPACE_ID` 时，向量和精排走 Mock，降级记录里会写明。

```bash
python -m schema_retrieval.keyword_recall_demo          # 关键词召回
python -m schema_retrieval.vector_recall_demo           # 向量召回
python -m schema_retrieval.hybrid_recall_demo           # 关键词 + 向量 + RRF
python -m schema_retrieval.hybrid_rerank_schema_demo    # 再加精排和 SchemaGraph
```

要看主链路的真实检索结果，用 `python -m askdata_pipeline.ecommerce_demo` 或 Web 界面。
