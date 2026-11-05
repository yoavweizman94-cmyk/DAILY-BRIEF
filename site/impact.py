# -*- coding: utf-8 -*-
"""עמוד "השפעה על מניות" (impact.html): לכל אירוע — מה זה עושה למניה, צעד אחר צעד.

הנתונים: scripts/analyze_impact.py, כל שעתיים, מתוך הכותרות שנבחרו, דיווחי מאיה
ופרסומי הרגולטורים. כרטיס לכל אירוע: מה קרה, בפשטות, ולכל חברה — כיוון, עוצמה,
שרשרת ההשפעה מהאירוע עד השורה בדוח, כמה זה גדול ביחס לחברה, ומה יכול לבטל את
ההשפעה. בסוף — השורה התחתונה ומה יאשר או יפריך.

**"נבדק — כנראה לא משנה" הוא חלק מהעמוד ולא פסולת שלו.** יואב ביקש הסבר גם למה
אירוע *אינו* משפיע (רעידת אדמה ואשלג — "להשפיע או לא להשפיע"). אירוע שכל החברות
בו בעוצמה נמוכה מרוכז בסוף היום, מקופל, כדי שהעמוד ייקרא קודם כרשימת מה שמשנה.

**הסינון בדפדפן הוא תוספת.** בלי JS כל הכרטיסים מוצגים, וסרגל הסינון מוסתר.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from autonews import IL, _local, _stamp, _txt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "impact"
PROFILES = ROOT / "data" / "company_profiles.json"
PAGE = "impact.html"
PAGE_DAYS = 7
KIND_HE = {"news": "תקשורת", "maya": "דיווח החברה", "gov": "רגולציה"}
DIR_CLASS = {"חיובי": "up", "שלילי": "down", "מעורב": "mixed"}
DIR_MARK = {"חיובי": "▲", "שלילי": "▼", "מעורב": "◆", "ניטרלי": "●"}
SIG = {"גבוהה": 3, "בינונית": 2, "נמוכה": 1}
SIG_LABEL = {3: "השפעה גבוהה", 2: "השפעה בינונית", 1: "השפעה נמוכה"}
WEEKDAY = ("שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון")


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def load() -> dict:
    try:
        state = json.loads((OUT / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    try:
        profiles = json.loads(PROFILES.read_text(encoding="utf-8")).get("companies") or {}
    except (OSError, ValueError):
        profiles = {}
    now = datetime.now(timezone.utc)
    by_id: dict[str, dict] = {}
    for i in range(PAGE_DAYS + 2):
        day = (now.astimezone(IL) - timedelta(days=i)).date().isoformat()
        for r in _jsonl(OUT / f"{day}.jsonl"):
            if r.get("id") and r.get("companies"):
                by_id[r["id"]] = r
    since = (now - timedelta(days=PAGE_DAYS)).isoformat(timespec="seconds")
    items = sorted((r for r in by_id.values() if (r.get("ts") or "") >= since),
                   key=lambda r: r.get("ts") or "", reverse=True)
    return {"state": state, "items": items, "profiles": profiles}


def anchor(src: str) -> str:
    return "im-" + re.sub(r"[^\w-]+", "-", str(src))[:120]


def links(data: dict) -> dict[str, str]:
    """מזהה המקור (כותרת, דיווח, פרסום) → העוגן שלו בעמוד — לקישורים מהעמודים האחרים."""
    return {r["src"]: anchor(r["src"]) for r in data.get("items") or [] if r.get("src")}


def _cap(m) -> str:
    if not m:
        return ""
    return f"{m / 1000:,.1f} מיליארד ₪" if m >= 1000 else f"{m:,.0f} מ׳ ₪"


def _when(ts: str | None, today) -> str:
    d = _local(ts)
    if not d:
        return ""
    return f"{d:%H:%M}" if d.date() == today else f"{d:%d/%m %H:%M}"


def _dir(d: str) -> str:
    return (f'<span class="cbs-dir {DIR_CLASS.get(d, "flat")}">'
            f'{DIR_MARK.get(d, "")} {escape(d)}</span>')


def _sig(n: int) -> str:
    return (f'<span class="im-sig s{n}"><span class="im-bars" aria-hidden="true"><i></i><i></i><i></i></span>'
            f'{SIG_LABEL[n]}</span>')


def _co(c: dict, profiles: dict) -> str:
    n = SIG.get(c.get("significance"), 1)
    p = profiles.get(c["name"]) or {}
    meta = [p.get("branch") or "",
            f"שווי שוק {_cap(p['market_cap_m'])} לפי מאיה" if p.get("market_cap_m") else "",
            f"דרך: {c['line']}" if c.get("line") else ""]
    chain = "".join(f"<li>{_txt(s)}</li>" for s in c.get("chain") or [])
    return (f'<section class="im-co"><div class="im-co-head"><h4>{escape(c["name"])}</h4>'
            f'{_dir(c.get("direction") or "ניטרלי")}{_sig(n)}</div>'
            + (f'<p class="im-co-meta">{" · ".join(escape(x) for x in meta if x)}</p>' if any(meta) else "")
            + f'<ol class="im-chain" aria-label="שרשרת ההשפעה">{chain}</ol>'
            + (f'<p class="im-size"><b>כמה זה גדול:</b> {_txt(c["size"])}</p>' if c.get("size") else "")
            + (f'<p class="im-against"><b>מה יכול לבטל את זה:</b> {_txt(c["against"])}</p>'
               if c.get("against") else "")
            + "</section>")


def _sources(r: dict) -> str:
    out, seen = [], {}
    for s in r.get("links") or []:
        url = str(s.get("url") or "")
        if not url.startswith("http"):
            continue
        name = s.get("name") or "מקור"
        k = seen[name] = seen.get(name, 0) + 1
        text = escape(name) if k == 1 else str(k)
        out.append(f'<a href="{escape(url)}" target="_blank" rel="noopener" '
                   f'title="{escape(s.get("title") or "")}">{text}</a>')
    if r.get("kind") == "gov" and r.get("page"):
        out.append(f'<a href="{escape(r["page"])}">הסיקור בעמוד הרגולציה</a>')
    return ("מקור: " if len(out) == 1 else "מקורות: ") + " · ".join(out) if out else ""


def _card(r: dict, profiles: dict, latest: str | None, today) -> str:
    sig = int(r.get("sig") or 1)
    kind = r.get("kind") or "news"
    cos = r.get("companies") or []
    tags = ' <span class="dg-tag dg-new">חדש</span>' if latest and r.get("run") == latest else ""
    basis = ' <span class="au-basis">לפי הכותרת</span>' if r.get("basis") == "כותרת" else ""
    names = "|".join(c["name"] for c in cos)
    src = _sources(r)
    return (f'<article class="im-card" id="{anchor(r.get("src") or r["id"])}" data-kind="{escape(kind)}" '
            f'data-sig="{sig}" data-cos="{escape(names)}">'
            f'<p class="im-meta"><span class="im-kind k-{escape(kind)}">{KIND_HE.get(kind, "")}</span>'
            f'<span class="dg-time">{_when(r.get("ts"), today)}</span>{tags}{basis}</p>'
            f'<h3 dir="auto">{_txt(r.get("headline"))}</h3>'
            + (f'<p class="dg-simple"><b>בפשטות:</b> {_txt(r["simple"])}</p>' if r.get("simple") else "")
            + (f'<p class="im-what"><b>מה קרה:</b> {_txt(r["what"])}</p>' if r.get("what") else "")
            + f'<div class="im-cos">{"".join(_co(c, profiles) for c in cos)}</div>'
            + (f'<p class="im-verdict"><b>השורה התחתונה:</b> {_txt(r["verdict"])}</p>' if r.get("verdict") else "")
            + (f'<p class="au-conf"><b>מה יאשר או יפריך:</b> {_txt(r["watch"])}</p>' if r.get("watch") else "")
            + (f'<p class="dg-src">{src}</p>' if src else "")
            + "</article>")


HOW = """<details class="im-how"><summary>איך לקרוא את הכרטיסים</summary><dl>
<dt>האירוע</dt><dd>דיווח של החברה במאיה, ידיעה בתקשורת או החלטה של רגולטור — וכל כרטיס עונה עליו על שאלה
אחת: מה זה עושה למניה.</dd>
<dt>שרשרת ההשפעה</dt><dd>הצעדים מהאירוע ועד השורה בדוח של החברה. הצעד האחרון, המודגש, הוא מה שקורה לחברה
עצמה — ולמה דווקא לה.</dd>
<dt>עוצמה</dt><dd><b>גבוהה</b> — עשוי לשנות במידה ניכרת את הרווח, השווי או הסיכון של החברה ביחס לגודלה.
<b>בינונית</b> — מורגש במגזר אחד או בשורה אחת בדוח. <b>נמוכה</b> — הקשר קיים, אבל קטן או לא ודאי.
אירוע שבו ההשפעה נמוכה לכל החברות מרוכז בסוף היום, תחת "נבדק — כנראה לא משנה".</dd>
<dt>כיוון</dt><dd>▲ חיובי · ▼ שלילי · ◆ מעורב · ● ניטרלי — על העסק של החברה, לא תחזית לשער המניה.</dd>
<dt>כמה זה גדול</dt><dd>ביחס לחברה: סכום מהמקור מול שווי השוק במאיה, או איזה חלק מהפעילות נוגע.</dd>
<dt>מה יכול לבטל את זה</dt><dd>מה יקטין או יבטל את ההשפעה, ומי בכיוון ההפוך.</dd>
</dl></details>"""

FILTERS = """<div class="im-filters" id="im-filters" hidden>
<div class="im-modes" role="group" aria-label="סינון">
<button type="button" data-mode="all" aria-pressed="true">הכל</button>
<button type="button" data-mode="sig" aria-pressed="false">גבוהה ובינונית</button>
<button type="button" data-mode="maya" aria-pressed="false">דיווחי חברות</button>
<button type="button" data-mode="news" aria-pressed="false">תקשורת</button>
<button type="button" data-mode="gov" aria-pressed="false">רגולציה</button>
</div>
<input type="search" id="im-q" placeholder="חיפוש חברה" aria-label="חיפוש לפי שם חברה" autocomplete="off">
<span class="im-count" id="im-count" aria-live="polite"></span>
</div>"""

# שם חברה עם נקודות, גרשיים ורווחים ("איי.סי.אל", "מנורה מב החז") — ההשוואה בלעדיהם
SCRIPT = r"""<script>
(function () {
  var bar = document.getElementById("im-filters");
  if (!bar) { return; }
  bar.hidden = false;
  var cards = Array.prototype.slice.call(document.querySelectorAll("article.im-card"));
  var input = document.getElementById("im-q"), count = document.getElementById("im-count");
  var mode = "all";
  function norm(s) { return (s || "").replace(/[\s.'"׳״\-]/g, "").toLowerCase(); }
  function apply() {
    var q = norm(input.value), shown = 0;
    cards.forEach(function (c) {
      var ok = mode === "all" || (mode === "sig" ? Number(c.getAttribute("data-sig")) >= 2
                                                 : c.getAttribute("data-kind") === mode);
      if (ok && q) {
        ok = c.getAttribute("data-cos").split("|").some(function (n) { return norm(n).indexOf(q) >= 0; });
      }
      c.hidden = !ok;
      if (ok) { shown += 1; }
    });
    document.querySelectorAll("details.im-low, section.im-day").forEach(function (box) {
      box.hidden = !box.querySelector("article.im-card:not([hidden])");
    });
    count.textContent = shown === 1 ? "אירוע אחד" : shown + " אירועים";
  }
  bar.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-mode]");
    if (!b) { return; }
    mode = b.getAttribute("data-mode");
    bar.querySelectorAll("button[data-mode]").forEach(function (x) {
      x.setAttribute("aria-pressed", x === b ? "true" : "false");
    });
    apply();
  });
  input.addEventListener("input", apply);
  apply();
})();
</script>"""


def _day_title(d, today) -> str:
    rel = "היום · " if d == today else ("אתמול · " if d == today - timedelta(days=1) else "")
    return f"{rel}יום {WEEKDAY[d.weekday()]} {d:%d/%m}"


def page(data: dict) -> str:
    state, items, profiles = data["state"], data["items"], data["profiles"]
    now = datetime.now(timezone.utc)
    today = now.astimezone(IL).date()
    last = state.get("last") or {}
    latest = state.get("updated")
    stamp = f"עודכן {_stamp(latest)}" if latest else "טרם עודכן"
    if last and not last.get("ok"):
        stamp += f' · <span class="stale">העדכון של {_stamp(last.get("at"))} נכשל</span>'
    # כמו analyze_impact.waiting: עדיפות 2 ומעלה ובתוך החלון — עדיפות 1 מנותחת רק כמדגם
    since = (now - timedelta(hours=36)).isoformat(timespec="seconds")
    pending = sum(1 for v in (state.get("triage") or {}).values()
                  if v.get("ask") and not v.get("done") and int(v.get("priority") or 0) >= 2
                  and (v.get("ts") or v.get("at") or "") >= since)
    if pending:
        stamp += f" · {pending} ממתינים לניתוח"
    head = f'<div class="dash-head"><h1>השפעה על מניות</h1><span class="stamp">{stamp}</span></div>'
    lead = ('<p class="lead">דיווחים של החברות עצמן, ידיעות בתקשורת והחלטות של רגולטורים — ולכל אחד '
            'התשובה לשאלה <b>מה זה עושה למניה</b>: דרך מה זה מגיע לחברה צעד אחר צעד, כמה זה גדול '
            'ביחס אליה, ומה יכול לבטל את ההשפעה. גם "כמעט כלום" היא תשובה, והיא מוסברת. מתעדכן כל '
            'שעתיים, מתוך הכותרות שנבחרו באתר, דיווחי מאיה ופרסומי הרגולטורים.</p>')
    if not items:
        return "\n".join([head, lead, HOW,
                          '<p class="au-quiet">טרם נותחו אירועים. העמוד מתעדכן כל שעתיים, בשעות היום.</p>'])

    n_today = sum(1 for r in items if (_local(r.get("ts")) or now).date() == today)
    n_high = sum(1 for r in items if int(r.get("sig") or 1) >= 3)
    n_cos = len({c["name"] for r in items for c in r.get("companies") or []})
    tiles = ('<div class="strip">'
             f'<div class="tile"><div class="lbl">אירועים</div><div class="val">{len(items)}</div>'
             f'<div class="chg txt">ב-{PAGE_DAYS} הימים האחרונים</div></div>'
             f'<div class="tile"><div class="lbl">היום</div><div class="val">{n_today}</div></div>'
             f'<div class="tile"><div class="lbl">השפעה גבוהה</div><div class="val">{n_high}</div>'
             '<div class="chg txt">לפחות חברה אחת</div></div>'
             f'<div class="tile"><div class="lbl">חברות</div><div class="val">{n_cos}</div>'
             '<div class="chg txt">שנותחו</div></div></div>')

    by_day: dict = {}
    for r in items:
        d = (_local(r.get("ts")) or now.astimezone(IL)).date()
        by_day.setdefault(d, []).append(r)
    secs = []
    for d in sorted(by_day, reverse=True):
        rows = sorted(by_day[d], key=lambda r: (int(r.get("sig") or 1), r.get("ts") or ""), reverse=True)
        main = [r for r in rows if int(r.get("sig") or 1) >= 2]
        low = [r for r in rows if int(r.get("sig") or 1) < 2]
        body = "".join(_card(r, profiles, latest, today) for r in main)
        if low:
            body += (f'<details class="im-low"><summary>נבדק — כנראה לא משנה '
                     f'<span class="au-cnt">{len(low)}</span></summary>'
                     '<p class="cbs-sub">אירועים שעוררו את השאלה, ושהתשובה עליהם היא שההשפעה קטנה או לא ודאית — '
                     'ולמה.</p>'
                     + "".join(_card(r, profiles, latest, today) for r in low) + "</details>")
        secs.append(f'<section class="im-day" id="im-d-{d.isoformat()}"><h2>{_day_title(d, today)} '
                    f'<span class="au-cnt">{len(rows)}</span></h2>{body}</section>')

    src = ('<p class="au-src">המקורות: הכותרות שנבחרו בעמוד <a href="headlines.html">כותרות</a>, '
           '<a href="reports.html">דיווחי מאיה</a> ופרסומי <a href="gov.html">הרגולטורים</a>. הניתוח: '
           'TLV TASE View — כל מספר בכרטיס נבדק מול המקור, ומה שכל חברה עושה נלקח מתיאור הפעילות '
           'שהיא מסרה למאיה. ניתוח השפעה, לא המלצת השקעה.</p>')
    return "\n".join([f'<div class="im-wrap">{head}', lead, tiles, HOW, FILTERS, *secs, src,
                      "</div>", SCRIPT])


def home(data: dict) -> str:
    """בלוק לעמוד הבית: האירועים של 24 השעות האחרונות שיש בהם השפעה גבוהה או בינונית."""
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    rows = [r for r in data.get("items") or [] if (r.get("ts") or "") >= since and int(r.get("sig") or 1) >= 2]
    if not rows:
        return ""
    rows.sort(key=lambda r: (int(r.get("sig") or 1), r.get("ts") or ""), reverse=True)
    today = now.astimezone(IL).date()
    lis = []
    for r in rows[:5]:
        cos = " · ".join(f'{escape(c["name"])} {DIR_MARK.get(c.get("direction"), "")}'
                         for c in (r.get("companies") or [])[:2])
        lis.append(f'<li><span class="dg-time">{_when(r.get("ts"), today)}</span>'
                   f'<a href="{PAGE}#{anchor(r.get("src") or r["id"])}" dir="auto">{_txt(r.get("headline"))}</a>'
                   f'<span class="dg-dtag">{cos}</span></li>')
    return ('<h2>השפעה על מניות — 24 השעות האחרונות</h2>'
            f'<ul class="dg-must im-home">{"".join(lis)}</ul>'
            f'<p><a href="{PAGE}">כל האירועים וההסברים ←</a></p>')


def report(data: dict) -> list[str]:
    items = data.get("items") or []
    last = (data.get("state") or {}).get("last") or {}
    return [f"::notice::עמוד ההשפעה על מניות: {len(items)} אירועים ב-{PAGE_DAYS} ימים "
            f"({sum(1 for r in items if int(r.get('sig') or 1) >= 3)} בהשפעה גבוהה) · עדכון אחרון "
            f"{_stamp((data.get('state') or {}).get('updated'))}"
            + ("" if not last or last.get("ok") else " · האחרון נכשל")]
