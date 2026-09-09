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

# סוגי נייר שאינם מניה של חברה. **הבדיקה על שדה הסוג ולא על השם** —
# "סלקום", "שופרסל", "סלע נדלן" ו"יוניברסל מוטורס" כולם מכילים "סל"
# בשמם והם מניות לכל דבר. שדה הסוג הוא רשימה סגורה, ולכן חד־משמעי.
NOT_SHARE = ("קרנות סל", "תעודות סל")


def _load_raw() -> list[dict]:
    rows = []
    for f in sorted(OTC.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("traded_at") or r["date"])
    return rows


def load() -> list[dict]:
    """כל העסקאות, בלי קרנות סל ותעודות סל.

    **הסוג נלמד לפי נייר ולא לפי רשומה.** רשומה שנמשכה מהיסטוריית הנייר
    מגיעה בלי שדה סוג כלל, ולכן סינון פר-רשומה היה מדלג עליה. הסוג נקבע
    מכל רשומה שבה הוא כן ידוע, וחל על כל הרשומות של אותו נייר.
    """
    rows = _load_raw()
    kind: dict[str, str] = {}
    for r in rows:
        t = (r.get("sec_type") or "").strip()
        if t:
            kind.setdefault(r["security_id"], t)
    return [r for r in rows
            if kind.get(r["security_id"], r.get("sec_type") or "") not in NOT_SHARE]


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
        # ביום בודד יש לרוב עסקה אחת או שתיים לנייר, וחציון של שתיים הוא
        # ממוצע ממילא. הממוצע נאמר כפי שהוא ואינו מתחזה למדד עמיד.
        e["mean_prem"] = (round(statistics.fmean(e["prem"]), 2)
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

def buyers(rows: list[dict], off: list[dict]) -> dict[str, list[str]]:
    """זהויות מדווחות לעסקאות של אותה תקופה, מתוך דיווחי מאיה.

    **סקירת הבורסה אינה נושאת זהויות בכלל.** מי שקנה נודע רק כשהוא חייב
    בדיווח — בעל עניין, או מי שחצה סף — ואז ת076 נושא את שמו. ההצלבה היא
    לפי נייר ותאריך, ולכן היא **אפשרית ולא ודאית**: באותו יום ובאותו
    נייר יכולות להיות גם עסקאות של אחרים. הניסוח בהתאם — "מדווח" ולא
    "הרוכש".
    """
    if not off:
        return {}
    days = {r["date"] for r in rows}
    secs = {r["security_id"] for r in rows}
    out: dict[str, list[str]] = {}
    for o in off:
        if str(o.get("security_id")) not in secs or o.get("date") not in days:
            continue
        if o.get("counted") is False or o.get("partial"):
            continue
        who = (o.get("holder") or "").strip()
        if not who:
            continue
        side = "רכש" if o.get("direction") == "buy" else "מכר"
        line = f"{who} {side}"
        out.setdefault(str(o["security_id"]), [])
        if line not in out[str(o["security_id"])]:
            out[str(o["security_id"])].append(line)
    return out


def tweet(rows: list[dict], label: str, off: list[dict], key: str) -> str:
    """תקציר באורך ציוץ, מוכן להעתקה.

    **נכתב לפרסום ולא לקריאה בעמוד.** לכן הוא קצר מהסקירה שמעליו, נוקב
    בשמות כשהם ידועים, ונעצר ב-280 תווים — האורך שאפשר להדביק בלי
    שייחתך. מעקה 5 חל: תיאור מה קרה, בלי המלצה.
    """
    if not rows:
        return ""
    agg = aggregate(rows)
    total = sum(e["value"] for e in agg)
    if not agg or not total:
        return ""
    ident = buyers(rows, off)
    lines = [f"עסקאות מחוץ לבורסה · {label}",
             f"{money(total)} ב-{sum(e['n'] for e in agg):,} עסקאות, "
             f"{len(agg)} ניירות"]

    big = agg[0]
    cap = (f" — {big['pct_capital']:.2f}% מההון"
           if big["pct_capital"] is not None else "")
    lines.append(f"הגדולה: {big['name']} {money(big['value'])}{cap}")

    # נייר שבו עבר החלק הגדול ביותר מההון — לא בהכרח הגדול בכסף, וזה
    # בדיוק מה שמעניין: מחזור גדול בחברה גדולה אינו שינוי החזקות.
    withcap = [e for e in agg if e["pct_capital"]]
    if withcap:
        top = max(withcap, key=lambda e: e["pct_capital"])
        if top["sid"] != big["sid"]:
            lines.append(f"החלק הגדול מההון: {top['name']} "
                         f"{top['pct_capital']:.2f}%")

    named = []
    for e in agg[:6]:
        for who in ident.get(e["sid"], [])[:1]:
            named.append(f"{e['name']}: {who}")
    if named:
        lines.append("מדווחים — " + " · ".join(named[:2]))

    out = ""
    for ln in lines:
        nxt = (out + "\n" + ln) if out else ln
        if len(nxt) > 268:
            break
        out = nxt
    return out + "\ntlvtaseview.com"


def tweet_block(text: str, key: str) -> str:
    if not text:
        return ""
    esc = (text.replace("&", "&amp;").replace("<", "&lt;")
               .replace(">", "&gt;"))
    return (f'<div class="otc-tweet" id="tw-{key}">'
            f'<pre>{esc}</pre></div>')

def period_table(title: str, sub: str, rows: list[dict],
                 show_days: bool, key: str = "", label: str = "",
                 stat: str = "median", extra: str = "", limit: int = 30) -> str:
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
            + '<th>היקף</th><th>% מהון החברה</th>'
            + (f'<th>{"ממוצע" if stat == "mean" else "חציון"} מול הבסיס</th>'))
    fld = "mean_prem" if stat == "mean" else "median_prem"
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
            "prem": signed(e[fld]),
        } for e in agg[:16]],
        "more": max(0, len(agg) - 16),
    }, ensure_ascii=False)
    out = [f'<h2>{title}</h2>',
           f'<p class="note">{sub}</p>',
           review(rows, label or title),
           extra,
           f'<script type="application/json" id="otc-{key}">{payload}</script>',
           f'<p class="otc-acts">'
           f'<button type="button" class="otc-png" data-key="{key}">'
           'ייצוא לתמונה</button>'
           f'<button type="button" class="otc-copy" data-key="{key}">'
           'העתקת התקציר</button></p>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           + head + '</tr></thead><tbody>']
    for e in agg[:limit]:
        pc = e["pct_capital"]
        out.append(
            f'<tr><td class="city">{e["name"]}</td>'
            f'<td dir="ltr">{e["n"]}</td>'
            + (f'<td dir="ltr">{e["days"]}</td>' if show_days else '')
            + f'<td class="key" dir="ltr">{money(e["value"])}</td>'
            f'<td dir="ltr">{num(pc, 2) + "%" if pc is not None else "—"}</td>'
            f'<td class="trend {cls(e[fld])}" dir="ltr">'
            f'{signed(e[fld])}</td></tr>')
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


def periods(a: dict, year: str, off: list[dict] | None = None) -> str:
    """שלוש התקופות, מהצרה לרחבה — יום, חודש, שנה.

    **היום הוא היום האחרון שיש בו נתונים, גם כשטרם ננעל.** הפרדת יום
    פתוח לסעיף נפרד יצרה טבלה רביעית, והיא הייתה הצפופה בעמוד. כאן היא
    אותה טבלה, עם כותרת שאומרת שהיום פתוח ועד איזו שעה נאסף — כדי
    שהמספר לא ייקרא כיום מלא.
    """
    off = off or []
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
        dlabel = "היום" if openday else "יום המסחר האחרון"
        parts.append(period_table(
            title, sub, day_rows, show_days=False, key="day", label=dlabel,
            # ביום בודד יש לרוב עסקה אחת לנייר; ממוצע נאמר כפי שהוא.
            stat="mean",
            extra=tweet_block(tweet(day_rows, f"{dlabel} {hebdate(latest)}",
                                    off, "day"), "day")))
    if month:
        parts.append(period_table(
            f"מתחילת החודש · {month[5:7]}/{month[:4]}",
            "מצטבר מהראשון בחודש ועד היום האחרון שנאסף.",
            mtd, show_days=True, key="mtd", label="החודש",
            extra=tweet_block(tweet(mtd, f"מתחילת {month[5:7]}/{month[:4]}",
                                    off, "mtd"), "mtd")))
    parts.append(period_table(
        f"מתחילת {year}",
        "מצטבר לכל השנה. עמודת הימים מראה נייר שחוזר מחוץ לבורסה — "
        "מספר הימים אומר יותר מהיקף של עסקה בודדת.",
        a["ytd"], show_days=True, key="ytd", label=f"מתחילת {year}",
        extra=tweet_block(tweet(a["ytd"], f"מתחילת {year}", off, "ytd"), "ytd")))
    return "\n".join(parts)



def head(a: dict, year: str) -> str:
    # ספירת הניירות האחרים הוסרה מהעמוד: היא תיאור של מה שלא מוצג,
    # והקורא לא ביקש אותו.
    note = ""
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
'</p>')


