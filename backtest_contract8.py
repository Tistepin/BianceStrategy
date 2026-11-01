import pandas as pd
import numpy as np
import os

# =====================================================================
# 🎯 策略说明：均线多头/即将金叉 + 强势回踩/追多策略
# 🚀 新增：动态实体-影线比例过滤（实体涨幅必须 >= 上影线幅度的 N 倍）
# 🛡️ 修复：拒绝空头趋势下的弱势贴脸买入，强制要求均线拐头向上
# 🌟 终极修复：新增“全K线悬空突破”豁免权，绝不错杀 2020-10-18 完美起爆点
# 🚧 新增防线：上方长线均线压制检测，拒绝 2022-02-27 这种“撞墙单”
# ✅ 本次修复：
#    1) 平仓时序改为“按同一根 K 线内价格发生的先后”排序：
#       开盘(open) → 盘中(low/high)。
#       开盘价已触发止损/跳空爆仓的，优先按开盘价成交；
#       开盘在爆仓价之上、盘中才跌穿的，才按爆仓价成交。
#    2) 爆仓不再硬清零 balance，改为按成交价结算本笔真实亏损，余额扣减后最低为 0。
#    3) “本单收益率(%)”爆仓时不再写死 -100，改为按真实净盈亏/保证金计算。
# 🌟 本次新增：
#    4) 长线均线止损：持仓期间，取 MA99/120/180/365 中“低于当日开盘价且最高”的一条
#       作为下方最近支撑止损线；盘中 low 跌破该线即止损。
#    5) 盘中触发顺序：长线止损 / 爆仓 / 止盈，按价格从高到低先触及谁就按谁成交；
#       长线止损优先于止盈，避免“先跌穿支撑又反抽到阻力”被误判为止盈。
# 🛡️ 长上影止损：
#    6) 持仓期间，若收盘出现“长上影阴线”，收盘标记 wait_for_shadow_exit，
#       下一根开盘按开盘价止损。纯上影线口径：high - max(open, close)，
#       除以 open 得到比例，默认 6%。
# 🛡️ 上下 x% 过滤：
#    7) 只针对长线均线 [99, 120, 180, 365]，MA10/MA21 不参与。
#       上方：长线均线在收盘价上方 <= 阈值 → 不开单（原有压制逻辑）。
#       下方：长线均线在收盘价下方 <= 阈值 → 不开单（新增支撑过滤）。
# 🎯 止盈容差：
#    8) 最高价进入止盈价下方 TP_TOLERANCE（默认 1%）以内即触发止盈，
#       不再要求 high >= 止盈线。止盈与止损、爆仓一起放进 intraday_hits，
#       按价格从高到低比较，先触及谁就按谁成交。
# 🛡️ MA21 止损：
#    9) 开盘价 <= MA21 → 开盘直接止损；
#       盘中模式（默认）：low <= MA21 → 盘中按 MA21 止损；
#       收盘模式：close < MA21 → 收盘标记，次日开盘止损。
#    ✅ 本次修正：MA21 止损只在 MA10 > MA21（多头排列）时生效。
#       如果 MA10 < MA21（空头排列），MA21 已不是有效短期支撑，
#       MA21 止损自动失效，回退到长线均线止损或死叉平仓。
# =====================================================================

# ================= 1. 参数与基础设置 =================
CoinName = "AVAX"
fileName = f"{CoinName}USDT_futures_3d.csv"
DATA_PATH = rf"re\{fileName}"
if not os.path.exists(DATA_PATH):
    DATA_PATH = rf"D:\Python\BianceStrategy\re\BianceData\{CoinName}USDT\3d\{fileName}"

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

# 🛡️ 长线均线止损开关与周期
ENABLE_LONG_MA_STOP = True
LONG_MA_PERIODS = [99, 120, 180, 365]

# 🛡️ 长上影止损
ENABLE_LONG_UPPER_SHADOW_STOP = True
LONG_UPPER_SHADOW_THRESHOLD = 0.2
LONG_UPPER_SHADOW_REQUIRE_BEAR = True  # 只对收盘阴线生效

