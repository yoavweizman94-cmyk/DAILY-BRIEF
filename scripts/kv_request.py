# -*- coding: utf-8 -*-
"""לחיצות "הפק" ב-KV של האתר: לקוח קטן, ובדיקת התור של brief-request.yml.

**למה KV.** כפתור "הפק ברייף" באתר רץ ב-Cloudflare Pages. שיגור workflow_dispatch
משם דורש אסימון GitHub, ובלעדיו (או כשהוא פג) הלחיצה נשמרת כאן. האסימון של
Cloudflare כבר קיים כסוד בריפו, ולכן הצנרת קוראת את ה-KV ישירות.

**שני מפתחות, וכל צד כותב רק לשלו.**
· `brief:request` — הלחיצה האחרונה: {edition, at, by}. הכפתור כותב אותה בכל לחיצה,
  לפני השיגור, לארבע שעות (site/functions/api/brief.js).
· `brief:request:done` — ה-at של הלחיצה האחרונה שבוצעה. כותבת אותו רק הריצה שתובעת
  את הלחיצה, וזו מחזיקה באותו רגע את המקום היחיד ב-concurrency של daily-brief
  (scripts/brief_claim.py).
לחיצה **ממתינה** כל עוד ה-at שלה חדש מזה שב-done, והיא בת פחות מ-MAX_AGE_MIN.

**הבקשה כבר אינה נמחקת בתביעה (13/11/2026).** עד אז הפעימה כאן מחקה אותה ואז הפעילה
את הברייף, אבל הריצה שנקראה מכאן חיכתה בתור של daily-brief — ו-GitHub מבטל ממתינה
כשמגיעה חדשה. בקשה שכבר נמחקה אבדה איתה. סימון ב-done במקום מחיקה סוגר גם מרוץ
שני: לחיצה חדשה שנכתבת בין הקריאה למחיקה הייתה נמחקת בלי שהופקה.

הרצה ישירה היא הבדיקה של brief-request.yml: מציצה, ואינה תובעת. פלט: שורות
KEY=value ל-$GITHUB_OUTPUT (או ל-stdout בהרצה מקומית).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.cloudflare.com/client/v4"
NS_TITLE = os.environ.get("KV_TITLE") or "tlv-tase-view-users"
KEY = os.environ.get("KV_KEY") or "brief:request"
DONE_KEY = KEY + ":done"
# הבדיקה העצמית כותבת למפתח משלה: עד 13/11 היא כתבה ומחקה את `brief:request`
# עצמו, ולחיצה אמיתית שחיכתה שם הייתה נמחקת בבדיקה.
SELFTEST_KEY = KEY + ":selftest"
MAX_AGE_MIN = int(os.environ.get("KV_MAX_AGE_MIN") or 240)
EDITIONS = ("", "morning", "midday", "close", "night")


def call(path: str, method: str = "GET", body: str | None = None) -> tuple[int, str]:
    token = os.environ.get("CF_API_TOKEN") or ""
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "tlv-tase-view"}
    if body is not None:
        headers["Content-Type"] = "text/plain"
    req = urllib.request.Request(f"{API}/accounts/{os.environ.get('CF_ACCOUNT_ID', '')}{path}",
                                 method=method, headers=headers,
                                 data=body.encode("utf-8") if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            return f.status, f.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except OSError as e:  # noqa: BLE001
        return 0, str(e)


# --- KV --------------------------------------------------------------------
def configured() -> bool:
    return bool(os.environ.get("CF_API_TOKEN") and os.environ.get("CF_ACCOUNT_ID"))


def namespace() -> tuple[str | None, int]:
    """(מזהה מרחב השמות, קוד התשובה). None כשאינו ברשימה או שהקריאה נכשלה."""
    code, body = call("/storage/kv/namespaces?per_page=100")
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    ns = next((n["id"] for n in (data.get("result") or [])
               if n.get("title") == NS_TITLE), None)
    return ns, code


def _path(ns: str, key: str) -> str:
    return f"/storage/kv/namespaces/{ns}/values/{urllib.parse.quote(key, safe='')}"


def get_json(ns: str, key: str) -> tuple[bool, dict | None]:
    """(הקריאה הצליחה, הערך). מפתח שאינו קיים הוא הצלחה עם None; ערך שאינו JSON — {}."""
    code, body = call(_path(ns, key))
    if code == 404 or (code == 200 and not body.strip()):
        return True, None
    if code != 200:
        return False, None
    try:
        val = json.loads(body)
    except ValueError:
        return True, {}
    return True, val if isinstance(val, dict) else {}


def put_json(ns: str, key: str, value: dict, ttl: int | None = None) -> bool:
    q = f"?expiration_ttl={int(ttl)}" if ttl else ""
    code, _ = call(_path(ns, key) + q, "PUT", json.dumps(value, ensure_ascii=False))
    return code in (200, 201, 204)


def delete(ns: str, key: str) -> bool:
    code, _ = call(_path(ns, key), "DELETE")
    return code in (200, 204, 404)


# --- הלוגיקה, בלי רשת -----------------------------------------------------
def parse_at(value) -> datetime | None:
    """חותמת ISO של הלחיצה (toISOString של הדפדפן: Z ואלפיות) כ-UTC, או None."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def edition_of(req: dict | None) -> str:
    ed = str((req or {}).get("edition") or "").strip()
    return ed if ed in EDITIONS else ""


