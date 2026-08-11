# -*- coding: utf-8 -*-
"""גנרטור סטטי: output/brief_*.md → site/dist/ (RTL, נפרס ל-GitHub Pages).

- index.html   — דשבורד: מצב מקורות, רצועת שווקים, לוח אירועים, הברייף המלא, ארכיון
- briefs/<date>.html — עמוד לכל ברייף
- archive.html — רשימת כל הברייפים
שימוש: python site/build.py
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "dist"
STYLE = Path(__file__).parent / "style.css"

# בלי smarty: הוא ממיר גרשיים אנגליים טיפוגרפיים ומשבש עברית —
# ש"ח הפך ל-ש&rdquo;ח וג'י סיטי ל-ג&rsquo;י סיטי.
MD_EXT = ["tables", "sane_lists"]

# מספר עם סימן מפורש בהקשר RTL: אלגוריתם ה-bidi מציב את הסימן מימין למספר,
# כך ש-"-7.11%" נקרא על המסך "7.11%-". בטבלת שווקים זו טעות קריאה של ממש,
# ולכן כל מספר חתום בתא טבלה נעטף ב-span עם כיוון LTR מפורש.
_CELL = re.compile(r"<(td|th)([^>]*)>(.*?)</\1>", re.S)
_SIGNED_NUM = re.compile(r"([+\-−])(\d[\d,.]*\s*%?)")

PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<link rel="stylesheet" href="{root}style.css">
</head>
<body>
<header>
  <nav><a href="{root}index.html">סקירה</a> · <a href="{root}reports.html">דיווחים וסיכומי דוחות</a> · <a href="{root}archive.html">ארכיון</a></nav>
  <div class="brand">{site_title}</div>
</header>
<main>
{body}
</main>
<footer>נוצר אוטומטית · לשימוש פנימי · אין לראות באמור המלצת השקעה</footer>
</body>
</html>
"""


def _isolate_signed_numbers(html_text: str) -> str:
    def fix(m):
        tag, attrs, inner = m.groups()
        inner = _SIGNED_NUM.sub(
            lambda x: f'<span dir="ltr">{x.group(1)}{x.group(2)}</span>', inner)
        return f"<{tag}{attrs}>{inner}</{tag}>"
    return _CELL.sub(fix, html_text)


def render(md_text: str) -> str:
    return _isolate_signed_numbers(markdown.markdown(md_text, extensions=MD_EXT))


def brief_title(md_text: str, fallback: str) -> str:
    first = md_text.strip().splitlines()[0] if md_text.strip() else ""
    return first.lstrip("# ").strip() or fallback


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------------------
# מקטעי הדשבורד
# --------------------------------------------------------------------------

def sources_panel(raw_dir: Path) -> str:
    """מצב חמשת המקורות — מה נטען היום ומה לא, בלי לפתוח לוגים."""
    checks = [("RSS", "rss.jsonl"), ("Feedly", "feedly.jsonl"), ("Gmail", "gmail.jsonl"), ("מאיה", "maya.jsonl"),
              ("שווקים", "markets.json"), ('רמ"י', "rmi.json"),
              ("Trading Economics", "te.json")]
    cells = []
    for label, fname in checks:
        p = raw_dir / fname
        if not p.exists() or p.stat().st_size == 0:
            cells.append(f'<li class="bad"><span>✗</span>{label}</li>')
            continue
        if fname.endswith(".jsonl"):
            n = sum(1 for _ in p.open(encoding="utf-8"))
            detail = f"{n} פריטים"
        else:
            d = load_json(p) or {}
            n = len(d.get("instruments", d.get("results", d.get("calendar", []))))
            detail = f"{n} רשומות" if n else "נטען"
        cells.append(f'<li class="ok"><span>✓</span>{label}<em>{detail}</em></li>')
    return f'<ul class="sources">{"".join(cells)}</ul>'


