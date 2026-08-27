# -*- coding: utf-8 -*-
"""משמר טריות: האם כל זרם נתונים התעדכן בזמן שהוא אמור.

**למה זה קיים.** במשך יומיים יואב גילה בעצמו שדברים תקועים — ברייף של
אתמול, עסקאות שלא זזו, תמלולים חסרים — ובכל פעם הריצות היו ירוקות.
ריצה מוצלחת אינה מבטיחה שהתוצר עודכן: היא יכולה לצאת מוקדם, לדחוף
לריפו התוכן בלי לפרוס, או להיכשל במקור בודד ולהמשיך.

הבדיקה כאן היא על **התוצר עצמו** ולא על הריצה שהייתה אמורה לייצר
אותו, ולכן היא תופסת גם כשל שאיש לא חשב עליו.

**היא קובעת ואינה מדפיסה.** זרם שחרג מהסף מדווח כשגיאה עם קוד יציאה
1 — הדפסה שאיש אינו קורא היא בדיוק הכשל שהיא נועדה לתפוס.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

IL = timezone(timedelta(hours=3))


def newest_brief() -> tuple[str, str] | None:
    """(תאריך, שם) של הברייף האחרון."""
    files = sorted(OUT.glob("brief_????-??-??*.md"))
    if not files:
        return None
    f = files[-1]
    return f.name[6:16], f.name


def newest_jsonl(dirname: str, pattern: str, field: str) -> str | None:
    """התאריך המאוחר ביותר בשדה `field` על פני קובצי JSONL בתיקייה."""
    d = OUT / dirname
    if not d.is_dir():
        return None
    best = None
    for f in sorted(d.glob(pattern)):
        for line in f.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                v = json.loads(line).get(field)
            except json.JSONDecodeError:
                continue
            if v and (best is None or str(v) > best):
                best = str(v)[:10]
    return best


def business_days_since(day: str, today: date) -> int:
    """כמה ימי מסחר חלפו. הבורסה נסחרת שני–שישי מינואר 2026, ולכן
    שבת וראשון אינם פיגור אלא לוח השנה."""
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return 999
    n = 0
    while d < today:
        d += timedelta(days=1)
        if d.weekday() not in (5, 6):   # שבת=5, ראשון=6
            n += 1
    return n


def main() -> int:
    today = datetime.now(IL).date()
    rows, bad = [], []

    # --- הברייף: נכתב שלוש פעמים ביום, כל יום ---
    b = newest_brief()
    if not b:
        bad.append("אין אף ברייף ב-output")
    else:
        day, name = b
        age = (today - date.fromisoformat(day)).days
        rows.append(("ברייף", day, f"{age} ימים", name))
        if age >= 1:
            bad.append(f"הברייף האחרון הוא של {day} — {age} ימים. "
                       "בדוק את Daily Brief; פעימות ההשלמה היו אמורות לתפוס זאת.")

    # --- זרמים שנגזרים ממסחר: נמדדים בימי מסחר ---
    for label, dirname, pattern, field, limit, hint in (
        ("עסקאות מחוץ לבורסה", "otc", "*.jsonl", "date", 3, "Offex Backfill"),
        ("דיווחי בעלי עניין", "offex", "*.jsonl", "date", 3, "Offex Backfill"),
        ("תמלולי שיחות", "calls", "transcripts_*.jsonl", "date", 4, "Globes Calls"),
    ):
        day = newest_jsonl(dirname, pattern, field)
        if not day:
            rows.append((label, "—", "אין נתונים", hint))
            bad.append(f"{label}: אין נתונים כלל ב-output/{dirname}")
            continue
        n = business_days_since(day, today)
        rows.append((label, day, f"{n} ימי מסחר", hint))
        if n > limit:
            bad.append(f"{label}: הרשומה האחרונה היא מ-{day} — {n} ימי מסחר. "
                       f"בדוק את {hint}.")

    w = max(len(r[0]) for r in rows) if rows else 10
    print("מצב טריות:")
    for label, day, age, extra in rows:
        print(f"  {label:{w}}  {day:12} {age:16} {extra}")

    if bad:
        print()
        for msg in bad:
            print(f"::error title=נתונים לא טריים::{msg}")
        return 1
    print("\nכל הזרמים בתוך הסף.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
