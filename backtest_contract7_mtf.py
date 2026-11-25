# =====================================================================
# 📌 backtest_contract7_mtf.py
#    = backtest_contract7.py + 日线多周期层（日线止损 / 日线均线止盈）
#
#    数据对齐：3 日线第 i 根 == 日线 [T_i, T_{i+1}) 的 1~3 根
#    日线来源：优先 re\BianceData\<COIN>USDT\1d\；没有则从 csvYear_All 的 1m 数据
#              按 ToOneDay.py 同口径（time-8h 取日期）重建，与 3 日线逐根 OHLC 完全一致
#
#    ── BTC 3 日线实测（2019-11 ~ 2026-10，5x，初始 10000）─────────────────
#    配置                                    期末权益   总收益   最大回撤   笔数
#    contract7 原版（无日线层）                539,631   5296%    -38.7%    24
#    ★ 日线止损·触及 + 均线须在MA10/21下方     453,850   4438%    -38.7%    26  ← 默认
#    （备选）日线止损·收盘确认 + 次日开盘       548,766   5388%    -38.7%    25
#
#    ── 13 个币横截面（收益中位 / 回撤中位 / 收益÷回撤中位）───────────────
#    contract7 原版          494%  /  -59.7%  /   6.46       盈利 8/13
#    日线止损(触及+趋势约束)  415%  /  -51.4%  /  10.55       盈利 8/13
#    收益：MTF 更优 5/13；回撤：MTF 更优 10/13
#    → 收益基本持平（中位 494%→415%），回撤明显收窄，收益/回撤比 6.46 → 10.55。
#
#    🐞 时序修正记录（close 模式的三层演进，务必看）：
#      信号在「日线收盘」那一刻就已知，不需要等 3 日线走完。
#      ① 错误版：用当根 3 日线自己的「开盘价」成交 —— 那个时刻早于信号（日线收盘），
#                属未来函数，等于卖在过去的高点。BTC 虚高到 7066%。
#      ② 过于保守版：推迟到「下一根 3 日线开盘」，最多晚 3 天。BTC 3675%。
#      ③ 现在（正确）：成交在「下一根日线开盘」。若次日已属下一根 3 日线，
#                其开盘价正好等于那根 3 日线的开盘价。BTC 4364% / 回撤 -26.3%。
#      ⚠️ intraday（触及）模式不受上述问题影响：均线是被挂单触发的实时价位，
#         按均线价成交真实可执行，无需等到任何 K 线收盘。
#      另：intraday 模式还有一个「抢跑」修正 —— 若本根 3 日线开盘就有待执行的出场
#         （跳空爆仓/破位/死叉），必须按开盘价先成交，不能被盘中触及抢跑（1941% → 2512%）。
#
#    📅 平仓时间口径：日线层出场的「平仓时间」记录为**实际触发/成交的那根日线**，
#       而不是所属 3 日线的起始日（否则会出现「比破位日早一天卖出」的错觉）。
#
#    🛡️ 止损有效性约束：日线 MA99/120/180/365 只有在「同时低于 MA10 与 MA21」时，
#       才被认作有效的下方支撑止损线（多头排列才成立）。由 STOP_MA_MUST_BELOW_TREND 控制。
#
#    ⚠️ 单币单窗口 29 笔，样本很小；换币/换周期需重新验证。
#    开关全关（DAILY_STOP_ENABLED=False, TP_USE_DAILY_MA=False,
#            TP_USE_3D_MA_INTRADAY=False）时，本文件与 contract7 完全一致（已回归校验）。
# =====================================================================

import pandas as pd
import numpy as np
import os

# =====================================================================
# 🎯 策略说明：均线多头/即将金叉 + 强势回踩/追多策略
# 🚀 新增：动态实体-影线比例过滤（实体涨幅必须 >= 上影线幅度的 N 倍）
# 🛡️ 修复：拒绝空头趋势下的弱势贴脸买入，强制要求均线拐头向上
# 🌟 终极修复：新增“全K线悬空突破”豁免权，绝不错杀 2020-10-18 完美起爆点
# 🚧 新增防线：上方长线均线压制检测，拒绝 2022-02-27 这种“撞墙单”  最终版

# 在 7 的基础上 增加 日线的 1日线止损 防止大回踩
# =====================================================================

# ================= 1. 参数与基础设置 =================
CoinName="BTC"
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

