"""עמוד עסקאות המניה מחוץ לבורסה.

הנתונים נאספים ב-ingest/offex_pull.py מטופס ת076 של מאיה. כאן רק חישוב
ורינדור — כדי ש-build.py לא ימשיך לתפוח.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from otc import card, embed, png_button

ROOT = Path(__file__).resolve().parent.parent
SRC_MAYA = "מקור: דיווחי בעלי עניין במערכת מאיה של הבורסה לניירות ערך"
KICKER = "דיווחי בעלי עניין · עסקאות מחוץ לבורסה"
MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט",
          "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]


def load_offex() -> list[dict]:
    """כל עסקאות המניה מחוץ לבורסה שנאספו, מהחדש לישן."""
    src = ROOT / "output" / "offex"
    if not src.is_dir():
        return []
    rows = []
    for f in sorted(src.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: (r.get("date") or "", r.get("report_id") or 0), reverse=True)
    return rows


def mark_pairs(rows: list[dict]) -> None:
    """מסמן מה נספר בסכומים ומה לא, ומשלים שיעור בין שני צדדיה של עסקה.

    שלוש צורות של ספירה כפולה, כולן נמדדו בנתונים:

    · **שני צדדים.** כשגם הקונה וגם המוכר מדווחים — נמדד על רם-און
      (47,593 מניות משני הכיוונים) ועל נקסטפרם (ת078 מול ת079). שניהם
      מוצגים כי הם נושאים את הזהויות, אבל בסכומים נספר צד אחד.
    · **הגשה חוזרת.** אותה עסקה מוגשת פעמיים באותו כיוון עם מזהה אחר —
      נמדד על רכישה עצמית של נאוי גרופ, 137,918 מניות בשני דיווחים.
      נספרת ההגשה המאוחרת.
    · **דיווח מאגד.** ת085 מאגד לעיתים "עסקאות בתוך ומחוץ לבורסה" בלי
      לפצל. אי אפשר לייחס את כל הסכום למסחר מחוץ לבורסה, ולכן הוא מוצג
      עם הסייג ואינו נספר בהיקף.

    בנוסף: כשצד אחד מדווח שיעור מההון והשני לא — למשל מי שחדל להיות
    בעל עניין ואחזקתו התאפסה — השיעור מושלם מהצד שכן דיווח. זו אותה
    עסקה, ולא הערכה.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        r.setdefault("counted", True)
        groups.setdefault((r.get("company_id"), r.get("date"), r.get("quantity")), []).append(r)

    for key, g in groups.items():
        if not key[0] or not key[1]:
            continue

        # הגשה חוזרת: אותו כיוון **ואותו מדווח**. בלי תנאי המדווח, שתי
        # רכישות של אנשים שונים באותה כמות ובאותו יום היו נבלעות זו בזו.
        # נבדק על הנתונים: כל 11 הקבוצות שסומנו הן אכן אותו מדווח.
        by_side: dict[tuple, list[dict]] = {}
        for r in g:
            by_side.setdefault((r["direction"], (r.get("holder") or "").strip()), []).append(r)
        for same in by_side.values():
            if len(same) > 1:
                keep = max(same, key=lambda r: r.get("report_id") or 0)
                for r in same:
                    r["restated"] = r is not keep
                    if r is not keep:
                        r["counted"] = False

        buys = [r for r in g if r["direction"] == "buy" and not r.get("restated")]
        sells = [r for r in g if r["direction"] == "sell" and not r.get("restated")]
        if buys and sells:
            known = next((r.get("pct_of_class") for r in g if r.get("pct_of_class")), None)
            for r in g:
                r["paired"] = True
                if known and not r.get("pct_of_class"):
                    r["pct_of_class"] = known
                    r["pct_inherited"] = True
            primary = next((r for r in buys if r.get("value_ils")), buys[0])
            for r in buys + sells:
                r["counted"] = r is primary

    # דיווח מאגד אינו ניתן לייחוס מלא, ולכן אינו נספר בהיקף
    for r in rows:
        if r.get("partial"):
            r["counted"] = False


