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

import contextlib
import heapq
import io
import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

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
    def __init__(self, runs=()):
        self.runs, self.calls = list(runs), []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        return (200, json.dumps({"workflow_runs": self.runs})) if method == "GET" else (204, "")


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


# --- 4. סימולציה של התור ---------------------------------------------------------
EVENT = {"schedule": "schedule", "push": "push", "explicit": "push", "manual": "workflow_dispatch",
         "click": "workflow_dispatch", "redispatch": "workflow_dispatch", "drainer": "schedule"}


class Run:
    _ids = itertools.count(1)

    def __init__(self, kind: str, edition: str = "", at: str = "", source: str = "",
                 redispatch_of: str = "", dur: float | None = None):
        self.id = next(Run._ids)
        self.kind, self.edition, self.at = kind, edition, at
        self.source, self.redispatch_of, self.dur = source, redispatch_of, dur
        self.mode = None
        self.started: float | None = None
        self.cancelled_by: Run | None = None


def decide_old(*, event, source, own_edition, own_at, **_):
    """הלוגיקה של לפני 13/11: בלי KV בשיגור הישיר, בלי שיגור חוזר."""
    claimer = bool(source) or (event == "workflow_dispatch" and bool(own_at))
    return {"mode": "click" if claimer else "own", "edition": own_edition, "at": own_at if claimer else "",
            "claim": False, "redispatch": None, "notes": []}


class Sim:
    def __init__(self, rng: random.Random | None = None, decide=bc.decide):
        self.rng = rng or random.Random(0)
        self.decide = decide
        self.t = 0.0
        self.q: list = []
        self.seq = itertools.count()
        self.req: dict | None = None
        self.done: dict | None = None
        self.running: Run | None = None
        self.pending: Run | None = None
        self.runs: list[Run] = []
        self.clicks: list[tuple[float, str]] = []
        self.fulfilled: list[tuple[Run, str]] = []
        self.violations: list[str] = []

    def iso(self, t: float) -> str:
        return iso(BASE + timedelta(minutes=t))

    def at(self, t: float, fn, *args) -> None:
        heapq.heappush(self.q, (t, next(self.seq), fn, args))

    def arrive(self, run: Run) -> None:
        self.runs.append(run)
        if self.running is None:
            self.start(run)
            return
        if self.pending is not None:
            self.pending.cancelled_by = run
            if run.kind == "redispatch":
                self.violations.append(f"שיגור חוזר {run.id} ביטל את {self.pending.kind} {self.pending.id}")
        self.pending = run

    def start(self, run: Run) -> None:
        # ג'וב claim אינו מיידי: עד שהוא קורא את ה-KV עוברות 20–40 שניות, ובהן ריצות
        # אחרות כבר נכנסות לתור. בלי החלון הזה בדיקת "יש ריצה ממתינה" אינה נבדקת כלל.
        self.running, run.started = run, self.t
        self.at(self.t + self.rng.uniform(0.3, 0.7), self.claim, run)

    def claim(self, run: Run) -> None:
        d = self.decide(event=EVENT[run.kind], source=run.source, own_edition=run.edition,
                        own_at=run.at, redispatch_of=run.redispatch_of, req=self.req,
                        done=self.done, kv_ok=True, now=BASE + timedelta(minutes=self.t),
                        max_age_min=10 ** 6)
        run.mode = d["mode"]
        if d["claim"]:
            self.done = {"at": d["at"], "run": str(run.id)}
        if d["mode"] == "click":
            self.fulfilled.append((run, d["at"]))
        # כמו brief_claim.redispatch: רק כשאין ריצה ממתינה. השיגור מיידי בסימולציה.
        if d["redispatch"] and self.pending is None:
            rd = d["redispatch"]
            self.arrive(Run("redispatch", rd["edition"], rd["at"], redispatch_of=str(run.id)))
        if run.dur is not None:                    # משך כולל מתחילת הריצה, כפי שנמדד
            dur = max(run.started + run.dur - self.t, 0.0)
        elif run.mode == "click":
            dur = self.rng.uniform(15, 50)     # ברייף, ואחריו final-deploy
        elif run.mode == "due":
            dur = self.rng.uniform(2, 4)
        else:
            dur = self.rng.choice([self.rng.uniform(1, 3), self.rng.uniform(15, 30)])
        self.at(self.t + dur, self.finish, run)

    def finish(self, run: Run) -> None:
        assert self.running is run
        self.running = None
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
    s.at(m("22:33:42"), s.arrive, Run("push", dur=m("23:00:55") - m("22:33:42")))   # מהדורת הלילה
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


def fuzz(days: int = 3000) -> None:
    kinds = ["schedule", "push", "explicit", "manual", "click", "click_nt", "double", "drainer"]
    weights = [5, 3, 1, 1, 4, 1, 1, 2]
    bad: list[tuple[int, list[str]]] = []
    n_clicks = n_rd = n_due = 0
    for seed in range(days):
        rng = random.Random(seed)
        s = Sim(rng)
        t = 0.0
        for _ in range(rng.randint(3, 40)):
            t += rng.expovariate(1 / rng.choice([3, 10, 25]))
            k = rng.choices(kinds, weights)[0]
            ed = rng.choice(["", "", "morning", "midday", "close", "night"])
            if k in ("schedule", "push", "explicit", "manual"):
                s.at(t, s.arrive, Run(k))
            elif k == "click":
                s.at(t, s.click, ed)
            elif k == "click_nt":                       # האסימון נדחה: רק KV
                s.at(t, s.click, ed, False)
            elif k == "double":                         # שתי לחיצות בהפרש שניות
                s.at(t, s.click, ed)
                s.at(t + rng.uniform(0.01, 0.5), s.click, rng.choice(["", "close"]))
            else:
                s.at(t, s.drainer)
        s.at(t + 60, s.arrive, Run("schedule"))         # ה-cron הבא מגיע מתישהו
        s.go()
        p = s.problems()
        if p:
            bad.append((seed, p))
        n_clicks += len(s.clicks)
        n_rd += sum(r.kind == "redispatch" for r in s.runs)
        n_due += sum(r.mode == "due" for r in s.runs)
    check(f"סימולציה: {days} ימים, {n_clicks} לחיצות — כל לחיצה פעם אחת, שיגור חוזר לא ביטל ריצה",
          not bad, f"{len(bad)} ימים בעייתיים, הראשון: {bad[0] if bad else ''}")
    print(f"     {n_rd} שיגורים חוזרים, {n_due} ריצות לחיצה שהמשיכו כרשת ביטחון")


def main() -> int:
    decision_table()
    args_table()
    io_table()
    replay()
    fuzz()
    print(f"\n{'נכשלו ' + str(len(FAILS)) if FAILS else 'הכל עבר'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
