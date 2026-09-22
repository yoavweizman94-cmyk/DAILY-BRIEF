# -*- coding: utf-8 -*-
"""עסקאות מתואמות מקובץ ה-Excel החם של GTO → ריפו התוכן הפרטי.

**רץ מקומית ולא ב-Actions.** הקובץ "מתואמות.xlsx" (בשורש הפרויקט) מתעדכן
מתוכנת GTO שפתוחה במחשב: כל תא בו הוא נוסחת RTD("gto", …), ואין לו מקבילה
בענן. הסקריפט קורא אותו, כותב את היום לתוך output/jumbo/<שנה>.jsonl בריפו
התוכן, ודוחף. הקובץ עצמו מוחרג ב-.gitignore: אלה נתוני מסחר ברישיון, והריפו
הזה ציבורי.

**קריאה חיה ולא מהדיסק.** ערכי RTD מתעדכנים בזיכרון של Excel, והקובץ שעל
הדיסק מחזיק רק את מה שהיה בשמירה האחרונה. כשהחוברת פתוחה, הערכים נקראים
מ-Excel עצמו (COM). כשהיא אינה פתוחה אבל GTO רץ — ממופע Excel נסתר ונפרד
שפותח אותה לקריאה בלבד (_hidden_rows). רק כש-GTO אינו רץ — מהשמירה האחרונה,
בתאריך של השמירה.

**מה נשמר.** כל נייר שבעמודה "עסקאות מתואמות" מופיעה בו האות J — כך GTO
מסמן נייר שהיו בו עסקאות מתואמות באותו יום (JumboIndication). לכל אחד:
התמורה המתואמת (DailyJumboRevenue), מחזור היום, שער בסיס, שער אחרון, שינוי
ושווי שוק. **אין בקובץ מחיר לכל עסקה**, ולכן גם לא סטייה משער הבסיס.

**שלושה מעקות מפני יום שגוי:**
  · לא בסוף שבוע, ולא לפני 09:50 — אז GTO עדיין מציג את היום הקודם.
  · GTO מנותק מחזיר #N/A בכל התאים — ואז לא נכתב כלום, ולא "אפס עסקאות".
  · תמונה זהה ליום הקודם שנשמר היא יום בלי מסחר (חג) — ואינה נכתבת שוב
    תחת התאריך החדש.

שימוש:
  python ingest/gto_pull.py            קריאה, כתיבה, דחיפה, ופריסה בסיום המסחר
  python ingest/gto_pull.py --dry-run  קריאה והדפסה בלבד
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "מתואמות.xlsx"
CONFIG = ROOT / "config" / "companies.yaml"

# **שני שכפולים נפרדים, מחוץ לעץ העבודה.** output/ המקומי הוא שכפול SSH
# ישן, ועץ העבודה של הפרויקט הוא מקום שבו עובדים — דחיפה אוטומטית ממנו
# הייתה מערבבת קומיטים של המשימה בשינויים שטרם נשמרו.
HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TLV-TASE-View"
CONTENT_URL = "https://github.com/yoavweizman94-cmyk/DAILY-BRIEF-content.git"
SITE_URL = "https://github.com/yoavweizman94-cmyk/DAILY-BRIEF.git"
STATE = HOME / "gto_state.json"
LOG = HOME / "gto_pull.log"

HEAD = {
    "sid": "מספר נייר", "name": "שם עברי", "base": "שער בסיס", "last": "שער אחרון",
    "chg": "שינוי ב-%", "day_value": "תמורה יומי", "mcap": "שווי שוק עכשווי",
    "value": "תמורה עסקאות מתואמות", "stage": "שלב מסחר", "flag": "עסקאות מתואמות",
}
REQUIRED = ("sid", "name", "value")
FINAL_STAGE = "סיום"
OPEN_AT = (9, 50)


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.replace(LOG.with_suffix(".log.1"))
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# --- קריאת החוברת ---------------------------------------------------------------

def _live_rows(path: Path) -> tuple[list[list], str] | None:
    """הערכים מתוך Excel הפתוח, או None כשהחוברת אינה פתוחה."""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None
    pythoncom.CoInitialize()
    target = os.path.normcase(str(path.resolve()))
    wb = None
    try:
        xl = win32com.client.GetActiveObject("Excel.Application")
        for w in xl.Workbooks:
            if os.path.normcase(str(w.FullName)) == target:
                wb = w
                break
    except pythoncom.com_error:
        return None
    if wb is None:
        return None
    return _read_workbook(wb)


def _read_workbook(wb) -> tuple[list[list], str] | None:
    """הגיליון שבשורה הראשונה שלו "מספר נייר", מחוברת COM פתוחה."""
    import pythoncom
    # Excel דוחה קריאות COM בזמן עריכת תא (RPC_E_CALL_REJECTED) — ממתינים.
    for _ in range(8):
        try:
            for ws in wb.Worksheets:
                vals = ws.UsedRange.Value
                if vals and any(str(v).strip() == HEAD["sid"] for v in vals[0] if v is not None):
                    return [list(r) for r in vals], str(ws.Name)
            return None
        except pythoncom.com_error:
            time.sleep(5)
    return None


GTO_PROCESS = "Trade1.exe"      # תוכנת המסחר; שרת ה-RTD ("gto") מתחבר אליה


def _gto_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GTO_PROCESS}", "/NH"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return GTO_PROCESS.lower() in out.lower()


def _hidden_rows(path: Path, wait_s: int = 120) -> tuple[list[list], str] | None:
    """הערכים החיים ממופע Excel נסתר ונפרד, כשהחוברת אינה פתוחה אצל המשתמש.

    **הקובץ לא היה פתוח, והיום אבד.** 18/09/2026 לא נאסף: GTO רץ, Excel היה
    פתוח על קובץ אחר, והקריאה נפלה לשמירה מ-17/09. מופע נפרד (DispatchEx)
    פותח את החוברת לקריאה בלבד, שרת ה-RTD נטען בו ומתחבר ל-GTO הרץ, ותוך
    כעשרים שניות הערכים מתמלאים — בלי לגעת בחלונות של המשתמש. נבדק 22/09.
    רץ רק כש-GTO רץ: אחרת שרת ה-RTD עלול לנסות להפעיל אותו.
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None
    pythoncom.CoInitialize()
    xl = win32com.client.DispatchEx("Excel.Application")
    wb = None
    try:
        xl.Visible = False
        xl.DisplayAlerts = False
        xl.ScreenUpdating = False
        wb = xl.Workbooks.Open(str(path), 0, True)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            for f in (lambda: xl.RTD.RefreshData(), lambda: xl.CalculateFull()):
                try:
                    f()
                except pythoncom.com_error:
                    pass
            got = _read_workbook(wb)
            if got:
                rows, _ = got
                header = [str(h).strip() if h is not None else "" for h in rows[0]]
                li = header.index(HEAD["last"]) if HEAD["last"] in header else None
                data = [r for r in rows[1:] if r and r[0] not in (None, "")]
                priced = sum(1 for r in data if li is not None and (_num(r[li]) or 0) > 0)
                if data and priced >= 0.5 * len(data):
                    return got
            time.sleep(6)
        return None
    except pythoncom.com_error:
        return None
    finally:
        try:
            if wb is not None:
                wb.Close(False)
        except pythoncom.com_error:
            pass
        try:
            xl.Quit()
        except pythoncom.com_error:
            pass


