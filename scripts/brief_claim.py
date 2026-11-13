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

**טריגרים מפורשים — אותה הגנה, מתוך הגיט (13/11/2026, ערב).** דחיפה של
.trigger/daily-brief.json שאינה if_missing — ברייף כפוי, עקיפת בלם, topics_only — היא
בקשה מפורשת כמו לחיצה, ונדרסת בתור באותה דרך. כאן אין צורך ב-KV: הבקשה שמורה בקומיט
שדחף אותה, וה-API מחזיר לכל ריצת push את ה-sha שלה. מהטריגרים המפורשים של השעתיים
האחרונות (כמו תוקף topics_only), כל אחד נבדק:
· **טופל** — ריצת ה-push שלו התחילה (יש לה ג'ובים; ריצה שבוטלה בתור אינה משאירה
  אף אחד), או ששיגור חוזר שלו עבר את שלב "Restore recovered trigger". כש-GitHub אינו
  עונה על השאלה, הטריגר נחשב כמטופל: שיגור כפול של ברייף כפוי עולה כסף, ואין לו
  בדיקת requested_at שתעצור אותו.
· **הוחלף** — טריגר מפורש חדש יותר מאותו סוג, או ברייף מלא חדש יותר אחרי topics_only.
  שתי דחיפות של ברייף כפוי הן תיקון ולא שתי בקשות; רענון סקטורים אינו מחליף ברייף.
הוותיק שלא טופל ולא הוחלף משוגר מחדש עם trigger_sha. הריצה ההיא בודקת שוב, מחזירה את
הקובץ לתוכנו בקומיט, ומתנהגת כמו הדחיפה עצמה (brief_args, mode=trigger).

**שיגור חוזר אחד לכל היותר בכל ריצה,** ורק כשאין ריצה ממתינה: יש מקום אחד בתור, ושני
שיגורים היו מבטלים זה את זה. לחיצה קודמת לטריגר; הריצה ששוגרה תשגר את הבא בתורו.

פלט ל-$GITHUB_OUTPUT:
· mode — click (לבצע לחיצה) / trigger (לבצע טריגר משוחזר) / due (רשת ביטחון) /
  own (הריצה כפי שהופעלה)
· edition, requested_at — של הלחיצה, כש-mode=click
· trigger_sha, trigger_pushed — של הטריגר, כש-mode=trigger
· pages — האם להפעיל את כל צנרות העמודים (refresh-pages)
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brief_args as ba  # noqa: E402
import kv_request as kv  # noqa: E402

WORKFLOW = "daily-brief.yml"
# done חייב לחיות יותר מהלחיצה עצמה (ארבע שעות ב-brief.js), אחרת לחיצה שבוצעה
# הייתה חוזרת להיות "ממתינה" כשהסימון פג.
DONE_TTL = 86400
LABEL = {"": "לפי השעה", "morning": "בוקר", "midday": "צהריים", "close": "נעילה", "night": "לילה"}

TRIGGER_FILE = ".trigger/daily-brief.json"
TRIGGER_MAX_AGE_MIN = int(ba.TOPICS_ONLY_TTL_H * 60)
# ה-run-name של שיגור חוזר (daily-brief.yml), וה-sha המלא אחריו. claim_smoke בודק
# ששני הקבצים מסכימים על הנוסח ועל שם השלב.
TRIGGER_TITLE = "טריגר · שיגור חוזר · "
TRIGGER_RE = re.compile(re.escape(TRIGGER_TITLE) + r"([0-9a-f]{40})")
RESTORE_STEP = "Restore recovered trigger"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
KIND_HE = {"full": "ברייף כפוי", "topics": "רענון סקטורים"}


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
    """רענון כל העמודים: בלחיצה, ובשיגור ידני כפי שהיה תמיד. לא בתזמון ולא בטריגר —
    גם לא בטריגר משוחזר, כי הדחיפה המקורית לא הייתה מרעננת."""
    if mode == "click":
        return True
    return mode == "own" and event == "workflow_dispatch" and not source


