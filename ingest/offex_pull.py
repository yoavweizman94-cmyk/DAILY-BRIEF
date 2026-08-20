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

from _maya_api import MayaSession, WindowTooLarge  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "offex"
STATE = ROOT / "data" / "offex_state.json"
FILES = "https://mayafiles.tase.co.il/"

# רישום מנתחים לפי טופס. הוספת מקור היא הוספת פונקציה ל-PARSERS —
# הלולאה הראשית אינה יודעת דבר על טופס מסוים.
PARSERS: dict[str, object] = {}


def parser(form: str, kind: str, identity: bool):
    """רושם מנתח לטופס. kind מתאר את סוג האירוע, identity אומר אם הטופס
    מחייב את המדווח להזדהות — וזה ההבדל שהקורא חייב לראות."""
    def deco(fn):
        fn._kind = kind
        fn._identity = identity
        PARSERS[form] = fn
        return fn
    return deco


FORM = "ת076"
# ערכים שהמדווח ממלא כשאין תוכן. נמדדו בפועל על 249 עסקאות: 14 מקפים,
# מקף כפול, נקודה בודדת, ו"לא רלוונטי". הצגתם כזהות היא רעש.
PLACEHOLDER = {"-", "--", "---", "–", "—", ".", "_________", "אין",
               "לא רלוונטי", "לא ידוע", "לא רלוונטית", "ללא"}
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


def _currency(raw: str) -> str:
    """המטבע כפי שהטופס נוקב בו. ת076 נוקב באגורות, ת085 בשקל חדש —
    וחלוקה ב-100 על הדיווח הלא נכון נותנת היקף כספי שגוי בשקט."""
    if "אג'" in raw or "אגורות" in raw:
        return "agorot"
    if "ש\"ח" in raw or "שקל חדש" in raw or "שקלים" in raw:
        return "ils"
    return "other"


def _value(qty, price, currency):
    if not (qty and price):
        return None
    if currency == "agorot":
        return round(qty * price / 100.0)
    if currency == "ils":
        return round(qty * price)
    return None


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


@parser("ת076", kind="holdings", identity=True)
def parse_076(rows: list[str], meta: dict) -> dict | None:
    """שינוי בהחזקות בעל עניין או נושא משרה — הטופס עם הזהות המלאה."""
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
    currency = _currency(price_raw)
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
        "value_ils": _value(qty, price, currency),
        "pct_of_class": share_pct,
        "holding_pct_after": pct(blob, L["cap_after"]),
        "url": f"https://maya.tase.co.il/he/reports/{meta['id']}",
    }


# ---------- ת078 / ת079: חציית סף בעל עניין ----------

T78 = {
    "nature": "מהות הפעולה",
    "sec": "שם וסוג נייר הערך נשוא הפעולה",
    "sec_id": "מספר נייר ערך בבורסה",
    "date": "תאריך ביצוע הפעולה",
    "qty": "כמות ני\"ע נשוא הפעולה",
    "price": "השער בו בוצעה הפעולה",
    "first": "שם פרטי",
    "last": "שם משפחה/שם תאגיד",
    "controller": "שם בעל השליטה בבעל העניין",
}


def _holding_row(rows: list[str], sec_id: str | None):
    """שורת מצבת ההחזקות שאחרי הפעולה.

    המבנה: שם | מס' ני"ע | כמות | רדומות | % הון | % הצבעה. מחזיר
    (כמות, אחוז מההון) — ומהם נגזר סך המניות ומתוכו חלקה של העסקה.
    """
    if not sec_id:
        return None, None
    for ln in rows:
        parts = [x.strip() for x in ln.split("|")]
        if len(parts) < 5 or sec_id not in parts:
            continue
        nums = [num(x) for x in parts]
        idx = parts.index(sec_id)
        after = [n for n in nums[idx + 1:] if n is not None]
        if len(after) >= 2:
            return after[0], after[-2] if len(after) > 2 else after[1]
    return None, None


def _cross_threshold(rows, meta, form):
    blob = "\n".join(rows)
    nature = field(blob, T78["nature"])
    if not nature or OFF_EXCHANGE not in nature:
        return None
    sec_name = field(blob, T78["sec"]) or ""
    if NOT_SHARE.search(sec_name) or not SHARE.search(sec_name):
        return None
    qty = num(field(blob, T78["qty"]))
    if not qty:
        return None

    price_raw = field(blob, T78["price"]) or ""
    price = num(price_raw)
    currency = _currency(price_raw)
    sec_id = field(blob, T78["sec_id"])
    q_after, p_after = _holding_row(rows, sec_id)
    total = q_after / (p_after / 100.0) if (q_after and p_after) else None

    first = field(blob, T78["first"]) or ""
    last = field(blob, T78["last"]) or ""
    holder = " ".join(x for x in (first, last) if x).strip() or None

    d = field(blob, T78["date"])
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
        "security_id": sec_id,
        "security": sec_name,
        "holder": holder,
        "holder_type": "נעשה בעל עניין" if form == "ת078" else "חדל להיות בעל עניין",
        "holder_controller": field(blob, T78["controller"]),
        "direction": "buy" if "גידול" in nature else "sell",
        "nature": nature.replace("_________", "").strip(),
        "quantity": int(abs(qty)),
        "price": price,
        "currency": currency,
        "value_ils": _value(abs(qty), price, currency),
        "pct_of_class": round(abs(qty) / total * 100, 4) if total else None,
        "holding_pct_after": p_after,
        "url": f"https://maya.tase.co.il/he/reports/{meta['id']}",
    }


