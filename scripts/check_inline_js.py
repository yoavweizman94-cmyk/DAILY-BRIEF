# -*- coding: utf-8 -*-
"""בדיקת תחביר לכל JS מוטמע בעמודי האתר.

**למה זה קיים.** ב-`landing.html` הייתה שורת מעבר בתוך מחרוזת:

    encodeURIComponent(lines.join("
    "))

זו שגיאת תחביר, ולכן **כל** בלוק ה-script לא נטען — כולל
`addEventListener("submit", ...)` של טופס ההרשמה. הטופס נשאר בלי מטפל,
הלחיצה על "שלח בקשה" לא שלחה דבר, ואף בקשה לא הגיעה לשרת. מבחוץ זה
נראה כמו אדם שלא נרשם: אין חשבון, אין דחייה רשומה, אין מה לחקור.
שני אנשים ניסו להירשם ונכשלו כך, ואיש לא ידע.

HTML אינו נכשל על JS פגום — הדפדפן מדלג בשקט. לכן הבדיקה חייבת לרוץ
לפני הפריסה, והיא נכשלת קשה: עמוד עם script שאינו מתפרש לא ייפרס.

הסיבה השורשית לשגיאה עצמה היא כלי עריכה שאוכל רמת בריחה אחת ומהפך
`\\n` בתוך מחרוזת לשורה חדשה ממשית. בדיקה אוטומטית זולה בהרבה מהסתמכות
על כך שזה לא יקרה שוב.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# בלוק script עם src חיצוני אין לו גוף לבדוק.
BLOCK = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.S | re.I)
TYPE = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)

# **רק בלוקים שהדפדפן מריץ כ-JavaScript.** ‏<script type="application/json">
# הוא מטען נתונים ולא קוד, ו-node --check מפרש אותו כ-JS ונופל על
# הנקודתיים הראשונה. הבדיקה חסמה בגלל זה פריסה תקינה של עמוד העסקאות.
# חוסם שגוי גרוע מבדיקה חסרה: הוא מלמד להתעלם מהבדיקה.
JS_TYPES = {"", "module", "text/javascript", "application/javascript",
            "text/ecmascript", "application/ecmascript", "text/jsx"}


def check(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for i, m in enumerate(BLOCK.finditer(text), 1):
        attrs, body = m.group(1), m.group(2)
        t = TYPE.search(attrs or "")
        kind = t.group(1).strip().lower() if t else ""
        if kind not in JS_TYPES:
            continue
        if not body.strip():
            continue
        # **הסיומת קובעת איך node מפרש.** ‎--check על קובץ .js מפרש כתסריט
        # קלאסי, ותחביר ESM שגוי עובר בו בשקט. נמדד: `import x from;`
        # יוצא בקוד 0 מ-.js ונכשל מ-.mjs.
        suffix = ".mjs" if kind == "module" else ".js"
        line0 = text[: m.start(2)].count("\n") + 1
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False,
                                         encoding="utf-8") as fh:
            fh.write(body)
            tmp = fh.name
        try:
            r = subprocess.run(["node", "--check", tmp],
                               capture_output=True, text=True, encoding="utf-8")
        finally:
            Path(tmp).unlink(missing_ok=True)
        if r.returncode != 0:
            err = (r.stderr or "").strip().splitlines()
            detail = next((l for l in err if "Error" in l), err[-1] if err else "?")
            # מספר השורה בפלט של node יחסי לבלוק; מתרגמים לשורה בקובץ.
            off = re.search(r"\.m?js:(\d+)", r.stderr or "")
            where = f"שורה {line0 + int(off.group(1)) - 1}" if off else f"בלוק {i}"
            problems.append(f"{path.relative_to(ROOT).as_posix()} · {where} · {detail}")
    return problems


def main() -> int:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        print("::warning::node אינו זמין — בדיקת ה-JS המוטמע דולגה")
        return 0

    # **גם עמודים מחוללים.** ה-JS של עמוד העסקאות נכתב מתוך site/otc.py
    # ואינו יושב ב-pages/, ולכן בדיקה שמסתכלת רק שם מפספסת בדיוק את הקוד
    # שנוצר בכל בנייה. dist נבדק כשהוא קיים.
    targets = sorted((ROOT / "site" / "pages").glob("*.html"))
    dist = ROOT / "site" / "dist"
    if dist.is_dir():
        targets += sorted(dist.glob("*.html"))
    if not targets:
        print("::warning::לא נמצאו עמודים לבדיקה")
        return 0

    bad: list[str] = []
    for p in targets:
        bad += check(p)

    print(f"נבדקו {len(targets)} עמודים.")
    if bad:
        for b in bad:
            print(f"::error title=JS מוטמע שאינו מתפרש::{b}")
        print("::error::עמוד עם script פגום נטען בדפדפן בלי שגיאה גלויה, "
              "והטפסים שבו מפסיקים לעבוד בשקט. הפריסה נעצרת.")
        return 1
    print("כל ה-JS המוטמע מתפרש.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
