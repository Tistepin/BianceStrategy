# -*- coding: utf-8 -*-
# =====================================================================
# 📌 backtest_contract7_mtf.py  ·  修正版（日线止损 / 可选日线止盈）
#
#    ✅ 相对上一版的修正
#    1. 【致命】close 模式不再成交在本根 3D 线开盘：
#       日线收盘确认 → 下一根日线开盘成交；只有确认发生在本 3D 线
#       最后一根日线时，才顺延到下一根 3D 线开盘。
#    2. 日线层改成「按日逐根」结算：爆仓 / 止损 / 止盈按日线
#       open → low/high → close 的时间顺序处理，不再用整根 3D 线的
#       low/high 事后判定。
#    3. 新增 STOP_MUST_BELOW_MA：止损均线必须同时低于 MA10、MA21。
#       默认用日线 MA10/21；STOP_BELOW_MA_MODE="3d" 改用 3 日线 MA10/21。
#    4. 止损位用「前一日收盘 + 前一日均线」选；跳空开在均线下方按开盘成交。
#    5. 最后一根 3D 线的日线窗口不再伸到未来。
#    6. 平仓时间记录真实触发日；结束强平补手续费与滑点。
#
#    ⚠️ 上一版头注释里的 7066% / -22% / 321 因成交时序 bug 作废，必须用本版重跑。
#    ⚠️ 3 日线阻力止盈仍沿用 contract7 的「当根 3D 均线」口径（已知前视），
#       设 TP_3D_MA_FROM_PREV_BAR=True 可切换成上一根均线的因果口径。
#    ⚠️ 单币单窗口样本很小；换币/换周期需重新验证。
# =====================================================================

import os
import glob
import numpy as np
import pandas as pd

# ================= 1. 参数与基础设置 =================
CoinName = "BTC"
fileName = f"{CoinName}USDT_futures_3d.csv"
DATA_PATH = rf"re\{fileName}"
if not os.path.exists(DATA_PATH):
    DATA_PATH = rf"F:\Python\BianceStrategy\re\BianceData\{CoinName}USDT\3d\{fileName}"

INITIAL_CAPITAL = 10000.0
LEVERAGE = 5
POSITION_SIZE_PCT = 0.33
FEE_RATE = 0.0004
SLIPPAGE = 0.0005

# --- 形态与距离阈值 ---
DISTANCE_TO_MA = 0.03
CHASE_DISTANCE_TO_MA = 0.15

GOLDEN_CROSS_DISTANCE = 0.03
DEATH_CROSS_DISTANCE = 0.005

CLOSE_NEAR_HIGH_PCT = 0.025
BODY_SHADOW_MULTIPLIER = 2.0
BIG_BULL_CANDLE = 0.05
POWERFUL_BULL_CANDLE = 0.08
NO_BIG_BEAR_CANDLE = 0.10

LOOKBACK_MA = [10, 21, 99, 120, 180, 365]

# --- 币安风控参数 ---
MMR = 0.005
UNI_MMR_LIMIT = 1.05
ENABLE_DEATH_CROSS_EXIT = True
ENABLE_BREAKDOWN_EXIT = True
ENABLE_GOLDEN_CROSS_CHASE = True

# =====================================================================
# 🆕 日线多周期模块
#    日线止损：持仓期间，价格下方最近的日线 MA99/120/180/365 被跌破即止损
#    日线止盈：把日线 MA99/120/180/365 也当作上方阻力（可选，默认关）
# =====================================================================
DAILY_STOP_ENABLED = True
DAILY_STOP_PERIODS = [99, 120, 180, 365]
DAILY_STOP_MODE = "close"          # "close"=日线收盘确认，下一根日线开盘成交；"intraday"=日线 low 触及即成交
SAME_BAR_PESSIMISTIC = True        # 同一根日线内止损与止盈都成立时，止损优先

TP_USE_DAILY_MA = False            # 止盈是否也看日线长均线
TP_USE_3D_MA = True                # 3 日线长均线阻力止盈（contract7 原逻辑）
TP_3D_MA_FROM_PREV_BAR = False     # False=当根 3D MA（原口径）；True=上一根 3D MA（因果口径）

# 🆕 止损线必须同时在 MA10、MA21 下方
STOP_MUST_BELOW_MA = True
STOP_BELOW_MA_MODE = "daily"       # "daily"=日线 MA10/21；"3d"=3 日线 MA10/21

