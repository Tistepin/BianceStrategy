import pandas as pd
import numpy as np
import os

# =====================================================================
# 🎯 策略说明：周线级别趋势跟踪
# 🚀 核心升级：即将金叉只认“强力破位”（大实体 + 远距离），拒绝弱势贴脸买入
# =====================================================================

# ================= 1. 参数与基础设置 =================
fileName = "BTCUSDT_1W_merged.csv"
DATA_PATH = rf"re\{fileName}"
if not os.path.exists(DATA_PATH):
    DATA_PATH = rf"D:\Python\BianceStrategy\re\BianceData\MergedData\{fileName}"
INITIAL_CAPITAL = 10000.0
LEVERAGE = 5.0
POSITION_SIZE_PCT = 0.33
FEE_RATE = 0.0004
SLIPPAGE = 0.0005

# --- 距离与阈值 ---
DISTANCE_TO_MA = 0.05
CHASE_DISTANCE_TO_MA = 0.15

GOLDEN_CROSS_DISTANCE = 0.03
DEATH_CROSS_DISTANCE = 0.005

# 🚀 核心：即将金叉时的强力破位参数
GOLDEN_BREAKOUT_MULTIPLIER = 3.0  # 实体涨幅 > 3% * 3 = 9%
POWERFUL_BREAKOUT_DISTANCE_TO_MA = 0.05  # 🚨 收盘价必须比 MA10 或 MA21 高出至少 5%

LOOKBACK_MA = [10, 21, 50, 120, 180, 365]
RESISTANCE_MA = [50, 120, 180, 365]

# --- 形态过滤参数 ---
CLOSE_NEAR_HIGH_PCT = 0.05
BODY_SHADOW_MULTIPLIER = 1.5
BIG_BULL_CANDLE = 0.05
POWERFUL_BULL_CANDLE = 0.15
NO_BIG_BEAR_CANDLE = 0.10

# --- 币安风控参数 ---
MMR = 0.005
UNI_MMR_LIMIT = 1.05
ENABLE_DEATH_CROSS_EXIT = True
ENABLE_BREAKDOWN_EXIT = True

# 🚨 开关保留，但逻辑已变：只允许强力破位，不允许贴脸抄底
ENABLE_GOLDEN_CROSS_CHASE = True

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
df['upper_shadow_pct'] = (df['high'] - df['close']) / df['high']
df['body_pct'] = (df['close'] - df['open']) / df['open']

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

    if not df['bullish_pattern'].iloc[i]:
        continue

    close_price = df['close'].iloc[i]
    open_price = df['open'].iloc[i]
    ma10, ma21, ma50 = df['MA10'].iloc[i], df['MA21'].iloc[i], df['MA50'].iloc[i]

    if close_price < ma10 or close_price < ma21:
        continue

    cond1 = False
    cond2 = False
    cond3 = False
    cond4 = False

    ma_trend_up = ma10 > ma21

    if ma_trend_up:
        # 标准多头排列（已金叉）
        ma_diff_up = (ma10 - ma21) / ma21
        if ma_diff_up <= DEATH_CROSS_DISTANCE:
            is_super_powerful = df['bullish_pattern'].iloc[i] and (df['body_pct'].iloc[i] >= POWERFUL_BULL_CANDLE)
            if not is_super_powerful:
                continue

        cond1 = (abs(open_price - ma10) / ma10 <= CHASE_DISTANCE_TO_MA) or \
                (abs(open_price - ma21) / ma21 <= CHASE_DISTANCE_TO_MA)
        cond2 = (abs(open_price - ma10) / ma10 <= DISTANCE_TO_MA) or \
                (abs(open_price - ma21) / ma21 <= DISTANCE_TO_MA)

        if not pd.isna(ma50) and ma50 < ma10:
            has_big_bear = df['is_big_bear'].iloc[max(0, i - 3):i + 1].any()
            if not has_big_bear:
                near_50 = abs(open_price - ma50) / ma50 <= DISTANCE_TO_MA
                break_50 = df['is_big_bull'].iloc[i]
                cond3 = near_50 or break_50
    else:
        # 🚨 空头排列（即将金叉）：只认“强力破位”
        if ENABLE_GOLDEN_CROSS_CHASE:
            # 要求实体涨幅 >= 9%
            is_strong_body = df['body_pct'].iloc[i] >= (GOLDEN_CROSS_DISTANCE * GOLDEN_BREAKOUT_MULTIPLIER)

            # 要求收盘价距离均线 >= 5%
            is_far_enough = ((close_price - ma10) / ma10 >= POWERFUL_BREAKOUT_DISTANCE_TO_MA) and \
                            ((close_price - ma21) / ma21 >= POWERFUL_BREAKOUT_DISTANCE_TO_MA)

            cond4 = is_strong_body and is_far_enough

    if cond1 or cond2 or cond3 or cond4:
        df.loc[df.index[i], 'signal'] = 1

