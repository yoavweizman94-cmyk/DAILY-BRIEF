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
from datetime import date

from curl_cffi import requests as creq

BASE = "https://maya.tase.co.il"
PAGE_SIZE = 30
MAX_PAGES = 60          # תקרת בטיחות — 1,800 דיווחים לחלון

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

    def _post(self, path: str, body: dict):
        self._wait()
        r = self._s.post(f"{BASE}{path}", json=body, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r

    # -- חברות ---------------------------------------------------------------

    def autocomplete(self, query: str) -> list[dict]:
        r = self._get("/api/v1/companies/autocomplete", {"search": query})
        return [c for c in r.json() if c.get("type") == "COMPANY"]

    def company_details(self, company_id: int) -> dict:
        return self._get(f"/api/v1/companies/{company_id}/details").json()

    # -- דיווחים -------------------------------------------------------------

    def reports_days(self, from_day: date, to_day: date,
                     company_id: int | None = None) -> list[dict]:
        """כל דיווחי החברות בטווח הימים [from_day, to_day] (כולל), בעימוד offset."""
        base = {"fromDate": from_day.isoformat(), "toDate": to_day.isoformat(),
                "limit": PAGE_SIZE}
        if company_id:
            base["companyId"] = int(company_id)
        seen, items, offset = set(), [], 0
        for _ in range(MAX_PAGES):
            r = self._post("/api/v1/reports/companies", {**base, "offset": offset})
            batch = r.json()
            total = int(r.headers.get("x-total-count", 0))
            for it in batch:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    items.append(it)
            offset += len(batch)
            if not batch or offset >= total:
                break
        return items