def export_js() -> str:
    """ציור הכרטיס לקנבס והורדה כ-PNG, ולצידו העתקת התקציר.

    **הפריסה נמדדת ואינה מנוחשת.** רוחבי העמודות נגזרים מרוחב הטקסט
    בפועל (measureText), ועמודת השם בולעת את העודף או נחתכת במכוון —
    כך סכום הרוחבים שווה תמיד לרוחב הפנוי ושום עמודה אינה יוצאת מהמסגרת.
    הגרסה הקודמת השתמשה ברוחבים קבועים שסכומם עלה על רוחב הקנבס, ולכן
    התמונה יצאה חתוכה.

    **הקרדיט נכתב בכיוון LTR.** בכיוון RTL מנוע הטקסט מסדר מחדש את "©"
    ואת ה-"@" סביב הטקסט הלטיני, והתוצאה על המסך הייתה "Cigarbutthunte7@ ©".

    מצייר מהמטען המוטמע ולא מגרד את ה-DOM: תמונה לציוץ צריכה להיראות
    זהה מכל מכשיר, ולא לרשת את רוחב המסך או את ערכת הצבעים של הקורא.
    ללא ספריות חיצוניות.
    """
    return """<script>
(function () {
  "use strict";


  var W = 1080, SCALE = 2, PAD = 48;
  var C = {
    bg: "#0c1a21", panel: "#122730", line: "#1e3a45", hair: "#16303a",
    text: "#eaf1f3", dim: "#8fa8b2", accent: "#4fd6bd",
    up: "#5fd48a", down: "#f5786f", zebra: "#0f2029",
  };
  var F = function (w, s) {
    return w + " " + s + "px 'Segoe UI', system-ui, Arial, sans-serif";
  };

  function ell(x, t, max) {
    if (x.measureText(t).width <= max) { return t; }
    var s = t;
    while (s.length > 1 && x.measureText(s + "…").width > max) {
      s = s.slice(0, -1);
    }
    return s + "…";
  }

  function roundRect(x, l, t, w, h, r) {
    x.beginPath();
    x.moveTo(l + r, t);
    x.arcTo(l + w, t, l + w, t + h, r);
    x.arcTo(l + w, t + h, l, t + h, r);
    x.arcTo(l, t + h, l, t, r);
    x.arcTo(l, t, l + w, t, r);
    x.closePath();
  }

  function drawCard(d) {
    var rows = d.rows || [];
    // טבלה עם עמודות משלה (למשל בעלי עניין) שולחת אותן במטען; אחרת
    // נבחרת אחת משתי הפריסות הקבועות של טבלאות התקופה.
    var cols = d.cols ? d.cols : d.showDays
      ? [["נייר", "name", "rtl"], ["עסקאות", "n", "ltr"], ["ימים", "days", "ltr"],
         ["היקף", "value", "rtl"], ["% מההון", "cap", "ltr"], ["מול הבסיס", "prem", "ltr"]]
      : [["נייר", "name", "rtl"], ["עסקאות", "n", "ltr"],
         ["היקף", "value", "rtl"], ["% מההון", "cap", "ltr"], ["מול הבסיס", "prem", "ltr"]];

    // מדידה על קנבס זמני: רוחב עמודה נגזר מהתוכן שבה ולא מהערכה.
    var probe = document.createElement("canvas").getContext("2d");
    var ROWF = F(400, 21), HEADF = F(600, 16);
    var inner = W - PAD * 2, GAP = 22;
    var wid = cols.map(function (c) {
      probe.font = HEADF;
      var m = probe.measureText(c[0]).width;
      probe.font = c[1] === "name" ? F(600, 21) : ROWF;
      rows.forEach(function (r) {
        m = Math.max(m, probe.measureText(String(r[c[1]])).width);
      });
      return Math.ceil(m) + GAP;
    });
    var sum = wid.reduce(function (a, b) { return a + b; }, 0);
    // עמודת השם בולעת את העודף או נחתכת — כך הסכום תמיד שווה לרוחב הפנוי.
    wid[0] += inner - sum;
    var NAME_MIN = 150;
    if (wid[0] < NAME_MIN) {
      var need = NAME_MIN - wid[0];
      wid[0] = NAME_MIN;
      for (var i = 1; i < wid.length && need > 0; i++) {
        var cut = Math.min(need, wid[i] - 60);
        if (cut > 0) { wid[i] -= cut; need -= cut; }
      }
    }

    var HEAD = 214, ROW = 46, FOOT = 118;
    var H = HEAD + 40 + ROW * rows.length + (d.more ? 40 : 0) + FOOT;

    var cv = document.createElement("canvas");
    cv.width = W * SCALE; cv.height = H * SCALE;
    var x = cv.getContext("2d");
    x.scale(SCALE, SCALE);
    x.textBaseline = "alphabetic";

    // רקע
    var g = x.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#0e1e26"); g.addColorStop(1, C.bg);
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    x.fillStyle = C.accent; x.fillRect(0, 0, W, 5);

    var right = W - PAD, left = PAD;

    // כותרת
    x.direction = "rtl"; x.textAlign = "right";
    x.fillStyle = C.accent; x.font = F(700, 15);
    x.letterSpacing = "3px";
    x.fillText("TLV TASE VIEW", right, PAD + 18);
    x.letterSpacing = "0px";
    x.fillStyle = C.text; x.font = F(700, 40);
    x.fillText(d.title, right, PAD + 68);
    x.fillStyle = C.dim; x.font = F(400, 19);
    x.fillText(d.kicker || "עסקאות מחוץ לבורסה", right, PAD + 98);

    // שלוש אריחי סיכום
    var pills = d.pills || [["היקף", d.total], ["עסקאות", String(d.deals)],
                            ["ניירות", String(d.securities)]];
    var pw = (inner - 24) / 3, py = PAD + 118;
    pills.forEach(function (p, i) {
      var px = right - pw - i * (pw + 12);
      x.fillStyle = C.panel;
      roundRect(x, px, py, pw, 62, 10); x.fill();
      x.strokeStyle = C.line; x.lineWidth = 1; x.stroke();
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.dim; x.font = F(500, 14);
      x.fillText(p[0], px + pw - 14, py + 23);
      x.fillStyle = C.text; x.font = F(700, 24);
      x.fillText(p[1], px + pw - 14, py + 50);
    });

    // כותרות עמודות
    var y = HEAD + 24, cx = right;
    x.font = HEADF; x.fillStyle = C.dim;
    cols.forEach(function (c, i) {
      x.direction = c[2]; x.textAlign = "right";
      x.fillText(c[0], cx, y);
      cx -= wid[i];
    });
    x.strokeStyle = C.line; x.lineWidth = 1.5;
    x.beginPath(); x.moveTo(left, y + 13); x.lineTo(right, y + 13); x.stroke();

    // שורות
    rows.forEach(function (r, n) {
      var top = y + 13 + ROW * n, base = top + 30;
      if (n % 2 === 0) {
        x.fillStyle = C.zebra;
        roundRect(x, left, top + 4, inner, ROW - 6, 6); x.fill();
      }
      var vx = right;
      cols.forEach(function (c, i) {
        var v = String(r[c[1]]);
        x.direction = c[2]; x.textAlign = "right";
        if (i === 0) {
          x.font = F(600, 21); x.fillStyle = C.text;
          v = ell(x, v, wid[0] - GAP);
        } else if (c[1] === "prem") {
          x.font = F(600, 21);
          x.fillStyle = v.charAt(0) === "-" ? C.down
            : v.charAt(0) === "+" ? C.up : C.dim;
        } else if (c[1] === "value") {
          x.font = F(600, 21); x.fillStyle = C.text;
        } else {
          x.font = ROWF; x.fillStyle = C.dim;
        }
        x.fillText(v, vx - 10, base);
        vx -= wid[i];
      });
    });

    var ey = y + 13 + ROW * rows.length;
    if (d.more) {
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.dim; x.font = F(400, 18);
      x.fillText("ועוד " + d.more + " ניירות", right, ey + 26);
      ey += 40;
    }

    // כותרת תחתונה
    x.strokeStyle = C.hair; x.lineWidth = 1;
    x.beginPath(); x.moveTo(left, H - FOOT + 16); x.lineTo(right, H - FOOT + 16);
    x.stroke();
    x.direction = "rtl"; x.textAlign = "right";
    x.fillStyle = C.dim; x.font = F(400, 16);
    x.fillText("מקור: סקירת העסקאות מחוץ לבורסה של הבורסה לניירות ערך בתל אביב",
               right, H - FOOT + 44);
    // **הקרדיט נכתב LTR.** בכיוון RTL המנוע מסדר מחדש את "©" ואת ה-"@"
    // סביב הטקסט הלטיני, והתוצאה על המסך הייתה "Cigarbutthunte7@ ©".
    x.direction = "ltr"; x.textAlign = "right";
    x.fillStyle = C.accent; x.font = F(700, 17);
    x.fillText("© @Cigarbutthunte7", right, H - FOOT + 78);
    x.textAlign = "left";
    x.fillStyle = C.dim; x.font = F(400, 16);
    x.fillText("tlvtaseview.com", left, H - FOOT + 78);
    return cv;
  }
  function save(c, name) {
    c.toBlob(function (b) {
      var u = URL.createObjectURL(b), a = document.createElement("a");
      a.href = u; a.download = name; document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(u); }, 1000);
    }, "image/png");
  }

  var cps = document.querySelectorAll("button.otc-copy");
  Array.prototype.forEach.call(cps, function (b) {
    b.addEventListener("click", function () {
      var el = document.getElementById("tw-" + b.getAttribute("data-key"));
      if (!el) { return; }
      var t = (el.textContent || "").trim(), was = b.textContent;
      function done(msg) { b.textContent = msg; setTimeout(function () {
        b.textContent = was; }, 2200); }
      // **דחייה של ה-clipboard חייבת ליפול אחורה ולא להיבלע.** הדפדפן
      // דוחה את הכתיבה בהקשרים מסוימים, ואז הכפתור לא הגיב בכלל
      // והמשתמש לא ידע אם הועתק. בחירת הטקסט מאפשרת Ctrl+C ידני.
      function pick() {
        try {
          var r = document.createRange();
          r.selectNodeContents(el);
          var sel = window.getSelection();
          sel.removeAllRanges(); sel.addRange(r);
          done("סומן — Ctrl+C");
        } catch (e) { done(was); }
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t).then(function () { done("הועתק"); }, pick);
        return;
      }
      pick();
    });
  });

  var btns = document.querySelectorAll("button.otc-png");
  Array.prototype.forEach.call(btns, function (b) {
    b.addEventListener("click", function () {
      var el = document.getElementById("otc-" + b.getAttribute("data-key"));
      if (!el) { return; }
      var d;
      try { d = JSON.parse(el.textContent); } catch (e) { d = null; }
      if (!d || !d.rows || !d.rows.length) { return; }
      var was = b.textContent;
      b.textContent = "מייצא…";
      try {
        save(drawCard(d), "tlv-otc-" + b.getAttribute("data-key") + ".png");
        b.textContent = "התמונה הורדה";
      } catch (e) {
        // הכשל אינו נאמר על המסך — אבל הוא כן נאמר לקונסולה. בליעה
        // מוחלטת הפכה באג בציור לכפתור שפשוט אינו מגיב.
        if (window.console) { console.error("otc export", e); }
        b.textContent = was;
      }
      setTimeout(function () { b.textContent = was; }, 2500);
    });
  });
})();
</script>"""

