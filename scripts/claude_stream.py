# -*- coding: utf-8 -*-
"""קורא את פלט ה-stream של ה-CLI, מדפיס יומן כלים, ושומר את המעטפת.

**למה.** מהדורה ב-Sonnet הגיעה ל-$10.15 בלי להשלים (28/09/2026), וזה
אינו מחיר של חשיבה אלא של חזרה: הקשר גדול שנשלח שוב ושוב, או כלי
שנקרא עשרות פעמים על אותו קובץ. עם `--output-format json` הלוג שותק עד
הסוף, ולכן לא היה שום מידע על מה הסשן עשה — רק כמה הוא עלה.

**מה נכתב ללוג, ומה לא.** הריפו ציבורי והלוגים שלו ציבוריים. לכן נכתבים
שמות כלים ונתיבים בלבד — נתונים שממילא בריפו — ולעולם לא תוכן: לא טקסט
הודעה, לא `new_string` של עריכה, לא גוף קובץ. פקודת Bash נחתכת ל-80 תו
כי היא קוד ולא מחקר.

הסיכום בסוף הוא הפואנטה: כמה קריאות לכל כלי, ואילו יעדים חזרו. יעד
שנקרא חמש פעמים הוא לולאה, ולולאה היא העלות.

שימוש: claude ... --output-format stream-json --verbose | python scripts/claude_stream.py <קובץ מעטפת>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# מפתחות שמותר להדפיס מתוך קלט של כלי: כולם נתיבים או דפוסי חיפוש.
SAFE_KEYS = ("file_path", "path", "pattern", "url", "notebook_path", "glob", "skill")
MAX_TARGET = 90
TOP_REPEATS = 12
REPEAT_FLAG = 3          # יעד שנקרא כך או יותר — נחשד כלולאה


def target(inp: dict) -> str:
    """היעד של קריאת הכלי, בלי תוכן."""
    if not isinstance(inp, dict):
        return ""
    for k in SAFE_KEYS:
        v = inp.get(k)
        if isinstance(v, str) and v:
            return v[:MAX_TARGET]
    cmd = inp.get("command")
    if isinstance(cmd, str):
        return " ".join(cmd.split())[:80]
    return ""


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    tools: Counter = Counter()
    targets: Counter = Counter()
    final = None
    n = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "result":
            final = ev
            continue
        if ev.get("type") != "assistant":
            continue
        for block in (ev.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name") or "?")
            tgt = target(block.get("input") or {})
            tools[name] += 1
            if tgt:
                targets[f"{name} {tgt}"] += 1
            n += 1
            print(f"  {n:>3}. {name} {tgt}", flush=True)

    print()
    print(f"כלים: {n} קריאות · " + ", ".join(f"{k} {v}" for k, v in tools.most_common()))
    repeats = [(t, c) for t, c in targets.most_common(TOP_REPEATS) if c >= 2]
    if repeats:
        print("יעדים חוזרים: " + " · ".join(f"{t} ×{c}" for t, c in repeats))
    loops = [t for t, c in targets.items() if c >= REPEAT_FLAG]
    if loops:
        print(f"::warning title=יעדים שנקראו {REPEAT_FLAG}+ פעמים::"
              f"{len(loops)} יעדים — {'; '.join(loops[:5])}")

    if final is not None and env_path:
        env_path.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
        return 0
    if final is None:
        print("::error title=הזרם נקטע::לא התקבלה רשומת סיום מה-CLI")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
