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
# כמו הפוסט "דוחות השבוע" ב-Claude Design (26/11/2026), מילה במילה
SRC = "מקור: לוח האירועים במערכת מאיה של הבורסה לניירות ערך, מועדי פרסום הדוחות ושיחות הוועידה"
# רוחב הלוחות בתמונה — אותם מספרים כמו NW ב-site/export_card.js: לוח של יום עם שלוש חברות
# לכל היותר צר (טור אחד), והשאר בשני טורים. רוחב התמונה נגזר מהם.
WIDE, NARROW, DAY_GAP, NIGHT_PAD = 318, 167, 18, 56


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
        ct, tm, od = None, "", ""
        if r.get("call_date"):
            linked.add((cid, r.get("call_date")))
            ct = tm = r.get("call_time") or ""
            if r["call_date"] != iso:
                od = r["call_date"]
                ct = f"{_dm(od)} {ct}".strip()
        # t — לעמוד (תאריך ושעה יחד); tm ו-od — לתמונה: שעה, או "ב־<תאריך>" לשיחה ביום אחר
        day(iso)["items"][cid] = {"cid": cid, "n": names.get(cid) or r.get("company") or "",
                                  "p": r.get("period") or "", "c": bool(r.get("call_date")),
                                  "t": ct or "", "tm": tm, "od": od,
                                  "lg": logos.get(cid, ""), "url": r.get("report_url")}
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
                                "tm": c.get("time") or "", "od": "",
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


def _shown(items: list[dict]) -> list[dict]:
    """החברות של יום בתמונה, בסדר של הקנבס: שיחות לפי השעה (המוקדמת ראשונה), אחריהן שיחות
    ביום אחר, ואחריהן דוח בלבד. **הבחירה לפני המיון**: MAX_DAY הגדולות לפי שווי השוק, כדי
    שחברה גדולה בלי שיחה לא תיפול מהתמונה רק בגלל סדר התצוגה. בתוך קבוצה — לפי השווי."""
    def key(it: dict) -> tuple:
        if it["c"] and it.get("tm") and not it.get("od"):
            return (0, it["tm"], "")
        if it["c"]:
            return (1, it.get("od") or "", it.get("tm") or "")
        return (2, "", "")
    return sorted(items[:MAX_DAY], key=key)


def image(week: dict) -> dict:
    """מטען לכרטיס התמונה (site/export_card.js, גוש week), בערכת הלילה — כמו הפוסט
    "דוחות השבוע" ב-Claude Design (יואב, 26/11/2026)."""
    by = {d["date"]: d for d in week["days"]}
    days = []
    for iso in _columns(week):
        items = (by.get(iso) or {}).get("items") or []
        days.append({"label": DAY_HE[date.fromisoformat(iso).weekday()], "date": _dm(iso), "iso": iso,
                     "n": len(items), "nc": sum(1 for it in items if it["c"]),
                     "items": [{"n": it["n"], "c": it["c"], "t": it.get("tm") or "",
                                "o": _dm(it["od"]) if it.get("od") else "", "lg": it["lg"]}
                               for it in _shown(items)],
                     "more": max(0, len(items) - MAX_DAY)})
    n_rep = sum(len(d["items"]) for d in week["days"])
    n_call = sum(1 for d in week["days"] for it in d["items"] if it["c"])
    card = otc.card(f"דוחות השבוע · {week_range(week)}",
                    "החברות שמפרסמות דוח כספי השבוע ושיחות הוועידה שלהן, לפי ההודעות במאיה.",
                    [{"type": "week", "days": days}],
                    file=f"tlv-reports-week-{week['start']}",
                    kicker="לוח הדוחות והשיחות", source=SRC, theme="night")
    # הגיבור כמו בקנבס: הכותרת והתאריך בשורה אחת, התאריך בזהב מדורג, שני שבבי ספירה
    # מתחת לשורת ההסבר — ובלי המפריד שבין הגיבור לגוף.
    stats = [{"v": n_rep, "t": "דוח כספי" if n_rep == 1 else "דוחות כספיים"}]
    if n_call:      # "0 עם שיחת ועידה" אינו מידע — השבב יורד
        stats.append({"v": n_call, "t": "עם שיחת ועידה", "call": True})
    card.update({"heroInline": True, "gilt": True, "divider": False, "heroStats": stats})
    cards_n = [len(d["items"]) + (1 if d["more"] else 0) for d in days]
    card["width"] = max(1200, 2 * NIGHT_PAD + DAY_GAP * (len(days) - 1)
                        + sum(NARROW if k <= 3 else WIDE for k in cards_n))
    return card


def chips(items: list[dict]) -> str:
    """שבב לכל חברה. **בלי סמל טלפון בעמוד** — יואב, 10/11/2026: הסמל רק בתמונת הייצוא.
    בעמוד חברה עם שיחה מסומנת במסגרת בצבע ההדגשה, והשעה בתיבת הרמז ובטבלת השיחות."""
    out = []
    for it in items:
        tip = " · ".join(x for x in (it.get("p"), ("שיחת ועידה " + it["t"]) if it.get("c") and it.get("t")
                                     else ("שיחת ועידה" if it.get("c") else "")) if x)
        body = escape(it["n"])
        tag = (f'<a class="rc-chip{" rc-call" if it.get("c") else ""}" href="{escape(it["url"])}" '
               f'target="_blank" rel="noopener" title="{escape(tip)}">{body}</a>') if it.get("url") else \
              f'<span class="rc-chip{" rc-call" if it.get("c") else ""}" title="{escape(tip)}">{body}</span>'
        out.append(tag)
    return "".join(out)
