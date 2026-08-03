# -*- coding: utf-8 -*-
"""משיכת אייטמים מ-Feedly (24 שעות אחרונות) ונרמול ל-JSONL.

דורש FEEDLY_TOKEN בסביבה (Feedly API access token).
פלט: data/raw/<YYYY-MM-DD>/feedly.jsonl — שורה לאייטם:
  {id, ts, title, body, url, source}
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden
harden()

import requests
import yaml

from _state import connect, filter_new
from _text import clean_html

ROOT = Path(__file__).resolve().parents[1]


def api(session: requests.Session, base: str, path: str, **params):
    r = session.get(f"{base}{path}", params=params or None, timeout=45)
    if r.status_code == 401:
        raise SystemExit("שגיאה: FEEDLY_TOKEN לא תקף (401) — יש לחדש את הטוקן")
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
        "title": (entry.get("title") or "").strip(),
        "body": clean_html(content),
        "url": url,
        "source": ((entry.get("origin") or {}).get("title") or "feedly").strip(),
    }


def main() -> int:
    token = os.environ.get("FEEDLY_TOKEN")
    if not token:
        print("שגיאה: FEEDLY_TOKEN לא מוגדר בסביבה — אין גישה ל-Feedly", file=sys.stderr)
        return 1

    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    fcfg = cfg["feedly"]
    lookback = int(cfg["params"].get("lookback_hours", 24))
    newer_than = int((datetime.now(timezone.utc) - timedelta(hours=lookback))
                     .timestamp() * 1000)

    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    base = fcfg.get("api_base", "https://cloud.feedly.com/v3")

    uid = api(s, base, "/profile")["id"]
    entries: list[dict] = []
    for stream in fcfg.get("stream_ids", ["global.all"]):
        stream_id = (f"user/{uid}/category/{stream}"
                     if "/" not in stream else stream)
        continuation = None
        while True:
            params = {"streamId": stream_id, "newerThan": newer_than,
                      "count": min(int(fcfg.get("max_items_per_stream", 250)), 250)}
            if continuation:
                params["continuation"] = continuation
            data = api(s, base, "/streams/contents", **params)
            entries.extend(data.get("items", []))
            continuation = data.get("continuation")
            if not continuation or len(entries) >= int(fcfg.get("max_items_per_stream", 250)):
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
