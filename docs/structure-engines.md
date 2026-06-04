# 结构引擎说明（Phase 7）

FlowMarkets 的缠论 **结构 JSON**（`get_chan_structure`、图表 API、AI 解读）必须标明来源引擎，避免与 **chanlun 原工程图表** 或 **历史 stats** 混比。

## 默认生产引擎：`structure-engine`

| 项 | 说明 |
|----|------|
| 实现 | 仓库内 vendored **chanpy**（目录名 `chanpy/`，业务不对外暴露包名） |
| 对外 ID | `meta.engine = "structure-engine"` |
| 代码 | `src/app/services/chan/backend.py` → `ChanEngineICL` |
| 用途 | API、CLI、`technical_only` / `full` Crew、分析库落库 |

## 对比引擎：`chanlun_icl`（仅实验）

| 项 | 说明 |
|----|------|
| 实现 | 同级目录 **chanlun** 仓库的 `chanlun_icl` / `SimpleICL` |
| 对外 ID | `meta.engine = "chanlun_icl"` |
| 启用 | `APP_CHAN_STRUCTURE_ENGINE=chanlun_icl` 或 CLI `--engine chanlun_icl` |
| 依赖 | `APP_CHANLUN_REPO_ROOT` 指向 chanlun 根目录（含 `chanlun_icl.py`） |
| 限制 | **非默认**；full 链与生产 API 仍应以 `structure-engine` 为准 |

## 与 chanlun 图表的差异（为何数值可能对不上）

两边 JSON **字段形状** 对齐（`bi` / `segment` / `center` / `signal` / `structure_summary`），**算法与划分不必一致**：

1. **引擎不同**：chanpy（CChan） vs chanlun `SimpleICL`
2. **中枢算法**：chanpy 支持 `zs_algo`（`normal` / `over_seg` / `auto`），chanlun ICL 自有划分逻辑
3. **K 线模式**：`APP_KLINE_MODE=utc|beijing` 只作用于 flow_markets 拉线；chanlun 侧习惯可能不同
4. **笔/段确认、买卖点命名、背驰附加** 等细节各自实现

## 对比与验收规范（防三边混比）

```text
✅ 比结构：同一 symbol、同一周期、同一 lookback、同一 engine、同一 kline_mode
✅ 比 AI 报告：先固定结构快照（或同一 engine 导出的 JSON），再比 Deliverable
❌ chanlun 网页图 + flow_markets structure-engine AI 结论，却声称「与图一致」
❌ 用 chanlun_icl 结构跑 stats / signal_quality，与 structure-engine 历史样本混算
```

## `zs_algo`（仅 structure-engine）

chanpy 中枢构造策略，经 `APP_CHAN_ZS_ALGO` 或 `--zs-algo` 传入，写入 `meta.zs_algo`：

| 值 | 含义（简述） |
|----|----------------|
| `normal` | 默认，按笔中枢常规合并 |
| `over_seg` | 线段级中枢倾向 |
| `auto` | 按段内笔数等在 normal / over_seg 间选择 |

对 `chanlun_icl` 无效（会被忽略）。

## 环境变量速查

| 变量 | 默认 | 说明 |
|------|------|------|
| `APP_CHAN_STRUCTURE_ENGINE` | `structure-engine` | `structure-engine` \| `chanlun_icl` |
| `APP_CHAN_ZS_ALGO` | `normal` | `normal` \| `over_seg` \| `auto` |
| `APP_CHANLUN_REPO_ROOT` | （空→自动找同级 `chanlun/`） | chanlun 仓库根目录 |
| `APP_CHAN_ENGINE_ROOT` | （空→内置 chanpy） | 覆盖 vendored chanpy 路径 |

## 相关命令

```bash
# 默认 structure-engine
uv run python scripts/chanlun_fm.py structure BTCUSDT 1h --limit 200

# 中枢实验
APP_CHAN_ZS_ALGO=over_seg uv run python scripts/chanlun_fm.py structure BTCUSDT 1h

# 与 chanlun 原 ICL 对比（需本机有 chanlun 仓库）
APP_CHAN_STRUCTURE_ENGINE=chanlun_icl uv run python scripts/chanlun_fm.py structure BTCUSDT 1h --json
```

图表接口 `GET /api/v1/chan/kline/...` 始终使用 **structure-engine**（chanpy）；结构快照对比请用 `structure` 子命令或 `get_chan_structure`。
