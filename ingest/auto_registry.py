# -*- coding: utf-8 -*-
"""נתוני רשם כלי הרכב (משרד התחבורה, data.gov.il) לסעיף הליסינג בגיליון הרכב.

**למה נתונים ולא רק כותרות.** כותרת על "חברות הליסינג מאטות רכישות" היא טענה;
הרשם אומר כמה רכבים חדשים עלו לכביש בבעלות ליסינג בכל חודש, מאיזו יבואנית,
מאיזה תוצר ובאיזה מחיר מחירון — ובהיסטוריית הבעלויות, כמה רכבים יצאו מציי
הליסינג ולאן. אלה שתי הזרימות שקובעות את כלכלת הצי: קנייה ומכירה.

ארבעה מאגרים ציבוריים, בלי מפתח:
  · מספרי רישוי של כלי רכב פרטיים ומסחריים (053cea08…) — כל רכב פעיל: בעלות
    נוכחית, חודש עלייה לכביש ("2026-8"), תוצר, דגם, שנת ייצור, דלק.
  · יבואנים ומחירוני רכב חדש (39f455bf…) — היבואן ומחיר המחירון לכל תוצר+דגם+שנה.
  · תוצרים של כלי הרכב הפעילים (d00812f4…) — המותג וארץ התוצר, רשמית.
  · היסטוריית כלי רכב פרטיים (bb2355dc…) — כל תקופת בעלות וחודש תחילתה. שם
    הליסינג נקרא "החכר"; כאן הוא מנורמל ל"ליסינג".

**הבעלות במאגר היא הנוכחית, לא זו שביום הרישום.** רכב שעלה לכביש בליסינג ונמכר
מאז לפרטי נספר היום כפרטי. לכן חודש שחושב נשמר כפי שחושב — כשהיה קרוב
לרישום — ורק שלושת החודשים האחרונים מחושבים מחדש בכל ריצה. חודש ישן שנכנס
לראשונה (מילוי אחורה) מסומן `late`: הבעלות בו כבר זזה.

**מכירות מהצי נמדדות מהיסטוריית הבעלויות.** לכל תקופת בעלות שהתחילה בחודש
נשלפת ההיסטוריה של אותו רכב, והבעלות הקודמת אומרת מאין בא: ליסינג שהפך
לפרטי או לסוחר הוא רכב שיצא מהצי. חודש כזה הוא ~90 אלף רכבים ו-~2 דקות של
שליפות, ולכן המילוי אחורה מוגבל בזמן ונמשך בריצות הבאות.

פלט: output/auto/registry/registrations.json, output/auto/registry/disposals.json
שימוש: python ingest/auto_registry.py [--budget-minutes 6] [--force]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402
harden()

from curl_cffi import requests as creq  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "auto" / "registry"
API = "https://data.gov.il/api/3/action/datastore_search"
RID_REG = "053cea08-09bc-40ec-8f7a-156f0677aff3"
RID_PRICE = "39f455bf-6db0-4926-859d-017f34eacbcb"
RID_MAKER = "d00812f4-58c5-4ce8-b16c-ac13ae52f9d8"
RID_HIST = "bb2355dc-9ec7-4f06-9c3f-3344672171da"

MONTHS = 25            # חודשי רישום שנשמרים — שנתיים ועוד חודש, להשוואה שנתית
REFRESH = 3            # החודשים האחרונים שמחושבים מחדש בכל ריצה
DISPOSAL_MONTHS = 12
TOP = 20
PAGE = 32000
BATCH = 1000           # רכבים לשליפת היסטוריה אחת
OWNERS = ("ליסינג", "השכרה", "פרטי", "חברה", "סוחר")
OWN_NORM = {"החכר": "ליסינג"}
FLEET = ("ליסינג", "השכרה")
FUEL = {"חשמל": "ev", "חשמל/בנזין": "hybrid", "חשמל/דיזל": "hybrid", "בנזין": "ice", "דיזל": "ice"}


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Jerusalem")
    except Exception:  # noqa: BLE001 — Windows בלי tzdata
        return timezone(timedelta(hours=3))


IL = _tz()


# --------------------------------------------------------------------------
# גישה למאגר

def call(s, payload: dict, tries: int = 4) -> dict:
    """POST ולא GET: סינון לפי אלף מספרי רכב חורג מאורך כתובת מותר (נמדד:
    500 מספרים ב-GET החזירו דף שגיאה HTML ולא JSON)."""
    err = ""
    for i in range(tries):
        try:
            r = s.post(API, json=payload, timeout=180)
            if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
                d = r.json()
                if d.get("success"):
                    return d["result"]
                err = str(d.get("error"))[:120]
            else:
                err = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"data.gov.il ({payload.get('resource_id', '')[:8]}): {err}")


def fetch_all(s, rid: str, filters: dict, fields: str) -> list[dict]:
    out, offset = [], 0
    while True:
        res = call(s, {"resource_id": rid, "filters": filters, "fields": fields,
                       "limit": PAGE, "offset": offset})
        recs = res.get("records") or []
        out += recs
        offset += len(recs)
        if not recs or offset >= (res.get("total") or 0):
            return out


def norm_owner(v) -> str:
    v = (v or "").strip()
    v = OWN_NORM.get(v, v)
    return v if v in OWNERS else "אחר"


def importer_name(v: str) -> str:
    """"קרסו מוטורס בע"מ" → "קרסו מוטורס". הסיומת משתנה בכתיב ואינה חלק מהשם."""
    v = " ".join((v or "").split())
    v = re.sub(r'\s*בע["״\']?מ\.?$', "", v)
    v = re.sub(r'\s*בע["״\']?$', "", v)
    return v.strip(" -")


