import pandas as pd
import glob
import os

# ================= 1. 路径设置 =================
PARQUET_DIR = r"D:\Python\BianceStrategy\CryptoCoin_Futures\raw\klines\market=futures\symbol=BTCUSDT\interval=1m"
CSV_DIR = r"D:\Python\BianceStrategy\re\BianceData\csv"
OUTPUT_DIR = r"D:\Python\BianceStrategy\re\BianceData\csvYear_All"

os.makedirs(OUTPUT_DIR, exist_ok=True)
yearly_data = {}

# ================= 2. 读取 2019 年的 Parquet 数据 =================
print("正在查找并读取 Parquet 碎片数据...")
parquet_files = glob.glob(os.path.join(PARQUET_DIR, "**", "*.parquet"), recursive=True)

for file_path in parquet_files:
    try:
        parts = file_path.replace("\\", "/").split("/")
        year_idx = parts.index([p for p in parts if p.startswith("year=")][0])
        year = parts[year_idx].replace("year=", "")
    except:
        continue

    df = pd.read_parquet(file_path)
    if 'open_time' in df.columns:
        df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
        df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
    else:
        df = df.iloc[:, :6]
        df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']

    if year not in yearly_data:
        yearly_data[year] = []
    yearly_data[year].append(df)

# ================= 3. 读取 2020-2026 年的单月 CSV 数据 =================
print("正在查找并读取单月 CSV 数据...")
csv_files = glob.glob(os.path.join(CSV_DIR, "*.csv"))

for file_path in csv_files:
    filename = os.path.basename(file_path)
    try:
        year = filename.split('-')[2].split('.')[0]
    except:
        continue

    df = pd.read_csv(file_path, header=None)
    df = df.iloc[:, :6]
    df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']

    if year not in yearly_data:
        yearly_data[year] = []
    yearly_data[year].append(df)

# ================= 4. 按年合并、清洗、截取并保存 =================
print(f"\n读取完毕！一共找到了 {len(yearly_data)} 个年份的数据，开始处理...")

for year, dfs in sorted(yearly_data.items()):
    print(f"正在处理 {year} 年的数据...")

    df_year = pd.concat(dfs, ignore_index=True)

    # 清洗数值
    for col in ['time', 'open', 'high', 'low', 'close', 'volume']:
        df_year[col] = pd.to_numeric(df_year[col], errors='coerce')
    df_year = df_year.dropna()

    # 时间戳转换 (+8小时 变成北京时间)
    df_year['time'] = df_year['time'].astype('int64')
    if df_year['time'].astype(str).str.len().max() > 13:
        df_year['time'] = pd.to_datetime(df_year['time'], unit='us') + pd.Timedelta(hours=8)
    else:
        df_year['time'] = pd.to_datetime(df_year['time'], unit='ms') + pd.Timedelta(hours=8)

    # ================= 核心修改：精准截取到次年 08:00 前 =================
    year_int = int(year)
    start_date = f"{year_int}-01-01 00:00:00"
    end_date = f"{year_int + 1}-01-01 07:59:59"  # 截取到次年的 1月1日 08:00 前

    # 过滤
    df_year = df_year[(df_year['time'] >= start_date) & (df_year['time'] <= end_date)]
    # ====================================================================

    df_year = df_year.drop_duplicates(subset=['time']).sort_values('time')

    out_path = os.path.join(OUTPUT_DIR, f"BTCUSDT_{year}.csv")
    df_year.to_csv(out_path, index=False)

    # 打印最后一行的时间，让你直观看到它确实截取到了次年的早上 8 点前
    last_time = df_year.iloc[-1]['time']
    print(f"  ✅ 已保存: {out_path} (共 {len(df_year)} 根 K 线) -> 最后一根时间是: {last_time}")

print("\n🎉 所有 1 分钟数据已完美处理，严格对齐北京时间到次年 1月1日 08:00 前！")