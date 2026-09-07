# -*- coding: utf-8 -*-
"""עמוד העסקאות מחוץ לבורסה — תמונת שוק, לא רשימת שורות.

שני מקורות שאינם מחליפים זה את זה:

· **הסקירה היומית של הבורסה** (ingest/otc_pull.py) — *כל* העסקאות,
  כולל אלה שאף צד בהן אינו בעל עניין. אין בה זהויות.
· **מאיה** (ingest/offex_pull.py) — רק עסקאות שחייבות דיווח, אך בהן
  המדווח מזוהה בשמו ובשיעור מההון.

מה שנגזר כאן ואינו באף אחד מהם — והוא עיקר העמוד:

**פרמיה מול שער הבסיס** היא השאלה בעסקה מחוץ לבורסה: באיזה מחיר
הסכימו הצדדים ביחס לשוק. אבל היא לבדה מטעה. עסקה שנקבעה ב-15% מתחת
לבסיס במניה שירדה 15% באותו יום נעשתה בדיוק במחיר הנעילה, ואין בה
הנחה כלל. לכן כל עסקה נמדדת **בשני צירים** — מול הבסיס ומול הנעילה —
והצירוף הוא שקובע את הפרשנות.

**חלק מהמחזור בבורסה** יכול לעבור 100%, ואין בכך שגיאה: מחזור הבורסה
אינו כולל את העסקאות מחוץ לה. שיעור של 150% פירושו שהעסקה הייתה גדולה
פי אחד וחצי מכל המסחר הרגיל באותו נייר באותו יום.
"""
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OTC = ROOT / "output" / "otc"

# מתחת לזה העסקה נחשבת "בשער הבסיס". טווח צר מדי הופך עיגול אגורות
# לסטייה, ורחב מדי בולע הנחה אמיתית בנייר סחיר.
AT = 0.5
# סטייה שמעליה האייטם ראוי להצגה בשמו.
NOTABLE = 2.0
# מעל זה העסקה גדולה מהמסחר הרגיל בנייר ומזיזה את תמונת הסחירות.
DOMINANT = 50.0


CAPITAL = ROOT / "data" / "capital.json"


