# quinn_5min_tp_sl.py
from binance.client import Client
import os
from dotenv import load_dotenv
import time
import logging

# -------------------------
# CONFIG
# -------------------------
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

client = Client(API_KEY, API_SECRET, testnet=True)
client.API_URL = 'https://testnet.binance.vision/api'

symbol = "BTCUSDT"
trade_quantity = 0.001          # trade size
interval = "5m"                 # 5-minute candles
lookback = 100                  # number of candles to compute EMA
fast_period = 9
slow_period = 21
poll_sleep = 300                # 5-minute polls
DRY_RUN = True                  # True = simulate trades
RISK_REWARD_RATIO = 2           # 1:2 or 1:3

# Stop loss as % of entry price (for 1:2 ratio, 1% SL = 2% TP)
SL_PERCENT = 0.01

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# -------------------------
# Helpers
# -------------------------
def get_historical_closes(symbol, interval, limit):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    closes = [float(k[4]) for k in klines]  # close price
    return closes

def calculate_ema(prices, period):
    if len(prices) < period:
        return []
    ema = []
    sma = sum(prices[:period]) / period
    ema.append(sma)
    alpha = 2 / (period + 1)
    for price in prices[period:]:
        prev = ema[-1]
        cur = (price - prev) * alpha + prev
        ema.append(cur)
    return [None] * (period - 1) + ema

def get_trend(prev, current):
    # ASCII arrows for Windows
    if prev is None:
        return "->"
    if current > prev:
        return "+"
    elif current < prev:
        return "-"
    else:
        return "->"

def format_ema(prev, current):
    trend = get_trend(prev, current)
    prev_str = f"{prev:.2f}" if prev is not None else "N/A"
    return f"{prev_str} -> {current:.2f} ({trend})"

def place_buy_order(symbol, quantity):
    logging.info(f"place_buy_order: symbol={symbol}, qty={quantity}")
    if DRY_RUN:
        logging.info("DRY_RUN enabled: skipping real buy order.")
        return {"status": "DRY_RUN"}
    try:
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        logging.info(f"Buy order result: {order}")
        return order
    except Exception as e:
        logging.exception(f"Buy order failed: {e}")
        return None

def place_sell_order(symbol, quantity):
    logging.info(f"place_sell_order: symbol={symbol}, qty={quantity}")
    if DRY_RUN:
        logging.info("DRY_RUN enabled: skipping real sell order.")
        return {"status": "DRY_RUN"}
    try:
        order = client.order_market_sell(symbol=symbol, quantity=quantity)
        logging.info(f"Sell order result: {order}")
        return order
    except Exception as e:
        logging.exception(f"Sell order failed: {e}")
        return None

# -------------------------
# Trading loop
# -------------------------
def trading_bot():
    logging.info("Starting EMA crossover bot with TP/SL. DRY_RUN=%s | Interval=%s", DRY_RUN, interval)
    in_position = False
    last_fast_ema = None
    last_slow_ema = None
    buy_price = None
    tp_price = None
    sl_price = None
    cumulative_profit = 0.0
    cumulative_invested = 0.0

    try:
        while True:
            closes = get_historical_closes(symbol, interval, lookback)
            if len(closes) < slow_period + 1:
                logging.warning("Not enough data for EMAs. Got %d closes.", len(closes))
                time.sleep(poll_sleep)
                continue

            fast_ema_list = calculate_ema(closes, fast_period)
            slow_ema_list = calculate_ema(closes, slow_period)

            current_fast_ema = fast_ema_list[-1]
            current_slow_ema = slow_ema_list[-1]

            cumulative_pct = ((cumulative_profit / cumulative_invested) * 100) if cumulative_invested > 0 else 0.0

            if last_fast_ema is not None and last_slow_ema is not None:
                bullish_cross = (last_fast_ema <= last_slow_ema) and (current_fast_ema > current_slow_ema)
                bearish_cross = (last_fast_ema >= last_slow_ema) and (current_fast_ema < current_slow_ema)

                logging.info(
                    "Price=%.2f | fast_ema=%s | slow_ema=%s | in_position=%s | cum_profit=%.2f USD (%.4f%%)",
                    closes[-1],
                    format_ema(last_fast_ema, current_fast_ema),
                    format_ema(last_slow_ema, current_slow_ema),
                    in_position,
                    cumulative_profit,
                    cumulative_pct
                )

                # Check exit conditions if in position
                if in_position:
                    current_price = closes[-1]
                    exited = False

                    # TP or SL hit
                    if current_price >= tp_price:
                        exited = True
                        reason = "TP hit"
                    elif current_price <= sl_price:
                        exited = True
                        reason = "SL hit"

                    # EMA crossover reversal
                    elif bearish_cross:
                        exited = True
                        reason = "EMA bearish crossover"

                    if exited:
                        order = place_sell_order(symbol, trade_quantity)
                        if order:
                            sell_price = closes[-1]
                            usd_profit = (sell_price - buy_price) * trade_quantity
                            cumulative_profit += usd_profit
                            cumulative_pct = ((cumulative_profit / cumulative_invested) * 100) if cumulative_invested > 0 else 0.0
                            logging.info(f"Exited position at {sell_price:.2f} | Reason: {reason}")
                            logging.info(f"Profit for this trade: {usd_profit:+.2f} USD ({usd_profit / buy_price * 100:+.4f}%) | Cumulative P&L: {cumulative_profit:+.2f} USD ({cumulative_pct:+.4f}%)")
                            in_position = False
                            buy_price = None
                            tp_price = None
                            sl_price = None
                            logging.info("--")  # Clear log separator

                # Enter new position
                if not in_position and bullish_cross:
                    order = place_buy_order(symbol, trade_quantity)
                    if order:
                        in_position = True
                        buy_price = closes[-1]
                        sl_price = buy_price * (1 - SL_PERCENT)
                        tp_price = buy_price + (buy_price - sl_price) * RISK_REWARD_RATIO
                        cumulative_invested += buy_price * trade_quantity
                        logging.info(f"Entered position at {buy_price:.2f} | TP={tp_price:.2f} | SL={sl_price:.2f}")

            else:
                logging.info(
                    "Initializing EMA values: fast_ema=%s | slow_ema=%s",
                    format_ema(last_fast_ema, current_fast_ema),
                    format_ema(last_slow_ema, current_slow_ema)
                )

            last_fast_ema = current_fast_ema
            last_slow_ema = current_slow_ema

            time.sleep(poll_sleep)

    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received — stopping bot.")
    except Exception as e:
        logging.exception("Unexpected exception in main loop: %s", e)

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    trading_bot()
