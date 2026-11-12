# -*- coding: utf-8 -*-
"""משלים ריצות מתוזמנות ש-GitHub לא הפעיל. רשת ביטחון מקומית לצנרות המקור.

**למה.** ה-cron של GitHub מפיל את רוב הריצות: ב-12/11/2026 נורו 4 מתוך 144
פעימות של brief-request, 3 מתוך 24 ריצות שעתיות של גלובס, ובין 18:00 ל-21:00 אף
ריצה של הכותרות, ההשפעה על מניות והסחורות. העמודים נשארו עם שעה ישנה, אף
שהצנרות עצמן תקינות. ראו גם scripts/ensure_editions.py, שעושה את אותו דבר
למהדורות הברייף בלבד.

**איך.** לכל צנרת ברשימה נקראים ביטויי ה-cron מקובץ ה-workflow עצמו, כך שהלוח
כאן לא יוצא מסנכרון. נבדקת המשבצת האחרונה שהגיעה, לפני GRACE דקות. אם הריצה
האחרונה של הצנרת (מכל סוג) נוצרה לפני המשבצת הזו, ואין ריצה פעילה, נשלחת
workflow_dispatch אחת. כשה-cron של GitHub עובד, הבדיקה לא עושה דבר.

**כפילות אפשרית ואינה מזיקה.** cron שמתאחר יותר מ-GRACE דקות עלול לרוץ אחרי
השיגור. הצנרות האלה מעבדות רק מה שחדש, ובתקרות היומיות שלהן.

**מחוץ לרשימה, בכוונה:**
- daily-brief: המהדורות שייכות ל-ensure_editions, ושיגור כאן היה כופה מהדורה.
- brief-request: התור של כפתור "הפק". מ-12/11 הכפתור משגר ישירות.
- nadlan-scan: Govmap חסום ב-reCAPTCHA.

רץ כל 15 דקות כמשימה מתוזמנת (scripts/catchup_task.ps1). היומן נשמר ב-
%LOCALAPPDATA%/TLV-TASE-View/catchup.log ומכיל שמות צנרות ומספרים בלבד.
    python scripts/catchup.py          בדיקה ושיגור
    python scripts/catchup.py --dry    רק להראות מה היה משוגר
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # פרוקסי TLS במשרד: אמון במאגר האישורים של Windows
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
WF_DIR = ROOT / ".github" / "workflows"
REPO = "yoavweizman94-cmyk/DAILY-BRIEF"
API = f"https://api.github.com/repos/{REPO}"
HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TLV-TASE-View"
LOG = HOME / "catchup.log"
GRACE = timedelta(minutes=20)
LOOKBACK = timedelta(hours=48)

# צנרת → קלטי השיגור. ריק = ברירות המחדל של workflow_dispatch.
# בגלובס ברירת המחדל היא probe, שאינה מסכמת. רק run מקביל לריצה מתוזמנת.
WORKFLOWS = {
    "maya-watch.yml": {},
    "headlines.yml": {},
    "impact-watch.yml": {},
    "commodities-watch.yml": {},
    "auto-watch.yml": {},
    "gov-watch.yml": {},
    "cbs-watch.yml": {},
    "globes-calls.yml": {"mode": "run"},
    "offex-backfill.yml": {},
    "calendar.yml": {},
    "meetings.yml": {},
    "filings-backfill.yml": {},
    "freshness.yml": {},
    "site-check.yml": {},
}


def log(msg: str) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > 1_000_000:
        LOG.replace(LOG.with_suffix(".old.log"))
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def token() -> str:
    out = subprocess.run(
        ["git", "-c", "credential.helper=", "-c", "credential.helper=wincred", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True, timeout=30,
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise RuntimeError("אין אישור GitHub שמור (wincred)")


# --- cron -----------------------------------------------------------------
def _field(expr: str, val: int, lo: int, hi: int) -> bool:
    for part in expr.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = int(part)
            b = hi if step > 1 else a
        if a <= val <= b and (val - a) % step == 0:
            return True
    return False


def _matches(cron: str, t: datetime) -> bool:
    mi, ho, dom, mo, dow = cron.split()
    cron_dow = (t.weekday() + 1) % 7          # cron: 0=ראשון; Python: 0=שני
    dow_ok = _field(dow, cron_dow, 0, 6) or (cron_dow == 0 and _field(dow, 7, 0, 7))
    return (_field(mi, t.minute, 0, 59) and _field(ho, t.hour, 0, 23)
            and _field(dom, t.day, 1, 31) and _field(mo, t.month, 1, 12) and dow_ok)


def last_slot(crons: list[str], now: datetime) -> datetime | None:
    """המשבצת האחרונה (UTC) שעברו ממנה לפחות GRACE דקות."""
    t = (now - GRACE).replace(second=0, microsecond=0)
    stop = now - LOOKBACK
    while t > stop:
        if any(_matches(c, t) for c in crons):
            return t
        t -= timedelta(minutes=1)
    return None


def crons_of(wf: str) -> list[str]:
    text = (WF_DIR / wf).read_text(encoding="utf-8")
    return re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', text, flags=re.M)


# --- GitHub ---------------------------------------------------------------
class GH:
    def __init__(self) -> None:
        self.h = {"Authorization": "Bearer " + token(), "User-Agent": "tlv-catchup",
                  "Accept": "application/vnd.github+json"}

    def get(self, path: str) -> dict:
        req = urllib.request.Request(f"{API}/{path}", headers=self.h)
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def dispatch(self, wf: str, inputs: dict) -> None:
        req = urllib.request.Request(
            f"{API}/actions/workflows/{wf}/dispatches", headers=self.h, method="POST",
            data=json.dumps({"ref": "main", "inputs": inputs}).encode())
        urllib.request.urlopen(req, timeout=60).read()


def main(argv: list[str]) -> int:
    dry = "--dry" in argv
    now = datetime.now(timezone.utc)
    gh = GH()
    sent, checked = [], 0
    for wf, inputs in WORKFLOWS.items():
        try:
            crons = crons_of(wf)
            slot = last_slot(crons, now) if crons else None
            if slot is None:
                continue
            checked += 1
            runs = gh.get(f"actions/workflows/{wf}/runs?per_page=1").get("workflow_runs") or []
            last = runs[0] if runs else None
            if last and last["status"] != "completed":
                continue                        # ריצה פעילה או בתור
            made = (datetime.strptime(last["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    if last else None)
            if made and made >= slot:
                continue                        # המשבצת כוסתה
            age = f"{(now - made).total_seconds() / 3600:.1f}h" if made else "never"
            if not dry:
                gh.dispatch(wf, inputs)
            sent.append(wf)
            log(f"{'[dry] ' if dry else ''}שוגר {wf} · משבצת {slot:%H:%M} UTC · הריצה האחרונה לפני {age}")
        except urllib.error.HTTPError as e:
            log(f"{wf}: GitHub השיב {e.code}")
        except Exception as e:  # noqa: BLE001 — צנרת אחת לא עוצרת את השאר
            log(f"{wf}: {type(e).__name__}")
    log(f"נבדקו {checked} צנרות · {'היו משוגרות' if dry else 'שוגרו'} {len(sent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
