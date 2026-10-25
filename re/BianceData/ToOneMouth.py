import pandas as pd
import glob
import os

# ================= 1. 路径设置 =================
INPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\csvYear_All"
OUTPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\1M"

os.makedirs(OUTPUT_DIR, exist_ok=True)

csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
print(f"找到 {len(csv_files)} 个年份文件，正在内存中读取并生成日线...")

all_daily_dfs = []

# ================= 2. 先将所有 1m 数据转为日线 =================
for file_path in csv_files:
    df = pd.read_csv(file_path)
    df['time'] = pd.to_datetime(df['time'])

    # 减去 8 小时提取日期（北京时间 08:00 切分日线）
    df['date_only'] = (df['time'] - pd.Timedelta(hours=8)).dt.date

    daily_df = df.groupby('date_only').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).reset_index()

    all_daily_dfs.append(daily_df)

df_all_daily = pd.concat(all_daily_dfs, ignore_index=True)
df_all_daily['date_only'] = pd.to_datetime(df_all_daily['date_only'])
df_all_daily = df_all_daily.drop_duplicates(subset=['date_only']).sort_values('date_only').reset_index(drop=True)

# ================= 3. 核心逻辑：按自然月切分 =================
# 提取年月作为分组依据（比如 2026-09）
df_all_daily['month_id'] = df_all_daily['date_only'].dt.to_period('M')

# 按 month_id 聚合生成月线
df_1m = df_all_daily.groupby('month_id').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).reset_index()

# ================= 4. 格式化时间并将 time 放到第一列 =================
# 把 month_id 转换为该月的第一天（比如 2026-09-01），并重命名为 time
df_1m['time'] = df_1m['month_id'].dt.strftime('%Y-%m-01')

# 强行重排列表顺序，把 time 放最前面
columns_order = ['time', 'open', 'high', 'low', 'close', 'volume']
df_1m = df_1m[columns_order]

# ================= 5. 按年份拆分并保存 =================
print("⏳ 正在按年份拆分保存 1月线文件...")
df_1m['year'] = df_1m['time'].str[:4]

for year, group in df_1m.groupby('year'):
    out_path = os.path.join(OUTPUT_DIR, f"BTCUSDT_1m_{year}.csv")
    group.drop(columns=['year']).to_csv(out_path, index=False)
    print(f"  ✅ 已保存: {out_path} (共 {len(group)} 根)")

# ================= 6. 验证打印 =================
print("\n🔍 验证 2019 年第一根月线数据（注意看 2019-09 的月线，开盘价应为 9月8日上线时的价格）：")
print(df_1m[df_1m['time'] == '2019-09-01'].to_string(index=False))