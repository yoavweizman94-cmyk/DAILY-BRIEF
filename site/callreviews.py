"""עמוד "דוח ושיחה": הסקירה המשולבת של דוח כספי ושל שיחת הוועידה שאחריו.

הנתונים נכתבים ב-`ingest/call_reviews.py`; כאן רק רינדור.

**הפוסט ל-X הוא טיוטה של הבעלים.** הוא נכתב לחשבון שלו ואינו חלק מהסקירה,
ולכן מוצג רק לו (data-owner, כמו הקישור ל"השיחות שלי"). זו הסתרה בתצוגה
ולא שער: הטקסט ממילא נועד להתפרסם. מ-11/11/2026 זה פוסט אחד ולא שרשור, והוא
נכתב בנפרד מהסקירה (scripts/x_threads.py → output/x/callreviews.json).
"""
import json
import re
from pathlib import Path

import share
from transcripts import anchor_heads, esc, he_date, summary_toc

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "calls" / "combined"
POSTS = ROOT / "output" / "x" / "callreviews.json"
MAYA = "https://maya.tase.co.il/he/reports/"
FILES = "https://mayafiles.tase.co.il/"
_POSTS: dict | None = None


def load() -> list[dict]:
    """הסקירות שנכתבו, מהשיחה החדשה לישנה. רשומות כישלון אינן מוצגות."""
    rows = []
    for f in sorted(SRC.glob("*.json")) if SRC.is_dir() else []:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r.get("status") == "ok" and r.get("review_md"):
            rows.append(r)
    rows.sort(key=lambda r: (r.get("call_date") or "", r.get("did") or ""), reverse=True)
    return rows


def slug(rec: dict) -> str:
    return f"{rec.get('did')}.html"


def post(rec: dict) -> str:
    """הפוסט ל-X של הסקירה. סקירה מלפני 11/11 שעוד אין לה פוסט מציגה את השרשור
    שנכתב איתה, מחובר לפוסט אחד ובלי המספור ("2/3") שנוסף לו אז."""
    global _POSTS
    if _POSTS is None:
        _POSTS = share.load_posts(POSTS)
    text = _POSTS.get(str(rec.get("did") or ""))
    if not text and rec.get("tweets"):
        text = "\n\n".join(re.sub(r"\s*\d+/\d+\s*$", "", str(t)).strip()
                           for t in rec["tweets"] if str(t).strip())
    return text or ""


def _thread(rec: dict) -> str:
    """פוסט ל-X לבעלים (share.post_block), אחרי הסקירה. ההעתקה — במאזין המשותף שבתחתית
    כל עמוד (build.py)."""
    return share.post_block(f"xc-{rec.get('did')}", post(rec),
                            ["הדוח במאיה", "שיחת המשקיעים, גלובס"])


def detail(rec: dict, rows: list[dict], render) -> str:
    rep = rec.get("report") or {}
    body = anchor_heads(render(rec.get("review_md") or ""))

    # רבעונים קודמים של אותה חברה — המעקב הוא עיקר הערך של ארכיון
    same = [r for r in rows if r.get("company") == rec.get("company") and r.get("did") != rec.get("did")]
    other = ""
    if same:
        other = ('<p class="tr-other">רבעונים נוספים: ' + " · ".join(
            f'<a href="{slug(r)}">{esc(r.get("period"))} ({he_date(r.get("call_date"))})</a>'
            for r in same[:8]) + "</p>")

    links = [f'<a href="{MAYA}{esc(rep.get("id"))}" target="_blank" rel="noopener">הדוח במאיה</a>']
    if rep.get("p"):
        links.append(f'<a href="{FILES}{esc(rep.get("p"))}" target="_blank" rel="noopener">ה-PDF</a>')
    links.append(f'<a href="../transcripts/{esc(rec.get("did"))}.html">סיכום השיחה המלא</a>')

    report = ""
    if rec.get("report_review"):
        report = ('<details class="tr-raw"><summary>סקירת הדוח המלאה</summary>'
                  f'<div class="tr-body tr-full">{render(rec["report_review"])}</div></details>')

    return (
        '<p class="tr-back"><a href="../results.html">← כל הסקירות</a></p>'
        f'<div class="dash-head"><h1>{esc(rec.get("company"))} · {esc(rec.get("period"))}</h1></div>'
        f'<p class="stamp">הדוח {he_date(rep.get("d"))} · השיחה {he_date(rec.get("call_date"))} · '
        + " · ".join(links) + "</p>"
        + other
        + (f'<p class="cr-lede">{esc(rec.get("headline"))}</p>' if rec.get("headline") else "")
        + summary_toc(body)
        + f'<div class="tr-body tr-full cr-body">{body}</div>'
        + _thread(rec)
        + report
        + note())


