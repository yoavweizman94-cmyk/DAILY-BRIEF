#!/usr/bin/env python3
"""עסקאות מניה מחוץ לבורסה, מטופס ת076 של מאיה.

**מה הדוח הזה כן ולא מכסה.** ת076 הוא "דוח מיידי על שינויים בהחזקות בעלי
עניין ונושאי משרה בכירה", ולכן הוא תופס עסקאות שצד אחד בהן לפחות הוא בעל
עניין או נושא משרה. עסקה מחוץ לבורסה בין שני צדדים שאינם בעלי עניין אינה
מדווחת בטופס הזה ואינה מופיעה כאן. זו בדיוק גם הסיבה שיש כאן זהות: בטופס
הזה המדווח חייב להזדהות בשמו ובמספר הזיהוי שלו.

הערה מהטופס עצמו: רכישה או מכירה של מניות בבורסה בדרך של **עסקה תואמת**
מסווגת כעסקה מחוץ לבורסה. כלומר הסיווג כאן כולל גם עסקאות תואמות, וזה
הסיווג הרשמי של הבורסה ולא פרשנות שלנו.

חישוב שיעור מההון: הטופס מדווח כמות ושיעור החזקה לפני ואחרי. סך ניירות
הערך מאותו סוג נגזר מ-(כמות אחרי חלקי שיעור אחרי), ומתוכו מחושב חלקה של
העסקה. כשהשיעור מעוגל לאפס אין ממה לגזור, והשדה נשאר ריק במקום לנחש.
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tls import harden  # noqa: E402

harden()

from curl_cffi import requests as creq  # noqa: E402
from _maya_api import MayaSession, WindowTooLarge  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "offex"
STATE = ROOT / "data" / "offex_state.json"
FILES = "https://mayafiles.tase.co.il/"

FORM = "ת076"
OFF_EXCHANGE = "מחוץ לבורסה"

# שם נייר הערך הוא הדרך היחידה בטופס להבחין בין מניה לאג"ח או לכתב אופציה.
SHARE = re.compile(r"מניות|מניה|"
                   r"רגילות|רגילה")
NOT_SHARE = re.compile(r"אג\"?ח|אגח|"
                       r"אופציה|אופ'|"
                       r"כתבי|השתתפות|"
                       r"תעודת")


def cell_text(html: str) -> list[str]:
    """שורות הטופס כטקסט. הטופס הוא HTML ישן בקידוד windows-1255."""
    html = re.sub(r"<(style|script).*?</\1>", "", html, flags=re.S | re.I)
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        vals = []
        for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I):
            v = re.sub(r"<[^>]+>", " ", c)
            v = re.sub(r"&nbsp;?", " ", v).replace("&amp;", "&")
            v = re.sub(r"\s+", " ", v).strip()
            if v and v != "_________":
                vals.append(v)
        if vals:
            rows.append(" | ".join(vals))
    return rows


def field(blob: str, label: str) -> str | None:
    m = re.search(re.escape(label) + r"\s*:?\s*\|?\s*([^\n|]+)", blob)
    return m.group(1).strip() if m else None


def num(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace(",", "").strip()
    neg = s.endswith("-") or s.startswith("-")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    v = float(m.group(0))
    return -v if neg else v


def pct(blob: str, label: str) -> float | None:
    """שיעור החזקה מופיע כ-'% 12.34' אחרי התווית."""
    m = re.search(re.escape(label) + r"[^%\n]*%\s*([\d.]+)", blob)
    return float(m.group(1)) if m else None


L = {
    "nature": "מהות השינוי",
    "sec": "שם וסוג נייר הערך",
    "sec_id": "מספר נייר ערך בבורסה",
    "qty": "שינוי בכמות ניירות הערך",
    "price": "שער העסקה",
    "date": "תאריך השינוי",
    "holder": "שם תאגיד/שם משפחה "
              "ושם פרטי של המחזיק",
    "holder_type": "סוג המחזיק",
    "controller": "שם בעל השליטה "
                  "בבעל העניין",
    "before_q": "יתרה (בכמות ניירות "
                "ערך) בדיווח האחרון",
    "after_q": "יתרה נוכחית "
               "(בכמות ניירות ערך)",
    "before_p": "שיעור החזקה מסך "
                "ניירות הערך מאותו "
                "הסוג בדיווח האחרון",
    "after_p": "שיעור החזקה נוכחי "
               "מסך ניירות הערך "
               "מאותו הסוג",
    "cap_after": "שיעור החזקה לאחר "
                 "השינוי",
    "growth": "גידול",
}


def parse(rows: list[str], meta: dict) -> dict | None:
    blob = "\n".join(rows)

    nature = field(blob, L["nature"])
    if not nature or OFF_EXCHANGE not in nature:
        return None

    sec_name = field(blob, L["sec"]) or ""
    if NOT_SHARE.search(sec_name) or not SHARE.search(sec_name):
        return None

    qty = num(field(blob, L["qty"]))
    if qty is None or qty == 0:
        return None
    direction = "buy" if L["growth"] in nature else "sell"
    qty = abs(qty)

    # השער מדווח עם מטבע מפורש. כמעט תמיד אגורות, אבל חלוקה ב-100 על
    # דיווח שאינו באגורות הייתה נותנת היקף כספי שגוי בשקט — ולכן הערך
    # הכספי מחושב רק כשהמטבע ידוע.
    price_raw = field(blob, L["price"]) or ""
    price = num(price_raw)
    currency = "agorot" if "אג'" in price_raw else (
        "ils" if "ש\"ח" in price_raw else "other")
    before_q = num(field(blob, L["before_q"]))
    after_q = num(field(blob, L["after_q"]))
    before_p = pct(blob, L["before_p"])
    after_p = pct(blob, L["after_p"])

    # סך ניירות הערך מאותו סוג — נגזר מהיתרה והשיעור שדווחו בטופס עצמו
    total = None
    for q, p in ((after_q, after_p), (before_q, before_p)):
        if q and p and p > 0:
            total = q / (p / 100.0)
            break
    share_pct = round(qty / total * 100, 4) if total else None

    d = field(blob, L["date"])
    try:
        tdate = datetime.strptime(d, "%d/%m/%Y").date().isoformat() if d else None
    except (ValueError, TypeError):
        tdate = None

    return {
        "report_id": meta["id"],
        "published": meta["publishDate"][:19],
        "date": tdate,
        "company": meta["company"],
        "company_id": meta["company_id"],
        "security_id": field(blob, L["sec_id"]),
        "security": sec_name,
        "holder": field(blob, L["holder"]),
        "holder_type": field(blob, L["holder_type"]),
        "holder_controller": field(blob, L["controller"]),
        "direction": direction,
        "nature": nature.replace("_________", "").strip(),
        "quantity": int(qty),
        "price": price,
        "currency": currency,
        "value_ils": (round(qty * price / 100.0) if currency == "agorot" else
                      round(qty * price) if currency == "ils" else None) if price else None,
        "pct_of_class": share_pct,
        "holding_pct_after": pct(blob, L["cap_after"]),
        "url": f"https://maya.tase.co.il/he/reports/{meta['id']}",
    }


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"last_day": None}


def main() -> int:
    days_back = int(os.environ.get("OFFEX_DAYS", "3"))
    start_env = os.environ.get("OFFEX_FROM")

    today = date.today()
    state = load_state()
    if start_env:
        start = date.fromisoformat(start_env)
    elif state.get("last_day"):
        start = date.fromisoformat(state["last_day"]) - timedelta(days=1)
    else:
        start = today - timedelta(days=days_back)
    until_env = os.environ.get("OFFEX_UNTIL")
    if until_env:
        today = min(today, date.fromisoformat(until_env))
    if start > today:
        start = today

    def fresh(tries: int = 4):
        """סשן חדש. ה-WAF של מאיה חוסם סשן שרץ יותר מדי זמן — בבקפיל
        הראשון הוא נחסם אחרי אחד-עשר ימי סריקה, וכל שאר החודשים דולגו.

        גם **יצירת** הסשן עצמה נכשלת לפעמים (HTTP/2 stream reset), ולכן
        היא חוזרת על עצמה. בלי זה חריגה מכאן מפילה את כל הריצה.
        """
        last = None
        for i in range(tries):
            try:
                m = MayaSession()
                f = creq.Session(impersonate="chrome")
                f.get("https://maya.tase.co.il/he", timeout=30)
                return m, f
            except Exception as e:
                last = e
                time.sleep(5 * (i + 1))
        raise last

    try:
        maya, files = fresh()
    except Exception as e:
        # כשל בפתיחת הסשן הראשון פירושו שמאיה חוסמת מהכתובת הזו. הודעה
        # ברורה עדיפה על traceback שנראה כמו באג בקוד.
        print(f"::error::לא ניתן לפתוח סשן מול מאיה: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 1
    found, scanned, failed = [], 0, 0
    bad_days: list[str] = []
    ok_through = None
    since_refresh = 0

    day = start
    while day <= today:
        # רענון יזום לפני שהחסימה מגיעה, במקום להתאושש ממנה
        if since_refresh >= 8:
            time.sleep(3)
            try:
                maya, files = fresh()
            except Exception:
                pass
            since_refresh = 0

        items = None
        for attempt in range(3):
            try:
                items = maya.reports_days(day, day)
                break
            except WindowTooLarge:
                print(f"  {day}: window too large, skipped", file=sys.stderr)
                items = []
                break
            except Exception as e:
                wait = 5 * (attempt + 1)
                print(f"  {day}: {type(e).__name__}, retry in {wait}s", file=sys.stderr)
                time.sleep(wait)
                try:
                    maya, files = fresh()
                except Exception:
                    pass
                since_refresh = 0
        since_refresh += 1

        if items is None:
            bad_days.append(day.isoformat())
            failed += 1
            day += timedelta(days=1)
            continue

        for it in items:
            if it.get("formId") != FORM:
                continue
            att = next((a for a in it.get("attachments", []) if a["fileType"] == "htm"), None)
            if not att:
                continue
            scanned += 1
            rows = None
            for attempt in range(2):
                try:
                    r = files.get(FILES + att["url"], timeout=30,
                                  headers={"Referer": "https://maya.tase.co.il/"})
                    rows = cell_text(r.content.decode("cp1255", "replace"))
                    break
                except Exception:
                    time.sleep(3)
                    try:
                        _, files = fresh()
                    except Exception:
                        pass
            if rows is None:
                failed += 1
                continue
            co = (it.get("companies") or [{}])[0]
            rec = parse(rows, {"id": it["id"], "publishDate": it["publishDate"],
                               "company": co.get("name"), "company_id": co.get("companyId")})
            if rec:
                found.append(rec)
            time.sleep(0.15)

        if not bad_days:
            ok_through = day
        day += timedelta(days=1)

    OUT.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, dict[int, dict]] = {}
    for rec in found:
        y = (rec["date"] or rec["published"])[:4]
        by_year.setdefault(y, {})[rec["report_id"]] = rec

    added = 0
    for y, recs in by_year.items():
        path = OUT / f"{y}.jsonl"
        existing = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    o = json.loads(line)
                    existing[o["report_id"]] = o
        added += len([k for k in recs if k not in existing])
        existing.update(recs)
        ordered = sorted(existing.values(), key=lambda r: (r["date"] or "", r["report_id"]))
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in ordered) + "\n",
                        encoding="utf-8")

    # ה-state מתקדם רק עד היום האחרון שנסרק **ברצף בהצלחה**. קידומו עד
    # היום כשימים באמצע נכשלו היה מבטיח שהם לא ייסרקו לעולם — וזה בדיוק
    # מה שקרה בבקפיל הראשון.
    STATE.parent.mkdir(parents=True, exist_ok=True)
    prev = load_state().get("last_day")
    last = (ok_through or (date.fromisoformat(prev) if prev else start - timedelta(days=1)))
    STATE.write_text(json.dumps(
        {"last_day": last.isoformat() if hasattr(last, "isoformat") else str(last),
         "failed_days": bad_days[:60],
         "updated": datetime.now().isoformat(timespec="seconds")},
        ensure_ascii=False), encoding="utf-8")
    print(f"scanned {scanned} {FORM} reports {start}..{today} | "
          f"off-exchange share trades: {len(found)} ({added} new) | "
          f"failures: {failed} | state through: {last}")
    if bad_days:
        print(f"::warning::{len(bad_days)} ימים לא נסרקו: {', '.join(bad_days[:8])}"
              f"{' …' if len(bad_days) > 8 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