def capital() -> dict[str, dict]:
    """הון מונפק ונפרע לכל נייר, מ-ingest/capital_pull.py.

    **המכנה שהופך היקף כספי למשמעות.** 10 מ׳ ₪ בחברה בשווי מיליארד הם
    רעש; באותה חברה בשווי 80 מ׳ הם שינוי שליטה. בלי המכנה הטבלה מדרגת
    לפי גודל החברה ולא לפי מה שקרה בה.

    נייר שאין לו הון ידוע מוצג עם מקף ואינו נספר בסיכום — כיסוי חסר
    נאמר, ואינו מוצג כאפס.
    """
    try:
        d = json.loads(CAPITAL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d.get("securities") or {}

def load() -> list[dict]:
    rows = []
    for f in sorted(OTC.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("traded_at") or r["date"])
    return rows


def bucket(r: dict) -> str:
    """סיווג העסקה לפי הצירוף של שתי הסטיות, לא לפי אחת מהן.

    זה הלב האנליטי של העמוד: אותה פרמיה מול הבסיס פירושה דבר אחד
    כשהעסקה נעשתה במחיר הנעילה, ודבר אחר לגמרי כשלא.
    """
    p, c = r.get("premium_pct"), r.get("vs_close_pct")
    if p is None or c is None:
        return "unknown"
    if abs(c) <= AT:
        return "at_close"
    if abs(p) <= AT:
        return "at_base"
    return "premium" if p > 0 else "discount"


LABEL = {
    "at_close": "במחיר הנעילה",
    "at_base": "בשער הבסיס",
    "premium": "בפרמיה מעל השוק",
    "discount": "בהנחה מתחת לשוק",
    "unknown": "בלי שער ייחוס",
}

EXPLAIN = {
    "at_close": "בלוק שנסגר על מחיר הנעילה של אותו יום. הפער מול שער "
                "הבסיס משקף את תנועת המניה במהלך היום ואינו הנחה שניתנה.",
    "at_base": "העסקה נקבעה על שער הפתיחה של אותו בוקר, בלי קשר למה "
               "שקרה במסחר. נפוץ בעסקאות שסוכמו מראש.",
    "premium": "הקונה שילם מעל מחיר השוק בסוף אותו יום — לרוב עבור "
               "נתח מהותי או ויתור על השפעת מכירה בשוק.",
    "discount": "המוכר קיבל מתחת למחיר השוק בסוף אותו יום. בנייר דליל "
                "זה מחיר הסחירות; בנייר סחיר זה אייטם בפני עצמו.",
}


def money(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1e9:
        return f"{v / 1e9:,.2f} מיליארד ₪"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.1f} מ׳ ₪"
    if abs(v) >= 1e3:
        return f"{v / 1e3:,.0f} א׳ ₪"
    return f"{v:,.0f} ₪"


def num(v, digits: int = 0) -> str:
    return "—" if v is None else f"{float(v):,.{digits}f}"


def signed(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{'+' if v > 0 else ''}{v:.{digits}f}%"


def cls(v) -> str:
    if v is None:
        return "flat"
    return "up" if v > 0.05 else ("down" if v < -0.05 else "flat")


def hebdate(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso) >= 10 else iso



def analyse(rows: list[dict], year: str) -> dict:
    """כל מה שהעמוד מציג, מחושב פעם אחת."""
    shares = [r for r in rows if r.get("is_share")]
    ytd = [r for r in shares if r["date"][:4] == year]

    by_day: dict[str, list] = defaultdict(list)
    for r in shares:
        by_day[r["date"]].append(r)
    days = sorted(by_day)

    # **רק ימים שנמשכו מהסקירה היומית הם ימי שוק שלמים.** יום שהגיע
    # ממילוי היסטורי מכיל את חברות הכיסוי בלבד, וכל מחזור או מגמה
    # שמחשבים עליו משווים תת-קבוצה לשוק שלם.
    market = [d for d in days if any(r.get("src") == "review" for r in by_day[d])]

    # ריצת אמצע-יום מפרסמת בהשהיה של 15 דקות, ולכן היום הנוכחי אינו
    # בסיס להשוואה.
    latest = market[-1] if market else (days[-1] if days else None)
    complete = [d for d in market if not any(r.get("intraday") for r in by_day[d])]
    ref = complete[-1] if complete else latest

    daily = [(d, sum(r["value"] for r in by_day[d])) for d in market]
    med = statistics.median([v for _, v in daily[-30:]]) if daily else 0

    # ריכוזיות: נייר שחוזר על עצמו מחוץ לבורסה אינו אקראי. מספר הימים
    # חשוב יותר מהיקף — עסקה אחת גדולה היא אירוע, חמישה ימים הם דפוס.
    per_sec: dict[str, dict] = {}
    for r in ytd:
        e = per_sec.setdefault(r["security_id"], {
            "name": r["name"], "covered": r.get("covered"), "value": 0,
            "n": 0, "days": set(), "prem": [], "dominant": 0})
        e["value"] += r["value"]
        e["n"] += 1
        e["days"].add(r["date"])
        if r.get("premium_pct") is not None:
            e["prem"].append(r["premium_pct"])
        if (r.get("pct_of_day") or 0) >= DOMINANT:
            e["dominant"] += 1
    for e in per_sec.values():
        e["days"] = len(e["days"])
        e["median_prem"] = round(statistics.median(e["prem"]), 2) if e["prem"] else None

    # ההתפלגות נמדדת רק על עסקאות שיש להן שער ייחוס. רשומה ישנה
    # ממילוי היסטורי נשמרת בלי בסיס, וספירתה כ"קבוצה" הייתה הופכת
    # מגבלת איסוף לממצא.
    priced = [r for r in ytd if bucket(r) != "unknown"]
    buckets = Counter(bucket(r) for r in priced)
    unpriced = len(ytd) - len(priced)
    notable = [r for r in ytd
               if abs(r.get("premium_pct") or 0) >= NOTABLE
               and abs(r.get("vs_close_pct") or 0) >= AT]
    dominant = [r for r in ytd if (r.get("pct_of_day") or 0) >= DOMINANT]

    return {
        "shares": shares, "ytd": ytd, "by_day": by_day, "days": days,
        "market_days": market, "latest": latest, "ref": ref,
        "daily": daily, "median_day": med, "unpriced": unpriced,
        "per_sec": per_sec, "buckets": buckets, "notable": notable,
        "dominant": dominant,
        "covered": [r for r in ytd if r.get("covered")],
        "other_types": [r for r in rows if not r.get("is_share")],
    }


def tiles(a: dict, year: str) -> str:
    """שלושה מספרים בלבד, ובאותה חלוקה כמו הטבלאות שמתחת.

    הגרסה הקודמת ערבבה מחזור יומי, יחס לחציון, "העסקה הגדולה באותו יום"
    וספירת עסקאות דומיננטיות — ארבעה חתכים שאין ביניהם קשר, שכל אחד
    דורש הסבר משלו. עמוד שנקרא בבוקר צריך שהמספרים שבראשו יובילו אל
    מה שמתחתיהם.
    """
    ref = a["latest"]
    day = sum(r["value"] for r in a["by_day"].get(ref, []))
    month = (ref or "")[:7]
    mtd_rows = [r for r in a["shares"] if r["date"][:7] == month]
    mtd = sum(r["value"] for r in mtd_rows)
    ytd = sum(r["value"] for r in a["ytd"])
    return "\n".join([
        '<section class="strip">',
        f'<div class="tile"><span class="lbl">'
        f'{"היום" if ref != a["ref"] else "יום המסחר האחרון"} · '
        f'{hebdate(ref or "")}</span>'
        f'<span class="val" dir="ltr">{money(day)}</span>'
        f'<span class="chg">{len(a["by_day"].get(ref, []))} עסקאות במניות</span></div>',
        f'<div class="tile"><span class="lbl">מתחילת החודש</span>'
        f'<span class="val" dir="ltr">{money(mtd)}</span>'
        f'<span class="chg">{len(mtd_rows)} עסקאות</span></div>',
        f'<div class="tile"><span class="lbl">מתחילת {year}</span>'
        f'<span class="val" dir="ltr">{money(ytd)}</span>'
        f'<span class="chg">{len(a["ytd"])} עסקאות</span></div>',
        '</section>',
    ])


def aggregate(rows: list[dict]) -> list[dict]:
    """סיכום לפי נייר: כמה עסקאות, באיזה היקף, ובאיזו סטייה טיפוסית.

    **הצבירה היא היחידה שעונה על "מה קרה בתקופה".** רשימת עסקאות בודדות
    עונה על "מה קרה ברגע", ובחודש שלם היא אלפי שורות שאיש אינו קורא.
    """
    cap = capital()
    out: dict[str, dict] = {}
    for r in rows:
        e = out.setdefault(r["security_id"], {
            "sid": r["security_id"], "name": r["name"],
            "covered": r.get("covered"),
            "value": 0.0, "units": 0, "n": 0, "days": set(), "prem": []})
        e["value"] += r["value"]
        e["units"] += r.get("units") or 0
        e["n"] += 1
        e["days"].add(r["date"])
        if r.get("premium_pct") is not None:
            e["prem"].append(r["premium_pct"])
    for e in out.values():
        e["days"] = len(e["days"])
        e["median_prem"] = (round(statistics.median(e["prem"]), 2)
                            if e["prem"] else None)
        issued = (cap.get(e["sid"]) or {}).get("issued")
        # **מצטבר, ולא ממוצע.** אותו נייר שנסחר בחמישה ימים — הסכום הוא
        # כמה מההון עבר ידיים בתקופה כולה.
        e["pct_capital"] = (round(e["units"] / issued * 100, 3)
                            if issued and e["units"] else None)
    return sorted(out.values(), key=lambda e: -e["value"])


def review(rows: list[dict], label: str) -> str:
    """סקירה קצרה של התקופה, נגזרת מהמספרים עצמם.

    **מה שנאמר כאן הוא עובדה מחושבת, לא הערכה.** ריכוזיות, כיוון
    הסטיות והנייר שבו עבר החלק הגדול ביותר מההון — כולם נמדדים מהטבלה
    שמתחת. ניתוח השפעה נכתב בברייף; העמוד הזה מתאר מה קרה.

    מעקה 5 חל כאן במלואו: אין ניסוח שממליץ על פעולה.
    """
    if not rows:
        return ""
    agg = aggregate(rows)
    total = sum(e["value"] for e in agg)
    if not total:
        return ""
    n_deals = sum(e["n"] for e in agg)
    top = agg[0]
    top3 = sum(e["value"] for e in agg[:3]) / total * 100

    bits = [f"{label}: {n_deals:,} עסקאות במניות בהיקף {money(total)}, "
            f"ב-{len(agg)} ניירות."]

    # ריכוזיות: נאמרת רק כשהיא חריגה מספיק כדי להיות עובדה על התקופה.
    if len(agg) >= 3:
        bits.append(f"שלושת הגדולים ריכזו {top3:.0f}% מההיקף, "
                    f"והגדול בהם — {top['name']} — {top['value'] / total * 100:.0f}%.")
    else:
        bits.append(f"הגדול בהם הוא {top['name']}.")

    # החלק מההון הוא מה שמבדיל בין מחזור לשינוי החזקות.
    withcap = [e for e in agg if e["pct_capital"]]
    if withcap:
        big = max(withcap, key=lambda e: e["pct_capital"])
        bits.append(f"החלק הגדול ביותר מהון החברה עבר ב{big['name']} — "
                    f"{big['pct_capital']:.2f}% מההון המונפק.")
        over1 = [e for e in withcap if e["pct_capital"] >= 1]
        if len(over1) > 1:
            bits.append(f"ב-{len(over1)} ניירות עבר מעל 1% מההון.")

    # כיוון הסטיות מול שער הבסיס.
    prem = [e["median_prem"] for e in agg if e["median_prem"] is not None]
    if prem:
        below = sum(1 for x in prem if x < 0)
        med = statistics.median(prem)
        side = "מתחת" if med < 0 else "מעל"
        bits.append(f"חציון הסטייה משער הבסיס הוא {med:+.2f}% — "
                    f"{below} מתוך {len(prem)} ניירות נסחרו {side} לבסיס.")

    # נייר שחוזר בכמה ימים הוא דפוס; עסקה בודדת אינה.
    rec = [e for e in agg if e["days"] >= 3]
    if rec:
        top_rec = max(rec, key=lambda e: e["days"])
        bits.append(f"{len(rec)} ניירות חזרו בשלושה ימים או יותר, "
                    f"והחוזר שבהם {top_rec['name']} ב-{top_rec['days']} ימים.")

    return '<p class="otc-review">' + " ".join(bits) + "</p>"

def period_table(title: str, sub: str, rows: list[dict],
                 show_days: bool, key: str = "", label: str = "",
                 limit: int = 30) -> str:
    """טבלה אחת, במבנה זהה לשלוש התקופות.

    אותן עמודות בשלושתן בכוונה: כך אפשר להשוות נייר בין יום, חודש ושנה
    בלי ללמוד מבנה חדש בכל סעיף.
    """
    if not rows:
        return (f'<h2>{title}</h2><p class="note">{sub}</p>'
                '<p class="note">אין עסקאות בתקופה הזו.</p>')
    agg = aggregate(rows)
    total = sum(e["value"] for e in agg)
    head = ('<th>נייר</th><th>עסקאות</th>'
            + ('<th>ימים</th>' if show_days else '')
            + '<th>היקף</th><th>% מהון החברה</th><th>חציון מול הבסיס</th>')
    # מטען לייצוא: הכפתור מצייר מהנתונים ולא מגרד את ה-DOM, כך
    # שהתמונה אינה תלויה בעיצוב העמוד או ברוחב המסך.
    payload = json.dumps({
        "title": title, "sub": sub, "showDays": show_days,
        "total": money(total), "deals": sum(e["n"] for e in agg),
        "securities": len(agg),
        "rows": [{
            "name": e["name"], "n": e["n"], "days": e["days"],
            "value": money(e["value"]),
            "cap": (f'{e["pct_capital"]:.2f}%'
                    if e["pct_capital"] is not None else "—"),
            "prem": signed(e["median_prem"]),
        } for e in agg[:12]],
    }, ensure_ascii=False)
    out = [f'<h2>{title}</h2>',
           f'<p class="note">{sub}</p>',
           review(rows, label or title),
           f'<script type="application/json" id="otc-{key}">{payload}</script>',
           f'<p><button type="button" class="otc-png" data-key="{key}">'
           'ייצוא לתמונה</button></p>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           + head + '</tr></thead><tbody>']
    for e in agg[:limit]:
        cov = '<span class="cov">כיסוי</span>' if e["covered"] else ""
        pc = e["pct_capital"]
        out.append(
            f'<tr><td class="city">{e["name"]}{cov}</td>'
            f'<td dir="ltr">{e["n"]}</td>'
            + (f'<td dir="ltr">{e["days"]}</td>' if show_days else '')
            + f'<td class="key" dir="ltr">{money(e["value"])}</td>'
            f'<td dir="ltr">{num(pc, 2) + "%" if pc is not None else "—"}</td>'
            f'<td class="trend {cls(e["median_prem"])}" dir="ltr">'
            f'{signed(e["median_prem"])}</td></tr>')
    cols = 6 if show_days else 5
    rest = len(agg) - limit
    if rest > 0:
        hidden = sum(e["value"] for e in agg[limit:])
        out.append(f'<tr><td colspan="{cols}" class="note">'
                   f'ועוד {rest} ניירות בהיקף {money(hidden)}.</td></tr>')
    # סכום אחוזי הון של ניירות שונים אינו מספר בעל משמעות, ולכן התא ריק.
    out.append(f'<tr><td class="city"><b>סך הכל</b></td>'
               f'<td dir="ltr">{sum(e["n"] for e in agg)}</td>'
               + ('<td></td>' if show_days else '')
               + f'<td class="key" dir="ltr"><b>{money(total)}</b></td>'
               f'<td></td><td></td></tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)


def periods(a: dict, year: str) -> str:
    """שלוש התקופות, מהצרה לרחבה — יום, חודש, שנה.

    **היום הוא היום האחרון שיש בו נתונים, גם כשטרם ננעל.** הפרדת יום
    פתוח לסעיף נפרד יצרה טבלה רביעית, והיא הייתה הצפופה בעמוד. כאן היא
    אותה טבלה, עם כותרת שאומרת שהיום פתוח ועד איזו שעה נאסף — כדי
    שהמספר לא ייקרא כיום מלא.
    """
    latest = a["latest"]
    day_rows = a["by_day"].get(latest, [])
    month = (latest or "")[:7]
    mtd = [r for r in a["shares"] if r["date"][:7] == month]
    parts = []
    if latest:
        openday = latest != a["ref"]
        clocks = [(r.get("traded_at") or "")[11:16] for r in day_rows]
        asof = max([c for c in clocks if c] or [""])
        if openday:
            title = f"היום · {hebdate(latest)}"
            sub = ("יום המסחר טרם ננעל"
                   + (f", הנתונים עד {asof}" if asof else "")
                   + ". הבורסה מפרסמת בהשהיה של 15 דקות, ולכן זהו חתך "
                     "חלקי ולא יום שלם.")
        else:
            title = f"יום המסחר האחרון · {hebdate(latest)}"
            sub = "כל העסקאות במניות באותו יום, מסוכמות לפי נייר."
        parts.append(period_table(title, sub, day_rows, show_days=False,
                                  key="day",
                                  label="היום" if openday else "יום המסחר האחרון"))
    if month:
        parts.append(period_table(
            f"מתחילת החודש · {month[5:7]}/{month[:4]}",
            "מצטבר מהראשון בחודש ועד היום האחרון שנאסף.",
            mtd, show_days=True, key="mtd", label="החודש"))
    parts.append(period_table(
        f"מתחילת {year}",
        "מצטבר לכל השנה. עמודת הימים מראה נייר שחוזר מחוץ לבורסה — "
        "מספר הימים אומר יותר מהיקף של עסקה בודדת.",
        a["ytd"], show_days=True, key="ytd", label=f"מתחילת {year}"))
    return "\n".join(parts)



def head(a: dict, year: str) -> str:
    others = a["other_types"]
    ov = sum(r["value"] for r in others)
    note = ""
    if others:
        note = ('<p class="note">העמוד מציג מניות בלבד. באותה סקירה דווחו גם '
                f'{len(others)} עסקאות בניירות אחרים — אג"ח, מק"מ, קרנות סל '
                f'ויחידות השתתפות — בהיקף {money(ov)}.</p>')
    return "\n".join([
        '<div class="dash-head"><h1>עסקאות מחוץ לבורסה</h1>',
        f'<span class="stamp">מתחילת {year} · נבנה {datetime.now():%d/%m %H:%M}</span></div>',
        # פסקה אחת במקום שתיים. ההסבר על ההשהיה עבר לכותרת של טבלת
        # היום, שם הוא רלוונטי — ולא לראש העמוד, שם הוא מס שפה שנקרא
        # פעם אחת ואז מדולג בכל בוקר.
        '<p class="lead">שלוש טבלאות באותו מבנה — יום, חודש ושנה — '
        'מסוכמות לפי נייר. המקור הוא הסקירה היומית של הבורסה, שמפרסמת '
        'את <strong>כל</strong> העסקאות מחוץ לבורסה אך בלי זהויות. '
        'בהמשך העמוד, מתוך מאיה, מי שמאחורי העסקאות שחייבות דיווח — '
        'בשמו ובשיעור מההון.</p>',
        note,
    ])


def method() -> str:
    return ('<p class="note"><strong>איך נגזרו המספרים.</strong> שער הבסיס '
            'אינו מתפרסם ישירות; הוא נגזר מהשינוי היומי שהבורסה מפרסמת לאותו '
            'נייר, ולכן הוא כולל התאמות לדיבידנד ולפיצול. "% מהמסחר בבורסה" '
            'משווה את היקף העסקה למחזור אותו נייר בבורסה באותו יום; הוא יכול '
            'לעבור 100%, כי מחזור הבורסה אינו כולל את העסקאות מחוץ לה. '
            'עסקה בלי שער ייחוס — נייר שלא נסחר באותו יום — מוצגת בלי סטייה '
            'ואינה נספרת בהתפלגות.</p>')


def export_js() -> str:
    """ציור הטבלה לקנבס והורדה כ-PNG.

    **מצייר מהנתונים ולא מגרד את ה-DOM.** גרידה של הטבלה הייתה יורשת
    את רוחב המסך, את גלילת המכולה ואת ערכת הצבעים של הקורא — ותמונה
    לציוץ צריכה להיראות זהה מכל מכשיר. המטען מוטמע כ-JSON לצד כל טבלה.

    ללא ספריות חיצוניות: אין CDN, אין תלות שתישבר, והכל רץ אצל הקורא.
    """
    return """<script>
(function () {
  "use strict";
  var W = 1200, PAD = 44, ROW = 46;

  function draw(d) {
    var cols = d.showDays
      ? [["נייר", 470, "rtl"], ["עסקאות", 110, "ltr"], ["ימים", 100, "ltr"],
         ["היקף", 190, "ltr"], ["% מההון", 150, "ltr"], ["מול הבסיס", 136, "ltr"]]
      : [["נייר", 570, "rtl"], ["עסקאות", 130, "ltr"],
         ["היקף", 210, "ltr"], ["% מההון", 160, "ltr"], ["מול הבסיס", 130, "ltr"]];
    var H = PAD * 2 + 96 + ROW * (d.rows.length + 2) + 54;
    var c = document.createElement("canvas");
    c.width = W; c.height = H;
    var x = c.getContext("2d");

    x.fillStyle = "#fbfaf7"; x.fillRect(0, 0, W, H);
    x.fillStyle = "#0f4c63"; x.fillRect(0, 0, W, 8);

    var right = W - PAD;
    x.textAlign = "right"; x.direction = "rtl";
    x.fillStyle = "#12222b";
    x.font = "700 34px system-ui, 'Segoe UI', Arial";
    x.fillText(d.title, right, PAD + 34);
    x.fillStyle = "#5b6b73";
    x.font = "400 19px system-ui, 'Segoe UI', Arial";
    x.fillText(d.deals.toLocaleString("he-IL") + " עסקאות · " +
               d.securities + " ניירות · " + d.total, right, PAD + 66);

    var y = PAD + 104, cx = right;
    x.font = "700 19px system-ui, 'Segoe UI', Arial";
    x.fillStyle = "#5b6b73";
    for (var i = 0; i < cols.length; i++) {
      x.direction = cols[i][2];
      x.fillText(cols[i][0], cx, y);
      cx -= cols[i][1];
    }
    x.strokeStyle = "#d8d2c6"; x.lineWidth = 1;
    x.beginPath(); x.moveTo(PAD, y + 14); x.lineTo(right, y + 14); x.stroke();

    d.rows.forEach(function (r, n) {
      var ry = y + 14 + ROW * (n + 1) - 12;
      if (n % 2 === 1) {
        x.fillStyle = "#f2efe8";
        x.fillRect(PAD, ry - 26, W - PAD * 2, ROW);
      }
      var vals = d.showDays
        ? [r.name, String(r.n), String(r.days), r.value, r.cap, r.prem]
        : [r.name, String(r.n), r.value, r.cap, r.prem];
      var vx = right;
      for (var i = 0; i < cols.length; i++) {
        x.direction = cols[i][2];
        x.font = (i === 0 ? "600 21px" : "400 21px") +
                 " system-ui, 'Segoe UI', Arial";
        x.fillStyle = (i === cols.length - 1 && vals[i].charAt(0) === "-")
          ? "#b3261e"
          : (i === cols.length - 1 && vals[i].charAt(0) === "+") ? "#1a7f5a" : "#12222b";
        x.fillText(vals[i], vx, ry);
        vx -= cols[i][1];
      }
    });

    var fy = H - PAD + 4;
    x.direction = "rtl"; x.textAlign = "right";
    x.fillStyle = "#8a949a";
    x.font = "400 17px system-ui, 'Segoe UI', Arial";
    x.fillText("TLV TASE View · מקור: סקירת העסקאות מחוץ לבורסה של הבורסה לניירות ערך",
               right, fy);
    x.textAlign = "left"; x.direction = "ltr";
    x.fillText("tlvtaseview.com", PAD, fy);
    return c;
  }

  function save(c, name) {
    c.toBlob(function (b) {
      var u = URL.createObjectURL(b), a = document.createElement("a");
      a.href = u; a.download = name; document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(u); }, 1000);
    }, "image/png");
  }

  var btns = document.querySelectorAll("button.otc-png");
  Array.prototype.forEach.call(btns, function (b) {
    b.addEventListener("click", function () {
      var el = document.getElementById("otc-" + b.getAttribute("data-key"));
      if (!el) { b.textContent = "אין נתונים לייצוא"; return; }
      var d;
      try { d = JSON.parse(el.textContent); } catch (e) { d = null; }
      if (!d || !d.rows || !d.rows.length) { b.textContent = "אין נתונים לייצוא"; return; }
      var was = b.textContent;
      b.textContent = "מייצא…";
      try {
        save(draw(d), "otc-" + b.getAttribute("data-key") + ".png");
        b.textContent = "התמונה הורדה";
      } catch (e) {
        b.textContent = "הייצוא נכשל";
      }
      setTimeout(function () { b.textContent = was; }, 2500);
    });
  });
})();
</script>"""

def page(otc_rows: list[dict], maya_body: str, year: str) -> str:
    if not otc_rows:
        return ('<div class="dash-head"><h1>עסקאות מחוץ לבורסה</h1></div>'
                '<p class="lead">טרם נאספו עסקאות. הסריקה רצה בכל מהדורה.</p>'
                + (maya_body or ""))
    a = analyse(otc_rows, year)
    # **סדר אחד: מהיום אל השנה.** הגרסה הקודמת פיזרה היסטוגרמה, גרף קו,
    # ליקוט עסקאות חריגות בשמן וטבלת חזרות בין שני חתכים יומיים, ולא
    # הייתה בה דרך לענות על "מה קרה החודש". שלוש טבלאות באותו מבנה
    # עונות על זה, ומאפשרות להשוות נייר בין התקופות בלי ללמוד מבנה חדש.
    parts = [head(a, year), tiles(a, year), periods(a, year), method(),
             export_js()]
    if maya_body:
        parts += ['<h2>מי עומד מאחורי העסקאות המדווחות</h2>', maya_body]
    return "\n".join(p for p in parts if p)
