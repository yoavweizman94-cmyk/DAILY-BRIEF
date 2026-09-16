# -*- coding: utf-8 -*-
"""עמוד נתוני הלמ"ס: בקצרה, מדדים, מדדי מחירים, לוח פרסומים, הודעות וניתוחים.

נבנה מ-output/cbs/, שנכתב ע"י ingest/cbs_pull.py (נתונים) ו-
scripts/analyze_cbs.py (ניתוחים). שני הקבצים מתעדכנים בצנרת cbs-watch
שלוש פעמים ביום.

**העמוד קורא גם בלי ניתוח.** הודעה שטרם נותחה מוצגת עם התקציר של הלמ"ס
ושורה שאומרת שהניתוח ממתין; הודעה שאינה נוגעת לשוק מוצגת בלי ניתוח ואומרת
זאת. אחרת עמוד שהניתוח שלו נכשל נראה בדיוק כמו עמוד שלא פורסם בו דבר.

**סדר העמוד הוא סדר השאלות של הקורא.** מה יצא לאחרונה ומה המשמעות (בקצרה);
איפה המשק עומד (מדדים, עם שינוי ומגמה ולא רק ערך); מה קורה במחירים
(גרפים); מה יוצא בימים הקרובים (לוח); והניתוח המלא של כל הודעה בסוף.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CBS = ROOT / "output" / "cbs"

DAYS = 30          # כמה ימים של הודעות מוצגים
OPEN_LATEST = 3    # כמה ניתוחים אחרונים מוצגים פתוחים; השאר מקופלים
BRIEF_CARDS = 6    # כרטיסי "בקצרה"
BRIEF_PER_TOPIC = 2
PREVIEW_FIGS = 4   # נתוני מפתח שמוצגים גם כשהניתוח מקופל
CAL_DAYS = 14
SPARK_MONTHS = 25
SPARK_QUARTERS = 16
WEEKDAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
DIR_CLASS = {"חיובי": "up", "שלילי": "down", "מעורב": "mixed"}
MINUS = "−"

TOPIC_LABELS = {
    "prices": "מחירים ואינפלציה", "housing": "דיור, בנייה ונדל״ן",
    "accounts": "צמיחה וחשבונות לאומיים", "labor": "שוק העבודה ושכר",
    "trade": "סחר חוץ", "business": "צריכה, מסחר ועסקים", "industry": "תעשייה והייטק",
    "tourism": "תיירות ותחבורה", "surveys": "סקרי אמון וציפיות", "other": "נושאים נוספים",
}

# קבוצות המדדים לפי מילה בכותרת ולא לפי מזהה: הלמ"ס מחליפה מזהים כשמדד
# עובר בסיס, והכותרת נשארת. ההתאמה הראשונה קובעת.
GROUPS = (
    ("prices", "מחירים", ("מחירים לצרכן", "מחירי הדירות", "מחירי דירות")),
    ("accounts", "צמיחה וצריכה", ("תוצר", "צריכה")),
    ("labor", "שוק העבודה", ("מועסקים", "שכר", "משרות")),
    ("trade", "סחר חוץ ומאזן התשלומים", ("יבוא", "יצוא", "מאזן התשלומים")),
    ("surveys", "סקרי אמון ומגמות", ("אמון", "מגמות")),
    ("other", "אוכלוסייה", ("תושבים", "אוכלוסי")),
)

# פרסום בלוח → המדד שהוא מעדכן, כדי להציג לידו את הקריאה האחרונה. "מדדי
# מחירים בסחר חוץ" נעצר בכלל הראשון ואינו נקשר ליבוא.
CAL_LINKS = (
    ("מדדי מחירים ב", None),
    ("מחירים לצרכן", "מדד המחירים לצרכן"),
    ("כוח אדם", "בלתי מועסקים"),
    ("משרות", "משרות פנויות"),
    ("שכר", "שכר חודשי ממוצע"),
    ("סחר החוץ", "יבוא סחורות"), ("סחר חוץ", "יבוא סחורות"),
    ("חשבונות לאומיים", "תוצר מקומי גולמי"),
    ("מאזן התשלומים", "מאזן התשלומים"),
    ("אמון הצרכנים", "מדד אמון הצרכנים"),
    ("מגמות בעסקים", "מגמות בעסקים"),
    ("מחירי דירות", "מדד מחירי הדירות"), ("שוק הדירות", "מדד מחירי הדירות"),
)

# יעד האינפלציה של בנק ישראל — תחום, לא נקודה. מסומן בגרף המדד לצרכן בלבד.
BOI_TARGET = (1.0, 3.0)
CPI_CODE = "120010"
PERIOD_LABEL = {"40010": "דו-חודשי"}   # מדד מחירי הדירות מחושב על חלונות של חודשיים


def _jsonl(p: Path) -> list[dict]:
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def load() -> dict:
    snap = {}
    if (CBS / "snapshot.json").exists():
        try:
            snap = json.loads((CBS / "snapshot.json").read_text(encoding="utf-8"))
        except ValueError:
            snap = {}
    releases = []
    for p in sorted((CBS / "releases").glob("*.jsonl")):
        releases += _jsonl(p)
    releases.sort(key=lambda r: (r.get("date") or "", r.get("published") or "", str(r.get("id") or "")),
                  reverse=True)
    analyses = {}
    for p in sorted((CBS / "analyses").glob("*.jsonl")):
        for a in _jsonl(p):
            if a.get("release_id") is not None:
                analyses[str(a["release_id"])] = a
    return {"snap": snap, "releases": releases, "analyses": analyses}


# --------------------------------------------------------------------------
# מספרים

def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _num(x: float | None, digits: int | None = None) -> str:
    """מספר לתצוגה: מפרידי אלפים, דיוק לפי גודל, ומינוס טיפוגרפי."""
    if x is None:
        return "—"
    ax = abs(x)
    if digits is None:
        digits = 0 if ax >= 1000 else 1 if ax >= 100 else 2
    s = f"{ax:,.{digits}f}"
    if digits and "." in s:
        s = s.rstrip("0").rstrip(".")
    return (MINUS if x < 0 and s.strip("0.,") else "") + s


def _sg(x: float | None, suffix: str = "%", digits: int = 1) -> str:
    if x is None:
        return "—"
    s = f"{abs(x):.{digits}f}"
    if float(s) == 0:
        return f"0{'.' + '0' * digits if digits else ''}{suffix}"
    return ("+" if x > 0 else MINUS) + s + suffix


def _unit(u) -> str:
    u = str(u or "").strip().replace('"', "״")
    return {"מספר": "", "אחוזים": "%"}.get(u, u)


def _scaled(x: float, unit: str) -> tuple[float, str, int | None]:
    """מיליונים שעברו את האלף מוצגים כמיליארדים: "558.4 מיליארד ש״ח"."""
    if unit.startswith("מיליוני ") and abs(x) >= 1000:
        rest = unit[len("מיליוני "):]
        return x / 1000, "מיליארד " + {"דולרים": "דולר"}.get(rest, rest), 1
    return x, unit, None


def _ym(iso: str | None) -> str:
    return (iso or "")[:7]


def _shift(ym: str, months: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    k = y * 12 + (m - 1) + months
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def _mm(ym: str) -> str:
    return f"{ym[5:7]}/{ym[:4]}" if len(ym) >= 7 else "—"


def _period_label(ym: str, quarterly: bool) -> str:
    if len(ym) < 7:
        return "—"
    if quarterly:
        return f"רבעון {(int(ym[5:7]) - 1) // 3 + 1} · {ym[:4]}"
    return _mm(ym)


def _dm(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if iso and len(iso) >= 10 else "—"


def _dmy(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) >= 10 else "—"


def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    """קווי רשת "עגולים" שמכסים את כל הטווח — הראשון מתחת למינימום, האחרון מעליו."""
    span = (hi - lo) or 1.0
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    t = math.floor(lo / step + 1e-9) * step
    out = []
    while True:
        out.append(round(t, 6))
        if t >= hi - 1e-9 or len(out) > 12:
            return out
        t += step


def _tick(t: float) -> str:
    s = f"{abs(t):.1f}".rstrip("0").rstrip(".")
    return (MINUS if t < 0 else "") + s


# --------------------------------------------------------------------------
# טקסט

def _para(text) -> str:
    """טקסט של המודל ל-HTML: בריחה, פסקאות, והדגשה ב-**...** בלבד."""
    if not text:
        return ""
    t = escape(str(text))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    parts = [p.strip() for p in re.split(r"\n\s*\n|\n", t) if p.strip()]
    return "".join(f"<p>{p}</p>" for p in parts)


def _dir(d: str | None) -> str:
    if not d:
        return ""
    return f'<span class="cbs-dir {DIR_CLASS.get(d, "flat")}">{escape(d)}</span>'


def _topic(key: str | None, label: str | None = None) -> str:
    k = key if key in TOPIC_LABELS else "other"
    return (f'<span class="cbs-topic t-{k}"><i class="tdot" aria-hidden="true"></i>'
            f'{escape(label or TOPIC_LABELS[k])}</span>')


_NUM_HEAD = re.compile(r"^\s*([+\-−]?\s?[\d.,]+\s?%?)\s*(.*)$")
_HEB = re.compile(r"[\u0590-\u05FF]")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _value_html(v) -> str:
    """ערך שהמודל כתב — "14.9%" או "0.5 מיליארד דולר" — לתצוגה.

    **המספר לבד בבידוד משמאל-לימין, והמילים בחוץ.** כשכל הערך היה בתוך
    dir="ltr" ובגופן המספרים, "0.5 מיליארד דולר" הוצג הפוך ("דולר מיליארד
    0.5" בקריאה מימין) ובגופן חלופי של המערכת.
    """
    t = str(v or "").strip()
    m = _NUM_HEAD.match(t)
    if m and m.group(1).strip():
        rest = m.group(2).strip()
        return (f'<b dir="ltr">{escape(m.group(1).strip())}</b>'
                + (f'<small>{escape(rest)}</small>' if rest else ""))
    if _HEB.search(t):
        return f'<b class="txt">{escape(t)}</b>'
    return f'<b dir="ltr">{escape(t)}</b>'


def _when(t) -> str:
    """תאריך ISO בטקסט של המודל → dd/mm/yyyy, כמו בשאר העמוד."""
    return _ISO.sub(lambda m: f"{m.group(3)}/{m.group(2)}/{m.group(1)}", str(t or ""))


def _words(s: str | None) -> set[str]:
    return {w for w in re.findall(r"\w+", s or "") if len(w) > 1}


# --------------------------------------------------------------------------
# גרפים

def _spark_line(vals: list[float], band: tuple[float, float] | None = None) -> str:
    """קו מגמה עם שטח: היחס קבוע (בלי מתיחה), ולכן נקודת הסיום נשארת עגולה."""
    if len(vals) < 2:
        return ""
    w, h, pad = 200.0, 46.0, 4.0
    lo, hi = min(vals), max(vals)
    if band:
        lo, hi = min(lo, band[0]), max(hi, band[1])
    span = (hi - lo) or 1.0
    n = len(vals)

    def X(i):
        return pad + i * (w - 2 * pad) / (n - 1)

    def Y(v):
        return pad + (hi - v) / span * (h - 2 * pad)

    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    parts = []
    if band:
        parts.append(f'<rect class="band" x="0" y="{Y(band[1]):.1f}" width="{w:.0f}" '
                     f'height="{Y(band[0]) - Y(band[1]):.1f}"/>')
    if lo < 0 < hi:
        parts.append(f'<line class="zero" x1="0" x2="{w:.0f}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>')
    parts.append(f'<path class="area" d="M{X(0):.1f},{h - pad:.1f} L{pts.replace(" ", " L")} '
                 f'L{X(n - 1):.1f},{h - pad:.1f} Z"/>')
    parts.append(f'<polyline class="ln" points="{pts}"/>')
    parts.append(f'<circle class="end" cx="{X(n - 1):.1f}" cy="{Y(vals[-1]):.1f}" r="2.6"/>')
    return f'<svg class="cbs-spark" viewBox="0 0 {w:.0f} {h:.0f}" aria-hidden="true">{"".join(parts)}</svg>'


def _spark_bars(vals: list[float]) -> str:
    if len(vals) < 2:
        return ""
    w, h, pad = 200.0, 46.0, 4.0
    lo, hi = min(0.0, min(vals)), max(0.0, max(vals))
    span = (hi - lo) or 1.0
    n = len(vals)
    slot = (w - 2 * pad) / n

    def Y(v):
        return pad + (hi - v) / span * (h - 2 * pad)

    y0 = Y(0)
    parts = [f'<line class="zero" x1="0" x2="{w:.0f}" y1="{y0:.1f}" y2="{y0:.1f}"/>']
    for i, v in enumerate(vals):
        yv = Y(v)
        top, ht = (yv, y0 - yv) if v >= 0 else (y0, yv - y0)
        cls = "bar" + (" neg" if v < 0 else "") + (" last" if i == n - 1 else "")
        parts.append(f'<rect class="{cls}" x="{pad + slot * i + slot * 0.18:.1f}" y="{top:.1f}" '
                     f'width="{slot * 0.64:.1f}" height="{max(ht, 0.9):.1f}"/>')
    return f'<svg class="cbs-spark" viewBox="0 0 {w:.0f} {h:.0f}" aria-hidden="true">{"".join(parts)}</svg>'


def _price_chart(code: str, s: dict) -> str:
    """עמודות לשינוי החודשי וקו לשינוי השנתי, על אותו ציר אחוזים.

    **השינויים ולא רמת המדד.** הלמ"ס מחליפה בסיס מדי כמה שנים (מדד תשומות
    הבנייה עבר לבסיס יולי 2025), וקו של רמת המדד היה מצייר את ההחלפה כקריסה
    של 22%. השינוי החודשי והשנתי מחושבים אצל הלמ"ס על פני ההחלפה.
    """
    pts = [p for p in (s.get("points") or []) if _f(p.get("m")) is not None and _f(p.get("y")) is not None]
    if len(pts) < 3:
        return ""
    # רוחב קרוב לרוחב המוצג, כדי שטקסט הצירים לא יתכווץ לשבעה פיקסלים בטלפון.
    W, H = 440.0, 180.0
    L, R, T, B = 34.0, 8.0, 10.0, 22.0
    ms = [_f(p["m"]) for p in pts]
    ys = [_f(p["y"]) for p in pts]
    band = BOI_TARGET if code == CPI_CODE else None
    lo = min(ms + ys + [0.0] + ([band[0]] if band else []))
    hi = max(ms + ys + [0.0] + ([band[1]] if band else []))
    ticks = _ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    pw, ph = W - L - R, H - T - B
    n = len(pts)
    slot = pw / n

    def X(i):
        return L + slot * (i + 0.5)

    def Y(v):
        return T + (hi - v) / ((hi - lo) or 1.0) * ph

    parts = []
    if band:
        parts.append(f'<rect class="band" x="{L:.0f}" y="{Y(band[1]):.1f}" width="{pw:.0f}" '
                     f'height="{Y(band[0]) - Y(band[1]):.1f}"/>')
    for t in ticks:
        parts.append(f'<line class="{"zero" if abs(t) < 1e-9 else "grid"}" x1="{L:.0f}" x2="{W - R:.0f}" '
                     f'y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>')
        parts.append(f'<text class="ax" x="{L - 6:.0f}" y="{Y(t) + 3.5:.1f}" text-anchor="end">{_tick(t)}%</text>')
    end_x = W - R
    parts.append(f'<text class="ax" x="{end_x:.0f}" y="{H - 7:.0f}" text-anchor="end">'
                 f'{pts[-1]["period"][5:7]}/{pts[-1]["period"][2:4]}</text>')
    for i, p in enumerate(pts):
        if i and p["period"].endswith("-01"):
            x = L + slot * i
            parts.append(f'<line class="yr" x1="{x:.1f}" x2="{x:.1f}" y1="{T:.0f}" y2="{T + ph:.0f}"/>')
            if end_x - x > 44:
                parts.append(f'<text class="ax" x="{x + 4:.1f}" y="{H - 7:.0f}">{p["period"][:4]}</text>')
    y0 = Y(0)
    for i, v in enumerate(ms):
        yv = Y(v)
        top, ht = (yv, y0 - yv) if v >= 0 else (y0, yv - y0)
        cls = "bar" + (" neg" if v < 0 else "") + (" last" if i == n - 1 else "")
        parts.append(f'<rect class="{cls}" x="{X(i) - slot * 0.31:.1f}" y="{top:.1f}" '
                     f'width="{slot * 0.62:.1f}" height="{max(ht, 0.9):.1f}"/>')
    parts.append('<polyline class="yoy" points="'
                 + " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(ys)) + '"/>')
    parts.append(f'<circle class="yoy-end" cx="{X(n - 1):.1f}" cy="{Y(ys[-1]):.1f}" r="3.4"/>')
    mlabel = PERIOD_LABEL.get(code, "חודשי")
    for i, p in enumerate(pts):
        parts.append(f'<rect class="hit" x="{L + slot * i:.1f}" y="{T:.0f}" width="{slot:.1f}" height="{ph:.0f}">'
                     f'<title>{_mm(p["period"])} · {mlabel} {_sg(ms[i])} · שנתי {_sg(ys[i])}</title></rect>')
    label = f'{s.get("name") or code}: שינוי {mlabel} ושנתי, {n} חודשים'
    return (f'<svg class="cbs-ch" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
            f'aria-label="{escape(label)}">{"".join(parts)}</svg>')


# --------------------------------------------------------------------------
# מדדים

def _group_of(title: str) -> str:
    for key, _, words in GROUPS:
        if any(w in title for w in words):
            return key
    return "other"


def _dedupe(rows: list[dict]) -> list[dict]:
    # הלמ"ס מחזיקה לעיתים שני פריטים באותה כותרת ובלי תיאור — הוצאה לצריכה
    # ציבורית רבעונית ושנתית, למשל. בלי יחידה ובלי תיאור אי אפשר להבחין
    # ביניהם, ולכן נשאר רק העדכני.
    latest = {}
    for i in rows:
        key = (i.get("title"), i.get("label") or "")
        if key not in latest or (i.get("period") or "") > (latest[key].get("period") or ""):
            latest[key] = i
    return [i for i in rows if latest.get((i.get("title"), i.get("label") or "")) is i]


def _adj_tag(adj: str) -> str:
    if "מנוכ" in adj:
        return "מנוכה עונתיות"
    if "מקורי" in adj:
        return "לא מנוכה עונתיות"
    if "משורשר" in adj:
        return "מחירים קבועים (משורשרים)"
    return ""


def _tile_model(prim: dict, rest: list[dict], snap: dict) -> dict:
    title = prim.get("title") or ""
    sid = str(prim.get("series") or "")
    price = (snap.get("series") or {}).get(sid)
    hist = (snap.get("history") or {}).get(sid) or {}
    hpts = hist.get("points") or []
    quarterly = hist.get("time") == "רבע"
    unit = _unit(prim.get("unit")) or _unit(hist.get("unit"))
    value, prev = _f(prim.get("value")), _f(prim.get("previous"))
    ym = _ym(prim.get("period"))
    adj = str(hist.get("adj") or "")
    seasonal_raw = bool(hist) and "מנוכ" not in adj

    # **סוג המדד קובע איזה שינוי מוצג.** שיעור (אבטלה, מאזן סקר) משתנה
    # בנקודות אחוז; מדד שהוא עצמו שינוי (מדד המחירים החודשי, קצב הצמיחה)
    # מוצג לצד הקריאה הקודמת; רמה (שכר, יבוא) — באחוז שינוי; ומאזן שחוצה
    # את האפס (החשבון השוטף) — בהפרש מוחלט, כי אחוז שינוי של מספר שלילי
    # הוא חסר משמעות.
    if any(w in title for w in ("בלתי מועסקים", "אמון", "מגמות")):
        kind = "rate"
    elif unit == "%":
        kind = "change"
    elif (value is not None and value < 0) or any(p["value"] < 0 for p in hpts):
        kind = "balance"
    else:
        kind = "level"

    m = {"title": title, "label": prim.get("label") or "", "explain": prim.get("explain") or "",
         "group": _group_of(title), "kind": kind, "period": _period_label(ym, quarterly),
         "deltas": [], "secondary": [], "spark": "", "range": "", "span": ("", ""),
         "tag": _adj_tag(adj)}

    # --- ערך ראשי. אחוז צמוד למספר בתוך הבידוד משמאל-לימין; יחידה עברית
    # נשארת בחוץ, כדי שתיקרא אחרי המספר ולא לפניו.
    scale_div, scale_digits = 1.0, None
    if kind == "change":
        m["value"], m["unit"] = _sg(value), ""
    elif value is None:
        m["value"], m["unit"] = "—", unit
    else:
        v, u, dg = _scaled(value, unit)
        if u != unit:
            scale_div, scale_digits = 1000.0, 1
        if u == "%":
            m["value"], m["unit"] = _num(v, dg) + "%", ""
        else:
            m["value"], m["unit"] = _num(v, dg), u

    prev_word = ("מול הרבעון הקודם" if quarterly else
                 "מול החודש הקודם" if hist or price else "מול הקריאה הקודמת")

    def lag(months: int) -> float | None:
        if not hpts or hpts[-1]["period"] != ym:
            return None
        target = _shift(ym, -months)
        return next((p["value"] for p in hpts if p["period"] == target), None)

    # --- שינויים: (תווית, טקסט, מחלקה, האם הטקסט חתום ודורש בידוד LTR)
    if kind == "change":
        if price:
            last = (price.get("points") or [{}])[-1]
            if _ym(last.get("period")) == ym and _f(last.get("y")) is not None:
                m["deltas"].append(("שנתי", _sg(_f(last.get("y"))), "", True))
            m["tag"] = "שינוי " + PERIOD_LABEL.get(sid, "חודשי")
        if prev is not None:
            m["deltas"].append(("קודם", _sg(prev), "", True))
        if "תוצר" in title:
            m["tag"] = "שינוי רבעוני בקצב שנתי, מנוכה עונתיות"
    elif kind == "rate":
        if value is not None and prev is not None:
            d = value - prev
            m["deltas"].append((prev_word, _delta(d, f"{abs(d):.1f}", "נ״א"), _cls(d), False))
        ly = lag(12)
        if value is not None and ly is not None:
            d = value - ly
            m["deltas"].append(("מול אשתקד", _delta(d, f"{abs(d):.1f}", "נ״א"), _cls(d), False))
    elif kind == "level":
        items = []
        if value is not None and prev not in (None, 0):
            d = (value / prev - 1) * 100
            items.append((prev_word, _delta(d, f"{abs(d):.1f}%", ""), _cls(d), False))
        ly = lag(12)
        if ly not in (None, 0):
            d = (hpts[-1]["value"] / ly - 1) * 100
            items.append(("מול אשתקד", _delta(d, f"{abs(d):.1f}%", ""), _cls(d), False))
        # **בסדרה שאינה מנוכה עונתיות השינוי השנתי ראשון.** השכר הממוצע קפץ
        # ביוני 6.7% מול מאי, כמעט כולו עונתיות. הקריאה היא מול אשתקד.
        if seasonal_raw and len(items) == 2:
            items.reverse()
        m["deltas"] = items
    elif kind == "balance":
        for label, base in ((prev_word, prev), ("מול אשתקד", lag(12))):
            if value is None or base is None:
                continue
            if label == "מול אשתקד" and _unit(hist.get("unit")) != unit:
                continue
            d, u, dg = _scaled(value - base, unit)
            m["deltas"].append((label, _delta(value - base, _num(abs(d), dg), u), _cls(value - base), False))

    # --- ערכים משניים: אותה כותרת ביחידה אחרת
    for r in rest:
        rv, ru = _f(r.get("value")), _unit(r.get("unit"))
        if rv is None:
            continue
        v, u, dg = _scaled(rv, ru)
        lbl = r.get("label") or r.get("title") or ""
        text = f'{escape(lbl)}: <b dir="ltr">{_num(v, dg)}</b> {escape(u)}'
        rh = ((snap.get("history") or {}).get(str(r.get("series") or "")) or {}).get("points") or []
        rym = _ym(r.get("period"))
        if rh and rh[-1]["period"] == rym:
            base = next((p["value"] for p in rh if p["period"] == _shift(rym, -12)), None)
            if base:
                text += f' · מול אשתקד <b dir="ltr">{_sg((rh[-1]["value"] / base - 1) * 100)}</b>'
        m["secondary"].append(text)

    # --- מגמה
    vals, periods = [], []
    if kind == "change" and price:
        seq = [p for p in (price.get("points") or []) if _f(p.get("m")) is not None][-SPARK_MONTHS:]
        vals, periods = [_f(p["m"]) for p in seq], [p["period"] for p in seq]
        m["spark"] = _spark_bars(vals)
    elif hpts:
        seq = hpts[-(SPARK_QUARTERS if quarterly else SPARK_MONTHS):]
        vals, periods = [p["value"] for p in seq], [p["period"] for p in seq]
        m["spark"] = _spark_bars(vals) if kind == "change" else _spark_line(vals)
    if len(vals) >= 2:
        # היסטוריה ביחידה אחרת מהערך הראשי (אלפים מול מיליון) — בלי שפל ושיא,
        # שהיו נקראים כמספרים בסדר גודל אחר.
        comparable = _unit(hist.get("unit")) == unit or kind == "change" or not hist
        if comparable:
            def fmt(x: float) -> str:
                if kind == "change":
                    return _sg(x)
                s = _num(x / scale_div, scale_digits)
                return s + ("%" if unit == "%" else "")
            lo_i = min(range(len(vals)), key=lambda i: vals[i])
            hi_i = max(range(len(vals)), key=lambda i: vals[i])
            m["range"] = (f'שפל <b dir="ltr">{fmt(vals[lo_i])}</b> ({_short(periods[lo_i], quarterly)}) · '
                          f'שיא <b dir="ltr">{fmt(vals[hi_i])}</b> ({_short(periods[hi_i], quarterly)})')
        m["span"] = (_short(periods[0], quarterly), _short(periods[-1], quarterly))
    return m


def _short(ym: str, quarterly: bool) -> str:
    if quarterly:
        return f"Q{(int(ym[5:7]) - 1) // 3 + 1}/{ym[2:4]}"
    return f"{ym[5:7]}/{ym[2:4]}"


def _delta(d: float, number: str, unit: str) -> str:
    """HTML של שינוי: חץ, מספר בלי סימן, יחידה. שינוי אפסי נאמר במילים."""
    if abs(d) < 0.05:
        return '<b class="txt">ללא שינוי</b>'
    return (f'<b>{_arrow(d)}{escape(number)}</b>'
            + (f' <span class="u">{escape(unit)}</span>' if unit else ""))


def _arrow(d: float) -> str:
    if abs(d) < 0.05:
        return "■ "
    return "▲ " if d > 0 else "▼ "


def _cls(d: float) -> str:
    return "flat" if abs(d) < 0.05 else "rise" if d > 0 else "fall"


def indicator_models(snap: dict) -> list[dict]:
    rows = _dedupe(snap.get("indicators") or [])
    by_title: dict[str, list[dict]] = {}
    for i in rows:
        by_title.setdefault(i.get("title") or "", []).append(i)
    out = []
    for items in by_title.values():
        # אותה כותרת ביחידות שונות — מדד המחירים באחוז ובנקודות, התמ"ג בקצב
        # ובשקלים — היא אריח אחד: האחוז ראשי, והשאר שורה משנית.
        items.sort(key=lambda i: 0 if _unit(i.get("unit")) == "%" else 1)
        out.append(_tile_model(items[0], items[1:], snap))
    return out


def _tile_html(m: dict) -> str:
    tip = f' title="{escape(m["explain"])}"' if m["explain"] else ""
    sub = (f'<span class="tl-sub">{escape(m["label"])}</span>'
           if m["label"] and m["label"] != m["title"] else "")
    unit = f'<span class="u">{escape(m["unit"])}</span>' if m["unit"] else ""
    deltas = []
    for label, text, cls, signed in m["deltas"]:
        if signed:
            deltas.append(f'<li><span>{escape(label)}</span> <b dir="ltr">{escape(text)}</b></li>')
        else:
            # חץ ומספר בלי סימן: נקראים נכון בכיוון העמוד, בלי בידוד.
            deltas.append(f'<li class="{cls}">{text} <span>{escape(label)}</span></li>')
    spark = ""
    if m["spark"]:
        a, b = m["span"]
        spark = (f'<div class="tl-spark" dir="ltr">{m["spark"]}'
                 f'<div class="tl-axis"><span>{a}</span><span>{b}</span></div></div>')
    return (f'<div class="cbs-tile k-{m["kind"]}"{tip}>'
            f'<div class="tl-head"><span class="tl-name">{escape(m["title"])}</span>'
            f'<span class="tl-per">{escape(m["period"])}</span></div>'
            f'{sub}'
            f'<div class="tl-val"><b dir="ltr">{escape(m["value"])}</b>{unit}</div>'
            + (f'<ul class="tl-deltas">{"".join(deltas)}</ul>' if deltas else "")
            + spark
            + "".join(f'<div class="tl-sec">{s}</div>' for s in m["secondary"])
            + (f'<div class="tl-range">{m["range"]}</div>' if m["range"] else "")
            + (f'<div class="tl-tag">{escape(m["tag"])}</div>' if m["tag"] else "")
            + '</div>')


def indicators_html(models: list[dict]) -> str:
    if not models:
        return ""
    blocks = []
    for key, label, _ in GROUPS:
        ms = [m for m in models if m["group"] == key]
        if not ms:
            continue
        blocks.append(f'<div class="cbs-group t-{key}"><h3 class="cbs-gh"><i class="tdot" aria-hidden="true"></i>'
                      f'{escape(label)}</h3><div class="cbs-tiles">'
                      + "".join(_tile_html(m) for m in ms) + '</div></div>')
    return ('<h2 id="cbs-ind">מדדים עיקריים</h2>'
            '<p class="cbs-sub">הערך האחרון של כל מדד, השינוי מול התצפית הקודמת ומול אשתקד, '
            'והמגמה בשנתיים האחרונות (ברבעונים — ארבע שנים). בסדרה שאינה מנוכה עונתיות השינוי '
            'מול אשתקד מוצג ראשון: השינוי החודשי בה משקף בעיקר עונתיות. מעבר עם העכבר על מדד '
            'מציג את הגדרתו בלשון הלמ"ס.</p>'
            f'<div class="cbs-groups">{"".join(blocks)}</div>')


def prices_html(snap: dict) -> str:
    cards = []
    for code, s in (snap.get("series") or {}).items():
        pts = s.get("points") or []
        chart = _price_chart(code, s)
        if not pts or not chart:
            continue
        last = pts[-1]
        mlabel = PERIOD_LABEL.get(code, "חודשי")
        cards.append(
            f'<div class="cbs-pc"><div class="pc-head"><h3>{escape(s.get("name") or code)}</h3>'
            f'<span class="pc-per">{_mm(last.get("period") or "")}</span></div>'
            f'<div class="pc-nums"><span><small>{mlabel}</small><b dir="ltr">{_sg(_f(last.get("m")))}</b></span>'
            f'<span><small>שנתי</small><b dir="ltr">{_sg(_f(last.get("y")))}</b></span>'
            f'<span><small>רמת המדד</small><b dir="ltr">{_num(_f(last.get("value")))}</b></span></div>'
            f'<div class="pc-chart" dir="ltr">{chart}</div>'
            f'<div class="pc-foot">בסיס המדד: {escape(str(last.get("base") or "—"))}'
            + (' · התחום המוצלל הוא יעד האינפלציה של בנק ישראל, <span dir="ltr">1%–3%</span>' if code == CPI_CODE else "")
            + '</div></div>')
    if not cards:
        return ""
    return ('<h2 id="cbs-prices">מדדי מחירים</h2>'
            '<p class="cbs-sub cbs-legend"><span><i class="sw sw-bar"></i>שינוי חודשי</span>'
            '<span><i class="sw sw-line"></i>שינוי שנתי</span>'
            '<span><i class="sw sw-band"></i>יעד האינפלציה</span>'
            '<span>25 חודשים אחרונים. מעבר על הגרף מציג את ערכי כל חודש.</span></p>'
            f'<div class="cbs-prices">{"".join(cards)}</div>')


# --------------------------------------------------------------------------
# בקצרה

def brief_html(recent: list[dict], analyses: dict, snap: dict) -> str:
    picked, per_topic = [], {}
    for r in recent:
        a = analyses.get(str(r["id"]))
        if not a or a.get("skip") or not a.get("headline"):
            continue
        t = r.get("topic") or "other"
        if per_topic.get(t, 0) >= BRIEF_PER_TOPIC:
            continue
        per_topic[t] = per_topic.get(t, 0) + 1
        picked.append((r, a))
        if len(picked) >= BRIEF_CARDS:
            break
    if not picked:
        return ""
    cards = []
    for r, a in picked:
        fig = next((f for f in (a.get("key_figures") or []) if isinstance(f, dict) and f.get("value")), None)
        kv = (f'<span class="bc-kv"><span class="v">{_value_html(fig.get("value"))}</span>'
              f'<small class="l">{escape(str(fig.get("label") or ""))}</small></span>') if fig else ""
        cards.append(
            f'<a class="cbs-bc" href="#rel-{escape(str(r["id"]))}">'
            f'<span class="bc-top">{_topic(r.get("topic"), r.get("topic_label"))}'
            f'<span class="bc-date" dir="ltr">{_dm(r.get("date"))}</span></span>'
            f'<span class="bc-title">{escape(r.get("title") or "")}</span>'
            f'{kv}<span class="bc-hl">{escape(str(a.get("headline")))}</span></a>')
    return ('<h2 id="cbs-latest">בקצרה</h2>'
            '<p class="cbs-sub">הקריאה המרכזית של הניתוחים האחרונים. לחיצה על כרטיס מובילה לניתוח המלא.</p>'
            f'<div class="cbs-brief">{"".join(cards)}</div>')


# --------------------------------------------------------------------------
# לוח פרסומים

def _cal_reading(title: str, models: list[dict]) -> str:
    for word, target in CAL_LINKS:
        if word in title:
            if target is None:
                return ""
            m = next((x for x in models if x["title"].startswith(target)), None)
            if not m:
                return ""
            unit = f' {m["unit"]}' if m["unit"] else ""
            return (f'קריאה אחרונה: {escape(m["title"])} <b dir="ltr">{m["value"]}</b>{escape(unit)} '
                    f'({escape(m["period"])})')
    return ""


def calendar_html(snap: dict, rels: list[dict], analyses: dict, models: list[dict]) -> str:
    today = date.today().isoformat()
    hi = (date.today() + timedelta(days=CAL_DAYS)).isoformat()
    rows = [c for c in (snap.get("calendar") or []) if today <= (c.get("date") or "") <= hi]
    if not rows:
        return ""
    latest_by_topic = {}
    for r in rels:
        a = analyses.get(str(r["id"]))
        if a and not a.get("skip"):
            latest_by_topic.setdefault(r.get("topic") or "other", r)
    days: dict[str, list[dict]] = {}
    for c in rows:
        days.setdefault(c["date"], []).append(c)
    blocks = []
    for d, items in days.items():
        wd = WEEKDAYS[datetime.strptime(d, "%Y-%m-%d").weekday()]
        lis = []
        for c in sorted(items, key=lambda c: (not c.get("relevant"), c.get("title") or "")):
            topic = c.get("topic") if c.get("topic") in TOPIC_LABELS else "other"
            meta = [escape(c.get("interval") or "")]
            reading = _cal_reading(c.get("title") or "", models) if c.get("relevant") else ""
            if reading:
                meta.append(reading)
            link = ""
            if d == today:
                cw = _words(c.get("title"))
                pub = next((r for r in rels if r.get("date") == d and cw
                            and len(cw & _words(r.get("title"))) / len(cw | _words(r.get("title"))) >= 0.5), None)
                if pub:
                    a = analyses.get(str(pub["id"]))
                    link = (f'<a class="ci-go" href="#rel-{escape(str(pub["id"]))}">פורסם · לניתוח</a>'
                            if a and not a.get("skip") else '<span class="ci-go wait">פורסם · הניתוח בדרך</span>')
            # רק לפרסום שמזוהה עם מדד: "הניתוח האחרון בנושא" ליד לקט על חברות
            # רב-לאומיות הפנה לניתוח התמ"ג, שאין לו קשר אליו.
            if not link and reading and topic in latest_by_topic:
                prev = latest_by_topic[topic]
                link = (f'<a class="ci-prev" href="#rel-{escape(str(prev["id"]))}">'
                        f'הניתוח האחרון בנושא ({_dm(prev.get("date"))})</a>')
            lis.append(f'<li class="t-{topic}{" rel" if c.get("relevant") else ""}">'
                       f'<i class="tdot" aria-hidden="true"></i><div class="ci">'
                       f'<span class="ci-title">{escape(c.get("title") or "")}</span>'
                       f'<span class="ci-meta">{" · ".join(x for x in meta if x)}</span>{link}</div></li>')
        blocks.append(f'<div class="cbs-day{" today" if d == today else ""}">'
                      f'<div class="cd-date"><b>{wd}</b><span dir="ltr">{_dm(d)}</span>'
                      + ('<span class="cbs-today">היום</span>' if d == today else "")
                      + f'</div><ul class="cd-items">{"".join(lis)}</ul></div>')
    return ('<h2 id="cbs-cal">לוח פרסומים</h2>'
            f'<p class="cbs-sub">{CAL_DAYS} הימים הקרובים לפי לוח הפרסומים של הלמ"ס. פרסום שנוגע לשוק '
            'מודגש ומנותח כשהוא יוצא; לידו הקריאה האחרונה של המדד שהוא מעדכן.</p>'
            f'<div class="cbs-cal">{"".join(blocks)}</div>')


# --------------------------------------------------------------------------
# הודעות וניתוחים

def _figs_html(figs: list[dict]) -> str:
    if not figs:
        return ""
    # **כרטיסים ולא טבלה.** השינוי והתקופה הם משפטים, ובטבלת האתר (שאינה
    # שוברת שורות) הם מתחו אותה לרוחב של מסך וחצי.
    return '<div class="cbs-kf">' + "".join(
        f'<div class="kf"><div class="val">{_value_html(f.get("value"))}</div>'
        f'<div class="lbl">{escape(str(f.get("label") or ""))}</div>'
        + (f'<div class="chg">{escape(str(f.get("change")))}</div>' if f.get("change") else "")
        + (f'<div class="per">{escape(str(f.get("period")))}</div>' if f.get("period") else "")
        + '</div>' for f in figs) + '</div>'


def _body_html(a: dict, figs_rest: list[dict]) -> str:
    out = [_figs_html(figs_rest)]
    if a.get("what_happened"):
        out.append(f'<section class="cbs-sec cbs-prose"><h4>מה פורסם</h4>{_para(a["what_happened"])}</section>')
    macro = [m for m in (a.get("macro") or []) if isinstance(m, dict)]
    if macro:
        out.append('<section class="cbs-sec"><h4>השלכות מאקרו</h4><div class="cbs-cards">'
                   + "".join(f'<div class="cbs-card"><div class="cc-head"><h5>{escape(str(m.get("title") or ""))}</h5>'
                             f'{_dir(m.get("direction"))}</div>{_para(m.get("body"))}</div>' for m in macro)
                   + '</div></section>')
    micro = [m for m in (a.get("micro") or []) if isinstance(m, dict)]
    if micro:
        cards = []
        for m in micro:
            cos = "".join(f'<span class="co">{escape(str(c))}</span>' for c in (m.get("companies") or []))
            meta = " · ".join(x for x in (escape(str(m.get("sector") or "")),
                                          f'קשר {escape(str(m.get("link")))}' if m.get("link") else "") if x)
            cards.append(f'<div class="cbs-card"><div class="cc-head"><h5>{escape(str(m.get("title") or ""))}</h5>'
                         f'{_dir(m.get("direction"))}</div>'
                         + (f'<div class="cc-meta">{meta}</div>' if meta else "")
                         + (f'<div class="cc-cos">{cos}</div>' if cos else "")
                         + f'{_para(m.get("body"))}</div>')
        out.append('<section class="cbs-sec"><h4>השלכות על חברות בבורסה</h4>'
                   f'<div class="cbs-cards">{"".join(cards)}</div></section>')
    if a.get("caveats"):
        out.append(f'<aside class="cbs-caveat"><h4>מה עלול להטעות</h4>{_para(a["caveats"])}</aside>')
    watch = [w for w in (a.get("watch_next") or []) if isinstance(w, dict) and w.get("what")]
    if watch:
        out.append('<section class="cbs-sec"><h4>מה לעקוב</h4><ul class="cbs-watch">'
                   + "".join(f'<li><span class="wn">{escape(_when(w.get("when")) or "—")}</span>'
                             f'<span>{escape(str(w["what"]))}</span></li>' for w in watch)
                   + '</ul></section>')
    terms = [t for t in (a.get("terms") or []) if isinstance(t, dict) and t.get("term")]
    if terms:
        out.append(f'<details class="cbs-terms"><summary>מונחים ({len(terms)})</summary><dl>'
                   + "".join(f'<dt>{escape(str(t["term"]))}</dt><dd>{escape(str(t.get("explain") or ""))}</dd>'
                             for t in terms)
                   + '</dl></details>')
    return "".join(out)


def _excerpt(r: dict, lines: int = 8) -> str:
    """תקציר הלמ"ס כרשימה צפופה, חתוך בגבול שורה."""
    rows = [x.strip() for x in (r.get("summary") or "").splitlines()]
    rows = [x for x in rows if x and x != "להודעה המלאה"]
    if not rows:
        return ""
    items = "".join(f"<li>{escape(x)}</li>" for x in rows[:lines])
    return f'<ul class="cbs-sum">{items}{"<li>…</li>" if len(rows) > lines else ""}</ul>'


