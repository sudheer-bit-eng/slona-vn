"""
=============================================================
  SOL/USDT Paper Trading Bot  —  Binance/KuCoin  |  30m
=============================================================
  Exact logic from Pine Script:

  Signal : ALMA(close,2) crosses ALMA(open,2)
           computed on 30m, resampled to 4h (30 * 8)

  BUY    : 4h ALMA close crosses ABOVE 4h ALMA open
           → close any SHORT, open LONG at market price

  SELL   : 4h ALMA close crosses BELOW 4h ALMA open
           → close any LONG, open SHORT at market price

  NO SL, NO TP — position held until next signal flips it.

  Outputs : data/trades.csv + Telegram phone alerts
=============================================================
"""

import time
import math
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import urllib3

from config          import CONFIG
from logger          import setup_logger, log_event
from sheets          import SheetsClient
from csv_log         import CSVLogger
from telegram_client import TelegramClient

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────── logging ──────────────────────
logger = setup_logger("bot", "logs/bot.log")


# ─────────────────────────── ALMA ─────────────────────────
def alma(series: pd.Series, length: int = 2,
         offset: float = 0.85, sigma: int = 5) -> pd.Series:
    """Arnaud Legoux Moving Average — matches Pine Script ta.alma()."""
    m       = offset * (length - 1)
    s       = length / sigma
    weights = np.array([
        math.exp(-((i - m) ** 2) / (2 * s * s))
        for i in range(length)
    ])
    weights /= weights.sum()
    result = series.copy() * np.nan
    for i in range(length - 1, len(series)):
        window = series.iloc[i - length + 1 : i + 1].values
        result.iloc[i] = (window * weights).sum()
    return result


# ─────────────────────────── Data fetch ───────────────────
def _get(url, params=None, timeout=10):
    return requests.get(url, params=params, timeout=timeout, verify=False)


def fetch_klines(symbol: str, interval: str,
                 limit: int = 500) -> pd.DataFrame:
    """Fetch OHLCV candles — tries Binance then KuCoin."""
    # Binance
    for url in ["https://api.binance.com/api/v3/klines",
                "https://api1.binance.com/api/v3/klines",
                "https://api2.binance.com/api/v3/klines"]:
        try:
            resp = _get(url, params=dict(symbol=symbol,
                                         interval=interval, limit=limit))
            resp.raise_for_status()
            raw = resp.json()
            df  = pd.DataFrame(raw, columns=[
                "open_time","open","high","low","close","volume",
                "close_time","qav","trades","tbbav","tbqav","ignore"
            ])
            for col in ["open","high","low","close"]:
                df[col] = df[col].astype(float)
            df["open_time"]  = pd.to_datetime(df["open_time"],  unit="ms")
            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
            return df.iloc[:-1].reset_index(drop=True)
        except Exception as e:
            logger.debug("Binance failed %s: %s", url, e)

    # KuCoin fallback
    try:
        kc_int    = interval.replace("m","min").replace("h","hour").replace("d","day")
        kc_symbol = symbol.replace("USDT", "-USDT")
        resp = _get("https://api.kucoin.com/api/v1/market/candles",
                    params=dict(symbol=kc_symbol, type=kc_int))
        resp.raise_for_status()
        raw = list(reversed(resp.json().get("data", [])))
        df  = pd.DataFrame(raw, columns=[
            "open_time","open","close","high","low","volume","turnover"
        ])
        for col in ["open","high","low","close"]:
            df[col] = df[col].astype(float)
        df["open_time"]  = pd.to_datetime(df["open_time"].astype(int), unit="s")
        df["close_time"] = df["open_time"]
        df = df.tail(limit)
        logger.debug("Klines from KuCoin ✓")
        return df.iloc[:-1].reset_index(drop=True)
    except Exception as e:
        logger.debug("KuCoin failed: %s", e)

    raise RuntimeError("All kline sources failed")