def stats(rows: list[dict], year: str) -> dict:
    yr = [r for r in rows if eff_date(r)[:4] == year]
    counted = [r for r in yr if r.get("counted", True)]
    by_company: dict[str, dict] = {}
    for r in counted:
        e = by_company.setdefault(r.get("company") or "—", {"pct": 0.0, "vol": 0, "n": 0})
        e["pct"] += r.get("pct_of_class") or 0.0
        e["vol"] += r.get("value_ils") or 0
        e["n"] += 1
    return {
        "n": len(counted),
        "vol": sum(r.get("value_ils") or 0 for r in counted),
        "companies": by_company,
        "days": len({eff_date(r) for r in yr if eff_date(r)}),
    }


def cumulative(rows: list[dict], year: str) -> dict[int, float]:
    """השיעור המצטבר בחברה **נכון לרגע כל עסקה**, ולא בסוף השנה.

    שורה שמראה את המצטבר הסופי בכל עסקה מטשטשת בדיוק את מה שמעניין —
    כמה הון כבר החליף ידיים עד אותה נקודה.
    """
    acc: dict[str, float] = {}
    out: dict[int, float] = {}
    for r in sorted(rows, key=lambda x: (eff_date(x), x.get("report_id") or 0)):
        if eff_date(r)[:4] != year:
            continue
        c = r.get("company") or "—"
        if r.get("counted", True):
            acc[c] = acc.get(c, 0.0) + (r.get("pct_of_class") or 0.0)
        out[r["report_id"]] = acc.get(c, 0.0)
    return out


PLACEHOLDER = {"-", "--", "---", "–", "—", ".", "_________", "אין",
               "לא רלוונטי", "לא ידוע", "לא רלוונטית", "ללא"}


def clean(v):
    """ערך שהמדווח מילא רק כדי לא להשאיר שדה ריק אינו מידע.

    הניקוי חוזר גם כאן ולא רק באיסוף: כך רשומות שכבר נאספו מוצגות נכון
    בלי להריץ סריקה חוזרת של כל השנה.
    """
    v = re.sub(r"_+", " ", (v or "")).strip(" 	_-–—")
    v = re.sub(r"\s{2,}", " ", v)
    return "" if v in PLACEHOLDER else v


UNIT = {"agorot": "אג׳", "ils": "₪", "other": ""}

KIND = {
    "holdings": ("שינוי החזקות", "ת076"),
    "threshold": ("חציית סף בעל עניין", "ת078/9"),
    "buyback": ("רכישה עצמית", "ת085"),
}


