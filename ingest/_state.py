# -*- coding: utf-8 -*-
"""גישה ל-data/state.sqlite: היסטוריית מחירים + IDs שכבר דווחו בברייפים קודמים.

כלל הדה-דופ: אייטם שנראה לראשונה ביום קודם — לא נכלל שוב היום. אייטם שנראה
לראשונה היום נשאר נכלל גם בריצות חוזרות של אותו יום (idempotent).
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "state.sqlite"


def connect() -> sqlite3.Connection:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(STATE)
    con.execute("""CREATE TABLE IF NOT EXISTS prices (
        key TEXT NOT NULL, date TEXT NOT NULL, value REAL NOT NULL,
        PRIMARY KEY (key, date))""")
    con.execute("""CREATE TABLE IF NOT EXISTS reported_ids (
        source TEXT NOT NULL, item_id TEXT NOT NULL, first_seen TEXT NOT NULL,
        PRIMARY KEY (source, item_id))""")
    return con


def filter_new(con: sqlite3.Connection, source: str, ids: list[str],
               today: str | None = None) -> set[str]:
    """מחזיר את תת-הקבוצה של ids שאינם 'ישנים' (נראו לראשונה יום קודם),
    ורושם את החדשים עם first_seen=today."""
    today = today or date.today().isoformat()
    keep: set[str] = set()
    for item_id in ids:
        row = con.execute(
            "SELECT first_seen FROM reported_ids WHERE source=? AND item_id=?",
            (source, str(item_id))).fetchone()
        if row is None:
            con.execute(
                "INSERT INTO reported_ids (source, item_id, first_seen) VALUES (?,?,?)",
                (source, str(item_id), today))
            keep.add(str(item_id))
        elif row[0] == today:
            keep.add(str(item_id))
    con.commit()
    return keep
