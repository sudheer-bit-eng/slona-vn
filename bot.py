"""
=============================================================
  SOL/USDT Paper Trading Bot  —  Binance 5m  |  ALMA Cross
=============================================================
  Converts Pine Script "SAIYAN OCC" strategy to Python.

  Entry  : ALMA(close,2) crosses ALMA(open,2) on 5m candles
  TP1    : +1.0%  → exit 50% of position
  TP2    : +1.5%  → exit 30% of remaining
  TP3    : +2.0%  → exit 20% of remaining
  SL     : -0.5%  → exit 100%
  Reversal: MA cross flips → close current, open opposite
  Balance : $1000 paper money (10% equity per trade)

  Outputs :  data/trades.csv   – every trade event
             Google Sheets      – live mirror of trades.csv
=============================================================
"""

import time
import math
import logging
import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from config   import CONFIG
from logger   import setup_logger, log_event
from sheets   import SheetsClient
from csv_log  import CSVLogger
from Telegramclient import TelegramClient

# ─────────────────────────── logging ──────────────────────
logger = setup_logger("bot", "logs/bot.log")

# ─────────────────────────── ALMA ─────────────────────────
def alma(series: pd.Series, length: int = 2,
         offset: float = 0.85, sigma: int = 5) -> pd.Series:
    """
    Arnaud Legoux Moving Average – matches Pine Script ta.alma().
    """
    m   = offset * (length - 1)
    s   = length / sigma
    weights = np.array([
        math.exp(-((i - m) ** 2) / (2 * s * s))
        for i in range(length)
    ])
    weights /= weights.sum()

    result = series.copy() * np.nan
    for i in range(length - 1, len(series)):
        window      = series.iloc[i - length + 1 : i + 1].values
        result.iloc[i] = (window * weights).sum()
    return result


# ─────────────────────────── Data sources ──────────────────
# Tries multiple sources in order — fixes 451 region blocks on Railway
import ssl, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _get(url: str, params: dict = None, timeout: int = 10) -> requests.Response:
    """GET with SSL verification disabled."""
    resp = requests.get(url, params=params, timeout=timeout, verify=False)
    resp.raise_for_status()
    return resp


def fetch_klines(symbol: str, interval: str,
                 limit: int = 100) -> pd.DataFrame:
    """
    Fetch OHLCV candles — tries multiple sources in order:
    1. Binance.com
    2. Binance US
    3. KuCoin (mapped symbol)
    """
    # ── Source 1: Binance.com ──────────────────────────────
    binance_urls = [
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines",
        "https://api2.binance.com/api/v3/klines",
    ]
    for url in binance_urls:
        try:
            resp = _get(url, params=dict(symbol=symbol, interval=interval, limit=limit))
            raw  = resp.json()
            df   = pd.DataFrame(raw, columns=[
                "open_time","open","high","low","close","volume",
                "close_time","qav","trades","tbbav","tbqav","ignore"
            ])
            for col in ["open","high","low","close"]:
                df[col] = df[col].astype(float)
            df["open_time"]  = pd.to_datetime(df["open_time"],  unit="ms")
            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
            logger.debug("Klines from %s", url)
            return df.iloc[:-1].reset_index(drop=True)
        except Exception as e:
            logger.debug("Binance klines failed %s: %s", url, e)

    # ── Source 2: KuCoin ──────────────────────────────────
    try:
        # convert interval: 5m→5min, 1h→1hour
        kc_interval = interval.replace("m", "min").replace("h", "hour").replace("d", "day")
        kc_symbol   = symbol.replace("USDT", "-USDT")   # SOLUSDT → SOL-USDT
        url  = "https://api.kucoin.com/api/v1/market/candles"
        resp = _get(url, params=dict(symbol=kc_symbol, type=kc_interval))
        raw  = resp.json().get("data", [])
        # KuCoin returns newest first — reverse it
        raw  = list(reversed(raw))
        df   = pd.DataFrame(raw, columns=["open_time","open","close","high","low","volume","turnover"])
        for col in ["open","high","low","close"]:
            df[col] = df[col].astype(float)
        df["open_time"]  = pd.to_datetime(df["open_time"].astype(int), unit="s")
        df["close_time"] = df["open_time"]
        df = df.tail(limit)
        logger.debug("Klines from KuCoin")
        return df.iloc[:-1].reset_index(drop=True)
    except Exception as e:
        logger.debug("KuCoin klines failed: %s", e)

    raise RuntimeError("All kline sources failed — check internet/region block")


