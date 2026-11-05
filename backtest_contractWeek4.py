# =====================================================================
# 📌 文件说明
# 本脚本是「BTC 永续合约 · 周线级别 · 只做多」的完整回测程序。
#
# 策略核心思想：
#   1. 只在周线出现「强势阳线」时考虑做多；
#   2. 做多分两种大场景：
#        A. 均线已经多头排列（MA10 > MA21）→ 找「回踩贴脸」或「突破追多」；
#        B. 均线尚未金叉但即将金叉（MA10 < MA21 且距离很近）→ 只认「强力大阳线突破」；
#   3. 用长线均线（MA99/120/180/365）做「上方压力过滤」和「下方支撑过滤」；
#   4. 持仓后用「长线均线止损 + 死叉平仓 + 破位平仓 + 长上影止损 + 动态阻力止盈 + 爆仓」管理风险；
#   5. 所有成交都考虑手续费与滑点，爆仓按真实成交价结算，余额最低为 0。
#
# 重要约定：
#   - 信号在「本周收盘后」确认，下一根周 K 的开盘价附近才成交（代码里用当根 close 作为 entry，属于近似；
#     真实交易中应理解为「收盘确认后、下一根开盘附近入场」）。
#   - 平仓时序严格按：先判断开盘跳空/开盘触发 → 再判断盘中 low/high 触发。
# =====================================================================

import pandas as pd
import numpy as np
import os

# =====================================================================
# 🎯 策略說明：週線版 均線多頭/即將金叉 + 強勢回踩/追多策略
# 🚀 動態實體-影線比例過濾（實體漲幅必須 >= 上影線幅度的 N 倍）
# 🛡️ 拒絕空頭趨勢下的弱勢貼臉買入，強制要求均線拐頭向上
# 🌟 全K線懸空突破豁免權
# 🚧 上方長線均線壓制檢測
# ✅ 平倉時序：開盤(open) → 盤中(low/high)
# ✅ 爆倉按成交價結算真實虧損，餘額最低為 0
# ✅ 長線均線止損：MA30/60/120/180 中低於開盤價且最高的一條
# ✅ 長上影止損：收盤標記，下一根開盤止損
# ✅ 上下 x% 過濾：只針對長線均線
# =====================================================================

# ================= 1. 參數與基礎設置（週線專用） =================

# ---- 1.1 数据文件定位 ----
CoinName = "BTC"  # 交易标的：BTC
fileName = f"{CoinName}USDT_futures_1w.csv"  # 周线数据文件名
DATA_PATH = rf"re\{fileName}"  # 优先在当前目录的 re\ 下找
if not os.path.exists(DATA_PATH):  # 如果当前目录找不到
    # 则回退到本机绝对路径（你本机的数据仓库位置）
    DATA_PATH = rf"f:\Python\BianceStrategy\re\BianceData\{CoinName}USDT\1w\{fileName}"

# ---- 1.2 资金与交易成本 ----
INITIAL_CAPITAL = 10000.0  # 初始资金 10000 USDT
LEVERAGE = 5  # 杠杆倍数。注释说“从5降到3”，但实际值仍是5，注意这里以代码为准
POSITION_SIZE_PCT = 0.33  # 每次开仓投入「当前余额」的 33% 作为保证金（注释写25%，实际33%）
FEE_RATE = 0.0004  # 单边手续费率 0.04%（开仓和平仓各收一次）
SLIPPAGE = 0.0005  # 单边滑点 0.05%，买入时价格上浮、卖出时价格下调

# ---- 1.3 均线周期（周线口径） ----
FAST_MA = 10  # 快线 MA10（约 2.5 个月）
SLOW_MA = 21  # 慢线 MA21（约 5 个月）
COND3_MA = 180  # cond3 专用长线均线 MA180（约 3.5 年）
LONG_MA_PERIODS = [99, 120, 180, 365]  # 所有长线均线周期，用于压力/支撑过滤与止损
ALL_MA = [FAST_MA, SLOW_MA] + LONG_MA_PERIODS  # 所有需要计算的均线
LOOKBACK_MA = ALL_MA  # 需要预计算的均线列表（与 ALL_MA 相同）

