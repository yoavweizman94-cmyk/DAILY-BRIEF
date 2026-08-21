# -*- coding: utf-8 -*-
"""אבחון גישה ל-govmap.gov.il, להרצה על ראנר של GitHub.

הצורך: הסריקה עובדת מתחנת עבודה ומחזירה 403 על כל 34 הערים מ-CI. יש
לכך שלושה הסברים אפשריים — טביעת TLS, היעדר עוגיות WAF, או חסימת טווח
IP של ספק ענן — והם דורשים תיקונים שונים לחלוטין. ניחוש עולה ריצה של
עשרים דקות לכל ניסיון, ולכן כאן נבדקות כל האסטרטגיות בבת אחת.

הפלט הוא קוד HTTP לכל צירוף. אם **כולם** 403, החסימה אינה בצד הלקוח.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from _tls import harden  # noqa: E402

harden()

HOME = "https://www.govmap.gov.il/"
API = "https://www.govmap.gov.il/api"
DEALS = f"{API}/real-estate/deals/3874000,3671000/1000"
AC = f"{API}/search-service/autocomplete"

HEADERS = {
    "Accept": "application/json",
    "Referer": HOME,
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"),
}


def show(label: str, fn) -> None:
    try:
        r = fn()
        body = (r.text or "")[:110].replace("\n", " ")
        print(f"  {label:34s} {r.status_code}  {body}")
    except Exception as e:  # noqa: BLE001 — כל כשל הוא תוצאה לגיטימית כאן
        print(f"  {label:34s} —    {type(e).__name__}: {e}")


def main() -> int:
    print("== requests רגיל ==")
    import requests
    s = requests.Session()
    s.headers.update(HEADERS)
    show("deals", lambda: s.get(DEALS, timeout=30))

    from curl_cffi import requests as creq
    for imp in ("chrome", "chrome124", "safari", "edge99"):
        print(f"== curl_cffi impersonate={imp} ==")
        try:
            c = creq.Session(impersonate=imp)
        except Exception as e:  # noqa: BLE001
            print(f"  פרופיל לא נתמך: {type(e).__name__}: {e}")
            continue
        c.headers.update(HEADERS)
        show("deals (בלי עוגיות)", lambda: c.get(DEALS, timeout=30))

        # זריעת עוגיות WAF מדף הבית — מה שפתר את מאיה ורמ"י
        try:
            h = c.get(HOME, timeout=30)
            print(f"  דף הבית                            {h.status_code}  "
                  f"עוגיות: {len(c.cookies)}")
        except Exception as e:  # noqa: BLE001
            print(f"  דף הבית                            —    {type(e).__name__}")
        show("deals (אחרי עוגיות)", lambda: c.get(DEALS, timeout=30))
        show("autocomplete (אחרי עוגיות)",
             lambda: c.post(AC, json={"searchText": "אבן גבירול 68 תל אביב",
                                      "language": "he", "isAccurate": False,
                                      "maxResults": 5},
                            headers={"Content-Type": "application/json"}, timeout=30))

    # אם החסימה היא לפי טווח כתובות, השאלה היחידה שנותרה היא מאיזו רשת
    # כן אפשר לסרוק. Cloudflare הוא התשתית היחידה שכבר בידינו.
    print("== דרך Cloudflare ==")
    show("api/govmap-probe",
         lambda: creq.get("https://app.tlvtaseview.com/api/govmap-probe",
                          timeout=45))

    print("\nכתובת היציאה של הראנר:")
    try:
        print("  ", creq.get("https://api.ipify.org", timeout=20).text)
    except Exception as e:  # noqa: BLE001
        print("  לא נקבעה:", type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
