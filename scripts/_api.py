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
import re

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
             model: str | None = None, max_usd: float = 1.0, effort: str | None = None,
             info: dict | None = None) -> tuple[dict | None, str | None, float]:
    """קריאה אחת: (JSON, שגיאה, עלות). שגיאה של יתרה מכילה את _cli.CREDIT_RE.

    effort — None: בלי שלב חשיבה (מיון, בחירה, סיכום — עבודה מכנית על טקסט נתון).
    "low"/"medium"/"high": חשיבה מסתגלת במאמץ הזה — לסקירות, שבהן ה-CLI חשב לפני
    שכתב, וויתור על כך היה משנה את הסקירה ולא רק את המחיר.
    info — אם נמסר, מתמלא בטוקנים, במשך ובסיבת העצירה, ללוג של הקורא.
    """
    model = model or os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
    if not os.environ.get("ANTHROPIC_API_KEY"):
        text, err, meta = _cli.run(system + "\n\nהנתונים ב-stdin.", job=job, model=model,
                                   max_usd=max_usd, schema=schema, stdin=data, max_turns=3)
        if err:
            return None, err, float(meta.get("cost") or 0)
        return _parse(text or "", float(meta.get("cost") or 0))

    import anthropic  # רק כשיש מפתח: הרצה מקומית בלי מפתח אינה צריכה את הספרייה

    import time

    client = anthropic.Anthropic(timeout=900, max_retries=2)
    out_cfg: dict = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        out_cfg["effort"] = effort
    kwargs = dict(model=model, max_tokens=max_tokens, system=system,
                  thinking={"type": "adaptive"} if effort else {"type": "disabled"},
                  output_config=out_cfg,
                  messages=[{"role": "user", "content": data}])
    t0 = time.monotonic()
    try:
        # **סטרימינג תמיד.** סקירה ארוכה בעברית עם שלב חשיבה עלולה לרוץ דקות, והספרייה
        # מסרבת לבקשה לא-מוזרמת שצפויה לחרוג מעשר דקות. התוצאה זהה — הודעה אחת.
        try:
            with client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
        except anthropic.BadRequestError as e:
            # מודל שאינו מקבל חשיבה או מאמץ יחד עם פלט מובנה — פעם אחת בלעדיהם,
            # ולא סקירה שלא נכתבה. הדחייה היא 400 לפני כל טוקן, ואין עליה חיוב.
            if not effort or not re.search(r"thinking|effort", getattr(e, "message", "") or str(e), re.I):
                raise
            kwargs["thinking"] = {"type": "disabled"}
            kwargs["output_config"] = {"format": out_cfg["format"]}
            with client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
    except anthropic.APIStatusError as e:
        m = getattr(e, "message", "") or str(e)
        return None, f"API {e.status_code}: {m[:240]}", 0.0
    except anthropic.APIError as e:
        return None, f"{type(e).__name__}: {str(e)[:240]}", 0.0

    usd, known = _usd(model, msg.usage)
    _cli.log_cost(job, usd, model=model, via="api", tokens_in=msg.usage.input_tokens,
                  tokens_out=msg.usage.output_tokens, **({} if known else {"price": "estimated"}))
    if info is not None:
        info.update({"tokens_in": msg.usage.input_tokens, "tokens_out": msg.usage.output_tokens,
                     "ms": int((time.monotonic() - t0) * 1000), "stop": msg.stop_reason,
                     "usd": usd})
    if msg.stop_reason == "max_tokens":
        return None, f"התשובה נקטעה ב-{max_tokens} טוקנים", usd
    if msg.stop_reason == "refusal":
        return None, "סירוב", usd
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _parse(text, usd)


def run_review(prompt: str, schema: dict, *, job: str, effort: str | None = "medium",
               max_usd: float | None = None, max_tokens: int = 32000,
               instruction: str = "נתח לפי ההוראות והנתונים שבהודעה. החזר JSON לפי הסכימה בלבד.",
               ) -> tuple[str | None, str | None, dict]:
    """אותו חוזה כמו run_model הישן בסקירות הרכב, הסחורות והלמ"ס: (טקסט JSON, שגיאה, מטא).

    הפרומפט המלא — הוראות ונתונים — הוא ההודעה, כמו שהיה ב-stdin של ה-CLI, ולכן
    parse() והבדיקות שאחריו בכל סקריפט לא השתנו. "תורות" הוא תמיד 1: אין סוכן.
    """
    info: dict = {}
    res, err, usd = ask_json(instruction, prompt, schema, job=job, max_tokens=max_tokens,
                             max_usd=max_usd or 2.0, effort=effort, info=info)
    meta = {"cost": usd, "ms": info.get("ms"), "turns": 1, "subtype": info.get("stop"),
            "out_tokens": info.get("tokens_out"), "in_tokens": info.get("tokens_in")}
    if err:
        return None, err, meta
    return json.dumps(res, ensure_ascii=False), None, meta


def _parse(text: str, usd: float) -> tuple[dict | None, str | None, float]:
    """JSON מהתשובה. סובלני לגדר markdown ולטקסט שאחרי האובייקט; בכשל — המקום
    והסיבה בלבד, בלי הטקסט עצמו (הלוג ציבורי, והטקסט הוא התוכן)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    start = t.find("{")
    try:
        obj, _end = json.JSONDecoder().raw_decode(t[start:] if start >= 0 else t)
        return obj, None, usd
    except ValueError as e:
        msg = getattr(e, "msg", type(e).__name__)
        pos = getattr(e, "pos", None)
        return None, f"פלט שאינו JSON ({len(text)} תווים; {msg} בתו {pos})", usd
