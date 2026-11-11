# -*- coding: utf-8 -*-
"""מכין לסוכן קלט מעוכל במקום קבצי השנה הגולמיים.

**למה זה קיים.** הברייף הוא הקריאה היקרה בצנרת, ורוב עלותו אינה החשיבה
אלא הקלט: `output/nadlan/<שנה>.jsonl` לבדו הוא 2.1MB — 5,717 עסקאות —
והוא גדול פי שניים וחצי מכל שאר הקלט יחד. הסוכן נשלח אליו כדי לכתוב
סעיף אחד על מגמת מחירים, בעוד בדיוק אותם חישובים כבר נעשים ב-
`site/nadlan_stats.py` עבור האתר. אותו דבר בעסקאות מחוץ לבורסה: הוא
צריך את היום, ומקבל את השנה.

נמדד 28/09/2026: מהדורה ב-Sonnet נקטעה בתקרה של $4 אחרי $4.39 בלי
להשלים, ומהדורה באופוס ב-$6. מיליון טוקן של קלט אינם נקראים פעם אחת —
הם נשלחים מחדש בכל תור.

מה שנוצר כאן נכתב ל-`data/raw/<תאריך>/pack/`, שהוא ממילא מחוץ לגיט:

  nadlan.json      תמונת שוק הדיור — מצרף, ערים, שכונות — מ-nadlan_stats
  otc.jsonl        עסקאות מחוץ לבורסה של הימים האחרונים בלבד
  offex.jsonl      דיווחי מאיה על עסקאות בעלי עניין, אותו חלון
  jumbo.jsonl      עסקאות מתואמות, אותו חלון
  maya_summaries.jsonl  גוף הדיווחים: הסיכום מגוף הדוח לכל דיווח שב-maya.jsonl
  cbs.jsonl        הודעות הלמ"ס הרלוונטיות מ-24 השעות האחרונות עם הניתוח, ולוח השבוע
  gov.jsonl        פרסומי משרדי הממשלה והרגולטורים שסומנו מהותיים, עם הנימוק
  call_reviews.jsonl  "דוח ושיחה": סקירת שיחת המשקיעים (תמליל גלובס) וסקירת הדוח
  impact.jsonl     עמוד ההשפעה על מניות: אירועים בהשפעה בינונית ומעלה, לפי חברה
  commodities_review.json / auto_review.json  הסקירה האחרונה של עמודי הסחורות והרכב
  companies.json   רשימת הכיסוי בלי שדות שאינם משמשים לכתיבה

**הדיגסט אינו מקצר את הניתוח, רק את הקריאה.** כל מה ש-CLAUDE.md דורש
מסעיף שוק הדיור — השוואה רבעונית, יד שנייה בנפרד, תמהיל מקבלן, ערים
חסרות — נמצא כאן מחושב. מה שאינו נמצא כאן (עסקה בודדת, כתובת) לא היה
אמור להיכתב בברייף ממילא.

שימוש: python scripts/brief_pack.py <תאריך> [ימים אחורה]
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))

# חלון ברירת המחדל: ארבעה ימים. הברייף צריך את היום, אבל במהדורת בוקר
# "היום" עוד ריק, ואחרי סוף שבוע היום האחרון שנסחר הוא לפני שלושה ימים.
WINDOW_DAYS = 4

# שכונות: שלוש הגדולות בכל עיר מספיקות לאייטם. הזנב הוא רעש שנשלח בכל תור.
TOP_HOODS = 3
# רבעונים: ארבעה אחרונים — מהם נגזרות ההשוואות רבעון-לרבעון ושנה-לשנה.
KEEP_QUARTERS = 5

# שדות שאינם משמשים לכתיבת הברייף. tase_id ו-maya_company_id משמשים את
# סקריפטי ה-ingest, לא את הסוכן; הוא מזהה חברות בשם ומקשר דרך maya.jsonl.
COMPANY_DROP = ("tase_id", "maya_company_id", "listing")


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _recent(rows: list[dict], since: str, *fields: str) -> list[dict]:
    """שומר רשומות שאחד משדות התאריך שלהן בתוך החלון.

    רשומה בלי תאריך כלל נשמרת: עדיף אייטם מיותר על אייטם שנמחק בשקט.
    """
    keep = []
    for r in rows:
        stamps = [str(r.get(f) or "")[:10] for f in fields]
        stamps = [s for s in stamps if s]
        if not stamps or max(stamps) >= since:
            keep.append(r)
    return keep


def nadlan_digest() -> dict | None:
    """תמונת שוק הדיור — בדיוק החישובים שהאתר מציג, בלי העסקאות עצמן."""
    try:
        import nadlan  # noqa: PLC0415
        import nadlan_stats as ns  # noqa: PLC0415
    except Exception as ex:  # noqa: BLE001
        print(f"  שוק הדיור: המודול לא נטען ({ex})")
        return None

    rows = nadlan.load()
    if not rows:
        return None
    clean, dropped = ns.clean_rows(rows)
    st = ns.city_stats(clean)
    mk = ns.market(clean, st)

    cities = {}
    for city, v in st.items():
        q = dict(sorted(v.get("quarters", {}).items())[-KEEP_QUARTERS:])
        cities[city] = {
            k: v[k] for k in (
                "region", "n", "n_new", "n_used", "ppsm", "ppsm_new", "ppsm_used",
                "premium_new", "price", "area", "level", "qoq", "yoy", "used_yoy",
                "share_new", "share_new_prev", "vol", "vol_prev", "vol_change",
                "label", "why", "mix_flag", "thin", "by_rooms",
            ) if k in v
        }
        cities[city]["quarters"] = q
        cities[city]["hoods"] = v.get("hoods", [])[:TOP_HOODS]

    state = {}
    try:
        state = json.loads((ROOT / "data" / "nadlan_state.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass

    # **נתונים קפואים נאמרים.** מאוקטובר 2026 Govmap דורש reCAPTCHA לשליפת
    # עסקאות, והסריקה נעצרת. הקבצים נשארים מהסריקה המוצלחת האחרונה — תמונה
    # רבעונית תקפה, אבל לא "מה קרה השבוע", וקורא שאינו יודע זאת יקרא אותה כטרייה.
    blk = state.get("blocked") or {}
    frozen = []
    if blk.get("reason") == "recaptcha":
        frozen = ["הסריקה מושבתת: Govmap דורש אימות reCAPTCHA לכל שליפת עסקאות (זוהה ב-"
                  f"{str(blk.get('since') or blk.get('at'))[:10]}). הנתונים כאן הם מהסריקה "
                  f"המוצלחת האחרונה ({str(state.get('updated') or '')[:10] or 'לא ידוע'}) — "
                  "לכתוב זאת בסעיף, ולא להציג שום נתון כחדש מהיום"]

    return {
        "מקור": "output/nadlan/<שנה>.jsonl — מחושב ב-site/nadlan_stats.py",
        "סריקה": {"עדכון_אחרון": state.get("updated"), "חסימה": blk or None},
        "סייגים": frozen + [
            "רשות המסים מדווחת כשישה שבועות אחרי העסקה; החודשיים האחרונים חסומים "
            f"מהחישוב ({ns.LAG_MONTHS} חודשים) ואין לכתוב עליהם ירידה בהיקפים",
            "הסריקה מכסה כמה שכונות בכל עיר — 'בשכונות שנסרקו' ולא 'בעיר'",
            "ההשוואה רבעונית; רבעון חסר חודש מראה ירידה של ~50% בהיקפים",
            "עיר ב-failed/empty אינה עיר שקטה ואינה אייטם",
        ],
        "מצרף": {k: v for k, v in mk.items()
                 if k not in ("series", "by_region", "leaders", "laggards")},
        "מובילות": [[c, v["yoy"]] for c, v in mk.get("leaders", [])],
        "מפגרות": [[c, v["yoy"]] for c, v in mk.get("laggards", [])],
        "ערים": cities,
        "נוקו": dropped,
        "ערים_ללא_עסקאות": {
            "failed": sorted((state.get("failed") or {}) if isinstance(state.get("failed"), dict)
                             else state.get("failed") or []),
            "empty": sorted((state.get("empty") or {}) if isinstance(state.get("empty"), dict)
                            else state.get("empty") or []),
        },
    }


# **גוף הדיווח, לא רק הכותרת.** maya.jsonl נושא כותרת בלבד, כי הפיד של מאיה אינו
# מחזיר גוף. במהדורת הנעילה של 09/11/2026 נכתב בתקלות שהגוף ריק בכל 73 הדיווחים,
# והניתוח נבנה מכותרות. אותה הערה הופיעה ברוב הברייפים מאז 02/11. באותו יום כבר
# שולם על סיכום מגוף כל דיווח (scripts/summarize_reports.py → output/reports), אבל
# הסוכן לא הופנה אליו. כאן הסיכומים מוצמדים לדיווחים לפי id.
# **רק מה שהברייף כותב ממנו.** כותרת, קישור וטופס כבר נמצאים ב-maya.jsonl. דיווח
# טכני (מהותיות 1) נשאר בכותרת ובסיכום בלבד, כי מקומו בהשמטה או ב"בקצרה".
SUMMARY_FIELDS = ("headline", "summary", "trend", "analysis", "balance", "flags",
                  "omissions", "direction", "why", "affected", "affected_why", "watch")


def maya_summaries(raw_dir: Path, reports_dir: Path, day: str,
                   window: int) -> tuple[list[dict], int]:
    """הסיכומים של הדיווחים שב-maya.jsonl, ומספר הדיווחים שם.

    הסיכום נכתב ליום שבו הדיווח נאסף, ולא בהכרח ליום הברייף: מהדורת לילה
    שאחרי חצות, או בוקר אחרי סוף שבוע. לכן הסיכומים נחפשים לאורך כל החלון.
    """
    ids = list(dict.fromkeys(str(r["id"]) for r in _rows(raw_dir / "maya.jsonl") if r.get("id")))
    if not ids:
        return [], 0
    pool: dict[str, dict] = {}
    d0 = date.fromisoformat(day)
    for k in range(window, -1, -1):          # מהישן לחדש, כך שהגרסה האחרונה גוברת
        for r in _rows(reports_dir / f"{(d0 - timedelta(days=k)).isoformat()}.jsonl"):
            if r.get("id"):
                pool[str(r["id"])] = r
    out = []
    for i in ids:
        s = pool.get(i)
        if not s:
            continue
        mat = s.get("materiality")
        rec = {"id": i, "ts": s.get("ts"), "coverage": s.get("coverage") or [], "materiality": mat}
        technical = isinstance(mat, int) and mat <= 1
        for k in (("headline", "summary") if technical else SUMMARY_FIELDS):
            v = s.get(k)
            if v not in (None, "", [], "טכני"):
                rec[k] = v
        figs = [f"{f['label']}: {f.get('value', '')}" for f in s.get("key_figures") or []
                if isinstance(f, dict) and f.get("label")]
        if figs and not technical:
            rec["key_figures"] = figs
        out.append(rec)
    return out, len(ids)


# **מה שצנרות האתר כבר ניתחו — גם לברייף.** עד 10/11/2026 הברייף ראה רק את
# data/raw ואת מאיה, בעוד האתר מנתח עוד שישה מקורות בצנרות משלו. באותו יום
# נכתב במהדורת הנעילה "אין פרסום חדש של הלמ"ס — נבדק מול הסקיל", כשבעמוד
# הלמ"ס כבר עמדה מהבוקר הודעה רלוונטית (פדיון רשתות השיווק) עם ניתוח מלא.
# הסקיל נשען על שרת MCP שאינו רואה את ההודעות לתקשורת. כאן מוצמד לחבילה מה
# שהאתר כבר כתב ב-24 השעות האחרונות, בשדות שהברייף כותב מהם בלבד.
# **החלון מתגלגל ולא יומי.** מהדורת הבוקר צריכה את ערב אתמול, והלילה —
# שנכתבת אחרי חצות — את היום שהסתיים. כפילות מול מהדורה קודמת נמנעת בברייף
# עצמו, שקורא את המהדורות הקודמות.
# **מחוץ לחבילה בכוונה:** meetings (השיחות של הבעלים בלבד), x (טיוטות ציוצים)
# וכל שדה tweets. הברייף מופץ ללקוחות.
SITE_HOURS = 24
# **הקיצוץ נמדד.** ב-11/11/2026 מהדורת הבוקר באופוס נקטעה בתקרה של $15 ($16.26)
# אחרי 37 קריאות כלים — הראשונה עם ניתוחי האתר בקלט, ביום דוחות עמוס (71
# דיווחי כיסוי). הניתוחים המלאים היו כ-120KB, והקלט נשלח מחדש בכל תור. מה
# שהברייף כותב מהם הוא השורה, הכיוון לכל חברה והמקור; הגוף המלא נמצא בעמודים.
IMPACT_MIN_SIG = 2              # 1 = נמוכה; הסף של הברייף משמיט אותה ממילא
CAL_DAYS_AHEAD = 7
_DROP = ("model", "effort", "cost_usd", "usd", "through", "prices_at", "window_h",
         "n_items", "n_il", "n_world", "analyzed_at", "triaged_at", "run", "basis",
         "page", "tweets", "tweet_len", "x_thread")


def _stamp(v) -> datetime | None:
    """חותמת זמן כ-datetime עם אזור. חותמת בלי אזור היא שעון מקומי — הריצה
    בענן היא TZ=Asia/Jerusalem, וכך נכתבות החותמות בצנרות."""
    try:
        t = datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.astimezone()


def _cut(text, n: int):
    return text if not isinstance(text, str) or len(text) <= n else text[:n].rstrip() + "…"


def _trim(v, n: int = 450):
    """כל מחרוזת בתוך המבנה — עד n תווים. המבנה עצמו (כותרות, חברות, מקורות) נשמר."""
    if isinstance(v, str):
        return _cut(v, n)
    if isinstance(v, list):
        return [_trim(x, n) for x in v]
    if isinstance(v, dict):
        return {k: _trim(x, n) for k, x in v.items()}
    return v


def site_analyses(day: str) -> dict:
    """מה שהאתר ניתח בחלון, לפי מקור. ריק = אין קובץ."""
    base = ROOT / "output"
    now = datetime.now().astimezone()
    cut = now - timedelta(hours=SITE_HOURS)
    cut_day = cut.date().isoformat()
    out: dict = {}

    # הלמ"ס — ההודעות הרלוונטיות עם הניתוח, ולוח הפרסומים של השבוע
    year = day[:4]
    ana = {str(a.get("release_id")): a for a in _rows(base / "cbs" / "analyses" / f"{year}.jsonl")}
    cbs = []
    for r in _rows(base / "cbs" / "releases" / f"{year}.jsonl"):
        pub = _stamp(r.get("published"))
        if not r.get("relevant") or (pub < cut if pub else str(r.get("date") or "") < cut_day):
            continue
        a = ana.get(str(r.get("id"))) or {}
        rec = {"id": r.get("id"), "date": r.get("date"), "published": r.get("published"),
               "title": r.get("title"), "url": r.get("url"), "topic": r.get("topic_label"),
               "analyzed": bool(a)}
        for k in ("headline", "key_figures", "what_happened", "macro", "micro", "caveats",
                  "watch_next", "terms"):
            if a.get(k):
                rec[k] = (a[k] if k in ("key_figures", "terms")
                          else _cut(a[k], 1200) if k == "what_happened" else _trim(a[k], 450))
        if not a:
            rec["summary"] = _cut(r.get("summary") or "", 1500)
        cbs.append(rec)
    snap_p = base / "cbs" / "snapshot.json"
    if snap_p.exists():
        try:
            cal = json.loads(snap_p.read_text(encoding="utf-8")).get("calendar") or []
        except json.JSONDecodeError:
            cal = []
        until = (date.fromisoformat(day) + timedelta(days=CAL_DAYS_AHEAD)).isoformat()
        out_titles = {str(r.get("title") or "")[:30] for r in cbs}   # שכבר פורסמו — לא שוב כצפויות
        for c in cal:
            if (c.get("relevant") and day <= str(c.get("date") or "") <= until
                    and str(c.get("title") or "")[:30] not in out_titles):
                cbs.append({"calendar": True, "date": c.get("date"), "time": c.get("time"),
                            "title": c.get("title"), "type": c.get("type"),
                            "topic": c.get("topic_label")})
    out["cbs.jsonl"] = cbs

    # משרדי הממשלה והרגולטורים — רק מה שהמיון סימן כמהותי
    gov = []
    gdir = base / "gov"
    for d in (sorted(p for p in gdir.iterdir() if p.is_dir()) if gdir.exists() else []):
        items = {str(i.get("id")): i for i in _rows(d / "items.jsonl")}
        for a in _rows(d / "analyses.jsonl"):
            it = items.get(str(a.get("id")))
            if not a.get("material") or not it:
                continue
            if str(it.get("date") or "")[:10] < cut_day:
                continue
            gov.append({"office": it.get("unit") or d.name, "date": it.get("date"),
                        "type": it.get("type"), "title": it.get("title"), "url": it.get("url"),
                        "companies": a.get("companies") or [], "why": a.get("reason")})
    out["gov.jsonl"] = gov

    # דוח ושיחה — סקירת שיחת המשקיעים מתמליל גלובס, לצד סקירת הדוח
    calls = []
    for p in sorted((base / "calls" / "combined").glob("*.json")):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        gen = _stamp(c.get("generated"))
        if c.get("status") != "ok" or not ((gen and gen >= cut)
                                           or str(c.get("call_date") or "") >= cut_day):
            continue
        rep = c.get("report") or {}
        calls.append({"company": c.get("company"), "period": c.get("period"),
                      "call_date": c.get("call_date"), "call_url": c.get("call_url"),
                      "report_id": rep.get("id"), "report_title": rep.get("t"),
                      "headline": c.get("headline"), "call_review": _cut(c.get("review_md"), 3500),
                      "report_review": _cut(c.get("report_review"), 1200)})
    out["call_reviews.jsonl"] = calls

    # ההשפעה על מניות — ניתוח לפי חברה וכיוון, בינונית ומעלה
    imp, seen = [], set()
    for k in (1, 0):
        for r in _rows(base / "impact" / f"{(date.fromisoformat(day) - timedelta(days=k)).isoformat()}.jsonl"):
            ts = _stamp(r.get("ts"))
            if (r.get("sig") or 0) < IMPACT_MIN_SIG or not ts or ts < cut or r.get("id") in seen:
                continue
            seen.add(r.get("id"))
            links = [{"name": x.get("name"), "url": x.get("url")} for x in r.get("links") or []
                     if isinstance(x, dict) and "mail.google" not in str(x.get("url"))][:1]
            # העובדות עצמן נמצאות במקור (מאיה/rss) שהברייף קורא ממילא; מכאן — הכרעה לפי חברה
            comps = [{"name": c.get("name"), "direction": c.get("direction"),
                      "line": _cut(c.get("line"), 160)}
                     for c in r.get("companies") or [] if isinstance(c, dict)]
            imp.append({"ts": r.get("ts"), "kind": r.get("kind"), "sig": r.get("sig"),
                        "headline": r.get("headline"), "verdict": _cut(r.get("verdict"), 350),
                        "companies": comps, "links": links})
    out["impact.jsonl"] = imp

    # הסקירה האחרונה של עמודי הסחורות והרכב, אם נכתבה בחלון
    for name, sub in (("commodities_review.json", "commodities"), ("auto_review.json", "auto")):
        rows = _rows(base / sub / "analyses" / f"{day[:7]}.jsonl")
        last = rows[-1] if rows else None
        at = _stamp(last.get("analyzed_at")) if last else None
        if at and at >= cut:
            # **התמונה והחברות, לא הסעיפים.** הסעיפים מסכמים כותרות שהברייף קורא
            # ממילא ב-rss.jsonl, וה-refs שלהם הם כתובות ארוכות (עברית מקודדת):
            # יחד כשני שלישים מהסקירה. מה שאין לברייף ממקום אחר הוא ההכרעה —
            # הסקירה הכוללת, השורה לכל חברה ומה לעקוב. מקור לעובדה — מה-rss.
            rec = {"analyzed_at": last.get("analyzed_at")}
            for k in ("registry_month", "headline", "overview", "companies", "impact", "watch"):
                if last.get(k):
                    rec[k] = _cut(last[k], 1200) if k == "overview" else _trim(last[k], 300)
            if isinstance(last.get("leasing"), dict) and last["leasing"].get("summary"):
                rec["leasing"] = _cut(last["leasing"]["summary"], 600)
            out[name] = rec
    return out


def companies_slim() -> str | None:
    """רשימת הכיסוי כטבלת טקסט — הסוכן מזהה בשם, לא ב-id.

    ה-YAML נושא מזהי מסחר, סיווג בורסה והזחות; מה שנדרש לכתיבה הוא שם,
    כינויים, סקטור ודרייברים. הטבלה נקראת באותה קלות ותופסת שליש.
    """
    try:
        import yaml  # noqa: PLC0415
        cfg = yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))
    except Exception as ex:  # noqa: BLE001
        print(f"  כיסוי: לא נטען ({ex})")
        return None

    # **מה החברה עושה, ממקור.** תיאור הפעילות שהחברה מסרה למאיה ושווי השוק שלה
    # (data/company_profiles.json). בלעדיהם ההסבר על חברה ספציפית נשען על
    # הזיכרון של המודל או נעצר ב"השפעה על הענף".
    sys.path.insert(0, str(ROOT / "scripts"))
    import _profiles  # noqa: PLC0415
    comps = cfg.get("companies", [])
    lines = [f"# רשימת הכיסוי — {len(comps)} חברות. מקור: config/companies.yaml; "
             f"פעילות ושווי שוק — מאיה ({_profiles.updated() or 'לא נטען'})",
             "# שם | אנגלית | כינויים | סקטור | דרייברים נוספים | גנרי=התאמה רק בהקשר עסקי"
             " | פעילות (מאיה) | שווי שוק",
             ""]
    for c in comps:
        prof = _profiles.load().get(c.get("name_he") or "") or {}
        lines.append(" | ".join((
            str(c.get("name_he") or ""),
            str(c.get("name_en") or ""),
            ",".join(c.get("aliases") or []),
            str(c.get("sector") or ""),
            ",".join(c.get("drivers_extra") or []),
            "גנרי" if c.get("generic_name") else "",
            _profiles.activity(c.get("name_he") or "", 110),
            _profiles.cap_text(prof.get("market_cap_m")),
        )).rstrip(" |"))

    lines += ["", "# פרופילי סקטור — לאיזה דרייבר כל סקטור חשוף", ""]
    for key, p in (cfg.get("sector_profiles") or {}).items():
        lines.append(f"{key} | {p.get('label', '')} | {', '.join(p.get('drivers') or [])}")

    lines += ["", "# קטלוג דרייברים — תיאור ומקור נתונים", ""]
    for key, d in (cfg.get("drivers_catalog") or {}).items():
        lines.append(f"{key} | {d.get('desc', '')} | {d.get('source', '')}")

    return "\n".join(lines) + "\n"


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    window = int(sys.argv[2]) if len(sys.argv) > 2 else WINDOW_DAYS
    since = (date.fromisoformat(day) - timedelta(days=window)).isoformat()

    out = ROOT / "data" / "raw" / day / "pack"
    out.mkdir(parents=True, exist_ok=True)
    year = day[:4]
    saved = written = 0

    def dump(name: str, payload) -> None:
        nonlocal written
        path = out / name
        if isinstance(payload, list):
            text = "\n".join(json.dumps(r, ensure_ascii=False) for r in payload) + "\n"
        else:
            text = json.dumps(payload, ensure_ascii=False, indent=1)
        path.write_text(text, encoding="utf-8")
        written += len(text.encode("utf-8"))

    # שוק הדיור — הקובץ הגדול בצנרת, ומה שהסוכן צריך ממנו הוא טבלה
    src = ROOT / "output" / "nadlan" / f"{year}.jsonl"
    dig = nadlan_digest()
    if dig:
        saved += src.stat().st_size if src.exists() else 0
        dump("nadlan.json", dig)
        print(f"  שוק הדיור: {len(dig['ערים'])} ערים, {dig['מצרף'].get('n')} עסקאות בחישוב")

    # שלושת מקורות העסקאות — היום ולא השנה
    for name, fields in (("otc", ("date", "traded_at")),
                         ("offex", ("date", "published")),
                         ("jumbo", ("date",))):
        src = ROOT / "output" / name / f"{year}.jsonl"
        rows = _rows(src)
        if not src.exists():
            continue
        keep = _recent(rows, since, *fields)
        saved += src.stat().st_size
        dump(f"{name}.jsonl", keep)
        print(f"  {name}: {len(keep)} מתוך {len(rows)} רשומות מאז {since}")

    # גוף הדיווחים — אין לו מקור שהוא מחליף, ולכן הוא אינו נספר ב"במקום"
    summ, n_maya = maya_summaries(ROOT / "data" / "raw" / day, ROOT / "output" / "reports",
                                  day, window)
    if n_maya:
        dump("maya_summaries.jsonl", summ)
        print(f"  סיכומי מאיה: {len(summ)} מתוך {n_maya} דיווחים")
        print(f"::notice title=סיכומי מאיה בקלט::{len(summ)} מתוך {n_maya} דיווחי הכיסוי "
              "עם סיכום מגוף הדוח; השאר כותרת בלבד")

    # מה שהאתר ניתח — מספרים בלבד בלוג: הלוג של Actions ציבורי
    try:
        site = site_analyses(day)
    except Exception as e:  # noqa: BLE001 — חבילה חלקית עדיפה על חבילה שנפלה
        site = {}
        print(f"::warning title=ניתוחי האתר לא צורפו לקלט::{type(e).__name__}")
    parts = []
    for name, payload in site.items():
        if payload:
            dump(name, payload)
            parts.append(f"{name.split('.')[0]} {len(payload) if isinstance(payload, list) else 1}")
    if parts:
        print(f"::notice title=ניתוחי האתר בקלט::{' · '.join(parts)}")

    comps = companies_slim()
    if comps:
        saved += (ROOT / "config" / "companies.yaml").stat().st_size
        dump("companies.txt", comps)

    if saved:
        line = (f"{written // 1024}KB במקום {saved // 1024}KB "
                f"({100 - written * 100 // max(saved, 1)}% פחות)")
        print(f"  קלט מעוכל: {line}")
        print(f"::notice title=קלט מעוכל::{line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
