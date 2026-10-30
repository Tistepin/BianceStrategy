import time
import random
import requests
import pandas as pd
import os
from datetime import datetime, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import SSLError, ConnectionError as ReqConnectionError


# ===== 参数 =====
INTERVAL = "1m"
BASE_URL = "https://fapi.binance.com"
URL = f"{BASE_URL}/fapi/v1/klines"
LIMIT = 1500

SLEEP_BETWEEN_REQUESTS = 0.3
WEIGHT_WARN_RATIO = 0.8

BASE_SAVE_DIR = r"D:\Python\BianceStrategy\re\BianceData"

START_YEAR = 2019
START_MONTH = 1
START_DAY = 27

# 全局 Session，复用连接，减少 TLS 握手
SESSION = requests.Session()
RETRY_STRATEGY = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
ADAPTER = HTTPAdapter(max_retries=RETRY_STRATEGY, pool_connections=10, pool_maxsize=10)
SESSION.mount("https://", ADAPTER)
SESSION.mount("http://", ADAPTER)


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


def get_valid_futures_symbols():
    try:
        r = SESSION.get(f"{BASE_URL}/fapi/v1/exchangeInfo", timeout=30)
        r.raise_for_status()
        data = r.json()
        return {
            s["symbol"]
            for s in data["symbols"]
            if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"
        }
    except Exception as e:
        print(f"[校验] 获取有效符号列表失败：{e}，跳过校验")
        return None


def fetch_month_data(symbol, year, month, start_ms, end_ms):
    all_rows = []
    start = start_ms
    consecutive_418 = 0

    while start < end_ms:
        params = {
            "symbol": symbol,
            "interval": INTERVAL,
            "startTime": start,
            "limit": LIMIT,
        }

        data = None
        for attempt in range(8):
            try:
                r = SESSION.get(URL, params=params, timeout=30)
            except (SSLError, ReqConnectionError) as e:
                wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                print(f"  [SSL/连接异常] {e}，{wait:.1f}s 后重试")
                time.sleep(wait)
                continue
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

            if r.status_code == 400:
                raise RuntimeError(f"Invalid symbol {symbol}，响应：{r.text[:200]}")

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

    df["datetime_utc"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["datetime"] = df["datetime_utc"].dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)

    df = df[df["open_time"] < end_ms]

    cols = ["datetime", "open_time", "datetime_utc"] + [
        c for c in df.columns if c not in ["datetime", "open_time", "datetime_utc"]
    ]
    return df[cols]


def month_file_path(symbol, interval, year, month):
    target_dir = os.path.join(BASE_SAVE_DIR, symbol, interval)
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, f"{symbol}_{interval}_futures_{year}-{month:02d}.csv")


def month_file_ok(path):
    return os.path.exists(path) and os.path.getsize(path) > 100


def run_symbol(symbol):
    """抓取单个币种的全部历史数据，支持断点续抓"""
    now = datetime.now(timezone.utc)
    current_year = START_YEAR
    current_month = START_MONTH

    while True:
        if current_year == 2019 and current_month == 11:
            month_start = datetime(2019, 11, 27, 0, 0, 0, tzinfo=timezone.utc)
        else:
            month_start = datetime(current_year, current_month, 1, tzinfo=timezone.utc)

        if current_month == 12:
            next_month_start = datetime(current_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month_start = datetime(current_year, current_month + 1, 1, tzinfo=timezone.utc)

        if month_start >= now:
            print(f"[{symbol}] 所有历史数据已抓取完毕")
            break

        end_time = min(next_month_start, now)
        month_str = f"{current_year}-{current_month:02d}"

        out_file = month_file_path(symbol, INTERVAL, current_year, current_month)
        is_current_month = (next_month_start > now)

        if month_file_ok(out_file) and not is_current_month:
            print(f"[{month_str}] 已存在，跳过：{out_file}")
        else:
            print(f"\n[{month_str}] 开始抓取 {symbol}. 范围：{month_start.strftime('%Y-%m-%d')} 到 {end_time.strftime('%Y-%m-%d')}")
            start_ms = int(month_start.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)

            df = fetch_month_data(symbol, current_year, current_month, start_ms, end_ms)

            if df is not None and not df.empty:
                df.to_csv(out_file, index=False, encoding="utf-8-sig")
                print(f"[{month_str}] 保存成功！总条数: {len(df)}，文件：{out_file}")
            else:
                print(f"[{month_str}] 无数据。")

        if current_month == 12:
            current_year += 1
            current_month = 1
        else:
            current_month += 1


if __name__ == "__main__":
    symbols_set = {
        "SOL", "BNB", "XRP", "TRX", "ZEC", "DOGE", "LINK",
        "XLM", "ADA", "UNI", "NEAR", "BCH", "DOT", "TAO", "ENA",
        "1000SHIB", "QNT", "1000PEPE"
    }

    valid_symbols = get_valid_futures_symbols()
    if valid_symbols:
        print(f"Binance Futures 当前有效永续合约共 {len(valid_symbols)} 个")

    for base_symbol in symbols_set:
        full_symbol = base_symbol + "USDT"

        if valid_symbols and full_symbol not in valid_symbols:
            print(f"\n跳过 {full_symbol}：不是 Binance Futures 有效永续合约")
            continue

        print(f"\n========== 开始处理 {full_symbol} ==========")
        try:
            run_symbol(full_symbol)
        except Exception as e:
            print(f"{full_symbol} 抓取失败：{e}")
            print("继续下一个币种...")
            continue