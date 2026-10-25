import pandas as pd
import glob
import os

# ================= 1. 路径设置 =================
INPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\csvYear_All"
OUTPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\1D"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# 获取所有按年的 1m 纯净数据
csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
print(f"找到 {len(csv_files)} 个年份文件，开始聚合 1日线...\n")

for file_path in csv_files:
    filename = os.path.basename(file_path)
    try:
        year = filename.split('_')[1].split('.')[0]
    except IndexError:
        continue

    print(f"⏳ 正在处理: {filename}")

    # 1. 读取数据，确保 time 列是 datetime 格式
    df = pd.read_csv(file_path)
    df['time'] = pd.to_datetime(df['time'])

    # ================= 2. 核心逻辑：时间平移 =================
    # 因为数据本身已经是北京时间，而币安日线以早上 08:00 为界
    # 所以将时间减去 8 小时，原本次日的 00:00-07:59 就会变成当天的 16:00-23:59
    df['date_adjusted'] = df['time'] - pd.Timedelta(hours=8)
    df['date_only'] = df['date_adjusted'].dt.date

    # ================= 3. 聚合成 1日线 =================
    daily_df = df.groupby('date_only').agg({
        'open': 'first',  # 当天第一条 1m 的开盘价
        'high': 'max',  # 当天最高的 high
        'low': 'min',  # 当天最低的 low
        'close': 'last',  # 当天最后一条 1m 的收盘价
        'volume': 'sum'  # 当天成交量累加
    }).reset_index()

    # ================= 4. 格式化与保存 =================
    # 把 date_only 改名回 time，并转为纯日期字符串
    daily_df = daily_df.rename(columns={'date_only': 'time'})
    daily_df['time'] = pd.to_datetime(daily_df['time']).dt.strftime('%Y-%m-%d')

    # 保存文件
    out_path = os.path.join(OUTPUT_DIR, f"BTCUSDT_1d_{year}.csv")
    daily_df.to_csv(out_path, index=False)

    print(f"  ✅ 已生成日线: {out_path} (共 {len(daily_df)} 天)\n")

print("🎉 所有的 1日线 均已聚合完毕！")