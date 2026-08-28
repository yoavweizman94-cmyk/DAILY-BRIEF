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
    "אינדקס הדוחות": "maya-watch.yml",
    "סיכומי דיווחים": "maya-watch.yml",
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


def alert(lines: list[str], subject: str = "TLV TASE View — נתונים לא טריים") -> None:
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
                          json={"subject": subject, "text": text}, timeout=30)
    except Exception as e:
        print(f"::warning::שליחת ההתראה נכשלה: {type(e).__name__}: {e}")
        return
    if r.ok:
        print("ההתראה נשלחה במייל")
    else:
        print(f"::warning::שליחת ההתראה נכשלה: {r.status_code} {r.text[:150]}")


# מזהה מרחב ה-KV של המשתמשים. אותו ערך שמופיע ב-users-admin.yml
# וב-access-flow-check.yml; הוא מזהה ולא סוד.
USERS_KV = "b437bf78b9bc4f358b6d0b4a64e0ad94"

# כתובת הבדיקה של access-flow-check. היא עשויה להישאר ממתינה לתמיד,
# ולכן אינה מפעילה התראה — אחרת ההתראה על בקשה אמיתית תיקבר תחת רעש.
TEST_ADDRESS = "access-check@tlvtaseview.com"


def mask_email(e: str) -> str:
    """כתובת בצורה שמאפשרת זיהוי בידי מי שמכיר אותה, ולא בידי אחר."""
    local, _, dom = (e or "").partition("@")
    keep = local[:2] if len(local) > 3 else local[:1]
    return f"{keep}{'*' * max(1, len(local) - len(keep))}@{dom}"