# 🚨 核心拆分：分别控制金叉和死叉的阈值
GOLDEN_CROSS_DISTANCE = 0.03
DEATH_CROSS_DISTANCE = 0.005

# 🚨 形态过滤核心参数
CLOSE_NEAR_HIGH_PCT = 0.025  # 上影线必须 < 2.5%
BODY_SHADOW_MULTIPLIER = 2.0  # 🚀 核心：实体涨幅必须是上影线幅度的 2 倍以上
BIG_BULL_CANDLE = 0.05  # 普通大阳线阈值（实体 >= 5%）
POWERFUL_BULL_CANDLE = 0.08  # 超级大阳线阈值（实体 >= 8%，用于死叉豁免）
NO_BIG_BEAR_CANDLE = 0.10

LOOKBACK_MA = [10, 21, 99, 120, 180, 365]

# --- 币安风控参数 ---
MMR = 0.005
UNI_MMR_LIMIT = 1.05
ENABLE_DEATH_CROSS_EXIT = True
ENABLE_BREAKDOWN_EXIT = True

# 🚨 开关：是否允许“即将金叉”时买入
ENABLE_GOLDEN_CROSS_CHASE = True

# =====================================================================
# 🆕 多周期（日线）模块
#    日线止损：持仓期间，价格下方的日线 MA99/120/180/365 被跌破即止损
#    日线止盈：把日线 MA99/120/180/365 也当作上方阻力，与原有 3 日线阻力一起取最近的一条
#    ✅ 开关全关时，本文件与 backtest_contract7.py 完全一致（已回归校验）
# =====================================================================
DAILY_STOP_ENABLED      = True      # 日线长均线止损总开关
DAILY_STOP_PERIODS      = [99, 120, 180, 365]   # 用哪几条日线均线
DAILY_STOP_MODE         = "intraday"  # "intraday"=日线 low 触及 MA99/120/180/365 即止损【按要求默认】; "close"=日线收盘跌破、下一根日线开盘止损
# 🛡️ 止损均线必须位于 MA10 与 MA21 之下，才是有效的下方支撑止损线
#    （多头排列 MA10 > MA21 > MA99/120/180/365 时才成立；空头排列里长均线在
#      MA21 上方，说明结构已坏，那条线不能当支撑止损用）
STOP_MA_MUST_BELOW_TREND = True
DAILY_TREND_MA           = [10, 21]

TP_USE_DAILY_MA         = False     # 止盈不看日线（按需求：止盈只用 3 日线 MA，保持 contract7 原逻辑）
TP_USE_3D_MA_INTRADAY   = False     # 3 日线止盈保持「3 日线收盘触发」；True=提前到日线粒度（实测更差）
SAME_BAR_PESSIMISTIC    = True      # 同一根日线内止损与止盈都成立时，止损优先（保守）

# ================= 2. 数据加载与指标计算 =================
print("正在加载数据并进行预处理...")
df = pd.read_csv(DATA_PATH)
df['time'] = pd.to_datetime(df['time'])
for col in ['open', 'high', 'low', 'close', 'volume']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df.dropna()
df = df.set_index('time')

for ma in LOOKBACK_MA:
    df[f'MA{ma}'] = df['close'].rolling(window=ma).mean()

df['is_bull'] = df['close'] > df['open']

# 计算上影线比例
df['upper_shadow_pct'] = (df['high'] - df['close']) / df['close']
# 计算实体涨幅
df['body_pct'] = (df['close'] - df['open']) / df['open']

# 🚨 核心逻辑：实体涨幅必须大于等于 上影线比例 * 倍数，且上影线本身不能超过设定的阈值
df['is_body_strong'] = df['body_pct'] >= (df['upper_shadow_pct'] * BODY_SHADOW_MULTIPLIER)
df['bullish_pattern'] = df['is_bull'] & (df['upper_shadow_pct'] < CLOSE_NEAR_HIGH_PCT) & df['is_body_strong']

df['is_big_bull'] = df['bullish_pattern'] & (df['body_pct'] >= BIG_BULL_CANDLE)
df['is_big_bear'] = (df['open'] - df['close']) / df['open'] >= NO_BIG_BEAR_CANDLE

