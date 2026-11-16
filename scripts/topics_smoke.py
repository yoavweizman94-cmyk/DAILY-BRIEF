# -*- coding: utf-8 -*-
"""בדיקה מקומית ל-summarize_topics: ניסיון חוזר לנושא שחזר ריק, ושמירת הגרסה הקודמת
של היום גם בהחלפה מלאה. בלי רשת ובלי מפתח, כי _api.ask_json מוחלף בתשובות קבועות.

    python scripts/topics_smoke.py

התרחיש מ-16/11/2026: אצווה ראשונה "מוצלחת" שהחזירה פתיח אחד בלי אייטמים, ושלושה
נושאים לא חזרו בה כלל. עם TOPICS_REPLACE=1 הם נמחקו מהקובץ של היום.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summarize_topics as st  # noqa: E402

SLUGS = ["datacenters", "energy", "building-materials", "metals", "shipping"]
FAILS: list[str] = []


def item(n: int) -> list[dict]:
    return [{"title": f"t{i}", "body": "b", "companies": "", "direction": "ניטרלי"} for i in range(n)]


def topic(slug: str, n: int) -> dict:
    return {"slug": slug, "lead": f"lead {slug}", "items": item(n), "takeaway": ""}


def setup(tmp: Path, prev: dict | None) -> Path:
    (tmp / "config").mkdir(parents=True)
    (tmp / "config" / "sources.yaml").write_text(json.dumps(
        {"topics": [{"slug": s, "label": s, "companies": []} for s in SLUGS]}), encoding="utf-8")
    (tmp / "output" / "news").mkdir(parents=True)
    rows = [{"ts": "2026-11-16T10:00", "source": "x", "title": f"h {s}", "topics": [s]} for s in SLUGS]
    (tmp / "output" / "news" / "2026-11-16.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp / "output" / "topics"
    out.mkdir(parents=True)
    path = out / f"{date.today().isoformat()}.json"
    if prev is not None:
        path.write_text(json.dumps({"date": "x", "summaries": prev}), encoding="utf-8")
    return path


def run(answers: list, prev: dict | None, replace: bool) -> tuple[int, dict, int]:
    """answers: לכל קריאה ברצף — רשימת נושאים, או מחרוזת שגיאה."""
    calls = []

    def fake(system, data, schema, **kw):
        calls.append(data)
        a = answers[len(calls) - 1] if len(calls) <= len(answers) else []
        if isinstance(a, str):
            return None, a, 0.0
        asked = {s for s in SLUGS if f"slug={s} " in data}
        return {"topics": [t for t in a if t["slug"] in asked]}, None, 0.01

    with tempfile.TemporaryDirectory() as d:
        path = setup(Path(d), prev)
        st.ROOT = Path(d)
        st._api.ask_json = fake
        st._profiles.line = lambda n, limit=120: ""
        os.environ.pop("TOPICS_REPLACE", None)
        if replace:
            os.environ["TOPICS_REPLACE"] = "1"
        rc = st.main()
        data = json.loads(path.read_text(encoding="utf-8"))["summaries"] if path.exists() else {}
    return rc, data, len(calls)


def check(name: str, cond: bool) -> None:
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# 1. אצווה ראשונה כמעט ריקה; הניסיון החוזר מחזיר הכל
degenerate = [{"slug": "datacenters", "lead": "רק פתיח", "items": [], "takeaway": ""}]
good = [topic(s, 3) for s in SLUGS]
rc, data, n = run([degenerate, good, good], None, replace=True)
check("ניסיון חוזר: 3 קריאות (2 אצוות + חוזר אחד)", n == 3)
check("ניסיון חוזר: כל חמשת הנושאים עם אייטמים", all(len(data.get(s, {}).get("items", [])) == 3 for s in SLUGS))

# 2. בהחלפה מלאה, נושא שלא חזר גם בניסיון החוזר שומר את גרסת הבוקר
prev = {s: topic(s, 4) for s in SLUGS}
rc, data, n = run([degenerate, good, [topic("datacenters", 2)]], prev, replace=True)
check("החלפה: energy לא חזר → נשמר מהבוקר (4)", len(data["energy"]["items"]) == 4)
check("החלפה: datacenters חזר דל → הגרסה החדשה (2)", len(data["datacenters"]["items"]) == 2)
check("החלפה: shipping חזר → הגרסה החדשה (3)", len(data["shipping"]["items"]) == 3)

# 3. בלי החלפה — הכלל הישן: הגרסה העשירה נשארת
rc, data, n = run([good[:4], good[4:]], prev, replace=False)
check("מיזוג: גרסת בוקר עשירה (4) גוברת על 3", all(len(data[s]["items"]) == 4 for s in SLUGS))
check("מיזוג: בלי ניסיון חוזר כשהכל חזר", n == 2)

# 4. אצווה שנכשלה בשגיאה נכנסת לניסיון החוזר
rc, data, n = run(["API 529: overloaded", good[4:], good[:4]], None, replace=True)
check("שגיאה: האצווה שנפלה נשלחה שוב", n == 3 and all(len(data[s]["items"]) == 3 for s in SLUGS))

# 5. כל האצוות נכשלו — אין ניסיון חוזר, והקובץ אינו נכתב
rc, data, n = run(["Credit balance is too low", "Credit balance is too low"], prev, replace=True)
check("יתרה: קוד 1, שתי קריאות בלבד", rc == 1 and n == 2)
check("יתרה: הקובץ של הבוקר לא נדרס", len(data.get("energy", {}).get("items", [])) == 4)

print("הכל עבר" if not FAILS else f"{len(FAILS)} נכשלו")
sys.exit(1 if FAILS else 0)
