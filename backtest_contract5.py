import pandas as pd
import numpy as np
import os

# =====================================================================
# 🎯 策略说明：均线多头/即将金叉 + 强势回踩/追多策略
# 🚀 新增：动态实体-影线比例过滤（实体涨幅必须 >= 上影线幅度的 N 倍）
# 🛡️ 修复：拒绝空头趋势下的弱势贴脸买入，强制要求均线拐头向上
# 🌟 终极修复：新增“全K线悬空突破”豁免权，绝不错杀 2020-10-18 完美起爆点
# 🚧 新增防线：上方长线均线压制检测，拒绝 2022-02-27 这种“撞墙单”  最终版
# =====================================================================

# ================= 1. 参数与基础设置 =================
fileName = "BTCUSDT_futures_3d.csv"
DATA_PATH = rf"re\{fileName}"
if not os.path.exists(DATA_PATH):
    DATA_PATH = rf"D:\Python\BianceStrategy\re\BTCUSDT_futures_3d.csv"

INITIAL_CAPITAL = 10000.0
LEVERAGE = 5.0
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
df['upper_shadow_pct'] = (df['high'] - df['close']) / df['high']
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

# ================= 4. 回测核心引擎 =================
print("开始执行回测引擎...\n")
balance = INITIAL_CAPITAL
position_size = 0
entry_price = 0
liquidation_price = 0

wait_for_reverse_exit = False
wait_for_breakdown_exit = False

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
        res_candidates = [row[f'MA{ma}'] for ma in [99, 120, 180, 365]
                          if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] > row['open']]
        dynamic_resistance = min(res_candidates) if res_candidates else None

        # 🚨 平仓优先级：爆仓 > 破位止损 > 死叉 > 动态阻力止盈
        if row['low'] <= liquidation_price:
            actual_sell = liquidation_price
            exit_reason = "💥爆仓"
            is_liquidated = True
        elif wait_for_breakdown_exit and ENABLE_BREAKDOWN_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "破位止损"
        elif wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "死叉平仓"
        elif dynamic_resistance is not None and row['high'] >= dynamic_resistance:
            actual_sell = max(row['open'], dynamic_resistance) * (1 - SLIPPAGE)
            exit_reason = "动态阻力止盈"

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
            '持仓期最大浮亏(USDT)', '最大浮亏占保证金(%)',
            '平仓_MA10', '平仓_MA21', '平仓_MA99', '平仓_MA120', '平仓_MA180', '平仓_MA365',
            '平仓后余额']
    records_df = records_df[cols]

    print("\n--- 完整交易记录明细 ---")
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(records_df.to_string(index=False))

    csv_save_path = "trade_records.csv"
    records_df.to_csv(csv_save_path, index=False, encoding='utf-8-sig')
    print(f"\n📁 完整的交易记录已保存为当前目录下的: {csv_save_path}")
else:
    print("\n⚠️ 在周期内，没有触发任何符合条件的交易。")