#!/usr/bin/env python3
"""ניהול משתמשי TLV TASE View מול מרחב ה-KV.

הטופס באתר יודע רק ליצור חשבון ממתין, וקישור האישור רק להפעיל אותו.
כל השאר — רשימה, השבתה, מחיקה, ואיפוס סיסמה — נעשה כאן.

    ACTION=list                       python scripts/users.py
    ACTION=show   EMAIL=a@b.com       python scripts/users.py
    ACTION=activate EMAIL=a@b.com     python scripts/users.py
    ACTION=disable  EMAIL=a@b.com     python scripts/users.py
    ACTION=delete   EMAIL=a@b.com     python scripts/users.py
    ACTION=setpw  EMAIL=a@b.com PASSWORD=...   python scripts/users.py
    ACTION=seed   EMAIL=a@b.com PASSWORD=... [NAME=...]  python scripts/users.py

הגיבוב חייב להיות זהה למימוש ב-site/functions/_lib/auth.js — PBKDF2-SHA256,
210,000 סבבים, מלח של 16 בתים, פלט 32 בתים, קידוד base64url בלי ריפוד.
"""
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
# חייב להיות זהה ל-site/functions/_lib/auth.js: Workers חוסם PBKDF2 מעל
# 100,000 סבבים בקריאה אחת, ולכן הגזירה משורשרת בשני המימושים.
ROUND_ITERS = 100000
ROUNDS = 3
ITERATIONS = ROUND_ITERS * ROUNDS
KEYLEN = 32

TOK = os.environ["CF_TOKEN"]
ACC = os.environ["CF_ACCOUNT"]
NS = os.environ["KV_NAMESPACE_ID"]
BASE = f"{API}/accounts/{ACC}/storage/kv/namespaces/{NS}"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def unb64url(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4))


def hash_password(password: str, salt: bytes | None = None):
    salt = salt or secrets.token_bytes(16)
    out = password.encode()
    for _ in range(ROUNDS):
        out = hashlib.pbkdf2_hmac("sha256", out, salt, ROUND_ITERS, KEYLEN)
    return b64url(out), b64url(salt)


def call(path, method="GET", data=None, ctype="application/json"):
    req = urllib.request.Request(
        f"{BASE}{path}", method=method,
        headers={"Authorization": f"Bearer {TOK}", "Content-Type": ctype},
        data=data)
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def get_user(email):
    code, body = call(f"/values/user:{email}")
    if code != 200:
        return None
    return json.loads(body)


def put_user(email, user):
    code, body = call(f"/values/user:{email}", "PUT",
                      json.dumps(user).encode(), "text/plain")
    if code >= 300:
        print(f"::error::כתיבה נכשלה: {code} {body[:200]}")
        return False
    return True


def mask_email(e: str) -> str:
    """כתובת בצורה שמאפשרת זיהוי בידי מי שמכיר אותה, ולא בידי אחר."""
    local, _, dom = (e or "").partition("@")
    keep = local[:2] if len(local) > 3 else local[:1]
    return f"{keep}{'*' * max(1, len(local) - len(keep))}@{dom}"


def redact(u):
    return {k: v for k, v in u.items() if k not in ("hash", "salt")}


def main():
    action = os.environ.get("ACTION", "list")
    email = os.environ.get("EMAIL", "").strip().lower()
    password = os.environ.get("PASSWORD", "")

    if action == "list":
        code, body = call("/keys?limit=1000")
        if code != 200:
            print(f"::error::{code} {body[:200]}")
            return 1
        keys = [k["name"] for k in json.loads(body).get("result", [])
                if k["name"].startswith("user:")]
        print(f"משתמשים: {len(keys)}")
        by_status = {}
        masked = []
        for k in sorted(keys):
            u = get_user(k[5:]) or {}
            st = u.get("status", "?")
            by_status[st] = by_status.get(st, 0) + 1
            print(f"  {st:8s} {k[5:]:38s} "
                  f"{u.get('name','')[:22]:24s} נכנס לאחרונה: {u.get('lastLogin') or '—'}")
            masked.append(f"{st}:{mask_email(k[5:])}")

        # **ספירות ומזהים ממוסכים בלבד לאנוטציה.** הלוג של הריצה דורש
        # אימות ולכן הוא פרטי, אבל אנוטציות בריפו ציבורי גלויות לכל —
        # ורשימת המשתמשים היא כתובות של אנשים אמיתיים. המיסוך מאפשר
        # לאבחן "האם ההרשמה נקלטה" בלי לפרסם את הכתובת.
        summary = " · ".join(f"{k}: {v}" for k, v in sorted(by_status.items()))
        print(f"::notice title=מצב המשתמשים::סה\"כ {len(keys)} — "
              f"{summary or 'אין'}%0A" + "%0A".join(masked))
        return 0

    if not email:
        print("::error::נדרש EMAIL")
        return 1

    if action == "show":
        u = get_user(email)
        if not u:
            print(f"לא נמצא: {email}")
            return 1
        print(json.dumps(redact(u), ensure_ascii=False, indent=2))
        return 0

    if action == "delete":
        code, body = call(f"/values/user:{email}", "DELETE")
        print(f"מחיקה: {'בוצעה' if code < 300 else code}")
        # אימות מול השרת ולא הנחה
        return 0 if get_user(email) is None else 1

    if action in ("activate", "disable"):
        u = get_user(email)
        if not u:
            print(f"::error::לא נמצא: {email}")
            return 1
        u["status"] = "active" if action == "activate" else "disabled"
        if action == "activate" and not u.get("approved"):
            u["approved"] = "manual"
        ok = put_user(email, u)
        after = get_user(email)
        print(f"{email} → {after.get('status') if after else '?'}")
        return 0 if ok and after and after["status"] == u["status"] else 1

    if action in ("setpw", "seed"):
        if len(password) < 10:
            print("::error::נדרשת PASSWORD באורך 10 לפחות")
            return 1
        u = get_user(email) or {
            "name": os.environ.get("NAME") or email.split("@")[0], "org": "", "why": "", "email": email,
            "created": "seeded", "approved": None, "lastLogin": None,
        }
        h, s = hash_password(password)
        u.update({"hash": h, "salt": s, "iterations": ITERATIONS})
        # NAME חל גם על משתמש קיים: חשבון שנוצר ידנית מקבל את שם ברירת
        # המחדל של הכלי, ואין דרך אחרת לתקן אותו.
        if os.environ.get("NAME"):
            u["name"] = os.environ["NAME"]
        if action == "seed":
            u["status"] = "active"
            u["approved"] = "seeded"
        ok = put_user(email, u)
        print(f"{email}: סיסמה עודכנה, מצב={u.get('status')}")
        return 0 if ok else 1

    print(f"::error::פעולה לא מוכרת: {action}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
