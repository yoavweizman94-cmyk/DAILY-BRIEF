# -*- coding: utf-8 -*-
"""בדיקת עשן ללחיצת "הפק": ההחלטה של brief_claim, הפרמטרים של brief_args, הקלט והפלט
מול KV ו-GitHub מדומים, וסימולציה של התור.

בלי רשת ובלי סודות:
    python scripts/claim_smoke.py

**הסימולציה** משחזרת את ה-concurrency של daily-brief כפי ש-GitHub מפעיל אותו — ריצה
פעילה אחת, ממתינה אחת, וריצה חדשה מבטלת את הממתינה — ומריצה עליו את ההחלטה האמיתית
(brief_claim.decide) מול KV בזיכרון. קודם התקלה של 13/11/2026 כפי שקרתה, פעם בלוגיקה
הישנה (שם הלחיצה צריכה ללכת לאיבוד, אחרת הסימולציה אינה מדמה את GitHub) ופעם בחדשה.
אחר כך אלפי ימים אקראיים של תזמונים, טריגרים, שיגורים ידניים ולחיצות, עם אסימון ובלעדיו,
ובכל אחד נבדק:
· כל לחיצה מבוצעת — בעצמה, או בלחיצה מאוחרת ממנה שגברה עליה (מפתח אחד ב-KV);
· אף לחיצה אינה מבוצעת פעמיים;
· שיגור חוזר אינו מבטל ריצה שממתינה בתור.
"""
from __future__ import annotations

import base64
import contextlib
import heapq
import io
import itertools
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brief_claim as bc  # noqa: E402
import kv_request as kv  # noqa: E402

BASE = datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc)
FAILS: list[str] = []


def iso(t: datetime) -> str:
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{(' — ' + detail) if detail and not ok else ''}")
    if not ok:
        FAILS.append(name)


# --- 1. ההחלטה -----------------------------------------------------------------
def decision_table() -> None:
    now = BASE + timedelta(hours=3)
    a1 = iso(now - timedelta(minutes=30))           # לחיצה לפני חצי שעה
    a2 = iso(now - timedelta(minutes=5))            # לחיצה מאוחרת יותר
    old = iso(now - timedelta(hours=5))             # מעבר לארבע שעות
    R1 = {"edition": "", "at": a1, "by": "o"}
    R2 = {"edition": "close", "at": a2, "by": "o"}
    D1 = {"at": a1, "run": "111"}

    def dec(**kw):
        base = dict(event="workflow_dispatch", source="", own_edition="", own_at="",
                    redispatch_of="", req=None, done=None, kv_ok=True, now=now)
        base.update(kw)
        return bc.decide(**base)

    cases = [
        # (שם, kwargs, mode, claim, at, redispatch-at)
        ("תזמון, תור ריק", dict(event="schedule"), "own", False, "", None),
        ("תזמון, לחיצה ממתינה → שיגור חוזר", dict(event="schedule", req=R1), "own", False, "", a1),
        ("טריגר, לחיצה ממתינה → שיגור חוזר", dict(event="push", req=R1), "own", False, "", a1),
        ("תזמון, לחיצה שבוצעה", dict(event="schedule", req=R1, done=D1), "own", False, "", None),
        ("תזמון, לחיצה ישנה", dict(event="schedule", req={"edition": "", "at": old}), "own", False, "", None),
        ("תזמון, KV לא נגיש", dict(event="schedule", req=R1, kv_ok=False), "own", False, "", None),
        ("שיגור ידני בלי requested_at → שלו, ושיגור חוזר", dict(req=R1), "own", False, "", a1),
        ("לחיצה, KV תואם → תביעה", dict(own_at=a1, req=R1), "click", True, a1, None),
        ("לחיצה, KV עוד ריק → תביעה לפי ה-inputs", dict(own_at=a1, own_edition="night"), "click", True, a1, None),
        ("לחיצה שכבר בוצעה → רשת ביטחון", dict(own_at=a1, req=R1, done=D1), "due", False, "", None),
        ("לחיצה, ב-KV לחיצה מאוחרת → המאוחרת", dict(own_at=a1, req=R2), "click", True, a2, None),
        ("לחיצה, KV לא נגיש → לפי ה-inputs, בלי תביעה", dict(own_at=a1, kv_ok=False), "click", False, a1, None),
        ("לחיצה ישנה, KV ריק → רשת ביטחון", dict(own_at=old), "due", False, "", None),
        ("לחיצה ישנה, KV לא נגיש → רשת ביטחון", dict(own_at=old, kv_ok=False), "due", False, "", None),
        ("שיגור חוזר → תביעה", dict(own_at=a1, req=R1, redispatch_of="222"), "click", True, a1, None),
        ("שיגור חוזר שבוצע → רשת ביטחון", dict(own_at=a1, req=R1, done=D1, redispatch_of="222"),
         "due", False, "", None),
        ("קריאה מהתור → תביעה", dict(event="schedule", source="kv", own_at=a1, req=R1), "click", True, a1, None),
        ("קריאה מהתור שבוצעה → רשת ביטחון", dict(event="schedule", source="kv", own_at=a1, req=R1, done=D1),
         "due", False, "", None),
        ("requested_at לא קריא בשיגור ידני → שלו", dict(own_at="garbage"), "own", False, "", None),
        ("requested_at לא קריא בקריאה מהתור → ה-KV", dict(event="schedule", source="kv", own_at="x", req=R1),
         "click", True, a1, None),
        ("לחיצה עם done ישן → תביעה", dict(own_at=a2, req=R2, done=D1), "click", True, a2, None),
    ]
    for name, kw, mode, claim, at, rd in cases:
        d = dec(**kw)
        got_rd = (d["redispatch"] or {}).get("at")
        ok = (d["mode"], d["claim"], d["at"], got_rd) == (mode, claim, at, rd)
        check(f"החלטה: {name}", ok, f"קיבלתי {d['mode']}/{d['claim']}/{d['at']}/{got_rd}")

    d = dec(own_at=a1, req=R2)
    check("החלטה: המהדורה של הלחיצה המאוחרת", d["edition"] == "close", d["edition"])
    d = dec(own_at=a1, own_edition="bogus")
    check("החלטה: מהדורה לא מוכרת → לפי השעה", d["edition"] == "", d["edition"])
    d = dec(own_at=a1, req=R1, redispatch_of="9")
    check("החלטה: שיגור חוזר אינו הלחיצה המקורית", d["original"] is False)
    d = dec(own_at=a1, req=R1)
    check("החלטה: לחיצה מהאתר היא המקורית", d["original"] is True)

    # רענון העמודים
    pf = bc.pages_for
    check("עמודים: לחיצה", pf("click", "workflow_dispatch", ""))
    check("עמודים: לחיצה מהתור", pf("click", "schedule", "kv"))
    check("עמודים: שיגור ידני", pf("own", "workflow_dispatch", ""))
    check("עמודים: לא בתזמון", not pf("own", "schedule", ""))
    check("עמודים: לא בטריגר", not pf("own", "push", ""))
    check("עמודים: לא ברשת ביטחון", not pf("due", "workflow_dispatch", ""))

    # pending עצמו
    check("ממתינה: בלי done", kv.pending(R1, None, now)[0])
    check("לא ממתינה: at שווה ל-done", kv.pending(R1, D1, now) == (False, "done"))
    check("לא ממתינה: ישנה", kv.pending({"at": old}, None, now) == (False, "stale"))
    check("לא ממתינה: בלי at", kv.pending({"edition": ""}, None, now) == (False, "bad"))
    check("זמן: Z ואלפיות", kv.parse_at("2026-11-12T22:36:54.123Z") is not None)


