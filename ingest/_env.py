# -*- coding: utf-8 -*-
"""טעינת .env מקומי לתוך os.environ, בלי תלויות חיצוניות.

עקרון: משתנה שכבר מוגדר בסביבה מנצח את הקובץ. כך ב-GitHub Actions ה-Secrets
גוברים, ו-.env משמש רק להרצה מקומית.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def _split(line: str):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, value = line.split("=", 1)
    key, value = key.strip(), value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return key, value


def load_env(path: Path | None = None) -> int:
    """מחזיר כמה משתנים נטענו בפועל."""
    path = path or ENV_FILE
    if not path.exists():
        return 0
    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        pair = _split(line)
        if pair and pair[0] not in os.environ and pair[1]:
            os.environ[pair[0]] = pair[1]
            loaded += 1
    return loaded


def update_env(key: str, value: str, path: Path | None = None) -> bool:
    """מעדכן מפתח ב-.env תוך שמירת שאר השורות. False אם אין קובץ (למשל ב-CI)."""
    path = path or ENV_FILE
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        pair = _split(line)
        if pair and pair[0] == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.environ[key] = value
    return True
