"""
=============================================================
  BTC/USDT Paper Trading Bot  —  Binance/KuCoin  |  15m
=============================================================
  Pine Script SAIYAN OCC logic — exact match:

  Signal : ALMA(close,2) crosses ALMA(open,2)
           on 15m candles, resampled to 2h (15 * 8 = 120m)

  BUY    : 2h ALMA close crosses ABOVE 2h ALMA open
  SELL   : 2h ALMA close crosses BELOW 2h ALMA open

  Trade Management:
    TP1 : +1.0%  → exit 50% of position
    TP2 : +1.5%  → exit 30% of remaining
    TP3 : +2.0%  → exit 20% of remaining
    SL  : -0.5%  → exit 100%

  On new opposite signal → close all, open new position

  Fixed $1000 per trade (use remaining if balance < $1000)
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

logger = setup_logger("bot", "logs/bot.log")


# ─────────────────────────── ALMA ─────────────────────────
def alma(series: pd.Series, length: int = 2,
         offset: float = 0.85, sigma: int = 5) -> pd.Series:
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
    Exact Pine Script SAIYAN OCC logic:
      Base TF : 15m
      HTF     : 15 * intRes(8) = 120m (2h)
      ALMA(close,2,0.85,5) and ALMA(open,2,0.85,5) on 15m
      Resampled to 2h → crossover = BUY, crossunder = SELL
    """
    cfg         = CONFIG["signal"]
    htf_minutes = cfg["htf_minutes"]   # 120

    df["alma_close"] = alma(df["close"], cfg["length"],
                            cfg["offset_alma"], cfg["sigma"])
    df["alma_open"]  = alma(df["open"],  cfg["length"],
                            cfg["offset_alma"], cfg["sigma"])

    df2       = df.set_index("open_time")
    rule      = f"{htf_minutes}min"
    htf_close = df2["alma_close"].resample(
        rule, closed="left", label="left").last().dropna()
    htf_open  = df2["alma_open"].resample(
        rule, closed="left", label="left").last().dropna()

    df["htf_close"] = htf_close.reindex(df2.index, method="ffill").values
    df["htf_open"]  = htf_open.reindex(df2.index,  method="ffill").values

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
    """
    Tracks open paper trade with TP1/TP2/TP3 + SL.
    Mirrors Pine Script risk management exactly.
    """

    def __init__(self, side: str, entry_price: float, qty_usd: float):
        self.side        = side
        self.entry_price = entry_price
        self.initial_usd = qty_usd
        self.remaining   = qty_usd    # shrinks at each TP hit
        self.tp_hit      = 0          # 0=none, 1=tp1, 2=tp2, 3=tp3
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

    def calc_pnl(self, price: float, usd_qty: float) -> float:
        if self.side == "LONG":
            return usd_qty * (price - self.entry_price) / self.entry_price
        else:
            return usd_qty * (self.entry_price - price) / self.entry_price

    def __repr__(self):
        return (f"<Position {self.side} entry={self.entry_price:.2f} "
                f"remaining=${self.remaining:.2f} tp_hit={self.tp_hit}>")


