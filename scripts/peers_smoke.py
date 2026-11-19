# -*- coding: utf-8 -*-
"""בדיקה מקומית לעמוד המתחרים: קריאת דוח האחזקות, בניית החיפושים, סינון הרעש והרינדור.
בלי רשת ובלי מפתח — נתונים בדויים בלבד.

    python scripts/peers_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "site"))
import analyze_peers as A  # noqa: E402
import fund_holdings as F  # noqa: E402
import peers as P  # noqa: E402
import peers_news as N  # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n     got:  {got!r}\n     want: {want!r}"))
    if not ok:
        FAILS.append(name)


# --- דוח האחזקות -------------------------------------------------------------
H = "\t".join(["מספר קרן", "שם קרן", "שם נכס", "סוג נכס", "מספר מזהה", "סוג מזהה", "כמות", "שווי בשקלים",
               "מחיר", "שווי במטבע מסחר", "%חשיפה", "תאריך דוח"])
rows = ["﻿" + H,
        "111 \t קרן א \tחברה גדולה \t1  \t100  \t1 \t5 \t5 \t1 \t5 \t2.50 \t31082026",
        "111 \t קרן א \tחברה קטנה \t1  \t200  \t1 \t5 \t5 \t1 \t5 \t0.40 \t31082026",
        "111 \t קרן א \tאג\"ח כלשהו \t10 \t300  \t1 \t5 \t5 \t1 \t5 \t9.00 \t31082026",
        "222 \t קרן ב \tחברה אחרת \t1  \t400  \t1 \t5 \t5 \t1 \t5 \t7.00 \t31082026"]
got = F.parse("\n".join(rows), "111")
check("אחזקות: רק מניות של הקרן", [g["security"] for g in got], ["100", "200"])
check("אחזקות: משקל ותאריך", (got[0]["weight"], got[0]["date"]), (2.5, "2026-08-31"))
check("תעשייתית: ענף תעשייה", F.is_industrial("תעשייה-כימיה, גומי ופלסטיק"), True)
check("תעשייתית: ביטחוניות", F.is_industrial("טכנולוגיה-ביטחוניות"), True)
check("תעשייתית: מסחר אינו", F.is_industrial("מסחר ושרותים-מסחר"), False)

# --- חיפושים -------------------------------------------------------------------
cfg = {"holdings": {
    "א": {"terms": ["masterbatch", "שוק היין"], "competitors": [{"name": "Avient", "q": "\"Avient\""},
                                                                {"name": "תוסף", "q": "\"תוסף\"", "il": True}]},
    "ב": {"competitors": [{"name": "Avient", "q": "\"Avient\""}], "customers": [{"name": "P&G"}]}}}
qs = {q["q"]: q for q in N.queries(cfg)}
check("חיפושים: שאילתה משותפת לשתי אחזקות", sorted(t["holding"] for t in qs['"Avient"']["tags"]), ["א", "ב"])
check("חיפושים: עברית לפי il ולפי תווים", (qs['"תוסף"']["hebrew"], qs["שוק היין"]["hebrew"], qs["masterbatch"]["hebrew"]),
      (True, True, False))
check("חיפושים: לקוח בלי q", '"P&G"' in qs and qs['"P&G"']["tags"][0]["kind"] == "customer", True)
check("מזהה: לפי כותרת מנורמלת", N.rid("u1", "Avient  Raises Outlook"), N.rid("u2", "avient raises outlook"))

# --- רעש -------------------------------------------------------------------------
noise = ["Cabot (NYSE:CBT) Shares Gap Up - Here's What Happened", "Fund X acquires new stake in Avient Corp",
         "Masterbatch Market to reach $20 billion by 2032, CAGR 6%"]
real = ["Avient raises full-year outlook on specialty demand", "Suominen to close spunlace line in Italy"]
check("רעש: נתפס", [bool(A.NOISE.search(t)) for t in noise], [True, True, True])
check("רעש: ידיעה עסקית עוברת", [bool(A.NOISE.search(t)) for t in real], [False, False])

# --- רינדור ----------------------------------------------------------------------
d = {"holdings": {"fund": {"name": "קרן בדיקה"}, "report": {"title": "דוח חודשי-אוגוסט 2026", "published": "2026-10-25"},
                  "holdings": [{"name": "א", "weight": 2.5, "tase_sector": "תעשייה-כימיה", "industrial": True},
                               {"name": "ג", "weight": 1.0, "tase_sector": "תעשייה-מזון", "industrial": True}]},
     "peers": {"holdings": {"א": {"competitors": [{"name": "Avient", "src": "דוח עמ' 15", "ticker": "NYSE:AVNT"},
                                                   {"name": "Fitesa", "src": "הצעה"}]}}},
     "cards": [{"holding": "א", "at": "2026-11-19T10:00:00+00:00", "title": "Avient <b>מעלה</b> תחזית",
                "fact": "לפי הכותרת", "sector": "ביקוש", "impact": "מחיר", "meaning": "פרשנות",
                "direction": "חיובי", "basis": "כותרת",
                "sources": [{"id": "x1", "title": "t", "url": "https://e.com/a", "source": "Reuters", "ts": "2026-11-19T09:00:00+00:00"}]}],
     "recent": [], "last_run": "2026-11-19T10:00:00+00:00"}
html = P.index(d)
check("רינדור: אחזקה עם מפה מוצגת", 'data-h="א"' in html, True)
check("רינדור: אחזקה בלי מפה ברשימת החסרות", "בלי מפת מתחרים: ג" in html, True)
check("רינדור: הצעה מסומנת", 'class="peer-chip prop"' in html, True)
check("רינדור: כותרת מוברחת", "&lt;b&gt;מעלה&lt;/b&gt;" in html and "<b>מעלה</b>" not in html, True)
check("רינדור: שורת באחזקה", "<b>באחזקה:</b> מחיר" in html, True)
check("רינדור: לפי כותרות מסומן", "לפי כותרות" in html, True)
d2 = dict(d, peers={"holdings": {**d["peers"]["holdings"], "ד": {"competitors": [{"name": "X", "src": "דוח"}],
                                                              "suppliers": [{"name": "Y", "src": "דוח"}]}}},
          sectors={"ד": "מסחר ושרותים-מסחר"})
h2 = P.index(d2)
check("רינדור: חברה במעקב מחוץ לקרן", "במעקב — לא בדוח האחזקות של הקרן · מסחר ושרותים-מסחר" in h2, True)
check("רינדור: ספקים מהותיים", "<b>ספקים מהותיים:</b>" in h2, True)
qs2 = {q["q"]: q for q in N.queries({"holdings": {"ד": {"suppliers": [{"name": "Y", "q": "\"Y\""}]}}})}
check("חיפושים: ספק", qs2['"Y"']["tags"][0]["kind"], "supplier")
check("רינדור: תווית כפולה מוסרת", P._f({"x": "בענף: בענף: מחיר"}, "x"), "מחיר")
check("רינדור: 'פרשנות:' מוסרת", P._f({"x": "פרשנות: אות"}, "x"), "אות")

print("הכל עבר" if not FAILS else f"{len(FAILS)} נכשלו")
sys.exit(1 if FAILS else 0)