def fetch_price(symbol: str) -> float:
    """Fetch current price — tries Binance then KuCoin."""
    for url in ["https://api.binance.com/api/v3/ticker/price",
                "https://api1.binance.com/api/v3/ticker/price"]:
        try:
            r = _get(url, params={"symbol": symbol}, timeout=5)
            r.raise_for_status()
            return float(r.json()["price"])
        except Exception as e:
            logger.debug("Binance price failed: %s", e)
    try:
        kc_sym = symbol.replace("USDT", "-USDT")
        r = _get(f"https://api.kucoin.com/api/v1/market/orderbook/level1"
                 f"?symbol={kc_sym}", timeout=5)
        r.raise_for_status()
        return float(r.json()["data"]["price"])
    except Exception as e:
        logger.debug("KuCoin price failed: %s", e)
    raise RuntimeError("All price sources failed")


# ─────────────────────────── Signal engine ────────────────
def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Exact Pine Script logic:
      1. ALMA(close, 2, 0.85, 5) and ALMA(open, 2, 0.85, 5) on 30m
      2. Resample both to 4h (30m * intRes 8 = 240m)
      3. BUY  = 4h ALMA close crosses ABOVE 4h ALMA open
      4. SELL = 4h ALMA close crosses BELOW 4h ALMA open
    """
    cfg         = CONFIG["signal"]
    htf_minutes = cfg["htf_minutes"]   # 240

    # Step 1: ALMA on 30m
    df["alma_close"] = alma(df["close"], cfg["length"],
                            cfg["offset_alma"], cfg["sigma"])
    df["alma_open"]  = alma(df["open"],  cfg["length"],
                            cfg["offset_alma"], cfg["sigma"])

    # Step 2: Resample to 4h
    df2       = df.set_index("open_time")
    rule      = f"{htf_minutes}min"
    htf_close = df2["alma_close"].resample(
        rule, closed="left", label="left").last().dropna()
    htf_open  = df2["alma_open"].resample(
        rule, closed="left", label="left").last().dropna()

    # Step 3: Forward-fill back to 30m (matches Pine lookahead_on)
    df["htf_close"] = htf_close.reindex(df2.index, method="ffill").values
    df["htf_open"]  = htf_open.reindex(df2.index,  method="ffill").values

    # Step 4: Crossover / crossunder
    df["cross_long"]  = (
        (df["htf_close"] >  df["htf_open"]) &
        (df["htf_close"].shift(1) <= df["htf_open"].shift(1))
    )
    df["cross_short"] = (
        (df["htf_close"] <  df["htf_open"]) &
        (df["htf_close"].shift(1) >= df["htf_open"].shift(1))
    )
    return df


# ─────────────────────────── Position tracker ─────────────
class Position:
    """Tracks a single open paper trade — no SL/TP, held until flip."""

    def __init__(self, side: str, entry_price: float, qty_usd: float):
        self.side        = side          # "LONG" | "SHORT"
        self.entry_price = entry_price
        self.qty_usd     = qty_usd
        self.open_time   = datetime.now(timezone.utc)

    def pnl(self, price: float) -> float:
        if self.side == "LONG":
            return self.qty_usd * (price - self.entry_price) / self.entry_price
        else:
            return self.qty_usd * (self.entry_price - price) / self.entry_price

    def __repr__(self):
        return (f"<Position {self.side} entry={self.entry_price:.4f}"
                f" qty=${self.qty_usd:.2f}>")


# ─────────────────────────── Bot ──────────────────────────
class TradingBot:

    def __init__(self):
        cfg             = CONFIG
        self.symbol     = cfg["symbol"]
        self.interval   = cfg["interval"]
        self.balance    = cfg["initial_balance"]
        self.equity_pct = cfg["equity_pct"]

        self.position: Position | None = None
        self.trade_id  = 0
        self.total_pnl = 0.0

        self.csv      = CSVLogger("data/trades.csv")
        self.sheets   = SheetsClient()
        tg            = CONFIG.get("telegram", {})
        self.telegram = TelegramClient(
            tg.get("token", ""), tg.get("chat_id", ""))

        logger.info("Bot initialised — balance: $%.2f", self.balance)
        logger.info("📁 Trade log → data/trades.csv")

    # ── helpers ───────────────────────────────────────────
    def _trade_size(self) -> float:
        # Always trade $1000 fixed — use whatever is available if balance < $1000
        fixed = CONFIG.get("fixed_trade_usd", 1000.0)
        return min(fixed, self.balance)

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _log(self, event: str, price: float,
             qty: float, pnl: float = 0.0, notes: str = ""):
        row = {
            "trade_id" : self.trade_id,
            "timestamp": self._now(),
            "symbol"   : self.symbol,
            "event"    : event,
            "side"     : self.position.side if self.position else "—",
            "price"    : round(price, 4),
            "usd_qty"  : round(qty,   4),
            "pnl"      : round(pnl,   4),
            "balance"  : round(self.balance, 4),
            "total_pnl": round(self.total_pnl, 4),
            "notes"    : notes,
        }
        self.csv.write(row)
        self.sheets.append(row)
        self.telegram.send(row)
        log_event(logger, row)

    # ── open position ─────────────────────────────────────
    def _open(self, side: str, price: float):
        self.trade_id += 1
        size           = self._trade_size()
        self.position  = Position(side, price, size)
        self._log(f"ENTRY_{side}", price, size,
                  notes=f"entry={price:.4f}")
        logger.info("▶ Opened %s @ %.4f  size=$%.2f",
                    side, price, size)

    # ── close position ────────────────────────────────────
    def _close(self, price: float, reason: str):
        p              = self.position
        pnl            = p.pnl(price)
        self.balance  += pnl
        self.total_pnl += pnl
        self._log(reason, price, p.qty_usd, pnl,
                  notes=f"entry={p.entry_price:.4f}  exit={price:.4f}")
        logger.info("■ Closed %s @ %.4f  P&L=$%.4f  bal=$%.2f",
                    p.side, price, pnl, self.balance)
        self.position = None

    # ── main loop ─────────────────────────────────────────
    def run(self):
        logger.info("═══ Bot started  symbol=%s  tf=%s ═══",
                    self.symbol, self.interval)

        last_signal_ts = None

        while True:
            try:
                # 1. Fetch closed candles & compute signals
                df = fetch_klines(self.symbol, self.interval, limit=500)
                df = compute_signals(df)

                latest_ts    = df.iloc[-1]["close_time"]
                new_candle   = (latest_ts != last_signal_ts)
                long_signal  = bool(df.iloc[-1]["cross_long"])
                short_signal = bool(df.iloc[-1]["cross_short"])

                # 2. Real-time price
                price = fetch_price(self.symbol)

                # 3. Act on new candle signal only
                if new_candle:
                    last_signal_ts = latest_ts

                    if long_signal:
                        # Close SHORT if open, then open LONG
                        if self.position and self.position.side == "SHORT":
                            self._close(price, "CLOSE_SHORT")
                        if not self.position:
                            self._open("LONG", price)

                    elif short_signal:
                        # Close LONG if open, then open SHORT
                        if self.position and self.position.side == "LONG":
                            self._close(price, "CLOSE_LONG")
                        if not self.position:
                            self._open("SHORT", price)

                # 4. Heartbeat log
                pos_info = (f"{self.position.side} @ "
                            f"{self.position.entry_price:.4f}"
                            if self.position else "flat")
                logger.debug("tick price=%.4f  pos=%s  bal=$%.2f",
                             price, pos_info, self.balance)

                time.sleep(CONFIG["poll_seconds"])

            except requests.exceptions.RequestException as e:
                logger.warning("Network error: %s — retrying in 15s", e)
                time.sleep(15)
            except KeyboardInterrupt:
                logger.info("Bot stopped. Total P&L: $%.4f", self.total_pnl)
                break
            except Exception as e:
                logger.exception("Unexpected error: %s", e)
                time.sleep(30)


# ─────────────────────────── entry point ──────────────────
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()