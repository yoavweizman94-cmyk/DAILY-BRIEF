# -*- coding: utf-8 -*-
"""מי נחשב "דוח כספי של חברת כיסוי" — כלל אחד, שני קוראים.

`ingest/filing_review.py` בוחר לפיו מה לסקור, ו-`site/build.py` בונה
לפיו את מפת הדוחות שהאתר מגיש. כשהכלל היה משוכפל, כפתור היה מופיע על
דוח שהסקריפט לא היה מסכים לסקור — ולהפך.

המודול הזה מכוון להיות חף מתלויות כבדות: `build.py` מייבא אותו בזמן
פריסה, שם `anthropic` אינו מותקן.
"""
from __future__ import annotations

# כותרות שמזהות דוח כספי. "מצבת התחייבות" ו"מצגת" מלוות דוח אך אינן דוח.
FINANCIAL = ("דוח רבעון", "דוח תקופתי", "דוחות כספיים", "דוח שנתי",
             "דוח חצי שנתי", "דוח רבעוני")
NOT_FINANCIAL = ("מצבת התחייבות", "מצגת", "iXBRL", "תיקון", "אסיפה",
                 "הצגה מחדש")


def is_financial(title: str) -> bool:
    t = title or ""
    if any(x in t for x in NOT_FINANCIAL):
        return False
    return any(x in t for x in FINANCIAL)


def reviewable(rec: dict) -> bool:
    """דוח שאפשר וכדאי לסקור: חברת כיסוי, דוח כספי, ויש קובץ."""
    if str(rec.get("cov")) != "1":
        return False
    if not is_financial(rec.get("t") or ""):
        return False
    p = rec.get("p")
    return bool(p) and p != "None"
