# -*- coding: utf-8 -*-
"""ארגומנטים ל-scripts/users.py כשהריצה הופעלה מדחיפת קובץ טריגר.

**רק פעולות קריאה.** מהטריגר מותרות `list` ו-`show` בלבד. הפעלה,
השבתה, מחיקה ואיפוס סיסמה משנות את מצבו של חשבון של אדם, וזו החלטה
שנשארת בהפעלה ידנית ומכוונת — לא בדחיפת קובץ.

הפלט הוא שורות KEY=VALUE, לטעינה לסביבה של אותו שלב.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TRIGGER = Path(__file__).resolve().parent.parent / ".trigger" / "users-admin.json"
READ_ONLY = ("list", "show")


def main() -> int:
    cfg = {}
    if TRIGGER.exists():
        try:
            cfg = json.loads(TRIGGER.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"::error::קובץ הטריגר אינו JSON תקין: {e}", file=sys.stderr)
            return 1

    action = str(cfg.get("action") or "list").strip()
    if action not in READ_ONLY:
        print(f"::error::הפעולה {action!r} אינה מותרת בהפעלה מטריגר. "
              f"מותרות: {', '.join(READ_ONLY)}. לשאר יש להשתמש ב-Run workflow.",
              file=sys.stderr)
        return 1

    email = str(cfg.get("email") or "").strip()
    if action == "show" and not email:
        print("::error::show דורש email בקובץ הטריגר", file=sys.stderr)
        return 1

    print(f"ACTION={action}")
    print(f"EMAIL={email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
