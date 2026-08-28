# -*- coding: utf-8 -*-
"""משמר טריות: האם כל זרם נתונים התעדכן בזמן שהוא אמור.

**למה זה קיים.** במשך יומיים יואב גילה בעצמו שדברים תקועים — ברייף של
אתמול, עסקאות שלא זזו, תמלולים חסרים — ובכל פעם הריצות היו ירוקות.
ריצה מוצלחת אינה מבטיחה שהתוצר עודכן: היא יכולה לצאת מוקדם, לדחוף
לריפו התוכן בלי לפרוס, או להיכשל במקור בודד ולהמשיך.

הבדיקה כאן היא על **התוצר עצמו** ולא על הריצה שהייתה אמורה לייצר
אותו, ולכן היא תופסת גם כשל שאיש לא חשב עליו.

**היא קובעת ואינה מדפיסה.** זרם שחרג מהסף מדווח כשגיאה עם קוד יציאה
1 — הדפסה שאיש אינו קורא היא בדיוק הכשל שהיא נועדה לתפוס.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

IL = timezone(timedelta(hours=3))


# --- למה זה נשבר, לא רק שזה נשבר -------------------------------------
# **התראה שאומרת "תקוע" מחייבת חקירה; התראה שאומרת "תקוע כי היתרה
# אזלה" מחייבת פעולה אחת.** הסיבה נשלפת מהריצה האחרונה של הצינור
# הרלוונטי — אותן אנוטציות שממילא נכתבות שם.
CAUSES = (
    ("credit balance", "יתרת Anthropic אזלה"),
    ("אינו מזוהה", "עוגיית גלובס פגה"),
    ("הסשן אינו", "עוגיית גלובס פגה"),
    ("overloaded", "עומס בצד המודל"),
    ("לא הופק ברייף", "הריצה יצאה בלי להפיק ברייף"),
    ("rate limit", "מגבלת קצב"),
)

WORKFLOWS = {
    "ברייף": "daily-brief.yml",
    "עסקאות מחוץ לבורסה": "offex-backfill.yml",
    "דיווחי בעלי עניין": "offex-backfill.yml",
    "תמלולי שיחות": "globes-calls.yml",
}


def last_failure_reason(workflow: str) -> str | None:
    """הסיבה מהריצה האחרונה של אותו workflow, אם היא נכשלה."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    api = f"https://api.github.com/repos/{repo}"
    h = {"Authorization": f"Bearer {token}",
         "Accept": "application/vnd.github+json"}
    try:
        import requests
        runs = requests.get(f"{api}/actions/workflows/{workflow}/runs",
                            headers=h, params={"per_page": 1}, timeout=30)
        if runs.status_code != 200:
            return None
        rows = runs.json().get("workflow_runs") or []
        if not rows or rows[0].get("conclusion") == "success":
            return None
        jobs = requests.get(rows[0]["jobs_url"], headers=h, timeout=30).json()
        for job in jobs.get("jobs", []):
            ann = requests.get(f"{api}/check-runs/{job['id']}/annotations",
                               headers=h, timeout=30)
            for a in (ann.json() if ann.status_code == 200 else []):
                msg = (a.get("message") or "") + " " + (a.get("title") or "")
                low = msg.lower()
                for needle, label in CAUSES:
                    if needle.lower() in low:
                        return label
        return "הריצה נכשלה"
    except Exception:
        return None


def alert(lines: list[str]) -> None:
    """שולח את ההתראה **במייל**, דרך נתיב ההתראות של האתר.

    **בלי זה יואב הוא מערכת הניטור.** האתר כבר מסמן "ברייף מאתמול",
    והבדיקה כאן כבר נכשלת אדום — ובכל זאת, שלושה ימים ברציפות הוא זה
    שגילה שמשהו תקוע. ערוץ שדורש ממנו לפתוח דף כדי לדעת אינו התראה.

    **למה דרך האתר.** מפתח הדואר יושב בסביבת Cloudflare ולא בסודות של
    GitHub, ואין סיבה לשכפל סוד לשני מקומות. SCAN_KEY כבר קיים בשניהם
    — הוא משמש את ממסר Govmap מאותה סיבה — ולכן הוא המפתח כאן.

    (טלגרם היה הניסיון הראשון ונזנח: הסודות שלו מעולם לא הוגדרו, וכל
    קריאה אליו בצנרת נכשלה בשקט מאז ומעולם.)
    """
    key = os.environ.get("SCAN_KEY")
    base = os.environ.get("ALERT_BASE", "https://app.tlvtaseview.com")
    if not key:
        print("::warning::SCAN_KEY אינו מוגדר — ההתראה במייל לא נשלחה")
        return
    import requests
    text = "\n".join(lines)
    try:
        r = requests.post(f"{base}/api/alert",
                          headers={"x-scan-key": key,
                                   "Content-Type": "application/json"},
                          json={"subject": "TLV TASE View — נתונים לא טריים",
                                "text": text}, timeout=30)
    except Exception as e:
        print(f"::warning::שליחת ההתראה נכשלה: {type(e).__name__}: {e}")
        return
    if r.ok:
        print("ההתראה נשלחה במייל")
    else:
        print(f"::warning::שליחת ההתראה נכשלה: {r.status_code} {r.text[:150]}")


