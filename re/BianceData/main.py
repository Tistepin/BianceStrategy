# 先要有 每年的1分钟数据集合k线 然后执行 转化为 你想要的k线 比如1日线 3日线 周线等

import subprocess
import sys
import os

# 获取当前 main.py 所在的绝对路径，确保无论在哪里运行，相对路径都不出错
current_dir = os.path.dirname(os.path.abspath(__file__))

# 1. 按照逻辑顺序定义需要执行的脚本列表
# (1) 先处理基础数据合并
# (2) 再基于 1m 数据转化为其他周期
scripts_to_run = [
    "merge_by_year.py",  # 先合并按年的基础数据
    "ToOneDay.py",  # 转换为 1日线
    "To3Day.py",  # 转换为 3日线
    "ToOneWeek.py",  # 转换为 1周线
    "ToOneMouth.py",  # 转换为 1月线
    "To3Mouth.py",  # 转换为 3月线

    "merge_csv.py",  # 执行其他 CSV 合并逻辑
]

print("🚀 开始执行数据处理流水线...\n" + "=" * 40)

for script in scripts_to_run:
    script_path = os.path.join(current_dir, script)

    if not os.path.exists(script_path):
        print(f"⚠️ 找不到脚本: {script}，已跳过。")
        continue

    print(f"\n▶️ 正在执行: {script} ...")

    try:
        # 使用 sys.executable 确保使用的是当前环境的 Python 解释器
        # check=True 表示如果脚本报错，会抛出异常并停止后续执行
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=current_dir,  # 确保脚本内部的相对路径正确
            check=True,
            text=True  # 捕获输出为字符串（可选）
        )
        print(f"✅ {script} 执行成功！")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ 严重错误: {script} 执行失败！")
        print("流水线已中断，请检查该脚本的具体报错信息。")
        sys.exit(1)  # 终止整个程序

print("\n" + "=" * 40)
print("🎉 所有任务已按顺序执行完毕！")