# ---- 1.4 形态与距离阈值（周线放大） ----
DISTANCE_TO_MA = 0.08  # 「贴脸」距离：开盘价距离 MA10/MA21 在 8% 以内算贴脸
CHASE_DISTANCE_TO_MA = 0.30  # 「追多」距离：开盘价距离 MA10/MA21 在 30% 以内都允许追
GOLDEN_CROSS_DISTANCE = 0.08  # 「即将金叉」：MA21 高于 MA10 的幅度 <= 8% 才算接近金叉
DEATH_CROSS_DISTANCE = 0.005  # 「死叉有效」：MA10 跌破 MA21 且幅度 >= 0.5% 才触发死叉平仓
MA_DIFF_UP_MIN = 0.02  # 多头排列时，MA10 必须比 MA21 高出至少 2%，否则视为“均线纠缠”
BREAKOUT_BUFFER = 0.03  # 即将金叉追多时，收盘必须高于 MA10/MA21 至少 3% 的缓冲

# ---- 1.5 K 线形态过滤（周线放大） ----
CLOSE_NEAR_HIGH_PCT = 0.06  # 上影线比例必须 < 6%，即收盘不能离最高价太远
BODY_SHADOW_MULTIPLIER = 2.0  # 实体涨幅必须 >= 上影线幅度的 2 倍（强势阳线）
BIG_BULL_CANDLE = 0.05  # 大阳线：实体涨幅 >= 5%（注释写12%，实际5%）
POWERFUL_BULL_CANDLE = 0.20  # 超级大阳线：实体涨幅 >= 20%
NO_BIG_BEAR_CANDLE = 0.25  # 大阴线：实体跌幅 >= 25%，用于 cond3 的“近期无大阴线”判断

# ---- 1.6 币安风控参数 ----
MMR = 0.005  # 维持保证金率 0.5%
UNI_MMR_LIMIT = 1.05  # 统一维持保证金上限系数，用于计算爆仓价
ENABLE_DEATH_CROSS_EXIT = True  # 是否启用「死叉平仓」
ENABLE_BREAKDOWN_EXIT = True  # 是否启用「破位平仓」

# 是否允许「即将金叉」时买入
ENABLE_GOLDEN_CROSS_CHASE = True

# ---- 1.7 长线均线止损 ----
ENABLE_LONG_MA_STOP = True  # 是否启用「跌破下方最近长线均线」止损

# ---- 1.8 长上影止损 ----
ENABLE_LONG_UPPER_SHADOW_STOP = True  # 是否启用「长上影阴线」止损
LONG_UPPER_SHADOW_THRESHOLD = 0.20  # 上影线长度 >= 开盘价的 20% 算长上影
LONG_UPPER_SHADOW_REQUIRE_BEAR = True  # 是否要求必须是阴线才触发（True=只认阴线）

# ---- 1.9 上下 x% 过滤：只针对长线均线 ----
RESISTANCE_DISTANCE_TO_MA = 0.2  # 上方长线均线若在收盘价上方 20% 内 → 视为压力，不開單
SUPPORT_DISTANCE_TO_MA = 0.2  # 下方长线均线若在收盘价下方 20% 内 → 视为支撑太近，不開單
# 注意：注释写30%，实际值是0.2（20%）
SUPPORT_SKIP_PERIODS = [COND3_MA]  # 下方支撑过滤时跳过 MA180，保留 cond3 的 near_180 逻辑

# ================= 2. 數據加載與指標計算 =================
print("正在加載數據並進行預處理...")

# ---- 2.1 读取 CSV ----
df = pd.read_csv(DATA_PATH)
df['time'] = pd.to_datetime(df['time'])  # 时间列转 datetime
for col in ['open', 'high', 'low', 'close', 'volume']:
    df[col] = pd.to_numeric(df[col], errors='coerce')  # 强制转数值，非法值变 NaN
df = df.dropna()  # 删除含 NaN 的行
df = df.set_index('time')  # 用时间做索引，方便按日期定位

# ---- 2.2 计算所有均线 ----
for ma in LOOKBACK_MA:
    # rolling(window=ma).mean()：过去 ma 根周线收盘价的简单移动平均
    df[f'MA{ma}'] = df['close'].rolling(window=ma).mean()

# ---- 2.3 基础 K 线属性 ----
df['is_bull'] = df['close'] > df['open']  # 是否阳线（收盘 > 开盘）

