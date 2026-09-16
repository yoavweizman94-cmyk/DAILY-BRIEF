# -*- coding: utf-8 -*-
"""הלמ"ס: הודעות לתקשורת, לוח פרסומים ומדדים עיקריים → output/cbs/.

ארבעה מקורות, כולם ממשקים של הלמ"ס עצמה:

· **הודעות לתקשורת** — רשימות SharePoint בשם "דפים" בשני אתרים: mediarelease
  (רוב ההודעות) ו-mediarelease/madad (מדד המחירים לצרכן, מחירי דירות, מחירי
  יצרן ותשומות — ההודעות הרגישות לשוק). לכל הודעה: כותרת, מועד, נושאים,
  ותקציר HTML עם המספרים.
· **גוף ההודעה** — קובץ ה-PDF המצורף. שדות ה-HTML של הדף ריקים, ובחלק מההודעות
  (מאזן התשלומים, עסקאות נדל"ן) התקציר הוא רק הקישור "להודעה המלאה". ה-PDF
  נמשך רק להודעות רלוונטיות, ורק פעם אחת לכל גרסה של ההודעה.
· **לוח הפרסומים** — הרשימה "למס - תחזיות פרסום": מה יתפרסם ומתי.
· **מדדים ואינדיקטורים** — המספרים שהלמ"ס מציגה בדף הבית: ערך נוכחי, ערך
  קודם, תקופה, והסבר המונח בלשון הלמ"ס.
· **API המדדים** (api.cbs.gov.il/index) — היסטוריה חודשית של מדדי המחירים.

**ה-WAF של הלמ"ס סוגר את החיבור בלי תשובה לכל User-Agent שאינו דפדפן.**
זה נראה בדיוק כמו תקלת רשת (RemoteDisconnected) ולא כמו חסימה — נמדד
16/09/2026: אותה כתובת החזירה 200 עם כותרות Chrome מלאות, ונסגרה מיד עם
"Mozilla/5.0" בלבד. לכן כל בקשה נשלחת עם כותרות דפדפן מלאות, ובקצב של
בקשה לשנייה לכל היותר.

פלט:
  output/cbs/releases/<שנה>.jsonl — הודעה לשורה לפי id; נדרסת כשהלמ"ס מעדכנת
  output/cbs/snapshot.json        — לוח פרסומים, מדדים, סדרות מחירים, מועד משיכה

ב-GitHub Actions נכתבים ל-GITHUB_OUTPUT:
  new=yes     — יש הודעה רלוונטית שטרם נותחה
  changed=yes — משהו בפלט השתנה מאז הריצה הקודמת (ולכן כדאי לבנות ולפרוס)
"""
from __future__ import annotations

import http.client
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "cbs"
SITE = "https://www.cbs.gov.il"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# שני אתרי ההודעות. ה-Id של פריט SharePoint ייחודי רק בתוך הרשימה שלו, ולכן
# מזהה ההודעה אצלנו הוא הקידומת יחד עם ה-Id.
WEBS = (("mr", "/he/mediarelease"), ("madad", "/he/mediarelease/madad"))

LOOKBACK_DAYS = 14
CAL_BACK_DAYS = 1
CAL_AHEAD_DAYS = 21
BODY_MAX = 20000
PDF_MAX_BYTES = 25 * 1024 * 1024
PDF_MAX_PAGES = 30

PRICE_SERIES = {
    120010: "מדד המחירים לצרכן",
    40010: "מחירי דירות",
    170030: "מדד מחירי יצרן — תפוקת התעשייה ליעדים מקומיים",
    200010: "מדד מחירי תשומה בבנייה למגורים",
}

