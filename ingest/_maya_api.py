# -*- coding: utf-8 -*-
"""גישה ל-API של מאיה (maya.tase.co.il/api/v1) מאחורי ה-WAF.

עקרונות שנקבעו אמפירית (2026-08):
- חובה session עם חיקוי TLS של דפדפן (curl_cffi impersonate) + עוגיות מדף הבית,
  אחרת F5/Incapsula מחזירים 403.
- POST /api/v1/reports/companies: גוף {"fromDate","toDate","limit","offset"[,"companyId"]}.
  התאריכים יומיים בלבד (yyyy-MM-dd) — השרת מתעלם משעות. עימוד: limit/offset.
  אזהרה: שדות בשם page/pageNum/skip מפעילים חתימת WAF ומחזירים 403 — לא לשלוח.
- GET /api/v1/companies/autocomplete?search=... — חיפוש חברה (key=companyId).
- GET /api/v1/companies/{id}/details — כולל mainSecurityId (מספר נייר) ו-corporateNo.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import sys

from curl_cffi import requests as creq
from curl_cffi.requests.exceptions import HTTPError

BASE = "https://maya.tase.co.il"
PAGE_SIZE = 30
MAX_PAGES = 60          # תקרת בטיחות — 1,800 דיווחים לחלון

# תקרת עימוד של ה-API: בקשה עם offset מעל ~1000 מוחזרת כ-HTTP 400. נמדד על
# חלון 07–13/07/2026 שבו x-total-count=1255 — העמודים עד offset 1020 חזרו
# תקין והבא אחריו נפל. זה נראה כמו חסימת WAF (וכך אובחן בטעות בהתחלה), אבל
# הוא תלוי אך ורק ב-offset: חלון קצר יותר על אותם תאריכים עובר בלי בעיה.
# המשמעות למי שמושך היסטוריה: לצמצם את החלון עד שהספירה יורדת מתחת לתקרה.
OFFSET_CEILING = 1000


class WindowTooLarge(Exception):
    """טווח התאריכים מכיל יותר דיווחים ממה שהעימוד מאפשר להגיע אליהם."""

    def __init__(self, total: int):
        self.total = total
        super().__init__(f"{total} דיווחים בחלון — מעל תקרת העימוד ({OFFSET_CEILING})")

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "he-IL",
    "Origin": BASE,
    "Referer": f"{BASE}/he",
}


class MayaSession:
    def __init__(self, throttle_sec: float = 0.4):
        self._s = creq.Session(impersonate="chrome")
        self._throttle = throttle_sec
        self._last = 0.0
        # דף הבית מזריע עוגיות WAF (incap/TS). בלי זה — 403.
        self._s.get(f"{BASE}/he", timeout=30)

    def _wait(self):
        dt = self._throttle - (time.monotonic() - self._last)
        if dt > 0:
            time.sleep(dt)
        self._last = time.monotonic()

    def _get(self, path: str, params: dict | None = None):
        self._wait()
        r = self._s.get(f"{BASE}{path}", params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r

    def _post(self, path: str, body: dict, tries: int = 3):
        """POST עם נסיגה על 403 ועל שגיאות שרת.

        ה-WAF של מאיה מחזיר 403 כשקצב הבקשות עולה — נמדד בזמן פיצול
        חלון רחב. זו חסימה זמנית ולא שגיאת בקשה, ולכן נסיגה פותרת אותה.
        400 אינו חוזר: הוא תמיד תקרת עימוד, ושם ניסיון נוסף רק מבזבז זמן.
        """
        last = None
        for i in range(tries):
            self._wait()
            r = self._s.post(f"{BASE}{path}", json=body, headers=HEADERS, timeout=30)
            if r.status_code == 400 or r.ok:
                r.raise_for_status()
                return r
            last = r
            time.sleep(3 * (i + 1))
        last.raise_for_status()
        return last

    # -- חברות ---------------------------------------------------------------

    def autocomplete(self, query: str) -> list[dict]:
        r = self._get("/api/v1/companies/autocomplete", {"search": query})
        return [c for c in r.json() if c.get("type") == "COMPANY"]

    def company_details(self, company_id: int) -> dict:
        return self._get(f"/api/v1/companies/{company_id}/details").json()

    # -- דיווחים -------------------------------------------------------------

    def reports_days(self, from_day: date, to_day: date,
                     company_id: int | None = None) -> list[dict]:
        """כל דיווחי החברות בטווח [from_day, to_day], עם פיצול אוטומטי.

        **חלון שחורג מתקרת העימוד מפוצל לשניים ונמשך שוב**, ולא מפיל את
        המקור. הגרסה הקודמת העדיפה להיכשל מפורשות מלהחזיר חלון קטוע —
        כוונה נכונה, תוצאה הפוכה: הקורא היחיד בפועל הוא `maya_pull`,
        שאינו מפצל אלא מת, ואז הברייף נכתב בלי דיווחי כיסוי בכלל.
        שלוש מהדורות רצופות יצאו כך עם "מקור מאיה נכשל".

        פיצול עדיף על כישלון כי הוא **מחזיר את אותו מידע בדיוק** — רק
        בכמה בקשות. כישלון מחזיר אפס. רק יום בודד שחורג בעצמו מהתקרה
        אינו ניתן לפיצול, ואז נזרקת WindowTooLarge כמו קודם.
        """
        if from_day < to_day:
            try:
                return self._reports_window(from_day, to_day, company_id)
            except (WindowTooLarge, HTTPError):
                mid = from_day + timedelta(days=(to_day - from_day).days // 2)
                print(f"מאיה: החלון {from_day}..{to_day} חורג מתקרת העימוד — "
                      f"מפוצל ב-{mid}", file=sys.stderr)
                left = self.reports_days(from_day, mid, company_id)
                right = self.reports_days(mid + timedelta(days=1), to_day, company_id)
                seen, out = set(), []
                for it in left + right:
                    if it["id"] not in seen:
                        seen.add(it["id"])
                        out.append(it)
                return out
        return self._reports_window(from_day, to_day, company_id)

    def _reports_window(self, from_day: date, to_day: date,
                        company_id: int | None = None) -> list[dict]:
        """משיכה של חלון יחיד, בעימוד offset. עלול לחרוג מהתקרה."""
        base = {"fromDate": from_day.isoformat(), "toDate": to_day.isoformat(),
                "limit": PAGE_SIZE}
        if company_id:
            base["companyId"] = int(company_id)
        seen, items, offset = set(), [], 0
        for _ in range(MAX_PAGES):
            r = self._post("/api/v1/reports/companies", {**base, "offset": offset})
            batch = r.json()
            total = int(r.headers.get("x-total-count", 0))
            # עדיף להיכשל מפורשות מלהחזיר חלון קטוע שנראה שלם: הקורא יכול
            # לפצל את הטווח, אבל רק אם הוא יודע שמשהו חסר.
            if total > OFFSET_CEILING:
                raise WindowTooLarge(total)
            for it in batch:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    items.append(it)
            offset += len(batch)
            if not batch or offset >= total:
                break
        return items
