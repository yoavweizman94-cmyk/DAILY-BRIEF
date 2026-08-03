# -*- coding: utf-8 -*-
"""מכרזי רמ"י: פרסומים חדשים + תוצאות ועדה, מוצלבים מול חברות הכיסוי.

למה סקריפט ולא שרת ה-MCP: ה-API של רמ"י מאחורי WAF של gov.il שחוסם requests
רגיל ומחזיר דף שגיאת HTML (remy-mcp נכשל בדיוק כך). כאן משתמשים בחיקוי TLS של
דפדפן + עוגיות, ומבקשים JSON במפורש — אחרת השרת מחזיר XML של 6.6MB.
בנוסף: פילטרי התאריכים בצד השרת (PirsumDate/VaadaDate) פשוט לא מיושמים —
הסינון חייב להתבצע מקומית.

פלט: data/raw/<YYYY-MM-DD>/rmi.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden
harden()

import yaml
from curl_cffi import requests as creq

from _state import connect, filter_new

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://apps.land.gov.il/MichrazimSite"
LOOKBACK_DAYS = 4           # מכסה סוף שבוע ארוך בלי לפספס ועדה של יום חמישי

YEUD = {1: "בנייה נמוכה/צמודת קרקע", 2: "בנייה רוויה", 3: "מסחר ו/או משרדים",
        4: "מלונאות", 5: "מוסדות ובנייני ציבור", 6: "ספורט/נופש/תיירות",
        7: "מגורים/מסחר/מלונאות", 8: "כרייה וחציבה", 9: "אחר"}
MERCHAV = {1: 'יו"ש', 2: "דרום", 3: "חיפה", 4: "תל אביב", 5: "ירושלים", 6: "מרכז"}


def load_yeshuv_map() -> dict:
    """טבלת קודי יישוב מה-clone של remy-mcp; בהיעדרו מחזירים מיפוי ריק."""
    vendored = ROOT / "vendor" / "remy-mcp"
    if vendored.exists():
        sys.path.insert(0, str(vendored))
        try:
            from data.kod_yeshuv import KOD_YESHUV_MAPPING
            return KOD_YESHUV_MAPPING
        except Exception:
            pass
    return {}


def coverage_matchers() -> list[tuple[re.Pattern, str, bool]]:
    data = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    out = []
    for c in data["companies"]:
        for alias in [c["name_he"]] + list(c.get("aliases") or []):
            pat = re.compile(r"(?<![\w֐-׿])" + re.escape(alias)
                             + r"(?![\w֐-׿])")
            out.append((pat, c["name_he"], bool(c.get("generic_name"))))
    return out


def as_date(v):
    try:
        return datetime.fromisoformat(v).date() if v else None
    except Exception:
        return None


def main() -> int:
    today = date.today()
    session = creq.Session(impersonate="chrome")
    session.get(f"{BASE}/", timeout=40)
    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "Origin": "https://apps.land.gov.il", "Referer": f"{BASE}/"}

    try:
        resp = session.post(f"{BASE}/api/SearchApi/Search", json={},
                            headers=headers, timeout=120)
        resp.raise_for_status()
        if "json" not in (resp.headers.get("content-type") or ""):
            raise RuntimeError("התקבל HTML/XML במקום JSON — ככל הנראה חסימת WAF")
        rows = resp.json()
    except Exception as ex:
        print(f"שגיאה: משיכת מכרזי רמ\"י נכשלה: {ex}", file=sys.stderr)
        return 1

    yeshuv = load_yeshuv_map()
    matchers = coverage_matchers()

    def fresh(field):
        hits = []
        for r in rows:
            d = as_date(r.get(field))
            if d and 0 <= (today - d).days <= LOOKBACK_DAYS:
                hits.append((d, r))
        return sorted(hits, key=lambda x: x[0], reverse=True)

    def describe(r, when):
        return {"michraz_id": r["MichrazID"], "name": r["MichrazName"],
                "date": when.isoformat(),
                "yeshuv": yeshuv.get(r.get("KodYeshuv"), str(r.get("KodYeshuv"))),
                "shchuna": (r.get("Shchuna") or "").strip(),
                "merchav": MERCHAV.get(r.get("KodMerchav")),
                "yeud": YEUD.get(r.get("KodYeudMichraz"), "אחר"),
                "units": r.get("YechidotDiur"),
                "url": f"{BASE}/#/michraz/{r['MichrazID']}"}

    published = [describe(r, d) for d, r in fresh("PirsumDate")]

    results = []
    for d, r in fresh("VaadaDate"):
        item = describe(r, d)
        try:
            det = session.get(f"{BASE}/api/MichrazDetailsApi/Get",
                              params={"michrazID": r["MichrazID"]},
                              headers={"Accept": "application/json", "Referer": f"{BASE}/"},
                              timeout=60).json()
        except Exception as ex:
            item["error"] = f"פרטי המכרז לא נמשכו: {ex}"
            results.append(item)
            continue
        winners = []
        for tik in (det.get("Tik") or []):
            name = (tik.get("ShemZoche") or "").strip()
            if not name:
                continue
            hits = [(full, gen) for pat, full, gen in matchers if pat.search(name)]
            winners.append({
                "shem": name,
                "sum": tik.get("SchumZchiya"),
                "kibolet": tik.get("Kibolet"),
                "no_bids": "אין הצעות" in name,
                "coverage_match": [full for full, _ in hits],
                # שם גנרי = לאמת הקשר לפני שמייחסים לחברת הכיסוי
                "coverage_match_needs_review": [full for full, gen in hits if gen],
            })
        item["winners"] = winners
        results.append(item)

    con = connect()
    ids = [f"{x['michraz_id']}:{x['date']}" for x in results] + \
          [f"pub:{x['michraz_id']}:{x['date']}" for x in published]
    keep = filter_new(con, "rmi", ids)
    con.close()
    results = [x for x in results if f"{x['michraz_id']}:{x['date']}" in keep]
    published = [x for x in published if f"pub:{x['michraz_id']}:{x['date']}" in keep]

    covered = sorted({m for x in results for w in x.get("winners", [])
                      for m in w["coverage_match"]})
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"),
               "lookback_days": LOOKBACK_DAYS, "source": BASE,
               "published": published, "results": results,
               "coverage_winners": covered}

    out_dir = ROOT / "data" / "raw" / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rmi.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"נכתב {out_path} | {len(published)} פרסומים חדשים, "
          f"{len(results)} תוצאות ועדה, זכיות חברות כיסוי: {covered or 'אין'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