def release_html(r: dict, a: dict | None, open_: bool) -> str:
    pdf = next((u for u in (r.get("attachments") or []) if u.lower().split("?")[0].endswith(".pdf")), None)
    analyzed = bool(a and not a.get("skip"))
    status = ('<span class="st done">מנותח</span>' if analyzed
              else '<span class="st wait">ממתין לניתוח</span>')
    links = (f'<a href="{escape(r.get("url") or "#")}" rel="noopener" target="_blank">באתר הלמ"ס</a>'
             + (f'<a href="{escape(pdf)}" rel="noopener" target="_blank">PDF</a>' if pdf else ""))
    head = (f'<div class="rl-meta">{_topic(r.get("topic"), r.get("topic_label"))}'
            f'<span class="rl-date" dir="ltr">{_dmy(r.get("date"))}</span>'
            f'{status}<span class="rl-links">{links}</span></div>'
            f'<h3 class="rl-title">{escape(r.get("title") or "")}</h3>')
    if analyzed:
        figs = [f for f in (a.get("key_figures") or []) if isinstance(f, dict)]
        lead = f'<p class="rl-headline">{escape(str(a.get("headline") or ""))}</p>'
        stamp = a.get("analyzed_at") or ""
        foot = (f'<p class="rl-foot">נותח {escape(stamp[8:10] + "/" + stamp[5:7] + " " + stamp[11:16])} · '
                'ניתוח השפעה, לא המלצת השקעה.</p>') if len(stamp) >= 16 else ""
        if open_:
            inner = lead + _figs_html(figs) + _body_html(a, []) + foot
        else:
            inner = (lead + _figs_html(figs[:PREVIEW_FIGS])
                     + '<details class="cbs-more"><summary>לניתוח המלא</summary>'
                     + _body_html(a, figs[PREVIEW_FIGS:]) + foot + '</details>')
    else:
        inner = ('<p class="cbs-note">הניתוח ייכתב בריצה הקרובה של הצנרת. בינתיים — עיקרי ההודעה '
                 'כפי שפרסמה הלמ"ס:</p>' + _excerpt(r))
    cls = "cbs-rel" + ("" if analyzed else " pending")
    return (f'<article class="{cls}" data-topic="{escape(r.get("topic") or "other")}" '
            f'id="rel-{escape(str(r.get("id")))}">{head}{inner}</article>')


