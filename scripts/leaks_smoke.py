# -*- coding: utf-8 -*-
"""בדיקה מקומית לניקוי הדליפות מהצנרת אל המוצר: קישורי Gmail ושמות קבצים בברייף
(normalize_briefs), שורות ניוזלטר בסיווג החדשות (publish_news) ובעמודי הסקטור
(site/build.py). בלי רשת.

    python scripts/leaks_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "ingest"))
import normalize_briefs as N  # noqa: E402
from _text import publisher  # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n     got:  {got!r}\n     want: {want!r}"))
    if not ok:
        FAILS.append(name)


def clean(t: str) -> str:
    return N.leaks(t)[0]


GM = "https://mail.google.com/mail/u/0/#all/1a1e57d9daf901e5"

# --- Gmail -------------------------------------------------------------------
check("קישור Gmail → שם הפרסום", clean(f"([FT/Bloomberg]({GM}); [גלובס](https://www.globes.co.il/x))"),
      "(FT/Bloomberg; [גלובס](https://www.globes.co.il/x))")
check("כתובת Gmail חשופה נמחקת עם הסוגריים", clean(f"לפי Bloomberg ({GM})."), "לפי Bloomberg.")

# --- שמות קבצים ----------------------------------------------------------------
check("גרש הפוך ותחילית", clean("ההחלטה ב-`markets.json` נקבעה"), "ההחלטה במאגר נתוני השוק נקבעה")
check("ה\"א הידיעה נבלעת", clean("וה-`pack/otc.jsonl` ריק"), "ודוח העסקאות מחוץ לבורסה ריק")
check("שם לועזי שומר על המקף", clean("מ-`te.json` (קריאת 12:19)"), "מ-Trading Economics (קריאת 12:19)")
check("נקודה בסוף משפט", clean("נסרקו rss.jsonl ו-pack/impact.jsonl."),
      "נסרקו מאגר פידי החדשות ועמוד ההשפעה על מניות.")
check("נתיב מלא", clean("`data/raw/<היום>/pack/nadlan.json` קפוא"), "מאגר העסקאות של Govmap קפוא")
check("תיקיית הפלט", clean("ב-`output/otc/2026.jsonl`"), "בדוח העסקאות מחוץ לבורסה")
check("שם ברייף", clean("ראו `brief_2026-11-16-close.md`"), "ראו מהדורת הנעילה של 16/11")
check("מודגש", clean("**`pack/jumbo.jsonl` — שלוש עסקאות**"), "**מאגר העסקאות המתואמות (GTO) — שלוש עסקאות**")
check("לא בתוך כתובת", clean("[קובץ](https://example.com/data/te.json)"), "[קובץ](https://example.com/data/te.json)")
check("לא בשם ארוך יותר", clean("markets.json.bak"), "markets.json.bak")
check("שם שדה בגרש הפוך נשאר", clean("`il_gov_10y` עדיין `null`"), "`il_gov_10y` עדיין `null`")
t, n = N.leaks("`foo_bar.json` ריק")
check("קובץ לא מוכר נשאר ונספר", (t, n["unknown"]), ("`foo_bar.json` ריק", 1))
once = clean(f"ב-`markets.json` ו-[Bloomberg]({GM})")
check("אידמפוטנטי", clean(once), once)
_, n = N.leaks("`markets.json`", files=False)
check("files=False אינו נוגע בשמות", (N.leaks("`markets.json`", files=False)[0], n["files"]), ("`markets.json`", 0))

# --- שם הפרסום ----------------------------------------------------------------
check("publisher: דומיין מוכר", publisher("Bloomberg <noreply@news.bloomberg.com>"), "Bloomberg")
check("publisher: שם תצוגה", publisher('gmail:"Desk" <a@b.co.il>'), "Desk")
check("publisher: כתובת בלבד אינה יוצאת", publisher("a@b.co.il"), "ניוזלטר")

# --- publish_news: בלי קישור ובלי כתובת, ובלי מיזוג של כל הניוזלטרים לשורה אחת ----
import publish_news as P  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "config").mkdir()
    (d / "config" / "sources.yaml").write_text(json.dumps(
        {"topics": [{"slug": "macro", "label": "מאקרו", "keywords": ["fed"]}]}), encoding="utf-8")
    day = P.date.today().isoformat()
    raw = d / "data" / "raw" / day
    raw.mkdir(parents=True)
    old = [{"id": f"m{i}", "ts": f"2026-11-17T0{i}:00", "title": f"Fed note {i}",
            "url": f"https://mail.google.com/mail/u/0/#all/{i}abc", "source": "gmail:FT <x@ft.com>"}
           for i in range(3)]
    (d / "output" / "news").mkdir(parents=True)
    (d / "output" / "news" / f"{day}.jsonl").write_text(
        json.dumps(old[0]) + "\n", encoding="utf-8")       # שורה ישנה שכבר בקובץ
    (raw / "gmail.jsonl").write_text("\n".join(json.dumps(r) for r in old), encoding="utf-8")
    P.ROOT = d
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        P.main()
    rows = [json.loads(x) for x in (d / "output" / "news" / f"{day}.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
check("publish_news: שלושה ניוזלטרים, לא אחד", len(rows), 3)
check("publish_news: בלי קישור Gmail", any("mail.google" in (r.get("url") or "") for r in rows), False)
check("publish_news: שם הפרסום בלבד", sorted({r["source"] for r in rows}), ["ניוזלטר: FT"])

# --- site/build.py: שורה ישנה מוצגת בלי קישור ובלי כתובת -------------------------
sys.path.insert(0, str(ROOT / "site"))
import build as B  # noqa: E402
html = B.news_items_html([{"ts": "2026-11-17T08:00", "title": "Fed note",
                           "url": "https://mail.google.com/mail/u/0/#all/abc",
                           "source": "gmail:FT Newswrap <newswrap@ft.com>"}])
check("build: בלי קישור Gmail", "mail.google" in html, False)
check("build: בלי כתובת שולח", "@ft.com" in html, False)
check("build: שם הפרסום מוצג", "ניוזלטר: FT Newswrap" in html, True)

print("הכל עבר" if not FAILS else f"{len(FAILS)} נכשלו")
sys.exit(1 if FAILS else 0)
