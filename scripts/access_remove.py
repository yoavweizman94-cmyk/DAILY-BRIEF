#!/usr/bin/env python3
"""הסרת Cloudflare Access מהאפליקציה, עם שחזור אוטומטי בכישלון.

ההגנה עוברת לאימות עצמי ב-Pages Functions, ולכן אפליקציית ה-Access
מיותרת — אבל הסרתה היא הרגע היחיד שבו התוכן עלול להיחשף אם השער החדש
אינו עובד. לכן הסדר כאן הוא: לגבות את התצורה, למחוק, לבדוק מיד את
האתר החי, ואם התוכן דולף — להקים את ההגנה הישנה בחזרה ולצאת בשגיאה.

DRY_RUN=1 מדפיס את התצורה ואינו נוגע בדבר.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
TOK = os.environ["CF_TOKEN"]
ACC = os.environ["CF_ACCOUNT"]
APP_HOST = "app.tlvtaseview.com"
DRY = os.environ.get("DRY_RUN") == "1"


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


def probe():
    """מחזיר (יעד סופי, האם גוף הברייף דלף)."""
    req = urllib.request.Request(f"https://{APP_HOST}/", headers={
        "User-Agent": "Mozilla/5.0 (compatible; tlv-access-check)"})
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode("utf-8", "replace")
            return r.geturl(), ('class="toc"' in body or "דיווחי מאיה" in body)
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", False
    except Exception as e:
        return f"שגיאה: {type(e).__name__}", False


def main():
    code, body = call(f"/accounts/{ACC}/access/apps")
    if not body.get("success"):
        print(f"::error::קריאת אפליקציות Access נכשלה: {body}")
        return 1
    apps = [a for a in body.get("result", []) if APP_HOST in (a.get("domain") or "")]
    if not apps:
        print("לא נמצאה אפליקציית Access על האפליקציה — כנראה כבר הוסרה.")
        eff, leaked = probe()
        print(f"  בדיקה: יעד={eff}  דליפה={'כן' if leaked else 'לא'}")
        return 1 if leaked else 0

    app = apps[0]
    _, pol = call(f"/accounts/{ACC}/access/apps/{app['id']}/policies")
    policies = pol.get("result") or []
    backup = {"app": app, "policies": policies}
    print(f"אפליקציה: {app['name']}  ({app['id']})")
    print(f"  domain: {app.get('domain')}")
    print(f"  מדיניות: {len(policies)}")
    with open("access-backup.json", "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    print("  גיבוי נשמר ב-access-backup.json")

    if DRY:
        print("\nDRY_RUN=1 — לא נמחק דבר.")
        return 0

    print("\nמוחק…")
    code, body = call(f"/accounts/{ACC}/access/apps/{app['id']}", "DELETE")
    if not (body.get("success") or 200 <= code < 300):
        print(f"::error::המחיקה נכשלה: {body}")
        return 1
    print("  נמחק. ממתין להתפשטות…")
    time.sleep(20)

    eff, leaked = probe()
    print(f"\nבדיקה אחרי ההסרה: יעד={eff}")
    gated = "/login" in eff or "HTTP 30" in eff
    if leaked or not gated:
        print("::error::השער החדש אינו חוסם — מחזיר את ההגנה הישנה")
        payload = {k: v for k, v in app.items()
                   if k in ("name", "domain", "type", "session_duration",
                            "app_launcher_visible", "allowed_idps",
                            "auto_redirect_to_identity")}
        code, nb = call(f"/accounts/{ACC}/access/apps", "POST", payload)
        if nb.get("success"):
            new_id = nb["result"]["id"]
            for p in policies:
                call(f"/accounts/{ACC}/access/apps/{new_id}/policies", "POST",
                     {k: v for k, v in p.items()
                      if k in ("name", "decision", "include", "exclude", "require")})
            print(f"  ההגנה הישנה שוחזרה ({new_id}).")
        else:
            print(f"::error::גם השחזור נכשל: {nb}. יש להקים Access ידנית מייד.")
        return 1

    print("  השער החדש חוסם ✓  התוכן לא דלף ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
