import pandas as pd
import numpy as np

# ======================================================================
# 参数区
# 所有可调阈值集中在这里，后面扫描参数只改这一段
# ======================================================================
CoinName = "ETH"
CSV_PATH = rf"F:\Python\BianceStrategy\re\BianceData\{CoinName}USDT\3d\{CoinName}USDT_futures_3d.csv"
OUT_PATH = "../short_trades_3d.csv"

# ---------- 资金与杠杆 ----------
INIT_BALANCE = 10000.0     # 初始资金 USDT
LEVERAGE = 5               # 杠杆倍数
MARGIN_PCT = 0.33          # 每笔开仓使用当前余额的 33% 作为保证金

# ---------- 交易成本 ----------
FEE_RATE = 0.0005          # taker 手续费，单边 0.05%
SLIP_RATE = 0.0002         # 单边滑点 0.02%，开平各算一次
MMR = 0.004                # 维持保证金率，全仓爆仓判断用

# ---------- K 线形态过滤 ----------
CLOSE_TO_LOW_TH = 0.04           # 收盘距最低点 <4%，才算“收在最低附近”
ENTITY_TO_LOWER_MIN_RATIO = 1    # 阴线实体幅度 / 下影线幅度 >= 1，下影太长不做空

# ---------- 第二类：下跌周期小反弹 需要参数----------
DIST_MA10_21 = 0.15        # 开盘距 MA10 或 MA21 的百分比阈值
BEAR_ENGULF_80 = 0.80      # 阴线跌幅 >= 前阳涨幅 × 80%
DOJI_TH = 0.002            # 十字星实体阈值：abs(close-open)/open <= 0.2%

# ---------- 第三类：MA180 型 ----------
MA180_NEAR_3A = 0.03       # 3a：open 在 MA180 下方 3% 内
DROP_3A = 0.03             # 3a：阴线跌幅 >= 3%
MA180_NEAR_3B = 0.05       # 3b：open 在 MA180 附近 5% 内
DROP_3B = 0.08             # 3b：阴线跌幅 >= 8%
MA180_NEAR_3C = 0.01       # 3c：close 在 MA180 附近 1% 内
DROP_3C = 0.03             # 3c：阴线跌幅 >= 3%

# ---------- 止盈均线列表 ----------
# MA99/120/180/365 都可以作为止盈位
MA_TP_LIST = [99, 120, 180, 365]
MA_TP_DIST = 0.05                  # 收盘距止盈均线 <=5% -> 下一根开盘平
MA_TP_ENABLE_MIN_DIST = 0.08       # 开仓价距该均线 >8% 才启用这条均线止盈
MA_TP_LOW_DIST = 0.03              # 盘中止盈：low 距均线 3% 以内也算触及

# ---------- MA180 开仓过滤 ----------
MIN_DIST_MA180 = 0.03              # 开仓价距 MA180 最小距离，太近不开
MAX_DIST_MA180 = 0.16              # 开仓价在 MA180 下方超过 16% 不开
MA180_SLOPE_LOOKBACK = 10          # MA180 斜率回看根数
MA180_SLOPE_MAX_UP = None          # MA180 涨幅超过该值不开；None 表示不启用

# ---------- 止损规则 ----------
BULL_BREAK_MA21_PCT = 0.03        # 阳线收盘 > MA21 × (1+3%) 止损
MA_SHRINK_TH = 0.06               # MA10/MA21 收缩到 6% 以内 + 阳线破 MA10 -> 止损
OPEN_ABOVE_MA21_TOL = 0.01        # 1C 允许 open 高于 MA21 最多 1%

# ---------- 开仓距止盈均线最小距离 ----------
# 开仓价距 MA99/120/180/365 任意一条 <9% 就不开，避免止盈空间太小
MIN_DIST_TP_MA_PCT = 0.09

# ---------- 前一根K线质量过滤 ----------
# 前阳：当前阴线 close < 前阳 open 才开
# 前阴：以下两个条件满足一个就开
#   - prev_close_to_low <= PREV_CLOSE_TO_LOW_TH
#   - prev_entity_ratio >= PREV_ENTITY_TO_LOWER_MIN_RATIO
PREV_CLOSE_TO_LOW_TH = 0.05
PREV_ENTITY_TO_LOWER_MIN_RATIO = 2.0