def pending_requests() -> list[dict] | None:
    """בקשות גישה שממתינות לאישור, ישירות מ-KV.

    **המייל בהרשמה הוא ערוץ יחיד, והוא נכשל פעמיים.** ההרשמה יוצרת
    חשבון ממתין ואז מנסה לשלוח התראה; אם השליחה נופלת — מפתח פסול,
    דומיין שאינו מאומת, ספק שנפל — החשבון נשמר והבעלים אינו יודע דבר.
    שתי הפעמים נראו זהות מבחוץ: אדם ביקש גישה, ולא קרה כלום.

    הבדיקה כאן קוראת את המקור עצמו במקום להסתמך על ההתראה, ולכן היא
    תופסת גם הרשמה שההודעה עליה מעולם לא נשלחה. היא רצה בכל שעה עם
    שאר משמר הטריות ואינה דורשת סוד חדש — האסימון של Cloudflare כבר
    כאן בשביל בדיקת הפריסה.

    מחזיר None כשאי אפשר היה לקרוא — מצב שאינו "אין בקשות".
    """
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token or not account:
        return None
    import requests
    base = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
            f"/storage/kv/namespaces/{USERS_KV}")
    head = {"Authorization": f"Bearer {token}"}
    out: list[dict] = []
    cursor = None
    try:
        while True:
            params = {"prefix": "user:", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(f"{base}/keys", headers=head, params=params, timeout=30)
            if r.status_code != 200:
                print(f"::warning::קריאת רשימת המשתמשים נכשלה: {r.status_code}")
                return None
            body = r.json()
            for k in body.get("result") or []:
                name = k.get("name") or ""
                if not name.startswith("user:"):
                    continue
                v = requests.get(f"{base}/values/{name}", headers=head, timeout=30)
                if v.status_code != 200:
                    continue
                try:
                    u = v.json()
                except ValueError:
                    continue
                if (u or {}).get("status") != "pending":
                    continue
                out.append({
                    "email": name[5:],
                    "name": (u.get("name") or "").strip(),
                    "org": (u.get("org") or "").strip(),
                    "why": (u.get("why") or "").strip(),
                    "created": (u.get("created") or "")[:16].replace("T", " "),
                })
            cursor = (body.get("result_info") or {}).get("cursor") or None
            if not cursor:
                break
    except Exception as e:  # noqa: BLE001
        print(f"::warning::קריאת רשימת המשתמשים נכשלה: {type(e).__name__}")
        return None
    out.sort(key=lambda r: r["created"], reverse=True)
    return out


def last_deploy() -> tuple[str, str] | None:
    """(מתי, מזהה) של הפריסה האחרונה ל-Cloudflare Pages.

    **תוכן שנבנה אינו תוכן שמוגש.** כל הכשלים שחזרו כאן ישבו בפער הזה:
    צינור שדוחף לריפו התוכן בלי לפרוס, פריסה שרצה לפני שהתוכן הגיע,
    בנייה שהצליחה על ראנר שאיש לא ראה. בדיקת קובץ ב-output אינה מוכיחה
    שהקורא רואה אותו, ולכן נבדק גם מה נפרס בפועל ומתי.
    """
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    project = os.environ.get("CF_PAGES_PROJECT", "forest-brief")
    if not token or not account:
        return None
    try:
        import requests
        r = requests.get(
            f"https://api.cloudflare.com/client/v4/accounts/{account}"
            f"/pages/projects/{project}/deployments",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 1}, timeout=30)
        if r.status_code != 200:
            return None
        rows = (r.json() or {}).get("result") or []
        if not rows:
            return None
        d = rows[0]
        return d.get("created_on", "")[:16].replace("T", " "), d.get("short_id", "")
    except Exception:
        return None


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
                    help="לשלוח התראה במייל כשמשהו אינו טרי")
    # **ערוץ שמעולם לא העביר הודעה אינו ערוץ.** הדגל הזה שולח הודעת
    # בדיקה בלי קשר למצב, כדי שאפשר יהיה לאמת את הנתיב מקצה לקצה —
    # ולא לגלות שהוא שבור דווקא ביום שבו הוא באמת נדרש.
    ap.add_argument("--test-alert", action="store_true",
                    help="לשלוח הודעת בדיקה ולצאת")
    args = ap.parse_args()

    if args.test_alert:
        alert(["זו הודעת בדיקה של נתיב ההתראות.",
               "אם היא הגיעה — כל תקיעה בצנרת תדווח לכאן מעצמה,",
               "עם הסיבה, שלוש פעמים ביום.", "",
               "אין צורך בפעולה."])
        return 0

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
    #
    # **שלושת אלה נוספו ב-28/08/2026 אחרי שיואב דיווח שהם ישנים.**
    # אינדקס הדוחות ("עמוד הדוחות") ודיווחי מאיה ("עמוד הדיווחים")
    # הם מה שהאתר מציג בפועל, והמשמר לא בדק אותם כלל — כלומר הוא היה
    # ירוק בדיוק בזמן שהעמודים היו תקועים.
    #
    # מאיה מפרסמת רצוף, ולכן הסף כאן צמוד: יום מסחר אחד.
    for label, dirname, pattern, field, limit, hint in (
        ("אינדקס הדוחות", "filings", "[0-9][0-9][0-9][0-9].jsonl", "d", 1, "Maya Watch"),
        ("סיכומי דיווחים", "reports", "*.jsonl", "ts", 2, "Maya Watch"),
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

    # --- מה נפרס בפועל, ומתי ---
    dep = last_deploy()
    if dep:
        when, sid = dep
        rows.append(("פריסה אחרונה", when[:10], when[11:], sid))
        # פריסה שקדמה לברייף האחרון פירושה שהאתר מגיש בנייה ישנה יותר
        # מהתוכן שכבר קיים — הפער שגרם לכך שהעמודים הראו את אתמול.
        if b and when[:10] < b[0]:
            bad.append(f"הפריסה האחרונה ({when}) קדמה לברייף של {b[0]} — "
                       "האתר מגיש בנייה ישנה מהתוכן הקיים.")
            tg.append(("פריסת האתר", when[:10], "ישנה מהתוכן"))
    else:
        rows.append(("פריסה אחרונה", "—", "לא נבדקה", "חסר CLOUDFLARE_API_TOKEN"))

    w = max(len(r[0]) for r in rows) if rows else 10
    print("מצב טריות:")
    for label, day, age, extra in rows:
        print(f"  {label:{w}}  {day:12} {age:16} {extra}")

    # **הדוח נאמר גם כשהכל תקין.** לוגים של Actions דורשים הזדהות ואינם
    # נקראים מבחוץ, ואילו אנוטציה נקראת. בלעדיה כל מה שרואים על ריצה
    # תקינה הוא "ירוק" — וזה בדיוק הסימן שהתברר כחסר ערך כאן: הריצות
    # היו ירוקות בכל אחד מהימים שבהם התוצר היה תקוע. שורה אחת שאומרת
    # מה נמדד בפועל הופכת את הבדיקה לניתנת לאימות מבחוץ.
    print("::notice title=מצב טריות::"
          + " · ".join(f"{label} {day} ({age})" for label, day, age, _ in rows))

    # **בקשת גישה שאיש אינו רואה שווה לבקשה שלא הוגשה.** פעמיים נרשם
    # אדם ולא הגיעה הודעה, ושתי הפעמים התגלו רק כשיואב שאל. הבדיקה
    # קוראת את המקור ואינה תלויה בכך שההתראה בהרשמה נשלחה בהצלחה.
    #
    # אינה נספרת ב-bad ואינה מפילה את הריצה: אדם שממתין לאישור אינו
    # תקלת נתונים. היא כן שולחת מייל, וכן חוזרת בכל שעה עד האישור.
    pend = pending_requests()
    if pend is None:
        print("::warning::לא ניתן היה לקרוא את רשימת המשתמשים — "
              "בקשות גישה ממתינות אינן נבדקות בריצה הזו")
    else:
        real = [u for u in pend if u["email"] != TEST_ADDRESS]
        if real:
            print(f"\n::warning title=בקשות גישה ממתינות::{len(real)} — "
                  + "%0A".join(f"{u['name'] or 'ללא שם'} · {mask_email(u['email'])}"
                               f" · נרשם {u['created'] or '—'}" for u in real))
            if args.alert:
                lines = ["מישהו ביקש גישה ל-TLV TASE View וטרם אושר.", ""]
                for u in real:
                    lines.append(f"• {u['name'] or 'ללא שם'} — {u['email']}")
                    if u["org"]:
                        lines.append(f"   גוף: {u['org']}")
                    if u["why"]:
                        lines.append(f"   מה מעניין אותו: {u['why'][:200]}")
                    lines.append(f"   נרשם: {u['created'] or '—'}")
                lines += ["",
                          "האישור נעשה בעמוד החשבון באתר, בסעיף בקשות הגישה.",
                          "ההודעה חוזרת בכל שעה עד שהחשבון יאושר או יימחק."]
                alert(lines, subject=f"בקשת גישה ממתינה ({len(real)})")
        else:
            print("בקשות גישה ממתינות: אין")

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
