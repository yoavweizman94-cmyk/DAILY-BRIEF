# -*- coding: utf-8 -*-
"""שליפת גוף דוח ממאיה והפיכתו לטקסט קריא.

הקבצים יושבים על mayafiles.tase.co.il בנתיב יחסי שמופיע ב-attachments של
הדיווח. גרסת ה-htm עדיפה על ה-pdf: היא קלה יותר, והטקסט בה כבר מובנה.
הקידוד אינו עקבי — חלק windows-1255 וחלק utf-8 — ולכן מזהים אותו מה-meta
ולא סומכים על ברירת מחדל.
"""
from __future__ import annotations

import re

FILES_BASE = "https://mayafiles.tase.co.il/"

# מבנה ה-HTML של מגנ"א משתנה בין סוגי הטפסים, ולכן חיתוך לפי אלמנטים אינו
# אמין. במקום זה מסננים ברמת השורה: כותרת הטופס מורכבת משורות קצרות וצפויות
# (מספרי רישום, אסמכתא, שעת שידור, כתובות הרשות והבורסה), והתוכן האמיתי הוא
# מה שנשאר. בלי הסינון הכותרת תופסת את רוב הטקסט הקצר ומטביעה את המהות.
_DROP_EXACT = {
    "false", "true", "פומבי", "(", ")", "לכבוד:", "לכבוד", "-", "·",
    "רשות ניירות ערך", 'הבורסה לניירות ערך בת"א בע"מ',
    "Israel Securities Authority", "Tel Aviv Stock Exchange",
}
_DROP_PREFIX = ("מספר ברשם", "Corporation no", "אסמכתא", "שעת שידור",
                "שודר במגנא", "Reported via MAGNA", "www.isa.gov.il",
                "www.tase.co.il", "סימול:", "Security No")
_ID_LINE = re.compile(r"^[\d\s\-.:/]+$")                 # מספרים, תאריכים, שעות
_REF_LINE = re.compile(r"^\d{4,}-\d{6,}-\d{6,}$")        # 13994-20290921-20280817
_FORM_LINE = re.compile(r"^[תדבחפ]\d{2,3}[א-ת]?$|^[A-Z]\d{3}$")


def strip_boilerplate(text: str) -> str:
    kept = []
    for line in text.splitlines():
        s = line.strip(" ‏‎·")
        if not s or s in _DROP_EXACT or len(s) == 1:
            continue
        if s.startswith(_DROP_PREFIX) or _REF_LINE.match(s) or _FORM_LINE.match(s):
            continue
        if _ID_LINE.match(s) and len(s) <= 12:
            continue
        if s.isascii() and s.isupper() and len(s) <= 40:  # שם החברה באנגלית
            continue
        kept.append(s)
    out, seen = [], set()
    for s in kept:                                        # מגנ"א משכפל שורות
        if s not in seen:
            seen.add(s)
            out.append(s)
    return "\n".join(out)


def decode(raw: bytes) -> str:
    head = raw[:800].decode("latin-1", "replace").lower()
    prefer = ("windows-1255" if "windows-1255" in head
              else "utf-8" if "utf-8" in head else None)
    for enc in ([prefer] if prefer else []) + ["utf-8", "windows-1255", "cp1255"]:
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def pick_attachment(report: dict, kind: str = "htm") -> dict | None:
    atts = report.get("attachments") or []
    wants = ("htm", "html") if kind == "htm" else ("pdf",)
    for want in wants:
        for a in atts:
            if (a.get("fileType") or "").lower().startswith(want) and a.get("url"):
                return a
    return None


MAX_PDF_BYTES = 12_000_000
MAX_PDF_PAGES = 25


def pdf_text(session, url: str) -> str:
    """טקסט מ-PDF מצורף. ב-ת053 ו-ת930 ה-htm הוא דף שער בלבד והמהות כאן."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        raw = session.get(url, timeout=90).content
        if len(raw) > MAX_PDF_BYTES:
            return ""
        import io
        reader = PdfReader(io.BytesIO(raw))
        parts = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return re.sub(r"[ \t]{2,}", " ", "\n".join(parts)).strip()
    except Exception:
        return ""


def fetch_text(session, report: dict, max_chars: int = 12000,
               with_pdf: bool = True) -> tuple[str, str | None]:
    """מחזיר (טקסט, קישור לקובץ).

    ה-htm נותן את הנושא והמסגרת, אבל בטפסים המהותיים (ת053, ת930) הוא דף שער
    בלבד — התוכן שממנו אפשר להסיק משהו יושב ב-PDF המצורף. לכן מחברים את שניהם.
    """
    from _text import clean_html

    htm = pick_attachment(report, "htm")
    pdf = pick_attachment(report, "pdf")
    url = FILES_BASE + (htm or pdf)["url"].lstrip("/") if (htm or pdf) else None
    if not url:
        return "", None

    head = ""
    if htm:
        try:
            raw = session.get(FILES_BASE + htm["url"].lstrip("/"), timeout=40).content
            head = strip_boilerplate(clean_html(decode(raw), max_chars=max_chars * 3))
            head = re.sub(r"[ \t]{2,}", " ", head).strip()
        except Exception:
            head = ""

    body = ""
    if with_pdf and pdf:
        body = pdf_text(session, FILES_BASE + pdf["url"].lstrip("/"))

    if body:
        combined = f"{head[:1500]}\n\n--- גוף הדוח המצורף ---\n{body}"
    else:
        combined = head
    return combined[:max_chars], url
