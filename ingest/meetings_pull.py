# -*- coding: utf-8 -*-
"""הקלטות של שיחות עם חברות → תמליל ב-Soniox → ריפו התוכן הפרטי.

**רץ מקומית ולא ב-Actions**, כמו gto_pull: ההקלטות נמצאות במחשב, בתיקייה
שיואב מנהל בעצמו (MEETINGS_DIR ב-.env), ואין להן עותק בענן. הסקריפט מוצא
הקלטה שעוד לא תומללה, שולח אותה ל-Soniox, מקבל תמליל עם הפרדה בין דוברים,
**מוחק את הקובץ ואת התמליל מ-Soniox**, ודוחף רשומה ל-meetings/ בריפו התוכן.
הסקירה נכתבת אחר כך ב-Actions (ingest/meetings_summarize.py).

**למה Soniox.** בטבלת ההשוואה של ivrit.ai לעברית (benchmark.csv, 10/2026)
הוא המדויק בשירותי הענן: WER ממוצע 9.9%, ו-4.8% בשיחה (eval-d1) — מול 11.5%
ב-Amazon, ‏16.4% ב-ElevenLabs ו-18.2% ב-OpenAI. ‏$0.10 לשעת הקלטה, כולל הפרדת
דוברים. תמלול מקומי (ivrit-ai על faster-whisper) מדויק כמוהו, אבל בלי כרטיס
גרפי הוא איטי, ויואב בחר בענן.

**הזהות היא התוכן, לא השם.** מזהה הרשומה נגזר מתוכן הקובץ, כך ששינוי שם או
העברה לתת-תיקייה אינם מתמללים שוב, וגם אינם מאבדים את הסקירה.

**פרטיות.** אלה פגישות עבודה עם הנהלות. הרשומות נכנסות רק לריפו התוכן הפרטי,
העמוד באתר פתוח לבעלים בלבד (site/functions/_middleware.js), והברייף אינו רואה
אותן (run_daily.sh מוציא את התיקייה מעץ העבודה בזמן הסוכן). ל-Soniox נשלח
הקובץ בשם ניטרלי, והטריגר שנדחף לריפו הציבורי מכיל ספירה ושעה בלבד.

שימוש:
  python ingest/meetings_pull.py             תמלול של מה שחדש, דחיפה ופריסה
  python ingest/meetings_pull.py --list      מה יתומלל, בלי לשלוח דבר
  python ingest/meetings_pull.py --limit 1   הקלטה אחת בלבד (בדיקה)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _tls import harden  # noqa: E402

harden()

import requests  # noqa: E402
import yaml  # noqa: E402

from _env import load_env  # noqa: E402
from _localrepo import CONTENT_URL, HOME, SITE_URL, Repo  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.soniox.com/v1"
MODEL = "stt-async-v5"
USD_PER_HOUR = 0.10
STATE = HOME / "meetings_state.json"
LOG = HOME / "meetings_pull.log"

# הפורמטים ש-Soniox מזהה בעצמו (opus הוא ogg; wma הוא asf).
EXTS = {".m4a", ".mp3", ".mp4", ".wav", ".aac", ".flac", ".ogg", ".opus", ".webm",
        ".amr", ".aiff", ".asf", ".wma"}
MIN_BYTES = 100_000          # פחות מזה — הקלטה שנקטעה מיד, לא שיחה
TIME_BUDGET_SEC = 90 * 60    # שתי ריצות ביום; אחרי שעה וחצי ממשיכים בריצה הבאה
MAX_FAILS = 3                # קובץ שנכשל שלוש פעמים נשלח שוב רק פעם ביום — ולא נזנח:
RETRY_AFTER = timedelta(days=1)   # הכישלון הראשון (28/10/2026) היה של הרשת, לא של הקובץ


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


# ── הקובץ ─────────────────────────────────────────────────────────────────────

def scan(base: Path) -> list[Path]:
    out = []
    for p in base.rglob("*"):
        if p.suffix.lower() not in EXTS or p.name.startswith(("~", ".")):
            continue
        try:
            if p.is_file() and p.stat().st_size >= MIN_BYTES:
                out.append(p)
        except OSError:
            continue
    return out


def file_id(p: Path) -> str:
    """מזהה מתוכן הקובץ: הגודל, וארבעת המגה הראשונים והאחרונים. קריאה מלאה של
    כמה ג'יגה בכל בדיקה מיותרת, והקצוות לבדם כבר שונים בין שתי הקלטות."""
    size = p.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with p.open("rb") as f:
        h.update(f.read(4 << 20))
        if size > 8 << 20:
            f.seek(-(4 << 20), os.SEEK_END)
            h.update(f.read())
    return h.hexdigest()[:16]


