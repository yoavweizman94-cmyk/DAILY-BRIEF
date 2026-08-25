# -*- coding: utf-8 -*-
"""תמלולי שיחות משקיעים מגלובס — גילוי, משיכה מאומתת וסיכום.

**מה נשמר ומה לא.** התמליל המלא הוא תוכן של גלובס שיואב משלם עליו
כמנוי יחיד. הוא נמשך, מסוכם, **ונזרק**. מה שנשמר הוא הסיכום שלנו,
מטא-דאטה, וקישור חזרה לגלובס — כדי שהקורא ילך למקור. ציטוט מוגבל
ל-15 מילים עם ייחוס, כמו כל מקור אחר בברייף.

**הגילוי אנונימי, הקריאה מאומתת.** רשימת התמלילים בערוץ 16118 היא
ניווט פומבי (כותרת, תאריך, מזהה) ואינה דורשת מנוי. גוף התמליל נקרא
רק בסשן מחובר — ראה `_globes.is_subscriber`.

הרצה: ידנית בלבד (workflow_dispatch), כמו שאר הצנרת מאז שעברה
להרצה לפי דרישה.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

from _tls import harden  # noqa: E402

harden()

import yaml  # noqa: E402

from _globes import (ARTICLE, BASE, NoCookie, NotSubscriber,  # noqa: E402
                     cookie_from_env, fetch, is_subscriber, session)

# ערוץ "תמלולי שיחות משקיעים" בגלובס.
CHANNEL = BASE + "/news/home.aspx?fid=16118"
OUT = ROOT / "output" / "calls"

MODEL = "claude-opus-5"

SYSTEM = """אתה אנליסט מחקר שכותב עבור מנהל השקעות מקצועי. אתה מקבל תמליל
של שיחת משקיעים של חברה ציבורית בבורסה בתל אביב, וכותב עליו סיכום בעברית.

הקורא לא האזין לשיחה ולא יקרא תמליל של שעה. מה שהוא קונה ממך הוא מה
שנאמר בשיחה **ואינו בדוח הכספי**: הנימוק של ההנהלה, מה שהיא צופה, ומה
שהיא נמנעה מלומר כשנשאלה.

כללים שאין לחרוג מהם:

1. **כל עובדה מהתמליל בלבד.** אין לך ידע עצמאי על החברה. אם נתון לא
   נאמר בשיחה, אל תשלים אותו מהזיכרון ואל תעריך.
2. **אין המלצות השקעה.** ניתוח — כן. "כדאי לקנות/למכור", "המניה
   זולה/יקרה", "מומלץ" — לעולם לא. גם לא ברמז.
3. **הפרד עובדה מפרשנות.** מה שנאמר הוא עובדה; מה שהוא אומר הוא
   פרשנות, ויש לפתוח אותה במילה "משמעות:".
4. **ציטוט עד 15 מילים**, במירכאות, עם ציון מי אמר. לא יותר. אל תשכתב
   את התמליל — סכם אותו.
5. **הפרד את מה שההנהלה אמרה מיוזמתה ממה שנאמר בתשובה לשאלה.** תשובה
   לשאלה קשה של אנליסט שווה יותר מהמצגת הפתוחה.
6. עברית בלבד. מונחים באנגלית מותרים היכן שמקובל (EBITDA, FFO, guidance).
7. ענייני וישיר. בלי סופרלטיבים, בלי "חשוב לציין", בלי ריפוד.

כתוב **בדיוק** את המבנה הבא, בכותרות markdown, בלי טקסט לפניו או אחריו:

## בשורה אחת
משפט אחד, עד 25 מילים: מה הדבר המרכזי שיצא מהשיחה הזו.

## מה ההנהלה אמרה
העיקר מדברי ההנהלה: מה הניע את הרבעון לשיטתה, מה השתנה בעסק, מה
הודגש. שלוש עד שש נקודות, כל אחת עם מי אמר אותה כשזה ידוע.

## מספרים ותחזיות שנאמרו בשיחה
רק מספרים שנאמרו בשיחה בפועל, ובעיקר כאלה שאינם בדוח: יעדים, קצב
שנתי, צבר, תמחור, כושר ייצור, לוחות זמנים. אם ההנהלה נתנה guidance —
הבא אותו כלשונו. אם לא נמסרו מספרים חדשים, כתוב "לא נמסרו".

