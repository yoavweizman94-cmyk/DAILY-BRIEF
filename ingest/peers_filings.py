# -*- coding: utf-8 -*-
"""דוחות של מתחרים, לקוחות וספקים שמדווחים ל-SEC (לעמוד peers.html).

**למי.** כל רשומה ב-output/peers/peers.json שהטיקר שלה בבורסה אמריקאית (NYSE/NASDAQ),
או שיש לה שדה "sec" עם הטיקר שבו היא מדווחת ל-SEC (חברה זרה עם ADR: הטיקר בבורסה המקומית אינו זה של SEC).

**מה.**
- הודעת התוצאות: 8-K עם פריט 2.02 (ההודעה עצמה בנספח EX-99), או 6-K של חברה זרה
  שהוא הודעת תוצאות (רבעון, חציון, שנה).
- אירועים מהותיים: 8-K עם פריט 2.01 (השלמת רכישה או מכירה), 2.05 (סגירת פעילות או מפעל)
  או 2.06 (ירידת ערך) — שינוי בכושר הייצור או במבנה של מתחר.
דוחות 10-Q/10-K אינם נמשכים: הודעת התוצאות קודמת להם ומכילה את מה שהסקירה צריכה.

**פרטי פנייה.** SEC מחייב כתובת מייל בכותרת User-Agent של כל בקשה. הכתובת בסוד
SEC_CONTACT ב-GitHub (הבעלים קבע אותה, 19/11/2026) — לא בקוד ולא בלוג. בלעדיה הסקריפט
מדלג, ושאר העמוד ממשיך כרגיל.

**הפלט.** output/peers/filings/<date>.jsonl — רשומה לדוח: מזהה, חברה, טופס, תאריך, קישור,
והאחזקות שהיא נוגעת בהן. הטקסט עצמו אינו נשמר בריפו התוכן (עשרות אלפי תווים לדוח): הוא
נכתב למטמון בתיקיית העבודה (tmp/sec), ו-scripts/analyze_peers.py קורא משם, או מושך מחדש
(fetch_text) בריצה אחרת. הלוג ציבורי — מודפסים מספרים בלבד.

    python ingest/peers_filings.py            # ימים אחרונים (PEERS_SEC_DAYS, ברירת מחדל 4)
    PEERS_SEC_DAYS=45 python ingest/peers_filings.py   # השלמה: עונת הדוחות האחרונה
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402
harden()

import requests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PEERS = ROOT / "output" / "peers"
OUT = PEERS / "filings"
CACHE = ROOT / "tmp" / "sec"
US = {"NYSE", "NASDAQ", "NYSEAMERICAN", "AMEX", "NYSEARCA", "BATS"}
ROLE = {"competitors": "competitor", "customers": "customer", "suppliers": "supplier"}
EVENT_ITEMS = {"2.01": "השלמת רכישה או מכירה", "2.05": "סגירת פעילות", "2.06": "ירידת ערך"}
RESULTS = re.compile(r"\b(first|second|third|fourth)[- ]quarter\b|\bQ[1-4]\b|half[- ]year|first half|"
                     r"nine[- ]months|full[- ]year|interim (report|results)|(financial|operating) results|"
                     r"results (for|of) the", re.I)
SALES = re.compile(r"\b(revenues?|net sales|sales)\b", re.I)
MAX_TEXT = 60000
PAUSE = 0.12            # SEC מתיר עד 10 בקשות בשנייה

_session: requests.Session | None = None


def session() -> requests.Session | None:
    global _session
    contact = (os.environ.get("SEC_CONTACT") or "").strip()
    if not contact:
        return None
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": f"peers-research {contact}", "Accept-Encoding": "gzip, deflate"})
    return _session


def get(url: str, as_json: bool = False):
    s = session()
    if s is None:
        return None
    for i in range(3):
        try:
            time.sleep(PAUSE)
            r = s.get(url, timeout=60)
            if r.status_code == 200:
                return r.json() if as_json else r.text
            if r.status_code == 404:
                return None
            time.sleep(4 * (i + 1))           # 403/429: SEC מאט לקוח שחורג מהקצב
        except (requests.RequestException, ValueError):
            time.sleep(3 * (i + 1))
    return None


BLOCK = re.compile(r"</?(p|div|tr|br|h[1-6]|li|table|td|th)\b[^>]*>", re.I)


def text_of(raw: str) -> str:
    raw = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", raw)
    raw = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", raw)
    raw = BLOCK.sub("\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw).replace("\xa0", " ")
    raw = re.sub(r"[ \t]+", " ", raw)
    return re.sub(r"\n\s*\n+", "\n", raw).strip()


def fetch_text(doc_url: str) -> str:
    """הטקסט של מסמך בדוח (ההודעה לעיתונות) — גם לשימוש scripts/analyze_peers.py."""
    raw = get(doc_url)
    return text_of(raw)[:MAX_TEXT] if raw else ""


def cached_text(acc: str) -> str:
    p = CACHE / f"{acc}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def cik_map() -> dict[str, tuple[int, str]]:
    d = get("https://www.sec.gov/files/company_tickers.json", as_json=True) or {}
    return {v["ticker"].upper(): (int(v["cik_str"]), v["title"]) for v in d.values()}


def targets(peers: dict, cmap: dict) -> dict[int, dict]:
    """CIK → החברה והאחזקות שהיא נוגעת בהן (חברה שהיא מתחר של אחת ולקוח של אחרת — פעם אחת)."""
    out: dict[int, dict] = {}
    for h, cfg in peers.items():
        for role, kind in ROLE.items():
            for p in cfg.get(role) or []:
                tk = (p.get("sec") or "").upper()
                if not tk:
                    ex, _, sym = (p.get("ticker") or "").partition(":")
                    tk = sym.upper() if ex.upper() in US else ""
                if not tk or tk not in cmap:
                    continue
                cik, title = cmap[tk]
                t = out.setdefault(cik, {"cik": cik, "ticker": tk, "company": p["name"], "sec_name": title,
                                         "holdings": []})
                t["holdings"].append({"holding": h, "role": kind, "src": p.get("src") or ""})
    return out


ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)


def documents(cik: int, acc: str) -> list[dict]:
    page = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm") or ""
    docs = []
    for row in ROW.findall(page):
        cells = CELL.findall(row)
        if len(cells) < 4:
            continue
        m = re.search(r'href="([^"]+)"', cells[2])
        if not m:
            continue
        href = m.group(1).replace("/ix?doc=", "")
        if not re.search(r"\.(htm|html|txt)$", href, re.I):
            continue
        docs.append({"desc": text_of(cells[1]), "type": text_of(cells[3]).upper(),
                     "url": href if href.startswith("http") else "https://www.sec.gov" + href})
    return docs


def pick(docs: list[dict], primary: str) -> dict | None:
    """ההודעה לעיתונות: נספח EX-99 (99.1 קודם), ואם אין — המסמך הראשי."""
    ex = sorted((d for d in docs if d["type"].startswith("EX-99")), key=lambda d: d["type"])
    if ex:
        return ex[0]
    for d in docs:
        if d["url"].endswith("/" + primary):
            return d
    return docs[0] if docs else None


def seen_ids() -> set[str]:
    p = OUT / "seen.json"
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def main() -> int:
    if session() is None:
        print("::notice title=דוחות מתחרים (SEC)::אין SEC_CONTACT — דילוג")
        return 0
    cfg = PEERS / "peers.json"
    if not cfg.exists():
        print("::warning title=דוחות מתחרים (SEC)::אין מפת מתחרים")
        return 0
    peers = json.loads(cfg.read_text(encoding="utf-8")).get("holdings") or {}
    cmap = cik_map()
    if not cmap:
        print("::warning title=דוחות מתחרים (SEC)::מפת הטיקרים של SEC לא נטענה — אין דוחות בריצה הזו")
        return 0
    tg = targets(peers, cmap)
    days = int(os.environ.get("PEERS_SEC_DAYS") or 4)
    since = (date.today() - timedelta(days=days)).isoformat()
    seen = seen_ids()
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    rows, skipped, failed = [], 0, 0
    for cik, t in tg.items():
        sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", as_json=True)
        if not sub:
            failed += 1
            continue
        rec = sub.get("filings", {}).get("recent", {})
        n = len(rec.get("form") or [])
        for i in range(n):
            filed = rec["filingDate"][i]
            if filed < since:
                break                                   # הרשימה ממוינת מהחדש לישן
            form, acc = rec["form"][i], rec["accessionNumber"][i]
            items = (rec.get("items") or [""] * n)[i] or ""
            if acc in seen or form not in ("8-K", "6-K"):
                continue
            if form == "8-K" and "2.02" in items:
                kind = "results"
            elif form == "8-K" and any(k in items for k in EVENT_ITEMS):
                kind = "event"
            elif form == "6-K":
                kind = "results?"
            else:
                seen.add(acc)
                continue
            docs = documents(cik, acc)
            doc = pick(docs, rec["primaryDocument"][i])
            text = fetch_text(doc["url"]) if doc else ""
            seen.add(acc)
            if kind == "results?":
                head = text[:5000]
                if not (RESULTS.search(head) and SALES.search(head)):
                    skipped += 1
                    continue
                kind = "results"
            if len(text) < 400:
                skipped += 1
                continue
            (CACHE / f"{acc}.txt").write_text(text, encoding="utf-8")
            first = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 25), "")[:200]
            rows.append({"id": acc, "cik": cik, "ticker": t["ticker"], "company": t["company"],
                         "sec_name": t["sec_name"], "form": form, "items": items, "kind": kind,
                         "events": [EVENT_ITEMS[k] for k in EVENT_ITEMS if k in items],
                         "filed": filed, "accepted": rec.get("acceptanceDateTime", [""] * n)[i],
                         "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm",
                         "doc_url": doc["url"] if doc else "", "title": first, "chars": len(text),
                         "holdings": t["holdings"]})
    if rows:
        with (OUT / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "seen.json").write_text(json.dumps(sorted(seen)[-4000:]), encoding="utf-8")
    res = sum(1 for r in rows if r["kind"] == "results")
    print(f"::notice title=דוחות מתחרים (SEC)::{len(tg)} חברות מדווחות · {len(rows)} דוחות חדשים "
          f"({res} תוצאות, {len(rows) - res} אירועים) · {skipped} 6-K שאינם תוצאות · {failed} כשלים · "
          f"חלון {days} ימים")
    return 0


if __name__ == "__main__":
    sys.exit(main())
