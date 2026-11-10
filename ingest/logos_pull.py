# -*- coding: utf-8 -*-
"""לוגואים של החברות, לתמונת השבוע בעמוד שיחות הוועידה — מהאתר של החברה עצמה.

**למה מהאתר של החברה.** יואב, 10/11/2026: "את הלוגו של כל חברה תיקח ממקור אינטרנטי
עם הלוגו הכי עדכני". מאיה אינה מחזיקה לוגו (השדה logo ריק אצל כל 16 החברות שנבדקו),
אבל היא מחזיקה את כתובת האתר של החברה (company details → site), והאתר של החברה הוא
המקור העדכני ביותר ללוגו שלה.

**סדר ההעדפה בעמוד הבית:**
  1. <img> שהכתובת, ה-alt, ה-class או ה-id שלו כוללים "logo" — הראשון בעמוד, שהוא
     כמעט תמיד הלוגו שבכותרת. לוגואים של צד שלישי (נגישות, רשתות חברתיות, הבורסה,
     רשות ניירות ערך) מסוננים.
  2. <svg> מוטמע עם "logo" ב-class, ב-id או ב-aria-label.
  3. apple-touch-icon — סמל המותג בריבוע.
אם אין אף אחד מאלה — אין לוגו, והתמונה מציגה את שם החברה. לא מנחשים.

**קובץ מאתר זר אינו מוגש כמות שהוא.** תמונה רסטרית נפתחת ב-Pillow ונשמרת מחדש כ-PNG
(בלי מטא-דאטה, ובלי קובץ שהוא גם תמונה וגם משהו אחר). SVG עובר ניקוי: בלי script,
foreignObject, מאזיני אירועים וקישורים חיצוניים, ובלי DOCTYPE או ENTITY. SVG עם
סקריפט, כשהוא מוגש מהדומיין שלנו ונפתח ישירות, היה רץ בהקשר של האתר — עם עוגיית
הסשן של מי שפתח אותו.

**מי מקבל לוגו.** החברות שבלוח הדוחות והשיחות (output/calls/upcoming.json) — אלה
שמופיעות בתמונת השבוע. לוגו בן יותר מ-REFRESH_DAYS נמשך מחדש, וניסיון שנכשל חוזר
אחרי RETRY_DAYS.

פלט: output/logos/<maya_company_id>.(png|svg) ו-output/logos/manifest.json.
שימוש: python ingest/logos_pull.py [--max N] [--force ID ...]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402

harden()
from curl_cffi import requests as creq  # noqa: E402

from _maya_api import MayaSession  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "logos"
MANIFEST = OUT / "manifest.json"
SCHEDULE = ROOT / "output" / "calls" / "upcoming.json"
REFRESH_DAYS = 30
RETRY_DAYS = 14
MAX_RUN = 80
MAX_BYTES = 400_000
MAX_W = 480

# לוגו של צד שלישי שמופיע באתרי חברות — לא הלוגו של החברה
THIRD = re.compile(r"nagish|accessib|negish|נגיש|facebook|linkedin|twitter|whatsapp|instagram|youtube|"
                   r"tiktok|google|apple|android|app-?store|play|tase|isa\.gov|magna|maya|wix-?logo|"
                   r"flag|lang|cookie|captcha|partner|client|award|certif|iso[-_ ]?\d", re.I)
LOGO = re.compile(r"logo", re.I)


class _Page(HTMLParser):
    """המועמדים מהעמוד, לפי סדר הופעתם."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.imgs: list[str] = []
        self.touch: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "img":
            src = a.get("src") or a.get("data-src") or a.get("data-lazy-src") or ""
            if not src:
                srcset = a.get("srcset") or a.get("data-srcset") or ""
                src = srcset.split(",")[-1].strip().split(" ")[0] if srcset else ""
            hay = " ".join((src, a.get("alt", ""), a.get("class", ""), a.get("id", ""), a.get("title", "")))
            if src and LOGO.search(hay) and not THIRD.search(hay):
                self.imgs.append(src)
        elif tag == "link":
            rel = a.get("rel", "").lower()
            if "apple-touch-icon" in rel and a.get("href"):
                self.touch.append(a["href"])


_INLINE = re.compile(r"<svg\b[^>]*(?:class|id|aria-label)\s*=\s*[\"'][^\"']*logo[^\"']*[\"'][^>]*>.*?</svg>",
                     re.I | re.S)
SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "{http://www.w3.org/1999/xlink}href"
BAD_TAGS = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video", "handler", "listener"}


def clean_svg(text: str) -> str | None:
    """SVG בלי שום דבר שרץ או נטען מבחוץ — או None כשאי אפשר לנקות בביטחון."""
    if len(text) > MAX_BYTES or re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    if not root.tag.lower().endswith("svg"):
        return None
    for parent in root.iter():
        for child in list(parent):
            tag = str(child.tag).split("}")[-1].lower()
            if tag in BAD_TAGS:
                parent.remove(child)
    for el in root.iter():
        for k in list(el.attrib):
            name = k.split("}")[-1].lower()
            v = el.attrib[k].strip().lower()
            if name.startswith("on"):
                del el.attrib[k]
            elif name == "href" or k == XLINK:
                if not (v.startswith("#") or v.startswith("data:image/png") or v.startswith("data:image/jpeg")):
                    del el.attrib[k]
            elif "javascript:" in v or ("url(" in v and "url(#" not in v):
                del el.attrib[k]
        tag = str(el.tag).split("}")[-1].lower()
        if tag == "style" and el.text and re.search(r"@import|url\((?!\s*#)", el.text, re.I):
            el.text = ""
    if not (root.get("viewBox") or (root.get("width") and root.get("height"))):
        return None
    # **מידות מפורשות מה-viewBox.** SVG בלי width/height נטען בדפדפן בגודל ברירת
    # מחדל של 300×150, והלוגו היה נמתח בקנבס ליחס הזה במקום ליחס שלו.
    try:
        vb = [float(v) for v in re.split(r"[\s,]+", (root.get("viewBox") or "").strip()) if v][-2:]
    except ValueError:
        vb = []
    w, h = root.get("width", ""), root.get("height", "")
    if len(vb) == 2 and vb[0] > 0 and vb[1] > 0 and (not w or not h or "%" in w + h):
        root.set("width", f"{vb[0]:g}")
        root.set("height", f"{vb[1]:g}")
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    return ET.tostring(root, encoding="unicode")


