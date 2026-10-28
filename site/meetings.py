"""עמוד "השיחות שלי": הקלטות של פגישות ושיחות עם הנהלות, מתומללות ומסוכמות.

הנתונים: output/meetings/<id>.json — התמליל מ-ingest/meetings_pull.py (רץ במחשב
של יואב), והסקירה מ-ingest/meetings_summarize.py. כאן רק רינדור.

**לבעלים בלבד.** השער ב-site/functions/_middleware.js מחזיר 404 לכל משתמש אחר,
והקישור בניווט מוצג רק כש-/api/me מחזיר owner. העמודים אינם נכנסים לשכבת
ה-MCP ולא לשום אינדקס אחר באתר — מי שאינו הבעלים לא אמור לדעת שהם קיימים.
"""
import json
from pathlib import Path

from transcripts import anchor_heads, esc, he_date, summary_toc

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "meetings"


def load() -> list[dict]:
    """כל ההקלטות, מהחדשה לישנה; הקלטה בלי תאריך בסוף."""
    rows = []
    for f in sorted(SRC.glob("*.json")) if SRC.is_dir() else []:
        try:
            rows.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    rows.sort(key=lambda r: (r.get("date") or "", r.get("transcribed_at") or ""), reverse=True)
    return rows


def firm(r: dict) -> str:
    """שם החברה: מרשימת הכיסוי לפי שם הקובץ, ואם לא — מה שהסקירה זיהתה בתמליל."""
    return r.get("company") or r.get("ai_company") or ""


def title(r: dict) -> str:
    folder = (r.get("folder") or "").rsplit("/", 1)[-1]
    return firm(r) or folder or Path(r.get("file") or "").stem or "שיחה"


def when(r: dict) -> str:
    d = r.get("date") or ""
    if len(d) == 7:                       # חודש בלבד ("רימוני אפריל 24")
        return f"{d[5:7]}/{d[:4]}"
    return he_date(d) if d else "בלי תאריך"


def minutes(r: dict) -> str:
    m = round((r.get("duration_sec") or 0) / 60)
    return f"{m // 60}:{m % 60:02d} שע׳" if m >= 60 else f"{m} דק׳"