# --- 2. brief_args --------------------------------------------------------------
def args_table() -> None:
    def run(env: dict) -> dict:
        full = {k: v for k, v in os.environ.items()
                if not k.startswith(("IN_", "CLAIM_", "GITHUB_EVENT_NAME"))}
        full.update(env)
        p = subprocess.run([sys.executable, str(HERE / "brief_args.py")], env=full,
                           capture_output=True, text=True, encoding="utf-8")
        return dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)

    X, Y = "2026-11-12T22:36:54.123Z", "2026-11-12T22:50:00.000Z"
    r = run({"GITHUB_EVENT_NAME": "workflow_dispatch", "IN_REQUESTED_AT": X, "CLAIM_MODE": "click",
             "CLAIM_EDITION": "night", "CLAIM_REQUESTED_AT": Y})
    check("פרמטרים: לחיצה שנתבעה", (r.get("BRIEF_FORCE_IN"), r.get("BRIEF_EDITION_IN"),
                                      r.get("BRIEF_REQUESTED_AT_IN")) == ("1", "night", Y), str(r))
    r = run({"GITHUB_EVENT_NAME": "workflow_dispatch", "IN_REQUESTED_AT": X, "IN_SOFT": "50",
             "IN_HARD": "60", "IN_EDITION": "close", "CLAIM_MODE": "due"})
    check("פרמטרים: רשת ביטחון — בלי כפייה ובלי עקיפת בלם",
          (r.get("BRIEF_FORCE_IN"), r.get("BRIEF_EDITION_IN"), r.get("BRIEF_REQUESTED_AT_IN"),
           r.get("BRIEF_SOFT_USD"), r.get("BRIEF_HARD_USD")) == ("", "", "", "", ""), str(r))
    r = run({"GITHUB_EVENT_NAME": "workflow_dispatch", "IN_REQUESTED_AT": X, "CLAIM_MODE": ""})
    check("פרמטרים: claim נכשל → כמו קודם", (r.get("BRIEF_FORCE_IN"),
                                              r.get("BRIEF_REQUESTED_AT_IN")) == ("1", X), str(r))
    r = run({"GITHUB_EVENT_NAME": "workflow_dispatch", "IN_SOFT": "50", "CLAIM_MODE": "own"})
    check("פרמטרים: שיגור ידני שומר על עקיפת הבלם", (r.get("BRIEF_FORCE_IN"),
                                                      r.get("BRIEF_SOFT_USD")) == ("1", "50"), str(r))
    r = run({"GITHUB_EVENT_NAME": "schedule", "CLAIM_MODE": "own"})
    check("פרמטרים: תזמון", (r.get("BRIEF_FORCE_IN"), r.get("BRIEF_REQUESTED_AT_IN")) == ("", ""), str(r))
    r = run({"GITHUB_EVENT_NAME": "schedule", "IN_SOURCE": "kv", "IN_REQUESTED_AT": X,
             "CLAIM_MODE": "click", "CLAIM_EDITION": "", "CLAIM_REQUESTED_AT": X})
    check("פרמטרים: קריאה מהתור", (r.get("BRIEF_FORCE_IN"), r.get("BRIEF_REQUESTED_AT_IN"),
                                    r.get("BRIEF_SOFT_USD")) == ("1", X, ""), str(r))


# --- 3. קלט ופלט, מול KV ו-GitHub מדומים -----------------------------------------
class FakeKV:
    """ה-REST של Cloudflare KV, בזיכרון: אותם נתיבים ש-kv_request.call שולח."""

    def __init__(self, req=None, done=None, fail_put=False, fail_get=False):
        self.store = {k: json.dumps(v) for k, v in (("brief:request", req), ("brief:request:done", done)) if v}
        self.fail_put, self.fail_get, self.calls = fail_put, fail_get, []

    def call(self, path, method="GET", body=None):
        self.calls.append((method, path))
        if path.startswith("/storage/kv/namespaces?"):
            return 200, json.dumps({"result": [{"id": "NS1", "title": kv.NS_TITLE}]})
        key = unquote(path.split("/values/", 1)[1].split("?", 1)[0])
        if method == "GET":
            if self.fail_get:
                return 500, "err"
            return (200, self.store[key]) if key in self.store else (404, "{}")
        if method == "PUT":
            if self.fail_put:
                return 403, "denied"
            self.store[key] = body
            return 200, "{}"
        self.store.pop(key, None)
        return 200, "{}"


class FakeGH:
    """ה-API של GitHub, בזיכרון: רשימת הריצות, קובץ הטריגר בקומיט, ג'ובים, ושיגור."""

    def __init__(self, runs=(), files=None, jobs=None, fail_list=False):
        self.runs, self.calls = list(runs), []
        self.files = files or {}                  # sha → תוכן קובץ הטריגר
        self.jobs = jobs or {}                    # מספר ריצה (str) → ג'ובים
        self.fail_list = fail_list

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "POST":
            return 204, ""
        if "/actions/workflows/" in path:
            return (500, "err") if self.fail_list else (200, json.dumps({"workflow_runs": self.runs}))
        if "/contents/" in path:
            sha = path.split("ref=", 1)[1]
            if sha not in self.files:
                return 404, "{}"
            raw = json.dumps(self.files[sha], ensure_ascii=False).encode("utf-8")
            return 200, json.dumps({"content": base64.b64encode(raw).decode("ascii")})
        if "/jobs" in path:
            return 200, json.dumps({"jobs": self.jobs.get(path.split("/runs/", 1)[1].split("/", 1)[0], [])})
        return 404, "{}"


def run_io(fn, env: dict, fkv: FakeKV, fgh: FakeGH | None = None) -> tuple[dict, str]:
    """מריץ main() עם סביבה של GitHub Actions, ומחזיר (GITHUB_OUTPUT, הלוג)."""
    with tempfile.TemporaryDirectory() as tmp:
        outp = Path(tmp) / "out"
        outp.write_text("", encoding="utf-8")
        saved = dict(os.environ)
        for k in [k for k in os.environ if k.startswith(("IN_", "KV_SEED", "GITHUB_EVENT_NAME"))]:
            del os.environ[k]
        os.environ.update({"CF_API_TOKEN": "x", "CF_ACCOUNT_ID": "acct", "GH_TOKEN": "g",
                           "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "777",
                           "GITHUB_OUTPUT": str(outp)}, **env)
        real_call, real_gh = kv.call, bc.gh
        kv.call, bc.gh = fkv.call, (fgh or FakeGH())
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                fn()
        finally:
            kv.call, bc.gh = real_call, real_gh
            os.environ.clear()
            os.environ.update(saved)
        res = dict(x.split("=", 1) for x in outp.read_text(encoding="utf-8").splitlines() if "=" in x)
    return res, buf.getvalue()


