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

ומאותה סיבה גם שתי דליפות מהצנרת, שנמדדו ב-17/11/2026 על 224 ברייפים
(ראו leaks() למטה):

  · קישורים לתיבת ה-Gmail של הבעלים — 68 ב-14 ברייפים.
  · שמות קבצים של הקלט (`pack/otc.jsonl`, `markets.json`) — 4,385 אזכורים,
    כ-20 לברייף, רובם בטבלת השווקים ובסעיף התקלות.

    python scripts/normalize_briefs.py [output]
"""
import os
import re
import sys
from pathlib import Path

H1_WANT = "# TLV TASE View"
H1_OLD = "# ברייף FOREST"

# הערות פנימיות שאין להן מה לחפש בכותרת סעיף
HEADING_NOTES = re.compile(r"[ \t]*←[^\n]*$")

# --- דליפות מהצנרת אל המוצר -------------------------------------------------
# **קישור לתיבת הדואר של הבעלים.** עד 17/11/2026 נשמר בכל ניוזלטר קישור ל-Gmail
# (ingest/gmail_pull.py), והסוכן ציטט אותו כמו כל מקור. הקישור אינו נפתח לאף קורא
# וחושף מזהי הודעות. נשאר שם הפרסום, בלי קישור.
GMAIL_LINK = re.compile(r"\[([^\]\n]+)\]\(\s*<?https?://mail\.google\.[^)\s]*>?\s*\)")
GMAIL_BARE = re.compile(r" ?\(?<?https?://mail\.google\.[^\s)>]*>?\)?")

# **שם קובץ אינו מקור.** הקורא אינו מכיר את `pack/otc.jsonl`; הוא מכיר את סקירת
# הבורסה. השמות בחרו ביחיד זכר כשאפשר ("מאגר", "דוח", "לוח"), כי הסוכן כותב אחריהם
# "ריק", "חזר", "קפוא" — כמו אחרי "הקובץ".
PUBLIC = {
    "markets": "מאגר נתוני השוק",
    "te": "Trading Economics",
    "rmi": 'מאגר רמ"י',
    "maya": "מאיה", "maya_new": "מאיה",
    "calls": "לוח שיחות הוועידה",
    "nadlan": "מאגר העסקאות של Govmap",
    "jumbo": "מאגר העסקאות המתואמות (GTO)",
    "otc": "דוח העסקאות מחוץ לבורסה",
    "offex": "מאגר דיווחי בעלי העניין",
    "gmail": "מאגר הניוזלטרים",
    "rss": "מאגר פידי החדשות",
    "cbs": 'מאגר פרסומי הלמ"ס',
    "companies": "רשימת הכיסוי",
    "call_reviews": "מאגר סקירות דוח ושיחה",
    "maya_summaries": "מאגר סיכומי הדיווחים",
    "commodities_review": "סקירת הסחורות",
    "auto_review": "סקירת הרכב",
    "gov": "מאגר פרסומי הממשלה",
    "impact": "עמוד ההשפעה על מניות",
    "upcoming": "לוח הפרסומים",
    "token": "הרשאת Gmail",
    "fetch_cbs_data": 'שליפת נתוני הלמ"ס',
    "markets_pull": "משיכת נתוני השוק",
    "maya_pull": "משיכת מאיה",
    "brief_pack": "הכנת הקלט",
    "_maya_api": "ממשק מאיה",
}
# **מאיזה ברייף מנקים**, לפי שם הקובץ. מ-17/11/2026 ואילך; הארכיון שלפני כן לא
# נכתב מחדש בלי החלטה של הבעלים. "brief_" כאן מנקה את כולו בריצה הבאה.
GMAIL_FROM = "brief_2026-11-17"
FILES_FROM = "brief_2026-11-17"
EDITIONS = {"": "הבוקר", "midday": "הצהריים", "close": "הנעילה", "night": "הלילה"}
# תחילית עברית עם מקף ("ב-", "ומה-") נצמדת לשם החדש; ה"א הידיעה נבלעת בסמיכות.
# לא בתוך כתובת (".../te.json"), ונקודה בסוף משפט אינה חלק מהשם.
FILE = re.compile(
    r"(?P<pre>(?<![\w֐-׿])[ובלמשכה]{1,4}[-־])?"
    r"(?P<tick>`?)(?<![\w/.:])"
    r"(?P<path>(?:data/raw/[^\s`/]+/|config/|scripts/|ingest/)?(?:pack/|output/)?"
    r"(?:(?P<dir>otc|offex|nadlan)/(?:\d{4}\.jsonl)?"
    r"|brief_(?P<d>\d{4}-\d{2}-\d{2})(?:-(?P<ed>midday|close|night))?\.md"
    r"|(?P<stem>[A-Za-z_][\w-]*)\.(?:jsonl|json|txt|yaml|py)))"
    r"(?P=tick)(?![\w/-]|\.\w)")
# שמות שדות בגרש הפוך (`asof`, `intraday: true`) — נספרים, לא נכתבים מחדש: בלי
# המשפט כולו אין להם תרגום, והכלל ב-CLAUDE.md הוא שמונע אותם.
FIELD = re.compile(r"`[a-z][a-z0-9_]*(?::\s?[^`\n]{0,12})?`")


def _public_name(m: re.Match) -> str | None:
    if m.group("dir"):
        return PUBLIC[m.group("dir")]
    if m.group("d"):
        y, mo, d = m.group("d").split("-")
        return f"מהדורת {EDITIONS[m.group('ed') or '']} של {d}/{mo}"
    return PUBLIC.get(m.group("stem"))


def leaks(text: str, *, gmail: bool = True, files: bool = True) -> tuple[str, dict]:
    """הטקסט בלי קישורי Gmail ובלי שמות קבצים מוכרים, וספירה של מה שהוחלף."""
    n = {"gmail": 0, "files": 0, "unknown": 0}

    def gm(m: re.Match) -> str:
        n["gmail"] += 1
        return m.group(1)

    def bare(m: re.Match) -> str:
        n["gmail"] += 1
        return ""
    if gmail:
        text = GMAIL_BARE.sub(bare, GMAIL_LINK.sub(gm, text))
    if not files:
        return text, n

    def fl(m: re.Match) -> str:
        pub = _public_name(m)
        if pub is None:
            n["unknown"] += 1
            return m.group(0)
        n["files"] += 1
        pre = (m.group("pre") or "")[:-1]
        if pre.endswith("ה"):
            pre = pre[:-1]
        if not pre:
            return pub
        return pre + pub if "֐" <= pub[0] <= "׿" else f"{pre}-{pub}"
    text = FILE.sub(fl, text)
    return text, n


def fix(path: Path, *, gmail: bool = True, files: bool = True) -> tuple[list[str], dict]:
    """מחזיר את רשימת התיקונים שבוצעו בקובץ, ואת ספירת הדליפות שנוקו בו."""
    lines = path.read_text(encoding="utf-8").split("\n")
    done = []

    if lines and lines[0].startswith(H1_OLD):
        lines[0] = H1_WANT + lines[0][len(H1_OLD):]
        done.append("מיתוג בכותרת")

    for i, line in enumerate(lines):
        if line.startswith("#") and "←" in line:
            lines[i] = HEADING_NOTES.sub("", line).rstrip()
            done.append(f"הערה בכותרת: {lines[i].lstrip('# ')[:30]}")

    text = "\n".join(lines)
    text, counts = leaks(text, gmail=gmail, files=files)
    if counts["gmail"]:
        done.append(f"קישורי Gmail: {counts['gmail']}")
    if counts["files"]:
        done.append(f"שמות קבצים: {counts['files']}")

    if done:
        path.write_text(text, encoding="utf-8")
    return done, counts


def main(root: str = "output") -> int:
    files = sorted(Path(root).glob("brief_*.md"))
    if not files:
        print(f"::error::לא נמצאו ברייפים ב-{root}/")
        return 1
    # המהדורה שנכתבה בריצה הזו — שאר הקבצים יצאו מגיט באותו רגע, והיא נכתבה אחריהם
    newest = max(files, key=lambda f: f.stat().st_mtime)
    fields_new = len(FIELD.findall(newest.read_text(encoding="utf-8")))

    changed, odd, total, new_leaks = {}, [], {"gmail": 0, "files": 0, "unknown": 0}, None
    for f in files:
        d, n = fix(f, gmail=f.name >= GMAIL_FROM, files=f.name >= FILES_FROM)
        if d:
            changed[f.name] = d
        for k in total:
            total[k] += n[k]
        if f == newest:
            new_leaks = n
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
    # **מספרים בלבד** — האנוטציות ציבוריות. דליפה במהדורה החדשה היא האות: הכלל
    # ב-CLAUDE.md (מעקה 9) לא נשמר, והניקוי כאן הוא רשת הביטחון ולא התיקון.
    if total["gmail"] or total["files"]:
        print(f"::notice title=דליפות שנוקו::קישורי Gmail {total['gmail']} · "
              f"שמות קבצים {total['files']} ב-{len(changed)} ברייפים")
    if new_leaks and (new_leaks["gmail"] or new_leaks["files"] or fields_new):
        print(f"::warning title=דליפות במהדורה החדשה::{newest.name}: קישורי Gmail "
              f"{new_leaks['gmail']} · שמות קבצים {new_leaks['files']} (נוקו) · "
              f"שמות שדות בגרש הפוך {fields_new} (לא נוקו)")
    if total["unknown"]:
        print(f"::notice title=שמות קבצים לא מוכרים::{total['unknown']} אזכורים נשארו "
              "כמות שהם — להוסיף ל-PUBLIC ב-scripts/normalize_briefs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "output"))
