# -*- coding: utf-8 -*-
"""קריאת RSS ישירות מהמקורות — בלי מתווך ובלי מכסה.

למה זה קיים לצד feedly_pull: חשבון ה-Feedly מוגבל ל-50 קריאות API ליום, ועם
שלוש מהדורות ביום זו תקרה שנוגעים בה. הפידים עצמם ציבוריים, כך שאין סיבה
לעבור דרך מתווך — כאן מושכים אותם ישירות, ללא מגבלה וללא תלות בצד שלישי.

הגישה היא ב-curl_cffi עם חיקוי דפדפן: חלק מהאתרים (גלובס, רויטרס) חוסמים
user-agent של ספריות HTTP.

פלט: data/raw/<YYYY-MM-DD>/rss.jsonl — אותו סכימה כמו feedly.jsonl
  {id, ts, title, body, url, source}
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden
harden()

import yaml
from curl_cffi import requests as creq

from _state import connect, filter_new
from _text import clean_html

ROOT = Path(__file__).resolve().parents[1]
NS = {"atom": "http://www.w3.org/2005/Atom",
      "content": "http://purl.org/rss/1.0/modules/content/",
      "dc": "http://purl.org/dc/elements/1.1/"}
# פיד שלא התעדכן זמן רב הוא כמעט תמיד מת. WSJ למשל מחזיר 200 עם 20 פריטים
# שכולם מינואר 2025 — בלי הבדיקה הזו הברייף היה מציג חדשות בנות שנה כטריות.
STALE_DAYS = 14


def txt(el, *paths) -> str:
    for p in paths:
        found = el.find(p, NS)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except Exception:
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_feed(xml: str, source: str) -> list[dict]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    items = root.findall(".//item") or root.findall(".//atom:entry", NS)
    rows = []
    for it in items:
        title = clean_html(txt(it, "title", "atom:title"), max_chars=300)
        link = txt(it, "link", "guid")
        if not link:
            a = it.find("atom:link", NS)
            link = (a.get("href") if a is not None else "") or ""
        body = clean_html(txt(it, "content:encoded", "description", "atom:summary",
                              "atom:content"))
        ts = parse_ts(txt(it, "pubDate", "dc:date", "atom:updated", "atom:published"))
        if not title and not body:
            continue
        rows.append({
            "id": f"rss:{hashlib.sha1((link or title).encode('utf-8')).hexdigest()}",
            "ts": (ts or datetime.now(timezone.utc)).astimezone(timezone.utc)
                  .isoformat(timespec="seconds"),
            "title": title, "body": body, "url": link or None, "source": source,
            "_ts": ts,
        })
    return rows


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    rcfg = cfg.get("rss") or {}
    feeds = rcfg.get("feeds") or []
    if not feeds:
        print("שגיאה: אין פידים מוגדרים תחת rss.feeds ב-sources.yaml", file=sys.stderr)
        return 1
    lookback = int(cfg["params"].get("lookback_hours", 24))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback)
    stale_cut = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)

    session = creq.Session(impersonate="chrome")
    rows, failures, stale = [], [], []
    for f in feeds:
        name, url = f.get("name") or f.get("url"), f.get("url")
        if not url:
            continue
        try:
            r = session.get(url, timeout=40, allow_redirects=True)
            r.raise_for_status()
            parsed = parse_feed(r.text, name)
        except Exception as ex:
            failures.append({"feed": name, "error": str(ex)[:120]})
            continue
        if not parsed:
            failures.append({"feed": name, "error": "לא נמצאו פריטים"})
            continue
        newest = max((p["_ts"] for p in parsed if p["_ts"]), default=None)
        if newest and newest < stale_cut:
            stale.append({"feed": name, "newest": newest.date().isoformat()})
            continue
        rows.extend(p for p in parsed if not p["_ts"] or p["_ts"] >= cutoff)

    for r in rows:
        r.pop("_ts", None)

    con = connect()
    fresh = filter_new(con, "rss", [r["id"] for r in rows])
    con.close()

    out_dir = ROOT / "data" / "raw" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "rss.jsonl"
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            if r["id"] in fresh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1

    print(f"נכתב {path} | {len(feeds)} פידים, {len(rows)} בחלון, {n} חדשים")
    for s in stale:
        print(f"  ⚠ פיד מת: {s['feed']} — הפריט החדש ביותר מ-{s['newest']}", file=sys.stderr)
    for f in failures:
        print(f"  ⚠ {f['feed']}: {f['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
