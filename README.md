# FlowMarkets

**FlowMarkets** 为本项目对外名称：在 FastAPI、CrewAI、OceanBase 与云原生可观测性骨架上，演进为加密货币交易研究助手（标的筛选、舆情、K 线、策略与回测等能力按迭代接入）。

- **仓库**（若已改名请替换为实际地址）: [https://github.com/kid0317/fastapi_base](https://github.com/kid0317/fastapi_base)

## 技术栈

- **Web**: FastAPI + Uvicorn
- **AI 编排**: CrewAI（智能体/任务/流程 YAML + Python）
- **持久化**: SQLAlchemy 2.0 异步（OceanBase/MySQL 兼容）、Alembic 迁移、本地文件客户端
- **安全**: X-API-Key 鉴权、SlowAPI 限流
- **可观测**: structlog 结构化日志、Prometheus 指标、Request ID 贯穿

## 环境要求

- Python 3.11+
- 可选：Redis、MySQL/OceanBase（生产）

## 快速开始

```bash
# 克隆（默认仓库目录名为 fastapi_base；若你本地使用 flow_markets 等名称，请 cd 到实际目录）
git clone https://github.com/kid0317/fastapi_base.git && cd fastapi_base

# 虚拟环境与依赖
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 配置（复制后填入阿里云/百度 API Key 等，见下方「配置说明」）
cp .env.example .env
# 编辑 .env，至少填写 APP_LLM_API_KEY；深度调研 Demo 另需 APP_BAIDU_API_KEY；
# 未填 APP_ 时 LLM Key 可 fallback：QWEN_API_KEY 或 DEEPSEEK_API_KEY；百度可 fallback：BAIDU_API_KEY

# 启动（任选其一，在项目根目录）
# 方式 A：虚拟环境激活后
uvicorn app.main:app --reload --app-dir src
# 方式 B：直接用 venv 的 Python（推荐，避免子进程用错解释器）APP_LLM_API_KEY
.venv/bin/python -m uvicorn app.main:app --reload --app-dir src
# 方式 C：以模块运行（需设置 PYTHONPATH）
PYTHONPATH=src python -m app
```

### 本地调试

- **命令行**（项目根目录，先激活 `.venv` 或使用 `.venv/bin/python`）：
  ```bash
  PYTHONPATH=src python -m app
  ```
  断点调试时可在 `src/app/__main__.py` 里把 `reload=True` 改为 `False`，避免 reload 子进程导致断点不命中。
- **Cursor / VS Code**：已配置 `.vscode/launch.json`，在「运行和调试」里选择：
  - **FastAPI (调试，无 reload)**：适合打断点调试，单进程。
  - **FastAPI (开发，reload)**：改代码自动重载。
  - **Python: 以模块运行 app**：以 `python -m app` 方式启动，便于在 `__main__.py` 里设断点。

### 常用端点

- 健康检查: `GET /health/live`、`GET /health/ready`
- API 文档: `GET /docs`（开发环境）
- 指标: `GET /metrics`
- 示例接口: `GET /api/v1/demo/ping`（需请求头 `X-API-Key`，开发环境可不配置 APP_API_KEYS）
- **Demo 深度调研**: `POST /api/v1/demo/deep-research`，请求体须为 JSON：必填 `topic`（非空字符串，1–500 字），可选 `extra_instructions`（字符串或 null）。需请求头 `Content-Type: application/json`、`X-API-Key`。返回 422 时查看响应 `detail` 定位校验错误。需配置 LLM + 百度搜索 API Key。
- **FlowMarkets 交易研究**: `POST /api/v1/flow-markets/analyze`，JSON 必填 `user_query`，可选 `symbol`、`notes`；YAML+CrewBase 顺序链，各 Task 通过 `output_pydantic` 由 CrewAI 约束结构化输出（通义千问等模型）。

## 项目结构

```
src/app/
├── main.py           # 入口、中间件、异常处理
├── api/v1/           # 版本化 API、dependencies
├── core/             # config、security
├── crews/            # agents、tasks、flows、tools、llm（CrewAI）
├── db/               # clients、models、migrations、repositories
├── schemas/          # Pydantic Request/Response/Domain
├── services/chan/    # analyze / backend / chart / kline / types
└── observability/
chanpy/               # vendored 缠论结构计算库（目录名保留；业务代码称「结构引擎」）
scripts/demo_chan_chart.py
tests/                # unit、integration
deploy/               # docker、k8s、grafana
```

## 配置说明

复制 `.env.example` 为 `.env` 后，**至少需填入以下与阿里云、百度相关的环境变量**（其余可选）：

### 上游 LLM（必填以使用 AI 编排）

| 变量                                            | 说明                                        | 必填   | 获取方式                               |
| ----------------------------------------------- | ------------------------------------------- | ------ | -------------------------------------- |
| **APP_LLM_API_KEY**                             | 上游 API Key                                | **是** | 随 Provider 而定（见下行）             |
| （备用）**QWEN_API_KEY** / **DEEPSEEK_API_KEY** | 未配置 `APP_LLM_API_KEY` 时的 fallback      | 否     | 与 DashScope / DeepSeek 控制台密钥一致 |
| APP_LLM_PROVIDER                                | `aliyun`（通义千问）或 `**deepseek`\*\*     | 否     | 默认 aliyun                            |
| APP_LLM_MODEL                                   | 如 `qwen-plus`；DeepSeek 如 `deepseek-chat` | 否     | 默认 qwen-plus                         |
| APP_LLM_BASE_URL                                | DeepSeek 或兼容网关根 URL（可选）           | 否     | 见 `.env.example`                      |
| APP_LLM_REGION                                  | 仅阿里云：`cn` / `intl` / `finance`         | 否     | 默认 cn                                |
| APP_LLM_TIMEOUT                                 | 请求超时秒数                                | 否     | 默认 600                               |

阿里云 Key 获取：[阿里云百炼 / 灵积控制台](https://dashscope.console.aliyun.com/)。DeepSeek：[DeepSeek 开放平台](https://platform.deepseek.com/)。

### 百度千帆搜索（百度搜索工具，使用搜索时必填）

| 变量                                          | 说明                        | 必填                       | 获取方式                                                                            |
| --------------------------------------------- | --------------------------- | -------------------------- | ----------------------------------------------------------------------------------- |
| **APP_BAIDU_API_KEY**（或 **BAIDU_API_KEY**） | 百度千帆 AppBuilder API Key | **使用百度搜索工具时必填** | [百度智能云千帆控制台](https://console.bce.baidu.com/qianfan/) 创建应用获取 API Key |
| APP_BAIDU_SEARCH_TIMEOUT                      | 搜索请求超时秒数            | 否                         | 默认 30                                                                             |

### 其他常用配置

| 变量             | 说明                               | 必填         |
| ---------------- | ---------------------------------- | ------------ |
| APP_ENV          | development / staging / production | 否           |
| APP_LOG_LEVEL    | DEBUG / INFO / WARNING / ERROR     | 否           |
| APP_DATABASE_URL | 数据库连接串                       | 生产必填     |
| APP_SECRET_KEY   | 签名/会话密钥                      | 生产必填     |
| APP_API_KEYS     | 合法 API Key，逗号分隔             | 生产建议配置 |

完整项见 `.env.example`。

### 缠论（结构引擎）

计算库 vendored 在仓库内 `chanpy/` 目录；对外 API、JSON 与日志统一使用 **`structure-engine`**，业务代码在 **`src/app/services/chan/`**。

| 文件         | 作用                                 |
| ------------ | ------------------------------------ |
| `analyze.py` | API 入口 `build_kline_chart_payload` |
| `backend.py` | 结构引擎计算与结构转换               |
| `chart.py`   | 结构 → 前端 JSON                     |
| `kline.py`   | Binance + 北京时间聚合               |

可选 **`APP_CHAN_ENGINE_ROOT`** 覆盖内置计算库路径（旧环境变量名仍可读入，见 `config.py`）。

**API**：`GET /api/v1/chan/kline/{symbol}/{interval}?limit=350`（需 `X-API-Key`）

返回字段与 chanlun 图表对齐：`klines`、`merged_klines`、`bi`、`xd`、`zs`、`fx`、`bsp`，`meta.engine` 为 **`structure-engine`**。

**本地验图**（与 `chan.py/demo_btcusdt.py` 同类，输出 PNG）：

```bash
uv sync --extra chart
uv run python scripts/demo_chan_chart.py
# 图片: output/chan_charts/btcusdt_1d_chan.png

# 与 API 相同 K 线（北京时间 5m 聚合）:
CHAN_USE_BEIJING=1 CHAN_INTERVAL=1d uv run python scripts/demo_chan_chart.py
```

**缠论 AI 分析 CLI**（对齐 chanlun 两套用法：单周期 `chanlun_ai.py` / 多级别 `multi_level_analyzer.py`）

在项目根目录执行；推荐 `uv run`，或先 `source .venv/bin/activate`。需配置 **APP_LLM_API_KEY**（`--no-ai` 除外）。

#### 单周期（默认 `analysis_mode=single`）

脚本：`scripts/flow_markets_ai.py`。指定 **一个** K 线周期（如 `1h`、`4h`），Agent 通过 `get_chan_structure` 拉结构 + `history`（历史胜率/相似案例），再调 LLM。

```bash
# 结构快览 + AI 分析报告（--table 为 chanlun 习惯参数）
FM_CHAN_PROGRESS=1 uv run python scripts/flow_markets_ai.py BTCUSDT 1h --table --limit 300

# 或项目根入口
uv run python flow_markets_ai.py BTCUSDT 1h --table --limit 300

# 仅结构、不调 LLM
uv run python scripts/flow_markets_ai.py BTCUSDT 1h --no-ai --limit 300

# 保存 output/{symbol}_{interval}_{时间}_structure.json / _analysis.json / _report.txt
uv run python scripts/flow_markets_ai.py BTCUSDT 1h --table --limit 300 --save
```

| 参数 | 说明 |
|------|------|
| `symbol` | 交易对，如 `BTCUSDT` |
| `interval` | 单周期，如 `1h`、`4h`、`15m` |
| `--limit` | K 线回溯根数（默认 300） |
| `--table` | 交易者可读终端输出 |
| `--no-ai` | 只算结构，跳过 LLM |
| `--save` | 写入 `output/` 并可选落分析记忆库 |
| `--user-query` | 自定义研究问题 |

#### 多级别联立（`analysis_mode=multi_timeframe`）

脚本：`scripts/multi_timeframe_analyze.py`。固定 **4h / 1h / 15m** 三级别：服务端先算多级别 JSON 并 **注入 Task**，再调技术分析师；`get_chan_structure@1h` 仅用于 `history`（胜率/降级 hints）。

```bash
# 多级别 4h/1h/15m：先算三级别 → JSON 注入 Task → 再调 AI
uv run python scripts/multi_timeframe_analyze.py BTCUSDT --save --limit 300

# 只看多级别结构与共振摘要，不调 LLM
uv run python scripts/multi_timeframe_analyze.py BTCUSDT --no-ai --limit 300

# 终端额外打印完整 multi_timeframe JSON
uv run python scripts/multi_timeframe_analyze.py BTCUSDT --no-ai --json
```

| 参数 | 说明 |
|------|------|
| `symbol` | 交易对（必填） |
| `--limit` | 每个级别的 K 线回溯根数（默认 300） |
| `--no-ai` | 只算 4h/1h/15m 结构与 `combined_judgment`，不调 LLM |
| `--save` | 保存 `output/multi_timeframe_{symbol}_{时间}.json`；调 AI 时另存 `_analysis.json` / `_report.txt` |
| `--user-query` | 自定义多级别联立分析问题 |

等价细粒度脚本：`scripts/run_technical_analyst.py`、`scripts/run_get_chan_structure.py`。

## 测试

```bash
# 从项目根目录执行，PYTHONPATH 已由 pyproject.toml 配置
pytest tests/ -v
```

**深度调研集成测试**（需配置 LLM + 百度 API Key，否则会跳过）：

```bash
# 方式一：使用 .env 中的 APP_LLM_API_KEY、APP_BAIDU_API_KEY
pytest tests/integration/test_deep_research.py -v

# 方式二：临时使用 QWEN_API_KEY（或 DEEPSEEK_API_KEY）、BAIDU_API_KEY 跑一次
export QWEN_API_KEY=sk-xxx
export BAIDU_API_KEY=bce-v3/xxx
pytest tests/integration/test_deep_research.py -v
```

**FlowMarkets 集成测试**（仅需 LLM Key，见 `tests/integration/test_flow_markets.py`）：

```bash
pytest tests/integration/test_flow_markets.py -v
```

## 部署

- **Docker**: `deploy/docker/Dockerfile`，多阶段构建、非 root 用户
- **K8s**: `deploy/k8s/deployment.yaml`，liveness/readiness 使用 `/health/live`、`/health/ready`
- 敏感配置使用 Secret，非敏感使用 ConfigMap，参见 `deploy/k8s/configmap.example.yaml`

## 设计文档

见 `doc/Python AI 应用框架设计文档.md`。

## License

MIT
