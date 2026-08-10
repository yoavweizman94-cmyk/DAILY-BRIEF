# -*- coding: utf-8 -*-
"""ניטור רציף של דיווחי מאיה — שולף כל דיווח חדש עם גוף הדוח.

רץ תדיר (ולא פעם ביום כמו maya_pull), ומזהה דיווחים שטרם נראו דרך
`reported_ids` ב-state.sqlite תחת המקור "maya_watch". כל דיווח חדש נשלף
עם גוף הדוח מ-mayafiles, ומסומן אם הוא מועמד לסיכום.

מדיניות הסיכום (config/sources.yaml → maya_watch):
  scope: coverage | material | all
    coverage — רק חברות הכיסוי (~14 ליום)
    material — חברות הכיסוי + טפסים מהותיים בכל הבורסה (ברירת מחדל)
    all      — כל דיווח בבורסה (~100–175 ליום; עלות LLM גבוהה משמעותית)

פלט: data/raw/<YYYY-MM-DD>/maya_new.jsonl — רק החדשים מהריצה הזו.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from _maya_api import MayaSession, BASE
from _maya_doc import fetch_text
from _state import connect, filter_new

import yaml

ROOT = Path(__file__).resolve().parents[1]
IL_TZ = ZoneInfo("Asia/Jerusalem")


def load_coverage() -> dict[int, dict]:
    data = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    return {int(c["maya_company_id"]): {"name_he": c["name_he"], "sector": c.get("sector")}
            for c in data["companies"] if c.get("maya_company_id")}


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    wcfg = cfg.get("maya_watch") or {}
    scope = wcfg.get("scope", "material")
    material_forms = set(wcfg.get("material_forms") or [])
    lookback_h = int(wcfg.get("lookback_hours", 6))

    coverage = load_coverage()
    now = datetime.now(IL_TZ)
    since = now - timedelta(hours=lookback_h)

    maya = MayaSession()
    raw = maya.reports_days(since.date(), now.date())

    fresh_window = []
    for it in raw:
        try:
            pub = datetime.fromisoformat(it["publishDate"]).replace(tzinfo=IL_TZ)
        except Exception:
            continue
        if pub >= since:
            fresh_window.append((it, pub))

    con = connect()
    new_ids = filter_new(con, "maya_watch", [str(i["id"]) for i, _ in fresh_window])
    con.close()
    new_items = [(i, p) for i, p in fresh_window if str(i["id"]) in new_ids]

    rows, fetched = [], 0
    for it, pub in sorted(new_items, key=lambda x: x[1]):
        hits = [c for c in (it.get("companies") or []) if c.get("companyId") in coverage]
        form = (it.get("formId") or "").strip()
        if scope == "coverage":
            summarize = bool(hits)
        elif scope == "all":
            summarize = True
        else:                                   # material
            summarize = bool(hits) or (form in material_forms)

        text, file_url = ("", None)
        if summarize:
            text, file_url = fetch_text(maya._s, it)
            fetched += 1

        rows.append({
            "id": str(it["id"]),
            "ts": pub.isoformat(timespec="seconds"),
            "title": (it.get("title") or "").strip(),
            "form_id": form,
            "is_priority": bool(it.get("isPriority")),
            "url": f"{BASE}/he/reports/{it['id']}",
            "file_url": file_url,
            "companies": [c.get("name") for c in (it.get("companies") or [])],
            "coverage": [coverage[c["companyId"]]["name_he"] for c in hits],
            "sectors": sorted({coverage[c["companyId"]]["sector"] for c in hits}),
            "summarize": summarize,
            "body": text,
        })

    out_dir = ROOT / "data" / "raw" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "maya_new.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as f:   # append: מספר ריצות ביום
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cov = sum(1 for r in rows if r["coverage"])
    print(f"נכתב {path} | חלון {lookback_h}ש: {len(fresh_window)} דיווחים, "
          f"{len(rows)} חדשים, {fetched} נשלפו לסיכום ({cov} של חברות כיסוי) | scope={scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
