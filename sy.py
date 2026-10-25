def xianhuo4():
    original_value = 9948.09 # 原始值
    new_value = 8794.49  # 新值

    # 计算差值
    difference = original_value - new_value

    # 计算跌幅百分比
    decline_percentage = (difference / original_value) * 100

    # 输出结果，保留指定的小数位数 (Java 的 %.3f 对应 Python 的 :.3f)
    print(f"原始值: {original_value:.3f}")
    print(f"新值:   {new_value:.3f}")
    print(f"下降值: {difference:.3f}")
    print(f"跌幅:   {decline_percentage:.2f}%")

    leverage = 25
    print(f"收益:   {decline_percentage * leverage:.2f}%")


# 调用函数
xianhuo4()