def clock(sec) -> str:
    s = int(sec or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


PLACEHOLDER = {"", "—", "-", "לא נאמר", "לא ידוע", "לא ידוע.", "לא נאמר."}


def speaker(r: dict, sp: str) -> str:
    """"דובר 2", ואם הסקירה זיהתה אותו מהתוכן — השם והתפקיד שנאמרו בשיחה.

    **רק תווית קצרה ונקייה.** בהקלטה הראשונה (פולירם, 28/10/2026) המכונה איחדה
    שני אנשי הנהלה לדובר אחד, והמודל כתב בשדה השם "יובל (ברוב הקטעים); בקטע
    18:25 ככל הנראה נתנאל". הסתייגות כזו שייכת לטבלת "מי דיבר" שבסקירה; ליד כל
    קטע בתמליל היא רעש — ואז נשאר "דובר N". המפתח הוא "2", או "דובר 2" כפי
    שהחזירה הסקירה הראשונה."""
    m = r.get("speakers_map") or {}
    who = m.get(str(sp)) or m.get(f"דובר {sp}") or {}
    parts = [v for v in ((who.get("name") or "").strip(), (who.get("role") or "").strip())
             if v not in PLACEHOLDER and len(v) <= 24 and ";" not in v]
    label = " · ".join(parts)
    if len(label) > 34:
        label = parts[0]
    return label or (f"דובר {sp}" if sp else "דובר")


def slug(r: dict) -> str:
    return f"{r.get('id')}.html"


def transcript_html(r: dict) -> str:
    out = []
    for s in r.get("segments") or []:
        out.append(f'<p class="sp"><b>{esc(speaker(r, s.get("sp")))}</b> '
                   f'<span class="mt-t">{clock(s.get("t"))}</span> {esc(s.get("text"))}</p>')
    return "".join(out) or "<p>התמליל ריק.</p>"


def detail(r: dict, rows: list[dict], render) -> str:
    same = [x for x in rows if firm(x) and firm(x) == firm(r) and x.get("id") != r.get("id")]
    other = ""
    if same:
        links = " · ".join(f'<a href="{slug(x)}">{when(x)}</a>' for x in same[:10])
        other = f'<p class="tr-other">שיחות נוספות עם {esc(firm(r))}: {links}</p>'

    flags = []
    if r.get("company") is None and r.get("ai_company"):
        flags.append('<span class="tr-approx" title="שם הקובץ לא נקב בחברה">החברה זוהתה מהתמליל</span>')
    if r.get("is_meeting") is False:
        flags.append('<span class="tr-approx">לא שיחה עם חברה</span>')
    if r.get("date_from") == "mtime":
        flags.append('<span class="tr-approx" title="לא בשם הקובץ ולא בנתוני ההקלטה">'
                     'תאריך לפי הקובץ</span>')

    if r.get("summary"):
        body = anchor_heads(render(r["summary"]))
        summary = summary_toc(body) + f'<div class="tr-body tr-full">{body}</div>'
    elif r.get("summary_skip"):
        summary = f'<p class="stamp">אין סקירה: {esc(r["summary_skip"])}.</p>'
    else:
        summary = ('<p class="stamp">הסקירה תיכתב בערב, אחרי מהדורת הנעילה. '
                   'בינתיים — התמליל המלא למטה.</p>')

    return (
        '<p class="tr-back"><a href="../meetings.html">← כל השיחות</a></p>'
        f'<div class="dash-head"><h1>{esc(title(r))} · {when(r)}</h1></div>'
        f'<p class="stamp">{minutes(r)} · {r.get("speakers") or 0} דוברים · '
        # בלי הסיומת ובבידוד: "פרטנר 5.12.24.m4a" בתוך שורה עברית מתהפך ל-"m4a.5.12.24"
        f'הקובץ: <bdi>{esc(Path(r.get("file") or "").stem)}</bdi>'
        f'{" " + " ".join(flags) if flags else ""}</p>'
        + other + summary
        + f'<details class="tr-raw"{"" if r.get("summary") else " open"}>'
        '<summary>התמליל המלא</summary>'
        '<p class="tr-note">תמלול אוטומטי (Soniox). שמות, מספרים והחלוקה לדוברים עלולים '
        'להשתבש — מספר שנשמע לא סביר כדאי לבדוק בהקלטה.</p>'
        f'<div class="tr-text">{transcript_html(r)}</div></details>')


def index(rows: list[dict]) -> str:
    head = ('<div class="dash-head"><h1>השיחות שלי</h1></div>'
            '<p class="stamp">הקלטות של פגישות ושיחות עם חברות, מתומללות ומסוכמות. '
            'העמוד גלוי רק לך.</p>')
    if not rows:
        return (head + '<p class="stamp">אין עדיין הקלטות. הקלטה שתיכנס לתיקייה במחשב תתומלל '
                'בבדיקה הבאה (12:00 או 17:30), והסקירה תיכתב בערב.</p>')

    firms = sorted({firm(r) for r in rows} - {""})
    hours = sum(r.get("duration_sec") or 0 for r in rows) / 3600
    waiting = sum(1 for r in rows if not r.get("summary") and not r.get("summary_skip"))
    tiles = (
        '<div class="strip">'
        f'<div class="tile"><div class="lbl">שיחות</div><div class="val">{len(rows)}</div></div>'
        f'<div class="tile"><div class="lbl">חברות</div><div class="val">{len(firms)}</div></div>'
        f'<div class="tile"><div class="lbl">הקלטה</div><div class="val">{hours:,.0f}</div>'
        '<div class="chg">שעות</div></div>'
        f'<div class="tile"><div class="lbl">ממתינות לסקירה</div><div class="val">{waiting}</div></div>'
        '</div>')

    firm_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in firms)
    controls = (
        '<div class="tr-filters">'
        '<input id="q" type="search" placeholder="חברה או מילה בשורת הפתיחה…" '
        'autocomplete="off" aria-label="סינון שיחות">'
        f'<select id="firm" aria-label="חברה"><option value="">כל החברות</option>{firm_opts}</select>'
        '<span class="stamp" id="cnt"></span></div>')

    cards = []
    for r in rows:
        tag = ""
        if r.get("is_meeting") is False:
            tag = '<span class="tr-approx">לא שיחה עם חברה</span>'
        elif not r.get("summary") and not r.get("summary_skip"):
            tag = '<span class="tr-approx">ממתינה לסקירה</span>'
        one = r.get("headline") or ""
        cards.append(
            f'<a class="tr-card" href="meetings/{slug(r)}" data-firm="{esc(firm(r))}">'
            f'<span class="tr-day">{when(r)}</span>'
            f'<span class="tr-firm">{esc(title(r))}</span>{tag}'
            f'<span class="tr-per">{minutes(r)}</span>'
            f'<span class="tr-one">{esc(one)}</span></a>')

    js = """
<script>
(function () {
  var q = document.getElementById('q'), firm = document.getElementById('firm'),
      cnt = document.getElementById('cnt'),
      all = Array.prototype.slice.call(document.querySelectorAll('.tr-card'));
  function apply() {
    var t = (q.value || '').trim().toLowerCase(), f = firm.value, n = 0;
    all.forEach(function (d) {
      var show = (!f || d.dataset.firm === f) &&
                 (!t || d.textContent.toLowerCase().indexOf(t) !== -1);
      d.hidden = !show;
      if (show) n++;
    });
    cnt.textContent = n === all.length ? '' : n + ' מתוך ' + all.length;
  }
  q.addEventListener('input', apply);
  firm.addEventListener('change', apply);
})();
</script>"""
    return head + tiles + controls + "".join(cards) + js


def pages(rows: list[dict], render) -> list[tuple[str, str, str]]:
    """(שם קובץ, כותרת, גוף) לכל הקלטה — build.py עוטף ב-PAGE."""
    return [(slug(r), f"{title(r)} · {when(r)} · השיחות שלי", detail(r, rows, render))
            for r in rows]
