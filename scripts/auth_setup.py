#!/usr/bin/env python3
"""הקמת התשתית לאימות עצמי מול Cloudflare.

יוצר מרחב KV למשתמשים, מקשר אותו לפרויקט ה-Pages, ומייצר את הסוד
שחותם את עוגיות הסשן. אידמפוטנטי — מה שקיים אינו נוצר מחדש.

PROBE=true בודק הרשאות בלבד ואינו יוצר דבר, כדי שאפשר יהיה לדעת מראש
אם הטוקן מספיק במקום לגלות זאת באמצע.
"""
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
PROJECT = "forest-brief"
KV_TITLE = "tlv-tase-view-users"
BINDING = "USERS"

TOK = os.environ["CF_TOKEN"]
ACC = os.environ["CF_ACCOUNT"]
PROBE = os.environ.get("PROBE", "true") == "true"


def call(path, method="GET", body=None):
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}


def errs(body):
    return "; ".join(f"{e.get('code')}:{e.get('message')}" for e in (body.get("errors") or []))


def main():
    print("=== בדיקת הרשאות ===")
    caps = {}
    for label, path in [("KV", f"/accounts/{ACC}/storage/kv/namespaces"),
                        ("Pages", f"/accounts/{ACC}/pages/projects/{PROJECT}")]:
        code, body = call(path)
        ok = body.get("success") is True
        caps[label] = ok
        print(f"  {label:6s} {'✓' if ok else '✗'}  HTTP {code}  {'' if ok else errs(body)}")

    if not caps["Pages"]:
        print("::error::אין גישה לפרויקט ה-Pages — בלעדיה אי אפשר לקשר את המרחב")
        return 1
    if not caps["KV"]:
        print("::error::לטוקן אין הרשאת Workers KV Storage. "
              "יש להוסיף לו 'Account · Workers KV Storage · Edit' בדשבורד.")
        return 1

    print("\n=== משתני הסביבה בפרויקט ===")
    _, pbody = call(f"/accounts/{ACC}/pages/projects/{PROJECT}")
    pcfg = (pbody.get("result") or {}).get("deployment_configs", {}).get("production", {}) or {}
    pev = pcfg.get("env_vars") or {}
    pkv = pcfg.get("kv_namespaces") or {}
    for k in sorted(pev):
        v = pev[k] or {}
        has = v.get("value") not in (None, "")
        print(f"  {k:20s} type={str(v.get('type')):12s} ערך={'קיים' if has else 'מוסתר או ריק'}")
    print(f"  קישורי KV: {', '.join(pkv) or 'אין'}")

    if PROBE:
        print("\nPROBE=true — ההרשאות מספיקות, לא נוצר דבר. "
              "להרצה אמיתית: probe_only=false")
        return 0

    print("\n=== מרחב ה-KV ===")
    _, body = call(f"/accounts/{ACC}/storage/kv/namespaces?per_page=100")
    ns = next((n for n in (body.get("result") or []) if n["title"] == KV_TITLE), None)
    if ns:
        print(f"  קיים: {ns['id']}")
    else:
        code, body = call(f"/accounts/{ACC}/storage/kv/namespaces", "POST", {"title": KV_TITLE})
        if not body.get("success"):
            print(f"::error::יצירת המרחב נכשלה: {errs(body)}")
            return 1
        ns = body["result"]
        print(f"  נוצר: {ns['id']}")

    print("\n=== קישור לפרויקט וסודות ===")
    code, body = call(f"/accounts/{ACC}/pages/projects/{PROJECT}")
    if not body.get("success"):
        print(f"::error::קריאת הפרויקט נכשלה: {errs(body)}")
        return 1
    cfg = body["result"].get("deployment_configs", {}).get("production", {}) or {}
    have = cfg.get("env_vars") or {}
    have_kv = cfg.get("kv_namespaces") or {}

    # **נשלחים רק מפתחות שמוסיפים או משנים.** ה-API אינו מחזיר ערכים של
    # משתני secret_text — הם write-only — ולכן קריאת התצורה והחזרתה
    # ב-PATCH שולחת אותם בלי ערך ומאפסת אותם. כך נמחקו RESEND_API_KEY
    # ו-APPROVAL_SECRET בהרצה הראשונה, וההרשמה החזירה 503.
    env = {}
    kv = {}
    changed = []
    if have_kv.get(BINDING, {}).get("namespace_id") != ns["id"]:
        kv[BINDING] = {"namespace_id": ns["id"]}
        changed.append(f"binding {BINDING}")
    for key in ("SESSION_SECRET", "APPROVAL_SECRET"):
        if key not in have or os.environ.get(f"FORCE_{key}") == "1":
            env[key] = {"type": "secret_text", "value": secrets.token_urlsafe(48)}
            changed.append(key)

    # שחזור מפתח הדואר מתוך הסוד המקביל ב-GitHub. הוא נמחק מ-Pages
    # כשהגרסה הראשונה של הסקריפט החזירה משתני secret_text שנקראו בלי
    # ערך; המקור השני שרד, ולכן אין צורך ליצור מפתח חדש ב-Resend.
    resend = os.environ.get("RESEND_API_KEY", "").strip()
    if resend and os.environ.get("RESTORE_MAIL") == "1":
        env["RESEND_API_KEY"] = {"type": "secret_text", "value": resend}
        changed.append("RESEND_API_KEY")

    # SCAN_KEY נוצר ב-GitHub ומועתק לכאן, ולא נוצר כאן — שני הצדדים
    # חייבים אותו ערך: הסריקה שולחת אותו בכותרת, והממסר משווה אליו.
    # מפתח ה-API נדרש ב-Pages בשביל סקירת דוח לפי דרישה. הוא זהה לזה
    # שב-GitHub Secrets — לא נוצר כאן, רק מועתק.
    ak = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if ak and (have.get("ANTHROPIC_API_KEY") is None
               or os.environ.get("FORCE_ANTHROPIC_API_KEY") == "1"):
        env["ANTHROPIC_API_KEY"] = {"type": "secret_text", "value": ak}
        changed.append("ANTHROPIC_API_KEY")

    scan = os.environ.get("SCAN_KEY", "").strip()
    if scan and have.get("SCAN_KEY") is None:
        env["SCAN_KEY"] = {"type": "secret_text", "value": scan}
        changed.append("SCAN_KEY")
    elif scan and os.environ.get("FORCE_SCAN_KEY") == "1":
        env["SCAN_KEY"] = {"type": "secret_text", "value": scan}
        changed.append("SCAN_KEY (נכפה)")

    if not changed:
        print("  הכל כבר מוגדר.")
        return 0

    payload = {"deployment_configs": {"production": {}}}
    if env:
        payload["deployment_configs"]["production"]["env_vars"] = env
    if kv:
        payload["deployment_configs"]["production"]["kv_namespaces"] = kv
    code, body = call(f"/accounts/{ACC}/pages/projects/{PROJECT}", "PATCH", payload)
    if not body.get("success"):
        print(f"::error::עדכון הפרויקט נכשל: {errs(body)}")
        return 1
    print(f"  עודכן: {', '.join(changed)}")
    print("\nשים לב: משתני Pages נכנסים לתוקף רק בפריסה הבאה.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
