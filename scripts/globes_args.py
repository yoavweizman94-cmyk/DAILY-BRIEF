# -*- coding: utf-8 -*-
"""ארגומנטים ל-ingest/globes_calls.py, לפי האירוע שהפעיל את הריצה.

**למה זה קיים.** ל-workflow_dispatch יש inputs, ולאירועי schedule ו-push
אין. בלי מקום אחד שמכריע, כל שלב היה צריך לטפל בשלושת המקרים בעצמו —
וזה כבר נשבר פעם אחת, כשתזמון הופעל ולא הריץ דבר כי התנאי בדק inputs
שלא היו קיימים.

**הטריגר בקובץ.** הרצה מרחוק דורשת אסימון GitHub, ואין כזה בסביבה
הזו. `.trigger/globes-calls.json` פותר את זה: דחיפה שלו מפעילה את
ה-workflow, והתוכן שלו הוא הפרמטרים. כך אפשר להריץ בלי אסימון ובלי
ללחוץ ידנית.

הפלט הוא שורות KEY=VALUE, לכתיבה אל $GITHUB_ENV.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TRIGGER = Path(__file__).resolve().parent.parent / ".trigger" / "globes-calls.json"


def truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")

    if event == "workflow_dispatch":
        limit = (os.environ.get("IN_LIMIT") or "").strip() or "8"
        want_all = truthy(os.environ.get("IN_ALL"))
        redo = truthy(os.environ.get("IN_REDO"))
        src = "workflow_dispatch"
    else:
        cfg = {}
        if TRIGGER.exists():
            try:
                cfg = json.loads(TRIGGER.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                # קובץ טריגר פגום לא ישתיק את הריצה: מוטב ברירת מחדל
                # רועשת מאשר ריצה שקטה עם פרמטרים שאיש לא התכוון אליהם.
                print(f"::warning::קובץ הטריגר אינו JSON תקין ({e}) — "
                      "ממשיכים בברירות מחדל", file=sys.stderr)
        limit = str(cfg.get("limit") or 8)
        want_all = truthy(cfg.get("all"))
        redo = truthy(cfg.get("redo"))
        src = f"{event or 'unknown'} (.trigger)"

        # **redo לעולם אינו נשמע בריצה מתוזמנת.** הוא נועד לפעולה חד-פעמית
        # אחרי תיקון בפענוח, והוא עולה כסף על כל תמליל בכיסוי. דגל שנשאר
        # דלוק בקובץ היה גורם לתשלום מלא **בכל יום**, בשקט, כי אף אחד לא
        # פותח קובץ טריגר אחרי שהשתמש בו.
        if redo and event == "schedule":
            print("::warning::redo מסומן בקובץ הטריגר אך הריצה מתוזמנת — "
                  "מתעלמים ממנו. להרצה חוזרת בתשלום יש לדחוף את הקובץ.",
                  file=sys.stderr)
            redo = False

    if not limit.isdigit():
        print(f"::warning::limit={limit!r} אינו מספר — נלקח 8", file=sys.stderr)
        limit = "8"

    flags = []
    if want_all:
        flags.append("--all")
    if redo:
        flags.append("--redo")

    print(f"CALL_LIMIT={limit}")
    print(f"CALL_FLAGS={' '.join(flags)}")
    print(f"CALL_SRC={src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
