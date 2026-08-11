# -*- coding: utf-8 -*-
"""עוטף להרצת שרת ה-MCP של nadlan-mcp (vendor/) עם הגדרות ה-TLS של הפרויקט.

השרת עצמו משתמש ב-requests רגיל. במחשב עם פרוקסי ארגוני שמיירט TLS זה נכשל
ב-CERTIFICATE_VERIFY_FAILED מול govmap.gov.il, כי תהליך ה-MCP הוא subprocess של
claude ואינו יורש את ה-CA bundle ש-ingest/_tls.py בונה. כאן קוראים ל-harden()
לפני שהשרת מייבא ssl/requests, ואז מריצים אותו כרגיל.

ב-CI (לינוקס, בלי יירוט) harden() לא מזיק, ולכן זה נתיב ההרצה היחיד — אין
צורך בשתי תצורות.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "nadlan-mcp"
ENTRY = VENDOR / "run_fastmcp_server.py"

sys.path.insert(0, str(ROOT / "ingest"))
from _tls import harden  # noqa: E402

harden()

if not ENTRY.exists():
    # stderr בלבד: stdout הוא ערוץ ה-JSON-RPC ופלט זר בו שובר את הפרוטוקול
    print(f"nadlan-mcp לא נמצא ב-{VENDOR} — הרץ clone לפי run_daily.sh",
          file=sys.stderr)
    raise SystemExit(1)

sys.path.insert(0, str(VENDOR))
runpy.run_path(str(ENTRY), run_name="__main__")