# ---------- 持仓期间K线形态止损 ----------
# 持仓空单时，若某根K线收盘距 MA99 <= HOLD_MA99_NEAR_TH，
# 且下影 >= HOLD_LONG_LOWER_SHADOW_TH，则下一根开盘平空
HOLD_MA99_NEAR_TH = 0.10
HOLD_LONG_LOWER_SHADOW_TH = 0.04

# ---------- 追空：下跌周期反弹触碰MA10/21长上影 ----------
LONG_UPPER_SHADOW_TH = 0.03   # 上影 >= 3%

# ---------- 死叉窗口与阻力位优先级 ----------
DEATH_CROSS_WINDOW_1A = 3     # 死叉当前或前3根内都算 1A
DEATH_CROSS_1A_IGNORE_RESISTANCE = True  # 1A 跳过阻力位距离过滤

# ---------- 死叉“附近”过滤 ----------
# 1A 如果离死叉参考价太远，且不是强势破位，就不开
DEATH_CROSS_NEAR_PCT = 0.03          # 开仓价距死叉K收盘价 3% 以内才开
DEATH_CROSS_1A_STRONG_BREAK_PCT = 0.05  # 收盘距 MA10/21 最近一条 >=5%，算强势破位

# ---------- 1E 跌破MA180且跌破MA99/120 ----------
# 阴线，open>MA180，close<MA180，且 close<MA99、close<MA120
# 跌幅 >= DROP_1E_MIN，收盘距最低 < CLOSE_TO_LOW_TH
# 满足这个形态的信号，即使开仓价在 MA180 下方超过 MAX_DIST_MA180，也放行
DROP_1E_MIN = 0.05

# ======================================================================
# 读取数据 & 计算均线
# ======================================================================
df = pd.read_csv(CSV_PATH)
df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time").reset_index(drop=True)

# 计算 SMA 均线，按收盘价 close
for p in [10, 21, 99, 120, 180, 365]:
    df[f"ma{p}"] = df["close"].rolling(p).mean()

# ======================================================================
# 辅助列
# 把信号判断要用到的中间变量提前算好，避免在信号函数里重复计算
# ======================================================================
df["is_bear"] = df["close"] < df["open"]   # 阴线
df["is_bull"] = df["close"] > df["open"]   # 阳线

# 收盘距最低点幅度，A 公式：(close-low)/low
df["close_to_low"] = (df["close"] - df["low"]) / df["low"]

# 阴线实体幅度
df["entity_pct"] = (df["open"] - df["close"]) / df["open"]

# 下影线幅度
df["lower_shadow_pct"] = (df["close"] - df["low"]) / df["low"]

# 实体 / 下影比例：下影为 0 时视为无穷大（收盘就是最低）
df["entity_ratio"] = np.where(
    df["lower_shadow_pct"] > 0,
    df["entity_pct"] / df["lower_shadow_pct"],
    np.inf
)

# 上影幅度：high 到 max(open, close) 的距离
_upper_base = df[["open", "close"]].max(axis=1)
df["upper_shadow_pct"] = (df["high"] - _upper_base) / _upper_base

# 前一根 K 线字段
df["prev_open"] = df["open"].shift(1)
df["prev_close"] = df["close"].shift(1)
df["prev_is_bull"] = df["prev_close"] > df["prev_open"]
df["prev_is_doji"] = (abs(df["prev_close"] - df["prev_open"]) / df["prev_open"]) <= DOJI_TH

# 前两根 K 线字段，用于“十字星 + 前阳”判断
df["prev2_open"] = df["open"].shift(2)
df["prev2_close"] = df["close"].shift(2)
df["prev2_is_bull"] = df["prev2_close"] > df["prev2_open"]

# 死叉：前一根 MA10>=MA21，当前 MA10<MA21
df["death_cross"] = (df["ma10"] < df["ma21"]) & (df["ma10"].shift(1) >= df["ma21"].shift(1))

