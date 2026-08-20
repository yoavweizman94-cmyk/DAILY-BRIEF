#!/usr/bin/env python3
"""עסקאות נדל"ן בגוש דן, בדרום ובצפון — מנתוני רשות המסים דרך Govmap.

**מה חשוב לדעת על המקור.** הנתונים הם דיווחי רשות המסים, והם מפגרים
כשישה שבועות אחרי מועד העסקה בפועל. לכן החודש האחרון תמיד נראה חלש —
זה פיגור בדיווח ולא צניחה בביקוש. הסטטיסטיקה מסמנת חודשים חלקיים
במקום להציג אותם כאילו הם מלאים.

**מקבלן מול יד שנייה** מגיע מהמקור עצמו: dealType=1 הוא עסקה ראשונה
(מקבלן) ו-dealType=2 יד שנייה. אין שדה משותף ברשומה, ולכן הסיווג נקבע
לפי השאילתה ונשמר ברשומה.

**שם הקבלן אינו בנתוני רשות המסים.** הוא נגזר ממקור נפרד — קובץ "דירה
בהנחה" של data.gov.il, שבו יש ProviderName לצד עיר ושכונה. לכן הוא
מוצג כ**התאמה משוערת** לפי עיר ושכונה, ולא כעובדה מהעסקה עצמה.

הסריקה יעילה כי `neighborhood-deals` עם מזהה חלקה מחזיר את כל השכונה
שסביבה — שש חלקות מכסות עיר, ולא צריך למנות אלפי חלקות.
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tls import harden  # noqa: E402

harden()

import requests  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "nadlan"
STATE = ROOT / "data" / "nadlan_state.json"
CFG = ROOT / "config" / "nadlan.yaml"

API = "https://www.govmap.gov.il/api"
GOV = "https://data.gov.il/api/3/action/datastore_search"
MECHIR_RES = "7c8255d0-49ef-49db-8904-4cf917586031"

HEADERS = {
    "Accept": "application/json",
    "Referer": "https://www.govmap.gov.il/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"),
}

# shape הוא MULTIPOLYGON של אלפי תווים לכל עסקה. שמירתו הייתה מנפחת את
# הקובץ פי עשרות בלי להוסיף דבר לתמונת המחירים.
DROP = {"shape", "objectid", "settlementNameEng", "streetNameEng", "streetCode"}


class Govmap:
    def __init__(self, throttle: float = 0.35):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.throttle = throttle
        self._last = 0.0

    def _wait(self):
        dt = self.throttle - (time.monotonic() - self._last)
        if dt > 0:
            time.sleep(dt)
        self._last = time.monotonic()

    def _get(self, url, **kw):
        last = None
        for i in range(3):
            try:
                self._wait()
                r = self.s.get(url, timeout=45, **kw)
                if r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}")
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last = e
                time.sleep(2 * (i + 1))
        raise last

    def point(self, text: str):
        """קואורדינטות לכתובת. autocomplete הוא POST, לא GET."""
        self._wait()
        r = self.s.post(f"{API}/search-service/autocomplete",
                        json={"searchText": text, "language": "he",
                              "isAccurate": False, "maxResults": 5},
                        headers={"Content-Type": "application/json"}, timeout=45)
        r.raise_for_status()
        for res in r.json().get("results", []):
            m = re.search(r"POINT\(([\d.]+)\s+([\d.]+)\)", res.get("shape") or "")
            if m:
                return float(m.group(1)), float(m.group(2))
        return None

    def polygons(self, x: float, y: float, radius: int = 3000):
        data = self._get(f"{API}/real-estate/deals/{x},{y}/{radius}")
        return data if isinstance(data, list) else []

    def neighborhood_deals(self, polygon_id: str, deal_type: int, limit: int = 400):
        data = self._get(f"{API}/real-estate/neighborhood-deals/{polygon_id}",
                         params={"limit": limit, "dealType": deal_type})
        if isinstance(data, dict):
            return data.get("data") or []
        return data if isinstance(data, list) else []


def norm_hood(s: str) -> str:
    """נרמול שם שכונה להשוואה בין שני מקורות עצמאיים.

    "שכונת השקדיות" מול "השקדיות", גרשיים, מקפים ורווחים כפולים — בלי
    נרמול ההצלבה מחזירה אפס התאמות גם כשמדובר באותה שכונה.
    """
    s = (s or "").strip()
    s = re.sub(r"^(שכונת|שכ\.|שכ׳|רובע)\s+", "", s)
    s = re.sub(r"[\"׳״'`,.\-–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def developer_index() -> dict:
    """מפתח (עיר, שכונה) → שמות יזמים, מקובץ "דירה בהנחה" של data.gov.il.

    זה המקור היחיד הציבורי שמקשר פרויקט ליזם. הוא מכסה רק תוכניות
    מסובסדות, ולכן ההתאמה היא רמז ולא ראיה — וכך היא גם מסומנת.
    """
    idx: dict[tuple, set] = {}
    try:
        offset, total = 0, None
        while total is None or offset < min(total, 4000):
            r = requests.get(GOV, params={"resource_id": MECHIR_RES, "limit": 1000,
                                          "offset": offset}, timeout=60)
            res = r.json().get("result", {})
            total = int(res.get("total") or 0)
            recs = res.get("records") or []
            if not recs:
                break
            for rec in recs:
                city = (rec.get("LamasName") or "").strip()
                hood = (rec.get("Neighborhood") or "").strip()
                prov = (rec.get("ProviderName") or "").strip()
                if city and prov:
                    idx.setdefault((city, norm_hood(hood)), set()).add(prov)
            offset += len(recs)
    except Exception as e:
        print(f"::warning::מדד היזמים לא נטען ({type(e).__name__}) — "
              f"עסקאות מקבלן יוצגו בלי שם יזם", file=sys.stderr)
    return {k: sorted(v) for k, v in idx.items()}


def clean(rec: dict, region_of: dict, deal_type: int, devs: dict) -> dict | None:
    """רשומה מנוקה, או None אם היא מחוץ לערים שהוגדרו.

    **העיר נלקחת מהרשומה עצמה ולא מהעיר שסביבה סרקנו.** פוליגון שכונה
    סביב עוגן ברמת גן חורג לתל אביב ולגבעתיים — נמדד: "בבלי" ו"תל גנים"
    תויגו כרמת גן. תמונת מחירים לפי עיר שמערבבת ערים אינה שווה דבר.
    """
    d = {k: v for k, v in rec.items() if k not in DROP}
    city = (d.get("settlementNameHeb") or "").strip()
    region = region_of.get(city)
    if not region:
        return None
    amount = d.get("dealAmount")
    area = d.get("assetArea")
    raw_date = d.get("dealDate") or ""
    if not amount or not raw_date:
        return None
    try:
        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None

    hood = (d.get("neighborhood") or "").strip()
    out = {
        "deal_id": d.get("dealId"),
        "date": dt,
        "city": city,
        "region": region,
        "neighborhood": hood or None,
        "street": (d.get("streetNameHeb") or "").strip() or None,
        "house_no": d.get("houseNum"),
        "rooms": d.get("assetRoomNum"),
        "area_sqm": area,
        "floor": (d.get("floorNo") or "").strip() or None,
        "property_type": (d.get("propertyTypeDescription") or "").strip() or None,
        "nature": (d.get("dealNatureDescription") or "").strip() or None,
        "amount": amount,
        "price_per_sqm": round(amount / area) if area else None,
        "is_new": deal_type == 1,
        "gush": d.get("gushNum"),
        "parcel": d.get("parcelNum"),
    }
    if deal_type == 1 and hood:
        # **התאמה לפי עיר ושכונה בלבד, בלי נפילה לאחור לעיר.** בגרסה
        # הקודמת כל עסקה בעיר קיבלה את אותם שני שמות — רעש שנראה כמו
        # מידע. עדיף שדה ריק מייחוס שאין לו בסיס.
        cand = devs.get((city, norm_hood(hood)))
        if cand:
            out["developer_candidates"] = cand[:4]
    return out


def main() -> int:
    cfg = load_cfg()
    months = int(os.environ.get("NADLAN_MONTHS") or cfg.get("months_back", 18))
    per_city = int(os.environ.get("NADLAN_POLYGONS") or cfg.get("polygons_per_city", 6))
    only = (os.environ.get("NADLAN_CITY") or "").strip()
    cutoff = (date.today() - timedelta(days=31 * months)).isoformat()

    # מפת עיר → אזור, לפי הקונפיג. הסריקה סביב עיר אחת מחזירה גם עסקאות
    # בערים שכנות, ואלה משויכות לאזור הנכון שלהן במקום להיזרק.
    region_of = {c["name"]: r["key"]
                 for r in cfg["regions"] for c in r["cities"]}

    g = Govmap()
    devs = developer_index()
    print(f"מדד יזמים: {len(devs)} מפתחות")

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    coords = state.get("coords", {})

    found: dict[int, dict] = {}
    failed = []
    for region in cfg["regions"]:
        for city in region["cities"]:
            name = city["name"]
            if only and only != name:
                continue
            try:
                pt = coords.get(name)
                if not pt:
                    pt = g.point(city["anchor"]) or g.point(name)
                    if not pt:
                        failed.append(name)
                        continue
                    coords[name] = list(pt)
                polys = g.polygons(pt[0], pt[1])
                polys.sort(key=lambda p: -int(p.get("dealscount") or 0))
                seen_hoods = set()
                picked = []
                for p in polys:
                    if len(picked) >= per_city:
                        break
                    picked.append(p["polygon_id"])
                n = 0
                for pid in picked:
                    for dt in (1, 2):
                        for rec in g.neighborhood_deals(pid, dt):
                            c = clean(rec, region_of, dt, devs)
                            if c and c["deal_id"] and c["date"] >= cutoff:
                                found[c["deal_id"]] = c
                                n += 1
                print(f"  {region['label']:8s} {name:14s} {len(picked)} חלקות → {n} עסקאות")
            except Exception as e:
                print(f"  {name}: {type(e).__name__} — מדולג", file=sys.stderr)
                failed.append(name)

    OUT.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, dict] = {}
    for rec in found.values():
        by_year.setdefault(rec["date"][:4], {})[rec["deal_id"]] = rec
    added = 0
    for yr, recs in by_year.items():
        path = OUT / f"{yr}.jsonl"
        existing = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    o = json.loads(line)
                    existing[o["deal_id"]] = o
        added += len([k for k in recs if k not in existing])
        existing.update(recs)
        rows = sorted(existing.values(), key=lambda r: (r["date"], r["deal_id"]))
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"coords": coords, "failed": failed,
                                 "updated": datetime.now().isoformat(timespec="seconds")},
                                ensure_ascii=False), encoding="utf-8")
    print(f"\nסה\"כ {len(found)} עסקאות ייחודיות ({added} חדשות) | ערים שנכשלו: {len(failed)}")
    if failed:
        print(f"::warning::ערים ללא נתונים: {', '.join(failed[:10])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
