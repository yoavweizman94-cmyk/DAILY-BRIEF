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
from html import escape as _esc_html
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


SRC_TASE = "מקור: סקירת העסקאות מחוץ לבורסה של הבורסה לניירות ערך בתל אביב"
KICKER = "עסקאות מחוץ לבורסה"

_ICON = ('<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5v7.5m0 0'
         'L4.8 6.8M8 10l3.2-3.2M3 13.2h10" fill="none" stroke="currentColor" '
         'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def png_button(text: str = "ייצוא לתמונה", cls: str = "", **data) -> str:
    """כפתור ייצוא. data-key מצביע על מטען מוטמע; data-day/data-month נבנים
    בדפדפן מתוך נתוני הדיווחים. התווית ב-span כדי שהחלפת הטקסט ("מייצא…")
    לא תמחק את האייקון."""
    attrs = "".join(f' data-{k}="{_esc_html(str(v))}"' for k, v in data.items())
    return (f'<button type="button" class="otc-png{(" " + cls) if cls else ""}"{attrs}>'
            f'{_ICON}<span class="lbl">{_esc_html(text, quote=False)}</span></button>')


def card(title: str, sub: str, blocks: list[dict], file: str,
         kicker: str = KICKER, source: str = SRC_TASE) -> dict:
    """מטען לכרטיס תמונה: כותרת ורצף גושים (ראה site/export_card.js)."""
    return {"kicker": kicker, "title": title, "sub": sub,
            "blocks": [b for b in blocks if b], "source": source, "file": file}


def embed(key: str, payload: dict) -> str:
    return f'<script type="application/json" id="otc-{key}">{_payload(payload)}</script>'



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
    day_rows = a["by_day"].get(ref, [])
    day = sum(r["value"] for r in day_rows)
    month = (ref or "")[:7]
    mtd_rows = [r for r in a["shares"] if r["date"][:7] == month]
    mtd = sum(r["value"] for r in mtd_rows)
    ytd = sum(r["value"] for r in a["ytd"])
    day_word = "היום" if ref != a["ref"] else "יום המסחר האחרון"

    # **תמונת המצב כתמונה.** שלושת המספרים, ומתחתם המחזור היומי בימי השוק
    # האחרונים מול החציון — ההקשר שאומר אם היום הזה גדול או שגרתי — והניירות
    # הגדולים של היום. הגרף אינו בעמוד בכוונה (שם הטבלאות עונות); בתמונה
    # שמופצת לבד, בלי העמוד שסביבה, הוא מה שנותן למספר קנה מידה.
    recent = a["daily"][-22:]
    top_day = aggregate(day_rows)[:6] if day_rows else []
    blocks = [
        {"type": "stats", "items": [
            {"label": f"{day_word} · {hebdate(ref or '')}", "value": money(day),
             "cap": f"{len(day_rows)} עסקאות במניות"},
            {"label": "מתחילת החודש", "value": money(mtd), "cap": f"{len(mtd_rows)} עסקאות"},
            {"label": f"מתחילת {year}", "value": money(ytd), "cap": f"{len(a['ytd'])} עסקאות"}]},
        {"type": "columns", "title": f"המחזור היומי · {len(recent)} ימי המסחר האחרונים",
         "items": [{"label": f"{d[8:10]}/{d[5:7]}", "value": v, "text": money(v)} for d, v in recent],
         "maxText": money(max((v for _, v in recent), default=0)),
         "median": a["median_day"], "medianText": f"חציון 30 יום: {money(a['median_day'])}"}
        if len(recent) >= 2 else None,
        {"type": "table", "title": f"הגדולות · {day_word}",
         "cols": [["נייר", "name", "rtl"], ["עסקאות", "n", "ltr"], ["היקף", "value", "ltr"],
                  ["% מהון החברה", "cap", "ltr"]],
         "rows": [{"name": " ".join(e["name"].split()), "n": str(e["n"]), "value": money(e["value"]),
                   "cap": (num(e["pct_capital"], 2) + "%" if e["pct_capital"] is not None else "—")}
                  for e in top_day]} if top_day else None,
    ]
    payload = card(f"תמונת מצב · {hebdate(ref or '')}",
                   "היקף העסקאות במניות מחוץ לבורסה — ביום, מתחילת החודש ומתחילת השנה.",
                   blocks, file=f"tlv-otc-summary-{ref}")
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
        embed("summary", payload),
        f'<p class="otc-acts otc-acts-strip">{png_button("ייצוא תמונת המצב", key="summary")}</p>',
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
    bits = review_bits(rows, label)
    return '<p class="otc-review">' + " ".join(bits) + "</p>" if bits else ""


def review_bits(rows: list[dict], label: str) -> list[str]:
    """סקירה קצרה של התקופה, נגזרת מהמספרים עצמם.

    **מה שנאמר כאן הוא עובדה מחושבת, לא הערכה.** ריכוזיות, כיוון
    הסטיות והנייר שבו עבר החלק הגדול ביותר מההון — כולם נמדדים מהטבלה
    שמתחת. ניתוח השפעה נכתב בברייף; העמוד הזה מתאר מה קרה.

    מעקה 5 חל כאן במלואו: אין ניסוח שממליץ על פעולה.
    """
    if not rows:
        return []
    agg = aggregate(rows)
    total = sum(e["value"] for e in agg)
    if not total:
        return []
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
    # **הספירה היא של הצד שהמשפט מדבר עליו.** הגרסה הקודמת ספרה תמיד את
    # הניירות שמתחת לבסיס, אבל כשהחציון לא היה שלילי המשפט אמר "מעל" — ו-9
    # ניירות שנסחרו מתחת לבסיס נקראו כ-9 שנסחרו מעליו. וחציון אפסי נכתב
    # "-0.00%": מינוס אפס של נקודה צפה, לא סטייה.
    if prem:
        below = sum(1 for x in prem if x < -0.005)
        above = sum(1 for x in prem if x > 0.005)
        med = statistics.median(prem)
        if abs(med) < 0.005:
            bits.append(f"חציון הסטייה משער הבסיס הוא 0.00% — {above} ניירות נסחרו "
                        f"מעל לבסיס ו-{below} מתחתיו.")
        else:
            side, n_side = ("מתחת", below) if med < 0 else ("מעל", above)
            bits.append(f"חציון הסטייה משער הבסיס הוא {med:+.2f}% — "
                        f"{n_side} מתוך {len(prem)} ניירות נסחרו {side} לבסיס.")

    # נייר שחוזר בכמה ימים הוא דפוס; עסקה בודדת אינה.
    rec = [e for e in agg if e["days"] >= 3]
    if rec:
        top_rec = max(rec, key=lambda e: e["days"])
        bits.append(f"{len(rec)} ניירות חזרו בשלושה ימים או יותר, "
                    f"והחוזר שבהם {top_rec['name']} ב-{top_rec['days']} ימים.")

    return bits


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

def _payload(d: dict) -> str:
    """JSON למטען שמוטמע בעמוד.

    רצף הסגירה של תגית נשבר בלוכסן הפוך, כדי ששם נייר או מדווח לא יסגור
    את תגית ה-script שהמטען יושב בתוכה. התוצאה עדיין JSON תקין.
    """
    return json.dumps(d, ensure_ascii=False).replace("</", "<" + chr(92) + "/")


def _public(r: dict) -> dict:
    """תא בלי שדות העזר (קו תחתון) — מה שנשלח לציור."""
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _td(key: str, v: str, trend: str, bold: bool = False) -> str:
    """תא אחד בטבלת התקופה, באותו עיצוב שהיה לה קודם."""
    t = _esc_html(str(v), quote=False)
    if key == "name":
        return f'<td class="city">{"<b>" + t + "</b>" if bold and t else t}</td>'
    if bold and not t:
        return "<td></td>"
    if key == "value":
        return f'<td class="key" dir="ltr">{"<b>" + t + "</b>" if bold else t}</td>'
    if key == "prem":
        return f'<td class="trend {trend}" dir="ltr">{t}</td>'
    return f'<td dir="ltr">{t}</td>'


def period_table(title: str, sub: str, rows: list[dict],
                 show_days: bool, key: str = "", label: str = "",
                 stat: str = "median", extra: str = "", limit: int = 30) -> str:
    """טבלה אחת, במבנה זהה לשלוש התקופות.

    אותן עמודות בשלושתן בכוונה: כך אפשר להשוות נייר בין יום, חודש ושנה
    בלי ללמוד מבנה חדש בכל סעיף.

    **הטבלה נבנית פעם אחת, והיא גם ה-HTML וגם התמונה.** קודם העמוד חתך
    30 שורות והמטען לייצוא חתך 16, בלי שורת הסך ועם כותרות עמודות אחרות
    — ולכן התמונה הראתה חצי טבלה, ואיש לא החליט על כך. שני חיתוכים
    שמתוחזקים בנפרד נפרדים עם הזמן; חיתוך אחד אינו יכול.
    """
    if not rows:
        return (f'<h2>{title}</h2><p class="note">{sub}</p>'
                '<p class="note">אין עסקאות בתקופה הזו.</p>')
    agg = aggregate(rows)
    total = sum(e["value"] for e in agg)
    fld = "mean_prem" if stat == "mean" else "median_prem"

    cols = [["נייר", "name", "rtl"], ["עסקאות", "n", "ltr"]]
    if show_days:
        cols.append(["ימים", "days", "ltr"])
    cols += [["היקף", "value", "ltr"], ["% מהון החברה", "cap", "ltr"],
             [("ממוצע" if stat == "mean" else "חציון") + " מול הבסיס",
              "prem", "ltr"]]

    shown = agg[:limit]
    cells = [{
        # שם עם רווחים כפולים ("דיסקונט       א") נשבר בתמונה למילים ריקות.
        "name": " ".join(e["name"].split()), "n": str(e["n"]), "days": str(e["days"]),
        "value": money(e["value"]),
        "cap": (num(e["pct_capital"], 2) + "%"
                if e["pct_capital"] is not None else "—"),
        "prem": signed(e[fld]),
        "_cls": cls(e[fld]),
    } for e in shown]
    rest = len(agg) - len(shown)
    more = (f'ועוד {rest} ניירות בהיקף '
            f'{money(sum(e["value"] for e in agg[len(shown):]))}.'
            if rest > 0 else "")
    # סכום אחוזי הון של ניירות שונים אינו מספר בעל משמעות, ולכן התא ריק.
    total_row = {"name": "סך הכל", "n": str(sum(e["n"] for e in agg)),
                 "days": "", "value": money(total), "cap": "", "prem": ""}

    # מטען לייצוא: הכפתור מצייר מהנתונים ולא מגרד את ה-DOM, כך
    # שהתמונה אינה תלויה בעיצוב העמוד או ברוחב המסך.
    bits = review_bits(rows, label or title)
    payload = card(title, sub, [
        {"type": "stats", "items": [
            {"label": "היקף", "value": money(total)},
            {"label": "עסקאות", "value": f'{sum(e["n"] for e in agg):,}'},
            {"label": "ניירות", "value": str(len(agg))}]},
        # המשפט הראשון בסקירה חוזר על שלושת המספרים שמעליו, ולכן אינו בתמונה.
        {"type": "notes", "title": "עיקרי התקופה", "items": bits[1:]} if len(bits) > 1 else None,
        {"type": "table", "title": "לפי נייר", "cols": cols,
         "rows": [_public(r) for r in cells], "moreText": more, "totalRow": total_row},
    ], file=f"tlv-otc-{key}-{max(r['date'] for r in rows)}")
    out = [f'<h2>{title}</h2>',
           f'<p class="note">{sub}</p>',
           review(rows, label or title),
           extra,
           embed(key, payload),
           f'<p class="otc-acts">{png_button(key=key)}'
           f'<button type="button" class="otc-copy" data-key="{key}">'
           'העתקת התקציר</button></p>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           + "".join(f"<th>{c[0]}</th>" for c in cols)
           + '</tr></thead><tbody>']
    for r in cells:
        out.append("<tr>" + "".join(_td(c[1], r[c[1]], r["_cls"]) for c in cols)
                   + "</tr>")
    if more:
        out.append(f'<tr><td colspan="{len(cols)}" class="note">{more}</td></tr>')
    out.append("<tr>" + "".join(_td(c[1], total_row[c[1]], "", bold=True)
                                for c in cols) + "</tr>")
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
    """הרנדרר של תמונות הייצוא ומטפלי הכפתורים — מ-site/export_card.js.

    **קובץ JS ולא מחרוזת Python.** כ-700 שורות של ציור בקנבס נכתבות ונבדקות
    טוב יותר כקובץ JS (node --check עובר עליו ישירות), ובלוכסנים של ביטויים
    רגולריים אין שכבת בריחה נוספת שאפשר לאבד בדרך. הוא מוטמע ולא מקושר, כמו
    שאר הסקריפטים באתר: עמוד אחד, בלי בקשה נוספת ובלי מטמון שמתיישן.
    """
    js = (ROOT / "site" / "export_card.js").read_text(encoding="utf-8")
    return "<script>\n" + js.replace("</script", "<\\/script") + "\n</script>"


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