def fetch_price(symbol: str) -> float:
    """
    Fetch current price — tries Binance then KuCoin.
    """
    # ── Binance ───────────────────────────────────────────
    for url in ["https://api.binance.com/api/v3/ticker/price",
                "https://api1.binance.com/api/v3/ticker/price"]:
        try:
            resp = _get(url, params={"symbol": symbol}, timeout=5)
            return float(resp.json()["price"])
        except Exception as e:
            logger.debug("Binance price failed %s: %s", url, e)

    # ── KuCoin ────────────────────────────────────────────
    try:
        kc_symbol = symbol.replace("USDT", "-USDT")
        url  = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={kc_symbol}"
        resp = _get(url, timeout=5)
        return float(resp.json()["data"]["price"])
    except Exception as e:
        logger.debug("KuCoin price failed: %s", e)

    raise RuntimeError("All price sources failed")


# ─────────────────────────── Signal engine ────────────────
def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add ALMA columns and crossover signals.
    Mirrors Pine Script:
        closeSeries = alma(close, basisLen=2, offsetSigma=5, offsetALMA=0.85)
        openSeries  = alma(open,  basisLen=2, offsetSigma=5, offsetALMA=0.85)
        leTrigger   = crossover (closeSeries, openSeries)   → Long
        seTrigger   = crossunder(closeSeries, openSeries)   → Short
    """
    cfg = CONFIG["signal"]
    df["alma_close"] = alma(df["close"], cfg["length"],
                            cfg["offset_alma"], cfg["sigma"])
    df["alma_open"]  = alma(df["open"],  cfg["length"],
                            cfg["offset_alma"], cfg["sigma"])

    df["cross_long"]  = (
        (df["alma_close"] >  df["alma_open"]) &
        (df["alma_close"].shift(1) <= df["alma_open"].shift(1))
    )
    df["cross_short"] = (
        (df["alma_close"] <  df["alma_open"]) &
        (df["alma_close"].shift(1) >= df["alma_open"].shift(1))
    )
    return df


# ─────────────────────────── Position tracker ─────────────
class Position:
    """Tracks a single open paper trade."""

    def __init__(self, side: str, entry_price: float,
                 qty_usd: float):
        self.side        = side          # "LONG" | "SHORT"
        self.entry_price = entry_price
        self.initial_usd = qty_usd       # dollar value at entry
        self.remaining   = qty_usd       # shrinks at each TP hit
        self.tp_hit      = 0             # 0 / 1 / 2 / 3
        self.open_time   = datetime.now(timezone.utc)

        cfg = CONFIG["risk"]
        if side == "LONG":
            self.tp1 = entry_price * (1 + cfg["tp1_pct"] / 100)
            self.tp2 = entry_price * (1 + cfg["tp2_pct"] / 100)
            self.tp3 = entry_price * (1 + cfg["tp3_pct"] / 100)
            self.sl  = entry_price * (1 - cfg["sl_pct"]  / 100)
        else:
            self.tp1 = entry_price * (1 - cfg["tp1_pct"] / 100)
            self.tp2 = entry_price * (1 - cfg["tp2_pct"] / 100)
            self.tp3 = entry_price * (1 - cfg["tp3_pct"] / 100)
            self.sl  = entry_price * (1 + cfg["sl_pct"]  / 100)

    def pnl(self, price: float) -> float:
        """Unrealised P&L in USD for remaining position."""
        if self.side == "LONG":
            return self.remaining * (price - self.entry_price) / self.entry_price
        else:
            return self.remaining * (self.entry_price - price) / self.entry_price

    def __repr__(self):
        return (f"<Position {self.side} entry={self.entry_price:.4f} "
                f"remaining=${self.remaining:.2f} tp_hit={self.tp_hit}>")


# ─────────────────────────── Bot ──────────────────────────
class TradingBot:

    def __init__(self):
        cfg             = CONFIG
        self.symbol     = cfg["symbol"]          # "SOLUSDT"
        self.interval   = cfg["interval"]        # "5m"
        self.balance    = cfg["initial_balance"] # 1000.0 USD
        self.equity_pct = cfg["equity_pct"]      # 10 %

        self.position: Position | None = None
        self.trade_id    = 0
        self.total_pnl   = 0.0

        self.csv      = CSVLogger("data/trades.csv")
        self.sheets   = SheetsClient()
        tg            = CONFIG.get("telegram", {})
        self.telegram = TelegramClient(tg.get("token",""), tg.get("chat_id",""))

        logger.info("Bot initialised — balance: $%.2f", self.balance)

    # ── helpers ────────────────────────────────────────────
    def _trade_size(self) -> float:
        return self.balance * (self.equity_pct / 100)

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # ── logging helper ─────────────────────────────────────
    def _log_trade(self, event: str, price: float,
                   usd_qty: float, pnl: float = 0.0,
                   notes: str = ""):
        row = {
            "trade_id"  : self.trade_id,
            "timestamp" : self._now(),
            "symbol"    : self.symbol,
            "event"     : event,
            "side"      : self.position.side if self.position else "—",
            "price"     : round(price, 4),
            "usd_qty"   : round(usd_qty, 4),
            "pnl"       : round(pnl, 4),
            "balance"   : round(self.balance, 4),
            "notes"     : notes,
        }
        self.csv.write(row)
        self.sheets.append(row)
        self.telegram.send(row)
        log_event(logger, row)

    # ── open position ──────────────────────────────────────
    def open_position(self, side: str, price: float):
        self.trade_id += 1
        size          = self._trade_size()
        self.position = Position(side, price, size)
        notes = (f"TP1={self.position.tp1:.4f}  "
                 f"TP2={self.position.tp2:.4f}  "
                 f"TP3={self.position.tp3:.4f}  "
                 f"SL={self.position.sl:.4f}")
        self._log_trade(f"ENTRY_{side}", price, size, notes=notes)
        logger.info("▶ Opened %s @ %.4f  size=$%.2f", side, price, size)

    # ── close position (full) ─────────────────────────────
    def close_position(self, price: float, reason: str):
        p   = self.position
        pnl = p.pnl(price)
        self.balance    += pnl
        self.total_pnl  += pnl
        self._log_trade(reason, price, p.remaining, pnl)
        logger.info("■ Closed %s @ %.4f  P&L=$%.4f  bal=$%.2f",
                    p.side, price, pnl, self.balance)
        self.position = None

    # ── partial exit ──────────────────────────────────────
    def partial_exit(self, label: str, price: float, pct: float):
        p        = self.position
        exit_usd = p.remaining * (pct / 100)

        if p.side == "LONG":
            pnl = exit_usd * (price - p.entry_price) / p.entry_price
        else:
            pnl = exit_usd * (p.entry_price - price) / p.entry_price

        self.balance   += pnl
        self.total_pnl += pnl
        p.remaining    -= exit_usd

        self._log_trade(label, price, exit_usd, pnl,
                        f"remaining=${p.remaining:.2f}")
        logger.info("◑ %s @ %.4f  exit=$%.2f  P&L=$%.4f  bal=$%.2f",
                    label, price, exit_usd, pnl, self.balance)

    # ── check exits on every tick ─────────────────────────
    def check_exits(self, price: float):
        p   = self.position
        cfg = CONFIG["risk"]

        if p.side == "LONG":
            # SL
            if price <= p.sl:
                self.close_position(price, "SL_HIT"); return
            # TP1
            if p.tp_hit == 0 and price >= p.tp1:
                self.partial_exit("TP1_HIT", price, cfg["tp1_qty"])
                p.tp_hit = 1
            # TP2
            elif p.tp_hit == 1 and price >= p.tp2:
                self.partial_exit("TP2_HIT", price, cfg["tp2_qty"])
                p.tp_hit = 2
            # TP3
            elif p.tp_hit == 2 and price >= p.tp3:
                self.partial_exit("TP3_HIT", price, cfg["tp3_qty"])
                p.tp_hit = 3
                self.close_position(price, "FULL_EXIT"); return

        else:  # SHORT
            if price >= p.sl:
                self.close_position(price, "SL_HIT"); return
            if p.tp_hit == 0 and price <= p.tp1:
                self.partial_exit("TP1_HIT", price, cfg["tp1_qty"])
                p.tp_hit = 1
            elif p.tp_hit == 1 and price <= p.tp2:
                self.partial_exit("TP2_HIT", price, cfg["tp2_qty"])
                p.tp_hit = 2
            elif p.tp_hit == 2 and price <= p.tp3:
                self.partial_exit("TP3_HIT", price, cfg["tp3_qty"])
                p.tp_hit = 3
                self.close_position(price, "FULL_EXIT"); return

    # ── main loop ─────────────────────────────────────────
    def run(self):
        logger.info("═══ Bot started  symbol=%s  tf=%s ═══",
                    self.symbol, self.interval)

        poll_sec  = CONFIG["poll_seconds"]   # price-check cadence (e.g. 10 s)
        candle_sec = CONFIG["candle_seconds"] # 5 min = 300 s
        last_signal_ts = None

        while True:
            try:
                # ── 1. fetch closed candles & recompute signals ──
                df = fetch_klines(self.symbol, self.interval, limit=60)
                df = compute_signals(df)

                latest_ts = df.iloc[-1]["close_time"]

                # only act on a new candle signal once
                new_candle = (latest_ts != last_signal_ts)
                long_signal  = bool(df.iloc[-1]["cross_long"])
                short_signal = bool(df.iloc[-1]["cross_short"])

                # ── 2. real-time price ──────────────────────────
                price = fetch_price(self.symbol)

                # ── 3. manage open position ─────────────────────
                if self.position:
                    self.check_exits(price)

                # ── 4. entry / reversal logic ───────────────────
                if new_candle:
                    last_signal_ts = latest_ts

                    if long_signal:
                        if self.position and self.position.side == "SHORT":
                            logger.info("↩ Reversal — closing SHORT, opening LONG")
                            self.close_position(price, "REVERSAL_CLOSE")
                        if not self.position:
                            self.open_position("LONG", price)

                    elif short_signal:
                        if self.position and self.position.side == "LONG":
                            logger.info("↩ Reversal — closing LONG, opening SHORT")
                            self.close_position(price, "REVERSAL_CLOSE")
                        if not self.position:
                            self.open_position("SHORT", price)

                # ── 5. heartbeat ─────────────────────────────
                pos_info = (f"{self.position.side} entry={self.position.entry_price:.4f}"
                            if self.position else "flat")
                logger.debug("tick price=%.4f  pos=%s  bal=$%.2f",
                             price, pos_info, self.balance)

                time.sleep(poll_sec)

            except (requests.exceptions.RequestException,
                    requests.exceptions.SSLError) as e:
                logger.warning("Network error: %s — retrying in 15 s", e)
                time.sleep(15)
            except KeyboardInterrupt:
                logger.info("Bot stopped by user. Total P&L: $%.4f", self.total_pnl)
                break
            except Exception as e:
                logger.exception("Unexpected error: %s", e)
                time.sleep(30)


# ─────────────────────────── entry point ──────────────────
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()