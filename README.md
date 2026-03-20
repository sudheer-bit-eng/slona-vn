# SOL/USDT Paper Trading Bot

Converts the **SAIYAN OCC Pine Script strategy** into a fully
automated Python paper trader.

---

## What It Does

| Feature | Detail |
|---|---|
| Exchange | Binance (no API key needed — public data only) |
| Symbol | SOL/USDT |
| Timeframe | 5-minute candles |
| Signal | ALMA(close,2) crosses ALMA(open,2) |
| Long entry | ALMA close **crosses above** ALMA open |
| Short entry | ALMA close **crosses below** ALMA open |
| TP1 | +1.0% → exit **50%** of position |
| TP2 | +1.5% → exit **60%** of remaining |
| TP3 | +2.0% → exit **100%** of remaining |
| Stop Loss | −0.5% → exit 100% |
| Reversal | Opposite signal → close current, open new |
| Starting balance | $1 000 paper USD |
| Trade size | 100% of current balance per trade (full $1 000) |
| Data output | `data/trades.csv`  +  Google Sheets (optional) |

---

## Folder Structure

```
sol_trader/
├── bot.py              ← main bot (run this)
├── config.py           ← all settings — edit here
├── logger.py           ← coloured console + file logging
├── csv_log.py          ← CSV writer
├── sheets.py           ← Google Sheets client
├── setup_sheets.py     ← one-time Sheets setup wizard
├── requirements.txt
├── credentials/
│   └── service_account.json   ← your Google key (you create this)
├── data/
│   └── trades.csv      ← auto-created on first run
└── logs/
    └── bot.log         ← full debug log
```

---

## Quick Start

### 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2 — (Optional) Set up Google Sheets

```bash
python setup_sheets.py          # read the guide
python setup_sheets.py --test   # test your credentials
```

Then open `config.py` and paste your spreadsheet ID:

```python
"spreadsheet_id" : "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
```

### 3 — Start the bot

```bash
python bot.py
```

The bot will print coloured output to the terminal:

```
10:05:00 | INFO    | ═══ Bot started  symbol=SOLUSDT  tf=5m ═══
10:05:01 | INFO    | ▶ Opened LONG @ 142.3100  size=$100.00
10:05:01 | INFO    | ENTRY_LONG        price=142.3100  qty=$100.00  bal=$900.00
10:10:05 | INFO    | ◑ TP1_HIT         price=143.7400  qty=$50.00   bal=$950.50  P&L=+$0.50
10:15:05 | INFO    | ◑ TP2_HIT         price=144.4500  qty=$30.00   bal=$951.56  P&L=+$1.06
10:20:05 | INFO    | ■ Closed LONG @ 145.1600  P&L=$+0.42  bal=$951.98
```

### 4 — Stop the bot

Press `Ctrl + C` — it prints your total P&L and exits cleanly.

---

## Tuning the Strategy

All parameters are in **`config.py`**:

```python
"equity_pct"  : 10.0   # trade size (% of balance)
"tp1_pct"     : 1.0    # TP1 target %
"tp2_pct"     : 1.5    # TP2 target %
"tp3_pct"     : 2.0    # TP3 target %
"sl_pct"      : 0.5    # stop loss %
"tp1_qty"     : 50.0   # % of position exited at TP1
"tp2_qty"     : 60.0   # % of REMAINING exited at TP2
"tp3_qty"     : 100.0  # % of REMAINING exited at TP3
```

---

## CSV Output — Column Reference

| Column | Description |
|---|---|
| `trade_id` | Sequential trade counter |
| `timestamp` | UTC time of the event |
| `symbol` | SOLUSDT |
| `event` | ENTRY_LONG / ENTRY_SHORT / TP1_HIT / TP2_HIT / TP3_HIT / SL_HIT / REVERSAL_CLOSE / FULL_EXIT |
| `side` | LONG or SHORT |
| `price` | Execution price |
| `usd_qty` | Dollar value of this exit / entry |
| `pnl` | Realised P&L for this event |
| `balance` | Paper balance after event |
| `notes` | TP/SL levels or remaining position size |

---

## Disclaimer

This is a **paper trading** / educational tool only.
No real money is used. Past simulated performance does not
guarantee future results. Always do your own research.
