# -*- coding: utf-8 -*-
"""חדשות על מתחרים, לקוחות ומגמות ענפיות של אחזקות הקרן (עמוד peers.html).

**שני מקורות.**
1. Google News RSS — חיפוש לכל מתחר, לקוח מהותי ומונח ענפי ב-output/peers/peers.json
   (בריפו התוכן הפרטי), ביומיים האחרונים (when:2d). שם באנגלית — חיפוש באנגלית; מתחר
   ישראלי (il: true) או מונח בעברית — חיפוש בעברית.
2. החדשות שהאתר כבר מסווג (output/news/<date>.jsonl, מפידי הברייף) — כותרת שמזכירה מתחר
   בשמו. אלה באים עם הקישור המקורי, ולכן הם עדיפים על Google News באותה ידיעה.

**הפלט:** output/peers/news/<date>.jsonl, שורה לידיעה: id, ts, title, url, source,
ומה שהיא נוגעת בו — אחזקה, מתחר/לקוח/מונח, סוג. ידיעה שנמצאה לשתי אחזקות (מתחר
משותף לשתיהן) היא שורה אחת עם שתיהן. מה שכבר נשמר ביומיים האחרונים
אינו נכתב שוב.

אין כאן מודל ואין עלות: המיון והתובנות ב-scripts/analyze_peers.py.

    python ingest/peers_news.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402
harden()

from curl_cffi import requests as creq  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PEERS = ROOT / "output" / "peers"
NEWS = PEERS / "news"
SITE_NEWS = ROOT / "output" / "news"
GN = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}"
WINDOW = timedelta(hours=48)
PAUSE = 1.2                     # שניות בין חיפושים — Google News חוסם קצב גבוה
HEB = re.compile(r"[֐-׿]")


def rid(url: str, title: str) -> str:
    key = re.sub(r"\s+", " ", (title or "").lower()).strip() or url
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def gn_search(session, q: str, hebrew: bool) -> list[dict]:
    hl, gl, lang = ("iw", "IL", "he") if hebrew else ("en-US", "US", "en")
    url = GN.format(q=urllib.parse.quote(f"{q} when:2d"), hl=hl, gl=gl, lang=lang)
    for i in range(3):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 * (i + 1))
    else:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):          # Google מוסיף " - <מקור>" לכותרת
            title = title[: -len(src) - 3].strip()
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        out.append({"title": title, "url": (it.findtext("link") or "").strip(), "source": src,
                    "ts": ts.isoformat(timespec="seconds")})
    return out


def queries(peers: dict) -> list[dict]:
    """(שאילתה, עברית?) לכל מתחר, לקוח ומונח — עם האחזקות שהיא שייכת להן."""
    by_q: dict[tuple, dict] = {}
    for holding, cfg in (peers.get("holdings") or {}).items():
        for kind, rows in (("competitor", cfg.get("competitors")), ("customer", cfg.get("customers"))):
            for p in rows or []:
                q = p.get("q") or f'"{p["name"]}"'
                k = (q, bool(p.get("il")) or bool(HEB.search(q)))
                e = by_q.setdefault(k, {"q": q, "hebrew": k[1], "tags": []})
                e["tags"].append({"holding": holding, "peer": p["name"], "kind": kind})
        for t in cfg.get("terms") or []:
            k = (t, bool(HEB.search(t)))
            e = by_q.setdefault(k, {"q": t, "hebrew": k[1], "tags": []})
            e["tags"].append({"holding": holding, "peer": t, "kind": "term"})
    return list(by_q.values())


def site_items(peers: dict, since: datetime) -> list[dict]:
    """כותרות מהאתר עצמו שמזכירות מתחר או לקוח בשמו (בלי מונחים — הם רחבים מדי)."""
    names = []
    for holding, cfg in (peers.get("holdings") or {}).items():
        for kind, rows in (("competitor", cfg.get("competitors")), ("customer", cfg.get("customers"))):
            for p in rows or []:
                base = re.split(r"\s*\(", p["name"])[0].strip()
                if len(base) >= 4:
                    names.append((re.compile(r"(?<![\w֐-׿])" + re.escape(base) + r"(?![\w֐-׿])", re.I),
                                  {"holding": holding, "peer": p["name"], "kind": kind}))
    out = []
    for f in sorted(SITE_NEWS.glob("*.jsonl"))[-3:]:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                ts = datetime.fromisoformat((r.get("ts") or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < since or not r.get("url"):
                continue
            tags = [t for pat, t in names if pat.search(r.get("title") or "")]
            if tags:
                out.append({"title": r["title"], "url": r["url"], "source": r.get("source") or "",
                            "ts": ts.isoformat(timespec="seconds"), "tags": tags, "via": "site"})
    return out


def main() -> int:
    cfg_path = PEERS / "peers.json"
    if not cfg_path.exists():
        print("::warning title=חדשות המתחרים::אין output/peers/peers.json — אין מה לחפש")
        return 0
    peers = json.loads(cfg_path.read_text(encoding="utf-8"))
    NEWS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    since = now - WINDOW
    seen = set()
    for f in sorted(NEWS.glob("*.jsonl"))[-3:]:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                pass

    found: dict[str, dict] = {}

    def add(item: dict, tags: list[dict], q: str | None) -> None:
        i = rid(item["url"], item["title"])
        e = found.get(i)
        if e is None:
            e = found[i] = {"id": i, **{k: item[k] for k in ("ts", "title", "url", "source")},
                            "via": item.get("via") or "gnews", "tags": [], "q": []}
        elif item.get("via") == "site" and e["via"] != "site":       # הקישור המקורי עדיף
            e.update(url=item["url"], source=item["source"], via="site")
        for t in tags:
            if t not in e["tags"]:
                e["tags"].append(t)
        if q and q not in e["q"]:
            e["q"].append(q)

    for it in site_items(peers, since):
        add(it, it["tags"], None)
    s = creq.Session(impersonate="chrome")
    qs = queries(peers)
    fails = 0
    for e in qs:
        rows = gn_search(s, e["q"], e["hebrew"])
        if not rows:
            fails += 1
        for it in rows:
            try:
                if datetime.fromisoformat(it["ts"]) < since:
                    continue
            except ValueError:
                continue
            add(it, e["tags"], e["q"])
        time.sleep(PAUSE)

    new = [r for i, r in found.items() if i not in seen]
    new.sort(key=lambda r: r["ts"])
    out = NEWS / f"{date.today().isoformat()}.jsonl"
    with out.open("a", encoding="utf-8", newline="\n") as f:
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # מספרים בלבד — הלוג ציבורי
    print(f"::notice title=חדשות המתחרים::{len(qs)} חיפושים ({fails} ריקים או נכשלו) · "
          f"{len(found)} ידיעות ביומיים · {len(new)} חדשות")
    if new:
        print("CHANGED=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
