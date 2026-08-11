# -*- coding: utf-8 -*-
"""שומר את מצב המקורות של הריצה כתוצר קבוע ב-output/status/<date>.json.

למה: לוח המקורות באתר בדק קבצים ב-`data/raw/`, שמוחרג מגיט. כש-maya-watch
בונה את האתר ה-runner שלו לא ראה מעולם את markets.json או rss.jsonl — הם
נוצרו בריצת הברייף על מכונה אחרת — וכל המקורות הופיעו כ-✗ אדום.

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
    print(f"נכתב סטטוס מקורות: {ok}/{len(payload['sources'])} תקינים")
    return 0


if __name__ == "__main__":
    sys.exit(main())