def pending(req: dict | None, done: dict | None, now: datetime,
            max_age_min: int = MAX_AGE_MIN) -> tuple[bool, str]:
    """(ממתינה, למה לא). הסיבות: empty / bad / stale / done."""
    if not req:
        return False, "empty"
    t = parse_at(req.get("at"))
    if t is None:
        return False, "bad"
    if now - t > timedelta(minutes=max_age_min):
        return False, "stale"
    d = parse_at((done or {}).get("at"))
    if d is not None and t <= d:
        return False, "done"
    return True, ""


def age_min(req: dict | None, now: datetime) -> float:
    t = parse_at((req or {}).get("at"))
    return max((now - t).total_seconds() / 60, 0.0) if t else 0.0


# --- הבדיקה של brief-request.yml -----------------------------------------
def out(**kw) -> None:
    lines = "".join(f"{k}={v}\n" for k, v in kw.items())
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(lines)
    sys.stdout.write(lines)


def selftest(ns: str, seed: str) -> None:
    """כתיבה, קריאה ומחיקה — מה שהכפתור והתביעה עושים — על מפתח בדיקה נפרד."""
    payload = {"edition": "" if seed == "-" else seed,
               "at": datetime.now(timezone.utc).isoformat(), "by": "self-test"}
    if not put_json(ns, SELFTEST_KEY, payload, ttl=600):
        print("::error title=כתיבה ל-KV נכשלה::הכפתור באתר לא יוכל לרשום לחיצה, "
              "והריצה לא תוכל לסמן לחיצה שבוצעה")
        return
    ok, back = get_json(ns, SELFTEST_KEY)
    gone = delete(ns, SELFTEST_KEY)
    if ok and back and back.get("at") == payload["at"] and gone:
        print(f"::notice title=מסלול הכפתור תקין::כתיבה, קריאה ומחיקה ב-KV עברו "
              f"(מהדורת {payload['edition'] or 'לפי השעה'}, מפתח בדיקה — בלי הפקה)")
    else:
        print(f"::error title=בדיקת KV נכשלה::קריאה {'עברה' if ok and back else 'נכשלה'}, "
              f"מחיקה {'עברה' if gone else 'נכשלה'}")


def main() -> int:
    if not configured():
        print("::warning title=אין גישה ל-KV::סודות Cloudflare חסרים — "
              "לחיצה שנשמרה בתור לא תיבדק כאן")
        out(run="false")
        return 0

    ns, code = namespace()
    if not ns:
        print(f"::warning title=KV לא נמצא::מרחב השמות {NS_TITLE} אינו ברשימה (קוד {code})")
        out(run="false")
        return 0

    # **בדיקה עצמית** מקובץ הטריגר: {"seed": "midday"} בודק את ההרשאות של המסלול
    # כולו בלי להפיק מהדורה ובלי לשלם עליה.
    seed = (os.environ.get("KV_SEED") or "").strip()
    if seed:
        selftest(ns, seed)
        out(run="false")
        return 0

    ok_req, req = get_json(ns, KEY)
    ok_done, done = get_json(ns, DONE_KEY)
    if not (ok_req and ok_done):
        print("::warning title=קריאת התור נכשלה::לחיצה ממתינה, אם יש, תיבדק בריצה הבאה")
        out(run="false")
        return 0

    now = datetime.now(timezone.utc)
    is_pending, why = pending(req, done, now)
    if not is_pending:
        if why == "stale":
            print(f"::notice title=לחיצה ישנה::הלחיצה בת {age_min(req, now):.0f} דקות "
                  f"(מעל {MAX_AGE_MIN}) — לא מבוצעת")
        elif why == "bad":
            print("::warning title=לחיצה לא קריאה::בתור יש רשומה בלי שעת לחיצה תקינה — מתעלמים")
        out(run="false")
        return 0

    edition = edition_of(req)
    at = str(req.get("at"))
    print(f"::notice title=לחיצה ממתינה::מהדורת {edition or 'לפי השעה'}, לפני "
          f"{age_min(req, now):.0f} דקות — נקראת הריצה, והיא תתבע את הלחיצה כשתקבל את מקומה")
    out(run="true", edition=edition, at=at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