def io_table() -> None:
    A = iso(datetime.now(timezone.utc) - timedelta(minutes=20))
    R = {"edition": "night", "at": A, "by": "owner@example.com"}
    click = {"GITHUB_EVENT_NAME": "workflow_dispatch", "IN_REQUESTED_AT": A, "IN_EDITION": "night"}

    fkv, fgh = FakeKV(req=R), FakeGH([{"id": 777, "status": "in_progress"}, {"id": 5, "status": "completed"}])
    res, log = run_io(bc.main, {"GITHUB_EVENT_NAME": "schedule"}, fkv, fgh)
    post = [c for c in fgh.calls if c[0] == "POST"]
    check("קלט/פלט: תזמון משגר מחדש את הלחיצה, עם אותם inputs",
          res.get("mode") == "own" and res.get("pages") == "false" and len(post) == 1
          and post[0][1] == "/repos/o/r/actions/workflows/daily-brief.yml/dispatches"
          and post[0][2] == {"ref": "main", "inputs": {"edition": "night", "reviews": "", "requested_at": A,
                                                        "redispatch_of": "777"}}
          and "brief:request:done" not in fkv.store, str((res, fgh.calls)))
    fgh = FakeGH([{"id": 777, "status": "in_progress"}, {"id": 900, "status": "pending"}])
    res, log = run_io(bc.main, {"GITHUB_EVENT_NAME": "schedule"}, FakeKV(req=R), fgh)
    check("קלט/פלט: ריצה ממתינה → בלי שיגור", not [c for c in fgh.calls if c[0] == "POST"] and "900" in log, log)

    fkv = FakeKV(req=R)
    res, log = run_io(bc.main, click, fkv)
    done = json.loads(fkv.store.get("brief:request:done", "{}"))
    check("קלט/פלט: לחיצה נתבעת — done ליממה, הבקשה נשארת",
          (res.get("mode"), res.get("edition"), res.get("requested_at"), res.get("pages")) == ("click", "night", A, "true")
          and done.get("at") == A and done.get("run") == "777" and "brief:request" in fkv.store
          and ("PUT", "/storage/kv/namespaces/NS1/values/brief%3Arequest%3Adone?expiration_ttl=86400") in fkv.calls
          and not [c for c in fkv.calls if c[0] == "DELETE"], str((res, fkv.calls)))
    res, log = run_io(bc.main, click, fkv)
    check("קלט/פלט: אותה לחיצה שוב → רשת ביטחון", (res.get("mode"), res.get("pages")) == ("due", "false"), str(res))

    res, log = run_io(bc.main, {**click, "IN_REDISPATCH_OF": "5"}, FakeKV(req=R, fail_put=True))
    check("קלט/פלט: שיגור חוזר שלא סומן → לא מבוצע", res.get("mode") == "due" and "::error" in log, log)
    res, log = run_io(bc.main, click, FakeKV(req=R, fail_put=True))
    check("קלט/פלט: הלחיצה המקורית שלא סומנה → מבוצעת", res.get("mode") == "click" and "::warning" in log, log)
    res, _ = run_io(bc.main, {**click, "IN_EDITION": "close"}, FakeKV(req=R, fail_get=True))
    check("קלט/פלט: KV לא נקרא → לפי ה-inputs", (res.get("mode"), res.get("edition")) == ("click", "close"), str(res))
    res, _ = run_io(bc.main, {**click, "CF_API_TOKEN": ""}, FakeKV())
    check("קלט/פלט: בלי סודות Cloudflare → לפי ה-inputs", res.get("mode") == "click", str(res))

    class Boom:
        @staticmethod
        def call(*_a, **_k):
            raise RuntimeError("x")
    res, log = run_io(bc.main, click, Boom())   # type: ignore[arg-type]
    check("קלט/פלט: חריגה → mode ריק, והריצה ממשיכה", res.get("mode") == "" and "::error" in log, log)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bc.annotate("notice", "a:b,c", "x:y,z\nw")
    check("קלט/פלט: בריחה בכותרת האנוטציה", buf.getvalue().strip() == "::notice title=a%3Ab%2Cc::x:y,z%0Aw")

    # הפעימה של brief-request.yml: מציצה ואינה מוחקת; הבדיקה העצמית — במפתח שלה בלבד
    fkv = FakeKV(req=R)
    res, _ = run_io(kv.main, {}, fkv)
    check("קלט/פלט: הפעימה מוצאת את הלחיצה ואינה מוחקת",
          (res.get("run"), res.get("edition"), res.get("at")) == ("true", "night", A)
          and "brief:request" in fkv.store and not [c for c in fkv.calls if c[0] == "DELETE"], str(res))
    res, _ = run_io(kv.main, {}, FakeKV(req=R, done={"at": A}))
    check("קלט/פלט: הפעימה מדלגת על לחיצה שבוצעה", res.get("run") == "false", str(res))
    fkv = FakeKV(req=R)
    res, log = run_io(kv.main, {"KV_SEED": "midday"}, fkv)
    keys = {c[1].split("/values/")[1].split("?")[0] for c in fkv.calls if "/values/" in c[1]}
    check("קלט/פלט: הבדיקה העצמית אינה נוגעת בלחיצה אמיתית",
          keys == {"brief%3Arequest%3Aselftest"} and json.loads(fkv.store["brief:request"]) == R
          and res.get("run") == "false" and "::notice" in log, str((keys, log)))


# --- 4. טריגרים מפורשים ------------------------------------------------------------
def sha_n(n: int) -> str:
    return f"{n:040x}"


