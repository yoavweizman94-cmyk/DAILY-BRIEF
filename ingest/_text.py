# -*- coding: utf-8 -*-
"""חילוץ טקסט קריא מ-HTML (ניוזלטרים, גוף כתבות) — stdlib בלבד."""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table",
               "section", "article", "blockquote"}
_SKIP_TAGS = {"script", "style", "head", "title", "template"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def clean_html(html: str, max_chars: int = 8000) -> str:
    if not html:
        return ""
    if "<" not in html:                       # כבר טקסט חלק
        text = unescape(html)
    else:
        ex = _Extractor()
        try:
            ex.feed(html)
            ex.close()
        except Exception:
            text = re.sub(r"<[^>]+>", " ", html)
        else:
            text = "".join(ex.parts)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " […]"
    return text
