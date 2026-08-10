# -*- coding: utf-8 -*-
"""משיכת אייטמים מ-Feedly (24 שעות אחרונות) ונרמול ל-JSONL.

דורש FEEDLY_TOKEN — מהסביבה או מ-.env מקומי. אם מוגדר גם FEEDLY_REFRESH_TOKEN,
טוקן שפג (401) מתחדש אוטומטית והבקשה נשלחת שוב; טוקני Feedly תקפים ~31 יום,
כך שבלי זה הריצה היומית נשברת אחת לחודש.

פלט: data/raw/<YYYY-MM-DD>/feedly.jsonl — שורה לאייטם:
  {id, ts, title, body, url, source}
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden
harden()

import requests
import yaml

from _env import load_env, update_env
from _state import connect, filter_new
from _text import clean_html

ROOT = Path(__file__).resolve().parents[1]
# מסלול הרענון של טוקני developer ב-Feedly משתמש בזוג הקבוע הזה
REFRESH_CLIENT = {"client_id": "feedlydev", "client_secret": "feedlydev"}


class Feedly:
    def __init__(self, base: str, token: str, refresh_token: str | None):
        self.base = base
        self.refresh_token = refresh_token
        self.session = requests.Session()
        self._set_token(token)
        self._refreshed = False

    def _set_token(self, token: str):
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _refresh(self) -> bool:
        if not self.refresh_token or self._refreshed:
            return False
        self._refreshed = True          # ניסיון אחד בלבד לכל ריצה
        r = requests.post(f"{self.base}/auth/token", timeout=45,
                          data={**REFRESH_CLIENT, "grant_type": "refresh_token",
                                "refresh_token": self.refresh_token})
        if not r.ok:
            print(f"אזהרה: רענון טוקן Feedly נכשל ({r.status_code})", file=sys.stderr)
            return False
        token = r.json().get("access_token")
        if not token:
            return False
        self._set_token(token)
        # ב-CI אין .env — הטוקן החדש חי לריצה הזו בלבד, וזה מספיק
        if update_env("FEEDLY_TOKEN", token):
            print("טוקן Feedly חודש ונשמר ב-.env")
        else:
            print("טוקן Feedly חודש (לריצה הנוכחית בלבד)")
        return True

    def get(self, path: str, **params):
        r = self.session.get(f"{self.base}{path}", params=params or None, timeout=45)
        if r.status_code == 401 and self._refresh():
            r = self.session.get(f"{self.base}{path}", params=params or None, timeout=45)
        if r.status_code == 401:
            raise SystemExit(
                "שגיאה: FEEDLY_TOKEN לא תקף (401) ולא ניתן לרענן — "
                "יש להנפיק טוקן חדש ולעדכן את הסביבה או את .env")
        if r.status_code == 429:
            # מכסת ה-API של Feedly היא 50 קריאות ליום לחשבון. שלוש מהדורות
            # צורכות ~15 (5 זרמים + מטמון למזהים), כך שיש מרווח — אבל חקירה
            # ידנית מול ה-API מכלה אותו ומפילה את המקור לשארית היום.
            reset = r.headers.get("x-ratelimit-reset", "?")
            used = r.headers.get("x-ratelimit-count", "?")
            limit = r.headers.get("x-ratelimit-limit", "?")
            raise SystemExit(
                f"שגיאה: מכסת ה-API של Feedly מוצתה ({used}/{limit}); "
                f"איפוס בעוד {reset} שניות. הברייף יופק בלי מקור Feedly.")
        r.raise_for_status()
        return r.json()


def normalize(entry: dict) -> dict:
    content = (entry.get("content") or entry.get("summary") or {}).get("content", "")
    url = None
    for link in (entry.get("canonical") or []) + (entry.get("alternate") or []):
        if link.get("href"):
            url = link["href"]
            break
    ts_ms = entry.get("published") or entry.get("crawled") or 0
    return {
        "id": entry.get("id"),
        "ts": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                      .isoformat(timespec="seconds"),
        # יש פידים (למשל RSS של gov.il) שמחזירים כותרת עטופה ב-HTML
        "title": clean_html(entry.get("title") or "", max_chars=300),
        "body": clean_html(content),
        "url": url,
        "source": ((entry.get("origin") or {}).get("title") or "feedly").strip(),
    }


def main() -> int:
    load_env()
    token = os.environ.get("FEEDLY_TOKEN")
    if not token:
        print("שגיאה: FEEDLY_TOKEN לא מוגדר בסביבה ולא ב-.env — אין גישה ל-Feedly",
              file=sys.stderr)
        return 1

    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    fcfg = cfg["feedly"]
    lookback = int(cfg["params"].get("lookback_hours", 24))
    newer_than = int((datetime.now(timezone.utc) - timedelta(hours=lookback))
                     .timestamp() * 1000)

    base = fcfg.get("api_base", "https://cloud.feedly.com/v3")
    api = Feedly(base, token, os.environ.get("FEEDLY_REFRESH_TOKEN"))

    # מכסת ה-API היא 50 קריאות ליום לחשבון, ועם שלוש מהדורות ביום כל קריאה
    # נחסכת נחשבת. זהות המשתמש ומיפוי הקטגוריות כמעט לא משתנים, ולכן הם
    # נשמרים במטמון ל-24 שעות — חיסכון של 2 קריאות בכל ריצה (6 ביום).
    meta_path = ROOT / "data" / "feedly_meta.json"
    meta = None
    try:
        cached = json.loads(meta_path.read_text(encoding="utf-8"))
        if time.time() - cached.get("cached_at", 0) < 86400:
            meta = cached
    except Exception:
        meta = None

    wanted_labels = [s for s in fcfg.get("stream_ids", []) if "/" not in s]
    if meta and not all(lbl in meta.get("by_label", {}) for lbl in wanted_labels):
        meta = None                                  # קטגוריה חדשה — לרענן

    if meta:
        uid, by_label = meta["uid"], meta["by_label"]
    else:
        uid = api.get("/profile")["id"]
        # Feedly מזהה קטגוריות שיצר המשתמש ב-UUID, לא בתווית. בקשה עם התווית
        # מחזירה 200 ורשימה ריקה — כשל שקט — ולכן מתרגמים תווית→מזהה.
        by_label = {c["label"]: c["id"] for c in api.get("/categories")}
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(
            {"uid": uid, "by_label": by_label, "cached_at": time.time()},
            ensure_ascii=False), encoding="utf-8")

    def resolve(stream: str) -> str:
        if "/" in stream:                       # מזהה מלא שסופק כלשונו
            return stream
        if stream in by_label:
            return by_label[stream]
        if stream in ("global.all", "global.saved", "global.read"):
            return f"user/{uid}/category/{stream}"
        raise SystemExit(
            f"שגיאה: הקטגוריה '{stream}' לא קיימת ב-Feedly. "
            f"קיימות: {', '.join(sorted(by_label)) or '(אין)'}")

    cap = int(fcfg.get("max_items_per_stream", 250))
    entries: list[dict] = []
    for stream in fcfg.get("stream_ids", ["global.all"]):
        stream_id = resolve(stream)
        continuation = None
        got = 0                    # מונה פר-זרם: אחרת קטגוריה עמוסה מרעיבה את הבאות
        while True:
            params = {"streamId": stream_id, "newerThan": newer_than,
                      "count": min(cap, 250)}
            if continuation:
                params["continuation"] = continuation
            data = api.get("/streams/contents", **params)
            batch = data.get("items", [])
            got += len(batch)
            entries.extend(batch)
            continuation = data.get("continuation")
            if not continuation or got >= cap:
                break

    rows = [normalize(e) for e in entries if e.get("id")]
    con = connect()
    fresh = filter_new(con, "feedly", [r["id"] for r in rows])
    con.close()

    out_dir = ROOT / "data" / "raw" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "feedly.jsonl"
    n = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            if r["id"] in fresh:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
    print(f"נכתב {out_path} | {len(rows)} אייטמים נמשכו, {n} חדשים")
    return 0


if __name__ == "__main__":
    sys.exit(main())
