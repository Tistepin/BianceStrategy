import os
import pandas as pd

# 1. 设定基础路径
base_dir = r"D:\Python\BianceStrategy\re\BianceData"
output_dir = os.path.join(base_dir, "MergedData")

os.makedirs(output_dir, exist_ok=True)

# ================= 修改点 1：定义需要跳过的文件夹黑名单 =================
# 把你不需要处理的文件夹名字加到这里（包括合并输出的文件夹本身）
ignore_folders = ["MergedData", "csv", "csvYear_All"]
# ======================================================================

# 2. 遍历基础目录下的所有子文件夹
for folder_name in os.listdir(base_dir):
    folder_path = os.path.join(base_dir, folder_name)

    # ================= 修改点 2：遇到黑名单里的文件夹直接跳过 =================
    if os.path.isdir(folder_path) and folder_name not in ignore_folders:
        # ======================================================================

        # 获取该文件夹下所有的 csv 文件
        csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
        csv_files.sort()  # 按年份排序

        if not csv_files:
            continue

        print(f"正在合并 {folder_name} 文件夹下的数据...")

        df_list = []
        for file in csv_files:
            file_path = os.path.join(folder_path, file)
            df = pd.read_csv(file_path)
            df_list.append(df)

        # 纵向拼接
        merged_df = pd.concat(df_list, ignore_index=True)

        # 3. 命名逻辑
        first_file = csv_files[0]
        coin_name = first_file.replace("_", "-").split("-")[0]

        # 最终命名为：币种_文件夹名_merged.csv (例如: BTCUSDT_1D_merged.csv)
        output_filename = f"{coin_name}_{folder_name}_merged.csv"

        output_file_path = os.path.join(output_dir, output_filename)
        merged_df.to_csv(output_file_path, index=False)

        print(f"✅ {folder_name} 合并完成，已保存至: {output_file_path}，共 {len(merged_df)} 行数据。")

print("🎉 所有数据合并完毕！")