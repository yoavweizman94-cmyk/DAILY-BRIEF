# -*- coding: utf-8 -*-
"""שכבת הנתונים של שרת ה-MCP: site/dist/mcp/*.json.

הפונקציה ב-site/functions/api/mcp/ רצה ב-Cloudflare ואין לה גישה לריפו
התוכן — רק לנכסים הסטטיים של אותה פריסה. לכן כל מה שהכלים שלה מגישים
נכתב כאן, בזמן הבנייה, כ-JSON קטן לצד עמודי ה-HTML. אותם לואדרים ואותו
חישוב שמזינים את העמודים מזינים גם את הקבצים האלה, ולכן אי אפשר שהאתר
והכלי יגידו שני מספרים שונים.

**קטן בכוונה.** כל קובץ נקרא בשלמותו בכל קריאת כלי, ולכן יש כאן חיתוך —
ימים אחרונים, שדות נבחרים, רשימות קצוצות — ולא העתק של output/.
הברייפים עצמם נשמרים כ-markdown גולמי, אחד לקובץ, כי הכלי מגיש אותם
כפי שהם; הסוכן שקורא אותם מעדיף טקסט על HTML.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import nadlan
import nadlan_stats as ns

ROOT = Path(__file__).resolve().parents[1]

DAYS_OTC = 10        # עסקאות מחוץ לבורסה ומתואמות
DAYS_REPORTS = 5     # כמו load_reports: חמשת הקבצים האחרונים
MAX_HEADLINES = 80
MAX_CBS = 40
MAX_COMMODITY_ITEMS = 60
MAX_HOODS = 8        # שכונות לעיר בשוק הדיור


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def _since(days: int) -> str:
    return (datetime.now().date() - timedelta(days=days)).isoformat()


def _pick(d: dict, keys: tuple) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] not in (None, "", [], {})}


REPORT_KEYS = ("ts", "companies", "coverage", "materiality", "direction", "headline",
               "title", "summary", "key_figures", "trend", "context", "analysis",
               "balance", "flags", "omissions", "why", "affected", "affected_why",
               "watch", "url", "kind")
COMPANY_KEYS = ("name_he", "name_en", "aliases", "listing", "tase_id", "sector",
                "tase_sector", "maya_company_id", "generic_name", "drivers_extra")
CALL_KEYS = ("company", "date", "time", "period", "link", "link_certain",
             "ambiguous", "other_links", "report_url", "coverage")
HEADLINE_KEYS = ("id", "ts", "headline", "summary", "why", "level", "companies",
                 "sources", "topics")
CITY_KEYS = ("region", "n", "n_new", "n_used", "ppsm", "ppsm_new", "ppsm_used",
             "premium_new", "price", "area", "quarters", "level", "qoq", "yoy",
             "used_yoy", "share_new", "share_new_prev", "vol", "vol_prev",
             "vol_change", "by_rooms", "label", "why", "mix_flag", "thin")


def housing(rows: list[dict]) -> dict:
    """אותו חישוב כמו עמוד שוק הדיור, בלי ה-HTML."""
    if not rows:
        return {"market": None, "cities": {}, "note": "טרם נאספו עסקאות"}
    clean, drop = ns.clean_rows(rows)
    if not clean:
        return {"market": None, "cities": {}, "dropped": drop,
                "note": "אף עסקה אינה דירת מגורים בטווח מחיר אפשרי"}
    st = ns.city_stats(clean)
    m = ns.market(clean, st)
    cities = {}
    for city, v in st.items():
        c = _pick(v, CITY_KEYS)
        c["hoods"] = (v.get("hoods") or [])[:MAX_HOODS]
        cities[city] = c
    try:
        missing = nadlan.missing_cities(set(st))
    except Exception:  # noqa: BLE001 — רשימת ערים חסרה אינה סיבה להפיל בנייה
        missing = []
    return {
        "market": m, "cities": cities, "dropped": drop,
        "cities_without_deals": missing,
        "cutoff_month": ns.cutoff_month(),
        "caveats": [
            "פיגור דיווח: רשות המסים מדווחת כשישה שבועות אחרי העסקה; החודשיים "
            "האחרונים אינם נכללים.",
            "מדגם ולא מפקד: בכל עיר נסרקות כמה שכונות.",
            "ההשוואה רבעונית. qoq/yoy הם שינוי בחציון ₪/מ״ר; used_yoy על יד שנייה "
            "בלבד; mix_flag=true פירושו שהפער ביניהם הוא תמהיל ולא מחיר.",
            "המצרף הארצי הוא חציון השינויים של הערים, לא חציון כל העסקאות.",
        ],
    }


def export(out: Path, *, briefs: list[tuple[str, str, str, Path]], markets, te,
           reports: list[dict], calls: list[dict], coverage: dict,
           nadlan_rows: list[dict], otc_rows: list[dict], offex_rows: list[dict],
           jumbo_rows: list[dict], topic_sums: dict, topic_day: str,
           topics_cfg: list[dict], digest: dict, cbs: dict, commod: dict) -> dict:
    """כותב את כל קבצי ה-MCP ומחזיר ספירות לדיווח בבנייה.

    briefs: (slug, edition, title, path) מהחדש לישן — כפי שהבנייה כבר מיינה.
    """
    d = out / "mcp"
    counts = {}

    # --- ברייפים: אינדקס + markdown גולמי לכל אחד ---------------------
    idx = []
    for slug, ed, title, p in briefs:
        (d / "briefs").mkdir(parents=True, exist_ok=True)
        (d / "briefs" / f"{slug}.md").write_text(p.read_text(encoding="utf-8"),
                                                 encoding="utf-8")
        idx.append({"slug": slug, "date": slug[:10], "edition": ed or "morning",
                    "title": title})
    counts["briefs"] = len(idx)
    _dump(d / "index.json", {
        "built": datetime.now().isoformat(timespec="seconds"),
        "latest_date": idx[0]["date"] if idx else None,
        "briefs": idx,
        "datasets": ["markets", "reports", "calls", "coverage", "housing", "offex",
                     "topics", "headlines", "cbs", "commodities", "filings"],
    })

    # --- שווקים ומאקרו ----------------------------------------------------
    _dump(d / "markets.json", {"markets": markets, "te": te})

    # --- דיווחי מאיה מסוכמים ---------------------------------------------
    rep = [_pick(r, REPORT_KEYS) for r in reports]
    counts["reports"] = len(rep)
    _dump(d / "reports.json", {"reports": rep, "days": DAYS_REPORTS})

    # --- שיחות ועידה -------------------------------------------------------
    cl = [_pick(c, CALL_KEYS) for c in calls]
    counts["calls"] = len(cl)
    _dump(d / "calls.json", {"calls": cl})

    # --- רשימת הכיסוי ------------------------------------------------------
    cos = [_pick(c, COMPANY_KEYS) for c in (coverage.get("companies") or [])]
    profiles = {k: {"label": (v or {}).get("label"), "drivers": (v or {}).get("drivers")}
                for k, v in (coverage.get("sector_profiles") or {}).items()}
    counts["companies"] = len(cos)
    _dump(d / "coverage.json", {"companies": cos, "sector_profiles": profiles,
                                "meta": coverage.get("meta") or {}})

    # --- שוק הדיור ---------------------------------------------------------
    h = housing(nadlan_rows)
    counts["housing_cities"] = len(h.get("cities") or {})
    _dump(d / "housing.json", h)

    # --- מחוץ לבורסה: שלושת הערוצים ---------------------------------------
    cut = _since(DAYS_OTC)
    otc = [r for r in otc_rows if (r.get("date") or "") >= cut]
    off = [r for r in offex_rows if (r.get("date") or "") >= cut]
    jmb = [r for r in jumbo_rows if (r.get("date") or "") >= cut]
    counts["otc"] = len(otc)
    _dump(d / "offex.json", {
        "since": cut, "otc": otc, "offex": off, "jumbo": jmb,
        "notes": [
            "otc: סקירת הבורסה, בלי זהויות. premium_pct מול שער הבסיס ו-vs_close_pct "
            "מול הנעילה נקראים יחד; pct_of_day מעל 100% אינו שגיאה.",
            "offex: מאיה, עם זהות המדווח ושיעור מההון. partial=true מאגד עסקאות "
            "בתוך ומחוץ לבורסה; counted=false הוא הצד השני של עסקה שכבר נספרה.",
            "jumbo: עסקאות מתואמות מ-GTO, בלי מחיר לעסקה; final=false נאסף לפני "
            "סיום המסחר. יום בלי רשומות אינו עדות שלא היו.",
        ],
    })

    # --- סיכומי סקטורים ----------------------------------------------------
    labels = {t["slug"]: t.get("label") for t in topics_cfg if t.get("slug")}
    _dump(d / "topics.json", {"date": topic_day, "labels": labels,
                              "summaries": topic_sums})
    counts["topics"] = len(topic_sums)

    # --- כותרות --------------------------------------------------------------
    items = [_pick(r, HEADLINE_KEYS) for r in (digest.get("items") or [])[:MAX_HEADLINES]]
    counts["headlines"] = len(items)
    _dump(d / "headlines.json", {"hours": digest.get("hours"), "items": items})

    # --- למ"ס ------------------------------------------------------------------
    rel = (cbs.get("releases") or [])[:MAX_CBS]
    an = cbs.get("analyses") or {}
    _dump(d / "cbs.json", {
        "snapshot": cbs.get("snap") or {},
        "releases": rel,
        "analyses": {k: an[k] for k in (str(r.get("id")) for r in rel) if k in an},
    })
    counts["cbs"] = len(rel)

    # --- סחורות ------------------------------------------------------------------
    snaps = commod.get("snaps") or []
    analyses = commod.get("analyses") or []
    _dump(d / "commodities.json", {
        "latest": snaps[-1] if snaps else None,
        "previous": snaps[-2] if len(snaps) > 1 else None,
        "items": (commod.get("items") or [])[:MAX_COMMODITY_ITEMS],
        "analysis": analyses[-1] if analyses else None,
    })
    counts["commodity_items"] = min(len(commod.get("items") or []), MAX_COMMODITY_ITEMS)

    return counts
