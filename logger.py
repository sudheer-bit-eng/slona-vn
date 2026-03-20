"""
logger.py — Coloured console + file logging.
"""

import logging
import sys
import os

# ANSI colour codes
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

EVENT_COLOURS = {
    "ENTRY_LONG"      : GREEN,
    "ENTRY_SHORT"     : RED,
    "TP1_HIT"         : CYAN,
    "TP2_HIT"         : CYAN,
    "TP3_HIT"         : CYAN,
    "SL_HIT"          : RED,
    "FULL_EXIT"       : YELLOW,
    "REVERSAL_CLOSE"  : YELLOW,
}


class ColouredFormatter(logging.Formatter):
    LEVEL_COLOURS = {
        logging.DEBUG   : "\033[90m",   # grey
        logging.INFO    : "\033[97m",   # white
        logging.WARNING : YELLOW,
        logging.ERROR   : RED,
        logging.CRITICAL: RED,
    }

    def format(self, record):
        col = self.LEVEL_COLOURS.get(record.levelno, "")
        record.msg = f"{col}{record.msg}{RESET}"
        return super().format(record)


def setup_logger(name: str, log_file: str) -> logging.Logger:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(ColouredFormatter(
        fmt="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S"
    ))

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


def log_event(logger: logging.Logger, row: dict):
    """Pretty-print a trade event row."""
    event  = row.get("event", "")
    colour = EVENT_COLOURS.get(event, "")
    pnl    = row.get("pnl", 0)
    pnl_str = f"P&L=${pnl:+.4f}" if pnl != 0 else ""

    logger.info(
        "%s%-18s%s  price=%-10.4f  qty=$%-8.2f  bal=$%-10.2f  %s",
        colour, event, "\033[0m",
        row.get("price", 0),
        row.get("usd_qty", 0),
        row.get("balance", 0),
        pnl_str,
    )
