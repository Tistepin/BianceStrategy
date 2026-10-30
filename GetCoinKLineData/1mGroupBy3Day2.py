import pandas as pd
import glob
import os
import traceback

# ================= 配置 =================
symbols_set = {
    # "SOL", "BNB", "XRP", "TRX", "ZEC", "HYPE", "DOGE", "LINK", "XLM", "ADA",
    # "UNI", "NEAR", "BCH", "DOT", "AVAX", "TAO", "ENA", "1000SHIB", "PUMP",
    # "QNT", "AAVE", "1000PEPE", "EVAA"
    "PUMP"
}

# 全局起始日：早于这个日期的数据全部丢弃（对所有年份、所有币种生效）
GLOBAL_START_DATE = '2025-07-12'

# 按年覆盖锚点：只影响指定年份，一般用不到，留空即可
# 如果真的想给某一年单独设锚点（而不是全局起点），才填这里
ANCHOR_OVERRIDE = {}

BASE_DIR = r"F:\Python\BianceStrategy\re\BianceData"


def get_anchor(year):
    """返回该年的分组锚点"""
    return pd.to_datetime(ANCHOR_OVERRIDE.get(year, f'{year}-01-01'))


def process_symbol(coin):
    """处理单个币种，返回 (coin, 条数, 信息)"""
    source_dir = os.path.join(BASE_DIR, f"{coin}USDT", "csvYear_All")
    target_file = os.path.join(BASE_DIR, f"{coin}USDT", "3d", f"{coin}USDT_futures_3d.csv")
    os.makedirs(os.path.dirname(target_file), exist_ok=True)

    all_files = glob.glob(os.path.join(source_dir, f"{coin}USDT_*.csv"))
    all_files.sort()
    if not all_files:
        return coin, 0, f"未找到源文件: {source_dir}"

    all_3d_dfs = []
    for file in all_files:
        df = pd.read_csv(file, usecols=["time", "open", "high", "low", "close", "volume"])
        df['time'] = pd.to_datetime(df['time'])

        # 减 8 小时提日期
        df['date_only'] = (df['time'] - pd.Timedelta(hours=8)).dt.date

        # 1m -> 日线
        daily_df = df.groupby('date_only').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).reset_index()
        daily_df['date_only'] = pd.to_datetime(daily_df['date_only'])
        if len(daily_df) == 0:
            continue

        year = daily_df['date_only'].dt.year.iloc[0]

        # ================= 按年重置锚点 =================
        anchor_date = get_anchor(year)
        if GLOBAL_START_DATE is not None:
            anchor_date = max(anchor_date, pd.to_datetime(GLOBAL_START_DATE))

        # 晚上线币种：数据首日明显晚于锚点（>3天），用数据首日做锚点，避免首组残缺
        year_first_day = daily_df['date_only'].min()
        if (year_first_day - anchor_date).days > 3:
            anchor_date = year_first_day

        daily_df = daily_df[daily_df['date_only'] >= anchor_date].copy()
        if len(daily_df) == 0:
            continue

        # ================= 分组 =================
        daily_df['days_diff'] = (daily_df['date_only'] - anchor_date).dt.days
        daily_df['group_id'] = daily_df['days_diff'] // 3

        df_3d_year = daily_df.groupby('group_id').agg({
            'date_only': 'first',
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index(drop=True)

        df_3d_year['time'] = df_3d_year['date_only'] + pd.Timedelta(hours=8)
        df_3d_year = df_3d_year.drop(columns=['date_only'])
        all_3d_dfs.append(df_3d_year)

    if not all_3d_dfs:
        return coin, 0, "无有效数据"

    final_df = pd.concat(all_3d_dfs, ignore_index=True)
    final_df = final_df[['time', 'open', 'high', 'low', 'close', 'volume']]
    final_df.sort_values('time', inplace=True)
    final_df.reset_index(drop=True, inplace=True)
    final_df.to_csv(target_file, index=False, encoding='utf-8-sig')
    return coin, len(final_df), "OK"


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