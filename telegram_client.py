"""
telegram_client.py — Send trade alerts to your phone via Telegram.
"""
import requests
import logging

logger = logging.getLogger("bot")

EMOJI = {
    "ENTRY_LONG"  : "🟢",
    "ENTRY_SHORT" : "🔴",
    "TP1_HIT"     : "💰",
    "TP2_HIT"     : "💰💰",
    "TP3_HIT"     : "💰💰💰",
    "SL_HIT"      : "🛑",
    "CLOSE_LONG"  : "🔄",
    "CLOSE_SHORT" : "🔄",
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
            logger.warning("Telegram not configured — add token & chat_id to config.py")

    def send(self, row: dict):
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
        event     = row.get("event", "")
        emoji     = EMOJI.get(event, "📊")
        pnl       = row.get("pnl", 0)
        total_pnl = row.get("total_pnl", 0)
        balance   = row.get("balance", 0)
        fixed     = 1000.0

        def fmt(val):
            if val > 0:   return f"📈 +${val:.2f}"
            elif val < 0: return f"📉 -${abs(val):.2f}"
            else:         return "—"

        lines = [
            f"{emoji} <b>{event}</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"💱 Symbol      : <b>{row.get('symbol','BTCUSDT')}</b>",
            f"📍 Side        : <b>{row.get('side','—')}</b>",
            f"💵 Price       : <b>${row.get('price', 0):,.2f}</b>",
            f"📦 Trade Size  : <b>${row.get('usd_qty', 0):.2f}</b>",
        ]

        if pnl != 0:
            lines.append(f"💹 Trade P&amp;L : <b>{fmt(pnl)}</b>")

        lines += [
            f"📊 Total P&amp;L : <b>{fmt(total_pnl)}</b>",
            f"🏦 Balance     : <b>${balance:,.2f}</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
        ]

        if balance >= fixed:
            lines.append(f"🎯 Next Trade  : <b>${fixed:.2f}</b> (fixed)")
        else:
            lines.append(f"⚠️ Next Trade  : <b>${min(fixed,balance):.2f}</b> (balance low)")

        if row.get("notes"):
            lines.append(f"📝 {row.get('notes')}")

        lines.append(f"🕐 {row.get('timestamp', '')}")
        return "\n".join(lines)