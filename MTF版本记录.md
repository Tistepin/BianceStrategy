# backtest_contract7_mtf 版本记录

> **命名规范（自本次起执行）**
> 1. 每次改动逻辑或默认参数，**必须**另存为 `backtest_contract7_mtf_vNN.py`，NN 递增，不覆盖旧文件。
> 2. 同步在本表新增一行，写清：改了什么、默认参数、BTC/DOGE 基准结果。
> 3. 回测报告里引用结果时，必须写清「版本号 + `DAILY_STOP_MODE`」，否则无法回溯。

---

## 版本总表

| 版本 | 文件 | 关键变更 | 默认模式 | BTC | DOGE | 状态 |
|---|---|---|---|---|---|---|
| v1–v4 | （已覆盖） | 加日线止损层；交易记录加「触发均线」两列 | close | 7066% | 43514% | ❌ 有未来函数 |
| v5 | — | 修未来函数：`daily_close_stop` → `pending_daily_close_stop`，信号留到下一根 3 日线开盘 | close | 3675% | — | ✅ |
| v6 | — | 头部注释更新 | close | 3675% | — | ✅ |
| v7 | — | 默认改 intraday；加 `_pending_open_exit`，修「盘中止损抢跑开盘出场」 | intraday | 1941% → 2512% | — | ✅ |
| v8 | — | 注释同步 | intraday | 2512% | — | ✅ |
| v9 | — | close 模式成交改为「下一根**日线**开盘」（原先错等下一根 3 日线） | intraday | 2512%（close: 4364%） | — | ✅ |
| v10 | — | 加趋势约束 `STOP_MA_MUST_BELOW_TREND`：止损均线须同时低于 MA10/MA21 | intraday | 4438% | 20421% | ✅ |
| **v11** | `backtest_contract7_mtf.py` | 修出场日期：日线层出场的 `平仓时间` 记为真实触发/成交日（原先误写 3 日线起始日） | **close** | **5388%** | **16172%** | ✅ 当前 |

> v11 的逻辑改动只有「日期标签」，不改撮合：v11 的 intraday 结果与 v10 完全一致（BTC 4438%、DOGE 20421%）。

---

## 关键参数快照（v11，2026-11-25）

```python
INITIAL_CAPITAL          = 10000.0
LEVERAGE                 = 5
POSITION_SIZE_PCT        = 0.33
FEE_RATE                 = 0.0004
SLIPPAGE                 = 0.0005
MMR                      = 0.005
UNI_MMR_LIMIT            = 1.05

DAILY_STOP_ENABLED       = True
DAILY_STOP_PERIODS       = [99, 120, 180, 365]
DAILY_STOP_MODE          = "close"      # ← 当前值；改 intraday 则 BTC 4438% / DOGE 20421%
STOP_MA_MUST_BELOW_TREND = True
DAILY_TREND_MA           = [10, 21]
TP_USE_DAILY_MA          = False
TP_USE_3D_MA_INTRADAY    = False
SAME_BAR_PESSIMISTIC     = True
```

---

## 同一版本、不同模式的基准（v11）

在切换 `DAILY_STOP_MODE` 前，请先看这两个数字确认自己在比什么：

| 币 | intraday（触及即止损） | close（收盘确认+次日开盘） |
|---|---|---|
| BTC | 4438% / -38.7% / 26 笔 | **5388%** / -38.7% / 25 笔 |
| DOGE | **20421%** / -57.6% / 13 笔 | 16172% / -66.9% / 13 笔 |
| ETH | 2002% / -44.8% | 4188% / -50.5% |
| SOL | 11455% / -44.2% | 11096% / -47.6% |

---

## 13 币横截面（v11，close 模式）

| 指标 | contract7 原版 | v11 |
|---|---|---|
| 收益中位 | 494% | 168% |
| 回撤中位 | -59.7% | -51.4% |
| 收益÷回撤中位 | 6.46 | ~3.1 |
| 盈利币数 | 8/13 | 8/13 |
| 回撤更优 | — | 8/13 |

（intraday 模式下：收益中位 415% / 回撤中位 -51.4% / 收益÷回撤 10.55）

---

## ⚠️ 作废文件，不要再跑

| 文件 | 问题 |
|---|---|
| `backtest_contract7_mtf2.py` | 带未来函数（`daily_close_stop` 同根 3 日线按开盘价成交）+ 无趋势约束。BTC 7066% / DOGE 43514% 是虚高值 |
| `backtest_contract7_mtf2-1.py` | 与上一行哈希相同，同一份 |

`backtest_contract7_mtf2-2.py` 是重写版且已修正：用**前一日**日线 MA、3D 止盈**逐日**判断，结果与 v11 在 7/13 个币上完全一致。

---

## 复现方式

```powershell
# 1) 确认当前版本
Get-FileHash .\backtest_contract7_mtf.py

# 2) 确认模式（决定了你会看到哪组数字）
Select-String .\backtest_contract7_mtf.py -Pattern '^DAILY_STOP_MODE'

# 3) 跑
python .\backtest_contract7_mtf.py
```

日线数据：优先 `re\BianceData\<COIN>USDT\1d\`，没有则从 `csvYear_All` 的 1m 数据重建（与 3 日线逐根 OHLC 对齐）。
