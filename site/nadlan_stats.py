# -*- coding: utf-8 -*-
"""מנוע הניתוח של שוק הדיור. חישוב בלבד — הרינדור ב-nadlan.py.

ארבע הכרעות שמפרידות בין טבלת חציונים לבין ניתוח:

**רק דירות מגורים.** הסריקה מחזירה גם קרקע, בניינים שלמים, חנויות
ומשרדים. עסקת קרקע ב-4 ₪ למ״ר ובניין ב-91 מיליון ₪ למ״ר באותו חציון
עם דירה אינם רעש — הם הופכים את המספר לחסר משמעות.

**רבעונים ולא חודשים.** בעיר בינונית נסגרות 3–5 עסקאות בחודש בשכונות
שנסרקות. חציון של שלוש עסקאות אינו מגמה אלא הגרלה; ברבעון המדגם
גדול פי שלושה ויציב.

**חלון השוואה קבוע.** "מתחילת החלון עד סופו" משתנה בכל יום שעובר, גם
כשהשוק לא זז. כאן ההשוואה היא תמיד הרבעון המלא האחרון — מול הרבעון
שלפניו, ומול אותו רבעון בשנה שעברה.

**אפקט תמהיל.** חציון ₪/מ״ר בעיר יכול לעלות בלי שאף דירה התייקרה, אם
נמכרו יותר דירות חדשות או גדולות. לכן כל שינוי מחושב **גם על יד שנייה
בלבד**, והפער בין השניים נאמר במפורש כשהוא גדול.

ומעל הכול: דיווח רשות המסים מפגר כשישה שבועות. החודשים האחרונים מוסרים
מהחישוב במקום להיות מוצגים מוחלשים.
"""
import statistics
from collections import defaultdict
from datetime import date, timedelta

LAG_MONTHS = 2
MIN_SAMPLE = 8
# מינימום עסקאות ברבעון כדי שהרבעון ייכנס לסדרת המגמה.
MIN_QUARTER = 8
# מינימום עסקאות בחודש לנקודה בגרף הזעיר. הגרף ממחיש צורה, לא מודד.
MIN_MONTH = 4
# פער בין המגמה הכוללת למגמת יד שנייה שמעליו התמהיל הוא ההסבר.
MIX_GAP = 4.0
# טווח ₪/מ״ר שמחוצה לו הרשומה היא שגיאת מקור ולא דירה יקרה או זולה.
PPSM_MIN, PPSM_MAX = 3_000, 150_000

# סיווגים שאינם דיור. עסקת קרקע או בניין שלם נכנסת לאותה סריקה.
NON_RES_TYPE = {"קרקע", "בנין", "בניין", "משק חקלאי", "מגרש"}
NON_RES_NATURE = {"חנות", "משרד", "מחסן", "חניה", "קרקע למגורים", "ללא תיכנון",
                  "תעשיה", "מלאכה", "מבנה מסחרי", "מחסנים"}


def residential(r: dict) -> bool:
    """דירת מגורים בלבד.

    **עסקאות מקבלן מגיעות בלי סיווג כלל** — Govmap אינו ממלא סוג נכס
    בענף העסקאות החדשות. סינון תמים לפי "סוג נכס = דירה" היה מוחק את
    כולן (2,680 רשומות, 100% מעסקאות הקבלן) ומרוקן מתוכן את ההשוואה
    בין קבלן ליד שנייה שכל העמוד בנוי עליה. לכן רשומה בלי סיווג עם
    חדרים ושטח נחשבת דירה.
    """
    t = (r.get("property_type") or "").strip()
    n = (r.get("nature") or "").strip()
    if t in NON_RES_TYPE or n in NON_RES_NATURE:
        return False
    if t == "דירה" or "דירה" in n or "קוטג" in n or "משפחתי" in n or "פנטהאוז" in n:
        return True
    return not t and not n and bool(r.get("rooms")) and bool(r.get("area_sqm"))


def clean_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    """הרשומות שמותר לחשב עליהן, ומה נפסל — כדי שייאמר בעמוד."""
    res = [r for r in rows if residential(r)]
    ok = [r for r in res
          if PPSM_MIN <= (r.get("price_per_sqm") or 0) <= PPSM_MAX]
    return ok, {
        "total": len(rows),
        "non_residential": len(rows) - len(res),
        "out_of_band": len(res) - len(ok),
        "kept": len(ok),
    }


def months_back(n: int) -> str:
    d = date.today().replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d.isoformat()[:7]


def cutoff_month() -> str:
    return months_back(LAG_MONTHS)


def quarter_of(iso: str) -> str:
    return f"{iso[:4]}-Q{(int(iso[5:7]) - 1) // 3 + 1}"


