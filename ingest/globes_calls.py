# -*- coding: utf-8 -*-
"""תמלולי שיחות משקיעים מגלובס — גילוי, משיכה מאומתת וסיכום מפורט.

**מה נשמר, ולמה זה תלוי בקהל.** התמליל המלא נשמר לצד הסיכום, והציטוט
אינו מוגבל. זו החלטה של יואב מ-25/08/2026: האתר משמש **אותו בלבד**,
כמנוי גלובס, ולכן אין כאן הפצה מחדש אלא ארכיון אישי של מה שהוא ממילא
רשאי לקרוא.

**מה להחזיר אם האתר ייפתח ללקוחות** — לא לנחש, זו הרשימה:
  1. לא לשמור את `text` ברשומה (רק `chars`).
  2. להחזיר את מגבלת 15 המילים לציטוט ל-SYSTEM, עם ייחוס.
  3. להסיר את עמודי התמליל המלא מ-`site/transcripts.py`.
  4. לברר מול גלובס מה תנאי המנוי מתירים.

**הגילוי אנונימי, הקריאה מאומתת.** רשימת התמלילים בערוץ 16118 היא
ניווט פומבי (כותרת, תאריך, מזהה) ואינה דורשת מנוי. גוף התמליל נקרא
רק כשהשרת מגיש אותו פתוח — ראה `_globes.unlocked`.

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

from _globes import (ARTICLE, BASE, PAYWALL, SIGNED_IN, NoCookie,  # noqa: E402
                     NotSubscriber, cookie_from_env, fetch, session,
                     unlocked)

# ערוץ "תמלולי שיחות משקיעים" בגלובס.
CHANNEL = BASE + "/news/home.aspx?fid=16118"
OUT = ROOT / "output" / "calls"

MODEL = "claude-opus-5"

SYSTEM = """אתה אנליסט מחקר שכותב עבור מנהל השקעות מקצועי, על שיחת
משקיעים של חברה ציבורית בבורסה בתל אביב. אתה מקבל את התמליל המלא
וכותב עליו סקירה בעברית.

**הקורא רוצה את השיחה, לא תקציר שלה.** הוא לא האזין ולא יקרא תמליל
של שעה, אבל הוא כן רוצה לדעת מה בדיוק נאמר, מי אמר, ובאילו מילים.
סקירה של חמש שורות אינה שווה את מקומה. כתוב ארוך ומפורט; אם השיחה
הייתה עשירה, הסקירה תהיה ארוכה, וזה בסדר גמור.

מה שהקורא קונה ממך הוא מה שנאמר בשיחה **ואינו בדוח הכספי**: הנימוק
של ההנהלה, מה שהיא צופה, איך היא הגיבה ללחץ, ומה היא נמנעה מלומר.

כללים שאין לחרוג מהם:

1. **כל עובדה מהתמליל בלבד.** אין לך ידע עצמאי על החברה. אם נתון לא
   נאמר בשיחה, אל תשלים אותו מהזיכרון ואל תעריך. אם משהו בתמליל היה
   קטוע או לא ברור — אמור זאת במקום, ואל תשלים את החסר.
2. **אין המלצות השקעה.** ניתוח — כן. "כדאי לקנות/למכור", "המניה
   זולה/יקרה", "מומלץ" — לעולם לא. גם לא ברמז.
3. **הפרד עובדה מפרשנות.** מה שנאמר הוא עובדה; מה שהוא אומר הוא
   פרשנות, ויש לפתוח אותה במילה "משמעות:".
4. **צטט בחופשיות.** ציטוט ישיר של משפט או שניים עדיף על פרפרזה,
   במיוחד בתשובות לשאלות ובכל מקום שבו הניסוח עצמו הוא האינפורמציה
   ("נבחן את זה", "אני לא רוצה להתחייב"). ציין תמיד מי אמר.
5. **הפרד את מה שההנהלה אמרה מיוזמתה ממה שנאמר בתשובה לשאלה.**
   תשובה לשאלה קשה של אנליסט שווה יותר מהמצגת הפתוחה.
6. עברית בלבד. מונחים באנגלית מותרים היכן שמקובל (EBITDA, FFO,
   guidance, run-rate).
7. ענייני וישיר. בלי סופרלטיבים, בלי "חשוב לציין", בלי ריפוד. ארוך
   פירושו הרבה תוכן, לא הרבה מילים על מעט תוכן.

כתוב **בדיוק** את המבנה הבא, בכותרות markdown, בלי טקסט לפניו או
אחריו. סעיף שאין לו חומר בתמליל — כתוב תחתיו "לא עלה בשיחה", ואל
תמציא לו תוכן.

