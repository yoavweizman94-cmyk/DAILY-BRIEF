# -*- coding: utf-8 -*-
"""אינדקס דוחות כספיים של כל החברות בבורסה, לחיפוש והורדה ישירה מהאתר.

למה אינדקס ולא קריאה חיה מהדפדפן: ל-API של מאיה אין CORS, והוא מחזיר 403
לבקשה שמגיעה מדפדפן בדומיין זר. לעומת זאת mayafiles.tase.co.il (שרת הקבצים)
כן מגיש עם `Access-Control-Allow-Origin: *` — ולכן הקישור להורדה עובד ישירות
מהאתר, וכל מה שצריך לייצר כאן הוא רשימת הדוחות ונתיבי ה-PDF שלהם.

המגבלה שקובעת את המבנה כאן היא **תקרת עימוד**, לא חסימת WAF: בקשה עם offset
מעל ~1000 מוחזרת כ-HTTP 400 (ראה OFFSET_CEILING ב-_maya_api.py). בנפח של
~180 דיווחים ביום, חלון של שבוע חוצה את התקרה ומחזיר 400 שנראה כמו חסימה
אקראית. לכן החלון הוא 4 ימים, ו-harvest מפצל אותו לבד אם בכל זאת נחצתה.

שני מצבי הרצה:

  --recent N   חלון קצר (ברירת מחדל 3 ימים) — רץ בצנרת היומית, עלות זניחה.
               זו הדרך שבה האינדקס גדל בפועל, יום אחר יום.
  --backfill   הליכה אחורה עם תקציב זמן. שומר מצב אחרי כל חלון, כך שהפסקה
               או כשל אינם מאבדים דבר וההרצה הבאה ממשיכה מאותה נקודה.
  --repair-pdf תיקון בחירת ה-PDF ברשומות שנאספו לפני 17/09/2026 (ראה pick_pdf),
               דיווח אחר דיווח, עם תקציב זמן. רשומה שתוקנה מסומנת ואינה נבדקת שוב.

פלט: output/filings/<שנה>.jsonl + manifest.json (נטענים ע"י site/pages/filings.html)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.parse import quote

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402

harden()

from _maya_api import MayaSession, WindowTooLarge  # noqa: E402
from _maya_doc import FILES_BASE as FILES, decode  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "filings"
STATE = ROOT / "data" / "maya_index_state.json"

# מה נחשב "דוח כספי". ת930 (תקופתי/רבעוני) ו-ת950 (אותו דוח ב-iXBRL) הם
# ודאיים ונכנסים לפי הטופס. השאר מזוהה לפי כותרת, כי חברות דואליות ותאגידי
# חוב מדווחים בטפסים אחרים (C001, C002, ת150, ת031).
FIN_FORMS = {"ת930", "ת950"}
FIN_TITLE = re.compile(
    r"דוח(?:ות)?\s*(?:כספי|רבעון|רבעוני|תקופתי|שנתי|חצי[-\s]*שנתי)"
    r"|דוחות\s+כספיים|תמצית\s+דוחות|financial\s+statements|10[-\s]?Q|6[-\s]?K",
    re.IGNORECASE)
# הודעה על **מועד** פרסום עתידי אינה דוח. נמדד: 12 מתוך 16 דיווחי ת121 שנתפסו
# בסינון לפי כותרת היו הודעות כאלה — רעש שמטביע את הדוחות עצמם.
NOISE_TITLE = re.compile(r"מועד\s+פרסום|הודעה\s+על\s+מועד|זימון\s+אסיפה")
# מצגת תוצאות היא חומר שאנליסט רוצה, אבל היא לא הדוח — תיוג נפרד, לא הדרה.
PRESENTATION = re.compile(r"מצגת|presentation", re.IGNORECASE)

# נפח נמדד: ~180 דיווחים ביום בכל הבורסה, כלומר ~1,250 לשבוע — מעל תקרת
# העימוד של 1,000. חלון של 4 ימים (~720) נשאר מתחתיה גם בעונת הדוחות, ואם
# בכל זאת נחצתה, harvest מפצל את החלון בעצמו.
WINDOW_DAYS = 4
BACKFILL_PAUSE = 6.0     # שהייה בין חלונות
THROTTLE = 1.0           # בין עמודים בתוך חלון (0.4 היא ברירת המחדל היומית)
MAX_RETRIES = 2          # ניסיונות עם סשן חדש לפני שמוותרים על החלון


def classify(rep: dict) -> str | None:
    """'דוח' / 'מצגת' / None אם אינו רלוונטי לאינדקס."""
    title = rep.get("title") or ""
    if (rep.get("formId") or "") in FIN_FORMS:
        return "דוח"                      # הטופס מכריע, תהיה הכותרת אשר תהיה
    if PRESENTATION.search(title):
        return "מצגת" if FIN_TITLE.search(title) else None
    if NOISE_TITLE.search(title):
        return None
    return "דוח" if FIN_TITLE.search(title) else None


def norm_name(s: str) -> str:
    """נרמול שם חברה להשוואה.

    companies.yaml כותב "אלקטרה נדלן" ומאיה כותבת "אלקטרה נדל\"ן". השוואת
    מחרוזות גולמית סימנה שלוש חברות כיסוי (אלרוב, ארי ואלקטרה נדל"ן) כאילו
    אינן בכיסוי, וסינון "כיסוי בלבד" באתר הסתיר את הדוחות שלהן.
    """
    s = re.sub(r"[\"'״׳`]", "", s or "")
    return re.sub(r"\s+", " ", s.replace("-", " ")).strip().lower()


def coverage_names() -> set[str]:
    cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    names = set()
    for c in cfg.get("companies") or []:
        for k in ("name_he", "name_en"):
            if c.get(k):
                names.add(norm_name(str(c[k])))
        for a in c.get("aliases") or []:
            if a:
                names.add(norm_name(str(a)))
    return {n for n in names if n}


# **המסמך הראשי: קודם טופס הדיווח, ורק כשאין בו תשובה — שם הקובץ.**
#
# הכלל המקורי בחר את ה-PDF הגדול ביותר בדיווח. בדוח התקופתי של לוינשטין
# הנדסה לשנת 2025 יש שני קבצים: הדוח (4,969KB) ו"הערכות_שווי_לוינשטין_הנדסה"
# (9,062KB) — ונבחרו הערכות השווי. הסקירה נכתבה על דוח שמאי, וההורדה הובילה
# אליו. באינדקס של 17/09/2026 הכלל בחר קובץ שאינו הראשון ב-352 דיווחים.
#
# **הטופס אומר במפורש איזה קובץ הוא הדוח.** בטפסים ת930, ת939 ו-ת031 המגיש
# ממלא שדה קובץ ראשי (STD-FieldAlias="File" — "דוח תקופתי בפורמט PDF" ב-ת930,
# "דוחות כספיים" בבנקים) ושדות לקבצים נוספים (File_1, File_2). ב-ת930 File_1
# הוא "קובץ הערכות השווי המהותיות מאוד", ו-File_2 קובץ עם הסבר שהמגיש כתב
# ("דוח כספי של חברה כלולה" — כך בפריורטק, שם הדוח של Access היה הגדול).
# ה-onclick של כל שדה נושא את מספר הקובץ: openReport(<id>,'PDF',1) הוא
# P<id>-01.pdf. **סדר השדות אינו סדר הקבצים** — בלאומי דוח הסיכונים הוא -00
# והדוחות הכספיים -01. הטופס (~120KB) נמשך רק כשיש יותר מ-PDF אחד, ופעם אחת
# לכל דיווח: הרצה שרואה שוב את אותם קבצים משתמשת בבחירה הקודמת.
#
# **כשאין בטופס שדה כזה — ניקוד לפי שם.** בחירה לפי מילות מפתח בלבד, ובשוויון
# את הקובץ הראשון, נבדקה על 180 דיווחים אמיתיים ובחרה לא נכון בשורה של מקרים:
# ברפק את הדוחות של חברה כלולה ("MRC_Alon_Tavor_Power") במקום "RAPACQ2_2026",
# בריט 1 קובץ נכס ("Raanana") במקום "Reit1_30062026", בפרידנזון את הדוח של
# חברה בת כי בשמו "דוח כספי". לכן הניקוד משלב כמה סימנים:
#   · נספח מובהק (הערכת שווי, שמאות, חוות דעת, ביאור, דוח סיכונים, מצגת,
#     נספחים, מכתב הסכמה, "HS" של רבד) — יוצא מהמרוץ.
#   · שם החברה בשם הקובץ, בעברית או באנגלית — הדוח שלה, לא של חברה כלולה.
#   · קובץ בסיס מול אותו שם עם סיומת — הסיומת היא הנספח.
#   · הגודל היחסי — בין מה שנשאר, הדוח הוא בדרך כלל הקובץ הגדול.
# מילות "דוח", "רבעון", "שנתי" מוסיפות מעט, כדי להכריע בין קבצים בגודל דומה.
PICK_VERSION = 1
PICK_KEYS = ("p", "s", "pk", "pn", "pa", "pv", "pf")

FORM_FILE = re.compile(r'<SPAN\b([^>]*\bSTD-FieldAlias="(File(?:_\d+)?)"[^>]*)>(.*?)</SPAN>',
                       re.IGNORECASE | re.DOTALL)
FORM_DESC = re.compile(r'<SPAN\b[^>]*\bSTD-FieldAlias="DescriptionFile"[^>]*>(.*?)</SPAN>',
                       re.IGNORECASE | re.DOTALL)
FORM_INDEX = re.compile(r"openReport\(\s*\d+\s*,\s*'PDF'\s*,\s*(\d+)\s*\)", re.IGNORECASE)
FORM_VALUATIONS = re.compile(r"הערכות\s+השווי|הערכת\s+שווי|הערכות\s+שווי")
VALUATIONS_LABEL = "הערכות שווי מהותיות מאוד"
# "חלק ג" / "חלקים ב + ג" — בדוח התקופתי חלק ג הוא הדוחות הכספיים.
FS_PART = re.compile(r"(?:חלק|פרק)(?:ים)?\s*(?:[א-ה]['׳]?\s*(?:[+,&]|ו-?|\s)\s*)*ג['׳]?(?![א-ת])")
OTHER_PARTS_LABEL = "יתר חלקי הדוח התקופתי"

NOT_MAIN_DOC = re.compile(
    r"הערכ\w*[\s_\-]*שווי|שמא[יו]|שמאות|שומ(?:ה|ת|ות)|valuation|apprais|shama|shamo|shmo|shuma|shov[iy]"
    r"|חוו[\"״']?ד|חוות[\s_\-]*דעת|opinion|ביאור|באור|נספח|appendi|annex|סיכונים|נדבך|pillar|\brisk"
    r"|מצגת|presentation|מכתב[\s_\-]*הסכמה|consent|תרגום|translation|english|מסומן|\bppa\b",
    re.IGNORECASE)
# שם קובץ שהוא רק ראשי תיבות של נספח: "HS_isa.pdf" ברבד הוא "הסכמה להכללת
# הערכות שווי" (10,259KB), והדוח התקופתי לידו הוא "FS311225_isa.pdf" (3,308KB).
NOT_MAIN_STEM = re.compile(r"hs\d*")
MAIN_DOC = re.compile(r"דוח|דו\"ח|דו״ח|רבעון|תקופתי|שנתי|report|annual|quarter", re.IGNORECASE)
FIN_DOC = re.compile(r"כספי|financial|statements|(?<![a-z])fs(?![a-z])", re.IGNORECASE)


def pdf_attachments(rep: dict) -> list[dict]:
    """כל קובצי ה-PDF בדיווח, בסדר שמאיה מציגה. fileType מגיע כ-pdf1/pdf2 ולא
    כ-pdf, ו-fileSize הוא קילובייטים (נבדק: fileSize=457 מול 468,608 בתים)."""
    out = []
    for a in rep.get("attachments") or []:
        if (a.get("fileType") or "").lower().startswith("pdf") and a.get("url"):
            out.append({"p": a["url"].lstrip("/"), "n": (a.get("fileName") or "").strip(),
                        "s": a.get("fileSize") or 0})
    return out


def _compact(t: str) -> str:
    return re.sub(r"[\s_\-\"'״׳.]+", "", t or "").lower()


def _stem(n: str) -> str:
    """שם הקובץ בלי סיומת, בלי _isa ובלי מפרידים — להשוואת קובץ בסיס מול גרסה."""
    n = re.sub(r"\.pdf$", "", n or "", flags=re.IGNORECASE)
    n = re.sub(r"[_\-]*isa$", "", n, flags=re.IGNORECASE)
    return _compact(n)


def _form_text(fragment: str) -> str:
    t = unescape(re.sub(r"<[^>]+>", " ", fragment or ""))
    t = " ".join(t.split())
    return "" if not t.strip("_ .") else t


def form_files(page: str) -> list[dict]:
    """שדות הקבצים בטופס הדיווח, לפי סדר הופעתם.

    [{"i": מספר הקובץ מה-onclick או None, "n": שם הקובץ, "main": שדה File,
      "l": "הערכות שווי מהותיות מאוד" / ההסבר שהמגיש כתב / ""}]
    הכיתוב של שדה נלקח רק מהטקסט שבינו לבין השדות השכנים, כדי שהכותרת
    "להלן קובץ הערכות השווי" לא תידבק לקובץ שאחריה.
    """
    page = page or ""
    ms = list(FORM_FILE.finditer(page))
    out = []
    for k, m in enumerate(ms):
        name = _form_text(m.group(3))
        if not name:
            continue
        idx = FORM_INDEX.search(m.group(1))
        main = m.group(2).lower() == "file"
        label = ""
        if not main:
            before = page[ms[k - 1].end() if k else max(0, m.start() - 1500):m.start()]
            after = page[m.end():ms[k + 1].start() if k + 1 < len(ms) else m.end() + 1500]
            if FORM_VALUATIONS.search(_form_text(before)):
                label = VALUATIONS_LABEL
            else:
                d = FORM_DESC.search(after)
                label = _form_text(d.group(1))[:80] if d else ""
        out.append({"i": int(idx.group(1)) if idx else None, "n": name, "main": main, "l": label})
    return out


def match_form(pdfs: list[dict], fields: list[dict]) -> tuple[int | None, dict[int, str]]:
    """(מיקום המסמך הראשי ב-pdfs או None, {מיקום: כיתוב}) לפי שדות הטופס.

    שם הקובץ קודם, ומספר הקובץ מה-onclick כגיבוי — שניהם נוצרים במגנ"א ולא
    בידי המגיש, אבל שם שמופיע פעמיים אינו מכריע.
    """
    def locate(f: dict) -> int | None:
        key = _compact(f["n"])
        hits = [j for j, a in enumerate(pdfs) if key and _compact(a["n"]) == key]
        if len(hits) == 1:
            return hits[0]
        if f["i"] is not None:
            tail = re.compile(rf"-0*{f['i']}\.pdf$", re.IGNORECASE)
            hits = [j for j, a in enumerate(pdfs) if tail.search(a["p"])]
            if len(hits) == 1:
                return hits[0]
        return None

    main, labels = None, {}
    for f in fields:
        j = locate(f)
        if j is None:
            continue
        if f["main"]:
            main = j if main is None else main
        elif f["l"]:
            labels.setdefault(j, f["l"])
    labels.pop(main, None)
    # דוח תקופתי מפוצל: בפלסאון השדה הראשי הוא "פלסאון_2025_חלק_א_ד_ה" (תיאור
    # העסקים ופרטים נוספים), והדוחות הכספיים בקובץ הנוסף — "חלקים ב + ג לדוח
    # התקופתי". אינדקס של דוחות כספיים, והסקירה שנכתבת ממנו, צריכים את חלק ג.
    if main is not None and not FS_PART.search(pdfs[main]["n"].replace("_", " ")):
        fs = [j for j, lab in labels.items() if FS_PART.search(lab)]
        if len(fs) == 1:
            labels[main] = OTHER_PARTS_LABEL
            main = fs[0]
            labels.pop(main, None)
    return main, labels


_EN_TOKENS: dict[str, tuple[set[str], set[str]]] | None = None


def english_tokens(name_he: str) -> tuple[set[str], set[str]]:
    """מילים ושם בראשי תיבות מהשם האנגלי ב-companies.yaml, לחברות שיש להן כזה.

    חברות רבות מגישות קבצים בשם אנגלי ("ERE626" של אלקטרה נדל"ן, "RAPACQ2"),
    ושם החברה בעברית לא יופיע בהם. ראשי התיבות נבדקים רק בתחילת שם הקובץ
    ורק משלוש אותיות, כדי ש"CG" לא יימצא באמצע כל מחרוזת.
    """
    global _EN_TOKENS
    if _EN_TOKENS is None:
        _EN_TOKENS = {}
        try:
            cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — בלי קובץ הכיסוי פשוט אין שמות אנגליים
            cfg = {}
        for c in (cfg or {}).get("companies") or []:
            en = c.get("name_en") or ""
            if not en or not c.get("name_he"):
                continue
            words = [w for w in re.split(r"[^A-Za-z0-9]+", en) if w]
            toks = {w.lower() for w in words if len(w) >= 4}
            acro = "".join(w[0] for w in words).lower()
            _EN_TOKENS[_compact(norm_name(c["name_he"]))] = (toks, {acro} if len(acro) >= 3 else set())
    return _EN_TOKENS.get(_compact(norm_name(name_he)), (set(), set()))


def name_pick(rep: dict, pdfs: list[dict]) -> int:
    """המסמך הראשי לפי שמות הקבצים וגודלם — כשהטופס לא הכריע."""
    names = [c.get("name") or "" for c in (rep.get("companies") or [])]
    tokens = {_compact(w) for n in names for w in re.split(r"[\s\-]+", n) if len(_compact(w)) >= 3}
    acronyms: set[str] = set()
    for n in names:
        en, acro = english_tokens(n)
        tokens |= en
        acronyms |= acro
    biggest = max((a["s"] for a in pdfs), default=0) or 1
    stems = [_stem(a["n"]) for a in pdfs]

    def score(i: int) -> tuple:
        raw = pdfs[i]["n"]
        n = raw.replace("_", " ")
        c = _compact(raw)
        sc = 30.0 * pdfs[i]["s"] / biggest
        if NOT_MAIN_DOC.search(n) or (stems[i] and NOT_MAIN_STEM.fullmatch(stems[i])):
            sc -= 100
        if MAIN_DOC.search(n):
            sc += 10
        if FIN_DOC.search(n):
            sc += 5
        if (tokens and any(t in c for t in tokens)) or any(c.startswith(a) for a in acronyms):
            sc += 40
        # קובץ בסיס מול אותו שם עם סיומת ("CG_2025" מול "CG_2025_A"): הסיומת
        # היא כמעט תמיד נספח — הערכות שווי, אישורים — גם כשהוא הגדול.
        if stems[i] and any(j != i and stems[j] != stems[i] and stems[j].startswith(stems[i])
                            for j in range(len(pdfs))):
            sc += 25
        return (sc, -i)

    return max(range(len(pdfs)), key=score)


def fetch_form(s: MayaSession, path: str) -> str | None:
    """טופס ה-HTM של דיווח מ-mayafiles, או None בתקלה (ואז הרשומה תיבדק שוב).

    בלי המתנת המגביל: mayafiles הוא שרת קבצים סטטי ולא ה-API שה-WAF סופר בו
    בקשות — כך גם maya_calls מושך משם טפסים.
    """
    try:
        r = s._s.get(FILES + path, timeout=60)
        if r.status_code != 200:
            return None
        return decode(r.content)
    except Exception:  # noqa: BLE001 — תקלת רשת בטופס אחד אינה עוצרת את האיסוף
        return None


def pick_pdf(rep: dict, form=None) -> dict:
    """המסמך הראשי בדיווח, ושאר הקבצים כנספחים.

    form — פונקציה שמקבלת נתיב htm ומחזירה את הטופס (fetch_form). בלעדיה
    הבחירה היא לפי שם בלבד.

    מחזיר שדות לרשומת האינדקס: p/s — המסמך הראשי; pn — שמו, רק כשיש יותר
    מקובץ אחד; pa — הנספחים, עם l = הכיתוב מהטופס כשיש; pf=1 כשהטופס הכריע;
    pv=2 כשהבחירה שונה ממה שהכלל הישן (הגדול ביותר) היה בוחר — סימן שסקירה
    שנשמרה לפני התיקון נכתבה על מסמך אחר; pk — גרסת הכלל. **בלי pk** כשהטופס
    היה נחוץ ולא נמשך: הבחירה לפי שם נשמרת בינתיים, והרשומה תיבדק שוב.
    """
    pdfs = pdf_attachments(rep)
    if not pdfs:
        return {"p": None, "s": 0, "pk": PICK_VERSION}
    best, labels, sure = None, {}, True
    if len(pdfs) > 1 and form is not None:
        htm = next((a for a in rep.get("attachments") or []
                    if (a.get("fileType") or "").lower().startswith("htm") and a.get("url")), None)
        if htm:
            page = form(htm["url"].lstrip("/"))
            if page is None:
                sure = False
            else:
                best, labels = match_form(pdfs, form_files(page))
    by_form = best is not None
    if best is None:
        best = name_pick(rep, pdfs)
    legacy = max(range(len(pdfs)), key=lambda i: (pdfs[i]["s"], -i))
    out = {"p": pdfs[best]["p"], "s": pdfs[best]["s"]}
    if sure:
        out["pk"] = PICK_VERSION
    if len(pdfs) > 1:
        out["pn"] = pdfs[best]["n"]
        out["pa"] = [{**a, **({"l": labels[i]} if labels.get(i) else {})}
                     for i, a in enumerate(pdfs) if i != best]
        if by_form:
            out["pf"] = 1
    if best != legacy:
        out["pv"] = 2
    return out


def same_files(prev: dict | None, rep: dict) -> bool:
    """הרשומה הקודמת נבחרה בכלל הנוכחי ועל אותם קבצים — אין סיבה למשוך שוב את הטופס.

    maya-watch רואה כל דיווח שוב ושוב במשך ארבעה ימים. בלי זה כל הרצה הייתה
    מורידה מחדש את הטפסים של כל הדוחות מרובי הקבצים בחלון.
    """
    if not prev or prev.get("pk") != PICK_VERSION:
        return False
    had = {x for x in [prev.get("p")] if x} | {a.get("p") for a in prev.get("pa") or []}
    return had == {a["p"] for a in pdf_attachments(rep)}


def to_entry(rep: dict, cover: set[str], kind: str, prev: dict | None = None,
             form=None) -> dict | None:
    pk = ({k: prev[k] for k in PICK_KEYS if k in prev} if same_files(prev, rep)
          else pick_pdf(rep, form))
    ts = rep.get("publishDate") or ""
    day = ts[:10]
    if not day:
        return None
    comps = [c.get("name") for c in (rep.get("companies") or []) if c.get("name")]
    return {
        "id": str(rep.get("id")),
        "d": day,
        "t": (rep.get("title") or "").strip(),
        "f": rep.get("formId") or "",
        "c": comps,
        "ci": [c.get("companyId") for c in (rep.get("companies") or []) if c.get("companyId")],
        "p": pk.get("p"),                           # יחסי ל-mayafiles.tase.co.il
        "s": pk.get("s", 0),                        # KB
        "k": kind,                                  # דוח / מצגת
        "cov": 1 if any(norm_name(n) in cover for n in comps) else 0,
        **{k: v for k, v in pk.items() if k not in ("p", "s")},
    }


REVIEWS = OUT / "reviews"


def retire_review(rid: str) -> bool:
    """סקירה מוכנה מראש שנכתבה על מסמך אחר — נמחקת, ורשימת הסקירות נכתבת מחדש.

    **נמחקת ולא מתוקנת.** היא נכתבה על הקובץ הלא נכון, ולכן אין בה מה
    לשמור; הלחיצה הבאה בעמוד תייצר סקירה חדשה מהדוח עצמו.
    """
    f = REVIEWS / f"{rid}.md"
    if not f.exists():
        return False
    f.unlink()
    ids = sorted(x.stem for x in REVIEWS.glob("*.md"))
    (REVIEWS / "index.json").write_text(
        json.dumps({"ids": ids, "updated": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False), encoding="utf-8")
    return True


# --- קריאה/כתיבה של האינדקס -------------------------------------------------

def load_index(cover: set[str] | None = None) -> dict[str, dict]:
    idx = {}
    for f in OUT.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    e = json.loads(line)
                    idx[e["id"]] = e
                except (json.JSONDecodeError, KeyError):
                    pass
    # דגל הכיסוי מחושב מחדש בכל טעינה ולא רק לרשומות חדשות: רשימת הכיסוי
    # ב-companies.yaml משתנה, וכללי ההתאמה עצמם השתנו כאן — בלי חישוב מחדש
    # רשומות ישנות היו נשארות עם דגל שגוי לנצח.
    if cover is not None:
        for e in idx.values():
            e["cov"] = 1 if any(norm_name(n) in cover for n in (e.get("c") or [])) else 0
    return idx


def save_index(idx: dict[str, dict]) -> bool:
    """כותב את האינדקס ומחזיר האם התוכן באמת השתנה.

    ה-workflow מחליט לפי `git status` אם לקבע ולפרוס. כשחותמת הזמן נכתבה
    בכל הרצה, ריצה שלא הוסיפה אף דוח עדיין נראתה כשינוי — וגררה קומיט,
    בנייה ופריסה על לא כלום. לכן החותמת מתעדכנת רק כשהנתונים זזו.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, list] = {}
    for e in idx.values():
        by_year.setdefault(e["d"][:4], []).append(e)

    changed = False
    for f in OUT.glob("*.jsonl"):          # שנים שהתרוקנו לא נשארות מאחור
        if f.stem not in by_year:
            f.unlink()
            changed = True

    years = []
    for y, rows in sorted(by_year.items()):
        rows.sort(key=lambda e: e["d"], reverse=True)
        body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
        path = OUT / f"{y}.jsonl"
        if not path.exists() or path.read_text(encoding="utf-8") != body:
            path.write_text(body, encoding="utf-8")
            changed = True
        years.append({"year": y, "count": len(rows)})

    prev = {}
    try:
        prev = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        changed = True

    days = sorted(e["d"] for e in idx.values())
    (OUT / "manifest.json").write_text(json.dumps({
        "years": sorted(years, key=lambda x: x["year"], reverse=True),
        "total": len(idx),
        "earliest": days[0] if days else None,
        "latest": days[-1] if days else None,
        "updated": (datetime.now().isoformat(timespec="seconds") if changed
                    else prev.get("updated")),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return changed


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


# --- מצבי הרצה ---------------------------------------------------------------

def harvest(s: MayaSession, a: date, b: date, idx: dict, cover: set[str],
            depth: int = 0) -> int:
    """שואב חלון אחד. חלון צפוף מדי מפוצל לשניים ונשאב לחלקיו."""
    try:
        rows = s.reports_days(a, b)
    except WindowTooLarge as exc:
        if a >= b:
            # יום בודד מעל התקרה — אין מה לפצל. עדיף לדעת מזה לשתוק.
            print(f"  {a}: {exc.total} דיווחים ביום אחד, מעל תקרת העימוד — "
                  f"חלק מהיום לא ייכנס לאינדקס", file=sys.stderr)
            return 0
        mid = a + (b - a) // 2
        print(f"  {a}→{b}: {exc.total} דיווחים, מפוצל", file=sys.stderr)
        return (harvest(s, a, mid, idx, cover, depth + 1) +
                harvest(s, mid + timedelta(days=1), b, idx, cover, depth + 1))
    added = 0
    for rep in rows:
        kind = classify(rep)
        if not kind:
            continue
        prev = idx.get(str(rep.get("id")))
        e = to_entry(rep, cover, kind, prev=prev, form=lambda path: fetch_form(s, path))
        if e and prev is None:
            idx[e["id"]] = e
            added += 1
        elif e:
            if prev.get("p") != e.get("p"):
                retire_review(e["id"])
            idx[e["id"]] = e          # עדכון: קבצים מצורפים מתווספים אחרי הפרסום
    return added


def run_recent(days: int) -> int:
    cover = coverage_names()
    idx = load_index(cover)
    before = len(idx)
    s = MayaSession()
    today = date.today()
    added = harvest(s, today - timedelta(days=days - 1), today, idx, cover)
    save_index(idx)
    print(f"אינדקס דוחות: +{added} חדשים, {len(idx)} סה\"כ "
          f"(היו {before}, חלון {days} ימים)")
    return 0


def run_backfill(until: date, budget_min: float) -> int:
    cover = coverage_names()
    idx = load_index(cover)
    st = read_state()
    cursor = date.fromisoformat(st["backfill_earliest"]) if st.get("backfill_earliest") \
        else date.today()
    deadline = time.monotonic() + budget_min * 60
    s = MayaSession(throttle_sec=THROTTLE)
    total, windows = 0, 0

    while cursor > until and time.monotonic() < deadline:
        b = cursor - timedelta(days=1)
        a = max(until, b - timedelta(days=WINDOW_DAYS - 1))
        # תקלת רשת או 403 חולף: סשן חדש מזריע עוגיות WAF מחדש מדף הבית
        # ולרוב עובר. חלון צפוף מדי כבר טופל בתוך harvest ואינו מגיע לכאן.
        ok = False
        for attempt in range(MAX_RETRIES + 1):
            try:
                total += harvest(s, a, b, idx, cover)
                windows += 1
                cursor = a
                st["backfill_earliest"] = cursor.isoformat()
                ok = True
                break
            except Exception as exc:
                code = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt == MAX_RETRIES or time.monotonic() > deadline:
                    print(f"עצירה ב-{a}: {type(exc).__name__} {code or str(exc)[:60]}",
                          file=sys.stderr)
                    break
                wait = BACKFILL_PAUSE * (attempt + 2)
                print(f"  {a}: {code or type(exc).__name__} — סשן חדש בעוד {wait:.0f}s",
                      file=sys.stderr)
                time.sleep(wait)
                s = MayaSession(throttle_sec=THROTTLE)
        save_index(idx)                 # שמירה אחרי כל חלון — הפסקה לא מאבדת כלום
        write_state(st)
        if not ok:
            break
        time.sleep(BACKFILL_PAUSE)

    save_index(idx)
    write_state(st)
    done = cursor <= until
    print(f"מילוי אחורה: {windows} חלונות, +{total} דוחות, {len(idx)} סה\"כ · "
          f"הגיע עד {cursor} · {'הושלם' if done else 'ימשיך בהרצה הבאה'}")
    return 0


def run_repair(budget_min: float) -> int:
    """תיקון בחירת ה-PDF ברשומות שנאספו בכלל הישן — דיווח אחר דיווח.

    **הסדר הוא לפי הסיכון.** קודם רשומות שבהן הכלל הישן בחר קובץ שאינו הראשון
    (-01, -02): שם כמעט בוודאות נבחר נספח גדול. אחריהן חברות הכיסוי, מהחדש
    לישן, ובסוף השאר. כל רשומה נמשכת מ-/api/v1/reports/<id>, ומסומנת pk
    אחרי הבדיקה — כך שהרצה שנקטעה ממשיכה מאותה נקודה, בלי קובץ מצב. רשומה
    שהטופס שלה לא נמשך נשארת בלי סימון, ונבדקת שוב בהרצה הבאה.
    """
    cover = coverage_names()
    idx = load_index(cover)
    todo = [e for e in idx.values() if e.get("pk") != PICK_VERSION]
    # מיון יציב: קודם לפי תאריך מהחדש, ואז לפי הסיכון — כך שבתוך כל קבוצה
    # החדשים נבדקים ראשונים.
    todo.sort(key=lambda e: e.get("d") or "", reverse=True)
    todo.sort(key=lambda e: (
        0 if (e.get("p") or "").endswith(".pdf") and not (e.get("p") or "").endswith("-00.pdf") else 1,
        0 if e.get("cov") == 1 else 1))
    deadline = time.monotonic() + budget_min * 60
    s = MayaSession(throttle_sec=THROTTLE)
    checked = changed = retired = errors = deferred = by_form = 0
    samples = []
    for e in todo:
        if time.monotonic() > deadline:
            break
        rep = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                rep = s._get(f"/api/v1/reports/{quote(e['id'])}").json()
                break
            except Exception as exc:  # noqa: BLE001 — דיווח בודד אינו עוצר את התיקון
                code = getattr(getattr(exc, "response", None), "status_code", None)
                if code == 404:
                    break
                time.sleep(BACKFILL_PAUSE * (attempt + 1))
                s = MayaSession(throttle_sec=THROTTLE)
        if not isinstance(rep, dict) or not rep.get("attachments"):
            errors += 1
            if errors >= 25 and checked == 0:
                print("::warning title=תיקון ה-PDF נעצר::25 דיווחים ראשונים לא נמשכו ממאיה", file=sys.stderr)
                break
            continue
        pk = pick_pdf(rep, form=lambda path: fetch_form(s, path))
        if not pk.get("pk"):
            deferred += 1
            continue
        old = e.get("p")
        for k in PICK_KEYS:
            e.pop(k, None)
        e.update(pk)
        checked += 1
        by_form += 1 if pk.get("pf") else 0
        if pk.get("p") != old:
            changed += 1
            if len(samples) < 8:
                samples.append(f'{e.get("d")} {", ".join(e.get("c") or [])}: {e.get("pn") or "?"}')
            if retire_review(e["id"]):
                retired += 1
        if checked % 50 == 0:
            save_index(idx)
    save_index(idx)
    left = sum(1 for e in idx.values() if e.get("pk") != PICK_VERSION)
    print(f"::notice::תיקון בחירת ה-PDF: {checked} דיווחים נבדקו ({by_form} לפי הטופס), "
          f"{changed} הוחלפו למסמך הראשי, {retired} סקירות מוכנות נמחקו · נותרו {left:,} לבדיקה"
          + (f" · {errors} לא נמשכו" if errors else "")
          + (f" · {deferred} נדחו (הטופס לא נמשך)" if deferred else ""))
    if samples:
        print("  לדוגמה: " + " · ".join(samples))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="אינדקס דוחות כספיים ממאיה")
    p.add_argument("--recent", type=int, default=3, metavar="ימים",
                   help="חלון קדימה לצנרת היומית (ברירת מחדל: 3)")
    p.add_argument("--backfill", action="store_true",
                   help="הליכה אחורה בזמן במקום חלון עדכני")
    p.add_argument("--until", default="2023-01-01", metavar="YYYY-MM-DD",
                   help="עד לאיזה תאריך למלא אחורה")
    p.add_argument("--budget-minutes", type=float, default=25.0,
                   help="תקציב זמן להרצת מילוי אחת")
    p.add_argument("--repair-pdf", action="store_true",
                   help="תיקון בחירת ה-PDF ברשומות שנאספו בכלל הישן")
    args = p.parse_args()
    if args.repair_pdf:
        return run_repair(args.budget_minutes)
    if args.backfill:
        return run_backfill(date.fromisoformat(args.until), args.budget_minutes)
    return run_recent(args.recent)


if __name__ == "__main__":
    sys.exit(main())
