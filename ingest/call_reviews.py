# -*- coding: utf-8 -*-
"""דוח ושיחה: סקירה אחת לדוח כספי ולשיחת הוועידה שבה ההנהלה הציגה אותו.

**הפוסט ל-X נכתב ממנה בנפרד** (scripts/x_threads.py, מ-11/11/2026), כמו לסקירות
הדוחות ולשיחות המשקיעים: פוסט אחד שנפתח בתובנה, ולא שרשור. עד אז הסקירה החזירה
גם שרשור של עד שלושה ציוצים, כאן, בקריאה של אופוס.

**מה נפגש כאן, ולמה זה לא עוד סיכום.** סקירת הדוח (filing_review.py) אומרת
מה במספרים; סיכום השיחה (globes_calls.py) אומר מה ההנהלה אמרה. כל אחד מהם
כבר נקרא לבד. הערך הוא במפגש — מה השיחה הוסיפה על הדוח, ואיפה היא והמספרים
לא מתיישבים. יואב ביקש ב-03/11/2026 "סיכום מועיל ויעיל עם דגשים על מה שחשוב".

**הצמדה לפי חברה ותאריך.** לשיחה של גלובס יש שם חברה מהכיסוי ותאריך; הדוח
הוא הדוח הכספי של אותה חברה שפורסם עד 21 יום לפניה או עד 3 ימים אחריה.
נמדד על 75 שיחות של 2026: 58 התקיימו ביום הדוח, והרחוקה 20 יום אחריו. כשיש
כמה מועמדים, דוח של החברה עצמה גובר על דוח של חברה בת, על מצגת ועל תיקון —
והמודל מאמת בעצמו שהדוח והשיחה הם אותה חברה ואותו רבעון.

**סקירת הדוח נקראת פעם אחת.** לפי הסדר: הסקירה שבריפו (filings/reviews), זו
שנשמרה ב-KV אחרי לחיצה בעמוד הדוחות, ורק אם אין — סקירה חדשה מה-PDF, שנשמרת
לריפו ומוגשת מאז גם בעמוד הדוחות. כשיש סקירה, הצמד עולה כ-30 סנט; כשאין,
עוד כדולר וחצי, כי הדוח נקרא כולו.

**רק דוחות חדשים.** סקירה נכתבת רק לדוח שפורסם ב-14 הימים האחרונים, ואין
מילוי לאחור — יואב ב-04/11/2026: "רק על הדוחות החדשים שמתפרסמים". שבועיים ולא
יום: השיחה מגיעה לפעמים ימים אחרי הדוח, וריצה שהחמיצה ערב צריכה להשלים.

**שני חלונות ותקרה אחת.** 15:00–16:30 ו-19:00–23:30; את 15:00 ביקש יואב
ב-04/11/2026. הסקירות אינן נספרות בבלם של הברייף (scripts/cost_guard.py):
הריצה של 15:00 קודמת למהדורת הנעילה, שמתחילה ממילא קרוב לסף הקשה ($29.73
מתוך $30 ב-03/11), ואילו נספרו — הנעילה הייתה מבוטלת בדיוק בימי הדוחות.
במקום זה יש להן תקרה משלהן, CALL_REVIEWS_MAX_USD ליום (ברירת מחדל $8),
משותפת לשני החלונות. --force עוקף את החלונות, לא את התקרה.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.append(str(ROOT / "site"))  # בסוף: ל-site ול-scripts יש מודולים באותו שם

import filing_review as fr  # noqa: E402  (מקשיח את ה-TLS בעצמו, לפני anthropic)

import anthropic  # noqa: E402

import _api  # noqa: E402
import _cli  # noqa: E402
from _filings import has_pdf, is_financial  # noqa: E402

CALLS = ROOT / "output" / "calls"
OUT = CALLS / "combined"
JOB = "call-reviews"
MODEL = "claude-opus-5-5"
WINDOWS = (((15, 0), (16, 30)), ((19, 0), (23, 30)))
BEFORE, AFTER = 21, 3        # ימים: הדוח לפני השיחה, או אחריה
NEW_DAYS = 14                # רק דוח שפורסם בשבועיים האחרונים — ראה למעלה
MAX_TRIES = 2                # ניסיונות בתשלום לפני שמוותרים על שיחה
TEXT_CAP = 40_000            # תווי תמליל לאימות; הסיכום הוא העיקר
# דוח של החברה עצמה גובר על אלה כשיש כמה מועמדים באותו חלון.
SIDE = ("חברת הבת", "חברה בת", "חברת בת", "כלולה", "מוחזקת", "מצגת", "תיקון")

# **התקרה של 550 מילים נמוכה בכוונה.** בשתי הסקירות הראשונות (גב ים ואמות,
# 03/11/2026) ההנחיה הייתה "400 עד 700", ויצאו 828 ו-851 מילים — המודל חורג
# מהטווח, ולכן התקרה מנוסחת כתקרה ונמוכה מהיעד האמיתי.
SYSTEM = """אתה אנליסט מחקר שכותב עבור מנהל השקעות מקצועי. אתה מקבל שני
מסמכים על אותה חברה ואותו רבעון: סקירה של הדוח הכספי, שנכתבה מתוך הדוח
המלא, וסיכום של שיחת הוועידה שבה ההנהלה הציגה אותו — ואת תמליל השיחה
לאימות. אתה כותב סקירה אחת שמחברת ביניהם.

