import pandas as pd
import numpy as np

# ======================================================================
# 参数区
# ======================================================================
CSV_PATH = r"D:\python\BianceStrategy\re\BianceData\MergedData\BTCUSDT_3D_merged.csv"
OUT_PATH = "short_trades_3d.csv"

INIT_BALANCE = 10000.0
LEVERAGE = 5
MARGIN_PCT = 0.33

FEE_RATE = 0.0005
SLIP_RATE = 0.0002
MMR = 0.004

CLOSE_TO_LOW_TH = 0.04
ENTITY_TO_LOWER_MIN_RATIO = 1
DEATH_CROSS_WINDOW = 1

DIST_MA10_21 = 0.15
BEAR_ENGULF_80 = 0.80
DOJI_TH = 0.002

MA180_NEAR_3A = 0.03
DROP_3A = 0.03
MA180_NEAR_3B = 0.05
DROP_3B = 0.08
MA180_NEAR_3C = 0.01
DROP_3C = 0.03

MA_TP_LIST = [99, 120, 180]
MA_TP_DIST = 0.05
MA_TP_ENABLE_MIN_DIST = 0.08

MA_TP_LOW_DIST = 0.03

MIN_DIST_MA180 = 0.03
MAX_DIST_MA180 = 0.16
MA180_SLOPE_LOOKBACK = 10
MA180_SLOPE_MAX_UP = None

BULL_BREAK_MA21_PCT = 0.03
MA_SHRINK_TH = 0.06
OPEN_ABOVE_MA21_TOL = 0.01

MIN_DIST_TP_MA_PCT = 0.09

PREV_CLOSE_TO_LOW_TH = 0.05
PREV_ENTITY_TO_LOWER_MIN_RATIO = 2.0

HOLD_MA99_NEAR_TH = 0.10
HOLD_LONG_LOWER_SHADOW_TH = 0.04

LONG_UPPER_SHADOW_TH = 0.03

DEATH_CROSS_WINDOW_1A = 3
DEATH_CROSS_1A_IGNORE_RESISTANCE = True

# ---------- 1A 开仓价距死叉 K 线收盘价的最大百分比 ----------
DEATH_CROSS_NEAR_PCT = 0.03

# ---------- 1A 信号 K 强势跌破阈值 ----------
# 信号 K 的 close 距 MA10/MA21 中较近那条超过该值，视为强势跌破，
# 豁免“开仓价距死叉 close”检查
DEATH_CROSS_1A_STRONG_BREAK_PCT = 0.05

# ======================================================================
# 读取数据 & 计算均线
# ======================================================================
df = pd.read_csv(CSV_PATH)
df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time").reset_index(drop=True)

for p in [10, 21, 99, 120, 180, 365]:
    df[f"ma{p}"] = df["close"].rolling(p).mean()

# ======================================================================
# 辅助列
# ======================================================================
df["is_bear"] = df["close"] < df["open"]
df["is_bull"] = df["close"] > df["open"]
df["close_to_low"] = (df["close"] - df["low"]) / df["low"]
df["entity_pct"] = (df["open"] - df["close"]) / df["open"]
df["lower_shadow_pct"] = (df["close"] - df["low"]) / df["low"]
df["entity_ratio"] = np.where(
    df["lower_shadow_pct"] > 0,
    df["entity_pct"] / df["lower_shadow_pct"],
    np.inf
)

_upper_base = df[["open", "close"]].max(axis=1)
df["upper_shadow_pct"] = (df["high"] - _upper_base) / _upper_base

df["prev_open"] = df["open"].shift(1)
df["prev_close"] = df["close"].shift(1)
df["prev_is_bull"] = df["prev_close"] > df["prev_open"]
df["prev_is_doji"] = (abs(df["prev_close"] - df["prev_open"]) / df["prev_open"]) <= DOJI_TH

df["prev2_open"] = df["open"].shift(2)
df["prev2_close"] = df["close"].shift(2)
df["prev2_is_bull"] = df["prev2_close"] > df["prev2_open"]

df["death_cross"] = (df["ma10"] < df["ma21"]) & (df["ma10"].shift(1) >= df["ma21"].shift(1))
df["golden_cross"] = (df["ma10"] > df["ma21"]) & (df["ma10"].shift(1) <= df["ma21"].shift(1))

df["ma180_prev_n"] = df["ma180"].shift(MA180_SLOPE_LOOKBACK)
df["ma180_slope"] = (df["ma180"] - df["ma180_prev_n"]) / df["ma180_prev_n"]

df["ma10_21_shrink"] = (df["ma21"] - df["ma10"]) / df["ma21"]

