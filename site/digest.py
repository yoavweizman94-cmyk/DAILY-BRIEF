# -*- coding: utf-8 -*-
"""עמוד הכותרות (headlines.html): מה מהותי מהחדשות בארץ ובעולם, לפי תחום.

הנתונים: scripts/digest.py, כל שלוש שעות. העמוד מציג את מה שנבחר ב-24
השעות האחרונות: בראש — מה שסומן "חשוב" (רמה 3), ואחריו כל תחום בנפרד,
ישראל ועולם זה לצד זה. כותרת מהעדכון האחרון מסומנת "חדש", כדי שמי שחוזר
אחרי שלוש שעות יראה מה נוסף בלי לקרוא הכול מחדש.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import yaml

from autonews import _local, _stamp, _txt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "digest"
CFG = ROOT / "config" / "digest.yaml"
SOURCES = ROOT / "config" / "sources.yaml"
REGIONS = ("ישראל", "עולם")


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _feed_names() -> list[str]:
    """שמות האתרים, בלי פירוק לפידים: "גלובס — שוק ההון" ו"גלובס — בארץ" הם גלובס."""
    names: list[str] = []
    for p, key in ((SOURCES, "rss"), (CFG, None)):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except OSError:
            continue
        feeds = (data.get(key) or {}).get("feeds") if key else data.get("feeds")
        for f in feeds or []:
            n = str(f.get("name") or "").split(" — ")[0].strip()
            if n and n not in names:
                names.append(n)
    return names


def load() -> dict:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}
    try:
        state = json.loads((OUT / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    now = datetime.now(timezone.utc)
    hours = int((cfg.get("params") or {}).get("page_hours", 24))
    since = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
    by_id: dict[str, dict] = {}
    for d in (now - timedelta(days=1), now):
        day = _local(d.isoformat()).date().isoformat()
        for r in _jsonl(OUT / f"{day}.jsonl"):
            if (r.get("run") or "") >= since:
                by_id[r["id"]] = r
    items = sorted(by_id.values(), key=lambda r: r.get("ts") or "", reverse=True)
    return {"cfg": cfg, "state": state, "items": items, "hours": hours}


def _when(ts: str | None, today) -> str:
    d = _local(ts)
    if not d:
        return ""
    return f"{d:%H:%M}" if d.date() == today else f"{d:%d/%m %H:%M}"


def _item(r: dict, latest: str | None, today) -> str:
    tags = ""
    if r.get("level") == 3:
        tags += ' <span class="dg-tag dg-imp">חשוב</span>'
    if latest and r.get("run") == latest:
        tags += ' <span class="dg-tag dg-new">חדש</span>'
    srcs = " · ".join(
        f'<a href="{escape(s["url"])}" target="_blank" rel="noopener" title="{escape(s.get("title") or "")}">'
        f'{escape(s["name"])}</a>'
        for s in r.get("sources") or [] if (s.get("url") or "").startswith("http"))
    cos = ("" if not r.get("companies") else
           '<div class="cc-cos">' + "".join(f'<span class="co">{escape(c)}</span>' for c in r["companies"]) + "</div>")
    return (f'<article class="dg-item" id="{escape(r["id"])}">'
            f'<p class="dg-meta"><span class="dg-time">{_when(r.get("ts"), today)}</span>{tags}</p>'
            f'<h3 dir="auto">{_txt(r["headline"])}</h3>'
            + (f'<p class="dg-sum">{_txt(r["summary"])}</p>' if r.get("summary") else "")
            + (f'<p class="dg-why"><b>למה זה חשוב:</b> {_txt(r["why"])}</p>' if r.get("why") else "")
            + cos
            + (f'<p class="dg-src">{srcs}</p>' if srcs else "")
            + "</article>")


def page(data: dict) -> str:
    cfg, state, items = data["cfg"], data["state"], data["items"]
    today = _local(datetime.now(timezone.utc).isoformat()).date()
    last = state.get("last") or {}
    latest = state.get("updated")
    stamp = f"עודכן {_stamp(latest)}" if latest else "טרם עודכן"
    if last and not last.get("ok"):
        stamp += f' · <span class="stale">העדכון של {_stamp(last.get("at"))} נכשל</span>'
    head = (f'<div class="dash-head"><h1>כותרות</h1><span class="stamp">{stamp}</span></div>')
    names = _feed_names()
    lead = (f'<p class="lead">מה שמהותי לחברות הכיסוי מהחדשות בארץ ובעולם, בתמצית ולפי תחום — '
            f'נבחר כל שלוש שעות מתוך {len(names)} אתרי חדשות ותעשייה. '
            f'{data["hours"]} השעות האחרונות; מה שנוסף בעדכון האחרון מסומן "חדש".</p>')
    if not items:
        return "\n".join([head, lead, '<p class="au-quiet">טרם נבחרו כותרות. העמוד מתעדכן כל שלוש שעות.</p>'])

    # התחום נשמר כמפתח באנגלית (config/digest.yaml), והתווית נלקחת מהתצורה —
    # כך שינוי ניסוח של תווית חל גם על כותרות שכבר נשמרו
    label = {d["key"]: d["label"] for d in cfg.get("domains") or []}
    domains = [k for k in label if any(r["domain"] == k for r in items)]
    toc = ('<nav class="cbs-toc" aria-label="תחומים">'
           + "".join(f'<a href="#dg-{k}">{escape(label[k])} <span class="au-cnt">'
                     f'{sum(1 for r in items if r["domain"] == k)}</span></a>'
                     for k in domains) + "</nav>")

    must = [r for r in items if r.get("level") == 3]
    must_html = ""
    if must:
        lis = "".join(f'<li><span class="dg-time">{_when(r.get("ts"), today)}</span>'
                      f'<a href="#{escape(r["id"])}" dir="auto">{_txt(r["headline"])}</a>'
                      f'<span class="dg-dtag">{escape(label.get(r["domain"], ""))} · {escape(r["region"])}</span></li>'
                      for r in must)
        must_html = (f'<h2 id="dg-must">חשוב היום <span class="au-cnt">{len(must)}</span></h2>'
                     f'<ul class="dg-must">{lis}</ul>')

    secs = []
    for k in domains:
        rows = [r for r in items if r["domain"] == k]
        cols = []
        for reg in REGIONS:
            rr = [r for r in rows if r.get("region") == reg]
            if rr:
                cols.append(f'<div class="dg-col"><h3 class="dg-reg">{reg} <span class="au-cnt">{len(rr)}</span></h3>'
                            + "".join(_item(r, latest, today) for r in rr) + "</div>")
        cls = "dg-cols" + (" one" if len(cols) == 1 else "")
        secs.append(f'<section class="dg-dom" id="dg-{k}"><h2>{escape(label[k])} '
                    f'<span class="au-cnt">{len(rows)}</span></h2><div class="{cls}">{"".join(cols)}</div></section>')

    src = (f'<p class="au-src">מקורות: {escape(", ".join(names))}. הבחירה והתמצית: TLV TASE View, '
           'כל מספר נבדק מול הפריט שצוטט. ניתוח השפעה, לא המלצת השקעה.</p>')
    return "\n".join([head, lead, toc, must_html, *secs, src])


def report(data: dict) -> list[str]:
    items = data["items"]
    last = (data["state"].get("last") or {})
    return [f"::notice::עמוד הכותרות: {len(items)} כותרות ב-{data['hours']} שעות "
            f"({sum(1 for r in items if r.get('level') == 3)} חשובות) · עדכון אחרון "
            f"{_stamp(data['state'].get('updated'))}" + ("" if not last or last.get("ok") else " · האחרון נכשל")]
