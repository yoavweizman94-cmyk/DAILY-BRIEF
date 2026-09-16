# -*- coding: utf-8 -*-
"""עמוד נתוני הלמ"ס — מדדים, לוח פרסומים, הודעות וניתוח השלכות.

נבנה מ-output/cbs/, שנכתב ע"י ingest/cbs_pull.py (נתונים) ו-
scripts/analyze_cbs.py (ניתוחים). שני הקבצים מתעדכנים בצנרת cbs-watch
שלוש פעמים ביום.

**העמוד קורא גם בלי ניתוח.** הודעה שטרם נותחה מוצגת עם התקציר של הלמ"ס
ושורה שאומרת שהניתוח ממתין; הודעה שאינה נוגעת לשוק מוצגת בלי ניתוח ואומרת
זאת. אחרת עמוד שהניתוח שלו נכשל נראה בדיוק כמו עמוד שלא פורסם בו דבר.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CBS = ROOT / "output" / "cbs"

DAYS = 30          # כמה ימים של הודעות מוצגים
OPEN_LATEST = 4    # כמה הודעות אחרונות מוצגות פתוחות; השאר מקופלות
CAL_DAYS = 14
WEEKDAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
DIR_CLASS = {"חיובי": "up", "שלילי": "down", "מעורב": "mixed"}


def _jsonl(p: Path) -> list[dict]:
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def load() -> dict:
    snap = {}
    if (CBS / "snapshot.json").exists():
        try:
            snap = json.loads((CBS / "snapshot.json").read_text(encoding="utf-8"))
        except ValueError:
            snap = {}
    releases = []
    for p in sorted((CBS / "releases").glob("*.jsonl")):
        releases += _jsonl(p)
    releases.sort(key=lambda r: (r.get("date") or "", r.get("published") or "", str(r.get("id") or "")),
                  reverse=True)
    analyses = {}
    for p in sorted((CBS / "analyses").glob("*.jsonl")):
        for a in _jsonl(p):
            if a.get("release_id") is not None:
                analyses[str(a["release_id"])] = a
    return {"snap": snap, "releases": releases, "analyses": analyses}


# --------------------------------------------------------------------------
# עזרים

def _num(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return escape(str(v)) if v not in (None, "") else "—"
    if abs(x) >= 10000:
        return f"{x:,.0f}"
    if abs(x) >= 1000:
        return f"{x:,.0f}" if x == int(x) else f"{x:,.1f}"
    if x == int(x):
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _period(iso: str | None) -> str:
    if not iso or len(iso) < 7:
        return "—"
    return f"{iso[5:7]}/{iso[:4]}"


def _dm(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if iso and len(iso) >= 10 else "—"


def _para(text) -> str:
    """טקסט של המודל ל-HTML: בריחה, פסקאות, והדגשה ב-**...** בלבד."""
    if not text:
        return ""
    t = escape(str(text))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    parts = [p.strip() for p in re.split(r"\n\s*\n|\n", t) if p.strip()]
    return "".join(f"<p>{p}</p>" for p in parts)


def _dir(d: str | None) -> str:
    if not d:
        return ""
    return f'<span class="cbs-dir {DIR_CLASS.get(d, "flat")}">{escape(d)}</span>'


def _spark(points: list[dict]) -> str:
    """קו מגמה כ-SVG. רק נקודות באותו בסיס מדד כמו האחרונה — החלפת בסיס
    בתוך החלון הייתה מציירת קפיצה שאינה שינוי מחירים."""
    if not points:
        return ""
    base = points[-1].get("base")
    vals = [p["value"] for p in points
            if p.get("base") == base and isinstance(p.get("value"), (int, float))]
    if len(vals) < 2:
        return ""
    w, h = 240.0, 48.0
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = w / (len(vals) - 1)
    ys = [h - 5 - (v - lo) / span * (h - 10) for v in vals]
    pts = " ".join(f"{i * step:.1f},{y:.1f}" for i, y in enumerate(ys))
    return (f'<svg class="cbs-spark" viewBox="0 0 {w:.0f} {h:.0f}" preserveAspectRatio="none" '
            f'aria-hidden="true"><polyline points="{pts}" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{(len(vals) - 1) * step:.1f}" cy="{ys[-1]:.1f}" r="2.8" '
            f'fill="currentColor"/></svg>')


# --------------------------------------------------------------------------
# חלקי העמוד

def indicators_html(snap: dict) -> str:
    rows = snap.get("indicators") or []
    if not rows:
        return ""
    # הלמ"ס מחזיקה לעיתים שני פריטים באותה כותרת ובלי תיאור — הוצאה לצריכה
    # ציבורית רבעונית ושנתית, למשל. בלי יחידה ובלי תיאור אי אפשר להבחין
    # ביניהם, ולכן נשאר רק העדכני.
    latest = {}
    for i in rows:
        key = (i.get("title"), i.get("label") or "")
        if key not in latest or (i.get("period") or "") > (latest[key].get("period") or ""):
            latest[key] = i
    rows = [i for i in rows if latest.get((i.get("title"), i.get("label") or "")) is i]
    tiles = []
    for i in rows:
        label = i.get("label") or i.get("title") or ""
        tip = i.get("explain") or ""
        tiles.append(
            f'<div class="cbs-tile"{f" title={chr(34)}{escape(tip)}{chr(34)}" if tip else ""}>'
            f'<div class="lbl">{escape(i.get("title") or "")}'
            + (f'<span class="sub">{escape(label)}</span>' if label and label != i.get("title") else "")
            + '</div>'
            f'<div class="val" dir="ltr">{_num(i.get("value"))}'
            f'<small>{escape(i.get("unit") or "")}</small></div>'
            f'<div class="meta">קודם: <span dir="ltr">{_num(i.get("previous"))}</span>'
            f' · {_period(i.get("period"))}</div></div>')
    return ('<h2>מדדים עיקריים</h2>'
            '<p class="note">המספרים שהלמ"ס מציגה בדף הבית שלה, עם הערך הקודם והתקופה. '
            'מעבר עם העכבר על אריח מציג את הגדרת המונח בלשון הלמ"ס.</p>'
            f'<div class="cbs-grid">{"".join(tiles)}</div>')


def series_html(snap: dict) -> str:
    cards = []
    for code, s in (snap.get("series") or {}).items():
        pts = s.get("points") or []
        if not pts:
            continue
        last = pts[-1]
        m, y = last.get("m"), last.get("y")
        cards.append(
            f'<div class="cbs-card"><div class="lbl">{escape(s.get("name") or code)}</div>'
            f'<div dir="ltr">{_spark(pts)}</div>'
            f'<div class="nums"><span>{_period(last.get("period") + "-01")}</span>'
            f'<span>מדד <b dir="ltr">{_num(last.get("value"))}</b></span>'
            f'<span>חודשי <b dir="ltr">{_signed(m)}</b></span>'
            f'<span>שנתי <b dir="ltr">{_signed(y)}</b></span></div>'
            f'<div class="sub">בסיס: {escape(str(last.get("base") or "—"))}</div></div>')
    if not cards:
        return ""
    return ('<h2>מדדי מחירים — 25 חודשים</h2>'
            f'<div class="cbs-series">{"".join(cards)}</div>')


def _signed(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{'+' if x > 0 else ''}{x:.1f}%"


def calendar_html(snap: dict) -> str:
    today = date.today().isoformat()
    hi = (date.today() + timedelta(days=CAL_DAYS)).isoformat()
    rows = [c for c in (snap.get("calendar") or []) if today <= (c.get("date") or "") <= hi]
    if not rows:
        return ""
    body = []
    for c in rows:
        d = c["date"]
        wd = WEEKDAYS[datetime.strptime(d, "%Y-%m-%d").weekday()]
        cls = ' class="cbs-rel-row"' if c.get("relevant") else ""
        tag = ' <span class="cbs-today">היום</span>' if d == today else ""
        body.append(f'<tr{cls}><td dir="ltr">{_dm(d)}</td><td>{wd}{tag}</td>'
                    f'<td class="city">{escape(c.get("title") or "")}</td>'
                    f'<td>{escape(c.get("interval") or "")}</td></tr>')
    return ('<h2>פרסומים צפויים</h2>'
            f'<p class="note">לוח הפרסומים של הלמ"ס ל-{CAL_DAYS} הימים הקרובים. '
            'פרסומים שנוגעים לשוק מודגשים, והם אלה שינותחו כשיתפרסמו.</p>'
            '<div class="tw"><table class="nadlan cbs-cal"><thead><tr>'
            '<th>תאריך</th><th>יום</th><th>פרסום</th><th>תדירות</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def _analysis_html(a: dict) -> str:
    out = []
    figs = [f for f in (a.get("key_figures") or []) if isinstance(f, dict)]
    if figs:
        # **כרטיסים ולא טבלה.** השינוי והתקופה הם משפטים, ובטבלת האתר (שאינה
        # שוברת שורות) הם מתחו אותה לרוחב של מסך וחצי ודחקו את שם הנתון
        # לעמודה של מילה אחת בשורה.
        out.append('<div class="cbs-kf">' + "".join(
            f'<div class="kf"><div class="lbl">{escape(str(f.get("label") or ""))}</div>'
            f'<div class="val" dir="ltr">{escape(str(f.get("value") or ""))}</div>'
            + (f'<div class="chg">{escape(str(f.get("change")))}</div>' if f.get("change") else "")
            + (f'<div class="per">{escape(str(f.get("period")))}</div>' if f.get("period") else "")
            + '</div>' for f in figs) + '</div>')
    if a.get("what_happened"):
        out.append(f'<section class="cbs-sec"><h3>מה פורסם</h3>{_para(a["what_happened"])}</section>')
    macro = [m for m in (a.get("macro") or []) if isinstance(m, dict)]
    if macro:
        out.append('<section class="cbs-sec"><h3>השלכות מאקרו</h3>'
                   + "".join(f'<div class="cbs-item"><h4>{escape(str(m.get("title") or ""))}'
                             f'{_dir(m.get("direction"))}</h4>{_para(m.get("body"))}</div>'
                             for m in macro)
                   + '</section>')
    micro = [m for m in (a.get("micro") or []) if isinstance(m, dict)]
    if micro:
        items = []
        for m in micro:
            cos = [escape(str(c)) for c in (m.get("companies") or [])]
            meta = " · ".join(x for x in (
                escape(str(m.get("sector") or "")),
                ("קשר " + escape(str(m.get("link")))) if m.get("link") else "",
                ", ".join(cos)) if x)
            items.append(f'<div class="cbs-item"><h4>{escape(str(m.get("title") or ""))}'
                         f'{_dir(m.get("direction"))}</h4>'
                         + (f'<p class="cbs-cos">{meta}</p>' if meta else "")
                         + f'{_para(m.get("body"))}</div>')
        out.append('<section class="cbs-sec"><h3>השלכות על חברות בבורסה</h3>'
                   + "".join(items) + '</section>')
    if a.get("caveats"):
        out.append(f'<section class="cbs-sec"><h3>מה עלול להטעות</h3>{_para(a["caveats"])}</section>')
    watch = [w for w in (a.get("watch_next") or []) if isinstance(w, dict) and w.get("what")]
    if watch:
        out.append('<p class="cbs-watch"><b>מה לעקוב:</b> '
                   + " · ".join(escape(str(w["what"])) + (f' ({escape(str(w["when"]))})' if w.get("when") else "")
                                for w in watch) + '</p>')
    terms = [t for t in (a.get("terms") or []) if isinstance(t, dict) and t.get("term")]
    if terms:
        out.append('<details class="cbs-sec cbs-terms"><summary>מונחים</summary><dl>'
                   + "".join(f'<dt>{escape(str(t["term"]))}</dt><dd>{escape(str(t.get("explain") or ""))}</dd>'
                             for t in terms)
                   + '</dl></details>')
    return "".join(out)


def _excerpt(r: dict, lines: int = 8) -> str:
    """תקציר הלמ"ס כרשימה צפופה, חתוך בגבול שורה.

    כל שורה בתקציר היא נתון נפרד ("עלייה של 3.5% בתמ"ג..."). כפסקאות הן
    תפסו מסך שלם בכל הודעה ממתינה, וחיתוך לפי תווים קטע נתון באמצע.
    """
    rows = [x.strip() for x in (r.get("summary") or "").splitlines()]
    rows = [x for x in rows if x and x != "להודעה המלאה"]
    if not rows:
        return ""
    items = "".join(f"<li>{escape(x)}</li>" for x in rows[:lines])
    return f'<ul class="cbs-sum">{items}{"<li>…</li>" if len(rows) > lines else ""}</ul>'


def release_html(r: dict, a: dict | None, open_: bool) -> str:
    pdf = next((u for u in (r.get("attachments") or []) if u.lower().split("?")[0].endswith(".pdf")), None)
    head = (f'<div class="cbs-rel-head"><span class="cbs-date" dir="ltr">{_dm(r.get("date"))}</span>'
            f'<span class="cbs-topic">{escape(r.get("topic_label") or r.get("topic") or "")}</span>'
            f'<a class="cbs-title" href="{escape(r.get("url") or "#")}" rel="noopener" target="_blank">'
            f'{escape(r.get("title") or "")}</a>'
            + (f'<a class="cbs-pdf" href="{escape(pdf)}" rel="noopener" target="_blank">ההודעה המלאה (PDF)</a>'
               if pdf else "")
            + '</div>')
    if a and not a.get("skip"):
        body = _analysis_html(a)
        lead = f'<p class="cbs-headline">{escape(str(a.get("headline") or ""))}</p>'
        inner = (lead + body) if open_ else (
            f'<details class="cbs-more"><summary>{escape(str(a.get("headline") or "הניתוח המלא"))}</summary>'
            f'{body}</details>')
    elif a and a.get("skip"):
        inner = ('<p class="cbs-note">לא נמצאו בהודעה נתונים בעלי השלכה שוקית'
                 + (f' — {escape(str(a.get("reason")))}' if a.get("reason") else "") + '.</p>'
                 + _excerpt(r))
    elif r.get("relevant"):
        inner = '<p class="cbs-note">הניתוח ייכתב בריצה הקרובה. בינתיים — תקציר הלמ"ס:</p>' + _excerpt(r)
    else:
        inner = '<p class="cbs-note">הודעה שאינה נוגעת לשוק, ומוצגת בלי ניתוח.</p>' + _excerpt(r, 4)
    return (f'<article class="cbs-rel" data-topic="{escape(r.get("topic") or "other")}" '
            f'id="rel-{r.get("id")}">{head}{inner}</article>')


SCRIPT = """<script>
(function () {
  "use strict";
  var nav = document.getElementById("cbs-chips");
  if (!nav) { return; }
  var arts = Array.prototype.slice.call(document.querySelectorAll("article.cbs-rel"));
  nav.hidden = false;
  nav.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("button[data-t]") : null;
    if (!b) { return; }
    var t = b.getAttribute("data-t");
    Array.prototype.forEach.call(nav.querySelectorAll("button"), function (x) {
      x.setAttribute("aria-pressed", x === b ? "true" : "false");
    });
    arts.forEach(function (a) { a.hidden = !!t && a.getAttribute("data-topic") !== t; });
  });
})();
</script>"""


def page(data: dict) -> str:
    snap = data.get("snap") or {}
    rels = data.get("releases") or []
    analyses = data.get("analyses") or {}
    if not snap and not rels:
        return ('<h1>נתוני הלמ"ס</h1><p class="lead">טרם נאספו נתונים מהלשכה המרכזית '
                'לסטטיסטיקה. הם ייאספו בריצה הקרובה של צנרת הלמ"ס.</p>')

    since = (date.today() - timedelta(days=DAYS)).isoformat()
    recent = [r for r in rels if (r.get("date") or "") >= since]
    n_an = sum(1 for r in recent if analyses.get(str(r["id"])) and not analyses[str(r["id"])].get("skip"))
    fetched = snap.get("fetched_at") or ""
    stamp = (f'עודכן {fetched[8:10]}/{fetched[5:7]} {fetched[11:16]}' if len(fetched) >= 16 else "")

    errors = snap.get("errors") or {}
    err_html = ""
    if errors:
        err_html = ('<p class="msg warn">בריצה האחרונה לא נמשכו: '
                    + escape(", ".join(errors)) + '. מוצגים הנתונים מהמשיכה המוצלחת האחרונה.</p>')

    topics = []
    for r in recent:
        key, label = r.get("topic") or "other", r.get("topic_label") or r.get("topic") or "נוסף"
        if key not in [k for k, _ in topics]:
            topics.append((key, label))
    chips = ('<div class="cbs-chips" id="cbs-chips" role="group" hidden aria-label="סינון לפי נושא">'
             '<button type="button" data-t="" aria-pressed="true">הכל</button>'
             + "".join(f'<button type="button" data-t="{escape(k)}" aria-pressed="false">{escape(l)}</button>'
                       for k, l in topics)
             + '</div>') if len(topics) > 1 else ""

    feed = "".join(release_html(r, analyses.get(str(r["id"])), i < OPEN_LATEST)
                   for i, r in enumerate(recent))

    return "\n".join(x for x in [
        '<div class="dash-head"><h1>נתוני הלמ"ס</h1>'
        f'<span class="stamp">{stamp}</span></div>',
        '<p class="lead">הודעות הלשכה המרכזית לסטטיסטיקה, עם ניתוח ההשלכות על המאקרו '
        'ועל חברות בבורסה בתל אביב. הנתונים נמשכים מממשקי הלמ"ס שלוש פעמים ביום.</p>',
        err_html,
        indicators_html(snap),
        series_html(snap),
        calendar_html(snap),
        f'<h2>הודעות אחרונות</h2><p class="note">{len(recent)} הודעות ב-{DAYS} הימים '
        f'האחרונים, מהן {n_an} מנותחות. הניתוחים נכתבים על בסיס ההודעה ונתוני הלמ"ס '
        'בלבד, וכל מספר בהם לקוח משם. <b>ניתוח השפעה, לא המלצת השקעה.</b></p>',
        chips,
        feed or '<p class="note">אין הודעות בתקופה.</p>',
        SCRIPT,
    ] if x)


def report(data: dict) -> list[str]:
    """שורות אנוטציה לבנייה: מה נבנה, ומה חסר."""
    snap = data.get("snap") or {}
    rels = data.get("releases") or []
    analyses = data.get("analyses") or {}
    if not snap and not rels:
        return ['::warning title=אין נתוני למ"ס::output/cbs ריק — עמוד הלמ"ס נבנה בלי נתונים.']
    since = (date.today() - timedelta(days=DAYS)).isoformat()
    recent = [r for r in rels if (r.get("date") or "") >= since]
    rel_ok = [r for r in recent if r.get("relevant")]
    done = [r for r in rel_ok if str(r["id"]) in analyses]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    stuck = [r for r in rel_ok if str(r["id"]) not in analyses and (r.get("date") or "") <= yesterday]
    out = [f'::notice::נתוני הלמ"ס: {len(recent)} הודעות ב-{DAYS} יום, {len(done)}/{len(rel_ok)} '
           f'רלוונטיות נותחו · לוח {len(snap.get("calendar") or [])} · מדדים '
           f'{len(snap.get("indicators") or [])} · משיכה {snap.get("fetched_at") or "—"}']
    fetched = snap.get("fetched_at")
    if fetched:
        try:
            age = datetime.now().astimezone() - datetime.fromisoformat(fetched)
            if age > timedelta(hours=30):
                out.append(f'::warning title=נתוני הלמ"ס ישנים::המשיכה האחרונה מ-{fetched} — '
                           'צנרת cbs-watch לא רצה או נכשלה.')
        except ValueError:
            pass
    if stuck:
        out.append('::warning title=הודעות למ"ס בלי ניתוח::' + " · ".join(
            f'{r.get("date")} {str(r.get("title"))[:50]}' for r in stuck[:6])
            + ' — ממתינות יותר מיום; בדוק את שלב הניתוח ב-cbs-watch.')
    return out
