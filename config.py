"""
config.py — All settings for the SOL/USDT paper trading bot.
Edit this file to tune the strategy without touching bot logic.
"""

CONFIG = {
    # ─── Exchange & Symbol ───────────────────────────────
    "symbol"          : "SOLUSDT",
    "interval"        : "5m",         # Binance kline interval

    # ─── Paper Trading ───────────────────────────────────
    "initial_balance" : 1000.0,       # USD paper money
    "equity_pct"      : 100.0,        # % of balance per trade (100% = full $1000)

    # ─── Timing ──────────────────────────────────────────
    "poll_seconds"    : 10,           # how often to check price (seconds)
    "candle_seconds"  : 300,          # 5 min candle = 300 seconds

    # ─── Signal (ALMA crossover) ─────────────────────────
    "signal": {
        "length"      : 2,            # MA Period  (basisLen in Pine)
        "sigma"       : 5,            # Sigma for ALMA (offsetSigma)
        "offset_alma" : 0.85,         # Offset for ALMA (offsetALMA)
    },

    # ─── Risk Management ─────────────────────────────────
    "risk": {
        "tp1_pct"     : 1.0,          # TP1 level  %
        "tp2_pct"     : 1.5,          # TP2 level  %
        "tp3_pct"     : 2.0,          # TP3 level  %
        "sl_pct"      : 0.5,          # Stop Loss  %

        "tp1_qty"     : 100.0,         # % of position to close at TP1
        "tp2_qty"     : 0.0,         # % of REMAINING position at TP2
        "tp3_qty"     : 0.0,        # % of REMAINING position at TP3
    },

    # ─── Google Sheets ───────────────────────────────────
    # Paste your spreadsheet ID after sharing with the service account email.
    # Example: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
    # ─── Telegram Alerts ─────────────────────────────────
    # Step 1: Open Telegram → search @BotFather → /newbot → copy token
    # Step 2: Search @userinfobot → /start → copy your chat_id
    "telegram": {
        "token"   : "8792621297:AAFHPeZW0dVjkV2fDlNl7El4zKk7_Hk9628",    # e.g. "7412xxxxxx:AAHxxxxxx"
        "chat_id" : "1876755546",      # e.g. "123456789"
    },

    "google_sheets": {
        "credentials_file" : "credentials/service_account.json",
        "spreadsheet_id"   : "YOUR_SPREADSHEET_ID_HERE",
        "worksheet_name"   : "Trades",
    },
}

# ─── CSV Output ──────────────────────────────────────────
CSV_COLUMNS = [
    "trade_id",
    "timestamp",
    "symbol",
    "event",          # ENTRY_LONG / ENTRY_SHORT / TP1_HIT / SL_HIT / REVERSAL_CLOSE / FULL_EXIT
    "side",           # LONG / SHORT
    "price",
    "usd_qty",        # dollar value of this partial exit / entry
    "pnl",            # realised P&L for this event
    "balance",        # running paper balance after event
    "notes",          # TP levels, SL level, remaining position size
]