def raster_png(raw: bytes) -> bytes | None:
    """תמונה רסטרית → PNG נקי, עד MAX_W ברוחב. None כשזו אינה תמונה סבירה ללוגו."""
    try:
        from PIL import Image  # noqa: PLC0415
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:  # noqa: BLE001
        return None
    w, h = im.size
    if w < 32 or h < 16 or w * h > 25_000_000:
        return None
    im = im.convert("RGBA")
    if w > MAX_W:
        im = im.resize((MAX_W, max(1, round(h * MAX_W / w))))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def get(url: str, timeout: int = 20):
    return creq.get(url, impersonate="chrome", timeout=timeout, allow_redirects=True)


def fetch_logo(site: str) -> tuple[bytes, str, str, str] | None:
    """(תוכן, סיומת, כתובת המקור, סוג) — או None."""
    base = site.strip()
    if not base:
        return None
    if not base.startswith("http"):
        base = "https://" + base.lstrip("/")
    try:
        r = get(base)
    except Exception:  # noqa: BLE001
        try:
            r = get(base.replace("https://", "http://", 1))
        except Exception:  # noqa: BLE001
            return None
    if r.status_code >= 400 or not r.text:
        return None
    home = str(r.url)
    html = r.text[:2_000_000]
    p = _Page()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    for src in p.imgs[:4]:
        url = urllib.parse.urljoin(home, src.strip())
        got = _download(url)
        if got:
            return got[0], got[1], url, "img"
    m = _INLINE.search(html)
    if m:
        svg = clean_svg(m.group(0))
        if svg:
            return svg.encode("utf-8"), "svg", home, "svg-inline"
    for src in p.touch[:2]:
        url = urllib.parse.urljoin(home, src.strip())
        got = _download(url)
        if got:
            return got[0], got[1], url, "touch"
    return None


def _download(url: str) -> tuple[bytes, str] | None:
    if url.startswith("data:"):
        return None
    try:
        r = get(url)
    except Exception:  # noqa: BLE001
        return None
    raw = r.content or b""
    if r.status_code >= 400 or len(raw) < 200 or len(raw) > MAX_BYTES * 5:
        return None
    head = raw[:600].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in raw[:2000].lower()):
        svg = clean_svg(raw.decode("utf-8", "replace"))
        return (svg.encode("utf-8"), "svg") if svg else None
    png = raster_png(raw)
    return (png, "png") if png else None


def schedule_ids() -> list[int]:
    """החברות שבלוח, מהקרוב לרחוק."""
    try:
        d = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = sorted((d.get("reports") or []) + (d.get("calls") or []), key=lambda r: r.get("date") or "")
    today = date.today().isoformat()
    return list(dict.fromkeys(int(r["company_id"]) for r in rows
                              if r.get("company_id") and (r.get("date") or "") >= today))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=MAX_RUN)
    ap.add_argument("--force", type=int, nargs="*", default=[])
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        man = {}
    today = date.today()
    fresh_cut = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    retry_cut = (today - timedelta(days=RETRY_DAYS)).isoformat()

    def due(cid: int) -> bool:
        e = man.get(str(cid)) or {}
        if cid in args.force or not e:
            return True
        return (e.get("at") or "") < (retry_cut if e.get("fail") else fresh_cut)

    todo = [c for c in dict.fromkeys(args.force + schedule_ids()) if due(c)][:args.max]
    maya = MayaSession() if todo else None
    got = failed = 0
    for cid in todo:
        e = man.get(str(cid)) or {}
        site = e.get("site")
        if not site:
            try:
                site = (maya.company_details(cid) or {}).get("site") or ""
            except Exception:  # noqa: BLE001
                site = ""
        res = fetch_logo(site) if site else None
        if not res:
            man[str(cid)] = {"site": site, "fail": "no-site" if not site else "not-found",
                             "at": today.isoformat(), **({"file": e["file"]} if e.get("file") else {})}
            failed += 1
            continue
        data, ext, src, kind = res
        for old in OUT.glob(f"{cid}.*"):
            if old.suffix != f".{ext}":
                old.unlink()
        (OUT / f"{cid}.{ext}").write_bytes(data)
        man[str(cid)] = {"file": f"{cid}.{ext}", "src": src, "site": site, "kind": kind,
                         "at": today.isoformat()}
        got += 1
    MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    have = sum(1 for v in man.values() if v.get("file"))
    print(f"::notice title=לוגואים של חברות::{got} נמשכו, {failed} לא נמצאו מתוך {len(todo)} "
          f"בריצה · {have} לוגואים בסך הכל")
    return 0


if __name__ == "__main__":
    sys.exit(main())