# 上影线比例 = (最高价 - 收盘价) / 收盘价
# 注意：这里用 close 做分母，而不是 open；对阳线来说 close>open，分母略大，数值略小
df['upper_shadow_pct'] = (df['high'] - df['close']) / df['close']

# 实体涨幅 = (收盘价 - 开盘价) / 开盘价
# 阳线为正，阴线为负
df['body_pct'] = (df['close'] - df['open']) / df['open']

# 实体是否足够强：实体涨幅 >= 上影线比例 × 倍数
# 目的：过滤“上影线很长、实体很小”的弱势阳线
df['is_body_strong'] = df['body_pct'] >= (df['upper_shadow_pct'] * BODY_SHADOW_MULTIPLIER)

# 强势阳线形态（第一道大闸）：
#   1) 必须是阳线
#   2) 上影线比例 < 6%（收盘接近最高价）
#   3) 实体足够强（实体 >= 上影线 × 2）
df['bullish_pattern'] = (
        df['is_bull']
        & (df['upper_shadow_pct'] < CLOSE_NEAR_HIGH_PCT)
        & df['is_body_strong']
)

# 大阳线：在强势阳线基础上，实体涨幅 >= 5%
df['is_big_bull'] = df['bullish_pattern'] & (df['body_pct'] >= BIG_BULL_CANDLE)

# 大阴线：实体跌幅 >= 25%
df['is_big_bear'] = (df['open'] - df['close']) / df['open'] >= NO_BIG_BEAR_CANDLE

# ================= 3. 生成做多信號 =================
print("正在生成開倉信號...")

df['signal'] = 0  # 初始化信号列，1 表示“本周收盘后确认做多”

