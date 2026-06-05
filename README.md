# FlowMarkets

**FlowMarkets** 是基于 FastAPI + CrewAI 的加密货币**交易研究助手**：缠论结构计算、技术分析师（及可选多智能体研究链）、历史胜率与信号质量治理、HTTP API 与统一 CLI。在 OceanBase/MySQL、Redis 与可观测性骨架上持续演进。

- **仓库**（若已改名请替换为实际地址）: [https://github.com/kid0317/fastapi_base](https://github.com/kid0317/fastapi_base)

## 能力概览

| 能力 | 说明 |
|------|------|
| **缠论结构** | Binance K 线 → 笔/段/中枢/买卖点 JSON（默认 `structure-engine` / chanpy） |
| **技术分析师** | `get_chan_structure` + Skill → `TechnicalAnalysisDeliverable`（brief + `chanlun_v2` 状态机） |
| **多级别联立** | 4h / 1h / 15m 预注入 + 1h `history`（对标 chanlun `multi_level_analyzer`） |
| **治理与统计** | `history_enforcement`、`signal_quality`、分析记忆库胜率（`StatsService`） |
| **Crew 模式** | `technical_only`（默认，仅技术分析师）或 `full`（市场→舆情→情绪→技术→综合→交易→组合） |
| **产品面** | REST 同步/流式分析、`chanlun_fm.py` 统一 CLI、`output/` 可选落盘 |
| **引擎实验** | `zs_algo`、可选 `chanlun_icl` 对比分支（见 [docs/structure-engines.md](docs/structure-engines.md)） |

> **说明**：`full` 模式含 synthesis / trader / portfolio，**不含真实回测引擎**；trader 读取治理后状态机、`signal_quality` 与 stats 摘要。

## 技术栈

- **Web**: FastAPI + Uvicorn
- **AI 编排**: CrewAI（智能体/任务 YAML + Python Flow）
- **持久化**: SQLAlchemy 2.0 异步、Alembic；分析记忆库独立 SQLite（`APP_ANALYSIS_DB_URL`）
- **安全**: X-API-Key 鉴权、SlowAPI 限流
- **可观测**: structlog、Prometheus、`X-Request-ID`

## 环境要求

- Python 3.11+
- 推荐 [uv](https://github.com/astral-sh/uv) 管理依赖
- 可选：Redis、MySQL/OceanBase（生产）
- 使用 AI / `full` Crew：配置 `APP_LLM_API_KEY`；`full` 上游搜索需 `APP_BAIDU_API_KEY`

## 快速开始

```bash
# 克隆后进入项目根目录（目录名可能是 fastapi_base 或 flow_markets）
git clone https://github.com/kid0317/fastapi_base.git && cd fastapi_base

# 依赖（任选）
uv sync
# 或: python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

cp .env.example .env
# 至少填写 APP_LLM_API_KEY；使用 full 链或百度搜索时另配 APP_BAIDU_API_KEY
# 未配 APP_ 时 LLM 可 fallback：QWEN_API_KEY / DEEPSEEK_API_KEY；百度：BAIDU_API_KEY

# 启动 API（项目根目录）
uv run uvicorn app.main:app --reload --app-dir src
# 或: PYTHONPATH=src .venv/bin/python -m uvicorn app.main:app --reload --app-dir src
# 或: PYTHONPATH=src python -m app
```

### 本地调试

- **命令行**：`PYTHONPATH=src python -m app`（断点调试时可在 `src/app/__main__.py` 将 `reload=False`）
- **VS Code / Cursor**：`.vscode/launch.json` 提供无 reload / 有 reload / 模块启动配置

### 常用 HTTP 端点

请求需 `X-API-Key`（`APP_API_KEYS` 为空时开发环境可不校验）。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health/live`、`/health/ready` | 健康检查 |
| GET | `/docs` | OpenAPI（开发） |
| GET | `/metrics` | Prometheus |
| GET | `/api/v1/demo/ping` | 示例 |
| POST | `/api/v1/demo/deep-research` | 深度调研 Demo（LLM + 百度搜索） |
| GET | `/api/v1/chan/kline/{symbol}/{interval}` | K 线 + 缠论图表 JSON（仅 `structure-engine`） |
| POST | `/api/v1/flow-markets/analyze` | 同步分析（技术链或 `no_ai` 仅结构） |
| POST | `/api/v1/flow-markets/analyze/stream` | SSE 流式（`start` / `log` / `result` / `complete`） |
| GET | `/api/v1/flow-markets/analyze/stream/{task_id}/result` | 流式结束后取结果（进程内，重启丢失） |

#### FlowMarkets 分析请求体（`FlowMarketsAnalyzeRequest`）

| 字段 | 默认 | 说明 |
|------|------|------|
| `user_query` | （必填） | 研究问题 |
| `symbol` | 可选 | 如 `BTCUSDT`；`multi_tf` / `no_ai` 时必填 |
| `notes` | 可选 | 风险偏好等补充 |
| `timeframe` | `1h` | 单周期 K 线周期 |
| `lookback` | `300` | 50–800，按周期封顶 |
| `multi_tf` | `false` | `true` → 4h/1h/15m 联立 |
| `no_ai` | `false` | `true` → 仅结构，不调 LLM，不落分析库 |
| `save` | 省略 | `true` → 写 `output/`；full 分析且强制落库。省略则仅 `APP_ANALYSIS_SAVE` 控制是否落库，**不写盘** |

**Crew 模式**（环境变量，非请求体）：

| 变量 | 值 | 行为 |
|------|-----|------|
| `APP_FLOW_MARKETS_MODE` 或 `FLOW_MARKETS_MODE` | `technical_only`（默认） | 仅技术分析师 Task |
| 同上 | `full` | 上游四域 → 治理 technical → 注入 stats → synthesis → trading → portfolio（两段 kickoff） |

`full` 上游工具：`get_market_ticker_summary`、`baidu_search`（需百度 Key）。

#### 请求 JSON 示例

以下 `BASE` 默认为 `http://127.0.0.1:8071`（与 `.env` 中 `APP_PORT` 一致）。生产请替换域名并配置真实 `X-API-Key`。

**1. 默认 `technical_only` — 单周期技术分析师**

```json
{
  "user_query": "基于 1h 缠论结构，简述 BTC 趋势、中枢位置与可执行状态机要点，不做投资建议",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "lookback": 300,
  "notes": "中线视角，现货",
  "multi_tf": false,
  "no_ai": false,
  "save": true
}
```

**2. 多级别联立（仍为技术分析师链，`multi_tf=true`）**

```json
{
  "user_query": "对 BTC 做 4h/1h/15m 缠论联立分析：大级别定方向、1h 买卖点、15m 入场节奏",
  "symbol": "BTCUSDT",
  "lookback": 300,
  "multi_tf": true,
  "save": false
}
```

**3. 仅结构（`no_ai`，不调 LLM、不写分析库）**

```json
{
  "user_query": "结构快览",
  "symbol": "BTCUSDT",
  "timeframe": "4h",
  "lookback": 200,
  "no_ai": true,
  "save": true
}
```

**4. `full` 多智能体链（请求体同上，模式由服务端环境变量决定）**

启动 API 前设置：

```bash
export FLOW_MARKETS_MODE=full
export APP_BAIDU_API_KEY=<your-baidu-key>   # 市场/叙事/情绪 Agent 搜索
export APP_LLM_API_KEY=<your-llm-key>
uv run uvicorn app.main:app --reload --app-dir src
```

请求示例（完整研究链，耗时显著长于 `technical_only`）：

```json
{
  "user_query": "综合 BTC 技术面、市场情绪与叙事，给出研究综合与交易 playbook 框架（勿编造未给出的价位）",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "lookback": 300,
  "notes": "风险偏好保守，仅研究用途",
  "save": true
}
```

> `full` 不会在请求体里切换模式；务必确认进程环境为 `APP_FLOW_MARKETS_MODE=full` 或 `FLOW_MARKETS_MODE=full`。本地也可用 `FLOW_MARKETS_MODE=full uv run python scripts/run_flow_markets.py` 调试整条 Crew。

#### curl 示例

```bash
BASE=http://127.0.0.1:8071
# 开发环境 APP_API_KEYS 为空时可省略 Key，或任意占位：
KEY=dev-no-key

# 健康检查
curl -sS "$BASE/health/live"

# 缠论图表（structure-engine）
curl -sS "$BASE/api/v1/chan/kline/BTCUSDT/1h?limit=350&kline_mode=utc" \
  -H "X-API-Key: $KEY" | jq '.data.meta'

# 同步分析 — technical_only（单周期）
curl -sS -X POST "$BASE/api/v1/flow-markets/analyze" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{
    "user_query": "基于 1h 缠论结构简述 BTC 趋势与状态机要点",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "lookback": 300,
    "save": false
  }' | jq '{code, message, success: .data.success, report_len: (.data.report_content | length)}'

# 同步分析 — 多级别
curl -sS -X POST "$BASE/api/v1/flow-markets/analyze" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{
    "user_query": "BTC 多级别缠论联立分析",
    "symbol": "BTCUSDT",
    "lookback": 300,
    "multi_tf": true
  }' | jq '.data | {success, structure_only}'

# 仅结构 no_ai
curl -sS -X POST "$BASE/api/v1/flow-markets/analyze" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{
    "user_query": "结构快览",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "lookback": 200,
    "no_ai": true
  }' | jq '.data | {success, structure_only, bi_count: .structure_payload.bi | length}'

# SSE 流式（观察 log 事件；完整报告在 result 事件 data 中）
curl -sS -N -X POST "$BASE/api/v1/flow-markets/analyze/stream" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -H "Accept: text/event-stream" \
  -d '{
    "user_query": "流式测试：BTC 1h 缠论技术摘要",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "lookback": 200
  }'

# 流式结束后按 task_id 取结果（task_id 来自首条 event:start）
# curl -sS "$BASE/api/v1/flow-markets/analyze/stream/BTCUSDT_1h_1730000000000/result" \
#   -H "X-API-Key: $KEY" | jq .
```

**`full` 模式 curl**（需服务端已 `FLOW_MARKETS_MODE=full` 且配置百度 Key）：

```bash
curl -sS -X POST "$BASE/api/v1/flow-markets/analyze" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{
    "user_query": "BTC 全链路研究：市场结构、叙事情绪、缠论技术、综合与交易建议框架",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "lookback": 300,
    "notes": "full crew 集成测试",
    "save": true
  }' | jq '{code, success: .data.success, files: .data.output_files}'
```

同步成功时响应外形（`ApiResponse`）：

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "…",
  "data": {
    "success": true,
    "message": "分析完成",
    "report_content": "# … Markdown 报告 …",
    "structure_only": false,
    "output_files": ["output/BTCUSDT_1h_…_analysis.json"]
  }
}
```

## 统一 CLI（推荐）

**`scripts/chanlun_fm.py`** — 对标 chanlun `chanlun_ai.py` / `query_stats.py`：

```bash
# 单周期：结构预览 + AI 技术分析师
FM_CHAN_PROGRESS=1 uv run python scripts/chanlun_fm.py analyze BTCUSDT 1h --limit 300 --save

# 多级别 4h/1h/15m
uv run python scripts/chanlun_fm.py analyze BTCUSDT 1h --multi-tf --save

# 仅结构（不调 LLM）
uv run python scripts/chanlun_fm.py structure BTCUSDT 4h --limit 200 --json

# 分析记忆库统计
uv run python scripts/chanlun_fm.py stats --accuracy --symbol BTC/USDT
uv run python scripts/chanlun_fm.py stats --export-csv output/stats_export.csv --charts
```

| 子命令 | 常用参数 |
|--------|----------|
| `analyze` | `symbol`、`interval`、`--limit`、`--multi-tf`、`--save`、`--user-query`、`--json` |
| `structure` | 同上 + `--json`；无 LLM |
| `stats` | `--accuracy`、`--snapshots`、`--export-csv`、`--charts` |

**结构引擎（Phase 7）**（`analyze` / `structure` 均支持）：

```bash
# chanpy 中枢实验
uv run python scripts/chanlun_fm.py structure BTCUSDT 1h --zs-algo over_seg

# 与 chanlun 原 ICL 对比（需同级 chanlun 仓库或 APP_CHANLUN_REPO_ROOT）
uv run python scripts/chanlun_fm.py structure BTCUSDT 1h --engine chanlun_icl --json
```

### 遗留 / 细粒度脚本（仍可用）

| 脚本 | 用途 |
|------|------|
| `scripts/flow_markets_ai.py` | 单周期 analyze（等同 `chanlun_fm analyze` 单周期） |
| `scripts/multi_timeframe_analyze.py` | 多级别 analyze |
| `scripts/run_flow_markets.py` | 本地跑 **full** Crew 链（需 `FLOW_MARKETS_MODE=full`） |
| `scripts/run_technical_analyst.py` | 仅 kickoff 技术 Task |
| `scripts/run_get_chan_structure.py` | 仅结构工具 |
| `scripts/query_analysis_stats.py` | 统计（`chanlun_fm stats` 封装） |
| `scripts/evaluate_outcomes.py` | outcome 回填 |
| `scripts/weight_optimizer.py` | 信号权重优化 |

## 缠论与结构引擎

计算库 vendored 在 `chanpy/`；对外 ID 为 **`structure-engine`**。业务代码：`src/app/services/chan/`。

| 模块 | 作用 |
|------|------|
| `analyze.py` | 图表 API `build_kline_chart_payload` |
| `backend.py` | chanpy 计算 → `ChanEngineICL` |
| `structure.py` | 结构快照 `build_chan_structure_snapshot` |
| `multi_timeframe.py` | 多级别 JSON |
| `engine_policy.py` / `chanlun_icl.py` | 引擎选择与 chanlun 对比 |

**K 线模式**（`APP_KLINE_MODE`）：

| 值 | 说明 |
|----|------|
| `utc`（默认） | Binance 原生周期 |
| `beijing` | 5m 聚合为北京时间桶（验图习惯）；兼容 `CHAN_USE_BEIJING=1` |

**图表 API**（始终 chanpy）：

`GET /api/v1/chan/kline/{symbol}/{interval}?limit=350&kline_mode=utc`

返回：`klines`、`merged_klines`、`bi`、`xd`、`zs`、`fx`、`bsp`；`meta.engine` 为 `structure-engine`。

**结构快照**（`get_chan_structure` / CLI / API `no_ai`）：

- 默认 `meta.engine=structure-engine`，可选 `meta.zs_algo`（`normal` / `over_seg` / `auto`）
- 对比：`APP_CHAN_STRUCTURE_ENGINE=chanlun_icl` → `meta.engine=chanlun_icl`
- 详见 [docs/structure-engines.md](docs/structure-engines.md)

**验图 PNG**：

```bash
uv sync --extra chart
uv run python scripts/demo_chan_chart.py
# output/chan_charts/btcusdt_1d_chan.png
APP_KLINE_MODE=beijing uv run python scripts/demo_chan_chart.py
```

## 分析记忆库与治理

- **库路径**：`APP_ANALYSIS_DB_URL`（默认 `sqlite:///./data/analysis.db`）
- **自动落库**：`APP_ANALYSIS_SAVE=true` 或 API/CLI **`--save` / `save=true`**（同时写 `output/`）
- **仅落库不写盘**：仅 `APP_ANALYSIS_SAVE=true`，不传 `save`
- **工具返回 `history`**：胜率、`state_machine_hints`、`learning_feedback`（样本不足时不强制降级）
- **服务端治理**：`history_enforcement`、`signal_quality`（六维评分）；`full` 模式在 synthesis 前完成 technical 治理

```bash
uv run python scripts/evaluate_outcomes.py
uv run python scripts/query_analysis_stats.py --accuracy
uv run python scripts/show_analysis_db.py --csv -o output/analysis_snapshots.csv
uv run python scripts/stats_visualizer.py
uv run python scripts/weight_optimizer.py --save --method correlation
```

## 项目结构

```
src/app/
├── main.py              # 入口、中间件
├── api/v1/              # flow_markets、chan、demo、health
├── core/                # config、security
├── crews/               # FlowMarkets Crew、tools、skills
├── services/
│   ├── chan/            # 结构引擎、K 线、多级别
│   ├── analyze_streaming.py
│   ├── analysis_output.py
│   └── structure_only.py
├── analysis_store/      # 快照持久化、history、stats
└── schemas/             # API 与 Deliverable 契约
chanpy/                  # vendored 缠论计算库
docs/structure-engines.md
scripts/chanlun_fm.py    # 统一 CLI
tests/
deploy/
```

## 配置说明

复制 `.env.example` 为 `.env`。完整项见示例文件。

### 上游 LLM（AI 分析必填）

| 变量 | 说明 |
|------|------|
| **APP_LLM_API_KEY** | 上游 API Key（**必填**以跑 analyze） |
| QWEN_API_KEY / DEEPSEEK_API_KEY | 未配 `APP_` 时的 fallback |
| APP_LLM_PROVIDER | `aliyun` 或 `deepseek` |
| APP_LLM_MODEL | 如 `qwen-plus`、`deepseek-chat` |
| APP_LLM_BASE_URL | DeepSeek 或兼容网关（可选） |
| APP_LLM_REGION | 阿里云：`cn` / `intl` / `finance` |
| APP_LLM_TIMEOUT | 默认 600 |

### 百度搜索（`full` 链上游 Agent）

| 变量 | 说明 |
|------|------|
| **APP_BAIDU_API_KEY** / BAIDU_API_KEY | 千帆 AppBuilder Key |
| APP_BAIDU_SEARCH_TIMEOUT | 默认 30 |

### FlowMarkets 与缠论

| 变量 | 默认 | 说明 |
|------|------|------|
| APP_FLOW_MARKETS_MODE / FLOW_MARKETS_MODE | `technical_only` | `technical_only` \| `full` |
| APP_ANALYSIS_SAVE | `false` | technical 成功后落分析库 |
| APP_ANALYSIS_DB_URL | `sqlite:///./data/analysis.db` | 分析记忆库 |
| APP_KLINE_MODE | `utc` | `utc` \| `beijing` |
| APP_CHAN_ENGINE_ROOT | （内置 chanpy） | 覆盖结构计算库路径 |
| APP_CHAN_STRUCTURE_ENGINE | `structure-engine` | `chanlun_icl` 仅对比 |
| APP_CHAN_ZS_ALGO | `normal` | `over_seg` \| `auto`（仅 chanpy） |
| APP_CHANLUN_REPO_ROOT | （自动 `../chanlun`） | chanlun 仓库根目录 |

### CrewAI 遥测（避免 `telemetry.crewai.com` 超时）

默认已在代码中关闭出站遥测（`app/core/crewai_env.py`）。若仍看到 `HTTPSConnectionPool(host='telemetry.crewai.com'... Read timed out`，在 `.env` 中显式加入：

```bash
CREWAI_DISABLE_TELEMETRY=true
OTEL_SDK_DISABLED=true
```

需要向 CrewAI 上报遥测时（少见）：`CREWAI_TELEMETRY=true`（会覆盖默认关闭）。

### 其他

| 变量 | 说明 |
|------|------|
| APP_ENV | development / staging / production |
| APP_API_KEYS | 合法 API Key，逗号分隔 |
| APP_DATABASE_URL | 主业务库 |
| APP_SECRET_KEY | 生产必填 |

## 测试

```bash
uv run pytest tests/ -v
```

| 套件 | 说明 |
|------|------|
| `tests/integration/test_flow_markets.py` | 需 LLM Key |
| `tests/integration/test_deep_research.py` | 需 LLM + 百度 Key |
| `tests/test_flow_markets_stream.py` | SSE 流式 |
| `tests/test_engine_policy.py` | Phase 7 引擎与 zs_algo |
| `tests/test_flow_markets_full_split.py` | full 两段链注入 |

```bash
# 仅 FlowMarkets 集成
uv run pytest tests/integration/test_flow_markets.py -v

# 缠论 / 引擎单元测试
uv run pytest tests/test_get_chan_structure.py tests/test_engine_policy.py -q
```

## 部署

- **Docker**: `deploy/docker/Dockerfile`
- **K8s**: `deploy/k8s/deployment.yaml`（`/health/live`、`/health/ready`）
- 敏感配置用 Secret，参见 `deploy/k8s/configmap.example.yaml`

## 设计文档

- 框架总览：`doc/Python AI 应用框架设计文档.md`
- 结构引擎差异：[docs/structure-engines.md](docs/structure-engines.md)

## License

MIT