def local_ago(minutes: float) -> str:
    """שדה at בקובץ טריגר: שעון מקומי בלי אזור זמן, כמו שהסשנים ו-ensure_editions כותבים."""
    return (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def trigger_table() -> None:
    now = BASE + timedelta(hours=5)

    def v(i, n, via, kind, state, ago):
        return {"id": i, "sha": sha_n(n), "via": via, "kind": kind, "state": state,
                "created": now - timedelta(minutes=ago), "title": f"טריגר {n}"}

    P, R = "push", "redispatch"
    cases = [
        # (שם, view, own (sha, push), execute צפוי, sha צפוי לשיגור חוזר)
        ("ריק", [], (0, False), None, None),
        ("ברייף כפוי שבוטל בתור → שיגור חוזר", [v(1, 1, P, "full", "dropped", 30)], (0, False), None, 1),
        ("ברייף כפוי שרץ → כלום", [v(1, 1, P, "full", "executed", 30)], (0, False), None, None),
        ("ברייף כפוי שממתין בתור → כלום", [v(1, 1, P, "full", "active", 30)], (0, False), None, None),
        ("בן יותר משעתיים → כלום", [v(1, 1, P, "full", "dropped", 130)], (0, False), None, None),
        ("כפוי שבוטל, כפוי חדש יותר רץ → הוחלף",
         [v(1, 1, P, "full", "dropped", 40), v(2, 2, P, "full", "executed", 30)], (0, False), None, None),
        ("כפוי שבוטל, סקטורים חדש יותר רץ → הכפוי עדיין משוחזר",
         [v(1, 1, P, "full", "dropped", 40), v(2, 2, P, "topics", "executed", 30)], (0, False), None, 1),
        ("סקטורים שבוטל, כפוי חדש יותר רץ → הוחלף",
         [v(1, 1, P, "topics", "dropped", 40), v(2, 2, P, "full", "executed", 30)], (0, False), None, None),
        ("שני סקטורים שבוטלו → רק החדש",
         [v(1, 1, P, "topics", "dropped", 40), v(2, 2, P, "topics", "dropped", 30)], (0, False), None, 2),
        ("כפוי וסקטורים חדש יותר, שניהם בוטלו → הוותיק קודם",
         [v(1, 1, P, "full", "dropped", 40), v(2, 2, P, "topics", "dropped", 30)], (0, False), None, 1),
        ("שיגור חוזר שביצע → כלום",
         [v(1, 1, P, "full", "dropped", 40), v(5, 1, R, "full", "executed", 20)], (0, False), None, None),
        ("שיגור חוזר שלא ביצע → שוב",
         [v(1, 1, P, "full", "dropped", 40), v(5, 1, R, "full", "dropped", 20)], (0, False), None, 1),
        ("שיגור חוזר: לבצע",
         [v(1, 1, P, "full", "dropped", 40), v(999, 1, R, "full", "active", 1)], (1, False), True, None),
        ("שיגור חוזר: שיגור אחר כבר ביצע",
         [v(1, 1, P, "full", "dropped", 40), v(5, 1, R, "full", "executed", 20),
          v(999, 1, R, "full", "active", 1)], (1, False), False, None),
        ("שיגור חוזר: שיגור קודם לא ביצע → לבצע",
         [v(1, 1, P, "full", "dropped", 40), v(5, 1, R, "full", "dropped", 20),
          v(999, 1, R, "full", "active", 1)], (1, False), True, None),
        ("שיגור חוזר: הדחיפה המקורית עוד בתור → לא",
         [v(1, 1, P, "full", "active", 40), v(999, 1, R, "full", "active", 1)], (1, False), False, None),
        ("שיגור חוזר: הוחלף בכפוי חדש יותר",
         [v(1, 1, P, "full", "dropped", 40), v(2, 2, P, "full", "active", 10),
          v(999, 1, R, "full", "active", 1)], (1, False), False, None),
        ("שיגור חוזר: ישן מדי",
         [v(1, 1, P, "full", "dropped", 130), v(999, 1, R, "full", "active", 1)], (1, False), False, None),
        ("ריצת push כפויה: לא משגרת את עצמה, ומחליפה כפוי ישן",
         [v(1, 1, P, "full", "dropped", 40), v(999, 2, P, "full", "active", 1)], (2, True), None, None),
        ("ריצת push של סקטורים: כפוי ישן שבוטל עדיין משוחזר",
         [v(1, 1, P, "full", "dropped", 40), v(999, 2, P, "topics", "active", 1)], (2, True), None, 1),
    ]
    for name, view, (own, push), execute, rd in cases:
        p = bc.trigger_plan(own_sha=sha_n(own) if own else "", own_push=push, run_id="999",
                            view=view, now=now)
        got_rd = (p["redispatch"] or {}).get("sha")
        ok = p["execute"] == execute and got_rd == (sha_n(rd) if rd else None)
        check(f"טריגר: {name}", ok, f"execute={p['execute']} redispatch={got_rd} why={p['why']}")


def view_table() -> None:
    now = datetime.now(timezone.utc)

    def ago(minutes):
        return iso(now - timedelta(minutes=minutes))

    files = {sha_n(1): {"edition": "close", "hard_usd": "40", "at": local_ago(30)},    # כפוי
             sha_n(2): {"if_missing": True, "at": local_ago(20)},                       # רשת ביטחון
             sha_n(3): {"topics_only": 1, "at": local_ago(15)},                         # סקטורים
             sha_n(4): {"topics_only": 1, "at": local_ago(400)}}                        # דגל ישן → כפוי
    runs = [
        {"id": 11, "event": "push", "head_sha": sha_n(1), "status": "completed", "conclusion": "cancelled",
         "created_at": ago(30), "display_title": "טריגר: עקיפת בלם"},
        {"id": 12, "event": "push", "head_sha": sha_n(2), "status": "completed", "conclusion": "success",
         "created_at": ago(20)},
        {"id": 13, "event": "push", "head_sha": sha_n(3), "status": "completed", "conclusion": "cancelled",
         "created_at": ago(15)},
        {"id": 14, "event": "push", "head_sha": sha_n(4), "status": "completed", "conclusion": "success",
         "created_at": ago(10)},
        {"id": 15, "event": "workflow_dispatch", "display_title": bc.TRIGGER_TITLE + sha_n(3),
         "status": "completed", "conclusion": "success", "created_at": ago(5)},
        {"id": 16, "event": "schedule", "status": "completed", "conclusion": "success", "created_at": ago(3)},
        {"id": 17, "event": "push", "head_sha": sha_n(9), "status": "completed", "conclusion": "cancelled",
         "created_at": ago(300)},
        {"id": 18, "event": "push", "head_sha": sha_n(8), "status": "completed", "conclusion": "cancelled",
         "created_at": ago(8)},
    ]
    jobs = {"11": [], "13": [], "18": [],
            "15": [{"steps": [{"name": bc.RESTORE_STEP, "conclusion": "success"}]}]}
    view = bc.build_view(runs, now, files.get, lambda rid: jobs.get(str(rid)))
    by = {r["id"]: r for r in view}
    check("תצוגה: רק טריגרים מפורשים, בחלון, עם תוכן קריא", set(by) == {11, 13, 14, 15}, str(sorted(by)))
    check("תצוגה: כפוי שבוטל בלי ג'ובים → dropped",
          by.get(11, {}).get("kind") == "full" and by[11]["state"] == "dropped" and by[11]["title"] == "טריגר: עקיפת בלם")
    check("תצוגה: סקטורים", by.get(13, {}).get("kind") == "topics" and by[13]["state"] == "dropped")
    check("תצוגה: topics_only ישן בדחיפה → ברייף כפוי, כמו ב-brief_args", by.get(14, {}).get("kind") == "full")
    check("תצוגה: שיגור חוזר שעבר את שלב השחזור → executed",
          by.get(15, {}).get("via") == "redispatch" and by[15]["sha"] == sha_n(3) and by[15]["state"] == "executed")
    check("תצוגה: ג'ובים שלא נקראו → executed (לא משחזרים בספק)",
          bc.build_view(runs[:1], now, files.get, lambda rid: None)[0]["state"] == "executed")
    skipped = {"15": [{"steps": [{"name": bc.RESTORE_STEP, "conclusion": "skipped"}]}]}
    check("תצוגה: שיגור חוזר שדילג על השחזור → dropped",
          bc.build_view(runs[2:5], now, files.get, lambda rid: skipped.get(str(rid), []))[-1]["state"] == "dropped")


def trigger_io() -> None:
    now = datetime.now(timezone.utc)

    def ago(minutes):
        return iso(now - timedelta(minutes=minutes))

    F = sha_n(1)
    files = {F: {"edition": "close", "hard_usd": "40", "at": local_ago(30)}}
    pushed = {"id": 11, "event": "push", "head_sha": F, "status": "completed", "conclusion": "cancelled",
              "created_at": ago(30), "display_title": "טריגר: עקיפת בלם"}
    me_sched = {"id": 777, "event": "schedule", "status": "in_progress", "created_at": ago(1)}
    me_redo = {"id": 777, "event": "workflow_dispatch", "status": "in_progress", "created_at": ago(1),
               "display_title": bc.TRIGGER_TITLE + F}
    redo_env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "IN_TRIGGER_SHA": F, "IN_REDISPATCH_OF": "5"}
    dispatches = "/repos/o/r/actions/workflows/daily-brief.yml/dispatches"

    fgh = FakeGH([pushed, me_sched], files, {"11": []})
    res, log = run_io(bc.main, {"GITHUB_EVENT_NAME": "schedule"}, FakeKV(), fgh)
    post = [c for c in fgh.calls if c[0] == "POST"]
    check("קלט/פלט טריגר: תזמון משגר מחדש טריגר שבוטל",
          post == [("POST", dispatches, {"ref": "main", "inputs": {"trigger_sha": F, "redispatch_of": "777"}})]
          and res.get("mode") == "own" and "טריגר שוגר מחדש" in log, str((post, log)))

    res, log = run_io(bc.main, redo_env, FakeKV(), FakeGH([pushed, me_redo], files, {"11": []}))
    got = kv.parse_at(res.get("trigger_pushed"))
    check("קלט/פלט טריגר: השיגור החוזר מבצע — בלי רענון עמודים",
          (res.get("mode"), res.get("trigger_sha"), res.get("pages")) == ("trigger", F, "false")
          and got is not None and abs((got - kv.parse_at(pushed["created_at"])).total_seconds()) < 1,
          str((res, log)))

    done_redo = {"id": 500, "event": "workflow_dispatch", "status": "completed", "conclusion": "success",
                 "created_at": ago(10), "display_title": bc.TRIGGER_TITLE + F}
    res, log = run_io(bc.main, redo_env, FakeKV(),
                      FakeGH([pushed, done_redo, me_redo], files,
                             {"11": [], "500": [{"steps": [{"name": bc.RESTORE_STEP, "conclusion": "success"}]}]}))
    check("קלט/פלט טריגר: שיגור חוזר שכבר בוצע → רשת ביטחון", res.get("mode") == "due" and "500" in log, log)

    A = iso(now - timedelta(minutes=5))
    fgh = FakeGH([pushed, me_sched], files, {"11": []})
    res, log = run_io(bc.main, {"GITHUB_EVENT_NAME": "schedule"}, FakeKV(req={"edition": "", "at": A}), fgh)
    post = [c for c in fgh.calls if c[0] == "POST"]
    check("קלט/פלט טריגר: לחיצה וטריגר ממתינים → שיגור אחד, ללחיצה",
          len(post) == 1 and post[0][2]["inputs"].get("requested_at") == A and "טריגר ממתין" in log, str(post))

    fgh = FakeGH([pushed, me_sched, {"id": 901, "status": "pending", "created_at": ago(0)}], files, {"11": []})
    run_io(bc.main, {"GITHUB_EVENT_NAME": "schedule"}, FakeKV(), fgh)
    check("קלט/פלט טריגר: ריצה ממתינה → בלי שיגור", not [c for c in fgh.calls if c[0] == "POST"])

    res, _ = run_io(bc.main, {**redo_env, "IN_TRIGGER_SHA": "abc"}, FakeKV(), FakeGH([pushed], files, {"11": []}))
    check("קלט/פלט טריגר: trigger_sha לא תקין → רשת ביטחון", res.get("mode") == "due", str(res))
    res, _ = run_io(bc.main, redo_env, FakeKV(), FakeGH(fail_list=True))
    check("קלט/פלט טריגר: רשימת הריצות לא נקראה → לא מבצעים", res.get("mode") == "due", str(res))
    res, _ = run_io(bc.main, {**redo_env, "IN_REQUESTED_AT": A}, FakeKV(req={"edition": "", "at": A}),
                    FakeGH([pushed, me_redo], files, {"11": []}))
    check("קלט/פלט טריגר: requested_at בשיגור של טריגר אינו הופך אותו ללחיצה",
          res.get("mode") == "trigger" and res.get("requested_at") == "", str(res))