def quarter_back(n: int) -> str:
    """הרבעון המלא האחרון הוא 0; כל צעד אחורה הוא רבעון.

    **"מלא" פירושו ששלושת חודשיו נמצאים בתוך החלון**, ולא שהוא הרבעון
    שבו נופל החודש האחרון. עם חתך ביוני, הרבעון השני מכיל אפריל ומאי
    בלבד — ואז השוואת היקפים מולו מציגה ירידה של כ-50% בכל עיר, שהיא
    חודש חסר ולא ביקוש.
    """
    cut = cutoff_month()
    y, mm = int(cut[:4]), int(cut[5:7])
    q = (mm - 1) // 3 + 1
    # חודש הסיום של הרבעון הזה; אם אינו לפני החתך, הרבעון אינו מלא.
    if q * 3 >= mm:
        q -= 1
    q -= n
    while q < 1:
        q += 4
        y -= 1
    return f"{y}-Q{q}"


def med(vals):
    vals = [v for v in vals if v]
    return round(statistics.median(vals)) if vals else None


def pct_change(new, old):
    if not new or not old:
        return None
    return round((new / old - 1) * 100, 1)


def quarterly(deals, key="price_per_sqm") -> dict:
    q = defaultdict(list)
    for d in deals:
        if d.get(key):
            q[quarter_of(d["date"])].append(d[key])
    return {k: med(v) for k, v in sorted(q.items()) if len(v) >= MIN_QUARTER}


def monthly(deals, key="price_per_sqm") -> dict:
    m = defaultdict(list)
    for d in deals:
        if d.get(key):
            m[d["date"][:7]].append(d[key])
    return {k: med(v) for k, v in sorted(m.items()) if len(v) >= MIN_MONTH}


def classify(qoq, yoy):
    """קריאה במילים, מהצירוף של הרבעוני והשנתי ולא מאחד מהם."""
    if yoy is None:
        return "אין די נתונים", "אין רבעון מקביל בשנה שעברה עם מדגם מספיק"
    if qoq is None:
        return ("עלה השנה" if yoy > 2 else "ירד השנה" if yoy < -2 else "יציב"), \
            "אין רבעון קודם להשוואה"
    if yoy > 2 and qoq > 1:
        return "עולה", "גם מול השנה שעברה וגם מול הרבעון הקודם"
    if yoy > 2 and qoq < -1:
        return "עלה והתהפך", "מעל השנה שעברה, אך הרבעון האחרון ירד"
    if yoy > 2:
        return "עולה ומתמתן", "מעל השנה שעברה, בקצב שנעצר ברבעון האחרון"
    if yoy < -2 and qoq < -1:
        return "יורד", "גם מול השנה שעברה וגם מול הרבעון הקודם"
    if yoy < -2:
        return "ירד ומתייצב", "מתחת לשנה שעברה, אך הרבעון האחרון לא ירד"
    return "יציב", "השינוי השנתי בתוך ±2%"


def rooms_bucket(r) -> str | None:
    n = r.get("rooms")
    if not n:
        return None
    if n <= 3:
        return "עד 3 חדרים"
    if n <= 4:
        return "4 חדרים"
    if n <= 5:
        return "5 חדרים"
    return "6 חדרים ומעלה"


ROOM_ORDER = ("עד 3 חדרים", "4 חדרים", "5 חדרים", "6 חדרים ומעלה")


def trend_pair(series: dict):
    """(רבעוני, שנתי) מול הרבעון המלא האחרון שיש לו נתון."""
    q0 = quarter_back(0)
    if q0 not in series:
        return None, None, None
    return (series[q0],
            pct_change(series[q0], series.get(quarter_back(1))),
            pct_change(series[q0], series.get(quarter_back(4))))


