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
import collections
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
from curl_cffi import requests as creq  # noqa: E402

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


def why(e: Exception) -> str:
    """שם השגיאה עם קוד ה-HTTP. "HTTPError" בלבד אינו ניתן לאבחון:
    403 הוא חסימת WAF, 404 הוא מזהה שגוי, 429 הוא קצב. בלי הקוד אי אפשר
    לדעת מי משלושתם, וזה בדיוק מה שקרה בריצה שהחזירה 0 עסקאות."""
    code = getattr(getattr(e, "response", None), "status_code", None)
    return f"{type(e).__name__} {code}" if code else type(e).__name__


class Govmap:
    """הגישה היא ב-curl_cffi עם חיקוי דפדפן, לא ב-requests.

    govmap.gov.il חוסם לפי טביעת TLS, כמו מאיה ורמ"י. מתחנת עבודה שיוצאת
    דרך פרוקסי ארגוני החוסם אינו מורגש — הפרוקסי חותם מחדש ומחליף את
    הטביעה — ולכן `requests` עבד מקומית ונכשל ב-33 הערים על ראנר Linux.
    """

    def __init__(self, throttle: float = 0.35):
        self.s = creq.Session(impersonate="chrome")
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

    def point(self, text: str, forms: list[str] | None = None):
        """קואורדינטות לכתובת. autocomplete הוא POST, לא GET.

        כשנמסר `forms`, מתקבלת רק תוצאה שאחת מצורות שם היישוב מופיעה בה.
        Govmap מדרג לפי התאמת מספר הבית ולא לפי היישוב: "העצמאות 40 קרית
        גת" החזיר את "העצמאות 40 קרית אתא" במקום הראשון — קרית גת נסרקה
        כעיר אחרת, וכל עסקאותיה נזרקו כי קריית אתא אינה בכיסוי.
        """
        self._wait()
        r = self.s.post(f"{API}/search-service/autocomplete",
                        json={"searchText": text, "language": "he",
                              "isAccurate": False, "maxResults": 10},
                        headers={"Content-Type": "application/json"}, timeout=45)
        r.raise_for_status()
        for res in r.json().get("results", []):
            txt = norm_city(res.get("text") or "")
            if forms and not any(f in txt for f in forms):
                continue
            m = re.search(r"POINT\(([\d.]+)\s+([\d.]+)\)", res.get("shape") or "")
            if m:
                return float(m.group(1)), float(m.group(2))
        return None

    def polygons(self, x: float, y: float, radius: int = 3000):
        data = self._get(f"{API}/real-estate/deals/{x},{y}/{radius}")
        return data if isinstance(data, list) else []

    def polygons_multi(self, x: float, y: float, radii=(1000, 2000, 3000)):
        """איחוד חלקות מכמה רדיוסים.

        ה-API מחזיר תקרה של 100 חלקות, והרכבן משתנה עם הרדיוס בלי שמירת
        סדר מרחק: סביב הרצליה הוחזרו 3 חלקות בעיר ברדיוס 3000 מול 7
        ברדיוס 2000. שאילתה אחת נותנת מדגם שרירותי, ולעיר צפופה־שכנים
        היא נותנת כמעט אפס.
        """
        seen, out = set(), []
        for rad in radii:
            for p in self.polygons(x, y, rad):
                pid = p.get("polygon_id")
                if pid and pid not in seen:
                    seen.add(pid)
                    out.append(p)
        return out

    def has_deals(self, polygon_id: str) -> bool:
        """בדיקה זולה (limit=1) אם לפוליגון יש עסקאות בכלל.

        `dealscount` שמגיע עם הפוליגון אינו מנבא זאת: נמדד dealscount=256
        שהחזיר אפס עסקאות, לצד dealscount=9 שהחזיר 401. מיון לפי השדה
        הזה בחר שש חלקות ריקות ברצף, ורמת השרון, שדרות וקרית שמונה
        הוצגו כאילו לא נסחרה בהן דירה.
        """
        for dt in (2, 1):
            d = self._get(f"{API}/real-estate/neighborhood-deals/{polygon_id}",
                          params={"limit": 1, "dealType": dt})
            if isinstance(d, dict) and int(d.get("totalCount") or 0) > 0:
                return True
        return False

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