for i in range(1, len(df)):  # 从第 2 根 K 线开始遍历（需要前一根做比较）
    # ---- 3.1 数据完整性检查 ----
    if pd.isna(df[f'MA{SLOW_MA}'].iloc[i]):
        continue  # MA21 还没算出来（前 20 根），跳过

    # ---- 3.2 第一道大闸：必须是强势阳线 ----
    # 如果本周不是“实体强、上影短”的阳线，后面所有条件都不用看了
    if not df['bullish_pattern'].iloc[i]:
        continue

    # ---- 3.3 取出本周关键价格与均线 ----
    close_price = df['close'].iloc[i]  # 本周收盘价
    open_price = df['open'].iloc[i]  # 本周开盘价
    ma_fast = df[f'MA{FAST_MA}'].iloc[i]  # MA10
    ma_slow = df[f'MA{SLOW_MA}'].iloc[i]  # MA21
    ma_cond3 = df[f'MA{COND3_MA}'].iloc[i]  # MA180（cond3 专用）

    # ---- 3.4 大前提：收盘价必须站上快慢均线 ----
    # 如果收盘还在 MA10 或 MA21 下方，说明均线还没被突破，不做多
    if close_price < ma_fast or close_price < ma_slow:
        continue

    # 四个买入条件，初始都为 False
    cond1 = False  # 标准多头排列下的“追多”
    cond2 = False  # 标准多头排列下的“贴脸回踩”
    cond3 = False  # 标准多头排列下，突破/贴近 MA180 且近期无大阴线
    cond4 = False  # 即将金叉下的“强力突破追多”

    # 当前是否已经多头排列（MA10 > MA21）
    ma_trend_up = ma_fast > ma_slow

    # =========================================================
    # 分支 A：均线已经多头排列（MA10 > MA21）
    # =========================================================
    if ma_trend_up:
        # ---- A.1 判断“全悬空突破” ----
        # 开盘价和收盘价全部站在 MA10、MA21 之上，且是阳线
        # 这种形态视为极强，后面可以豁免“慢线拐头”和“均线拉开距离”的检查
        is_full_breakout = (
                (open_price > ma_fast) and (open_price > ma_slow)
                and (close_price > ma_fast) and (close_price > ma_slow)
                and df['is_bull'].iloc[i]
        )

        # ---- A.2 慢线必须走平或向上拐头（全悬空突破豁免）----
        # 如果 MA21 还在往下走，说明中期趋势仍弱，拒绝买入
        # 例外：全悬空突破说明价格极强，允许 MA21 暂时向下
        if not is_full_breakout and (ma_slow < df[f'MA{SLOW_MA}'].iloc[i - 1]):
            continue

        # ---- A.3 防止“即将死叉”的假多头 ----
        # 多头排列时，MA10 必须比 MA21 高出至少 2%，否则均线太纠缠，容易马上死叉
        ma_diff_up = (ma_fast - ma_slow) / ma_slow
        if not is_full_breakout and (ma_diff_up <= MA_DIFF_UP_MIN):
            # 例外：如果本周是超级大阳线（实体 >= 20%），允许均线纠缠时买入
            is_super_powerful = (
                    df['bullish_pattern'].iloc[i]
                    and (df['body_pct'].iloc[i] >= POWERFUL_BULL_CANDLE)
            )
            if not is_super_powerful:
                continue

        # ---- A.4 cond1：标准追多 ----
        # 开盘价距离 MA10 或 MA21 在 30% 以内，就允许追多
        # 含义：价格没有离均线太远，追高风险可控
        cond1 = (
                (abs(open_price - ma_fast) / ma_fast <= CHASE_DISTANCE_TO_MA)
                or (abs(open_price - ma_slow) / ma_slow <= CHASE_DISTANCE_TO_MA)
        )

        # ---- A.5 cond2：贴脸回踩 ----
        # 必须同时满足：
        #   1) 本周是“大阳线”或“全悬空突破”（强势确认）
        #   2) 开盘价距离 MA10 或 MA21 在 8% 以内（贴脸）
        # 含义：价格回踩到均线附近后，出现强势大阳线，买回踩
        is_strong_close = df['is_big_bull'].iloc[i] or is_full_breakout
        cond2 = is_strong_close and (
                (abs(open_price - ma_fast) / ma_fast <= DISTANCE_TO_MA)
                or (abs(open_price - ma_slow) / ma_slow <= DISTANCE_TO_MA)
        )

        # ---- A.6 cond3：MA180 附近/突破 ----
        # 前提：MA180 已经低于 MA10（长期均线在短期均线下方，说明大趋势向上）
        if not pd.isna(ma_cond3) and ma_cond3 < ma_fast:
            # 最近 4 根周线（含本周）不能出现大阴线，否则视为趋势被破坏
            has_big_bear = df['is_big_bear'].iloc[max(0, i - 3):i + 1].any()
            if not has_big_bear:
                # near_cond3：开盘价距离 MA180 在 8% 以内（贴近长期均线）
                near_cond3 = abs(open_price - ma_cond3) / ma_cond3 <= DISTANCE_TO_MA
                # break_cond3：本周是大阳线，直接突破 MA180
                break_cond3 = df['is_big_bull'].iloc[i]
                cond3 = near_cond3 or break_cond3

    # =========================================================
    # 分支 B：均线尚未金叉（MA10 <= MA21），但可能“即将金叉”
    # =========================================================
    else:
        if ENABLE_GOLDEN_CROSS_CHASE:
            # MA21 高于 MA10 的幅度
            ma_diff = (ma_slow - ma_fast) / ma_slow

            # 两条均线距离 <= 8%，才算“即将金叉”
            is_ma_close = ma_diff <= GOLDEN_CROSS_DISTANCE

            # 本周必须是大阳线（强势确认）
            is_powerful_bull = df['is_big_bull'].iloc[i]

            # 收盘必须强势突破 MA10 和 MA21，且高出 3% 的缓冲
            # 目的：拒绝“只是碰一下均线”的弱突破，要求有效站上
            is_valid_breakout = (
                    (close_price > ma_fast * (1 + BREAKOUT_BUFFER))
                    and (close_price > ma_slow * (1 + BREAKOUT_BUFFER))
            )

            # 三个条件同时满足，才认定 cond4
            if is_ma_close and is_powerful_bull and is_valid_breakout:
                cond4 = True

    # =========================================================
    # 3.5 长线均线上下 x% 过滤（最后一层大闸）
    # =========================================================
    # 只有前面 cond1~cond4 至少有一个成立，才进入过滤
    if cond1 or cond2 or cond3 or cond4:
        is_suppressed = False  # 是否被上方长线均线压制
        is_near_support = False  # 是否离下方长线均线太近

        for long_ma_period in LONG_MA_PERIODS:
            long_ma_val = df[f'MA{long_ma_period}'].iloc[i]
            if pd.isna(long_ma_val):
                continue  # 该长线均线还没算出来

            # ---- 情况 1：长线均线在收盘价上方 → 视为压力 ----
            if long_ma_val > close_price:
                distance_to_res = (long_ma_val - close_price) / close_price
                # 压力距离在 20% 以内 → 上方空间不足，不開單
                if distance_to_res <= RESISTANCE_DISTANCE_TO_MA:
                    is_suppressed = True

            # ---- 情况 2：长线均线在收盘价下方 → 视为支撑 ----
            elif long_ma_val < close_price:
                # 如果该周期在“跳过列表”里（默认是 MA180），不参与下方支撑过滤
                if long_ma_period in SUPPORT_SKIP_PERIODS:
                    continue
                distance_to_support = (close_price - long_ma_val) / close_price
                # 支撑距离在 20% 以内 → 离支撑太近，不開單
                if distance_to_support <= SUPPORT_DISTANCE_TO_MA:
                    is_near_support = True

        # 既没有被上方压力压制，也没有离下方支撑太近 → 才真正写入 signal=1
        if not is_suppressed and not is_near_support:
            df.loc[df.index[i], 'signal'] = 1