# 🛡️ 上下 x% 过滤：只针对长线均线，MA10/MA21 不参与
RESISTANCE_DISTANCE_TO_MA = 0.05   # 上方：长线均线在收盘价上方 2% 内不开单
SUPPORT_DISTANCE_TO_MA = 0.05     # 下方：长线均线在收盘价下方 2% 内不开单
SUPPORT_SKIP_PERIODS = []          # 下方过滤跳过的周期，空列表表示全拦

# 🎯 止盈容差：最高价进入止盈价下方 x% 以内即触发止盈
TP_TOLERANCE = 0.01   # 1%，可调 0.005 / 0.01 / 0.02

# 🛡️ MA21 止损
ENABLE_MA21_STOP = False
MA21_STOP_MODE = "close"   # "intraday"=盘中 low 跌破 MA21 即止损；"close"=收盘跌破 MA21 才标记，次日开盘止损
MA21_STOP_REQUIRE_BULL = True  # ✅ 只在 MA10 > MA21（多头排列）时启用 MA21 止损

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
        if not is_full_breakout and (ma21 < df['MA21'].iloc[i - 1]):
            continue

        # 🚨 即将死叉过滤
        ma_diff_up = (ma10 - ma21) / ma21
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
            ma_diff = (ma21 - ma10) / ma21
            is_ma_close = ma_diff <= GOLDEN_CROSS_DISTANCE
            is_powerful_bull = df['is_big_bull'].iloc[i]
            is_valid_breakout = (close_price > ma10 * 1.015) and (close_price > ma21 * 1.015)
            if is_ma_close and is_powerful_bull and is_valid_breakout:
                cond4 = True

    # =========================================================================
    # 🛡️ 上下 x% 过滤：只针对长线均线 [99, 120, 180, 365]，MA10/MA21 不参与
    # =========================================================================
    if cond1 or cond2 or cond3 or cond4:
        is_suppressed = False
        is_near_support = False

        for long_ma_period in LONG_MA_PERIODS:
            long_ma_val = df[f'MA{long_ma_period}'].iloc[i]
            if pd.isna(long_ma_val):
                continue

            # 上方压力
            if long_ma_val > close_price:
                distance_to_res = (long_ma_val - close_price) / close_price
                if distance_to_res <= RESISTANCE_DISTANCE_TO_MA:
                    is_suppressed = True

            # 下方支撑
            elif long_ma_val < close_price:
                if long_ma_period in SUPPORT_SKIP_PERIODS:
                    continue
                distance_to_support = (close_price - long_ma_val) / close_price
                if distance_to_support <= SUPPORT_DISTANCE_TO_MA:
                    is_near_support = True

        if not is_suppressed and not is_near_support:
            df.loc[df.index[i], 'signal'] = 1

# ================= 4. 回测核心引擎 =================
print("开始执行回测引擎...\n")
balance = INITIAL_CAPITAL
position_size = 0
entry_price = 0
liquidation_price = 0

wait_for_reverse_exit = False
wait_for_breakdown_exit = False
wait_for_shadow_exit = False

current_max_loss_usdt = 0.0
current_max_loss_pct = 0.0

trade_records = []
current_trade = {}

