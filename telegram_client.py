"""
telegram_client.py — Send trade alerts to your phone via Telegram.

Setup (2 minutes):
  1. Open Telegram → search @BotFather → send /newbot → copy TOKEN
  2. Search @userinfobot → send /start → copy your CHAT ID
  3. Paste both into config.py under "telegram"
"""

import requests
import logging

logger = logging.getLogger("bot")

EMOJI = {
    "ENTRY_LONG"     : "🟢",
    "ENTRY_SHORT"    : "🔴",
    "TP1_HIT"        : "💰",
    "TP2_HIT"        : "💰💰",
    "TP3_HIT"        : "💰💰💰",
    "SL_HIT"         : "🛑",
    "FULL_EXIT"      : "✅",
    "REVERSAL_CLOSE" : "🔄",
}


class TelegramClient:

    def __init__(self, token: str, chat_id: str):
        self._token   = token
        self._chat_id = str(chat_id)
        self._enabled = bool(
            token and chat_id
            and token   != "YOUR_BOT_TOKEN"
            and chat_id != "YOUR_CHAT_ID"
        )
        if self._enabled:
            logger.info("✅ Telegram connected — alerts will be sent to your phone")
        else:
            logger.warning(
                "Telegram not configured — add token & chat_id to config.py"
            )

    def send(self, row: dict):
        """Format and send a trade event as a Telegram message."""
        if not self._enabled:
            return
        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            requests.post(url, json={
                "chat_id"    : self._chat_id,
                "text"       : self._format(row),
                "parse_mode" : "HTML",
            }, timeout=10, verify=False)
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)

    def _format(self, row: dict) -> str:
        event    = row.get("event", "")
        emoji    = EMOJI.get(event, "📊")
        pnl      = row.get("pnl", 0)
        pnl_icon = "📈" if pnl > 0 else "📉" if pnl < 0 else ""
        pnl_str  = f"{pnl_icon} +${pnl:.2f}" if pnl > 0 else \
                   f"{pnl_icon} -${abs(pnl):.2f}" if pnl < 0 else "—"

        lines = [
            f"{emoji} <b>{event}</b>",
            f"━━━━━━━━━━━━━━━━",
            f"💱 Symbol  : <b>{row.get('symbol', 'SOLUSDT')}</b>",
            f"📍 Side    : <b>{row.get('side', '—')}</b>",
            f"💵 Price   : <b>${row.get('price', 0):.4f}</b>",
            f"📦 Qty     : <b>${row.get('usd_qty', 0):.2f}</b>",
        ]
        if pnl != 0:
            lines.append(f"💹 P&amp;L    : <b>{pnl_str}</b>")
        lines.append(f"🏦 Balance : <b>${row.get('balance', 0):.2f}</b>")
        if row.get("notes"):
            lines += [f"━━━━━━━━━━━━━━━━", f"📝 {row.get('notes')}"]
        lines += [f"━━━━━━━━━━━━━━━━", f"🕐 {row.get('timestamp', '')}"]
        return "\n".join(lines)