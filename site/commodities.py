# -*- coding: utf-8 -*-
"""עמוד הסחורות: תמונת מצב, סעיף לכל קבוצה, אזורים, חוזים, דשנים, עסקאות, חברות ומחירים.

נבנה מ-output/commodities/ — המחירים, העקומים ונתוני הבנק העולמי מ-
ingest/commodities_pull.py, והסקירות מ-scripts/analyze_commodities.py. ההגדרות ב-
config/commodities.yaml.

**העמוד קורא גם בלי סקירה.** המחירים, העקומים, הפערים בין האזורים ומפת החשיפות
מחושבים מהנתונים עצמם; הסקירה מוסיפה את ה"למה" ואת החברות, ושורה אומרת כשהיא ישנה.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import yaml

import autonews as an

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "output" / "commodities"
CFG = ROOT / "config" / "commodities.yaml"

HISTORY_DAYS = 45       # תמונות יומיות לקו המגמה בטבלת המחירים
DAYS = 7
STALE_H = 36
SIDE_LABEL = {"producer": "יצרן", "consumer": "צרכן", "margin": "מרווח"}
# אותם גוונים כמו בשאר האתר; נושאים קרובים חולקים צבע.
THEME_CLASS = {"crude": "t-business", "gas": "t-prices", "refining": "t-industry", "electricity": "t-labor",
               "fertilizers": "t-housing", "bromine": "t-surveys", "metals": "t-accounts", "steel": "t-accounts",
               "polymers": "t-trade", "grains": "t-tourism", "softs": "t-tourism", "dairy": "t-other",
               "shipping": "t-trade", "deals": "t-surveys", "macro": "t-other"}
CURRENCY_REGION = {"CNY": "סין", "MYR": "מלזיה", "INR": "הודו", "EUR": "אירופה", "GBP": "בריטניה", "JPY": "יפן"}


def _jsonl(p: Path) -> list[dict]:
    return an._jsonl(p)


def load() -> dict:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}
    snaps = []
    for p in sorted((DATA / "prices").glob("*.json"))[-HISTORY_DAYS:]:
        try:
            snaps.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            continue
    try:
        wb = json.loads((DATA / "worldbank.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        wb = {}
    cut = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat(timespec="seconds")
    items = []
    for p in sorted((DATA / "items").glob("*.jsonl"), reverse=True)[:DAYS + 1]:
        items += [r for r in _jsonl(p) if (r.get("ts") or "") >= cut]
    items.sort(key=lambda r: r.get("ts") or "", reverse=True)
    analyses = []
    for p in sorted((DATA / "analyses").glob("*.jsonl"))[-2:]:
        analyses += _jsonl(p)
    analyses.sort(key=lambda a: a.get("analyzed_at") or "")
    try:
        state = json.loads((DATA / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    return {"cfg": cfg or {}, "snaps": snaps, "wb": wb, "items": items, "analyses": analyses, "state": state}


# --------------------------------------------------------------------------
# עזרים

def _num(v) -> str:
    if v is None:
        return "—"
    a = abs(v)
    return f"{v:,.0f}" if a >= 1000 else (f"{v:,.2f}" if a >= 10 else f"{v:,.3f}")


def _pct_cell(v) -> str:
    if v is None:
        return '<td class="trend flat" dir="ltr">—</td>'
    cls = "up" if v > 0.05 else ("down" if v < -0.05 else "flat")
    return f'<td class="trend {cls}" dir="ltr">{v:+.1f}%</td>'


def _region(ins: dict, row: dict) -> str:
    if ins.get("region"):
        return ins["region"]
    cur = str(row.get("unit") or "").upper()[:3]
    return CURRENCY_REGION.get(cur, "")


def _spark(vals: list[float]) -> str:
    pts = [v for v in vals if isinstance(v, (int, float))]
    if len(pts) < 5:
        return ""
    w, h = 70.0, 18.0
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    xy = [(i * w / (len(pts) - 1), h - 1.5 - (v - lo) / span * (h - 3)) for i, v in enumerate(pts)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    return (f'<svg class="cbs-spark cm-spark" viewBox="0 0 {w:.0f} {h:.0f}" aria-hidden="true">'
            f'<polyline class="ln" points="{path}"/><circle class="end" cx="{xy[-1][0]:.1f}" cy="{xy[-1][1]:.1f}" r="1.8"/></svg>')


def _group_label(cfg: dict) -> dict:
    return {g["key"]: g["label"] for g in cfg.get("groups") or []}


# --------------------------------------------------------------------------
# חלקי העמוד

def now_html(a: dict | None) -> str:
    if not a:
        return ('<h2 id="cm-now">תמונת מצב</h2><p class="cbs-note">הסקירה הראשונה תיכתב בריצה הקרובה של '
                'הצנרת. בינתיים — המחירים, העקומים והחשיפות למטה מחושבים מהנתונים עצמם.</p>')
    d = an._local(a.get("analyzed_at"))
    age_h = (datetime.now(an.IL) - d).total_seconds() / 3600 if d else None
    stale = ('<p class="msg warn">הסקירה נכתבה לפני יותר מ-36 שעות. המחירים למטה עדכניים יותר ממנה.</p>'
             if age_h and age_h > STALE_H else "")
    watch = [w for w in a.get("watch") or [] if isinstance(w, dict) and w.get("what")]
    watch_html = ('<div class="au-watch"><h3>מה לעקוב</h3><ul class="cbs-watch">'
                  + "".join(f'<li><span class="wn">{escape(an._t(w.get("when")) or "—")}</span>'
                            f'<span>{an._txt(w["what"])}</span></li>' for w in watch)
                  + '</ul></div>') if watch else ""
    return ('<h2 id="cm-now">תמונת מצב</h2>' + stale + '<div class="au-now">'
            f'<p class="au-headline">{an._txt(a.get("headline"))}</p>'
            f'<div class="au-overview">{an._para(a.get("overview"))}</div>'
            f'<p class="au-meta">סקירה מ-{an._stamp(a.get("analyzed_at"))}, על מחירים מ-{an._stamp(a.get("prices_at"))} '
            f'ו-{a.get("n_items", 0)} כותרות. ניתוח השפעה, לא המלצת השקעה.</p>' + watch_html + '</div>')


def sections_html(a: dict | None, cfg: dict) -> str:
    if not a or not a.get("sections"):
        return ""
    labels = _group_label(cfg)
    refs = a.get("refs") or {}
    cards = []
    for m in a["sections"]:
        badge = '<span class="au-data">נתוני מחירים</span>' if m.get("data") else ""
        cards.append(f'<div class="cbs-card au-trend"><div class="cm-kicker">{escape(labels.get(m.get("group"), ""))}</div>'
                     f'<div class="cc-head"><h3>{an._txt(m.get("title"))}</h3>{an._dir(m.get("direction"))}</div>'
                     f'{an._para(m.get("body"))}{an._cos_html(m.get("companies"))}'
                     f'<div class="au-foot">{badge}{an._sources_html(m.get("sources"), refs)}</div></div>')
    return ('<h2 id="cm-groups">מה זז, לפי קבוצה</h2>'
            '<p class="cbs-sub">מחיר ושינוי, מה החוזים הרחוקים אומרים, פערים בין אזורים, היצע וביקוש, והחברות '
            'שמושפעות — לכל קבוצה שבה יש תנועה.</p>'
            f'<div class="cbs-cards">{"".join(cards)}</div>')


def regional_html(cfg: dict, te: dict) -> str:
    ins = {i["symbol"]: i for i in cfg.get("instruments") or []}
    blocks = []
    for r in cfg.get("regional") or []:
        rows = []
        for sym in r.get("symbols") or []:
            row, i = te.get(sym), ins.get(sym) or {}
            if row and row.get("YearlyPercentualChange") is not None:
                rows.append((i.get("label") or row.get("Name"), _region(i, row), row))
        if len(rows) < 2:
            continue
        top = max(abs(x[2]["YearlyPercentualChange"]) for x in rows) or 1.0
        bars = []
        for label, region, row in rows:
            y = row["YearlyPercentualChange"]
            width = abs(y) / top * 50
            side = "pos" if y >= 0 else "neg"
            bars.append(f'<div class="cm-rbar"><span class="nm">{escape(label)}'
                        f'{f" · {escape(region)}" if region else ""}</span>'
                        f'<span class="val" dir="ltr">{_num(row.get("Last"))} {escape(str(row.get("unit") or ""))}</span>'
                        f'<span class="track" dir="ltr"><i class="{side}" style="width:{width:.1f}%"></i></span>'
                        f'<span class="chg {"up" if y > 0 else "down"}" dir="ltr">{y:+.0f}%</span></div>')
        blocks.append(f'<div class="cm-region"><h3>{escape(r["title"])}</h3>{"".join(bars)}</div>')
    if not blocks:
        return ""
    return ('<h2 id="cm-regions">אותה סחורה, אזורים שונים</h2>'
            '<p class="cbs-sub">השינוי בשנה האחרונה, זה לצד זה. הרמות ביחידות שונות ואינן ברות השוואה ישירה — '
            'השינוי כן, והפער ביניהם אומר לאן זורם הסחר ואיפה המחסור.</p>'
            f'<div class="cm-regions">{"".join(blocks)}</div>')


def _curve_svg(front: float, points: list[dict]) -> str:
    xs = [0] + [p["ahead"] for p in points]
    ys = [front] + [p["price"] for p in points]
    if len(xs) < 3:
        return ""
    w, h = 110.0, 30.0
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1.0
    top = max(xs) or 1

    def X(v):
        return 3 + v / top * (w - 6)

    def Y(v):
        return h - 4 - (v - lo) / span * (h - 8)

    path = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in zip(xs, ys))
    cls = "down" if ys[-1] < ys[0] else "up"
    return (f'<svg class="cm-curve {cls}" viewBox="0 0 {w:.0f} {h:.0f}" aria-hidden="true">'
            f'<polyline points="{path}"/>'
            + "".join(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="1.9"/>' for x, y in zip(xs, ys)) + '</svg>')


def curves_html(snap: dict, cfg: dict) -> str:
    cv = snap.get("curves") or {}
    if not cv:
        return ""
    horizons = cfg.get("curve_horizons") or [3, 6, 12, 24]
    rows = []
    for c in cv.values():
        f = (c.get("front") or {}).get("price")
        pts = {p["ahead"]: p for p in c.get("points") or []}
        cells = []
        for h in horizons:
            p = pts.get(h)
            if not p:
                cells.append('<td dir="ltr">—</td>')
                continue
            v = p.get("vs_front_pct")
            cls = "up" if (v or 0) > 0.05 else ("down" if (v or 0) < -0.05 else "flat")
            cells.append(f'<td dir="ltr" title="{escape(p.get("contract") or "")} · {escape(p.get("month") or "")}">'
                         f'{_num(p["price"])} <span class="trend {cls}">{f"{v:+.1f}%" if v is not None else ""}</span></td>')
        twelve = (pts.get(12) or {}).get("vs_front_pct")
        shape = ("בקוורדיישן" if twelve is not None and twelve < -2 else
                 "קונטנגו" if twelve is not None and twelve > 2 else "שטוח" if twelve is not None else "—")
        rows.append(f'<tr><td class="city">{escape(c["label"])}</td><td class="u">{escape(c.get("unit") or "")}</td>'
                    f'<td class="key" dir="ltr">{_num(f)}</td>{"".join(cells)}'
                    f'<td class="shape">{shape}</td><td>{_curve_svg(f, list(pts.values())) if f else ""}</td></tr>')
    head = "".join(f"<th>{h} ח׳</th>" for h in horizons)
    return ('<h2 id="cm-curves">ספוט מול חוזים</h2>'
            '<p class="cbs-sub">מחיר החוזה העתידי הקרוב מול חוזים לאספקה בעוד 3, 6, 12 ו-24 חודשים, ובסוגריים ההפרש '
            'מהקרוב. <b>בקוורדיישן</b> (חוזים רחוקים זולים מהקרוב) — השוק מתמחר מחסור עכשיו שיתמתן; '
            '<b>קונטנגו</b> (חוזים רחוקים יקרים) — יש היצע עכשיו, והמחיר העתידי כולל עלות אחסון ומימון.</p>'
            '<div class="tw"><table class="nadlan au-tbl cm-curves"><thead><tr><th>סחורה</th><th>יחידה</th>'
            f'<th>חוזה קרוב</th>{head}<th>מבנה (12 ח׳)</th><th>עקום</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>'
            f'<p class="cbs-note">מחירי סגירה אחרונים של חוזים עתידיים (yfinance), {an._stamp(snap.get("fetched_at"))}. '
            'חוזה רחוק שלא נסחר לאחרונה מוצג במחיר העסקה האחרונה שלו.</p>')


def fertilizers_html(wb: dict, cfg: dict) -> str:
    series = wb.get("series") or {}
    keys = [k for k in ((cfg.get("worldbank") or {}).get("chart") or []) if (series.get(k) or {}).get("points")]
    if not keys:
        return ""
    months = sorted({p["month"] for k in keys for p in series[k]["points"]})[-36:]
    vals = {k: {p["month"]: p["value"] for p in series[k]["points"]} for k in keys}
    W, H, L, R, T, B = 440.0, 190.0, 40.0, 8.0, 10.0, 22.0
    allv = [v for k in keys for m, v in vals[k].items() if m in months]
    hi = 100.0 * (int(max(allv) // 100) + 1)
    ticks = [hi * i / 4 for i in range(5)]
    pw, ph = W - L - R, H - T - B
    slot = pw / len(months)

    def X(i):
        return L + slot * (i + 0.5)

    def Y(v):
        return T + (hi - v) / hi * ph

    parts = []
    for t in ticks:
        parts.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L:.0f}" x2="{W - R:.0f}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>')
        parts.append(f'<text class="ax" x="{L - 6:.0f}" y="{Y(t) + 3.5:.1f}" text-anchor="end">{t:,.0f}</text>')
    for i, m in enumerate(months):
        if i and m.endswith("-01"):
            x = L + slot * i
            parts.append(f'<line class="yr" x1="{x:.1f}" x2="{x:.1f}" y1="{T:.0f}" y2="{T + ph:.0f}"/>')
            parts.append(f'<text class="ax" x="{x + 4:.1f}" y="{H - 7:.0f}">{m[:4]}</text>')
    for n, k in enumerate(keys):
        pts = [(X(i), Y(vals[k][m])) for i, m in enumerate(months) if m in vals[k]]
        if len(pts) >= 2:
            parts.append(f'<polyline class="l{n + 1}" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}"/>')
            parts.append(f'<circle class="l{n + 1}-end" cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3"/>')
    for i, m in enumerate(months):
        tip = " · ".join(f'{series[k]["label"]} {_num(vals[k].get(m))}' for k in keys)
        parts.append(f'<rect class="hit" x="{L + slot * i:.1f}" y="{T:.0f}" width="{slot:.1f}" height="{ph:.0f}">'
                     f'<title>{m[5:7]}/{m[:4]} · {tip}</title></rect>')
    chart = (f'<svg class="cbs-ch au-ch cm-fert" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
             f'aria-label="מחירי דשנים חודשיים">{"".join(parts)}</svg>')
    legend = "".join(f'<i class="sw l{n + 1}"></i>{escape(series[k]["label"])} ({escape(series[k].get("region") or "")})'
                     for n, k in enumerate(keys))
    rows = []
    for k in keys:
        s = series[k]
        pts = s["points"]
        last = pts[-1]
        ya = next((p for p in pts if p["month"] == f"{int(last['month'][:4]) - 1}-{last['month'][5:]}"), None)
        ma = pts[-2] if len(pts) >= 2 else None
        rows.append(f'<tr><td class="city">{escape(s["label"])}</td><td>{escape(s.get("region") or "")}</td>'
                    f'<td class="key" dir="ltr">{_num(last["value"])}</td><td dir="ltr">{last["month"][5:7]}/{last["month"][:4]}</td>'
                    + _pct_cell((last["value"] / ma["value"] - 1) * 100 if ma and ma["value"] else None)
                    + _pct_cell((last["value"] / ya["value"] - 1) * 100 if ya and ya["value"] else None)
                    + f'<td class="desc">{escape(s.get("desc") or "")[:140]}</td></tr>')
    return ('<h2 id="cm-fert">דשנים: מחירי ייחוס חודשיים</h2>'
            '<p class="cbs-sub">אשלג, פוספטים ואוריאה — המחירים שקובעים את הכנסות יצרני הדשנים ואת עלות התשומות '
            'בחקלאות. מקור: הבנק העולמי (Pink Sheet), ממוצע חודשי בדולר לטון, לפי ההגדרה הרשמית של כל סדרה.</p>'
            f'<div class="au-charts cm-one"><figure><figcaption>דולר לטון, {len(months)} חודשים</figcaption>{chart}'
            f'<p class="au-legend">{legend}</p></figure></div>'
            '<div class="tw"><table class="nadlan au-tbl cm-wb"><thead><tr><th>סדרה</th><th>אזור</th><th>מחיר</th>'
            '<th>חודש</th><th>מול חודש קודם</th><th>שנתי</th><th>הגדרה רשמית</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>'
            f'<p class="cbs-note">{escape((wb.get("updated") or "").replace("Updated on", "עודכן בבנק העולמי:"))}. '
            'ברום אינו מתפרסם במקורות האלה; מה שנכתב עליו בעמוד נשען על כותרות בלבד.</p>')


def deals_html(a: dict | None) -> str:
    deals = (a or {}).get("deals") or []
    if not deals:
        return ""
    refs = (a or {}).get("refs") or {}
    cards = "".join(f'<div class="cbs-card au-trend"><div class="cc-head"><h3>{an._txt(d.get("title"))}</h3></div>'
                    f'{an._para(d.get("body"))}{an._cos_html(d.get("companies"))}'
                    f'<div class="au-foot">{an._sources_html(d.get("sources"), refs)}</div></div>' for d in deals)
    return ('<h2 id="cm-deals">עסקאות וחוזים</h2>'
            '<p class="cbs-sub">הסכמי אספקה, חוזים ועסקאות שנחתמו או הוכרזו לפי הכותרות — מי, מה ולמה זה חשוב לשוק.</p>'
            f'<div class="cbs-cards">{cards}</div>')


def _signed(v: float) -> str:
    """"+19%" בתוך משפט עברי — בבידוד, אחרת הסימן נודד לסוף ("19%+")."""
    return '<bdi dir="ltr">0%</bdi>' if abs(v) < 0.5 else f'<bdi dir="ltr">{v:+.0f}%</bdi>'


def _signal(key: str, te: dict, wb: dict, ins: dict) -> str:
    s = (wb.get("series") or {}).get(key)
    if s and s.get("points"):
        last = s["points"][-1]
        pts = s["points"]
        ya = next((p for p in pts if p["month"] == f"{int(last['month'][:4]) - 1}-{last['month'][5:]}"), None)
        yoy = f" · שנתי {_signed((last['value'] / ya['value'] - 1) * 100)}" if ya and ya["value"] else ""
        return (f'<span class="cm-sig"><b>{escape(s["label"])}</b> {escape(s.get("region") or "")} '
                f'<bdi dir="ltr">{_num(last["value"])}</bdi> ({last["month"][5:7]}/{last["month"][2:4]}{yoy})</span>')
    row = te.get(key)
    if not row or row.get("Last") is None:
        return ""
    i = ins.get(key) or {}
    y, m = row.get("YearlyPercentualChange"), row.get("MonthlyPercentualChange")
    ch = " · ".join(x for x in (f"חודש {_signed(m)}" if m is not None else "",
                                f"שנה {_signed(y)}" if y is not None else "") if x)
    region = _region(i, row)
    label = escape(i.get("label") or row.get("Name") or key) + (f" · {escape(region)}" if region else "")
    return (f'<span class="cm-sig"><b>{label}</b> '
            f'<bdi dir="ltr">{_num(row["Last"])}</bdi>{f" ({ch})" if ch else ""}</span>')


def companies_html(cfg: dict, te: dict, wb: dict, a: dict | None) -> str:
    ins = {i["symbol"]: i for i in cfg.get("instruments") or []}
    notes = {c["name"]: c for c in (a or {}).get("companies") or [] if isinstance(c, dict)}
    refs = (a or {}).get("refs") or {}
    note_cards = []
    for name, c in notes.items():
        note_cards.append(f'<li><div class="au-co"><b>{escape(name)}</b>{an._dir(c.get("direction"))}</div>'
                          f'<div class="au-note">{an._txt(c.get("note"))}{an._sources_html(c.get("sources"), refs)}</div></li>')
    blocks = []
    for e in cfg.get("exposures") or []:
        sig = " ".join(x for x in (_signal(k, te, wb, ins) for k in e.get("commodities") or []) if x)
        groups = "".join(
            f'<div class="cm-side"><span class="cm-sidelbl {escape(g.get("side") or "")}">{SIDE_LABEL.get(g.get("side"), "")}</span>'
            f'<span class="why">{escape(g.get("why") or "")}</span>'
            f'<div class="cc-cos">{"".join(f"<span class=co>{escape(n)}</span>" for n in g.get("companies") or [])}</div></div>'
            for g in e.get("groups") or [])
        blocks.append(f'<div class="au-role cm-exp"><h3>{escape(e["label"])}</h3>'
                      f'<div class="cm-sigs">{sig}</div>{groups}</div>')
    top = (f'<div class="au-role cm-notes"><h3>השבוע, לפי הסקירה</h3><ul>{"".join(note_cards)}</ul></div>'
           if note_cards else "")
    return ('<h2 id="cm-cos">החברות והחשיפות</h2>'
            '<p class="cbs-sub">החברות הנסחרות בתל אביב לפי הסחורה שמזיזה אותן, והצד שלהן: יצרן מרוויח ממחיר גבוה, '
            'צרכן משלם אותו, ובית זיקוק או משלח תלויים במרווח ולא במחיר. לצד כל קבוצה — המחירים הרלוונטיים עכשיו.</p>'
            + top + f'<div class="au-chain cm-exps">{"".join(blocks)}</div>')


def board_html(cfg: dict, snaps: list[dict]) -> str:
    if not snaps:
        return ""
    te = snaps[-1].get("te") or {}
    labels = _group_label(cfg)
    hist: dict[str, list] = {}
    for s in snaps:
        for sym, row in (s.get("te") or {}).items():
            hist.setdefault(sym, []).append(row.get("Last"))
    out = []
    for g in cfg.get("groups") or []:
        rows = []
        for i in cfg.get("instruments") or []:
            if i["group"] != g["key"]:
                continue
            row = te.get(i["symbol"])
            if not row or row.get("Last") is None:
                continue
            asof = str(row.get("Date") or "")[:10]
            rows.append(f'<tr><td class="city">{escape(i["label"])}</td><td>{escape(_region(i, row))}</td>'
                        f'<td class="key" dir="ltr">{_num(row["Last"])}</td><td class="u" dir="ltr">{escape(str(row.get("unit") or ""))}</td>'
                        + _pct_cell(row.get("DailyPercentualChange")) + _pct_cell(row.get("MonthlyPercentualChange"))
                        + _pct_cell(row.get("YearlyPercentualChange"))
                        + f'<td>{_spark(hist.get(i["symbol"]) or [])}</td>'
                        f'<td class="d" dir="ltr">{asof[8:10]}/{asof[5:7]}</td></tr>')
        if rows:
            out.append(f'<details class="cm-board" open><summary>{escape(labels.get(g["key"], g["key"]))} '
                       f'<span class="au-n">{len(rows)}</span></summary>'
                       '<div class="tw"><table class="nadlan au-tbl"><thead><tr><th>סחורה</th><th>אזור</th><th>מחיר</th>'
                       '<th>יחידה</th><th>יום</th><th>חודש</th><th>שנה</th><th>מגמה</th><th>עדכון</th></tr></thead><tbody>'
                       + "".join(rows) + '</tbody></table></div></details>')
    return ('<h2 id="cm-board">כל המחירים</h2>'
            f'<p class="cbs-sub">מקור: Trading Economics, {an._stamp(snaps[-1].get("fetched_at"))}. אזור מוצג כשהוא ידוע, '
            'או לפי מטבע המחיר (יואן — סין). "מגמה" — המחיר בימים שנאספו כאן, מתמלא ככל שהאיסוף מתקדם.</p>'
            + "".join(out))


def page(data: dict) -> str:
    cfg = data.get("cfg") or {}
    snaps = data.get("snaps") or []
    wb = data.get("wb") or {}
    items = data.get("items") or []
    analyses = data.get("analyses") or []
    state = data.get("state") or {}
    a = analyses[-1] if analyses else None
    if not snaps and not items:
        return '<h1>סחורות</h1><p class="lead">טרם נאספו נתונים. הם ייאספו בריצה הקרובה של צנרת הסחורות.</p>'
    snap = snaps[-1] if snaps else {}
    te = snap.get("te") or {}
    stamp = " · ".join(x for x in (f'מחירים {an._stamp(snap.get("fetched_at"))}' if snap else "",
                                   f'סקירה {an._stamp(a.get("analyzed_at"))}' if a else "") if x)
    fails = state.get("failures") or []
    fail_html = (f'<p class="msg warn">בריצה האחרונה חלק מהמקורות לא נקראו: {escape(" · ".join(fails[:3]))}.</p>'
                 if any(not f.startswith("Google News") for f in fails) else "")
    parts = [
        ("cm-now", "תמונת מצב", now_html(a)),
        ("cm-groups", "לפי קבוצה", sections_html(a, cfg)),
        ("cm-regions", "אזורים", regional_html(cfg, te)),
        ("cm-curves", "ספוט מול חוזים", curves_html(snap, cfg)),
        ("cm-fert", "דשנים", fertilizers_html(wb, cfg)),
        ("cm-deals", "עסקאות", deals_html(a)),
        ("cm-cos", "חברות", companies_html(cfg, te, wb, a)),
        ("cm-board", "כל המחירים", board_html(cfg, snaps)),
        ("au-news", "כותרות", an.headlines_html(
            cfg, items, THEME_CLASS,
            f'{len(items)} כותרות ב-{DAYS} הימים האחרונים: היצע וביקוש, מאקרו ועסקאות, מאתרי אנרגיה, מתכות, '
            'חקלאות וספנות ומהעיתונות הכלכלית בישראל. כל כותרת מתויגת בנושאים ובחברות שהיא מזכירה.') if items else ""),
    ]
    toc = "".join(f'<a href="#{i}">{l}</a>' for i, l, html in parts if html)
    return "\n".join(x for x in [
        f'<div class="dash-head"><h1>סחורות</h1><span class="stamp">{stamp}</span></div>',
        '<p class="lead">מחירי ספוט וחוזים עתידיים, פערים בין אזורים, היצע וביקוש, מאקרו ועסקאות שנחתמו — '
        'דרך החברות הנסחרות שתלויות בהם: איי.סי.אל, יצרניות הגז ובתי הזיקוק, יצרניות הפלסטיק, המזון והבנייה. '
        'מתעדכן פעמיים ביום.</p>',
        f'<nav class="cbs-toc" aria-label="בעמוד הזה">{toc}</nav>',
        fail_html,
        *[html for _, _, html in parts],
        an.previous_html(analyses),
        an.SCRIPT if items else "",
    ] if x)


def report(data: dict) -> list[str]:
    snaps = data.get("snaps") or []
    analyses = data.get("analyses") or []
    if not snaps:
        return ['::warning title=אין נתוני סחורות::output/commodities ריק — העמוד נבנה בלי מחירים.']
    snap = snaps[-1]
    a = analyses[-1] if analyses else None
    out = [f'::notice::עמוד הסחורות: {len(snap.get("te") or {})} מחירים ({snap.get("date")}), '
           f'{len(snap.get("curves") or {})} עקומים, {len(data.get("items") or [])} כותרות ב-{DAYS} ימים · '
           f'סקירה אחרונה {(a or {}).get("analyzed_at") or "—"}']
    fetched = an._local(snap.get("fetched_at"))
    if fetched and datetime.now(an.IL) - fetched > timedelta(hours=40):
        out.append(f'::warning title=מחירי הסחורות ישנים::המשיכה האחרונה מ-{snap.get("fetched_at")} — '
                   'צנרת commodities-watch לא רצה או נכשלה.')
    return out
