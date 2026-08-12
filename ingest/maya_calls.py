# -*- coding: utf-8 -*-
"""שיחות ועידה של חברות לסיכום הרבעון: מי, מתי, ואיך נכנסים.

המקור הוא לוח האירועים של מאיה:
    POST /api/v1/corporate-actions/financial-reports-schedule
    {"fromDate": ..., "toDate": ..., "by": "company", "eventTypeId": 1}
(eventTypeId=1 הוא Conference Call; 2 הוא מועד פרסום הדוח עצמו.)

הלוח מחזיר חברה, תאריך ושעה — **אבל לא את קישור הכניסה**. הקישור מתפרסם
בגוף דיווח ה-ת121 שמקושר ברשומה (`reportId`), ושליפתו היא רוב העבודה כאן:

1. ה-HTM לרוב דף שער; אצל חלק מהחברות הקישור בו ואצל אחרות רק ב-PDF המצורף.
2. **חילוץ טקסט מה-PDF קוטע כתובות** — נמדד "https://www.veidan" במקום
   "https://www.veidan-conferencing.com/opc", כי ה-URL נשבר בין שורות. לכן
   הקישורים נלקחים מאנוטציות הקישור של ה-PDF, שבהן הכתובת שלמה.
3. חלק מהמפרסמים מדביקים מ-Outlook, והקישור מגיע עטוף ב-safelinks — נפתח כאן.
4. boilerplate (isa.gov.il, tase.co.il, אתר הבית של החברה) מסונן, ו-file:///
   מושמט לגמרי: בנק לאומי פרסם נתיב מקומי ממחשב הכותב.

חברה שלא פרסמה קישור מסומנת ככזו במפורש. אין לנחש.

פלט: data/raw/<היום>/calls.json (לברייף) + output/calls/upcoming.json (לאתר)
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402

harden()

from _maya_api import MayaSession  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE_OUT = ROOT / "output" / "calls"
CACHE = ROOT / "data" / "calls_links.json"

# ה-API דוחה fromDate בעבר ב-HTTP 400 — נמדד: היום→+92 מחזיר 30 שיחות,
# אתמול→+92 נופל. אין תקרה קדימה (גם +365 עובד). המשמעות: שיחה שהתקיימה
# כבר אינה ניתנת לשליפה, ולכן הרשימה נצברת מקומית ולא נבנית מאפס בכל יום —
# בלי זה מהדורת הבוקר לא הייתה יכולה להזכיר את שיחות אתמול.
AHEAD_DAYS = 180
KEEP_PAST_DAYS = 30       # כמה זמן לשמור שיחות שכבר התקיימו

# מארחי ועידה מוכרים — קישור אצלם הוא כמעט תמיד קישור הכניסה עצמו
HOSTS = ("zoom.us", "veidan-conferencing", "teams.microsoft", "teams.live",
         "webcast", "webinar", "choruscall", "media-server", "gcs-web",
         "streamyard", "kenes", "meetings", "clickmeeting", "livestorm",
         "on24", "brighttalk", "youtube.com/live", "vimeo")
# מופיע בכל דיווח ואינו קשור לשיחה
BOILERPLATE = ("isa.gov.il", "tase.co.il", "magna", "w3.org", "adobe.com",
               "microsoft.com/download", "gov.il")

URL_RE = re.compile(r'https?://[^\s"\'<>)\]]+')


def unwrap(url: str) -> str:
    """פותח עטיפת Outlook SafeLinks. מניף-פיננסים פרסמה כך."""
    if "safelinks.protection.outlook.com" not in url:
        return url
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return urllib.parse.unquote(q.get("url", [url])[0])
    except Exception:
        return url


def clean(url: str) -> str:
    return unwrap(url.rstrip(".,;:)]}'\"").replace("&amp;", "&"))


def block_of(rid: int) -> str:
    lo = (rid - 1) // 1000 * 1000 + 1
    return f"{lo}-{lo + 999}"


def htm_links(session, rid: int) -> list[str]:
    try:
        r = session._s.get(
            f"https://mayafiles.tase.co.il/rhtm/{block_of(rid)}/H{rid}.htm", timeout=60)
        if not r.ok:
            return []
        return [clean(u) for u in URL_RE.findall(r.content.decode("utf-8", "replace"))]
    except Exception:
        return []


def pdf_links(session, rid: int) -> list[str]:
    """מאנוטציות הקישור — הטקסט המחולץ קוטע כתובות ארוכות."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    for suffix in ("-00", "-01"):
        try:
            r = session._s.get(
                f"https://mayafiles.tase.co.il/rpdf/{block_of(rid)}/P{rid}{suffix}.pdf",
                timeout=90)
            if not r.ok:
                continue
            out = []
            for page in PdfReader(io.BytesIO(r.content)).pages[:12]:
                for annot in (page.get("/Annots") or []):
                    try:
                        uri = (annot.get_object().get("/A") or {}).get("/URI")
                        if uri:
                            out.append(clean(str(uri)))
                    except Exception:
                        pass
            if out:
                return out
        except Exception:
            continue
    return []