def norm_city(s: str) -> str:
    """נרמול שם יישוב להשוואה בין הקונפיג לנתונים.

    Govmap כותב בכתיב מלא — "קריית ביאליק", "הרצלייה" — והקונפיג בכתיב
    חסר. בלי נרמול ההתאמה נכשלת ו-clean() זורק את העסקה בשקט: כל עסקאות
    הרצליה נעלמו כך, והעיר הוצגה עם שתי עסקאות. הכלל הוא כיווץ יו"ד
    כפולה לאחת, ולא רשימת חריגים — הרשימה תמיד חסרה עיר.
    """
    s = (s or "").strip()
    s = re.sub(r"[\"׳״'`]", "", s)
    s = re.sub(r"[-–—]", " ", s)
    s = s.replace("יי", "י")
    return re.sub(r"\s+", " ", s).strip()


def city_forms(city: dict) -> list[str]:
    """צורות שם היישוב שמתקבלות באימות העוגן.

    "תל אביב-יפו" בקונפיג מול "אבן גבירול 68 תל אביב" בתוצאה — התאמה
    מלאה נכשלת, ולכן גם הקידומת בת שתי המילים מתקבלת.
    """
    forms = []
    for nm in [city["name"], *(city.get("aliases") or [])]:
        n = norm_city(nm)
        forms.append(n)
        parts = n.split()
        if len(parts) > 2:
            forms.append(" ".join(parts[:2]))
    return forms


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


UNMATCHED: collections.Counter = collections.Counter()