# 金叉：前一根 MA10<=MA21，当前 MA10>MA21
df["golden_cross"] = (df["ma10"] > df["ma21"]) & (df["ma10"].shift(1) <= df["ma21"].shift(1))

# MA180 斜率：当前 MA180 相对 N 根前的变化率
df["ma180_prev_n"] = df["ma180"].shift(MA180_SLOPE_LOOKBACK)
df["ma180_slope"] = (df["ma180"] - df["ma180_prev_n"]) / df["ma180_prev_n"]

# MA10 与 MA21 的收缩距离：死叉状态下 MA21 比 MA10 高出的比例
df["ma10_21_shrink"] = (df["ma21"] - df["ma10"]) / df["ma21"]

# ======================================================================
# 信号函数
# ======================================================================
def is_death_cross_recent(i, window=1):
    """当前K或前window根K内是否发生过死叉。"""
    for k in range(max(1, i - window), i + 1):
        if df.loc[k, "death_cross"]:
            return True
    return False


def get_recent_death_cross_idx(i, window=1):
    """返回当前K或前window根K内最近一次死叉的索引，没有则返回 None。"""
    for k in range(i, max(1, i - window) - 1, -1):
        if df.loc[k, "death_cross"]:
            return k
    return None


def is_break_below_ma180(i):
    """
    信号 K 是否是“从 MA180 上方跌破 MA180，且同时跌破 MA99/MA120”的跌破形态。
    用于：当 MAX_DIST_MA180 挡住开仓时，如果信号 K 本身是这种跌破形态，就放行。
    """
    r = df.loc[i]
    if pd.isna(r["ma99"]) or pd.isna(r["ma120"]) or pd.isna(r["ma180"]):
        return False

    return (r["is_bear"] and
            r["open"] > r["ma180"] and
            r["close"] < r["ma180"] and
            r["close"] < r["ma99"] and
            r["close"] < r["ma120"] and
            (r["open"] - r["close"]) / r["open"] >= DROP_1E_MIN and
            r["close_to_low"] < CLOSE_TO_LOW_TH)


def signal_first(i):
    """
    第一类：追空
    1A 刚死叉追空：死叉在当前K或前N根；阴线；收盘距最低<阈值
    1B 死叉后追空：MA10<MA21；阴线；收盘距最低<阈值；且 close < MA10
    1C 未死叉跌破双均线：MA10>MA21尚未死叉；阴线open<MA10；close<MA10且<MA21
    1E 跌破MA180多均线：从 MA180 上方跌破，且同时跌破 MA99/MA120
    """
    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]):
        return False, ""

    # 统一前提：阴线且收盘贴近最低
    if not (r["is_bear"] and r["close_to_low"] < CLOSE_TO_LOW_TH):
        return False, ""

    # 1A：刚死叉追空
    if is_death_cross_recent(i, DEATH_CROSS_WINDOW_1A):
        return True, "第一类-1A刚死叉追空"

    # 1B：死叉后追空，要求收盘跌破 MA10
    if r["ma10"] < r["ma21"] and r["close"] < r["ma10"]:
        return True, "第一类-1B死叉后追空"

    # 1C：未死叉但价格已跌破双均线
    if (r["ma10"] > r["ma21"] and
            r["open"] < r["ma10"] and r["close"] < r["ma10"] and
            r["close"] < r["ma21"] and
            r["open"] < r["ma21"] * (1 + OPEN_ABOVE_MA21_TOL)):
        return True, "第一类-1C未死叉跌破双均线"

    # 1E：开盘在 MA180 上方，收盘跌破 MA180，且同时跌破 MA99/MA120
    if is_break_below_ma180(i):
        return True, "第一类-1E跌破MA180多均线"

    return False, ""