def brand_from_name(nm: str, country: str | None, known: set[str], countries: set[str]) -> str | None:
    """מותג מ-tozeret_nm, כשבטבלת התוצרים אין לו tozar.

    **הטבלה מאבדת שמות מותג.** ב-22/09/2026 היו בה 108 קודי תוצר בלי tozar,
    ביניהם בי ווי די (1014, "בי ווי די סין") וקיה (885, "קיה ד. קוריאה") — 1,332
    רכבי ליסינג באוגוסט שנספרו תחת "לא ידוע", ו-BYD נעלמה מטבלת המותגים. השם
    המלא כולל את ארץ התוצר, ולכן: המותג הידוע הארוך ביותר שהשם מתחיל בו; ואם אין
    כזה — השם בלי ארץ התוצר שבסופו.
    """
    nm = " ".join((nm or "").split())
    if not nm:
        return None
    words = nm.split()
    for k in range(len(words), 0, -1):
        if " ".join(words[:k]) in known:
            return " ".join(words[:k])
    if country and nm.endswith(country) and nm[: -len(country)].strip():
        return nm[: -len(country)].strip()
    # המילה האחרונה יורדת רק כשהיא ארץ ("פורד ברזיל"), לא חלק מהשם ("דיימלר קרייזלר").
    if len(words) > 1 and words[-1] in countries:
        base = words[:-1]
        while base and base[-1].endswith("."):  # "ד. קוריאה" — קיצור לפני הארץ
            base = base[:-1]
        return " ".join(base) or nm
    return nm


def makers(s) -> dict[int, dict]:
    rows = fetch_all(s, RID_MAKER, {}, "tozeret_cd,tozar,tozeret_nm,tozeret_eretz_nm")
    known = {(r.get("tozar") or "").strip() for r in rows} - {""}
    countries = ({(r.get("tozeret_eretz_nm") or "").strip() for r in rows} - {""}) | {"אנגליה", "קוריאה"}
    out = {}
    for r in rows:
        if r.get("tozeret_cd") is None:
            continue
        country = (r.get("tozeret_eretz_nm") or "").strip() or None
        brand = (r.get("tozar") or "").strip() or brand_from_name(r.get("tozeret_nm"), country, known, countries)
        out[r["tozeret_cd"]] = {"brand": brand, "country": country}
    return out


def price_list(s, years: range) -> dict[tuple, dict]:
    out = {}
    for y in years:
        for r in fetch_all(s, RID_PRICE, {"shnat_yitzur": y},
                           "sug_degem,tozeret_cd,degem_cd,shnat_yitzur,shem_yevuan,mehir"):
            key = (r.get("sug_degem"), r.get("tozeret_cd"), r.get("degem_cd"), r.get("shnat_yitzur"))
            out[key] = {"importer": importer_name(r.get("shem_yevuan")), "price": r.get("mehir")}
    return out


# --------------------------------------------------------------------------
# רישומים

