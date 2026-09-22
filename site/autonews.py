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

import share

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
               "supply": "t-prices", "leasing": "t-housing", "finance": "t-other", "fuel": "t-business"}


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
    registry = {}
    for name in ("registrations", "disposals"):
        try:
            registry[name] = json.loads((AUTO / "registry" / f"{name}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            registry[name] = {}
    state = {}
    if (AUTO / "state.json").exists():
        try:
            state = json.loads((AUTO / "state.json").read_text(encoding="utf-8"))
        except ValueError:
            state = {}
    return {"cfg": cfg, "items": items, "analyses": analyses, "state": state, "registry": registry}


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


# **מספר חתום בתוך משפט עברי.** "(חודש +15.0%)" נראה על המסך "(חודש +%15.0)": האחוז
# נודד אל בין הסימן למספר. נמדד בסקירת הסחורות (17/09/2026). מספר שבא אחרי רווח או
# סוגר נעטף ב-bdi; "ב-104.67" (תחילית ומקף) וטווח "25%-30%" אינם נוגעים.
_SIGNED = re.compile(r"(?:(?<=\s)|(?<=\())([+\-−]\d[\d.,]*%?)")


def _bidi(escaped: str) -> str:
    return _SIGNED.sub(r'<bdi dir="ltr">\1</bdi>', escaped)


def _txt(v) -> str:
    """טקסט מהסקירה: escape, ניקוי מספור ובידוד מספרים חתומים."""
    return _bidi(escape(_t(v)))


def _para(text) -> str:
    if not text:
        return ""
    t = _txt(text)
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
# ייצוא לתמונה ולציוץ — המנוע ב-site/export_card.js, הכלים ב-site/share.py.
#
# **הכרטיס נבנה מאותם נתונים כמו הסעיף.** בסעיף הליסינג — מאותם משתנים שמהם
# נבנים האריחים והטבלאות (בתוך leasing_html), כך שמספר בתמונה אינו יכול להיות
# שונה מהמספר שבעמוד. ושורת המקור נוקבת במקור של הכרטיס: רשם כלי הרכב, או
# הכותרות שעליהן נשענה הסקירה.

SRC_REG = "משרד התחבורה — רשם כלי הרכב, מחירון היבואנים והיסטוריית הבעלויות (data.gov.il)"
SRC_REG_SHORT = "משרד התחבורה (data.gov.il)"
SRC_AI = "ניתוח — TLV TASE View"


def _day(a: dict | None) -> str:
    d = _local((a or {}).get("analyzed_at"))
    return f"{d:%d/%m}" if d else ""


def _src_ai(refs: dict, ids, reg: bool = False) -> str:
    pubs = share.publishers(refs, ids)
    return share.source_line([SRC_REG if reg else "", ("כותרות — " + ", ".join(pubs)) if pubs else "", SRC_AI])


def _tsrc_ai(refs: dict, ids, reg: bool = False) -> str:
    pubs = share.publishers(refs, ids)
    names = ([SRC_REG_SHORT] if reg else []) + pubs[:2]
    if not names:
        return ""
    more = len(pubs) > 2
    return ("מקורות: " if len(names) > 1 or more else "מקור: ") + ", ".join(names) + (" ועוד" if more else "")


def _export(key: str, stamp: str, kicker: str, title: str, sub: str, blocks: list, source: str,
            head: str, lines: list[str], tsource: str | None = None) -> str:
    payload = share.card(kicker, title, sub, blocks, source, file=f"tlv-auto-{key}-{stamp or 'latest'}")
    return share.controls(key, payload, share.tweet(head, lines, tsource or source))


def export_now(a: dict | None) -> str:
    if not a:
        return ""
    watch = [w for w in a.get("watch") or [] if isinstance(w, dict) and w.get("what")]
    ids = sorted({i for k in ("israel", "world") for m in a.get(k) or [] if isinstance(m, dict)
                  for i in m.get("sources") or []})
    refs = a.get("refs") or {}
    titles = [share.plain(m.get("title")) for k in ("israel", "world") for m in a.get(k) or []
              if isinstance(m, dict) and m.get("title")]
    blocks = [{"type": "notes", "title": "תמונת מצב", "items": share.sentences(a.get("overview"))},
              {"type": "notes", "title": "מה לעקוב",
               "items": [(f'{share.plain(w.get("when"))} — ' if w.get("when") else "") + share.plain(w["what"])
                         for w in watch]} if watch else None]
    sub = (f'סקירה מ-{_stamp(a.get("analyzed_at"))}, על {a.get("n_il", 0)} כותרות מישראל ו-{a.get("n_world", 0)} '
           f'מהעולם. {share.DISCLAIMER}')
    return _export("au-now", str(a.get("analyzed_at") or "")[:10], "ענף הרכב · תמונת מצב",
                   share.plain(a.get("headline")), sub, blocks, _src_ai(refs, ids),
                   f"ענף הרכב · {_day(a)}", [share.lead(a.get("headline"))] + [f"• {t}" for t in titles],
                   _tsrc_ai(refs, ids))


def export_trends(a: dict | None, key: str, title: str) -> str:
    items = [m for m in (a or {}).get(key) or [] if isinstance(m, dict) and m.get("title")]
    if not items:
        return ""
    refs = a.get("refs") or {}
    notes = []
    for m in items:
        t = f'{share.plain(m["title"])} — {share.plain(m.get("body"))}'
        if m.get("channel"):
            t += f' איך זה מגיע לכאן: {share.plain(m["channel"])}'
        notes.append(t)
    ids = sorted({i for m in items for i in m.get("sources") or []})
    cos = sorted({str(c) for m in items for c in m.get("companies") or []})
    blocks = [{"type": "notes", "items": notes},
              {"type": "notes", "title": "החברות", "items": ["מושפעות לפי הסקירה: " + ", ".join(cos) + "."]}
              if cos else None]
    sub = f'סקירה מ-{_stamp(a.get("analyzed_at"))}. {share.DISCLAIMER}'
    return _export(f"au-{key}", str(a.get("analyzed_at") or "")[:10], "ענף הרכב", title, sub, blocks,
                   _src_ai(refs, ids), f"{title} · {_day(a)}", [f"• {share.plain(m['title'])}" for m in items],
                   _tsrc_ai(refs, ids))


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
                            f'<span>{_txt(w["what"])}</span></li>' for w in watch)
                  + '</ul></div>') if watch else ""
    return ('<h2 id="au-now">תמונת מצב</h2>' + stale + export_now(a)
            + '<div class="au-now">'
            f'<p class="au-headline">{_txt(a.get("headline"))}</p>'
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
        channel = (f'<p class="au-channel"><b>איך זה מגיע לכאן:</b> {_txt(m["channel"])}</p>'
                   if m.get("channel") else "")
        cards.append(f'<div class="cbs-card au-trend"><div class="cc-head"><h3>{_txt(m.get("title"))}</h3>'
                     f'{_dir(m.get("direction"))}</div>{_para(m.get("body"))}{channel}'
                     f'{_cos_html(m.get("companies"))}{_sources_html(m.get("sources"), refs)}</div>')
    if not cards:
        return ""
    return (f'<h2 id="{anchor}">{title}</h2><p class="cbs-sub">{sub}</p>' + export_trends(a, key, title)
            + f'<div class="cbs-cards">{"".join(cards)}</div>')


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
            note = (f'<div class="au-note">{_dir(n.get("direction"))} {_txt(n.get("note"))}'
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


# --------------------------------------------------------------------------
# ליסינג והשכרה — נתוני רשם כלי הרכב

def _n(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else "—"


def _p(a, b, digits: int = 1) -> float | None:
    return round(a / b * 100, digits) if b else None


def _mm(k: str) -> str:
    return f"{k[5:7]}/{k[:4]}"


HE_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר",
             "אוקטובר", "נובמבר", "דצמבר"]


def _mon(k: str) -> str:
    return f"{HE_MONTHS[int(k[5:7]) - 1]} {k[:4]}"


def _mrange(a: str, b: str) -> str:
    """"יוני–אוגוסט 2026" ולא "06/2026–08/2026": טווח מספרי בתוך משפט עברי
    מתהפך, וקורא לא יודע אם הוא נקרא מימין או משמאל."""
    if a[:4] == b[:4]:
        return f"{HE_MONTHS[int(a[5:7]) - 1]}–{HE_MONTHS[int(b[5:7]) - 1]} {a[:4]}"
    return f"{_mon(a)}–{_mon(b)}"


def _yago(k: str) -> str:
    return f"{int(k[:4]) - 1}-{k[5:]}"


def _change_words(now: float, before: float, when: str) -> str:
    """"עלייה של 12.1% מול 08/2025" ולא "+12.1%": סימן לפני מספר בתוך משפט
    עברי נודד לצד השני ("12.1%+")."""
    if not before:
        return "אין השוואה שנתית"
    d = (now - before) / before * 100
    if abs(d) < 0.05:
        return f"ללא שינוי מול {when}"
    return f"{'עלייה' if d > 0 else 'ירידה'} של {abs(d):.1f}% מול {when}"


def _share_series(months: dict, keys: list[str], field: str, owner: str, key: str) -> list[float | None]:
    out = []
    for k in keys:
        v = months[k]
        base = (v.get("own") or {}).get(owner, 0)
        if field == "fuel":
            num = ((v.get("fuel") or {}).get(owner) or {}).get(key, 0)
        else:
            num = dict((v.get("country") or {}).get(owner) or []).get(key, 0)
        out.append(_p(num, base))
    return out


def _ticks_n(hi: float) -> list[float]:
    step = 1000
    for cand in (1000, 2000, 2500, 4000, 5000, 10000):
        if hi / cand <= 5:
            step = cand
            break
    top = step * (int(hi // step) + 1)
    return [step * i for i in range(int(top // step) + 1)]


def _lease_bars(months: dict, keys: list[str]) -> str:
    """רכישות ציי הליסינג לפי חודש. החודש הנוכחי חלקי ומסומן בהיר."""
    W, H, L, R, T, B = 440.0, 180.0, 40.0, 8.0, 10.0, 22.0
    vals = [(months[k].get("own") or {}).get("ליסינג", 0) for k in keys]
    ticks = _ticks_n(max(vals) or 1)
    hi = ticks[-1] or 1
    pw, ph = W - L - R, H - T - B
    slot = pw / len(keys)
    parts = []
    for t in ticks:
        y = T + (hi - t) / hi * ph
        parts.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L:.0f}" x2="{W - R:.0f}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="ax" x="{L - 6:.0f}" y="{y + 3.5:.1f}" text-anchor="end">{t / 1000:g}K</text>')
    last_full = max((i for i, k in enumerate(keys) if not months[k].get("partial")), default=-1)
    for i, (k, v) in enumerate(zip(keys, vals)):
        x = L + slot * i
        if i and k.endswith("-01"):
            parts.append(f'<line class="yr" x1="{x:.1f}" x2="{x:.1f}" y1="{T:.0f}" y2="{T + ph:.0f}"/>')
            parts.append(f'<text class="ax" x="{x + 4:.1f}" y="{H - 7:.0f}">{k[:4]}</text>')
        y = T + (hi - v) / hi * ph
        cls = "bar" + (" last" if i == last_full else "") + (" partial" if months[k].get("partial") else "")
        parts.append(f'<rect class="{cls}" x="{x + slot * 0.19:.1f}" y="{y:.1f}" width="{slot * 0.62:.1f}" '
                     f'height="{max(T + ph - y, 0.9):.1f}"/>')
        share = _p(v, months[k].get("n") or 0)
        note = " · חודש חלקי" if months[k].get("partial") else (" · חושב באיחור" if months[k].get("late") else "")
        parts.append(f'<rect class="hit" x="{x:.1f}" y="{T:.0f}" width="{slot:.1f}" height="{ph:.0f}">'
                     f'<title>{_mm(k)} · {_n(v)} רכבים לליסינג ·{share if share is not None else "—"}% מהרכב החדש{note}</title></rect>')
    return (f'<svg class="cbs-ch au-ch" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
            f'aria-label="רכישות ציי הליסינג לפי חודש">{"".join(parts)}</svg>')


def _share_lines(months: dict, keys: list[str]) -> str:
    """חלק התוצרת הסינית והחשמליים בציי הליסינג — אחוזים, חודשים שלמים."""
    W, H, L, R, T, B = 440.0, 180.0, 34.0, 8.0, 10.0, 22.0
    china = _share_series(months, keys, "country", "ליסינג", "סין")
    ev = _share_series(months, keys, "fuel", "ליסינג", "ev")
    top = max([x for x in china + ev if x is not None] + [10.0])
    hi = 20.0 * (int(top // 20) + 1)
    ticks = [hi * i / 4 for i in range(5)]
    pw, ph = W - L - R, H - T - B
    slot = pw / len(keys)

    def X(i):
        return L + slot * (i + 0.5)

    def Y(v):
        return T + (hi - v) / hi * ph

    parts = []
    for t in ticks:
        parts.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L:.0f}" x2="{W - R:.0f}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>')
        parts.append(f'<text class="ax" x="{L - 6:.0f}" y="{Y(t) + 3.5:.1f}" text-anchor="end">{t:g}%</text>')
    for i, k in enumerate(keys):
        if i and k.endswith("-01"):
            x = L + slot * i
            parts.append(f'<line class="yr" x1="{x:.1f}" x2="{x:.1f}" y1="{T:.0f}" y2="{T + ph:.0f}"/>')
            parts.append(f'<text class="ax" x="{x + 4:.1f}" y="{H - 7:.0f}">{k[:4]}</text>')
    for cls, series in (("l-china", china), ("l-ev", ev)):
        pts = [f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(series) if v is not None]
        if len(pts) >= 2:
            parts.append(f'<polyline class="{cls}" points="{" ".join(pts)}"/>')
            i_last = max(i for i, v in enumerate(series) if v is not None)
            parts.append(f'<circle class="{cls}-end" cx="{X(i_last):.1f}" cy="{Y(series[i_last]):.1f}" r="3.2"/>')
    for i, k in enumerate(keys):
        parts.append(f'<rect class="hit" x="{L + slot * i:.1f}" y="{T:.0f}" width="{slot:.1f}" height="{ph:.0f}">'
                     f'<title>{_mm(k)} · תוצרת סין {china[i]}% · חשמלי {ev[i]}%</title></rect>')
    return (f'<svg class="cbs-ch au-ch" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
            f'aria-label="חלק התוצרת הסינית והחשמליים בציי הליסינג">{"".join(parts)}</svg>')


def _sum_top(months: dict, keys: list[str], field: str, owner: str) -> dict:
    out: dict = {}
    for k in keys:
        for name, cnt in ((months.get(k) or {}).get(field) or {}).get(owner) or []:
            out[name] = out.get(name, 0) + cnt
    return out


def _pts(d: float) -> str:
    """שינוי בנקודות אחוז: "+7.4" / "−2.1"."""
    return f"{0:.1f}" if abs(d) < 0.05 else f"{'+' if d > 0 else '−'}{abs(d):.1f}"


def _lease_exports(data: dict, a: dict | None, months: dict, keys: list[str], full: list[str],
                   tiles: list[tuple], disp: dict, imap: dict) -> dict:
    """הכרטיסים והציוצים של סעיף הליסינג — מאותם נתונים שמהם נבנים האריחים והטבלאות."""
    out = {"month": "", "imp": "", "brands": "", "disp": "", "ai": ""}
    last = full[-1]
    v, ya = months[last], months.get(_yago(last)) or {}
    n, own = v.get("n") or 0, v.get("own") or {}
    lease, ya_n, ya_lease = own.get("ליסינג", 0), ya.get("n") or 0, (ya.get("own") or {}).get("ליסינג", 0)
    china = dict((v.get("country") or {}).get("ליסינג") or []).get("סין", 0)
    ya_china = dict((ya.get("country") or {}).get("ליסינג") or []).get("סין", 0)
    ev_l = ((v.get("fuel") or {}).get("ליסינג") or {}).get("ev", 0)
    ev_p = ((v.get("fuel") or {}).get("פרטי") or {}).get("ev", 0)
    reg = (data.get("registry") or {}).get("registrations") or {}
    upd = _stamp(reg.get("updated"))
    src = share.source_line([SRC_REG + (f", עודכן {upd}" if upd != "—" else "")])
    tsrc = f"מקור: {SRC_REG_SHORT}"
    kick = "ענף הרכב · ליסינג והשכרה"
    lz_a = (a or {}).get("leasing") or {}
    refs = (a or {}).get("refs") or {}

    # ---- החודש: אריחים, רישומים לפי חודש, תוצרת סין וחשמלי, והסקירה
    win = full[-13:]
    labels = [f"{k[5:7]}/{k[2:4]}" for k in win]
    vals = [(months[k].get("own") or {}).get("ליסינג", 0) for k in win]
    items = [{"label": l, "value": val, "cap": c} for l, val, c in tiles]
    dm = disp.get("months") or {}
    dk = sorted(dm)[-1] if dm else None
    fl = (dm.get(dk) or {}).get("flows") or {} if dk else {}
    d_out = sum(x for kk, x in fl.items() if kk.startswith("ליסינג>"))
    held = ((dm.get(dk) or {}).get("held_median") or {}).get("ליסינג") if dk else None
    blocks = [{"type": "stats", "items": items[:3]},
              {"type": "stats", "items": items[3:]} if len(items) > 3 else None,
              {"type": "columns", "title": "רכבים חדשים שנרשמו לליסינג, לפי חודש",
               "items": [{"label": lb, "value": x, "text": _n(x)} for lb, x in zip(labels, vals)],
               "maxText": _n(max(vals) if vals else 0)},
              {"type": "lines", "title": "מה נכנס לציי הליסינג: תוצרת סין וחשמלי מלא, % מהליסינג",
               "suffix": "%", "decimals": 1, "zero": True, "labels": labels,
               "series": [{"name": "תוצרת סין", "values": _share_series(months, win, "country", "ליסינג", "סין")},
                          {"name": "חשמלי מלא", "values": _share_series(months, win, "fuel", "ליסינג", "ev")}]},
              {"type": "notes", "title": "הסקירה", "items": share.sentences(lz_a.get("summary"))}
              if lz_a.get("summary") else None]
    lines = [f"{_n(lease)} רכבים חדשים לציי הליסינג — {_p(lease, n)}% מהרכב הפרטי החדש",
             f"תוצרת סין: {_p(china, lease)}% מהליסינג" + (f" (אשתקד {_p(ya_china, ya_lease)}%)" if ya_lease else ""),
             f"חשמלי: {_p(ev_l, lease)}% בליסינג, {_p(ev_p, own.get('פרטי', 0))}% בקנייה פרטית"]
    if dk:
        lines.append(f"{_n(d_out)} רכבים יצאו מהציים ב{HE_MONTHS[int(dk[5:7]) - 1]}"
                     + (f", חציון {held} חודשים בצי" if held else ""))
    msrc = src if not lz_a.get("summary") else share.source_line([SRC_REG, SRC_AI])
    payload = share.card(kick, f"מה הציים קונים ומוכרים · {_mon(last)}",
                         "רכב פרטי חדש שעלה לכביש, לפי בעלות, ורכבים שיצאו מציי הליסינג — מנתוני רשם כלי הרכב.",
                         blocks, msrc, file=f"tlv-auto-lease-{last}")
    out["month"] = share.controls("au-lease", payload, share.tweet(f"ליסינג · {_mon(last)}", lines, tsrc))

    # ---- היבואניות
    last3 = full[-3:]
    prev3 = [_yago(k) for k in last3]
    tot, lz, dl, before = (_sum_top(months, last3, "importer", "all"), _sum_top(months, last3, "importer", "ליסינג"),
                           _sum_top(months, last3, "importer", "סוחר"), _sum_top(months, prev3, "importer", "all"))
    order = sorted(tot, key=lambda x: -tot[x])[:12]
    order += [x for x in imap if x in tot and x not in order]
    rows, tlines = [], []
    for name in order:
        t = tot[name]
        yoy = _p(t - before.get(name, 0), before.get(name, 0), 0) if before.get(name, 0) >= 300 else None
        listed = (" · נסחרת" if imap[name] == name else f" · נסחרת: {imap[name]}") if name in imap else ""
        rows.append({"name": name + listed, "t": _n(t), "l": _n(lz.get(name, 0)),
                     "lp": f"{_p(lz.get(name, 0), t, 0)}%", "d": _n(dl.get(name, 0)),
                     "y": share.signed(yoy, 0) if yoy is not None else "—"})
    for name in order[:4] + [x for x in imap if x in tot and x not in order[:4]]:
        yoy = _p(tot[name] - before.get(name, 0), before.get(name, 0), 0) if before.get(name, 0) >= 300 else None
        tlines.append(f"{name} {_n(tot[name])}" + (f" · {share.arrow(yoy, 0)} מול אשתקד" if yoy is not None else ""))
    rng = _mrange(last3[0], last3[-1])
    payload = share.card(kick, f"היבואניות: רכב חדש ב{rng}",
                         "רכב פרטי חדש לפי יבואנית, ומה ממנו נרשם לליסינג ולסוחרים.",
                         [{"type": "table", "cols": [["יבואנית", "name", "rtl"], ["רכב חדש", "t", "ltr"],
                                                     ["לליסינג", "l", "ltr"], ["% לליסינג", "lp", "ltr"],
                                                     ["לסוחרים", "d", "ltr"], ["מול אשתקד", "y", "ltr"]],
                           "rows": rows},
                          {"type": "notes", "items": [
                              "השוואה שנתית רק ליבואנית עם 300 רכבים לפחות אשתקד. שינוי חד יכול לשקף מותג שעבר בין "
                              "יבואניות — השם נלקח ממחירון משרד התחבורה לכל שנת דגם.",
                              "\"לסוחרים\" — רכב חדש שנרשם על שם סוחר; לרוב רישום מוקדם לפני מכירה."]}],
                         src, file=f"tlv-auto-importers-{last}")
    out["imp"] = share.controls("au-imp", payload, share.tweet(f"היבואניות · רכב חדש ב{rng}", tlines, tsrc))

    # ---- המותגים בליסינג
    brands, bprev = _sum_top(months, last3, "brand", "ליסינג"), _sum_top(months, prev3, "brand", "ליסינג")
    bsum, bpsum = sum(brands.values()) or 1, sum(bprev.values()) or 1
    bc = {}
    for k in last3:
        bc.update(months[k].get("brand_country") or {})
    rows, tlines = [], []
    for name in sorted(brands, key=lambda x: -brands[x])[:12]:
        sh, ps = brands[name] / bsum * 100, bprev.get(name, 0) / bpsum * 100
        rows.append({"name": name, "c": bc.get(name, "—"), "n": _n(brands[name]), "sh": f"{sh:.1f}%",
                     "ps": f"{ps:.1f}%", "d": _pts(sh - ps)})
        if len(tlines) < 5 and name != "לא ידוע":
            tlines.append(f"{name} {sh:.1f}% (אשתקד {ps:.1f}%)")
    payload = share.card(kick, f"מה קונים הציים: המותגים בליסינג ב{rng}",
                         "חלק כל מותג מהרכב הפרטי החדש שנרשם לליסינג, מול אותם חודשים אשתקד.",
                         [{"type": "table", "cols": [["מותג", "name", "rtl"], ["ארץ תוצר", "c", "rtl"],
                                                     ["רכבים", "n", "ltr"], ["חלק מהליסינג", "sh", "ltr"],
                                                     ["אשתקד", "ps", "ltr"], ["שינוי (נק׳)", "d", "ltr"]],
                           "rows": rows}],
                         src, file=f"tlv-auto-brands-{last}")
    out["brands"] = share.controls("au-brands", payload,
                                   share.tweet(f"מה קונים ציי הליסינג · {rng}", tlines, tsrc))

    # ---- מה יוצא מהציים
    if dm:
        dks = sorted(dm)[-12:]
        drows, dvals = [], []
        for k in dks:
            f = dm[k].get("flows") or {}
            o = sum(x for kk, x in f.items() if kk.startswith("ליסינג>"))
            h = (dm[k].get("held_median") or {}).get("ליסינג")
            dvals.append(o)
            drows.append({"m": _mm(k), "o": _n(o), "d": _n(f.get("ליסינג>סוחר", 0)), "p": _n(f.get("ליסינג>פרטי", 0)),
                          "c": _n(f.get("ליסינג>חברה", 0)), "h": str(h) if h is not None else "—"})
        hi_k, lo_k = dks[dvals.index(max(dvals))], dks[dvals.index(min(dvals))]
        tl = [f"{_n(d_out)} רכבים — {_n(fl.get('ליסינג>סוחר', 0))} לסוחרים, {_n(fl.get('ליסינג>פרטי', 0))} לפרטיים",
              f"חציון {held} חודשים בצי" if held else "",
              f"ב-{len(dks)} החודשים: בין {_n(min(dvals))} ({_mon(lo_k)}) ל-{_n(max(dvals))} ({_mon(hi_k)})"]
        payload = share.card(kick, "מה יוצא מהציים: רכבים שנמכרו מבעלות ליסינג",
                             "רכב שבעלות חדשה עליו התחילה בחודש, אחרי תקופה בבעלות ליסינג — ההיצע שנכנס לשוק "
                             "היד השנייה.",
                             [{"type": "columns", "title": "יצאו מציי הליסינג, לפי חודש",
                               "items": [{"label": f"{k[5:7]}/{k[2:4]}", "value": x, "text": _n(x)}
                                         for k, x in zip(dks, dvals)], "maxText": _n(max(dvals))},
                              {"type": "table", "cols": [["חודש", "m", "ltr"], ["יצאו מליסינג", "o", "ltr"],
                                                         ["לסוחר", "d", "ltr"], ["לפרטי", "p", "ltr"],
                                                         ["לחברה", "c", "ltr"], ["חציון חודשים בצי", "h", "ltr"]],
                               "rows": drows}],
                             src, file=f"tlv-auto-disposals-{dk}")
        out["disp"] = share.controls("au-disp", payload,
                                     share.tweet(f"יצאו מציי הליסינג · {_mon(dk)}", tl, tsrc))

    # ---- התובנות מהסקירה
    pts = [m for m in lz_a.get("points") or [] if isinstance(m, dict) and m.get("title")]
    if pts:
        ids = sorted({i for m in pts for i in m.get("sources") or []})
        cos = sorted({str(c) for m in pts for c in m.get("companies") or []})
        reg_m = (a or {}).get("registry_month")
        payload = share.card(kick, "ליסינג והשכרה: התובנות",
                             f'ניתוח מ-{_stamp((a or {}).get("analyzed_at"))}'
                             + (f", על נתוני הרשם עד {_mon(reg_m)}" if reg_m else "") + f". {share.DISCLAIMER}",
                             [{"type": "notes", "items": [f'{share.plain(m["title"])} — {share.plain(m.get("body"))}'
                                                          for m in pts]},
                              {"type": "notes", "title": "החברות", "items": [", ".join(cos) + "."]} if cos else None],
                             _src_ai(refs, ids, reg=True), file=f"tlv-auto-lease-insights-{last}")
        out["ai"] = share.controls("au-lease-ai", payload,
                                   share.tweet(f"ליסינג · תובנות · {_day(a)}", [f"• {share.plain(m['title'])}" for m in pts],
                                               _tsrc_ai(refs, ids, reg=True)))
    return out


def leasing_html(data: dict, a: dict | None) -> str:
    reg = (data.get("registry") or {}).get("registrations") or {}
    disp = (data.get("registry") or {}).get("disposals") or {}
    months = reg.get("months") or {}
    keys = sorted(months)
    full = [k for k in keys if not months[k].get("partial")]
    if not full:
        return ""
    cfg = data.get("cfg") or {}
    imap = (cfg.get("registry") or {}).get("importers") or {}
    last, v = full[-1], months[full[-1]]
    ya = months.get(_yago(last)) or {}
    n, own = v.get("n") or 0, v.get("own") or {}
    lease = own.get("ליסינג", 0)
    ya_n, ya_lease = ya.get("n") or 0, (ya.get("own") or {}).get("ליסינג", 0)
    china = dict((v.get("country") or {}).get("ליסינג") or []).get("סין", 0)
    ya_china = dict((ya.get("country") or {}).get("ליסינג") or []).get("סין", 0)
    ev_l = ((v.get("fuel") or {}).get("ליסינג") or {}).get("ev", 0)
    ev_p = ((v.get("fuel") or {}).get("פרטי") or {}).get("ev", 0)

    tiles = [
        (f"רכב פרטי חדש · {_mon(last)}", _n(n), _change_words(n, ya_n, _mon(_yago(last)))),
        ("לציי הליסינג", _n(lease),
         f"{_p(lease, n)}% מהרכב החדש" + (f" · אשתקד {_p(ya_lease, ya_n)}%" if ya_n else "")),
        ("תוצרת סין בליסינג", f"{_p(china, lease)}%",
         f"אשתקד {_p(ya_china, ya_lease)}%" if ya_lease else ""),
        ("חשמלי בליסינג", f"{_p(ev_l, lease)}%",
         f"בקנייה פרטית {_p(ev_p, own.get('פרטי', 0))}%"),
    ]
    dm = disp.get("months") or {}
    if dm:
        dk = sorted(dm)[-1]
        f = dm[dk].get("flows") or {}
        out = sum(x for key, x in f.items() if key.startswith("ליסינג>"))
        held = (dm[dk].get("held_median") or {}).get("ליסינג")
        tiles.append((f"יצאו מציי הליסינג · {_mon(dk)}", _n(out),
                      (f"חציון {held} חודשים בצי · " if held else "")
                      + f"{_p(f.get('ליסינג>סוחר', 0), out, 0)}% לסוחרים"))
    exp = _lease_exports(data, a, months, keys, full, tiles, disp, imap)
    _EXP_IMP, _EXP_BR, _EXP_DP, _EXP_AI = exp["imp"], exp["brands"], exp["disp"], exp["ai"]
    strip = ('<section class="strip wide au-kpi">' + "".join(
        f'<div class="tile"><span class="lbl">{escape(l)}</span><span class="val" dir="ltr">{escape(val)}</span>'
        f'<span class="chg txt">{escape(c)}</span></div>' for l, val, c in tiles) + '</section>')

    charts = ('<div class="au-charts">'
              f'<figure><figcaption>רכבים חדשים שנרשמו לליסינג, לפי חודש</figcaption>{_lease_bars(months, keys)}'
              '<p class="au-legend"><i class="sw bar"></i>חודש שלם <i class="sw partial"></i>החודש הנוכחי, חלקי</p></figure>'
              f'<figure><figcaption>מה נכנס לציי הליסינג: תוצרת סין וחשמליים</figcaption>{_share_lines(months, full)}'
              '<p class="au-legend"><i class="sw l-china"></i>תוצרת סין <i class="sw l-ev"></i>חשמלי מלא</p></figure>'
              '</div>')

    last3 = full[-3:]
    prev3 = [_yago(k) for k in last3]
    tot, lz, dl, before = (_sum_top(months, last3, "importer", "all"), _sum_top(months, last3, "importer", "ליסינג"),
                           _sum_top(months, last3, "importer", "סוחר"), _sum_top(months, prev3, "importer", "all"))
    order = sorted(tot, key=lambda x: -tot[x])[:12]
    order += [x for x in imap if x in tot and x not in order]
    rows = []
    for name in order:
        t = tot[name]
        chip = f' <span class="co">{escape(imap[name])}</span>' if name in imap else ""
        yoy = _p(t - before.get(name, 0), before.get(name, 0), 0) if before.get(name, 0) >= 300 else None
        cls = "up" if (yoy or 0) > 0 else ("down" if (yoy or 0) < 0 else "flat")
        tr = '<tr class="listed">' if name in imap else "<tr>"
        rows.append(f'{tr}<td class="city">{escape(name)}{chip}</td>'
                    f'<td dir="ltr">{_n(t)}</td><td class="key" dir="ltr">{_n(lz.get(name, 0))}</td>'
                    f'<td dir="ltr">{_p(lz.get(name, 0), t, 0)}%</td><td dir="ltr">{_n(dl.get(name, 0))}</td>'
                    f'<td class="trend {cls}" dir="ltr">{("0%" if abs(yoy) < 0.5 else f"{yoy:+.0f}%") if yoy is not None else "—"}</td></tr>')
    importers = (f'<h3 class="au-h3">היבואניות: רכב חדש ב{_mrange(last3[0], last3[-1])}, ומה ממנו לליסינג</h3>'
                 + _EXP_IMP +
                 '<div class="tw"><table class="nadlan au-tbl"><thead><tr><th>יבואנית</th><th>רכב חדש</th>'
                 '<th>לליסינג</th><th>% לליסינג</th><th>לסוחרים</th><th>מול אשתקד</th></tr></thead><tbody>'
                 + "".join(rows) + '</tbody></table></div>'
                 '<p class="cbs-note">"לסוחרים" — רכב חדש שנרשם על שם סוחר; לרוב רישום מוקדם לפני מכירה. '
                 'השוואה שנתית מוצגת רק ליבואנית עם 300 רכבים לפחות אשתקד, ושינוי חד בה יכול לשקף מותג '
                 'שעבר בין יבואניות — השם נלקח ממחירון משרד התחבורה לכל שנת דגם.</p>')

    brands, bprev = _sum_top(months, last3, "brand", "ליסינג"), _sum_top(months, prev3, "brand", "ליסינג")
    bsum, bpsum = sum(brands.values()) or 1, sum(bprev.values()) or 1
    bc = {}
    for k in last3:
        bc.update(months[k].get("brand_country") or {})
    brows = []
    for name in sorted(brands, key=lambda x: -brands[x])[:12]:
        sh, ps = brands[name] / bsum * 100, bprev.get(name, 0) / bpsum * 100
        d = sh - ps
        cls = "up" if d > 0.05 else ("down" if d < -0.05 else "flat")
        brows.append(f'<tr><td class="city">{escape(name)}</td><td>{escape(bc.get(name, "—"))}</td>'
                     f'<td dir="ltr">{_n(brands[name])}</td><td class="key" dir="ltr">{sh:.1f}%</td>'
                     f'<td dir="ltr">{ps:.1f}%</td><td class="trend {cls}" dir="ltr">{d:+.1f}</td></tr>')
    brand_tbl = (f'<h3 class="au-h3">מה קונים הציים: המותגים שנרשמו לליסינג ב{_mrange(last3[0], last3[-1])}</h3>'
                 + _EXP_BR +
                 '<div class="tw"><table class="nadlan au-tbl"><thead><tr><th>מותג</th><th>ארץ תוצר</th>'
                 '<th>רכבים</th><th>חלק מהליסינג</th><th>אשתקד</th><th>שינוי (נק׳)</th></tr></thead><tbody>'
                 + "".join(brows) + '</tbody></table></div>')

    drows = []
    for k in sorted(dm)[-12:]:
        f = dm[k].get("flows") or {}
        out = sum(x for key, x in f.items() if key.startswith("ליסינג>"))
        held = (dm[k].get("held_median") or {}).get("ליסינג")
        drows.append(f'<tr><td class="city">{_mm(k)}</td><td class="key" dir="ltr">{_n(out)}</td>'
                     f'<td dir="ltr">{_n(f.get("ליסינג>סוחר", 0))}</td><td dir="ltr">{_n(f.get("ליסינג>פרטי", 0))}</td>'
                     f'<td dir="ltr">{_n(f.get("ליסינג>חברה", 0))}</td><td dir="ltr">{held if held is not None else "—"}</td></tr>')
    disp_tbl = ('<h3 class="au-h3">מה יוצא מהציים: רכבים שנמכרו מבעלות ליסינג</h3>'
                + _EXP_DP +
                '<div class="tw"><table class="nadlan au-tbl"><thead><tr><th>חודש</th><th>יצאו מליסינג</th>'
                '<th>לסוחר</th><th>לפרטי</th><th>לחברה</th><th>חציון חודשים בצי</th></tr></thead><tbody>'
                + "".join(drows) + '</tbody></table></div>'
                '<p class="cbs-note">רכב שבעלות חדשה עליו התחילה באותו חודש, אחרי תקופה בבעלות ליסינג. אלה הרכבים '
                'שנכנסים לשוק היד השנייה — היצע שמזיז את מחירי הרכב המשומש, ואיתם את ערך הצי בסוף התקופה.</p>'
                ) if drows else ""

    ai = ""
    lz_a = (a or {}).get("leasing") or {}
    if lz_a.get("summary") or lz_a.get("points"):
        refs = (a or {}).get("refs") or {}
        cards = []
        for m in lz_a.get("points") or []:
            badge = '<span class="au-data">נתוני רשם</span>' if m.get("data") else ""
            cards.append(f'<div class="cbs-card au-trend"><div class="cc-head"><h3>{_txt(m.get("title"))}</h3>'
                         f'{_dir(m.get("direction"))}</div>{_para(m.get("body"))}{_cos_html(m.get("companies"))}'
                         f'<div class="au-foot">{badge}{_sources_html(m.get("sources"), refs)}</div></div>')
        reg_m = (a or {}).get("registry_month")
        ai = ((f'<div class="au-lease-sum">{_para(lz_a.get("summary"))}'
               f'<p class="au-meta">ניתוח מ-{_stamp((a or {}).get("analyzed_at"))}'
               + (f", על נתוני הרשם עד {_mon(reg_m)}" if reg_m else "")
               + '. ניתוח השפעה, לא המלצת השקעה.</p></div>' if lz_a.get("summary") else "")
              + _EXP_AI
              + (f'<div class="cbs-cards">{"".join(cards)}</div>' if cards else ""))

    late = [k for k in full[-13:] if months[k].get("late")]
    method = ('<p class="cbs-note"><strong>מקור ושיטה.</strong> משרד התחבורה ב-data.gov.il: רשם כלי הרכב (בעלות, '
              'חודש עלייה לכביש, תוצר, דלק), מחירון היבואנים (יבואנית ומחיר מחירון לכל דגם ושנה), טבלת התוצרים (ארץ '
              'תוצר) והיסטוריית הבעלויות. רכב פרטי בלבד. <b>הבעלות ברשם היא הנוכחית</b>: רכב שנמכר מאז רישומו נספר '
              'לפי הבעלות החדשה, ולכן כל חודש נשמר כפי שחושב כשהיה קרוב לרישום'
              + (f'. חודשים שנכנסו למאגר באיחור ({_mrange(late[0], late[-1])}) חושבו כשחלק מהרכבים כבר נמכרו, '
                 'וחלק הליסינג בהם נמוך מבפועל' if late else "")
              + f'. עודכן {_stamp(reg.get("updated"))}.</p>')

    return ('<h2 id="au-lease">ליסינג והשכרה</h2>'
            '<p class="cbs-sub">שתי הזרימות שקובעות את כלכלת הצי — מה הציים קונים ומה הם מוכרים — מנתוני רשם כלי '
            'הרכב, ומה זה אומר לחברות: חברות הליסינג, היבואניות שמוכרות להן, האשראי לרכב והמבטחות.</p>'
            + exp["month"] + ai + strip + charts + importers + brand_tbl + disp_tbl + method)


def _item_html(r: dict, labels: dict, classes: dict | None = None) -> str:
    classes = THEME_CLASS if classes is None else classes
    d = _local(r.get("ts"))
    tags = "".join(f'<span class="au-tag {classes.get(t, "t-other")}">'
                   f'<i class="tdot" aria-hidden="true"></i>{escape(labels.get(t, t))}</span>'
                   for t in r.get("themes") or [])
    cos = "".join(f'<span class="co">{escape(c)}</span>' for c in r.get("companies") or [])
    return (f'<li class="au-item" data-t="{escape(" ".join(r.get("themes") or []))}">'
            f'<span class="au-time" dir="ltr">{f"{d:%H:%M}" if d else ""}</span>'
            f'<div class="au-body"><a class="au-title" href="{escape(r.get("url") or "#")}" target="_blank" '
            f'rel="noopener" dir="auto">{escape(r.get("title") or "")}</a>'
            f'<div class="au-tags"><span class="au-srcname">{escape(r.get("source") or "")}</span>{tags}{cos}</div>'
            '</div></li>')


def _column(rows: list[dict], labels: dict, title: str, classes: dict | None = None) -> str:
    def render(chunk: list[dict]) -> str:
        out, last = [], None
        for r in chunk:
            d = _local(r.get("ts"))
            day = d.date() if d else None
            if day != last:
                out.append(f'<li class="au-day">{WEEKDAYS[day.weekday()]} {day:%d/%m}</li>' if day else "")
                last = day
            out.append(_item_html(r, labels, classes))
        return "".join(out)

    shown, rest = rows[:SHOW_PER_COL], rows[SHOW_PER_COL:]
    more = (f'<details class="au-more"><summary>עוד {len(rest)} כותרות</summary>'
            f'<ul class="au-list">{render(rest)}</ul></details>') if rest else ""
    body = (f'<ul class="au-list">{render(shown)}</ul>{more}' if rows
            else '<p class="cbs-note">אין כותרות בתקופה.</p>')
    return f'<section class="au-col"><h3>{title} <span class="au-n">{len(rows)}</span></h3>{body}</section>'


def headlines_html(cfg: dict, items: list[dict], classes: dict | None = None, intro: str | None = None) -> str:
    """שתי עמודות, ישראל ועולם, עם סינון לפי נושא. classes/intro — לעמוד אחר (הסחורות)."""
    classes = THEME_CLASS if classes is None else classes
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
                       f'<i class="tdot {classes.get(slug, "t-other")}" aria-hidden="true"></i>'
                       f'{escape(label)} <span class="au-n">{counts[slug]}</span></button>'
                       for slug, label in labels.items() if counts.get(slug))
             + '</div>')
    sub = intro or (f'{len(items)} כותרות ב-{DAYS} הימים האחרונים, מאתרי רכב, כלכלה וסחר בישראל '
                    'ובעולם. כל כותרת מתויגת בנושאים שבה ובחברות הכיסוי שהיא מזכירה.')
    return ('<h2 id="au-news">כותרות</h2>'
            f'<p class="cbs-sub">{sub}</p>'
            + chips
            + f'<div class="au-cols">{_column(il, labels, "ישראל", classes)}{_column(world, labels, "עולם", classes)}</div>')


def previous_html(analyses: list[dict]) -> str:
    older = list(reversed(analyses[:-1]))[:PREV_SHOWN]
    if not older:
        return ""
    lis = "".join(f'<li><span class="rl-date" dir="ltr">{_stamp(a.get("analyzed_at"))}</span>'
                  f'<details><summary>{_txt(a.get("headline"))}</summary>'
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
                     "מחירים והשקות, מותגים סיניים, מיסוי ומימון — ומי מהחברות מושפע.")
    world = trends_html(a, "world", "מגמות בעולם", "au-world",
                        "מכסים, ייצור ושרשרת אספקה, סוללות ויצרנים סיניים — ואיך כל אחת מגיעה לחברות בישראל.")
    lease = leasing_html(data, a)
    toc = [("au-now", "תמונת מצב", True), ("au-lease", "ליסינג והשכרה", lease),
           ("au-il", "ישראל", il), ("au-world", "עולם", world),
           ("au-chain", "החברות בשרשרת", True), ("au-news", "כותרות", True)]
    return "\n".join(x for x in [
        '<div class="dash-head"><h1>ענף הרכב</h1>'
        f'<span class="stamp">{stamp}</span></div>',
        '<p class="lead">כותרות ומגמות מענף הרכב בישראל ובעולם, דרך החברות הנסחרות בשרשרת: '
        'יבואניות, רכיבים, ליסינג, אשראי, ביטוח ודלק — ולצידן נתוני רשם כלי הרכב על מה שציי הליסינג '
        'קונים ומוכרים. מתעדכן שלוש פעמים ביום.</p>',
        '<nav class="cbs-toc" aria-label="בעמוד הזה">'
        + "".join(f'<a href="#{i}">{l}</a>' for i, l, present in toc if present) + '</nav>',
        fail_html,
        now_html(a, state),
        lease,
        il,
        world,
        chain_html(cfg, items, a),
        headlines_html(cfg, items),
        previous_html(analyses),
        SCRIPT,
        # **הסקריפט של הייצוא אחרון, אחרי כל הכפתורים** — הוא קושר מאזינים למה שכבר ב-DOM.
        share.js(),
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
