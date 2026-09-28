# -*- coding: utf-8 -*-
"""מפרק את מעטפת ה-JSON של קריאת הברייף: מדפיס את הטקסט, רושם עלות, ומחזיר קוד.

run_daily.sh קורא ל-CLI עם --output-format json כדי לדעת כמה עלתה כל מהדורה.
בלי זה הברייף — הקריאה היקרה בצנרת — היה הדבר היחיד שלא דיווח על עלותו.

שימוש: python scripts/claude_envelope.py <קובץ מעטפת> <שם העבודה> [תווית]
יציאה: 0 בהצלחה, 1 בכישלון (ואז ההודעה נכתבת כאנוטציה).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("שימוש: claude_envelope.py <קובץ> <עבודה> [תווית]", file=sys.stderr)
        return 2
    path, job = Path(sys.argv[1]), sys.argv[2]
    label = sys.argv[3] if len(sys.argv) > 3 else ""
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    text, err, meta = _cli.envelope(raw, 0 if raw else 1, "")
    cost = float(meta.get("cost") or 0)
    if cost:
        _cli.log_cost(job, cost, label=label, turns=meta.get("turns"),
                      models=meta.get("models"), out_tokens=meta.get("out_tokens"),
                      cache_read=meta.get("cache_read"), cache_new=meta.get("cache_new"))
    if err:
        # התקרה נועדה לעצור סשן שנתקע, לא מהדורה לגיטימית. כשהיא זו שעצרה —
        # לומר זאת במפורש, אחרת "קוד 1" נראה כמו כל כשל אחר.
        if "max_budget" in err:
            print(f"::error title=הברייף נקטע בתקרת העלות::המהדורה חרגה מ-BRIEF_MAX_USD. "
                  f"העלות עד הקטיעה: ${cost:.2f}. הגדל את התקרה או הרץ את המהדורה במודל זול יותר.")
            return 1
        if _cli.CREDIT_RE in err:
            print("::error title=יתרת Anthropic אזלה::הברייף אינו נכתב. "
                  "טעינה: console.anthropic.com/settings/billing")
        print(f"::error title=הברייף נכשל::{err[:400]}")
        return 1
    print(text or "")
    # הטוקנים הם המספר שמסביר את העלות: תור אחד על הקשר של מיליון טוקן
    # עולה יותר מעשרה תורות על מאה אלף. שניהם מספרים בלבד — הלוג ציבורי.
    m = int((meta.get("cache_read") or 0) / 1e6 * 10) / 10
    print(f"::notice::עלות {job}{f' ({label})' if label else ''}: ${cost:.2f} · "
          f"{meta.get('turns')} תורות · {m}M טוקן מהמטמון · {meta.get('models') or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
