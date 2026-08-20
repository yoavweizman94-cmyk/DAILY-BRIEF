"""עמוד עסקאות המניה מחוץ לבורסה.

הנתונים נאספים ב-ingest/offex_pull.py מטופס ת076 של מאיה. כאן רק חישוב
ורינדור — כדי ש-build.py לא ימשיך לתפוח.
"""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


def page(rows: list[dict], year: str) -> str:
    if not rows:
        return ('<div class="dash-head"><h1>עסקאות מניה מחוץ לבורסה</h1></div>'
                '<p class="lead">טרם נאספו עסקאות. הסריקה רצה בכל מהדורה.</p>')

    mark_pairs(rows)
    st = stats(rows, year)
    cum = cumulative(rows, year)

    out = [
        '<div class="dash-head"><h1>עסקאות מניה מחוץ לבורסה</h1>',
        f'<span class="stamp">מתחילת {year} · נבנה {datetime.now():%d/%m %H:%M}</span></div>',
        '<p class="lead">כל עסקה במניה שדווחה במאיה כמבוצעת מחוץ לבורסה, '
        'משלושה סוגי דיווח: <strong>ת076</strong> שינוי בהחזקות בעל עניין; '
        '<strong>ת078/ת079</strong> מי שנעשה או חדל להיות בעל עניין — אלה '
        'העסקאות שחוצות את סף 5%, ולרוב הגדולות שבהן; ו<strong>ת085</strong> '
        'רכישה עצמית של החברה במניותיה, שבה אין צד שני מזוהה. לפי הבורסה גם '
        'עסקה תואמת מסווגת כמחוץ לבורסה.</p>'
        '<p class="lead">מה שאינו כאן: עסקה מחוץ לבורסה שאף צד בה אינו בעל '
        'עניין ואינה נוגעת במניות רדומות אינה מחייבת דיווח, ולכן אינה מתועדת '
        'במאיה כלל. בעסקאות שכן מדווחות המדווח חייב להזדהות — ומכאן הזהויות '
        'שבעמוד.</p>',
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
    day = None
    out.append('<ul class="offex">')
    for r in rows:
        d = eff_date(r)
        if d != day:
            day = d
            dd = f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) >= 10 else d
            out.append(f'<li class="daysep">{dd}</li>')
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