# ─────────────────────────── Bot ──────────────────────────
class TradingBot:

    def __init__(self):
        cfg             = CONFIG
        self.symbol     = cfg["symbol"]
        self.interval   = cfg["interval"]
        self.balance    = cfg["initial_balance"]

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
        fixed = CONFIG.get("fixed_trade_usd", 1000.0)
        return min(fixed, self.balance)

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _log(self, event: str, side: str, price: float,
             qty: float, pnl: float = 0.0, notes: str = ""):
        row = {
            "trade_id" : self.trade_id,
            "timestamp": self._now(),
            "symbol"   : self.symbol,
            "event"    : event,
            "side"     : side,
            "price"    : round(price, 2),
            "usd_qty"  : round(qty,   2),
            "pnl"      : round(pnl,   4),
            "total_pnl": round(self.total_pnl, 4),
            "balance"  : round(self.balance, 2),
            "notes"    : notes,
        }
        self.csv.write(row)
        self.sheets.append(row)
        self.telegram.send(row)
        log_event(logger, row)

    # ── open position ─────────────────────────────────────
    def _open(self, side: str, price: float):
        self.trade_id += 1
        size          = self._trade_size()
        self.position = Position(side, price, size)
        p             = self.position
        notes = (f"TP1={p.tp1:.2f}  TP2={p.tp2:.2f}  "
                 f"TP3={p.tp3:.2f}  SL={p.sl:.2f}")
        self._log(f"ENTRY_{side}", side, price, size, notes=notes)
        logger.info("▶ Opened %s @ %.2f  size=$%.2f", side, price, size)

    # ── partial exit ──────────────────────────────────────
    def _partial_exit(self, label: str, price: float, pct: float):
        p        = self.position
        exit_usd = p.remaining * (pct / 100)
        pnl      = p.calc_pnl(price, exit_usd)
        self.balance   += pnl
        self.total_pnl += pnl
        p.remaining    -= exit_usd
        self._log(label, p.side, price, exit_usd, pnl,
                  notes=f"remaining=${p.remaining:.2f}")
        logger.info("◑ %s @ %.2f  exit=$%.2f  P&L=$%.4f  bal=$%.2f",
                    label, price, exit_usd, pnl, self.balance)

    # ── full close ────────────────────────────────────────
    def _close(self, price: float, reason: str):
        p              = self.position
        pnl            = p.calc_pnl(price, p.remaining)
        self.balance  += pnl
        self.total_pnl += pnl
        self._log(reason, p.side, price, p.remaining, pnl,
                  notes=f"entry={p.entry_price:.2f}  exit={price:.2f}")
        logger.info("■ Closed %s @ %.2f  P&L=$%.4f  bal=$%.2f",
                    p.side, price, pnl, self.balance)
        self.position = None

    # ── check TP/SL on every price tick ──────────────────
    def _check_exits(self, price: float):
        p   = self.position
        cfg = CONFIG["risk"]

        if p.side == "LONG":
            # SL
            if price <= p.sl:
                self._close(price, "SL_HIT")
                return
            # TP1
            if p.tp_hit == 0 and price >= p.tp1:
                self._partial_exit("TP1_HIT", price, cfg["tp1_qty"])
                p.tp_hit = 1
            # TP2
            elif p.tp_hit == 1 and price >= p.tp2:
                self._partial_exit("TP2_HIT", price, cfg["tp2_qty"])
                p.tp_hit = 2
            # TP3 — close remaining
            elif p.tp_hit == 2 and price >= p.tp3:
                self._close(price, "TP3_HIT")

        else:  # SHORT
            if price >= p.sl:
                self._close(price, "SL_HIT")
                return
            if p.tp_hit == 0 and price <= p.tp1:
                self._partial_exit("TP1_HIT", price, cfg["tp1_qty"])
                p.tp_hit = 1
            elif p.tp_hit == 1 and price <= p.tp2:
                self._partial_exit("TP2_HIT", price, cfg["tp2_qty"])
                p.tp_hit = 2
            elif p.tp_hit == 2 and price <= p.tp3:
                self._close(price, "TP3_HIT")

    # ── main loop ─────────────────────────────────────────
    def run(self):
        logger.info("═══ Bot started  symbol=%s  tf=%s ═══",
                    self.symbol, self.interval)

        last_signal_ts = None

        while True:
            try:
                # 1. Fetch candles & compute signals
                df = fetch_klines(self.symbol, self.interval, limit=500)
                df = compute_signals(df)

                latest_ts    = df.iloc[-1]["close_time"]
                new_candle   = (latest_ts != last_signal_ts)
                long_signal  = bool(df.iloc[-1]["cross_long"])
                short_signal = bool(df.iloc[-1]["cross_short"])

                # 2. Real-time price
                price = fetch_price(self.symbol)

                # 3. Check TP/SL on open position every tick
                if self.position:
                    self._check_exits(price)

                # 4. New candle signal logic
                if new_candle:
                    last_signal_ts = latest_ts

                    if long_signal:
                        # Close SHORT (any remaining) then open LONG
                        if self.position and self.position.side == "SHORT":
                            self._close(price, "CLOSE_SHORT")
                        if not self.position:
                            self._open("LONG", price)

                    elif short_signal:
                        # Close LONG (any remaining) then open SHORT
                        if self.position and self.position.side == "LONG":
                            self._close(price, "CLOSE_LONG")
                        if not self.position:
                            self._open("SHORT", price)

                # 5. Heartbeat
                pos_info = (f"{self.position.side} @ "
                            f"{self.position.entry_price:.2f} "
                            f"tp={self.position.tp_hit}"
                            if self.position else "flat")
                logger.debug("tick price=%.2f  pos=%s  bal=$%.2f",
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


if __name__ == "__main__":
    bot = TradingBot()
    bot.run()