# ================= 3. 生成做多信号 =================
print("正在生成开仓信号...")
df['signal'] = 0
for i in range(1, len(df)):
    if pd.isna(df['MA21'].iloc[i]):
        continue

    # 第一道大闸：必须是实体大于上影线倍数的强势阳线
    if not df['bullish_pattern'].iloc[i]:
        continue

    close_price = df['close'].iloc[i]
    open_price = df['open'].iloc[i]
    ma10, ma21, ma180 = df['MA10'].iloc[i], df['MA21'].iloc[i], df['MA180'].iloc[i]

    # 大前提：收盘价必须站上均线
    if close_price < ma10 or close_price < ma21:
        continue

    cond1 = False
    cond2 = False
    cond3 = False
    cond4 = False

    ma_trend_up = ma10 > ma21

    if ma_trend_up:
        # 🌟 终极豁免权：如果开盘价和收盘价全部悬空于均线之上，代表极度强势的空中加油
        is_full_breakout = (open_price > ma10) and (open_price > ma21) and \
                           (close_price > ma10) and (close_price > ma21) and \
                           df['is_bull'].iloc[i]

        # 🛡️ 新增防线1：强制要求 MA21 必须走平或向上拐头！拒绝下跌趋势中的假多头
        # 但如果满足全悬空突破，则直接放行
        if not is_full_breakout and (ma21 < df['MA21'].iloc[i - 1]):
            continue

        # 🚨 即将死叉过滤
        ma_diff_up = (ma10 - ma21) / ma21
        # 🛡️ 新增防线2：把死叉距离从 0.5% 提高到 1%，必须拉开距离才算真多头
        # 但如果满足全悬空突破，则无视贴脸死叉
        if not is_full_breakout and (ma_diff_up <= 0.01):
            # 🚀 豁免条件：超级大阳线破局
            is_super_powerful = df['bullish_pattern'].iloc[i] and (df['body_pct'].iloc[i] >= POWERFUL_BULL_CANDLE)
            if not is_super_powerful:
                continue

        # 标准的多头排列逻辑
        cond1 = (abs(open_price - ma10) / ma10 <= CHASE_DISTANCE_TO_MA) or \
                (abs(open_price - ma21) / ma21 <= CHASE_DISTANCE_TO_MA)

        # 🛡️ 新增防线3：cond2 的贴脸回踩，必须是大阳线（实体>=5%）！或者满足终极豁免权！
        is_strong_close = df['is_big_bull'].iloc[i] or is_full_breakout
        cond2 = is_strong_close and ((abs(open_price - ma10) / ma10 <= DISTANCE_TO_MA) or \
                                     (abs(open_price - ma21) / ma21 <= DISTANCE_TO_MA))

        if not pd.isna(ma180) and ma180 < ma10:
            has_big_bear = df['is_big_bear'].iloc[max(0, i - 3):i + 1].any()
            if not has_big_bear:
                near_180 = abs(open_price - ma180) / ma180 <= DISTANCE_TO_MA
                break_180 = df['is_big_bull'].iloc[i]
                cond3 = near_180 or break_180
    else:
        # 🚨 “即将金叉”逻辑：拒绝弱势贴脸，只认强力破位
        if ENABLE_GOLDEN_CROSS_CHASE:
            # 1. 均线距离必须足够窄（即将金叉的大前提）
            ma_diff = (ma21 - ma10) / ma21
            is_ma_close = ma_diff <= GOLDEN_CROSS_DISTANCE

            # 2. 强力破位：必须是你代码里定义的“大阳线”（复用 is_big_bull，即实体 >= 5%）
            is_powerful_bull = df['is_big_bull'].iloc[i]

            # 3. 有效突破：收盘价必须强势向上突破，比两根均线至少高出 1.5%（硬编码防止贴脸）
            is_valid_breakout = (close_price > ma10 * 1.015) and (close_price > ma21 * 1.015)

            # 三者必须同时满足：均线靠近 + 实体够大 + 强势突破
            if is_ma_close and is_powerful_bull and is_valid_breakout:
                cond4 = True

    # =========================================================================
    # 🚧 新增核心防线（终极拦截）：上方长线均线压制检测 (解决 2022-02-27 撞墙单)
    # =========================================================================
    if cond1 or cond2 or cond3 or cond4:
        is_suppressed = False
        # 检查上方的 99, 120, 180, 365 均线
        for long_ma_period in [99, 120, 180, 365]:
            long_ma_val = df[f'MA{long_ma_period}'].iloc[i]
            # 如果该均线在上方，且当前收盘价距离该均线不足 5% (0.05)
            if not pd.isna(long_ma_val) and long_ma_val > close_price:
                distance_to_res = (long_ma_val - close_price) / close_price
                if distance_to_res <= 0.05:
                    is_suppressed = True
                    break # 发现上方有天花板压制，直接打断循环，禁止开仓

        # 只有在没有被长线均线压制的情况下，才确认发出买入信号
        if not is_suppressed:
            df.loc[df.index[i], 'signal'] = 1

