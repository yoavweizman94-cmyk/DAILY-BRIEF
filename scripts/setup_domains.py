# -*- coding: utf-8 -*-
"""הקמת ההפרדה בין האפקס הציבורי לאפליקציה המוגנת, דרך ה-API של Cloudflare.

רץ מתוך GitHub Actions כי הטוקן שמור שם כסוד.

סדר הפעולות נבחר כך שלא ייווצר רגע שבו התוכן חשוף: ההגנה על
app.tlvtaseview.com נוצרת ומאומתת לפני שההגנה מוסרת מהאפקס, ושחרור
האפקס נעשה רק בהרצה נפרדת עם דגל מפורש.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

CF = "https://api.cloudflare.com/client/v4"
APEX = "tlvtaseview.com"
APP = "app.tlvtaseview.com"
PROJECT = "forest-brief"

TOKEN = os.environ["CF_TOKEN"]
ACCOUNT = os.environ["CF_ACCOUNT"]
OWNER = os.environ["OWNER"].strip().lower()
RELEASE_APEX = os.environ.get("RELEASE", "false").lower() == "true"


def call(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        CF + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def ok(code: int) -> bool:
    return code in (200, 201)


def fail(msg: str):
    print(f"::error::{msg}")
    sys.exit(1)


def zone_id() -> str:
    code, d = call("GET", "/zones")
    for z in d.get("result") or []:
        if z["name"] == APEX:
            return z["id"]
    fail(f"לא נמצא zone עבור {APEX}")


def main() -> int:
    zid = zone_id()
    print(f"zone: {zid}")

    # --- ניקוי שאריות מבדיקות קודמות ---------------------------------------
    code, apps = call("GET", f"/accounts/{ACCOUNT}/access/apps")
    for a in apps.get("result") or []:
        if a.get("domain", "").startswith("probe."):
            call("DELETE", f"/accounts/{ACCOUNT}/access/apps/{a['id']}")
            print(f"נמחקה אפליקציית בדיקה: {a['domain']}")

    # --- רשומת DNS ל-app ----------------------------------------------------
    code, recs = call("GET", f"/zones/{zid}/dns_records?name={APP}")
    if ok(code) and (recs.get("result") or []):
        print(f"רשומת DNS ל-{APP} כבר קיימת")
    else:
        code, r = call("POST", f"/zones/{zid}/dns_records", {
            "type": "CNAME", "name": "app", "content": f"{PROJECT}.pages.dev",
            "proxied": True, "ttl": 1,
            "comment": "TLV TASE View — האפליקציה המוגנת"})
        if not ok(code):
            fail(f"יצירת רשומת DNS נכשלה: {json.dumps(r, ensure_ascii=False)[:300]}")
        print(f"נוצרה רשומת CNAME: {APP} → {PROJECT}.pages.dev (proxied)")

    # --- חיבור הדומיין לפרויקט ---------------------------------------------
    base = f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}/domains"
    code, d = call("GET", base)
    have = {x.get("name") for x in (d.get("result") or [])}
    if APP in have:
        print(f"{APP} כבר מחובר לפרויקט")
    else:
        code, r = call("POST", base, {"name": APP})
        if not ok(code):
            fail(f"חיבור {APP} נכשל: {json.dumps(r, ensure_ascii=False)[:300]}")
        print(f"{APP} חובר לפרויקט")

    # --- הגנת Access על האפליקציה ------------------------------------------
    code, apps = call("GET", f"/accounts/{ACCOUNT}/access/apps")
    by_domain = {a.get("domain"): a for a in (apps.get("result") or [])}
    app_id = None
    if APP in by_domain:
        app_id = by_domain[APP]["id"]
        print(f"הגנת Access על {APP} כבר קיימת")
    else:
        code, r = call("POST", f"/accounts/{ACCOUNT}/access/apps", {
            "name": "TLV TASE View", "domain": APP, "type": "self_hosted",
            "session_duration": "720h",
            "policies": [{"name": "approved", "decision": "allow",
                          "include": [{"email": {"email": OWNER}}]}]})
        if not ok(code):
            fail(f"יצירת הגנת Access נכשלה: {json.dumps(r, ensure_ascii=False)[:400]}")
        app_id = r["result"]["id"]
        print(f"נוצרה הגנת Access על {APP} · מורשה: {OWNER}")

    print(f"\nACCESS_APP_ID={app_id}")

    # --- אימות בפועל --------------------------------------------------------
    time.sleep(20)
    import ssl
    ctx = ssl.create_default_context()

    def probe(host):
        try:
            req = urllib.request.Request(f"https://{host}/", method="GET")
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                return r.status, r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.url
        except Exception as e:
            return 0, type(e).__name__

    for host in (APP, APEX):
        st, where = probe(host)
        guarded = "cloudflareaccess.com" in str(where)
        print(f"  {host}: {st} · {'מוגן' if guarded else 'פתוח'}")

    # --- שחרור האפקס, רק בדגל מפורש ----------------------------------------
    if RELEASE_APEX:
        st, where = probe(APP)
        if "cloudflareaccess.com" not in str(where):
            fail("האפליקציה אינה מוגנת עדיין — לא משחררים את האפקס")
        if APEX in by_domain:
            code, r = call("DELETE", f"/accounts/{ACCOUNT}/access/apps/{by_domain[APEX]['id']}")
            if not ok(code):
                fail(f"הסרת ההגנה מהאפקס נכשלה: {json.dumps(r, ensure_ascii=False)[:300]}")
            print(f"ההגנה הוסרה מ-{APEX} — עמוד הנחיתה ציבורי")
        else:
            print(f"לא נמצאה הגנה על {APEX}")
    else:
        print("\nהאפקס נשאר מוגן. להריץ שוב עם release_apex=true אחרי אימות.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
