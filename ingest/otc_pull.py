# -*- coding: utf-8 -*-
"""כל העסקאות מחוץ לבורסה, מהסקירה היומית של הבורסה.

למה מקור נוסף ל-offex_pull: מאיה מדווחת רק על עסקאות שצד בהן הוא בעל
עניין (ת076/ת078/ת079) או רכישה עצמית (ת085). עסקה שאף צד בה אינו בעל
עניין אינה מחייבת דיווח ולכן אינה במאיה כלל — וזה רוב השוק. הסקירה
היומית של הבורסה מפרסמת את **כולן**, אך בלי זהות הצדדים.

לכן שני המקורות משלימים ואינם מחליפים: כאן שלמות, שם זהות.

נגזר כאן ואינו במקור:
· **שער בסיס.** `Change` בסקירת הנייר מחושב מולו, ולכן
  base = LastRate / (1 + Change/100). זה מחזיר את הסגירה הקודמת
  כשלא הייתה התאמה, ואת השער המותאם כשהייתה (דיבידנד, פיצול).
· **פרמיה/דיסקאונט** של מחיר העסקה מול אותו בסיס — השאלה האמיתית
  בעסקה מחוץ לבורסה: באיזה מחיר הסכימו הצדדים ביחס לשוק.
· **חלק מהמחזור היומי** של אותו נייר. עסקה של מיליון ש"ח בנייר
  שנסחר במיליארד אינה אותה עסקה כמו בנייר שנסחר בשניים.

השהיית הפרסום היא 15 דקות, ולכן ריצת אמצע-יום אינה מלאה. ההשלמה
מגיעה בריצה של יום המסחר הבא (dType=2).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tls import harden  # noqa: E402

harden()

import yaml  # noqa: E402
from curl_cffi import requests as creq  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "otc"
STATE = ROOT / "data" / "otc_state.json"
CFG = ROOT / "config" / "companies.yaml"

API = "https://api.tase.co.il/api"
SEED = "https://market.tase.co.il/he/market_data/daily-review/otc"

# מניות הן קוד 0. שאר הקודים (אג"ח, מק"מ, קרנות סל, יחידות השתתפות)
# נשמרים גם הם, אך העמוד מציג אותם בנפרד — הבקשה הייתה מניות.
SHARE = "0"


class Tase:
    """המקור חוסם ספריות HTTP רגילות; חיקוי דפדפן + עוגיות מדף הסקירה."""

    def __init__(self, throttle: float = 0.3):
        self.s = creq.Session(impersonate="chrome")
        self.s.headers.update({
            "Accept": "application/json",
            "Referer": "https://market.tase.co.il/",
            "Origin": "https://market.tase.co.il",
        })
        self.s.get(SEED, timeout=45)
        self.throttle = throttle
        self._last = 0.0
        self._major: dict[tuple, dict] = {}

    def _wait(self):
        dt = self.throttle - (time.monotonic() - self._last)
        if dt > 0:
            time.sleep(dt)
        self._last = time.monotonic()

    def _post(self, path: str, body: dict):
        last = None
        for i in range(3):
            try:
                self._wait()
                r = self.s.post(f"{API}/{path}", timeout=45,
                                headers={"Content-Type": "application/json"},
                                data=json.dumps(body))
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(2 * (i + 1))
        raise last

    def otc(self, dtype: int) -> tuple[str | None, list[dict]]:
        """כל עסקאות היום המבוקש. dType: 1 = היום, 2 = יום המסחר הקודם.

        `pageNum` אינו אופציונלי — בלעדיו התשובה היא 200 עם אפס רשומות,
        וזה נראה כמו יום בלי עסקאות ולא כמו בקשה שגויה.
        """
        items: list[dict] = []
        page, total, trade_date = 1, None, None
        while True:
            d = self._post("marketdata/otctransactions",
                           {"lang": 0, "dType": dtype, "pageNum": page})
            batch = d.get("Items") or []
            trade_date = trade_date or d.get("TradeDate")
            total = d.get("TotalRec") if total is None else total
            items += batch
            if not batch or len(items) >= (total or 0) or page > 40:
                break
            page += 1
        return trade_date, items

    def major(self, sec_id: str, comp_id: str) -> dict:
        key = (sec_id, comp_id)
        if key not in self._major:
            try:
                self._wait()
                r = self.s.get(f"{API}/security/majordata", timeout=45,
                               params={"secId": sec_id, "compId": comp_id, "lang": 0})
                self._major[key] = r.json() if r.status_code == 200 else {}
            except Exception:  # noqa: BLE001
                self._major[key] = {}
        return self._major[key]


def day_row(major: dict, ddmmyyyy: str) -> dict | None:
    for row in major.get("LastDaysData") or []:
        if row.get("TradeDate") == ddmmyyyy:
            return row
    return None


def coverage() -> dict[int, str]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    rows = cfg["companies"] if isinstance(cfg, dict) and "companies" in cfg else cfg
    return {int(c["tase_id"]): c["name_he"] for c in rows if c.get("tase_id")}


def deal_id(rec: dict) -> str:
    raw = f"{rec['security_id']}|{rec['traded_at']}|{rec['price']}|{rec['units']}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def clean(it: dict, t: Tase, cov: dict, src: str = "review") -> dict | None:
    """`src` מבחין בין שני משטרי איסוף, וההבחנה אינה קוסמטית.

    "review" הוא יום שנמשך מהסקירה היומית ולכן **שלם** — כל עסקאות
    השוק. "security" הוא היסטוריה שנמשכה נייר-נייר לחברות הכיסוי, ולכן
    יום כזה מכיל רק אותן. חישוב מחזור יומי או מגמה שמערבב את השניים
    משווה שוק שלם לתת-קבוצה — נמדד: קפיצה מדומה של 8,600%.
    """
    stamp = (it.get("TradeDate") or "").strip()
    if not stamp:
        return None
    d, _, clock = stamp.partition(" ")
    try:
        iso = datetime.strptime(d, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None
    price = it.get("Price")
    if not price:
        return None

    sec_id = (it.get("Id") or "").lstrip("0") or (it.get("ShareId") or "").lstrip("0")
    rec = {
        "date": iso,
        "traded_at": f"{iso} {clock}".strip(),
        "security_id": sec_id,
        "company_id": it.get("CompanyId"),
        "name": (it.get("Name") or "").strip(),
        "symbol": (it.get("Symbol") or "").strip(),
        "sec_type": (it.get("Type") or "").strip(),
        "is_share": it.get("SecurityTypeInSite") == SHARE,
        "isin": it.get("ISIN"),
        "price": round(float(price), 2),
        "value": round(float(it.get("TurnOver") or 0)),
        "units": round(float(it.get("TurnOverUnits") or 0)),
        "intraday": bool(it.get("InDay")),
        "src": src,
    }
    rec["deal_id"] = deal_id(rec)

    # שער בסיס וחלק מהמחזור — שניהם מסקירת הנייר, ושניהם עשויים לחסר
    # ביום שטרם נסגר. חסר נאמר כ-null ולא מושלם בניחוש.
    row = day_row(t.major(sec_id, it.get("CompanyId") or ""), d) if sec_id else None
    if row and row.get("LastRate") and row.get("Change") is not None:
        base = row["LastRate"] / (1 + row["Change"] / 100)
        rec["base_rate"] = round(base, 2)
        rec["premium_pct"] = round((rec["price"] / base - 1) * 100, 2)
        rec["day_close"] = row["LastRate"]
        rec["vs_close_pct"] = round((rec["price"] / row["LastRate"] - 1) * 100, 2)
    turnover = (row or {}).get("TurnOver1000")
    if turnover:
        rec["day_turnover"] = round(turnover * 1000)
        rec["pct_of_day"] = round(rec["value"] / (turnover * 1000) * 100, 2)

    name = cov.get(int(sec_id)) if sec_id.isdigit() else None
    rec["covered"] = bool(name)
    if name:
        rec["coverage_name"] = name
    return rec


def merge(recs: list[dict]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, dict] = {}
    for r in recs:
        by_year.setdefault(r["date"][:4], {})[r["deal_id"]] = r
    added = 0
    for yr, fresh in by_year.items():
        path = OUT / f"{yr}.jsonl"
        have = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    o = json.loads(line)
                    have[o["deal_id"]] = o
        added += len([k for k in fresh if k not in have])
        # רשומת אמצע-יום מוחלפת בגרסה הסופית של אותה עסקה. אך רשומה
        # שנראתה בסקירה היומית לא תרד ל-"security": מקור היום קובע
        # אם אפשר להתייחס אליו כאל יום שלם.
        for k, v in fresh.items():
            old = have.get(k)
            if old and old.get("src") == "review" and v.get("src") != "review":
                v = {**v, "src": "review"}
            have[k] = v
        rows = sorted(have.values(), key=lambda r: (r["traded_at"], r["deal_id"]))
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")
    return added


def backfill(t: Tase, cov: dict) -> list[dict]:
    """היסטוריית העסקאות של חברות הכיסוי, נייר-נייר.

    הסקירה היומית מוגשת יום אחד בכל פעם ואין בה טווח תאריכים; לעומתה
    `security/otctransactions` מחזיר כחודש אחורה לכל נייר. זה מה שמאפשר
    לעמוד להראות דפוס — נייר שחוזר בכמה ימים — ולא רק את היום האחרון.

    **שער הבסיס לא יושלם לרוב הרשומות האלה.** סקירת הנייר מחזיקה חמישה
    ימי מסחר בלבד, ולכן עסקה ישנה יותר נשמרת בלי שער ייחוס. חסר נאמר
    כ-null, ובעמוד הוא מוצג כמקף ואינו נספר בהתפלגות.
    """
    out: list[dict] = []
    for i, (tase_id, name) in enumerate(cov.items(), 1):
        try:
            d = t._post("security/otctransactions",
                        {"lang": 0, "oId": str(tase_id), "pageNum": 1})
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: {type(e).__name__} — מדולג", file=sys.stderr)
            continue
        items = d.get("Items") or []
        got = [c for c in (clean(it, t, cov, src="security") for it in items) if c]
        out += got
        if got:
            print(f"  [{i}/{len(cov)}] {name}: {len(got)} עסקאות")
    return out


def main() -> int:
    cov = coverage()
    t = Tase()
    days = [2, 1] if not os.environ.get("OTC_TODAY_ONLY") else [1]

    recs: list[dict] = []
    seen_days = []
    for dtype in days:
        label = "יום מסחר קודם" if dtype == 2 else "היום"
        try:
            trade_date, items = t.otc(dtype)
        except Exception as e:  # noqa: BLE001
            print(f"::error::{label}: {type(e).__name__}", file=sys.stderr)
            continue
        if not items:
            print(f"  {label}: אין עסקאות")
            continue
        got = [c for c in (clean(i, t, cov) for i in items) if c]
        shares = [c for c in got if c["is_share"]]
        covered = [c for c in shares if c["covered"]]
        print(f"  {label} ({trade_date}): {len(got)} עסקאות, "
              f"{len(shares)} במניות, {len(covered)} בחברות כיסוי")
        recs += got
        seen_days.append(trade_date)

    if os.environ.get("OTC_BACKFILL"):
        print("\nמילוי היסטורי לחברות הכיסוי:")
        recs += backfill(t, cov)

    if not recs:
        print("::error::לא נאספה ולו עסקה אחת", file=sys.stderr)
        return 1

    added = merge(recs)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "days": seen_days,
        "records": len(recs),
        "updated": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False), encoding="utf-8")

    val = sum(r["value"] for r in recs if r["is_share"])
    print(f"\nסה\"כ {len(recs)} עסקאות ({added} חדשות) | "
          f"מחזור במניות ₪{val:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
