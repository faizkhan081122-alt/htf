import os
import time
import requests
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

from dotenv import load_dotenv
load_dotenv()  # load .env variables
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in env variables")


# Binance Futures client (public data only, no API key needed)
client = Client()

# HTF Settings
HTF_INTERVAL = "15m"
ATR_PERIOD = 14

# Coin tracking
active_positions = {}  # symbol: {"side": "BUY"/"SELL", "tp": price, "sl": price}

# ================= TELEGRAM FUNCTION =================
def send_telegram(symbol, signal, price, tp, sl, retries=3, delay=2):
    emoji = "🟢" if signal == "BUY" else "🔴"
    msg = f"{emoji} {symbol} NEW {signal} signal\nEntry: {price:.4f}\nTP: ±{tp:.4f} | SL: ±{sl:.4f}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    
    for attempt in range(retries):
        try:
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                print(f"Telegram sent: {symbol} {signal}")
                return
            else:
                print(f"Telegram failed ({response.status_code}): {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Telegram send failed, retry {attempt+1}/{retries}: {e}")
        time.sleep(delay)

# ================= HELPER FUNCTIONS =================
def get_top_futures_pairs(limit=50):
    info = client.futures_exchange_info()
    symbols = [s['symbol'] for s in info['symbols'] if s['quoteAsset'] == 'USDT' and s['contractType']=='PERPETUAL']
    return symbols[:limit]

def fetch_klines(symbol, interval, limit=20):
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            "open_time","open","high","low","close","volume","close_time","quote_asset_volume",
            "number_of_trades","taker_buy_base","taker_buy_quote","ignore"
        ])
        df = df.astype({"open":"float","high":"float","low":"float","close":"float","volume":"float"})
        return df
    except BinanceAPIException as e:
        print(f"Klines fetch error for {symbol}: {e}")
        return None
    except Exception as e:
        print(f"Unknown error fetching {symbol}: {e}")
        return None

def calculate_atr(df, period=ATR_PERIOD):
    df['H-L'] = df['high'] - df['low']
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L','H-PC','L-PC']].max(axis=1)
    atr = df['TR'].rolling(period).mean().iloc[-1]
    return atr

# ================= HTF SIGNAL LOGIC =================
def check_htf_signal(symbol):
    df = fetch_klines(symbol, HTF_INTERVAL, limit=20)
    if df is None or df.empty:
        return None
    open_htf = df['open'].iloc[-1]
    close_htf = df['close'].iloc[-1]
    high_htf = df['high'].iloc[-1]
    low_htf = df['low'].iloc[-1]
    body = abs(close_htf - open_htf)
    avg_body = df['close'].diff().abs().rolling(10).mean().iloc[-1]
    is_bull = (close_htf > open_htf) and (body > avg_body*1.1)
    is_bear = (close_htf < open_htf) and (body > avg_body*1.1)
    atr = calculate_atr(df)
    tp = close_htf + 2*atr if is_bull else close_htf - 2*atr
    sl = close_htf - 1*atr if is_bull else close_htf + 1*atr
    if is_bull:
        return "BUY", close_htf, tp, sl
    elif is_bear:
        return "SELL", close_htf, tp, sl
    return None

# ================= MAIN LOOP =================
def main_loop():
    symbols = get_top_futures_pairs()
    print(f"Scanning {len(symbols)} symbols...")
    while True:
        for sym in symbols:
            result = check_htf_signal(sym)
            if result:
                signal, price, tp, sl = result
                # Check active position
                if sym in active_positions:
                    pos = active_positions[sym]
                    # TP/SL hit or opposite signal
                    if (signal != pos['side']):
                        send_telegram(sym, signal, price, tp, sl)
                        active_positions[sym] = {"side": signal, "tp": tp, "sl": sl}
                    else:
                        # Signal sama, tunggu sampai TP/SL tercapai
                        continue
                else:
                    send_telegram(sym, signal, price, tp, sl)
                    active_positions[sym] = {"side": signal, "tp": tp, "sl": sl}
        time.sleep(60)  # scan tiap 1 menit

if __name__ == "__main__":
    print("HTF Signal Bot starting...")
    main_loop()
