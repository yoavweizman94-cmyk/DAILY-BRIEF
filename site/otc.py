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


def spark(series: list[tuple], width: int = 120, height: int = 26) -> str:
    """גרף קו זעיר. ערכים בלבד — הצירים נאמרים בטקסט שסביבו."""
    vals = [v for _, v in series]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = width / (len(vals) - 1)
    pts = " ".join(
        f"{i * step:.1f},{height - (v - lo) / rng * (height - 3) - 1.5:.1f}"
        for i, v in enumerate(vals))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" '
            f'stroke-width="1.5" stroke-linejoin="round"/></svg>')


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
    ref, by_day = a["ref"], a["by_day"]
    day_rows = by_day.get(ref, [])
    vol = sum(r["value"] for r in day_rows)
    med = a["median_day"] or 0
    delta = (vol / med - 1) * 100 if med else None
    big = max(day_rows, key=lambda r: r["value"], default=None)
    dom = sum(1 for r in day_rows if (r.get("pct_of_day") or 0) >= DOMINANT)
    # מספר הימים נאמר כפי שהוא. תווית "30 ימים" על שניים היא הבטחה
    # שהעמוד אינו מקיים, ובעמוד שנמכר היא הפרש בין דיוק לשיווק.
    nd = min(30, len(a["daily"]))

    out = ['<section class="strip">',
           f'<div class="tile"><span class="lbl">מחזור מחוץ לבורסה · {hebdate(ref or "")}</span>'
           f'<span class="val" dir="ltr">{money(vol)}</span>'
           f'<span class="chg">{len(day_rows)} עסקאות במניות</span></div>',
           f'<div class="tile {cls(delta)}"><span class="lbl">מול החציון של '
           f'{nd} ימי המסחר שנאספו</span>'
           f'<span class="val" dir="ltr">{signed(delta, 0) if delta is not None else "—"}</span>'
           f'<span class="chg">חציון {money(med)}</span></div>']
    if big:
        out.append(
            f'<div class="tile"><span class="lbl">העסקה הגדולה באותו יום</span>'
            f'<span class="val" dir="ltr">{money(big["value"])}</span>'
            f'<span class="chg">{big["name"]} · {signed(big.get("premium_pct"))} מהבסיס</span></div>')
    out.append(
        f'<div class="tile"><span class="lbl">עסקאות גדולות מכל המסחר בנייר</span>'
        f'<span class="val" dir="ltr">{dom} מתוך {len(day_rows)}</span>'
        f'<span class="chg">{len(a["dominant"])} כאלה מתחילת {year}</span></div>')
    out.append('</section>')
    return "\n".join(out)


def pricing(a: dict) -> str:
    """התפלגות התמחור — ומה כל קבוצה אומרת."""
    b, tot = a["buckets"], sum(a["buckets"].values())
    if not tot:
        return ""
    out = ['<h2>איך תומחרו העסקאות</h2>',
           '<p class="lead">כל עסקה נמדדת בשני צירים: מול <strong>שער '
           'הבסיס</strong> של אותו בוקר, ומול <strong>מחיר הנעילה</strong> '
           'של אותו יום. הציר הראשון לבדו מטעה — עסקה שנקבעה 15% מתחת לבסיס '
           'במניה שירדה 15% באותו יום נעשתה בדיוק במחיר השוק. הצירוף הוא '
           'שקובע.</p>',
           '<ul class="otc-buckets">']
    for key in ("at_close", "at_base", "premium", "discount"):
        n = b.get(key, 0)
        if not n:
            continue
        share = round(n / tot * 100)
        out.append(
            f'<li class="b-{key}"><span class="nm">{LABEL[key]}</span>'
            f'<span class="bar"><i style="width:{max(2, share)}%"></i></span>'
            f'<span class="pv" dir="ltr">{share}%</span>'
            f'<span class="ex">{EXPLAIN.get(key, "")}</span></li>')
    out.append('</ul>')
    if a.get("unpriced"):
        out.append(f'<p class="note">{a["unpriced"]} עסקאות נוספות נשמרו בלי שער '
                   'ייחוס ואינן נספרות כאן. הן נמשכו מהיסטוריית הנייר, שמחזיקה '
                   'חמישה ימי מסחר אחורה בלבד, ולכן אין להן שער בסיס.</p>')
    return "\n".join(out)


