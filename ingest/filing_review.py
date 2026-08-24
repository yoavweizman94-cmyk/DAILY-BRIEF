# -*- coding: utf-8 -*-
"""סקירה מעמיקה לכל דוח כספי של חברת כיסוי.

התוצר נשמר ב-`output/filings/reviews/<id>.md` ומוגש בעמוד הדוחות בלחיצה.

**למה מראש ולא לפי דרישה.** סקירה בלחיצה הייתה מחייבת מפתח API בקצה
הציבורי, עלות לכל קליק, והמתנה של דקה מול מסך ריק. הכנה מראש בצנרת
היומית נותנת תשובה מיידית, עלות ידועה, ואת אותם מעקות שחלים על הברייף.

**ה-PDF נשלח כמות שהוא ולא כטקסט מחולץ.** חילוץ טקסט מדוחות בעברית
מערבב עמודות ומעוות ספרות — נמדד בדוח אלרוב, שבו שורת סך ההכנסות
יצאה בלתי קריאה. המודל קורא את הקובץ עצמו, כולל טבלאות.

**מעקות שחלים כאן במלואם** (CLAUDE.md): כל מספר מגוף הדוח בלבד; אין
המלצות קנייה או מכירה; ומה שלא נמצא בדוח נאמר כחסר ולא מושלם.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tls import harden  # noqa: E402

harden()

import anthropic  # noqa: E402
from curl_cffi import requests as creq  # noqa: E402

from _filings import is_financial, reviewable  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FILINGS = ROOT / "output" / "filings"
REVIEWS = FILINGS / "reviews"
FILES = "https://mayafiles.tase.co.il/"

MODEL = "claude-opus-5"
# מגבלת הבקשה היא 32MB; נשארים מתחת לה בבטחה, ומעליה עוברים לחילוץ טקסט.
MAX_PDF_BYTES = 28 * 1024 * 1024



SYSTEM = """אתה אנליסט מחקר שכותב עבור מנהל השקעות מקצועי. אתה מקבל דוח
כספי של חברה ציבורית בבורסה בתל אביב, וכותב עליו סקירה בעברית.

הקורא יודע לפתוח את הדוח בעצמו. מה שהוא קונה ממך הוא הקריאה **מתחת**
למספרים — לא ציטוט של שורת ההכנסות והרווח.

כללים שאין לחרוג מהם:

1. **כל מספר מגוף הדוח בלבד.** אין לך ידע עצמאי על החברה. אם נתון אינו
   בדוח, כתוב שהוא אינו שם — אל תשלים מהזיכרון ואל תעריך.
2. **אין המלצות השקעה.** ניתוח השפעה — כן. "כדאי לקנות/למכור", "המניה
   זולה/יקרה", "מומלץ" — לעולם לא. גם לא ברמז.
3. **הפרד עובדה מפרשנות.** מספר מהדוח הוא עובדה; מה שהוא אומר הוא
   פרשנות, ויש לסמן אותה במילה "משמעות:" בתחילת המשפט.
4. עברית בלבד. מונחים באנגלית מותרים היכן שמקובל (FFO, EBITDA, cap rate).
5. ענייני וישיר. בלי סופרלטיבים, בלי "חשוב לציין", בלי ריפוד.

כתוב **בדיוק** את המבנה הבא, בכותרות markdown, ובלי שום טקסט לפניו או
אחריו:

## בשורה אחת
משפט אחד, עד 25 מילים, שאומר מה קרה בדוח הזה.

## המספרים
טבלת markdown: שורה לכל נתון מרכזי שיש בדוח — הכנסות, רווח גולמי, רווח
תפעולי, רווח נקי, EBITDA, תזרים מפעילות שוטפת, הון עצמי, וכל מדד שהחברה
עצמה מדגישה (NOI, FFO, צבר). עמודות: מדד | התקופה | מקבילה | שינוי.
אם נתון אינו בדוח — אל תמציא שורה עבורו.

