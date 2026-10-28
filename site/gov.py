# -*- coding: utf-8 -*-
"""עמודי הרגולציה: 17 משרדים ורשויות (config/gov.yaml), ועמוד ראשי שמרכז אותם.

הנתונים: ingest/gov_pull.py (פרסומים מה-API הפתוח של gov.il) ו-
scripts/analyze_gov.py (מה מהותי, וסיקור מתוך המסמך). עמוד לכל גוף, ובו:
מה הגוף עושה ודוגמאות להחלטות שלו, הפרסומים המהותיים עם הסיקור שלהם — בפשטות,
מה נקבע, איך זה מגיע לחברות ודוגמה — ואחריהם כל הפרסומים, כדי שהקורא יראה גם
מה סונן ולא רק את מה שנבחר בשבילו.

**העמוד הראשי (gov.html)** — הגופים לפי קבוצות, ולכל אחד כמה מהותיים יש לו
והאחרון שבהם; ומעליהם המהותיים האחרונים מכל הגופים יחד. 17 לשוניות בשורה אחת
אינן ניווט, ולכן בעמוד של גוף הלשוניות הן של הקבוצה שלו בלבד.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

import yaml

from autonews import _dir, _stamp, _txt

ROOT = Path(__file__).resolve().parent.parent
GOV = ROOT / "output" / "gov"
CFG = ROOT / "config" / "gov.yaml"
KIND_HE = {"news": "חדשות והודעות", "policies": "החלטות ונהלים", "pubs": "פרסומים ושימועים"}
MATERIAL_DAYS = 45
LIST_DAYS = 45
HUB = "gov.html"
DATAGOV = "https://data.gov.il/he/organizations/{}"


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


def _anchor(item_id: str) -> str:
    return "i-" + "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(item_id))


def tabs(cfg: dict, active: str) -> str:
    """הקישור לעמוד הראשי, ואחריו הגופים של אותה קבוצה."""
    me = next((o for o in cfg.get("offices") or [] if o["key"] == active), {})
    links = [f'<a href="{HUB}">כל הרגולטורים</a>']
    for o in cfg.get("offices") or []:
        if o.get("group") != me.get("group"):
            continue
        cls = ' class="on"' if o["key"] == active else ""
        links.append(f'<a href="{escape(o["page"])}"{cls}>{escape(o["name"])}</a>')
    return '<nav class="cbs-toc gv-tabs" aria-label="גופי רגולציה">' + "".join(links) + "</nav>"


def _cos(names: list[str] | None) -> str:
    if not names:
        return ""
    return '<div class="cc-cos">' + "".join(f'<span class="co">{escape(n)}</span>' for n in names) + "</div>"


def _example_li(s: str) -> str:
    """"כותרת: הסבר" → כותרת מודגשת והסבר."""
    head, sep, rest = s.partition(": ")
    return (f"<li><b>{escape(head)}:</b> {escape(rest)}</li>" if sep and len(head) <= 60
            else f"<li>{escape(s)}</li>")


def about(office: dict) -> str:
    """מה הגוף עושה, ודוגמאות להחלטות שלו — לקורא שאינו מכיר את הענף."""
    if not office.get("about"):
        return ""
    ex = "".join(_example_li(s) for s in office.get("examples") or [])
    dg = (f' · <a href="{DATAGOV.format(escape(office["datagov"]))}" target="_blank" rel="noopener">'
          'מאגרי המידע שלו ב-data.gov.il</a>' if office.get("datagov") else "")
    return (f'<div class="gv-about"><p><b>מה הגוף הזה עושה:</b> {escape(office["about"])}</p>'
            + (f'<p class="gv-ex-h">החלטות טיפוסיות שלו, ומה הן עושות:</p><ul class="gv-ex">{ex}</ul>'
               if ex else "")
            + f'<p class="gv-about-src"><a href="{escape(office["url"])}" target="_blank" '
              f'rel="noopener">האתר שלו ב-gov.il</a>{dg}</p></div>')


def _card(it: dict, a: dict) -> str:
    head = a.get("headline") or it["title"]
    meta = " · ".join(x for x in (_d(it.get("date")), it.get("type"), it.get("unit")) if x)
    links = [f'<a href="{escape(it["url"])}" target="_blank" rel="noopener">העמוד ב-gov.il</a>']
    if a.get("doc") and a["doc"].startswith("https://"):
        links.append(f'<a href="{escape(a["doc"])}" target="_blank" rel="noopener">המסמך (PDF)</a>')
    if a.get("what"):
        basis = "מתוך המסמך" if a.get("basis") == "מסמך" else "לפי הכותרת"
        body = ((f'<p class="dg-simple gv-simple"><b>בפשטות:</b> {_txt(a["simple"])}</p>'
                 if a.get("simple") else "")
                + (f'<p class="gv-what"><b>מה נקבע:</b> {_txt(a["what"])}</p>')
                + (f'<p class="au-channel"><b>איך זה מגיע לחברות:</b> {_txt(a["mechanism"])}</p>'
                   if a.get("mechanism") else "")
                + (f'<p class="gv-example">{_txt(a["example"])}</p>' if a.get("example") else "")
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
    return (f'<div class="cbs-card gv-item" id="{_anchor(it["id"])}"><div class="cc-head"><h3>'
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


def _recent(data: dict, key: str) -> tuple[list[dict], list[dict], dict]:
    """(כל הפרסומים בחלון, המהותיים שבהם, הסיקורים) לגוף אחד."""
    od = data["offices"].get(key) or {"items": [], "an": {}}
    today = date.today()
    mat_from = (today - timedelta(days=MATERIAL_DAYS)).isoformat()
    list_from = (today - timedelta(days=LIST_DAYS)).isoformat()
    items = [it for it in od["items"] if (it.get("date") or "") >= list_from]
    an = od["an"]
    material = [it for it in items if (it.get("date") or "") >= mat_from
                and (an.get(it["id"]) or {}).get("material")]
    return items, material, an


def page(data: dict, key: str) -> str:
    cfg = data["cfg"]
    office = next(o for o in cfg["offices"] if o["key"] == key)
    items, material, an = _recent(data, key)
    surveyed = sum(1 for it in material if (an.get(it["id"]) or {}).get("what"))
    stamp = data.get("state", {}).get("updated")
    roles = "".join(f'<li><b>{escape(g["role"])}</b> — {", ".join(escape(c) for c in g.get("companies") or [])}'
                    f'<br><span class="gv-why">{escape(g.get("why") or "")}</span></li>'
                    for g in office.get("roles") or [])

    if not items:
        return (f'<h1>{escape(office["name"])}</h1>{tabs(cfg, key)}{about(office)}'
                '<p class="lead">טרם נאספו פרסומים. הם ייאספו בריצה הקרובה של צנרת הרגולציה.</p>')

    mat_html = ("".join(_card(it, an.get(it["id"]) or {}) for it in material)
                if material else '<p class="au-quiet">אין פרסום מהותי לחברות הנסחרות ב-45 הימים האחרונים.</p>')
    return "\n".join([
        f'<div class="dash-head"><h1>{escape(office["name"])}</h1>'
        f'<span class="stamp">עודכן {_stamp(stamp)}</span></div>',
        tabs(cfg, key),
        about(office),
        f'<h2 id="gv-mat">מהותי לחברות הנסחרות <span class="au-cnt">{len(material)}</span></h2>',
        '<p class="cbs-sub">לכל פרסום: בפשטות, מה נקבע, איך זה מגיע לחברות ודוגמה. הסיקור נכתב מתוך מסמך '
        'הפרסום עצמו כשהוא זמין, ומסומן "לפי הכותרת" כשלא. ניתוח השפעה, לא המלצת השקעה.</p>',
        f'<div class="cbs-cards gv-cards">{mat_html}</div>',
        f'<h2 id="gv-all">כל הפרסומים — {LIST_DAYS} הימים האחרונים</h2>',
        '<p class="cbs-sub">כולל מה שלא סומן כמהותי, כדי שאפשר יהיה לראות גם מה סונן. משרות והודעות לימאים אינן נאספות.</p>',
        f'<div class="au-chain gv-all">{_list(items, an)}</div>',
        f'<details class="gv-map"><summary>החברות שהעמוד הזה עוקב אחריהן, ולמה</summary><ul>{roles}</ul></details>',
        f'<p class="au-src">מקור: {escape(office["name"])} — '
        f'<a href="{escape(office["url"])}" target="_blank" rel="noopener">gov.il</a>, דרך ה-API הפתוח של אתר הממשלה. '
        f'סיקור: TLV TASE View ({surveyed} מתוך {len(material)} פרסומים מהותיים).</p>',
    ])


def _first_sentence(s: str) -> str:
    s = " ".join((s or "").split())
    cut = s.find(". ")
    return s[:cut + 1] if 0 < cut < 220 else s[:220]


def hub(data: dict) -> str:
    """העמוד הראשי: המהותיים האחרונים מכל הגופים, והגופים לפי קבוצות."""
    cfg = data["cfg"]
    offices = cfg.get("offices") or []
    stamp = data.get("state", {}).get("updated")
    n_items = n_mat = n_surv = 0
    latest: list[tuple[dict, dict, dict]] = []
    per: dict[str, tuple[int, list[dict], dict]] = {}
    for o in offices:
        items, material, an = _recent(data, o["key"])
        per[o["key"]] = (len(items), material, an)
        n_items += len(items)
        n_mat += len(material)
        n_surv += sum(1 for it in material if (an.get(it["id"]) or {}).get("what"))
        latest += [(o, it, an.get(it["id"]) or {}) for it in material]
    latest.sort(key=lambda t: (t[1].get("date") or "", t[1].get("fetched_at") or ""), reverse=True)

    tiles = (
        '<div class="strip">'
        f'<div class="tile"><div class="lbl">גופים</div><div class="val">{len(offices)}</div></div>'
        f'<div class="tile"><div class="lbl">פרסומים</div><div class="val">{n_items:,}</div>'
        f'<div class="chg">ב-{LIST_DAYS} יום</div></div>'
        f'<div class="tile"><div class="lbl">מהותיים</div><div class="val">{n_mat}</div>'
        '<div class="chg">לחברות הנסחרות</div></div>'
        f'<div class="tile"><div class="lbl">עם סיקור</div><div class="val">{n_surv}</div></div>'
        '</div>')

    rows = []
    for o, it, a in latest[:12]:
        head = a.get("headline") or it["title"]
        rows.append(f'<li><span class="gv-date">{_d(it.get("date"))}</span>'
                    f'<span class="gv-type">{escape(o["name"])}</span>'
                    f'<a href="{escape(o["page"])}#{_anchor(it["id"])}">{_txt(head)}</a>'
                    f'{_dir(a.get("direction"))}</li>')
    recent = (f'<ul class="gv-list gv-latest">{"".join(rows)}</ul>' if rows
              else '<p class="au-quiet">אין פרסום מהותי ב-45 הימים האחרונים.</p>')

    groups = []
    for g in cfg.get("groups") or []:
        cards = []
        for o in [x for x in offices if x.get("group") == g["key"]]:
            n, material, an = per[o["key"]]
            last = material[0] if material else None
            last_html = (f'<p class="gv-last"><span class="gv-date">{_d(last.get("date"))}</span> '
                         f'{_txt((an.get(last["id"]) or {}).get("headline") or last["title"])}</p>'
                         if last else '<p class="gv-last gv-none">אין פרסום מהותי ב-45 הימים האחרונים</p>')
            badge = (f'<span class="gv-mat">{len(material)} מהותיים</span>' if material
                     else '<span class="gv-cnt0">0 מהותיים</span>')
            cards.append(f'<a class="cbs-card gv-office" href="{escape(o["page"])}">'
                         f'<div class="cc-head"><h3>{escape(o["name"])}</h3>{badge}</div>'
                         f'<p class="gv-blurb">{escape(_first_sentence(o.get("about") or ""))}</p>'
                         f'{last_html}<p class="gv-meta">{n} פרסומים ב-{LIST_DAYS} יום</p></a>')
        groups.append(f'<h2>{escape(g["name"])}</h2><div class="cbs-cards gv-hub">{"".join(cards)}</div>')

    return "\n".join([
        f'<div class="dash-head"><h1>רגולציה</h1><span class="stamp">עודכן {_stamp(stamp)}</span></div>',
        '<p class="lead">החלטות, שימועים והודעות של 17 משרדים ורשויות שנוגעים בחברות הנסחרות — '
        'ישירות מ-gov.il, כמה פעמים ביום בימי עבודה. לכל פרסום מהותי: מה נקבע, הסבר בפשטות, '
        'איך זה מגיע לדוחות של החברות, ודוגמה.</p>',
        tiles,
        '<h2>המהותיים האחרונים, מכל הגופים</h2>',
        f'<div class="au-chain gv-all">{recent}</div>',
        *groups,
        '<p class="au-src">רשימת הגופים: <a href="https://data.gov.il/he" target="_blank" rel="noopener">'
        'data.gov.il</a>, ורשות התחרות ורשות החשמל מ-gov.il. הפרסומים: ה-API הפתוח של gov.il. '
        'בנק ישראל ורשות ניירות ערך מפרסמים באתרים משלהם, ואינם כאן. ניתוח השפעה, לא המלצת השקעה.</p>',
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