def others_html(rows: list[tuple[dict, dict | None]]) -> str:
    if not rows:
        return ""
    lis = []
    for r, a in rows:
        why = (f' — {escape(str(a.get("reason")))}' if a and a.get("skip") and a.get("reason") else "")
        lis.append(f'<li id="rel-{escape(str(r.get("id")))}"><span class="rl-date" dir="ltr">{_dm(r.get("date"))}</span>'
                   f'<a href="{escape(r.get("url") or "#")}" rel="noopener" target="_blank">'
                   f'{escape(r.get("title") or "")}</a>{why}</li>')
    return (f'<details class="cbs-others"><summary>הודעות נוספות, ללא השלכה שוקית ({len(rows)})</summary>'
            f'<ul>{"".join(lis)}</ul></details>')


SCRIPT = """<script>
(function () {
  "use strict";
  var nav = document.getElementById("cbs-chips");
  var arts = Array.prototype.slice.call(document.querySelectorAll("article.cbs-rel"));
  function filter(t) {
    if (nav) {
      Array.prototype.forEach.call(nav.querySelectorAll("button"), function (x) {
        x.setAttribute("aria-pressed", (x.getAttribute("data-t") || "") === t ? "true" : "false");
      });
    }
    arts.forEach(function (a) { a.hidden = !!t && a.getAttribute("data-topic") !== t; });
  }
  if (nav) {
    nav.hidden = false;
    nav.addEventListener("click", function (e) {
      var b = e.target && e.target.closest ? e.target.closest("button[data-t]") : null;
      if (b) { filter(b.getAttribute("data-t") || ""); }
    });
  }
  // קישור מכרטיס "בקצרה" או מהלוח לניתוח מקופל פותח אותו — ואם הסינון
  // הסתיר אותו, הסינון מתבטל.
  function openTarget() {
    var id = decodeURIComponent((location.hash || "").slice(1));
    var el = id ? document.getElementById(id) : null;
    if (!el || !el.classList.contains("cbs-rel")) { return; }
    if (el.hidden) { filter(""); }
    var more = el.querySelector("details.cbs-more");
    if (more) { more.open = true; }
    el.scrollIntoView();
  }
  window.addEventListener("hashchange", openTarget);
  if (location.hash) { openTarget(); }
})();
</script>"""