# ================= 2. 数据加载与指标 =================
def load_3d(path):
    df = pd.read_csv(path)
    df['time'] = pd.to_datetime(df['time'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna().set_index('time').sort_index()
    return df


def add_indicators(df):
    for ma in LOOKBACK_MA:
        df[f'MA{ma}'] = df['close'].rolling(window=ma).mean()

    df['is_bull'] = df['close'] > df['open']
    df['upper_shadow_pct'] = (df['high'] - df['close']) / df['close']
    df['body_pct'] = (df['close'] - df['open']) / df['open']

    df['is_body_strong'] = df['body_pct'] >= (df['upper_shadow_pct'] * BODY_SHADOW_MULTIPLIER)
    df['bullish_pattern'] = df['is_bull'] & (df['upper_shadow_pct'] < CLOSE_NEAR_HIGH_PCT) & df['is_body_strong']

    df['is_big_bull'] = df['bullish_pattern'] & (df['body_pct'] >= BIG_BULL_CANDLE)
    df['is_big_bear'] = (df['open'] - df['close']) / df['open'] >= NO_BIG_BEAR_CANDLE
    return df


def build_signals(df):
    """contract7 原信号逻辑，逐字保留。"""
    df['signal'] = 0
    for i in range(1, len(df)):
        if pd.isna(df['MA21'].iloc[i]):
            continue

        if not df['bullish_pattern'].iloc[i]:
            continue

        close_price = df['close'].iloc[i]
        open_price = df['open'].iloc[i]
        ma10, ma21, ma180 = df['MA10'].iloc[i], df['MA21'].iloc[i], df['MA180'].iloc[i]

        if close_price < ma10 or close_price < ma21:
            continue

        cond1 = cond2 = cond3 = cond4 = False
        ma_trend_up = ma10 > ma21

        if ma_trend_up:
            is_full_breakout = (open_price > ma10) and (open_price > ma21) and \
                               (close_price > ma10) and (close_price > ma21) and df['is_bull'].iloc[i]

            if not is_full_breakout and (ma21 < df['MA21'].iloc[i - 1]):
                continue

            ma_diff_up = (ma10 - ma21) / ma21
            if not is_full_breakout and (ma_diff_up <= 0.01):
                is_super_powerful = df['bullish_pattern'].iloc[i] and (df['body_pct'].iloc[i] >= POWERFUL_BULL_CANDLE)
                if not is_super_powerful:
                    continue

            cond1 = (abs(open_price - ma10) / ma10 <= CHASE_DISTANCE_TO_MA) or \
                    (abs(open_price - ma21) / ma21 <= CHASE_DISTANCE_TO_MA)

            is_strong_close = df['is_big_bull'].iloc[i] or is_full_breakout
            cond2 = is_strong_close and ((abs(open_price - ma10) / ma10 <= DISTANCE_TO_MA) or
                                         (abs(open_price - ma21) / ma21 <= DISTANCE_TO_MA))

            if not pd.isna(ma180) and ma180 < ma10:
                has_big_bear = df['is_big_bear'].iloc[max(0, i - 3):i + 1].any()
                if not has_big_bear:
                    near_180 = abs(open_price - ma180) / ma180 <= DISTANCE_TO_MA
                    break_180 = df['is_big_bull'].iloc[i]
                    cond3 = near_180 or break_180
        else:
            if ENABLE_GOLDEN_CROSS_CHASE:
                ma_diff = (ma21 - ma10) / ma21
                is_ma_close = ma_diff <= GOLDEN_CROSS_DISTANCE
                is_powerful_bull = df['is_big_bull'].iloc[i]
                is_valid_breakout = (close_price > ma10 * 1.015) and (close_price > ma21 * 1.015)
                if is_ma_close and is_powerful_bull and is_valid_breakout:
                    cond4 = True

        if cond1 or cond2 or cond3 or cond4:
            is_suppressed = False
            for long_ma_period in [99, 120, 180, 365]:
                long_ma_val = df[f'MA{long_ma_period}'].iloc[i]
                if not pd.isna(long_ma_val) and long_ma_val > close_price:
                    distance_to_res = (long_ma_val - close_price) / close_price
                    if distance_to_res <= 0.05:
                        is_suppressed = True
                        break
            if not is_suppressed:
                df.loc[df.index[i], 'signal'] = 1
    return df


# ================= 3. 日线数据 =================
def load_daily(coin):
    """优先读 1d 目录；没有就从 csvYear_All 的 1m 数据重建。"""
    d1 = rf"F:\python\BianceStrategy\re\BianceData\{coin}USDT\1d\{coin}USDT_futures_1d.csv"
    if os.path.exists(d1):
        d = pd.read_csv(d1)
    else:
        src_dir = rf"F:\python\BianceStrategy\re\BianceData\{coin}USDT\csvYear_All"
        files = sorted(glob.glob(os.path.join(src_dir, f"{coin}USDT_*.csv")))
        if not files:
            raise FileNotFoundError(f"找不到日线或 1m 数据: {src_dir}")
        print(f"  未找到 1d 文件，从 {len(files)} 个 1m 文件重建日线...")
        parts = [pd.read_csv(f, usecols=['time', 'open', 'high', 'low', 'close', 'volume']) for f in files]
        m = pd.concat(parts, ignore_index=True)
        m['time'] = pd.to_datetime(m['time'])
        m = m.sort_values('time').drop_duplicates('time')
        m['date'] = (m['time'] - pd.Timedelta(hours=8)).dt.date   # 与 ToOneDay.py 同口径
        d = (m.groupby('date')
              .agg(open=('open', 'first'), high=('high', 'max'),
                   low=('low', 'min'), close=('close', 'last'), volume=('volume', 'sum'))
              .reset_index())
        d['time'] = pd.to_datetime(d['date'])

    d['time'] = pd.to_datetime(d['time'])
    d = d.sort_values('time').drop_duplicates('time').reset_index(drop=True)

    need = sorted(set([10, 21] + DAILY_STOP_PERIODS))
    for p in need:
        d[f'DMA{p}'] = d['close'].rolling(p).mean()
        d[f'DMA{p}_prev'] = d[f'DMA{p}'].shift(1)   # 只用前一日已知的均线
    return d


def build_daily_windows(df, daily):
    """3 日线第 i 根 ↔ 日线 [T_i, T_{i+1})。最后一根不再伸到未来。"""
    d_dates = pd.DatetimeIndex(daily['time']).normalize().values
    d3_dates = pd.DatetimeIndex(df.index).normalize().values
    pos = np.searchsorted(d_dates, d3_dates)
    last_end = np.searchsorted(
        d_dates, np.datetime64((df.index[-1] + pd.Timedelta(days=3)).normalize())
    )
    win = {}
    for i in range(len(df)):
        lo = int(pos[i])
        hi = int(pos[i + 1]) if i + 1 < len(df) else min(int(last_end), len(daily))
        if hi > lo:
            win[i] = daily.iloc[lo:hi].to_dict('records')
    return win


def _prev_ma(d, p):
    v = d.get(f'DMA{p}_prev')
    if v is None or pd.isna(v):
        return None
    return float(v)


def _pick_stop(df, i, d, ref):
    """在「前一日收盘下方 + 前一日均线」里选最近的一条，且必须低于 MA10/MA21。
    语义：只保留同时低于 MA10/21 的长均线，取最近的一条；全被过滤则当日不止损，
    绝不会拿上方的均线当止损线。
    """
    if not DAILY_STOP_ENABLED:
        return None
    cands = []
    for p in DAILY_STOP_PERIODS:
        v = _prev_ma(d, p)
        if v is None or v > ref:
            continue
        if STOP_MUST_BELOW_MA:
            if STOP_BELOW_MA_MODE == "daily":
                m10, m21 = _prev_ma(d, 10), _prev_ma(d, 21)
            else:
                m10 = df['MA10'].iloc[i - 1] if i > 0 else np.nan
                m21 = df['MA21'].iloc[i - 1] if i > 0 else np.nan
                m10 = None if pd.isna(m10) else float(m10)
                m21 = None if pd.isna(m21) else float(m21)
            if m10 is None or m21 is None or not (v < m10 and v < m21):
                continue
        cands.append((v, p))
    return max(cands, key=lambda x: x[0]) if cands else None


def _pick_tp(d, o, tp3):
    """3D 阻力沿用原口径（已按 3D 开盘过滤）；日线阻力按当日开盘过滤。"""
    cands = list(tp3)
    if TP_USE_DAILY_MA:
        for p in DAILY_STOP_PERIODS:
            v = _prev_ma(d, p)
            if v is not None and v > o:
                cands.append((v, f'日线MA{p}'))
    return min(cands, key=lambda x: x[0]) if cands else None


def _tp3_levels(df, row, i):
    if not TP_USE_3D_MA:
        return []
    out = []
    for p in [99, 120, 180, 365]:
        if TP_3D_MA_FROM_PREV_BAR and i > 0:
            v = df[f'MA{p}'].iloc[i - 1]
        else:
            v = row[f'MA{p}']
        if not pd.isna(v) and v > row['open']:
            out.append((float(v), f'3日线MA{p}'))
    return out


# ================= 4. 回测引擎 =================
def run_engine(df, daily_win):
    balance = INITIAL_CAPITAL
    position_size = 0.0
    entry_price = 0.0
    liquidation_price = 0.0
    wait_for_reverse_exit = False
    wait_for_breakdown_exit = False
    pending_stop = None                 # (止损价, 均线周期)：收盘确认，等下一根日线开盘
    current_max_loss_usdt = 0.0
    current_max_loss_pct = 0.0
    trade_records = []
    current_trade = {}
    equity_curve = [(str(df.index[0])[:10], balance)]

    def _ma_of(bar_row, p):
        v = bar_row.get(f'MA{p}')
        return None if v is None or pd.isna(v) else round(float(v), 2)

    def _record(fill, reason, when, bar_row, ma_name=None, ma_val=None, liquidated=False):
        nonlocal balance, position_size, wait_for_reverse_exit, wait_for_breakdown_exit, pending_stop
        if liquidated:
            net_pnl = -balance
            balance = 0.0
        else:
            net_pnl = (fill - entry_price) * position_size - position_size * fill * FEE_RATE
            balance += net_pnl
            if balance < 0:
                balance = 0.0

        current_trade.update({
            '平仓时间': when,
            '平仓价格': round(fill, 2),
            '平仓原因': reason,
            '触发均线': ma_name,
            '触发均线值': round(ma_val, 2) if ma_val is not None else None,
            '盈亏(USDT)': round(net_pnl, 2),
            '平仓后余额': round(balance, 2),
            '本单收益率(%)': -100.0 if liquidated else round(net_pnl / current_trade['投入成本(保证金)'] * 100, 2),
            '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
            '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),
            '平仓_MA10': _ma_of(bar_row, 10),
            '平仓_MA21': _ma_of(bar_row, 21),
            '平仓_MA99': _ma_of(bar_row, 99),
            '平仓_MA120': _ma_of(bar_row, 120),
            '平仓_MA180': _ma_of(bar_row, 180),
            '平仓_MA365': _ma_of(bar_row, 365),
        })
        trade_records.append(dict(current_trade))
        position_size = 0.0
        wait_for_reverse_exit = False
        wait_for_breakdown_exit = False
        pending_stop = None
        equity_curve.append((when, balance))
        return net_pnl

    for i in range(1, len(df)):
        row = df.iloc[i]
        date_str = str(row.name)[:10]

        # ---------------- A. 持仓：出场 ----------------
        if position_size > 0:
            bars = daily_win.get(i)
            daily_layer_on = DAILY_STOP_ENABLED or TP_USE_DAILY_MA

            if daily_layer_on and bars:
                prev_3d_close = float(df['close'].iloc[i - 1])
                tp3 = _tp3_levels(df, row, i)

                for k, d in enumerate(bars):
                    o = float(d['open']); h = float(d['high'])
                    l = float(d['low']); c = float(d['close'])
                    when = str(pd.Timestamp(d['time']))[:10] if d.get('time') is not None else date_str
                    ref = float(bars[k - 1]['close']) if k > 0 else prev_3d_close

                    # 1) 开盘即破强平
                    if o <= liquidation_price:
                        _record(o, "💥爆仓", when, row, liquidated=True)
                        break

                    # 2) 昨日收盘确认的日线止损：今天开盘成交
                    if pending_stop is not None:
                        _st, _per = pending_stop
                        pending_stop = None
                        _record(o * (1 - SLIPPAGE), f'日线收盘跌破MA{_per}止损', when, row,
                                ma_name=f'日线MA{_per}', ma_val=_st)
                        break

                    # 3) 上一根 3D 线收盘触发的破位/死叉（只在本根第 1 天开盘）
                    if k == 0 and wait_for_breakdown_exit and ENABLE_BREAKDOWN_EXIT:
                        _record(o * (1 - SLIPPAGE), "破位止损", when, row)
                        break
                    if k == 0 and wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT:
                        _record(o * (1 - SLIPPAGE), "死叉平仓", when, row)
                        break

                    # 4) 当日止损位（前一日收盘 + 前一日均线，且低于 MA10/21）
                    stop = _pick_stop(df, i, d, ref)

                    # 5) 开盘跳空到止损位下方
                    if stop is not None and o <= stop[0]:
                        _record(o * (1 - SLIPPAGE), f'日线跳空跌破MA{stop[1]}止损', when, row,
                                ma_name=f'日线MA{stop[1]}', ma_val=stop[0])
                        break

                    # 6) 持仓期最大浮亏
                    if l < entry_price:
                        fl = (entry_price - l) * position_size + entry_price * position_size * FEE_RATE
                        if fl > current_max_loss_usdt:
                            current_max_loss_usdt = fl
                            current_max_loss_pct = fl / current_trade['投入成本(保证金)'] * 100

                    # 7) 盘中爆仓
                    if l <= liquidation_price:
                        _record(liquidation_price, "💥爆仓", when, row, liquidated=True)
                        break

                    # 8) 盘中止损 / 止盈（同日双触默认止损优先）
                    tp = _pick_tp(d, o, tp3)
                    s_hit = (DAILY_STOP_MODE == "intraday" and stop is not None and l <= stop[0])
                    t_hit = (tp is not None and h >= tp[0])
                    if s_hit and t_hit:
                        if SAME_BAR_PESSIMISTIC or (o - stop[0]) <= (tp[0] - o):
                            t_hit = False
                        else:
                            s_hit = False

                    if s_hit:
                        _record(stop[0] * (1 - SLIPPAGE), f'日线跌破MA{stop[1]}止损', when, row,
                                ma_name=f'日线MA{stop[1]}', ma_val=stop[0])
                        break
                    if t_hit:
                        _record(max(o, tp[0]) * (1 - SLIPPAGE), f'{tp[1]}阻力止盈', when, row,
                                ma_name=tp[1], ma_val=tp[0])
                        break

                    # 9) 收盘确认：挂到下一根日线开盘
                    if DAILY_STOP_MODE == "close" and stop is not None and c < stop[0]:
                        pending_stop = (stop[0], stop[1])

                if position_size == 0:
                    if balance <= 0:
                        print(f"❌ {date_str} 账户资金归零，回测提前终止！")
                        break
                    continue

            else:
                # ---------- 没有日线数据：退回 3D 级别 ----------
                exited = False
                if row['open'] <= liquidation_price:
                    _record(row['open'], "💥爆仓", date_str, row, liquidated=True)
                    exited = True
                elif pending_stop is not None:
                    _st, _per = pending_stop
                    pending_stop = None
                    _record(row['open'] * (1 - SLIPPAGE), f'日线收盘跌破MA{_per}止损', date_str, row,
                            ma_name=f'日线MA{_per}', ma_val=_st)
                    exited = True
                elif wait_for_breakdown_exit and ENABLE_BREAKDOWN_EXIT:
                    _record(row['open'] * (1 - SLIPPAGE), "破位止损", date_str, row)
                    exited = True
                elif wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT:
                    _record(row['open'] * (1 - SLIPPAGE), "死叉平仓", date_str, row)
                    exited = True

                if not exited:
                    # 持仓期最大浮亏（contract7 原口径）
                    if row['low'] < entry_price:
                        fl = (entry_price - row['low']) * position_size + entry_price * position_size * FEE_RATE
                        if fl > current_max_loss_usdt:
                            current_max_loss_usdt = fl
                            current_max_loss_pct = fl / current_trade['投入成本(保证金)'] * 100

                    if row['low'] <= liquidation_price:
                        _record(liquidation_price, "💥爆仓", date_str, row, liquidated=True)
                    elif TP_USE_3D_MA:
                        res_candidates = [(row[f'MA{p}'], p) for p in [99, 120, 180, 365]
                                          if not pd.isna(row[f'MA{p}']) and row[f'MA{p}'] > row['open']]
                        if res_candidates:
                            res, per = min(res_candidates, key=lambda x: x[0])
                            if row['high'] >= res:
                                _record(max(row['open'], res) * (1 - SLIPPAGE), f'3日线MA{per}阻力止盈', date_str, row,
                                        ma_name=f'3日线MA{per}', ma_val=res)

                if position_size == 0:
                    if balance <= 0:
                        print(f"❌ {date_str} 账户资金归零，回测提前终止！")
                        break
                    continue

            # 未出场：用 3D 收盘更新破位/死叉旗标
            if (row['MA10'] < row['MA21']) and (df['MA10'].iloc[i - 1] >= df['MA21'].iloc[i - 1]):
                wait_for_reverse_exit = True
            if (row['close'] < row['open'] and
                    row['close'] < row['MA10'] and row['close'] < row['MA21']):
                wait_for_breakdown_exit = True

        # ---------------- B. 空仓：开仓 ----------------
        if row['signal'] == 1 and position_size == 0:
            if row['close'] > row['open']:
                margin_cost = balance * POSITION_SIZE_PCT
                trade_capital = margin_cost * LEVERAGE

                entry_price = row['close'] * (1 + SLIPPAGE)
                position_size = trade_capital / entry_price

                maintenance_margin = trade_capital * MMR
                allowed_loss = balance - (maintenance_margin * UNI_MMR_LIMIT)
                liquidation_price = entry_price - (allowed_loss / position_size)

                open_fee = trade_capital * FEE_RATE
                balance -= open_fee

                current_max_loss_usdt = 0.0
                current_max_loss_pct = 0.0
                wait_for_reverse_exit = False
                wait_for_breakdown_exit = False
                pending_stop = None

                current_trade = {
                    '开仓时间': date_str,
                    '方向': '做多',
                    '杠杆(倍)': int(LEVERAGE),
                    '开仓价格': round(entry_price, 2),
                    '投入成本(保证金)': round(margin_cost, 2),
                    '仓位总价值': round(trade_capital, 2),
                }

    # ---------------- C. 结束强平 ----------------
    if position_size > 0:
        last = df.iloc[-1]
        fill = last['close'] * (1 - SLIPPAGE)
        _record(fill, '回测结束强平', str(df.index[-1])[:10], last)

    return balance, trade_records, equity_curve


# ================= 5. 输出 =================
def report(balance, trades, equity):
    print("=" * 50)
    print(f"初始资金: {INITIAL_CAPITAL:.2f} USDT")
    print(f"最终资金: {balance:.2f} USDT")
    print(f"总收益率: {((balance - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100):.2f}%")
    print(f"总交易次数: {len(trades)} 笔")
    print("=" * 50)

    if trades:
        records_df = pd.DataFrame(trades)
        cols = ['开仓时间', '方向', '杠杆(倍)', '开仓价格', '投入成本(保证金)', '仓位总价值',
                '平仓时间', '平仓价格', '平仓原因', '触发均线', '触发均线值',
                '盈亏(USDT)', '本单收益率(%)',
                '持仓期最大浮亏(USDT)', '最大浮亏占保证金(%)',
                '平仓_MA10', '平仓_MA21', '平仓_MA99', '平仓_MA120', '平仓_MA180', '平仓_MA365',
                '平仓后余额']
        records_df = records_df[cols]

        print("\n--- 完整交易记录明细 ---")
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(records_df.to_string(index=False))

        csv_save_path = "contract7_mtf_trades.csv"
        records_df.to_csv(csv_save_path, index=False, encoding='utf-8-sig')
        print(f"\n📁 完整的交易记录已保存为当前目录下的: {csv_save_path}")

        if len(equity) > 1:
            eq = pd.Series([v for _, v in equity])
            dd = (eq / eq.cummax() - 1.0).min() * 100
            print(f"最大回撤(按逐笔平仓权益，非逐bar): {dd:.2f}%")
    else:
        print("\n⚠️ 在周期内，没有触发任何符合条件的交易。")


def main():
    print("正在加载数据并进行预处理...")
    df = load_3d(DATA_PATH)
    df = add_indicators(df)
    df = build_signals(df)

    print("正在加载日线并计算长周期均线...")
    daily = load_daily(CoinName)
    print(f"  日线 {len(daily)} 根：{daily['time'].iloc[0].date()} -> {daily['time'].iloc[-1].date()}")

    win = build_daily_windows(df, daily)
    print(f"  3 日线 {len(df)} 根，其中 {len(win)} 根有对应日线")

    print("开始执行回测引擎...\n")
    balance, trades, equity = run_engine(df, win)
    report(balance, trades, equity)


if __name__ == "__main__":
    main()