# ================= 🆕 3.5 日线数据加载 =================
import glob


def _load_daily(coin):
    """优先读 1d 目录；没有就从 csvYear_All 的 1m 数据按同一口径重建（与 3 日线严格对齐）"""
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
    for p in sorted(set(DAILY_STOP_PERIODS) | set(DAILY_TREND_MA)):
        d[f'DMA{p}'] = d['close'].rolling(p).mean()
    return d


print("正在加载日线并计算长周期均线...")
daily = _load_daily(CoinName)
print(f"  日线 {len(daily)} 根：{daily['time'].iloc[0].date()} -> {daily['time'].iloc[-1].date()}")

_d_dates = pd.DatetimeIndex(daily['time']).normalize().values
_d3_dates = pd.DatetimeIndex(df.index).normalize().values
_pos = np.searchsorted(_d_dates, _d3_dates)
DAILY_WIN = {}
for _i in range(len(df)):
    _lo = _pos[_i]
    _hi = _pos[_i + 1] if _i + 1 < len(df) else len(daily)
    if _hi > _lo:
        DAILY_WIN[_i] = list(zip(range(_lo, _hi), daily.iloc[_lo:_hi].to_dict('records')))
_d_open = daily['open'].values          # 供 close 模式取「下一根日线开盘价」
_d_n = len(daily)
print(f"  3 日线 {len(df)} 根，其中 {len(DAILY_WIN)} 根有对应日线")

# ================= 4. 回测核心引擎 =================
print("开始执行回测引擎...\n")
balance = INITIAL_CAPITAL
position_size = 0
entry_price = 0
liquidation_price = 0

wait_for_reverse_exit = False
wait_for_breakdown_exit = False
daily_close_stop = None          # 🆕 close 模式：今天开盘要执行的止损
pending_daily_close_stop = None  # 🆕 close 模式：今天（当根3日线内部）新产生的、留到下一根开盘执行

current_max_loss_usdt = 0.0
current_max_loss_pct = 0.0

trade_records = []
current_trade = {}