def page(data: dict) -> str:
    snap = data.get("snap") or {}
    rels = data.get("releases") or []
    analyses = data.get("analyses") or {}
    if not snap and not rels:
        return ('<h1>נתוני הלמ"ס</h1><p class="lead">טרם נאספו נתונים מהלשכה המרכזית '
                'לסטטיסטיקה. הם ייאספו בריצה הקרובה של צנרת הלמ"ס.</p>')

    since = (date.today() - timedelta(days=DAYS)).isoformat()
    recent = [r for r in rels if (r.get("date") or "") >= since]
    main_rows = [r for r in recent if r.get("relevant")
                 and not (analyses.get(str(r["id"])) or {}).get("skip")]
    other_rows = [(r, analyses.get(str(r["id"]))) for r in recent if r not in main_rows]
    n_an = sum(1 for r in main_rows if analyses.get(str(r["id"])))
    n_wait = len(main_rows) - n_an

    fetched = snap.get("fetched_at") or ""
    stamp = (f'עודכן {fetched[8:10]}/{fetched[5:7]} {fetched[11:16]}' if len(fetched) >= 16 else "")
    errors = snap.get("errors") or {}
    err_html = ('<p class="msg warn">בריצה האחרונה לא נמשכו: ' + escape(", ".join(errors))
                + '. מוצגים הנתונים מהמשיכה המוצלחת האחרונה.</p>') if errors else ""

    models = indicator_models(snap)
    brief = brief_html(recent, analyses, snap)
    ind = indicators_html(models)
    prices = prices_html(snap)
    cal = calendar_html(snap, recent, analyses, models)

    topics = []
    for r in main_rows:
        key = r.get("topic") or "other"
        if key not in [k for k, _ in topics]:
            topics.append((key, r.get("topic_label") or TOPIC_LABELS.get(key, key)))
    chips = ('<div class="cbs-chips" id="cbs-chips" role="group" hidden aria-label="סינון לפי נושא">'
             '<button type="button" data-t="" aria-pressed="true">הכל</button>'
             + "".join(f'<button type="button" data-t="{escape(k)}" aria-pressed="false">'
                       f'<i class="tdot t-{escape(k)}" aria-hidden="true"></i>{escape(l)}</button>'
                       for k, l in topics)
             + '</div>') if len(topics) > 1 else ""

    opened = 0
    arts = []
    for r in main_rows:
        a = analyses.get(str(r["id"]))
        is_open = bool(a) and opened < OPEN_LATEST
        opened += 1 if is_open else 0
        arts.append(release_html(r, a, is_open))

    toc = [("cbs-latest", "בקצרה", brief), ("cbs-ind", "מדדים", ind), ("cbs-prices", "מחירים", prices),
           ("cbs-cal", "לוח פרסומים", cal), ("cbs-rels", "הודעות וניתוחים", True)]
    toc_html = ('<nav class="cbs-toc" aria-label="בעמוד הזה">'
                + "".join(f'<a href="#{i}">{l}</a>' for i, l, present in toc if present) + '</nav>')

    return "\n".join(x for x in [
        '<div class="dash-head"><h1>נתוני הלמ"ס</h1>'
        f'<span class="stamp">{stamp}</span></div>',
        '<p class="lead">הודעות הלשכה המרכזית לסטטיסטיקה, עם ניתוח ההשלכות על המאקרו '
        'ועל חברות בבורסה בתל אביב. הנתונים נמשכים מממשקי הלמ"ס שלוש פעמים ביום.</p>',
        toc_html,
        err_html,
        brief,
        ind,
        prices,
        cal,
        '<h2 id="cbs-rels">הודעות וניתוחים</h2>'
        f'<p class="cbs-sub">{len(main_rows)} הודעות שנוגעות לשוק ב-{DAYS} הימים האחרונים: {n_an} מנותחות'
        + (f', {n_wait} ממתינות לניתוח' if n_wait else "")
        + '. הניתוחים נכתבים על בסיס ההודעה ונתוני הלמ"ס בלבד, וכל מספר בהם לקוח משם. '
        '<b>ניתוח השפעה, לא המלצת השקעה.</b></p>',
        chips,
        "".join(arts) or '<p class="cbs-note">אין הודעות בתקופה.</p>',
        others_html(other_rows),
        SCRIPT,
    ] if x)