for i in range(1, len(df)):
    row = df.iloc[i]
    date_str = str(row.name)[:10]

    # --- A. 持仓状态下：监控浮亏与平仓 ---
    if position_size > 0:
        if row['low'] < entry_price:
            floating_loss_usdt = (entry_price - row['low']) * position_size
            floating_loss_usdt += (entry_price * position_size * FEE_RATE)
            if floating_loss_usdt > current_max_loss_usdt:
                current_max_loss_usdt = floating_loss_usdt
                current_max_loss_pct = (current_max_loss_usdt / current_trade['投入成本(保证金)']) * 100

        exit_reason = None
        actual_sell = 0
        is_liquidated = False

        # 🚨 每日动态计算阻力位
        res_candidates = [row[f'MA{ma}'] for ma in LONG_MA_PERIODS
                          if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] > row['open']]
        dynamic_resistance = min(res_candidates) if res_candidates else None

        # 🛡️ 下方最近的长线均线作为支撑止损线
        long_stop = None
        long_stop_period = None
        if ENABLE_LONG_MA_STOP:
            below_ma_pairs = [(row[f'MA{ma}'], ma) for ma in LONG_MA_PERIODS
                              if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] < row['open']]
            if below_ma_pairs:
                long_stop, long_stop_period = max(below_ma_pairs, key=lambda x: x[0])

        # 🛡️ MA21 止损是否有效：必须 MA10 > MA21（多头排列），且未关闭
        ma21_stop_valid = (
            ENABLE_MA21_STOP
            and not pd.isna(row['MA10'])
            and not pd.isna(row['MA21'])
            and (not MA21_STOP_REQUIRE_BULL or row['MA10'] > row['MA21'])
        )

        # =====================================================================
        # ✅ 平仓时序：
        #    ① 开盘价已 <= 爆仓价：跳空穿仓，按开盘价成交
        #    ② 昨日收盘发出破位信号：今日开盘止损
        #    ③ 昨日收盘发出死叉信号：今日开盘平仓
        #    ④ 昨日收盘发出长上影信号：今日开盘止损
        #    ⑤ 🛡️ 开盘价 <= MA21 且 MA10 > MA21：开盘直接按 MA21 止损
        #    ⑥ 盘中触发：长线止损 / MA21 止损 / 爆仓 / 止盈（带容差），
        #       按价格从高到低先触及谁就按谁成交
        # =====================================================================
        if row['open'] <= liquidation_price:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "💥跳空爆仓"
            is_liquidated = True
        elif wait_for_breakdown_exit and ENABLE_BREAKDOWN_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "破位止损"
        elif wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "死叉平仓"
        elif wait_for_shadow_exit and ENABLE_LONG_UPPER_SHADOW_STOP:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "长上影止损"
        elif ma21_stop_valid and row['open'] <= row['MA21']:
            # 🛡️ 开盘已在 MA21 下方，且仍处于多头排列：按开盘价止损
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "开盘跌破MA21止损"
        else:
            # 盘中触发候选：长线止损、MA21 止损、爆仓、止盈（带容差）
            intraday_hits = []

            # 长线止损候选
            if long_stop is not None and row['low'] <= long_stop:
                intraday_hits.append((long_stop, f"跌破MA{long_stop_period}止损", False))

            # 🛡️ MA21 止损候选（仅 intraday 模式，且 MA10 > MA21）
            if ma21_stop_valid and MA21_STOP_MODE == "intraday" \
                    and row['low'] <= row['MA21']:
                intraday_hits.append((row['MA21'], "跌破MA21止损", False))

            # 爆仓候选
            if row['low'] <= liquidation_price:
                intraday_hits.append((liquidation_price, "💥爆仓", True))

            # 🎯 动态阻力止盈（带容差）：high 进入止盈价下方 TP_TOLERANCE 以内即触发
            if dynamic_resistance is not None and \
                    row['high'] >= dynamic_resistance * (1 - TP_TOLERANCE):
                tp_fill = max(row['open'], min(row['high'], dynamic_resistance))
                intraday_hits.append((tp_fill, "动态阻力止盈(容差)", False))

            if intraday_hits:
                # 按价格从高到低，先触及谁就按谁成交
                hit_price, hit_reason, hit_liq = max(intraday_hits, key=lambda x: x[0])
                actual_sell = hit_price if hit_liq else hit_price * (1 - SLIPPAGE)
                exit_reason = hit_reason
                is_liquidated = hit_liq

        # 执行平仓结算
        if exit_reason:
            profit = (actual_sell - entry_price) * position_size
            close_fee = position_size * actual_sell * FEE_RATE
            net_pnl = profit - close_fee
            balance += net_pnl
            if balance < 0:
                balance = 0

            margin_used = current_trade['投入成本(保证金)']
            trade_return_pct = round((net_pnl / margin_used) * 100, 2) if margin_used > 0 else 0.0

            if row['open'] > 0:
                close_upper_shadow_ratio = round(
                    (row['high'] - max(row['open'], row['close'])) / row['open'] * 100, 2
                )
            else:
                close_upper_shadow_ratio = None

            current_trade.update({
                '平仓时间': date_str,
                '平仓价格': round(actual_sell, 2),
                '平仓原因': exit_reason,
                '盈亏(USDT)': round(net_pnl, 2),
                '平仓后余额': round(balance, 2),
                '本单收益率(%)': trade_return_pct,
                '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
                '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),
                '平仓_上影线比例(%)': close_upper_shadow_ratio,

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
            wait_for_shadow_exit = False

            if balance <= 0:
                print(f"❌ {date_str} 账户发生全仓爆仓，资金归零，回测提前终止！")
                break
            continue

        # 收盘后的指标判断
        if (row['MA10'] < row['MA21']) and (df.iloc[i - 1]['MA10'] >= df.iloc[i - 1]['MA21']):
            ma_diff_down = (row['MA21'] - row['MA10']) / row['MA21']
            if ma_diff_down >= DEATH_CROSS_DISTANCE:
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

        # 🛡️ MA21 收盘模式：收盘跌破 MA21 才标记，次日开盘止损（仅 MA10 > MA21 时生效）
        if ENABLE_MA21_STOP and MA21_STOP_MODE == "close" \
                and not pd.isna(row['MA10']) and not pd.isna(row['MA21']) \
                and (not MA21_STOP_REQUIRE_BULL or row['MA10'] > row['MA21']) \
                and row['close'] < row['MA21']:
            wait_for_breakdown_exit = True

        # 🛡️ 长上影阴线止损判断（收盘标记，次日开盘执行）
        if ENABLE_LONG_UPPER_SHADOW_STOP:
            upper_shadow_price = row['high'] - max(row['open'], row['close'])
            upper_shadow_ratio = upper_shadow_price / row['open'] if row['open'] > 0 else 0.0
            is_bear_candle = row['close'] < row['open']
            if (not LONG_UPPER_SHADOW_REQUIRE_BEAR or is_bear_candle) and \
                    upper_shadow_ratio >= LONG_UPPER_SHADOW_THRESHOLD:
                wait_for_shadow_exit = True

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
            wait_for_shadow_exit = False

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
    close_fee = position_size * actual_sell * FEE_RATE
    net_pnl = profit - close_fee
    balance += net_pnl
    if balance < 0:
        balance = 0
    margin_used = current_trade['投入成本(保证金)']
    trade_return_pct = round((net_pnl / margin_used) * 100, 2) if margin_used > 0 else 0.0

    if last_row['open'] > 0:
        last_upper_shadow_ratio = round(
            (last_row['high'] - max(last_row['open'], last_row['close'])) / last_row['open'] * 100, 2
        )
    else:
        last_upper_shadow_ratio = None

    current_trade.update({
        '平仓时间': str(df.index[-1])[:10],
        '平仓价格': round(actual_sell, 2),
        '平仓原因': '回测结束强平',
        '盈亏(USDT)': round(net_pnl, 2),
        '平仓后余额': round(balance, 2),
        '本单收益率(%)': trade_return_pct,
        '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
        '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),
        '平仓_上影线比例(%)': last_upper_shadow_ratio,

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
            '平仓时间', '平仓价格', '平仓原因', '盈亏(USDT)', '本单收益率(%)',
            '持仓期最大浮亏(USDT)', '最大浮亏占保证金(%)', '平仓_上影线比例(%)',
            '平仓_MA10', '平仓_MA21', '平仓_MA99', '平仓_MA120', '平仓_MA180', '平仓_MA365',
            '平仓后余额']
    records_df = records_df[cols]

    print("\n--- 完整交易记录明细 ---")
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(records_df.to_string(index=False))

    csv_save_path = "trade_records1.csv"
    records_df.to_csv(csv_save_path, index=False, encoding='utf-8-sig')
    print(f"\n📁 完整的交易记录已保存为当前目录下的: {csv_save_path}")
else:
    print("\n⚠️ 在周期内，没有触发任何符合条件的交易。")