def is_bare_home(url: str) -> bool:
    """אתר הבית של החברה — נמצא כמעט בכל דיווח ואינו קישור כניסה."""
    try:
        p = urllib.parse.urlparse(url)
        return p.path in ("", "/") and not p.query
    except Exception:
        return False


def pick_link(urls: list[str]) -> dict:
    """מסווג את הקישורים שנמצאו בדיווח לשלוש רמות ודאות.

    שתי רמות ולא אחת, כי המציאות לא בינארית: קמהדע פרסמה קישור אצל שירות
    שאינו ברשימת המארחים המוכרים, ולהחזיר "אין קישור" היה מסתיר קישור אמיתי.
    מנגד, אתר הבית של דיסקונט אינו קישור כניסה ואסור להציגו ככזה.
    """
    seen, cands = set(), []
    for u in urls:
        low = u.lower()
        if not low.startswith("http"):              # file:/// — לאומי פרסמה נתיב מקומי
            continue
        if any(b in low for b in BOILERPLATE):
            continue
        if u not in seen:
            seen.add(u)
            cands.append(u)

    known = [u for u in cands if any(h in u.lower() for h in HOSTS)]
    if known:
        return {"link": known[0], "certain": True, "known": known,
                "others": [u for u in cands if u not in known][:4]}
    probable = [u for u in cands if not is_bare_home(u)]
    # מועמד שאינו אצל מארח מוכר נבדק בפועל לפני שהוא מוצג ככניסה לשיחה:
    # מזרחי טפחות פרסמה כתובת שמחזירה 404, וקישור שבור גרוע מ"לא פורסם
    # קישור". קישור אצל מארח מוכר אינו נבדק — שירותי ההרשמה חוסמים לעיתים
    # בקשות אוטומטיות, ושלילה שם הייתה שגיאה ולא ממצא.
    if len(probable) == 1 and resolves(probable[0]):
        return {"link": probable[0], "certain": False, "known": [],
                "others": [u for u in cands if u != probable[0]][:4]}
    return {"link": None, "certain": False, "known": [], "others": cands[:5]}


def resolves(url: str) -> bool:
    try:
        import requests
        r = requests.head(url, timeout=20, allow_redirects=True)
        if r.status_code >= 400:
            r = requests.get(url, timeout=20, allow_redirects=True, stream=True)
        return r.status_code < 400
    except Exception:
        return False        # ספק שלא נענה אינו קישור שאפשר להציג בברייף


def load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\s*$")


def norm_time(t: str | None) -> str | None:
    """מאיה מחזירה גם '09:30' וגם '08:30 AM' באותו לוח. מאחדים ל-24 שעות."""
    m = _TIME_RE.match(t or "")
    if not m:
        return t
    h, mnt, ampm = int(m.group(1)), m.group(2), (m.group(3) or "").lower()
    if ampm == "pm" and h != 12:
        h += 12
    elif ampm == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mnt}"


