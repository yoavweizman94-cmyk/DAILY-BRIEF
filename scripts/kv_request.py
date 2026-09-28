# -*- coding: utf-8 -*-
"""קורא בקשת הפקה שהאתר כתב ל-KV, ותובע אותה.

**למה דרך KV ולא שיגור ישיר.** כפתור "הפק ברייף" באתר רץ ב-Cloudflare
Pages, ושיגור workflow_dispatch משם דורש אסימון GitHub — אסימון שרק
הבעלים יכול ליצור, ועד שייווצר הכפתור אינו עושה דבר. האסימון של
Cloudflare כבר קיים כסוד בריפו ונמדד שהוא מגיע ל-KV, ולכן הכיוון
ההפוך פתוח: האתר כותב בקשה, והריצה הקצרה הזו קוראת אותה.

**התביעה קודמת להפקה.** המפתח נמחק לפני שהברייף מופעל, לא אחריו: ריצה
שתיפול אחרי המחיקה עולה מהדורה אחת, בעוד מפתח שנשאר אחרי הפעלה מייצר
הפקה נוספת בכל פעימה — לולאה שמרוקנת את היתרה.

פלט: שורות KEY=value ל-$GITHUB_OUTPUT (או ל-stdout בהרצה מקומית).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.cloudflare.com/client/v4"
NS_TITLE = os.environ.get("KV_TITLE") or "tlv-tase-view-users"
KEY = os.environ.get("KV_KEY") or "brief:request"
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


def out(**kw) -> None:
    lines = "".join(f"{k}={v}\n" for k, v in kw.items())
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(lines)
    sys.stdout.write(lines)


def main() -> int:
    if not (os.environ.get("CF_API_TOKEN") and os.environ.get("CF_ACCOUNT_ID")):
        print("::warning title=אין גישה ל-KV::סודות Cloudflare חסרים — "
              "כפתור ההפקה באתר לא יפעל")
        out(run="false")
        return 0

    code, body = call("/storage/kv/namespaces?per_page=100")
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    ns = next((n["id"] for n in (data.get("result") or [])
               if n.get("title") == NS_TITLE), None)
    if not ns:
        print(f"::warning title=KV לא נמצא::מרחב השמות {NS_TITLE} אינו ברשימה (קוד {code})")
        out(run="false")
        return 0

    key = urllib.parse.quote(KEY, safe="")

    # **בדיקה עצמית.** מסלול הכפתור נבדק עד כה רק בחציו: תור ריק ויציאה
    # שקטה. עם KV_SEED נכתבת בקשה אמיתית ומיד נתבעת, וכך נבדקות גם
    # הכתיבה, גם הקריאה וגם המחיקה — בלי להפיק מהדורה ובלי לשלם עליה.
    seed = (os.environ.get("KV_SEED") or "").strip()
    if seed:
        payload = json.dumps({"edition": "" if seed == "-" else seed,
                              "at": datetime.now(timezone.utc).isoformat(),
                              "by": "self-test"}, ensure_ascii=False)
        scode, _ = call(f"/storage/kv/namespaces/{ns}/values/{key}", "PUT", payload)
        if scode not in (200, 204):
            print(f"::error title=כתיבה ל-KV נכשלה::קוד {scode} — הכפתור באתר לא יוכל "
                  "לרשום בקשה, ולכן לא יפעל")
            out(run="false")
            return 0
        print("::notice title=בדיקה עצמית::נכתבה בקשה זמנית ל-KV; ממשיכים לתביעה")

    code, body = call(f"/storage/kv/namespaces/{ns}/values/{key}")
    if code == 404 or not body.strip():
        out(run="false")
        return 0
    if code != 200:
        print(f"::warning title=קריאת הבקשה נכשלה::קוד {code}")
        out(run="false")
        return 0

    try:
        req = json.loads(body)
    except ValueError:
        req = {}

    # תביעה: מוחקים לפני שמפעילים, אחרת כל פעימה תפעיל שוב את אותה בקשה.
    dcode, _ = call(f"/storage/kv/namespaces/{ns}/values/{key}", method="DELETE")
    if dcode not in (200, 204):
        print(f"::error title=הבקשה לא נמחקה::קוד {dcode} — אין הפקה, "
              "אחרת אותה בקשה תרוץ שוב בכל פעימה")
        out(run="false")
        return 0

    edition = str(req.get("edition") or "")
    if edition not in EDITIONS:
        print(f"::warning::מהדורה {edition!r} אינה מוכרת — נבחרת לפי השעה")
        edition = ""

    at = str(req.get("at") or "")
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(at.replace("Z", "+00:00"))).total_seconds() / 60
    except ValueError:
        age = 0.0
    if age > MAX_AGE_MIN:
        print(f"::notice title=בקשה ישנה::הבקשה בת {age:.0f} דקות "
              f"(מעל {MAX_AGE_MIN}) — נמחקה בלי הפקה")
        out(run="false")
        return 0

    if seed:
        print(f"::notice title=מסלול הכפתור תקין::כתיבה, קריאה ומחיקה עברו; "
              f"מהדורת {edition or 'לפי השעה'} נתבעה ולא הופקה (בדיקה)")
        out(run="false")
        return 0

    print(f"::notice title=בקשת הפקה::מהדורת {edition or 'לפי השעה'} — "
          f"נתבעה מ-KV אחרי {max(age, 0):.0f} דקות המתנה")
    out(run="true", edition=edition)
    return 0


if __name__ == "__main__":
    sys.exit(main())