def _months_back(n: int, today: date) -> list[tuple[int, int]]:
    y, m, out = today.year, today.month, []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def registrations(s, y: int, m: int, mk: dict, prices: dict, partial: bool) -> dict:
    recs = fetch_all(s, RID_REG, {"moed_aliya_lakvish": f"{y}-{m}"},
                     "baalut,sug_degem,tozeret_cd,degem_cd,shnat_yitzur,sug_delek_nm")
    cars = [r for r in recs if r.get("sug_degem") == "P"]
    own, fuel = Counter(), defaultdict(Counter)
    country, brand, importer = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    price, mapped, brand_country = defaultdict(list), 0, {}
    for r in cars:
        o = norm_owner(r.get("baalut"))
        own[o] += 1
        info = mk.get(r.get("tozeret_cd")) or {}
        if info.get("brand") and info.get("country"):
            brand_country.setdefault(info["brand"], info["country"])
        p = prices.get(("P", r.get("tozeret_cd"), r.get("degem_cd"), r.get("shnat_yitzur")))
        for key in (o, "all"):
            fuel[key][FUEL.get((r.get("sug_delek_nm") or "").strip(), "other")] += 1
            country[key][info.get("country") or "לא ידוע"] += 1
            brand[key][info.get("brand") or "לא ידוע"] += 1
            if p:
                importer[key][p["importer"]] += 1
                if p.get("price"):
                    price[key].append(p["price"])
        mapped += 1 if p else 0

    def top(c: Counter, n: int = TOP) -> list:
        return [[k, v] for k, v in c.most_common(n)]

    keys = [k for k in (*OWNERS, "אחר", "all") if own.get(k) or k == "all"]
    return {
        "month": f"{y:04d}-{m:02d}", "partial": partial,
        "computed_at": datetime.now(IL).isoformat(timespec="minutes"),
        "n_all": len(recs), "n": len(cars), "commercial": len(recs) - len(cars),
        "own": {k: own[k] for k in (*OWNERS, "אחר") if own.get(k)},
        "fuel": {k: dict(fuel[k]) for k in keys},
        "country": {k: top(country[k], 12) for k in keys},
        "brand": {k: top(brand[k]) for k in keys},
        "importer": {k: top(importer[k]) for k in keys},
        "importer_mapped": mapped,
        "brand_country": {b: c for b, c in brand_country.items()
                          if any(b == x for k in keys for x, _ in brand[k].most_common(TOP))},
        "price": {k: {"n": len(price[k]), "median": round(statistics.median(price[k])),
                      "mean": round(statistics.fmean(price[k]))}
                  for k in keys if price[k]},
    }


# --------------------------------------------------------------------------
# יציאות מהצי