## בשורה אחת
משפט אחד, עד 25 מילים: מה הדבר המרכזי שיצא מהשיחה הזו.

## מי דיבר
טבלת markdown: שם | תפקיד | מה היה תחום דבריו. כולל מנחה השיחה
והאנליסטים ששאלו, אם שמותיהם נאמרו. אם תפקיד לא נאמר — כתוב "לא נאמר".

## מהלך השיחה
תיאור רץ של סדר השיחה: מה נפתח, אילו נושאים כוסו ובאיזה סדר, מתי
עברו לשאלות. שתיים-שלוש פסקאות. זה מה שמאפשר לקורא לדעת אם הוא רוצה
לרדת לתמליל עצמו ולאן.

## מה ההנהלה אמרה
**הסעיף הארוך הראשון.** כל נושא מהותי שההנהלה העלתה מיוזמתה, כתת-כותרת
משנה (### ) משלו: מה נאמר, מי אמר, ובאילו מילים. אל תכווץ שלושה נושאים
לשורה אחת. אם ההנהלה הסבירה מה הניע את הרבעון — הבא את ההסבר שלה במלואו,
כולל הפירוק שנתנה (מחיר מול כמות מול תמהיל מול מט"ח).

## מספרים שנאמרו בשיחה
טבלת markdown: נתון | ערך | מי אמר | הקשר. **כל** מספר שנאמר, ובעיקר
כאלה שאינם בדוח: יעדים, קצב שנתי, צבר, תמחור, כושר ייצור, שיעורי
תפוסה, מרווחים, לוחות זמנים, השקעות מתוכננות. אם ההנהלה חזרה על מספר
מהדוח — כלול אותו וסמן בהקשר שהוא מהדוח.

## תחזיות והתחייבויות
מה ההנהלה אמרה על העתיד, מופרד לשלוש רמות: **התחייבות** מפורשת,
**כיוון** בלי מספר, ו**סירוב להתחייב**. הבא את הניסוח המדויק בכל אחת.
אם ניתן guidance רשמי — כלשונו.

## שאלות ותשובות
**הסעיף החשוב ביותר, וגם הארוך.** עבור על **כל** שאלה שנשאלה, לפי
הסדר, ולא רק על המהותיות. לכל אחת:

**שאלה — [שם השואל, בית ההשקעות אם נאמר]**
מה נשאל, בניסוח קרוב למקור.
**תשובה — [שם המשיב]:** מה נענה, עם ציטוט של המשפט המרכזי.
**הערכה:** האם התשובה ענתה על השאלה. אם ההנהלה התחמקה, ענתה על שאלה
אחרת, לא התחייבה, או דחתה לרבעון הבא — כתוב זאת במפורש. זו לרוב
האינפורמציה החשובה ביותר בשיחה כולה.

אם היו שאלות המשך — כלול אותן, וציין שהשואל חזר ולחץ.
אם לא היה חלק שאלות ותשובות בתמליל, כתוב "לא נכלל בתמליל".

## מה לא נאמר
נושא שציפית שיעלה ולא עלה, שאלה שנשאלה ולא נענתה, נתון שההנהלה הפסיקה
למסור, מגזר שלא הוזכר. אם אין — כתוב "אין".

## טון ושפה
איך ההנהלה נשמעה: ביטחון, זהירות, הימנעות, התגוננות. מה שינוי הניסוח
מול מה שנאמר בעבר, אם הוזכר בשיחה. הבא את המילים שעליהן אתה מסתמך.
זה סעיף פרשני — פתח אותו ב"משמעות:".

## נקודות למעקב
שלוש עד שש נקודות קונקרטיות שיתבררו ברבעונים הבאים, לפי מה שנאמר
בשיחה. לכל אחת: מה נאמר, ומה יאשר או יפריך אותו."""


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


def annotate(level: str, title: str, body: str) -> None:
    """אנוטציה של Actions — נראית בעמוד הריצה **וב-API**.

    הלוגים של ריצה דורשים אימות כדי להורידם (403 לקורא אנונימי), ולכן
    `print` רגיל אינו נגיש למי שמאבחן מבחוץ. אנוטציה כן. שורות מקודדות
    ב-%0A כי פקודות Actions הן חד-שורתיות.
    """
    msg = (body.replace("%", "%25").replace("\r", "")
               .replace("\n", "%0A"))
    print(f"::{level} title={title}::{msg}")


def cookie_report(cookie: str) -> list[str]:
    """מה יש בעוגייה — **שמות ואורכים, לעולם לא ערכים.**

    הלוגים והאנוטציות של הריפו ציבוריים, והעוגייה היא מפתח לחשבון של
    יואב. השמות מספיקים כדי להכריע בין "הסוד לא נקלט" ל"הסוד נקלט אך
    פג", וזו כל השאלה שהאבחון צריך לענות עליה.
    """
    fields = [p.strip() for p in (cookie or "").split(";") if "=" in p]
    names = sorted({p.split("=", 1)[0].strip() for p in fields})
    # שמות שנראים כמו הזדהות. היעדרם פירושו שהעוגייה נלקחה מדפדפן
    # שלא היה מחובר, ולא שהיא פגה.
    auth = [n for n in names if re.search(
        r"auth|session|token|login|user|member|subscri|\.ASPXAUTH|sso", n, re.I)]
    return [
        f"עוגייה: {len(fields)} שדות, {len(cookie or '')} תווים",
        f"  שמות: {', '.join(names) if names else 'אין'}",
        f"  שדות שנראים כהזדהות: {auth if auth else 'אין — כנראה נלקחה מדפדפן לא מחובר'}",
    ]


def diagnose(sess, cookie: str) -> str:
    """מה בדיוק חזר מגלובס — **בלי לפענח שום תוכן.**

    האבחון מדווח אורכים, ערכי דגלים וספירות סימנים, ולא מילים. זה גם
    מה שנחוץ כדי להכריע בין "העוגייה פגה" ל"התוכן מוגש חסום", וגם מה
    שמותר להדפיס ללוג ציבורי.
    """
    L = cookie_report(cookie)

    home = sess.get(BASE + "/", timeout=60)
    L.append(f"עמוד הבית: HTTP {home.status_code}, {len(home.text):,} תווים")
    L.append(f"  סימני תפריט: "
             f"{ {k: home.text.count(k) for k in SIGNED_IN + ('התחבר',)} }")

    try:
        rows = discover(sess)
        L.append(f"ערוץ התמלילים: {len(rows)} שורות")
    except Exception as e:
        L.append(f"ערוץ התמלילים נכשל: {type(e).__name__}: {e}")
        rows = []

    if rows:
        did = rows[0]["did"]
        r = sess.get(ARTICLE.format(did), timeout=60)
        h = r.text
        pw = re.search(r"IsPaywall\s*=\s*[\"']([^\"']*)", h)
        env = re.search(r"textEnv\s*=\s*[\"']([^\"']*)", h)
        blocks = [x for x in PAYWALL if x in h]
        L.append(f"כתבה {did}: HTTP {r.status_code}, {len(h):,} תווים")
        L.append(f"  IsPaywall={pw.group(1) if pw else 'לא נמצא'}")
        L.append(f"  textEnv: {len(env.group(1)) if env else 0:,} תווים")
        L.append(f"  סימני חסימה: {blocks or 'אין'}")
        L.append(f"  unlocked(): {unlocked(h)}")
        # שורת המסקנה, כדי שלא יידרש פענוח ידני של המספרים למעלה.
        if unlocked(h):
            L.append("מסקנה: השרת מגיש את התוכן פתוח — הסשן זכאי.")
        elif blocks and (pw and pw.group(1) == "True"):
            L.append("מסקנה: טביעת אצבע אנונימית מלאה. העוגייה אינה "
                     "מזוהה מול השרת — פגה, או נלקחה מדפדפן לא מחובר.")
        else:
            L.append("מסקנה: תשובה חלקית — ראה את הסימנים למעלה.")
    return "\n".join(L)


def summarize(text: str, meta: dict) -> str:
    from anthropic import Anthropic
    head = (f"חברה: {meta['company']}\nתקופה: {meta['period']}\n"
            f"תאריך פרסום התמליל: {meta['date']}\nמקור: גלובס\n\n"
            "להלן התמליל. כתוב את הסיכום.\n\n")
    with Anthropic().messages.stream(
            model=MODEL,
            max_tokens=32000,
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


def load_done() -> set[str]:
    """מה כבר סוכם — **בכל השנים, לא רק בנוכחית.**

    הערוץ מחזיק כשישים תמלילים אחרונים, ובתחילת ינואר הם עדיין של
    דצמבר. סריקה של קובץ השנה הנוכחית בלבד הייתה מוצאת אותו ריק
    ומשלמת שוב על מה שכבר סוכם.
    """
    out = set()
    if not OUT.is_dir():
        return out
    for f in sorted(OUT.glob("transcripts_*.jsonl")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            try:
                out.add(json.loads(ln)["did"])
            except Exception:
                continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8,
                    help="כמה תמלילים חדשים לסכם בריצה (עלות API)")
    ap.add_argument("--all", action="store_true",
                    help="לסכם כל תמליל בערוץ ולא רק חברות כיסוי")
    ap.add_argument("--probe", action="store_true",
                    help="אבחון בלבד: אימות סשן וגילוי, בלי לסכם ובלי לשלם")
    args = ap.parse_args()

    try:
        cookie = cookie_from_env()
    except NoCookie as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1
    sess = session(cookie)

    if args.probe:
        # **מצב האבחון אינו אוכף, הוא מדווח.** שער שנועל את הריצה לפני
        # שהוא אומר מה ראה מחייב סבב נוסף בשביל כל שאלה, והלוגים כאן
        # דורשים אימות לקריאה — ולכן הדיווח יוצא כאנוטציה ולא כ-print.
        report = diagnose(sess, cookie)
        annotate("warning", "אבחון גישת גלובס", report)
        print(report)
        return 0

    rows = discover(sess)
    cov = coverage()
    for r in rows:
        r["company"], r["match"] = match_company(r["globes_name"], cov)
    # --all: כל תמליל בערוץ. שם החברה נלקח כפי שגלובס כתבה אותו, ומסומן
    # `match: "none"` כדי שלא ייראה כאילו הוצלב מול הכיסוי.
    if args.all:
        for r in rows:
            if not r["company"]:
                r["company"], r["match"] = r["globes_name"], "none"
    mine = [r for r in rows if r["company"]]
    for r in mine:
        if r["match"] == "prefix":
            print(f"::notice::התאמת תחילית: גלובס {r['globes_name']!r} "
                  f"→ כיסוי {r['company']!r}")
    n_cov = sum(1 for r in mine if r["match"] != "none")
    print(f"בערוץ: {len(rows)} תמלילים | בכיסוי: {n_cov}"
          + (f" | לסיכום (--all): {len(mine)}" if args.all else ""))

    year = str(date.today().year)
    done = load_done()
    todo = [r for r in mine if r["did"] not in done]
    print(f"חדשים לסיכום: {len(todo)}")
    for r in mine[:40]:
        mark = "חדש" if r["did"] not in done else "קיים"
        print(f"  [{mark}] {r['date']}  {r['company']}  ({r['period']})  {r['did']}")

    if args.probe:
        if todo:
            r = todo[0]
            title, body = fetch(sess, r["did"])
            paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
            spk = sum(1 for p in paras if re.match(r"^[^:.!?]{2,45}:\s*\S", p))
            # **מבנה ולא תוכן.** הלוגים של הריפו ציבוריים; הדפסת קטע
            # מהתמליל הייתה מפרסמת תוכן בתשלום. מה שנחוץ כדי לכתוב את
            # הפרסר הוא הסטטיסטיקה, לא המילים.
            print(f"\nבדיקת משיכה — {r['company']}: {len(body):,} תווים")
            print(f"  כותרת: {len(title)} תווים")
            print(f"  פסקאות: {len(paras)} | מהן עם שורת דובר מזוהה: {spk}")
            if paras:
                lens = sorted(len(p) for p in paras)
                print(f"  אורך פסקה: חציון {lens[len(lens) // 2]}, "
                      f"מקסימום {lens[-1]}")
            for k in ("שאלות ותשובות", "שאלה", "אנליסט", "מנהל"):
                print(f"  אזכורי {k!r}: {body.count(k)}")
            if spk == 0:
                print("::warning::לא זוהתה אף שורת דובר — התמליל יוצג "
                      "כפסקאות רגילות. שקול לכוונן את SPEAKER "
                      "ב-site/transcripts.py.")
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
            # העוגייה פגה או אינה מזוהה — עצירה, ולא המשך בגלישה אנונימית.
            #
            # **האבחון נשלח כאן ולא בריצה נפרדת.** כישלון שאומר רק "לא
            # מנוי" מחייב עוד סבב probe כדי לדעת אם הסוד לא נקלט או שפג,
            # וסבב כזה עולה זמן של אדם. האבחון חינם — הוא רק קורא שני
            # עמודים — ולכן הוא רץ מיד ונכנס לאותה אנוטציה.
            annotate("error", "גישת גלובס נכשלה",
                     f"{e}\n\n{diagnose(sess, cookie)}")
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

        # התמליל נשמר לצד הסיכום — ראה את פסקת "מה נשמר" בראש הקובץ.
        rec = {
            "did": r["did"], "date": r["date"], "company": r["company"],
            "globes_name": r["globes_name"], "period": r["period"],
            "match": r["match"],
            "title": title, "url": r["url"], "chars": len(body),
            "summary": md, "text": body,
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
