# -*- coding: utf-8 -*-
"""גנרטור סטטי מינימלי: output/brief_*.md → site/dist/ (RTL, נפרס ל-GitHub Pages).

- index.html — הברייף האחרון + ניווט לארכיון
- briefs/<date>.html — עמוד לכל ברייף
- archive.html — רשימת כל הברייפים
שימוש: python site/build.py
"""
from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "dist"
STYLE = Path(__file__).parent / "style.css"

MD_EXT = ["tables", "sane_lists", "smarty"]

PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<link rel="stylesheet" href="{root}style.css">
</head>
<body>
<header>
  <nav><a href="{root}index.html">ברייף אחרון</a> · <a href="{root}archive.html">ארכיון</a></nav>
  <div class="brand">{site_title}</div>
</header>
<main>
{body}
</main>
<footer>נוצר אוטומטית · לשימוש פנימי · אין לראות באמור המלצת השקעה</footer>
</body>
</html>
"""


def render(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=MD_EXT)


def brief_title(md_text: str, fallback: str) -> str:
    first = md_text.strip().splitlines()[0] if md_text.strip() else ""
    return first.lstrip("# ").strip() or fallback


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    site_title = cfg.get("site", {}).get("title", "ברייף FOREST")

    briefs = sorted(ROOT.glob("output/brief_*.md"), reverse=True)
    briefs = [p for p in briefs if re.match(r"brief_\d{4}-\d{2}-\d{2}\.md$", p.name)]

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "briefs").mkdir(parents=True)
    shutil.copy(STYLE, OUT / "style.css")

    entries = []
    for p in briefs:
        date = p.stem.replace("brief_", "")
        md_text = p.read_text(encoding="utf-8")
        title = brief_title(md_text, f"ברייף {date}")
        (OUT / "briefs" / f"{date}.html").write_text(
            PAGE.format(title=title, site_title=site_title, root="../",
                        body=render(md_text)),
            encoding="utf-8")
        entries.append((date, title))

    if entries:
        latest_date, latest_title = entries[0]
        latest_md = briefs[0].read_text(encoding="utf-8")
        index_body = render(latest_md)
    else:
        latest_title = site_title
        index_body = "<p>אין עדיין ברייפים ב-output/.</p>"
    (OUT / "index.html").write_text(
        PAGE.format(title=latest_title, site_title=site_title, root="",
                    body=index_body),
        encoding="utf-8")

    items = "\n".join(
        f'<li><a href="briefs/{d}.html">{t}</a></li>' for d, t in entries)
    archive_body = f"<h1>ארכיון</h1>\n<ul class=\"archive\">\n{items}\n</ul>" if items \
        else "<h1>ארכיון</h1><p>ריק.</p>"
    (OUT / "archive.html").write_text(
        PAGE.format(title=f"ארכיון · {site_title}", site_title=site_title, root="",
                    body=archive_body),
        encoding="utf-8")

    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"נבנה {OUT} | {len(entries)} ברייפים | "
          f"{datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