def disposals(s, y: int, m: int, deadline: float) -> dict | None:
    """תקופות בעלות שהתחילו בחודש, והבעלות שקדמה להן. None — נגמר הזמן."""
    ym = y * 100 + m
    starts = fetch_all(s, RID_HIST, {"baalut_dt": ym}, "mispar_rechev,baalut")
    cars = sorted({r["mispar_rechev"] for r in starts if r.get("mispar_rechev") is not None})
    flows, held = Counter(), defaultdict(list)
    for i in range(0, len(cars), BATCH):
        if time.monotonic() > deadline:
            return None
        batch = cars[i:i + BATCH]
        hist = defaultdict(list)
        for r in fetch_all(s, RID_HIST, {"mispar_rechev": batch}, "mispar_rechev,baalut_dt,baalut"):
            hist[r["mispar_rechev"]].append((r.get("baalut_dt") or 0, norm_owner(r.get("baalut"))))
        for h in hist.values():
            h.sort()
            for k in range(1, len(h)):
                if h[k][0] != ym:
                    continue
                prev_dt, prev = h[k - 1]
                if prev in FLEET and h[k][1] != prev:
                    flows[f"{prev}>{h[k][1]}"] += 1
                    if prev_dt:
                        months = (ym // 100 - prev_dt // 100) * 12 + (ym % 100 - prev_dt % 100)
                        if 0 <= months <= 240:
                            held[prev].append(months)
    return {
        "month": f"{y:04d}-{m:02d}", "computed_at": datetime.now(IL).isoformat(timespec="minutes"),
        "starts": len(starts), "cars": len(cars), "flows": dict(flows),
        "held_median": {k: round(statistics.median(v)) for k, v in held.items() if v},
        "held_n": {k: len(v) for k, v in held.items()},
    }


# --------------------------------------------------------------------------

def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="נתוני רשם כלי הרכב לסעיף הליסינג")
    ap.add_argument("--budget-minutes", type=float, default=6.0)
    ap.add_argument("--force", action="store_true", help="גם אם כבר חושב היום")
    args = ap.parse_args()
    deadline = time.monotonic() + args.budget_minutes * 60
    today = datetime.now(IL).date()

    reg_p, disp_p = OUT / "registrations.json", OUT / "disposals.json"
    reg, disp = _load(reg_p), _load(disp_p)
    if not args.force and (reg.get("updated") or "")[:10] == today.isoformat() \
            and len(disp.get("months") or {}) >= DISPOSAL_MONTHS:
        print("רשם כלי הרכב: כבר חושב היום — מדלגים")
        _output(False)
        return 0

    s = creq.Session(impersonate="chrome")
    months = _months_back(MONTHS, today)
    done = reg.get("months") or {}
    todo = [(y, m) for k, (y, m) in enumerate(months)
            if k < REFRESH or f"{y:04d}-{m:02d}" not in done]
    try:
        mk = makers(s)
        years = sorted({y for y, _ in months})
        prices = price_list(s, range(years[0] - 1, years[-1] + 2))
    except RuntimeError as e:
        print(f"::warning title=רשם כלי הרכב לא נקרא::{e}")
        _output(False)
        return 0
    failures = []
    for y, m in todo:
        key = f"{y:04d}-{m:02d}"
        try:
            rec = registrations(s, y, m, mk, prices, partial=(y, m) == (today.year, today.month))
        except RuntimeError as e:
            failures.append(f"{key}: {e}")
            continue
        # חודש ישן שנכנס בפעם הראשונה: הבעלות בו כבר אינה זו של יום הרישום.
        age = (today.year - y) * 12 + today.month - m
        if key not in done and age >= REFRESH:
            rec["late"] = True
        done[key] = rec
    keep = {f"{y:04d}-{m:02d}" for y, m in months}
    reg = {"updated": datetime.now(IL).isoformat(timespec="minutes"),
           "source": "משרד התחבורה — רשם כלי הרכב, data.gov.il",
           "months": {k: done[k] for k in sorted(done) if k in keep}}
    _save(reg_p, reg)

    # יציאות מהצי: החודש הקודם (השלם האחרון) קודם, ואז אחורה — בתקציב הזמן.
    dmonths = _months_back(DISPOSAL_MONTHS + 1, today)[1:]
    ddone = disp.get("months") or {}
    pending = [(y, m) for k, (y, m) in enumerate(dmonths)
               if k == 0 or f"{y:04d}-{m:02d}" not in ddone]
    computed = 0
    for y, m in pending:
        if time.monotonic() > deadline:
            break
        try:
            rec = disposals(s, y, m, deadline)
        except RuntimeError as e:
            failures.append(f"יציאות {y}-{m}: {e}")
            continue
        if rec is None:
            break
        ddone[rec["month"]] = rec
        computed += 1
    dkeep = {f"{y:04d}-{m:02d}" for y, m in dmonths}
    disp = {"updated": datetime.now(IL).isoformat(timespec="minutes"),
            "source": "משרד התחבורה — היסטוריית כלי רכב פרטיים, data.gov.il",
            "months": {k: ddone[k] for k in sorted(ddone) if k in dkeep}}
    _save(disp_p, disp)

    last = reg["months"].get(max(k for k in reg["months"] if not reg["months"][k].get("partial"))) \
        if any(not v.get("partial") for v in reg["months"].values()) else None
    msg = f"::notice::רשם כלי הרכב: {len(todo)} חודשי רישום חושבו"
    if last:
        n, lease = last["n"], last["own"].get("ליסינג", 0)
        msg += f" · {last['month']}: {n:,} רכב פרטי חדש, ליסינג {lease:,} ({lease / n * 100:.1f}%)"
    msg += f" · יציאות מהצי: {computed} חודשים חושבו, {len(disp['months'])}/{DISPOSAL_MONTHS} בקובץ"
    print(msg)
    if failures:
        print("::warning title=רשם כלי הרכב — חלק מהחודשים לא נקראו::" + " · ".join(failures[:4]))
    _output(True)
    return 0


def _output(updated: bool) -> None:
    """updated=yes — יש מה לשמור ולפרוס גם כשלא נאספה כותרת חדשה."""
    import os
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"updated={'yes' if updated else 'no'}\n")


if __name__ == "__main__":
    sys.exit(main())