def trigger_args() -> None:
    def run(env: dict) -> dict:
        full = {k: v for k, v in os.environ.items()
                if not k.startswith(("IN_", "CLAIM_", "GITHUB_EVENT_NAME", "BRIEF_TRIGGER_FILE"))}
        full.update(env)
        p = subprocess.run([sys.executable, str(HERE / "brief_args.py")], env=full,
                           capture_output=True, text=True, encoding="utf-8")
        return dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "daily-brief.json"
        at = datetime.now() - timedelta(minutes=150)          # שעתיים וחצי לפני עכשיו
        f.write_text(json.dumps({"edition": "close", "hard_usd": "40", "topics_only": 1,
                                 "at": at.isoformat(timespec="seconds")}), encoding="utf-8")
        pushed = (at + timedelta(minutes=30)).astimezone(timezone.utc).isoformat()
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "BRIEF_TRIGGER_FILE": str(f),
               "CLAIM_MODE": "trigger", "CLAIM_TRIGGER_SHA": sha_n(1), "CLAIM_TRIGGER_PUSHED": pushed,
               "IN_EDITION": "morning", "IN_SOFT": "99"}
        r = run(env)
        check("פרמטרים: טריגר משוחזר — מהקובץ, לא מה-inputs של השיגור",
              (r.get("BRIEF_FORCE_IN"), r.get("BRIEF_EDITION_IN"), r.get("BRIEF_HARD_USD"),
               r.get("BRIEF_SOFT_USD"), r.get("BRIEF_REQUESTED_AT_IN")) == ("1", "close", "40", "", ""), str(r))
        check("פרמטרים: topics_only נמדד מול שעת הדחיפה", r.get("BRIEF_TOPICS_ONLY") == "1", str(r))
        r = run({k: v for k, v in env.items() if k != "CLAIM_TRIGGER_PUSHED"})
        check("פרמטרים: ובלי שעת הדחיפה הוא היה פג", r.get("BRIEF_TOPICS_ONLY") == "", str(r))


