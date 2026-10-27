import pandas as pd
import glob
import os

# ================= 路径配置 =================
# 输入：存放 1m 数据的文件夹（假设你之前合并好的按年文件在这里，或者按月也行）
# 这里我们直接读取全量的 1m 数据统一合成，防止年份交界处断线
SOURCE_DIR = r"D:\Python\BianceStrategy\re\BianceData\ETHUSDT\1m"

# 输出：保存 3日线 的文件夹
TARGET_DIR = r"D:\Python\BianceStrategy\re\BianceData\ETHUSDT\3d"
os.makedirs(TARGET_DIR, exist_ok=True)

COIN = "ETHUSDT"

# ================= 1. 读取所有 1m 数据 =================
print("正在读取所有 1m 数据文件...")
# 匹配你按月份抓取的所有文件
all_files = glob.glob(os.path.join(SOURCE_DIR, f"{COIN}_1m_futures_*.csv"))
all_files.sort()

if not all_files:
    print("❌ 未找到 1m 数据文件！")
    exit()

df_list = []
for file in all_files:
    temp_df = pd.read_csv(file)
    df_list.append(temp_df)

# 合并成一个大 DataFrame
print("正在合并数据...")
df = pd.concat(df_list, ignore_index=True)

# ================= 2. 数据预处理 =================
# 确保 time 列是 datetime 类型，并设为索引（resample 必须用时间做索引）
df['time'] = pd.to_datetime(df['time'])
df = df.drop_duplicates(subset=['time']).sort_values('time').set_index('time')

# ================= 3. 核心：合成 3日线 =================
print("正在合成 3日线...")

# 定义聚合规则（OHLCV）
agg_dict = {
    'open': 'first',    # 3天内第一根1m K线的开盘价
    'high': 'max',      # 3天内最高价
    'low': 'min',       # 3天内最低价
    'close': 'last',    # 3天内最后一根1m K线的收盘价
    'volume': 'sum'     # 3天内总成交量
}

# 执行 Resample
# '3D' 表示 3天；offset='8h' 非常关键！它让 3日线的切分点落在北京时间早上 08:00（对应 UTC 0点）
df_3d = df.resample('3D', offset='8h').agg(agg_dict)

# 因为有些 3天里可能全是没有成交量的死盘，会产生 NaN，直接删掉
df_3d = df_3d.dropna()

# 把索引恢复成普通列，并改名为 'time'，适配你的回测代码
df_3d = df_3d.reset_index()

# ================= 4. 保存文件 =================
out_file = os.path.join(TARGET_DIR, f"{COIN}_futures_3d.csv")
df_3d.to_csv(out_file, index=False, encoding='utf-8-sig')

print(f"\n🎉 合成完毕！")
print(f"1m 数据总条数：{len(df)}")
print(f"3d 数据总条数：{len(df_3d)}")
print(f"文件已保存至：{out_file}")
print("\n--- 数据前 3 行预览 ---")
print(df_3d.head(3))