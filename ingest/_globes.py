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
ACCOUNT = BASE + "/news/personal_zone/manageaccount.aspx"

# הסימנים שגלובס מציג לגולש שאינו מנוי. נוכחותם פירושה שהעוגייה פגה או
# שגויה — ולא שהכתבה ריקה. ההבחנה הזו היא כל ההבדל בין "לתקן את הסוד"
# ל"לחפש באג בפרסר".
PAYWALL = ("למנויים בלבד", "מינוי גלובס בדיגיטל", "להצטרפות למנויים")

RC4_KEY = "s@d45f2FTgd76f#Rd!"

# **שלושה סימנים שנוסו ונפסלו** — נשמרים כתיעוד כדי שלא ינוסו שוב:
#   · מחרוזות תפריט ("התנתק", "החשבון שלי") — עמוד הבית בונה אותן ב-JS,
#     ולכן הן חסרות משתי הצורות. גם "התחבר" מופיע 0 פעמים.
#   · מחרוזות ה-PAYWALL שלמטה — מופיעות גם בכתבה **חופשית** לגמרי.
#   · `IsPaywall` — תכונה של הכתבה ולא של הגולש: חופשית=False,
#     חסומה=True, בשתיהן גם בגלישה אנונימית.
# גוף הכתבה אינו נושא מידע על הזכאות. הזיהוי נבדק ב-`recognized`.


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


def form_shape(html: str) -> dict:
    """טביעת אצבע מבנית של טופס בעמוד — בלי לקרוא את תוכנו."""
    return {
        "password": len(re.findall(r'type="password"', html, re.I)),
        "email": len(re.findall(r'type="email"', html, re.I)),
        "forms": len(re.findall(r"<form", html, re.I)),
        "len": len(html),
    }


EMAILISH = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def skeleton(line: str) -> str:
    """שלד של שורת HTML — שמות תגיות ומאפיינים, בלי ערכים ובלי טקסט.

    **דיווח על הבדלים בלי לדווח מה נמצא שם.** האזור האישי של מנוי
    מחזיק את שמו ואת האימייל שלו, והאנוטציות ציבוריות. השלד אומר
    *היכן* התשובות נבדלות ומספיק כדי לאבחן, ואינו מוציא ערך אחד.
    """
    tags = re.findall(r"<(\w+)([^>]*)>", line)
    out = []
    for tag, attrs in tags[:4]:
        names = re.findall(r"([\w-]+)\s*=", attrs)
        out.append(tag + ("[" + ",".join(names[:4]) + "]" if names else ""))
    return " ".join(out) or "(טקסט בלבד)"


def recognized(sess) -> tuple[bool, list[str]]:
    """האם השרת מזהה את הסשן — נבדק ב-A/B מול אותה בקשה בלי עוגייה.

    **למה A/B ולא חיפוש סימן.** שלוש בדיקות קודמות נכשלו כי כל אחת
    מהן מדדה משהו שאינו הרשאה: מחרוזות תפריט (עמוד הבית בונה אותן
    ב-JS ולכן הן חסרות תמיד), סימני חסימה (מופיעים גם בכתבה חופשית),
    ו-`IsPaywall` (תכונה של הכתבה — חופשית=False, חסומה=True, בשתיהן
    בגלישה אנונימית). גוף הכתבה פשוט אינו נושא מידע על הזכאות.

    מה שכן נושא מידע הוא עמוד שדורש התחברות. אנחנו מבקשים את האזור
    האישי פעמיים — עם העוגייה ובלעדיה — ושואלים אם השרת ענה **אחרת**.

    **ההכרעה היא על הטופס, לא על האורך.** עמוד עם טופס התחברות מלא
    (שדות סיסמה) הוא עמוד של מי שאינו מחובר, גם כשאורכו זז ב-92 תווים
    בגלל טוקן או פרסומת. אורך לבדו סימן "מזוהה" על הפרש רעש.
    """
    from curl_cffi import requests as creq

    ra = sess.get(ACCOUNT, timeout=60)
    a = ra.text
    bare = creq.Session(impersonate="chrome")
    bare.headers.update({"Accept-Language": "he-IL,he;q=0.9", "Referer": BASE + "/"})
    b = bare.get(ACCOUNT, timeout=60).text

    fa, fb = form_shape(a), form_shape(b)
    delta = abs(fa["len"] - fb["len"]) / max(fb["len"], 1)
    ea, eb = len(EMAILISH.findall(a)), len(EMAILISH.findall(b))

    # **ההכרעה: תוכן אישי שמופיע רק כשהעוגייה מוצגת.**
    # ספירת שדות הסיסמה נפסלה כשהתברר שהאזור האישי של מנוי מחזיק טופס
    # החלפת סיסמה — שלושה שדות, בדיוק כמו טופס ההתחברות של האנונימי.
    # כתובת אימייל, לעומת זאת, אינה יכולה להופיע בעמוד של מי שאינו
    # מזוהה: נמדד 0 בגלישה נקייה ו-2 עם עוגייה מחוברת.
    ok = ea > eb or fa["password"] < fb["password"]

    rep = [
        f"אזור אישי עם עוגייה: {fa}",
        f"אזור אישי בלי עוגייה: {fb}",
        f"הפרש אורך יחסי: {delta:.2%}",
        f"מחרוזות דמויות אימייל בתשובה: עם={ea}, בלי={eb}",
        f"Set-Cookie שהשרת החזיר: "
        f"{sorted({c.split('=')[0] for c in ra.headers.get_list('set-cookie')}) if hasattr(ra.headers, 'get_list') else 'לא נקרא'}",
    ]

    # היכן בדיוק נבדלו התשובות — בשלד בלבד, בלי ערכים.
    la, lb = a.splitlines(), b.splitlines()
    only_a = [l for l in la if l not in set(lb) and l.strip()]
    if only_a:
        rep.append(f"שורות שקיימות רק בתשובה עם העוגייה: {len(only_a)}")
        for l in only_a[:6]:
            rep.append(f"    {skeleton(l)[:90]}")

    if ok:
        rep.append("מסקנה: העמוד מציג תוכן אישי רק כשהעוגייה מוצגת — "
                   "הסשן מזוהה.")
    else:
        rep.append("מסקנה: התשובה אינה מציגה תוכן אישי. הסשן אינו מזוהה "
                   "מהראנר.")
    return ok, rep


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


