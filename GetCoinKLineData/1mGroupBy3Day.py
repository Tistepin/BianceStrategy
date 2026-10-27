import pandas as pd
import glob
import os

# ================= 路径配置 =================
# 你的按年划分的 1m 数据文件夹（请根据实际情况修改）
SOURCE_DIR = r"D:\Python\BianceStrategy\re\BianceData\ETHUSDT\csvYear_All"

# 最终生成的 3d 文件的保存路径
TARGET_FILE = r"D:\Python\BianceStrategy\re\BianceData\ETHUSDT\3d\ETHUSDT_futures_3d.csv"

# ================= 1. 寻找并合并所有 1m 文件 =================
print("正在寻找本地的 1m 数据文件...")
# 匹配类似 ETHUSDT_2019.csv, ETHUSDT_2020.csv
all_files = glob.glob(os.path.join(SOURCE_DIR, "ETHUSDT_*.csv"))
all_files.sort()

if not all_files:
    print("❌ 没找到任何文件，请检查 SOURCE_DIR 路径是否正确！")
    exit()

print(f"找到 {len(all_files)} 个文件，开始合并...")
df_list = []
for file in all_files:
    print(f"正在读取: {os.path.basename(file)}")
    # 只读取需要的列，加快速度
    temp_df = pd.read_csv(file, usecols=["time", "open", "high", "low", "close", "volume"])
    df_list.append(temp_df)

# 合并成一个大 DataFrame
df = pd.concat(df_list, ignore_index=True)

# ================= 2. 数据预处理 =================
print("正在进行数据清洗和时间对齐...")
df['time'] = pd.to_datetime(df['time'])
# 去重、按时间排序并设为索引
df = df.drop_duplicates(subset=['time']).sort_values('time').set_index('time')

# ================= 3. 核心：合成 3日线 =================
print("正在合成 3d K线（按北京时间 08:00 切分）...")
agg_dict = {
    'open': 'first',    # 3天内的第一个开盘价
    'high': 'max',      # 3天内的最高价
    'low': 'min',       # 3天内的最低价
    'close': 'last',    # 3天内的最后一个收盘价
    'volume': 'sum'     # 3天内的总成交量
}

# offset='8h' 确保每根 3日线都是从北京时间早上 08:00 开始
df_3d = df.resample('3D', offset='8h').agg(agg_dict).dropna()

# 重置索引，变成回测需要的格式
df_3d = df_3d.reset_index()

# ================= 4. 保存文件 =================
df_3d.to_csv(TARGET_FILE, index=False, encoding='utf-8-sig')

print(f"\n✅ 完美搞定！")
print(f"1m 数据总条数：{len(df)}")
print(f"3d 数据总条数：{len(df_3d)}")
print(f"文件已保存至：{TARGET_FILE}")
print("\n--- 最终 3d 数据预览 ---")
print(df_3d.head(3))
print("...")
print(df_3d.tail(3))