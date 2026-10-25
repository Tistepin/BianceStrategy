import os
import requests
import pandas as pd
import zipfile
import io

# ================= 1. 参数设置 =================
SYMBOL = "BTCUSDT"
TIMEFRAMES = ["1h"]  # 一次性下载 日线 和 3日线
START_YEAR = 2019  # 下载起始年份 (建议从2021年开始，包含牛市和熊市)
END_YEAR = 2027 # 下载结束年份

# 🚨 请确保这个路径是你想保存的位置 (注意路径前加 r)
SAVE_DIR = r"D:\Python\BianceStrategy\re"

# 代理设置 (如果你下载失败，取消下面两行的注释，并填入你的代理IP和端口)
# os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
# os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

# ================= 2. 核心下载逻辑 =================
os.makedirs(SAVE_DIR, exist_ok=True)

# 币安K线标准列名 (原始数据有12列，我们只需要前6列)
columns = ['time', 'open', 'high', 'low', 'close', 'volume',
           'close_time', 'quote_volume', 'count', 'taker_buy_volume',
           'taker_buy_quote_volume', 'ignore']

for tf in TIMEFRAMES:
    all_data = []
    print(f"\n🚀 开始下载 {SYMBOL} 的 {tf} 数据，年份: {START_YEAR} - {END_YEAR}")

    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 13):
            # 构建币安官方 URL
            file_name = f"{SYMBOL}-{tf}-{year}-{month:02d}.zip"
            url = f"https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{tf}/{file_name}"

            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    # 从内存解压
                    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                        csv_filename = z.namelist()[0]
                        with z.open(csv_filename) as f:
                            # 读取数据，忽略表头 (header=None)
                            df = pd.read_csv(f, header=None)

                            # 🛠️ 修复1：过滤掉可能混入的表头文字行 (open_time等)
                            # 只要第一列无法转为纯数字，就直接删掉这一行
                            df = df[pd.to_numeric(df[0], errors='coerce').notna()]

                            # 只取前 6 列 (时间, 开, 高, 低, 收, 量)
                            df = df.iloc[:, :6]
                            all_data.append(df)
                elif response.status_code == 404:
                    pass  # 某些月份可能真的没有数据，静默跳过
            except Exception as e:
                print(f"下载 {file_name} 失败: {e}")

    # ================= 3. 数据清洗与合并 =================
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        final_df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']

        # 🛠️ 修复2：强制转为数字类型，剔除所有不可转换的脏数据
        for col in ['time', 'open', 'high', 'low', 'close', 'volume']:
            final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

        final_df.dropna(inplace=True)  # 删除包含 NaN 的行

        # 🛠️ 修复3：解决超大整数溢出报错
        # 强制将 time 列转为 int64 格式，杜绝字符串解析
        final_df['time'] = final_df['time'].astype('int64')

        # 判断是毫秒(13位)还是微秒(16位)，并转换时间
        if final_df['time'].astype(str).str.len().max() > 13:
            final_df['time'] = pd.to_datetime(final_df['time'], unit='us')
        else:
            final_df['time'] = pd.to_datetime(final_df['time'], unit='ms')

        # 去重并按时间排序
        final_df.drop_duplicates(subset=['time'], inplace=True)
        final_df.sort_values('time', inplace=True)

        # 保存文件
        save_path = os.path.join(SAVE_DIR, f"{SYMBOL}_{tf}.csv")
        final_df.to_csv(save_path, index=False)

        print(f"✅ {tf} 数据下载完成！共 {len(final_df)} 根 K 线。已保存至: {save_path}")
    else:
        print(f"❌ 未能获取到 {tf} 数据。")

print("\n🎉 所有下载任务执行完毕！")