**הקורא יכול לקרוא כל אחד מהם לבד.** מה שהוא קונה ממך הוא המפגש: מה
המספרים אומרים, מה ההנהלה הוסיפה עליהם, ואיפה השניים לא מתיישבים. סקירה
שמסכמת את הדוח ואחר כך את השיחה, זה אחר זה, לא עשתה את העבודה.

**יעיל פירושו קצר.** עד 550 מילים לכל הסקירה — זו תקרה, לא יעד. כל משפט
צריך להצדיק את מקומו; נתון שאינו משנה את הקריאה אינו נכנס. מחוץ להדגשים,
כל סעיף של נקודות — עד ארבע, והחשובה ראשונה.

כללים שאין לחרוג מהם:

1. **כל מספר וכל עובדה — מהחומר שקיבלת בלבד.** אין לך ידע עצמאי על החברה.
   אם הסקירה והשיחה סותרות במספר — כתוב את שניהם ואת הסתירה, ואל תכריע.
2. **אין המלצות השקעה.** ניתוח השפעה — כן. "כדאי לקנות/למכור", "המניה
   זולה/יקרה", "הזדמנות", מחיר יעד — לעולם לא, גם לא ברמז. זה חל גם על
   הציוצים, ושם במיוחד: הם פומביים.
3. **הפרד עובדה מפרשנות.** פרשנות נפתחת במילה "משמעות:".
4. **מקור לכל טענה:** "בדוח" או "בשיחה", וכשזה מהשיחה — מי אמר (תפקיד,
   ושם אם נאמר).
5. עברית בלבד. מונחים באנגלית מותרים היכן שמקובל (EBITDA, FFO, NOI,
   guidance). מונח מקצועי צר מקבל הסבר של חצי שורה בסוגריים בהופעתו
   הראשונה.
6. ענייני וישיר. בלי סופרלטיבים, בלי "חשוב לציין", בלי ריפוד.
7. **ודא שזו אותה חברה ואותה תקופה.** אם הדוח והשיחה אינם על אותה חברה
   או על אותו רבעון — same_company=false, ובשדה mismatch_reason מה אינו
   מתיישב; את שאר השדות השאר ריקים. אחרת same_company=true ו-mismatch_reason
   ריק.

