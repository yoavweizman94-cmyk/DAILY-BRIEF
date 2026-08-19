#!/usr/bin/env python3
"""ניהול רשימת המורשים ב-Cloudflare Access.

ה-Function שבאתר (site/functions/api/approve.js) יודעת רק להוסיף כתובת.
הסרה נדרשת כשמנוי מסתיים, כשכתובת נוספה בטעות, או כשמישהו לחץ על קישור
אישור שלא היה אמור להילחץ — ואין לה מסלול באתר עצמו.

שימוש:
    ACTION=list   python scripts/access_members.py
    ACTION=remove TARGET=someone@example.com python scripts/access_members.py

דורש CF_TOKEN, CF_ACCOUNT, APP_ID בסביבה.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_ROOT = "https://api.cloudflare.com/client/v4"


def call(url, tok, method="GET", body=None):
    req = urllib.request.Request(
        url,
        method=method,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print(f"::error::Cloudflare החזיר {e.code}: {detail}")
        sys.exit(1)


def emails(rules):
    return [r["email"]["email"] for r in rules if r.get("email", {}).get("email")]


def main():
    tok = os.environ["CF_TOKEN"]
    acc = os.environ["CF_ACCOUNT"]
    app = os.environ["APP_ID"]
    action = os.environ.get("ACTION", "list")
    target = os.environ.get("TARGET", "").strip().lower()
    api = f"{API_ROOT}/accounts/{acc}/access/apps/{app}/policies"

    pols = call(api, tok).get("result") or []
    if not pols:
        print("::error::לא נמצאה מדיניות Access לאפליקציה הזו")
        return 1
    pol = pols[0]
    inc = pol.get("include") or []

    print(f"מדיניות: {pol['name']}  ·  decision={pol['decision']}")
    print(f"כתובות ברשימה: {len(emails(inc))}")
    for a in emails(inc):
        print(f"  · {a}")
    other = [r for r in inc if not r.get("email", {}).get("email")]
    if other:
        print(f"  ({len(other)} כללים שאינם כתובת בודדת — דומיין או קבוצה — לא נגענו בהם)")

    if action != "remove":
        return 0
    if not target:
        print("::error::action=remove דורש כתובת ב-TARGET")
        return 1
    if target not in emails(inc):
        print(f"::warning::{target} אינה ברשימה — אין מה להסיר")
        return 0

    kept = [r for r in inc if r.get("email", {}).get("email") != target]
    # מדיניות בלי אף כלל include אינה מצב שכדאי להגיע אליו בהרצה אוטומטית:
    # תלוי בספק היא נועלת את כולם או פותחת לכולם. עוצרים לפני.
    if not kept:
        print("::error::זו הרשומה האחרונה; הסרתה הייתה משאירה מדיניות ריקה. בוטל.")
        return 1

    call(f"{api}/{pol['id']}", tok, "PUT",
         {"name": pol["name"], "decision": pol["decision"], "include": kept})

    # אימות מול השרת ולא הנחה שה-PUT תפס
    after = emails((call(api, tok).get("result") or [{}])[0].get("include") or [])
    print(f"\nאחרי ההסרה — {len(after)} כתובות:")
    for a in after:
        print(f"  · {a}")
    if target in after:
        print(f"::error::{target} עדיין ברשימה — ההסרה לא נתפסה")
        return 1
    print(f"\n{target} הוסרה, ואומת מול השרת שאיננה.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
