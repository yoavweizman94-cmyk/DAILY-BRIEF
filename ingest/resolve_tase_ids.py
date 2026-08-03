# -*- coding: utf-8 -*-
"""ממלא tase_id (מספר נייר ראשי) ו-maya_company_id ב-config/companies.yaml מול מאיה.

בקרת איכות לפי CLAUDE.md: שם שלא נמצא או שההתאמה שלו עמומה — שגיאה מפורשת
בסוף הריצה וקוד יציאה 1. לא מנחשים.

שימוש:
    python ingest/resolve_tase_ids.py [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML

sys.path.insert(0, str(Path(__file__).parent))
from _maya_api import MayaSession

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "companies.yaml"

_QUOTES = "\"'`״׳"


def norm(s: str) -> str:
    s = s.translate({ord(c): None for c in _QUOTES})
    s = s.replace("בעמ", " ").replace(".", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> frozenset:
    return frozenset(norm(s).split())


def candidate_names(c: dict) -> tuple[str, str]:
    """(שם קצר, שם רשמי) מתוך תוצאת autocomplete."""
    value = c.get("value") or ""
    label = c.get("label") or ""
    short = label[: -len(value)].strip() if value and label.endswith(value) else label
    return short or value, value


def pick(candidates: list[dict], queries: list[str]) -> tuple[dict | None, str]:
    """בחירת מועמד: יחיד → מתקבל; אחרת התאמה מדויקת/סדר-מילים יחידה; אחרת עמימות."""
    if not candidates:
        return None, "לא נמצאו תוצאות"
    if len(candidates) == 1:
        return candidates[0], "מועמד יחיד"
    qnorms = {norm(q) for q in queries}
    qtokens = [tokens(q) for q in queries]
    exact = [c for c in candidates
             if {norm(candidate_names(c)[0]), norm(candidate_names(c)[1])} & qnorms
             or tokens(candidate_names(c)[0]) in qtokens
             or tokens(candidate_names(c)[1]) in qtokens]
    if len(exact) == 1:
        return exact[0], "התאמה מדויקת"
    prefix = [c for c in candidates
              if any(norm(candidate_names(c)[0]).startswith(qn) for qn in qnorms)]
    if len(prefix) == 1:
        return prefix[0], "התאמת תחילית יחידה"
    names = "; ".join(f"{candidate_names(c)[0]} (id={c['key']})" for c in candidates[:6])
    return None, f"עמימות בין {len(candidates)} מועמדים: {names}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="רזולוציה מחדש גם למי שכבר יש tase_id")
    ap.add_argument("--dry-run", action="store_true", help="בלי לכתוב לקובץ")
    args = ap.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    data = yaml.load(CONFIG.read_text(encoding="utf-8"))

    maya = MayaSession()
    errors: list[str] = []
    resolved = skipped = 0

    for comp in data["companies"]:
        name = comp["name_he"]
        if comp.get("listing") != "TASE":
            skipped += 1
            continue
        if comp.get("tase_id") and not args.force:
            skipped += 1
            continue

        queries = [name] + list(comp.get("aliases", []) or [])
        if comp.get("name_en"):
            queries.append(comp["name_en"])
        # וריאנטים: כתיב עם גרשיים (נדלן→נדל"ן) ולבסוף המילה הראשונה לבדה
        for q in list(queries):
            if "נדלן" in q:
                queries.insert(queries.index(q), q.replace("נדלן", 'נדל"ן'))
        first = name.split()[0]
        if len(name.split()) > 1 and first not in queries:
            queries.append(first)

        candidates, used_q = [], None
        for q in queries:
            try:
                candidates = maya.autocomplete(q)
            except Exception as ex:
                errors.append(f"{name}: שגיאת API בחיפוש '{q}': {ex}")
                candidates = []
                break
            if candidates:
                used_q = q
                break

        chosen, why = pick(candidates, queries)
        if chosen is None:
            errors.append(f"{name}: {why} (חיפושים: {', '.join(queries)})")
            continue

        try:
            det = maya.company_details(chosen["key"])
        except Exception as ex:
            errors.append(f"{name}: נמצא id={chosen['key']} אך details נכשל: {ex}")
            continue

        if det.get("isDeleted"):
            errors.append(f"{name}: החברה מסומנת כמחוקה במאיה (id={chosen['key']})")
            continue
        sec_id = det.get("mainSecurityId")
        if not sec_id:
            errors.append(f"{name}: אין mainSecurityId ב-details (id={chosen['key']})")
            continue

        comp["tase_id"] = int(sec_id)
        comp["maya_company_id"] = int(chosen["key"])
        resolved += 1
        flags = "".join(f" [{f}]" for f, v in
                        (("אג\"ח בלבד", det.get("isBond")), ("TASE-UP", det.get("isTaseup")),
                         ("מושעה", det.get("isSuspended"))) if v)
        print(f"  ✓ {name} → {candidate_names(chosen)[0]} | נייר {sec_id} | חברה {chosen['key']}"
              f" | {why} (חיפוש: {used_q}){flags}")

    if not args.dry_run and resolved:
        yaml.dump(data, CONFIG.open("w", encoding="utf-8", newline="\n"))

    print(f"\nסיכום: {resolved} נפתרו, {skipped} דולגו, {len(errors)} שגיאות")
    if errors:
        print("\n--- שגיאות (טעונות טיפול ידני) ---", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