## מה הניע את התוצאה
מחיר מול כמות מול תמהיל מול מט"ח. "ההכנסות עלו 12%" הוא נתון; "ההכנסות
עלו 12% כולן ממחיר בעוד הכמויות ירדו 3%" הוא ניתוח. אם הדוח מפרט מגזרים,
אמור איזה מגזר הזיז את התוצאה ובכמה.

## האם זה חוזר על עצמו
רווח שנשען על מימוש נכס, שערוך, הפרשי שער או הכנסה חד-פעמית — לציין
במפורש ולהפריד מהרווח התפעולי השוטף. אם ההנהלה מציגה נתון מנוטרל, הבא
אותו ואמור מה נוטרל.

## שולי הרווח
בכל רמה שהדוח מפרט — גולמי, תפעולי, נקי. חשב את השיעור ואמור למה זז.
שים לב לפער בין כיוון המרווח לכיוון ההכנסות; זה לרוב עיקר הסיפור.

## תזרים מול רווח
האם התזרים התפעולי תומך ברווח החשבונאי. פער מתמשך בין השניים הוא האייטם,
לא הרווח.

## מה השתנה במבנה
מגזרים, צבר, ריכוזיות לקוחות, כושר ייצור, מינוף, אמות מידה פיננסיות,
מועדי פירעון, שינויים בהון.

## סימנים שדורשים מבט
לקוחות או מלאי שגדלים מהר מההכנסות, היוון עלויות, שינוי מדיניות
חשבונאית, עסקאות בעלי עניין, הערת עסק חי, הפניית תשומת לב של רואה
החשבון. אם אין — כתוב "לא נמצאו".

