import pandas as pd
import numpy as np
import os
#  十倍BTC 3日线有效成绩 10000到48210.89
# 这逻辑的爆仓是 亏损单次仓位 9%就爆仓了
fileName = "BTCUSDT_3D_merged.csv"
DATA_PATH = rf"re\{fileName}"
if not os.path.exists(DATA_PATH):
    DATA_PATH = rf"D:\Python\BianceStrategy\re\BianceData\MergedData\{fileName}"

INITIAL_CAPITAL = 10000.0
LEVERAGE = 10
POSITION_SIZE_PCT = 0.33
FEE_RATE = 0.0004
SLIPPAGE = 0.0005
TAKER_PROFIT_PCT = 0.03

DISTANCE_TO_MA = 0.03
BIG_BULL_CANDLE = 0.05
CLOSE_NEAR_HIGH_PCT = 0.02
NO_BIG_BEAR_CANDLE = 0.10
LOOKBACK_MA = [10, 21, 99, 120, 180, 365]

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
df['close_near_high'] = (df['high'] - df['close']) / df['high'] < CLOSE_NEAR_HIGH_PCT
df['bullish_pattern'] = df['is_bull'] & df['close_near_high']
df['body_pct'] = (df['close'] - df['open']) / df['open']
df['is_big_bull'] = df['bullish_pattern'] & (df['body_pct'] >= BIG_BULL_CANDLE)
df['is_big_bear'] = (df['open'] - df['close']) / df['open'] >= NO_BIG_BEAR_CANDLE

# ================= 3. 信号生成 =================
print("正在生成开仓信号...")
df['signal'] = 0
for i in range(1, len(df)):
    if pd.isna(df['MA21'].iloc[i]):
        continue

    # 大前提：MA10 > MA21 (多头排列)
    ma_trend_up = df['MA10'].iloc[i] > df['MA21'].iloc[i]
    if not ma_trend_up or not df['bullish_pattern'].iloc[i]:
        continue

    close_price = df['close'].iloc[i]
    ma10, ma21, ma180 = df['MA10'].iloc[i], df['MA21'].iloc[i], df['MA180'].iloc[i]

    # 🚨 终极逻辑：只要收盘价跌破 MA10 或 MA21 任何一根，就说明趋势被破坏，直接放弃开仓
    # 换句话说，收盘价必须大于 MA10 且 大于 MA21，才是合格的做多阳线
    if close_price < ma10 or close_price < ma21:
        continue

    open_price = df['open'].iloc[i]

    cond1 = True
    cond2 = (abs(open_price - ma10) / ma10 <= DISTANCE_TO_MA) or (abs(open_price - ma21) / ma21 <= DISTANCE_TO_MA)
    cond3 = False
    if ma180 < ma10:
        has_big_bear = df['is_big_bear'].iloc[max(0, i - 3):i + 1].any()
        if not has_big_bear:
            near_180 = abs(open_price - ma180) / ma180 <= DISTANCE_TO_MA
            break_180 = df['is_big_bull'].iloc[i]
            cond3 = near_180 or break_180

    if cond1 or cond2 or cond3:
        df.loc[df.index[i], 'signal'] = 1

# ================= 4. 回测引擎与交易记录 =================
print("开始执行回测引擎...\n")
balance = INITIAL_CAPITAL
position_size = 0
entry_price = 0
resistance_ma = None
liquidation_price = 0
wait_for_reverse_exit = False

trade_records = []
current_trade = {}

for i in range(1, len(df)):
    row = df.iloc[i]
    date_str = str(row.name)[:10]

    # --- A. 持仓状态下检查平仓 ---
    if position_size > 0:
        exit_reason = None
        actual_sell = 0

        if wait_for_reverse_exit:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "死叉平仓"
        elif row['low'] <= liquidation_price:
            actual_sell = liquidation_price
            exit_reason = "💥爆仓"
        elif row['high'] >= entry_price * (1 + TAKER_PROFIT_PCT):
            actual_sell = max(row['open'], entry_price * (1 + TAKER_PROFIT_PCT)) * (1 - SLIPPAGE)
            exit_reason = "固定止盈"
        elif resistance_ma is not None and row['high'] >= resistance_ma:
            actual_sell = max(row['open'], resistance_ma) * (1 - SLIPPAGE)
            exit_reason = "阻力止盈"

        if exit_reason:
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
                '本单收益率(%)': round((net_pnl / current_trade['投入成本(保证金)']) * 100, 2)
            })
            trade_records.append(current_trade)
            position_size = 0
            wait_for_reverse_exit = False
            continue

        if row['MA10'] < row['MA21']:
            wait_for_reverse_exit = True

    # --- B. 空仓状态下检查开仓 (当根K线收盘价买入) ---
    if row['signal'] == 1 and position_size == 0:
        if row['close'] > row['open']:
            margin_cost = balance * POSITION_SIZE_PCT
            trade_capital = margin_cost * LEVERAGE

            entry_price = row['close'] * (1 + SLIPPAGE)
            position_size = trade_capital / entry_price
            liquidation_price = entry_price * (1 - (0.9 / LEVERAGE))

            open_fee = trade_capital * FEE_RATE
            balance -= open_fee

            res_candidates = [row[f'MA{ma}'] for ma in [99, 120, 180]
                              if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] > entry_price]
            resistance_ma = min(res_candidates) if res_candidates else None

            current_trade = {
                '开仓时间': date_str,
                '方向': '做多',
                '杠杆(倍)': int(LEVERAGE),
                '开仓价格': round(entry_price, 2),
                '投入成本(保证金)': round(margin_cost, 2),
                '仓位总价值': round(trade_capital, 2),
            }

# 强制平仓剩余单子
if position_size > 0:
    actual_sell = df.iloc[-1]['close']
    profit = (actual_sell - entry_price) * position_size
    net_pnl = profit
    balance += net_pnl
    current_trade.update({
        '平仓时间': str(df.index[-1])[:10],
        '平仓价格': round(actual_sell, 2),
        '平仓原因': '回测结束强平',
        '盈亏(USDT)': round(net_pnl, 2),
        '平仓后余额': round(balance, 2),
        '本单收益率(%)': round((net_pnl / current_trade['投入成本(保证金)']) * 100, 2)
    })
    trade_records.append(current_trade)

# ================= 5. 结果输出 =================
print("=" * 50)
print(f"初始资金: {INITIAL_CAPITAL:.2f} USDT")
print(f"最终资金: {balance:.2f} USDT")
print(f"总收益率: {((balance - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100):.2f}%")
print(f"总交易次数: {len(trade_records)} 笔")
print("=" * 50)

if len(trade_records) > 0:
    records_df = pd.DataFrame(trade_records)
    cols = ['开仓时间', '方向', '杠杆(倍)', '开仓价格', '投入成本(保证金)', '仓位总价值',
            '平仓时间', '平仓价格', '平仓原因', '盈亏(USDT)', '本单收益率(%)', '平仓后余额']
    records_df = records_df[cols]

    print("\n--- 完整交易记录明细 ---")
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(records_df.to_string(index=False))

    csv_save_path = "trade_records.csv"
    records_df.to_csv(csv_save_path, index=False, encoding='utf-8-sig')
    print(f"\n📁 完整的交易记录已保存: {csv_save_path}")
else:
    print("\n⚠️ 没有触发符合条件的交易。")