def signal_touch_ma_upper_shadow(i):
    """
    追空：下跌周期反弹触碰 MA10/21 后长上影回落。
    条件：
    - MA10 < MA21（下跌周期）
    - 阴线
    - high 触碰 MA10 或 MA21
    - close < MA10（收盘回到 MA10 下方）
    - 上影 >= LONG_UPPER_SHADOW_TH
    """
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
    """
    第二类：下跌周期中的小反弹做空。
    前提：MA10 < MA21（下跌周期）
    价格反弹到 MA10 或 MA21 附近（开盘距均线 <= DIST_MA10_21）
    当前是阴线，收盘距最低 < 阈值
    且满足以下任一：
        a) 前一根阳线，当前收盘 < 前阳开盘（吞没）
        b) 当前阴线跌幅 >= 前阳涨幅 × 80%
        c) 前一根十字星，十字星前一根是阳线，当前收盘 < 那根阳线开盘
    如果接近的是 MA21，额外要求 close < MA10。
    """
    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]):
        return False, ""

    # 前提：MA10 < MA21
    if not (r["ma10"] < r["ma21"]):
        return False, ""

    # 开盘是否接近 MA10 或 MA21
    near_ma10 = abs(r["open"] - r["ma10"]) / r["ma10"] <= DIST_MA10_21
    near_ma21 = abs(r["open"] - r["ma21"]) / r["ma21"] <= DIST_MA10_21
    if not (near_ma10 or near_ma21):
        return False, ""

    # 必须是阴线且收盘贴近最低
    if not (r["is_bear"] and r["close_to_low"] < CLOSE_TO_LOW_TH):
        return False, ""

    prev_bull = r["prev_is_bull"]

    # a) 吞没：前阳，当前收盘 < 前阳开盘
    cond_a = prev_bull and (r["close"] < r["prev_open"])

    # b) 阴线跌幅 >= 前阳涨幅 × 80%
    if prev_bull and r["prev_open"] > 0:
        prev_gain = (r["prev_close"] - r["prev_open"]) / r["prev_open"]
        cur_drop = (r["open"] - r["close"]) / r["open"]
        cond_b = cur_drop >= prev_gain * BEAR_ENGULF_80
    else:
        cond_b = False

    # c) 十字星后阴线：前一根十字星，十字星前一根阳线，当前收盘 < 前阳开盘
    cond_c = r["prev_is_doji"] and r["prev2_is_bull"] and (r["close"] < r["prev2_open"])

    if not (cond_a or cond_b or cond_c):
        return False, ""

    # 接近 MA21 时，要求 close < MA10
    if near_ma21 and not (r["close"] < r["ma10"]):
        return False, ""

    return True, "第二类-下跌周期小反弹做空"


def signal_third(i):
    """
    第三类：MA180 型。
    前提：MA180 > MA10 且 MA180 > MA21（大周期在上方，视为下跌中的反弹）

    3a：open 在 MA180 下方 3% 内，跌幅 >=3%，阴线，收盘贴低
    3b：open 在 MA180 附近 5% 内，跌幅 >=8%，close < MA180，阴线，收盘贴低
    3c：close 在 MA180 附近 1% 内，close < MA180，跌幅 >=3%，
        且 MA10<MA21 或当根死叉
    """
    r = df.loc[i]
    if pd.isna(r["ma10"]) or pd.isna(r["ma21"]) or pd.isna(r["ma180"]):
        return False, ""

    # 前提：MA180 在 MA10 和 MA21 上方
    if not (r["ma180"] > r["ma10"] and r["ma180"] > r["ma21"]):
        return False, ""

    # 必须是阴线且收盘贴近最低
    if not (r["is_bear"] and r["close_to_low"] < CLOSE_TO_LOW_TH):
        return False, ""

    drop = (r["open"] - r["close"]) / r["open"]

    # 3a：MA180 下方不远处开大阴线
    if r["open"] < r["ma180"] and (r["ma180"] - r["open"]) / r["ma180"] <= MA180_NEAR_3A:
        if drop >= DROP_3A:
            return True, "第三类-3a MA180下方开大阴线"

    # 3b：反弹到 MA180 附近的大阴线
    if abs(r["open"] - r["ma180"]) / r["ma180"] <= MA180_NEAR_3B:
        if drop >= DROP_3B and r["close"] < r["ma180"]:
            return True, "第三类-3b 反弹到MA180附近大阴线"

    # 3c：大阴线跌破 MA180，且均线空头排列或当根死叉
    if abs(r["close"] - r["ma180"]) / r["ma180"] <= MA180_NEAR_3C:
        if r["close"] < r["ma180"] and drop >= DROP_3C:
            if (r["ma10"] < r["ma21"]) or r["death_cross"]:
                return True, "第三类-3c 大阴线跌破MA180"

    return False, ""


