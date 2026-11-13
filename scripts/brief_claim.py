# -*- coding: utf-8 -*-
"""מי מבצע לחיצה על "הפק": הריצה שמחזיקה כרגע את המקום בתור של daily-brief.

**התקלה (13/11/2026).** ב-concurrency של daily-brief יש מקום לריצה פעילה אחת ולריצה
ממתינה אחת, וריצה חדשה שנכנסת לתור מבטלת את הממתינה. לחיצה מ-00:36 חיכתה אחרי מהדורת
הלילה, ו-cron מאוחר ביטל אותה ב-00:57. ה-cron עצמו יצא על "המהדורה כבר קיימת", וריצה
מתוזמנת אינה מרעננת עמודים — כך שרענון העמודים של הלחיצה אבד בלי עקבה. ריצה שבוטלה
בתור אינה משאירה ג'וב אחד, וה-API אינו מחזיר את ה-inputs שלה.

**התיקון: הלחיצה שמורה ב-KV, והשיגור רק מעיר ריצה.** הכפתור כותב את הלחיצה ל-KV ואז
משגר (site/functions/api/brief.js). כל ריצה של daily-brief פותחת בג'וב הזה, שרץ רק
כשהריצה כבר קיבלה את מקומה בתור:
· **ריצת לחיצה** — workflow_dispatch עם requested_at, או קריאה מ-brief-request.yml —
  תובעת את הלחיצה הממתינה: רושמת את ה-at שלה ב-`brief:request:done` *לפני* ההפקה,
  ומבצעת אותה.
· **כל ריצה אחרת** (תזמון, טריגר, שיגור ידני בלי requested_at) שמוצאת לחיצה ממתינה,
  ואין אחריה ריצה בתור, משגרת את הלחיצה מחדש עם אותם inputs — וממשיכה בשלה.
ריצה שביטלה לחיצה בתור היא בדיוק מי שמחזיקה את המקום אחר כך, ולכן היא שמשגרת אותה.

**בלי שיגור כשיש ריצה בתור.** ריצה ממתינה תקבל את המקום אחרינו ותראה את הלחיצה בעצמה.
שיגור במקומה היה מבטל אותה — וייתכן שזה טריגר מפורש, כמו עקיפת בלם.

**ולעולם לא פעמיים.** done הוא סימן מים: לחיצה שה-at שלה אינו חדש ממנו כבר בוצעה. ריצת
לחיצה שמגיעה אחרי שריצה אחרת ביצעה את אותה לחיצה — מרוץ בין התור לשיגור, למשל — אינה
מפיקה ואינה מרעננת שוב. היא ממשיכה כרשת ביטחון: המהדורה שבזמן, ורק אם חסרה. זה מה שהריצה
שאולי ביטלה בדרכה הייתה עושה. מעל כל זה נשארת בדיקת requested_at ב-run_daily.sh: מהדורה
שנכתבה אחרי הלחיצה אינה נכתבת שוב.

**ה-KV אינו תנאי.** כשאי אפשר לקרוא אותו, ריצת לחיצה פועלת לפי ה-inputs שלה, כמו לפני
13/11; כשאי אפשר לרשום בו תביעה, רק הלחיצה המקורית פועלת — לא שיגור חוזר ולא התור —
אחרת כל ריצה הייתה מבצעת אותה שוב.

פלט ל-$GITHUB_OUTPUT:
· mode — click (לבצע לחיצה) / due (רשת ביטחון) / own (הריצה כפי שהופעלה)
· edition, requested_at — של הלחיצה, כש-mode=click
· pages — האם להפעיל את כל צנרות העמודים (refresh-pages)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kv_request as kv  # noqa: E402

WORKFLOW = "daily-brief.yml"
# done חייב לחיות יותר מהלחיצה עצמה (ארבע שעות ב-brief.js), אחרת לחיצה שבוצעה
# הייתה חוזרת להיות "ממתינה" כשהסימון פג.
DONE_TTL = 86400
LABEL = {"": "לפי השעה", "morning": "בוקר", "midday": "צהריים", "close": "נעילה", "night": "לילה"}


def when(at: str) -> str:
    """שעת הלחיצה בשעון המקומי של הריצה (TZ=Asia/Jerusalem ב-workflow)."""
    t = kv.parse_at(at)
    return t.astimezone().strftime("%d/%m %H:%M") if t else str(at)


def decide(*, event: str, source: str, own_edition: str, own_at: str, redispatch_of: str,
           req: dict | None, done: dict | None, kv_ok: bool, now: datetime,
           max_age_min: int = kv.MAX_AGE_MIN) -> dict:
    """ההחלטה, בלי רשת. מחזיר mode / edition / at / claim / original / redispatch / notes."""
    d: dict = {"mode": "own", "edition": "", "at": "", "claim": False, "original": False,
               "redispatch": None, "notes": []}

    def note(level: str, title: str, text: str) -> None:
        d["notes"].append((level, title, text))

    claimer = bool(source) or (event == "workflow_dispatch" and bool(own_at))
    if not claimer:
        if not kv_ok:
            note("warning", "התור של הפק לא נבדק",
                 "ה-KV לא נקרא, ולכן לא נבדק אם לחיצה ממתינה. הריצה ממשיכה כרגיל.")
            return d
        if kv.pending(req, done, now, max_age_min)[0]:
            d["redispatch"] = {"edition": kv.edition_of(req), "at": str(req["at"])}
        return d

    d["original"] = not source and not redispatch_of
    own_t = kv.parse_at(own_at)
    own = {"edition": kv.edition_of({"edition": own_edition}), "at": own_at} if own_t else None
    if own_at and own_t is None:
        if not source:
            note("warning", "requested_at לא קריא",
                 f"'{own_at[:40]}' — הריצה מתנהגת כשיגור ידני: הפקה כפויה ורענון העמודים.")
            return d
        note("warning", "requested_at לא קריא", f"'{own_at[:40]}' — נבדקת רק הלחיצה שב-KV.")

    if not kv_ok:
        ok, why = kv.pending(own, None, now, max_age_min) if own else (False, "empty")
        if ok:
            d.update(mode="click", edition=own["edition"], at=own["at"])
            note("warning", "KV לא נגיש",
                 "הלחיצה מבוצעת לפי ה-inputs של הריצה, בלי סימון שבוצעה — כמו לפני 13/11.")
        else:
            d["mode"] = "due"
            note("warning", "KV לא נגיש",
                 ("הלחיצה ישנה מדי לביצוע." if why == "stale" else "אין לחיצה לבצע.")
                 + " הריצה ממשיכה כרשת ביטחון: המהדורה שבזמן, ורק אם חסרה.")
        return d

    cands = []
    if kv.pending(req, done, now, max_age_min)[0]:
        cands.append({"edition": kv.edition_of(req), "at": str(req["at"])})
    own_ok, own_why = kv.pending(own, done, now, max_age_min) if own else (False, "empty")
    if own_ok:
        cands.append(own)
    if not cands:
        d["mode"] = "due"
        if own_why == "done":
            text = (f"הלחיצה מ-{when(own_at)} כבר בוצעה בריצה "
                    f"{(done or {}).get('run') or 'אחרת'}, ולא תבוצע שוב.")
        elif own_why == "stale":
            text = f"הלחיצה מ-{when(own_at)} בת יותר מ-{max_age_min // 60} שעות ולא תבוצע."
        else:
            text = "אין לחיצה ממתינה."
        note("notice", "אין לחיצה לבצע",
             text + " הריצה ממשיכה כרשת ביטחון: המהדורה שבזמן, ורק אם חסרה.")
        return d

    chosen = max(cands, key=lambda c: kv.parse_at(c["at"]))
    d.update(mode="click", edition=chosen["edition"], at=chosen["at"], claim=True)
    if own and chosen["at"] != own["at"]:
        note("notice", "נבחרה לחיצה מאוחרת יותר",
             f"ב-KV ממתינה לחיצה מ-{when(chosen['at'])}, אחרי זו של הריצה "
             f"({when(own_at)}). היא זו שמבוצעת.")
    return d


def pages_for(mode: str, event: str, source: str) -> bool:
    """רענון כל העמודים: בלחיצה, ובשיגור ידני כפי שהיה תמיד. לא בתזמון ולא בטריגר."""
    if mode == "click":
        return True
    return mode == "own" and event == "workflow_dispatch" and not source


# --- I/O ---------------------------------------------------------------------
def annotate(level: str, title: str, text: str) -> None:
    def esc(s: str, prop: bool = False) -> str:
        s = s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return s.replace(":", "%3A").replace(",", "%2C") if prop else s
    print(f"::{level} title={esc(title, True)}::{esc(text)}", flush=True)


def out(**kw) -> None:
    lines = "".join(f"{k}={v}\n" for k, v in kw.items())
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(lines)
    sys.stdout.write(lines)


def gh(method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    url = (os.environ.get("GITHUB_API_URL") or "https://api.github.com") + path
    headers = {"Authorization": f"Bearer {os.environ.get('GH_TOKEN', '')}",
               "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "tlv-tase-view"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except OSError as e:  # noqa: BLE001
        return 0, str(e)


def redispatch(click: dict, run_id: str) -> tuple[str, str, str]:
    """משגר מחדש לחיצה ממתינה — אלא אם כבר ממתינה ריצה שתראה אותה בעצמה."""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    ed, at = click["edition"], click["at"]
    what = f"לחיצה על הפק מ-{when(at)} ({LABEL.get(ed, ed)})"
    if not (repo and os.environ.get("GH_TOKEN")):
        return ("warning", "לחיצה ממתינה", f"{what} לא בוצעה, ואין כאן אסימון לשגר אותה מחדש.")
    code, body = gh("GET", f"/repos/{repo}/actions/workflows/{WORKFLOW}/runs?per_page=20")
    if code == 200:
        try:
            runs = json.loads(body).get("workflow_runs") or []
        except ValueError:
            runs = []
        waiting = [r for r in runs
                   if r.get("status") != "completed" and str(r.get("id")) != str(run_id)]
        if waiting:
            return ("notice", "לחיצה ממתינה",
                    f"{what} עוד לא בוצעה. ריצה {waiting[0].get('id')} כבר ממתינה אחרי הריצה "
                    "הזו, והיא תבצע אותה.")
    # רשימה שלא נקראה אינה סיבה להשאיר לחיצה בלי ריצה: השיגור כמו בלעדיה.
    code, body = gh("POST", f"/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches",
                    {"ref": "main", "inputs": {"edition": ed, "reviews": "", "requested_at": at,
                                               "redispatch_of": str(run_id)}})
    if code == 204:
        return ("notice", "לחיצה שוגרה מחדש",
                f"{what} לא בוצעה — כנראה בוטלה בתור, או שהשיגור מהאתר נכשל. היא שוגרה "
                "מחדש ותרוץ אחרי הריצה הזו.")
    return ("warning", "השיגור החוזר נכשל",
            f"{what} לא בוצעה, ו-GitHub השיב {code} ({body[:160]}). היא נשארת ב-KV "
            "ותיבדק בריצה הבאה.")


def run() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    source = (os.environ.get("IN_SOURCE") or "").strip()
    own_edition = (os.environ.get("IN_EDITION") or "").strip()
    own_at = (os.environ.get("IN_REQUESTED_AT") or "").strip()
    redispatch_of = (os.environ.get("IN_REDISPATCH_OF") or "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID") or ""
    now = datetime.now(timezone.utc)

    ns, req, done, kv_ok = None, None, None, False
    if kv.configured():
        ns, _ = kv.namespace()
        if ns:
            ok_req, req = kv.get_json(ns, kv.KEY)
            ok_done, done = kv.get_json(ns, kv.DONE_KEY)
            kv_ok = ok_req and ok_done

    d = decide(event=event, source=source, own_edition=own_edition, own_at=own_at,
               redispatch_of=redispatch_of, req=req, done=done, kv_ok=kv_ok, now=now)

    if d["claim"]:
        rec = {"at": d["at"], "edition": d["edition"], "run": run_id,
               "claimed": now.isoformat(timespec="seconds")}
        what = f"לחיצה על הפק מ-{when(d['at'])} ({LABEL.get(d['edition'], d['edition'])})"
        if kv.put_json(ns, kv.DONE_KEY, rec, ttl=DONE_TTL):
            d["notes"].append(("notice", "לחיצה נתבעה",
                               f"{what} מבוצעת בריצה הזו, עם רענון כל העמודים. אם המהדורה "
                               "נכתבה אחרי הלחיצה — היא אינה נכתבת שוב."))
        elif d["original"]:
            d["notes"].append(("warning", "הלחיצה לא סומנה ב-KV",
                               f"{what} מבוצעת בכל זאת, כי זו הלחיצה עצמה. ריצה מאוחרת עלולה "
                               "לרענן את העמודים פעם נוספת, אבל לא להפיק את המהדורה שוב."))
        else:
            d["notes"].append(("error", "הלחיצה לא סומנה ב-KV",
                               f"{what} אינה מבוצעת כאן: בלי סימון, כל ריצה הבאה הייתה מבצעת "
                               "אותה שוב. הריצה ממשיכה כרשת ביטחון."))
            d.update(mode="due", edition="", at="")

    if d["redispatch"]:
        d["notes"].append(redispatch(d["redispatch"], run_id))

    for level, title, text in d["notes"]:
        annotate(level, title, text)
    out(mode=d["mode"], edition=d["edition"], requested_at=d["at"],
        pages="true" if pages_for(d["mode"], event, source) else "false")
    return 0


def main() -> int:
    try:
        return run()
    except Exception as e:  # noqa: BLE001 — הבדיקה הזו לעולם אינה עוצרת ברייף
        annotate("error", "בדיקת הלחיצה נכשלה",
                 f"{type(e).__name__}: {str(e)[:200]} — הריצה ממשיכה לפי ה-inputs שלה, "
                 "כמו לפני 13/11.")
        out(mode="", edition="", requested_at="", pages="")
        return 0


if __name__ == "__main__":
    sys.exit(main())
