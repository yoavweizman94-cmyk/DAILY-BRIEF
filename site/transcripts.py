"""עמוד תמלולי שיחות המשקיעים.

הנתונים נאספים ב-`ingest/globes_calls.py`: התמליל נמשך מגלובס בסשן
מנוי, מסוכם, ונזרק. כאן רק רינדור של הסיכומים.

**מה הקורא רואה בלי לפתוח.** שורת ה"בשורה אחת" של כל שיחה מוצגת
בכותרת המקופלת. עמוד שדורש פתיחה של עשרים כרטיסים כדי לדעת מה יש בהם
אינו נסרק, ושיחה שנפתחת רק אחרי קליק היא שיחה שלא נקראה.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "calls"


def load() -> list[dict]:
    """כל הסיכומים שנאספו, מהחדש לישן."""
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
    """שורת "בשורה אחת" מתוך הסיכום, לתצוגה במצב מקופל."""
    m = re.search(r"##\s*בשורה אחת\s*\n+(.+?)(?:\n\s*\n|\n##|$)", md or "", re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[*_`#]", "", m.group(1))).strip()


def he_date(iso: str) -> str:
    p = (iso or "").split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else (iso or "")


def page(rows: list[dict], render) -> str:
    """`render` הוא ממיר ה-markdown של build.py — כדי שהטבלאות יקבלו
    את אותה עטיפת גלילה כמו בשאר האתר."""
    head = ('<div class="dash-head"><h1>תמלולי שיחות משקיעים</h1></div>')

    if not rows:
        return (head + '<p class="stamp">אין עדיין סיכומי שיחות. '
                'ההרצה היא לפי דרישה — <code>ingest/globes_calls.py</code>.</p>'
                + note())

    firms = sorted({r.get("company") or "" for r in rows} - {""})
    periods = sorted({r.get("period") or "" for r in rows} - {""}, reverse=True)
    last = max((r.get("date") or "") for r in rows)

    stamp = (f'<p class="stamp">{len(rows)} שיחות · {len(firms)} חברות כיסוי · '
             f'עדכון אחרון {he_date(last)}</p>')

    opts = "".join(f'<option value="{esc(p)}">{esc(p)}</option>' for p in periods)
    controls = (
        '<div class="tr-filters">'
        '<input id="q" type="search" placeholder="חברה או מילה בסיכום…" '
        'autocomplete="off" aria-label="סינון שיחות">'
        f'<select id="per" aria-label="תקופה"><option value="">כל התקופות</option>{opts}</select>'
        '<span class="stamp" id="cnt"></span></div>')

    cards = []
    for r in rows:
        md = r.get("summary") or ""
        one = headline(md)
        tag = ('<b class="tr-approx" title="השם בגלובס אינו זהה לשם בכיסוי — '
               f'הותאם לפי תחילית">{esc(r.get("globes_name"))}</b>'
               if r.get("match") == "prefix" else "")
        cards.append(
            '<details class="tr" data-firm="{firm}" data-per="{per}">'
            '<summary><span class="tr-day">{day}</span>'
            '<span class="tr-firm">{firm}</span>{tag}'
            '<span class="tr-per">{per}</span>'
            '<span class="tr-one">{one}</span></summary>'
            '<div class="tr-body">{body}'
            '<p class="tr-src">המקור: <a href="{url}" target="_blank" rel="noopener">'
            'תמליל מלא בגלובס</a> · התמליל המקורי אינו נשמר אצלנו; '
            'הסיכום נכתב מתוכו ({chars} תווים).</p></div></details>'.format(
                firm=esc(r.get("company")), per=esc(r.get("period")),
                day=he_date(r.get("date")), tag=tag, one=esc(one),
                body=render(md), url=esc(r.get("url")),
                chars=f'{r.get("chars", 0):,}'))

    js = """
<script>
(function () {
  var q = document.getElementById('q'), per = document.getElementById('per'),
      cnt = document.getElementById('cnt'),
      all = Array.prototype.slice.call(document.querySelectorAll('details.tr'));
  function apply() {
    var t = (q.value || '').trim().toLowerCase(), p = per.value, n = 0;
    all.forEach(function (d) {
      var okP = !p || d.dataset.per === p;
      var okT = !t || d.textContent.toLowerCase().indexOf(t) !== -1;
      var show = okP && okT;
      d.hidden = !show;
      if (show) n++;
    });
    cnt.textContent = n === all.length ? '' : n + ' מתוך ' + all.length;
  }
  q.addEventListener('input', apply);
  per.addEventListener('change', apply);
})();
</script>"""

    return head + stamp + controls + "".join(cards) + note() + js


def note() -> str:
    return (
        '<p class="tr-note">התמלילים הם של <a href="https://www.globes.co.il" '
        'target="_blank" rel="noopener">גלובס</a> ונקראים במנוי. באתר מוצג '
        'סיכום שנכתב אצלנו ולא התמליל עצמו; ציטוט מוגבל ל-15 מילים עם ייחוס. '
        'הסיכום מכסה שיחות של חברות הכיסוי בלבד.</p>')
