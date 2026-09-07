# -*- coding: utf-8 -*-
"""הון מניות מונפק ונפרע לכל נייר, ממאיה.

**למה זה נדרש.** עמוד העסקאות מחוץ לבורסה מציג כמה מהון החברה עבר ידיים
מחוץ לבורסה בתקופה. היקף כספי לבדו אינו עונה על זה: 10 מ׳ ₪ בחברה בשווי
מיליארד הם רעש, ובחברה בשווי 80 מ׳ הם שינוי שליטה. המכנה הוא מספר
המניות המונפקות, והוא אינו מופיע בסקירת העסקאות עצמה.

**מאיפה.** `/api/v1/companies/<id>/details` מחזיר לכל נייר של החברה את
`issuedPaidUp` — הון מונפק ונפרע. אומת מול הנתיב העקיף: דיווח ת076 של
אלקטרה נדל"ן נתן 68,690,702 מניות (כמות חלקי שיעור מההון), והשדה מחזיר
69,634,063 — פער של 1.4%, שמקורו בעיגול השיעור לארבע ספרות. השדה הוא
המקור המדויק, והנגזרת שימשה רק לאימות.

שים לב לשגיאת הכתיב במפתח של מאיה: `secrities` ולא `securities`.

**הון משתנה לעיתים רחוקות** — הנפקה, פיצול, מימוש אופציות — ולכן די
בריצה שבועית. הקובץ נשמר עם תאריך, וקריאה שנכשלה משאירה את הערך הקודם
במקום למחוק אותו.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tls import harden  # noqa: E402

harden()
from _maya_api import MayaSession  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "companies.yaml"
OUT = ROOT / "data" / "capital.json"


def coverage() -> list[dict]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    rows = cfg["companies"] if isinstance(cfg, dict) and "companies" in cfg else cfg
    return [c for c in rows if c.get("maya_company_id")]


def main() -> int:
    have: dict = {}
    if OUT.exists():
        try:
            have = json.loads(OUT.read_text(encoding="utf-8")).get("securities") or {}
        except json.JSONDecodeError:
            have = {}

    s = MayaSession()
    companies = coverage()
    fresh, failed = 0, 0
    for i, c in enumerate(companies, 1):
        try:
            d = s.company_details(int(c["maya_company_id"]))
        except Exception as e:  # noqa: BLE001
            failed += 1
            if failed <= 5:
                print(f"  {c['name_he']}: {type(e).__name__}", file=sys.stderr)
            continue
        for sec in (d.get("secrities") or []):
            sid = str(sec.get("securityId") or "")
            issued = sec.get("issuedPaidUp")
            if not sid or not issued:
                continue
            have[sid] = {
                "issued": int(issued),
                "tradable": int(sec.get("tradableSecurities") or 0),
                "market_cap_m": sec.get("marketCap"),
                "symbol": sec.get("symbol") or "",
                "name": sec.get("securityName") or c["name_he"],
                "company": c["name_he"],
                "asof": date.today().isoformat(),
            }
            fresh += 1
        if i % 50 == 0:
            print(f"  {i}/{len(companies)} — {len(have)} ניירות")
        time.sleep(0.25)

    if not have:
        print("::error::לא נאסף ולו נייר אחד — הקובץ לא נכתב", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": date.today().isoformat(),
        "companies": len(companies),
        "failed": failed,
        "securities": have,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nניירות עם הון מונפק: {len(have)} (רועננו {fresh}) · "
          f"חברות שנכשלו: {failed}")
    if failed > len(companies) * 0.2:
        print(f"::warning::{failed} מתוך {len(companies)} חברות נכשלו — "
              "ייתכן שהמכסה של מאיה נחסמה")
    return 0


if __name__ == "__main__":
    sys.exit(main())
