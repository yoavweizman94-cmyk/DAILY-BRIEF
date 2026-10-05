# -*- coding: utf-8 -*-
"""קריאה ישירה ל-API של Anthropic לעבודות של "טקסט נתון → JSON": מיון, בחירה, סיקור.

**למה לא דרך ה-CLI כמו _cli.run.** ה-CLI הוא סוכן: הוא שולח את הנחיות המערכת
וכלי העבודה שלו בכל קריאה. נמדד 05/10/2026 — קריאה ריקה ב-Sonnet יצרה 54,561
טוקני מטמון ועלתה $0.218 לפני שהמודל קרא מילה מהקלט. ועל עבודה של כותרות:
קריאת CLI אחת על 260 כותרות רצה 16 דקות, עלתה $0.99 ונעצרה בתקרה בלי תוצאה.
כאן אין סוכן, אין כלים ואין שלב חשיבה: הקלט, הסכימה, והתשובה.

**העלות נרשמת לאותו יומן** (output/costs/<יום>.jsonl, דרך _cli.log_cost), ולכן
גם לבלם היומי של הברייף. ה-API אינו מחזיר מחיר — הוא מחושב מהטוקנים לפי
המחירון למטה.

**בלי מפתח (הרצה מקומית) — חזרה ל-CLI**, שמתחבר בהתחברות של המשתמש. יקר
ואיטי, אבל מאפשר לבדוק פרומפט בלי מפתח API במחשב.
"""
from __future__ import annotations

import json
import os

import _cli

DEFAULT_MODEL = "claude-sonnet-5"
# $ לטוקן. Sonnet 5 נגזר 05/10/2026 מקריאת CLI: 54,561 טוקני כתיבת מטמון (שעה,
# פי 2 ממחיר קלט) ועוד 2 קלט ו-4 פלט עלו $0.218288 — כלומר $2 למיליון קלט,
# ו-$10 לפלט ביחס המקובל של 1:5. מודל שאינו כאן מתומחר כ-Sonnet, ומסומן.
PRICES = {
    "claude-sonnet-5": {"in": 2e-6, "out": 10e-6, "cache_write": 2.5e-6, "cache_read": 0.2e-6},
}


def _usd(model: str, usage) -> tuple[float, bool]:
    p = PRICES.get(model)
    known = p is not None
    p = p or PRICES[DEFAULT_MODEL]
    usd = ((getattr(usage, "input_tokens", 0) or 0) * p["in"]
           + (getattr(usage, "output_tokens", 0) or 0) * p["out"]
           + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * p["cache_write"]
           + (getattr(usage, "cache_read_input_tokens", 0) or 0) * p["cache_read"])
    return usd, known


def ask_json(system: str, data: str, schema: dict, *, job: str, max_tokens: int = 8000,
             model: str | None = None, max_usd: float = 1.0) -> tuple[dict | None, str | None, float]:
    """קריאה אחת: (JSON, שגיאה, עלות). שגיאה של יתרה מכילה את _cli.CREDIT_RE."""
    model = model or os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
    if not os.environ.get("ANTHROPIC_API_KEY"):
        text, err, meta = _cli.run(system + "\n\nהנתונים ב-stdin.", job=job, model=model,
                                   max_usd=max_usd, schema=schema, stdin=data, max_turns=3)
        if err:
            return None, err, float(meta.get("cost") or 0)
        try:
            return json.loads(text or ""), None, float(meta.get("cost") or 0)
        except ValueError:
            return None, f"פלט שאינו JSON ({len(text or '')} תווים)", float(meta.get("cost") or 0)

    import anthropic  # רק כשיש מפתח: הרצה מקומית בלי מפתח אינה צריכה את הספרייה

    client = anthropic.Anthropic(timeout=600, max_retries=2)
    kwargs = dict(model=model, max_tokens=max_tokens, system=system,
                  thinking={"type": "disabled"},
                  output_config={"format": {"type": "json_schema", "schema": schema}},
                  messages=[{"role": "user", "content": data}])
    try:
        msg = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        m = getattr(e, "message", "") or str(e)
        return None, f"API {e.status_code}: {m[:240]}", 0.0
    except anthropic.APIError as e:
        return None, f"{type(e).__name__}: {str(e)[:240]}", 0.0

    usd, known = _usd(model, msg.usage)
    _cli.log_cost(job, usd, model=model, via="api", tokens_in=msg.usage.input_tokens,
                  tokens_out=msg.usage.output_tokens, **({} if known else {"price": "estimated"}))
    if msg.stop_reason == "max_tokens":
        return None, f"התשובה נקטעה ב-{max_tokens} טוקנים", usd
    if msg.stop_reason == "refusal":
        return None, "סירוב", usd
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    try:
        return json.loads(text), None, usd
    except ValueError:
        return None, f"פלט שאינו JSON ({len(text)} תווים)", usd