# נושא ראשי לפי תוויות הטקסונומיה של הלמ"ס וכותרת ההודעה. הסדר קובע:
# ההתאמה הראשונה היא הנושא. ההשוואה היא על תת-מחרוזת, כי הלמ"ס כותבת את
# אותו נושא בכמה צורות — "בינוי, דיור ונדל＂ן" עם מירכאה ברוחב מלא, למשל.
TOPICS = [
    ("prices", "מחירים ואינפלציה",
     ("מדד המחירים", "מדדי מחירים", "מדדי המחירים", "מחירי יצרן", "תשומה", "תשומות",
      "מחירי שוק הדירות", "אינפלציה")),
    ("housing", "דיור, בנייה ונדל\"ן",
     ("בינוי", "דיור", "נדל", "דירות", "בנייה", "משכנתא")),
    ("accounts", "צמיחה וחשבונות לאומיים",
     ("חשבונות לאומיים", "תוצר", "מאזן התשלומים", "חשבונות בין", "הוצאה לצריכה")),
    ("labor", "שוק העבודה ושכר",
     ("שוק העבודה", "שכר", "משרות", "תעסוקה", "מועסקים", "אבטלה", "כוח אדם")),
    ("trade", "סחר חוץ",
     ("יבוא", "יצוא", "סחר חוץ", "סחר החוץ")),
    ("business", "צריכה, מסחר ועסקים",
     ("רשתות שיווק", "מסחר", "עסקים", "כרטיסי אשראי", "פדיון", "קמעונ")),
    ("industry", "תעשייה והייטק",
     ("תעשייה", "ייצור התעשייתי", "הייטק", "חברות הזנק", "מחקר ופיתוח")),
    ("tourism", "תיירות ותחבורה",
     ("תיירות", "מלונות", "הארחה", "מבקרים", "יוצאים לחו", "כלי רכב")),
    ("surveys", "סקרי אמון וציפיות",
     ("אמון הצרכנים", "אמון צרכנים", "הערכות עסקים", "מגמות בעסקים")),
]
TOPIC_LABELS = {k: label for k, label, _ in TOPICS} | {"other": "נושאים נוספים"}

# הודעות שנושאן מתאים אבל אין בהן נתון שמזיז שוק — טקס, כנס, לקט חג.
# הן נשמרות ומוצגות, אבל אינן נשלחות לניתוח, שעולה כסף.
EXCLUDE_TITLE = ("הסכם", "כנס", "תרבות", "בידור", "ספורט", "בחירות", "הבוחרים",
                 "ישראל במספרים", "ערב ראש השנה", "ערב פסח", "סטטיסטי-קל", "מינוי",
                 "הסקר החברתי", "תאונות")


# --------------------------------------------------------------------------
# HTTP

_last_call = 0.0


def _fetch(url: str, accept: str, tries: int, timeout: int, limit: int | None = None) -> bytes:
    """GET עם כותרות דפדפן, קצב של בקשה לשנייה ונסיגה על תקלות רשת.

    RemoteDisconnected ו-5xx מקבלים ניסיון חוזר; 4xx אחר אינו חוזר — הוא
    בקשה שגויה, ולא תקלה חולפת.
    """
    global _last_call
    err: Exception | None = None
    for i in range(tries):
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": accept, "Accept-Language": "he,en;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(limit + 1) if limit else r.read()
            if limit and len(data) > limit:
                raise RuntimeError(f"הקובץ גדול מ-{limit // 1048576}MB")
            return data
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise
            err = e
        except (urllib.error.URLError, ConnectionError, TimeoutError,
                http.client.HTTPException) as e:
            err = e
        time.sleep(3 * (i + 1))
    assert err is not None
    raise err


def _get_json(url: str, accept: str = "application/json"):
    raw = _fetch(url, accept, tries=4, timeout=45)
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as e:
        # תשובה שאינה JSON היא כמעט תמיד דף חסימה של ה-WAF — נאמר בשמו.
        raise RuntimeError(f"תשובה שאינה JSON ({len(raw)} בייט) — כנראה דף חסימה") from e


def _q(params: dict) -> str:
    # רווח נשלח כ-%20 ולא כ-"+": מסנן OData של SharePoint אינו מפענח "+".
    return "&".join(f"{k}={urllib.parse.quote(str(v), safe=',()')}" for k, v in params.items())


def sp_items(web: str, title: str, params: dict) -> list[dict]:
    url = (f"{SITE}{web}/_api/web/lists/getbytitle('{urllib.parse.quote(title)}')/items?"
           + _q(params))
    return (_get_json(url, accept="application/json;odata=nometadata") or {}).get("value", [])


