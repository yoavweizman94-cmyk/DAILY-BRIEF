# -*- coding: utf-8 -*-
"""חילוץ טקסט קריא מ-HTML (ניוזלטרים, גוף כתבות) — stdlib בלבד."""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table",
               "section", "article", "blockquote"}
_SKIP_TAGS = {"script", "style", "head", "title", "template"}


def _chars(*cps: int | tuple[int, int]) -> str:
    """התווים עצמם מנקודות קוד; זוג הוא טווח סגור.

    נקודות קוד ולא escape: Write ו-heredoc ממירים רצף backslash-u לתו עצמו, ואז
    התו שנועד להימחק יושב בקוד בלתי נראה — כך נכתב MAIL_INVIS ב-analyze_impact."""
    out = []
    for c in cps:
        lo, hi = c if isinstance(c, tuple) else (c, c)
        out.extend(map(chr, range(lo, hi + 1)))
    return "".join(out)


# **תווים בלתי נראים נמחקים לפני החיתוך ב-max_chars.** Bloomberg ו-FT מרפדים את
# התקציר שתיבת הדואר מציגה בתווי ZWNJ (U+200C) מופרדים ברווחים, ובגרסאות אחרות
# של אותו טריק גם CGJ (U+034F), BOM (U+FEFF) ומילויי הנגול. הם שרדו את כיווץ
# הרווחים ונספרו בתקציב. נמדד 06/11/2026 על 20 ניוזלטרים: בכל גוף של Bloomberg
# 250 תווי ZWNJ — ריצה של כ-505 תווים מיד אחרי שורת הפתיחה; ב-FT עד 3,600.
# הסט: תווי עיצוב ומילויים שאין להם תפקיד בעברית או באנגלית. ZWJ מחבר גם
# אמוג'י מורכב, ובלעדיו הוא מתפרק לרכיביו — זה המחיר.
INVISIBLE = _chars(0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180E,
                   (0x200B, 0x200D), (0x2060, 0x2064), (0x206A, 0x206F),
                   0x3164, 0xFEFF, 0xFFA0)
# **סימני כיווניות — רק ב-strip_bidi=True.** LRM/RLM (U+200E/U+200F), הטבעה
# ועקיפה (U+202A–U+202E), בידוד (U+2066–U+2069). כותרות שעוברות כאן מוצגות
# באתר כמות שהן — עמודי הנושאים (rss_pull דרך publish_news) ו-auto.html
# (auto_pull) — ובשורה עברית הסימנים האלה קובעים איפה נופלים אחוז, סוגריים
# ומונח לועזי. בטקסט שמגיע רק למודל הם רעש.
BIDI = _chars(0x200E, 0x200F, (0x202A, 0x202E), (0x2066, 0x2069))
_DROP = str.maketrans("", "", INVISIBLE)
_DROP_BIDI = str.maketrans("", "", INVISIBLE + BIDI)
_LINE_BREAK = re.compile(r"\r\n?|[" + _chars(0x2028, 0x2029) + "]")

# **קישורי מעקב — רק ב-drop_urls=True.** בגרסת הטקסט של ניוזלטר כל קישור עובר
# דרך שרת המעקב של שירות ההפצה (click.e.economist.com, link.<אתר>.com/click/...),
# 80–570 תווים לקישור. נמדד 06/11/2026: 80% מגוף ניוזלטר של FT ו-44% מזה של
# The Economist היו קישורים כאלה. הכתובת אינה מקור שאפשר לצטט — היא עוברת דרך
# המנוי של יואב ופגה. קישור קנוני וקצר (stratechery.com/2026/..., maya.tase.co.il)
# נשאר: הוא כן מקור.
_URL = re.compile(r'[<(\[]?(?:https?://|www\.)[^\s<>"\])]+[>)\]]?', re.I)
_TRACK_HOST = re.compile(r"(?:links?|clicks?|emails?|trk|track|tracking|lnk)\.", re.I)
_TRACK_PATH = re.compile(r"(?:clicks?|ls|wf|track|trk|redirect|e3t)\b", re.I)
_TRACK_LEN = 150      # מעל זה — אסימון מקודד של הפניה; קישור קנוני כמעט אף פעם לא


def _tracking(m: re.Match) -> str:
    url = m.group(0).strip("<>()[]")
    host, _, path = url.split("://", 1)[-1].partition("/")
    if len(url) > _TRACK_LEN or _TRACK_HOST.match(host) or _TRACK_PATH.match(path):
        return " "
    return m.group(0)


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def clean_html(html: str, max_chars: int = 8000, *, strip_bidi: bool = False,
               drop_urls: bool = False) -> str:
    """טקסט קריא, שורה לכל בלוק, עד max_chars תווים.

    כל הניקוי נעשה לפני החיתוך, כדי שהתקציב ייספר על טקסט ולא על ריפוד.
    strip_bidi — גם סימני הכיווניות (BIDI); רק לטקסט שמגיע למודל ואינו מוצג.
    drop_urls — גם קישורי מעקב גלויים בטקסט (_tracking); קישור קנוני נשאר.
    """
    if not html:
        return ""
    if "<" not in html:                       # כבר טקסט חלק
        text = unescape(html)
    else:
        ex = _Extractor()
        try:
            ex.feed(html)
            ex.close()
        except Exception:
            text = unescape(re.sub(r"<[^>]+>", " ", html))
        else:
            text = "".join(ex.parts)
    text = text.translate(_DROP_BIDI if strip_bidi else _DROP)
    if drop_urls:
        text = _URL.sub(_tracking, text)
    text = _LINE_BREAK.sub("\n", text)
    text = re.sub(r"[^\S\n]+", " ", text)     # כל רווח אופקי (NBSP, U+2007, טאב) — לרווח אחד
    text = re.sub(r" ?\n[ \n]*", "\n", text).strip()   # בלי שורות ריקות ובלי רווח בקצה שורה
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " […]"
    return text
