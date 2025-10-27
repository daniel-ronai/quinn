# Quinn Trading Bot

A Binance EMA crossover bot with 5-minute intervals, TP/SL, and cumulative profit tracking.

## Features
- EMA crossover entry (fast vs slow)
- Take Profit / Stop Loss
- Cumulative profit logging
- Dry-run mode for testing
- 5-minute candle polling

## Configuration
1. Copy `.env.example` to `.env` and fill in your Binance API keys.
2. Adjust parameters in `quinn.py` (symbol, intervals, TP/SL ratio, etc.)

## Running
```bash
python quinn.py