review_md — **בדיוק** המבנה הבא, בכותרות markdown, בלי כותרת ראשית ובלי
טקסט לפניו או אחריו. סעיף שאין לו חומר — כתוב תחתיו "לא עלה", ואל תמציא:

## הדגשים
שלוש עד חמש נקודות, לפי חשיבות למנהל השקעות ולא לפי סדר הדוח. כל נקודה:
עובדה אחת עם מספר, ומה היא אומרת. נקודה שמקורה בשיחה מסומנת "(בשיחה)".

## המספרים שחשובים
טבלת markdown, עד שמונה שורות: מדד | התקופה | מקבילה | שינוי | מקור. רק
המספרים שהסיפור עומד עליהם. "מקור" הוא "דוח" או "שיחה".

## מה השיחה הוסיפה על הדוח
מה שנאמר בשיחה ואינו בדוח: ההסבר של ההנהלה למה שהניע את התוצאה, יעדים,
קצב, צבר, תמחור, תוכניות. מי אמר, בקצרה.

## איפה הדוח והשיחה לא נפגשים
מה שהדוח מסמן — סימן שדורש מבט, נתון חסר, שחיקה במרווח, פער בין תזרים
לרווח — וההנהלה לא התייחסה אליו או התחמקה; וטענה של ההנהלה שהמספרים בדוח
אינם תומכים בה. אם לא נמצאו — כתוב "לא נמצאו פערים".

## תחזיות והתחייבויות
מה ההנהלה אמרה על ההמשך, בשלוש רמות: התחייבות מפורשת, כיוון בלי מספר,
סירוב להתחייב. שורה לכל רמה שעלתה.

## מה יאשר או יפריך
שניים-שלושה דברים קרובים — דוח, אבן דרך, החלטה — שיגידו אם הקריאה נכונה.

headline — משפט אחד, עד 25 מילים: הדבר המרכזי שעולה מהדוח ומהשיחה יחד.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "same_company": {"type": "boolean"},
        "mismatch_reason": {"type": "string"},
        "headline": {"type": "string"},
        "review_md": {"type": "string"},
    },
    "required": ["same_company", "mismatch_reason", "headline", "review_md"],
    "additionalProperties": False,
}


# ── הקלט ──────────────────────────────────────────────────────────────
def load_calls() -> list[dict]:
    """שיחות גלובס שסוכמו. מזהה שסוכם פעמיים — המאוחרת גוברת, כמו בעמוד התמלולים."""
    by: dict = {}
    for f in sorted(CALLS.glob("transcripts_*.jsonl")) if CALLS.is_dir() else []:
        # split ולא splitlines: U+2028 יושב כתו גולמי בתוך מחרוזות JSON תקינות
        for line in f.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            by[r.get("did")] = r
    return [r for r in by.values()
            if r.get("did") and r.get("summary") and r.get("company") and r.get("date")]


def index_filings() -> dict[str, list[dict]]:
    """דוחות כספיים עם קובץ, לפי שם חברה כפי שהוא באינדקס."""
    out: dict[str, list[dict]] = {}
    for r in fr.load_index():
        if has_pdf(r) and is_financial(r.get("t")):
            for c in r.get("c") or []:
                out.setdefault(c, []).append(r)
    return out


def find_report(call: dict, by_company: dict[str, list[dict]]) -> dict | None:
    try:
        day = date.fromisoformat(call["date"])
    except ValueError:
        return None
    cands = []
    for r in by_company.get(call["company"], []):
        try:
            d = date.fromisoformat(r.get("d") or "")
        except ValueError:
            continue
        if day - timedelta(days=BEFORE) <= d <= day + timedelta(days=AFTER):
            cands.append(r)
    if not cands:
        return None

    def rank(r: dict) -> tuple:
        own = not any(x in (r.get("t") or "") for x in SIDE)
        return own, (r.get("d") or "") <= call["date"], r.get("d") or ""
    return max(cands, key=rank)


_NS: str | None = None


