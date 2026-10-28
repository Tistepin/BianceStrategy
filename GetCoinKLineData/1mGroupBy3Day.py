import pandas as pd
import glob
import os

# ================= 路径配置 =================
SOURCE_DIR = r"F:\Python\BianceStrategy\re\BianceData\ETHUSDT\csvYear_All"
TARGET_FILE = r"F:\Python\BianceStrategy\re\BianceData\ETHUSDT\3d\ETHUSDT_futures_3d.csv"

os.makedirs(os.path.dirname(TARGET_FILE), exist_ok=True)

# ================= 1. 读取所有文件 =================
all_files = glob.glob(os.path.join(SOURCE_DIR, "ETHUSDT_*.csv"))
all_files.sort()

all_3d_dfs = []

for file in all_files:
    print(f"正在处理: {os.path.basename(file)}")
    df = pd.read_csv(file, usecols=["time", "open", "high", "low", "close", "volume"])
    df['time'] = pd.to_datetime(df['time'])

    # 减去 8 小时提取日期（这样 08:00 会被归为这一天的开始，而不是前一天的结束）
    df['date_only'] = (df['time'] - pd.Timedelta(hours=8)).dt.date

    # 先按天聚合，把 1m 变成日线
    daily_df = df.groupby('date_only').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).reset_index()

    daily_df['date_only'] = pd.to_datetime(daily_df['date_only'])
    year = daily_df['date_only'].dt.year.iloc[0]

    # ================= 2. 按年重置锚点 =================
    if year == 2019:
        anchor_date = pd.to_datetime('2019-09-10')  # 2019 年可按你的实际情况修改起点
        daily_df = daily_df[daily_df['date_only'] >= anchor_date].copy()
    else:
        anchor_date = pd.to_datetime(f'{year}-01-01') # 2020及以后，强行以 1月1日 为起点

    if len(daily_df) == 0:
        continue

    # ================= 3. 计算组号并生成 3日线 =================
    # 计算距离锚点的天数差，每 3 天分为一组
    daily_df['days_diff'] = (daily_df['date_only'] - anchor_date).dt.days
    daily_df['group_id'] = daily_df['days_diff'] // 3

    df_3d_year = daily_df.groupby('group_id').agg({
        'date_only': 'first',   # 取这一组的第一天
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).reset_index(drop=True)

    # 把日期加回 8 小时，变成标准的 K 线时间格式 (如 2019-12-30 08:00:00)
    df_3d_year['time'] = df_3d_year['date_only'] + pd.Timedelta(hours=8)
    df_3d_year = df_3d_year.drop(columns=['date_only'])

    all_3d_dfs.append(df_3d_year)

# ================= 4. 汇总并保存 =================
final_df = pd.concat(all_3d_dfs, ignore_index=True)
final_df = final_df[['time', 'open', 'high', 'low', 'close', 'volume']]
final_df.sort_values('time', inplace=True)
final_df.reset_index(drop=True, inplace=True)

final_df.to_csv(TARGET_FILE, index=False, encoding='utf-8-sig')

print(f"\n✅ 完美搞定！汇总文件已保存至：\n👉 {TARGET_FILE}")
print(f"3d 数据总条数：{len(final_df)}")

# ================= 5. 验证打印 =================
print("\n🔍 验证跨年数据（严格按年重置）：")
print("--- 2019 年的最后 2 根（只到 1月1日 8点前）---")
print(final_df[final_df['time'] < '2020-01-01'].tail(2).to_string(index=False))

print("\n--- 2020 年的第 1 根（从 1月1日 8点重新开始）---")
print(final_df[final_df['time'] >= '2020-01-01'].head(1).to_string(index=False))