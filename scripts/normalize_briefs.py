#!/usr/bin/env python3
"""נורמליזציה של ארטיפקטים שדולפים מתבנית ההוראות אל תוך הברייף.

הסוכן מקבל את מבנה הפלט כבלוק markdown ב-CLAUDE.md, וכותב אותו כמעט
מילה במילה. לכן כל הערה פנימית שיושבת בתוך הבלוק ההוא מגיעה למוצר —
וכיוון שכל מהדורה קוראת את קודמותיה ומעתיקה מהן, היא מתקבעת ומשכפלת
את עצמה יום אחרי יום. שני מקרים שנתפסו כך:

  · "# ברייף FOREST" ששרד את שינוי השם ב-31 ברייפים.
  · "## נדל\"ן ובנייה   ← מודול הליבה" — הערת היקף שהפכה לכותרת סעיף
    באתר, ב-24 ברייפים.

הסקריפט מתקן את שתיהן ומדווח על כל כותרת שאינה מוכרת, במקום לנחש.
הוא אידמפוטנטי: הרצה חוזרת אינה משנה דבר.

    python scripts/normalize_briefs.py [output]
"""
import re
import sys
from pathlib import Path

H1_WANT = "# TLV TASE View"
H1_OLD = "# ברייף FOREST"

# הערות פנימיות שאין להן מה לחפש בכותרת סעיף
HEADING_NOTES = re.compile(r"[ \t]*←[^\n]*$")


def fix(path: Path) -> list[str]:
    """מחזיר את רשימת התיקונים שבוצעו בקובץ."""
    lines = path.read_text(encoding="utf-8").split("\n")
    done = []

    if lines and lines[0].startswith(H1_OLD):
        lines[0] = H1_WANT + lines[0][len(H1_OLD):]
        done.append("מיתוג בכותרת")

    for i, line in enumerate(lines):
        if line.startswith("#") and "←" in line:
            lines[i] = HEADING_NOTES.sub("", line).rstrip()
            done.append(f"הערה בכותרת: {lines[i].lstrip('# ')[:30]}")

    if done:
        path.write_text("\n".join(lines), encoding="utf-8")
    return done


def main(root: str = "output") -> int:
    files = sorted(Path(root).glob("brief_*.md"))
    if not files:
        print(f"::error::לא נמצאו ברייפים ב-{root}/")
        return 1

    changed, odd = {}, []
    for f in files:
        d = fix(f)
        if d:
            changed[f.name] = d
        head = f.read_text(encoding="utf-8").split("\n", 1)[0]
        if not head.startswith(H1_WANT):
            odd.append((f.name, head[:60]))

    print(f"נבדקו {len(files)} ברייפים · תוקנו {len(changed)}")
    for name, d in changed.items():
        print(f"  · {name}: {', '.join(sorted(set(d)))}")
    if odd:
        print(f"\n::warning::כותרת ראשית לא מוכרת ב-{len(odd)} קבצים — לא נגענו:")
        for name, head in odd:
            print(f"  · {name}: {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "output"))
