# -*- coding: utf-8 -*-
"""ייצוא לתמונה ותקציר לציוץ — לעמודי הסחורות והרכב.

אותו מנוע כמו בעמוד העסקאות מחוץ לבורסה (site/export_card.js): הכפתור מצייר
כרטיס ממטען JSON שמוטמע בעמוד, ולא מגרד את ה-DOM, ולכן התמונה אינה תלויה בעיצוב
העמוד או ברוחב המסך. כאן — מה שמשותף לשני העמודים: כפתורים, מטען, תקציר לציוץ
ושורת מקורות.

**התקציר לציוץ נבנה מהמספרים, לא מהסקירה.** שורת הפתיחה היא כותרת הסעיף, שכבר
עברה את הניקוי של הסקירה; כל מספר אחריה נלקח ישירות מהנתונים, כך שאין בציוץ
מספר שאינו בעמוד. שינוי נכתב בחץ (▲ / ▼) ולא בסימן: "+1.1%" בתוך טקסט עברי
מוצג "1.1%+".

**האורך נספר כמו שטוויטר סופר.** עברית נספרת כתו אחד, אבל חץ, ₪, € ומינוס
טיפוגרפי נספרים כשניים, וקישור כ-23 בלי קשר לאורכו. ספירה ב-len() הייתה
מאשרת ציוץ שטוויטר חותך.

**שורת המקור נכנסת תמיד.** היא נכתבת לפני שנבחרות שורות הנתונים, והן אלה
שמתקצרות כשאין מקום.
"""
from __future__ import annotations

import re
from html import escape

import otc

SITE = "tlvtaseview.com"
LIMIT = 280
URL_WEIGHT = 23
DISCLAIMER = "ניתוח השפעה, לא המלצת השקעה."


def weighted_len(text: str) -> int:
    """אורך ציוץ לפי twitter-text v3: משקל 1 לטווחים הלטיניים והעבריים, 2 לכל
    השאר, וקישור 23."""
    n = 0
    for part in re.split(r"(https?://\S+|\b" + re.escape(SITE) + r"\S*)", text):
        if not part:
            continue
        if part.startswith("http") or part.startswith(SITE):
            n += URL_WEIGHT
            continue
        for ch in part:
            o = ord(ch)
            light = (o <= 0x10FF or 0x2000 <= o <= 0x200D or 0x2010 <= o <= 0x201F
                     or 0x2032 <= o <= 0x2037)
            n += 1 if light else 2
    return n


def maqaf(text: str) -> str:
    """"ל-100" → "ל־100": מקף אחרי אות שימוש הוא תו ניטרלי, והמספר אחריו עלול
    לנדוד לצד השני בתצוגה. המקף העברי הוא אות עברית, והמספר נשאר במקומו."""
    return re.sub(r"([\u05D0-\u05EA])-(?=\d)", "\\1\u05BE", text or "")


def lead(text, limit: int = 110) -> str:
    """שורת פתיחה לציוץ מכותרת הסקירה: עד הפסיק הראשון, ואם ארוכה — עד גבול מילה."""
    first = re.split(r",\s|;\s|\s[—–]\s|\s-\s", plain(text))[0]
    if len(first) <= limit:
        return first
    return first[:limit].rsplit(" ", 1)[0] + "…"


def tweet(head: str, lines: list[str], source: str) -> str:
    """פתיחה, שורות נתונים כל עוד יש מקום, מקור וקישור — עד 280 בספירת טוויטר."""
    tail = f"{source}\n{SITE}" if source else SITE
    head = maqaf(" ".join((head or "").split()))
    lines = [maqaf(ln) for ln in lines]
    # פתיחה ארוכה מדי נחתכת במילה, והחיתוך אומר שהוא חיתוך.
    while head and weighted_len(f"{head}\n{tail}") > LIMIT:
        head = head.rsplit(" ", 1)[0].rstrip(",:;—-") + "…" if " " in head else ""
    out = head
    for ln in lines:
        ln = " ".join((ln or "").split())
        if not ln:
            continue
        cand = f"{out}\n{ln}" if out else ln
        if weighted_len(f"{cand}\n{tail}") <= LIMIT:
            out = cand
    return f"{out}\n{tail}" if out else tail


def arrow(v, digits: int = 1) -> str:
    """"▲1.1%" / "▼6.7%" — לציוץ ולשורות הקשר בתמונה."""
    if v is None:
        return "—"
    if abs(v) < 0.5 * 10 ** -digits:
        return f"{0:.{digits}f}%"
    return f"{'▲' if v > 0 else '▼'}{abs(v):.{digits}f}%"


def signed(v, digits: int = 1) -> str:
    """"+1.1%" / "−6.7%" — לתאי טבלה בתמונה, שהמנוע צובע לפי הסימן ומצייר LTR."""
    if v is None:
        return "—"
    if abs(v) < 0.5 * 10 ** -digits:
        return f"{0:.{digits}f}%"
    return f"{'+' if v > 0 else '−'}{abs(v):.{digits}f}%"


def plain(text) -> str:
    """טקסט סקירה לתמונה: בלי הדגשות markdown ובלי רווחים כפולים."""
    return " ".join(str(text or "").replace("**", "").split())


def sentences(text) -> list[str]:
    """פסקת סקירה למשפטים — כל משפט נקודה משלו בגוש ההערות."""
    t = plain(text)
    if not t:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[^\s\d])", t) if s.strip()]


def publishers(refs: dict, ids, limit: int = 5) -> list[str]:
    """שמות המקורות של הכותרות שעליהן נשען סעיף, בלי כפילות."""
    out = []
    for i in ids or []:
        name = " ".join(str((refs.get(str(i)) or {}).get("source") or "").split())
        if name and name not in out:
            out.append(name)
    return out[:limit]


def source_line(parts: list[str], lead: str = "מקורות") -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return f"{'מקור' if len(parts) == 1 and lead == 'מקורות' else lead}: " + " · ".join(parts)


def card(kicker: str, title: str, sub: str, blocks: list, source: str, file: str) -> dict:
    return otc.card(title, sub, blocks, file=file, kicker=kicker, source=source)


def controls(key: str, payload: dict, tweet_text: str, label: str = "ייצוא לתמונה") -> str:
    """מטען, כפתור ייצוא, כפתור העתקה, והתקציר עצמו בתוך details סגור.

    התקציר בתוך details ולא גלוי: בעמוד יש כאן עשרה ויותר ייצואים, ותיבת ציוץ
    פתוחה לכל אחד הייתה מכסה את התוכן. כפתור ההעתקה קורא את הטקסט גם כשהוא סגור.
    """
    esc = escape(tweet_text or "", quote=False)
    tw = (f'<details class="sh-tw"><summary>תקציר לציוץ</summary>'
          f'<div class="otc-tweet" id="tw-{key}"><pre>{esc}</pre></div></details>') if tweet_text else ""
    copy = (f'<button type="button" class="otc-copy" data-key="{key}">העתקת התקציר</button>'
            if tweet_text else "")
    return (otc.embed(key, payload)
            + f'<div class="otc-acts sh-acts">{otc.png_button(label, key=key)}{copy}</div>' + tw)


def js() -> str:
    return otc.export_js()
