# -*- coding: utf-8 -*-
"""אבחון הגישה המזוהה לגלובס, להרצה ב-Actions עם הסוד.

מטרתו לומר בדיוק **מה** חוזר כשהעוגייה בתוקף, כדי שהפרסר ייכתב מול
מבנה אמיתי ולא מול ניחוש. ריצה אחת כאן חוסכת כמה סבבים של פרסר שנכתב
בעיוורון ונשבר.

**ערך העוגייה לעולם אינו מודפס.** מודפסים שמות העוגיות בלבד ואורכן —
די כדי לאבחן "העוגייה פגה" ולא די כדי לדלוף. הלוגים של הריפו ציבוריים.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from _tls import harden  # noqa: E402

harden()

from _globes import (ARTICLE, PAYWALL, NoCookie, cookie_from_env,  # noqa: E402
                     session)

DID = os.environ.get("GLOBES_PROBE") or "1001553326"


def main() -> int:
    try:
        cookie = cookie_from_env()
    except NoCookie as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1

    names = sorted({p.split("=", 1)[0].strip() for p in cookie.split(";") if "=" in p})
    print(f"עוגייה: {len(names)} שדות, {len(cookie)} תווים")
    print(f"  שמות: {', '.join(names)}")

    s = session(cookie)
    r = s.get(ARTICLE.format(DID), timeout=60)
    html = r.text
    print(f"\nכתבה {DID}: HTTP {r.status_code} | {len(html):,} תווים")

    m = re.search(r"<title>(.*?)</title>", html, re.S)
    print("כותרת:", (m.group(1).strip() if m else "—")[:100])

    hits = [p for p in PAYWALL if p in html]
    print("סימני חסימה:", hits or "אין ✓")

    # אילו בלוקים מחזיקים טקסט רץ, וכיצד הם מסומנים — זה מה שהפרסר צריך
    print("\nהבלוקים העשירים בטקסט:")
    seen = []
    for m2 in re.finditer(r'<div([^>]*)>(.*?)</div>', html, re.S):
        attrs, inner = m2.group(1), m2.group(2)
        txt = re.sub(r"<[^>]+>", " ", inner)
        txt = re.sub(r"\s+", " ", txt).strip()
        if len(txt) > 500:
            cls = re.search(r'class="([^"]*)"', attrs)
            idd = re.search(r'id="([^"]*)"', attrs)
            seen.append((len(txt), (cls.group(1) if cls else "")[:70],
                         (idd.group(1) if idd else "")[:40], txt[:110]))
    seen.sort(reverse=True)
    for n, cls, idd, sample in seen[:6]:
        print(f"  {n:>6} תווים | class={cls!r} id={idd!r}")
        print(f"         {sample}")

    if not seen:
        print("  אין בלוק עם טקסט רץ — כנראה עדיין חסום")

    # האם יש שאלות ותשובות, שזה עיקר הערך
    for k in ("שאלות ותשובות", "שאלה", "אנליסט", "מנכ\"ל", "סמנכ\"ל"):
        print(f"  אזכורי {k!r}: {html.count(k)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
