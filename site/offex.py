"""עמוד עסקאות המניה מחוץ לבורסה.

הנתונים נאספים ב-ingest/offex_pull.py מטופס ת076 של מאיה. כאן רק חישוב
ורינדור — כדי ש-build.py לא ימשיך לתפוח.
"""
import json
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
    """מסמן עסקאות שדווחו משני צדדיה של אותה העברה.

    כשגם הקונה וגם המוכר הם בעלי עניין, אותה עסקה מדווחת פעמיים — נמדד
    על רם-און, 47,593 מניות באותו יום משני הכיוונים. ספירת שתיהן הייתה
    מכפילה את ההיקף הכספי. לכן צד אחד מסומן כנספר והשני לא, אבל **שניהם
    מוצגים**: הצד השני הוא שנושא את זהות הצד שכנגד, וזו עיקר התועלת.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r.get("company_id"), r.get("date"), r.get("quantity")), []).append(r)
    for key, g in groups.items():
        for r in g:
            r.setdefault("counted", True)
        if len(g) < 2 or not key[0] or not key[1]:
            continue
        buys = [r for r in g if r["direction"] == "buy"]
        sells = [r for r in g if r["direction"] == "sell"]
        if not (buys and sells):
            continue
        primary = next((r for r in buys if r.get("value_ils")), buys[0])
        for r in g:
            r["paired"] = True
            r["counted"] = r is primary


def stats(rows: list[dict], year: str) -> dict:
    yr = [r for r in rows if (r.get("date") or "")[:4] == year]
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
        "days": len({r.get("date") for r in yr if r.get("date")}),
    }


def cumulative(rows: list[dict], year: str) -> dict[int, float]:
    """השיעור המצטבר בחברה **נכון לרגע כל עסקה**, ולא בסוף השנה.

    שורה שמראה את המצטבר הסופי בכל עסקה מטשטשת בדיוק את מה שמעניין —
    כמה הון כבר החליף ידיים עד אותה נקודה.
    """
    acc: dict[str, float] = {}
    out: dict[int, float] = {}
    for r in sorted(rows, key=lambda x: (x.get("date") or "", x.get("report_id") or 0)):
        if (r.get("date") or "")[:4] != year:
            continue
        c = r.get("company") or "—"
        if r.get("counted", True):
            acc[c] = acc.get(c, 0.0) + (r.get("pct_of_class") or 0.0)
        out[r["report_id"]] = acc.get(c, 0.0)
    return out


def money(v) -> str:
    if not v:
        return "—"
    if v >= 1_000_000:
        return f"{v / 1_000_000:,.2f} מ׳ ₪"
    if v >= 1000:
        return f"{v / 1000:,.0f} א׳ ₪"
    return f"{v:,.0f} ₪"


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
        '<p class="lead">כל עסקה במניה שדווחה כמבוצעת מחוץ לבורסה בטופס ת076 — '
        'הדוח המיידי על שינוי בהחזקות בעלי עניין ונושאי משרה בכירה. '
        '<strong>זה גם גבול הכיסוי:</strong> עסקה שבה אף צד אינו בעל עניין אינה '
        'מדווחת בטופס הזה ואינה מופיעה כאן. מנגד, זו בדיוק הסיבה שיש כאן זהות — '
        'בטופס הזה המדווח חייב להזדהות בשמו ובמספר הזיהוי שלו. לפי הבורסה, גם '
        'עסקה תואמת מסווגת כעסקה מחוץ לבורסה.</p>',
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
        d = r.get("date") or (r.get("published") or "")[:10]
        if d != day:
            day = d
            dd = f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) >= 10 else d
            out.append(f'<li class="daysep">{dd}</li>')
        buy = r["direction"] == "buy"
        who = "הקונה" if buy else "המוכר"
        ctrl = r.get("holder_controller")
        htype = r.get("holder_type")
        dup = "" if r.get("counted", True) else (
            '<span class="dup" title="אותה עסקה דווחה גם מהצד השני של ההעברה; '
            'בסכומים היא נספרת פעם אחת">הצד השני</span>')
        out.append(
            f'<li class="tx {"buy" if buy else "sell"}">'
            f'<div class="tx-head"><span class="dir">{"רכישה" if buy else "מכירה"}</span>'
            f'<a class="co" href="{r["url"]}" target="_blank" rel="noopener">'
            f'{r.get("company") or "—"}</a>'
            f'<span class="sec">{r.get("security") or ""}</span>{dup}</div>'
            f'<div class="tx-who"><b>{who}:</b> {r.get("holder") or "—"}'
            + (f' <em>({htype})</em>' if htype else "")
            + (f'<span class="ctrl">בעל השליטה בו: {ctrl}</span>' if ctrl else "")
            + '</div>'
            f'<div class="tx-nums">'
            f'<span><b>כמות</b><i dir="ltr">{r["quantity"]:,}</i></span>'
            f'<span><b>שער</b><i dir="ltr">{r.get("price") or "—"} אג׳</i></span>'
            f'<span><b>היקף</b><i dir="ltr">{money(r.get("value_ils"))}</i></span>'
            f'<span class="hi"><b>מההון</b><i dir="ltr">{pct(r.get("pct_of_class"))}</i></span>'
            f'<span><b>מצטבר בחברה</b><i dir="ltr">'
            f'{pct(cum.get(r["report_id"]), 2) if cum.get(r["report_id"]) else "—"}</i></span>'
            f'<span><b>החזקה אחרי</b><i dir="ltr">{pct(r.get("holding_pct_after"), 2)}</i></span>'
            f'</div></li>')
    out.append("</ul>")
    out.append('<p class="note">שיעור העסקה מההון נגזר מהכמות ומשיעור ההחזקה שדווחו '
               'בטופס עצמו. כשהשיעור מעוגל לאפס אין ממה לגזור, והשדה נשאר ריק במקום '
               'לנחש. השער מוצג כפי שדווח, באגורות.</p>')
    return "\n".join(out)
