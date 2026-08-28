# -*- coding: utf-8 -*-
"""פרמטרים למהדורת הברייף, לפי האירוע שהפעיל את הריצה.

שלושה מקורות, ולכל אחד כללים אחרים:

· `schedule` — המהדורה נגזרת מביטוי ה-cron ולא מהשעה בפועל, ולכן היא
  מוכרעת ב-workflow עצמו ולא כאן. **BRIEF_FORCE נשאר כבוי**: ריצה
  מתוזמנת שמוצאת ברייף טרי צריכה לדלג, אחרת שתי מהדורות של אותה שעה
  יכתבו זו על זו.
· `workflow_dispatch` — הפרמטרים מה-inputs, והפקה כפויה.
· `push` על קובץ הטריגר — הפרמטרים מהקובץ, והפקה כפויה. זהו מנגנון
  ההרצה היחיד שזמין בלי אסימון GitHub.

הפלט הוא שורות KEY=VALUE, לטעינה לסביבה של השלב.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TRIGGER = Path(__file__).resolve().parent.parent / ".trigger" / "daily-brief.json"
EDITIONS = ("", "morning", "close", "night")


def main() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")

    if event == "workflow_dispatch":
        edition = (os.environ.get("IN_EDITION") or "").strip()
        reviews = (os.environ.get("IN_REVIEWS") or "").strip()
        force = "1"
        src = "workflow_dispatch"
    elif event == "schedule":
        # המהדורה נקבעת מה-cron בשלב Resolve edition; כאן רק ברירות מחדל.
        edition, reviews, force, src = "", "", "", "schedule"
    else:
        cfg = {}
        if TRIGGER.exists():
            try:
                cfg = json.loads(TRIGGER.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"::warning::קובץ הטריגר אינו JSON תקין ({e}) — "
                      "ממשיכים בברירות מחדל", file=sys.stderr)
        edition = str(cfg.get("edition") or "").strip()
        reviews = str(cfg.get("reviews") or "").strip()
        force = "1"
        src = f"{event or 'unknown'} (.trigger)"

    if edition not in EDITIONS:
        print(f"::warning::מהדורה {edition!r} אינה מוכרת — נבחרת לפי השעה",
              file=sys.stderr)
        edition = ""
    if reviews and not reviews.isdigit():
        print(f"::warning::reviews={reviews!r} אינו מספר — נלקח 0", file=sys.stderr)
        reviews = ""

    print(f"BRIEF_EDITION_IN={edition}")
    # אפס = כבוי. הסקירות נוצרות בלחיצה בעמוד; ראה run_daily.sh.
    print(f"BRIEF_REVIEWS={reviews or 0}")
    print(f"BRIEF_FORCE_IN={force}")
    print(f"BRIEF_SRC={src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
