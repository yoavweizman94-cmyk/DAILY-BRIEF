# -*- coding: utf-8 -*-
"""שליחת תמצית הברייף לטלגרם: תמונת בוקר + כותרות רמה 3 + קישור לעמוד המלא.

חילוץ מכני מהברייף:
- "תמונת בוקר" — כל הסעיף.
- "כותרות רמה 3" — לפי החוזה ב-CLAUDE.md: אייטם רמה 3 נפתח בשורת פסקה עם **כותרת
  מודגשת**. נאספות ההדגשות הפותחות מכל הסעיפים (עד תקרה).

דורש TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID בסביבה.
שימוש: python scripts/send_telegram.py [--date YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from _tls import harden
from _env import load_env
harden()
load_env()

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
MAX_HEADLINES = 8
TG_LIMIT = 4096


def section(md: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", md,
                  re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def level3_headlines(md: str) -> list[str]:
    """שורות פסקה שנפתחות ב-**מודגש** — כותרות אייטמי רמה 3."""
    out, seen = [], set()
    body = re.sub(r"^## (תמונת בוקר|שווקים|בקצרה|מה לעקוב היום|תקלות מקורות)\s*\n.*?(?=^## |\Z)",
                  "", md, flags=re.MULTILINE | re.DOTALL)
    for m in re.finditer(r"^\*\*(.+?)\*\*", body, re.MULTILINE):
        h = m.group(1).strip().rstrip(":—-")
        if h and h not in seen and not h.startswith(("כיוון", "משמעות")):
            seen.add(h)
            out.append(h)
    return out[:MAX_HEADLINES]


def md_to_tg(text: str) -> str:
    """המרה מינימלית של Markdown ל-HTML של טלגרם.

    quote=False בכוונה: טלגרם דורש רק &amp; &lt; &gt;. בריחה של גרשיים הופכת
    כל מונח עברי עם גרשיים (ת"א, נדל"ן, אג"ח) ל-&quot; על המסך.
    """
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not args.dry_run and (not token or not chat_id):
        print("שגיאה: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID לא מוגדרים", file=sys.stderr)
        return 1

    brief_path = ROOT / "output" / f"brief_{args.date}.md"
    if not brief_path.exists():
        print(f"שגיאה: {brief_path} לא קיים", file=sys.stderr)
        return 1
    md = brief_path.read_text(encoding="utf-8")

    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    base_url = cfg.get("site", {}).get("base_url", "").rstrip("/")
    link = f"{base_url}/briefs/{args.date}.html" if base_url else ""

    title = md.splitlines()[0].lstrip("# ").strip() if md.strip() else f"ברייף {args.date}"
    morning = section(md, "תמונת בוקר")
    headlines = level3_headlines(md)

    parts = [f"<b>{html.escape(title, quote=False)}</b>", "", md_to_tg(morning)]
    if headlines:
        parts += ["", "<b>עיקרי היום:</b>"]
        parts += [f"• {md_to_tg(h)}" for h in headlines]
    if link:
        parts += ["", f'<a href="{link}">לברייף המלא ←</a>']
    text = "\n".join(parts)
    if len(text) > TG_LIMIT:
        text = text[:TG_LIMIT - 60].rsplit("\n", 1)[0] + f'\n<a href="{link}">להמשך ←</a>'

    if args.dry_run:
        print(text)
        return 0

    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print(f"שגיאה משליחת טלגרם: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return 1
    print("נשלח לטלגרם")
    return 0


if __name__ == "__main__":
    sys.exit(main())
