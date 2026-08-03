# -*- coding: utf-8 -*-
"""אימות Gmail חד-פעמי (מקומי, פותח דפדפן) — מייצר token.json ומדפיס את הערך
שיש לשים ב-GitHub Secret בשם GMAIL_CREDENTIALS.

הכנה (פעם אחת):
1. Google Cloud Console → פרויקט חדש → הפעלת Gmail API.
2. OAuth consent screen (External, מצב Testing מספיק) + הוספת המייל שלך כ-Test user.
3. Credentials → Create OAuth client ID → Desktop app → הורדת JSON
   ושמירה כ-credentials.json בשורש הפרויקט (מוחרג מ-git).
4. python scripts/gmail_authorize.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
# _tls is added to sys.path dynamically at runtime.
from _tls import harden  # type: ignore[import-not-found]
harden()

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("pip install google-auth-oauthlib", file=sys.stderr)
        return 1

    secrets = ROOT / "credentials.json"
    if not secrets.exists():
        print("שגיאה: אין credentials.json בשורש — ראה הוראות בראש הקובץ", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    creds = flow.run_local_server(port=0)

    (ROOT / "token.json").write_text(creds.to_json(), encoding="utf-8")
    print("נכתב token.json (לשימוש מקומי)\n")

    secret_value = json.dumps({
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
    })
    print("ערך ל-GitHub Secret בשם GMAIL_CREDENTIALS:\n")
    print(secret_value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