def pdf_text(url: str) -> str:
    """טקסט מ-PDF של הודעה, עם pypdf.

    **pypdf ולא PyMuPDF — נבדק 16/09/2026 על הודעת החשבונות הלאומיים.**
    PyMuPDF מחזיר כל שורה בסדר מילים הפוך (סדר חזותי), ולעיתים הופך גם
    תו בתוך מילה. pypdf מחזיר את גוף ההודעה בסדר הנכון, והפגמים שלו —
    מילים מחוברות ומספר הפוך פה ושם — מרוכזים בכותרת העמוד הראשון. הפרומפט
    של הניתוח אומר זאת במפורש ומפנה את המספרים לתקציר ה-HTML.
    """
    from pypdf import PdfReader
    data = _fetch(url, "application/pdf,*/*;q=0.8", tries=3, timeout=90, limit=PDF_MAX_BYTES)
    if not data.startswith(b"%PDF"):
        raise RuntimeError("הקובץ אינו PDF — כנראה דף חסימה")
    parts = []
    for page in PdfReader(io.BytesIO(data)).pages[:PDF_MAX_PAGES]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — עמוד פגום אחד אינו מפיל את ההודעה
            continue
    t = "\n".join(parts).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# --------------------------------------------------------------------------
# עיבוד

class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "table", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.links: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag in ("td", "th"):
            self.out.append(" | ")
        if tag == "a":
            href = (dict(attrs).get("href") or "").strip()
            if re.search(r"\.(pdf|xlsx?|docx?|csv)(\?|$)", href, re.I):
                self.links.append(urllib.parse.urljoin(SITE, href))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def to_text(markup: str | None) -> tuple[str, list[str]]:
    if not markup:
        return "", []
    p = _Text()
    p.feed(markup)
    p.close()
    t = "".join(p.out).replace("​", "").replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t, list(dict.fromkeys(p.links))


def labels(v) -> list[str]:
    if isinstance(v, list):
        return [x["Label"] for x in v if isinstance(x, dict) and x.get("Label")]
    return []


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Jerusalem")
    except Exception:  # noqa: BLE001 — Windows בלי tzdata
        return timezone(timedelta(hours=3))


IL = _tz()