def signal_short(i):
    """
    空单总信号入口：
    1. 先统一检查实体/下影比例
    2. 依次检查：
       - 第一类：1A/1B/1C/1E
       - 追空：反弹触碰MA10/21长上影
       - 第二类：下跌周期小反弹
       - 第三类：MA180型
    """
    r = df.loc[i]

    # 实体/下影比例过滤，只对阴线生效
    if r["is_bear"] and r["entity_ratio"] < ENTITY_TO_LOWER_MIN_RATIO:
        return False, ""

    for fn in [signal_first, signal_touch_ma_upper_shadow, signal_second, signal_third]:
        ok, reason = fn(i)
        if ok:
            return True, reason
    return False, ""


def pass_prev_kline_filter(i):
    """
    前一根K线质量过滤：
    1. 前一根是阳线：当前阴线 close < 前阳线 open，才允许开
    2. 前一根是阴线：以下两个条件满足一个就开
       - prev_close_to_low <= PREV_CLOSE_TO_LOW_TH（下影不太长）
       - prev_entity_ratio >= PREV_ENTITY_TO_LOWER_MIN_RATIO（实体/下影够大）
    """
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
    """
    MA180 距离与斜率过滤：
    - MIN_DIST_MA180：开仓价距 MA180 太近，不开（上下都检查）
    - MAX_DIST_MA180：开仓价在 MA180 下方太远，不开（只检查下方）
      如果信号 K 本身是“从 MA180 上方跌破 MA180 且跌破 MA99/120”，
      这是趋势转折，不是低位深追空，放行
    - MA180_SLOPE_MAX_UP：MA180 涨幅超过阈值，不开
    """
    ma180_sig = df.loc[i, "ma180"]

    if not pd.isna(ma180_sig) and ma180_sig > 0:
        dist = abs(open_price - ma180_sig) / open_price

        if MIN_DIST_MA180 > 0 and dist < MIN_DIST_MA180:
            return False

        if MAX_DIST_MA180 > 0 and open_price < ma180_sig:
            dist_below = (ma180_sig - open_price) / open_price
            if dist_below > MAX_DIST_MA180:
                if is_break_below_ma180(i):
                    pass  # 豁免 MAX_DIST_MA180
                else:
                    print(
                        f"{df.loc[i, 'time']} 开仓{open_price:.2f} MA180={ma180_sig:.2f} "
                        f"下方距离{dist_below * 100:.2f}% 被MAX_DIST_MA180挡"
                    )
                    return False

    if MA180_SLOPE_MAX_UP is not None:
        slope = df.loc[i, "ma180_slope"]
        if not pd.isna(slope) and slope > MA180_SLOPE_MAX_UP:
            return False

    return True


