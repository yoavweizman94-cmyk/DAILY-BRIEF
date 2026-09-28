# -*- coding: utf-8 -*-
"""קריאה אחת ל-CLI של claude לעבודות המכניות — סיכומים וסקירות — ויומן עלויות.

**מודל, תיקייה ותקרה — שלושתם במפורש, ולא כברירת מחדל.** נמדד 28/09/2026 עם
אותה קריאה ריקה בדיוק ("החזר: ok"):

    מתיקיית הפרויקט, ברירת מחדל   claude-opus-5[1m]   $0.366
    מתיקייה זמנית, ברירת מחדל     claude-opus-5[1m]   $0.156
    מתיקייה זמנית, Sonnet         claude-sonnet-5     $0.052

שלושה דברים נגזרים מזה. ברירת המחדל של ה-CLI היא **אופוס בהקשר של מיליון
טוקנים** — המדרגה היקרה ביותר. קריאה שרצה מתיקיית הפרויקט טוענת את CLAUDE.md
(45KB של הוראות כתיבת ברייף) לכל בקשה, ומשלמת עליהן גם כשהיא רק מסכמת דיווח.
ועבודת סיכום — טקסט נתון, סכימה, פלט מובנה — אינה צריכה את המודל היקר; זו
בדיוק העבודה שסקירות הרכב, הסחורות והלמ"ס עושות ב-Sonnet מאז ומעולם.

**כל קריאה נרשמת.** העלות נכתבת ל-output/costs/<יום>.jsonl והבנייה מדפיסה את
הסכום היומי לפי עבודה. בלי זה אין דרך לדעת לאן הלך הכסף עד שהיתרה נגמרת —
וכך אכן קרה פעמיים בשבועיים.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COSTS = ROOT / "output" / "costs"
DEFAULT_MODEL = "claude-sonnet-5"
CREDIT_RE = "credit balance is too low"


def log_cost(job: str, usd, **extra) -> None:
    """שורה ליומן העלויות. כשל בכתיבה אינו מפיל עבודה שכבר שולמה."""
    try:
        COSTS.mkdir(parents=True, exist_ok=True)
        line = {"at": datetime.now().isoformat(timespec="minutes"), "job": job,
                "usd": round(float(usd or 0), 4), **extra}
        with (COSTS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        pass


def envelope(out: str, rc: int, err: str) -> tuple[str | None, str | None, dict]:
    """מפרק את מעטפת ה-JSON של ה-CLI: (טקסט, שגיאה, מטא)."""
    try:
        env = json.loads(out or "")
    except ValueError:
        env = None
    if not isinstance(env, dict) or not ("result" in env or "subtype" in env):
        if rc != 0:
            return None, f"קוד {rc} — " + (" ".join((err or out or "").split())[-240:] or "בלי פלט שגיאה"), {}
        return out, None, {}
    usage = env.get("usage") or {}
    meta = {"cost": env.get("total_cost_usd"), "ms": env.get("duration_ms"),
            "turns": env.get("num_turns"), "subtype": env.get("subtype"),
            "in_tokens": usage.get("input_tokens"), "out_tokens": usage.get("output_tokens"),
            # קריאות המטמון הן המדד לכובד ההקשר: קלט גדול אינו נקרא פעם אחת
            # אלא נשלח מחדש בכל תור, ושם הוא מתומחר שוב (בעשירית, אבל שוב).
            "cache_read": usage.get("cache_read_input_tokens"),
            "cache_new": usage.get("cache_creation_input_tokens"),
            "models": ", ".join((env.get("modelUsage") or {}).keys())}
    if env.get("is_error") or rc != 0:
        return None, (f"{env.get('subtype')}: " + " ".join(str(env.get("result") or "").split())[:240]), meta
    return str(env.get("result") or ""), None, meta


def run(prompt: str, *, job: str, model: str | None = None, max_usd: float | None = None,
        timeout: int = 900, tools: str = "", **log) -> tuple[str | None, str | None, dict]:
    """מריץ קריאה אחת ומחזיר (טקסט, שגיאה, מטא). רץ מתיקייה זמנית: בלי CLAUDE.md."""
    model = model or os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
    cmd = ["claude", "-p", prompt, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--allowedTools", tools, "--model", model]
    if max_usd:
        cmd += ["--max-budget-usd", str(max_usd)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout, cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        return None, f"חריגה מ-{timeout} שניות", {}
    except OSError as e:  # noqa: BLE001
        return None, f"{type(e).__name__} — {e}", {}
    text, err, meta = envelope(proc.stdout, proc.returncode, proc.stderr)
    if meta.get("cost"):
        log_cost(job, meta["cost"], model=model, **log)
    return text, err, meta
