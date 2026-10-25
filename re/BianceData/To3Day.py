import pandas as pd
import glob
import os

# ================= 1. 路径设置 =================
INPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\csvYear_All"
OUTPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\3D"

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

# 合并所有年份的日线并排序
df_all_daily = pd.concat(all_daily_dfs, ignore_index=True)
df_all_daily['date_only'] = pd.to_datetime(df_all_daily['date_only'])
df_all_daily = df_all_daily.drop_duplicates(subset=['date_only']).sort_values('date_only').reset_index(drop=True)

# 提取出年份，准备按年循环重置
df_all_daily['year'] = df_all_daily['date_only'].dt.year

# ================= 3. 按年重置周期，生成 3日线 =================
print("⏳ 正在按年份独立切分 3日线（每年重新收束）...")

all_3d_dfs = []

for year, df_year in df_all_daily.groupby('year'):
    # 确定该年的锚点（起点）
    if year == 2019:
        anchor_date = pd.to_datetime('2019-09-10')
        # 剔除 2019-09-10 之前的早期数据
        df_year = df_year[df_year['date_only'] >= anchor_date].copy()
    else:
        # 2020 及以后，每年 1月1日 为起点
        anchor_date = pd.to_datetime(f'{year}-01-01')

    if len(df_year) == 0:
        continue

    # 计算距离当年锚点的天数差，并计算 group_id
    df_year['days_diff'] = (df_year['date_only'] - anchor_date).dt.days
    df_year['group_id'] = df_year['days_diff'] // 3

    # 聚合该年的 3日线
    df_3d_year = df_year.groupby('group_id').agg({
        'date_only': 'first',  # 这一组的第一天作为 3日线的日期
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).reset_index(drop=True)

    all_3d_dfs.append(df_3d_year)

# 合并所有年份的 3日线结果
df_3d_final = pd.concat(all_3d_dfs, ignore_index=True)
df_3d_final = df_3d_final.rename(columns={'date_only': 'time'})
df_3d_final['time'] = df_3d_final['time'].dt.strftime('%Y-%m-%d')

# ================= 4. 拆分并保存到文件夹 =================
print("✅ 所有年份 3日线 切分完毕！正在按年份保存文件...")
df_3d_final['save_year'] = df_3d_final['time'].str[:4]

for save_year, group in df_3d_final.groupby('save_year'):
    out_path = os.path.join(OUTPUT_DIR, f"BTCUSDT_3d_{save_year}.csv")
    group.drop(columns=['save_year']).to_csv(out_path, index=False)
    print(f"  ✅ 已保存: {out_path} (共 {len(group)} 根)")

# ================= 5. 验证打印 =================
print("\n🔍 验证 2019 年第一根与最后一根（看是否在年底收束）：")
print(df_3d_final[df_3d_final['save_year'] == '2019'].head(1).to_string(index=False))
print(df_3d_final[df_3d_final['save_year'] == '2019'].tail(1).to_string(index=False))

print("\n🔍 验证 2020 年第一根（看是否从1月1日重新开始）：")
print(df_3d_final[df_3d_final['save_year'] == '2020'].head(1).to_string(index=False))