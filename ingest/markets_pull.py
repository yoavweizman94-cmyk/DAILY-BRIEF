# -*- coding: utf-8 -*-
"""משיכת נתוני שוק: שערים יציגים מבנק ישראל + yfinance.

- כל ערך נשמר ל-data/state.sqlite (prices: key, date, value).
- שינוי יומי/שבועי/חודשי מחושב מול ה-state (לא מול המקור), כך שהמתודולוגיה אחידה.
- בריצה ראשונה נזרעת היסטוריה של ~40 יום מ-yfinance כדי ששינויים יהיו זמינים מייד;
  לשערי BOI נצבר state עם הזמן (שינוי יומי מגיע מה-API עצמו גם בלי היסטוריה).
- מקור שנכשל נרשם ב-failures ולא מפיל את הריצה — הסוכן מדווח "תקלות מקורות".

פלט: data/raw/<YYYY-MM-DD>/markets.json
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden
harden()

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "state.sqlite"
TODAY = date.today().isoformat()
OUT_DIR = ROOT / "data" / "raw" / TODAY

YIELD_GROUPS = {"yields"}          # שינוי מדווח בנקודות (pp), לא באחוזים
WEEKLY_SLACK_DAYS = 10             # כמה אחורה מוכנים ללכת מהיעד לפני שמוותרים
MONTHLY_SLACK_DAYS = 15


from _state import connect as db


def upsert(con, key: str, d: str, value: float):
    con.execute("INSERT OR REPLACE INTO prices (key, date, value) VALUES (?,?,?)",
                (key, d, float(value)))


def ref_value(con, key: str, target: date, slack_days: int) -> float | None:
    """הערך השמור העדכני ביותר שתאריכו ≤ target ולא ישן מ-target-slack."""
    lo = (target - timedelta(days=slack_days)).isoformat()
    row = con.execute(
        "SELECT value FROM prices WHERE key=? AND date<=? AND date>=? ORDER BY date DESC LIMIT 1",
        (key, target.isoformat(), lo)).fetchone()
    return row[0] if row else None


def changes(con, key: str, asof: date, value: float, kind: str) -> dict:
    """kind='pct' → אחוזים; kind='pp' → הפרש נקודות."""
    out = {}
    prev = con.execute(
        "SELECT value FROM prices WHERE key=? AND date<? ORDER BY date DESC LIMIT 1",
        (key, asof.isoformat())).fetchone()
    refs = {"daily": prev[0] if prev else None,
            "weekly": ref_value(con, key, asof - timedelta(days=7), WEEKLY_SLACK_DAYS),
            "monthly": ref_value(con, key, asof - timedelta(days=30), MONTHLY_SLACK_DAYS)}
    for name, ref in refs.items():
        if ref is None or value is None:
            out[name] = None
        elif kind == "pp":
            out[name] = round(value - ref, 3)
        else:
            out[name] = round((value / ref - 1) * 100, 2) if ref else None
    return out


def pull_boi(cfg, con, failures) -> dict:
    out = {}
    try:
        r = requests.get(cfg["boi"]["api"], timeout=30)
        r.raise_for_status()
        rates = {x["key"]: x for x in r.json()["exchangeRates"]}
    except Exception as ex:
        failures.append({"source": "BOI", "error": str(ex)})
        return out
    for cur in cfg["boi"]["currencies"]:
        x = rates.get(cur)
        if not x:
            failures.append({"source": "BOI", "error": f"מטבע {cur} חסר בתשובה"})
            continue
        val = x["currentExchangeRate"]
        asof = datetime.fromisoformat(x["lastUpdate"].replace("Z", "+00:00")).date()
        key = f"fx_{cur.lower()}_ils"
        upsert(con, key, asof.isoformat(), val)
        chg = changes(con, key, asof, val, "pct")
        if chg["daily"] is None:                      # אין עדיין state — ניקח מה-API
            chg["daily"] = round(x.get("currentChange", 0.0), 2)
        out[key] = {"label": f"{cur}/ILS", "value": val, "unit": x.get("unit", 1),
                    "asof": asof.isoformat(), "source": "BOI", "changes": chg}
    return out


def pull_yfinance(cfg, con, failures) -> dict:
    try:
        import yfinance as yf
    except ImportError as ex:
        failures.append({"source": "yfinance", "error": f"החבילה חסרה: {ex}"})
        return {}
    out = {}
    for inst in cfg["yfinance"]:
        key, ticker = inst["key"], inst["ticker"]
        try:
            hist = yf.Ticker(ticker).history(period="40d", interval="1d",
                                             auto_adjust=False, raise_errors=True)
            if hist.empty:
                raise RuntimeError("היסטוריה ריקה")
        except Exception as ex:
            failures.append({"source": f"yfinance:{ticker}", "error": str(ex)})
            continue
        closes = hist["Close"].dropna()
        if inst.get("transform") == "tnx_div10":
            closes = closes / 10 if closes.iloc[-1] > 20 else closes
        for ts, v in closes.items():                  # זריעת/עדכון היסטוריה
            upsert(con, key, ts.date().isoformat(), float(v))
        asof = closes.index[-1].date()
        val = round(float(closes.iloc[-1]), 4)
        kind = "pp" if inst.get("group") in YIELD_GROUPS else "pct"
        # ריצת הבוקר מקדימה את פרסום הסגירה של חלק מהמכשירים (במיוחד מדדי ארה"ב),
        # ואז asof מפגר. בלי סימון, "שינוי יומי" נקרא כאילו הוא תזוזת היום.
        stale = (date.today() - asof).days
        out[key] = {"label": inst["label"], "ticker": ticker, "group": inst.get("group"),
                    "proxy": bool(inst.get("proxy")), "value": val,
                    "asof": asof.isoformat(), "stale_days": stale, "source": "yfinance",
                    "change_unit": "pp" if kind == "pp" else "%",
                    "changes": changes(con, key, asof, val, kind)}
    return out


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))["markets"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = db()
    failures: list[dict] = []

    fx = pull_boi(cfg, con, failures)
    instruments = pull_yfinance(cfg, con, failures)
    con.commit()

    il10 = cfg.get("il_gov_10y", {})
    stale = sorted(k for k, v in instruments.items() if v.get("stale_days", 0) > 0)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": TODAY,
        # מכשירים שה-asof שלהם אינו היום — הברייף חייב לציין את תאריך הנתון לצידם
        "stale_instruments": stale,
        "fx": fx,
        "instruments": instruments,
        "il_gov_10y": None if not il10.get("enabled") else il10,
        "il_gov_10y_note": il10.get("note"),
        "failures": failures,
    }
    out_path = OUT_DIR / "markets.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"נכתב {out_path} | fx={len(fx)} instruments={len(instruments)} failures={len(failures)}")
    for f in failures:
        print(f"  ⚠ {f['source']}: {f['error']}", file=sys.stderr)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
