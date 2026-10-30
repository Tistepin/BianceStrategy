import asyncio
import aiohttp
import random
import pandas as pd
import os
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ===== 全局参数 =====
INTERVAL = "1m"
BASE_URL = "https://fapi.binance.com"
URL = f"{BASE_URL}/fapi/v1/klines"
LIMIT = 1500

# 异步控制参数 (已优化，保证不封IP)
MAX_CONCURRENT_REQUESTS = 3  # 同时并发的最大币种数
SLEEP_BETWEEN_REQUESTS = 0.5  # 每次请求后的冷却时间
WEIGHT_WARN_RATIO = 0.8  # 权重预警阈值 (2400 * 0.8 = 1920)

# 路径参数配置
BASE_SAVE_DIR = r"D:\Python\BianceStrategy\re\BianceData"

# 设置起始时间（2019年11月27日）
START_YEAR = 2019
START_MONTH = 11
START_DAY = 27

NOW = datetime.now(timezone.utc)


def interval_to_ms(s: str) -> int:
    unit = s[-1]
    n = int(s[:-1])
    if unit == "m": return n * 60_000
    if unit == "h": return n * 3_600_000
    if unit == "d": return n * 86_400_000
    raise ValueError("暂不支持该周期")


def parse_retry_after(resp, default):
    ra = resp.headers.get("Retry-After")
    if not ra: return default
    ra = ra.strip()
    if ra.isdigit(): return int(ra)
    try:
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


# ================= 核心异步抓取函数（单月） =================
async def async_fetch_month_data(session, symbol, year, month, start_ms, end_ms, semaphore):
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
        async with semaphore:  # 限制并发数量
            for attempt in range(8):
                try:
                    async with session.get(URL, params=params, timeout=30) as r:
                        used = get_used_weight(r)
                        # 动态权重控制：越接近 2400，睡的时间越长，最高睡 15 秒
                        if used is not None and used > 2400 * WEIGHT_WARN_RATIO:
                            sleep_time = (used / 2400) * 15
                            print(f"[{symbol}] ⚠️ [权重预警] 已用权重 {used}，强制休眠 {sleep_time:.1f}s 降速...")
                            await asyncio.sleep(sleep_time)

                        if r.status == 418:
                            consecutive_418 += 1
                            base = parse_retry_after(r, default=120)
                            wait = min(base * (2 ** (consecutive_418 - 1)), 3 * 24 * 3600)
                            print(f"[{symbol}] 🚫 [418 封禁] IP 已被封，等待 {wait}s")
                            await asyncio.sleep(wait)
                            continue

                        if r.status == 429:
                            wait = parse_retry_after(r, default=10)
                            print(f"[{symbol}] 🛑 [429 限频] 等待 {wait}s 后再试。")
                            await asyncio.sleep(wait)
                            continue

                        if r.status in (500, 502, 503, 504):
                            wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                            print(f"[{symbol}] [HTTP {r.status}] 服务端错误，{wait:.1f}s 后重试")
                            await asyncio.sleep(wait)
                            continue

                        if 400 <= r.status < 500:
                            text = await r.text()
                            # 遇到不存在的交易对，直接抛出特定异常中断当前币种
                            if "-1121" in text:
                                raise ValueError("InvalidSymbol")
                            print(f"[{symbol}] [HTTP {r.status}] 请求错误，响应：{text[:200]}")
                            raise RuntimeError("请求参数错误")

                        try:
                            data = await r.json()
                        except Exception:
                            wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                            print(f"[{symbol}] [解析失败] {wait:.1f}s 后重试")
                            await asyncio.sleep(wait)
                            continue

                        consecutive_418 = 0
                        break  # 成功则跳出重试循环

                except asyncio.TimeoutError:
                    wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                    print(f"[{symbol}] ⏳ [网络超时] {wait:.1f}s 后重试")
                    await asyncio.sleep(wait)
                except aiohttp.ClientError as e:
                    wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                    print(f"[{symbol}] 🌐 [网络异常] {e}，{wait:.1f}s 后重试")
                    await asyncio.sleep(wait)

        if data is None:
            raise RuntimeError(f"[{symbol}] 多次重试仍失败，当前月份抓取中断。")

        if not data:
            break

        all_rows.extend(data)
        last_open_time = data[-1][0]
        next_start = last_open_time + STEP_MS
        if next_start <= start: break

        start = next_start
        # print(f"[{symbol}] 已拉取 {len(all_rows)} 条...") # 如果觉得刷屏可以注释掉这行

        # 请求间隔，释放信号量给其他协程
        await asyncio.sleep(SLEEP_BETWEEN_REQUESTS + random.uniform(0, 0.1))

    if not all_rows:
        return None

    # 整理数据 (这部分是 CPU 计算，直接同步执行)
    columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
               "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
    df = pd.DataFrame(all_rows, columns=columns)
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)

    numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume",
                    "taker_buy_quote_volume"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["datetime_utc"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["datetime"] = df["datetime_utc"].dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)

    # 严格过滤掉超出本月范围的数据
    df = df[df["open_time"] < end_ms]

    cols = ["datetime", "open_time", "datetime_utc"] + [c for c in df.columns if
                                                        c not in ["datetime", "open_time", "datetime_utc"]]
    return df[cols]


