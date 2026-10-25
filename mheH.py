import pandas as pd
import os

# 你的数据所在目录
input_dir = r"D:\Python\BianceStrategy\re"
input_csv = os.path.join(input_dir, "BTCUSDT_futures_1m_all.csv")

print("正在读取 1 分钟数据...")
df = pd.read_csv(input_csv)

# 将时间列转为 datetime 类型，并设为索引
df['time'] = pd.to_datetime(df['time'])
df = df.set_index('time')

print("正在合成 1 天（1D）K 线...")
df_1d = df.resample(
    '1D',
    origin='epoch',
    label='left',
    closed='left'
).agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).dropna()

# 把索引变回普通列
df_1d = df_1d.reset_index()

# 🚨 核心：强制筛选并按照指定的列顺序排列
df_1d = df_1d[['time', 'open', 'high', 'low', 'close', 'volume']]

# 保存为 CSV
output_csv = os.path.join(input_dir, "BTCUSDT_futures_1d.csv")
df_1d.to_csv(output_csv, index=False)

print("=" * 50)
print(f"✅ 1D 数据合成成功！共 {len(df_1d)} 根日线。")
print(f"📅 时间范围：{df_1d['time'].min()} 到 {df_1d['time'].max()}")
print(f"📁 文件已保存至：{output_csv}")
print("=" * 50)