# ================= 4. 回測核心引擎 =================
print("開始執行回測引擎...\n")

# ---- 4.1 账户与持仓状态初始化 ----
balance = INITIAL_CAPITAL  # 当前账户余额（USDT）
position_size = 0  # 当前持仓数量（币），0 表示空仓
entry_price = 0  # 开仓均价
liquidation_price = 0  # 爆仓价

# 三种“收盘标记、下一根开盘执行”的延迟平仓标记
wait_for_reverse_exit = False  # 死叉平仓标记
wait_for_breakdown_exit = False  # 破位平仓标记
wait_for_shadow_exit = False  # 长上影止损标记

current_max_loss_usdt = 0.0  # 本笔交易持仓期间最大浮亏（USDT）
current_max_loss_pct = 0.0  # 本笔交易最大浮亏占保证金比例（%）

trade_records = []  # 所有已完成交易的记录
current_trade = {}  # 当前正在持仓的交易字典

for i in range(1, len(df)):
    row = df.iloc[i]  # 当前周 K
    date_str = str(row.name)[:10]  # 当前日期字符串（YYYY-MM-DD）

    # =========================================================
    # A. 持倉狀態：監控浮虧與平倉
    # =========================================================
    if position_size > 0:

        # ---- A.1 记录持仓期间最大浮亏 ----
        # 只用本周最低价 low 来估算最差情况
        if row['low'] < entry_price:
            # 浮亏 = (开仓价 - 本周最低价) × 持仓数量
            floating_loss_usdt = (entry_price - row['low']) * position_size
            # 再加上开仓手续费（近似）
            floating_loss_usdt += (entry_price * position_size * FEE_RATE)
            # 如果创出更大浮亏，则更新记录
            if floating_loss_usdt > current_max_loss_usdt:
                current_max_loss_usdt = floating_loss_usdt
                current_max_loss_pct = (
                                               current_max_loss_usdt / current_trade['投入成本(保證金)']
                                       ) * 100

        exit_reason = None  # 平仓原因
        actual_sell = 0  # 实际卖出价
        is_liquidated = False  # 是否爆仓

        # ---- A.2 计算本周“动态阻力位” ----
        # 在所有长线均线中，找出“高于本周开盘价”的均线，取最低的一条作为阻力
        res_candidates = [
            row[f'MA{ma}'] for ma in LONG_MA_PERIODS
            if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] > row['open']
        ]
        dynamic_resistance = min(res_candidates) if res_candidates else None

        # ---- A.3 计算“下方最近长线均线止损位” ----
        # 在所有长线均线中，找出“低于本周开盘价”的均线，取最高的一条作为止损
        long_stop = None
        long_stop_period = None
        if ENABLE_LONG_MA_STOP:
            below_ma_pairs = [
                (row[f'MA{ma}'], ma) for ma in LONG_MA_PERIODS
                if not pd.isna(row[f'MA{ma}']) and row[f'MA{ma}'] < row['open']
            ]
            if below_ma_pairs:
                # max 按均线值取最大，即“最靠近开盘价的下方均线”
                long_stop, long_stop_period = max(below_ma_pairs, key=lambda x: x[0])

        # ---- A.4 平仓优先级：开盘 → 盘中 ----
        # 第一优先级：开盘价已经跌破爆仓价 → 跳空爆仓
        if row['open'] <= liquidation_price:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "💥跳空爆倉"
            is_liquidated = True

        # 第二优先级：上一根收盘标记了“破位”，本周开盘平仓
        elif wait_for_breakdown_exit and ENABLE_BREAKDOWN_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "破位止損"

        # 第三优先级：上一根收盘标记了“死叉”，本周开盘平仓
        elif wait_for_reverse_exit and ENABLE_DEATH_CROSS_EXIT:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "死叉平倉"

        # 第四优先级：上一根收盘标记了“长上影”，本周开盘平仓
        elif wait_for_shadow_exit and ENABLE_LONG_UPPER_SHADOW_STOP:
            actual_sell = row['open'] * (1 - SLIPPAGE)
            exit_reason = "長上影止損"

        # 第五优先级：盘中触发（止损/爆仓/止盈）
        else:
            intraday_hits = []  # 收集本周盘中所有触发的价位

            # 跌破下方最近长线均线 → 止损
            if long_stop is not None and row['low'] <= long_stop:
                intraday_hits.append((long_stop, f"跌破MA{long_stop_period}止損", False))

            # 盘中跌破爆仓价 → 爆仓
            if row['low'] <= liquidation_price:
                intraday_hits.append((liquidation_price, "💥爆倉", True))

            if intraday_hits:
                # 如果同一周触发多个价位，取“最高价”那个先成交
                # 因为价格从高往低走，先碰到高的
                hit_price, hit_reason, hit_liq = max(intraday_hits, key=lambda x: x[0])
                # 爆仓按成交价结算，不再扣滑点；普通止损扣滑点
                actual_sell = hit_price if hit_liq else hit_price * (1 - SLIPPAGE)
                exit_reason = hit_reason
                is_liquidated = hit_liq

            # 盘中触及动态阻力位 → 止盈
            elif dynamic_resistance is not None and row['high'] >= dynamic_resistance:
                # 如果开盘已经高于阻力，按开盘价成交；否则按阻力价成交
                actual_sell = max(row['open'], dynamic_resistance) * (1 - SLIPPAGE)
                exit_reason = "動態阻力止盈"

        # ---- A.5 执行平仓结算 ----
        if exit_reason:
            # 多头盈亏 = (卖出价 - 开仓价) × 持仓数量
            profit = (actual_sell - entry_price) * position_size

            # 平仓手续费 = 持仓数量 × 卖出价 × 费率
            close_fee = position_size * actual_sell * FEE_RATE

            # 净盈亏 = 毛利 - 平仓手续费（开仓手续费已在开仓时扣除）
            net_pnl = profit - close_fee

            balance += net_pnl
            if balance < 0:
                balance = 0  # 账户余额最低为 0，不允许负数

            margin_used = current_trade['投入成本(保證金)']
            # 本单收益率 = 净盈亏 / 保证金 × 100%
            trade_return_pct = round((net_pnl / margin_used) * 100, 2) if margin_used > 0 else 0.0

            # 记录平仓这根 K 线的上影线比例（用于事后分析）
            if row['open'] > 0:
                close_upper_shadow_ratio = round(
                    (row['high'] - max(row['open'], row['close'])) / row['open'] * 100, 2
                )
            else:
                close_upper_shadow_ratio = None

            # 把平仓信息写回当前交易记录
            current_trade.update({
                '平倉時間': date_str,
                '平倉價格': round(actual_sell, 2),
                '平倉原因': exit_reason,
                '盈虧(USDT)': round(net_pnl, 2),
                '平倉後餘額': round(balance, 2),
                '本單收益率(%)': trade_return_pct,
                '持倉期最大浮虧(USDT)': round(current_max_loss_usdt, 2),
                '最大浮虧佔保證金(%)': round(current_max_loss_pct, 2),
                '平倉_上影線比例(%)': close_upper_shadow_ratio,
            })

            # 动态写入平仓时的所有均线值，方便复盘
            for ma in ALL_MA:
                current_trade[f'平倉_MA{ma}'] = (
                    round(row[f'MA{ma}'], 2) if not pd.isna(row[f'MA{ma}']) else None
                )

            trade_records.append(current_trade)  # 保存这笔交易

            # 重置持仓状态
            position_size = 0
            wait_for_reverse_exit = False
            wait_for_breakdown_exit = False
            wait_for_shadow_exit = False

            # 如果账户归零，回测提前终止
            if balance <= 0:
                print(f"❌ {date_str} 賬戶發生全倉爆倉，資金歸零，回測提前終止！")
                break
            continue  # 本周已平仓，不再判断开仓

        # ---- A.6 收盘后：标记下一根开盘要执行的平仓信号 ----
        # 注意：这些标记是“本周收盘确认，下一根周 K 开盘执行”

        # (1) 死叉标记：本周 MA10 跌破 MA21，且跌破幅度 >= 0.5%
        if (
                (row[f'MA{FAST_MA}'] < row[f'MA{SLOW_MA}'])
                and (df.iloc[i - 1][f'MA{FAST_MA}'] >= df.iloc[i - 1][f'MA{SLOW_MA}'])
        ):
            ma_diff_down = (
                                   row[f'MA{SLOW_MA}'] - row[f'MA{FAST_MA}']
                           ) / row[f'MA{SLOW_MA}']
            if ma_diff_down >= DEATH_CROSS_DISTANCE:
                wait_for_reverse_exit = True

        # (2) 破位标记：阴线且收盘跌破 MA10、MA21，同时 MA10 仍在 MA21 上方
        #     含义：多头排列被破坏，价格跌破均线
        if (
                row['close'] < row['open']
                and row['close'] < row[f'MA{FAST_MA}']
                and row['close'] < row[f'MA{SLOW_MA}']
                and row[f'MA{FAST_MA}'] > row[f'MA{SLOW_MA}']
        ):
            wait_for_breakdown_exit = True

        # (3) 破位标记：阴线且收盘跌破 MA10、MA21，同时 MA10 已在 MA21 下方
        #     含义：空头排列下的破位，同样平仓
        if (
                row['close'] < row['open']
                and row['close'] < row[f'MA{FAST_MA}']
                and row['close'] < row[f'MA{SLOW_MA}']
                and row[f'MA{FAST_MA}'] < row[f'MA{SLOW_MA}']
        ):
            wait_for_breakdown_exit = True

        # (4) 长上影阴线止损标记
        if ENABLE_LONG_UPPER_SHADOW_STOP:
            upper_shadow_price = row['high'] - max(row['open'], row['close'])
            upper_shadow_ratio = upper_shadow_price / row['open'] if row['open'] > 0 else 0.0
            is_bear_candle = row['close'] < row['open']

            # 如果要求必须是阴线，则 is_bear_candle 必须为 True
            # 且上影线比例 >= 20%
            if (
                    (not LONG_UPPER_SHADOW_REQUIRE_BEAR or is_bear_candle)
                    and upper_shadow_ratio >= LONG_UPPER_SHADOW_THRESHOLD
            ):
                wait_for_shadow_exit = True

    # =========================================================
    # B. 空倉狀態：尋找開倉機會
    # =========================================================
    if row['signal'] == 1 and position_size == 0:
        # 二次确认：本周必须是阳线才开仓
        # （signal 生成时已经要求 bullish_pattern，这里再保一道）
        if row['close'] > row['open']:
            # ---- B.1 计算保证金与仓位 ----
            margin_cost = balance * POSITION_SIZE_PCT  # 投入保证金 = 当前余额 × 33%
            trade_capital = margin_cost * LEVERAGE  # 仓位总价值 = 保证金 × 杠杆

            # ---- B.2 开仓价（含滑点）----
            entry_price = row['close'] * (1 + SLIPPAGE)  # 买入价上浮滑点
            position_size = trade_capital / entry_price  # 持仓数量 = 总价值 / 开仓价

            # ---- B.3 计算爆仓价 ----
            maintenance_margin = trade_capital * MMR  # 维持保证金
            # 允许亏损 = 当前余额 - 维持保证金 × 上限系数
            allowed_loss = balance - (maintenance_margin * UNI_MMR_LIMIT)
            # 爆仓价 = 开仓价 - 允许亏损 / 持仓数量
            liquidation_price = entry_price - (allowed_loss / position_size)

            # ---- B.4 扣除开仓手续费 ----
            open_fee = trade_capital * FEE_RATE
            balance -= open_fee

            # ---- B.5 重置本笔交易的浮亏记录与延迟平仓标记 ----
            current_max_loss_usdt = 0.0
            current_max_loss_pct = 0.0

            wait_for_reverse_exit = False
            wait_for_breakdown_exit = False
            wait_for_shadow_exit = False

            # ---- B.6 记录开仓信息 ----
            current_trade = {
                '開倉時間': date_str,
                '方向': '做多',
                '槓桿(倍)': int(LEVERAGE),
                '開倉價格': round(entry_price, 2),
                '投入成本(保證金)': round(margin_cost, 2),
                '倉位總價值': round(trade_capital, 2),
            }