def page(otc_rows: list[dict], maya_body: str, year: str,
         offex_rows: list[dict] | None = None) -> str:
    if not otc_rows:
        return ('<div class="dash-head"><h1>עסקאות מחוץ לבורסה</h1></div>'
                + (maya_body or ""))
    a = analyse(otc_rows, year)
    # **סדר אחד: מהיום אל השנה.** הגרסה הקודמת פיזרה היסטוגרמה, גרף קו,
    # ליקוט עסקאות חריגות בשמן וטבלת חזרות בין שני חתכים יומיים, ולא
    # הייתה בה דרך לענות על "מה קרה החודש". שלוש טבלאות באותו מבנה
    # עונות על זה, ומאפשרות להשוות נייר בין התקופות בלי ללמוד מבנה חדש.
    parts = [head(a, year), tiles(a, year),
             periods(a, year, offex_rows), method()]
    if maya_body:
        parts += ['<h2>מי עומד מאחורי העסקאות המדווחות</h2>', maya_body]
    # **הסקריפט אחרון, אחרי כל הכפתורים.** הוא רץ בזמן פענוח העמוד
    # וקושר מאזינים למה שכבר קיים ב-DOM; כשהוא ישב לפני שכבת מאיה,
    # כפתורי טבלת בעלי העניין נוצרו אחריו ולא קיבלו מאזין כלל —
    # לחיצה עליהם לא עשתה דבר, בלי שגיאה ובלי סימן.
    parts.append(export_js())
    return "\n".join(p for p in parts if p)