# ======================================================================
# 信号函数
# ======================================================================
def is_death_cross_recent(i, window=1):
    for k in range(max(1, i - window), i + 1):
        if df.loc[k, "death_cross"]:
            return True
    return False


def get_recent_death_cross_idx(i, window=1):
    for k in range(i, max(1, i - window) - 1, -1):
        if df.loc[k, "death_cross"]:
            return k
    return None


def signal_first(i):
    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]):
        return False, ""

    if not (r["is_bear"] and r["close_to_low"] < CLOSE_TO_LOW_TH):
        return False, ""

    if is_death_cross_recent(i, DEATH_CROSS_WINDOW_1A):
        return True, "第一类-1A刚死叉追空"

    if r["ma10"] < r["ma21"] and r["close"] < r["ma10"]:
        return True, "第一类-1B死叉后追空"

    if (r["ma10"] > r["ma21"] and
            r["open"] < r["ma10"] and r["close"] < r["ma10"] and
            r["close"] < r["ma21"] and
            r["open"] < r["ma21"] * (1 + OPEN_ABOVE_MA21_TOL)):
        return True, "第一类-1C未死叉跌破双均线"

    return False, ""


def signal_touch_ma_upper_shadow(i):
    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]):
        return False, ""

    if not (r["ma10"] < r["ma21"]):
        return False, ""

    if not r["is_bear"]:
        return False, ""

    if not (r["high"] >= r["ma10"] or r["high"] >= r["ma21"]):
        return False, ""

    if not (r["close"] < r["ma10"]):
        return False, ""

    if r["upper_shadow_pct"] < LONG_UPPER_SHADOW_TH:
        return False, ""

    return True, "第二类-追空:反弹触碰MA10/21长上影"


def signal_second(i):
    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]):
        return False, ""

    if not (r["ma10"] < r["ma21"]):
        return False, ""

    near_ma10 = abs(r["open"] - r["ma10"]) / r["ma10"] <= DIST_MA10_21
    near_ma21 = abs(r["open"] - r["ma21"]) / r["ma21"] <= DIST_MA10_21
    if not (near_ma10 or near_ma21):
        return False, ""

    if not (r["is_bear"] and r["close_to_low"] < CLOSE_TO_LOW_TH):
        return False, ""

    prev_bull = r["prev_is_bull"]
    cond_a = prev_bull and (r["close"] < r["prev_open"])

    if prev_bull and r["prev_open"] > 0:
        prev_gain = (r["prev_close"] - r["prev_open"]) / r["prev_open"]
        cur_drop = (r["open"] - r["close"]) / r["open"]
        cond_b = cur_drop >= prev_gain * BEAR_ENGULF_80
    else:
        cond_b = False

    cond_c = r["prev_is_doji"] and r["prev2_is_bull"] and (r["close"] < r["prev2_open"])

    if not (cond_a or cond_b or cond_c):
        return False, ""

    if near_ma21 and not (r["close"] < r["ma10"]):
        return False, ""

    return True, "第二类-下跌周期小反弹做空"


def signal_third(i):
    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]) or pd.isna(r["ma180"]):
        return False, ""

    if not (r["ma180"] > r["ma10"] and r["ma180"] > r["ma21"]):
        return False, ""

    if not (r["is_bear"] and r["close_to_low"] < CLOSE_TO_LOW_TH):
        return False, ""

    drop = (r["open"] - r["close"]) / r["open"]

    if r["open"] < r["ma180"] and (r["ma180"] - r["open"]) / r["ma180"] <= MA180_NEAR_3A:
        if drop >= DROP_3A:
            return True, "第三类-3a MA180下方开大阴线"

    if abs(r["open"] - r["ma180"]) / r["ma180"] <= MA180_NEAR_3B:
        if drop >= DROP_3B and r["close"] < r["ma180"]:
            return True, "第三类-3b 反弹到MA180附近大阴线"

    if abs(r["close"] - r["ma180"]) / r["ma180"] <= MA180_NEAR_3C:
        if r["close"] < r["ma180"] and drop >= DROP_3C:
            if (r["ma10"] < r["ma21"]) or r["death_cross"]:
                return True, "第三类-3c 大阴线跌破MA180"

    return False, ""


def signal_short(i):
    r = df.loc[i]

    if r["is_bear"] and r["entity_ratio"] < ENTITY_TO_LOWER_MIN_RATIO:
        return False, ""

    for fn in [signal_first, signal_touch_ma_upper_shadow, signal_second, signal_third]:
        ok, reason = fn(i)
        if ok:
            return True, reason
    return False, ""


