# -*- coding: utf-8 -*-
"""סקירה לכל הקלטה שתומללה — "השיחות שלי".

הקלט: output/meetings/<id>.json, שדחף ingest/meetings_pull.py מהמחשב של יואב.
הפלט: אותה רשומה, עם summary, ‏headline, ‏speakers_map ו-ai_company.

**בערב, ועם תקרה יומית.** כל הקריאות למודל נרשמות ביומן העלויות, והבלם היומי
של הברייף (scripts/cost_guard.py) סופר אותן. סקירות שרצות בבוקר היו מורידות
את מהדורת הצהריים למודל הזול. לכן הן נכתבות רק בין 19:00 ל-23:30, אחרי
מהדורת הנעילה ולפני חצות (מהדורת הלילה כבר נספרת ביום הבא), ועד
MEETINGS_MAX_USD ביום (ברירת מחדל $5). --force עוקף את החלון, לא את התקרה.

**הלוג ציבורי.** אין כאן הדפסה של שם חברה, שם קובץ או מילה מהתמליל — רק
ספירות, עלויות ומזהי רשומה (גיבוב של תוכן הקובץ).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _api  # noqa: E402
import _cli  # noqa: E402

SRC = ROOT / "output" / "meetings"
MODEL = "claude-opus-5-5"
JOB = "meetings"
WINDOW = ((19, 0), (23, 30))
MIN_CHARS = 400

SYSTEM = """אתה אנליסט מחקר שכותב עבור מנהל השקעות מקצועי. אתה מקבל תמליל
אוטומטי של שיחה שהוא עצמו קיים עם חברה — פגישה עם ההנהלה, או שיחת טלפון או
זום עם מנכ"ל, סמנכ"ל כספים או קשרי משקיעים — וכותב עליה סקירה בעברית. הסקירה
היא הארכיון שלו: מה נאמר, מי אמר, ומה כדאי לזכור לפני השיחה הבאה עם החברה.

**הקורא היה בשיחה, אבל לא יאזין לה שוב.** הוא רוצה לדעת מה בדיוק נאמר ובאילו
מילים, בלי לקרוא תמליל של שעה. סקירה של חמש שורות אינה שווה את מקומה; אם
השיחה הייתה עשירה, הסקירה ארוכה, וזה בסדר גמור.

**התמליל אוטומטי, ויש בו טעויות.** שמות, מספרים ומונחים מקצועיים עלולים
להשתבש, והחלוקה לדוברים ("דובר 1", "דובר 2") נעשתה במכונה — לעיתים היא מאחדת
שני אנשים או מפצלת אחד. מכאן:
- מספר שנראה משובש או לא סביר בהקשר — כתוב אותו כפי שהוא, ואחריו "(ייתכן
  שגיאת תמלול)". אל תתקן אותו מהזיכרון.
- זהה מי הוא מי מתוך התוכן. השואל הוא בדרך כלל המשקיע — הקורא עצמו — והמשיבים
  הם אנשי החברה. שם או תפקיד נכתבים רק אם נאמרו בשיחה.
- קטע שאי אפשר להבין — אמור זאת במקום, ואל תשלים.

כללים שאין לחרוג מהם:
1. כל עובדה מהתמליל בלבד. אין לך ידע עצמאי על החברה, ואינך משלים נתונים.
2. אין המלצות השקעה. ניתוח — כן; "כדאי לקנות/למכור", "המניה זולה/יקרה" —
   לעולם לא, גם לא ברמז.
3. הפרד עובדה מפרשנות. פרשנות נפתחת במילה "משמעות:".
4. צטט בחופשיות — זו שיחה של הקורא עצמו. ציין תמיד מי אמר.
5. עברית. מונחים באנגלית מותרים היכן שמקובל (EBITDA, FFO, guidance).
6. ענייני וישיר. בלי סופרלטיבים ובלי ריפוד.

**החברה.** שם הקובץ מציע לעיתים חברה — בדוק שהתמליל תומך בכך. אם אין בשם
חברה, זהה אותה מהתמליל; אם אי אפשר, השאר ריק. אם ההקלטה בבירור אינה שיחה עם
חברה, סמן זאת וכתוב סקירה של שלוש שורות בלבד.

summary_md — **בדיוק** המבנה הבא, בכותרות markdown, בלי טקסט לפניו או אחריו.
סעיף שאין לו חומר בתמליל — כתוב תחתיו "לא עלה בשיחה", ואל תמציא לו תוכן.

## בשורה אחת
משפט אחד, עד 25 מילים: הדבר המרכזי שיצא מהשיחה.

