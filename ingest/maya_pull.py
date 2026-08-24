# -*- coding: utf-8 -*-
"""משיכת הודעות מאיה ל-24 השעות האחרונות, מסוננות לחברות הכיסוי.

הערה: נכתב מאפס מול ה-API החדש של maya.tase.co.il (אין סקרייפר קודם בריפו).
הסינון לפי maya_company_id שמולא ע"י resolve_tase_ids.py ב-config/companies.yaml.

פלט: data/raw/<YYYY-MM-DD>/maya.jsonl — שורה לדיווח:
  {id, ts, title, body, url, source, form_id, is_priority, companies:[...]}
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from _maya_api import MayaSession, WindowTooLarge, BASE
from _state import connect, filter_new

import yaml

ROOT = Path(__file__).resolve().parents[1]
IL_TZ = ZoneInfo("Asia/Jerusalem")


def load_coverage() -> dict[int, dict]:
    data = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    cov = {}
    for c in data["companies"]:
        cid = c.get("maya_company_id")
        if cid:
            cov[int(cid)] = {"name_he": c["name_he"], "sector": c.get("sector"),
                             "tase_id": c.get("tase_id")}
    return cov


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    lookback = int(cfg["params"].get("lookback_hours", 24))
    now_il = datetime.now(IL_TZ)
    cutoff = now_il - timedelta(hours=lookback)

    coverage = load_coverage()
    if not coverage:
        print("שגיאה: אין maya_company_id ב-companies.yaml — הרץ resolve_tase_ids.py",
              file=sys.stderr)
        return 1

    out_dir = ROOT / "data" / "raw" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "maya.jsonl"

    maya = MayaSession()
    # ה-API יומי — מושכים מהיום של ה-cutoff ומסננים שעות בצד שלנו
    try:
        raw = maya.reports_days(cutoff.date(), now_il.date())
    except WindowTooLarge as e:
        # יום עמוס בודד יכול לחרוג מתקרת העימוד, ואז אין מה לפצל לפי
        # תאריך. הרזולוציה הבאה היא חברה: שאילתה לכל חברת כיסוי מחזירה
        # בדיוק את מה שהברייף צריך ולעולם אינה מתקרבת לתקרה.
        # **זה עדיף על כישלון בכל מקרה** — הכישלון הפיל את המקור כולו,
        # ושלוש מהדורות רצופות נכתבו בלי דיווחי כיסוי.
        print(f"מאיה: {e} — יורד לשאילתה לפי חברה ({len(coverage)} חברות)",
              file=sys.stderr)
        raw, seen = [], set()
        failed = 0
        for cid in coverage:
            try:
                for it in maya.reports_days(cutoff.date(), now_il.date(),
                                            company_id=cid):
                    if it["id"] not in seen:
                        seen.add(it["id"])
                        raw.append(it)
            except Exception as ce:  # noqa: BLE001
                failed += 1
                print(f"  חברה {cid}: {type(ce).__name__}", file=sys.stderr)
        if failed:
            print(f"::warning::מאיה: {failed} חברות נכשלו בשאילתה הפרטנית",
                  file=sys.stderr)
        if not raw:
            print("::error::מאיה: גם המסלול לפי חברה לא החזיר דבר", file=sys.stderr)
            return 1

    matched = []
    for it in raw:
        pub = datetime.fromisoformat(it["publishDate"]).replace(tzinfo=IL_TZ)
        if pub < cutoff:
            continue
        hits = [c for c in it.get("companies", [])
                if c.get("companyId") in coverage]
        if not hits:
            continue
        matched.append((it, pub, hits))

    con = connect()
    fresh_ids = filter_new(con, "maya", [str(it["id"]) for it, _, _ in matched])
    con.close()

    n = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for it, pub, hits in matched:
            if str(it["id"]) not in fresh_ids:
                continue
            row = {
                "id": str(it["id"]),
                "ts": pub.isoformat(timespec="seconds"),
                "title": (it.get("title") or "").strip(),
                "body": "",                       # הפיד מחזיר כותרת בלבד; הקובץ המלא ב-url
                "url": f"{BASE}/he/reports/{it['id']}",
                "source": "maya",
                "form_id": it.get("formId"),
                "is_priority": bool(it.get("isPriority")),
                "companies": [{
                    "name_he": coverage[c["companyId"]]["name_he"],
                    "sector": coverage[c["companyId"]]["sector"],
                    "maya_company_id": c["companyId"],
                    "tase_id": coverage[c["companyId"]]["tase_id"],
                } for c in hits],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1

    print(f"נכתב {out_path} | נסרקו {len(raw)} דיווחים, "
          f"{len(matched)} של חברות כיסוי בחלון, {n} חדשים")
    return 0


if __name__ == "__main__":
    sys.exit(main())
