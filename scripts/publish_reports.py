# -*- coding: utf-8 -*-
"""מעתיק את סיכומי מאיה של היום מ-data/raw (שאינו בגיט) ל-output/reports.

data/raw/ מוחרג מהריפו כדי לא להטביע אותו בקלט גולמי, אבל הסיכומים עצמם
הם תוצר שצריך לשרוד — גם כדי שהאתר ייבנה מהם וגם כארכיון.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    day = date.today().isoformat()
    src = ROOT / "data" / "raw" / day / "maya_summaries.jsonl"
    if not src.exists():
        print("אין סיכומים היום")
        return 0
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        print("קובץ הסיכומים ריק")
        return 0

    dst_dir = ROOT / "output" / "reports"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{day}.jsonl"

    # מיזוג עם מה שכבר פורסם היום — הריצה רצה כל רבע שעה
    merged: dict[str, dict] = {}
    if dst.exists():
        for line in dst.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                merged[r["id"]] = r
    for r in rows:
        merged[r["id"]] = r

    with dst.open("w", encoding="utf-8", newline="\n") as f:
        for r in sorted(merged.values(), key=lambda x: x.get("ts") or ""):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"פורסמו {len(merged)} סיכומים → {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