def clean(rec: dict, region_of: dict, deal_type: int, devs: dict) -> dict | None:
    """רשומה מנוקה, או None אם היא מחוץ לערים שהוגדרו.

    **העיר נלקחת מהרשומה עצמה ולא מהעיר שסביבה סרקנו.** פוליגון שכונה
    סביב עוגן ברמת גן חורג לתל אביב ולגבעתיים — נמדד: "בבלי" ו"תל גנים"
    תויגו כרמת גן. תמונת מחירים לפי עיר שמערבבת ערים אינה שווה דבר.
    """
    d = {k: v for k, v in rec.items() if k not in DROP}
    raw_city = (d.get("settlementNameHeb") or "").strip()
    hit = region_of.get(norm_city(raw_city))
    if not hit:
        UNMATCHED[raw_city] += 1
        return None
    # השם הקנוני מהקונפיג, כדי ששתי איותיה של אותה עיר לא ייספרו כשתי ערים.
    region, city = hit
    amount = d.get("dealAmount")
    area = d.get("assetArea")
    raw_date = d.get("dealDate") or ""
    if not amount or not raw_date:
        return None
    try:
        parsed = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
    except ValueError:
        return None
    # תאריך עתידי הוא שגיאת מקור (נמצאה עסקה ב-2027), והוא פותח קובץ שנה
    # שלמה על רשומה אחת ומעוות את חלון "החודשים האחרונים".
    if parsed > date.today():
        return None
    dt = parsed.isoformat()

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
    max_probe = int(cfg.get("max_probes_per_city", 40))
    only = (os.environ.get("NADLAN_CITY") or "").strip()
    reprobe = bool(os.environ.get("NADLAN_REPROBE"))
    cutoff = (date.today() - timedelta(days=31 * months)).isoformat()

    # מפת עיר → אזור, לפי הקונפיג. הסריקה סביב עיר אחת מחזירה גם עסקאות
    # בערים שכנות, ואלה משויכות לאזור הנכון שלהן במקום להיזרק.
    # aliases: Govmap שומר שמות היסטוריים ("נצרת עילית" ל"נוף הגליל"),
    # וכל אחד מהם ממופה לאותה עיר קנונית.
    region_of = {}
    for r in cfg["regions"]:
        for c in r["cities"]:
            for nm in [c["name"], *(c.get("aliases") or [])]:
                region_of[norm_city(nm)] = (r["key"], c["name"])

    g = Govmap()
    devs = developer_index()
    print(f"מדד יזמים: {len(devs)} מפתחות")

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    coords = state.get("coords", {})
    # החלקות הפוריות נשמרות, כי איתורן דורש עשרות בדיקות ותוצאתן יציבה.
    # בלי המטמון מהדורת הבוקר מבזבזת עליהן רבע שעה בכל יום.
    plots = {} if reprobe else state.get("plots", {})

    found: dict[int, dict] = {}
    failed, empty = [], []
    for region in cfg["regions"]:
        for city in region["cities"]:
            name = city["name"]
            if only and only != name:
                continue
            try:
                pt = coords.get(name)
                if not pt:
                    forms = city_forms(city)
                    pt = g.point(city["anchor"], forms) or g.point(name, forms)
                    if not pt:
                        print(f"  {name}: העוגן לא נפתר ליישוב הנכון — מדולג",
                              file=sys.stderr)
                        failed.append(name)
                        continue
                    coords[name] = list(pt)

                # פוליגון ששייך ליישוב מחוץ לכיסוי אינו תורם דבר — עסקאותיו
                # ייזרקו ב-clean() בכל מקרה — אך הוא כן דוחק פוליגון שכן.
                picked, probed = plots.get(name) or [], 0
                if not picked:
                    cand = [p for p in g.polygons_multi(pt[0], pt[1])
                            if norm_city(p.get("settlementNameHeb")) in region_of]
                    # חלקות העיר עצמה נבדקות ראשונות. בלי זה הרצליה בזבזה
                    # 38 בדיקות על שכנותיה וסיימה עם עסקה אחת משלה.
                    own = norm_city(name)
                    polys = ([p for p in cand
                              if norm_city(p.get("settlementNameHeb")) == own]
                             + [p for p in cand
                                if norm_city(p.get("settlementNameHeb")) != own])
                    if not polys:
                        print(f"  {name}: אין חלקות בערי הכיסוי סביב העוגן — מדולג",
                              file=sys.stderr)
                        failed.append(name)
                        continue
                    # פוליגון שנבחר מחזיר את **כל** השכונה שסביבו, ולכן די
                    # במעט פוליגונים פוריים; החיפוש הוא אחריהם, לא אחרי
                    # הראשונים ברשימה.
                    for p in polys:
                        if len(picked) >= per_city or probed >= max_probe:
                            break
                        probed += 1
                        if g.has_deals(p["polygon_id"]):
                            picked.append(p["polygon_id"])
                    if picked:
                        plots[name] = picked
                n = 0
                for pid in picked:
                    for dt in (1, 2):
                        for rec in g.neighborhood_deals(pid, dt):
                            c = clean(rec, region_of, dt, devs)
                            if c and c["deal_id"] and c["date"] >= cutoff:
                                found[c["deal_id"]] = c
                                n += 1
                if not n and plots.get(name):
                    # המטמון הצביע על חלקות שהתרוקנו. מוחקים אותו כדי
                    # שהריצה הבאה תחפש מחדש במקום לקפוא על עיר ריקה.
                    plots.pop(name, None)
                    print(f"  {name}: החלקות השמורות התרוקנו — המטמון נוקה",
                          file=sys.stderr)
                if not picked:
                    print(f"  {name}: {probed} חלקות נבדקו, בכולן אפס עסקאות",
                          file=sys.stderr)
                    empty.append(name)
                how = f"מתוך {probed} שנבדקו" if probed else "מהמטמון"
                print(f"  {region['label']:8s} {name:14s} "
                      f"{len(picked)} חלקות {how} → {n} עסקאות")
            except Exception as e:
                print(f"  {name}: {why(e)} — מדולג", file=sys.stderr)
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
    STATE.write_text(json.dumps({"coords": coords, "plots": plots,
                                 "failed": failed, "empty": empty,
                                 "updated": datetime.now().isoformat(timespec="seconds")},
                                ensure_ascii=False), encoding="utf-8")
    print(f"\nסה\"כ {len(found)} עסקאות ייחודיות ({added} חדשות) | ערים שנכשלו: {len(failed)}")
    if failed:
        print(f"::warning::ערים ללא נתונים: {', '.join(failed[:10])}")
    if empty:
        print(f"::warning::ערים שנסרקו והמקור החזיר בהן אפס עסקאות: {', '.join(empty)}")

    # שם יישוב שנזרק בהיקף גדול הוא כמעט תמיד איות שאינו מכוסה, לא יישוב
    # זר. הרצליה נעלמה כך לגמרי, ואיש לא ידע כי clean() שתק.
    big = [(nm, n) for nm, n in UNMATCHED.most_common(8) if n >= 200 and nm]
    if big:
        print("::warning::שמות יישוב שנזרקו בהיקף גדול (איות לא מכוסה?): "
              + ", ".join(f"{nm} ({n})" for nm, n in big))
    return 0


if __name__ == "__main__":
    sys.exit(main())