for i in range(1, len(df)):
    row = df.iloc[i]
    date_str = str(row.name)[:10]

    # ✅ 时序修正：日线收盘跌破的信号，只能留到「下一根 3 日线开盘」执行，
    #    不能在产生信号的同一根 3 日线上按它的开盘价成交（那是未来函数）
    daily_close_stop, pending_daily_close_stop = pending_daily_close_stop, None

    # --- A. 持仓状态下：监控浮亏与平仓 ---
    if position_size > 0:
        # =================================================================
        # 🆕 日线多周期层：早于 3 日线收盘判断，按日线逐根检查
        #    ① 日线止损：取「日线开盘价下方最近的一条 DMA」，触发方式见 DAILY_STOP_MODE
        #    ② 日线止盈：取「日线开盘价上方最近的一条 DMA」，high 触及即止盈
        #    ③ 同一根日线两者都成立 → 默认止损优先（保守）
        # =================================================================
        # ⏱️ 若本根 3 日线开盘就有待执行的出场（跳空爆仓/破位/死叉/日线收盘止损），
        #    这些在时间上早于盘中，必须先由下面的 3 日线出场链按开盘价成交，
        #    不能被「盘中触及日线均线」抢跑（否则会按更差的价格离场）
        _pending_open_exit = (
            row['open'] <= liquidation_price
            or daily_close_stop is not None
            or (wait_for_breakdown_exit and ENABLE_BREAKDOWN_EXIT)
            or (wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT)
        )

        if (not _pending_open_exit) and (DAILY_STOP_ENABLED or TP_USE_DAILY_MA or TP_USE_3D_MA_INTRADAY) and i in DAILY_WIN:
            d_exit_reason = None
            d_exit_price = None
            d_exit_date = None       # 🆕 实际触发/成交的那根日线日期
            d_trigger_ma = None      # 触发本次平仓的日线均线
            d_trigger_val = None
            for g, drow in DAILY_WIN[i]:
                d_o, d_h, d_l, d_c = drow['open'], drow['high'], drow['low'], drow['close']

                if d_l < entry_price:
                    _fl = (entry_price - d_l) * position_size + entry_price * position_size * FEE_RATE
                    if _fl > current_max_loss_usdt:
                        current_max_loss_usdt = _fl
                        current_max_loss_pct = _fl / current_trade['投入成本(保证金)'] * 100

                # ① 止损候选：日线开盘价下方最近的长均线
                d_stop, d_stop_p = None, None
                if DAILY_STOP_ENABLED:
                    _d10, _d21 = drow[f'DMA{DAILY_TREND_MA[0]}'], drow[f'DMA{DAILY_TREND_MA[1]}']
                    _trend_ok = (not pd.isna(_d10)) and (not pd.isna(_d21))
                    _below = []
                    for p in DAILY_STOP_PERIODS:
                        v = drow[f'DMA{p}']
                        if pd.isna(v) or v > d_o:
                            continue                      # 必须在开盘价下方
                        if STOP_MA_MUST_BELOW_TREND:
                            if not _trend_ok:
                                continue                  # 趋势均线缺失 → 不认
                            if v > _d21 or v > _d10:
                                continue                  # 🛡️ 必须在 MA21 与 MA10 之下
                        _below.append((v, p))
                    if _below:
                        d_stop, d_stop_p = max(_below, key=lambda x: x[0])

                # ② 止盈候选：日线开盘价上方最近的长均线
                _cands = []
                if TP_USE_DAILY_MA:
                    _cands += [(drow[f'DMA{p}'], f'日线MA{p}') for p in DAILY_STOP_PERIODS
                               if not pd.isna(drow[f'DMA{p}']) and drow[f'DMA{p}'] > d_o]
                if TP_USE_3D_MA_INTRADAY:
                    _cands += [(row[f'MA{p}'], f'3日线MA{p}') for p in DAILY_STOP_PERIODS
                               if not pd.isna(row[f'MA{p}']) and row[f'MA{p}'] > d_o]
                d_tp, d_tp_name = (min(_cands, key=lambda x: x[0]) if _cands else (None, None))

                # ③ 触发判定
                if d_stop is not None and DAILY_STOP_MODE == "close":
                    if d_c < d_stop:                     # 日线收盘确认跌破（此刻已知，无需等 3 日线走完）
                        # ✅ 正确成交时刻 = 下一根日线的开盘价
                        #    若下一根日线属于下一根 3 日线，其开盘价正好等于那根 3 日线的开盘价
                        if g + 1 < _d_n:
                            d_exit_price = _d_open[g + 1] * (1 - SLIPPAGE)
                            d_exit_reason = f'日线收盘跌破MA{d_stop_p}止损'
                            d_trigger_ma = f'日线MA{d_stop_p}'
                            d_trigger_val = round(d_stop, 2)
                            d_exit_date = daily['time'].iloc[g + 1]   # 执行日 = 下一根日线
                        else:
                            pending_daily_close_stop = (d_stop, d_stop_p)   # 数据末尾兜底
                        break
                    s_hit = False
                else:
                    s_hit = d_stop is not None and d_l <= d_stop

                t_hit = d_tp is not None and d_h >= d_tp

                if s_hit and t_hit:
                    if SAME_BAR_PESSIMISTIC or (d_o - d_stop) <= (d_tp - d_o):
                        t_hit = False
                    else:
                        s_hit = False

                if s_hit:
                    d_trigger_ma = f'日线MA{d_stop_p}'
                    d_trigger_val = round(d_stop, 2)
                    d_exit_date = daily['time'].iloc[g]           # 触发日 = 当根日线
                    if d_o <= d_stop:                    # 跳空开在均线下方
                        d_exit_price = d_o * (1 - SLIPPAGE)
                        d_exit_reason = f'日线跳空跌破MA{d_stop_p}止损'
                    else:
                        d_exit_price = d_stop * (1 - SLIPPAGE)
                        d_exit_reason = f'日线跌破MA{d_stop_p}止损'
                    break
                if t_hit:
                    d_exit_price = max(d_o, d_tp) * (1 - SLIPPAGE)
                    d_exit_reason = f'{d_tp_name}止盈'
                    d_trigger_ma = d_tp_name
                    d_trigger_val = round(d_tp, 2)
                    d_exit_date = daily['time'].iloc[g]
                    break

            if d_exit_reason:
                profit = (d_exit_price - entry_price) * position_size
                close_fee = position_size * d_exit_price * FEE_RATE
                net_pnl = profit - close_fee
                balance += net_pnl
                current_trade.update({
                    '平仓时间': str(d_exit_date)[:10] if d_exit_date is not None else date_str,
                    '平仓价格': round(d_exit_price, 2),
                    '平仓原因': d_exit_reason,
                    '触发均线': d_trigger_ma,
                    '触发均线值': d_trigger_val,
                    '盈亏(USDT)': round(net_pnl, 2),
                    '平仓后余额': round(balance, 2),
                    '本单收益率(%)': round((net_pnl / current_trade['投入成本(保证金)']) * 100, 2),
                    '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
                    '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),
                    '平仓_MA10': round(row['MA10'], 2) if not pd.isna(row['MA10']) else None,
                    '平仓_MA21': round(row['MA21'], 2) if not pd.isna(row['MA21']) else None,
                    '平仓_MA99': round(row['MA99'], 2) if not pd.isna(row['MA99']) else None,
                    '平仓_MA120': round(row['MA120'], 2) if not pd.isna(row['MA120']) else None,
                    '平仓_MA180': round(row['MA180'], 2) if not pd.isna(row['MA180']) else None,
                    '平仓_MA365': round(row['MA365'], 2) if not pd.isna(row['MA365']) else None,
                })
                trade_records.append(current_trade)
                position_size = 0
                wait_for_reverse_exit = False
                wait_for_breakdown_exit = False
                daily_close_stop = None
                if balance <= 0:
                    print(f"❌ {date_str} 账户资金归零，回测提前终止！")
                    break
                continue

        if row['low'] < entry_price:
            floating_loss_usdt = (entry_price - row['low']) * position_size
            floating_loss_usdt += (entry_price * position_size * FEE_RATE)
            if floating_loss_usdt > current_max_loss_usdt:
                current_max_loss_usdt = floating_loss_usdt
                current_max_loss_pct = (current_max_loss_usdt / current_trade['投入成本(保证金)']) * 100

        exit_reason = None
        actual_sell = 0
        is_liquidated = False
        trigger_ma = None        # 触发本次平仓的均线，如 '3日线MA180' / '日线MA99'
        trigger_ma_val = None    # 该均线的数值

        # 🚨 每日动态计算阻力位（同时记录是「哪一条」3 日线均线构成上方阻力）
        #    候选 = 3 日线 MA99/120/180/365 中「高于当根开盘价」的那些，
        #    取价格最低的一条 = 最先被触及的阻力
        res_candidates = [(row[f'MA{ma}'], ma) for ma in [99, 120, 180, 365]
                          if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] > row['open']]
        if res_candidates:
            dynamic_resistance, tp_res_period = min(res_candidates, key=lambda x: x[0])
        else:
            dynamic_resistance, tp_res_period = None, None

        # 🚨 平仓优先级：爆仓 > 破位止损 > 死叉 > 动态阻力止盈
        if row['low'] <= liquidation_price:
            actual_sell = liquidation_price
            exit_reason = "💥爆仓"
            is_liquidated = True
        elif daily_close_stop is not None:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = f'日线收盘跌破MA{daily_close_stop[1]}止损'
            trigger_ma = f'日线MA{daily_close_stop[1]}'
            trigger_ma_val = round(daily_close_stop[0], 2)
            daily_close_stop = None
        elif wait_for_breakdown_exit and ENABLE_BREAKDOWN_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "破位止损"
        elif wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "死叉平仓"
        elif dynamic_resistance is not None and row['high'] >= dynamic_resistance:
            actual_sell = max(row['open'], dynamic_resistance) * (1 - SLIPPAGE)
            exit_reason = f"3日线MA{tp_res_period}阻力止盈"
            trigger_ma = f'3日线MA{tp_res_period}'
            trigger_ma_val = round(dynamic_resistance, 2)

        # 执行平仓结算
        if exit_reason:
            if is_liquidated:
                net_pnl = -balance
                balance = 0
            else:
                profit = (actual_sell - entry_price) * position_size
                close_fee = position_size * actual_sell * FEE_RATE
                net_pnl = profit - close_fee
                balance += net_pnl

            current_trade.update({
                '平仓时间': date_str,
                '平仓价格': round(actual_sell, 2),
                '平仓原因': exit_reason,
                '触发均线': trigger_ma,
                '触发均线值': trigger_ma_val,
                '盈亏(USDT)': round(net_pnl, 2),
                '平仓后余额': round(balance, 2),
                '本单收益率(%)': round((net_pnl / current_trade['投入成本(保证金)']) * 100,
                                       2) if not is_liquidated else -100.00,
                '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
                '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),

                '平仓_MA10': round(row['MA10'], 2) if not pd.isna(row['MA10']) else None,
                '平仓_MA21': round(row['MA21'], 2) if not pd.isna(row['MA21']) else None,
                '平仓_MA99': round(row['MA99'], 2) if not pd.isna(row['MA99']) else None,
                '平仓_MA120': round(row['MA120'], 2) if not pd.isna(row['MA120']) else None,
                '平仓_MA180': round(row['MA180'], 2) if not pd.isna(row['MA180']) else None,
                '平仓_MA365': round(row['MA365'], 2) if not pd.isna(row['MA365']) else None,
            })
            trade_records.append(current_trade)

            position_size = 0
            wait_for_reverse_exit = False
            wait_for_breakdown_exit = False

            if balance <= 0:
                print(f"❌ {date_str} 账户发生全仓爆仓，资金归零，回测提前终止！")
                break
            continue

        # 收盘后的指标判断
        if (row['MA10'] < row['MA21']) and (df.iloc[i - 1]['MA10'] >= df.iloc[i - 1]['MA21']):
            wait_for_reverse_exit = True

        if (row['close'] < row['open'] and
                row['close'] < row['MA10'] and
                row['close'] < row['MA21'] and
                row['MA10'] > row['MA21']):
            wait_for_breakdown_exit = True

        if (row['close'] < row['open'] and
                row['close'] < row['MA10'] and
                row['close'] < row['MA21'] and
                row['MA10'] < row['MA21']):
            wait_for_breakdown_exit = True

    # --- B. 空仓状态下：寻找开仓机会 ---
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
            daily_close_stop = None
            pending_daily_close_stop = None

            current_trade = {
                '开仓时间': date_str,
                '方向': '做多',
                '杠杆(倍)': int(LEVERAGE),
                '开仓价格': round(entry_price, 2),
                '投入成本(保证金)': round(margin_cost, 2),
                '仓位总价值': round(trade_capital, 2),
            }

