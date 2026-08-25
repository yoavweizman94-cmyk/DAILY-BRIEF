"""עמודי תמלולי שיחות המשקיעים.

הנתונים נאספים ב-`ingest/globes_calls.py`: התמליל נמשך מגלובס בסשן
מנוי, מסוכם, ונשמר לצד הסיכום. כאן רק רינדור.

**למה עמוד לכל שיחה ולא עמוד אחד.** תמליל טיפוסי הוא עשרות אלפי
תווים. שמונה מהם בעמוד אחד הם כמעט חצי מגה של HTML, וששים יהיו
שלושה — עמוד שנטען לאט ושהדפדפן מתקשה לחפש בתוכו. לכן: אינדקס קליל
עם שורת ה"בשורה אחת" של כל שיחה, ועמוד מלא לכל שיחה בנפרד.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "calls"


def load() -> list[dict]:
    """כל השיחות שנאספו, מהחדשה לישנה."""
    if not SRC.is_dir():
        return []
    rows = []
    for f in sorted(SRC.glob("transcripts_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    # מזהה שסוכם פעמיים (ריצה חוזרת) — הרשומה המאוחרת גוברת.
    by_did = {}
    for r in rows:
        by_did[r.get("did")] = r
    out = list(by_did.values())
    out.sort(key=lambda r: (r.get("date") or "", r.get("did") or ""), reverse=True)
    return out


def esc(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def headline(md: str) -> str:
    """שורת "בשורה אחת" מתוך הסיכום, לתצוגה באינדקס."""
    m = re.search(r"##\s*בשורה אחת\s*\n+(.+?)(?:\n\s*\n|\n##|$)", md or "", re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[*_`#]", "", m.group(1))).strip()


def he_date(iso: str) -> str:
    p = (iso or "").split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else (iso or "")


def slug(rec: dict) -> str:
    return f"{rec.get('did')}.html"


# ── התמליל ────────────────────────────────────────────────────────────
# שורת דובר: שם קצר ואחריו נקודתיים, בלי סימני סוף-משפט לפניהם. הסייג
# על האורך ועל הפיסוק הוא מה שמונע מכל משפט שיש בו נקודתיים באמצע
# להיראות כמו דובר חדש.
SPEAKER = re.compile(r"^([^:.!?]{2,45}):\s*(.*)$", re.S)


def transcript_html(text: str) -> str:
    """התמליל, מפוסק לפי דוברים כשאפשר לזהותם.

    **הזיהוי אינו מובטח.** גלובס אינה מסמנת דוברים בתגית, ולכן זו
    היוריסטיקה על טקסט. פסקה שלא זוהתה מוצגת כפסקה רגילה ולא נעלמת —
    הכלל הוא שהתמליל מוצג במלואו גם כשהפיסוק נכשל.
    """
    out = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        para = para.strip()
        if not para:
            continue
        m = SPEAKER.match(para)
        if m and m.group(2).strip():
            out.append(f'<p class="sp"><b>{esc(m.group(1).strip())}:</b> '
                       f'{esc(m.group(2).strip())}</p>')
        else:
            out.append(f"<p>{esc(para)}</p>")
    return "".join(out) or "<p>התמליל ריק.</p>"


def summary_toc(html: str) -> str:
    """ניווט לסעיפי הסיכום, שהוא ארוך ונקרא בסריקה."""
    heads = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)
    if len(heads) < 3:
        return ""
    items = []
    for h in heads:
        t = re.sub(r"<[^>]+>", "", h).strip()
        aid = "s-" + re.sub(r"[^\w֐-׿]+", "-", t).strip("-")
        items.append(f'<a href="#{aid}">{esc(t)}</a>')
    return f'<nav class="toc">{"".join(items)}</nav>'


def anchor_heads(html: str) -> str:
    def add(m):
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        aid = "s-" + re.sub(r"[^\w֐-׿]+", "-", t).strip("-")
        return f'<h2 id="{aid}">{m.group(1)}</h2>'
    return re.sub(r"<h2[^>]*>(.*?)</h2>", add, html, flags=re.S)


# ── עמוד השיחה ────────────────────────────────────────────────────────
def detail(rec: dict, rows: list[dict], render) -> str:
    md = rec.get("summary") or ""
    body = anchor_heads(render(md))

    # שיחות קודמות של אותה חברה — מעקב על פני רבעונים הוא עיקר הערך
    # של ארכיון, ובלי קישור הוא דורש חזרה לאינדקס וחיפוש ידני.
    same = [r for r in rows
            if r.get("company") == rec.get("company") and r.get("did") != rec.get("did")]
    other = ""
    if same:
        links = " · ".join(
            f'<a href="{slug(r)}">{esc(r.get("period"))} ({he_date(r.get("date"))})</a>'
            for r in same[:8])
        other = f'<p class="tr-other">שיחות נוספות של {esc(rec.get("company"))}: {links}</p>'

    approx = ""
    if rec.get("match") == "prefix":
        approx = (f' <span class="tr-approx" title="השם בגלובס אינו זהה לשם '
                  f'בכיסוי — הותאם לפי תחילית">בגלובס: '
                  f'{esc(rec.get("globes_name"))}</span>')
    elif rec.get("match") == "none":
        approx = ' <span class="tr-approx">מחוץ לכיסוי</span>'

    return (
        f'<p class="tr-back"><a href="../transcripts.html">← כל התמלולים</a></p>'
        f'<div class="dash-head"><h1>{esc(rec.get("company"))} · '
        f'{esc(rec.get("period"))}</h1></div>'
        f'<p class="stamp">{he_date(rec.get("date"))}{approx} · '
        f'תמליל בן {rec.get("chars", 0):,} תווים · '
        f'<a href="{esc(rec.get("url"))}" target="_blank" rel="noopener">המקור בגלובס</a>'
        f'</p>'
        + other
        + summary_toc(body)
        + f'<div class="tr-body tr-full">{body}</div>'
        + '<details class="tr-raw"><summary>התמליל המלא</summary>'
        + f'<div class="tr-text">{transcript_html(rec.get("text") or "")}</div>'
        + '</details>')


# ── האינדקס ───────────────────────────────────────────────────────────
def index(rows: list[dict]) -> str:
    head = '<div class="dash-head"><h1>תמלולי שיחות משקיעים</h1></div>'

    if not rows:
        return (head + '<p class="stamp">אין עדיין שיחות. ההרצה היא לפי דרישה — '
                'הפעל את <code>Globes Calls</code> ב-Actions.</p>' + note())

    firms = sorted({r.get("company") or "" for r in rows} - {""})
    periods = sorted({r.get("period") or "" for r in rows} - {""}, reverse=True)
    last = max((r.get("date") or "") for r in rows)
    chars = sum(r.get("chars", 0) for r in rows)

    tiles = (
        '<div class="strip">'
        f'<div class="tile"><div class="lbl">שיחות</div><div class="val">{len(rows)}</div></div>'
        f'<div class="tile"><div class="lbl">חברות</div><div class="val">{len(firms)}</div></div>'
        f'<div class="tile"><div class="lbl">תמליל שנקרא</div>'
        f'<div class="val">{chars // 1000:,}K</div><div class="chg">תווים</div></div>'
        f'<div class="tile"><div class="lbl">אחרונה</div>'
        f'<div class="val">{he_date(last)}</div></div>'
        '</div>')

    opts = "".join(f'<option value="{esc(p)}">{esc(p)}</option>' for p in periods)
    firm_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in firms)
    controls = (
        '<div class="tr-filters">'
        '<input id="q" type="search" placeholder="חברה או מילה בשורת הפתיחה…" '
        'autocomplete="off" aria-label="סינון שיחות">'
        f'<select id="firm" aria-label="חברה"><option value="">כל החברות</option>{firm_opts}</select>'
        f'<select id="per" aria-label="תקופה"><option value="">כל התקופות</option>{opts}</select>'
        '<span class="stamp" id="cnt"></span></div>')

    cards = []
    for r in rows:
        one = headline(r.get("summary") or "")
        tag = ""
        if r.get("match") == "prefix":
            tag = (f'<span class="tr-approx" title="הותאם לפי תחילית">'
                   f'{esc(r.get("globes_name"))}</span>')
        elif r.get("match") == "none":
            tag = '<span class="tr-approx">מחוץ לכיסוי</span>'
        cards.append(
            f'<a class="tr-card" href="transcripts/{slug(r)}" '
            f'data-firm="{esc(r.get("company"))}" data-per="{esc(r.get("period"))}">'
            f'<span class="tr-day">{he_date(r.get("date"))}</span>'
            f'<span class="tr-firm">{esc(r.get("company"))}</span>{tag}'
            f'<span class="tr-per">{esc(r.get("period"))}</span>'
            f'<span class="tr-one">{esc(one)}</span></a>')

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
  [q, per, firm].forEach(function (el) {
    el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', apply);
  });
})();
</script>"""

    return head + tiles + controls + "".join(cards) + note() + js


def note() -> str:
    return (
        '<p class="tr-note">התמלילים הם של <a href="https://www.globes.co.il" '
        'target="_blank" rel="noopener">גלובס</a> ונקראים במנוי. הסיכום נכתב '
        'אצלנו מתוך התמליל; התמליל המקורי מוצג בעמוד השיחה כארכיון אישי. '
        'הסיכום מכסה שיחות של חברות הכיסוי, אלא אם ההרצה הייתה עם <code>--all</code>.</p>')


def pages(rows: list[dict], render) -> list[tuple[str, str, str]]:
    """(שם קובץ, כותרת, גוף) לכל שיחה — build.py עוטף ב-PAGE."""
    return [(slug(r),
             f'{r.get("company")} · {r.get("period")} · שיחת משקיעים',
             detail(r, rows, render)) for r in rows]
