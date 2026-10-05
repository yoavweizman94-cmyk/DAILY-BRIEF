# -*- coding: utf-8 -*-
"""פרסומי רגולטורים מה-API הפתוח של gov.il — תקשורת, חשמל, תחבורה.

**המקור.** אוספי התוכן של gov.il (collectors) נטענים מ-
openapi-gc.digital.gov.il עם clientId ציבורי, שכל דפדפן מקבל ב-
CollectorsWebApi/client-config.js. הסקריפט קורא אותו משם בכל ריצה — הוא
אינו סוד, אבל גם אינו שלנו, ולכן לא נשמר בריפו ויתעדכן לבד אם יוחלף.
ה-API דורש את הכותרת Origin של gov.il; בלעדיה הוא עונה 500.

**מה נשמר.** לכל גוף (config/gov.yaml) — חדשות, החלטות ופרסומים, מנורמלים
לרשומה אחת: מזהה, סוג, כותרת, תקציר, תאריך, יחידה, נושאים וקישור. הקובץ
output/gov/<גוף>/items.jsonl ממוין מהחדש לישן ונגזם ל-retention_days.

**מה לא נשמר.** משרות והודעות לימאים — רעש שאינו פרסום רגולטורי (exclude
בתצורה). הסיקור עצמו — scripts/analyze_gov.py, שקורא את הקבצים האלה.

פלט ל-GITHUB_OUTPUT: changed=yes כשנוסף פריט חדש לאחד הגופים.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import _tls  # noqa: F401  — מחשב המשרד מאחורי יירוט TLS
except Exception:  # noqa: BLE001
    pass

CFG = ROOT / "config" / "gov.yaml"
OUT = ROOT / "output" / "gov"
CONFIG_JS = "https://www.gov.il/CollectorsWebApi/client-config.js"
API = "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/collectors/v1/api/DataCollector/GetResults"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
KINDS = {
    "news": ["news"],
    "policies": ["policy", "pmopolicy"],
    "pubs": ["reports", "rfp", "publicsharing"],
}
KIND_HE = {"news": "חדשות", "policies": "החלטות ונהלים", "pubs": "פרסומים ושימועים"}
MAX_PAGES = 8   # בהשלמה הראשונה: עד 8 עמודים לכל סוג, ואז עוצרים


def http_get(url: str, headers: dict, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return f.read().decode("utf-8", "replace")


def client_id() -> str:
    js = http_get(CONFIG_JS, {})
    m = re.search(r'"clientId"\s*:\s*"([^"]+)"', js)
    if not m:
        raise RuntimeError("clientId לא נמצא בקונפיג של gov.il — מבנה הקובץ השתנה")
    return m.group(1)


def fetch(cid: str, office_id: str, kind: str, skip: int, limit: int) -> dict:
    q = [("CollectorType", t) for t in KINDS[kind]]
    q += [("officeId", office_id), ("skip", str(skip)), ("limit", str(limit)), ("culture", "he")]
    url = f"{API}?{urllib.parse.urlencode(q)}"
    for attempt in range(3):
        try:
            return json.loads(http_get(url, {"x-client-id": cid, "Accept": "application/json",
                                              "Origin": "https://www.gov.il"}))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == 2:
                raise RuntimeError(f"{kind} skip={skip}: {type(e).__name__} {str(e)[:80]}") from e
            time.sleep(4 * (attempt + 1))
    return {}


def _first(meta: dict, key: str) -> str:
    v = (meta or {}).get(key) or []
    return (v[0].get("title") or "").strip() if v and isinstance(v[0], dict) else ""


def _date(s: str) -> str | None:
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y").date().isoformat()
    except (ValueError, AttributeError):
        return None


def norm(raw: dict, office: str, kind: str) -> dict | None:
    tags = raw.get("tags") or {}
    meta = tags.get("metaData") or {}
    promoted = tags.get("promotedMetaData") or {}
    title = " ".join((raw.get("title") or "").split())
    if not title:
        return None
    url = raw.get("url") or ""
    if url and not url.startswith("http"):
        url = "https://www.gov.il" + (url if url.startswith("/") else "/" + url)
    # המזהה הוא ה-slug של העמוד: יציב, ומשמש גם ל-API של עמודי התוכן.
    slug = url.rstrip("/").rsplit("/", 1)[-1] if "/pages/" in url or "/departments/" in url else ""
    item_id = slug or hashlib.sha1(f"{office}|{title}".encode()).hexdigest()[:16]
    topics = [x.get("title") for k in ("נושא", "נושא משני") for x in (meta.get(k) or [])
              if isinstance(x, dict) and x.get("title")]
    return {
        "id": item_id,
        "office": office,
        "kind": kind,
        "type": _first(promoted, "סוג") or _first(meta, "סוג") or KIND_HE[kind],
        "title": title,
        "description": " ".join((raw.get("description") or "").split())[:1200],
        "date": _date(_first(meta, "תאריך פרסום")) or _date(_first(meta, "תאריך עדכון")),
        "updated": _date(_first(meta, "תאריך עדכון")),
        "unit": _first(meta, "משרד"),
        "topics": topics[:6],
        "url": url,
        "slug": slug,
    }


def excluded(item: dict, cfg: dict) -> bool:
    ex = cfg.get("exclude") or {}
    if item["type"] in (ex.get("types") or []):
        return True
    return any(re.search(p, item["title"]) for p in ex.get("title_patterns") or [])


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def collect(cid: str, office: dict, cfg: dict, known: set[str], cutoff: str) -> tuple[list[dict], list[str]]:
    """פריטים חדשים לגוף אחד. עוצר בסוג כשעמוד שלם כבר מוכר או ישן מהחלון."""
    size = int(cfg.get("page_size") or 40)
    new, errors = [], []
    for kind in KINDS:
        for page in range(MAX_PAGES):
            try:
                data = fetch(cid, office["office_id"], kind, page * size, size)
            except RuntimeError as e:
                errors.append(f"{office['key']}/{e}")
                break
            results = data.get("results") or []
            if not results:
                break
            unseen, old = 0, 0
            for raw in results:
                item = norm(raw, office["key"], kind)
                if not item or not item["date"]:
                    continue
                if item["date"] < cutoff:
                    old += 1
                    continue
                if item["id"] in known:
                    continue
                unseen += 1
                if excluded(item, cfg):
                    continue
                item["fetched_at"] = datetime.now().isoformat(timespec="minutes")
                known.add(item["id"])
                new.append(item)
            # עוצרים כשעמוד כולו מוכר או כולו מחוץ לחלון. **פריט מסונן נספר
            # כלא-מוכר**: עמוד שכולו הודעות לימאים אינו סוף החדש — בלי זה
            # האיסוף נעצר עליו ודילג על הפרסומים שמתחתיו.
            if unseen == 0 or old == len(results):
                break
    return new, errors


def main() -> int:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    try:
        cid = client_id()
    except Exception as e:  # noqa: BLE001
        print(f"::error title=gov.il — אין clientId::{type(e).__name__}: {str(e)[:160]}")
        return 1

    today = date.today()
    keep_from = (today - timedelta(days=int(cfg.get("retention_days") or 180))).isoformat()
    total_new, errors, lines = 0, [], []
    for office in cfg["offices"]:
        path = OUT / office["key"] / "items.jsonl"
        rows = [r for r in load(path) if (r.get("date") or "") >= keep_from]
        known = {r["id"] for r in rows}
        # השלמה ראשונה: חלון backfill_days; אחר כך מספיקים הימים האחרונים
        days = int(cfg.get("backfill_days") or 45) if not rows else 14
        new, errs = collect(cid, office, cfg, known, (today - timedelta(days=days)).isoformat())
        errors += errs
        rows = sorted(rows + new, key=lambda r: (r.get("date") or "", r.get("fetched_at") or ""),
                      reverse=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        total_new += len(new)
        by_kind = {k: sum(1 for r in new if r["kind"] == k) for k in KINDS}
        lines.append(f"{office['name']}: {len(new)} חדשים ({', '.join(f'{KIND_HE[k]} {v}' for k, v in by_kind.items())}) · "
                     f"{len(rows)} בקובץ")

    state = {"updated": datetime.now().isoformat(timespec="minutes"), "errors": errors}
    (OUT / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print("::notice title=פרסומי רגולטורים::" + " · ".join(lines))
    for e in errors[:5]:
        print(f"::warning title=gov.il — כשל בקריאה::{e}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"changed={'yes' if total_new else 'no'}\n")
    return 0 if len(errors) < 9 else 1


if __name__ == "__main__":
    sys.exit(main())