def trigger_plan(*, own_sha: str, own_push: bool, run_id: str, view: list[dict], now: datetime,
                 max_age_min: int = TRIGGER_MAX_AGE_MIN) -> dict:
    """ההחלטה על טריגרים מפורשים, בלי רשת.

    view — ריצות daily-brief שקשורות לטריגר מפורש (build_view): id, sha, via (push /
    redispatch), kind (full / topics), state (active / executed / dropped), created, title.
    own_sha — הטריגר של הריצה הזו: ה-sha שלה בריצת push, או trigger_sha בשיגור חוזר.

    מחזיר execute — רק בשיגור חוזר: האם לבצע את own_sha — עם why, pushed ו-title; ו-redispatch:
    הטריגר הוותיק שלא טופל ולא הוחלף, אם יש, לשיגור חוזר."""
    trig: dict[str, dict] = {}
    for r in sorted(view, key=lambda r: r["created"]):
        if (r["via"] == "push" and r["kind"] in KIND_HE
                and now - r["created"] <= timedelta(minutes=max_age_min)):
            trig.setdefault(r["sha"], {"kind": r["kind"], "pushed": r["created"],
                                       "title": r.get("title") or ""})

    def superseded_by(sha: str) -> str | None:
        me = trig[sha]
        return next((s for s, o in trig.items()
                     if s != sha and o["pushed"] > me["pushed"] and o["kind"] in (me["kind"], "full")),
                    None)

    def handled_by(sha: str) -> str | None:
        if own_push and sha == own_sha:
            return str(run_id)                     # ריצת ה-push הזו מבצעת אותו עכשיו
        return next((str(r["id"]) for r in view
                     if r["sha"] == sha and str(r["id"]) != str(run_id) and r["state"] != "dropped"),
                    None)

    res: dict = {"execute": None, "why": "", "pushed": None, "title": "", "redispatch": None}
    if own_sha and not own_push:
        t = trig.get(own_sha)
        if t is None:
            res.update(execute=False, why=f"הוא אינו בין הטריגרים המפורשים של {max_age_min // 60} "
                                          "השעות האחרונות")
        elif (s := superseded_by(own_sha)):
            res.update(execute=False, why=f"טריגר חדש יותר מחליף אותו ({trig[s]['title'][:60] or s[:7]})")
        elif (h := handled_by(own_sha)):
            res.update(execute=False, why=f"הוא כבר בוצע, או ממתין לביצוע, בריצה {h}")
        else:
            res.update(execute=True, pushed=t["pushed"], title=t["title"])
    for sha, t in trig.items():                    # מהוותיק לחדש
        if sha == own_sha or superseded_by(sha) or handled_by(sha):
            continue
        res["redispatch"] = {"sha": sha, **t}
        break
    return res


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


def _repo_get(path: str) -> dict | None:
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    if not (repo and os.environ.get("GH_TOKEN")):
        return None
    code, body = gh("GET", f"/repos/{repo}{path}")
    if code != 200:
        return None
    try:
        val = json.loads(body)
    except ValueError:
        return None
    return val if isinstance(val, dict) else None


def list_runs() -> list[dict] | None:
    """הריצות האחרונות של daily-brief, החדשה ראשונה. None כשהרשימה לא נקראה."""
    got = _repo_get(f"/actions/workflows/{WORKFLOW}/runs?per_page=30")
    return None if got is None else (got.get("workflow_runs") or [])


def trigger_content(sha: str) -> dict | None:
    """קובץ הטריגר כפי שהיה בקומיט — מה שריצת ה-push שלו קראה."""
    got = _repo_get(f"/contents/{TRIGGER_FILE}?ref={sha}")
    try:
        val = json.loads(base64.b64decode((got or {}).get("content") or "").decode("utf-8"))
    except (ValueError, TypeError):
        return None
    return val if isinstance(val, dict) else None


def run_jobs(run_id) -> list[dict] | None:
    got = _repo_get(f"/actions/runs/{run_id}/jobs?filter=all&per_page=50")
    return None if got is None else (got.get("jobs") or [])


def run_state(r: dict, via: str, jobs) -> str:
    """active — בתור או רצה; executed — ביצעה את הטריגר; dropped — לא ביצעה.

    ריצה שבוטלה בתור אינה משאירה ג'וב. כשהג'ובים אינם נקראים — executed: עדיף לוותר על
    שחזור מאשר להפיק ברייף כפוי פעמיים."""
    if r.get("status") != "completed":
        return "active"
    if via == "push" and r.get("conclusion") != "cancelled":
        return "executed"
    js = jobs(r.get("id"))
    if js is None:
        return "executed"
    if via == "push":
        return "executed" if js else "dropped"
    ran = any(s.get("name") == RESTORE_STEP and s.get("conclusion") == "success"
              for j in js for s in (j.get("steps") or []))
    return "executed" if ran else "dropped"