## שאלות ותשובות
**הסעיף החשוב ביותר.** לכל שאלה מהותית: מי שאל (שם ובית ההשקעות אם
נאמרו), מה נשאל בקצרה, ומה נענה. אם ההנהלה התחמקה, לא התחייבה, או
דחתה לרבעון הבא — כתוב זאת במפורש, זו אינפורמציה. אם לא היה חלק
שאלות ותשובות בתמליל, כתוב "לא נכלל בתמליל".

## מה לא נאמר
נושא שציפית שיעלה ולא עלה, שאלה שנשאלה ולא נענתה, נתון שההנהלה
הפסיקה למסור. אם אין — כתוב "אין".

## נקודות למעקב
שתיים עד ארבע נקודות קונקרטיות שיתבררו ברבעונים הבאים, לפי מה
שנאמר בשיחה."""


def norm_name(s: str) -> str:
    """נרמול שם חברה להשוואה — זהה ל-maya_index, ומאותה סיבה.

    גלובס כותבת "אלקטרה נדלן" ומאיה כותבת את אותו שם עם גרשיים.
    """
    s = re.sub(r"[\"'״׳`]", "", s or "")
    return re.sub(r"\s+", " ", s.replace("-", " ")).strip().lower()


def coverage() -> dict[str, str]:
    """כל צורות השם המנורמלות → שם החברה הקנוני ב-companies.yaml."""
    cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for c in cfg.get("companies") or []:
        canon = c["name_he"]
        for k in ("name_he", "name_en"):
            if c.get(k):
                out.setdefault(norm_name(str(c[k])), canon)
        for a in c.get("aliases") or []:
            if a:
                out.setdefault(norm_name(str(a)), canon)
    out.pop("", None)
    return out


def match_company(name: str, cov: dict[str, str]) -> tuple[str | None, str]:
    """שם החברה הקנוני, ואיך הוא נמצא ("exact" / "prefix").

    **התאמה מדויקת לבדה מחמיצה בשקט.** גלובס כותבת "עשות אשקלון",
    "עזריאלי" ו"בוליגו קפיטל" במקום השמות המלאים שב-companies.yaml,
    ושלוש חברות כיסוי נשרו בלי שאיש ידע. לכן נוספה נפילה לתחילית.

    התחילית בטוחה כאן ולא במקום אחר: השדה הזה הוא **שם החברה בלבד**,
    ולא טקסט חופשי, ולכן חשש ה-`generic_name` (רימון בכתבה קולינרית)
    אינו רלוונטי. הסייג נשמר בכל זאת: התאמה רק על גבול מילה ומאורך 3.
    """
    n = norm_name(name)
    if n in cov:
        return cov[n], "exact"
    if len(n) >= 3:
        for k, canon in cov.items():
            if len(k) < 3:
                continue
            if n.startswith(k + " ") or k.startswith(n + " "):
                return canon, "prefix"
    return None, ""


# "אינרום שיחת משקיעים - רבעון 2"  →  ("אינרום", "רבעון 2")
TITLE = re.compile(r"^(.*?)\s*שיחת\s+משקיעים\s*[-–]\s*(.+?)\s*$")


def parse_title(t: str) -> tuple[str, str] | None:
    m = TITLE.match((t or "").strip())
    if not m or not m.group(1).strip():
        return None
    return m.group(1).strip(), m.group(2).strip()


def discover(sess) -> list[dict]:
    """רשימת התמלילים בערוץ: מזהה, תאריך, ושם החברה כפי שגלובס כתבה.

    **הפרסור נכשל ברעש ולא בשקט.** ערוץ שמחזיר עמוד תקין אך שינה מבנה
    היה מחזיר רשימה ריקה, וריצה ריקה נראית בדיוק כמו "אין תמלילים היום".
    """
    r = sess.get(CHANNEL, timeout=60)
    r.raise_for_status()
    html = r.text

    rows, seen = [], set()
    for m in re.finditer(
            r'href="(/news/article\.aspx\?did=(\d+))"[^>]*>(.*?)</a>', html, re.S):
        did, raw = m.group(2), m.group(3)
        if did in seen:
            continue
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
        dm = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})\s*(.+)$", txt)
        if not dm:
            continue
        parsed = parse_title(dm.group(4))
        if not parsed:
            continue
        seen.add(did)
        rows.append({
            "did": did,
            "date": f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}",
            "globes_name": parsed[0],
            "period": parsed[1],
            "url": ARTICLE.format(did),
        })
    if not rows:
        raise RuntimeError(
            f"ערוץ התמלילים לא הניב אף שורה ({len(html):,} תווים) — "
            "כנראה שמבנה העמוד השתנה")
    return rows


def summarize(text: str, meta: dict) -> str:
    from anthropic import Anthropic
    head = (f"חברה: {meta['company']}\nתקופה: {meta['period']}\n"
            f"תאריך פרסום התמליל: {meta['date']}\nמקור: גלובס\n\n"
            "להלן התמליל. כתוב את הסיכום.\n\n")
    with Anthropic().messages.stream(
            model=MODEL,
            max_tokens=12000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=[{"role": "user", "content": head + text}]) as st:
        msg = st.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("המודל סירב לסכם את התמליל")
    md = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not md:
        raise RuntimeError("התקבל סיכום ריק")
    return md


def load_done(year: str) -> set[str]:
    f = OUT / f"transcripts_{year}.jsonl"
    if not f.exists():
        return set()
    out = set()
    for ln in f.read_text(encoding="utf-8").splitlines():
        try:
            out.add(json.loads(ln)["did"])
        except Exception:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6,
                    help="כמה תמלילים חדשים לסכם בריצה (עלות API)")
    ap.add_argument("--probe", action="store_true",
                    help="אבחון בלבד: אימות סשן וגילוי, בלי לסכם ובלי לשלם")
    args = ap.parse_args()

    try:
        cookie = cookie_from_env()
    except NoCookie as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1
    sess = session(cookie)

    # שער המנוי נבדק פעם אחת מול עמוד הבית, לפני כל משיכה של תוכן.
    home = sess.get(BASE + "/", timeout=60)
    if not is_subscriber(home.text):
        print("::error::הסשן אינו מחובר לגלובס — רענן את GLOBES_COOKIE "
              "(Copy as cURL מתוך דפדפן מחובר).", file=sys.stderr)
        return 1
    print("סשן מנוי: מאומת")

    rows = discover(sess)
    cov = coverage()
    for r in rows:
        r["company"], r["match"] = match_company(r["globes_name"], cov)
    mine = [r for r in rows if r["company"]]
    for r in mine:
        if r["match"] == "prefix":
            print(f"::notice::התאמת תחילית: גלובס {r['globes_name']!r} "
                  f"→ כיסוי {r['company']!r}")
    print(f"בערוץ: {len(rows)} תמלילים | מהם בכיסוי: {len(mine)}")

    year = str(date.today().year)
    done = load_done(year)
    todo = [r for r in mine if r["did"] not in done]
    print(f"חדשים לסיכום: {len(todo)}")
    for r in mine[:20]:
        mark = "חדש" if r["did"] not in done else "קיים"
        print(f"  [{mark}] {r['date']}  {r['company']}  ({r['period']})  {r['did']}")

    if args.probe:
        if todo:
            r = todo[0]
            title, body = fetch(sess, r["did"])
            print(f"\nבדיקת משיכה — {r['company']}: {len(body):,} תווים")
            print("  כותרת:", title[:80])
            print("  פתיחה:", body[:200].replace("\n", " "))
            for k in ("שאלות ותשובות", "שאלה", "אנליסט", "מנהל"):
                print(f"  אזכורי {k!r}: {body.count(k)}")
        else:
            print("אין תמליל חדש לבדיקה")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"transcripts_{year}.jsonl"
    ok = fail = 0
    for r in todo[:args.limit]:
        try:
            title, body = fetch(sess, r["did"])
        except NotSubscriber as e:
            # העוגייה פגה באמצע הריצה — עצירה, ולא המשך בגלישה אנונימית.
            print(f"::error::{e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"::warning::{r['company']} ({r['did']}): {type(e).__name__}: {e}")
            fail += 1
            continue
        try:
            md = summarize(body, r)
        except Exception as e:
            print(f"::warning::סיכום נכשל ל{r['company']} ({r['did']}): {e}")
            fail += 1
            continue

        # התמליל עצמו אינו נשמר — רק הסיכום, ואורך המקור לצורך שקיפות.
        rec = {
            "did": r["did"], "date": r["date"], "company": r["company"],
            "globes_name": r["globes_name"], "period": r["period"],
            "match": r["match"],
            "title": title, "url": r["url"], "chars": len(body),
            "summary": md,
            "generated": datetime.now().isoformat(timespec="seconds"),
        }
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ok += 1
        print(f"נשמר: {r['company']} {r['period']} "
              f"({len(body):,} תווים → {len(md):,} סיכום)")

    left = max(0, len(todo) - args.limit)
    if left:
        print(f"::notice::נותרו {left} תמלילים בכיסוי שלא סוכמו במגבלת --limit")
    print(f"סיכום ריצה: {ok} הצליחו, {fail} נכשלו")
    return 1 if (ok == 0 and todo) else 0


if __name__ == "__main__":
    sys.exit(main())