def pass_ma_tp_distance_filter(i, open_price):
    """
    阻力位距离过滤：开仓价距 MA99/120/180/365 任意一条太近，不开。
    1A 刚死叉信号优先级高于阻力位，会跳过这个过滤。
    """
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
    """
    死叉“附近”过滤：
    开仓价距最近一次死叉 K 的收盘价，必须在 DEATH_CROSS_NEAR_PCT 以内。
    用于 1A：死叉后走了几根，如果价格已经离开死叉位太远，就不是“刚死叉追空”了。
    """
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
    死叉强势破位：
    收盘距 MA10 或 MA21 最近的那条，距离 >= DEATH_CROSS_1A_STRONG_BREAK_PCT。
    强势破位的 1A 可以跳过“死叉附近”过滤。
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
    """
    盘中止盈（基于最低价）：
    MA_TP_LIST = [99, 120, 180, 365]
    1. 均线在开仓价下方，且开仓价距均线 > MA_TP_ENABLE_MIN_DIST；
    2. low <= 均线：真正穿插，按均线价成交；
    3. low 在均线 MA_TP_LOW_DIST 容差内：算接近触及，按 low 成交；
    4. 多条均线满足时，选价格最高的那条（最先触及）。
    返回 (period, exec_price)。
    """
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
    """
    收盘距离止盈（基于收盘价）：
    MA_TP_LIST = [99, 120, 180, 365]
    1. 均线在开仓价下方；
    2. 开仓价距均线 > MA_TP_ENABLE_MIN_DIST；
    3. 收盘价距均线 <= MA_TP_DIST（距离用开仓价作分母）。
    多条满足时选价格最高的那条。
    返回 (period, ma_value)。
    """
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
# 每个 i 代表一根 3 日 K，按顺序做四件事：
#   1. 开盘执行上一根收盘确认的平仓
#   2. 开盘执行上一根收盘确认的开仓（带过滤）
#   3. 盘中检查全仓爆仓、均线盘中止盈
#   4. 收盘检查平仓信号、开仓信号，写入 pending_*
# ======================================================================
balance = INIT_BALANCE
position = None         # 当前持仓字典，None 表示空仓
pending_open = None     # (signal_idx, reason)，等待下一根开盘开仓
pending_close = None    # (reason, signal_idx, tp_ma_value, tp_period)，等待下一根开盘平仓

trades = []             # 交易明细
equity_curve = []       # 权益曲线

