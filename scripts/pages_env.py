# -*- coding: utf-8 -*-
"""מציב משתנה סביבה מוצפן בפרויקט ה-Pages, דרך ה-API של Cloudflare.

**למה.** כפתור "הפק ברייף" צריך אסימון GitHub כדי לשגר ריצה מיד, והאסימון
חי בצד Cloudflare. הוספתו בדשבורד דורשת למצוא מסך ששינה את שמו (היום
"Variables and Secrets", לא "Environment variables"), ואת זה אפשר לחסוך:
הסוד נוסף ב-GitHub — ממשק מוכר — והריצה הזו מעבירה אותו הלאה.

**העברה ולא הדפסה.** הערך מגיע מסוד של Actions, נשלח ל-API, ואינו נכתב
לשום פלט. האימות בסוף בודק ששם המשתנה קיים ושסוגו מוצפן — לא את ערכו.

**PATCH חלקי בכוונה.** ה-API של Pages מוחק משתנה רק כשנשלח לו null עבורו,
ולכן שליחת מפתח אחד אינה נוגעת בשאר. GET-ואז-PUT היה מסוכן כאן: סודות
קיימים חוזרים מה-GET בלי ערך, והחזרתם הייתה מוחקת אותם.

שימוש: VAR_NAME=X VAR_VALUE=... python scripts/pages_env.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
PROJECT = os.environ.get("PAGES_PROJECT") or "forest-brief"
ENVIRONMENT = os.environ.get("PAGES_ENV") or "production"


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{API}/accounts/{os.environ.get('CF_ACCOUNT_ID', '')}{path}",
        method=method, data=data,
        headers={"Authorization": f"Bearer {os.environ.get('CF_API_TOKEN', '')}",
                 "User-Agent": "tlv-tase-view",
                 **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=40) as f:
            return f.status, json.loads(f.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace") or "{}")
        except ValueError:
            return e.code, {}
    except OSError as e:  # noqa: BLE001
        return 0, {"errors": [{"message": str(e)}]}


def errors(payload: dict) -> str:
    return "; ".join(str(e.get("message")) for e in payload.get("errors") or [])[:200]


def main() -> int:
    name = (os.environ.get("VAR_NAME") or "").strip()
    value = os.environ.get("VAR_VALUE") or ""
    if not name:
        print("::error::VAR_NAME חסר")
        return 2

    # בדיקה בלבד: האם המשתנה קיים. משמש את site-check כדי לדעת אם הכפתור
    # באתר משגר מיד או ממתין לתזמון — בלי לגעת בערך ובלי להזדקק לו.
    if os.environ.get("CHECK_ONLY"):
        code, body = call("GET", f"/pages/projects/{PROJECT}")
        cfg = (((body.get("result") or {}).get("deployment_configs") or {})
               .get(ENVIRONMENT) or {}).get("env_vars") or {}
        if code != 200:
            print(f"::warning title=בדיקת הפרויקט נכשלה::קוד {code} — {errors(body)}")
            return 0
        if cfg.get(name):
            print(f"::notice title=הכפתור משגר מיד::{name} מוגדר ב-{PROJECT}/{ENVIRONMENT}")
        else:
            print(f"::warning title=הכפתור ממתין לתזמון::{name} אינו מוגדר ב-{PROJECT}, "
                  "ולכן לחיצה נרשמת ל-KV ומחכה לפעימה של GitHub (שמאחרת שעות)")
        return 0

    if not value.strip():
        print(f"::error title=הסוד ריק::{name} אינו מוגדר כסוד ב-GitHub, "
              "ולכן אין מה להעביר ל-Cloudflare.")
        return 1
    if not (os.environ.get("CF_API_TOKEN") and os.environ.get("CF_ACCOUNT_ID")):
        print("::error::סודות Cloudflare חסרים")
        return 1

    code, body = call("PATCH", f"/pages/projects/{PROJECT}", {
        "deployment_configs": {ENVIRONMENT: {"env_vars": {
            name: {"type": "secret_text", "value": value},
        }}},
    })
    if code != 200 or not body.get("success"):
        print(f"::error title=ההצבה נכשלה::קוד {code} — {errors(body) or 'בלי פירוט'}")
        return 1

    # אימות: השם קיים וסוגו מוצפן. הערך עצמו אינו נקרא ואינו מודפס.
    code, body = call("GET", f"/pages/projects/{PROJECT}")
    cfg = (((body.get("result") or {}).get("deployment_configs") or {})
           .get(ENVIRONMENT) or {}).get("env_vars") or {}
    got = cfg.get(name)
    if not got:
        print(f"::error title=המשתנה אינו מופיע::{name} לא נמצא ב-{PROJECT}/{ENVIRONMENT} "
              "אחרי ההצבה")
        return 1
    print(f"::notice title=האסימון הוצב::{name} ({got.get('type')}) ב-{PROJECT}/{ENVIRONMENT}. "
          "הפריסה הבאה של האתר תשתמש בו, והכפתור יתחיל לשגר מיד.")
    print("משתנים בפרויקט: " + ", ".join(sorted(cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