HE_MONTHS = {"ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6,
             "יולי": 7, "אוגוסט": 8, "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12}


def _valid(y: int, m: int, d: int) -> date | None:
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    return dt if date(2015, 1, 1) <= dt <= date.today() else None


def name_date(stem: str) -> tuple[date | None, str]:
    """תאריך משם הקובץ, ודיוקו: "day", ‏"month", או "partial" — יום וחודש בלי שנה.

    השמות בתיקיות של יואב: "שפיר 17.06.24", "פרטנר 5.12.24", "ארד 14.09.2026",
    "WhatsApp Audio 2025-02-23", "קול 241223_160002" (מקליט הטלפון),
    "רימוני אפריל 24", "קליל 09.22" (חודש.שנה), "תדיראן 16.6" (בלי שנה).
    """
    m = re.search(r"(20\d\d)[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)", stem)
    if m and (d := _valid(int(m[1]), int(m[2]), int(m[3]))):
        return d, "day"
    m = re.search(r"(?<!\d)(\d\d)(\d\d)(\d\d)_\d{6}(?!\d)", stem)
    if m and (d := _valid(2000 + int(m[1]), int(m[2]), int(m[3]))):
        return d, "day"
    m = re.search(r"(?<![\d.])(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d\d)(?![\d.])", stem)
    if m:
        y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        if d := _valid(y, int(m[2]), int(m[1])):
            return d, "day"
    m = re.search("(" + "|".join(HE_MONTHS) + r")\s*'?(\d{4}|\d\d)(?!\d)", stem)
    if m:
        y = int(m[2]) + (2000 if len(m[2]) == 2 else 0)
        if d := _valid(y, HE_MONTHS[m[1]], 1):
            return d, "month"
    m = re.search(r"(?<![\d.])(\d{1,2})[./](\d{1,2})(?![\d./])", stem)
    if m:
        a, b = int(m[1]), int(m[2])
        if 1 <= a <= 12 and b > 12 and (d := _valid(2000 + b, a, 1)):
            return d, "month"            # 09.22 — ספטמבר 2022
        if 1 <= a <= 31 and 1 <= b <= 12:
            try:
                return date(2000, b, a), "partial"   # השנה תיקבע מול תאריך ייחוס
            except ValueError:
                pass
    return None, ""


def media_date(p: Path) -> date | None:
    """תאריך ההקלטה מ-mvhd של קובץ MP4/M4A. מקליטים בטלפון כותבים אותו גם
    כששם הקובץ אינו אומר דבר, ו"תאריך השינוי" של הקובץ הוא לרוב יום ההעתקה."""
    if p.suffix.lower() not in {".m4a", ".mp4", ".mov", ".3gp"}:
        return None
    try:
        total = p.stat().st_size
        with p.open("rb") as f:
            pos = 0
            while pos + 8 <= total:
                f.seek(pos)
                n, typ = struct.unpack(">I4s", f.read(8))
                hl = 8
                if n == 1:
                    n, hl = struct.unpack(">Q", f.read(8))[0], 16
                elif n == 0:
                    n = total - pos
                if n < hl:
                    return None
                if typ == b"moov":
                    q, end = pos + hl, pos + n
                    while q + 8 <= end:
                        f.seek(q)
                        n2, t2 = struct.unpack(">I4s", f.read(8))
                        if n2 < 8:
                            return None
                        if t2 == b"mvhd":
                            ver = f.read(4)[0]
                            raw = f.read(8 if ver == 1 else 4)
                            secs = struct.unpack(">Q" if ver == 1 else ">I", raw)[0]
                            if not secs:
                                return None
                            d = (datetime(1904, 1, 1, tzinfo=timezone.utc)
                                 + timedelta(seconds=secs)).astimezone().date()
                            return _valid(d.year, d.month, d.day)
                        q += n2
                    return None
                pos += n
    except (OSError, struct.error, OverflowError, IndexError, ValueError):
        return None
    return None


def resolve_date(p: Path) -> tuple[str | None, str]:
    """(תאריך ISO, מקור). שם הקובץ קודם — יואב כתב אותו; אחריו נתוני ההקלטה;
    ותאריך השינוי של הקובץ רק כשאין דבר אחר, כי הוא לרוב יום ההעתקה."""
    d, kind = name_date(p.stem)
    if kind == "day":
        return d.isoformat(), "name"
    if kind == "month":
        return d.isoformat()[:7], "name"
    media = media_date(p)
    if kind == "partial":
        ref = media or datetime.fromtimestamp(p.stat().st_mtime).date()
        y = ref.year
        try:
            cand = date(y, d.month, d.day)
            if cand > ref:
                cand = date(y - 1, d.month, d.day)
            return cand.isoformat(), "name+year"
        except ValueError:
            pass
    if media:
        return media.isoformat(), "media"
    return datetime.fromtimestamp(p.stat().st_mtime).date().isoformat(), "mtime"


def name_period(stem: str) -> str | None:
    m = re.search(r"(?i)\bQ([1-4])\s*'?(20\d\d|\d\d)\b", stem)
    if not m:
        return None
    y = m[2] if len(m[2]) == 4 else f"20{m[2]}"
    return f"Q{m[1]} {y}"


# ── החברה ──────────────────────────────────────────────────────────────────────

def _norm(s) -> str:
    s = re.sub(r"[\"'״׳`]", "", str(s or ""))
    s = re.sub(r"[^\w֐-׿]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def company_keys() -> list[tuple[str, str]]:
    """(מפתח מנורמל, שם קנוני) מרשימת הכיסוי, מהארוך לקצר — כדי ש"אלקטרה פאוור"
    יגבר על "אלקטרה". **המילה הראשונה של שם ארוך** ("תדיראן" ל"תדיראן גרופ",
    "שפיר" ל"שפיר הנדסה") — כי כך יואב קורא לקבצים, ורק כשהיא ייחודית ברשימה."""
    cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    first: dict[str, set] = {}
    for c in cfg.get("companies") or []:
        canon = c.get("name_he")
        if not canon:
            continue
        for k in [canon, c.get("name_en"), *(c.get("aliases") or [])]:
            n = _norm(k)
            if len(n) >= 3:
                out.setdefault(n, canon)
        w = _norm(canon).split()
        if len(w) > 1 and len(w[0]) >= 4:
            first.setdefault(w[0], set()).add(canon)
    for w, names in first.items():
        if len(names) == 1:
            out.setdefault(w, next(iter(names)))
    return sorted(out.items(), key=lambda kv: -len(kv[0]))


def guess_company(stem: str, keys: list[tuple[str, str]]) -> str | None:
    s = f" {_norm(stem)} "
    for k, canon in keys:
        if f" {k} " in s:
            return canon
    return None


# ── Soniox ─────────────────────────────────────────────────────────────────────

class Fatal(Exception):
    """מפתח שגוי או חשבון בלי יתרה — אין טעם להמשיך לקובץ הבא."""


class Soniox:
    def __init__(self, key: str):
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {key}"

    def _ok(self, r: requests.Response, what: str) -> dict:
        if r.status_code in (401, 403):
            raise Fatal(f"Soniox דחה את המפתח ({r.status_code}) — בדוק את SONIOX_API_KEY ב-.env")
        if r.status_code == 402:
            raise Fatal("אין יתרה בחשבון Soniox (402) — יש להוסיף אמצעי תשלום ב-console.soniox.com")
        if r.status_code >= 400:
            raise RuntimeError(f"{what}: HTTP {r.status_code} {r.text[:200]}")
        return r.json() if r.content else {}

    def upload(self, p: Path, fid: str) -> str:
        # **שם ניטרלי.** שם הקובץ אומר עם מי נפגשת; ל-Soniox מספיקה הסיומת.
        # **חומת האש של המשרד עוצרת העלאה גדולה לבדיקה.** Fortinet מיירט את ה-TLS
        # ל-api.soniox.com (נבדק 28/10/2026): ‏156KB עלו בשנייה וחצי, ו-51MB נתקעו
        # ונפלו אחרי 30 שניות על "write operation timed out" — ועם המתנה ארוכה עברו
        # ב-136 שניות. ב-requests הערך הראשון חל גם על כל כתיבה בזמן השליחה, ולכן
        # הוא ארוך כאן ולא רק הקריאה.
        with p.open("rb") as f:
            r = self.s.post(f"{API}/files", files={"file": (fid + p.suffix.lower(), f)},
                            timeout=(900, 1800))
        return self._ok(r, "העלאה")["id"]

    def create(self, file_id: str, fid: str, context: dict | None) -> str:
        body = {"model": MODEL, "file_id": file_id, "language_hints": ["he", "en"],
                "enable_speaker_diarization": True, "client_reference_id": fid}
        if context:
            body["context"] = context
        r = self.s.post(f"{API}/transcriptions", json=body, timeout=60)
        if r.status_code == 400 and context:
            # הקשר שנדחה אינו סיבה לוותר על התמליל — שוב, בלעדיו
            log(f"  ההקשר נדחה ({r.text[:120]}) — שוב בלעדיו")
            body.pop("context")
            r = self.s.post(f"{API}/transcriptions", json=body, timeout=60)
        return self._ok(r, "יצירת תמלול")["id"]

    def wait(self, tid: str, limit: int = 3600) -> dict:
        t0, delay = time.monotonic(), 3.0
        while True:
            j = self._ok(self.s.get(f"{API}/transcriptions/{tid}", timeout=60), "מצב")
            if j.get("status") == "completed":
                return j
            if j.get("status") == "error":
                raise RuntimeError(f"Soniox: {j.get('error_type') or ''} {j.get('error_message') or ''}".strip())
            if time.monotonic() - t0 > limit:
                raise RuntimeError("Soniox לא סיים תוך שעה")
            time.sleep(delay)
            delay = min(delay * 1.5, 20)

    def transcript(self, tid: str) -> dict:
        return self._ok(self.s.get(f"{API}/transcriptions/{tid}/transcript", timeout=120), "תמליל")

    def delete(self, kind: str, oid: str | None) -> None:
        if not oid:
            return
        try:
            r = self.s.delete(f"{API}/{kind}/{oid}", timeout=60)
            if r.status_code >= 400 and r.status_code != 404:
                log(f"  מחיקת {kind} ב-Soniox נכשלה: HTTP {r.status_code} — תימחק שם אחרי 30 יום")
        except requests.RequestException as e:
            log(f"  מחיקת {kind} ב-Soniox נכשלה: {type(e).__name__} — תימחק שם אחרי 30 יום")


def context_for(company: str | None) -> dict:
    """הקשר לזיהוי: התחום, ושם החברה כשהוא ידוע — שמות פרטיים הם מה שמשתבש
    ראשון בתמלול, ושם החברה חוזר בשיחה עשרות פעמים."""
    ctx: dict = {"general": [
        {"key": "domain", "value": "Finance"},
        {"key": "topic", "value": "Meeting between an investor and the management of a company "
                                  "traded on the Tel Aviv Stock Exchange"},
    ]}
    if company:
        ctx["general"].append({"key": "organization", "value": company})
        ctx["terms"] = [company]
    return ctx


def segments(tokens: list[dict]) -> list[dict]:
    """טוקנים → פסקאות לפי דובר. **טוקן נושא את הרווח שלפניו**, ולכן מחברים
    כמות שהם, ובתחילת פסקה מסירים רווח מוביל — כמו בדוגמה של Soniox. דובר אחד
    שמדבר יותר מדקה וחצי מפוצל בסוף המשפט, כדי שהתמליל ייקרא."""
    out: list[dict] = []
    cur: dict | None = None
    for t in tokens:
        txt = t.get("text") or ""
        if not txt:
            continue
        sp = str(t.get("speaker") or "")
        start = (t.get("start_ms") or 0) / 1000
        long_turn = (cur is not None and start - cur["t"] > 90
                     and cur["text"].rstrip()[-1:] in (".", "?", "!"))
        if cur is None or sp != cur["sp"] or long_turn:
            if cur:
                out.append(cur)
            cur = {"sp": sp, "t": round(start, 1), "text": txt.lstrip()}
        else:
            cur["text"] += txt
    if cur:
        out.append(cur)
    for s in out:
        s["text"] = s["text"].strip()
    return [s for s in out if s["text"]]


def transcribe(sx: Soniox, p: Path, fid: str, company: str | None) -> tuple[list[dict], float]:
    file_id = tid = None
    try:
        t0 = time.monotonic()
        file_id = sx.upload(p, fid)
        tid = sx.create(file_id, fid, context_for(company))
        st = sx.wait(tid)
        tokens = sx.transcript(tid).get("tokens") or []
        dur = (st.get("audio_duration_ms") or max((t.get("end_ms") or 0) for t in tokens or [{}])) / 1000
        log(f"  תומלל: {dur / 60:.0f} דקות הקלטה ב-{(time.monotonic() - t0) / 60:.1f} דקות")
        return segments(tokens), dur
    finally:
        # **מוחקים גם בכישלון.** בלי זה הקובץ נשאר אצלם עד שלושים יום.
        sx.delete("transcriptions", tid)
        sx.delete("files", file_id)


# ── מצב ודחיפה ─────────────────────────────────────────────────────────────────

def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(st: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def resting(fail: dict | None) -> bool:
    """קובץ שנכשל MAX_FAILS פעמים ממתין יום מהכישלון האחרון, ואז מקבל ניסיון נוסף."""
    if not fail or fail.get("n", 0) < MAX_FAILS:
        return False
    try:
        return datetime.now() - datetime.fromisoformat(fail.get("at") or "") < RETRY_AFTER
    except ValueError:
        return False


def write_record(folder: Path, rec: dict) -> None:
    f = folder / "meetings" / f"{rec['id']}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def trigger(n: int) -> None:
    """הפעלת Meetings ב-Actions: פריסת התמלילים, וסקירה אם זה ערב."""
    site = Repo(SITE_URL, HOME / "site-meetings", "/.trigger/", author="Meetings local")

    def touch(d: Path) -> None:
        t = d / ".trigger" / "meetings.json"
        t.parent.mkdir(parents=True, exist_ok=True)
        # **ספירה ושעה בלבד** — הריפו הזה ציבורי.
        t.write_text(json.dumps({"reason": "הקלטות שתומללו", "count": n,
                                 "at": datetime.now().isoformat(timespec="minutes")},
                                ensure_ascii=False) + "\n", encoding="utf-8")
    site.commit_push("meetings: הקלטות שתומללו", touch, [".trigger/meetings.json"])


def main() -> int:
    ap = argparse.ArgumentParser(description="תמלול הקלטות של שיחות עם חברות")
    ap.add_argument("--dir", help="תיקיית ההקלטות (ברירת מחדל: MEETINGS_DIR ב-.env)")
    ap.add_argument("--list", action="store_true", help="מה יתומלל, בלי לשלוח דבר")
    ap.add_argument("--limit", type=int, default=0, help="כמה הקלטות לכל היותר בריצה")
    ap.add_argument("--no-deploy", action="store_true", help="בלי טריגר לפריסה")
    args = ap.parse_args()

    load_env()
    raw = args.dir or os.environ.get("MEETINGS_DIR") or ""
    base = Path(raw.strip().strip('"')) if raw.strip() else None
    if not base or not base.is_dir():
        log(f"תיקיית ההקלטות {'לא הוגדרה' if not base else 'לא נמצאה'} — "
            "יש להגדיר MEETINGS_DIR ב-.env")
        return 1

    keys = company_keys()
    st = read_state()
    fails = st.setdefault("failed", {})

    content = Repo(CONTENT_URL, HOME / "content-meetings", "/meetings/", author="Meetings local")
    try:
        content.sync()
    except Exception as e:  # noqa: BLE001
        log(f"ריפו התוכן: {e}")
        return 1
    have = {p.stem for p in (content.dir / "meetings").glob("*.json")}

    todo, seen = [], set()
    for p in scan(base):
        try:
            fid = file_id(p)
        except OSError as e:
            log(f"{p.name}: לא נקרא ({e})")
            continue
        if fid in have or fid in seen:
            continue
        seen.add(fid)
        if resting(fails.get(fid)):
            continue
        d, how = resolve_date(p)
        todo.append({"p": p, "fid": fid, "date": d, "how": how})
    # **החדשות קודם** — הן אלה שיואב מחכה להן; תאריך חסר בסוף
    todo.sort(key=lambda t: t["date"] or "", reverse=True)

    if args.list:
        print(f"{len(todo)} הקלטות ממתינות לתמלול ({len(have)} כבר בריפו):")
        for t in todo:
            print(f"  {t['date'] or '—':<10} ({t['how']:<9}) {guess_company(t['p'].stem, keys) or '—':<18} "
                  f"{t['p'].relative_to(base)}")
        return 0
    if not todo:
        log(f"אין הקלטות חדשות ({len(have)} כבר תומללו)")
        st["last_run"] = datetime.now().isoformat(timespec="seconds")
        write_state(st)
        return 0

    key = os.environ.get("SONIOX_API_KEY")
    if not key:
        log("SONIOX_API_KEY חסר ב-.env — אין איך לתמלל")
        return 1
    sx = Soniox(key)

    done, t0 = 0, time.monotonic()
    for t in todo[:args.limit or None]:
        if time.monotonic() - t0 > TIME_BUDGET_SEC:
            log(f"עברה שעה וחצי — {len(todo) - done} הקלטות יחכו לריצה הבאה")
            break
        p, fid = t["p"], t["fid"]
        company = guess_company(p.stem, keys)
        log(f"{p.name} · {t['date'] or 'בלי תאריך'} · {company or 'חברה לא זוהתה'}")
        try:
            segs, dur = transcribe(sx, p, fid, company)
        except Fatal as e:
            log(str(e))
            break
        except Exception as e:  # noqa: BLE001
            n = (fails.get(fid) or {}).get("n", 0) + 1
            fails[fid] = {"n": n, "file": p.name, "err": f"{type(e).__name__}: {e}"[:300],
                          "at": datetime.now().isoformat(timespec="minutes")}
            log(f"  נכשל ({n}/{MAX_FAILS}): {type(e).__name__}: {e}")
            continue
        rel = p.parent.relative_to(base)
        rec = {
            "id": fid, "file": p.name, "folder": "" if str(rel) == "." else rel.as_posix(),
            "company": company, "date": t["date"], "date_from": t["how"],
            "period": name_period(p.stem),
            "duration_sec": round(dur), "speakers": len({s["sp"] for s in segs if s["sp"]}),
            "chars": sum(len(s["text"]) for s in segs), "segments": segs,
            "engine": f"soniox {MODEL}", "stt_usd": round(dur / 3600 * USD_PER_HOUR, 3),
            "transcribed_at": datetime.now().isoformat(timespec="minutes"),
        }
        try:
            content.commit_push(f"meetings: {company or p.stem} {t['date'] or ''}".strip(),
                                lambda d, r=rec: write_record(d, r), ["meetings"])
        except Exception as e:  # noqa: BLE001
            log(f"  הדחיפה לריפו התוכן נכשלה: {e} — יתומלל שוב בריצה הבאה")
            break
        fails.pop(fid, None)
        done += 1
        st["usd_total"] = round((st.get("usd_total") or 0) + rec["stt_usd"], 3)

    if done and not args.no_deploy:
        try:
            trigger(done)
            log(f"{done} הקלטות נדחפו, והפריסה הופעלה")
        except Exception as e:  # noqa: BLE001
            log(f"טריגר הפריסה נכשל: {e} — התמלילים ייכנסו לאתר בפריסה הבאה של כל צנרת")
    st["last_run"] = datetime.now().isoformat(timespec="seconds")
    write_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
