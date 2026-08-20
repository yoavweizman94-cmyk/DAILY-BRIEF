"""עמוד תמונת המצב של עסקאות הנדל"ן.

הנתונים נאספים ב-ingest/nadlan_pull.py מ-Govmap (דיווחי רשות המסים).
כאן רק חישוב ורינדור.

שלושה סייגים שמעצבים את כל העמוד ולכן נאמרים בו במפורש:

· **פיגור דיווח.** רשות המסים מדווחת כשישה שבועות אחרי מועד העסקה,
  ולכן החודשיים האחרונים תמיד נראים חלשים. חודש חלקי מסומן ואינו
  נכנס לחישוב המגמה.
· **מדגם ולא מפקד.** הסריקה מכסה כמה שכונות מרכזיות בכל עיר, לא את
  כולה. המספרים הם אינדיקציה למגמה, לא היקף המסחר בעיר.
· **שם היזם אינו בנתוני העסקה.** הוא מוצלב ממקור נפרד לפי עיר ושכונה,
  ולכן הוא מועמד ולא ייחוס.
"""
import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REGIONS = [("dan", "גוש דן"), ("south", "דרום"), ("north", "צפון")]

# חודשיים אחרונים חלקיים בגלל פיגור הדיווח, ולכן אינם נכנסים למגמה.
LAG_MONTHS = 2
# מתחת לזה חציון הוא רעש ולא מגמה.
MIN_SAMPLE = 8


def load() -> list[dict]:
    src = ROOT / "output" / "nadlan"
    if not src.is_dir():
        return []
    rows = []
    for f in sorted(src.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("date") or "")
    return rows


def cutoff_month() -> str:
    d = date.today().replace(day=1)
    for _ in range(LAG_MONTHS):
        d = (d - timedelta(days=1)).replace(day=1)
    return d.isoformat()[:7]


def med(vals):
    vals = [v for v in vals if v]
    return round(statistics.median(vals)) if vals else None


def city_stats(rows: list[dict]) -> dict:
    """סטטיסטיקה לכל עיר, על חודשים מלאים בלבד."""
    cut = cutoff_month()
    by_city = defaultdict(list)
    for r in rows:
        by_city[r["city"]].append(r)

    out = {}
    for city, deals in by_city.items():
        full = [d for d in deals if (d.get("date") or "")[:7] < cut]
        new = [d for d in full if d.get("is_new")]
        used = [d for d in full if not d.get("is_new")]
        months = defaultdict(list)
        for d in full:
            if d.get("price_per_sqm"):
                months[d["date"][:7]].append(d["price_per_sqm"])
        series = {m: med(v) for m, v in sorted(months.items()) if len(v) >= 3}

        trend = None
        if len(series) >= 6:
            keys = list(series)
            recent = med([series[k] for k in keys[-3:]])
            older = med([series[k] for k in keys[:3]])
            if recent and older:
                trend = round((recent - older) / older * 100, 1)

        out[city] = {
            "region": deals[0].get("region"),
            "n": len(full),
            "n_new": len(new),
            "n_used": len(used),
            "ppsm": med([d.get("price_per_sqm") for d in full]),
            "ppsm_new": med([d.get("price_per_sqm") for d in new]),
            "ppsm_used": med([d.get("price_per_sqm") for d in used]),
            "price": med([d.get("amount") for d in full]),
            "rooms": med([d.get("rooms") for d in full]),
            "trend": trend,
            "series": series,
            "thin": len(full) < MIN_SAMPLE,
        }
    return out


def num(v) -> str:
    """מספר עם מפרידי אלפים, או מקף. עדיף על ביטוי מקונן בתוך f-string."""
    return f"{v:,}" if v else "—"


def money(v) -> str:
    if not v:
        return "—"
    if v >= 1_000_000:
        return f"{v / 1_000_000:,.2f} מ׳"
    return f"{v:,.0f}"


