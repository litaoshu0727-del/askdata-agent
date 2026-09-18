from __future__ import annotations

import sqlite3
from pathlib import Path


def create_trade_demo_database(db_path: str | Path) -> Path:
    """
    创建端到端流程测试数据库。

    数据库包含：
    - trade_summary：用户交易汇总表
    - interest_info：用户利率信息表

    这里直接读取 sql/create_trade_demo.sql，方便你单独查看和修改测试数据。
    """
    db_path = Path(db_path)

    if db_path.exists():
        db_path.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[1]
    sql_path = project_root / "sql" / "create_trade_demo.sql"
    sql_text = sql_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql_text)
    conn.commit()
    conn.close()

    return db_path


def get_trade_business_meta() -> dict:
    """
    Demo 业务元数据。

    这些信息用于增强表级 Schema、字段级 Schema 和三级索引文本。
    """
    return {
        "trade_summary": {
            "description": "该表记录用户交易汇总信息，包括用户累计交易笔数、累计交易金额、活跃交易天数以及最近交易时间。",
            "aliases": ["用户交易汇总表", "交易统计表"],
            "columns": {
                "user_id": {
                    "description": "用户唯一标识。",
                    "aliases": ["用户ID", "客户ID"],
                    "semantic_role": "join_key",
                    "business_usage": "用于唯一标识交易汇总表中的用户。",
                    "keyword_text": "user_id 用户ID 客户ID 用户唯一标识 交易汇总表",
                    "vector_text": "字段名：user_id。所属表：trade_summary。该字段表示交易汇总表中的用户唯一标识。",
                    "rerank_text": "字段：trade_summary.user_id。含义：用户唯一标识。角色：join_key。",
                },
                "total_trade_count": {
                    "description": "用户累计交易总笔数，表示用户在统计周期内完成的交易次数。",
                    "aliases": ["总交易笔数", "累计交易笔数", "交易笔数", "交易次数"],
                    "semantic_role": "metric_filter",
                    "value_range": "整数，>= 0",
                    "data_distribution": "多数用户集中在0-50区间，高频交易用户可能超过50000。",
                    "business_usage": "用于衡量用户交易活跃程度，筛选高频交易用户。",
                    "samples": ["0", "12", "5800", "56000", "102430"],
                    "keyword_text": "total_trade_count 总交易笔数 累计交易笔数 交易笔数 交易次数 高频交易 大于50000 用户交易汇总表 交易统计表",
                    "vector_text": "字段名：total_trade_count。所属表：trade_summary。该字段表示用户累计交易总笔数，用于筛选高频交易用户。",
                    "rerank_text": "字段：trade_summary.total_trade_count。含义：用户累计交易总笔数。别名：总交易笔数、累计交易笔数、交易笔数、交易次数。取值范围：整数，>=0。数据分布：高频交易用户可能超过50000。用途：筛选总交易笔数大于某个阈值的用户。",
                },
                "total_trade_amount": {
                    "description": "用户累计交易金额。",
                    "aliases": ["交易金额", "累计交易金额", "成交金额", "交易总额"],
                    "semantic_role": "metric",
                    "value_range": ">= 0",
                    "business_usage": "用于衡量用户交易价值、统计交易金额或识别高价值用户。",
                    "samples": ["0.00", "5300.50", "230000.00", "1800000.00"],
                    "keyword_text": "total_trade_amount 交易金额 累计交易金额 成交金额 交易总额 交易规模 高价值用户",
                    "vector_text": "字段名：total_trade_amount。所属表：trade_summary。该字段表示用户累计交易金额。",
                    "rerank_text": "字段：trade_summary.total_trade_amount。含义：用户累计交易金额。用途：统计交易金额或识别高价值用户。",
                },
                "active_days": {
                    "description": "用户活跃交易天数。",
                    "aliases": ["活跃天数", "交易活跃天数"],
                    "semantic_role": "metric",
                    "business_usage": "用于衡量用户交易活跃程度。",
                },
                "last_trade_time": {
                    "description": "用户最近一次交易时间。",
                    "aliases": ["最近交易时间", "最后交易时间"],
                    "semantic_role": "time",
                    "business_usage": "用于按最近交易时间筛选或排序。",
                },
            },
        },
        "interest_info": {
            "description": "该表记录用户利率信息，包括用户利率类型、利率数值以及利率生效状态等内容。",
            "aliases": ["用户利率表", "利率信息表"],
            "columns": {
                "user_id": {
                    "description": "用户唯一标识。",
                    "aliases": ["用户ID", "客户ID"],
                    "semantic_role": "join_key",
                    "business_usage": "用于唯一标识利率信息表中的用户。",
                    "keyword_text": "user_id 用户ID 客户ID 用户唯一标识 利率信息表",
                    "vector_text": "字段名：user_id。所属表：interest_info。该字段表示利率信息表中的用户唯一标识。",
                    "rerank_text": "字段：interest_info.user_id。含义：用户唯一标识。角色：join_key。",
                },
                "interest_rate": {
                    "description": "用户对应年化利率。",
                    "aliases": ["利率", "年化利率", "用户利率", "利率数值"],
                    "semantic_role": "output_metric",
                    "value_range": "0-100",
                    "data_distribution": "不同用户分层对应不同利率。",
                    "business_usage": "用于展示或分析用户当前适用的年化利率。",
                    "samples": ["2.35", "3.12", "4.58", "4.95"],
                    "keyword_text": "interest_rate 利率 年化利率 用户利率 利率数值 用户利率表 利率信息表",
                    "vector_text": "字段名：interest_rate。所属表：interest_info。该字段表示用户对应年化利率，通常作为查询结果输出。",
                    "rerank_text": "字段：interest_info.interest_rate。含义：用户对应年化利率。别名：利率、年化利率、用户利率、利率数值。取值范围：0-100。用途：当用户询问利率是多少时，通常作为输出字段。",
                },
                "rate_type": {
                    "description": "利率类型。",
                    "aliases": ["利率类型", "利率分层"],
                    "semantic_role": "dimension",
                    "business_usage": "用于区分标准、VIP、高价值等利率类型。",
                },
                "effective_status": {
                    "description": "利率生效状态。",
                    "aliases": ["生效状态", "是否生效"],
                    "semantic_role": "filter",
                    "business_usage": "用于筛选当前有效或无效的利率记录。",
                },
            },
        },
    }


def get_trade_relations_meta() -> list[dict]:
    """
    Demo 表关系元数据。

    当前 SQLite 可以通过外键提取出关系。
    这里保留结构，后续可以写入 Milvus 的表关系 Collection。
    """
    return [
        {
            "database": "trade_db",
            "source_table": "interest_info",
            "source_column": "user_id",
            "target_table": "trade_summary",
            "target_column": "user_id",
            "description": "通过用户ID关联用户交易汇总信息与用户利率信息。",
        }
    ]