def flow(a: dict) -> str:
    """המחזור לאורך זמן, עם הקריאה שלו במילים."""
    daily = a["daily"][-40:]
    if len(daily) < 6:
        return ""
    vals = [v for _, v in daily]
    first, last = vals[:5], vals[-5:]
    m0, m1 = statistics.median(first), statistics.median(last)
    drift = (m1 / m0 - 1) * 100 if m0 else None
    word = ("התרחב" if (drift or 0) > 15 else
            "הצטמצם" if (drift or 0) < -15 else "נשאר יציב")
    return "\n".join([
        '<h2>המחזור לאורך זמן</h2>',
        f'<div class="otc-flow"><span class="ln {cls(drift)}">{spark(daily, 220, 40)}</span>'
        f'<span class="rd">המחזור היומי מחוץ לבורסה <strong>{word}</strong>: '
        f'חציון {money(m0)} בחמשת ימי המסחר הראשונים שבתצוגה מול '
        f'{money(m1)} בחמשת האחרונים ({signed(drift, 0)}). '
        f'הטווח בתצוגה: {hebdate(daily[0][0])} – {hebdate(daily[-1][0])}.</span></div>',
    ])


def repeats(a: dict, year: str) -> str:
    """ניירות שחוזרים על עצמם — הדפוס, לא האירוע."""
    rows = [(sid, e) for sid, e in a["per_sec"].items() if e["days"] >= 3]
    rows.sort(key=lambda kv: (-kv[1]["days"], -kv[1]["value"]))
    if not rows:
        return ""
    out = ['<h2>ניירות שחוזרים מחוץ לבורסה</h2>',
           '<p class="lead">עסקה אחת גדולה היא אירוע. אותו נייר בשלושה ימים '
           'שונים ומעלה הוא דפוס — צבירה או הפצה שנמשכת, ולא סגירת פוזיציה '
           f'אחת. הטבלה מתחילת {year}.</p>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           '<th>נייר</th><th>ימים</th><th>עסקאות</th><th>היקף מצטבר</th>'
           '<th>חציון מול הבסיס</th><th>ימים שבהם עברה את המסחר</th>'
           '</tr></thead><tbody>']
    for _, e in rows[:15]:
        cov = '<span class="cov">כיסוי</span>' if e["covered"] else ""
        out.append(
            f'<tr><td class="city">{e["name"]}{cov}</td>'
            f'<td dir="ltr">{e["days"]}</td>'
            f'<td dir="ltr">{e["n"]}</td>'
            f'<td class="key" dir="ltr">{money(e["value"])}</td>'
            f'<td class="trend {cls(e["median_prem"])}" dir="ltr">'
            f'{signed(e["median_prem"])}</td>'
            f'<td dir="ltr">{e["dominant"] or "—"}</td></tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)


def standouts(a: dict) -> str:
    """העסקאות שבאמת חורגות — אחרי שהוסרו אלה שרק עקבו אחרי הנעילה."""
    rows = sorted(a["notable"], key=lambda r: -abs(r["premium_pct"]))[:12]
    if not rows:
        return ""
    out = ['<h2>עסקאות שחרגו מהשוק</h2>',
           f'<p class="lead">סטייה של {NOTABLE}% ומעלה משער הבסיס '
           f'<strong>וגם</strong> יותר מ-{AT}% ממחיר הנעילה. התנאי השני הוא '
           'שמנפה: בלעדיו הרשימה מתמלאת בעסקאות שנעשו במחיר הנעילה בימים '
           'שבהם המניה זזה חזק, ואין בהן פרמיה או הנחה כלל.</p>',
           '<ul class="otc-cards">']
    for r in rows:
        b = bucket(r)
        out.append(
            f'<li class="{b}"><span class="nm">{r["name"]}'
            f'{" <span class=\'cov\'>כיסוי</span>" if r.get("covered") else ""}</span>'
            f'<span class="dt" dir="ltr">{hebdate(r["date"])}</span>'
            f'<span class="v" dir="ltr">{money(r["value"])}</span>'
            f'<span class="p {cls(r["premium_pct"])}" dir="ltr">'
            f'{signed(r["premium_pct"])} מהבסיס</span>'
            f'<span class="c {cls(r["vs_close_pct"])}" dir="ltr">'
            f'{signed(r["vs_close_pct"])} מהנעילה</span>'
            f'<span class="s">{LABEL[b]} · {num(r.get("pct_of_day"), 1)}% '
            f'מהמסחר בבורסה באותו יום</span></li>')
    out.append('</ul>')
    return "\n".join(out)


def open_day(a: dict) -> str:
    """יום המסחר הנוכחי, כשהוא עדיין פתוח.

    **הנתונים היו כאן ולא הוצגו.** המספרים הראשיים מחושבים על יום מסחר
    שהושלם, וזה נכון — יום חלקי אינו בסיס להשוואה. אבל הטבלה היחידה
    שהראתה עסקאות בפועל רונדרה גם היא על אותו יום, ולכן עסקאות שנאספו
    היום נכתבו לקובץ ולא הופיעו בעמוד כלל. הקורא ראה את אתמול וסיכם
    שהעמוד תקוע. נמדד 28/08/2026: 26 עסקאות היום, אפס מהן על המסך.

    היום הפתוח מוצג בנפרד ומסומן בשעת האיסוף, כדי שיהיה ברור שהוא אינו
    מלא ואינו נספר בסטטיסטיקה שמעליו.
    """
    latest = a["latest"]
    if not latest or latest == a["ref"]:
        return ""
    rows = sorted(a["by_day"].get(latest, []), key=lambda r: -r["value"])
    if not rows:
        return ""
    clocks = [(r.get("traded_at") or "")[11:16] for r in rows]
    asof = max([c for c in clocks if c] or [""])
    val = sum(r["value"] for r in rows)
    out = [f'<h2>היום · {hebdate(latest)} <span class="cov">יום פתוח</span></h2>',
           f'<p class="note">יום המסחר טרם ננעל. {len(rows)} עסקאות עד כה '
           f'בהיקף {money(val)}'
           + (f", העדכנית ב-{asof}" if asof else "") + '. הנתונים מתפרסמים '
           'בהשהיה של 15 דקות, והיום אינו נספר במספרים הראשיים שמעלה.</p>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           '<th>נייר</th><th>שעה</th><th>שער</th><th>שער בסיס</th>'
           '<th>מול הבסיס</th><th>מול הנעילה</th><th>היקף</th>'
           '<th>% מהמסחר בבורסה</th></tr></thead><tbody>']
    for r in rows:
        cov = '<span class="cov">כיסוי</span>' if r.get("covered") else ""
        clock = (r.get("traded_at") or "")[11:16] or "—"
        out.append(
            f'<tr><td class="city">{r["name"]}{cov}</td>'
            f'<td dir="ltr">{clock}</td>'
            f'<td dir="ltr">{num(r["price"], 2)}</td>'
            f'<td dir="ltr">{num(r.get("base_rate"), 2)}</td>'
            f'<td class="trend {cls(r.get("premium_pct"))}" dir="ltr">'
            f'{signed(r.get("premium_pct"))}</td>'
            f'<td class="trend {cls(r.get("vs_close_pct"))}" dir="ltr">'
            f'{signed(r.get("vs_close_pct"))}</td>'
            f'<td class="key" dir="ltr">{money(r["value"])}</td>'
            f'<td dir="ltr">{num(r.get("pct_of_day"), 1)}%</td></tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)


def latest_day(a: dict) -> str:
    ref = a["ref"]
    rows = sorted(a["by_day"].get(ref, []), key=lambda r: -r["value"])
    if not rows:
        return ""
    out = [f'<h2>יום המסחר האחרון שננעל · {hebdate(ref)}</h2>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           '<th>נייר</th><th>שעה</th><th>שער</th><th>שער בסיס</th>'
           '<th>מול הבסיס</th><th>מול הנעילה</th><th>היקף</th>'
           '<th>% מהמסחר בבורסה</th></tr></thead><tbody>']
    for r in rows:
        cov = '<span class="cov">כיסוי</span>' if r.get("covered") else ""
        clock = (r.get("traded_at") or "")[11:16] or "—"
        out.append(
            f'<tr><td class="city">{r["name"]}{cov}</td>'
            f'<td dir="ltr">{clock}</td>'
            f'<td dir="ltr">{num(r["price"], 2)}</td>'
            f'<td dir="ltr">{num(r.get("base_rate"), 2)}</td>'
            f'<td class="trend {cls(r.get("premium_pct"))}" dir="ltr">'
            f'{signed(r.get("premium_pct"))}</td>'
            f'<td class="trend {cls(r.get("vs_close_pct"))}" dir="ltr">'
            f'{signed(r.get("vs_close_pct"))}</td>'
            f'<td class="key" dir="ltr">{money(r["value"])}</td>'
            f'<td dir="ltr">{num(r.get("pct_of_day"), 1)}%</td></tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)


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
        '<p class="lead">שני מקורות שאינם מחליפים זה את זה. הסקירה היומית של '
        'הבורסה מפרסמת את <strong>כל</strong> העסקאות מחוץ לבורסה, כולל אלה '
        'שאף צד בהן אינו בעל עניין — אך בלי זהויות. מאיה מפרסמת רק את העסקאות '
        'שחייבות דיווח, ובהן המדווח מזוהה בשמו ובשיעור מההון. השכבה הראשונה '
        'בעמוד היא השוק כולו; השנייה, בהמשך, היא מי שמאחורי מה שדווח.</p>',
        '<p class="lead">נתוני הבורסה מתפרסמים בהשהיה של 15 דקות, ולכן יום '
        'שטרם ננעל אינו שלם. המספרים הראשיים מוצגים על יום המסחר האחרון '
        'שהושלם.</p>',
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
    parts = [head(a, year), tiles(a, year), pricing(a), flow(a),
             standouts(a), repeats(a, year), open_day(a), latest_day(a),
             method()]
    if maya_body:
        parts += ['<h2>מי עומד מאחורי העסקאות המדווחות</h2>', maya_body]
    return "\n".join(p for p in parts if p)
