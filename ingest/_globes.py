# -*- coding: utf-8 -*-
"""גישה מזוהה לגלובס — חילוץ העוגייה ומשיכת כתבה.

**למה cURL ולא מחרוזת עוגייה.** עוגיית ההתחברות מסומנת HttpOnly, ולכן
`document.cookie` בקונסול אינו רואה אותה: המשתמש מקבל מחרוזת שנראית
תקינה ולא עובדת, בלי שום הודעת שגיאה. "Copy as cURL" קורא את כותרת
הבקשה עצמה וכולל אותה. לכן הסוד נשמר כבלוק cURL שלם, והחילוץ נעשה כאן.

הפונקציה מקבלת גם מחרוזת עוגייה נקייה, למי שידע להוציא אותה לבד.
"""
from __future__ import annotations

import os
import re

BASE = "https://www.globes.co.il"
ARTICLE = BASE + "/news/article.aspx?did={}"

# הסימנים שגלובס מציג לגולש שאינו מנוי. נוכחותם פירושה שהעוגייה פגה או
# שגויה — ולא שהכתבה ריקה. ההבחנה הזו היא כל ההבדל בין "לתקן את הסוד"
# ל"לחפש באג בפרסר".
PAYWALL = ("למנויים בלבד", "מינוי גלובס בדיגיטל", "להצטרפות למנויים")


class NoCookie(Exception):
    """הסוד חסר או שלא נמצאה בו עוגייה."""


class Paywalled(Exception):
    """הבקשה עברה אך הוחזר תוכן של לא-מנוי."""


def extract_cookie(blob: str) -> str:
    """מחרוזת העוגייה מתוך בלוק cURL, מ-PowerShell, או מטקסט נקי.

    Chrome פולט שלוש צורות ציטוט לאותה כותרת (`'`, `"`, ו-`$'...'`
    כשיש תווים מיוחדים), ו-PowerShell פולט צורה רביעית. כולן מטופלות,
    כי מי שמדביק אינו אמור לדעת באיזו מהן הדפדפן שלו בחר.
    """
    b = (blob or "").strip()
    if not b:
        raise NoCookie("הסוד ריק")

    pats = [
        r"-H\s+\$?'cookie:\s*(.*?)'",          # -H 'cookie: ...'  /  $'...'
        r'-H\s+"cookie:\s*(.*?)"',             # -H "cookie: ..."
        r'"Cookie"\s*=\s*"(.*?)"',             # PowerShell headers
        r"-b\s+\$?'(.*?)'",                    # -b '...'
        r'-b\s+"(.*?)"',
    ]
    for p in pats:
        m = re.search(p, b, re.I | re.S)
        if m and m.group(1).strip():
            return re.sub(r"\s*\\\s*\n\s*", "", m.group(1)).strip()

    # מחרוזת עוגייה נקייה: זוגות name=value מופרדים בנקודה-פסיק
    if "=" in b and ";" in b and "\n" not in b.strip():
        return b.strip()
    raise NoCookie("לא נמצאה עוגייה בסוד — ודא שהודבק פלט של Copy as cURL (bash)")


def cookie_from_env(var: str = "GLOBES_COOKIE") -> str:
    return extract_cookie(os.environ.get(var, ""))


def session(cookie: str):
    """חיקוי דפדפן — גלובס מאחורי WAF, כמו שאר המקורות הישראליים."""
    from curl_cffi import requests as creq
    s = creq.Session(impersonate="chrome")
    s.headers.update({
        "Cookie": cookie,
        "Accept-Language": "he-IL,he;q=0.9",
        "Referer": BASE + "/",
    })
    return s


def article_text(html: str) -> tuple[str, str]:
    """(כותרת, גוף) מתוך HTML של כתבה. זורק Paywalled כשאין גוף."""
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"\s*-\s*גלובס\s*$", "", (m.group(1) if m else "").strip())

    body = ""
    # גוף הכתבה יושב ב-div של התוכן; שמות המחלקות משתנים, ולכן נלקח
    # הבלוק הארוך ביותר שנראה כמו טקסט רץ.
    chunks = re.findall(
        r'<div[^>]*class="[^"]*(?:article|content|body|text)[^"]*"[^>]*>(.*?)</div>\s*(?=<div|</article|</section)',
        html, re.S | re.I)
    for c in sorted(chunks, key=len, reverse=True):
        txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", c, flags=re.S | re.I)
        txt = re.sub(r"<br\s*/?>|</p>", "\n", txt, flags=re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"&nbsp;?", " ", txt)
        txt = re.sub(r"[ \t]{2,}", " ", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
        if len(txt) > len(body):
            body = txt

    if len(body) < 800 or any(p in html for p in PAYWALL) and len(body) < 3000:
        raise Paywalled(f"הוחזר תוכן של לא-מנוי (גוף באורך {len(body)})")
    return title, body


def fetch(sess, did: str) -> tuple[str, str]:
    r = sess.get(ARTICLE.format(did), timeout=60)
    r.raise_for_status()
    return article_text(r.text)