def report(data: dict) -> list[str]:
    """שורות אנוטציה לבנייה: מה נבנה, ומה חסר."""
    snap = data.get("snap") or {}
    rels = data.get("releases") or []
    analyses = data.get("analyses") or {}
    if not snap and not rels:
        return ['::warning title=אין נתוני למ"ס::output/cbs ריק — עמוד הלמ"ס נבנה בלי נתונים.']
    since = (date.today() - timedelta(days=DAYS)).isoformat()
    recent = [r for r in rels if (r.get("date") or "") >= since]
    rel_ok = [r for r in recent if r.get("relevant")]
    done = [r for r in rel_ok if str(r["id"]) in analyses]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    stuck = [r for r in rel_ok if str(r["id"]) not in analyses and (r.get("date") or "") <= yesterday]
    models = indicator_models(snap)
    no_trend = [m["title"] for m in models if not m["spark"]]
    out = [f'::notice::נתוני הלמ"ס: {len(recent)} הודעות ב-{DAYS} יום, {len(done)}/{len(rel_ok)} '
           f'רלוונטיות נותחו · לוח {len(snap.get("calendar") or [])} · מדדים {len(models)} '
           f'({len(models) - len(no_trend)} עם מגמה) · משיכה {snap.get("fetched_at") or "—"}']
    if no_trend and snap.get("history"):
        out.append('::warning title=מדדי למ"ס בלי מגמה::' + " · ".join(no_trend[:8])
                   + ' — אין להם היסטוריה ב-snapshot; בדוק את שלב היסטוריית המדדים ב-cbs_pull.')
    fetched = snap.get("fetched_at")
    if fetched:
        try:
            age = datetime.now().astimezone() - datetime.fromisoformat(fetched)
            if age > timedelta(hours=30):
                out.append(f'::warning title=נתוני הלמ"ס ישנים::המשיכה האחרונה מ-{fetched} — '
                           'צנרת cbs-watch לא רצה או נכשלה.')
        except ValueError:
            pass
    if stuck:
        out.append('::warning title=הודעות למ"ס בלי ניתוח::' + " · ".join(
            f'{r.get("date")} {str(r.get("title"))[:50]}' for r in stuck[:6])
            + ' — ממתינות יותר מיום; בדוק את שלב הניתוח ב-cbs-watch.')
    return out
