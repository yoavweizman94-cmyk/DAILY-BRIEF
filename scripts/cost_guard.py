# -*- coding: utf-8 -*-
"""בלם יומי: כמה כבר הוצא היום, ומה לעשות עם זה.

**למה.** ב-28/09/2026 נשרפו $25.42 בארבע ריצות ברייף — שלוש נקטעו בתקרה
ואחת מתה כשהיתרה אזלה — ולא פורסם ולו ברייף אחד. התקרה לקריאה בודדת לא
עזרה: היא עצרה כל ריצה בנפרד, וכל ניסיון חוזר התחיל מאפס. מה שחסר הוא
בלם על **היום כולו**.

שני ספים, ושניהם על סכום היום עד כה:
· רך (BRIEF_SOFT_USD, ברירת מחדל $20) — המהדורה יורדת ל-Sonnet. היא
  עדיין נכתבת, וזה ההבדל בין ברייף זול לבין אין ברייף.
· קשה (BRIEF_HARD_USD, ברירת מחדל $40) — לא מופק ברייף. יום שהגיע לשם
  הוא יום תקול, וריצה נוספת רק תרוקן את היתרה לפני מהדורת הבוקר.

הפלט הוא שורות KEY=VALUE לטעינה לסביבה; אנוטציות נכתבות ל-stdout ולכן
הן חלק מהפלט ומסוננות ע"י הקורא (`grep '^[A-Z]'`).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOFT = float(os.environ.get("BRIEF_SOFT_USD") or 20)
HARD = float(os.environ.get("BRIEF_HARD_USD") or 40)
CHEAP = "claude-sonnet-5"


def spent(day: str) -> tuple[float, int]:
    p = ROOT / "output" / "costs" / f"{day}.jsonl"
    if not p.exists():
        return 0.0, 0
    total, n = 0.0, 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            total += float(json.loads(line).get("usd") or 0)
            n += 1
        except (ValueError, AttributeError):
            continue
    return total, n


def main() -> int:
    day = os.environ.get("BRIEF_DATE") or date.today().isoformat()
    usd, n = spent(day)
    print(f"DAY_USD={usd:.2f}")

    if usd >= HARD:
        print("BRIEF_SKIP=1")
        print(f"::error title=הבלם היומי נסגר::היום כבר הוצאו ${usd:.2f} ב-{n} קריאות "
              f"(מעל ${HARD:.0f}) — לא מופק ברייף. העלה BRIEF_HARD_USD כדי לעקוף.",
              file=sys.stderr)
        return 0

    if usd >= SOFT:
        print(f"BRIEF_MODEL_FORCED={CHEAP}")
        print(f"::warning title=מעבר למודל זול::היום כבר הוצאו ${usd:.2f} ב-{n} קריאות "
              f"(מעל ${SOFT:.0f}) — המהדורה נכתבת ב-{CHEAP}.", file=sys.stderr)
        return 0

    if n:
        print(f"::notice title=עלות היום עד כה::${usd:.2f} ב-{n} קריאות "
              f"(רך ${SOFT:.0f} · קשה ${HARD:.0f})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
