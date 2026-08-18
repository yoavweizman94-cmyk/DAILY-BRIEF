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


def ok(code: int, body=None) -> bool:
    """הצלחה נקבעת לפי גוף התשובה, לא לפי ניחוש קודי סטטוס.

    Cloudflare מחזיר 200 ליצירה אחת, 201 לאחרת ו-202 למחיקה, ובדיקה
    שמונה קודים ידנית פסלה כאן פעמיים פעולות שהצליחו — פעם POST של Access
    שחזר 201, ופעם DELETE שחזר עם success:true. השדה success הוא הסמכות.
    """
    if isinstance(body, dict) and "success" in body:
        return bool(body["success"])
    return 200 <= code < 300


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
    if ok(code, recs) and (recs.get("result") or []):
        print(f"רשומת DNS ל-{APP} כבר קיימת")
    else:
        code, r = call("POST", f"/zones/{zid}/dns_records", {
            "type": "CNAME", "name": "app", "content": f"{PROJECT}.pages.dev",
            "proxied": True, "ttl": 1,
            "comment": "TLV TASE View — האפליקציה המוגנת"})
        if not ok(code, r):
            fail(f"יצירת רשומת DNS נכשלה: {json.dumps(r, ensure_ascii=False)[:300]}")
        print(f"נוצרה רשומת CNAME: {APP} → {PROJECT}.pages.dev (proxied)")

    # www — בלי רשומה, כל מי שמקליד אותו מקבל שגיאת רשת
    code, recs = call("GET", f"/zones/{zid}/dns_records?name=www.{APEX}")
    if ok(code, recs) and (recs.get("result") or []):
        print("רשומת DNS ל-www כבר קיימת")
    else:
        code, r = call("POST", f"/zones/{zid}/dns_records", {
            "type": "CNAME", "name": "www", "content": f"{PROJECT}.pages.dev",
            "proxied": True, "ttl": 1, "comment": "TLV TASE View — www"})
        print("נוצרה רשומת www" if ok(code, r) else f"www נכשל: {str(r)[:200]}")

    # --- חיבור הדומיין לפרויקט ---------------------------------------------
    base = f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}/domains"
    code, d = call("GET", base)
    have = {x.get("name") for x in (d.get("result") or [])}
    for host in (APP, f"www.{APEX}"):
        if host in have:
            print(f"{host} כבר מחובר לפרויקט")
            continue
        code, r = call("POST", base, {"name": host})
        if not ok(code, r):
            if host == APP:
                fail(f"חיבור {host} נכשל: {json.dumps(r, ensure_ascii=False)[:300]}")
            print(f"חיבור {host} נכשל (לא קריטי): {str(r)[:150]}")
        else:
            print(f"{host} חובר לפרויקט")

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
        if not ok(code, r):
            fail(f"יצירת הגנת Access נכשלה: {json.dumps(r, ensure_ascii=False)[:400]}")
        app_id = r["result"]["id"]
        print(f"נוצרה הגנת Access על {APP} · מורשה: {OWNER}")

    print(f"\nACCESS_APP_ID={app_id}")

    # --- אימות בפועל --------------------------------------------------------
    time.sleep(20)

    def probe(host):
        """האם המארח מגיש את התוכן שלנו, או שמשהו חוסם לפניו.

        זיהוי לפי הפניה ל-cloudflareaccess.com אינו אמין: Access מחזיר 403
        ישירות לבקשה שאינה נראית כדפדפן, ואז נראה כאילו אין הגנה. הבדיקה
        ההפוכה חד-משמעית — אם הגוף מכיל סמן של האתר שלנו, הוא מוגש.
        """
        req = urllib.request.Request(f"https://{host}/", headers={
            "User-Agent": "Mozilla/5.0 (compatible; setup-check)"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read(4000).decode("utf-8", "replace")
                served = ('class="tile"' in body or "TLV TASE View" in body
                          or "ברייף" in body)
                return r.status, served, r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, False, getattr(e, "url", "")
        except Exception as e:
            return 0, False, type(e).__name__

    status = {}
    for host in (APP, APEX):
        st, served, where = probe(host)
        status[host] = served
        print(f"  {host}: HTTP {st} · {'מגיש תוכן' if served else 'חסום'}"
              + (f" · {where}" if "cloudflareaccess" in str(where) else ""))

    # --- שחרור האפקס, רק בדגל מפורש ----------------------------------------
    if RELEASE_APEX:
        if status.get(APP):
            fail("האפליקציה מגישה תוכן ללא הזדהות — לא משחררים את האפקס")
        if APEX in by_domain:
            code, r = call("DELETE", f"/accounts/{ACCOUNT}/access/apps/{by_domain[APEX]['id']}")
            if not ok(code, r):
                fail(f"הסרת ההגנה מהאפקס נכשלה: {json.dumps(r, ensure_ascii=False)[:300]}")
            print(f"ההגנה הוסרה מ-{APEX} — עמוד הנחיתה ציבורי")
        else:
            print(f"לא נמצאה הגנה על {APEX}")
    else:
        print("\nהאפקס נשאר מוגן. להריץ שוב עם release_apex=true אחרי אימות.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
