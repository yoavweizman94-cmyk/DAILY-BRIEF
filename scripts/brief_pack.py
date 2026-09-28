# -*- coding: utf-8 -*-
"""מכין לסוכן קלט מעוכל במקום קבצי השנה הגולמיים.

**למה זה קיים.** הברייף הוא הקריאה היקרה בצנרת, ורוב עלותו אינה החשיבה
אלא הקלט: `output/nadlan/<שנה>.jsonl` לבדו הוא 2.1MB — 5,717 עסקאות —
והוא גדול פי שניים וחצי מכל שאר הקלט יחד. הסוכן נשלח אליו כדי לכתוב
סעיף אחד על מגמת מחירים, בעוד בדיוק אותם חישובים כבר נעשים ב-
`site/nadlan_stats.py` עבור האתר. אותו דבר בעסקאות מחוץ לבורסה: הוא
צריך את היום, ומקבל את השנה.

נמדד 28/09/2026: מהדורה ב-Sonnet נקטעה בתקרה של $4 אחרי $4.39 בלי
להשלים, ומהדורה באופוס ב-$6. מיליון טוקן של קלט אינם נקראים פעם אחת —
הם נשלחים מחדש בכל תור.

מה שנוצר כאן נכתב ל-`data/raw/<תאריך>/pack/`, שהוא ממילא מחוץ לגיט:

  nadlan.json      תמונת שוק הדיור — מצרף, ערים, שכונות — מ-nadlan_stats
  otc.jsonl        עסקאות מחוץ לבורסה של הימים האחרונים בלבד
  offex.jsonl      דיווחי מאיה על עסקאות בעלי עניין, אותו חלון
  jumbo.jsonl      עסקאות מתואמות, אותו חלון
  companies.json   רשימת הכיסוי בלי שדות שאינם משמשים לכתיבה

**הדיגסט אינו מקצר את הניתוח, רק את הקריאה.** כל מה ש-CLAUDE.md דורש
מסעיף שוק הדיור — השוואה רבעונית, יד שנייה בנפרד, תמהיל מקבלן, ערים
חסרות — נמצא כאן מחושב. מה שאינו נמצא כאן (עסקה בודדת, כתובת) לא היה
אמור להיכתב בברייף ממילא.

שימוש: python scripts/brief_pack.py <תאריך> [ימים אחורה]
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))

# חלון ברירת המחדל: ארבעה ימים. הברייף צריך את היום, אבל במהדורת בוקר
# "היום" עוד ריק, ואחרי סוף שבוע היום האחרון שנסחר הוא לפני שלושה ימים.
WINDOW_DAYS = 4

# שכונות: שלוש הגדולות בכל עיר מספיקות לאייטם. הזנב הוא רעש שנשלח בכל תור.
TOP_HOODS = 3
# רבעונים: ארבעה אחרונים — מהם נגזרות ההשוואות רבעון-לרבעון ושנה-לשנה.
KEEP_QUARTERS = 5

# שדות שאינם משמשים לכתיבת הברייף. tase_id ו-maya_company_id משמשים את
# סקריפטי ה-ingest, לא את הסוכן; הוא מזהה חברות בשם ומקשר דרך maya.jsonl.
COMPANY_DROP = ("tase_id", "maya_company_id", "listing")


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _recent(rows: list[dict], since: str, *fields: str) -> list[dict]:
    """שומר רשומות שאחד משדות התאריך שלהן בתוך החלון.

    רשומה בלי תאריך כלל נשמרת: עדיף אייטם מיותר על אייטם שנמחק בשקט.
    """
    keep = []
    for r in rows:
        stamps = [str(r.get(f) or "")[:10] for f in fields]
        stamps = [s for s in stamps if s]
        if not stamps or max(stamps) >= since:
            keep.append(r)
    return keep


def nadlan_digest() -> dict | None:
    """תמונת שוק הדיור — בדיוק החישובים שהאתר מציג, בלי העסקאות עצמן."""
    try:
        import nadlan  # noqa: PLC0415
        import nadlan_stats as ns  # noqa: PLC0415
    except Exception as ex:  # noqa: BLE001
        print(f"  שוק הדיור: המודול לא נטען ({ex})")
        return None

    rows = nadlan.load()
    if not rows:
        return None
    clean, dropped = ns.clean_rows(rows)
    st = ns.city_stats(clean)
    mk = ns.market(clean, st)

    cities = {}
    for city, v in st.items():
        q = dict(sorted(v.get("quarters", {}).items())[-KEEP_QUARTERS:])
        cities[city] = {
            k: v[k] for k in (
                "region", "n", "n_new", "n_used", "ppsm", "ppsm_new", "ppsm_used",
                "premium_new", "price", "area", "level", "qoq", "yoy", "used_yoy",
                "share_new", "share_new_prev", "vol", "vol_prev", "vol_change",
                "label", "why", "mix_flag", "thin", "by_rooms",
            ) if k in v
        }
        cities[city]["quarters"] = q
        cities[city]["hoods"] = v.get("hoods", [])[:TOP_HOODS]

    state = {}
    try:
        state = json.loads((ROOT / "data" / "nadlan_state.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass

    return {
        "מקור": "output/nadlan/<שנה>.jsonl — מחושב ב-site/nadlan_stats.py",
        "סייגים": [
            "רשות המסים מדווחת כשישה שבועות אחרי העסקה; החודשיים האחרונים חסומים "
            f"מהחישוב ({ns.LAG_MONTHS} חודשים) ואין לכתוב עליהם ירידה בהיקפים",
            "הסריקה מכסה כמה שכונות בכל עיר — 'בשכונות שנסרקו' ולא 'בעיר'",
            "ההשוואה רבעונית; רבעון חסר חודש מראה ירידה של ~50% בהיקפים",
            "עיר ב-failed/empty אינה עיר שקטה ואינה אייטם",
        ],
        "מצרף": {k: v for k, v in mk.items()
                 if k not in ("series", "by_region", "leaders", "laggards")},
        "מובילות": [[c, v["yoy"]] for c, v in mk.get("leaders", [])],
        "מפגרות": [[c, v["yoy"]] for c, v in mk.get("laggards", [])],
        "ערים": cities,
        "נוקו": dropped,
        "ערים_ללא_עסקאות": {
            "failed": sorted((state.get("failed") or {}) if isinstance(state.get("failed"), dict)
                             else state.get("failed") or []),
            "empty": sorted((state.get("empty") or {}) if isinstance(state.get("empty"), dict)
                            else state.get("empty") or []),
        },
    }


def companies_slim() -> str | None:
    """רשימת הכיסוי כטבלת טקסט — הסוכן מזהה בשם, לא ב-id.

    ה-YAML נושא מזהי מסחר, סיווג בורסה והזחות; מה שנדרש לכתיבה הוא שם,
    כינויים, סקטור ודרייברים. הטבלה נקראת באותה קלות ותופסת שליש.
    """
    try:
        import yaml  # noqa: PLC0415
        cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    except Exception as ex:  # noqa: BLE001
        print(f"  כיסוי: לא נטען ({ex})")
        return None

    comps = cfg.get("companies", [])
    lines = [f"# רשימת הכיסוי — {len(comps)} חברות. מקור: config/companies.yaml",
             "# שם | אנגלית | כינויים | סקטור | דרייברים נוספים | גנרי=התאמה רק בהקשר עסקי",
             ""]
    for c in comps:
        lines.append(" | ".join((
            str(c.get("name_he") or ""),
            str(c.get("name_en") or ""),
            ",".join(c.get("aliases") or []),
            str(c.get("sector") or ""),
            ",".join(c.get("drivers_extra") or []),
            "גנרי" if c.get("generic_name") else "",
        )).rstrip(" |"))

    lines += ["", "# פרופילי סקטור — לאיזה דרייבר כל סקטור חשוף", ""]
    for key, p in (cfg.get("sector_profiles") or {}).items():
        lines.append(f"{key} | {p.get('label', '')} | {', '.join(p.get('drivers') or [])}")

    lines += ["", "# קטלוג דרייברים — תיאור ומקור נתונים", ""]
    for key, d in (cfg.get("drivers_catalog") or {}).items():
        lines.append(f"{key} | {d.get('desc', '')} | {d.get('source', '')}")

    return "\n".join(lines) + "\n"


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    window = int(sys.argv[2]) if len(sys.argv) > 2 else WINDOW_DAYS
    since = (date.fromisoformat(day) - timedelta(days=window)).isoformat()

    out = ROOT / "data" / "raw" / day / "pack"
    out.mkdir(parents=True, exist_ok=True)
    year = day[:4]
    saved = written = 0

    def dump(name: str, payload) -> None:
        nonlocal written
        path = out / name
        if isinstance(payload, list):
            text = "\n".join(json.dumps(r, ensure_ascii=False) for r in payload) + "\n"
        else:
            text = json.dumps(payload, ensure_ascii=False, indent=1)
        path.write_text(text, encoding="utf-8")
        written += len(text.encode("utf-8"))

    # שוק הדיור — הקובץ הגדול בצנרת, ומה שהסוכן צריך ממנו הוא טבלה
    src = ROOT / "output" / "nadlan" / f"{year}.jsonl"
    dig = nadlan_digest()
    if dig:
        saved += src.stat().st_size if src.exists() else 0
        dump("nadlan.json", dig)
        print(f"  שוק הדיור: {len(dig['ערים'])} ערים, {dig['מצרף'].get('n')} עסקאות בחישוב")

    # שלושת מקורות העסקאות — היום ולא השנה
    for name, fields in (("otc", ("date", "traded_at")),
                         ("offex", ("date", "published")),
                         ("jumbo", ("date",))):
        src = ROOT / "output" / name / f"{year}.jsonl"
        rows = _rows(src)
        if not src.exists():
            continue
        keep = _recent(rows, since, *fields)
        saved += src.stat().st_size
        dump(f"{name}.jsonl", keep)
        print(f"  {name}: {len(keep)} מתוך {len(rows)} רשומות מאז {since}")

    comps = companies_slim()
    if comps:
        saved += (ROOT / "config" / "companies.yaml").stat().st_size
        dump("companies.txt", comps)

    if saved:
        print(f"  קלט מעוכל: {written // 1024}KB במקום {saved // 1024}KB "
              f"({100 - written * 100 // max(saved, 1)}% פחות)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