def city_stats(rows: list[dict]) -> dict:
    cut = cutoff_month()
    by_city = defaultdict(list)
    for r in rows:
        by_city[r["city"]].append(r)

    out = {}
    for city, deals in by_city.items():
        full = [d for d in deals if (d.get("date") or "")[:7] < cut]
        if not full:
            continue
        new = [d for d in full if d.get("is_new")]
        used = [d for d in full if not d.get("is_new")]

        qs = quarterly(full)
        level, qoq, yoy = trend_pair(qs)
        _, _, used_yoy = trend_pair(quarterly(used))

        def in_quarter(n):
            q = quarter_back(n)
            return [d for d in full if quarter_of(d["date"]) == q]

        now, prev = in_quarter(0), in_quarter(1)
        share_new = round(sum(1 for d in now if d.get("is_new")) / len(now) * 100) \
            if now else None
        share_prev = round(sum(1 for d in prev if d.get("is_new")) / len(prev) * 100) \
            if prev else None

        ppsm_new = med([d.get("price_per_sqm") for d in new])
        ppsm_used = med([d.get("price_per_sqm") for d in used])

        by_rooms = {}
        for b in ROOM_ORDER:
            sel = [d.get("price_per_sqm") for d in full if rooms_bucket(d) == b]
            if len([v for v in sel if v]) >= MIN_SAMPLE:
                by_rooms[b] = med(sel)

        hoods = defaultdict(list)
        for d in full:
            if d.get("neighborhood"):
                hoods[d["neighborhood"]].append(d)

        label, why = classify(qoq, yoy)
        out[city] = {
            "region": deals[0].get("region"),
            "n": len(full), "n_new": len(new), "n_used": len(used),
            "ppsm": med([d.get("price_per_sqm") for d in full]),
            "ppsm_new": ppsm_new, "ppsm_used": ppsm_used,
            "premium_new": pct_change(ppsm_new, ppsm_used),
            "price": med([d.get("amount") for d in full]),
            "area": med([d.get("area_sqm") for d in full]),
            "series": monthly(full), "quarters": qs,
            "level": level, "qoq": qoq, "yoy": yoy, "used_yoy": used_yoy,
            "share_new": share_new, "share_new_prev": share_prev,
            "vol": len(now), "vol_prev": len(prev),
            "vol_change": pct_change(len(now), len(prev)) if prev else None,
            "by_rooms": by_rooms,
            "hoods": sorted(
                ({"name": h, "n": len(v),
                  "ppsm": med([x.get("price_per_sqm") for x in v]),
                  "new": sum(1 for x in v if x.get("is_new"))}
                 for h, v in hoods.items() if len(v) >= MIN_SAMPLE),
                key=lambda x: -x["n"]),
            "label": label, "why": why,
            "mix_flag": (yoy is not None and used_yoy is not None
                         and abs(yoy - used_yoy) >= MIX_GAP),
            "thin": len(now) < MIN_SAMPLE,
        }
    return out


def market(rows: list[dict], st: dict) -> dict:
    """מצרף על פני הערים — ולא חציון מאוחד של כל העסקאות.

    חציון מאוחד נשלט בתמהיל הערים ולא במחירים: אם ברבעון האחרון נסגרו
    יחסית יותר עסקאות בפריפריה, החציון הארצי יורד גם כשכל עיר עלתה.
    נמדד: הפער בין השניים היה 20 נקודות אחוז, בכיוונים הפוכים. לכן
    השינוי המצרפי הוא **חציון השינויים של הערים** — עיר אחת, קול אחד —
    והרמה המוצגת היא זו של העיר החציונית ולא של "הארץ".
    """
    cut = cutoff_month()
    full = [d for d in rows if (d.get("date") or "")[:7] < cut]

    usable = [(c, v) for c, v in st.items()
              if v["yoy"] is not None and not v["thin"]]
    yoys = [v["yoy"] for _, v in usable]
    qoqs = [v["qoq"] for _, v in usable if v["qoq"] is not None]
    used = [v["used_yoy"] for _, v in usable if v["used_yoy"] is not None]
    levels = [v["level"] for _, v in usable if v["level"]]

    def median_of(vals):
        return round(statistics.median(vals), 1) if vals else None

    yoy, qoq = median_of(yoys), median_of(qoqs)
    label, why = classify(qoq, yoy)

    ranked = sorted(usable, key=lambda kv: -kv[1]["yoy"])
    by_region = defaultdict(list)
    for c, v in usable:
        by_region[v["region"]].append((c, v))

    return {
        "n": len(full), "series": monthly(full),
        "panel": len(usable),
        "level": round(statistics.median(levels)) if levels else None,
        "qoq": qoq, "yoy": yoy, "used_yoy": median_of(used),
        "rising": sum(1 for v in yoys if v > 2),
        "falling": sum(1 for v in yoys if v < -2),
        "flat": sum(1 for v in yoys if -2 <= v <= 2),
        "label": label, "why": why,
        "cities": len(st),
        "q_now": quarter_back(0), "q_prev": quarter_back(1), "q_yoy": quarter_back(4),
        "share_new": (round(sum(1 for d in full if d.get("is_new")) / len(full) * 100)
                      if full else None),
        "span": (min((d["date"] for d in full), default=""),
                 max((d["date"] for d in full), default="")),
        "leaders": ranked[:5], "laggards": ranked[-5:][::-1],
        "by_region": by_region,
        "mix_cities": [c for c, v in st.items() if v["mix_flag"]],
    }