def load_previous() -> dict:
    """שיחות שכבר נאספו, לפי מפתח יציב. ה-API אינו מחזיר עבר."""
    try:
        old = json.loads((SITE_OUT / "upcoming.json").read_text(encoding="utf-8"))
        return {f"{c.get('company_id')}|{c.get('date')}|{c.get('time')}": c
                for c in old.get("calls") or []}
    except Exception:
        return {}


def main() -> int:
    today = date.today()
    s = MayaSession()
    body = {"fromDate": today.isoformat(),
            "toDate": (today + timedelta(days=AHEAD_DAYS)).isoformat(),
            "by": "company", "eventTypeId": 1}
    rows = s._post("/api/v1/corporate-actions/financial-reports-schedule", body).json()

    cache = load_cache()          # reportId → {link, others} — חוסך משיכת PDF יומית
    calls, fetched = [], 0
    for r in rows:
        rid = r.get("reportId")
        key = str(rid) if rid else None
        if key and key not in cache:
            cache[key] = pick_link(htm_links(s, rid) + pdf_links(s, rid))
            fetched += 1
        info = cache.get(key or "") or {"link": None, "certain": False,
                                        "known": [], "others": []}
        calls.append({
            "company": r.get("companyName"),
            "company_id": r.get("companyId"),
            "date": (r.get("scheduledDate") or "")[:10],
            "time": norm_time(r.get("scheduledTime")),
            "period": r.get("period"),
            "year": r.get("year"),
            "report_id": rid,
            "report_url": f"https://maya.tase.co.il/he/reports/{rid}" if rid else None,
            "link": info.get("link"),
            "link_certain": bool(info.get("certain")),
            "other_links": info.get("others") or [],
            "_known": info.get("known") or [],
        })

    # שיחה עברית ושיחה אנגלית באותו יום מדווחות בדיווח אחד עם שני קישורים,
    # והלוח אינו אומר איזה שייך לאיזו. בחירת הראשון לשתיהן נותנת קישור שגוי
    # לאחת מהן — גרוע מלא לתת. לכן מסומן כלא-מוכרע ושני הקישורים מוצגים.
    by_report: dict[str, list] = {}
    for c in calls:
        if c["report_id"]:
            by_report.setdefault(str(c["report_id"]), []).append(c)
    for group in by_report.values():
        if len(group) > 1 and len(group[0]["_known"]) > 1:
            for c in group:
                c["ambiguous"] = True
                c["other_links"] = c["_known"] + c["other_links"]
                c["link"] = None
                c["link_certain"] = False
    for c in calls:
        c.setdefault("ambiguous", False)
        c.pop("_known", None)

    # מיזוג עם מה שנאסף קודם: שיחה שהתקיימה נעלמת מה-API, ובלי הצבירה
    # מהדורת הבוקר לא הייתה יכולה להזכיר את שיחות אתמול.
    merged = load_previous()
    for c in calls:
        merged[f"{c['company_id']}|{c['date']}|{c['time']}"] = c
    floor = (today - timedelta(days=KEEP_PAST_DAYS)).isoformat()
    calls = [c for c in merged.values() if (c.get("date") or "") >= floor]
    calls.sort(key=lambda c: (c["date"] or "", c["time"] or "", c["company"] or ""))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    payload = {
        "asof": datetime.now().isoformat(timespec="seconds"),
        "window": {"from": body["fromDate"], "to": body["toDate"]},
        "count": len(calls),
        "with_link": sum(1 for c in calls if c["link"]),
        "calls": calls,
    }
    raw = ROOT / "data" / "raw" / today.isoformat()
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "calls.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    SITE_OUT.mkdir(parents=True, exist_ok=True)
    (SITE_OUT / "upcoming.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    today_n = sum(1 for c in calls if c["date"] == today.isoformat())
    print(f"שיחות ועידה: {len(calls)} בטווח ({today_n} היום), "
          f"{payload['with_link']} עם קישור כניסה, {fetched} דיווחים נמשכו")
    return 0


if __name__ == "__main__":
    sys.exit(main())