# ================= 4. 回测核心引擎 =================
print("开始执行回测引擎...\n")
balance = INITIAL_CAPITAL
position_size = 0
entry_price = 0
liquidation_price = 0

wait_for_reverse_exit = False

current_max_loss_usdt = 0.0
current_max_loss_pct = 0.0

trade_records = []
current_trade = {}

for i in range(1, len(df)):
    row = df.iloc[i]
    date_str = str(row.name)[:10]

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

        res_candidates = [row[f'MA{ma}'] for ma in RESISTANCE_MA
                          if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] > row['open']]
        dynamic_resistance = min(res_candidates) if res_candidates else None

        if row['low'] <= liquidation_price:
            actual_sell = liquidation_price
            exit_reason = "💥爆仓"
            is_liquidated = True

        elif wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "死叉平仓"

        elif dynamic_resistance is not None and row['high'] >= dynamic_resistance:
            actual_sell = max(row['open'], dynamic_resistance) * (1 - SLIPPAGE)
            exit_reason = "动态阻力止盈"

        elif ENABLE_BREAKDOWN_EXIT and (row['close'] < row['MA10'] and row['close'] < row['MA21']):
            actual_sell = row['close'] * (1 - SLIPPAGE)
            exit_reason = "收盘破位止损"

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
                '盈亏(USDT)': round(net_pnl, 2),
                '平仓后余额': round(balance, 2),
                '本单收益率(%)': round((net_pnl / current_trade['投入成本(保证金)']) * 100,
                                       2) if not is_liquidated else -100.00,
                '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
                '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),

                '平仓_MA10': round(row['MA10'], 2) if not pd.isna(row['MA10']) else None,
                '平仓_MA21': round(row['MA21'], 2) if not pd.isna(row['MA21']) else None,
                '平仓_MA50': round(row['MA50'], 2) if not pd.isna(row['MA50']) else None,
                '平仓_MA120': round(row['MA120'], 2) if not pd.isna(row['MA120']) else None,
                '平仓_MA180': round(row['MA180'], 2) if not pd.isna(row['MA180']) else None,
                '平仓_MA365': round(row['MA365'], 2) if not pd.isna(row['MA365']) else None,
            })
            trade_records.append(current_trade)

            position_size = 0
            wait_for_reverse_exit = False

            if balance <= 0:
                print(f"❌ {date_str} 账户发生全仓爆仓，资金归零，回测提前终止！")
                break
            continue

        if (row['MA10'] < row['MA21']) and (df.iloc[i - 1]['MA10'] >= df.iloc[i - 1]['MA21']):
            wait_for_reverse_exit = True

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
        '盈亏(USDT)': round(net_pnl, 2),
        '平仓后余额': round(balance, 2),
        '本单收益率(%)': round((net_pnl / current_trade['投入成本(保证金)']) * 100, 2),
        '持仓期最大浮亏(USDT)': round(current_max_loss_usdt, 2),
        '最大浮亏占保证金(%)': round(current_max_loss_pct, 2),

        '平仓_MA10': round(last_row['MA10'], 2) if not pd.isna(last_row['MA10']) else None,
        '平仓_MA21': round(last_row['MA21'], 2) if not pd.isna(last_row['MA21']) else None,
        '平仓_MA50': round(last_row['MA50'], 2) if not pd.isna(last_row['MA50']) else None,
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
            '持仓期最大浮亏(USDT)', '最大浮亏占保证金(%)',
            '平仓_MA10', '平仓_MA21', '平仓_MA50', '平仓_MA120', '平仓_MA180', '平仓_MA365',
            '平仓后余额']
    records_df = records_df[cols]

    print("\n--- 完整交易记录明细 ---")
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(records_df.to_string(index=False))

    csv_save_path = "trade_records_weekly.csv"
    records_df.to_csv(csv_save_path, index=False, encoding='utf-8-sig')
    print(f"\n📁 完整的周线交易记录已保存为: {csv_save_path}")
else:
    print("\n⚠️ 在周期内，没有触发任何符合条件的交易。")