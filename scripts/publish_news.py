# -*- coding: utf-8 -*-
"""מסווג את חדשות היום לנושאים ושומר אותן כתוצר קבוע.

למה זה נחוץ: `data/raw/` מוחרג מהריפו, כך שהחדשות נעלמות אחרי הריצה. עמודי
הנושאים באתר צריכים להצטבר לאורך זמן, ולכן האייטמים המסווגים נשמרים ל-
`output/news/<date>.jsonl` — בלי גוף הכתבה, רק כותרת, מקור, קישור ונושאים.

הסיווג במילות מפתח ולא ב-LLM: ~330 אייטמים ביום, וסיווג במודל היה מכפיל את
עלות ההרצה בלי להוסיף דיוק ממשי על טקסונומיה של 12 נושאים.

שימוש: python scripts/publish_news.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("rss.jsonl", "gmail.jsonl")
MAX_MATCH_CHARS = 4000        # מספיק לכותרת ולפתיח; מייל שלם רק מרעיש


def norm(s: str) -> str:
    """נרמול לצורך התאמה: גרשיים עבריים/טיפוגרפיים → אחידים, רווחים מכווצים."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("״", '"').replace("׳", "'")
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", s).lower()


def build_matchers(topics: list[dict]):
    out = []
    for t in topics:
        pats = []
        for kw in t.get("keywords") or []:
            k = norm(kw).strip()
            if not k:
                continue
            # גבולות מילה רק לצדדים אלפאנומריים — עברית ורווחים מטופלים כרגיל
            pats.append(re.compile(r"(?<![\w֐-׿])" + re.escape(k)
                                   + r"(?![\w֐-׿])"))
        out.append((t["slug"], t["label"], pats))
    return out


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    topics = cfg.get("topics") or []
    if not topics:
        print("שגיאה: אין נושאים מוגדרים תחת topics ב-sources.yaml", file=sys.stderr)
        return 1
    matchers = build_matchers(topics)

    day = date.today().isoformat()
    raw_dir = ROOT / "data" / "raw" / day
    items: list[dict] = []
    for fname in SOURCES:
        p = raw_dir / fname
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not items:
        print("אין אייטמי חדשות היום")
        return 0

    classified, counts = [], {}
    for it in items:
        blob = norm(f"{it.get('title','')} {(it.get('body') or '')[:MAX_MATCH_CHARS]}")
        hits = [(slug, label) for slug, label, pats in matchers
                if any(p.search(blob) for p in pats)]
        if not hits:
            continue
        for slug, _ in hits:
            counts[slug] = counts.get(slug, 0) + 1
        classified.append({
            "id": it.get("id"), "ts": it.get("ts"), "title": it.get("title"),
            "url": it.get("url"), "source": it.get("source"),
            "topics": [s for s, _ in hits],
        })

    out_dir = ROOT / "output" / "news"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{day}.jsonl"

    # דה-דופ חוצה-מקורות: אותו פיד נמשך גם ב-rss וגם ב-feedly, וה-id שונה
    # בין השניים. המפתח הוא הקישור, ובהיעדרו הכותרת המנורמלת.
    def key(r: dict) -> str:
        return (r.get("url") or "").split("#")[0].rstrip("/") or norm(r.get("title", ""))

    merged: dict[str, dict] = {}
    if dst.exists():                       # שלוש מהדורות ביום כותבות לאותו קובץ
        for line in dst.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                merged[key(r)] = r
    for r in classified:
        k = key(r)
        if k in merged:                    # שמירת איחוד הנושאים משני המקורות
            r["topics"] = sorted(set(r["topics"]) | set(merged[k].get("topics") or []))
        merged[k] = r

    with dst.open("w", encoding="utf-8", newline="\n") as f:
        for r in sorted(merged.values(), key=lambda x: x.get("ts") or "", reverse=True):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    top = ", ".join(f"{s}={n}" for s, n in sorted(counts.items(), key=lambda x: -x[1])[:6])
    print(f"סווגו {len(classified)}/{len(items)} אייטמים → {dst} | {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
