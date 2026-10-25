import pandas as pd
import glob
import os

# ================= 1. 路径设置 =================
INPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\csvYear_All"
OUTPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\3M"

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

# ================= 3. 核心逻辑：按季度切分 =================
# 提取季度作为分组依据（比如 2019Q1, 2019Q2 等）
df_all_daily['quarter_id'] = df_all_daily['date_only'].dt.to_period('Q')

# 按 quarter_id 聚合生成季度线
df_3m = df_all_daily.groupby('quarter_id').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).reset_index()

# ================= 4. 格式化时间并将 time 放到第一列 =================
# 将季度转换为该季度的第一天（比如 2019Q3 变成 2019-07-01）
df_3m['time'] = df_3m['quarter_id'].dt.start_time.dt.strftime('%Y-%m-%d')

# 强行重排列表顺序，把 time 放最前面
columns_order = ['time', 'open', 'high', 'low', 'close', 'volume']
df_3m = df_3m[columns_order]

# ================= 5. 按年份拆分并保存 =================
print("⏳ 正在按年份拆分保存 季度线文件...")
df_3m['year'] = df_3m['time'].str[:4]

for year, group in df_3m.groupby('year'):
    out_path = os.path.join(OUTPUT_DIR, f"BTCUSDT_3m_{year}.csv")
    group.drop(columns=['year']).to_csv(out_path, index=False)
    print(f"  ✅ 已保存: {out_path} (共 {len(group)} 根)")

# ================= 6. 验证打印 =================
print("\n🔍 验证 2019 年第三季度 (2019Q3) 的数据：")
print(df_3m[df_3m['time'] == '2019-07-01'].to_string(index=False))
print("\n🔍 验证 2019 年第四季度 (2019Q4) 的数据：")
print(df_3m[df_3m['time'] == '2019-10-01'].to_string(index=False))