def fmt_value(v, is_yield: bool) -> str:
    """עיצוב לפי סדר גודל — אחרת מופיע 4,164.8701 לצד 84.7 באותה רצועה."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if is_yield:
        return f"{x:.3f}%"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if abs(x) >= 10:
        return f"{x:,.2f}"
    return f"{x:,.4f}"


def markets_strip(markets: dict | None, te: dict | None = None) -> str:
    """רצועת מספרים קומפקטית — הדבר הראשון שרואים."""
    if not markets:
        return ""
    tiles = []
    # תשואת הממשלתי הישראלי מגיעה מ-TE ולא מ-markets.json, אבל מקומה כאן
    # בראש הרצועה — היא עוגן התמחור של כל סקטור הנדל"ן בכיסוי.
    il = (te or {}).get("il_gov_10y")
    if il and il.get("yield") is not None:
        ch = il.get("daily")
        cls = "flat" if not ch else ("up" if ch > 0 else "down")
        sign = "+" if (ch or 0) > 0 else ""
        tiles.append(
            f'<div class="tile {cls}"><span class="lbl">ממשלתי ישראלי 10ש</span>'
            f'<span class="val" dir="ltr">{il["yield"]:.3f}%</span>'
            f'<span class="chg" dir="ltr">{"—" if ch is None else f"{sign}{ch}"}</span></div>')
    order = ["fx_usd_ils", "fx_eur_ils", "brent", "us10y", "ta125", "ta35",
             "sp500", "nasdaq", "steel_hrc", "aluminum", "cocoa", "dry_bulk"]
    pool = {**markets.get("fx", {}), **markets.get("instruments", {})}
    for key in order:
        v = pool.get(key)
        if not v:
            continue
        ch = (v.get("changes") or {}).get("daily")
        unit = v.get("change_unit", "%")
        cls = "flat" if ch in (None, 0) else ("up" if ch > 0 else "down")
        sign = "" if ch is None else ("+" if ch > 0 else "")
        chtxt = "—" if ch is None else f"{sign}{ch}{'' if unit == 'pp' else '%'}"
        stale = "" if not v.get("stale_days") else f'<b title="נתון לא עדכני">{v["asof"][5:]}</b>'
        tiles.append(
            f'<div class="tile {cls}"><span class="lbl">{v["label"]}{stale}</span>'
            f'<span class="val" dir="ltr">{fmt_value(v["value"], unit == "pp")}</span>'
            f'<span class="chg" dir="ltr">{chtxt}</span></div>')
    return f'<section class="strip">{"".join(tiles)}</section>' if tiles else ""


def indicators_panel(te: dict | None) -> str:
    """אינדיקטורי מאקרו לישראל מ-Trading Economics, עם כיוון מול הקריאה הקודמת."""
    if not te or not te.get("indicators"):
        return ""
    rows = []
    for i in te["indicators"]:
        val, prev = i.get("value"), i.get("previous")
        arrow = ""
        if isinstance(val, (int, float)) and isinstance(prev, (int, float)):
            arrow = ('<span class="up">▲</span>' if val > prev
                     else '<span class="down">▼</span>' if val < prev else "—")
        rows.append(
            f"<tr><td>{i.get('category','')}</td>"
            f"<td dir='ltr'>{val} {i.get('unit','') or ''}</td>"
            f"<td class='imp'>{arrow}</td>"
            f"<td dir='ltr'>{prev if prev is not None else '—'}</td>"
            f"<td>{str(i.get('date') or '')[:10]}</td></tr>")
    return ('<h2>מאקרו ישראל — אינדיקטורים</h2><table class="cal"><thead><tr>'
            '<th>מדד</th><th>ערך</th><th>כיוון</th><th>קודם</th><th>לתאריך</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def calendar_panel(te: dict | None) -> str:
    """לוח האירועים הקרובים — מ-Trading Economics, אם קיים."""
    if not te or not te.get("calendar"):
        return ""
    rows = []
    for e in sorted(te["calendar"], key=lambda x: x.get("date") or "")[:14]:
        imp = int(e.get("importance") or 0)
        dots = "●" * imp + "○" * (3 - imp)
        when = (e.get("date") or "")[:16].replace("T", " ")
        vals = " · ".join(
            f"{k}: {v}" for k, v in (("צפי", e.get("forecast")), ("קודם", e.get("previous")))
            if v not in (None, ""))
        rows.append(f"<tr><td>{when}</td><td>{e.get('country','')}</td>"
                    f"<td>{e.get('event','')}</td><td class='imp'>{dots}</td>"
                    f"<td>{vals}</td></tr>")
    return ('<h2>לוח אירועים קרוב</h2><table class="cal"><thead><tr>'
            '<th>מועד</th><th>מדינה</th><th>אירוע</th><th>חשיבות</th><th>צפי / קודם</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def archive_panel(entries: list[tuple[str, str]], limit: int = 10) -> str:
    if not entries:
        return ""
    items = "\n".join(f'<li><a href="briefs/{d}.html">{t}</a></li>'
                      for d, t in entries[1:limit + 1])
    if not items:
        return ""
    return (f'<h2>ברייפים קודמים</h2><ul class="archive">{items}</ul>'
            '<p><a href="archive.html">לארכיון המלא ←</a></p>')


def load_reports(day: str | None = None) -> list[dict]:
    """סיכומי מאיה מ-output/reports/*.jsonl, החדש ביותר קודם."""
    d = ROOT / "output" / "reports"
    if not d.exists():
        return []
    files = sorted(d.glob("*.jsonl"), reverse=True)
    if day:
        files = [f for f in files if f.stem == day]
    rows = []
    for f in files[:5]:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return sorted(rows, key=lambda x: x.get("ts") or "", reverse=True)


def reports_rows(rows: list[dict], limit: int | None = None,
                 day_separators: bool = False) -> str:
    out, last_day = [], None
    for r in (rows[:limit] if limit else rows):
        if day_separators:
            day = (r.get("ts") or "")[:10]
            if day != last_day:
                out.append(f'<li class="daysep">{day[8:10]}/{day[5:7]}</li>')
                last_day = day
        mat = r.get("materiality") or 1
        cov = r.get("coverage") or []
        badge = ('<span class="cov">כיסוי</span>' if cov else "")
        dirc = (r.get("direction") or "").strip()
        dcls = {"חיובי": "up", "שלילי": "down"}.get(dirc, "flat")
        figs = "".join(
            f'<span class="fig"><b>{f.get("label","")}</b>{f.get("value","")}</span>'
            for f in (r.get("key_figures") or [])[:5] if isinstance(f, dict))
        aff = ", ".join(r.get("affected") or [])
        head = r.get("headline") or r.get("title") or ""
        out.append(
            f'<li class="rep m{mat}">'
            f'<div class="rep-head"><span class="t">{(r.get("ts") or "")[11:16]}</span>'
            f'<a href="{r.get("url","#")}" target="_blank" rel="noopener">'
            f'{", ".join(r.get("companies") or []) or "—"}</a>{badge}'
            f'<span class="chg {dcls}">{dirc}</span>'
            f'<span class="mat">{"●" * int(mat)}</span></div>'
            + (f'<div class="rep-hl">{head}</div>' if head else "")
            + f'<div class="rep-sum">{r.get("summary","")}</div>'
            + (f'<div class="figs">{figs}</div>' if figs else "")
            + (f'<div class="rep-ctx">השוואה: {r.get("context")}</div>'
               if (r.get("context") or "").strip() else "")
            + (f'<div class="rep-why">{r.get("why","")}</div>'
               if (r.get("why") or "").strip() not in ("", "טכני") else "")
            + (f'<div class="rep-aff"><b>נוגע ל:</b> {aff}'
               + (f' — {r.get("affected_why")}' if (r.get("affected_why") or "").strip() else "")
               + "</div>" if aff else "")
            + (f'<div class="rep-watch"><b>לעקוב:</b> {r.get("watch")}</div>'
               if (r.get("watch") or "").strip() else "")
            + "</li>")
    return "".join(out)


def reports_panel(rows: list[dict]) -> str:
    if not rows:
        return ""
    lvl3 = [r for r in rows if (r.get("materiality") or 1) >= 3]
    head = (f'<h2>דיווחי מאיה — {len(rows)} סוכמו'
            + (f', {len(lvl3)} מהותיים' if lvl3 else "") + "</h2>")
    return (head + f'<ul class="reports">{reports_rows(rows, 12)}</ul>'
            '<p><a href="reports.html">כל הדיווחים ←</a></p>')


def load_news(days: int = 14) -> list[dict]:
    """חדשות מסווגות מ-output/news/*.jsonl, החדשות קודם."""
    d = ROOT / "output" / "news"
    if not d.exists():
        return []
    rows = []
    for f in sorted(d.glob("*.jsonl"), reverse=True)[:days]:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return sorted(rows, key=lambda x: x.get("ts") or "", reverse=True)


def news_items_html(rows: list[dict], limit: int | None = None) -> str:
    out, last_day = [], None
    for r in (rows[:limit] if limit else rows):
        day = (r.get("ts") or "")[:10]
        if day != last_day:
            out.append(f'<li class="daysep">{day[8:10]}/{day[5:7]}</li>')
            last_day = day
        url = r.get("url") or "#"
        out.append(
            f'<li class="nw"><span class="t">{(r.get("ts") or "")[11:16]}</span>'
            f'<a href="{url}" target="_blank" rel="noopener">{r.get("title","")}</a>'
            f'<span class="src">{r.get("source","")}</span></li>')
    return "".join(out)


def topics_nav(topics: list[dict], counts: dict, current: str = "") -> str:
    links = []
    for t in topics:
        n = counts.get(t["slug"], 0)
        if not n:
            continue
        cls = ' class="cur"' if t["slug"] == current else ""
        links.append(f'<a href="topics/{t["slug"]}.html"{cls}>{t["label"]}'
                     f'<em>{n}</em></a>')
    return f'<nav class="topics">{"".join(links)}</nav>' if links else ""


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    site_title = cfg.get("site", {}).get("title", "ברייף FOREST")
    topics = cfg.get("topics") or []

    # שלוש מהדורות ביום: brief_<date>.md (בוקר, שם היסטורי) ו-brief_<date>-<edition>.md.
    # המיון הוא לפי (תאריך, סדר המהדורה) כדי שהחדשה ביותר תהיה ראשונה.
    # סדר כרונולוגי בתוך היום: מהדורת הלילה נכתבת ב-00:00 ולכן היא הראשונה,
    # לא האחרונה. מיון הפוך שהניח night>morning הציג ברייף ישן כעדכני ביותר.
    ED_ORDER = {"night": 0, "": 1, "morning": 1, "close": 2}
    ED_HE = {"": "בוקר", "morning": "בוקר", "close": "נעילה", "night": "לילה"}
    found = []
    for f in ROOT.glob("output/brief_*.md"):
        m = re.match(r"brief_(\d{4}-\d{2}-\d{2})(?:-(morning|close|night))?\.md$", f.name)
        if m:
            found.append((m.group(1), ED_ORDER.get(m.group(2) or "", 0), m.group(2) or "", f))
    found.sort(key=lambda x: (x[0], x[1]), reverse=True)
    briefs = [f for _, _, _, f in found]
    slugs = {f: (d + ("-" + e if e else "")) for d, _, e, f in found}
    ed_of = {f: ED_HE.get(e, "בוקר") for d, _, e, f in found}

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "briefs").mkdir(parents=True)
    shutil.copy(STYLE, OUT / "style.css")

    # --- עמודי נושאים -----------------------------------------------------
    news = load_news()
    counts = {}
    for r in news:
        for s in r.get("topics") or []:
            counts[s] = counts.get(s, 0) + 1
    (OUT / "topics").mkdir(exist_ok=True)
    for tp in topics:
        rows = [r for r in news if tp["slug"] in (r.get("topics") or [])]
        if not rows:
            continue
        comps = ", ".join(tp.get("companies") or [])
        body = (f'<h1>{tp["label"]}</h1>'
                + (f'<p class="stamp">חברות כיסוי שנוגעות בנושא: {comps}</p>' if comps else "")
                + f'<p class="stamp">{len(rows)} אייטמים מ-14 הימים האחרונים</p>'
                + topics_nav(topics, counts, tp["slug"]).replace('topics/', '')
                + f'<ul class="news">{news_items_html(rows)}</ul>')
        (OUT / "topics" / f'{tp["slug"]}.html').write_text(
            PAGE.format(title=f'{tp["label"]} · {site_title}', site_title=site_title,
                        root="../", body=body), encoding="utf-8")

    entries = []
    for p in briefs:
        slug = slugs[p]
        md_text = p.read_text(encoding="utf-8")
        title = brief_title(md_text, f"ברייף {slug}")
        (OUT / "briefs" / f"{slug}.html").write_text(
            PAGE.format(title=title, site_title=site_title, root="../", body=render(md_text)),
            encoding="utf-8")
        entries.append((slug, f"{title}" if ed_of[p] in title else f"{title} · {ed_of[p]}"))

    if entries:
        latest_slug, latest_title = entries[0]
        latest_date = latest_slug[:10]
        raw_dir = ROOT / "data" / "raw" / latest_date
        markets = load_json(raw_dir / "markets.json")
        te = load_json(raw_dir / "te.json")
        reports = load_reports()
        # חותמת לפי תאריך הברייף ולא לפי שעת הבנייה: בנייה חוזרת בלי ברייף חדש
        # הייתה מציגה "עודכן עכשיו" מעל תוכן של אתמול.
        d_disp = f"{latest_date[8:10]}/{latest_date[5:7]}/{latest_date[:4]}"
        age = (datetime.now().date() - datetime.strptime(latest_date, "%Y-%m-%d").date()).days
        stale_note = "" if age <= 0 else f' <b class="stale">ברייף בן {age} ימים</b>'
        body = "\n".join(filter(None, [
            f'<div class="dash-head"><h1>{latest_title}</h1>'
            f'<span class="stamp">ברייף ל-{d_disp}{stale_note} · נבנה {datetime.now():%d/%m %H:%M}</span></div>',
            sources_panel(raw_dir),
            topics_nav(topics, counts),
            markets_strip(markets, te),
            reports_panel(reports),
            indicators_panel(te),
            calendar_panel(te),
            '<hr class="sep">',
            render(briefs[0].read_text(encoding="utf-8")),
            '<hr class="sep">',
            archive_panel(entries),
        ]))
    else:
        latest_title = site_title
        body = "<p>אין עדיין ברייפים ב-output/.</p>"

    (OUT / "index.html").write_text(
        PAGE.format(title=latest_title, site_title=site_title, root="", body=body),
        encoding="utf-8")

    items = "\n".join(f'<li><a href="briefs/{d}.html">{t}</a></li>' for d, t in entries)
    (OUT / "archive.html").write_text(
        PAGE.format(title=f"ארכיון · {site_title}", site_title=site_title, root="",
                    body=f'<h1>ארכיון</h1><ul class="archive">{items}</ul>'
                         if items else "<h1>ארכיון</h1><p>ריק.</p>"),
        encoding="utf-8")

    all_reports = load_reports()
    if all_reports:
        lvl3 = [r for r in all_reports if (r.get("materiality") or 1) >= 3]
        cov = [r for r in all_reports if r.get("coverage")]
        comps = len({c for r in all_reports for c in (r.get("companies") or [])})
        head = (
            '<h1>דיווחים וסיכומי דוחות</h1>'
            '<p class="stamp">כל דיווח מהותי שמתפרסם במאיה — <b>מכל חברה נסחרת</b>, '
            'לא רק מחברות הכיסוי. הניטור רץ כל רבע שעה בשעות המסחר, מוריד את גוף '
            'הדוח (כולל ה-PDF המצורף) ומסכם אותו.</p>'
            f'<p class="stamp">{len(all_reports)} דיווחים · {comps} חברות · '
            f'{len(lvl3)} ברמת מהותיות 3 · {len(cov)} של חברות כיסוי</p>')
        body = head
        if lvl3:
            body += ('<h2>מהותיים</h2>'
                     f'<ul class="reports">{reports_rows(lvl3, day_separators=True)}</ul>')
        rest = [r for r in all_reports if (r.get("materiality") or 1) < 3]
        if rest:
            body += ('<h2>שאר הדיווחים</h2>'
                     f'<ul class="reports">{reports_rows(rest, day_separators=True)}</ul>')
    else:
        body = ('<h1>דיווחים וסיכומי דוחות</h1>'
                '<p>אין עדיין סיכומים. הניטור רץ בשעות המסחר, שני–שישי.</p>')
    (OUT / "reports.html").write_text(
        PAGE.format(title=f"דיווחים וסיכומי דוחות · {site_title}",
                    site_title=site_title, root="", body=body), encoding="utf-8")

    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"נבנה {OUT} | {len(entries)} ברייפים | "
          f"{datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