def spark(series: dict, width: int = 60, height: int = 18) -> str:
    """קו מגמה זעיר. הצורה היא המידע — המספר המדויק כבר בעמודה שלידו."""
    vals = list(series.values())
    if len(vals) < 3:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = width / (len(vals) - 1)
    pts = " ".join(
        f"{round(i * step, 1)},{round(height - (v - lo) / rng * height, 1)}"
        for i, v in enumerate(vals))
    up = vals[-1] >= vals[0]
    return (f'<svg class="spark {"up" if up else "down"}" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" '
            f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>')


def page(rows: list[dict]) -> str:
    if not rows:
        return ('<div class="dash-head"><h1>עסקאות נדל"ן</h1></div>'
                '<p class="lead">טרם נאספו עסקאות. הסריקה רצה בכל בוקר.</p>')

    st = city_stats(rows)
    cut = cutoff_month()
    full = [r for r in rows if (r.get("date") or "")[:7] < cut]
    n_new = sum(1 for r in full if r.get("is_new"))
    span = f'{rows[0]["date"][:7]} – {cut}'

    out = [
        '<div class="dash-head"><h1>עסקאות נדל"ן — תמונת מצב</h1>',
        f'<span class="stamp">{span} · נבנה {datetime.now():%d/%m %H:%M}</span></div>',
        '<p class="lead">חציוני מחיר והיקפי עסקאות בגוש דן, בדרום ובצפון, '
        'בחלוקה בין רכישה <strong>מקבלן</strong> לבין <strong>יד שנייה</strong>. '
        'המקור הוא דיווחי רשות המסים דרך Govmap, וההבחנה בין השניים מגיעה '
        'מהמקור עצמו.</p>',
        '<p class="lead"><strong>שני סייגים שקובעים איך לקרוא את הטבלה:</strong> '
        f'הדיווח מפגר כשישה שבועות אחרי מועד העסקה, ולכן {LAG_MONTHS} החודשים '
        'האחרונים אינם נכללים כאן — הם היו נראים כצניחה שהיא רק פיגור. '
        'והסריקה מכסה כמה שכונות מרכזיות בכל עיר ולא את כולה, כך שהמספרים '
        'הם אינדיקציה למגמה ולא היקף המסחר בעיר.</p>',
        '<section class="strip">',
        f'<div class="tile"><span class="lbl">עסקאות בחלון</span>'
        f'<span class="val" dir="ltr">{len(full):,}</span>'
        f'<span class="chg">חודשים מלאים בלבד</span></div>',
        f'<div class="tile"><span class="lbl">מהן מקבלן</span>'
        f'<span class="val" dir="ltr">{round(n_new / len(full) * 100) if full else 0}%</span>'
        f'<span class="chg">{n_new:,} עסקאות</span></div>',
        f'<div class="tile"><span class="lbl">ערים</span>'
        f'<span class="val" dir="ltr">{len(st)}</span>'
        f'<span class="chg">בשלושה אזורים</span></div>',
        '</section>',
    ]

    for key, label in REGIONS:
        cities = {c: v for c, v in st.items() if v["region"] == key}
        if not cities:
            continue
        order = sorted(cities.items(), key=lambda kv: -(kv[1]["ppsm"] or 0))
        out.append(f'<h2>{label}</h2>')
        out.append('<div class="tw"><table class="nadlan"><thead><tr>'
                   '<th>עיר</th><th>עסקאות</th><th>מקבלן</th>'
                   '<th>חציון ₪/מ״ר</th><th>מקבלן</th><th>יד שנייה</th>'
                   '<th>חציון עסקה</th><th>מגמה</th></tr></thead><tbody>')
        for city, v in order:
            share = round(v["n_new"] / v["n"] * 100) if v["n"] else 0
            t = v["trend"]
            tcls = "flat" if t is None else ("up" if t > 0 else "down")
            ttxt = "—" if t is None else f'{"+" if t > 0 else ""}{t}%'
            thin = ('<span class="thin" title="מדגם קטן מדי למגמה">מדגם דק</span>'
                    if v["thin"] else "")
            out.append(
                f'<tr><td class="city">{city}{thin}</td>'
                f'<td dir="ltr">{v["n"]:,}</td>'
                f'<td dir="ltr">{share}%</td>'
                f'<td class="key" dir="ltr">{num(v["ppsm"])}</td>'
                f'<td dir="ltr">{num(v["ppsm_new"])}</td>'
                f'<td dir="ltr">{num(v["ppsm_used"])}</td>'
                f'<td dir="ltr">{money(v["price"])}</td>'
                f'<td class="trend {tcls}" dir="ltr">{spark(v["series"])} {ttxt}</td></tr>')
        out.append('</tbody></table></div>')

    # ריכוז לפי פרויקט — מי מוכר, איפה, ובאיזה מחיר. שורות בודדות של
    # אותו פרויקט חוזרות על עצמן ואינן מוסיפות מידע.
    new_deals = [r for r in rows if r.get("is_new")]
    tagged = [r for r in new_deals if r.get("developer_candidates")]
    if tagged:
        proj = defaultdict(list)
        for r in tagged:
            proj[(r["city"], r["neighborhood"], tuple(r["developer_candidates"]))].append(r)
        out.append('<h2>פרויקטים עם יזם מזוהה</h2>')
        out.append(
            '<p class="lead">שם היזם <strong>אינו חלק מנתוני העסקה</strong>. הוא '
            'מוצלב מקובץ "דירה בהנחה" של data.gov.il, שהוא המקור הציבורי היחיד '
            'שמקשר פרויקט ליזם — ולכן הוא מכסה רק תוכניות מסובסדות, וההתאמה היא '
            f'לפי עיר ושכונה. בפועל ניתן לשייך כך '
            f'{round(len(tagged) / len(new_deals) * 100)}% מעסקאות הקבלן '
            f'({len(tagged):,} מתוך {len(new_deals):,}). '
            '<strong>זהו מועמד ולא ייחוס:</strong> ייתכן שבאותה שכונה בונים כמה '
            'יזמים, והדירה שנמכרה אינה של מי שמופיע כאן.</p>')
        out.append('<ul class="projects">')
        for (city, hood, devs), deals in sorted(proj.items(), key=lambda kv: -len(kv[1])):
            ppsm = med([d.get("price_per_sqm") for d in deals])
            lo = min(d["amount"] for d in deals)
            hi = max(d["amount"] for d in deals)
            last = max(d["date"] for d in deals)
            out.append(
                f'<li><div class="ph"><span class="c">{city}</span>'
                f'<span class="h">{hood}</span>'
                f'<span class="cnt" dir="ltr">{len(deals)} עסקאות</span></div>'
                f'<div class="pd">יזם אפשרי: {" · ".join(devs[:3])}</div>'
                f'<div class="pn"><span><b>חציון</b>'
                f'<i dir="ltr">{num(ppsm)} ₪/מ״ר</i></span>'
                f'<span><b>טווח</b><i dir="ltr">{money(lo)}–{money(hi)} ₪</i></span>'
                f'<span><b>אחרונה</b><i dir="ltr">{last[8:10]}/{last[5:7]}/{last[:4]}</i></span>'
                f'</div></li>')
        out.append('</ul>')

    # ורשימת האחרונות, ללא תלות בשיוך
    newest = [r for r in reversed(new_deals)][:20]
    if newest:
        out.append('<h2>רכישות מקבלן אחרונות</h2>')
        out.append('<ul class="newbuild">')
        for r in newest:
            devs = r.get("developer_candidates") or []
            dev = ('<span class="dev">יזם אפשרי: ' + " · ".join(devs[:2]) + '</span>'
                   if devs else "")
            loc = " · ".join(x for x in (r.get("neighborhood"), r.get("street")) if x)
            out.append(
                f'<li><span class="d">{r["date"][8:10]}/{r["date"][5:7]}</span>'
                f'<span class="c">{r["city"]}</span>'
                f'<span class="l">{loc or "—"}</span>'
                f'<span class="n" dir="ltr">{r.get("rooms") or "—"} ח׳ · '
                f'{r.get("area_sqm") or "—"} מ״ר</span>'
                f'<span class="p" dir="ltr">{money(r.get("amount"))} ₪</span>'
                f'<span class="s" dir="ltr">{num(r.get("price_per_sqm"))} ₪/מ״ר</span>'
                f'{dev}</li>')
        out.append('</ul>')

    out.append('<p class="note">חציון ולא ממוצע: עסקה חריגה אחת מזיזה ממוצע '
               'ולא מזיזה חציון. "מגמה" היא השינוי בין חציון שלושת החודשים '
               'המלאים האחרונים לשלושת הראשונים שבחלון, ומחושבת רק כשיש לפחות '
               'שישה חודשים עם שלוש עסקאות ומעלה בכל אחד. עיר עם פחות '
               f'מ-{MIN_SAMPLE} עסקאות מסומנת כמדגם דק.</p>')
    return "\n".join(out)
