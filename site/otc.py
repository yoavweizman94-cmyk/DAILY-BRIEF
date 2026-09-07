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
    out: dict[str, dict] = {}
    for r in rows:
        e = out.setdefault(r["security_id"], {
            "name": r["name"], "covered": r.get("covered"),
            "value": 0.0, "n": 0, "days": set(), "prem": []})
        e["value"] += r["value"]
        e["n"] += 1
        e["days"].add(r["date"])
        if r.get("premium_pct") is not None:
            e["prem"].append(r["premium_pct"])
    for e in out.values():
        e["days"] = len(e["days"])
        e["median_prem"] = (round(statistics.median(e["prem"]), 2)
                            if e["prem"] else None)
    return sorted(out.values(), key=lambda e: -e["value"])


def period_table(title: str, sub: str, rows: list[dict],
                 show_days: bool, limit: int = 30) -> str:
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
            + '<th>היקף</th><th>% מהתקופה</th><th>חציון מול הבסיס</th>')
    out = [f'<h2>{title}</h2>',
           f'<p class="note">{sub}</p>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           + head + '</tr></thead><tbody>']
    for e in agg[:limit]:
        cov = '<span class="cov">כיסוי</span>' if e["covered"] else ""
        share = (e["value"] / total * 100) if total else 0
        out.append(
            f'<tr><td class="city">{e["name"]}{cov}</td>'
            f'<td dir="ltr">{e["n"]}</td>'
            + (f'<td dir="ltr">{e["days"]}</td>' if show_days else '')
            + f'<td class="key" dir="ltr">{money(e["value"])}</td>'
            f'<td dir="ltr">{num(share, 1)}%</td>'
            f'<td class="trend {cls(e["median_prem"])}" dir="ltr">'
            f'{signed(e["median_prem"])}</td></tr>')
    cols = 6 if show_days else 5
    rest = len(agg) - limit
    if rest > 0:
        hidden = sum(e["value"] for e in agg[limit:])
        out.append(f'<tr><td colspan="{cols}" class="note">'
                   f'ועוד {rest} ניירות בהיקף {money(hidden)}.</td></tr>')
    out.append(f'<tr><td class="city"><b>סך הכל</b></td>'
               f'<td dir="ltr">{sum(e["n"] for e in agg)}</td>'
               + ('<td></td>' if show_days else '')
               + f'<td class="key" dir="ltr"><b>{money(total)}</b></td>'
               f'<td dir="ltr">100%</td><td></td></tr>')
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
        parts.append(period_table(title, sub, day_rows, show_days=False))
    if month:
        parts.append(period_table(
            f"מתחילת החודש · {month[5:7]}/{month[:4]}",
            "מצטבר מהראשון בחודש ועד היום האחרון שנאסף.",
            mtd, show_days=True))
    parts.append(period_table(
        f"מתחילת {year}",
        "מצטבר לכל השנה. עמודת הימים מראה נייר שחוזר מחוץ לבורסה — "
        "מספר הימים אומר יותר מהיקף של עסקה בודדת.",
        a["ytd"], show_days=True))
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
    parts = [head(a, year), tiles(a, year), periods(a, year), method()]
    if maya_body:
        parts += ['<h2>מי עומד מאחורי העסקאות המדווחות</h2>', maya_body]
    return "\n".join(p for p in parts if p)