def kv_get(key: str) -> str | None:
    """ערך מה-KV של האתר — שם יושבות סקירות שנוצרו בלחיצה. בלי סודות Cloudflare: None."""
    global _NS
    if not (os.environ.get("CF_API_TOKEN") and os.environ.get("CF_ACCOUNT_ID")):
        return None
    import kv_request as kv
    if _NS is None:
        _, body = kv.call("/storage/kv/namespaces?per_page=100")
        try:
            data = json.loads(body)
        except ValueError:
            data = {}
        _NS = next((n["id"] for n in (data.get("result") or [])
                    if n.get("title") == kv.NS_TITLE), "")
    if not _NS:
        return None
    code, body = kv.call(f"/storage/kv/namespaces/{_NS}/values/{urllib.parse.quote(key, safe='')}")
    return body if code == 200 and body.strip() else None


def stored_review(rec: dict) -> tuple[str | None, str | None]:
    """(סקירה, מקור) — מהריפו או מה-KV. אותו מפתח שבו functions/api/review שומר."""
    p = fr.REVIEWS / f"{rec['id']}.md"
    if p.exists():
        body = p.read_text(encoding="utf-8")
        if body.startswith("<!--"):
            body = body.split("-->", 1)[-1].lstrip()
        return body, "repo"
    tag = re.sub(r"\.pdf$", "", str(rec.get("p") or "").rsplit("/", 1)[-1], flags=re.I)
    md = kv_get(f"review:{rec['id']}:{tag}" if rec.get("pv") else f"review:{rec['id']}")
    return (md, "kv") if md else (None, None)


def write_review(rec: dict) -> tuple[str | None, float, str | None]:
    """סקירה חדשה מה-PDF, באותה הנחיה של עמוד הדוחות. (טקסט, עלות, שגיאה)."""
    blob = fr.fetch_pdf(rec["p"])
    if not blob:
        return None, 0.0, "הקובץ לא נמשך ממאיה"
    content = fr.request_content(rec, blob)
    if content is None:
        return None, 0.0, "הקובץ לא נקרא"
    client = anthropic.Anthropic(timeout=900, max_retries=2)
    try:
        # 32K ולא 16K: החשיבה והסקירה נספרות יחד, ודוח ארוך עלול להיקטע.
        with client.messages.stream(model=MODEL, max_tokens=32000, system=fr.SYSTEM,
                                    thinking={"type": "adaptive"},
                                    output_config={"effort": "high"},
                                    messages=[{"role": "user", "content": content}]) as s:
            msg = s.get_final_message()
    except anthropic.APIStatusError as e:
        return None, 0.0, f"API {e.status_code}: {(getattr(e, 'message', '') or str(e))[:240]}"
    except anthropic.APIError as e:
        return None, 0.0, f"{type(e).__name__}: {str(e)[:240]}"
    usd, _ = _api._usd(MODEL, msg.usage)
    _cli.log_cost(JOB, usd, model=MODEL, via="api", part="report",
                  tokens_in=msg.usage.input_tokens, tokens_out=msg.usage.output_tokens)
    if msg.stop_reason == "refusal":
        return None, usd, "סירוב"
    if msg.stop_reason == "max_tokens":
        return None, usd, "סקירת הדוח נקטעה"
    md = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not md:
        return None, usd, "סקירת הדוח חזרה ריקה"
    fr.REVIEWS.mkdir(parents=True, exist_ok=True)
    fr.save(rec, md, len(blob), model=MODEL)
    fr.write_index()
    return md, usd, None


