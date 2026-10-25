import pandas as pd
import glob
import os

# ================= 1. 路径设置 =================
INPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\csvYear_All"
OUTPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\1W"

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

# ================= 3. 核心逻辑：以 2019-09-02 为锚点切分自然周 =================
anchor_date = pd.to_datetime('2019-09-02')  # 这是一个周一
df_all_daily = df_all_daily[df_all_daily['date_only'] >= anchor_date].copy().reset_index(drop=True)

df_all_daily['days_diff'] = (df_all_daily['date_only'] - anchor_date).dt.days
df_all_daily['week_id'] = df_all_daily['days_diff'] // 7

# 按 week_id 聚合生成周线
df_1w = df_all_daily.groupby('week_id').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).reset_index()

# ================= 4. 还原真实的“周一”日期 =================
df_1w['time'] = anchor_date + pd.to_timedelta(df_1w['week_id'] * 7, unit='D')
df_1w['time'] = df_1w['time'].dt.strftime('%Y-%m-%d')

# ================= 5. 【关键修改】调整列的顺序，把 time 放到最前面 =================
# 重新指定列的顺序
columns_order = ['time', 'open', 'high', 'low', 'close', 'volume']
df_1w = df_1w[columns_order]

# 保存
print("⏳ 正在保存周线文件...")
df_1w['year'] = df_1w['time'].str[:4]
for year, group in df_1w.groupby('year'):
    out_path = os.path.join(OUTPUT_DIR, f"BTCUSDT_1w_{year}.csv")
    # 保存时剔除临时生成的 year 列
    group.drop(columns=['year']).to_csv(out_path, index=False)
    print(f"  ✅ 已保存: {out_path} (共 {len(group)} 根)")

# 验证打印
print("\n🔍 验证第一根周线数据（注意看 time 是不是在第一列）：")
print(df_1w.head(1).to_string(index=False))