def consistency() -> None:
    wf = (HERE.parent / ".github" / "workflows" / "daily-brief.yml").read_text(encoding="utf-8")
    check("עקביות: ה-run-name של שיגור חוזר הוא TRIGGER_TITLE", f"format('{bc.TRIGGER_TITLE}{{0}}'" in wf)
    check("עקביות: שם שלב השחזור הוא RESTORE_STEP", f"- name: {bc.RESTORE_STEP}\n" in wf)
    claim_job = re.search(r"\n  claim:\n(.*?)\n  brief:\n", wf, re.S)
    check("עקביות: ג'וב claim מושך את שלושת הסקריפטים",
          bool(claim_job) and all(f"scripts/{s}" in claim_job.group(1)
                                  for s in ("kv_request.py", "brief_claim.py", "brief_args.py")))
    doc = yaml.safe_load(wf)
    inputs = set(((doc.get(True) or doc.get("on"))["workflow_dispatch"]["inputs"]))
    check("עקביות: כל ה-inputs ששיגור חוזר שולח מוגדרים",
          {"edition", "reviews", "requested_at", "redispatch_of", "trigger_sha"} <= inputs, str(inputs))


# --- 5. סימולציה של התור ---------------------------------------------------------
EVENT = {"schedule": "schedule", "push": "push", "explicit": "push", "manual": "workflow_dispatch",
         "click": "workflow_dispatch", "redispatch": "workflow_dispatch", "drainer": "schedule",
         "trig": "push", "redispatch_t": "workflow_dispatch"}


class Run:
    _ids = itertools.count(1)

    def __init__(self, kind: str, edition: str = "", at: str = "", source: str = "",
                 redispatch_of: str = "", dur: float | None = None, trig: dict | None = None,
                 trig_sha: str = ""):
        self.id = next(Run._ids)
        self.kind, self.edition, self.at = kind, edition, at
        self.source, self.redispatch_of, self.dur = source, redispatch_of, dur
        self.trig = trig              # ריצת push של קובץ הטריגר: {"sha", "kind"}
        self.trig_sha = trig_sha      # שיגור חוזר של טריגר
        self.mode = None
        self.created: float = 0.0
        self.started: float | None = None
        self.finished = False
        self.executed = False         # שיגור חוזר שעבר את שלב השחזור
        self.rerun = False            # Re-run ידני של ריצה שבוטלה
        self.cancelled_by: Run | None = None


def decide_old(*, event, source, own_edition, own_at, **_):
    """הלוגיקה של לפני 13/11: בלי KV בשיגור הישיר, בלי שיגור חוזר."""
    claimer = bool(source) or (event == "workflow_dispatch" and bool(own_at))
    return {"mode": "click" if claimer else "own", "edition": own_edition, "at": own_at if claimer else "",
            "claim": False, "redispatch": None, "notes": []}


def plan_none(**_):
    """הלוגיקה של לפני השחזור: אף טריגר אינו משוחזר."""
    return {"execute": None, "why": "", "pushed": None, "title": "", "redispatch": None}


