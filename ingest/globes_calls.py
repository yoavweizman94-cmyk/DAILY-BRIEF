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
רק אחרי שהשרת אישר שהסשן מזוהה — ראה `_globes.recognized`.

הרצה: ידנית בלבד (workflow_dispatch), כמו שאר הצנרת מאז שעברה
להרצה לפי דרישה.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

from _tls import harden  # noqa: E402

harden()

import yaml  # noqa: E402

from _globes import (ARTICLE, BASE, Garbled, NoCookie,  # noqa: E402
                     NotSubscriber, cookie_from_env, fetch, hebrew_ratio,
                     recognized, session, ua_from_env)

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
    אינו מזוהה", וזו כל השאלה שהאבחון צריך לענות עליה.
    """
    fields = [p.strip() for p in (cookie or "").split(";") if "=" in p]
    names = sorted({p.split("=", 1)[0].strip() for p in fields})

    # **חתימה שמבדילה בין "הסוד לא עודכן" ל"עודכן ועדיין לא עובד".**
    # שתי ריצות רצופות נכשלו על אותה עוגייה בדיוק, ובלי חתימה אי אפשר
    # היה לדעת זאת אלא בהשוואה ידנית של רשימת שמות בת 62 איברים.
    #
    # נחתם התוכן המלא ולא רק שמות ואורכים: עוגיית סשן מתחדשת שומרת
    # לרוב על אורכה, וחתימה על המבנה בלבד לא הייתה זזה בדיוק במקרה
    # שבשבילו היא נועדה. שמונה תווים מ-SHA-256 של מחרוזת בת 4KB הם
    # מזהה שינוי, ואינם ניתנים להיפוך לסוד.
    sig = hashlib.sha256((cookie or "").encode()).hexdigest()[:8]
    auth = [n for n in names if re.search(
        r"auth|session|token|login|member|subscri|^gls$|^pw", n, re.I)]
    return [
        f"עוגייה: {len(fields)} שדות, {len(cookie or '')} תווים, חתימה {sig}",
        "  (השווה את החתימה לריצה קודמת כדי לדעת אם הסוד הוחלף)",
        f"  שמות: {', '.join(names) if names else 'אין'}",
        f"  שדות שנראים כהזדהות: {auth or 'אין'}",
    ]


def diagnose(sess, cookie: str) -> str:
    """מה בדיוק חזר מגלובס — **בלי לפענח שום תוכן.**

    האבחון מדווח אורכים, מבנה טפסים וספירות, ולא מילים. זה גם מה
    שנחוץ כדי להכריע למה הגישה נכשלה, וגם מה שמותר להדפיס ללוג ציבורי.
    """
    L = cookie_report(cookie)
    ua = ua_from_env()
    L.append(f"User-Agent מהבלוק: {ua[:70] if ua else 'לא נמצא — נשלח UA של curl_cffi'}")
    try:
        _, rep = recognized(sess)
        L += rep
    except Exception as e:
        L.append(f"בדיקת הזיהוי נכשלה: {type(e).__name__}: {e}")

    try:
        rows = discover(sess)
        L.append(f"ערוץ התמלילים: {len(rows)} שורות")
    except Exception as e:
        L.append(f"ערוץ התמלילים נכשל: {type(e).__name__}: {e}")
        rows = []

    # מדדי הכתבה נשארים בדיווח כי הם מאשרים שהמשיכה עצמה עובדת — אבל
    # **הם אינם עדות להרשאה**: IsPaywall הוא תכונה של הכתבה (חופשית=False,
    # חסומה=True גם בגלישה אנונימית), ומחרוזות החסימה מופיעות בשתיהן.
    if rows:
        did = rows[0]["did"]
        r = sess.get(ARTICLE.format(did), timeout=60)
        pw = re.search(r"IsPaywall\s*=\s*[\"']([^\"']*)", r.text)
        env = re.search(r"textEnv\s*=\s*[\"']([^\"']*)", r.text)
        L.append(f"כתבה {did}: HTTP {r.status_code}, {len(r.text):,} תווים "
                 f"(IsPaywall={pw.group(1) if pw else '-'}, "
                 f"textEnv={len(env.group(1)) if env else 0:,}) — "
                 f"תכונות של הכתבה, לא של ההרשאה")
    return "\n".join(L)


class OutOfCredit(Exception):
    """היתרה אזלה. אין טעם להמשיך לתמליל הבא."""


# שגיאות שחולפות מעצמן: עומס בצד המודל, מגבלת קצב, ותקלות שער זמניות.
# **בלעדי הניסיון החוזר אבדו 46 תמלילים בריצה אחת** — כולם על
# overloaded_error, שהיא בהגדרה זמנית.
TRANSIENT = ("overloaded", "rate_limit", "429", "500", "502", "503", "529",
             "timeout", "connection", "temporarily")


def transient(err: Exception) -> bool:
    t = f"{type(err).__name__} {err}".lower()
    if "credit balance" in t or "insufficient" in t:
        return False
    return any(k in t for k in TRANSIENT)


def summarize(text: str, meta: dict, tries: int = 4) -> str:
    """סיכום עם ניסיון חוזר על שגיאות חולפות.

    **היתרה אינה שגיאה חולפת.** כשהיא אזלה, הריצה מפסיקה מיד במקום
    לנסות עוד חמישים תמלילים ולקבל את אותה תשובה — נמדד בריצה #18,
    שבזבזה ארבע-עשרה ניסיונות אחרי שכבר היה ברור שאין כסף.
    """
    from anthropic import Anthropic

    head = (f"חברה: {meta['company']}\nתקופה: {meta['period']}\n"
            f"תאריך פרסום התמליל: {meta['date']}\nמקור: גלובס\n\n"
            "להלן התמליל. כתוב את הסיכום.\n\n")
    client = Anthropic()
    delay = 20
    last = None
    for attempt in range(1, tries + 1):
        try:
            with client.messages.stream(
                    model=MODEL,
                    max_tokens=32000,
                    system=SYSTEM,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "high"},
                    messages=[{"role": "user", "content": head + text}]) as st:
                msg = st.get_final_message()
            break
        except Exception as e:
            last = e
            if "credit balance" in str(e).lower() or "insufficient" in str(e).lower():
                raise OutOfCredit(str(e)[:200]) from e
            if not transient(e) or attempt == tries:
                raise
            print(f"    ניסיון {attempt}/{tries} נכשל ({type(e).__name__}) — "
                  f"המתנה {delay}ש", flush=True)
            time.sleep(delay)
            delay *= 2
    else:
        raise last or RuntimeError("הסיכום נכשל")

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
        bad = 0
        # פיצול על newline בלבד: splitlines מפצל גם על U+2028 ודומיו,
        # שיושבים בתוך מחרוזות JSON תקינות לגמרי.
        lines = f.read_text(encoding="utf-8").split("\n")
        for ln in lines:
            if not ln.strip():
                continue
            try:
                out.add(json.loads(ln)["did"])
            except Exception:
                bad += 1
        # **שורה שלא נקראה חייבת להישמע.** הבליעה השקטה כאן היא שגרמה
        # לסיכום חוזר של שמונה תמלילים ששולם עליהם: הקובץ היה במקומו,
        # אף מזהה לא נקרא ממנו, ושום דבר לא אמר זאת.
        if bad:
            print(f"::warning::{f.name}: {bad} מתוך {len(lines)} שורות "
                  f"לא נקראו — הדה-דופ חלקי ותמלילים עלולים לסוכם שוב")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8,
                    help="כמה תמלילים חדשים לסכם בריצה (עלות API)")
    ap.add_argument("--since", default="",
                    help="לסכם רק תמלילים מתאריך זה ואילך (YYYY-MM-DD)")
    ap.add_argument("--redo", action="store_true",
                    help="לסכם מחדש גם תמלילים שכבר סוכמו (למשל אחרי "
                         "תיקון בפענוח שהפך סיכומים קודמים לחסרי ערך)")
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
    ua = ua_from_env()
    sess = session(cookie, ua)

    if args.probe:
        # **מצב האבחון אינו אוכף, הוא מדווח.** שער שנועל את הריצה לפני
        # שהוא אומר מה ראה מחייב סבב נוסף בשביל כל שאלה, והלוגים כאן
        # דורשים אימות לקריאה — ולכן הדיווח יוצא כאנוטציה ולא כ-print.
        report = diagnose(sess, cookie)
        annotate("warning", "אבחון גישת גלובס", report)
        print(report)
        # **מה כבר שמור בריפו התוכן** — הבדיקה החינמית שמפרידה בין
        # "הסיכומים לא נשמרו" ל"נשמרו ואינם מוצגים". ריצה שסיכמה שוב
        # את אותם שמונה תמלילים שילמה פעמיים, ובלי הדיווח הזה אי אפשר
        # היה לדעת מי משני הכיוונים נשבר בלי לשלם שלישית.
        done = load_done()
        L = [f"תיקיית {OUT.relative_to(ROOT)} קיימת: {OUT.is_dir()}",
             f"מזהים שכבר סוכמו: {len(done)}"]
        for tf in (sorted(OUT.glob("transcripts_*.jsonl")) if OUT.is_dir() else []):
            raw = tf.read_bytes()
            lines = raw.decode("utf-8", "replace").splitlines()
            L.append(f"{tf.name}: {len(raw):,} בתים, {len(lines)} שורות")
            for i, ln in enumerate(lines[:3], 1):
                if not ln.strip():
                    L.append(f"  שורה {i}: ריקה")
                    continue
                try:
                    # **מפתחות בלבד ולא ערכים** — הרשומה מחזיקה תמליל מלא,
                    # והאנוטציות ציבוריות.
                    L.append(f"  שורה {i}: {len(ln):,} תווים, "
                             f"מפתחות {sorted(json.loads(ln).keys())}")
                except Exception as e:
                    L.append(f"  שורה {i}: {len(ln):,} תווים, "
                             f"שגיאת פרסור {type(e).__name__} — {e}")
        if OUT.is_dir():
            L.append(f"כל הקבצים בתיקייה: {sorted(f.name for f in OUT.iterdir())}")
        annotate("warning", "מצב ריפו התוכן", "\n".join(L))
        return 0

    ok, rep = recognized(sess)
    if not ok:
        # **נכשל סגור.** בלי זיהוי אין ראיה שהתוכן שלנו לקרוא, ולכן
        # אין פענוח — גם אם טכנית הוא מגיע לכאן מוצפן בכל מקרה.
        annotate("error", "הסשן אינו מזוהה בגלובס",
                 "\n".join(rep + [""] + cookie_report(cookie)))
        return 1
    print("זיהוי סשן: אושר")

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

    # **חלון תאריכים.** הערוץ מחזיק כשבעים תמלילים, ולעיתים רוצים רק
    # את מה שפורסם בימים האחרונים. הסינון כאן ולא בגילוי, כדי שספירת
    # "מה יש בערוץ" תישאר נכונה בדיווח.
    if args.since:
        before = len(mine)
        mine = [r for r in mine if (r.get("date") or "") >= args.since]
        print(f"סינון מ-{args.since}: {len(mine)} מתוך {before}")
    for r in mine:
        if r["match"] == "prefix":
            print(f"::notice::התאמת תחילית: גלובס {r['globes_name']!r} "
                  f"→ כיסוי {r['company']!r}")
    n_cov = sum(1 for r in mine if r["match"] != "none")
    print(f"בערוץ: {len(rows)} תמלילים | בכיסוי: {n_cov}"
          + (f" | לסיכום (--all): {len(mine)}" if args.all else ""))

    year = str(date.today().year)
    done = set() if args.redo else load_done()
    if args.redo:
        print("::warning::--redo פעיל: תמלילים שכבר סוכמו יסוכמו שוב בתשלום")
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
        except OutOfCredit as e:
            # **היתרה אזלה — עוצרים מיד.** ריצה #18 המשיכה לנסות
            # ארבעה-עשר תמלילים אחרי שכבר היה ברור שאין כסף, וכל אחד
            # מהם קיבל את אותה תשובה. מה שכבר סוכם נשמר בשלב הבא.
            annotate("error", "יתרת Anthropic אזלה",
                     "\n".join([
                         f"הריצה נעצרה אחרי {ok} סיכומים.",
                         str(e),
                         "טעינה: console.anthropic.com/settings/billing",
                         "הריצה הבאה תמשיך מהמקום שבו נעצרה — "
                         "הדה-דופ מונע תשלום כפול.",
                     ]))
            break
        except Garbled as e:
            # פענוח שנכשל אינו מגיע למודל. תשלום על סיכום של ג'יבריש
            # כבר קרה פעמיים, וזה בדיוק מה שהשער הזה מונע.
            print(f"::warning::{r['company']} ({r['did']}): {e}")
            fail += 1
            continue
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
            "heb": round(hebrew_ratio(body), 3),
            "summary": md, "text": body,
            "generated": datetime.now().isoformat(timespec="seconds"),
        }
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ok += 1
        print(f"נשמר: {r['company']} {r['period']} "
              f"({len(body):,} תווים → {len(md):,} סיכום)")

    left = max(0, len(todo) - args.limit)
    # **ריצה מוצלחת חייבת לומר כמה היא הפיקה.** ריצה שסיכמה אפס וריצה
    # שסיכמה שמונה נראות זהות בעמוד ה-Actions, והלוג עצמו דורש אימות
    # כדי להיקרא. בלי השורה הזו "הצליח" אינו אומר דבר.
    annotate("notice", "סיכום ריצת תמלולים",
             f"סוכמו {ok} · נכשלו {fail} · נותרו {left} במגבלת --limit · "
             f"סה\"כ בכיסוי {len(mine)} מתוך {len(rows)} בערוץ")
    print(f"סיכום ריצה: {ok} הצליחו, {fail} נכשלו")
    return 1 if (ok == 0 and todo) else 0


if __name__ == "__main__":
    sys.exit(main())