def ua_from_env(var: str = "GLOBES_COOKIE") -> str:
    return extract_header(os.environ.get(var, ""), "user-agent")


def extract_header(blob: str, name: str) -> str:
    """כותרת כלשהי מתוך בלוק ה-cURL, לפי שמה."""
    n = re.escape(name)
    pats = [
        r"-H\s+\$?'" + n + r":\s*(.*?)'",
        r'-H\s+"' + n + r':\s*(.*?)"',
        r'"' + n + r'"\s*=\s*"(.*?)"',
    ]
    for p in pats:
        m = re.search(p, blob or "", re.I | re.S)
        if m and m.group(1).strip():
            return re.sub(r"\s*\\\s*\n\s*", "", m.group(1)).strip()
    return ""


def session(cookie: str, ua: str = ""):
    """חיקוי דפדפן — גלובס מאחורי WAF, כמו שאר המקורות הישראליים.

    **ה-User-Agent נלקח מבלוק ה-cURL כשהוא שם.** סשן שנוצר בדפדפן אחד
    ומושמע מסוכן אחר הוא בדיוק התבנית שמערכות הזדהות חוסמות, ו-curl_cffi
    שולח כברירת מחדל את ה-UA שלו ולא של הדפדפן שהעוגייה נולדה בו.
    ההעתקה של הכותרת עולה כלום ומסלקת סיבת דחייה שלמה.
    """
    from curl_cffi import requests as creq
    s = creq.Session(impersonate="chrome")
    s.headers.update({
        "Cookie": cookie,
        "Accept-Language": "he-IL,he;q=0.9",
        "Referer": BASE + "/",
    })
    if ua:
        s.headers["User-Agent"] = ua
    return s


# **מפרידי שורה של יוניקוד שאינם "\n".** U+2028/2029, NEL וקרובים
# עוברים כלשונם ב-json.dumps(ensure_ascii=False), אבל str.splitlines()
# מפצל עליהם. רשומה שהכילה אחד מהם נשברה לשברים שאינם JSON תקין —
# ומכאן גם קובץ הסיכומים שנקרא כריק, גם התמלולים שלא הופיעו באתר,
# וגם שמונה תמלילים שסוכמו וששולם עליהם פעמיים. הנרמול כאן, במקור,
# מונע את זה מכל צרכן עתידי של הטקסט.
UNI_BREAKS = (" ", " ", "", "\v", "\f",
              "\x1c", "\x1d", "\x1e")


def clean_html(frag: str) -> str:
    t = frag or ""
    for ch in UNI_BREAKS:
        t = t.replace(ch, "\n")
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&quot;", '"').replace("&amp;", "&")
    t = t.replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def article_text(html: str) -> tuple[str, str]:
    """(כותרת, גוף) מתוך HTML של כתבה שהוחזרה לסשן מנוי."""
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
