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
        # **מדלגים רק כששני המזהים קיימים.** מספר הנייר מגיע מרשימת
        # הכיסוי של יואב ולכן הוא קיים לכולן, אבל maya_company_id אינו
        # נגזר ממנו — נמדד ש-44 מתוך 73 אינם tase_id//1000 — ולכן תנאי
        # שבדק tase_id בלבד היה מדלג על כל הרשימה ולא פותר דבר.
        if comp.get("tase_id") and comp.get("maya_company_id") and not args.force:
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

        # **שאילתה שמחזירה תוצאות עמומות אינה סוף הדרך.** הגרסה הקודמת
        # עצרה בראשונה שהחזירה משהו, ולכן "מר" — שמחזיר שמונה חברות
        # שאף אחת מהן אינה הנכונה — חסם את השם החלופי "ח.מר תעשיות"
        # שכן פותר אותה. עכשיו ממשיכים עד להכרעה.
        candidates, used_q, chosen, why = [], None, None, "לא נמצאו תוצאות"
        for q in queries:
            try:
                cands = maya.autocomplete(q)
            except Exception as ex:
                errors.append(f"{name}: שגיאת API בחיפוש '{q}': {ex}")
                cands = []
                break
            if not cands:
                continue
            candidates, used_q = cands, q
            chosen, why = pick(cands, queries)
            if chosen is not None:
                break

        # **מספר הנייר מכריע עמימות.** כשהשם מחזיר כמה מועמדים, ההתאמה
        # לפי טקסט היא ניחוש — אבל מספר הנייר שבקובץ הוא עובדה. שליפת
        # ה-details של כל מועמד והשוואה מול mainSecurityId הופכת את
        # ההכרעה לדטרמיניסטית: או שיש בדיוק אחד שתואם, או שאין אף אחד.
        if chosen is None and comp.get("tase_id") and candidates:
            want = int(comp["tase_id"])
            hits = []
            for cand in candidates:
                try:
                    d2 = maya.company_details(cand["key"])
                except Exception:
                    continue
                if d2.get("mainSecurityId") and int(d2["mainSecurityId"]) == want:
                    hits.append(cand)
            if len(hits) == 1:
                chosen = hits[0]
                why = f"הוכרע לפי מספר נייר {want}"

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

        # **מספר הנייר שבקובץ הוא הסמכות, ומאיה מאמתת אותו.** רשימת
        # הכיסוי היא קלט אנושי מכוון; אם מאיה מחזירה נייר אחר, פירושו
        # שההתאמה לפי שם תפסה חברה אחרת — וזו שגיאה שצריך לראות, לא
        # ערך שצריך לדרוס בשקט. maya_company_id מהתאמה כזו אינו נכתב.
        have = comp.get("tase_id")
        if have and int(sec_id) != int(have):
            errors.append(
                f"{name}: מאיה מחזירה נייר {sec_id} ({candidate_names(chosen)[0]}) "
                f"אך בקובץ {have} — ההתאמה לפי שם כנראה תפסה חברה אחרת")
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
