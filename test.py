import os
import requests
import pandas as pd
import zipfile
import io
from datetime import datetime

# ================= 1. 参数设置 =================
SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"  # 1分钟线
START_YEAR = 2020  # 起始年份
START_MONTH = 1  # 起始月份

# 🚨 目标存储根地址
BASE_SAVE_DIR = r"D:\Python\BianceStrategy\re\BianceData"
ZIP_SAVE_DIR = os.path.join(BASE_SAVE_DIR, "zip")
CSV_SAVE_DIR = os.path.join(BASE_SAVE_DIR, "csv")

# 代理设置 (如果下载失败，取消下面两行的注释，填入你的代理IP和端口)
# os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
# os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

# ================= 2. 动态计算结束时间 =================
now = datetime.now()
current_year = now.year
current_month = now.month

if current_month == 1:
    end_year = current_year - 1
    end_month = 12
else:
    end_year = current_year
    end_month = current_month - 1

print(f"==================================================")
print(f"🚀 开始下载 {SYMBOL} 合约 {TIMEFRAME} 数据")
print(f"📅 时间范围: {START_YEAR}-{START_MONTH:02d} 到 {end_year}-{end_month:02d}")
print(f"📁 ZIP保存路径: {ZIP_SAVE_DIR}")
print(f"📁 CSV保存路径: {CSV_SAVE_DIR}")
print(f"==================================================\n")

# 自动创建所有需要的文件夹
os.makedirs(ZIP_SAVE_DIR, exist_ok=True)
os.makedirs(CSV_SAVE_DIR, exist_ok=True)

all_data = []

# 循环年份和月份
for year in range(START_YEAR, end_year + 1):
    month_range = range(1, end_month + 1) if year == end_year else range(1, 13)

    for month in month_range:
        file_name = f"{SYMBOL}-{TIMEFRAME}-{year}-{month:02d}.zip"
        url = f"https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{TIMEFRAME}/{file_name}"

        # 定义当前的 zip 路径和 csv 路径
        zip_path = os.path.join(ZIP_SAVE_DIR, file_name)
        csv_filename = file_name.replace('.zip', '.csv')
        csv_path = os.path.join(CSV_SAVE_DIR, csv_filename)

        # 如果 csv 已经存在，说明之前下载过了，直接读取合并，跳过下载（断点续传功能）
        if os.path.exists(csv_path):
            print(f"已存在: {csv_filename} (跳过下载)")
            df = pd.read_csv(csv_path, header=None)
            all_data.append(df)
            continue

        print(f"正在下载: {file_name} ...", end=" ")

        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                # 1. 保存原始 ZIP 文件
                with open(zip_path, 'wb') as f_zip:
                    f_zip.write(response.content)

                # 2. 从内存解压并读取
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    internal_csv_name = z.namelist()[0]
                    with z.open(internal_csv_name) as f:
                        # 读取数据，忽略表头
                        df = pd.read_csv(f, header=None)

                        # 过滤表头文字行
                        df = df[pd.to_numeric(df[0], errors='coerce').notna()]

                        # 只取前 6 列 (时间, 开, 高, 低, 收, 量)
                        df = df.iloc[:, :6]

                        # 3. 将解压出来的单月数据保存为 CSV
                        df.to_csv(csv_path, index=False, header=False)

                        all_data.append(df)
                        print("✅ 成功")
            elif response.status_code == 404:
                print("⚠️ 文件不存在 (跳过)")
            else:
                print(f"❌ 失败 (状态码: {response.status_code})")
        except Exception as e:
            print(f"❌ 报错: {e}")

# ================= 3. 数据清洗与合并 =================
if all_data:
    print("\n正在合并和清洗所有数据...")
    final_df = pd.concat(all_data, ignore_index=True)
    final_df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']

    # 强制转为数字并清理
    for col in ['time', 'open', 'high', 'low', 'close', 'volume']:
        final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

    final_df.dropna(inplace=True)
    final_df['time'] = final_df['time'].astype('int64')

    # 处理时间戳 (毫秒转日期)
    if final_df['time'].astype(str).str.len().max() > 13:
        final_df['time'] = pd.to_datetime(final_df['time'], unit='us')
    else:
        final_df['time'] = pd.to_datetime(final_df['time'], unit='ms')

    final_df.drop_duplicates(subset=['time'], inplace=True)
    final_df.sort_values('time', inplace=True)

    # 保存大合并文件
    final_save_path = os.path.join(BASE_SAVE_DIR, f"{SYMBOL}_{TIMEFRAME}_all.csv")
    final_df.to_csv(final_save_path, index=False)

    print(f"\n✅ 数据下载、解压并合并完成！共 {len(final_df)} 根 K 线。")
    print(f"📁 合并后的总文件已保存至: {final_save_path}")
    print(f"📁 单月的 CSV 文件保存在: {CSV_SAVE_DIR}")
else:
    print("\n❌ 未能获取到任何数据，请检查网络或代理设置。")