# ================= 4.2 循環結束：若仍有持倉，按最後一根收盤價強平 =================
if position_size > 0:
    last_row = df.iloc[-1]
    actual_sell = last_row['close']  # 按最后收盘价卖出（这里没扣滑点）

    profit = (actual_sell - entry_price) * position_size
    close_fee = position_size * actual_sell * FEE_RATE
    net_pnl = profit - close_fee

    balance += net_pnl
    if balance < 0:
        balance = 0

    margin_used = current_trade['投入成本(保證金)']
    trade_return_pct = round((net_pnl / margin_used) * 100, 2) if margin_used > 0 else 0.0

    if last_row['open'] > 0:
        last_upper_shadow_ratio = round(
            (last_row['high'] - max(last_row['open'], last_row['close'])) / last_row['open'] * 100, 2
        )
    else:
        last_upper_shadow_ratio = None

    current_trade.update({
        '平倉時間': str(df.index[-1])[:10],
        '平倉價格': round(actual_sell, 2),
        '平倉原因': '回測結束強平',
        '盈虧(USDT)': round(net_pnl, 2),
        '平倉後餘額': round(balance, 2),
        '本單收益率(%)': trade_return_pct,
        '持倉期最大浮虧(USDT)': round(current_max_loss_usdt, 2),
        '最大浮虧佔保證金(%)': round(current_max_loss_pct, 2),
        '平倉_上影線比例(%)': last_upper_shadow_ratio,
    })

    for ma in ALL_MA:
        current_trade[f'平倉_MA{ma}'] = (
            round(last_row[f'MA{ma}'], 2) if not pd.isna(last_row[f'MA{ma}']) else None
        )

    trade_records.append(current_trade)

