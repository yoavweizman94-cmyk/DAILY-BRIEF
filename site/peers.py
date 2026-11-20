# -*- coding: utf-8 -*-
"""עמוד המתחרים והמגמות (peers.html) — לבעלים בלבד.

לכל אחזקה תעשייתית של הקרן: המתחרים והלקוחות המהותיים (מ-output/peers/peers.json, עם
מקור השיוך — הדוח התקופתי של החברה או הצעה), כרטיסי התובנה מ-scripts/analyze_peers.py,
והידיעות המהותיות של היומיים האחרונים עם קישור למקור. מתחתם — הסקירה האחרונה של כל דוח
(output/peers/reviews, מהודעות התוצאות ב-SEC) ושל כל שיחת ועידה (output/peers/calls) של
המתחרים, הלקוחות והספקים.

**לבעלים בלבד** (site/functions/_middleware.js, OWNER_ONLY): העמוד חושף את אחזקות הקרן.
הקישור בניווט נושא data-owner, כמו "השיחות שלי".
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PEERS = ROOT / "output" / "peers"
DAYS = 7
# סקירת דוח או שיחה נשארת בעמוד עד הדוח הבא של אותה חברה — רבעון ומעט
REVIEW_DAYS = 100
DIR_CLS = {"חיובי": "up", "שלילי": "down", "מעורב": "mixed"}
KIND_LBL = {"report": "סקירת דוח", "call": "שיחת ועידה"}


def _json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _jsonl(p: Path) -> list[dict]:
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def load() -> dict:
    now = datetime.now(timezone.utc)
    cards = [c for f in sorted((PEERS / "insights").glob("*.jsonl"))[-DAYS:] for c in _jsonl(f)]
    # סקירות דוחות (scripts/analyze_peers.py, מ-SEC) ושיחות ועידה (output/peers/calls): האחרונה
    # לכל אחזקה, חברה וסוג — דוח של רבעון קודם מוחלף בחדש
    latest: dict[tuple, dict] = {}
    for sub in ("reviews", "calls"):
        for f in sorted((PEERS / sub).glob("*.jsonl"))[-REVIEW_DAYS:]:
            for c in _jsonl(f):
                k = (c.get("holding"), c.get("company"), c.get("kind"))
                if (c.get("at") or "") >= (latest.get(k, {}).get("at") or ""):
                    latest[k] = c
    reviews = sorted(latest.values(), key=lambda c: c.get("at") or "", reverse=True)
    news = {r["id"]: r for f in sorted((PEERS / "news").glob("*.jsonl"))[-3:] for r in _jsonl(f) if "id" in r}
    state = _json(PEERS / "state.json", {})
    tri = state.get("triage") or {}
    recent = []
    for i, t in tri.items():
        r = news.get(i)
        if not r or not t.get("keep") or t.get("sig", 0) < 2:
            continue
        try:
            if now - datetime.fromisoformat(r["ts"]) > timedelta(hours=48):
                continue
        except (KeyError, ValueError):
            continue
        recent.append({**r, "why": t.get("why", ""), "sig": t.get("sig", 0), "holdings": t.get("holdings") or []})
    try:
        import yaml
        cos = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8")).get("companies") or []
        sectors = {c.get("name_he"): c.get("tase_sector") or "" for c in cos}
    except (OSError, ImportError, AttributeError):
        sectors = {}
    return {"holdings": _json(PEERS / "holdings.json", {}), "peers": _json(PEERS / "peers.json", {}),
            "cards": cards, "reviews": reviews, "recent": recent, "last_run": state.get("last_run") or "",
            "sectors": sectors}


def _when(ts: str) -> str:
    try:
        d = datetime.fromisoformat(ts).astimezone()
    except (TypeError, ValueError):
        return ""
    return d.strftime("%d/%m %H:%M")


def _day(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso) >= 10 else iso


def _src_link(s: dict) -> str:
    name = escape(s.get("source") or "מקור")
    when = _when(s.get("ts") or "")
    if s.get("url"):
        return (f'<a href="{escape(s["url"])}" target="_blank" rel="noopener">{name}</a>'
                + (f' <span class="t">{when}</span>' if when else ""))
    return name


def _chips(rows: list[dict], label: str) -> str:
    if not rows:
        return ""
    out = []
    for p in rows:
        src = p.get("src") or ""
        cls = "peer-chip prop" if src.startswith("הצעה") else "peer-chip"
        tip = escape(src + (f" · {p['ticker']}" if p.get("ticker") else ""))
        out.append(f'<span class="{cls}" title="{tip}">{escape(p["name"])}</span>')
    return f'<p class="peer-chips"><b>{label}:</b> {"".join(out)}</p>'


LABEL = re.compile(r"^\s*(?:(?:בענף|באחזקה|משמעות|פרשנות|תחזית)\s*:\s*)+")


def _f(c: dict, k: str) -> str:
    """שדה בלי תווית בראשו: העמוד מוסיף "בענף:"/"באחזקה:"/"משמעות:" בעצמו, וכרטיסים
    מהריצה הראשונה (19/11/2026) כתבו אותן גם בתוך השדה — "בענף: בענף:".
    שורה חדשה בשדה (סקירות השיחות נכתבות בשורות ותבליטים) נשמרת כשבירת שורה."""
    return escape(LABEL.sub("", c.get(k) or "")).replace("\n", "<br>")


def _card(c: dict) -> str:
    cls = DIR_CLS.get(c.get("direction") or "", "flat")
    srcs = " · ".join(_src_link(s) for s in c.get("sources") or [])
    basis = '<span class="tr-approx">לפי כותרות</span>' if c.get("basis") == "כותרת" else ""
    return ('<div class="topic-item">'
            f'<h3>{escape(c.get("title") or "")}</h3>'
            f'<p>{_f(c, "fact")}</p>'
            f'<p><b>בענף:</b> {_f(c, "sector")}</p>'
            f'<p><b>באחזקה:</b> {_f(c, "impact")}</p>'
            f'<p class="takeaway"><b>משמעות:</b> {_f(c, "meaning")}</p>'
            f'<p class="topic-meta"><span class="dir {cls}">{escape(c.get("direction") or "")}</span>'
            f'{basis}<span class="co">{srcs}</span>'
            f'<span class="t">{_when(c.get("at") or "")}</span></p></div>')


def _review(c: dict) -> str:
    """סקירת דוח או שיחת ועידה של מתחר: התווית אומרת של מי ואיזו תקופה, ויש בה שורת תחזית."""
    cls = DIR_CLS.get(c.get("direction") or "", "flat")
    srcs = " · ".join(_src_link(s) for s in c.get("sources") or [])
    lbl = " · ".join(escape(x) for x in (KIND_LBL.get(c.get("kind") or "", "סקירה"), c.get("company") or "",
                                         c.get("period") or "") if x)
    return ('<div class="topic-item peer-review">'
            f'<p class="peer-kind">{lbl}</p>'
            f'<h3>{escape(c.get("title") or "")}</h3>'
            f'<p>{_f(c, "fact")}</p>'
            + (f'<p><b>תחזית:</b> {_f(c, "outlook")}</p>' if c.get("outlook") else "")
            + f'<p><b>בענף:</b> {_f(c, "sector")}</p>'
            f'<p><b>באחזקה:</b> {_f(c, "impact")}</p>'
            f'<p class="takeaway"><b>משמעות:</b> {_f(c, "meaning")}</p>'
            f'<p class="topic-meta"><span class="dir {cls}">{escape(c.get("direction") or "")}</span>'
            f'<span class="co">{srcs}</span>'
            f'<span class="t">{_when(c.get("at") or "")}</span></p></div>')


def index(d: dict) -> str:
    hold = d["holdings"] or {}
    peers = (d["peers"] or {}).get("holdings") or {}
    rep = hold.get("report") or {}
    fund = (hold.get("fund") or {}).get("name") or "הקרן"
    rows = [h for h in hold.get("holdings") or [] if h.get("name") in peers]
    # **חברות במעקב שאינן בדוח האחזקות** (לבקשת הבעלים, 19/11/2026): במפת המתחרים, אבל לא
    # בקרן לפי הדוח האחרון. אחרי האחזקות, בלי משקל.
    held = {h["name"] for h in rows}
    sectors = d.get("sectors") or {}
    rows += [{"name": n, "weight": None, "tase_sector": sectors.get(n, ""), "extra": True}
             for n in peers if n not in held]
    unmapped = [h["name"] for h in hold.get("holdings") or []
                if h.get("industrial") and h.get("name") and h["name"] not in peers]
    head = ('<div class="dash-head"><h1>מתחרים ומגמות</h1></div>'
            f'<p class="stamp">מה קורה אצל המתחרים, הלקוחות והספקים המהותיים והענפים של האחזקות התעשייתיות '
            f'של {escape(fund)} ושל חברות נוספות במעקב — ומה זה אומר על כל חברה. האחזקות לפי {escape(rep.get("title") or "דוח האחזקות")}'
            f'{" שפורסם ב-" + _day(rep["published"]) if rep.get("published") else ""}, ולכן אינן משקפות שינויים מאז. '
            'העמוד גלוי רק לך.</p>')
    if not rows:
        return head + '<p class="stamp">אין עדיין אחזקות עם מפת מתחרים.</p>'

    by_h: dict[str, list[dict]] = {}
    for c in sorted(d["cards"], key=lambda c: c.get("at") or "", reverse=True):
        by_h.setdefault(c.get("holding") or "", []).append(c)
    rec_h: dict[str, list[dict]] = {}
    for r in sorted(sorted(d["recent"], key=lambda r: r["ts"], reverse=True), key=lambda r: -r["sig"]):
        for h in r["holdings"]:
            rec_h.setdefault(h, []).append(r)
    rev_h: dict[str, list[dict]] = {}
    for c in d.get("reviews") or []:
        rev_h.setdefault(c.get("holding") or "", []).append(c)
    n_rev = sum(len(v) for k, v in rev_h.items() if k in peers)
    weight = sum(h.get("weight") or 0 for h in rows)
    n_extra = sum(1 for h in rows if h.get("extra"))
    tiles = ('<div class="strip">'
             f'<div class="tile"><div class="lbl">חברות במעקב</div><div class="val">{len(rows)}</div>'
             + (f'<div class="chg">{len(rows) - n_extra} בקרן · {n_extra} מחוצה לה</div>' if n_extra else "")
             + '</div>'
             f'<div class="tile"><div class="lbl">משקל בקרן</div><div class="val">{weight:.1f}%</div></div>'
             f'<div class="tile"><div class="lbl">תובנות ב-{DAYS} ימים</div><div class="val">{len(d["cards"])}</div></div>'
             f'<div class="tile"><div class="lbl">דוחות ושיחות של מתחרים</div><div class="val">{n_rev}</div>'
             '<div class="chg">האחרון לכל חברה</div></div>'
             f'<div class="tile"><div class="lbl">ידיעות מהותיות</div><div class="val">{len(d["recent"])}</div>'
             '<div class="chg">ב-48 שעות</div></div></div>')
    opts = "".join(f'<option value="{escape(h["name"])}">{escape(h["name"])}</option>' for h in rows)
    controls = ('<div class="tr-filters"><select id="ph" aria-label="אחזקה">'
                f'<option value="">כל האחזקות</option>{opts}</select></div>')

    sec = []
    for h in rows:
        name = h["name"]
        cfg = peers.get(name) or {}
        cards = by_h.get(name) or []
        rec = [r for r in rec_h.get(name) or [] if r["id"] not in {s["id"] for c in cards for s in c.get("sources") or []}]
        body = "".join(_card(c) for c in cards) or '<p class="stamp">אין תובנות בשבוע האחרון.</p>'
        more = ""
        if rec:
            items = "".join(
                f'<li><a href="{escape(r["url"])}" target="_blank" rel="noopener">{escape(r["title"])}</a> '
                f'<span class="src">{escape(r.get("source") or "")} · {_when(r["ts"])}</span>'
                f'<br><span class="stamp">{escape(r.get("why") or "")}</span></li>' for r in rec[:12])
            more = f'<details class="peer-more"><summary>עוד {len(rec)} ידיעות מהותיות ב-48 שעות</summary><ul>{items}</ul></details>'
        revs = rev_h.get(name) or []
        rblock = ('<div class="peer-reviews"><h4>דוחות ושיחות ועידה של המתחרים, הלקוחות והספקים</h4>'
                  + "".join(_review(c) for c in revs) + '</div>') if revs else ""
        where = ("במעקב — לא בדוח האחזקות של הקרן" if h.get("extra")
                 else f'{h.get("weight") or 0:.2f}% מהקרן')
        sector = f' · {escape(h["tase_sector"])}' if h.get("tase_sector") else ""
        sec.append(
            f'<section class="topic-sum peer-h" data-h="{escape(name)}">'
            f'<div class="topic-sum-head">{escape(name)}'
            f'<span class="stamp">{where}{sector}</span></div>'
            + _chips(cfg.get("competitors") or [], "מתחרים")
            + _chips(cfg.get("customers") or [], "לקוחות מהותיים")
            + _chips(cfg.get("suppliers") or [], "ספקים מהותיים")
            + body + more + rblock + '</section>')

    foot = ('<p class="stamp">מקור השיוך של כל מתחר מופיע במעבר עכבר: "דוח" — החברה נוקבת בשמו בדוח התקופתי '
            '2025 שלה (או בדוח השנתי שהגישה ל-SEC); "דוח X" — החברה X נוקבת באחזקה כמתחרה שלה; '
            '"הצעה" (מסומן במסגרת מקווקוות) — אין מקור שנוקב בשמות. '
            'הידיעות מ-Google News ומפידי האתר; כרטיס שנשען על כותרות בלבד מסומן כך. '
            'סקירות הדוחות נכתבות מהודעות התוצאות שהחברות הגישו ל-SEC; סקירות השיחות — מתמלילים '
            'בחשבון Koyfin שלך, לעיונך בלבד.'
            + (f' עדכון אחרון: {_when(d["last_run"])}.' if d.get("last_run") else "") + '</p>')
    if unmapped:
        foot += ('<p class="stamp">אחזקות תעשייתיות בדוח בלי מפת מתחרים: '
                 + ", ".join(escape(n) for n in unmapped) + '.</p>')
    js = """
<script>
(function () {
  var s = document.getElementById('ph'),
      all = Array.prototype.slice.call(document.querySelectorAll('.peer-h'));
  s.addEventListener('change', function () {
    all.forEach(function (d) { d.hidden = !(!s.value || d.dataset.h === s.value); });
  });
})();
</script>"""
    return head + tiles + controls + "".join(sec) + foot + js