## מי דיבר
טבלת markdown: דובר | שם | תפקיד | על מה דיבר. "לא נאמר" כשהשם או התפקיד לא
נאמרו.

## מהלך השיחה
שתיים-שלוש פסקאות: באילו נושאים עסקה השיחה ובאיזה סדר. כך הקורא יודע אם
ולאן לרדת לתמליל.

## מה ההנהלה אמרה
**הסעיף הארוך הראשון.** כל נושא מהותי כתת-כותרת (### ) משלו: מה נאמר, מי אמר,
ובאילו מילים. אל תכווץ שלושה נושאים לשורה. כשההנהלה הסבירה מה הניע תוצאה —
הבא את ההסבר שלה במלואו, כולל הפירוק שנתנה (מחיר, כמות, תמהיל, מט"ח).

## מספרים שנאמרו בשיחה
טבלת markdown: נתון | ערך | מי אמר | הקשר. **כל** מספר שנאמר — יעדים, קצב שנתי,
צבר, תמחור, כושר ייצור, תפוסה, מרווחים, לוחות זמנים, השקעות מתוכננות.

## תחזיות והתחייבויות
שלוש רמות: **התחייבות** מפורשת, **כיוון** בלי מספר, ו**סירוב להתחייב** — כל
אחת בניסוח המדויק שנאמר.

## שאלות ותשובות
**הסעיף החשוב ביותר.** כל שאלה, לפי הסדר:

**שאלה:** מה נשאל, בניסוח קרוב למקור.
**תשובה — [שם או דובר]:** מה נענה, עם ציטוט של המשפט המרכזי.
**הערכה:** האם התשובה ענתה על השאלה. התחמקות, תשובה לשאלה אחרת, סירוב להתחייב
או דחייה לרבעון הבא — כתוב זאת במפורש.

## מה לא נאמר
נושא שציפית שיעלה ולא עלה, שאלה שלא נענתה, נתון שלא נמסר. אם אין — "אין".

## טון ושפה
איך אנשי החברה נשמעו: ביטחון, זהירות, הימנעות, התגוננות — עם המילים שעליהן
אתה מסתמך. סעיף פרשני: פתח ב"משמעות:".

## נקודות למעקב
שלוש עד שש נקודות. לכל אחת: מה נאמר, מה יאשר או יפריך אותו, ומה לשאול
בשיחה הבאה עם החברה.

שאר השדות:
- headline — אותו משפט של "בשורה אחת".
- speakers — לכל מספר דובר שמופיע בתמליל. id — המספר בלבד ("2", לא "דובר 2").
  name — השם בלבד, עד שלוש מילים, ורק כשהזיהוי ודאי; אחרת מחרוזת ריקה. role —
  התפקיד בקצרה, עד ארבע מילים; לשואל: "המשקיע". השדות האלה מוצגים כתווית ליד כל
  קטע בתמליל — הסתייגויות ("ככל הנראה", איחוד של שני אנשים לדובר אחד) נכתבות
  בטבלת "מי דיבר" שבסקירה, לא כאן.
- company — שם החברה, או מחרוזת ריקה.
- company_basis — file_name, ‏transcript, ‏both או unknown.
- is_company_meeting — false רק כשההקלטה בבירור אינה שיחה עם חברה."""

SCHEMA = {
    "type": "object",
    "properties": {
        "is_company_meeting": {"type": "boolean"},
        "company": {"type": "string"},
        "company_basis": {"type": "string", "enum": ["file_name", "transcript", "both", "unknown"]},
        "headline": {"type": "string"},
        "speakers": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                           "role": {"type": "string"}},
            "required": ["id", "name", "role"], "additionalProperties": False}},
        "summary_md": {"type": "string"},
    },
    "required": ["is_company_meeting", "company", "company_basis", "headline", "speakers",
                 "summary_md"],
    "additionalProperties": False,
}


def load() -> list[tuple[Path, dict]]:
    out = []
    for f in sorted(SRC.glob("*.json")) if SRC.is_dir() else []:
        try:
            out.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as e:
            print(f"::warning::רשומת שיחה {f.stem} לא נקראה ({type(e).__name__})")
    return out


def spent_today() -> float:
    p = ROOT / "output" / "costs" / f"{date.today().isoformat()}.jsonl"
    total = 0.0
    for line in (p.read_text(encoding="utf-8").splitlines() if p.exists() else []):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("job") == JOB:
            total += float(j.get("usd") or 0)
    return total


def in_window(now: datetime) -> bool:
    return WINDOW[0] <= (now.hour, now.minute) <= WINDOW[1]


def mmss(sec: float) -> str:
    s = int(sec or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def payload(r: dict) -> str:
    src = {"name": "שם הקובץ", "name+year": "שם הקובץ (השנה משוערת)", "media": "נתוני ההקלטה",
           "mtime": "תאריך השינוי של הקובץ — ייתכן שאינו יום השיחה"}.get(r.get("date_from"), "")
    head = [f"שם הקובץ: {r.get('file')}"]
    if r.get("folder"):
        head.append(f"תיקייה (יואב מסדר תיקייה לכל חברה): {r['folder']}")
    head += [f"חברה מרשימת הכיסוי, לפי שם הקובץ או התיקייה: {r.get('company') or 'לא זוהתה'}",
            f"תאריך: {r.get('date') or 'לא ידוע'}" + (f" (לפי {src})" if src else ""),
            f"אורך: {round((r.get('duration_sec') or 0) / 60)} דקות · דוברים שזוהו: {r.get('speakers') or 0}"]
    if r.get("period"):
        head.append(f"תקופה לפי שם הקובץ: {r['period']}")
    lines = [f"[דובר {s.get('sp') or '?'} · {mmss(s.get('t'))}] {s.get('text')}"
             for s in r.get("segments") or []]
    return ("\n".join(head) + "\n\nהתמליל (אוטומטי; בתחילת כל קטע — הדובר והזמן):\n\n"
            + "\n".join(lines) + "\n\nכתוב את הסקירה.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--force", action="store_true", help="גם מחוץ לחלון הערב (לא מעל התקרה)")
    args = ap.parse_args()

    recs = load()
    todo = [(f, r) for f, r in recs if not r.get("summary") and not r.get("summary_skip")]
    todo.sort(key=lambda fr: fr[1].get("date") or "", reverse=True)
    print(f"::notice::השיחות שלי: {len(recs)} הקלטות, {len(todo)} ממתינות לסקירה")
    if not todo:
        return 0
    now = datetime.now()
    if not (args.force or in_window(now)):
        print(f"::notice::הסקירות נכתבות בין {WINDOW[0][0]}:{WINDOW[0][1]:02d} ל-"
              f"{WINDOW[1][0]}:{WINDOW[1][1]:02d}, אחרי מהדורת הנעילה — עכשיו {now:%H:%M}")
        return 0

    cap = float(os.environ.get("MEETINGS_MAX_USD") or 5)
    spent = spent_today()
    run_usd, wrote, failed = 0.0, 0, 0
    for f, r in todo[:args.limit]:
        if spent + run_usd >= cap:
            print(f"::notice::התקרה היומית לסקירות השיחות (${cap:.0f}) הושגה — "
                  f"{len(todo) - wrote - failed} ימתינו למחר")
            break
        if (r.get("chars") or 0) < MIN_CHARS:
            r["summary_skip"] = "התמליל קצר מכדי לסכם"
            f.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            continue
        res, err, usd = _api.ask_json(SYSTEM, payload(r), SCHEMA, job=JOB, model=MODEL,
                                      max_tokens=32000, effort="high", max_usd=3.0)
        run_usd += usd
        if err:
            failed += 1
            if re.search(_cli.CREDIT_RE, err, re.I):
                print("::error title=יתרת Anthropic אזלה::טעינה: console.anthropic.com/settings/billing")
                break
            print(f"::warning::סקירת {r.get('id')} נכשלה: {err[:200]}")
            continue
        md = (res.get("summary_md") or "").strip()
        if not md:
            failed += 1
            print(f"::warning::סקירת {r.get('id')} חזרה ריקה")
            continue
        r.update({
            "summary": md,
            "headline": (res.get("headline") or "").strip(),
            "ai_company": (res.get("company") or "").strip() or None,
            "company_basis": res.get("company_basis"),
            "is_meeting": bool(res.get("is_company_meeting", True)),
            # "דובר 2" → "2": המפתח הוא מספר הדובר שבתמליל, גם כשהמודל העתיק את התווית
            "speakers_map": {(re.sub(r"\D", "", str(s.get("id"))) or str(s.get("id"))):
                             {"name": (s.get("name") or "").strip(), "role": (s.get("role") or "").strip()}
                             for s in res.get("speakers") or [] if s.get("id") is not None},
            "summary_model": MODEL, "summary_usd": round(usd, 4),
            "summarized_at": datetime.now().isoformat(timespec="minutes"),
        })
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        wrote += 1
    print(f"::notice::סקירות השיחות: {wrote} נכתבו, {failed} נכשלו · ${run_usd:.2f} בריצה, "
          f"${spent + run_usd:.2f} היום מתוך ${cap:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