def build_view(runs: list[dict], now: datetime, content, jobs,
               max_age_min: int = TRIGGER_MAX_AGE_MIN) -> list[dict]:
    """הריצות של השעתיים האחרונות שקשורות לטריגר מפורש, במבנה של trigger_plan.
    content(sha) — קובץ הטריגר בקומיט; jobs(run_id) — הג'ובים של ריצה. None = לא נקרא."""
    recent = []
    for r in runs:
        t = kv.parse_at(r.get("created_at"))
        if t and now - t <= timedelta(minutes=max_age_min):
            recent.append((r, t))
    kinds: dict[str, str] = {}
    for r, t in recent:
        sha = r.get("head_sha") or ""
        if r.get("event") == "push" and sha and sha not in kinds:
            cfg = content(sha)
            # תוכן שלא נקרא — לא משחזרים: אין דרך לדעת מה הדחיפה ביקשה.
            kinds[sha] = ba.trigger_kind(cfg, t) if isinstance(cfg, dict) else "skip"
    explicit = {s for s, k in kinds.items() if k in KIND_HE}
    view = []
    for r, t in recent:
        m = TRIGGER_RE.search(r.get("display_title") or "")
        if r.get("event") == "push" and r.get("head_sha") in explicit:
            sha, via = r["head_sha"], "push"
        elif r.get("event") == "workflow_dispatch" and m and m.group(1) in explicit:
            sha, via = m.group(1), "redispatch"
        else:
            continue
        view.append({"id": r.get("id"), "sha": sha, "via": via, "kind": kinds[sha],
                     "state": run_state(r, via, jobs), "created": t,
                     "title": (r.get("display_title") or "") if via == "push" else ""})
    return view


def dispatch(inputs: dict) -> tuple[int, str]:
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    if not (repo and os.environ.get("GH_TOKEN")):
        return 0, "אין אסימון"
    return gh("POST", f"/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches",
              {"ref": "main", "inputs": inputs})


def redispatch_click(click: dict, run_id: str) -> tuple[str, str, str]:
    ed, at = click["edition"], click["at"]
    what = f"לחיצה על הפק מ-{when(at)} ({LABEL.get(ed, ed)})"
    code, body = dispatch({"edition": ed, "reviews": "", "requested_at": at,
                           "redispatch_of": str(run_id)})
    if code == 204:
        return ("notice", "לחיצה שוגרה מחדש",
                f"{what} לא בוצעה — כנראה בוטלה בתור, או שהשיגור מהאתר נכשל. היא שוגרה "
                "מחדש ותרוץ אחרי הריצה הזו.")
    return ("warning", "השיגור החוזר נכשל",
            f"{what} לא בוצעה, ו-GitHub השיב {code} ({body[:160]}). היא נשארת ב-KV "
            "ותיבדק בריצה הבאה.")


def redispatch_trigger(t: dict, run_id: str) -> tuple[str, str, str]:
    what = f"טריגר {t['sha'][:7]} — {KIND_HE.get(t['kind'], t['kind'])} ({t['title'][:80]})"
    code, body = dispatch({"trigger_sha": t["sha"], "redispatch_of": str(run_id)})
    if code == 204:
        return ("notice", "טריגר שוגר מחדש",
                f"{what} בוטל בתור לפני שרץ. הוא שוגר מחדש ויתבצע אחרי הריצה הזו, כמו הדחיפה "
                "המקורית.")
    return ("warning", "השיגור החוזר של הטריגר נכשל",
            f"{what} לא בוצע, ו-GitHub השיב {code} ({body[:160]}). הריצה הבאה תנסה שוב, "
            f"עד {TRIGGER_MAX_AGE_MIN // 60} שעות מהדחיפה.")


