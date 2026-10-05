# -*- coding: utf-8 -*-
"""מסירות רכב חדש לפי חודש — לסעיף "מסירות רכב חדש" בגיליון הרכב.

המקור: משרד התחבורה ב-data.gov.il, "כמות כלי רכב חדשים בעלי קוד דגם העולים על הכביש
בכל חודש" (602ac32d…) — שורה לכל תוצר ודגם בחודש, עם מספר הרכבים. המאגר מתעדכן פעם
בחודש, בימים הראשונים של החודש הבא, ומכסה עד החודש הקלנדרי הקודם.

**למה המאגר הזה ולא רשם כלי הרכב.** הרשם (ingest/auto_registry.py) הוא תמונת מצב של
הרכב הפעיל היום: רכב שירד מהכביש נעלם ממנו, ובעלות שהתחלפה נספרת לפי הבעלים החדש.
מאגר המסירות הוא ספירה של מה שעלה לכביש באותו חודש, והוא המקור למספרי "המסירות"
שמתפרסמים בכל חודש. ההפרש קטן (אוגוסט 2026: 28,287 רכב פרטי במסירות מול 28,234
ברשם), אבל למשפט "נמסרו X" המקור הנכון הוא זה.

שלושה חיבורים, כולם לפי (סוג דגם, קוד תוצר, קוד דגם):
  · היבואנית — ממחירון משרד התחבורה (39f455bf…), מהשנה האחרונה שבה הדגם מופיע. דגם
    שאין לו שורה במחירון מקבל את היבואנית הנפוצה של אותו קוד תוצר, וכמה כאלה היו —
    נשמר ב-importer_fallback.
  · המותג וארץ התוצר — מטבלת התוצרים, באותו קוד כמו בסעיף הליסינג.
  · סוג ההנעה — ממאגר הדגמים (WLTP, 142afde2…): חשמלי, פלאג-אין, היברידי, בנזין/דיזל.

**סוג הדגם קובע מה נספר.** P הוא רכב פרטי ו-M מסחרי עד 3.5 טון — שניהם יחד הם
"המסירות" שבטבלאות. "3" הוא דו-גלגלי (אופנועים וקטנועים: 2,092 בספטמבר 2026), והוא
נספר בנפרד: בריצה הראשונה, כשנספר כמסחרי, המסחרי קפץ פי ארבעה ו-1,867 רכבים נשארו
בלי יבואנית — אין להם שורה במחירון.

**חודש בלי שורות אינו חודש של אפס מסירות.** בימים הראשונים של החודש המאגר עוד לא
כולל את החודש שהסתיים; חודש כזה אינו נשמר, והוא ייכנס בריצה שאחרי העדכון.

פלט: output/auto/registry/deliveries.json
שימוש: python ingest/auto_deliveries.py [--force]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from auto_registry import (CKAN, IL, OUT, _load, _months_back, _save, fetch_all,  # noqa: E402
                           makers, price_list, source_links)
from curl_cffi import requests as creq  # noqa: E402

RID_DEL = "602ac32d-19c0-4b41-88e0-e3ce8a7e80b7"
RID_PRICE = "39f455bf-6db0-4926-859d-017f34eacbcb"
RID_WLTP = "142afde2-6228-49f9-8a29-9b6c3a0cbe40"
MONTHS = 25            # שנתיים ועוד חודש: השוואה שנתית לכל חודש בשנה האחרונה, ומתחילת השנה אשתקד
TOP_MODELS = 30
PATH = OUT / "deliveries.json"
# ארץ תוצר כשגם טבלת התוצרים וגם מאגר הדגמים ריקים בה. נמדד בספטמבר 2026: קיה
# (קוד 885, "קיה ד. קוריאה") — 999 רכבים — ו-KG מוביליטי, 160; בלי זה הם נספרו
# "לא ידוע" והחלק הקוריאני ירד ב-4.7 נקודות.
COUNTRY_HINTS = {"ד. קוריאה": "קוריאה הדרומית", "קיי גי מוביליט": "קוריאה הדרומית"}


def drive(delek: str | None, tech: str | None) -> str:
    """סוג ההנעה ממאגר הדגמים. הערכים נבדקו 05/10/2026 על שנות הדגם 2025–2027:
    'רכב חשמלי', 'PLUG IN', 'היברידי רגיל', 'הנעה רגילה' — ולצידם סוג הדלק."""
    d, t = (delek or "").strip(), (tech or "").strip()
    if d == "חשמל" or t == "רכב חשמלי":
        return "ev"
    if "PLUG" in t.upper():
        return "phev"
    if "היברידי" in t:
        return "hev"
    if d in ("בנזין", "דיזל"):
        return "ice"
    return "other"


def modified(s) -> str:
    try:
        r = s.get(f"{CKAN}/resource_show", params={"id": RID_DEL}, timeout=40).json().get("result") or {}
        return str(r.get("last_modified") or r.get("metadata_modified") or "")
    except Exception:  # noqa: BLE001
        return ""


def importer_maps(prices: dict) -> tuple[dict, dict]:
    """(סוג, תוצר, דגם) → היבואנית בשנת הדגם האחרונה; ותוצר → היבואנית הנפוצה שלו."""
    by_key: dict[tuple, tuple[int, str]] = {}
    by_maker: dict = defaultdict(Counter)
    for (sug, tcd, dcd, year), v in prices.items():
        name = v.get("importer")
        if not name:
            continue
        k = (sug, tcd, dcd)
        if k not in by_key or (year or 0) > by_key[k][0]:
            by_key[k] = (year or 0, name)
        by_maker[tcd][name] += 1
    return ({k: v[1] for k, v in by_key.items()},
            {t: c.most_common(1)[0][0] for t, c in by_maker.items()})


def model_map(s, years: list[int]) -> dict[tuple, dict]:
    """(סוג, תוצר, דגם) → סוג הנעה, ומותג וארץ תוצר מאותה שורה.

    המותג והארץ כאן הם גיבוי לטבלת התוצרים: בספטמבר 2026 היו 1,159 רכבים שלקוד
    התוצר שלהם אין שם ארץ, אף שהמותג עצמו ידוע — והם נספרו "לא ידוע" בחלק הסיני."""
    rows = fetch_all(s, RID_WLTP, {"shnat_yitzur": years},
                     "sug_degem,tozeret_cd,degem_cd,shnat_yitzur,delek_nm,technologiat_hanaa_nm,"
                     "tozar,tozeret_eretz_nm")
    best: dict[tuple, tuple[int, dict]] = {}
    for r in rows:
        k = (r.get("sug_degem"), r.get("tozeret_cd"), r.get("degem_cd"))
        y = r.get("shnat_yitzur") or 0
        if k not in best or y > best[k][0]:
            best[k] = (y, {"drive": drive(r.get("delek_nm"), r.get("technologiat_hanaa_nm")),
                           "brand": (r.get("tozar") or "").strip() or None,
                           "country": (r.get("tozeret_eretz_nm") or "").strip() or None})
    return {k: v[1] for k, v in best.items()}


def month(s, y: int, m: int, imp_key: dict, imp_maker: dict, mk: dict, dmap: dict) -> dict | None:
    recs = fetch_all(s, RID_DEL, {"sgira_month": y * 100 + m},
                     "sug_degem,tozeret_cd,tozeret_nm,degem_cd,kinuy_mishari,car_num")
    if not recs:
        return None
    tot: Counter = Counter()
    imp: dict = defaultdict(Counter)
    brand: dict = defaultdict(Counter)
    country: Counter = Counter()
    fuel: Counter = Counter()
    models: Counter = Counter()
    # ארץ התוצר של מותג — זו שממנה הגיעו רוב הרכבים שלו בחודש. "הראשונה שנמצאה" נתנה
    # בספטמבר 2026 קיה = סלובקיה וטויוטה = תאילנד.
    bcc: dict = defaultdict(Counter)
    fallback = unknown = 0
    moto: Counter = Counter()
    for r in recs:
        n = int(r.get("car_num") or 0)
        sug = r.get("sug_degem")
        info = mk.get(r.get("tozeret_cd")) or {}
        if sug not in ("P", "M"):
            tot["moto" if sug == "3" else "other"] += n
            if sug == "3":
                moto[info.get("brand") or "לא ידוע"] += n
            continue
        kind = "p" if sug == "P" else "m"
        key = (sug, r.get("tozeret_cd"), r.get("degem_cd"))
        tot[kind] += n
        name = imp_key.get(key)
        if not name:
            name = imp_maker.get(r.get("tozeret_cd"))
            if name:
                fallback += n
            else:
                name, unknown = "לא ידוע", unknown + n
        imp[name][kind] += n
        mdl = dmap.get(key) or {}
        b = info.get("brand") or mdl.get("brand") or "לא ידוע"
        ctry = info.get("country") or mdl.get("country") or next(
            (c for hint, c in COUNTRY_HINTS.items() if hint in (r.get("tozeret_nm") or "")), None)
        brand[b][kind] += n
        if ctry:
            bcc[b][ctry] += n
        country[ctry or "לא ידוע"] += n
        fuel[mdl.get("drive", "other")] += n
        if kind == "p":
            models[(b, " ".join((r.get("kinuy_mishari") or "").split()) or "—")] += n
    return {
        "month": f"{y:04d}-{m:02d}",
        "computed_at": datetime.now(IL).isoformat(timespec="minutes"),
        "p": tot["p"], "m": tot["m"], "n": tot["p"] + tot["m"],
        "moto": tot["moto"], "other": tot["other"],
        "moto_brand": [[b, n] for b, n in moto.most_common(10)],
        "importer": {k: dict(v) for k, v in sorted(imp.items(), key=lambda kv: -sum(kv[1].values()))},
        "brand": {k: dict(v) for k, v in sorted(brand.items(), key=lambda kv: -sum(kv[1].values()))},
        "brand_country": {b: c.most_common(1)[0][0] for b, c in bcc.items()},
        "country": dict(country.most_common()),
        "fuel": dict(fuel),
        "models": [[b, mdl, n] for (b, mdl), n in models.most_common(TOP_MODELS)],
        "importer_fallback": fallback, "importer_unknown": unknown,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="מסירות רכב חדש לפי חודש")
    ap.add_argument("--force", action="store_true", help="גם אם המאגר לא התעדכן מאז הריצה הקודמת")
    args = ap.parse_args()
    s = creq.Session(impersonate="chrome")
    cur = _load(PATH)
    mod = modified(s)
    today = datetime.now(IL).date()
    wanted = _months_back(MONTHS + 1, today)[1:]          # בלי החודש הנוכחי: עוד אין לו נתונים
    have = cur.get("months") or {}
    newest = f"{wanted[0][0]:04d}-{wanted[0][1]:02d}"
    if not args.force and mod and cur.get("source_modified") == mod and have:
        print(f"מסירות רכב: המאגר לא התעדכן מאז {mod[:16]} — מדלגים")
        _output(False)
        return 0

    try:
        mk = makers(s)
        years = sorted({y for y, _ in wanted})
        prices = price_list(s, range(years[0] - 1, years[-1] + 2))
        imp_key, imp_maker = importer_maps(prices)
        dmap = model_map(s, list(range(years[0] - 1, years[-1] + 2)))
    except RuntimeError as e:
        print(f"::warning title=מסירות רכב — טבלאות העזר לא נקראו::{e}")
        _output(False)
        return 0

    months, failures, empty = {}, [], []
    for y, m in wanted:
        key = f"{y:04d}-{m:02d}"
        try:
            rec = month(s, y, m, imp_key, imp_maker, mk, dmap)
        except RuntimeError as e:
            failures.append(f"{key}: {e}")
            if key in have:
                months[key] = have[key]       # חודש שכבר חושב אינו נמחק בגלל תקלה
            continue
        if rec is None:
            empty.append(key)
            continue
        months[key] = rec
    out = {"updated": datetime.now(IL).isoformat(timespec="minutes"),
           "source_modified": mod,
           "source": "משרד התחבורה — כמות כלי רכב חדשים העולים על הכביש בכל חודש, data.gov.il",
           "links": source_links(s, {"מסירות רכב חדש לפי חודש": RID_DEL,
                                     "מחירון היבואנים": RID_PRICE,
                                     "דגמי רכב (WLTP)": RID_WLTP}),
           "months": {k: months[k] for k in sorted(months)}}
    _save(PATH, out)

    keys = sorted(out["months"])
    msg = f"::notice::מסירות רכב: {len(keys)} חודשים"
    if keys:
        last = out["months"][keys[-1]]
        ya = out["months"].get(f"{int(keys[-1][:4]) - 1}{keys[-1][4:]}") or {}
        msg += f" · {keys[-1]}: {last['n']:,} (פרטי {last['p']:,}, מסחרי {last['m']:,})"
        if ya.get("n"):
            msg += f", מול {ya['n']:,} אשתקד"
        msg += f" · יבואנית לפי תוצר: {last['importer_fallback']:,}, לא ידועה: {last['importer_unknown']:,}"
    if empty and empty[0] == newest:
        msg += f" · {newest} עוד לא במאגר"
    print(msg)
    if failures:
        print("::warning title=מסירות רכב — חלק מהחודשים לא נקראו::" + " · ".join(failures[:4]))
    _output(True)
    return 0


def _output(updated: bool) -> None:
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"deliveries={'yes' if updated else 'no'}\n")


if __name__ == "__main__":
    sys.exit(main())