class Sim:
    def __init__(self, rng: random.Random | None = None, decide=bc.decide, plan=bc.trigger_plan):
        self.rng = rng or random.Random(0)
        self.decide, self.plan = decide, plan
        self.t = 0.0
        self.q: list = []
        self.seq = itertools.count()
        self.shas = itertools.count(1)
        self.req: dict | None = None
        self.done: dict | None = None
        self.running: Run | None = None
        self.pending: Run | None = None
        self.runs: list[Run] = []
        self.clicks: list[tuple[float, str]] = []
        self.fulfilled: list[tuple[Run, str]] = []
        self.triggers: dict[str, dict] = {}                 # sha → kind, pushed
        self.executions: list[tuple[Run, str, float]] = []  # (ריצה, sha, מתי)
        self.violations: list[str] = []

    def iso(self, t: float) -> str:
        return iso(BASE + timedelta(minutes=t))

    def at(self, t: float, fn, *args) -> None:
        heapq.heappush(self.q, (t, next(self.seq), fn, args))

    def arrive(self, run: Run) -> None:
        run.created = self.t
        self.runs.append(run)
        if self.running is None:
            self.start(run)
            return
        if self.pending is not None:
            self.pending.cancelled_by = run
            if run.kind in ("redispatch", "redispatch_t"):
                self.violations.append(f"שיגור חוזר {run.id} ביטל את {self.pending.kind} {self.pending.id}")
        self.pending = run

    def rerun(self) -> None:
        """Re-run ידני ב-GitHub של ריצת טריגר שבוטלה בתור: אותה ריצה חוזרת לתור, בלי ריצה חדשה."""
        dropped = [r for r in self.runs if r.kind == "trig" and r.trig["kind"] in bc.KIND_HE
                   and r.started is None and r.cancelled_by is not None]
        if not dropped:
            return
        r = self.rng.choice(dropped)
        r.cancelled_by, r.rerun = None, True
        if self.running is None:
            self.start(r)
            return
        if self.pending is not None:
            self.pending.cancelled_by = r
        self.pending = r

    def push_trigger(self, kind: str, dur: float | None = None) -> str:
        """דחיפה של .trigger/daily-brief.json: full / topics / skip (if_missing)."""
        sha = sha_n(next(self.shas))
        self.triggers[sha] = {"kind": kind, "pushed": self.t}
        self.arrive(Run("trig", trig={"sha": sha, "kind": kind}, dur=dur))
        return sha

    def view(self) -> list[dict]:
        """מה ש-build_view היה מחזיר מה-API ברגע הזה."""
        v = []
        for r in self.runs:
            if r.kind == "trig" and r.trig["kind"] in bc.KIND_HE:
                sha, via = r.trig["sha"], "push"
            elif r.kind == "redispatch_t":
                sha, via = r.trig_sha, "redispatch"
            else:
                continue
            if not r.finished and r.cancelled_by is None:
                state = "active"
            elif r.started is None:
                state = "dropped"
            else:
                state = "executed" if via == "push" or r.executed else "dropped"
            v.append({"id": r.id, "sha": sha, "via": via, "kind": self.triggers[sha]["kind"],
                      "state": state, "created": BASE + timedelta(minutes=r.created), "title": ""})
        return v

    def start(self, run: Run) -> None:
        # ג'וב claim אינו מיידי: עד שהוא קורא את ה-KV עוברות 20–40 שניות, ובהן ריצות
        # אחרות כבר נכנסות לתור. בלי החלון הזה בדיקת "יש ריצה ממתינה" אינה נבדקת כלל.
        self.running, run.started = run, self.t
        self.at(self.t + self.rng.uniform(0.3, 0.7), self.claim, run)

    def claim(self, run: Run) -> None:
        now = BASE + timedelta(minutes=self.t)
        d = self.decide(event=EVENT[run.kind], source=run.source, own_edition=run.edition,
                        own_at=run.at, redispatch_of=run.redispatch_of, req=self.req,
                        done=self.done, kv_ok=True, now=now, max_age_min=10 ** 6)
        run.mode = d["mode"]
        if d["claim"]:
            self.done = {"at": d["at"], "run": str(run.id)}
        if d["mode"] == "click":
            self.fulfilled.append((run, d["at"]))
        own_push = run.kind == "trig"
        tp = self.plan(own_sha=run.trig_sha or (run.trig["sha"] if own_push else ""), own_push=own_push,
                       run_id=str(run.id), view=self.view(), now=now, max_age_min=10 ** 6)
        if run.kind == "redispatch_t":
            run.mode = "trigger" if tp["execute"] else "due"
            if tp["execute"]:
                # המפרט: שיגור חוזר אינו מבצע טריגר שריצה אחרת כבר ביצעה או שממתינה לבצע
                # (למשל Re-run ידני של הדחיפה, שחזר לתור בזמן ג'וב claim).
                if any(o is not run and o.started is None and o.cancelled_by is None and not o.finished
                       or o is not run and (o.kind == "trig" and o.started is not None or o.executed)
                       for o in self.runs
                       if (o.trig or {}).get("sha", o.trig_sha) == run.trig_sha):
                    self.violations.append(f"שיגור חוזר {run.id} ביצע טריגר שכבר טופל")
                run.executed = True
                self.executions.append((run, run.trig_sha, self.t))
        elif own_push and run.trig["kind"] in bc.KIND_HE:
            self.executions.append((run, run.trig["sha"], self.t))   # push מבצעת את שלה תמיד
        # כמו brief_claim.run: שיגור אחד לכל היותר, לחיצה קודם, ורק כשאין ריצה ממתינה.
        if self.pending is None:
            if d["redispatch"]:
                rd = d["redispatch"]
                self.arrive(Run("redispatch", rd["edition"], rd["at"], redispatch_of=str(run.id)))
            elif tp["redispatch"]:
                self.arrive(Run("redispatch_t", trig_sha=tp["redispatch"]["sha"], redispatch_of=str(run.id)))
        if run.dur is not None:                    # משך כולל מתחילת הריצה, כפי שנמדד
            dur = max(run.started + run.dur - self.t, 0.0)
        elif run.mode in ("click", "trigger"):
            dur = self.rng.uniform(5, 50)      # ברייף או רענון סקטורים, ואחריהם פריסה
        elif run.mode == "due":
            dur = self.rng.uniform(2, 4)
        else:
            dur = self.rng.choice([self.rng.uniform(1, 3), self.rng.uniform(15, 30)])
        self.at(self.t + dur, self.finish, run)

    def finish(self, run: Run) -> None:
        assert self.running is run
        self.running, run.finished = None, True
        if self.pending is not None:
            nxt, self.pending = self.pending, None
            self.start(nxt)

    def click(self, edition: str = "", direct: bool = True, lag: float = 0.02) -> str:
        """brief.js: רישום ל-KV, ואז (כשיש אסימון) שיגור."""
        at = self.iso(self.t)
        self.req = {"edition": edition, "at": at, "by": "owner"}
        self.clicks.append((self.t, at))
        if direct:
            self.at(self.t + lag, self.arrive, Run("click", edition, at))
        return at

    def drainer(self, delay: float = 0.5) -> None:
        """brief-request.yml: הצצה, ואם יש לחיצה ממתינה — קריאה לריצה עם source=kv."""
        if kv.pending(self.req, self.done, BASE + timedelta(minutes=self.t), 10 ** 6)[0]:
            self.at(self.t + delay, self.arrive,
                    Run("drainer", kv.edition_of(self.req), self.req["at"], source="kv"))

    def go(self) -> None:
        while self.q:
            self.t, _, fn, args = heapq.heappop(self.q)
            fn(*args)

    def problems(self) -> list[str]:
        out = list(self.violations)
        ats = [a for _, a in self.fulfilled]
        dup = sorted({a for a in ats if ats.count(a) > 1})
        if dup:
            out.append(f"לחיצה בוצעה פעמיים: {dup}")
        for t, a in self.clicks:
            if not any(kv.parse_at(fa) >= kv.parse_at(a) for _, fa in self.fulfilled):
                out.append(f"לחיצה מ-{a} לא בוצעה")

        # טריגרים: אף אחד פעמיים; כל מי שלא הוחלף — בוצע; שיגור חוזר לא ביצע טריגר שהוחלף
        def replaced(sha: str, by_time: float) -> bool:
            me = self.triggers[sha]
            return any(s != sha and o["kind"] in bc.KIND_HE and me["pushed"] < o["pushed"] <= by_time
                       and o["kind"] in (me["kind"], "full") for s, o in self.triggers.items())
        ex = [s for _, s, _ in self.executions]
        # Re-run ידני אחרי שהטריגר כבר בוצע הוא בחירה של הבעלים, לא כפילות של המנגנון
        own = [s for r, s, _ in self.executions if not r.rerun]
        twice = sorted({s[-4:] for s in own if own.count(s) > 1})
        if twice:
            out.append(f"טריגר בוצע פעמיים: {twice}")
        for sha, t in self.triggers.items():
            if t["kind"] in bc.KIND_HE and sha not in ex and not replaced(sha, float("inf")):
                out.append(f"טריגר {t['kind']} {sha[-4:]} לא בוצע ולא הוחלף")
        for i, (r, sha, when_) in enumerate(self.executions):
            if r.kind != "redispatch_t":
                continue
            if replaced(sha, when_):
                out.append(f"שיגור חוזר {r.id} ביצע טריגר שכבר הוחלף")
            if any(s == sha for _, s, _ in self.executions[:i]):
                out.append(f"שיגור חוזר {r.id} ביצע טריגר שכבר בוצע")
        if self.running or self.pending:
            out.append("התור לא התרוקן")
        return out


def m(hhmmss: str) -> float:
    """שעה UTC של 12/11 (או 13/11 אחרי חצות) כדקות מ-BASE."""
    h, mi, s = (int(x) for x in hhmmss.split(":"))
    return (h - 22) * 60 + mi + s / 60 if h >= 22 else (h + 2) * 60 + mi + s / 60


