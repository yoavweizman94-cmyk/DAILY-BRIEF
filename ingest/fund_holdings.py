# -*- coding: utf-8 -*-
"""אחזקות המניות של הקרן שעמוד המתחרים (peers.html) עוקב אחריה, מדוח האחזקות החודשי במאיה.

**המקור.** קרן נאמנות מפרסמת במאיה דוח חודשי (טופס ק203) עם קובץ טקסט של כל נכסי
כל הקרנות של המנהל, שורה לנכס: מספר קרן, שם נכס, סוג נכס, מספר נייר, שווי ו-%חשיפה.
הדוח מתפרסם באיחור של כחודשיים (דוח אוגוסט 2026 פורסם ב-25/10), ולכן הוא אינו משקף
קניות ומכירות אחרונות — וכך נכתב בעמוד.

**הפלט** (output/peers/holdings.json, בריפו התוכן הפרטי — לא בקוד הציבורי): לכל מניה
שם, מספר נייר, משקל, ושיוך לרשימת הכיסוי (שם, ענף בבורסה, מספר חברה במאיה).
"תעשייתית" נקבעת לפי ענף הבורסה; peers.json, שבו המתחרים לכל אחזקה, נשען עליה.

    python ingest/fund_holdings.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402
harden()

import yaml  # noqa: E402

from _maya_api import BASE, HEADERS, MayaSession  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "peers"
FILES = "https://mayafiles.tase.co.il/"
FUND_ID = os.environ.get("PEERS_FUND_ID") or "5128616"

# **תעשייתית** — ענף בורסה "תעשייה-*", ועוד ייצור שמסווג בבורסה אחרת: ביטחוניות
# ואלקטרוניקה (ארד מייצרת מדי מים, אלביט מערכות). מסחר, פיננסים, נדל"ן ותוכנה — לא.
INDUSTRIAL_EXTRA = {"טכנולוגיה-ביטחוניות", "טכנולוגיה-אלקטרוניקה ואופטיקה"}
SHARE_TYPE = "1"          # "סוג נכס" בקובץ: מניה


def is_industrial(tase_sector: str) -> bool:
    return bool(tase_sector) and (tase_sector.startswith("תעשייה-") or tase_sector in INDUSTRIAL_EXTRA)


def parse(text: str, fund_id: str) -> list[dict]:
    """שורות המניות של הקרן מקובץ הדוח החודשי (TSV, כותרת בעברית)."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter="\t"))
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        d = dict(zip(head, (c.strip() for c in r)))
        if d.get("מספר קרן") != fund_id or d.get("סוג נכס") != SHARE_TYPE:
            continue
        try:
            w = float(d.get("%חשיפה") or 0)
        except ValueError:
            w = 0.0
        raw = (d.get("תאריך דוח") or "").strip()          # DDMMYYYY
        day = f"{raw[4:8]}-{raw[2:4]}-{raw[0:2]}" if len(raw) == 8 and raw.isdigit() else raw
        out.append({"security": d.get("מספר מזהה") or "", "asset": d.get("שם נכס") or "",
                    "weight": round(w, 2), "date": day})
    out.sort(key=lambda x: -x["weight"])
    return out


def enrich(shares: list[dict]) -> list[dict]:
    cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    by_sec = {str(c.get("tase_id")): c for c in cfg.get("companies") or []}
    for s in shares:
        c = by_sec.get(s["security"]) or {}
        s.update({"name": c.get("name_he") or "", "maya_id": c.get("maya_company_id"),
                  "tase_sector": c.get("tase_sector") or "", "sector": c.get("sector") or "",
                  "industrial": is_industrial(c.get("tase_sector") or "")})
    return shares


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "holdings.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    s = MayaSession()
    s._wait()
    fund = s._s.get(f"{BASE}/api/v1/funds/mutual/{FUND_ID}", headers=HEADERS, timeout=30).json()
    rid = fund.get("lastMonthlyReportId")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not rid:
        print("::warning title=אחזקות הקרן::אין דוח חודשי אחרון בפרטי הקרן — נשאר הקובץ הקודם")
        return 0
    if str((prev.get("report") or {}).get("id")) == str(rid):
        prev["checked"] = now
        path.write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"אחזקות הקרן: אין דוח חודשי חדש (האחרון {rid}, {prev['report'].get('title')})")
        return 0
    s._wait()
    rep = s._s.get(f"{BASE}/api/v1/reports/{rid}", headers=HEADERS, timeout=30).json()
    att = next((a for a in rep.get("attachments") or [] if (a.get("fileType") or "").startswith("txt")), None)
    if not att:
        print(f"::warning title=אחזקות הקרן::לדוח {rid} אין קובץ טקסט — נשאר הקובץ הקודם")
        return 0
    s._wait()
    raw = s._s.get(FILES + att["url"], timeout=120).content
    shares = enrich(parse(raw.decode("utf-8", "replace"), FUND_ID))
    if not shares:
        print(f"::warning title=אחזקות הקרן::בדוח {rid} לא נמצאו מניות של הקרן — נשאר הקובץ הקודם")
        return 0
    data = {"fund": {"id": FUND_ID, "name": fund.get("longName") or fund.get("name"),
                     "aum_m": fund.get("assetValueNISMillions"), "aum_asof": (fund.get("assetValueAsOf") or "")[:10]},
            "report": {"id": rid, "title": rep.get("title"), "published": (rep.get("publishDate") or "")[:10],
                       "asof": shares[0].get("date") or ""},
            "fetched": now, "checked": now, "holdings": shares}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    ind = [x for x in shares if x["industrial"]]
    # מספרים בלבד: הלוג ציבורי, והרשימה עצמה אינה יוצאת מריפו התוכן
    print(f"::notice title=אחזקות הקרן — דוח חודשי חדש::{len(shares)} מניות, מהן {len(ind)} תעשייתיות "
          f"({sum(x['weight'] for x in ind):.1f}% מהקרן) · פורסם {data['report']['published']}")
    print("CHANGED=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
