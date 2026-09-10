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
from datetime import datetime
from pathlib import Path

TRIGGER = Path(__file__).resolve().parent.parent / ".trigger" / "daily-brief.json"
EDITIONS = ("", "morning", "close", "night")
TOPICS_ONLY_TTL_H = 2


def _age_hours(stamp) -> float | None:
    """גיל חותמת הזמן של הטריגר בשעות, או None אם אינה קריאה.

    הזמן בקובץ נכתב מקומית ובלי אזור זמן, והריצה בענן היא UTC. ההשוואה
    היא לזמן המקומי של הריצה (TZ=Asia/Jerusalem ב-workflow), ולכן שתי
    הצדדים באותו אזור. גיל שלילי — שעון שהוזז — נחשב טרי.
    """
    try:
        t = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    if t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    return max(0.0, (datetime.now() - t).total_seconds() / 3600)


def main() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")

    topics_only = ""
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
        # **רענון עמודי הסקטור בלי לשלם על ברייף.** סיכומי הנושאים הם
        # קריאה אחת למודל; הברייף הוא הקריאה היקרה בצינור. כשהתיקון נוגע
        # לעמודי הסקטור בלבד אין סיבה לכתוב ברייף מחדש — ובוודאי לא
        # לדרוס את זה שכבר פורסם הבוקר.
        #
        # **והדגל פג מעצמו.** קובץ הטריגר נשמר בגיט, ולכן דגל שנשאר בו
        # שורד לטריגר הבא: מי שידחוף טריגר מחר יקבל ריצה ירוקה שלא
        # הפיקה ברייף. אזהרה אחרי מעשה אינה מספיקה כאן — ברירת המחדל
        # הבטוחה היא ברייף, ולכן הדגל תקף רק לצד חותמת זמן טרייה.
        topics_only = "1" if cfg.get("topics_only") else ""
        if topics_only:
            age = _age_hours(cfg.get("at"))
            if age is None:
                print("::warning::topics_only בלי שדה at תקין — מופק ברייף מלא",
                      file=sys.stderr)
                topics_only = ""
            elif age > TOPICS_ONLY_TTL_H:
                print(f"::notice::topics_only בקובץ הטריגר בן {age:.1f} שעות "
                      f"(מעל {TOPICS_ONLY_TTL_H}) — נשאר משימוש קודם ומתעלמים "
                      "ממנו; מופק ברייף מלא", file=sys.stderr)
                topics_only = ""
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
    print(f"BRIEF_TOPICS_ONLY={topics_only}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
