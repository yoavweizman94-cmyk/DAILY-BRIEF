# -*- coding: utf-8 -*-
"""מוודא שכל מהדורה נכתבה — רשת ביטחון מקומית לתזמון של GitHub.

**למה.** ה-cron של GitHub מתאחר בשעות ולפעמים לא מגיע: ב-04/10/2026 לא
נכתב שום ברייף יומי, וב-05/10 cron הבוקר לא הגיע עד 10:43. הצנרת יודעת
לבחור את המהדורה שבזמן ולהפיק אותה פעם אחת (edition_due + בדיקת קיום ב-
run_daily.sh), אבל רק אם משהו מפעיל אותה.

**מה זה עושה.** בשעת כל מהדורה, משימה ב-Windows (scripts/ensure_task.ps1)
מריצה את הסקריפט הזה, שדוחף לריפו טריגר `if_missing`. הריצה שנפתחת בוחרת
את המהדורה לפי השעה, ויוצאת לפני האיסוף אם היא כבר נכתבה — כלומר כשה-cron
הספיק, זה לא עולה דבר; כשלא, זה משלים.

**שכפול נפרד ולא תיקיית העבודה.** ב-01/10 שני מנגנונים דחפו מאותה תיקייה
באותה שנייה, התנגשו (`Cannot rebase onto multiple branches`) ושניהם נכשלו.
כאן יש שכפול רדוד משלו ב-%LOCALAPPDATA%: הוא לא נוגע בעבודה פתוחה, לא
מתנגש במשימת ה-GTO, ומתאפס לראש הענף לפני כל דחיפה.

יומן: %LOCALAPPDATA%\\TLV-TASE-View\\ensure_editions.log
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_URL = "https://github.com/yoavweizman94-cmyk/DAILY-BRIEF.git"
HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TLV-TASE-View"
CLONE = HOME / "ensure-repo"
LOG = HOME / "ensure_editions.log"
LOCK = HOME / "ensure_editions.lock"
TRIGGER = ".trigger/daily-brief.json"
# אותו אישור שמור ש-git push משתמש בו בתיקיית העבודה; בלי מסוף, ולכן בלי
# בקשת סיסמה שתולה את המשימה.
GIT = ["git", "-c", "credential.helper=", "-c", "credential.helper=wincred"]
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg: str) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def git(*args: str, cwd: Path | None = None, timeout: int = 180) -> tuple[int, str]:
    try:
        p = subprocess.run([*GIT, *args], cwd=cwd, env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=NO_WINDOW)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"{type(e).__name__}: {e}"


def take_lock() -> bool:
    """מופע אחד בכל רגע. נעילה בת יותר מחצי שעה היא שארית של ריצה שמתה."""
    HOME.mkdir(parents=True, exist_ok=True)
    try:
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime > 1800:
            LOCK.unlink()
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def sync() -> bool:
    """שכפול רדוד, מאופס לראש main."""
    if not (CLONE / ".git").exists():
        rc, out = git("clone", "-q", "--depth", "1", REPO_URL, str(CLONE), timeout=300)
        if rc:
            log(f"שכפול נכשל: {out[-200:]}")
            return False
        return True
    rc, out = git("fetch", "-q", "--depth", "1", "origin", "main", cwd=CLONE)
    if rc:
        log(f"fetch נכשל: {out[-200:]}")
        return False
    rc, out = git("reset", "-q", "--hard", "origin/main", cwd=CLONE)
    if rc:
        log(f"reset נכשל: {out[-200:]}")
        return False
    return True


def push_trigger() -> bool:
    now = datetime.now()
    (CLONE / TRIGGER).write_text(json.dumps({
        "if_missing": True,
        "reason": "רשת ביטחון מקומית: לוודא שהמהדורה שבזמן נכתבה",
        "at": now.isoformat(timespec="seconds"),
        "by": "ensure_editions",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    git("add", TRIGGER, cwd=CLONE)
    rc, out = git("commit", "-q", "-m", f"טריגר: לוודא את המהדורה שבזמן ({now:%d/%m %H:%M})",
                  cwd=CLONE)
    if rc:
        log(f"commit נכשל: {out[-200:]}")
        return False
    rc, out = git("push", "-q", "origin", "HEAD:main", cwd=CLONE)
    if rc:
        log(f"push נדחה: {out[-160:]}")
        return False
    return True


def main() -> int:
    if not take_lock():
        log("מופע אחר כבר רץ — יוצאים")
        return 0
    try:
        # ניסיון חוזר: דחיפה נדחית כשמישהו דחף בין ה-fetch ל-push.
        for attempt in range(1, 4):
            if sync() and push_trigger():
                log(f"נדחף טריגר if_missing (ניסיון {attempt})")
                return 0
            time.sleep(15 * attempt)
        log("לא נדחף אחרי שלושה ניסיונות")
        return 1
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