# ================= 单币种按月循环抓取 =================
async def fetch_symbol_data(session, symbol, semaphore):
    current_year = START_YEAR
    current_month = START_MONTH

    while True:
        month_start = datetime(current_year, current_month, 1, tzinfo=timezone.utc)
        if current_year == 2019 and current_month == 11:
            month_start = datetime(2019, 11, 27, 0, 0, 0, tzinfo=timezone.utc)

        if current_month == 12:
            next_month_start = datetime(current_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month_start = datetime(current_year, current_month + 1, 1, tzinfo=timezone.utc)

        if month_start >= NOW:
            print(f"[{symbol}] ✅ 所有历史数据已抓取完毕！")
            break

        end_time = min(next_month_start, NOW)
        month_str = f"{current_year}-{current_month:02d}"

        print(f"[{symbol}] 📥 开始抓取：{month_start.strftime('%Y-%m-%d')} 到 {end_time.strftime('%Y-%m-%d')}")

        start_ms = int(month_start.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        try:
            df = await async_fetch_month_data(session, symbol, current_year, current_month, start_ms, end_ms, semaphore)
        except ValueError as e:
            if str(e) == "InvalidSymbol":
                print(f"❌ [{symbol}] 币安不存在此交易对（或已下架），跳过该币种。")
                return  # 结束当前币种任务
            else:
                raise e
        except Exception as e:
            print(f"⚠️ [{symbol}] 抓取异常终止: {e}")
            return  # 遇到其他严重错误也跳过当前币种

        if df is not None and not df.empty:
            target_dir = os.path.join(BASE_SAVE_DIR, symbol, INTERVAL)
            os.makedirs(target_dir, exist_ok=True)
            out_file = os.path.join(target_dir, f"{symbol}_{INTERVAL}_futures_{month_str}.csv")
            df.to_csv(out_file, index=False, encoding="utf-8-sig")
            print(f"[{symbol}] 💾 [{month_str}] 保存成功！总条数: {len(df)}")
        else:
            print(f"[{symbol}] [{month_str}] 无数据。")

        if current_month == 12:
            current_year += 1
            current_month = 1
        else:
            current_month += 1


# ================= 主控调度 =================
async def main():
    # 注意：SHIB 已经改为 1000SHIB，HYPE/EVAA 如果报错会自动跳过
    symbols_set = {
        "SOL", "BNB", "XRP", "TRX", "ZEC", "HYPE", "DOGE", "LINK", "XLM", "ADA",
        "UNI", "NEAR", "BCH", "DOT", "TAO", "ENA", "1000SHIB", "QNT", "1000PEPE", "EVAA"
    }

    # 创建信号量，限制最大并发数
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    # 强制使用 IPv4 + 读取系统代理环境变量 (trust_env=True)
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
        tasks = []
        for symbol in symbols_set:
            full_symbol = symbol + "USDT"
            tasks.append(fetch_symbol_data(session, full_symbol, semaphore))

        print(f"🚀 总计启动 {len(tasks)} 个币种的异步抓取任务，最大并发数：{MAX_CONCURRENT_REQUESTS}")
        # 并发执行所有任务
        await asyncio.gather(*tasks)
        print("🎉 所有任务执行完毕！")


if __name__ == "__main__":
    asyncio.run(main())