def index(rows: list[dict]) -> str:
    head = '<div class="dash-head"><h1>דוח ושיחה</h1></div>'
    lede = ('<p class="cr-intro">סקירה אחת לדוח הכספי ולשיחת הוועידה שבה ההנהלה הציגה '
            'אותו: מה המספרים אומרים, מה השיחה הוסיפה עליהם, ואיפה השניים לא נפגשים.</p>')
    if not rows:
        return (head + lede + '<p class="stamp">אין עדיין סקירות. הן נכתבות בערב, אחרי '
                'מהדורת הנעילה, לכל שיחת ועידה שיש לה דוח כספי.</p>' + note())

    firms = sorted({r.get("company") or "" for r in rows} - {""})
    periods = sorted({r.get("period") or "" for r in rows} - {""}, reverse=True)
    tiles = (
        '<div class="strip">'
        f'<div class="tile"><div class="lbl">סקירות</div><div class="val">{len(rows)}</div></div>'
        f'<div class="tile"><div class="lbl">חברות</div><div class="val">{len(firms)}</div></div>'
        f'<div class="tile"><div class="lbl">שיחה אחרונה</div>'
        f'<div class="val">{he_date(rows[0].get("call_date"))}</div></div>'
        '</div>')
    firm_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in firms)
    per_opts = "".join(f'<option value="{esc(p)}">{esc(p)}</option>' for p in periods)
    controls = (
        '<div class="tr-filters">'
        '<input id="q" type="search" placeholder="חברה או מילה בשורת הפתיחה…" '
        'autocomplete="off" aria-label="סינון סקירות">'
        f'<select id="firm" aria-label="חברה"><option value="">כל החברות</option>{firm_opts}</select>'
        f'<select id="per" aria-label="תקופה"><option value="">כל התקופות</option>{per_opts}</select>'
        '<span class="stamp" id="cnt"></span></div>')

    cards = []
    for r in rows:
        rep = r.get("report") or {}
        cards.append(
            f'<a class="tr-card" href="results/{slug(r)}" data-firm="{esc(r.get("company"))}" '
            f'data-per="{esc(r.get("period"))}">'
            f'<span class="tr-day">{he_date(r.get("call_date"))}</span>'
            f'<span class="tr-firm">{esc(r.get("company"))}</span>'
            f'<span class="tr-per">{esc(r.get("period"))}</span>'
            f'<span class="cr-src" title="תאריך הדוח">דוח {he_date(rep.get("d"))}</span>'
            f'<span class="tr-one">{esc(r.get("headline"))}</span></a>')

    js = """
<script>
(function () {
  var q = document.getElementById('q'), per = document.getElementById('per'),
      firm = document.getElementById('firm'), cnt = document.getElementById('cnt'),
      all = Array.prototype.slice.call(document.querySelectorAll('.tr-card'));
  function apply() {
    var t = (q.value || '').trim().toLowerCase(), p = per.value, f = firm.value, n = 0;
    all.forEach(function (d) {
      var show = (!p || d.dataset.per === p) && (!f || d.dataset.firm === f) &&
                 (!t || d.textContent.toLowerCase().indexOf(t) !== -1);
      d.hidden = !show;
      if (show) n++;
    });
    cnt.textContent = n === all.length ? '' : n + ' מתוך ' + all.length;
  }
  q.addEventListener('input', apply);
  per.addEventListener('change', apply);
  firm.addEventListener('change', apply);
})();
</script>"""
    return head + lede + tiles + controls + "".join(cards) + note() + js


def note() -> str:
    return ('<p class="tr-note">הסקירה נכתבת אצלנו מתוך סקירת הדוח הכספי (מהדוח המלא '
            'במאיה) ומתוך סיכום שיחת הוועידה (מהתמליל של גלובס). כל מספר מהם בלבד. '
            'אין באמור ייעוץ השקעות או המלצה לפעולה בניירות ערך.</p>')


def pages(rows: list[dict], render) -> list[tuple[str, str, str]]:
    """(שם קובץ, כותרת, גוף) לכל סקירה — build.py עוטף ב-PAGE."""
    return [(slug(r), f'{r.get("company")} · {r.get("period")} · דוח ושיחה',
             detail(r, rows, render)) for r in rows]


def by_did(rows: list[dict]) -> set[str]:
    """מזהי השיחות שיש להן סקירה משולבת — לקישור מעמוד התמליל."""
    return {str(r.get("did")) for r in rows}