def _saved_rows(path: Path) -> tuple[list[list], str]:
    """הערכים מהשמירה האחרונה. עותק זמני — Excel נועל את המקור כשהוא פתוח."""
    import openpyxl
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "gto.xlsx"
        shutil.copyfile(path, tmp)
        wb = openpyxl.load_workbook(tmp, data_only=True, read_only=True)
        try:
            for ws in wb.worksheets:
                rows = [list(r) for r in ws.iter_rows(values_only=True)]
                if rows and any(str(v).strip() == HEAD["sid"] for v in rows[0] if v is not None):
                    return rows, ws.title
        finally:
            wb.close()
    raise ValueError(f"אין בחוברת גיליון עם העמודה \"{HEAD['sid']}\"")


def _num(v) -> float | None:
    """מספר, או None לתא ריק ולשגיאה. שגיאת Excel מגיעה ב-COM כמספר שלילי
    ענק (#N/A הוא -2146826246) ובקובץ כמחרוזת "#N/A" — שתיהן אינן נתון."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if -2146826300 < v < -2146826200 else float(v)
    s = str(v).strip().replace(",", "")
    if not s or s.startswith("#"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def coverage() -> dict[int, str]:
    try:
        import yaml
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — בלי קובץ הכיסוי פשוט אין סימון כיסוי
        return {}
    rows = cfg["companies"] if isinstance(cfg, dict) and "companies" in cfg else cfg
    return {int(c["tase_id"]): c["name_he"] for c in rows or [] if c.get("tase_id")}


def collect(path: Path) -> dict:
    """קורא את החוברת ומחזיר את התמונה: תאריך, רשומות, ומה נבדק בדרך."""
    got, how = _live_rows(path), "live"
    if got is None and _gto_running():
        got, how = _hidden_rows(path), "hidden"
    if got is not None:
        asof = datetime.now()
    else:
        got = _saved_rows(path)
        how, asof = "saved", datetime.fromtimestamp(path.stat().st_mtime)
    rows, sheet = got
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    col = {k: header.index(h) for k, h in HEAD.items() if h in header}
    missing = [HEAD[k] for k in REQUIRED if k not in col]
    if missing:
        raise ValueError("עמודות חסרות בחוברת: " + ", ".join(missing))

    def cell(r, k):
        i = col.get(k)
        return r[i] if i is not None and i < len(r) else None

    data = [r for r in rows[1:] if cell(r, "sid") not in (None, "")]
    priced = sum(1 for r in data if (_num(cell(r, "last")) or 0) > 0)
    stages = Counter(str(cell(r, "stage")).strip() for r in data if cell(r, "stage"))
    final = bool(stages) and stages.get(FINAL_STAGE, 0) >= 0.9 * sum(stages.values())

    cov = coverage()
    day = asof.strftime("%Y-%m-%d")
    recs = []
    for r in data:
        flag = cell(r, "flag")
        flagged = (str(flag).strip().upper() == "J" if "flag" in col
                   else any(str(v).strip() == "J" for v in r if isinstance(v, str)))
        if not flagged:
            continue
        sid_raw = str(cell(r, "sid")).strip()
        try:
            sid = str(int(float(sid_raw)))
        except ValueError:
            continue
        value = _num(cell(r, "value"))
        if not value or value <= 0:
            continue                              # J בלי תמורה (#N/A) אינו נתון
        day_value = _num(cell(r, "day_value"))
        last = _num(cell(r, "last"))
        mcap_m = _num(cell(r, "mcap"))            # מיליוני ₪
        chg = _num(cell(r, "chg"))
        rec = {
            "date": day,
            "security_id": sid,
            "name": " ".join(str(cell(r, "name") or "").split()),
            "value": round(value, 2),
            "day_value": round(day_value) if day_value is not None else None,
            "pct_of_day": round(value / day_value * 100, 2) if day_value else None,
            "mcap": round(mcap_m * 1e6) if mcap_m else None,
            # הון מונפק משוער: שווי השוק חלקי השער האחרון (באגורות).
            "issued": round(mcap_m * 1e6 / (last / 100)) if mcap_m and last else None,
            "base": _num(cell(r, "base")),
            "last": last,
            "chg_pct": round(chg, 2) if chg is not None else None,
            "stage": str(cell(r, "stage") or "").strip() or None,
            "final": final,
            "asof": asof.isoformat(timespec="minutes"),
            "src": "gto",
            "covered": int(sid) in cov,
        }
        if int(sid) in cov:
            rec["coverage_name"] = cov[int(sid)]
        recs.append(rec)
    recs.sort(key=lambda x: -(x["value"] or 0))
    return {"how": how, "asof": asof, "day": day, "sheet": sheet, "rows": len(data),
            "priced": priced, "stages": dict(stages), "final": final, "records": recs}


def fingerprint(recs: list[dict]) -> str:
    key = sorted((r["security_id"], r.get("value")) for r in recs)
    return hashlib.sha1(json.dumps(key, ensure_ascii=False).encode()).hexdigest()


def problem(snap: dict) -> str | None:
    """סיבה לא לכתוב את התמונה, או None."""
    asof = snap["asof"]
    if asof.weekday() >= 5:
        return "סוף שבוע — אין מסחר"
    if (asof.hour, asof.minute) < OPEN_AT:
        return f"לפני {OPEN_AT[0]:02d}:{OPEN_AT[1]:02d} — GTO עדיין מציג את היום הקודם"
    if snap["rows"] < 50 or snap["priced"] < 0.5 * snap["rows"]:
        return (f"רק {snap['priced']} מתוך {snap['rows']} ניירות עם שער — "
                "GTO כנראה מנותק")
    if not snap["records"]:
        return "אין ניירות עם J — טרם בוצעו עסקאות מתואמות"
    return None


# --- ריפו ---------------------------------------------------------------------------

class Repo:
    """שכפול רדוד ודליל של תיקייה אחת. **בכל ריצה מאפסים אל הענף המרוחק**
    ובונים את השינוי מחדש, כך שאין קומיטים מקומיים שמצטברים או מתנגשים."""

    def __init__(self, url: str, where: Path, sparse: str):
        self.url, self.dir, self.sparse = url, where, sparse

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        r = subprocess.run(
            ["git", "-c", "credential.helper=", "-c", "credential.helper=wincred",
             "-c", "core.quotepath=false", "-c", "user.name=GTO local",
             "-c", "user.email=gto-local@users.noreply.github.com", *args],
            cwd=str(cwd or self.dir), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[:300]}")
        return r

    def sync(self) -> None:
        if not (self.dir / ".git").exists():
            self.dir.parent.mkdir(parents=True, exist_ok=True)
            self.git("clone", "--quiet", "--depth", "1", "--filter=blob:none", "--no-checkout",
                     self.url, str(self.dir), cwd=self.dir.parent)
            self.git("sparse-checkout", "set", "--no-cone", self.sparse)
        self.git("fetch", "--quiet", "--depth", "1", "origin", "main")
        self.git("checkout", "--quiet", "-B", "main", "origin/main")
        self.git("reset", "--quiet", "--hard", "origin/main")

    def commit_push(self, message: str, apply, paths: list[str]) -> bool:
        """apply() כותב את השינוי על העותק העדכני. False — אין מה לדחוף."""
        for attempt in range(4):
            self.sync()
            apply(self.dir)
            self.git("add", "--", *paths)
            if self.git("diff", "--cached", "--quiet", check=False).returncode == 0:
                return False
            self.git("commit", "--quiet", "-m", message)
            if self.git("push", "--quiet", "origin", "HEAD:main", check=False).returncode == 0:
                return True
            time.sleep(5 * (attempt + 1))   # מישהו דחף בינתיים — מאפסים ובונים מחדש
        raise RuntimeError("הדחיפה נכשלה ארבע פעמים")


def merge_day(folder: Path, day: str, recs: list[dict]) -> None:
    """מחליף את רשומות היום בקובץ השנה, ומשאיר את שאר הימים כמות שהם."""
    f = folder / "jumbo" / f"{day[:4]}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    keep = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("date") != day:
                    keep.append(r)
    rows = keep + recs
    rows.sort(key=lambda r: (r["date"], -(r.get("value") or 0)))
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def previous_day(folder: Path, day: str) -> tuple[str | None, str | None]:
    """היום האחרון שנשמר לפני `day`, וטביעת האצבע שלו."""
    by_day: dict[str, list] = {}
    for f in sorted((folder / "jumbo").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("date") and r["date"] < day:
                    by_day.setdefault(r["date"], []).append(r)
    if not by_day:
        return None, None
    last = max(by_day)
    return last, fingerprint(by_day[last])


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(st: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="עסקאות מתואמות מ-GTO")
    ap.add_argument("--file", default=str(WORKBOOK), help="נתיב החוברת")
    ap.add_argument("--dry-run", action="store_true", help="קריאה והדפסה בלבד")
    ap.add_argument("--no-deploy", action="store_true", help="בלי טריגר לפריסה בסיום המסחר")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        log(f"החוברת לא נמצאה: {path}")
        return 1
    try:
        snap = collect(path)
    except Exception as e:  # noqa: BLE001
        log(f"קריאת החוברת נכשלה: {type(e).__name__}: {e}")
        return 1

    total = sum(r["value"] or 0 for r in snap["records"])
    log(f"{snap['day']} · קריאה {({'live': 'חיה', 'hidden': 'חיה (מופע נסתר)'}).get(snap['how'], 'מהשמירה')} "
        f"({snap['asof']:%H:%M}, גיליון {snap['sheet']}) · {snap['rows']} ניירות, "
        f"{len(snap['records'])} עם J, {total / 1e6:,.1f} מ׳ ₪ · "
        f"{'סיום מסחר' if snap['final'] else 'תוך כדי מסחר'}")
    if args.dry_run:
        for r in snap["records"][:12]:
            print(f"  {r['name']:<22} {r['value'] / 1e6:>7.2f} מ׳ ₪  "
                  f"{r['pct_of_day'] if r['pct_of_day'] is not None else '—':>6}% מהמחזור")
        why = problem(snap)
        print("לא ייכתב:" if why else "ייכתב", why or "")
        return 0

    why = problem(snap)
    if why:
        log(f"לא נכתב: {why}")
        return 0

    st = read_state()
    fp = fingerprint(snap["records"])
    content = Repo(CONTENT_URL, HOME / "content", "/jumbo/")
    try:
        content.sync()
        prev, prev_fp = previous_day(content.dir, snap["day"])
        if prev_fp and prev_fp == fp:
            log(f"לא נכתב: התמונה זהה ליום {prev} — כנראה אין מסחר היום")
            return 0
        pushed = content.commit_push(
            f"jumbo: {snap['day']} {snap['asof']:%H:%M}"
            + (" (סיום)" if snap["final"] else ""),
            lambda d: merge_day(d, snap["day"], snap["records"]), ["jumbo"])
        log("נדחף לריפו התוכן" if pushed else "אין שינוי מול ריפו התוכן")
    except Exception as e:  # noqa: BLE001
        log(f"ריפו התוכן: {e}")
        return 1

    # **פריסה פעם אחת ביום, בסיום המסחר.** כל דחיפה ל-main מריצה את
    # Cloudflare Deploy; תמונות ביניים נכנסות לאתר בפריסות של הצנרת הרגילה.
    if snap["final"] and not args.no_deploy and st.get("deployed") != snap["day"]:
        site = Repo(SITE_URL, HOME / "site", "/.trigger/")

        def touch(d: Path) -> None:
            t = d / ".trigger" / "gto.json"
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(json.dumps({"reason": "עסקאות מתואמות — סיום יום מסחר",
                                     "date": snap["day"]}, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        try:
            site.commit_push(f"gto: עסקאות מתואמות {snap['day']}", touch, [".trigger/gto.json"])
            st["deployed"] = snap["day"]
            log("פריסת האתר הופעלה")
        except Exception as e:  # noqa: BLE001
            log(f"טריגר הפריסה נכשל: {e}")
    st.update({"last_run": datetime.now().isoformat(timespec="seconds"), "last_day": snap["day"],
               "last_fp": fp, "last_final": snap["final"]})
    write_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
