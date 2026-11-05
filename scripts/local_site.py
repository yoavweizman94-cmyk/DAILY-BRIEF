# -*- coding: utf-8 -*-
"""עותק מקומי של האתר: HTML במחשב, שנפתח בלי הדומיין.

**למה.** חומת האש של המשרד (FortiGuard) חוסמת את הדומיין, ואתר שזמין רק דרך
דומיין אחד אינו זמין בכל רגע. העותק נבנה מאותו קוד ומאותו תוכן שמהם האתר
נבנה בענן, כלומר site/build.py מעל ריפו התוכן, ונפתח כקובץ (file://).

**לעותק יש שני שכפולים משלו**, תחת %LOCALAPPDATA%\\TLV-TASE-View\\viewer, ולא בעץ
העבודה של הפרויקט: שם עובדים, ובנייה אוטומטית מעץ העבודה הייתה מציגה שינויים
שטרם נשמרו. ריפו התוכן משוכפל אל code/output, באותו מבנה שבו הוא נבנה
ב-Actions. LOCALAPPDATA אינו מסונכרן ל-OneDrive.

**מה יש בעותק ומה אין.** כל העמודים נמצאים בו, כולל אלה שלבעלים בלבד, כי זה
העותק שלו ובמחשב שלו. מה שתלוי בשרת אינו עובד מקובץ: "הפק", סקירת דוח
בלחיצה, החשבון ועריכת החשיבות ברשימת הכיסוי.

**בונים רק כשמשהו השתנה.** כשהקוד והתוכן נמצאים באותם קומיטים כמו בבנייה
הקודמת, לא בונים, ו-`--open` פותח מיד. כשאין רשת או ש-GitHub לא זמין, נפתח
העותק האחרון שנבנה.

שימוש:
  python scripts/local_site.py           עדכון העותק (המשימה המתוזמנת)
  python scripts/local_site.py --open    עדכון ואז פתיחה בדפדפן (קיצור הדרך)
  python scripts/local_site.py --force   בנייה גם כשלא היה שינוי
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from _localrepo import CONTENT_URL, HOME, SITE_URL, Repo  # noqa: E402

V = HOME / "viewer"
CODE = V / "code"
CONTENT = CODE / "output"
SITE = V / "site"
STATE = V / "state.json"
LOCK = V / ".lock"
LOG = HOME / "local_site.log"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    if sys.stdout is not None:      # pythonw: אין קונסולה
        try:
            print(line, flush=True)
        except OSError:
            pass
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.replace(LOG.with_suffix(".log.1"))
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lock() -> bool:
    """המשימה המתוזמנת וקיצור הדרך עלולים לרוץ באותה דקה, ושניהם כותבים לאותם
    שכפולים. נעילה בת יותר מחצי שעה נשארה מריצה שנקטעה, ולכן אפשר לשבור אותה."""
    V.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - LOCK.stat().st_mtime < 1800:
                    return False
                LOCK.unlink()
            except OSError:
                return False
    return False


def head(repo: Repo) -> str:
    return repo.git("rev-parse", "HEAD").stdout.strip()


def publish(dist: Path) -> None:
    """העתקה ואז החלפה, כך שבנייה שנכשלה באמצע לא משאירה עותק חצי בנוי."""
    new, old = V / "site.new", V / "site.old"
    for p in (new, old):
        shutil.rmtree(p, ignore_errors=True)
    shutil.copytree(dist, new)
    try:
        if SITE.exists():
            SITE.rename(old)
        new.rename(SITE)
    except OSError:
        # תיקייה שקובץ בתוכה פתוח לא ניתנת לשינוי שם ב-Windows. לכן מעתיקים
        # מעל העותק הקיים, ומה שנמחק מהאתר נשאר עד ההחלפה המלאה הבאה.
        shutil.copytree(new, SITE, dirs_exist_ok=True)
        shutil.rmtree(new, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)


def update(force: bool) -> int:
    t0 = time.time()
    built = read_state().get("built", "אף פעם")
    try:
        code = Repo(SITE_URL, CODE, "/*", author="local site")
        code.sync()
        content = Repo(CONTENT_URL, CONTENT, "/*", author="local site")
        content.sync()
    except Exception as e:  # noqa: BLE001 — בלי רשת נשאר העותק הקודם
        log(f"המשיכה מ-GitHub נכשלה ({str(e)[:200]}), ולכן נשאר העותק שנבנה ב-{built}")
        return 1
    heads = {"code": head(code), "content": head(content)}
    st = read_state()
    if not force and st.get("heads") == heads and (SITE / "index.html").exists():
        log(f"אין שינוי מאז הבנייה של {built}, ולכן לא בונים")
        return 0
    log("בונה את האתר...")
    dist = CODE / "site" / "dist"
    r = subprocess.run([sys.executable, str(CODE / "site" / "build.py")], cwd=str(CODE),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                       creationflags=NO_WINDOW)
    if r.returncode != 0 or not (dist / "index.html").exists():
        tail = " ".join((r.stderr or r.stdout or "").strip().splitlines()[-3:])[:300]
        log(f"הבנייה נכשלה (קוד {r.returncode}): {tail}. נשאר העותק שנבנה ב-{built}")
        return 1
    publish(dist)
    stamp = f"{datetime.now():%d/%m %H:%M}"
    STATE.write_text(json.dumps({"heads": heads, "built": stamp}, ensure_ascii=False), encoding="utf-8")
    log(f"העותק עודכן ב-{time.time() - t0:.0f} שניות (קוד {heads['code'][:7]}, תוכן {heads['content'][:7]})")
    return 0


def open_site() -> None:
    idx = SITE / "index.html"
    if idx.exists():
        os.startfile(str(idx))  # noqa: S606 — הדפדפן שמוגדר כברירת מחדל
    else:
        log("עדיין אין עותק מקומי לפתוח")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--open", action="store_true", help="לפתוח בדפדפן בסיום")
    ap.add_argument("--force", action="store_true", help="לבנות גם בלי שינוי")
    a = ap.parse_args()
    if not lock():
        log("ריצה אחרת מעדכנת עכשיו את העותק")
        if a.open:
            open_site()
        return 0
    try:
        rc = update(a.force)
    finally:
        LOCK.unlink(missing_ok=True)
    if a.open:
        open_site()
    return rc


if __name__ == "__main__":
    sys.exit(main())
