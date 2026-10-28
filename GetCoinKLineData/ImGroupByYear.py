import pandas as pd
import glob
import os


# ================= 路径配置 =================
# 币种前缀（用于输出命名）
COIN = "PUMP"
# 你的按月数据文件夹（根据你的截图，应该是这个路径）
SOURCE_DIR = rf"D:\Python\BianceStrategy\re\BianceData\{COIN}USDT\1m"
# 合并后按年保存的文件夹（模拟你图3的结构）
TARGET_DIR = rf"D:\Python\BianceStrategy\re\BianceData\{COIN}USDT\csvYear_All"

# 自动创建目标文件夹
os.makedirs(TARGET_DIR, exist_ok=True)



# ================= 1. 查找所有月份文件 =================
print(f"正在扫描文件夹：{SOURCE_DIR}")
# 匹配所有包含 ethusdt_1m_futures_ 的 csv 文件
all_files = glob.glob(os.path.join(SOURCE_DIR, f"{COIN}USDT_1m_futures_*.csv"))
all_files.sort()  # 按名字排序，确保时间顺序

if not all_files:
    print("❌ 未找到任何文件，请检查路径是否正确！")
    exit()

print(f"✅ 共找到 {len(all_files)} 个月度文件，开始合并...")

# ================= 2. 按年份分组读取并合并 =================
# 用字典暂存每年的 DataFrame 列表
yearly_dfs = {}

for file in all_files:
    file_name = os.path.basename(file)

    # 从文件名提取年份，例如从 "ETHUSDT_1m_futures_2019-11.csv" 提取 "2019"
    # 假设格式固定，用字符串切片或正则都可以
    try:
        year = file_name.split('_')[-1][:4]
    except Exception as e:
        print(f"跳过无法解析年份的文件: {file_name}")
        continue

    # 读取 CSV
    df = pd.read_csv(file)

    # ---- 数据清洗与列名对齐（适配你的图1回测代码） ----
    # 1. 把 'datetime' 改名为回测需要的 'time'
    if 'datetime' in df.columns:
        df = df.rename(columns={'datetime': 'time'})

    # 2. 只保留回测需要的核心列（可选，防止多余列影响回测速度）
    # 如果你需要 quote_volume 等其他指标，可以把它们加到这个列表里
    keep_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
    # 确保列存在才保留
    df = df[[c for c in keep_cols if c in df.columns]]

    # 放入对应年份的列表中
    if year not in yearly_dfs:
        yearly_dfs[year] = []
    yearly_dfs[year].append(df)
    print(f"  -> 已读取 {file_name} (年份: {year})")

# ================= 3. 合并各年数据并保存 =================
print("\n开始按年份合并并保存...")

for year, df_list in yearly_dfs.items():
    # 将该年所有月份的数据拼接到一起
    merged_df = pd.concat(df_list, ignore_index=True)

    # 去重（防止月份边界有重复数据）并按时间排序
    merged_df = merged_df.drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)

    # 将 time 列转回 datetime 格式（图1要求的是 datetime 格式）
    merged_df['time'] = pd.to_datetime(merged_df['time'])

    # 保存文件：例如 ETHUSDT_2019.csv
    out_file = os.path.join(TARGET_DIR, f"{COIN}USDT_{year}.csv")
    merged_df.to_csv(out_file, index=False, encoding='utf-8-sig')

    print(f"✨ [{year}年] 合并完成！总条数: {len(merged_df)} 条，已保存至: {out_file}")

print("\n🎉 所有年份数据合并完毕！你可以直接拿这些年份文件去跑你的回测代码了。")