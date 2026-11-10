# -*- coding: utf-8 -*-
"""לוח הדוחות בעמוד שיחות הוועידה: מי מפרסם דוח כספי בכל יום, ומי גם מקיים שיחה.

**מה זה מוסיף.** עד 10/11/2026 העמוד הציג רק שיחות ועידה. יואב ביקש "לכל יום — גם
החברות שרק הודיעו שיפרסמו דוח כספי", ולכל שבוע תמונה בסגנון לוחות הדוחות שברשתות:
עמודה לכל יום, לוגו לכל חברה, וסמל טלפון למי שמקיים גם שיחת ועידה. הכל ממאיה — לוח
האירועים (ingest/maya_calls.py: "פרסום דוחות" ו"שיחת ועידה") — והלוגו מאתר החברה
(ingest/logos_pull.py).

**השבוע מתחיל ביום ראשון.** הבורסה נסחרת שני–שישי, אבל חברות מפרסמות דוחות גם
בראשון. העמודות בתמונה: שני עד חמישי תמיד, ראשון ושישי רק כשיש בהם פרסום.

**סדר החברות ביום — לפי שווי השוק במאיה**, הגדולה ראשונה (data/company_profiles.json,
לחברות הכיסוי). חברה מחוץ לכיסוי, שאין לה שווי, בסוף — לפי השם.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from html import escape
from pathlib import Path

import otc

ROOT = Path(__file__).resolve().parent.parent
LOGOS = ROOT / "output" / "logos"
DAY_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]   # date.weekday()
MAX_DAY = 16           # אריחים ליום בתמונה; השאר — "ועוד N"
SRC = ("מקור: לוח האירועים במערכת מאיה של הבורסה לניירות ערך — מועדי פרסום הדוחות "
       "ושיחות הוועידה; הלוגואים מאתרי החברות")

PHONE_SVG = ('<svg class="rc-ph" viewBox="0 0 24 24" aria-label="שיחת ועידה" role="img"><path d="M6.62 '
             '10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 '
             '0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 '
             '2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" fill="currentColor"/></svg>')


def _cover() -> tuple[dict[int, str], dict[int, float]]:
    """מזהה מאיה → שם בכיסוי, ושווי שוק (מיליוני ₪)."""
    try:
        import yaml  # noqa: PLC0415
        cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
        prof = json.loads((ROOT / "data" / "company_profiles.json").read_text(encoding="utf-8")).get("companies") or {}
    except Exception:  # noqa: BLE001
        return {}, {}
    names, caps = {}, {}
    for c in cfg.get("companies") or []:
        mid = c.get("maya_company_id")
        if not mid:
            continue
        names[int(mid)] = c.get("name_he") or ""
        cap = (prof.get(c.get("name_he") or "") or {}).get("market_cap_m")
        if cap:
            caps[int(mid)] = float(cap)
    return names, caps


def _logos() -> dict[int, str]:
    try:
        man = json.loads((LOGOS / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {int(k): f"logos/{v['file']}" for k, v in man.items()
            if isinstance(v, dict) and v.get("file") and (LOGOS / v["file"]).exists()}


def _sunday(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _dm(iso: str) -> str:
    return f"{int(iso[8:10])}.{int(iso[5:7])}"


def weeks(calls: list[dict], reports: list[dict], today: str) -> list[dict]:
    """השבועות מהשבוע הנוכחי והלאה: לכל יום — מי מפרסם דוח, ומי מקיים שיחה."""
    names, caps = _cover()
    logos = _logos()
    start = _sunday(date.fromisoformat(today)).isoformat()
    days: dict[str, dict] = {}

    def day(iso: str) -> dict:
        return days.setdefault(iso, {"date": iso, "items": {}, "calls": []})

    linked = set()
    for r in reports:
        iso = r.get("date") or ""
        if iso < start or not r.get("company_id"):
            continue
        cid = int(r["company_id"])
        ct = None
        if r.get("call_date"):
            linked.add((cid, r.get("call_date")))
            ct = r.get("call_time") or ""
            if r["call_date"] != iso:
                ct = f"{_dm(r['call_date'])} {ct}".strip()
        day(iso)["items"][cid] = {"cid": cid, "n": names.get(cid) or r.get("company") or "",
                                  "p": r.get("period") or "", "c": bool(r.get("call_date")),
                                  "t": ct or "", "lg": logos.get(cid, ""), "url": r.get("report_url")}
    for c in calls:
        iso = c.get("date") or ""
        if iso < start:
            continue
        dd = day(iso)
        dd["calls"].append(c)
        cid = int(c["company_id"]) if c.get("company_id") else None
        # שיחה שאין לה הודעת פרסום ביום שלה ולא ביום אחר — עדיין חברה שמדווחת השבוע
        if cid and (cid, iso) not in linked and cid not in dd["items"]:
            dd["items"][cid] = {"cid": cid, "n": names.get(cid) or c.get("company") or "",
                                "p": c.get("period") or "", "c": True, "t": c.get("time") or "",
                                "lg": logos.get(cid, ""), "url": c.get("report_url"), "co": True}

    out: dict[str, dict] = {}
    for iso in sorted(days):
        d = days[iso]
        items = sorted(d["items"].values(), key=lambda it: (-caps.get(it["cid"], 0.0), it["n"]))
        wk = out.setdefault(_sunday(date.fromisoformat(iso)).isoformat(), {"days": []})
        wk["days"].append({"date": iso, "items": items, "calls": d["calls"]})
    return [{"start": k, **v} for k, v in sorted(out.items())]


def _columns(week: dict) -> list[str]:
    """שני–חמישי תמיד; ראשון ושישי כשיש בהם משהו."""
    have = {d["date"] for d in week["days"] if d["items"] or d["calls"]}
    sun = date.fromisoformat(week["start"])
    cols = []
    for k in range(6):                      # ראשון..שישי
        iso = (sun + timedelta(days=k)).isoformat()
        if 1 <= k <= 4 or iso in have:
            cols.append(iso)
    return cols


def week_range(week: dict) -> str:
    cols = _columns(week)
    a, b = cols[0], cols[-1]
    if a[5:7] == b[5:7]:
        return f"{int(a[8:10])}–{int(b[8:10])}.{int(b[5:7])}.{b[:4]}"
    return f"{_dm(a)}–{_dm(b)}.{b[:4]}"


def image(week: dict) -> dict:
    """מטען לכרטיס התמונה (site/export_card.js, גוש week), בערכת הלילה."""
    by = {d["date"]: d for d in week["days"]}
    days = []
    for iso in _columns(week):
        items = (by.get(iso) or {}).get("items") or []
        days.append({"label": DAY_HE[date.fromisoformat(iso).weekday()], "date": _dm(iso),
                     "items": [{"n": it["n"], "c": it["c"], "t": it["t"], "lg": it["lg"]}
                               for it in items[:MAX_DAY]],
                     "more": max(0, len(items) - MAX_DAY)})
    n_rep = sum(len(d["items"]) for d in week["days"])
    n_call = sum(1 for d in week["days"] for it in d["items"] if it["c"])
    card = otc.card(f"דוחות השבוע · {week_range(week)}",
                    f"{n_rep} חברות מפרסמות דוח כספי השבוע, {n_call} מהן מקיימות גם שיחת ועידה — "
                    "לפי ההודעות במאיה.",
                    [{"type": "week", "days": days}],
                    file=f"tlv-reports-week-{week['start']}",
                    kicker="לוח הדוחות והשיחות", source=SRC, theme="night")
    # שבוע עם ראשון ושישי — שש עמודות; ב-1200 האריחים צרים מכדי לשאת שם של שתי מילים
    if len(days) > 5:
        card["width"] = 1400
    return card


def chips(items: list[dict]) -> str:
    out = []
    for it in items:
        tip = " · ".join(x for x in (it.get("p"), ("שיחה " + it["t"]) if it.get("c") and it.get("t") else "") if x)
        body = escape(it["n"]) + (PHONE_SVG if it.get("c") else "")
        tag = (f'<a class="rc-chip{" rc-call" if it.get("c") else ""}" href="{escape(it["url"])}" '
               f'target="_blank" rel="noopener" title="{escape(tip)}">{body}</a>') if it.get("url") else \
              f'<span class="rc-chip{" rc-call" if it.get("c") else ""}" title="{escape(tip)}">{body}</span>'
        out.append(tag)
    return "".join(out)
