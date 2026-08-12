# -*- coding: utf-8 -*-
"""משמר תוצרי ingest שהאתר צריך, כדי שכל בנייה תוכל להציג אותם.

`data/raw/` מוחרג מגיט. כש-maya-watch בונה את האתר (כל רבע שעה) ה-runner
שלו לא ראה מעולם את markets.json — הוא נוצר בריצת הברייף על מכונה אחרת.
כתוצאה מכך כל בנייה שאינה ריצת ברייף איבדה חלקים מהדשבורד:

- לוח המקורות הופיע כולו ב-✗ אדום (תוקן כאן קודם)
- **רצועת השווקים ופאנל האינדיקטורים נעלמו לגמרי** — נמדד באתר החי:
  הרצועה קיימת אחרי ריצת ברייף ונעלמת במחזור הניטור הבא, 96 פעמים ביום

לכן שלושת התוצרים נשמרים ל-output/ ומקובעים לריפו:
  output/status/<date>.json   — מצב המקורות
  output/markets/<date>.json  — שערים ומדדים
  output/te/<date>.json       — Trading Economics

נקרא מ-run_daily.sh מיד אחרי ה-ingest, כשהקבצים עוד קיימים.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    ("RSS", "rss.jsonl"),
    ("Gmail", "gmail.jsonl"),
    ("מאיה", "maya.jsonl"),
    ("שווקים", "markets.json"),
    ('רמ"י', "rmi.json"),
    ("Trading Economics", "te.json"),
]


def measure(raw_dir: Path) -> list[dict]:
    out = []
    for label, fname in CHECKS:
        p = raw_dir / fname
        if not p.exists() or p.stat().st_size == 0:
            out.append({"label": label, "ok": False, "detail": ""})
            continue
        if fname.endswith(".jsonl"):
            n = sum(1 for line in p.open(encoding="utf-8") if line.strip())
            detail = f"{n} פריטים"
        else:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                out.append({"label": label, "ok": False, "detail": "קובץ פגום"})
                continue
            n = len(d.get("instruments") or d.get("results") or d.get("bonds") or [])
            detail = f"{n} רשומות" if n else "נטען"
        out.append({"label": label, "ok": True, "detail": detail})
    return out


def main() -> int:
    day = date.today().isoformat()
    raw_dir = ROOT / "data" / "raw" / day
    if not raw_dir.exists():
        print("אין data/raw להיום — לא נכתב סטטוס")
        return 0
    payload = {"date": day,
               "generated_at": datetime.now().isoformat(timespec="seconds"),
               "sources": measure(raw_dir)}
    out_dir = ROOT / "output" / "status"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{day}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for s in payload["sources"] if s["ok"])

    # שימור התוצרים שהדשבורד מציג. העתקה ולא קישור: הקובץ ב-data/raw נמחק
    # עם ה-runner, וזה שב-output מקובע לריפו וזמין לכל בנייה עתידית.
    kept = []
    for src, sub in (("markets.json", "markets"), ("te.json", "te")):
        p = raw_dir / src
        if not p.exists() or p.stat().st_size == 0:
            continue
        d = ROOT / "output" / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{day}.json").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        kept.append(sub)
    print(f"נכתב סטטוס מקורות: {ok}/{len(payload['sources'])} תקינים"
          + (f" · נשמרו לאתר: {', '.join(kept)}" if kept else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
