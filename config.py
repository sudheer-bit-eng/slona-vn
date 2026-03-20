import os

CONFIG = {
    "symbol"          : "SOLUSDT",
    "interval"        : "30m",
    "initial_balance" : 1000.0,
    "equity_pct"      : 100.0,
    "poll_seconds"    : 15,
    "fixed_trade_usd" : 1000.0,
    "signal": {
        "length"       : 2,
        "sigma"        : 5,
        "offset_alma"  : 0.85,
        "base_minutes" : 30,
        "htf_minutes"  : 240,
    },
    "telegram": {
        "token"   : os.environ.get("TELEGRAM_TOKEN",   "8715249704:AAGnSisR-1302hvQXM2dKse_6AjixzioilU"),
        "chat_id" : os.environ.get("TELEGRAM_CHAT_ID", "1876755546"),
    },
    "google_sheets": {
        "credentials_file" : "credentials/service_account.json",
        "spreadsheet_id"   : "YOUR_SPREADSHEET_ID_HERE",
        "worksheet_name"   : "Trades",
    },
}

CSV_COLUMNS = ["trade_id","timestamp","symbol","event","side","price","usd_qty","pnl","total_pnl","balance","notes"]