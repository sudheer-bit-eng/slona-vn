"""
sheets.py — Push trade rows to Google Sheets in real time.

Uses the gspread library + a Google Service Account JSON key.
Falls back to NO-OP logging if credentials are missing so the
bot still runs without Sheets configured.
"""

import logging
import os
from config import CONFIG, CSV_COLUMNS

logger = logging.getLogger("bot")


class SheetsClient:

    def __init__(self):
        self._gc        = None
        self._worksheet = None
        self._enabled   = False
        self._setup()

    def _setup(self):
        cfg  = CONFIG["google_sheets"]
        cred = cfg["credentials_file"]
        sid  = cfg["spreadsheet_id"]

        if sid == "YOUR_SPREADSHEET_ID_HERE":
            logger.warning(
                "Google Sheets not configured — "
                "set spreadsheet_id in config.py  (trades will still be saved to CSV)"
            )
            return

        if not os.path.exists(cred):
            logger.warning(
                "Credentials file not found at '%s' — Sheets disabled", cred
            )
            return

        try:
            import gspread  # type: ignore
            from google.oauth2.service_account import Credentials  # type: ignore

            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds          = Credentials.from_service_account_file(cred, scopes=scopes)
            self._gc       = gspread.authorize(creds)
            sh             = self._gc.open_by_key(sid)

            # open or create worksheet
            ws_name = cfg["worksheet_name"]
            try:
                self._worksheet = sh.worksheet(ws_name)
            except gspread.WorksheetNotFound:
                self._worksheet = sh.add_worksheet(
                    title=ws_name, rows=5000, cols=len(CSV_COLUMNS)
                )
                # write header
                self._worksheet.append_row(CSV_COLUMNS)

            self._enabled = True
            logger.info("✅ Google Sheets connected — spreadsheet id: %s", sid)

        except ImportError:
            logger.warning(
                "gspread / google-auth not installed. "
                "Run:  pip install gspread google-auth"
            )
        except Exception as e:
            logger.warning("Google Sheets setup failed: %s", e)

    def append(self, row: dict):
        """Append one trade row. Silent no-op if Sheets disabled."""
        if not self._enabled or self._worksheet is None:
            return
        try:
            values = [str(row.get(col, "")) for col in CSV_COLUMNS]
            self._worksheet.append_row(values)
        except Exception as e:
            logger.warning("Sheets append failed: %s", e)
