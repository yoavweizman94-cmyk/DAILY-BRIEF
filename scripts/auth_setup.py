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
    env = dict(cfg.get("env_vars") or {})
    kv = dict(cfg.get("kv_namespaces") or {})

    changed = []
    if kv.get(BINDING, {}).get("namespace_id") != ns["id"]:
        kv[BINDING] = {"namespace_id": ns["id"]}
        changed.append(f"binding {BINDING}")
    if not env.get("SESSION_SECRET"):
        env["SESSION_SECRET"] = {"type": "secret_text", "value": secrets.token_urlsafe(48)}
        changed.append("SESSION_SECRET")

    if not changed:
        print("  הכל כבר מוגדר.")
        return 0

    code, body = call(f"/accounts/{ACC}/pages/projects/{PROJECT}", "PATCH",
                      {"deployment_configs": {"production": {"env_vars": env, "kv_namespaces": kv}}})
    if not body.get("success"):
        print(f"::error::עדכון הפרויקט נכשל: {errs(body)}")
        return 1
    print(f"  עודכן: {', '.join(changed)}")
    print("\nשים לב: משתני Pages נכנסים לתוקף רק בפריסה הבאה.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
