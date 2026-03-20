"""
setup_sheets.py
───────────────────────────────────────────────────────────────
Step-by-step Google Sheets setup helper.
Run this ONCE before starting the bot:

    python setup_sheets.py

It will:
  1. Print the exact steps to create a Google Service Account
  2. Test your credentials once you've saved the JSON file
  3. Verify the spreadsheet connection
───────────────────────────────────────────────────────────────
"""

import os
import sys

GUIDE = """
╔══════════════════════════════════════════════════════════════╗
║      GOOGLE SHEETS SETUP — Step by Step                      ║
╚══════════════════════════════════════════════════════════════╝

STEP 1 — Create a Google Cloud Project
──────────────────────────────────────
  1. Go to  https://console.cloud.google.com/
  2. Click "Select a project" → "New Project"
  3. Name it  sol-trader  → click "Create"

STEP 2 — Enable the Google Sheets & Drive APIs
───────────────────────────────────────────────
  1. In the left menu: APIs & Services → Library
  2. Search "Google Sheets API" → Enable
  3. Search "Google Drive API"  → Enable

STEP 3 — Create a Service Account
───────────────────────────────────
  1. APIs & Services → Credentials → Create Credentials
     → Service Account
  2. Name it  sol-trader-bot  → Done
  3. Click the service account email → Keys tab
     → Add Key → Create New Key → JSON
  4. A JSON file downloads automatically — this is your key!

STEP 4 — Save credentials to this project
──────────────────────────────────────────
  mkdir credentials
  mv ~/Downloads/your-key-file.json  credentials/service_account.json

STEP 5 — Create your Google Sheet
───────────────────────────────────
  1. Go to https://sheets.google.com → Create a blank sheet
  2. Name it  SOL Trades
  3. Copy the Spreadsheet ID from the URL:
       https://docs.google.com/spreadsheets/d/ >>>ID_IS_HERE<<< /edit
  4. Share the sheet with the service account email
     (found in credentials/service_account.json → "client_email")
     Give it  Editor  access.

STEP 6 — Update config.py
──────────────────────────
  Open config.py and set:
    "spreadsheet_id" : "YOUR_COPIED_ID_HERE"

STEP 7 — Test (run this script again)
───────────────────────────────────────
  python setup_sheets.py --test
"""


def test_connection():
    print("\n🔍 Testing Google Sheets connection...\n")

    cred_path = "credentials/service_account.json"
    if not os.path.exists(cred_path):
        print(f"  ✗  Credentials file not found at: {cred_path}")
        print("     → Follow STEP 4 above first.")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("  ✗  Missing libraries. Install with:")
        print("     pip install gspread google-auth")
        return False

    # Load creds
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        creds = Credentials.from_service_account_file(cred_path, scopes=scopes)
        gc    = gspread.authorize(creds)
        print(f"  ✓  Service account authenticated")
        print(f"     email: {creds.service_account_email}")
    except Exception as e:
        print(f"  ✗  Auth failed: {e}")
        return False

    # Load config
    try:
        from config import CONFIG
        sid = CONFIG["google_sheets"]["spreadsheet_id"]
        if sid == "YOUR_SPREADSHEET_ID_HERE":
            print("\n  ✗  spreadsheet_id not set in config.py")
            print("     → Follow STEP 6 above.")
            return False
    except ImportError:
        print("  ✗  config.py not found — run from the sol_trader/ directory")
        return False

    # Open sheet
    try:
        sh = gc.open_by_key(sid)
        print(f"  ✓  Spreadsheet opened: '{sh.title}'")
    except Exception as e:
        print(f"  ✗  Could not open spreadsheet: {e}")
        print("     → Check STEP 5 (share the sheet with the service account email)")
        return False

    # Write test row
    try:
        from config import CSV_COLUMNS
        ws_name = CONFIG["google_sheets"]["worksheet_name"]
        try:
            ws = sh.worksheet(ws_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=ws_name, rows=5000, cols=len(CSV_COLUMNS))
            ws.append_row(CSV_COLUMNS)
            print(f"  ✓  Created worksheet '{ws_name}' with headers")

        ws.append_row(["TEST", "connection_ok", "", "", "", "", "", "", "", ""])
        print(f"  ✓  Test row written to worksheet '{ws_name}'")
    except Exception as e:
        print(f"  ✗  Write test failed: {e}")
        return False

    print("\n  🎉  Everything works! You can now run:  python bot.py\n")
    return True


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_connection()
    else:
        print(GUIDE)
        print("\nWhen ready, run:  python setup_sheets.py --test\n")