for i in range(len(df)):
    row = df.loc[i]
    t = row["time"]

    # ---------- 步骤1：开盘执行 pending_close ----------
    # 上一根收盘确认了平仓信号，这一根开盘价成交
    if position is not None and pending_close is not None:
        reason, sig_i, tp_ma_value, tp_period = pending_close
        open_price = row["open"]

        # 空单买入平仓，滑点不利：成交价上浮
        exec_price = open_price * (1 + SLIP_RATE)

        # 如果是“距离止盈”，且下一根开盘直接跌破该均线，按均线价平
        if "距离止盈" in reason and not pd.isna(tp_ma_value) and open_price < tp_ma_value:
            exec_price = tp_ma_value * (1 + SLIP_RATE)

        pos = position
        qty = pos["qty"]
        entry = pos["entry"]
        margin = pos["margin"]

        # 空单盈亏 = (开仓价 - 平仓价) × 数量
        pnl = (entry - exec_price) * qty
        fee_close = exec_price * qty * FEE_RATE
        balance += pnl - fee_close

        # 平仓时各均线值，方便复盘
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
    # 上一根收盘确认了开仓信号，这一根开盘价成交，成交前还要过几道过滤
    if position is None and pending_open is not None:
        sig_i, reason = pending_open
        open_price = row["open"]
        ma180_sig = df.loc[sig_i, "ma180"]

        # 过滤1：第三类 3b 要求开仓价 < MA180
        if reason.startswith("第三类-3b") and not (open_price < ma180_sig):
            pending_open = None

        # 过滤2：1A 优先级高，先检查“死叉附近”和 MA180 距离，跳过阻力位距离过滤
        elif reason.startswith("第一类-1A") and DEATH_CROSS_1A_IGNORE_RESISTANCE:
            if not is_death_cross_strong_break(sig_i):
                if not pass_death_cross_near(sig_i, open_price):
                    pending_open = None
            if pending_open is not None and not pass_ma180_filters(sig_i, open_price):
                pending_open = None

        # 过滤3：1A 但未开启优先级豁免时，正常检查所有过滤
        elif reason.startswith("第一类-1A"):
            if not is_death_cross_strong_break(sig_i):
                if not pass_death_cross_near(sig_i, open_price):
                    pending_open = None
            if pending_open is not None and not pass_ma180_filters(sig_i, open_price):
                pending_open = None
            if pending_open is not None and not pass_ma_tp_distance_filter(sig_i, open_price):
                pending_open = None

        # 过滤4：其他信号，依次检查前一根K线质量、MA180 距离、阻力位距离
        elif not pass_prev_kline_filter(sig_i):
            pending_open = None

        elif not pass_ma180_filters(sig_i, open_price):
            pending_open = None

        elif not pass_ma_tp_distance_filter(sig_i, open_price):
            pending_open = None

        # 所有过滤通过，正式开仓
        if pending_open is not None:
            # 空单卖出，滑点不利：成交价下浮
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

    # ---------- 步骤3：盘中检查：全仓爆仓 / 均线即时止盈 ----------
    if position is not None:
        pos = position
        entry = pos["entry"]
        qty = pos["qty"]
        margin = pos["margin"]

        # 更新最大浮亏：空单浮亏用 high
        dd = (row["high"] - entry) * qty
        if dd > pos["max_dd"]:
            pos["max_dd"] = dd

        # ---------- 全仓爆仓判断 ----------
        # 用 high 作为标记价格近似
        mark_price = row["high"]
        unrealized_pnl = (entry - mark_price) * qty
        equity = balance + unrealized_pnl
        mm = mark_price * qty * MMR

        if equity <= mm:
            # 解强平价：balance + (entry - liq) * qty = liq * qty * MMR
            # liq = (balance + entry * qty) / (qty * (1 + MMR))
            liq_price = (balance + entry * qty) / (qty * (1 + MMR))
            exec_price = liq_price
            pnl = (entry - exec_price) * qty
            fee_close = exec_price * qty * FEE_RATE
            balance += pnl - fee_close
            balance = max(balance, 0.0)  # 穿仓简化：权益不为负

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

        # 通用均线盘中即时止盈：MA99/120/180/365 中任一条被盘中触及或接近
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

        # 1) 真金叉平空
        if row["golden_cross"]:
            pending_close = ("金叉平空", i, np.nan, None)

        # 2) 持仓K线长下影 + 距MA99不远，形态止损
        elif (not pd.isna(row["ma99"]) and
              abs(row["close"] - row["ma99"]) / row["close"] <= HOLD_MA99_NEAR_TH and
              row["lower_shadow_pct"] >= HOLD_LONG_LOWER_SHADOW_TH):
            pending_close = ("持仓K线长下影止损", i, np.nan, None)

        # 3) 阳线收盘 > MA21 × (1+X%) 止损
        elif (not pd.isna(row["ma21"]) and row["is_bull"] and
              row["close"] > row["ma21"] * (1 + BULL_BREAK_MA21_PCT)):
            pending_close = ("阳线破MA21止损", i, np.nan, None)

        # 4) 阳线破 MA10 未破 MA21 + MA10<MA21 + 均线收缩
        elif (not pd.isna(row["ma10"]) and not pd.isna(row["ma21"]) and
              row["is_bull"] and
              row["close"] > row["ma10"] and
              row["close"] < row["ma21"] and
              row["ma10"] < row["ma21"] and
              row["ma10_21_shrink"] <= MA_SHRINK_TH):
            pending_close = ("阳线破MA10均线收缩止损", i, np.nan, None)

        # 5) 即将金叉止损：收盘站上 MA10 和 MA21，但 MA10 尚未上穿 MA21
        elif (not pd.isna(row["ma10"]) and not pd.isna(row["ma21"]) and
              row["close"] > row["ma10"] and
              row["close"] > row["ma21"] and
              row["ma10"] <= row["ma21"]):
            pending_close = ("即将金叉止损", i, np.nan, None)

        # 6) 通用均线距离止盈：收盘距 MA99/120/180/365 任一条 <= MA_TP_DIST
        else:
            tp_period, tp_ma_value = find_ma_tp_close(row, entry)
            if tp_period is not None:
                pending_close = (f"MA{tp_period}距离止盈", i, np.nan, None)

    # 空仓则检查开空信号
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
    # CSV 导出全部列
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    # 控制台完整打印：不限制列数、行数、列宽、显示宽度
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", None)

    print(f"交易明细已导出：{OUT_PATH}")
    print(f"交易笔数：{len(out)}")
    print(f"期末余额：{balance:.2f}")
    print(f"总收益率：{(balance / INIT_BALANCE - 1) * 100:.2f}%")
    print()

    # 控制台只打印你指定的列
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