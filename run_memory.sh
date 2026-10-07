#!/usr/bin/env bash
# 长短期记忆 + 路由联合 Demo，用固定的用户和会话 ID 跑。
#
# Demo 默认每次自动生成新 ID，避免旧数据干扰；这里固定下来，重复运行时能接着上一次的
# 记忆，看长期召回和摘要怎么累积。要从头来，删掉 runtime_data/my_memory.db。
#
#   bash run_memory.sh
#   PYTHON=/path/to/env/bin/python bash run_memory.sh   # 没激活环境时指定解释器

set -euo pipefail
cd "$(dirname "$0")"

"${PYTHON:-python}" -m askdata_pipeline.memory_end_to_end_demo \
  --user-id user-001 \
  --session-id session-001 \
  --memory-db runtime_data/my_memory.db