# ================= 5. 結果輸出與保存 =================
print("=" * 50)
print(f"初始資金: {INITIAL_CAPITAL:.2f} USDT")
print(f"最終資金: {balance:.2f} USDT")
print(f"總收益率: {((balance - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100):.2f}%")
print(f"總交易次數: {len(trade_records)} 筆")
print("=" * 50)

if len(trade_records) > 0:
    records_df = pd.DataFrame(trade_records)

    # 输出列顺序：开仓 → 平仓 → 盈亏 → 平仓均线 → 余额
    base_cols = [
        '開倉時間', '方向', '槓桿(倍)', '開倉價格', '投入成本(保證金)', '倉位總價值',
        '平倉時間', '平倉價格', '平倉原因', '盈虧(USDT)', '本單收益率(%)',
        '持倉期最大浮虧(USDT)', '最大浮虧佔保證金(%)', '平倉_上影線比例(%)',
    ]
    ma_cols = [f'平倉_MA{ma}' for ma in ALL_MA]
    cols = base_cols + ma_cols + ['平倉後餘額']
    records_df = records_df[cols]

    print("\n--- 完整交易記錄明細 ---")
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1200)
    print(records_df.to_string(index=False))

    csv_save_path = "trade_records_weekly.csv"
    records_df.to_csv(csv_save_path, index=False, encoding='utf-8-sig')
    print(f"\n📁 完整的交易記錄已保存為當前目錄下的: {csv_save_path}")
else:
    print("\n⚠️ 在週期內，沒有觸發任何符合條件的交易。")