# שמות של אנשים וחברות מגיעים ממאיה ונכתבים ל-HTML. גרשיים בשם חברה
# הם הכלל ולא היוצא מן הכלל ("אלקו בע\"מ"), ולכן בריחה אינה אופציונלית.
def esc(t) -> str:
    return (str(t if t is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def money(v) -> str:
    if not v:
        return "—"
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:,.2f} מיליארד ₪"
    if v >= 1_000_000:
        return f"{v / 1_000_000:,.1f} מ׳ ₪"
    if v >= 1000:
        return f"{v / 1000:,.0f} א׳ ₪"
    return f"{v:,.0f} ₪"


def rate(v) -> str:
    """שער באגורות. 1005.0 הוא רעש; 1005 הוא מספר."""
    if v in (None, ""):
        return "—"
    return f"{v:,.0f}" if float(v) == int(float(v)) else f"{v:,.2f}"


def eff_date(r: dict) -> str:
    """תאריך העסקה, ובהיעדרו מועד הפרסום — כדי שרשומה בלי תאריך לא
    תיפול מחוץ לסטטיסטיקה השנתית בשקט."""
    return r.get("date") or (r.get("published") or "")[:10]


def pct(v, digits: int = 3) -> str:
    return "—" if v in (None, "") else f"{v:.{digits}f}%"


def holders_summary(rows: list[dict], year: str) -> str:
    """מי צבר ומי מימש — לפי מדווח, ולא לפי עסקה.

    **עסקה בודדת אינה מספרת מי זז.** אותו בעל עניין מדווח לאורך השנה
    בעשרות הודעות קטנות, וכל אחת בנפרד היא רעש; הסכום שלהן הוא הסיפור.
    הטבלה מצרפת לפי מדווח וחברה, ומדרגת לפי **השינוי נטו** בחלק מהון
    החברה — לא לפי היקף כספי, כי מיליון שקל בחברה קטנה משנה שליטה
    ובגדולה לא, ולא לפי המחזור המצטבר.

    **סכימת המחזור דירגה מי שלא זז.** הגרסה הקודמת חיברה
    `abs(pct_of_class)` של כל דיווח, ולכן מי שקנה 0.5% ומכר 0.5% הופיע
    כמי שהזיז 1% מהחברה בזמן שהחזקתו לא השתנתה כלל — ובראש הטבלה, לפני
    מי שצבר באמת. הסימן נלקח מ-`direction`, כי `pct_of_class` תמיד גודל
    מוחלט. אותו תיקון חל על ההיקף הכספי: `abs(net)` הראה קונה נטו ומוכר
    נטו באותו מספר בדיוק.

    עמודת "החזקה אחרי" היא **מלאי ולא תנועה** — 60%–75% שם הם בעל שליטה
    בחברה קטנה, לא היקף העסקה. היא נשארת כי היא ההקשר לשינוי, והכותרות
    מפרידות בין השתיים.

    `counted: false` הוא הצד השני של עסקה שכבר נספרה, ו-`partial: true`
    מאגד מסחר בתוך ומחוץ לבורסה בלי לפצל; שניהם יוצאים מהסכימה כדי שלא
    ייספרו פעמיים או ייוחסו כולם למחוץ לבורסה.
    """
    agg: dict[tuple, dict] = {}
    for r in rows:
        if (r.get("date") or "")[:4] != year:
            continue
        if r.get("counted") is False or r.get("partial"):
            continue
        # מאיה משאירה לעיתים קווים תחתונים מתבנית הטופס בקצה השם
        # ("שותפות מוגבלת _"), והם הופיעו כך גם בטבלה וגם בתמונה.
        who = (r.get("holder") or "").strip(" _")
        co = (r.get("company") or "").strip(" _")
        if not who or not co:
            continue
        k = (who, co)
        e = agg.setdefault(k, {
            "holder": who, "company": co, "buy": 0.0, "sell": 0.0,
            "n": 0, "pct_buy": 0.0, "pct_sell": 0.0,
            "after": None, "kinds": set()})
        e["n"] += 1
        v = r.get("value_ils") or 0
        q = abs(r.get("pct_of_class") or 0)
        if r.get("direction") == "buy":
            e["buy"] += v
            e["pct_buy"] += q
        else:
            e["sell"] += v
            e["pct_sell"] += q
        if r.get("holding_pct_after") is not None:
            e["after"] = r["holding_pct_after"]
        if r.get("kind"):
            e["kinds"].add(r["kind"])
    if not agg:
        return ""
    for e in agg.values():
        e["pct"] = e["pct_buy"] - e["pct_sell"]
        e["net"] = e["buy"] - e["sell"]
    top = sorted(agg.values(), key=lambda e: -abs(e["pct"]))[:20]

    def side(e):
        """הכיוון הוא של התוצאה, לא של הפעילות.

        "מעורב" תיאר מי שהיו לו עסקאות לשני הכיוונים, וזה נכון אך אינו
        עונה על השאלה — בסוף השנה הוא צבר או מימש. מי שסחר לשני הכיוונים
        מסומן כך בסוגריים, אבל הכיוון עצמו הוא של הנטו.
        """
        d = "צבירה" if e["pct"] > 0 else "מימוש" if e["pct"] < 0 else "ללא שינוי"
        return d + (" (דו-כיווני)" if e["buy"] and e["sell"] else "")

    def signed(v, unit=""):
        # מקף ASCII ולא − (MINUS SIGN): הציור בקנבס בודק
        # v.charAt(0) === "-" כדי לצבוע שלילי באדום, וסימן טיפוגרפי
        # יפה יותר היה יוצא מהתמונה אפור כמו ערך חסר סימן.
        return ("+" if v > 0 else "-" if v < 0 else "") + (
            f"{abs(v):.2f}%" if unit == "%" else money(abs(v)))

    # **טבלה אחת, שני פלטים** — כמו ב-otc.period_table. העמוד הראה 20
    # שורות בשבע עמודות והתמונה 14 בשש: "החזקה אחרי" פשוט לא הייתה בה,
    # ושורת ה"ועוד" ספרה מדווחים וקראה להם "ניירות".
    cols = [["מדווח", "name", "rtl"], ["חברה", "co", "rtl"],
            ["כיוון", "side", "rtl"], ["עסקאות", "n", "ltr"],
            ["היקף נטו", "value", "ltr"], ["שינוי נטו בהון", "cap", "ltr"],
            ["החזקה אחרי", "after", "ltr"]]
    cells = [{
        "name": e["holder"], "co": e["company"], "side": side(e),
        "n": str(e["n"]), "value": signed(e["net"]),
        "cap": signed(e["pct"], "%"),
        "after": f'{e["after"]:.2f}%' if e["after"] is not None else "—",
        "_cls": "up" if e["pct"] > 0 else "down" if e["pct"] < 0 else "",
    } for e in top]
    rest = len(agg) - len(top)
    more = f"ועוד {rest} מדווחים עם שינוי נטו קטן יותר." if rest > 0 else ""

    body = []
    for r in cells:
        body.append(
            f'<tr><td class="city">{esc(r["name"])}</td>'
            f'<td>{esc(r["co"])}</td>'
            f'<td>{esc(r["side"])}</td>'
            f'<td dir="ltr">{r["n"]}</td>'
            f'<td class="key" dir="ltr">{esc(r["value"])}</td>'
            f'<td class="{r["_cls"]}" dir="ltr">{esc(r["cap"])}</td>'
            f'<td dir="ltr">{esc(r["after"])}</td></tr>')
    if more:
        body.append(f'<tr><td colspan="{len(cols)}" class="note">{more}</td></tr>')

    buyers_n = sum(1 for e in agg.values() if e["pct"] > 0)
    sellers_n = sum(1 for e in agg.values() if e["pct"] < 0)
    payload = card(
        f"מי צבר ומי מימש · מתחילת {year}",
        "כל הדיווחים של בעל עניין באותה חברה מצורפים יחד, ומדורגים לפי השינוי נטו "
        "בחלקו מהון החברה — רכישות פחות מכירות.",
        [{"type": "stats", "items": [
            {"label": "מדווחים", "value": str(len(agg)),
             "cap": f"{buyers_n} צברו · {sellers_n} מימשו"},
            {"label": "עסקאות", "value": f'{sum(e["n"] for e in agg.values()):,}'},
            {"label": "היקף", "value": money(sum(e["buy"] + e["sell"] for e in agg.values())),
             "cap": "רכישות ומכירות יחד"}]},
         {"type": "table", "title": "20 השינויים הגדולים בחלק מההון", "cols": cols,
          "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in cells],
          "moreText": more}],
        # הטבלה הזו ממאיה ולא מסקירת הבורסה.
        file=f"tlv-offex-holders-{year}", kicker=KICKER, source=SRC_MAYA)

    lines = [f"בעלי עניין · מתחילת {year}",
             f"{len(agg)} מדווחים, {sum(e['n'] for e in agg.values()):,} עסקאות"]
    # מי שלא זז אינו ציוץ. הוא נשאר בטבלה כהקשר, אבל שורה
    # "ללא שינוי 0.00% מההון" בתקציר היא בזבוז של אחת משלוש השורות.
    for e in [e for e in top if abs(e["pct"]) >= 0.005][:3]:
        lines.append(f"{e['holder'][:24]} · {e['company']}: "
                     f"{side(e)} {abs(e['pct']):.2f}% מההון")
    tw = ""
    for ln in lines:
        nxt = (tw + "\n" + ln) if tw else ln
        if len(nxt) > 268:
            break
        tw = nxt
    tw += "\ntlvtaseview.com"

    return "\n".join([
        '<h2>מי צבר ומי מימש</h2>',
        '<p class="note">צירוף כל הדיווחים של אותו בעל עניין באותה חברה '
        'מתחילת השנה, מדורג לפי <b>השינוי נטו</b> בחלקו מהון החברה — '
        'רכישות פחות מכירות, ולא סכום המחזור. מי שקנה ומכר את אותו שיעור '
        'לא זז, ולכן אינו בראש הטבלה. "היקף נטו" הוא ההפרש הכספי באותו '
        'חישוב. <b>"החזקה אחרי"</b> היא ההחזקה הכוללת של אותו בעל עניין '
        'בחברה אחרי הדיווח האחרון — מלאי ולא תנועה, ולכן שיעורים של '
        'עשרות אחוזים שם הם בעל שליטה ולא היקף העסקה.</p>',
        f'<div class="otc-tweet" id="tw-holders"><pre>'
        + esc(tw) + '</pre></div>',
        embed("holders", payload),
        f'<p class="otc-acts">{png_button(key="holders")}'
        '<button type="button" class="otc-copy" data-key="holders">'
        'העתקת התקציר</button></p>',
        '<div class="tw"><table class="nadlan"><thead><tr>'
        + "".join(f"<th>{c[0]}</th>" for c in cols)
        + '</tr></thead><tbody>',
        "".join(body),
        '</tbody></table></div>',
    ])


# סוג המדווח כפי שמאיה כותבת אותו ארוך מכדי שורה בתמונה, ואינו אומר יותר
# מ"בעל עניין".
def _type_short(v) -> str:
    v = clean(v)
    return "בעל עניין" if v.startswith(("בעל ענין שאינו", "בעל עניין שאינו")) else v


def _ctrl_short(v) -> str:
    """בעל השליטה במדווח — לתמונה בלבד.

    **בלי מספרי זהות.** השדה בטופס מכיל לעיתים "ת.ז 007048671" לכל בעל
    שליטה, בכמה כתיבים ("ת.ז..007511652", "ת.ז. 006580211"). זה ציבורי
    במאיה, אבל תמונה נועדה להפצה, ומספר זהות אינו מידע שהקורא צריך. ובלי
    הפניות לטופס עצמו ("ראה סעיף 5 להלן"), שאין להן משמעות מחוצה לו.
    """
    v = clean(v)
    if not v or re.search(r"להלן|לעיל|ראה|ראו|כמפורט|בהערות|פרטים", v):
        return ""
    v = re.sub(r"(?:ת[\s.\"״׳']*ז|ח[\s.\"״׳']*פ|מס['׳]?\s*(?:זהות|חברה)|ID)[\s.:\-\"״׳']*\d[\d\-]{4,}", ",", v)
    v = re.sub(r"\d{7,10}", ",", v)
    v = re.sub(r"(?:^|(?<=[\s,]))\d{1,2}[.)]\s+", "", v)
    v = re.sub(r"\s*,[\s,]*", ", ", v)
    return re.sub(r"\s{2,}", " ", v).strip(" ,;·")


def report_data(rows: list[dict]) -> dict:
    """הדיווחים בצורה שהדפדפן מצייר מהם תמונה ליום או לחודש.

    **מחרוזות התצוגה נבנות כאן, לא בדפדפן.** כמות, שער, היקף ושיעור מההון
    מעוצבים באותן פונקציות שמעצבות את הרשימה בעמוד, כך שהתמונה והעמוד אינם
    יכולים להציג אותו דיווח בשני פורמטים. הדפדפן רק מסנן לפי יום או חודש
    ומסכם — ספירה, היקף ומי הגדול.

    `cnt` הוא מה ש-mark_pairs קבע: הצד השני של עסקה, הגשה חוזרת ודיווח
    מאגד אינם נספרים בהיקף — בתמונה בדיוק כמו בסיכומי העמוד.
    """
    out = []
    for r in rows:
        d = eff_date(r)
        if not d:
            continue
        counted = r.get("counted", True) is not False and not r.get("partial")
        out.append({
            "id": r.get("report_id"), "d": d,
            "co": (r.get("company") or "—").strip(" _"),
            "who": clean(r.get("holder")), "type": _type_short(r.get("holder_type")),
            "ctrl": _ctrl_short(r.get("holder_controller")),
            "dir": "buy" if r.get("direction") == "buy" else "sell",
            "kind": r.get("kind") or "holdings",
            "form": KIND.get(r.get("kind") or "holdings", ("", ""))[1],
            "q": f'{r["quantity"]:,}' if r.get("quantity") is not None else "—",
            # שער 0 הוא שדה שלא מולא (עסקה בלי תמורה במזומן), לא מחיר.
            "px": (f'{rate(r.get("price"))} {UNIT.get(r.get("currency") or "agorot", "")}'.strip()
                   if r.get("price") not in (None, "", 0, 0.0) else "—"),
            "v": money(r.get("value_ils")), "vn": r.get("value_ils") or 0,
            "pct": pct(r.get("pct_of_class")), "pn": r.get("pct_of_class"),
            "after": pct(r.get("holding_pct_after"), 2),
            "inh": bool(r.get("pct_inherited")),
            "partial": bool(r.get("partial")), "restated": bool(r.get("restated")),
            "other": (not r.get("partial") and not r.get("restated")
                      and r.get("counted", True) is False),
            "cnt": counted,
        })
    return {"rows": out}


def page(rows: list[dict], year: str, head: bool = True) -> str:
    """הגוף של שכבת מאיה.

    `head=False` כשהשכבה מוטמעת בעמוד שכבר פתח כותרת ראשית — אז גם
    ההסבר על מה שאינו במאיה מיותר, כי הוא נאמר שם על שני המקורות יחד.
    """
    if not rows:
        empty = '<p class="lead">טרם נאספו דיווחי מאיה על עסקאות מחוץ לבורסה.</p>'
        return empty if not head else (
            '<div class="dash-head"><h1>עסקאות מניה מחוץ לבורסה</h1></div>' + empty)

    mark_pairs(rows)
    st = stats(rows, year)
    cum = cumulative(rows, year)

    out = []
    if head:
        out += [
            '<div class="dash-head"><h1>עסקאות מניה מחוץ לבורסה</h1>',
            f'<span class="stamp">מתחילת {year} · נבנה {datetime.now():%d/%m %H:%M}</span></div>',
        ]
    out.append(
        '<p class="lead">דיווחי מאיה, משלושה סוגי טופס: <strong>ת076</strong> '
        'שינוי בהחזקות בעל עניין; <strong>ת078/ת079</strong> מי שנעשה או חדל '
        'להיות בעל עניין — אלה העסקאות שחוצות את סף 5%, ולרוב הגדולות שבהן; '
        'ו<strong>ת085</strong> רכישה עצמית של החברה במניותיה, שבה אין צד שני '
        'מזוהה. לפי הבורסה גם עסקה תואמת מסווגת כמחוץ לבורסה.</p>')
    out.append(holders_summary(rows, year))
    if head:
        out.append(
            '<p class="lead">מה שאינו כאן: עסקה מחוץ לבורסה שאף צד בה אינו בעל '
            'עניין ואינה נוגעת במניות רדומות אינה מחייבת דיווח, ולכן אינה '
            'מתועדת במאיה כלל.</p>')
    out += [
        '<section class="strip">',
        f'<div class="tile"><span class="lbl">עסקאות מתחילת השנה</span>'
        f'<span class="val" dir="ltr">{st["n"]}</span>'
        f'<span class="chg">ב-{st["days"]} ימים</span></div>',
        f'<div class="tile"><span class="lbl">היקף כספי מצטבר</span>'
        f'<span class="val" dir="ltr">{money(st["vol"])}</span>'
        f'<span class="chg">בלי ספירה כפולה</span></div>',
        f'<div class="tile"><span class="lbl">חברות</span>'
        f'<span class="val" dir="ltr">{len(st["companies"])}</span>'
        f'<span class="chg">מניות בלבד</span></div>',
        '</section>',
    ]

    top = sorted(st["companies"].items(), key=lambda kv: -kv[1]["pct"])[:12]
    if top:
        mx = max(v["pct"] for _, v in top) or 1
        out.append('<h2>שיעור מצטבר מההון, לפי חברה</h2>')
        out.append('<p class="lead">סכום חלקן של העסקאות בהון המניות של אותה חברה, '
                   f'מתחילת {year}.</p>')
        out.append(embed("companies", card(
            f"שיעור מצטבר מההון, לפי חברה · מתחילת {year}",
            "סכום חלקן של העסקאות המדווחות בהון המניות של כל חברה — בלי ספירה כפולה "
            "של שני צדדיה של אותה עסקה.",
            [{"type": "stats", "items": [
                {"label": "עסקאות מתחילת השנה", "value": str(st["n"]), "cap": f'ב-{st["days"]} ימים'},
                {"label": "היקף כספי מצטבר", "value": money(st["vol"]), "cap": "בלי ספירה כפולה"},
                {"label": "חברות", "value": str(len(st["companies"])), "cap": "מניות בלבד"}]},
             {"type": "bars", "title": f"{len(top)} החברות עם השיעור הגבוה",
              "rows": [{"label": name, "pct": v["pct"], "pctText": pct(v["pct"], 2),
                        "volText": money(v["vol"])} for name, v in top]}],
            file=f"tlv-offex-companies-{year}", kicker=KICKER, source=SRC_MAYA)))
        out.append(f'<p class="otc-acts">{png_button(key="companies")}</p>')
        out.append('<ul class="offex-bars">')
        for name, v in top:
            w = max(2, round(v["pct"] / mx * 100))
            out.append(
                f'<li><span class="nm">{name}</span>'
                f'<span class="bar"><i style="width:{w}%"></i></span>'
                f'<span class="pv" dir="ltr">{pct(v["pct"], 2)}</span>'
                f'<span class="mv" dir="ltr">{money(v["vol"])}</span></li>')
        out.append('</ul>')

    out.append('<h2>העסקאות</h2>')
    # **תמונה ליום ולחודש.** כל כותרת יום וכל כותרת חודש נושאות כפתור ייצוא;
    # התמונה נבנית בדפדפן מהנתונים המוטמעים כאן, ולכן אין מטען נפרד לכל יום.
    out.append('<p class="lead offex-exp-lead">כל יום וכל חודש ברשימה אפשר לייצא כתמונה — '
               'הכפתור ליד התאריך. תמונת היום כוללת את כל הדיווחים של אותו יום; תמונת החודש — '
               'את סיכום החודש, עיקריו ו-25 הדיווחים עם החלק הגדול מהון החברה.</p>')
    out.append('<script type="application/json" id="offex-data">'
               + json.dumps(report_data(rows), ensure_ascii=False).replace("</", "<" + chr(92) + "/")
               + '</script>')
    per_month: dict[str, int] = {}
    per_day: dict[str, int] = {}
    for r in rows:
        d = eff_date(r)
        per_month[d[:7]] = per_month.get(d[:7], 0) + 1
        per_day[d] = per_day.get(d, 0) + 1
    day = None
    month = None
    out.append('<ul class="offex">')
    for r in rows:
        d = eff_date(r)
        if d[:7] != month and len(d) >= 7:
            month = d[:7]
            n_m = per_month.get(month, 0)
            out.append(
                f'<li class="monthsep"><span class="mn">{MONTHS[int(month[5:7]) - 1]} {month[:4]}</span>'
                f'<span class="cnt">{n_m} {"דיווח" if n_m == 1 else "דיווחים"}</span>'
                f'{png_button("ייצוא החודש", cls="sm", month=month)}</li>')
        if d != day:
            day = d
            dd = f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) >= 10 else d
            n_d = per_day.get(d, 0)
            btn = png_button("ייצוא היום", cls="sm", day=d) if len(d) >= 10 else ""
            out.append(f'<li class="daysep"><span class="dd">{dd}</span>'
                       f'<span class="cnt">{n_d} {"דיווח" if n_d == 1 else "דיווחים"}</span>{btn}</li>')
        buy = r["direction"] == "buy"
        who = "הקונה" if buy else "המוכר"
        ctrl = clean(r.get("holder_controller"))
        htype = clean(r.get("holder_type"))
        kind_label, kind_form = KIND.get(r.get("kind") or "holdings", ("", ""))
        tags = []
        if kind_form:
            tags.append(f'<span class="kind" title="{kind_label}">{kind_form}</span>')
        # התגיות מצטברות: דיווח מאגד שהוגש שוב הוא גם וגם, והצגת אחת
        # מהן בלבד מסתירה מהקורא למה אותה עסקה מופיעה פעמיים.
        if r.get("partial"):
            tags.append('<span class="dup" title="הדיווח מאגד עסקאות בתוך ומחוץ '
                        'לבורסה בלי לפצל, ולכן אינו נספר בהיקף">מאגד</span>')
        if r.get("restated"):
            tags.append('<span class="dup" title="הוגש שוב עם מזהה אחר; '
                        'נספרת ההגשה המאוחרת">הוגש שוב</span>')
        elif not r.get("partial") and not r.get("counted", True):
            tags.append('<span class="dup" title="אותה עסקה דווחה גם מהצד השני; '
                        'בסכומים נספרת פעם אחת">הצד השני</span>')
        dup = "".join(tags)
        out.append(
            f'<li class="tx {"buy" if buy else "sell"}">'
            f'<div class="tx-head"><span class="dir">{"רכישה" if buy else "מכירה"}</span>'
            f'<a class="co" href="{r["url"]}" target="_blank" rel="noopener">'
            f'{r.get("company") or "—"}</a>'
            f'<span class="sec">{r.get("security") or ""}</span>{dup}</div>'
            f'<div class="tx-who"><b>{who}:</b> {clean(r.get("holder")) or "—"}'
            + (f' <em>({htype})</em>' if htype else "")
            + (f'<span class="ctrl">בעל השליטה בו: {ctrl}</span>' if ctrl else "")
            + '</div>'
            f'<div class="tx-nums">'
            f'<span><b>כמות</b><i dir="ltr">{r["quantity"]:,}</i></span>'
            f'<span><b>שער</b><i dir="ltr">{rate(r.get("price"))} '
            f'{UNIT.get(r.get("currency") or "agorot", "")}</i></span>'
            f'<span><b>היקף</b><i dir="ltr">{money(r.get("value_ils"))}</i></span>'
            f'<span class="hi"><b>מההון{"*" if r.get("pct_inherited") else ""}</b>'
            f'<i dir="ltr">{pct(r.get("pct_of_class"))}</i></span>'
            f'<span><b>מצטבר בחברה</b><i dir="ltr">'
            f'{pct(cum.get(r["report_id"]), 2) if cum.get(r["report_id"]) else "—"}</i></span>'
            f'<span><b>החזקה אחרי</b><i dir="ltr">{pct(r.get("holding_pct_after"), 2)}</i></span>'
            f'</div></li>')
    out.append("</ul>")
    out.append('<p class="note">שיעור העסקה מההון נגזר מהכמות ומשיעור ההחזקה שדווחו '
               'בטופס עצמו. כשהשיעור מעוגל לאפס אין ממה לגזור, והשדה נשאר ריק במקום '
               'לנחש. כוכבית ליד "מההון" — השיעור הושלם מהצד השני של אותה עסקה. '
               'השער מוצג כפי שדווח: ת076 ו-ת078/9 נוקבים באגורות, ת085 בשקלים.</p>')
    return "\n".join(out)