def payload(call: dict, rec: dict, review: str) -> str:
    text = call.get("text") or ""
    cut = f" (קטוע: {TEXT_CAP:,} התווים הראשונים)" if len(text) > TEXT_CAP else ""
    return (f"חברה: {call['company']}\n"
            f"השיחה: {call.get('period')}, {call['date']} (תמליל של גלובס)\n"
            f"הדוח: {rec.get('t')}, פורסם {rec.get('d')} (מאיה {rec['id']})\n\n"
            "=== סקירת הדוח (נכתבה מתוך הדוח המלא) ===\n" + review.strip()
            + "\n\n=== סיכום שיחת הוועידה (נכתב מתוך התמליל) ===\n" + call["summary"].strip()
            + f"\n\n=== התמליל, לאימות מספרים וציטוטים{cut} ===\n" + text[:TEXT_CAP]
            + "\n\nכתוב את הסקירה המשולבת.")


# ── מצב ועלות ─────────────────────────────────────────────────────────
def state(did: str) -> dict | None:
    p = OUT / f"{did}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


def fail(call: dict, rec: dict, reason: str, tries: int, final: bool = False) -> None:
    """כישלון בתשלום נרשם, כדי שלא ישולם שוב בכל ריצה. final — לא לנסות שוב."""
    (OUT / f"{call['did']}.json").write_text(json.dumps({
        "did": call["did"], "status": "failed", "tries": MAX_TRIES if final else tries,
        "error": reason[:300], "company": call.get("company"), "period": call.get("period"),
        "report_id": rec.get("id"), "at": datetime.now().isoformat(timespec="minutes"),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=4, help="כמה סקירות בריצה")
    ap.add_argument("--force", action="store_true", help="גם מחוץ לחלון הערב (לא מעל התקרה)")
    ap.add_argument("--list", action="store_true", help="להציג את ההצמדות בלי לכתוב דבר")
    args = ap.parse_args()

    # רק דוחות חדשים. שיחה יכולה להקדים את הדוח ב-AFTER ימים, ולכן הסינון
    # הראשון של השיחות רחב ממנו בהתאם; הדוח עצמו נבדק אחרי ההצמדה.
    floor = (date.today() - timedelta(days=NEW_DAYS)).isoformat()
    early = (date.today() - timedelta(days=NEW_DAYS + AFTER)).isoformat()
    calls = sorted((c for c in load_calls() if c["date"] >= early),
                   key=lambda c: (c["date"], c["did"]), reverse=True)
    by_company = index_filings()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = []
    for c in calls:
        r = find_report(c, by_company)
        if r is None or (r.get("d") or "") >= floor:   # שיחה על דוח ישן אינה נכתבת
            rows.append((c, r, state(c["did"])))
    done = sum(1 for _, _, st in rows if st and st.get("status") != "failed")
    todo = [(c, r, st) for c, r, st in rows
            if r and not (st and st.get("status") != "failed")
            and int((st or {}).get("tries") or 0) < MAX_TRIES]
    with_report = sum(1 for _, r, _ in rows if r)
    print(f"::notice::דוח ושיחה: {with_report} שיחות על דוחות מ-{floor} ואילך, "
          f"{len(rows) - with_report} בלי דוח · {done} נכתבו · {len(todo)} ממתינות")

    if args.list:
        for c, r, st in rows:
            mark = "✓" if st and st.get("status") != "failed" else ("✗" if st else " ")
            src = stored_review(r)[1] if r else None
            print(f" [{mark}] {c['date']} {c['company'][:22]:<22} {c.get('period') or '':<9} "
                  + (f"דוח {r['d']} {r['id']} · סקירה: {src or 'תיכתב'}" if r else "אין דוח בחלון"))
        return 0
    if not todo:
        return 0
    now = datetime.now()
    if not (args.force or any(a <= (now.hour, now.minute) <= b for a, b in WINDOWS)):
        spans = " וב-".join(f"{a[0]}:{a[1]:02d}–{b[0]}:{b[1]:02d}" for a, b in WINDOWS)
        print(f"::notice::דוח ושיחה נכתבים ב-{spans} — עכשיו {now:%H:%M}")
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("::error::ANTHROPIC_API_KEY חסר — אי אפשר לכתוב את סקירות דוח ושיחה")
        return 1

    cap = float(os.environ.get("CALL_REVIEWS_MAX_USD") or 8)
    spent = spent_today()
    run_usd, wrote, failed, new_reviews = 0.0, 0, 0, 0
    for c, rec, st in todo:
        if wrote + failed >= args.limit:
            break
        if spent + run_usd >= cap:
            print(f"::notice::התקרה היומית לדוח ושיחה (${cap:.0f}) הושגה — "
                  "השאר ימתינו לערב הבא")
            break
        tries = int((st or {}).get("tries") or 0)
        print(f"  {c['date']} {c['company']} ({c.get('period')}) ← דוח {rec['d']} {rec['id']}",
              flush=True)
        item_usd = 0.0

        review, src = stored_review(rec)
        if not review:
            review, usd, err = write_review(rec)
            run_usd += usd
            item_usd += usd
            if err:
                failed += 1
                if re.search(_cli.CREDIT_RE, err, re.I):
                    print("::error title=יתרת Anthropic אזלה::טעינה: console.anthropic.com/settings/billing")
                    break
                # כישלון שלא עלה דבר (הקובץ לא נמשך) לא נרשם — הריצה הבאה תנסה שוב
                if usd:
                    fail(c, rec, f"סקירת הדוח: {err}", tries + 1)
                print(f"::warning::סקירת הדוח של {c['company']} לא נכתבה: {err[:160]}")
                continue
            src = "new"
            new_reviews += 1
        # סקירה של מסמך שאינו הדוח (הערכת שווי, דוח של חברה בת) נכתבת בלי טבלת
        # המספרים — ראה כלל 6 ב-filing_review.SYSTEM. אין על מה לבנות.
        if "## המספרים" not in review:
            fail(c, rec, "סקירת הדוח אינה של דוח כספי — המסמך שצורף אינו הדוח", tries, final=True)
            failed += 1
            continue

        res, err, usd = _api.ask_json(SYSTEM, payload(c, rec, review), SCHEMA, job=JOB,
                                      model=MODEL, max_tokens=32000, effort="high", max_usd=2.0)
        run_usd += usd
        item_usd += usd
        if err:
            failed += 1
            if re.search(_cli.CREDIT_RE, err, re.I):
                print("::error title=יתרת Anthropic אזלה::טעינה: console.anthropic.com/settings/billing")
                break
            fail(c, rec, err, tries + 1)
            print(f"::warning::דוח ושיחה של {c['company']} נכשל: {err[:160]}")
            continue
        if not res.get("same_company", True):
            fail(c, rec, "הדוח והשיחה אינם מתיישבים: " + (res.get("mismatch_reason") or ""),
                 tries, final=True)
            failed += 1
            print(f"::warning::{c['company']}: הדוח שנמצא אינו של השיחה — לא נכתבה סקירה")
            continue
        md = (res.get("review_md") or "").strip()
        if not md:
            fail(c, rec, "הסקירה חזרה ריקה", tries + 1)
            failed += 1
            continue

        (OUT / f"{c['did']}.json").write_text(json.dumps({
            "did": c["did"], "status": "ok",
            "company": c["company"], "period": c.get("period"), "match": c.get("match"),
            "globes_name": c.get("globes_name"), "call_date": c["date"], "call_url": c.get("url"),
            "report": {k: rec.get(k) for k in ("id", "d", "t", "p")},
            "review_src": src, "report_review": review,
            "headline": (res.get("headline") or "").strip(), "review_md": md,
            "model": MODEL, "usd": round(item_usd, 4),
            "generated": datetime.now().isoformat(timespec="minutes"),
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        wrote += 1

    print(f"::notice::דוח ושיחה: {wrote} נכתבו ({new_reviews} עם סקירת דוח חדשה), "
          f"{failed} נכשלו · ${run_usd:.2f} בריצה, ${spent + run_usd:.2f} היום מתוך ${cap:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
