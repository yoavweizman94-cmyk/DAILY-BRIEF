# -*- coding: utf-8 -*-
"""אינדקס דוחות כספיים של כל החברות בבורסה, לחיפוש והורדה ישירה מהאתר.

למה אינדקס ולא קריאה חיה מהדפדפן: ל-API של מאיה אין CORS, והוא מחזיר 403
לבקשה שמגיעה מדפדפן בדומיין זר. לעומת זאת mayafiles.tase.co.il (שרת הקבצים)
כן מגיש עם `Access-Control-Allow-Origin: *` — ולכן הקישור להורדה עובד ישירות
מהאתר, וכל מה שצריך לייצר כאן הוא רשימת הדוחות ונתיבי ה-PDF שלהם.

המגבלה שקובעת את המבנה כאן היא **תקרת עימוד**, לא חסימת WAF: בקשה עם offset
מעל ~1000 מוחזרת כ-HTTP 400 (ראה OFFSET_CEILING ב-_maya_api.py). בנפח של
~180 דיווחים ביום, חלון של שבוע חוצה את התקרה ומחזיר 400 שנראה כמו חסימה
אקראית. לכן החלון הוא 4 ימים, ו-harvest מפצל אותו לבד אם בכל זאת נחצתה.

שני מצבי הרצה:

  --recent N   חלון קצר (ברירת מחדל 3 ימים) — רץ בצנרת היומית, עלות זניחה.
               זו הדרך שבה האינדקס גדל בפועל, יום אחר יום.
  --backfill   הליכה אחורה עם תקציב זמן. שומר מצב אחרי כל חלון, כך שהפסקה
               או כשל אינם מאבדים דבר וההרצה הבאה ממשיכה מאותה נקודה.

פלט: output/filings/<שנה>.jsonl + manifest.json (נטענים ע"י site/pages/filings.html)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402

harden()

from _maya_api import MayaSession, WindowTooLarge  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "filings"
STATE = ROOT / "data" / "maya_index_state.json"

# מה נחשב "דוח כספי". ת930 (תקופתי/רבעוני) ו-ת950 (אותו דוח ב-iXBRL) הם
# ודאיים ונכנסים לפי הטופס. השאר מזוהה לפי כותרת, כי חברות דואליות ותאגידי
# חוב מדווחים בטפסים אחרים (C001, C002, ת150, ת031).
FIN_FORMS = {"ת930", "ת950"}
FIN_TITLE = re.compile(
    r"דוח(?:ות)?\s*(?:כספי|רבעון|רבעוני|תקופתי|שנתי|חצי[-\s]*שנתי)"
    r"|דוחות\s+כספיים|תמצית\s+דוחות|financial\s+statements|10[-\s]?Q|6[-\s]?K",
    re.IGNORECASE)
# הודעה על **מועד** פרסום עתידי אינה דוח. נמדד: 12 מתוך 16 דיווחי ת121 שנתפסו
# בסינון לפי כותרת היו הודעות כאלה — רעש שמטביע את הדוחות עצמם.
NOISE_TITLE = re.compile(r"מועד\s+פרסום|הודעה\s+על\s+מועד|זימון\s+אסיפה")
# מצגת תוצאות היא חומר שאנליסט רוצה, אבל היא לא הדוח — תיוג נפרד, לא הדרה.
PRESENTATION = re.compile(r"מצגת|presentation", re.IGNORECASE)

# נפח נמדד: ~180 דיווחים ביום בכל הבורסה, כלומר ~1,250 לשבוע — מעל תקרת
# העימוד של 1,000. חלון של 4 ימים (~720) נשאר מתחתיה גם בעונת הדוחות, ואם
# בכל זאת נחצתה, harvest מפצל את החלון בעצמו.
WINDOW_DAYS = 4
BACKFILL_PAUSE = 6.0     # שהייה בין חלונות
THROTTLE = 1.0           # בין עמודים בתוך חלון (0.4 היא ברירת המחדל היומית)
MAX_RETRIES = 2          # ניסיונות עם סשן חדש לפני שמוותרים על החלון


def classify(rep: dict) -> str | None:
    """'דוח' / 'מצגת' / None אם אינו רלוונטי לאינדקס."""
    title = rep.get("title") or ""
    if (rep.get("formId") or "") in FIN_FORMS:
        return "דוח"                      # הטופס מכריע, תהיה הכותרת אשר תהיה
    if PRESENTATION.search(title):
        return "מצגת" if FIN_TITLE.search(title) else None
    if NOISE_TITLE.search(title):
        return None
    return "דוח" if FIN_TITLE.search(title) else None


def coverage_names() -> set[str]:
    cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    names = set()
    for c in cfg.get("companies") or []:
        for k in ("name_he", "name_en"):
            if c.get(k):
                names.add(str(c[k]).strip())
    return names


def pdf_of(rep: dict) -> tuple[str | None, int]:
    """נתיב ה-PDF היחסי + גודלו ב-KB. fileType מגיע כ-pdf1/pdf2 ולא כ-pdf,
    ו-fileSize הוא קילובייטים (נבדק: fileSize=457 מול קובץ של 468,608 בתים)."""
    best, size = None, 0
    for a in rep.get("attachments") or []:
        if (a.get("fileType") or "").lower().startswith("pdf") and a.get("url"):
            if not best or (a.get("fileSize") or 0) > size:
                best, size = a["url"].lstrip("/"), a.get("fileSize") or 0
    return best, size


def to_entry(rep: dict, cover: set[str], kind: str) -> dict | None:
    pdf, size = pdf_of(rep)
    ts = rep.get("publishDate") or ""
    day = ts[:10]
    if not day:
        return None
    comps = [c.get("name") for c in (rep.get("companies") or []) if c.get("name")]
    return {
        "id": str(rep.get("id")),
        "d": day,
        "t": (rep.get("title") or "").strip(),
        "f": rep.get("formId") or "",
        "c": comps,
        "ci": [c.get("companyId") for c in (rep.get("companies") or []) if c.get("companyId")],
        "p": pdf,                                   # יחסי ל-mayafiles.tase.co.il
        "s": size,                                  # KB
        "k": kind,                                  # דוח / מצגת
        "cov": 1 if any(n in cover for n in comps) else 0,
    }


# --- קריאה/כתיבה של האינדקס -------------------------------------------------

def load_index() -> dict[str, dict]:
    idx = {}
    for f in OUT.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    e = json.loads(line)
                    idx[e["id"]] = e
                except (json.JSONDecodeError, KeyError):
                    pass
    return idx


def save_index(idx: dict[str, dict]) -> bool:
    """כותב את האינדקס ומחזיר האם התוכן באמת השתנה.

    ה-workflow מחליט לפי `git status` אם לקבע ולפרוס. כשחותמת הזמן נכתבה
    בכל הרצה, ריצה שלא הוסיפה אף דוח עדיין נראתה כשינוי — וגררה קומיט,
    בנייה ופריסה על לא כלום. לכן החותמת מתעדכנת רק כשהנתונים זזו.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, list] = {}
    for e in idx.values():
        by_year.setdefault(e["d"][:4], []).append(e)

    changed = False
    for f in OUT.glob("*.jsonl"):          # שנים שהתרוקנו לא נשארות מאחור
        if f.stem not in by_year:
            f.unlink()
            changed = True

    years = []
    for y, rows in sorted(by_year.items()):
        rows.sort(key=lambda e: e["d"], reverse=True)
        body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
        path = OUT / f"{y}.jsonl"
        if not path.exists() or path.read_text(encoding="utf-8") != body:
            path.write_text(body, encoding="utf-8")
            changed = True
        years.append({"year": y, "count": len(rows)})

    prev = {}
    try:
        prev = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        changed = True

    days = sorted(e["d"] for e in idx.values())
    (OUT / "manifest.json").write_text(json.dumps({
        "years": sorted(years, key=lambda x: x["year"], reverse=True),
        "total": len(idx),
        "earliest": days[0] if days else None,
        "latest": days[-1] if days else None,
        "updated": (datetime.now().isoformat(timespec="seconds") if changed
                    else prev.get("updated")),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return changed


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


# --- מצבי הרצה ---------------------------------------------------------------

def harvest(s: MayaSession, a: date, b: date, idx: dict, cover: set[str],
            depth: int = 0) -> int:
    """שואב חלון אחד. חלון צפוף מדי מפוצל לשניים ונשאב לחלקיו."""
    try:
        rows = s.reports_days(a, b)
    except WindowTooLarge as exc:
        if a >= b:
            # יום בודד מעל התקרה — אין מה לפצל. עדיף לדעת מזה לשתוק.
            print(f"  {a}: {exc.total} דיווחים ביום אחד, מעל תקרת העימוד — "
                  f"חלק מהיום לא ייכנס לאינדקס", file=sys.stderr)
            return 0
        mid = a + (b - a) // 2
        print(f"  {a}→{b}: {exc.total} דיווחים, מפוצל", file=sys.stderr)
        return (harvest(s, a, mid, idx, cover, depth + 1) +
                harvest(s, mid + timedelta(days=1), b, idx, cover, depth + 1))
    added = 0
    for rep in rows:
        kind = classify(rep)
        if not kind:
            continue
        e = to_entry(rep, cover, kind)
        if e and e["id"] not in idx:
            idx[e["id"]] = e
            added += 1
        elif e:
            idx[e["id"]] = e          # עדכון: קבצים מצורפים מתווספים אחרי הפרסום
    return added


def run_recent(days: int) -> int:
    cover, idx = coverage_names(), load_index()
    before = len(idx)
    s = MayaSession()
    today = date.today()
    added = harvest(s, today - timedelta(days=days - 1), today, idx, cover)
    save_index(idx)
    print(f"אינדקס דוחות: +{added} חדשים, {len(idx)} סה\"כ "
          f"(היו {before}, חלון {days} ימים)")
    return 0


def run_backfill(until: date, budget_min: float) -> int:
    cover, idx = coverage_names(), load_index()
    st = read_state()
    cursor = date.fromisoformat(st["backfill_earliest"]) if st.get("backfill_earliest") \
        else date.today()
    deadline = time.monotonic() + budget_min * 60
    s = MayaSession(throttle_sec=THROTTLE)
    total, windows = 0, 0

    while cursor > until and time.monotonic() < deadline:
        b = cursor - timedelta(days=1)
        a = max(until, b - timedelta(days=WINDOW_DAYS - 1))
        # תקלת רשת או 403 חולף: סשן חדש מזריע עוגיות WAF מחדש מדף הבית
        # ולרוב עובר. חלון צפוף מדי כבר טופל בתוך harvest ואינו מגיע לכאן.
        ok = False
        for attempt in range(MAX_RETRIES + 1):
            try:
                total += harvest(s, a, b, idx, cover)
                windows += 1
                cursor = a
                st["backfill_earliest"] = cursor.isoformat()
                ok = True
                break
            except Exception as exc:
                code = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt == MAX_RETRIES or time.monotonic() > deadline:
                    print(f"עצירה ב-{a}: {type(exc).__name__} {code or str(exc)[:60]}",
                          file=sys.stderr)
                    break
                wait = BACKFILL_PAUSE * (attempt + 2)
                print(f"  {a}: {code or type(exc).__name__} — סשן חדש בעוד {wait:.0f}s",
                      file=sys.stderr)
                time.sleep(wait)
                s = MayaSession(throttle_sec=THROTTLE)
        save_index(idx)                 # שמירה אחרי כל חלון — הפסקה לא מאבדת כלום
        write_state(st)
        if not ok:
            break
        time.sleep(BACKFILL_PAUSE)

    save_index(idx)
    write_state(st)
    done = cursor <= until
    print(f"מילוי אחורה: {windows} חלונות, +{total} דוחות, {len(idx)} סה\"כ · "
          f"הגיע עד {cursor} · {'הושלם' if done else 'ימשיך בהרצה הבאה'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="אינדקס דוחות כספיים ממאיה")
    p.add_argument("--recent", type=int, default=3, metavar="ימים",
                   help="חלון קדימה לצנרת היומית (ברירת מחדל: 3)")
    p.add_argument("--backfill", action="store_true",
                   help="הליכה אחורה בזמן במקום חלון עדכני")
    p.add_argument("--until", default="2023-01-01", metavar="YYYY-MM-DD",
                   help="עד לאיזה תאריך למלא אחורה")
    p.add_argument("--budget-minutes", type=float, default=25.0,
                   help="תקציב זמן להרצת מילוי אחת")
    args = p.parse_args()
    if args.backfill:
        return run_backfill(date.fromisoformat(args.until), args.budget_minutes)
    return run_recent(args.recent)


if __name__ == "__main__":
    sys.exit(main())
