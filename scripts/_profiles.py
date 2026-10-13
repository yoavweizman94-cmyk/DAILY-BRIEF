# -*- coding: utf-8 -*-
"""מה כל חברת כיסוי עושה — לפי תיאור הפעילות שהיא מסרה למאיה.

**למה זה קיים.** הניתוחים באתר נדרשים להסביר מה אירוע עושה לחברה מסוימת —
באיזה מגזר, דרך איזו שורה בדוח, ולמה היא חשופה יותר או פחות מהשכנות שלה. עד
13/10/2026 היה בידיהם רק שם וסקטור, וההוראה (בצדק) אסרה לייחס לחברה תמהיל
עסקי מהזיכרון — כך שההסבר נעצר ברמת "השפעה על הענף". תיאור הפעילות ממאיה
נותן את מה שחסר ממקור: "החברה עוסקת במתן שירותי פיתוח ועיבוד של מוליכים
למחצה..." מספיק כדי להבחין בין פאונדרי ליצרנית ציוד, או בין יזם לקבלן ביצוע.

הקובץ נבנה ב-ingest/capital_pull.py (data/company_profiles.json), מאותה
קריאה שמביאה את ההון המונפק.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "company_profiles.json"
MAX_ACT = 150


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load() -> dict[str, dict]:
    return _data().get("companies") or {}


def updated() -> str:
    return str(_data().get("updated") or "")


def cap_text(m) -> str:
    """שווי שוק במיליוני ש"ח, כטקסט: "75.7 מיליארד ₪" / "830 מ׳ ₪"."""
    if not m:
        return ""
    return f"{m / 1000:,.1f} מיליארד ₪" if m >= 1000 else f"{m:,.0f} מ׳ ₪"


def activity(name: str, limit: int = MAX_ACT) -> str:
    act = (load().get(name) or {}).get("activity") or ""
    if len(act) > limit:
        act = act[:limit].rsplit(" ", 1)[0] + "…"
    return act


def line(name: str, cap: bool = False, limit: int = MAX_ACT) -> str:
    """"פעילות · ענף [· שווי שוק]" לחברה אחת, או ריק כשאין לה פרופיל.

    **שווי השוק רק כשמבקשים.** בניתוחים שיש בהם בדיקת מספרים מול המקור (רגולציה,
    רכב) מספר מהבלוק הזה היה נפסל, ולכן שם הבלוק נושא רק את הפעילות.
    """
    p = load().get(name) or {}
    parts = [activity(name, limit), p.get("branch") or ""]
    if cap and p.get("market_cap_m"):
        parts.append(f"שווי שוק {cap_text(p['market_cap_m'])}")
    return " · ".join(x for x in parts if x)


def block(names, cap: bool = False, limit: int = MAX_ACT) -> str:
    """בלוק לפרומפט: שורה לכל חברה שיש לה פרופיל, בסדר שבו הופיעה. ריק כשאין."""
    seen, rows = set(), []
    for n in names:
        if not n or n in seen:
            continue
        seen.add(n)
        text = line(n, cap=cap, limit=limit)
        if text:
            rows.append(f"- {n}: {text}")
    if not rows:
        return ""
    when = f", {updated()}" if updated() else ""
    return (f"=== מה החברות עושות (תיאור הפעילות שמסרו למאיה{when}) ===\n"
            + "\n".join(rows))
