import pandas as pd
import numpy as np

# ======================================================================
# 参数区
# 所有可调阈值集中在这里，后面扫描参数只改这一段
# ======================================================================
CoinName = "BTC"
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

# -------- 开单必须条件---------
# 每次开单必须检测 k线的形态
# 阴线收盘价贴近最低点，距离最低点<CLOSE_TO_LOW_TH% 才算可以开单的阴线
CLOSE_TO_LOW_TH = 0.04           # 收盘距最低点 <4%，才算“收在最低附近”
# 并且 下影太长不做
ENTITY_TO_LOWER_MIN_RATIO = 1    # 阴线实体幅度 / 下影线幅度 >= 1，下影太长不做

MA_ALL_LIST = [10, 21, 99, 120, 180, 365]

# ======================================================================
# 读取数据 & 计算均线
# ======================================================================
# 收集数据
df = pd.read_csv(CSV_PATH)
# 强转 时间
df["time"] = pd.to_datetime(df["time"])
# 排序 将数据框 df 按照 "time" 列的时间先后顺序进行排序，并且将排序后被打乱的行号（索引）重新重置为从 0 开始的连续数字，最后覆盖更新原来的 df
df = df.sort_values("time").reset_index(drop=True)


# 计算 SMA 均线，按收盘价 close
for p in MA_ALL_LIST:
    df[f"ma{p}"] = df["close"].rolling(p).mean()



# ======================================================================
# 辅助列
# 把信号判断要用到的中间变量提前算好，避免在信号函数里重复计算
# ======================================================================

# 计算这根k线是阴线还阳线
df["is_bear"] = df["close"] < df["open"]   # 阴线
df["is_bull"] = df["close"] > df["open"]   # 阳线

# 收盘距最低点幅度，A 公式：(close-low)/close
df["close_to_low"] = (df["close"] - df["low"]) / df["close"]

# 阴线实体幅度
df["entity_pct"] = (df["open"] - df["close"]) / df["open"]

# 下影线幅度
df["lower_shadow_pct"] = (df["close"] - df["low"]) / df["close"]