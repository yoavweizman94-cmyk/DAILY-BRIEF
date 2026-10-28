# -*- coding: utf-8 -*-
"""דחיפה לריפו ממשימה שרצה במחשב: עסקאות מתואמות (gto_pull) והקלטות השיחות
(meetings_pull).

**שני שכפולים נפרדים לכל משימה, מחוץ לעץ העבודה.** output/ המקומי הוא שכפול
SSH ישן, ועץ העבודה של הפרויקט הוא מקום שבו עובדים — דחיפה אוטומטית ממנו
הייתה מערבבת קומיטים של המשימה בשינויים שטרם נשמרו. ושתי משימות שחולקות
שכפול אחד היו נתקעות זו על המנעול של זו כשהן רצות באותה דקה.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TLV-TASE-View"
CONTENT_URL = "https://github.com/yoavweizman94-cmyk/DAILY-BRIEF-content.git"
SITE_URL = "https://github.com/yoavweizman94-cmyk/DAILY-BRIEF.git"


class Repo:
    """שכפול רדוד ודליל של תיקייה אחת. **בכל ריצה מאפסים אל הענף המרוחק**
    ובונים את השינוי מחדש, כך שאין קומיטים מקומיים שמצטברים או מתנגשים."""

    def __init__(self, url: str, where: Path, sparse: str, author: str = "GTO local"):
        self.url, self.dir, self.sparse = url, where, sparse
        self.author = author

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        email = self.author.lower().replace(" ", "-") + "@users.noreply.github.com"
        r = subprocess.run(
            ["git", "-c", "credential.helper=", "-c", "credential.helper=wincred",
             "-c", "core.quotepath=false", "-c", f"user.name={self.author}",
             "-c", f"user.email={email}", *args],
            cwd=str(cwd or self.dir), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[:300]}")
        return r

    def sync(self) -> None:
        if not (self.dir / ".git").exists():
            self.dir.parent.mkdir(parents=True, exist_ok=True)
            self.git("clone", "--quiet", "--depth", "1", "--filter=blob:none", "--no-checkout",
                     self.url, str(self.dir), cwd=self.dir.parent)
            self.git("sparse-checkout", "set", "--no-cone", self.sparse)
        self.git("fetch", "--quiet", "--depth", "1", "origin", "main")
        self.git("checkout", "--quiet", "-B", "main", "origin/main")
        self.git("reset", "--quiet", "--hard", "origin/main")

    def commit_push(self, message: str, apply, paths: list[str]) -> bool:
        """apply() כותב את השינוי על העותק העדכני. False — אין מה לדחוף."""
        for attempt in range(4):
            self.sync()
            apply(self.dir)
            self.git("add", "--", *paths)
            if self.git("diff", "--cached", "--quiet", check=False).returncode == 0:
                return False
            self.git("commit", "--quiet", "-m", message)
            if self.git("push", "--quiet", "origin", "HEAD:main", check=False).returncode == 0:
                return True
            time.sleep(5 * (attempt + 1))   # מישהו דחף בינתיים — מאפסים ובונים מחדש
        raise RuntimeError("הדחיפה נכשלה ארבע פעמים")