def run() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    source = (os.environ.get("IN_SOURCE") or "").strip()
    own_edition = (os.environ.get("IN_EDITION") or "").strip()
    own_trigger = (os.environ.get("IN_TRIGGER_SHA") or "").strip().lower()
    # שיגור חוזר של טריגר אינו לחיצה, גם אם מישהו מילא בו requested_at.
    own_at = "" if own_trigger else (os.environ.get("IN_REQUESTED_AT") or "").strip()
    redispatch_of = (os.environ.get("IN_REDISPATCH_OF") or "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID") or ""
    now = datetime.now(timezone.utc)

    # --- 1. לחיצות, מ-KV ---
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
    notes = d["notes"]

    # --- 2. הריצות של daily-brief: מי בתור, ואילו טריגרים מפורשים לא בוצעו ---
    runs = list_runs()
    own_push = event == "push" and not source and not own_trigger
    own_sha = own_trigger or (os.environ.get("GITHUB_SHA", "") if own_push else "")
    tp = None
    if runs is not None:
        try:
            view = build_view(runs, now, trigger_content, run_jobs)
            tp = trigger_plan(own_sha=own_sha, own_push=own_push, run_id=run_id, view=view, now=now)
        except Exception as e:  # noqa: BLE001 — טריגר שלא נבדק אינו עוצר את השאר
            notes.append(("warning", "הטריגרים לא נבדקו", f"{type(e).__name__}: {str(e)[:160]}"))

    # --- 3. שיגור חוזר של טריגר: האם לבצע אותו כאן ---
    trig_sha = trig_pushed = ""
    if own_trigger:
        what = f"טריגר {own_trigger[:7]}"
        if not SHA_RE.match(own_trigger):
            why = f"trigger_sha לא תקין ('{own_trigger[:50]}')"
        elif tp is None:
            why = "לא ניתן היה לוודא מול GitHub שהוא לא בוצע (הריצה הבאה תבדוק שוב)"
        elif not tp["execute"]:
            why = tp["why"]
        else:
            why = ""
            d.update(mode="trigger", edition="", at="")
            trig_sha, trig_pushed = own_trigger, tp["pushed"].isoformat(timespec="seconds")
            notes.append(("notice", "טריגר משוחזר",
                          f"{what} ({tp['title'][:80]}) בוטל בתור לפני שרץ. הקובץ מוחזר לתוכנו "
                          "בקומיט, והריצה מתנהגת כמו הדחיפה עצמה."))
        if why:
            d.update(mode="due", edition="", at="")
            notes.append(("notice", "הטריגר אינו מבוצע כאן",
                          f"{what}: {why}. הריצה ממשיכה כרשת ביטחון: המהדורה שבזמן, ורק אם חסרה."))

    # --- 4. שיגור חוזר: אחד לכל היותר, ורק כשאין ריצה ממתינה ---
    want_click = d["redispatch"]
    want_trig = tp["redispatch"] if tp else None
    if want_click or want_trig:
        waiting = [r for r in runs or []
                   if r.get("status") != "completed" and str(r.get("id")) != str(run_id)]
        if waiting:
            what = "לחיצה על הפק" if want_click else f"טריגר {want_trig['sha'][:7]}"
            notes.append(("notice", "בקשה ממתינה",
                          f"{what} עוד לא בוצע/ה. ריצה {waiting[0].get('id')} כבר ממתינה אחרי הריצה "
                          "הזו, והיא תבדוק בעצמה."))
        elif want_click:
            # רשימה שלא נקראה אינה סיבה להשאיר לחיצה בלי ריצה: השיגור כמו בלעדיה.
            notes.append(redispatch_click(want_click, run_id))
            if want_trig:
                notes.append(("notice", "טריגר ממתין",
                              f"טריגר {want_trig['sha'][:7]} עוד לא בוצע. הוא ישוגר מהריצה ששוגרה "
                              "עכשיו — יש מקום אחד בתור."))
        else:
            notes.append(redispatch_trigger(want_trig, run_id))

    for level, title, text in notes:
        annotate(level, title, text)
    out(mode=d["mode"], edition=d["edition"], requested_at=d["at"],
        trigger_sha=trig_sha, trigger_pushed=trig_pushed,
        pages="true" if pages_for(d["mode"], event, source) else "false")
    return 0


def main() -> int:
    try:
        return run()
    except Exception as e:  # noqa: BLE001 — הבדיקה הזו לעולם אינה עוצרת ברייף
        annotate("error", "בדיקת הלחיצה נכשלה",
                 f"{type(e).__name__}: {str(e)[:200]} — הריצה ממשיכה לפי ה-inputs שלה, "
                 "כמו לפני 13/11.")
        out(mode="", edition="", requested_at="", trigger_sha="", trigger_pushed="", pages="")
        return 0


if __name__ == "__main__":
    sys.exit(main())
