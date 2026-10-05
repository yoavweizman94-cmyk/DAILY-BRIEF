# -*- coding: utf-8 -*-
"""עמודי הרגולציה: משרד התקשורת, רשות החשמל ומשרד התחבורה.

הנתונים: ingest/gov_pull.py (פרסומים מה-API הפתוח של gov.il) ו-
scripts/analyze_gov.py (מה מהותי, וסיקור מתוך המסמך). עמוד לכל גוף, עם
לשוניות ביניהם, ושני חלקים: הפרסומים המהותיים עם הסיקור שלהם, ואחריהם כל
הפרסומים — כדי שהקורא יראה גם מה סונן ולא רק את מה שנבחר בשבילו.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

import yaml

from autonews import _dir, _para, _stamp, _txt

ROOT = Path(__file__).resolve().parent.parent
GOV = ROOT / "output" / "gov"
CFG = ROOT / "config" / "gov.yaml"
KIND_HE = {"news": "חדשות והודעות", "policies": "החלטות ונהלים", "pubs": "פרסומים ושימועים"}
MATERIAL_DAYS = 45
LIST_DAYS = 45


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load() -> dict:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {"offices": []}
    offices = {}
    for o in cfg.get("offices") or []:
        an: dict[str, dict] = {}
        for r in _jsonl(GOV / o["key"] / "analyses.jsonl"):
            an.setdefault(r["id"], {}).update(r)
        offices[o["key"]] = {"items": _jsonl(GOV / o["key"] / "items.jsonl"), "an": an}
    state = {}
    try:
        state = json.loads((GOV / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"cfg": cfg, "offices": offices, "state": state}


def _d(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m") if iso else ""
    except ValueError:
        return ""


def tabs(cfg: dict, active: str) -> str:
    links = []
    for o in cfg.get("offices") or []:
        cls = ' class="on"' if o["key"] == active else ""
        links.append(f'<a href="{escape(o["page"])}"{cls}>{escape(o["name"])}</a>')
    return '<nav class="cbs-toc gv-tabs" aria-label="גופי רגולציה">' + "".join(links) + "</nav>"


def _cos(names: list[str] | None) -> str:
    if not names:
        return ""
    return '<div class="cc-cos">' + "".join(f'<span class="co">{escape(n)}</span>' for n in names) + "</div>"


def _card(it: dict, a: dict) -> str:
    head = a.get("headline") or it["title"]
    meta = " · ".join(x for x in (_d(it.get("date")), it.get("type"), it.get("unit")) if x)
    links = [f'<a href="{escape(it["url"])}" target="_blank" rel="noopener">העמוד ב-gov.il</a>']
    if a.get("doc") and a["doc"].startswith("https://"):
        links.append(f'<a href="{escape(a["doc"])}" target="_blank" rel="noopener">המסמך (PDF)</a>')
    if a.get("what"):
        basis = "מתוך המסמך" if a.get("basis") == "מסמך" else "לפי הכותרת"
        body = (_para(a.get("what"))
                + (f'<p class="au-channel"><b>איך זה מגיע לחברות:</b> {_txt(a["mechanism"])}</p>'
                   if a.get("mechanism") else "")
                + (f'<p class="au-mag"><b>גודל:</b> {_txt(a["magnitude"])}</p>' if a.get("magnitude") else "")
                + (f'<p class="au-conf"><b>מה הלאה:</b> {_txt(a["next"])}</p>' if a.get("next") else ""))
        tag = f'<span class="au-basis">{basis}</span> '
    else:
        # מהותי לפי המיון, ועדיין בלי סיקור — או שהסיקור נפסל בבדיקת המספרים.
        # סיקור שנפסל אינו נכתב שוב (analyze_gov מדלג עליו), ולכן אין להבטיח אותו.
        why = _txt(a.get("reason")) if a.get("reason") else ""
        note = ("הסיקור נפסל: הופיע בו מספר שאינו במסמך המקורי. הפרטים במסמך עצמו."
                if a.get("survey_failed") else "הסיקור ייכתב בריצה הבאה.")
        body = (f"<p>{why}</p>" if why else "") + f'<p class="gv-pending">{note}</p>'
        tag = ""
    return (f'<div class="cbs-card gv-item"><div class="cc-head"><h3>'
            f'<a href="{escape(it["url"])}" target="_blank" rel="noopener">{_txt(head)}</a></h3>'
            f'{_dir(a.get("direction"))}</div>'
            f'<p class="gv-meta">{escape(meta)}</p>{_cos(a.get("companies"))}{body}'
            f'<p class="gv-src">{tag}{" · ".join(links)}</p></div>')


def _list(items: list[dict], an: dict) -> str:
    blocks = []
    for kind, label in KIND_HE.items():
        rows = [it for it in items if it.get("kind") == kind]
        if not rows:
            continue
        lis = []
        for it in rows:
            a = an.get(it["id"]) or {}
            mark = ' <span class="gv-mat" title="מהותי לחברות הנסחרות">מהותי</span>' if a.get("material") else ""
            lis.append(f'<li><span class="gv-date">{_d(it.get("date"))}</span>'
                       f'<span class="gv-type">{escape(it.get("type") or "")}</span>'
                       f'<a href="{escape(it["url"])}" target="_blank" rel="noopener" dir="auto">'
                       f'{escape(it["title"])}</a>{mark}</li>')
        blocks.append(f'<div class="au-role gv-kind"><h3>{escape(label)} <span class="au-cnt">{len(rows)}</span></h3>'
                      f'<ul class="gv-list">{"".join(lis)}</ul></div>')
    return "".join(blocks)


def page(data: dict, key: str) -> str:
    cfg = data["cfg"]
    office = next(o for o in cfg["offices"] if o["key"] == key)
    od = data["offices"].get(key) or {"items": [], "an": {}}
    today = date.today()
    mat_from = (today - timedelta(days=MATERIAL_DAYS)).isoformat()
    list_from = (today - timedelta(days=LIST_DAYS)).isoformat()
    items = [it for it in od["items"] if (it.get("date") or "") >= list_from]
    an = od["an"]
    material = [it for it in items if (it.get("date") or "") >= mat_from and (an.get(it["id"]) or {}).get("material")]
    surveyed = sum(1 for it in material if (an.get(it["id"]) or {}).get("what"))
    stamp = data.get("state", {}).get("updated")
    roles = "".join(f'<li><b>{escape(g["role"])}</b> — {", ".join(escape(c) for c in g.get("companies") or [])}</li>'
                    for g in office.get("roles") or [])

    if not items:
        return (f'<h1>{escape(office["name"])}</h1>{tabs(cfg, key)}'
                '<p class="lead">טרם נאספו פרסומים. הם ייאספו בריצה הקרובה של צנרת הרגולציה.</p>')

    mat_html = ("".join(_card(it, an.get(it["id"]) or {}) for it in material)
                if material else '<p class="au-quiet">אין פרסום מהותי לחברות הנסחרות ב-45 הימים האחרונים.</p>')
    return "\n".join([
        f'<div class="dash-head"><h1>{escape(office["name"])}</h1>'
        f'<span class="stamp">עודכן {_stamp(stamp)}</span></div>',
        tabs(cfg, key),
        f'<p class="lead">החלטות, שימועים, הודעות ופרסומים של {escape(office["name"])}, ישירות מה-API של '
        'gov.il — ולכל פרסום מהותי, מה נקבע בו ואיך זה מגיע לדוחות של החברות הנסחרות. '
        'מתעדכן כמה פעמים ביום בימי עבודה.</p>',
        f'<h2 id="gv-mat">מהותי לחברות הנסחרות <span class="au-cnt">{len(material)}</span></h2>',
        '<p class="cbs-sub">הסיקור נכתב מתוך מסמך הפרסום עצמו כשהוא זמין, ומסומן "לפי הכותרת" כשלא. '
        'ניתוח השפעה, לא המלצת השקעה.</p>',
        f'<div class="cbs-cards gv-cards">{mat_html}</div>',
        f'<h2 id="gv-all">כל הפרסומים — {LIST_DAYS} הימים האחרונים</h2>',
        '<p class="cbs-sub">כולל מה שלא סומן כמהותי, כדי שאפשר יהיה לראות גם מה סונן. משרות והודעות לימאים אינן נאספות.</p>',
        f'<div class="au-chain gv-all">{_list(items, an)}</div>',
        f'<details class="gv-map"><summary>החברות שהעמוד הזה עוקב אחריהן</summary><ul>{roles}</ul></details>',
        f'<p class="au-src">מקור: {escape(office["name"])} — '
        f'<a href="{escape(office["url"])}" target="_blank" rel="noopener">gov.il</a>, דרך ה-API הפתוח של אתר הממשלה. '
        f'סיקור: TLV TASE View ({surveyed} מתוך {len(material)} פרסומים מהותיים).</p>',
    ])


def report(data: dict) -> list[str]:
    """שורות לבנייה: כמה פרסומים, כמה מהותיים, כמה בלי סיקור."""
    out = []
    since = (date.today() - timedelta(days=MATERIAL_DAYS)).isoformat()
    for o in data["cfg"].get("offices") or []:
        od = data["offices"].get(o["key"]) or {"items": [], "an": {}}
        recent = [it for it in od["items"] if (it.get("date") or "") >= since]
        mat = [it for it in recent if (od["an"].get(it["id"]) or {}).get("material")]
        pend = [it for it in mat if not (od["an"].get(it["id"]) or {}).get("what")]
        fail = [it for it in pend if (od["an"].get(it["id"]) or {}).get("survey_failed")]
        out.append(f"{o['name']}: {len(recent)} פרסומים ב-45 יום, {len(mat)} מהותיים"
                   + (f" ({len(pend)} בלי סיקור, מהם {len(fail)} שנפסלו)" if fail else
                      f" ({len(pend)} בלי סיקור)" if pend else ""))
    stamp = data.get("state", {}).get("updated")
    return [f"::notice::עמודי הרגולציה: " + " · ".join(out) + f" · משיכה {stamp or '—'}"]
