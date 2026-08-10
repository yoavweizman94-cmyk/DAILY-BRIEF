# -*- coding: utf-8 -*-
"""משיכת מיילים מלייבל "ברייף" ב-Gmail וחילוץ טקסט נקי.

אימות (אחד מהשניים):
1. GMAIL_CREDENTIALS בסביבה — JSON עם client_id, client_secret, refresh_token
   (OAuth של אפליקציית Desktop עם scope gmail.readonly). זה המסלול ב-CI.
2. מקומית: קובץ token.json בשורש (נוצר ע"י scripts/gmail_authorize.py).

פלט: data/raw/<YYYY-MM-DD>/gmail.jsonl — שורה למייל: {id, ts, title, body, url, source}
"""
from __future__ import annotations

import base64
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden
harden()

import yaml

from _env import load_env
from _state import connect, filter_new
from _text import clean_html

load_env()

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_service():
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit(
            "שגיאה: חבילות Google חסרות — pip install google-api-python-client google-auth")

    raw = (os.environ.get("GMAIL_CREDENTIALS") or "").strip().lstrip("﻿")
    token_file = ROOT / "token.json"
    if raw:
        # נוחות: אם הודבק נתיב לקובץ במקום תוכנו, נקרא אותו
        if not raw.startswith("{") and Path(raw).is_file():
            raw = Path(raw).read_text(encoding="utf-8-sig").strip()
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as ex:
            # אבחון בלי לחשוף את הסוד עצמו
            raise SystemExit(
                f"שגיאה: GMAIL_CREDENTIALS אינו JSON תקין ({ex.msg}). "
                f"אורך הערך {len(raw)} תווים, מתחיל ב-'{'{' if raw.startswith('{') else raw[:1]}'. "
                "הערך צריך להיות שורה אחת בצורה "
                '{"client_id":"...","client_secret":"...","refresh_token":"..."} — '
                "הפק אותה עם scripts/gmail_authorize.py והדבק את התוכן, לא את נתיב הקובץ.")
        missing = [k for k in ("client_id", "client_secret", "refresh_token")
                   if not info.get(k)]
        if missing:
            raise SystemExit(f"שגיאה: ב-GMAIL_CREDENTIALS חסרים השדות: {', '.join(missing)}")
        creds = Credentials(None, refresh_token=info["refresh_token"],
                            token_uri=TOKEN_URI, client_id=info["client_id"],
                            client_secret=info["client_secret"], scopes=SCOPES)
    elif token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    else:
        raise SystemExit(
            "שגיאה: אין אימות Gmail — הגדר GMAIL_CREDENTIALS או הרץ scripts/gmail_authorize.py")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def find_label_id(svc, name: str) -> str:
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    for lb in labels:
        if lb["name"] == name:
            return lb["id"]
    raise SystemExit(f"שגיאה: לייבל '{name}' לא קיים ב-Gmail — יש ליצור אותו")


def walk_parts(payload: dict):
    stack = [payload]
    while stack:
        part = stack.pop()
        if part.get("parts"):
            stack.extend(part["parts"])
        else:
            yield part


def extract_body(payload: dict) -> str:
    plain, html = None, None
    for part in walk_parts(payload):
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        text = base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
        mime = part.get("mimeType", "")
        if mime == "text/plain" and plain is None:
            plain = text
        elif mime == "text/html" and html is None:
            html = text
    if plain and plain.strip():
        return clean_html(plain)              # מנקה גם ישויות HTML בטקסט
    return clean_html(html or "")


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    gcfg = cfg["gmail"]
    lookback = int(cfg["params"].get("lookback_hours", 24))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback)

    svc = get_service()
    label_id = find_label_id(svc, gcfg["label"])
    cap = int(gcfg.get("max_messages", 50))
    days_back = max(1, (lookback + 23) // 24) + 1     # שוליים — סינון מדויק בהמשך

    # שני מסלולים: מה שתויג ידנית ללייבל, ובנוסף שולחים קבועים מהקונפיג.
    # שאילתות נפרדות ולא OR אחד — שם לייבל בעברית בתוך q מועד לתקלות escaping.
    ids: list[str] = []
    seen_ids: set[str] = set()

    def collect(**kw):
        resp = svc.users().messages().list(userId="me", maxResults=cap, **kw).execute()
        for m in resp.get("messages", []):
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                ids.append(m["id"])

    collect(labelIds=[label_id], q=f"newer_than:{days_back}d")
    senders = [s for s in (gcfg.get("senders") or []) if s]
    if senders:
        from_q = " OR ".join(f"from:{s}" for s in senders)
        collect(q=f"newer_than:{days_back}d ({from_q})")

    skip_prefixes = tuple(gcfg.get("skip_subject_prefixes") or [])
    skipped = 0
    rows = []
    for mid in ids:
        msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)
        if ts < cutoff:
            continue
        headers = {h["name"].lower(): h["value"]
                   for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "(ללא נושא)")
        if skip_prefixes and subject.strip().startswith(skip_prefixes):
            skipped += 1
            continue
        rows.append({
            "id": mid,
            "ts": ts.isoformat(timespec="seconds"),
            "title": subject,
            "body": extract_body(msg.get("payload", {})),
            "url": f"https://mail.google.com/mail/u/0/#all/{mid}",
            "source": f"gmail:{headers.get('from', '?')}",
        })

    con = connect()
    fresh = filter_new(con, "gmail", [r["id"] for r in rows])
    con.close()

    out_dir = ROOT / "data" / "raw" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gmail.jsonl"
    n = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            if r["id"] in fresh:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
    print(f"נכתב {out_path} | {len(rows)} מיילים בחלון, {n} חדשים"
          + (f", {skipped} אישורי הרשמה סוננו" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