def incident(decide) -> Sim:
    """13/11/2026, לפי הריצות עצמן (GitHub API): 43321033475 → 43324593277 → 43325430772."""
    s = Sim(decide=decide)
    s.at(m("22:33:42"), s.push_trigger, "skip", m("23:00:55") - m("22:33:42"))   # if_missing: הלילה
    at = None

    def press():
        nonlocal at
        at = s.click("")                                                            # 00:36:54
    s.at(m("22:36:54"), press)
    # השיגור הידני של 00:41 (ריצה 43322273635), עם אותה שעת לחיצה
    s.at(m("22:41:49"), lambda: s.arrive(Run("click", "", at)))
    s.at(m("22:57:20"), s.arrive, Run("schedule", dur=m("23:01:54") - m("23:00:55")))  # cron הלילה
    s.go()
    return s


def replay() -> None:
    old = incident(decide_old)
    check("13/11, לוגיקה ישנה: הסימולציה משחזרת את האובדן",
          not old.fulfilled and any(r.kind == "click" and r.cancelled_by and r.cancelled_by.kind == "schedule"
                                    for r in old.runs), [(r.kind, r.mode) for r in old.runs].__str__())
    new = incident(bc.decide)
    runs = [(r.kind, r.mode) for r in new.runs]
    rd = [r for r in new.runs if r.kind == "redispatch"]
    check("13/11, לוגיקה חדשה: הלחיצה בוצעה פעם אחת", not new.problems(), str(new.problems()))
    check("13/11, לוגיקה חדשה: ה-cron שביטל אותה הוא ששיגר אותה מחדש",
          len(rd) == 1 and rd[0].mode == "click" and rd[0].redispatch_of == str(
              next(r.id for r in new.runs if r.kind == "schedule")), str(runs))
    if rd:
        print(f"     השיגור החוזר התחיל {rd[0].started - m('22:36:54'):.0f} דקות אחרי הלחיצה")

    # טריגר מפורש ("תעקוף" — hard_usd) שחיכה אחרי מהדורה, ו-if_missing של רשת הביטחון ביטל אותו
    def trigger_case(plan) -> Sim:
        s = Sim(plan=plan)
        s.at(0, s.arrive, Run("schedule", dur=25))
        s.at(5, s.push_trigger, "full")
        s.at(10, s.push_trigger, "skip", 2)
        s.go()
        return s
    old = trigger_case(plan_none)
    check("טריגר שנדרס, בלי שחזור: הסימולציה משחזרת את האובדן",
          not old.executions and any("לא בוצע ולא הוחלף" in p for p in old.problems()), str(old.problems()))
    new = trigger_case(bc.trigger_plan)
    rt = [r for r in new.runs if r.kind == "redispatch_t"]
    safety = next(r for r in new.runs if r.kind == "trig" and r.trig["kind"] == "skip")
    check("טריגר שנדרס, עם שחזור: בוצע פעם אחת, בשיגור חוזר מהריצה שביטלה אותו",
          not new.problems() and len(rt) == 1 and rt[0].executed and rt[0].redispatch_of == str(safety.id),
          str((new.problems(), [(r.kind, r.mode) for r in new.runs])))

    # ובזמן ג'וב claim של השיגור החוזר, הבעלים עושה Re-run ידני לדחיפה שבוטלה
    s = Sim(plan=bc.trigger_plan)
    s.at(0, s.arrive, Run("schedule", dur=25))
    s.at(5, s.push_trigger, "full")
    s.at(10, s.push_trigger, "skip", 2)
    # ה-if_missing מתחיל ב-25, משגר ב-25.3–25.7 ומסתיים ב-27; השיגור החוזר מתחיל ב-27
    # וג'וב claim שלו מחליט ב-27.3 לפחות — Re-run ב-27.1 נוחת בדיוק בחלון הזה.
    s.at(27.1, s.rerun)
    s.go()
    rt = [r for r in s.runs if r.kind == "redispatch_t"]
    check("Re-run ידני בזמן claim של השיגור החוזר: השיגור מוותר, והטריגר מבוצע פעם אחת",
          not s.problems() and rt and rt[0].mode == "due" and len(s.executions) == 1,
          str((s.problems(), [(r.kind, r.mode, r.started) for r in s.runs])))


def fuzz(days: int = 3000) -> None:
    kinds = ["schedule", "push", "full", "topics", "manual", "click", "click_nt", "double", "drainer",
             "rerun"]
    weights = [5, 3, 1, 1, 1, 4, 1, 1, 2, 1]
    bad: list[tuple[int, list[str]]] = []
    n_clicks = n_trig = n_rd = n_rdt = n_due = 0
    for seed in range(days):
        rng = random.Random(seed)
        s = Sim(rng)
        t = 0.0
        for _ in range(rng.randint(3, 40)):
            t += rng.expovariate(1 / rng.choice([3, 10, 25]))
            k = rng.choices(kinds, weights)[0]
            ed = rng.choice(["", "", "morning", "midday", "close", "night"])
            if k in ("schedule", "manual"):
                s.at(t, s.arrive, Run(k))
            elif k == "push":                           # if_missing של רשת הביטחון
                s.at(t, s.push_trigger, "skip")
            elif k in ("full", "topics"):               # טריגר מפורש
                s.at(t, s.push_trigger, k)
            elif k == "click":
                s.at(t, s.click, ed)
            elif k == "click_nt":                       # האסימון נדחה: רק KV
                s.at(t, s.click, ed, False)
            elif k == "double":                         # שתי לחיצות בהפרש שניות
                s.at(t, s.click, ed)
                s.at(t + rng.uniform(0.01, 0.5), s.click, rng.choice(["", "close"]))
            elif k == "rerun":                          # Re-run ידני של טריגר שבוטל
                s.at(t, s.rerun)
            else:
                s.at(t, s.drainer)
        s.at(t + 60, s.arrive, Run("schedule"))         # ה-cron הבא מגיע מתישהו
        s.go()
        p = s.problems()
        if p:
            bad.append((seed, p))
        n_clicks += len(s.clicks)
        n_trig += sum(t["kind"] in bc.KIND_HE for t in s.triggers.values())
        n_rd += sum(r.kind == "redispatch" for r in s.runs)
        n_rdt += sum(r.kind == "redispatch_t" for r in s.runs)
        n_due += sum(r.mode == "due" for r in s.runs)
    check(f"סימולציה: {days} ימים, {n_clicks} לחיצות ו-{n_trig} טריגרים מפורשים — כל בקשה פעם אחת "
          "(או הוחלפה), שיגור חוזר לא ביטל ריצה", not bad,
          f"{len(bad)} ימים בעייתיים, הראשון: {bad[0] if bad else ''}")
    print(f"     {n_rd} שיגורים חוזרים של לחיצות, {n_rdt} של טריגרים, {n_due} ריצות שהמשיכו כרשת ביטחון")


def main() -> int:
    decision_table()
    args_table()
    io_table()
    trigger_table()
    view_table()
    trigger_io()
    trigger_args()
    consistency()
    replay()
    fuzz()
    print(f"\n{'נכשלו ' + str(len(FAILS)) if FAILS else 'הכל עבר'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
