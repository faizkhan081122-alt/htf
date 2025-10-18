import os
import time
import requests
import pandas as pd
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in env variables")

client = Client()  # Public endpoints saja, tidak perlu API key/secret

TOP_50_USDT = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","SOLUSDT","DOGEUSDT",
    "DOTUSDT","MATICUSDT","LTCUSDT","TRXUSDT","AVAXUSDT","SHIBUSDT","UNIUSDT",
    "LINKUSDT","ATOMUSDT","ETCUSDT","XLMUSDT","XMRUSDT","FILUSDT","ALGOUSDT",
    "ICPUSDT","VETUSDT","SANDUSDT","THETAUSDT","AXSUSDT","MANAUSDT","EGLDUSDT",
    "AAVEUSDT","NEARUSDT","FTMUSDT","KSMUSDT","CHZUSDT","CRVUSDT","KNCUSDT",
    "LRCUSDT","ZILUSDT","STXUSDT","EOSUSDT","GRTUSDT","MKRUSDT","SNXUSDT",
    "ENJUSDT","1INCHUSDT","BATUSDT","CELOUSDT","ANKRUSDT","QTUMUSDT","HNTUSDT"
]

# Parameter HTF
HTF_INTERVAL = '15m'
ATR_PERIOD = 14

# Track active positions
active_positions = {}

def fetch_klines(symbol, interval, limit=20):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Klines fetch error for {symbol}: {resp.status_code}")
        return None
    return resp.json()

def calculate_atr(klines, period=14):
    df = pd.DataFrame(klines, columns=['open','high','low','close','ignore','ignore2','ignore3','ignore4','ignore5','ignore6','ignore7','ignore8'])
    df['high'] = df[1].astype(float)
    df['low'] = df[2].astype(float)
    df['close'] = df[4].astype(float)
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = df[['high','low','close','prev_close']].apply(lambda x: max(
        x['high'] - x['low'],
        abs(x['high'] - x['prev_close']),
        abs(x['low'] - x['prev_close'])
    ), axis=1)
    atr = df['tr'].rolling(period).mean().iloc[-1]
    return atr

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
        if resp.status_code != 200:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Telegram send exception: {e}")

def scan_symbols():
    for symbol in TOP_50_USDT:
        klines = fetch_klines(symbol, HTF_INTERVAL)
        if not klines:
            continue
        o = float(klines[-1][1])
        h = float(klines[-1][2])
        l = float(klines[-1][3])
        c = float(klines[-1][4])
        body = abs(c - o)
        avg_body = pd.Series([abs(float(k[4]) - float(k[1])) for k in klines]).rolling(10).mean().iloc[-1]
        is_bull = (c > o) and (body > avg_body * 1.5)
        is_bear = (c < o) and (body > avg_body * 1.5)
        atr = calculate_atr(klines, ATR_PERIOD)
        tp_points = atr * 2
        sl_points = atr * 4

        # Check active position
        pos = active_positions.get(symbol, None)
        signal = None
        if pos:
            if pos['type'] == 'BUY' and is_bear:
                # Close opposite
                send_telegram(f"⚠️ {symbol} BUY closed by opposite signal at {c}")
                active_positions.pop(symbol)
            elif pos['type'] == 'SELL' and is_bull:
                send_telegram(f"⚠️ {symbol} SELL closed by opposite signal at {c}")
                active_positions.pop(symbol)
            else:
                continue  # Skip same active signal

        # New signal
        if not pos:
            if is_bull:
                active_positions[symbol] = {'type':'BUY','entry':c,'tp':c+tp_points,'sl':c-sl_points}
                send_telegram(f"🟢 {symbol} NEW BUY signal\nEntry: {c:.4f}\nTP: ±{c+tp_points:.4f} | SL: ±{c-sl_points:.4f}")
            elif is_bear:
                active_positions[symbol] = {'type':'SELL','entry':c,'tp':c-tp_points,'sl':c+sl_points}
                send_telegram(f"🔴 {symbol} NEW SELL signal\nEntry: {c:.4f}\nTP: ±{c-tp_points:.4f} | SL: ±{c+sl_points:.4f}")

def main():
    print("HTF Signal Bot starting...")
    while True:
        print("Starting HTF Signal Scan...")
        scan_symbols()
        time.sleep(60)

if __name__ == "__main__":
    main()