## מה הדוח לא אומר
נתון שהופסק פרסומו, מגזר שאוחד, תחזית שנמשכה בלי הסבר, וכל דבר שציפית
למצוא ולא מצאת. אם חלק מהדוח לא היה קריא — אמור זאת כאן במפורש.
"""


def load_index() -> list[dict]:
    rows = []
    for f in sorted(FILINGS.glob("[0-9][0-9][0-9][0-9].jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def candidates(rows: list[dict], since: str | None = None) -> list[dict]:
    """דוחות כספיים של חברות כיסוי שיש להם קובץ וטרם נסקרו.

    **חסום בתאריך.** האינדקס מגיע עד 2024, ולסקור את כולו זה מאות בקשות
    ומאות דולרים בבת אחת. הקורא מחפש את הדוח האחרון, לא את זה של לפני
    שנתיים, ולכן ברירת המחדל היא השנתיים האחרונות — והמצטבר גדל מהחדש
    אל הישן, ריצה אחרי ריצה.
    """
    out = []
    for r in rows:
        if not reviewable(r):
            continue
        if since and (r.get("d") or "") < since:
            continue
        if (REVIEWS / f"{r['id']}.md").exists():
            continue
        out.append(r)
    # החדשים קודם — הם מה שהקורא מחפש
    out.sort(key=lambda r: r.get("d") or "", reverse=True)
    return out


def fetch_pdf(path: str) -> bytes | None:
    for i in range(3):
        try:
            r = creq.get(FILES + path, impersonate="chrome", timeout=180)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                return r.content
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 * (i + 1))
    return None


def as_text(blob: bytes) -> str | None:
    """נפילה חלופית לקובץ שגדול מדי לשליחה. פחות מדויק — ונאמר בסקירה."""
    try:
        import io

        import pypdf
        rd = pypdf.PdfReader(io.BytesIO(blob))
        return "\n".join((p.extract_text() or "") for p in rd.pages)
    except Exception:  # noqa: BLE001
        return None


def review_one(client: anthropic.Anthropic, rec: dict, blob: bytes) -> str | None:
    who = ", ".join(rec.get("c") or []) if isinstance(rec.get("c"), list) else str(rec.get("c"))
    head = (f"חברה: {who}\nכותרת הדיווח: {rec.get('t')}\n"
            f"תאריך הדיווח: {rec.get('d')}\nמזהה מאיה: {rec.get('id')}")

    if len(blob) <= MAX_PDF_BYTES:
        doc = {"type": "document",
               "source": {"type": "base64", "media_type": "application/pdf",
                          "data": base64.standard_b64encode(blob).decode()}}
        content = [doc, {"type": "text", "text": head + "\n\nכתוב את הסקירה."}]
    else:
        txt = as_text(blob)
        if not txt:
            return None
        content = [{"type": "text",
                    "text": head + "\n\n**הערה: הדוח גדול מכדי לשלוח כקובץ, "
                    "ולכן להלן טקסט שחולץ ממנו. החילוץ עלול לערבב עמודות — "
                    "ציין זאת בסעיף 'מה הדוח לא אומר'.**\n\n" + txt
                    + "\n\nכתוב את הסקירה."}]

    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        print(f"  סירוב: {getattr(msg.stop_details, 'category', '?')}", file=sys.stderr)
        return None
    return "".join(b.text for b in msg.content if b.type == "text").strip() or None


def write_index() -> int:
    """רשימת המזהים שיש להם סקירה — העמוד קורא אותה כדי לדעת מתי להציג כפתור."""
    ids = sorted(p.stem for p in REVIEWS.glob("*.md"))
    (REVIEWS / "index.json").write_text(
        json.dumps({"ids": ids, "updated": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False), encoding="utf-8")
    return len(ids)


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("::error::ANTHROPIC_API_KEY חסר — אי אפשר לכתוב סקירות", file=sys.stderr)
        return 1
    if not FILINGS.exists():
        print("::error::אין אינדקס דוחות — הרץ קודם את משיכת התוכן", file=sys.stderr)
        return 1

    REVIEWS.mkdir(parents=True, exist_ok=True)
    limit = int(os.environ.get("REVIEW_LIMIT") or 8)
    since = os.environ.get("REVIEW_SINCE") or f"{date.today().year - 1}-01-01"
    pending = candidates(load_index(), since)
    todo = pending[:limit]
    print(f"ממתינים לסקירה מאז {since}: {len(pending)} | בריצה זו: {len(todo)}")
    if not todo:
        print("אין דוחות חדשים לסקירה")
        write_index()
        return 0

    client = anthropic.Anthropic()
    done, failed = 0, 0
    for rec in todo:
        who = ", ".join(rec.get("c") or [])
        print(f"  {rec['d']} {who[:22]:<23} {rec['t'][:44]}", flush=True)
        blob = fetch_pdf(rec["p"])
        if not blob:
            print("    הקובץ לא נמשך — מדולג", file=sys.stderr)
            failed += 1
            continue
        try:
            md = review_one(client, rec, blob)
        except anthropic.APIStatusError as e:
            print(f"    שגיאת API {e.status_code} — מדולג", file=sys.stderr)
            failed += 1
            continue
        except Exception as e:  # noqa: BLE001
            print(f"    {type(e).__name__} — מדולג", file=sys.stderr)
            failed += 1
            continue
        if not md:
            failed += 1
            continue
        meta = {"id": rec["id"], "date": rec["d"], "title": rec["t"],
                "companies": rec.get("c"), "model": MODEL,
                "generated": datetime.now().isoformat(timespec="seconds"),
                "pdf_bytes": len(blob)}
        (REVIEWS / f"{rec['id']}.md").write_text(
            "<!--" + json.dumps(meta, ensure_ascii=False) + "-->\n" + md,
            encoding="utf-8")
        done += 1

    total = write_index()
    print(f"\nנכתבו {done} סקירות ({failed} נכשלו) | סה\"כ בארכיון: {total}")
    if failed and not done:
        print("::error::אף סקירה לא נכתבה", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
