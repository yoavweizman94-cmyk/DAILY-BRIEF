# -*- coding: utf-8 -*-
"""כותרות ענף הרכב — ישראל ועולם — לגיליון auto.html.

מקורות, נושאים וחברות מוגדרים ב-config/auto.yaml. שני סוגי מקורות:
פידי RSS של אתרי רכב, ושאילתות Google News שמביאות כותרות מאתרים בלי RSS
פתוח (כלכליסט, גלובס, TheMarker, רויטרס). הגישה ב-curl_cffi עם חיקוי
דפדפן, כמו ב-rss_pull.

**הסינון דטרמיניסטי ולא במודל.** כותרת נשמרת רק אם יש בה אחד מנושאי הגיליון
(מכירות בישראל, מיסוי, מכסים, חשמלי, יצרנים סיניים, שרשרת אספקה, מימון
וביטוח, דלק). פידים צרכניים (השקות דגמים) נכנסים רק עם מילה עסקית. מבחני
דרכים ומקורות רעש נחסמים לפי כותרת ומקור. הניתוח עצמו — scripts/analyze_auto.py.

פלט: output/auto/items/<YYYY-MM-DD>.jsonl, כותרת בשורה:
  {id, ts, title, source, url, region, themes, companies, snippet}
גוף הכתבה אינו נשמר — רק תקציר קצר מה-RSS, לשימוש הניתוח בלבד.

GITHUB_OUTPUT: new=<מספר>, analyze=yes|no, changed=yes|no
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402
harden()

import yaml  # noqa: E402
from curl_cffi import requests as creq  # noqa: E402

from _text import clean_html  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "auto.yaml"
COMPANIES = ROOT / "config" / "companies.yaml"
OUT = ROOT / "output" / "auto"

LOOKBACK_H = 72        # כותרת ישנה מזה אינה נשמרת כחדשה
FIRST_RUN_H = 24 * 7   # בריצה הראשונה — שבוע, כדי שהעמוד לא ייפתח כמעט ריק
STALE_DAYS = 14        # פיד שהכותרת החדשה בו ישנה מזה — כנראה מת
KEEP_DAYS = 8          # כמה קובצי יום נקראים לדה-דופ
SNIPPET = 320
MIN_NEW = int(os.environ.get("AUTO_MIN_NEW", "6"))
MIN_HOURS = float(os.environ.get("AUTO_MIN_HOURS", "5"))
HEB = "֐-׿"
NS = {"atom": "http://www.w3.org/2005/Atom",
      "content": "http://purl.org/rss/1.0/modules/content/",
      "dc": "http://purl.org/dc/elements/1.1/"}


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Jerusalem")
    except Exception:  # noqa: BLE001 — Windows בלי tzdata
        return timezone(timedelta(hours=3))


IL = _tz()


# --------------------------------------------------------------------------
# התאמת מילים

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("״", '"').replace("׳", "'").replace("“", '"').replace("”", '"')
    s = s.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


def matchers(words, whole_word_hebrew: bool = False) -> list[re.Pattern]:
    """עברית: מתחילת מילה, עם עד שתי תחיליות (ו/ה/ב/ל/מ/ש/כ), ובלי גבול בסוף —
    כדי ש"יבואנ" יתפוס "והיבואנים". שם חברה מקבל גבול גם בסוף, כדי ש"רבל"
    לא יתפוס מילה ארוכה יותר. אנגלית: מילה שלמה, עם s/es אופציונלי."""
    pats = []
    for w in words or []:
        k = norm(w)
        if not k:
            continue
        if re.search(f"[{HEB}]", k):
            tail = f"(?![{HEB}])" if whole_word_hebrew else ""
            pats.append(re.compile(f"(?<![{HEB}])(?:[והבלמשכ]{{0,2}}){re.escape(k)}{tail}"))
        else:
            pats.append(re.compile(rf"(?<![\w]){re.escape(k)}(?:s|es)?(?![\w])"))
    return pats


def hits(pats: list[re.Pattern], text: str) -> bool:
    return any(p.search(text) for p in pats)


def title_key(title: str) -> str:
    """מפתח דה-דופ: אותה כותרת מגיעה מ-RSS ומ-Google News בכתובות שונות."""
    return re.sub(r"[\W_]+", "", norm(title))[:90]


# --------------------------------------------------------------------------
# קריאת פידים

def _txt(el, *paths) -> str:
    for p in paths:
        found = el.find(p, NS)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def _ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except Exception:  # noqa: BLE001
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_feed(xml: str, source: str, gn: bool) -> list[dict]:
    root = ET.fromstring(xml)
    items = root.findall(".//item") or root.findall(".//atom:entry", NS)
    rows = []
    for it in items:
        title = clean_html(_txt(it, "title", "atom:title"), max_chars=300)
        link = _txt(it, "link", "guid")
        if not link:
            a = it.find("atom:link", NS)
            link = (a.get("href") if a is not None else "") or ""
        src = source
        snippet = ""
        if gn:
            # Google News: הכותרת היא "כותרת - מקור", והמקור גם באלמנט source.
            s_el = it.find("source")
            if s_el is not None and (s_el.text or "").strip():
                src = s_el.text.strip()
            if src and title.endswith(" - " + src):
                title = title[: -(len(src) + 3)].strip()
        else:
            snippet = clean_html(_txt(it, "description", "atom:summary", "content:encoded",
                                      "atom:content"), max_chars=SNIPPET)
            if norm(snippet).startswith(norm(title)[:40]):
                snippet = snippet[len(title):].strip(" -–—:")
        ts = _ts(_txt(it, "pubDate", "dc:date", "atom:published", "atom:updated"))
        if title:
            rows.append({"title": title, "url": link or None, "source": src, "snippet": snippet, "_ts": ts})
    return rows


def gn_url(query: str, region: str) -> str:
    q = urllib.parse.quote(query)
    if region == "il":
        return f"https://news.google.com/rss/search?q={q}&hl=he&gl=IL&ceid=IL:he"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# --------------------------------------------------------------------------
# אחסון

def read_items(days: int = KEEP_DAYS) -> list[dict]:
    rows = []
    d = OUT / "items"
    if not d.exists():
        return rows
    for p in sorted(d.glob("*.jsonl"), reverse=True)[:days]:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def last_analysis() -> dict | None:
    d = OUT / "analyses"
    if not d.exists():
        return None
    for p in sorted(d.glob("*.jsonl"), reverse=True):
        lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def write_items(new: list[dict]) -> None:
    by_day: dict[str, list[dict]] = {}
    for r in new:
        day = datetime.fromisoformat(r["ts"]).astimezone(IL).date().isoformat()
        by_day.setdefault(day, []).append(r)
    (OUT / "items").mkdir(parents=True, exist_ok=True)
    for day, rows in by_day.items():
        p = OUT / "items" / f"{day}.jsonl"
        old = []
        if p.exists():
            old = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        seen = {o["id"] for o in old}
        merged = old + [r for r in rows if r["id"] not in seen]
        merged.sort(key=lambda r: r["ts"], reverse=True)
        with p.open("w", encoding="utf-8", newline="\n") as f:
            for r in merged:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------

def main() -> int:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
    known = {(c.get("name_he") or "").strip()
             for c in (yaml.safe_load(COMPANIES.read_text(encoding="utf-8")) or {}).get("companies") or []}

    themes = [(t["slug"], matchers(t.get("keywords"))) for t in cfg.get("themes") or []]
    business = matchers(cfg.get("business_words"))
    auto_words = matchers(cfg.get("auto_words"))
    ex_sources = [norm(x) for x in cfg.get("exclude_sources") or []]
    ex_titles = [norm(x) for x in cfg.get("exclude_title") or []]
    world_ok = [norm(x) for x in cfg.get("world_sources") or []]
    companies = []
    bad_names = []
    for g in cfg.get("chain") or []:
        for c in g.get("companies") or []:
            if c["name"] not in known:
                bad_names.append(c["name"])
            terms = c.get("match") or [c["name"], *(c.get("aliases") or [])]
            companies.append((c["name"], matchers(terms, whole_word_hebrew=True)))
    if bad_names:
        # שם שאינו ב-companies.yaml היה מוצג בעמוד כחברת כיסוי בלי להיות כזו.
        print("::warning title=חברות בגיליון הרכב שאינן ברשימת הכיסוי::" + ", ".join(bad_names))

    sources = [(f["name"], f["url"], f.get("region") or "world", bool(f.get("business_only")), False,
                bool(f.get("auto_only"))) for f in cfg.get("feeds") or []]
    for region, queries in (cfg.get("google_news") or {}).items():
        for q in queries or []:
            sources.append((f"Google News: {q}", gn_url(q, region), region, False, True, False))

    now = datetime.now(timezone.utc)
    existing = read_items()
    cutoff = now - timedelta(hours=LOOKBACK_H if existing else FIRST_RUN_H)
    stale_cut = now - timedelta(days=STALE_DAYS)
    seen = {r["id"] for r in existing}
    session = creq.Session(impersonate="chrome")

    fresh: dict[str, dict] = {}
    failures, stale, per_source = [], [], {}
    dropped = {"ישן": 0, "מקור חסום": 0, "מקור עולם לא ברשימה": 0, "מבחן/צרכנות": 0,
               "בלי נושא": 0, "לא עסקי": 0, "לא רכב": 0}
    for name, url, region, business_only, gn, auto_only in sources:
        try:
            r = session.get(url, timeout=30, allow_redirects=True)
            r.raise_for_status()
            rows = parse_feed(r.text, name, gn)
        except Exception as e:  # noqa: BLE001 — מקור אחד שנכשל אינו עוצר את השאר
            failures.append(f"{name} ({type(e).__name__}: {str(e)[:60]})")
            continue
        finally:
            time.sleep(1.2 if gn else 0.3)
        newest = max((x["_ts"] for x in rows if x["_ts"]), default=None)
        if rows and newest and newest < stale_cut and not gn:
            stale.append(f"{name} ({newest.date().isoformat()})")
            continue
        kept = 0
        for x in rows:
            ts = x["_ts"] or now
            if ts < cutoff:
                dropped["ישן"] += 1
                continue
            src = norm(x["source"])
            if any(s and s in src for s in ex_sources):
                dropped["מקור חסום"] += 1
                continue
            if gn and region == "world" and not any(w and w in src for w in world_ok):
                dropped["מקור עולם לא ברשימה"] += 1
                continue
            t = norm(x["title"])
            if any(e and e in t for e in ex_titles):
                dropped["מבחן/צרכנות"] += 1
                continue
            blob = norm(f"{x['title']} {x['snippet']}")
            if (business_only or region == "world") and not hits(business, blob):
                dropped["לא עסקי"] += 1
                continue
            if auto_only and not hits(auto_words, blob):
                dropped["לא רכב"] += 1
                continue
            th = [slug for slug, pats in themes if hits(pats, blob)]
            if not th:
                dropped["בלי נושא"] += 1
                continue
            key = title_key(x["title"])
            rid = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
            if rid in seen:
                continue
            item = {"id": rid, "ts": ts.astimezone(timezone.utc).isoformat(timespec="seconds"),
                    "title": x["title"], "source": x["source"], "url": x["url"],
                    "region": region, "themes": th,
                    "companies": [n for n, pats in companies if hits(pats, blob)],
                    "snippet": x["snippet"]}
            prev = fresh.get(rid)
            if prev:
                # אותה כותרת משני מקורות: ישראל גוברת, והנושאים מתאחדים.
                prev["themes"] = sorted(set(prev["themes"]) | set(th))
                prev["companies"] = sorted(set(prev["companies"]) | set(item["companies"]))
                if region == "il":
                    prev["region"] = "il"
                if not prev.get("snippet") and item["snippet"]:
                    prev["snippet"] = item["snippet"]
                continue
            fresh[rid] = item
            kept += 1
        per_source[name] = kept

    ok = len(sources) - len(failures)
    if ok == 0:
        print("::error title=גיליון הרכב: כל המקורות נכשלו::" + " · ".join(failures[:4]))
        return 1
    if failures:
        print("::warning title=מקורות רכב שנכשלו::" + " · ".join(failures[:8]))
    if stale:
        print("::warning title=פידי רכב שלא התעדכנו::" + " · ".join(stale))

    new = list(fresh.values())
    if new:
        write_items(new)
    # מצב המשיכה נשמר לחוד מהכותרות: ריצה בלי כותרת חדשה היא עדיין ריצה,
    # והעמוד צריך לדעת להבדיל בינה לבין צנרת שלא רצה.
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "state.json").write_text(json.dumps({
        "fetched_at": datetime.now(IL).isoformat(timespec="minutes"),
        "sources_ok": ok, "sources_total": len(sources), "failures": failures[:12],
        "stale": stale, "new": len(new)}, ensure_ascii=False, indent=1), encoding="utf-8")

    # **מתי מנתחים.** ריצה שלא הביאה מספיק כותרות חדשות, או שבאה שעות
    # ספורות אחרי הניתוח הקודם, אינה מזמינה ניתוח — הסקירה הייתה חוזרת
    # כמעט מילה במילה, ובכל פעם בתשלום.
    last = last_analysis()
    items = existing + new
    if last and last.get("through"):
        since = [r for r in items if r["ts"] > last["through"]]
        age_h = (now - datetime.fromisoformat(last["analyzed_at"])).total_seconds() / 3600
    else:
        since, age_h = [r for r in items if datetime.fromisoformat(r["ts"]) >= cutoff], 1e9
    analyze = (len(since) >= MIN_NEW and age_h >= MIN_HOURS) or os.environ.get("AUTO_FORCE") == "1"
    why = (f"{len(since)} כותרות מאז הניתוח הקודם"
           + (f", לפני {age_h:.1f} שעות" if age_h < 1e8 else ", אין ניתוח קודם"))

    n_il = sum(1 for r in new if r["region"] == "il")
    top = {}
    for r in new:
        for t in r["themes"]:
            top[t] = top.get(t, 0) + 1
    busiest = ", ".join(f"{k}={v}" for k, v in sorted(top.items(), key=lambda kv: -kv[1])[:5])
    cos = sorted({c for r in new for c in r["companies"]})
    print(f"::notice::גיליון הרכב: {len(new)} כותרות חדשות (ישראל {n_il}, עולם {len(new) - n_il}) · "
          f"מקורות {ok}/{len(sources)} · נושאים: {busiest or '—'}"
          + (f" · חברות: {', '.join(cos)}" if cos else "")
          + f" · ניתוח: {'כן' if analyze else 'לא'} ({why})")
    print("  נפסלו: " + ", ".join(f"{k} {v}" for k, v in dropped.items()))
    for name, kept in per_source.items():
        print(f"  {kept:>3}  {name}")

    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"new={len(new)}\n")
            f.write(f"analyze={'yes' if analyze else 'no'}\n")
            f.write(f"changed={'yes' if new or analyze else 'no'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