def newest_brief() -> tuple[str, str] | None:
    """(תאריך, שם) של הברייף האחרון."""
    files = sorted(OUT.glob("brief_????-??-??*.md"))
    if not files:
        return None
    f = files[-1]
    return f.name[6:16], f.name


def newest_jsonl(dirname: str, pattern: str, field: str) -> str | None:
    """התאריך המאוחר ביותר בשדה `field` על פני קובצי JSONL בתיקייה."""
    d = OUT / dirname
    if not d.is_dir():
        return None
    best = None
    for f in sorted(d.glob(pattern)):
        for line in f.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                v = json.loads(line).get(field)
            except json.JSONDecodeError:
                continue
            if v and (best is None or str(v) > best):
                best = str(v)[:10]
    return best


def business_days_since(day: str, today: date) -> int:
    """כמה ימי מסחר חלפו. הבורסה נסחרת שני–שישי מינואר 2026, ולכן
    שבת וראשון אינם פיגור אלא לוח השנה."""
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return 999
    n = 0
    while d < today:
        d += timedelta(days=1)
        if d.weekday() not in (5, 6):   # שבת=5, ראשון=6
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true",
                    help="לשלוח התראה לטלגרם כשמשהו אינו טרי")
    args = ap.parse_args()

    today = datetime.now(IL).date()
    rows, bad, tg = [], [], []

    # --- הברייף: נכתב שלוש פעמים ביום, כל יום ---
    b = newest_brief()
    if not b:
        bad.append("אין אף ברייף ב-output")
    else:
        day, name = b
        age = (today - date.fromisoformat(day)).days
        rows.append(("ברייף", day, f"{age} ימים", name))
        if age >= 1:
            bad.append(f"הברייף האחרון הוא של {day} — {age} ימים. "
                       "בדוק את Daily Brief; פעימות ההשלמה היו אמורות לתפוס זאת.")
            tg.append(("ברייף", day, f"{age} ימים"))

    # --- זרמים שנגזרים ממסחר: נמדדים בימי מסחר ---
    for label, dirname, pattern, field, limit, hint in (
        ("עסקאות מחוץ לבורסה", "otc", "*.jsonl", "date", 3, "Offex Backfill"),
        ("דיווחי בעלי עניין", "offex", "*.jsonl", "date", 3, "Offex Backfill"),
        ("תמלולי שיחות", "calls", "transcripts_*.jsonl", "date", 4, "Globes Calls"),
    ):
        day = newest_jsonl(dirname, pattern, field)
        if not day:
            rows.append((label, "—", "אין נתונים", hint))
            bad.append(f"{label}: אין נתונים כלל ב-output/{dirname}")
            tg.append((label, "—", "אין נתונים"))
            continue
        n = business_days_since(day, today)
        rows.append((label, day, f"{n} ימי מסחר", hint))
        if n > limit:
            bad.append(f"{label}: הרשומה האחרונה היא מ-{day} — {n} ימי מסחר. "
                       f"בדוק את {hint}.")
            tg.append((label, day, f"{n} ימי מסחר"))

    w = max(len(r[0]) for r in rows) if rows else 10
    print("מצב טריות:")
    for label, day, age, extra in rows:
        print(f"  {label:{w}}  {day:12} {age:16} {extra}")

    if bad:
        print()
        for msg in bad:
            print(f"::error title=נתונים לא טריים::{msg}")
        if args.alert and tg:
            lines = []
            for label, day, age in tg:
                wf = WORKFLOWS.get(label)
                why = last_failure_reason(wf) if wf else None
                lines.append(f"• <b>{label}</b> — {day} ({age})"
                             + (f"\n   הסיבה: {why}" if why else ""))
            lines += ["", "הצינורות ממשיכים לנסות. הודעה זו נשלחת עד שהמצב נפתר."]
            alert(lines)
        return 1
    print("\nכל הזרמים בתוך הסף.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