def local_date(iso: str | None) -> str | None:
    """תאריך מקומי. הלמ"ס שומרת תאריך כחצות מקומית ב-UTC — 21:00Z של היום הקודם."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IL).date().isoformat()
    except ValueError:
        return None


def local_dt(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IL).isoformat(timespec="minutes")
    except ValueError:
        return None


def classify(subjects: list[str], title: str) -> tuple[str, bool]:
    text = " ".join(subjects) + " " + title
    topic = next((k for k, _, keys in TOPICS if any(w in text for w in keys)), "other")
    relevant = topic != "other" and not any(w in title for w in EXCLUDE_TITLE)
    return topic, relevant


def _words(s: str) -> set[str]:
    return {w for w in re.split(r"[^\w]+", s or "") if len(w) >= 3}


# --------------------------------------------------------------------------
# משיכה

def pull_releases(cache: dict[str, dict]) -> tuple[list[dict], list[str]]:
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    out: list[dict] = []
    pdf_errors: list[str] = []
    for key, web in WEBS:
        rows = sp_items(web, "דפים", {
            "$select": ("Id,Title,FileRef,ArticleStartDate,CbsDataPublishDate,CbsMMDSubjects,"
                        "CbsMMDInterval,CbsPubNumber,CbsPageSummary,PublishingPageContent,Modified"),
            "$filter": f"ArticleStartDate ge datetime'{since}'",
            "$orderby": "ArticleStartDate desc",
            "$top": "80",
        })
        for r in rows:
            title = (r.get("Title") or "").strip()
            ref = r.get("FileRef") or ""
            if not title or "/Pages/" not in ref or ref.lower().endswith("default.aspx"):
                continue
            subjects = labels(r.get("CbsMMDSubjects"))
            summary, s_links = to_text(r.get("CbsPageSummary"))
            page, p_links = to_text(r.get("PublishingPageContent"))
            topic, relevant = classify(subjects, title)
            interval = labels(r.get("CbsMMDInterval"))
            rec = {
                "id": f"{key}-{r['Id']}",
                "title": title,
                "url": SITE + urllib.parse.quote(ref),
                "date": local_date(r.get("ArticleStartDate")),
                "published": local_dt(r.get("CbsDataPublishDate")),
                "interval": interval[0] if interval else "",
                "subjects": subjects,
                "topic": topic,
                "topic_label": TOPIC_LABELS[topic],
                "relevant": relevant,
                "pub_number": r.get("CbsPubNumber") or "",
                "summary": summary,
                "attachments": list(dict.fromkeys(s_links + p_links))[:15],
                "modified": r.get("Modified"),
                "body": "", "body_source": "", "body_truncated": False,
            }
            if len(page) > 200:
                rec.update(body=page[:BODY_MAX], body_source="page", body_truncated=len(page) > BODY_MAX)
            elif relevant:
                old = cache.get(rec["id"])
                if old and old.get("modified") == rec["modified"] and old.get("body"):
                    # אותה גרסה של ההודעה — ה-PDF כבר נקרא. לא מורידים שוב.
                    rec.update(body=old["body"], body_source=old.get("body_source") or "pdf",
                               body_truncated=bool(old.get("body_truncated")))
                else:
                    pdf = next((u for u in rec["attachments"]
                                if re.search(r"\.pdf(\?|$)", u, re.I)), None)
                    if pdf:
                        try:
                            text = pdf_text(pdf)
                            rec.update(body=text[:BODY_MAX], body_source="pdf",
                                       body_truncated=len(text) > BODY_MAX)
                        except Exception as e:  # noqa: BLE001
                            pdf_errors.append(f"{title[:45]}: {type(e).__name__}: {str(e)[:90]}")
            out.append(rec)
    return out, pdf_errors


def pull_calendar() -> list[dict]:
    today = datetime.now(IL).date()
    a = (today - timedelta(days=CAL_BACK_DAYS + 1)).strftime("%Y-%m-%dT00:00:00Z")
    b = (today + timedelta(days=CAL_AHEAD_DAYS + 1)).strftime("%Y-%m-%dT00:00:00Z")
    fields = ("Id,Title,CbsDateField,CbsMMDInterval,CbsMMDArticleType,CbsMMDSubjects,"
              "CbsForecast_IsSpecial,CbsDataPublishDate")
    try:
        rows = sp_items("/he", "למס - תחזיות פרסום", {
            "$select": fields,
            "$filter": f"CbsDateField ge datetime'{a}' and CbsDateField le datetime'{b}'",
            "$orderby": "CbsDateField asc", "$top": "400"})
    except urllib.error.HTTPError as e:
        # **רשימה של 21 אלף פריטים.** סינון על עמודה שאינה מאונדקסת עלול
        # לחצות את סף התצוגה של SharePoint; הפריטים של השבועות הקרובים הם
        # גם האחרונים שנערכו, ולכן מסננים אותם כאן אחרי משיכה לפי Modified.
        print(f"  לוח הפרסומים: סינון בצד השרת נכשל ({e.code}) — ממיינים לפי Modified",
              file=sys.stderr)
        rows = sp_items("/he", "למס - תחזיות פרסום", {
            "$select": fields, "$orderby": "Modified desc", "$top": "1500"})
    lo = (today - timedelta(days=CAL_BACK_DAYS)).isoformat()
    hi = (today + timedelta(days=CAL_AHEAD_DAYS)).isoformat()
    out = []
    for r in rows:
        d = local_date(r.get("CbsDateField"))
        title = (r.get("Title") or "").strip()
        if not d or not title or not (lo <= d <= hi):
            continue
        subjects = labels(r.get("CbsMMDSubjects"))
        topic, relevant = classify(subjects, title)
        interval = labels(r.get("CbsMMDInterval"))
        out.append({
            "id": int(r["Id"]), "title": title, "date": d,
            "time": (local_dt(r.get("CbsDataPublishDate")) or "")[11:16] or None,
            "interval": interval[0] if interval else "",
            "type": (labels(r.get("CbsMMDArticleType")) or [""])[0],
            "subjects": subjects, "topic": topic, "topic_label": TOPIC_LABELS[topic],
            "relevant": relevant,
        })
    out.sort(key=lambda x: (x["date"], x["time"] or "", x["title"]))
    return out


def pull_indicators() -> list[dict]:
    rows = sp_items("/he", "למס - מדדים ואינדיקטורים", {
        "$select": ("Id,Title,CbsIndicatorsUnit,CbsIndicatorsLastValue,"
                    "CbsIndicatorsPreviousLastValue,CbsLastUpdate,CbsIndicatorsSerie,HoverTooltip,"
                    "CbsIndicatorsTooltipContent,CbsIndicatorsMOBILE_Category,"
                    "CbsIndicators_IsIndicator,eWaveListOrderValue"),
        "$top": "80"})
    out = []
    for r in rows:
        if r.get("CbsIndicators_IsIndicator") is False:
            continue
        explain, _ = to_text(r.get("CbsIndicatorsTooltipContent"))
        out.append({
            "id": int(r["Id"]),
            "title": (r.get("Title") or "").strip(),
            "unit": (r.get("CbsIndicatorsUnit") or "").strip(),
            "value": r.get("CbsIndicatorsLastValue"),
            "previous": r.get("CbsIndicatorsPreviousLastValue"),
            "period": local_date(r.get("CbsLastUpdate")),
            "series": r.get("CbsIndicatorsSerie"),
            "label": (r.get("HoverTooltip") or "").strip(),
            "explain": explain[:600],
            "category": (r.get("CbsIndicatorsMOBILE_Category") or "").strip(),
            "order": r.get("eWaveListOrderValue") or 999,
        })
    out.sort(key=lambda x: (x["order"], x["title"]))
    return out


def pull_price_series() -> dict:
    out = {}
    for code, name in PRICE_SERIES.items():
        d = _get_json(f"https://api.cbs.gov.il/index/data/price?id={code}"
                      "&format=json&download=false&last=25")
        months = (d or {}).get("month") or []
        pts = []
        for e in (months[0].get("date") or []) if months else []:
            base = e.get("currBase") or {}
            if e.get("year") and e.get("month") and base.get("value") is not None:
                pts.append({"period": f"{e['year']}-{int(e['month']):02d}",
                            "value": base.get("value"), "base": base.get("baseDesc"),
                            "m": e.get("percent"), "y": e.get("percentYear")})
        pts.sort(key=lambda p: p["period"])
        out[str(code)] = {"name": name, "points": pts}
    return out


# --------------------------------------------------------------------------
# כתיבה

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def _write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def stored_releases() -> dict[str, dict]:
    out = {}
    for p in (OUT / "releases").glob("*.jsonl"):
        for r in _read_jsonl(p):
            out[str(r["id"])] = r
    return out


def analyzed_ids() -> set[str]:
    ids = set()
    for p in (OUT / "analyses").glob("*.jsonl"):
        for r in _read_jsonl(p):
            if r.get("release_id") is not None:
                ids.add(str(r["release_id"]))
    return ids


def upsert_releases(fresh: list[dict]) -> int:
    """מעדכן את קובצי ההודעות לפי שנה. מחזיר כמה שורות השתנו או נוספו."""
    by_year: dict[str, list[dict]] = {}
    for r in fresh:
        by_year.setdefault((r.get("date") or "0000")[:4], []).append(r)
    changed = 0
    for year, rows in by_year.items():
        p = OUT / "releases" / f"{year}.jsonl"
        cur = {str(r["id"]): r for r in _read_jsonl(p)}
        for r in rows:
            if cur.get(r["id"]) != r:
                changed += 1
                cur[r["id"]] = r
        _write_jsonl(p, sorted(cur.values(),
                               key=lambda r: (r.get("date") or "", r.get("published") or "", str(r["id"])),
                               reverse=True))
    return changed


def main() -> int:
    harden()
    OUT.mkdir(parents=True, exist_ok=True)
    errors: dict[str, str] = {}

    def attempt(name, fn, default):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — כל מקור נכשל לחוד, והשאר ממשיכים
            errors[name] = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"::warning title=הלמ\"ס: {name} נכשל::{errors[name]}")
            return default

    pulled = attempt("הודעות לתקשורת", lambda: pull_releases(stored_releases()), None)
    releases, pdf_errors = pulled if pulled is not None else (None, [])
    calendar = attempt("לוח פרסומים", pull_calendar, None)
    indicators = attempt("מדדים ואינדיקטורים", pull_indicators, None)
    series = attempt("סדרות מדדי מחירים", pull_price_series, None)

    if releases is None and calendar is None and indicators is None and series is None:
        print("::error title=הלמ\"ס לא זמין::כל המקורות נכשלו. אם השגיאה היא "
              "RemoteDisconnected, בדוק שה-User-Agent עדיין נשלח כדפדפן מלא.")
        return 1
    if pdf_errors:
        # הודעה בלי גוף עדיין מנותחת מהתקציר, אבל בעומק נמוך יותר — וזה נאמר.
        print("::warning title=קובצי PDF של הלמ\"ס שלא נקראו::" + " · ".join(pdf_errors[:5]))

    changed_rows = upsert_releases(releases) if releases is not None else 0

    snap_path = OUT / "snapshot.json"
    prev = {}
    if snap_path.exists():
        try:
            prev = json.loads(snap_path.read_text(encoding="utf-8"))
        except ValueError:
            prev = {}
    now = datetime.now(IL).isoformat(timespec="minutes")
    # מקור שנכשל אינו מוחק את מה שנמשך בהצלחה בריצה קודמת: עדיף לוח פרסומים
    # של הבוקר על עמוד ריק. מועד המשיכה נשמר לכל מקור בנפרד.
    snap = {
        "fetched_at": now,
        "calendar": calendar if calendar is not None else prev.get("calendar", []),
        "indicators": indicators if indicators is not None else prev.get("indicators", []),
        "series": series if series is not None else prev.get("series", {}),
        "source_at": {
            k: (now if v is not None else (prev.get("source_at") or {}).get(k))
            for k, v in (("calendar", calendar), ("indicators", indicators), ("series", series),
                         ("releases", releases))},
        "errors": errors,
    }
    body_changed = any(snap[k] != prev.get(k) for k in ("calendar", "indicators", "series"))
    snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    # **פרסום שבלוח ואינו ברשימות הוא אתר-משנה שאינו נסרק.** כך בדיוק נמצא
    # ש-madad נפרד מ-mediarelease: מדד המחירים לצרכן הופיע בלוח ולא ברשימה.
    # נבדק רק על אתמול — פרסום של היום עשוי עוד לא לצאת בשעת הריצה.
    if releases is not None and calendar is not None:
        yday = (datetime.now(IL).date() - timedelta(days=1)).isoformat()
        titles = [_words(r["title"]) for r in releases]
        missing = []
        for c in calendar:
            if not c["relevant"] or c["date"] != yday:
                continue
            cw = _words(c["title"])
            if not any(len(cw & t) / max(1, len(cw | t)) >= 0.5 for t in titles):
                missing.append(c["title"][:60])
        if missing:
            print("::warning title=פרסומים מהלוח שלא נמצאו ברשימות ההודעות::"
                  + " · ".join(missing[:6])
                  + " — ייתכן שהלמ\"ס מפרסמת אותם באתר-משנה שאינו נסרק.")

    done = analyzed_ids()
    everything = stored_releases()
    pending = [r for r in everything.values() if r.get("relevant") and str(r["id"]) not in done]
    changed = body_changed or changed_rows > 0

    n_rel = len(releases) if releases is not None else 0
    n_ok = sum(1 for r in (releases or []) if r["relevant"])
    n_pdf = sum(1 for r in (releases or []) if r.get("body_source") == "pdf")
    print(f"::notice::הלמ\"ס: {n_rel} הודעות ב-{LOOKBACK_DAYS} ימים ({n_ok} רלוונטיות, "
          f"{n_pdf} עם גוף מ-PDF), {changed_rows} חדשות או מעודכנות · {len(pending)} ממתינות "
          f"לניתוח · לוח פרסומים {len(snap['calendar'])} · מדדים {len(snap['indicators'])} · "
          f"סדרות {len(snap['series'])}")

    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"new={'yes' if pending else 'no'}\n")
            f.write(f"changed={'yes' if changed else 'no'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