# --- 循环结束强平 ---
if position_size > 0:
    last_row = df.iloc[-1]
    actual_sell = last_row['close']
    profit = (actual_sell - entry_price) * position_size
    net_pnl = profit
    balance += net_pnl
    current_trade.update({
        '平仓时间': str(df.index[-1])[:10],
        '平仓价格': round(actual_sell, 2),
        '平仓原因': '回测结束强平',
        '触发均线': None,
        '触发均线值': None,
        '盈亏(USDT)': round(net_pnl, 2),
        '平仓后余额': round(balance, 2),
        '本单收益率(%)': round((net_pnl / current_trade['投入成本(保证金)']) * 100, 2),
        '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
        '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),

        '平仓_MA10': round(last_row['MA10'], 2) if not pd.isna(last_row['MA10']) else None,
        '平仓_MA21': round(last_row['MA21'], 2) if not pd.isna(last_row['MA21']) else None,
        '平仓_MA99': round(last_row['MA99'], 2) if not pd.isna(last_row['MA99']) else None,
        '平仓_MA120': round(last_row['MA120'], 2) if not pd.isna(last_row['MA120']) else None,
        '平仓_MA180': round(last_row['MA180'], 2) if not pd.isna(last_row['MA180']) else None,
        '平仓_MA365': round(last_row['MA365'], 2) if not pd.isna(last_row['MA365']) else None,
    })
    trade_records.append(current_trade)

# ================= 5. 结果输出与保存 =================
print("=" * 50)
print(f"初始资金: {INITIAL_CAPITAL:.2f} USDT")
print(f"最终资金: {balance:.2f} USDT")
print(f"总收益率: {((balance - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100):.2f}%")
print(f"总交易次数: {len(trade_records)} 笔")
print("=" * 50)

if len(trade_records) > 0:
    records_df = pd.DataFrame(trade_records)
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
else:
    print("\n⚠️ 在周期内，没有触发任何符合条件的交易。")