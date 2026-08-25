# -*- coding: utf-8 -*-
"""גישה מזוהה לגלובס — חילוץ העוגייה, אימות מנוי ומשיכת כתבה.

**למה cURL ולא מחרוזת עוגייה.** עוגיית ההתחברות מסומנת HttpOnly, ולכן
`document.cookie` בקונסול אינו רואה אותה: המשתמש מקבל מחרוזת שנראית
תקינה ולא עובדת, בלי שום הודעת שגיאה. "Copy as cURL" קורא את כותרת
הבקשה עצמה וכולל אותה. לכן הסוד נשמר כבלוק cURL שלם, והחילוץ נעשה כאן.

**למה בכלל צריך את המנוי.** גלובס שולחת את גוף הכתבה לכל גולש, מוצפן
RC4 עם מפתח שכתוב ב-JS הפומבי שלה; החסימה היא בצד הלקוח בלבד. המפתח
הזה אינו בקרת גישה אלא ערפול, ולכן היכולת לפענח אינה זכאות לקרוא.
המודול מפענח **רק** אחרי שאומת שהתשובה הוחזרה לסשן מחובר — עוגייה
שפגה נכשלת כאן ואינה מידרדרת בשקט לגלישה אנונימית.
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

RC4_KEY = "s@d45f2FTgd76f#Rd!"

# סימנים שמופיעים רק בסשן מחובר. נמדדו מול משיכה אנונימית של אותה
# כתבה: "התחבר" הופיע פעם אחת, וכל אלה — אפס.
SIGNED_IN = ("התנתק", "החשבון שלי", "logout", "signout")


class NoCookie(Exception):
    """הסוד חסר או שלא נמצאה בו עוגייה."""


class NotSubscriber(Exception):
    """הבקשה עברה אך הוחזרה לסשן שאינו מחובר."""


class Paywalled(Exception):
    """הסשן תקין אך לא נמצא גוף כתבה."""


def rc4(key: str, data: str) -> str:
    ks = [ord(c) for c in key]
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + ks[i % len(ks)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out, i, j = [], 0, 0
    for ch in data:
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(chr(ord(ch) ^ S[(S[i] + S[j]) & 0xFF]))
    return "".join(out)


def is_subscriber(html: str) -> bool:
    """האם התשובה הוחזרה לסשן מחובר.

    **התנאי לפענוח, ולא קישוט.** בלעדיה הקוד היה קורא תוכן חסום גם בלי
    מנוי, וזה בדיוק מה שהוחלט לא לעשות.
    """
    return any(k in html for k in SIGNED_IN)


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
            return re.sub(r"\s*\\s*\n\s*", "", m.group(1)).strip()

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


def clean_html(frag: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", frag, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&quot;", '"').replace("&amp;", "&")
    t = t.replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def article_text(html: str) -> tuple[str, str]:
    """(כותרת, גוף) מתוך HTML של כתבה שהוחזרה לסשן מנוי."""
    if not is_subscriber(html):
        raise NotSubscriber("הסשן אינו מחובר — כנראה שהעוגייה פגה. "
                            "רענן את GLOBES_COOKIE מהדפדפן.")

    m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"\s*-\s*גלובס\s*$", "", (m.group(1) if m else "").strip())

    # הגוף מגיע ב-textEnv מוצפן, ולא ב-HTML. הדפדפן מפענח ומזריק
    # ל-.articleInner; כאן נעשה אותו דבר, אחרי שאומת שהסשן זכאי.
    m2 = re.search(r"textEnv\s*=\s*[\"']([^\"']*)[\"']", html)
    if m2 and m2.group(1):
        txt = clean_html(rc4(RC4_KEY, m2.group(1)))
        if len(txt) > 500:
            return title, txt

    # נפילה חלופית: כתבה חופשית, שבה הגוף יושב ב-HTML כרגיל.
    body = ""
    chunks = re.findall(
        r'<div[^>]*class="[^"]*(?:article|content|body|text)[^"]*"[^>]*>(.*?)</div>\s*(?=<div|</article|</section)',
        html, re.S | re.I)
    for c in sorted(chunks, key=len, reverse=True):
        txt = clean_html(c)
        if len(txt) > len(body):
            body = txt

    if len(body) < 800:
        raise Paywalled(f"לא נמצא גוף כתבה (אורך {len(body)})")
    return title, body


def fetch(sess, did: str) -> tuple[str, str]:
    r = sess.get(ARTICLE.format(did), timeout=60)
    r.raise_for_status()
    return article_text(r.text)
