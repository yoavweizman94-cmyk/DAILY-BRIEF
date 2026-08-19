#!/usr/bin/env python3
"""נורמליזציה של כותרת הברייף למיתוג הנוכחי.

השירות נקרא TLV TASE View, אבל שורת ה-H1 נכתבה "# ברייף FOREST" —
המיתוג שקדם לשינוי השם. מפני שכל מהדורה קוראת את קודמותיה ומעתיקה מהן
את מבנה הכותרת, הטעות שכפלה את עצמה יום אחרי יום, והופיעה ככותרת
הדפדפן של עמוד הבית ובכל שורה בארכיון.

הסקריפט נוגע **בשורה הראשונה בלבד** ורק כשהיא נפתחת במיתוג הישן, ולכן
הרצה חוזרת אינה משנה דבר. גוף הברייף אינו נגזר ואינו נערך.

run_daily.sh מנרמל מעכשיו כל ברייף חדש, כך שזו הרצה חד-פעמית להיסטוריה.
"""
import sys
from pathlib import Path

OLD = "# ברייף FOREST"
NEW = "# TLV TASE View"


def main(root: str = "output") -> int:
    files = sorted(Path(root).glob("brief_*.md"))
    if not files:
        print(f"::error::לא נמצאו ברייפים ב-{root}/")
        return 1

    changed, already, odd = [], 0, []
    for f in files:
        lines = f.read_text(encoding="utf-8").split("\n")
        if not lines:
            continue
        head = lines[0]
        if head.startswith(NEW):
            already += 1
        elif head.startswith(OLD):
            lines[0] = NEW + head[len(OLD):]
            f.write_text("\n".join(lines), encoding="utf-8")
            changed.append(f.name)
        else:
            odd.append((f.name, head[:60]))

    print(f"נבדקו {len(files)} ברייפים")
    print(f"  תוקנו:      {len(changed)}")
    print(f"  כבר תקינים: {already}")
    for name in changed:
        print(f"    · {name}")
    if odd:
        print(f"  כותרת לא מוכרת ({len(odd)}) — לא נגענו:")
        for name, head in odd:
            print(f"    · {name}: {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "output"))
