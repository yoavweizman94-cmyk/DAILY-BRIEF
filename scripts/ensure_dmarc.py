# -*- coding: utf-8 -*-
"""מוודא שרשומת DMARC קיימת בדומיין, ויוצר אותה אם לא.

**למה זה קוד ולא הוראה.** ההודעות שהשירות שולח — בקשת גישה חדשה,
התראת טריות — יוצאות מ-`noreply@tlvtaseview.com` אל תיבת Gmail, ו-Resend
מחזיר עליהן 200. הן פשוט לא הגיעו. DKIM ו-SPF היו מוגדרים כראוי; מה
שחסר היה DMARC, ו-Gmail מסנן בחומרה דואר מדומיינים צעירים בלי הרשומה
הזו. הוראה ידנית להוסיף רשומת DNS היא בדיוק סוג הדבר שנשכח או מוקלד
לא נכון — ראו את שלוש הווריאציות השגויות שנבדקו — ולכן היא נכתבת כאן
כפעולה שמריצים ומאמתים.

`p=none` בכוונה: זו מדיניות ניטור בלבד. היא מספיקה כדי לעבור את הסף
של Gmail ואינה יכולה להפיל מסירה של דואר קיים, בשונה מ-quarantine או
reject. החמרה היא החלטה נפרדת שנעשית אחרי שרואים דוחות.

הפעולה אידמפוטנטית: רשומה תקינה שכבר קיימת אינה נדרסת.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
APEX = os.environ.get("DMARC_DOMAIN", "tlvtaseview.com")
NAME = f"_dmarc.{APEX}"
VALUE = "v=DMARC1; p=none;"


def call(method: str, path: str, payload=None):
    token = os.environ["CF_TOKEN"]
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:  # noqa: BLE001
            return e.code, {}


def errors(body) -> str:
    return "; ".join(str(e.get("message")) for e in (body or {}).get("errors") or []) or "—"


def main() -> int:
    if not os.environ.get("CF_TOKEN"):
        print("::warning::חסר CF_TOKEN — רשומת ה-DMARC לא נבדקה")
        return 0

    code, d = call("GET", f"/zones?name={APEX}")
    if code != 200 or not (d.get("result") or []):
        print(f"::error::לא נמצא אזור DNS עבור {APEX}: {code} {errors(d)}")
        return 1
    zid = d["result"][0]["id"]

    code, recs = call("GET", f"/zones/{zid}/dns_records?type=TXT&name={NAME}")
    if code != 200:
        print(f"::error::קריאת רשומות ה-DNS נכשלה: {code} {errors(recs)}")
        return 1

    existing = recs.get("result") or []
    for r in existing:
        content = (r.get("content") or "").strip().strip('"')
        if content.lower().startswith("v=dmarc1"):
            print(f"::notice title=DMARC::הרשומה כבר קיימת — {content}")
            return 0

    code, r = call("POST", f"/zones/{zid}/dns_records", {
        "type": "TXT", "name": NAME, "content": VALUE, "ttl": 3600,
        "comment": "נוצר אוטומטית: בלעדיה Gmail סינן את התראות השירות",
    })
    if not (200 <= code < 300) and not (r or {}).get("success"):
        # 81058 = רשומה זהה כבר קיימת. אינה שגיאה מבחינתנו.
        if any(e.get("code") == 81058 for e in (r or {}).get("errors") or []):
            print("::notice title=DMARC::רשומה זהה כבר קיימת")
            return 0
        print(f"::error title=יצירת DMARC נכשלה::{code} {errors(r)}")
        return 1

    print(f"::notice title=DMARC::הרשומה נוצרה — {NAME} → {VALUE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
