import requests
import pandas as pd


def get_first_complete_3d_kline(symbol: str):
    """
    获取币安USDT合约指定交易对的第一个“完整”3日K线。
    即跳过上线时的残缺K线，获取第一个严格对齐周期的K线。
    """
    url = "https://fapi.binance.com/fapi/v1/klines"

    params = {
        "symbol": symbol.upper(),
        "interval": "3d",
        "startTime": 0,
        "limit": 2,  # 获取前两根K线
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if len(data) < 2:
            print(f"返回数据不足，可能 {symbol} 上线时间太短。")
            return None

        # 取第二根K线，即第一个完整的3日线
        complete_kline = data[1]

        columns = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ]
        df = pd.DataFrame([complete_kline], columns=columns)

        # 将时间戳转换为UTC+8的可读时间
        df['open_time_utc8'] = pd.to_datetime(df['open_time'], unit='ms') + pd.Timedelta(hours=8)
        df['close_time_utc8'] = pd.to_datetime(df['close_time'], unit='ms') + pd.Timedelta(hours=8)

        # 类型转换
        numeric_cols = ['open', 'high', 'low', 'close', 'volume',
                        'quote_asset_volume', 'taker_buy_base_asset_volume',
                        'taker_buy_quote_asset_volume']
        df[numeric_cols] = df[numeric_cols].astype(float)
        df['number_of_trades'] = df['number_of_trades'].astype(int)

        df = df[['open_time_utc8', 'open', 'high', 'low', 'close', 'volume',
                 'close_time_utc8', 'quote_asset_volume', 'number_of_trades']]

        return df

    except Exception as e:
        print(f"请求或解析出错: {e}")
        return None


# --- 使用示例 ---
if __name__ == "__main__":
    symbol = "SOLUSDT"
    complete_kline_df = get_first_complete_3d_kline(symbol)

    if complete_kline_df is not None:
        print(f"=== {symbol} 的第一根完整3日线 (UTC+8) ===")
        print(complete_kline_df.to_string())