def pass_prev_kline_filter(i):
    if i < 1:
        return False

    r = df.loc[i]
    prev = df.loc[i - 1]

    if prev["is_bull"]:
        return r["close"] < prev["open"]

    cond_low = prev["close_to_low"] <= PREV_CLOSE_TO_LOW_TH
    cond_ratio = prev["entity_ratio"] >= PREV_ENTITY_TO_LOWER_MIN_RATIO
    return cond_low or cond_ratio


def pass_ma180_filters(i, open_price):
    ma180_sig = df.loc[i, "ma180"]

    if not pd.isna(ma180_sig) and ma180_sig > 0:
        dist = abs(open_price - ma180_sig) / open_price

        if MIN_DIST_MA180 > 0 and dist < MIN_DIST_MA180:
            return False

        if MAX_DIST_MA180 > 0 and open_price < ma180_sig:
            dist_below = (ma180_sig - open_price) / open_price
            if dist_below > MAX_DIST_MA180:
                return False

    if MA180_SLOPE_MAX_UP is not None:
        slope = df.loc[i, "ma180_slope"]
        if not pd.isna(slope) and slope > MA180_SLOPE_MAX_UP:
            return False

    return True


def pass_ma_tp_distance_filter(i, open_price):
    if MIN_DIST_TP_MA_PCT <= 0:
        return True

    for p in MA_TP_LIST:
        ma_val = df.loc[i, f"ma{p}"]
        if pd.isna(ma_val):
            continue
        dist = abs(open_price - ma_val) / open_price
        if dist < MIN_DIST_TP_MA_PCT:
            return False

    return True


def pass_death_cross_near(i, open_price):
    if DEATH_CROSS_NEAR_PCT <= 0:
        return True

    death_idx = get_recent_death_cross_idx(i, DEATH_CROSS_WINDOW_1A)
    if death_idx is None:
        return False

    ref_price = df.loc[death_idx, "close"]
    if pd.isna(ref_price) or ref_price <= 0:
        return False

    dist = abs(open_price - ref_price) / ref_price
    return dist <= DEATH_CROSS_NEAR_PCT


def is_death_cross_strong_break(i):
    """
    判断信号 K 是否“强势跌破 MA10/MA21”：
    close 距 MA10 和 MA21 中较近的那条，超过 DEATH_CROSS_1A_STRONG_BREAK_PCT。
    """
    if DEATH_CROSS_1A_STRONG_BREAK_PCT <= 0:
        return False

    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]):
        return False

    dist_ma10 = abs(r["close"] - r["ma10"]) / r["ma10"]
    dist_ma21 = abs(r["close"] - r["ma21"]) / r["ma21"]
    nearest = min(dist_ma10, dist_ma21)
    return nearest >= DEATH_CROSS_1A_STRONG_BREAK_PCT


# ======================================================================
# 通用均线止盈函数
# ======================================================================
def find_ma_tp_intraday(row, entry):
    candidates = []
    for p in MA_TP_LIST:
        ma_val = row.get(f"ma{p}", np.nan)
        if pd.isna(ma_val):
            continue
        if entry <= ma_val:
            continue
        if (entry - ma_val) / entry <= MA_TP_ENABLE_MIN_DIST:
            continue

        if row["low"] <= ma_val:
            candidates.append((ma_val, p, ma_val))
        else:
            dist = (row["low"] - ma_val) / ma_val
            if dist <= MA_TP_LOW_DIST:
                candidates.append((ma_val, p, row["low"]))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, p, exec_price = candidates[0]
    return p, exec_price


def find_ma_tp_close(row, entry):
    candidates = []
    for p in MA_TP_LIST:
        ma_val = row.get(f"ma{p}", np.nan)
        if pd.isna(ma_val):
            continue
        if entry <= ma_val:
            continue
        if (entry - ma_val) / entry <= MA_TP_ENABLE_MIN_DIST:
            continue
        if abs(row["close"] - ma_val) / entry <= MA_TP_DIST:
            candidates.append((ma_val, p))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[0], reverse=True)
    ma_val, p = candidates[0]
    return p, ma_val


# ======================================================================
# 回测主循环
# ======================================================================
balance = INIT_BALANCE
position = None
pending_open = None
pending_close = None

trades = []
equity_curve = []

