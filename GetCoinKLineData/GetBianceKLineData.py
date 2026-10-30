import time
import random
import requests
import pandas as pd
import os
from datetime import datetime, timezone

# ===== 参数 =====
SYMBOL = "DOTUSDT"  # 币种
INTERVAL = "1m"  # 周期
BASE_URL = "https://fapi.binance.com"
URL = f"{BASE_URL}/fapi/v1/klines"
LIMIT = 1500

# 每次请求间隔（按月抓，请求量不大，0.2秒很安全）
SLEEP_BETWEEN_REQUESTS = 0.2
WEIGHT_WARN_RATIO = 0.8

# 路径参数配置
BASE_SAVE_DIR = r"D:\Python\BianceStrategy\re\BianceData"

# 设置起始时间（2019年11月27日）
START_YEAR = 2019
START_MONTH = 11
START_DAY = 27

# 计算当前时间，作为抓取的终点
NOW = datetime.now(timezone.utc)


def interval_to_ms(s: str) -> int:
    unit = s[-1]
    n = int(s[:-1])
    if unit == "m":
        return n * 60_000
    if unit == "h":
        return n * 3_600_000
    if unit == "d":
        return n * 86_400_000
    raise ValueError("暂不支持该周期")


def parse_retry_after(resp, default):
    ra = resp.headers.get("Retry-After")
    if not ra:
        return default
    ra = ra.strip()
    if ra.isdigit():
        return int(ra)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(ra)
        return max(1, int((dt - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        return default


def get_used_weight(resp):
    for k, v in resp.headers.items():
        if k.lower().startswith("x-mbx-used-weight-1m"):
            try:
                return int(v)
            except ValueError:
                return None
    return None


STEP_MS = interval_to_ms(INTERVAL)


def fetch_month_data(year, month, start_ms, end_ms):
    """抓取指定时间段的数据并返回 DataFrame"""
    all_rows = []
    start = start_ms
    consecutive_418 = 0

    while start < end_ms:
        params = {
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "startTime": start,
            "limit": LIMIT,
        }

        data = None
        for attempt in range(8):
            try:
                r = requests.get(URL, params=params, timeout=30)
            except Exception as e:
                wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                print(f"  [网络异常] {e}，{wait:.1f}s 后重试")
                time.sleep(wait)
                continue

            used = get_used_weight(r)
            if used is not None and used > 2400 * WEIGHT_WARN_RATIO:
                print(f"  [权重预警] 已用权重 {used}，主动降速 5s")
                time.sleep(5)

            if r.status_code == 418:
                consecutive_418 += 1
                base = parse_retry_after(r, default=120)
                wait = min(base * (2 ** (consecutive_418 - 1)), 3 * 24 * 3600)
                print(f"  [418 封禁] IP 已被封，等待 {wait}s")
                time.sleep(wait)
                continue

            if r.status_code == 429:
                wait = parse_retry_after(r, default=10)
                print(f"  [429 限频] 等待 {wait}s 后再试。")
                time.sleep(wait)
                continue

            if r.status_code in (500, 502, 503, 504):
                wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                print(f"  [HTTP {r.status_code}] 服务端错误，{wait:.1f}s 后重试")
                time.sleep(wait)
                continue

            if 400 <= r.status_code < 500:
                print(f"  [HTTP {r.status_code}] 请求错误，响应：{r.text[:200]}")
                raise RuntimeError("请求参数错误")

            try:
                data = r.json()
            except Exception:
                wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                print(f"  [解析失败] {wait:.1f}s 后重试")
                time.sleep(wait)
                continue

            consecutive_418 = 0
            break

        if data is None:
            raise RuntimeError("多次重试仍失败，当前月份抓取中断。")

        if not data:
            break

        all_rows.extend(data)

        last_open_time = data[-1][0]
        next_start = last_open_time + STEP_MS
        if next_start <= start:
            break

        start = next_start
        print(
            f"  已拉取 {len(all_rows)} 条，最新：{pd.to_datetime(last_open_time, unit='ms', utc=True).strftime('%Y-%m-%d %H:%M')}")
        time.sleep(SLEEP_BETWEEN_REQUESTS + random.uniform(0, 0.1))

    if not all_rows:
        return None

    # 整理数据
    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "count",
        "taker_buy_volume", "taker_buy_quote_volume", "ignore"
    ]
    df = pd.DataFrame(all_rows, columns=columns)
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)

    numeric_cols = [
        "open", "high", "low", "close", "volume",
        "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume"
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 时间转换（保留 UTC 和 北京时间）
    df["datetime_utc"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["datetime"] = df["datetime_utc"].dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)

    # 严格过滤掉超出本月范围的数据（API 可能多返回）
    df = df[df["open_time"] < end_ms]

    cols = ["datetime", "open_time", "datetime_utc"] + [c for c in df.columns if
                                                        c not in ["datetime", "open_time", "datetime_utc"]]
    return df[cols]


# ================= 主循环：逐月抓取 =================
def main():
    current_year = START_YEAR
    current_month = START_MONTH

    # 循环直到超过当前时间
    while True:
        # 计算这个月的起止时间
        month_start = datetime(current_year, current_month, 1, tzinfo=timezone.utc)

        # 如果是 2019 年 11 月，特殊处理起始日
        if current_year == 2019 and current_month == 11:
            month_start = datetime(2019, 11, 27, 0, 0, 0, tzinfo=timezone.utc)

        # 计算下个月 1 号作为结束时间
        if current_month == 12:
            next_month_start = datetime(current_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month_start = datetime(current_year, current_month + 1, 1, tzinfo=timezone.utc)

        # 如果这个月的起始时间已经超过当前时间，说明抓完了，退出
        if month_start >= NOW:
            print("所有历史数据已抓取完毕！")
            break

        # 如果下个月的时间超过了当前时间，就把结束时间截断到当前时间
        end_time = min(next_month_start, NOW)

        # 格式化月份字符串
        month_str = f"{current_year}-{current_month:02d}"
        print(f"\n[{month_str}] 开始抓取.{SYMBOL}. 范围：{month_start.strftime('%Y-%m-%d')} 到 {end_time.strftime('%Y-%m-%d')}")

        start_ms = int(month_start.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        # 抓取数据
        df = fetch_month_data(current_year, current_month, start_ms, end_ms)

        if df is not None and not df.empty:
            # 创建目录
            target_dir = os.path.join(BASE_SAVE_DIR, SYMBOL, INTERVAL)
            os.makedirs(target_dir, exist_ok=True)

            # 保存文件：ETHUSDT_1m_futures_2019-11.csv
            out_file = os.path.join(target_dir, f"{SYMBOL}_{INTERVAL}_futures_{month_str}.csv")
            df.to_csv(out_file, index=False, encoding="utf-8-sig")
            print(f"[{month_str}] 保存成功！总条数: {len(df)}，文件：{out_file}")
        else:
            print(f"[{month_str}] 无数据。")

        # 月份加 1
        if current_month == 12:
            current_year += 1
            current_month = 1
        else:
            current_month += 1


if __name__ == "__main__":
    symbols_set = { "SOL","BNB","XRP","TRX","ZEC","HYPE","DOGE","LINK","XLM","ADA","UNI","NEAR","BCH","DOT","TAO","ENA","SHIB","QNT",
                   "1000PEPE","EVAA"

                    }
    for symbol in symbols_set:
        SYMBOL=symbol+"USDT"
        main()
