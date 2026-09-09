# -*- coding: utf-8 -*-
"""מדווח את הגדרות הדואר של האתר, ממוסכות.

**"נשלח" אינו "הגיע".** ב-28/08/2026 בדיקת הזרימה דיווחה שהמייל נשלח —
Resend החזיר 200 — ובכל זאת שום הודעה לא הגיעה ליואב, לא על בקשת גישה
ולא מהבדיקה עצמה. הודעה שמתקבלת בשער ונעלמת אחריו נראית מבחוץ בדיוק
כמו הודעה שנשלחה בהצלחה, ולכן צריך לראות **לאן** היא נשלחת.

שלוש התשובות שהדוח הזה מפריד ביניהן:
- OWNER_EMAIL מצביע על תיבה שאינה קיימת או שאינה נקראת (למשל כתובת
  בדומיין השירות שאין מאחוריה תיבה) — אז הכל "מצליח" והדואר נופל לתהום.
- דומיין השולח אינו מאומת ב-Resend, שמקבל את הבקשה ואינו מוסר אותה.
- המפתח כלל אינו מוגדר בסביבת הייצור.

הכתובות מוחזרות ממוסכות: מי שמכיר אותן יזהה, ומי שלא — לא ילמד מהן
דבר. הריפו ציבורי והאנוטציות גלויות.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
# שמות שהערך שלהם הוא כתובת — מוצג ממוסך. השאר: קיים / חסר בלבד.
# **ANTHROPIC_API_KEY נדרש גם בצד Cloudflare.** סקירת הדוח נוצרת
# בלחיצה, בתוך Function, ולכן היא קוראת למודל מסביבת Cloudflare ולא
# מהראנר. המפתח קיים בסודות GitHub — שם רצים הברייף והסיכומים — וזה
# אינו אותו מקום. בלעדיו הנתיב מחזיר 503 בכל לחיצה.
MAIL_KEYS = ("OWNER_EMAIL", "FROM_EMAIL", "RESEND_API_KEY", "SCAN_KEY",
             "APPROVAL_SECRET", "SESSION_SECRET", "ANTHROPIC_API_KEY")
ADDRESS_KEYS = ("OWNER_EMAIL", "FROM_EMAIL")


def mask_email(e: str) -> str:
    local, _, dom = (e or "").partition("@")
    if not dom:
        return "(אינה כתובת מייל)"
    keep = local[:2] if len(local) > 3 else local[:1]
    return f"{keep}{'*' * max(1, len(local) - len(keep))}@{dom}"


def main() -> int:
    token = os.environ.get("CF_TOKEN")
    account = os.environ.get("CF_ACCOUNT")
    project = os.environ.get("CF_PAGES_PROJECT", "forest-brief")
    if not token or not account:
        print("::warning::חסר CF_TOKEN או CF_ACCOUNT — הגדרות הדואר לא נבדקו")
        return 0

    req = urllib.request.Request(
        f"{API}/accounts/{account}/pages/projects/{project}",
        headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"::warning::קריאת הגדרות הפרויקט נכשלה: {e.code}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"::warning::קריאת הגדרות הפרויקט נכשלה: {type(e).__name__}")
        return 0

    cfg = ((data.get("result") or {}).get("deployment_configs") or {})
    env = (cfg.get("production") or {}).get("env_vars") or {}

    lines = []
    fail = 0
    for k in MAIL_KEYS:
        v = env.get(k)
        if v is None:
            lines.append(f"{k}: חסר")
            if k in ("OWNER_EMAIL", "RESEND_API_KEY"):
                fail = 1
            continue
        kind = v.get("type") or "?"
        val = v.get("value")
        if k in ADDRESS_KEYS and val:
            # FROM_EMAIL מגיע לרוב בצורה "שם <כתובת>"
            addr = val.split("<")[-1].rstrip(">").strip() if "<" in val else val
            lines.append(f"{k}: {mask_email(addr)}"
                         + ("" if kind == "plain_text" else f" ({kind})"))
        elif val is None:
            # ערך של secret_text אינו מוחזר ב-API — קיומו הוא כל מה שנדרש
            lines.append(f"{k}: מוגדר (סוד)")
        else:
            lines.append(f"{k}: מוגדר")

    print("הגדרות הדואר בייצור:")
    for l in lines:
        print(f"  {l}")
    print("::notice title=הגדרות הדואר::" + "%0A".join(lines))

    if "ANTHROPIC_API_KEY" not in env:
        print("::error title=סקירת הדוחות מושבתת::ANTHROPIC_API_KEY אינו "
              "מוגדר בסביבת Cloudflare, ולכן /api/review מחזיר 503 בכל "
              "לחיצה. המפתח שבסודות GitHub משמש את הברייף ואינו זמין "
              "ל-Functions.")

    own = (env.get("OWNER_EMAIL") or {}).get("value")
    frm = (env.get("FROM_EMAIL") or {}).get("value") or "noreply@tlvtaseview.com"
    if own and own.split("@")[-1] == frm.split("<")[-1].rstrip(">").split("@")[-1]:
        # תיבה בדומיין של השירות עצמו היא החשוד המרכזי: Resend מוסר
        # אליה, ואם לא הוגדרה מאחוריה תיבה בפועל ההודעה נעלמת בלי שגיאה.
        print("::warning title=כתובת היעד בדומיין השירות::"
              "OWNER_EMAIL נמצאת באותו דומיין שממנו נשלח הדואר. "
              "אם לא מוגדרת מאחוריה תיבה אמיתית, ההודעות מתקבלות ונעלמות "
              "בלי שגיאה. כדאי להצביע על כתובת חיצונית שנקראת בפועל.")
    return fail


if __name__ == "__main__":
    sys.exit(main())
