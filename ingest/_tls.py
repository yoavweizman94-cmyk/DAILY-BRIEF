# -*- coding: utf-8 -*-
"""התמודדות עם פרוקסי ארגוני שמיירט TLS (תעודות חתומות ע"י CA פנימי).

harden() עושה שניים:
1. truststore — מפנה את stdlib ssl/requests לחנות התעודות של מערכת ההפעלה.
2. ב-Windows: בונה bundle משולב (certifi + חנויות ROOT/CA של Windows) ומכוון אליו
   את CURL_CA_BUNDLE — זה מה ש-curl_cffi (וממנו yfinance) קורא.

ב-Linux/CI אין יירוט — הפונקציה לא מזיקה.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def harden() -> None:
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:
        pass

    if sys.platform != "win32" or os.environ.get("CURL_CA_BUNDLE"):
        return
    try:
        import ssl
        import certifi
        pem = [Path(certifi.where()).read_text(encoding="utf-8")]
        for store in ("ROOT", "CA"):
            for cert, enc, _trust in ssl.enum_certificates(store):
                if enc == "x509_asn":
                    pem.append(ssl.DER_cert_to_PEM_cert(cert))
        bundle = Path(tempfile.gettempdir()) / "forest_ca_bundle.pem"
        bundle.write_text("\n".join(pem), encoding="utf-8")
        os.environ["CURL_CA_BUNDLE"] = str(bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(bundle))
    except Exception:
        pass
