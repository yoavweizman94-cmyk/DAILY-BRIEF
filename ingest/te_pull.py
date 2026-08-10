# -*- coding: utf-8 -*-
"""Trading Economics — לוח אירועים כלכליים, תשואות אג"ח ממשלתיות ואינדיקטורים.

זה המקור שסוגר שני חורים ותיקים בברייף:
1. `il_gov_10y` — תשואת הממשלתי השקלי ל-10 שנים, שעד היום הגיעה רק אם מישהו
   הזכיר אותה בכתבה. כאן היא נתון מובנה.
2. "מה לעקוב היום" — עד כה נבנה מדיווחי מאיה בלבד; כעת עם לוח אירועים אמיתי
   הכולל תחזית קונצנזוס וערך קודם.

דורש TRADINGECONOMICS_KEY בסביבה או ב-.env, בפורמט "key:secret".
בלי מפתח הסקריפט יוצא בקוד 1 עם הודעה — כמו שאר המקורות, run_daily ימשיך.

פלט: data/raw/<YYYY-MM-DD>/te.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden
harden()

import requests
import yaml

from _env import load_env

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.tradingeconomics.com"


CALL_GAP_SEC = 2.0      # TE חונק קריאות רצופות; בלי המרווח הקריאה השלישית נופלת


class NotInPlan(Exception):
    """המנוי אינו כולל את הנתון — לא תקלה, פשוט מחוץ למסלול."""


def fetch(session, key: str, path: str, _retry: bool = True, **params):
    r = session.get(f"{BASE}{path}", params={"c": key, "f": "json", **params}, timeout=45)
    if r.status_code == 401:
        raise SystemExit("שגיאה: TRADINGECONOMICS_KEY נדחה (401) — מפתח לא תקף")
    if r.status_code in (403, 409):
        body = r.text[:160].strip()
        # TE מחזיר 403 גם על חנק קצב וגם על פיצ'ר שאינו במנוי, עם אותו קוד.
        # ההבחנה היא לפי הטקסט — בלעדיה חנק זמני נרשם כ"לא במנוי" ומטעה.
        if "slow down" in body.lower():
            if _retry:
                time.sleep(8)
                return fetch(session, key, path, _retry=False, **params)
            raise RuntimeError(f"חנק קצב של Trading Economics גם אחרי המתנה: {body}")
        raise NotInPlan(body)
    r.raise_for_status()
    if not (r.headers.get("content-type") or "").startswith("application/json"):
        raise RuntimeError(f"תשובה לא-JSON מ-{path}: {r.text[:120]}")
    return r.json()


def main() -> int:
    load_env()
    key = os.environ.get("TRADINGECONOMICS_KEY")
    if not key:
        print("שגיאה: TRADINGECONOMICS_KEY לא מוגדר — מדלגים על Trading Economics",
              file=sys.stderr)
        return 1

    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    tcfg = cfg.get("trading_economics") or {}
    countries = tcfg.get("calendar_countries") or ["israel", "united states"]
    horizon = int(tcfg.get("calendar_days_ahead", 7))
    want_bonds = set(tcfg.get("bonds") or [])

    s = requests.Session()
    today = date.today()
    out: dict = {"generated_at": datetime.now().isoformat(timespec="seconds"),
                 "date": today.isoformat(), "failures": []}

    # -- לוח אירועים: מהיום ועד horizon ימים קדימה -------------------------
    try:
        frm, to = today.isoformat(), (today + timedelta(days=horizon)).isoformat()
        events = fetch(s, key, f"/calendar/country/{','.join(countries)}/{frm}/{to}")
        out["calendar"] = [{
            "date": e.get("Date"), "country": e.get("Country"),
            "event": e.get("Event"), "category": e.get("Category"),
            "importance": e.get("Importance"), "unit": e.get("Unit"),
            "actual": e.get("Actual"), "previous": e.get("Previous"),
            "forecast": e.get("Forecast"), "te_forecast": e.get("TEForecast"),
        } for e in events if isinstance(e, dict)]
    except NotInPlan as ex:
        out["calendar"] = []
        out["calendar_unavailable"] = f"המנוי אינו כולל לוח אירועים: {ex}"
        print("הערה: לוח האירועים אינו כלול במנוי — מדלגים עליו", file=sys.stderr)
    except SystemExit:
        raise
    except Exception as ex:
        out["calendar"] = []
        out["failures"].append({"source": "calendar", "error": str(ex)})

    # -- תשואות אג"ח ממשלתיות ---------------------------------------------
    time.sleep(CALL_GAP_SEC)
    try:
        bonds = fetch(s, key, "/markets/bonds")
        rows = []
        for b in bonds:
            if not isinstance(b, dict):
                continue
            name = (b.get("Name") or b.get("Symbol") or "").strip()
            if want_bonds and not any(w.lower() in name.lower() for w in want_bonds):
                continue
            rows.append({"name": name, "symbol": b.get("Symbol"),
                         "yield": b.get("Last"), "daily": b.get("DailyChange"),
                         "weekly": b.get("WeeklyChange"), "monthly": b.get("MonthlyChange"),
                         "asof": b.get("Date")})
        out["bonds"] = rows
        il = next((r for r in rows if "israel" in (r["name"] or "").lower()
                   and "10y" in (r["name"] or "").lower()), None)
        out["il_gov_10y"] = il          # הנתון שהיה חסר בפייפליין
    except (SystemExit, NotInPlan) as ex:
        if isinstance(ex, SystemExit):
            raise
        out["bonds"], out["il_gov_10y"] = [], None
        out["failures"].append({"source": "bonds", "error": f"לא במנוי: {ex}"})
    except Exception as ex:
        out["bonds"], out["il_gov_10y"] = [], None
        out["failures"].append({"source": "bonds", "error": str(ex)})

    # -- אינדיקטורים מרכזיים לישראל ---------------------------------------
    time.sleep(CALL_GAP_SEC)
    try:
        ind = fetch(s, key, "/country/israel")
        wanted = {w.lower() for w in (tcfg.get("indicators") or [])}
        out["indicators"] = [{
            "category": i.get("Category"), "title": i.get("Title"),
            "value": i.get("LatestValue"), "unit": i.get("Unit"),
            "date": i.get("LatestValueDate"), "previous": i.get("PreviousValue"),
            "frequency": i.get("Frequency"),
        } for i in ind if isinstance(i, dict)
            and (not wanted or (i.get("Category") or "").lower() in wanted)]
    except (SystemExit, NotInPlan) as ex:
        if isinstance(ex, SystemExit):
            raise
        out["indicators"] = []
        out["failures"].append({"source": "indicators", "error": f"לא במנוי: {ex}"})
    except Exception as ex:
        out["indicators"] = []
        out["failures"].append({"source": "indicators", "error": str(ex)})

    out_dir = ROOT / "data" / "raw" / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "te.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    il = out.get("il_gov_10y")
    print(f"נכתב {path} | אירועים={len(out.get('calendar', []))} "
          f"אג\"ח={len(out.get('bonds', []))} אינדיקטורים={len(out.get('indicators', []))} "
          f"| ישראל 10ש={(il or {}).get('yield', 'לא נמצא')}")
    for f in out["failures"]:
        print(f"  ⚠ {f['source']}: {f['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
