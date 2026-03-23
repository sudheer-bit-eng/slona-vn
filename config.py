import os

CONFIG = {
    # BTC/USDT — 15m timeframe
    "symbol"          : "BTCUSDT",
    "interval"        : "15m",
    "initial_balance" : 1000.0,
    "fixed_trade_usd" : 1000.0,
    "poll_seconds"    : 10,

    # Signal: ALMA on 15m resampled to 2h (15 * 8 = 120m)
    "signal": {
        "length"       : 2,
        "sigma"        : 5,
        "offset_alma"  : 0.85,
        "base_minutes" : 15,
        "htf_minutes"  : 120,
    },

    # Risk Management — exact Pine Script values
    "risk": {
        "tp1_pct" : 1.0,    # TP1 +1.0%
        "tp2_pct" : 1.5,    # TP2 +1.5%
        "tp3_pct" : 2.0,    # TP3 +2.0%
        "sl_pct"  : 0.5,    # SL  -0.5%
        "tp1_qty" : 80.0,   # exit 50% at TP1
        "tp2_qty" : 20.0,   # exit 60% of remaining at TP2 (= 30% of original)
        "tp3_qty" : 0.0,  # exit 100% of remaining at TP3 (= 20% of original)
    },

    # Telegram
    "telegram": {
        "token"   : os.environ.get("TELEGRAM_TOKEN",   "8715249704:AAGnSisR-1302hvQXM2dKse_6AjixzioilU"),
        "chat_id" : os.environ.get("TELEGRAM_CHAT_ID", "1876755546"),
    },

    # Google Sheets (disabled)
    "google_sheets": {
        "credentials_file" : "credentials/service_account.json",
        "spreadsheet_id"   : "YOUR_SPREADSHEET_ID_HERE",
        "worksheet_name"   : "Trades",
    },
}

CSV_COLUMNS = ["trade_id","timestamp","symbol","event","side",
               "price","usd_qty","pnl","total_pnl","balance","notes"]