for i in range(len(df)):
    row = df.loc[i]
    t = row["time"]

    # ---------- 步骤1：开盘执行 pending_close ----------
    if position is not None and pending_close is not None:
        reason, sig_i, tp_ma_value, tp_period = pending_close
        open_price = row["open"]

        exec_price = open_price * (1 + SLIP_RATE)

        if "距离止盈" in reason and not pd.isna(tp_ma_value) and open_price < tp_ma_value:
            exec_price = tp_ma_value * (1 + SLIP_RATE)

        pos = position
        qty = pos["qty"]
        entry = pos["entry"]
        margin = pos["margin"]

        pnl = (entry - exec_price) * qty
        fee_close = exec_price * qty * FEE_RATE
        balance += pnl - fee_close

        ma_cols = {f"平仓_MA{p}": row.get(f"ma{p}", np.nan) for p in [10, 21, 99, 120, 180, 365]}

        trades.append({
            "开仓时间": pos["entry_time"],
            "方向": "空",
            "杠杆(倍)": LEVERAGE,
            "开仓价格": entry,
            "投入成本(保证金)": margin,
            "仓位总价值": pos["notional"],
            "平仓时间": t,
            "平仓价格": exec_price,
            "平仓原因": reason,
            "盈亏(USDT)": pnl - fee_close,
            "本单收益率(%)": (pnl - fee_close) / margin * 100,
            "持仓期最大浮亏(USDT)": pos["max_dd"],
            "最大浮亏占保证金(%)": pos["max_dd"] / margin * 100,
            **ma_cols,
            "平仓后余额": balance,
            "开仓原因/信号类型": pos["reason"],
            "是否爆仓": "是" if reason == "爆仓" else "否",
        })

        position = None
        pending_close = None

    # ---------- 步骤2：开盘执行 pending_open ----------
    if position is None and pending_open is not None:
        sig_i, reason = pending_open
        open_price = row["open"]
        ma180_sig = df.loc[sig_i, "ma180"]

        if reason.startswith("第三类-3b") and not (open_price < ma180_sig):
            pending_open = None

        # 1A：跳过阻力位过滤和前一根K线过滤
        # 如果信号 K 强势跌破 MA10/21，豁免“距死叉 close”检查；
        # 否则仍要求开仓价距死叉 close 不太远。
        elif reason.startswith("第一类-1A") and DEATH_CROSS_1A_IGNORE_RESISTANCE:
            if not is_death_cross_strong_break(sig_i):
                if not pass_death_cross_near(sig_i, open_price):
                    pending_open = None
            if pending_open is not None and not pass_ma180_filters(sig_i, open_price):
                pending_open = None

        elif reason.startswith("第一类-1A"):
            if not is_death_cross_strong_break(sig_i):
                if not pass_death_cross_near(sig_i, open_price):
                    pending_open = None
            if pending_open is not None and not pass_ma180_filters(sig_i, open_price):
                pending_open = None
            if pending_open is not None and not pass_ma_tp_distance_filter(sig_i, open_price):
                pending_open = None

        elif not pass_prev_kline_filter(sig_i):
            pending_open = None

        elif not pass_ma180_filters(sig_i, open_price):
            pending_open = None

        elif not pass_ma_tp_distance_filter(sig_i, open_price):
            pending_open = None

        if pending_open is not None:
            exec_price = open_price * (1 - SLIP_RATE)

            margin = balance * MARGIN_PCT
            notional = margin * LEVERAGE
            qty = notional / exec_price

            fee_open = notional * FEE_RATE
            balance -= fee_open

            position = {
                "entry_time": t,
                "entry": exec_price,
                "margin": margin,
                "notional": notional,
                "qty": qty,
                "max_dd": 0.0,
                "reason": reason,
                "entry_idx": i,
                "ma180_at_entry": ma180_sig,
            }
            pending_open = None

    # ---------- 步骤3：盘中检查：爆仓 / 均线即时止盈 ----------
    if position is not None:
        pos = position
        entry = pos["entry"]
        qty = pos["qty"]
        margin = pos["margin"]

        dd = (row["high"] - entry) * qty
        if dd > pos["max_dd"]:
            pos["max_dd"] = dd

        liq_price = entry * (1 + 1 / LEVERAGE) / (1 + MMR)
        if row["high"] >= liq_price:
            exec_price = liq_price
            pnl = (entry - exec_price) * qty
            fee_close = exec_price * qty * FEE_RATE
            balance += pnl - fee_close

            ma_cols = {f"平仓_MA{p}": row.get(f"ma{p}", np.nan) for p in [10, 21, 99, 120, 180, 365]}

            trades.append({
                "开仓时间": pos["entry_time"],
                "方向": "空",
                "杠杆(倍)": LEVERAGE,
                "开仓价格": entry,
                "投入成本(保证金)": margin,
                "仓位总价值": pos["notional"],
                "平仓时间": t,
                "平仓价格": exec_price,
                "平仓原因": "爆仓",
                "盈亏(USDT)": pnl - fee_close,
                "本单收益率(%)": (pnl - fee_close) / margin * 100,
                "持仓期最大浮亏(USDT)": pos["max_dd"],
                "最大浮亏占保证金(%)": pos["max_dd"] / margin * 100,
                **ma_cols,
                "平仓后余额": balance,
                "开仓原因/信号类型": pos["reason"],
                "是否爆仓": "是",
            })
            position = None
            pending_close = None
            continue

        tp_period, tp_ma_value = find_ma_tp_intraday(row, entry)
        if tp_period is not None:
            exec_price = tp_ma_value * (1 + SLIP_RATE)
            pnl = (entry - exec_price) * qty
            fee_close = exec_price * qty * FEE_RATE
            balance += pnl - fee_close

            reason = f"MA{tp_period}盘中止盈"
            ma_cols = {f"平仓_MA{p}": row.get(f"ma{p}", np.nan) for p in [10, 21, 99, 120, 180, 365]}

            trades.append({
                "开仓时间": pos["entry_time"],
                "方向": "空",
                "杠杆(倍)": LEVERAGE,
                "开仓价格": entry,
                "投入成本(保证金)": margin,
                "仓位总价值": pos["notional"],
                "平仓时间": t,
                "平仓价格": exec_price,
                "平仓原因": reason,
                "盈亏(USDT)": pnl - fee_close,
                "本单收益率(%)": (pnl - fee_close) / margin * 100,
                "持仓期最大浮亏(USDT)": pos["max_dd"],
                "最大浮亏占保证金(%)": pos["max_dd"] / margin * 100,
                **ma_cols,
                "平仓后余额": balance,
                "开仓原因/信号类型": pos["reason"],
                "是否爆仓": "否",
            })
            position = None
            pending_close = None
            continue

    # ---------- 步骤4：收盘检查：平空信号 / 开空信号 ----------
    if position is not None and pending_close is None:
        pos = position
        entry = pos["entry"]

        if row["golden_cross"]:
            pending_close = ("金叉平空", i, np.nan, None)

        elif (not pd.isna(row["ma99"]) and
              abs(row["close"] - row["ma99"]) / row["close"] <= HOLD_MA99_NEAR_TH and
              row["lower_shadow_pct"] >= HOLD_LONG_LOWER_SHADOW_TH):
            pending_close = ("持仓K线长下影止损", i, np.nan, None)

        elif (not pd.isna(row["ma21"]) and row["is_bull"] and
              row["close"] > row["ma21"] * (1 + BULL_BREAK_MA21_PCT)):
            pending_close = ("阳线破MA21止损", i, np.nan, None)

        elif (not pd.isna(row["ma10"]) and not pd.isna(row["ma21"]) and
              row["is_bull"] and
              row["close"] > row["ma10"] and
              row["close"] < row["ma21"] and
              row["ma10"] < row["ma21"] and
              row["ma10_21_shrink"] <= MA_SHRINK_TH):
            pending_close = ("阳线破MA10均线收缩止损", i, np.nan, None)

        elif (not pd.isna(row["ma10"]) and not pd.isna(row["ma21"]) and
              row["close"] > row["ma10"] and
              row["close"] > row["ma21"] and
              row["ma10"] <= row["ma21"]):
            pending_close = ("即将金叉止损", i, np.nan, None)

        else:
            tp_period, tp_ma_value = find_ma_tp_close(row, entry)
            if tp_period is not None:
                pending_close = (f"MA{tp_period}距离止盈", i, np.nan, None)

    if position is None and pending_open is None:
        ok, reason = signal_short(i)
        if ok:
            pending_open = (i, reason)

    equity_curve.append({"time": t, "balance": balance})

# ======================================================================
# 导出
# ======================================================================
out = pd.DataFrame(trades)

if not out.empty:
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", None)

    print(f"交易明细已导出：{OUT_PATH}")
    print(f"交易笔数：{len(out)}")
    print(f"期末余额：{balance:.2f}")
    print(f"总收益率：{(balance / INIT_BALANCE - 1) * 100:.2f}%")
    print()

    show_cols = [
        "开仓时间",
        "开仓价格",
        "平仓时间",
        "平仓价格",
        "平仓原因",
        "盈亏(USDT)",
        "本单收益率(%)",
        "持仓期最大浮亏(USDT)",
        "最大浮亏占保证金(%)",
    ]
    print(out[show_cols].to_string(index=False))
else:
    print("没有产生交易")