@parser("ת078", kind="threshold", identity=True)
def parse_078(rows, meta):
    """מי שנעשה בעל עניין. תופס עסקאות שחוצות את סף 5% — לרוב הגדולות."""
    return _cross_threshold(rows, meta, "ת078")


@parser("ת079", kind="threshold", identity=True)
def parse_079(rows, meta):
    """מי שחדל להיות בעל עניין — הצד שכנגד של ת078."""
    return _cross_threshold(rows, meta, "ת079")


# ---------- ת085: רכישה עצמית של החברה ----------

T85 = {
    "holder": "שם המחזיק במניות הרדומות",
    "sec_id": "מס' ני\"ע בבורסה",
    "sec": "שם המניה",
    "nature": "מהות השינוי",
    "date": "התאריך בו בוצעה העסקה",
    "value": "הסכום הכולל של התמורה המחושבת",
}


@parser("ת085", kind="buyback", identity=False)
def parse_085(rows, meta):
    """מניות רדומות — החברה רוכשת מניות של עצמה.

    כאן **אין צד שני מזוהה**, וזה בדיוק המקרה שטופס ת076 אינו מכסה.
    שני סייגים שנשמרים ברשומה במקום להיטשטש: השער מדווח בשקלים ולא
    באגורות, וחלק מהדיווחים מאגדים "מספר עסקאות בתוך ומחוץ לבורסה"
    בלי לפצל — ואז אי אפשר לייחס את כל הסכום למסחר מחוץ לבורסה.
    """
    blob = "\n".join(rows)
    if OFF_EXCHANGE not in blob:
        return None
    sec_name = field(blob, T85["sec"]) or ""
    if NOT_SHARE.search(sec_name) or not SHARE.search(sec_name):
        return None

    mixed = "בתוך ומחוץ לבורסה" in blob
    note = next((ln.strip() for ln in rows if OFF_EXCHANGE in ln and len(ln) < 90), None)

    price_raw = next((ln for ln in rows if ln.startswith("שער העסקה")), "")
    price = num(price_raw)
    currency = _currency(price_raw)
    value = num(field(blob, T85["value"]))
    qty = round(value / price) if (value and price) else None
    if not qty:
        return None

    nature = field(blob, T85["nature"]) or ""
    d = field(blob, T85["date"])
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
        "security_id": field(blob, T85["sec_id"]),
        "security": sec_name,
        "holder": field(blob, T85["holder"]) or meta["company"],
        "holder_type": "התאגיד המדווח",
        "holder_controller": None,
        "direction": "buy" if "גידול" in nature else "sell",
        "nature": (nature.replace("_________", "").strip() + (f" · {note}" if note else "")).strip(),
        "quantity": int(qty),
        "price": price,
        "currency": currency,
        "value_ils": round(value) if value else None,
        # סך ההון אינו מדווח בטופס הזה, ולכן אין ממה לגזור שיעור.
        "pct_of_class": None,
        "holding_pct_after": None,
        "partial": mixed,
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

    def fresh(tries: int = 5):
        """סשן יחיד לכל הבקשות.

        הגרסה הקודמת פתחה שני סשנים — אחד ל-API ואחד לקבצים — ושניהם
        פנו לאותו מארח. מאיה ביטלה זרמי HTTP/2 (curl 92, error CANCEL)
        כבר בבקשה השלישית, גם ממחשב מקומי וגם מראנר של GitHub. סשן אחד
        עם ויסות אחד פותר את זה, וגם מוריד את העומס בחצי.
        """
        last = None
        for i in range(tries):
            try:
                return MayaSession()
            except Exception as e:
                last = e
                time.sleep(6 * (i + 1))
        raise last

    def fetch_file(sess, url: str, tries: int = 3):
        """קובץ נספח, דרך אותו סשן ובאותו ויסות."""
        last = None
        for i in range(tries):
            try:
                sess._wait()
                r = sess._s.get(FILES + url, timeout=30,
                                headers={"Referer": "https://maya.tase.co.il/"})
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}")
                return r.content
            except Exception as e:
                last = e
                time.sleep(4 * (i + 1))
        raise last

    try:
        maya = fresh()
    except Exception as e:
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
        if since_refresh >= 10:
            time.sleep(4)
            try:
                maya = fresh()
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
                    maya = fresh()
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
            fn = PARSERS.get(it.get("formId") or "")
            if fn is None:
                continue
            att = next((a for a in it.get("attachments", []) if a["fileType"] == "htm"), None)
            if not att:
                continue
            scanned += 1
            try:
                rows = cell_text(fetch_file(maya, att["url"]).decode("cp1255", "replace"))
            except Exception:
                failed += 1
                continue
            co = (it.get("companies") or [{}])[0]
            rec = fn(rows, {"id": it["id"], "publishDate": it["publishDate"],
                            "company": co.get("name"), "company_id": co.get("companyId")})
            if rec:
                rec.setdefault("form", it.get("formId"))
                rec.setdefault("kind", fn._kind)
                rec.setdefault("has_identity", fn._identity)
                found.append(rec)

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
    print(f"scanned {scanned} reports ({'/'.join(PARSERS)}) {start}..{today} | "
          f"off-exchange share trades: {len(found)} ({added} new) | "
          f"failures: {failed} | state through: {last}")
    if bad_days:
        print(f"::warning::{len(bad_days)} ימים לא נסרקו: {', '.join(bad_days[:8])}"
              f"{' …' if len(bad_days) > 8 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
