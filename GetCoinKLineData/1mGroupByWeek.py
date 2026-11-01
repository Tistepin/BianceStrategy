import pandas as pd
import glob
import os
import traceback

# ================= 配置 =================
symbols_set = {
    "AVAX"
}

# 全局起始日：早于这个日期的数据全部丢弃
GLOBAL_START_DATE = '2020-9-21'

BASE_DIR = r"D:\Python\BianceStrategy\re\BianceData"


def process_symbol(coin):
    """处理单个币种，聚合成周线，返回 (coin, 条数, 信息)"""
    source_dir = os.path.join(BASE_DIR, f"{coin}USDT", "csvYear_All")
    target_file = os.path.join(BASE_DIR, f"{coin}USDT", "1w", f"{coin}USDT_futures_1w.csv")
    os.makedirs(os.path.dirname(target_file), exist_ok=True)

    all_files = glob.glob(os.path.join(source_dir, f"{coin}USDT_*.csv"))
    all_files.sort()
    if not all_files:
        return coin, 0, f"未找到源文件: {source_dir}"

    # ========= 第一步：每个文件 1m -> 日线，先全部收集 =========
    daily_dfs = []
    for file in all_files:
        df = pd.read_csv(file, usecols=["time", "open", "high", "low", "close", "volume"])
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time')

        # 提日期（保持与原代码一致的时区约定）
        df['date_only'] = (df['time'] - pd.Timedelta(hours=8)).dt.date

        daily = df.groupby('date_only').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()

        if len(daily) == 0:
            continue

        daily['date_only'] = pd.to_datetime(daily['date_only'])
        daily_dfs.append(daily)

    if not daily_dfs:
        return coin, 0, "无有效数据"

    # ========= 第二步：合并所有日线，统一处理跨年/跨文件 =========
    daily_df = pd.concat(daily_dfs, ignore_index=True)
    daily_df = daily_df.sort_values('date_only')
    # 防御：同一日期只保留最后一条
    daily_df = daily_df.drop_duplicates(subset='date_only', keep='last').reset_index(drop=True)

    # 全局起始日过滤
    if GLOBAL_START_DATE is not None:
        daily_df = daily_df[daily_df['date_only'] >= pd.to_datetime(GLOBAL_START_DATE)].copy()
    if len(daily_df) == 0:
        return coin, 0, "起始日过滤后无数据"

    # ========= 第三步：按自然周分组（周一为周起点） =========
    # weekday: 0=周一, 6=周日；减去 weekday 天得到本周周一
    daily_df['week_start'] = (
        daily_df['date_only']
        - pd.to_timedelta(daily_df['date_only'].dt.weekday, unit='D')
    )

    weekly_df = daily_df.groupby('week_start').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).reset_index()

    # 输出时间：周一 00:00 + 8h（与原 3d 代码约定一致）
    weekly_df['time'] = weekly_df['week_start'] + pd.Timedelta(hours=8)
    weekly_df = weekly_df[['time', 'open', 'high', 'low', 'close', 'volume']]
    weekly_df.sort_values('time', inplace=True)
    weekly_df.reset_index(drop=True, inplace=True)

    weekly_df.to_csv(target_file, index=False, encoding='utf-8-sig')
    return coin, len(weekly_df), "OK"


# ================= 主循环 =================
results = []
for coin in sorted(symbols_set):
    print(f"\n{'=' * 60}\n▶ 处理 {coin}")
    try:
        c, n, msg = process_symbol(coin)
        results.append((c, n, msg))
        print(f"  ✅ {c}: {n} 条 | {msg}")
    except Exception as e:
        results.append((coin, 0, f"ERROR: {e}"))
        print(f"  ❌ {coin} 失败: {e}")
        traceback.print_exc()

# ================= 汇总 =================
print(f"\n{'=' * 60}\n📊 汇总")
ok = fail = 0
for c, n, msg in results:
    if n > 0:
        ok += 1
        print(f"  ✅ {c:<12} {n:>7} 条")
    else:
        fail += 1
        print(f"  ❌ {c:<12} {n:>7} 条  {msg}")

print(f"\n成功 {ok} 个，失败/空 {fail} 个，共 {len(results)} 个")