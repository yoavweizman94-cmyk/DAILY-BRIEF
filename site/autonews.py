# -*- coding: utf-8 -*-
"""גיליון ענף הרכב: תמונת מצב, מגמות בישראל ובעולם, החברות בשרשרת, כותרות.

נבנה מ-output/auto/ — הכותרות מ-ingest/auto_pull.py והסקירות מ-
scripts/analyze_auto.py, בצנרת auto-watch שלוש פעמים ביום. המקורות, הנושאים
ומפת החברות ב-config/auto.yaml.

**הגיליון קורא גם בלי סקירה.** לפני הסקירה הראשונה, או כשהאחרונה ישנה,
הכותרות והחברות בשרשרת עדיין מוצגות, ושורה אומרת מה חסר ולמה.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AUTO = ROOT / "output" / "auto"
CFG = ROOT / "config" / "auto.yaml"

DAYS = 7           # כמה ימים של כותרות מוצגים
SHOW_PER_COL = 40  # כותרות גלויות בכל עמודה; השאר תחת "עוד"
PREV_SHOWN = 6     # סקירות קודמות ברשימה המקופלת
STALE_ANALYSIS_H = 36
WEEKDAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
DIR_CLASS = {"חיובי": "up", "שלילי": "down", "מעורב": "mixed"}
# צבע לכל נושא — אותם גוונים כמו נושאי הלמ"ס, כדי שלאתר תהיה שפת צבע אחת.
THEME_CLASS = {"il-market": "t-accounts", "tax-reg": "t-surveys", "tariffs": "t-trade",
               "ev": "t-labor", "china": "t-tourism", "makers": "t-industry",
               "supply": "t-prices", "finance": "t-housing", "fuel": "t-business"}


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Jerusalem")
    except Exception:  # noqa: BLE001 — Windows בלי tzdata
        return timezone(timedelta(hours=3))


IL = _tz()


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
    cfg = {}
    if CFG.exists():
        cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
    cut = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat(timespec="seconds")
    items = []
    for p in sorted((AUTO / "items").glob("*.jsonl"), reverse=True)[:DAYS + 1]:
        items += [r for r in _jsonl(p) if (r.get("ts") or "") >= cut]
    items.sort(key=lambda r: r.get("ts") or "", reverse=True)
    analyses = []
    for p in sorted((AUTO / "analyses").glob("*.jsonl"))[-2:]:
        analyses += _jsonl(p)
    analyses.sort(key=lambda a: a.get("analyzed_at") or "")
    state = {}
    if (AUTO / "state.json").exists():
        try:
            state = json.loads((AUTO / "state.json").read_text(encoding="utf-8"))
        except ValueError:
            state = {}
    return {"cfg": cfg, "items": items, "analyses": analyses, "state": state}


# --------------------------------------------------------------------------
# עזרים

def _local(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(ts).astimezone(IL) if ts else None
    except ValueError:
        return None


def _stamp(ts: str | None) -> str:
    d = _local(ts)
    return f"{d:%d/%m %H:%M}" if d else "—"


# מספור פריטים מהפרומפט ("[21-26]") שדלף לטקסט. analyze_auto מסיר אותו לפני
# השמירה; כאן רשת ביטחון לסקירות ישנות.
_REFS = re.compile(r"\s*\[\d+(?:\s*[-–,]\s*\d+)*\]")


def _t(v) -> str:
    return _REFS.sub("", str(v or "")).strip()


def _para(text) -> str:
    if not text:
        return ""
    t = escape(_t(text))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return "".join(f"<p>{p.strip()}</p>" for p in re.split(r"\n\s*\n|\n", t) if p.strip())


def _dir(d: str | None) -> str:
    if not d:
        return ""
    return f'<span class="cbs-dir {DIR_CLASS.get(d, "flat")}">{escape(d)}</span>'


def _theme_labels(cfg: dict) -> dict:
    return {t["slug"]: t.get("label") or t["slug"] for t in cfg.get("themes") or []}


def _sources_html(nums, refs: dict) -> str:
    links = []
    for k in nums or []:
        r = refs.get(str(k))
        if not r:
            continue
        when = _local(r.get("ts"))
        label = f'{r.get("source") or "מקור"}' + (f" {when:%d/%m}" if when else "")
        links.append(f'<a href="{escape(r.get("url") or "#")}" target="_blank" rel="noopener" '
                     f'title="{escape(r.get("title") or "")}">{escape(label)}</a>')
    return f'<p class="au-src">מקורות: {" · ".join(links)}</p>' if links else ""


def _cos_html(names) -> str:
    cos = "".join(f'<span class="co">{escape(str(c))}</span>' for c in names or [])
    return f'<div class="cc-cos">{cos}</div>' if cos else ""


# --------------------------------------------------------------------------
# חלקי העמוד

def now_html(a: dict | None, state: dict) -> str:
    if not a:
        return ('<h2 id="au-now">תמונת מצב</h2><p class="cbs-note">הסקירה הראשונה תיכתב בריצה הקרובה '
                'של הצנרת, כשייאספו מספיק כותרות. בינתיים — הכותרות והחברות בשרשרת למטה.</p>')
    age_h = None
    d = _local(a.get("analyzed_at"))
    if d:
        age_h = (datetime.now(IL) - d).total_seconds() / 3600
    stale = ('<p class="msg warn">הסקירה נכתבה לפני יותר מ-36 שעות. הכותרות למטה עדכניות יותר ממנה.</p>'
             if age_h and age_h > STALE_ANALYSIS_H else "")
    watch = [w for w in a.get("watch") or [] if isinstance(w, dict) and w.get("what")]
    watch_html = ('<div class="au-watch"><h3>מה לעקוב</h3><ul class="cbs-watch">'
                  + "".join(f'<li><span class="wn">{escape(_t(w.get("when")) or "—")}</span>'
                            f'<span>{escape(_t(w["what"]))}</span></li>' for w in watch)
                  + '</ul></div>') if watch else ""
    return ('<h2 id="au-now">תמונת מצב</h2>' + stale
            + '<div class="au-now">'
            f'<p class="au-headline">{escape(_t(a.get("headline")))}</p>'
            f'<div class="au-overview">{_para(a.get("overview"))}</div>'
            f'<p class="au-meta">סקירה מ-{_stamp(a.get("analyzed_at"))}, על בסיס {a.get("n_il", 0)} כותרות '
            f'מישראל ו-{a.get("n_world", 0)} מהעולם מ-{a.get("window_h", 72)} השעות שקדמו לה. '
            'ניתוח השפעה, לא המלצת השקעה.</p>'
            + watch_html + '</div>')


def trends_html(a: dict | None, key: str, title: str, anchor: str, sub: str) -> str:
    if not a:
        return ""
    refs = a.get("refs") or {}
    cards = []
    for m in a.get(key) or []:
        if not isinstance(m, dict):
            continue
        channel = (f'<p class="au-channel"><b>איך זה מגיע לכאן:</b> {escape(_t(m["channel"]))}</p>'
                   if m.get("channel") else "")
        cards.append(f'<div class="cbs-card au-trend"><div class="cc-head"><h3>{escape(_t(m.get("title")))}</h3>'
                     f'{_dir(m.get("direction"))}</div>{_para(m.get("body"))}{channel}'
                     f'{_cos_html(m.get("companies"))}{_sources_html(m.get("sources"), refs)}</div>')
    if not cards:
        return ""
    return (f'<h2 id="{anchor}">{title}</h2><p class="cbs-sub">{sub}</p>'
            f'<div class="cbs-cards">{"".join(cards)}</div>')


def chain_html(cfg: dict, items: list[dict], a: dict | None) -> str:
    groups = cfg.get("chain") or []
    if not groups:
        return ""
    notes = {c.get("name"): c for c in (a or {}).get("companies") or [] if isinstance(c, dict)}
    refs = (a or {}).get("refs") or {}
    blocks = []
    for g in groups:
        rows, quiet = [], []
        for c in g.get("companies") or []:
            name = c["name"]
            mentions = [r for r in items if name in (r.get("companies") or [])]
            n = notes.get(name)
            if not mentions and not n:
                quiet.append(name)
                continue
            latest = mentions[0] if mentions else None
            count = (f'<span class="au-cnt">{len(mentions)} כותרות ב-{DAYS} ימים</span>' if mentions else "")
            link = (f'<a class="au-latest" href="{escape(latest.get("url") or "#")}" target="_blank" '
                    f'rel="noopener" dir="auto">{escape(latest["title"])}</a>' if latest else "")
            note = (f'<div class="au-note">{_dir(n.get("direction"))} {escape(_t(n.get("note")))}'
                    f'{_sources_html(n.get("sources"), refs)}</div>' if n else "")
            rows.append(f'<li><div class="au-co"><b>{escape(name)}</b>{count}</div>{link}{note}</li>')
        # **חברה בלי אזכור היא שורה אחת לכל התפקיד, לא שורה לכל חברה.** בגרסה
        # הראשונה שבע מבטחות קיבלו שבע שורות של "בלי אזכור השבוע", והקופסה
        # שלהן הייתה הארוכה בעמוד בלי שיש בה מידע.
        quiet_html = (f'<p class="au-quiet"><span>בלי אזכור השבוע:</span> {" · ".join(escape(q) for q in quiet)}</p>'
                      if quiet else "")
        blocks.append(f'<div class="au-role"><h3>{escape(g.get("role") or "")}</h3>'
                      f'<p class="why">{escape(g.get("why") or "")}</p>'
                      + (f'<ul>{"".join(rows)}</ul>' if rows else "") + quiet_html + '</div>')
    return ('<h2 id="au-chain">החברות בשרשרת</h2>'
            '<p class="cbs-sub">החברות הנסחרות בתל אביב שענף הרכב עובר דרך הדוחות שלהן, והמנגנון שמחבר '
            'ביניהם. אזכור נספר רק כששם החברה מופיע בכותרת או בתקציר.</p>'
            f'<div class="au-chain">{"".join(blocks)}</div>')


def _item_html(r: dict, labels: dict) -> str:
    d = _local(r.get("ts"))
    tags = "".join(f'<span class="au-tag {THEME_CLASS.get(t, "t-other")}">'
                   f'<i class="tdot" aria-hidden="true"></i>{escape(labels.get(t, t))}</span>'
                   for t in r.get("themes") or [])
    cos = "".join(f'<span class="co">{escape(c)}</span>' for c in r.get("companies") or [])
    return (f'<li class="au-item" data-t="{escape(" ".join(r.get("themes") or []))}">'
            f'<span class="au-time" dir="ltr">{f"{d:%H:%M}" if d else ""}</span>'
            f'<div class="au-body"><a class="au-title" href="{escape(r.get("url") or "#")}" target="_blank" '
            f'rel="noopener" dir="auto">{escape(r.get("title") or "")}</a>'
            f'<div class="au-tags"><span class="au-srcname">{escape(r.get("source") or "")}</span>{tags}{cos}</div>'
            '</div></li>')


def _column(rows: list[dict], labels: dict, title: str) -> str:
    def render(chunk: list[dict]) -> str:
        out, last = [], None
        for r in chunk:
            d = _local(r.get("ts"))
            day = d.date() if d else None
            if day != last:
                out.append(f'<li class="au-day">{WEEKDAYS[day.weekday()]} {day:%d/%m}</li>' if day else "")
                last = day
            out.append(_item_html(r, labels))
        return "".join(out)

    shown, rest = rows[:SHOW_PER_COL], rows[SHOW_PER_COL:]
    more = (f'<details class="au-more"><summary>עוד {len(rest)} כותרות</summary>'
            f'<ul class="au-list">{render(rest)}</ul></details>') if rest else ""
    body = (f'<ul class="au-list">{render(shown)}</ul>{more}' if rows
            else '<p class="cbs-note">אין כותרות בתקופה.</p>')
    return f'<section class="au-col"><h3>{title} <span class="au-n">{len(rows)}</span></h3>{body}</section>'


def headlines_html(cfg: dict, items: list[dict]) -> str:
    labels = _theme_labels(cfg)
    il = [r for r in items if r.get("region") == "il"]
    world = [r for r in items if r.get("region") != "il"]
    counts = {}
    for r in items:
        for t in r.get("themes") or []:
            counts[t] = counts.get(t, 0) + 1
    chips = ('<div class="cbs-chips" id="au-chips" role="group" hidden aria-label="סינון לפי נושא">'
             '<button type="button" data-t="" aria-pressed="true">הכל</button>'
             + "".join(f'<button type="button" data-t="{escape(slug)}" aria-pressed="false">'
                       f'<i class="tdot {THEME_CLASS.get(slug, "t-other")}" aria-hidden="true"></i>'
                       f'{escape(label)} <span class="au-n">{counts[slug]}</span></button>'
                       for slug, label in labels.items() if counts.get(slug))
             + '</div>')
    return ('<h2 id="au-news">כותרות</h2>'
            f'<p class="cbs-sub">{len(items)} כותרות ב-{DAYS} הימים האחרונים, מאתרי רכב, כלכלה וסחר בישראל '
            'ובעולם. כל כותרת מתויגת בנושאים שבה ובחברות הכיסוי שהיא מזכירה.</p>'
            + chips
            + f'<div class="au-cols">{_column(il, labels, "ישראל")}{_column(world, labels, "עולם")}</div>')


def previous_html(analyses: list[dict]) -> str:
    older = list(reversed(analyses[:-1]))[:PREV_SHOWN]
    if not older:
        return ""
    lis = "".join(f'<li><span class="rl-date" dir="ltr">{_stamp(a.get("analyzed_at"))}</span>'
                  f'<details><summary>{escape(_t(a.get("headline")))}</summary>'
                  f'{_para(a.get("overview"))}</details></li>' for a in older)
    return (f'<details class="cbs-others au-prev"><summary>סקירות קודמות ({len(older)})</summary>'
            f'<ul>{lis}</ul></details>')


SCRIPT = """<script>
(function () {
  "use strict";
  var nav = document.getElementById("au-chips");
  if (!nav) { return; }
  var items = Array.prototype.slice.call(document.querySelectorAll("li.au-item"));
  nav.hidden = false;
  nav.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("button[data-t]") : null;
    if (!b) { return; }
    var t = b.getAttribute("data-t") || "";
    Array.prototype.forEach.call(nav.querySelectorAll("button"), function (x) {
      x.setAttribute("aria-pressed", x === b ? "true" : "false");
    });
    items.forEach(function (li) {
      li.hidden = !!t && (" " + li.getAttribute("data-t") + " ").indexOf(" " + t + " ") < 0;
    });
    // כותרת יום שכל הכותרות תחתיה הוסתרו — מוסתרת גם היא.
    Array.prototype.forEach.call(document.querySelectorAll("li.au-day"), function (day) {
      var n = day.nextElementSibling, any = false;
      while (n && !n.classList.contains("au-day")) {
        if (!n.hidden) { any = true; break; }
        n = n.nextElementSibling;
      }
      day.hidden = !any;
    });
    if (t) {
      Array.prototype.forEach.call(document.querySelectorAll("details.au-more"), function (d) { d.open = true; });
    }
  });
})();
</script>"""


def page(data: dict) -> str:
    cfg = data.get("cfg") or {}
    items = data.get("items") or []
    analyses = data.get("analyses") or []
    state = data.get("state") or {}
    a = analyses[-1] if analyses else None
    if not items and not a:
        return ('<h1>ענף הרכב</h1><p class="lead">טרם נאספו כותרות. הן ייאספו בריצה הקרובה של '
                'צנרת הרכב.</p>')
    stamp = " · ".join(x for x in (
        f'כותרות עד {_stamp(state.get("fetched_at"))}' if state.get("fetched_at") else "",
        f'סקירה {_stamp(a.get("analyzed_at"))}' if a else "") if x)
    fails = state.get("failures") or []
    fail_html = (f'<p class="msg warn">בריצה האחרונה לא נקראו {len(fails)} מקורות מתוך '
                 f'{state.get("sources_total")}. הכותרות מהם יחסרו עד הריצה הבאה.</p>'
                 if fails and len(fails) * 3 >= (state.get("sources_total") or 99) else "")

    il = trends_html(a, "israel", "מגמות בשוק הישראלי", "au-il",
                     "מחירים והשקות, מותגים סיניים, מיסוי, ליסינג ומימון — ומי מהחברות מושפע.")
    world = trends_html(a, "world", "מגמות בעולם", "au-world",
                        "מכסים, ייצור ושרשרת אספקה, סוללות ויצרנים סיניים — ואיך כל אחת מגיעה לחברות בישראל.")
    toc = [("au-now", "תמונת מצב", True), ("au-il", "ישראל", il), ("au-world", "עולם", world),
           ("au-chain", "החברות בשרשרת", True), ("au-news", "כותרות", True)]
    return "\n".join(x for x in [
        '<div class="dash-head"><h1>ענף הרכב</h1>'
        f'<span class="stamp">{stamp}</span></div>',
        '<p class="lead">כותרות ומגמות מענף הרכב בישראל ובעולם, דרך החברות הנסחרות בשרשרת: '
        'יבואניות, רכיבים, ליסינג, אשראי, ביטוח ודלק. מתעדכן שלוש פעמים ביום.</p>',
        '<nav class="cbs-toc" aria-label="בעמוד הזה">'
        + "".join(f'<a href="#{i}">{l}</a>' for i, l, present in toc if present) + '</nav>',
        fail_html,
        now_html(a, state),
        il,
        world,
        chain_html(cfg, items, a),
        headlines_html(cfg, items),
        previous_html(analyses),
        SCRIPT,
    ] if x)


def report(data: dict) -> list[str]:
    items = data.get("items") or []
    analyses = data.get("analyses") or []
    state = data.get("state") or {}
    if not items and not analyses:
        return ['::warning title=אין נתוני רכב::output/auto ריק — גיליון הרכב נבנה בלי כותרות.']
    il = sum(1 for r in items if r.get("region") == "il")
    a = analyses[-1] if analyses else None
    out = [f'::notice::גיליון הרכב: {len(items)} כותרות ב-{DAYS} ימים (ישראל {il}, עולם {len(items) - il}) · '
           f'סקירה אחרונה {(a or {}).get("analyzed_at") or "—"} · משיכה {state.get("fetched_at") or "—"}']
    now = datetime.now(IL)
    fetched = _local(state.get("fetched_at"))
    if fetched and now - fetched > timedelta(hours=30):
        out.append(f'::warning title=כותרות הרכב ישנות::המשיכה האחרונה מ-{state.get("fetched_at")} — '
                   'צנרת auto-watch לא רצה או נכשלה.')
    done = _local((a or {}).get("analyzed_at"))
    if items and (not done or now - done > timedelta(hours=STALE_ANALYSIS_H)):
        out.append('::warning title=סקירת הרכב ישנה::' + (f'האחרונה מ-{a.get("analyzed_at")}' if a else 'אין סקירה')
                   + ' — בדוק את שלב הניתוח ב-auto-watch.')
    return out
