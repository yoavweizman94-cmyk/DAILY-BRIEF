#!/usr/bin/env bash
# ריפו התוכן הפרטי, שמותקן כ-output/ בתוך עץ העבודה.
#
# למה כך: כל הסקריפטים באתר ובצנרת קוראים וכותבים נתיבי output/... .
# שכפול הריפו הפרטי בדיוק לנתיב הזה משאיר את כולם עובדים בלי שינוי,
# ובמקום זאת רק פעולות הגיט מתחלפות.
#
# הקוד נשאר בריפו הציבורי (ולכן ה-CI חינם), והמחקר יושב בפרטי.
set -uo pipefail

REMOTE="git@github.com:yoavweizman94-cmyk/DAILY-BRIEF-content.git"
DIR="output"

setup_key() {
  [ -n "${CONTENT_DEPLOY_KEY:-}" ] || { echo "CONTENT_DEPLOY_KEY חסר" >&2; return 1; }
  mkdir -p ~/.ssh
  printf '%s\n' "$CONTENT_DEPLOY_KEY" > ~/.ssh/content_key
  chmod 600 ~/.ssh/content_key
  ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null
  export GIT_SSH_COMMAND="ssh -i ~/.ssh/content_key -o IdentitiesOnly=yes"
}

case "${1:-}" in
  pull)
    setup_key || exit 1
    rm -rf "$DIR"
    git clone --quiet "$REMOTE" "$DIR" || { echo "שכפול ריפו התוכן נכשל" >&2; exit 1; }
    echo "ריפו התוכן נמשך: $(git -C "$DIR" log --oneline | wc -l) קומיטים"
    ;;
  push)
    setup_key || exit 1
    cd "$DIR" || exit 1
    git config user.name "forest-brief-bot"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git add -A
    git diff --cached --quiet && { echo "אין שינוי בתוכן"; exit 0; }
    git commit -q -m "${2:-content update} $(date +'%F %H:%M')"
    # שתי ריצות יכולות לכתוב במקביל (daily-brief ו-maya-watch בקבוצות
    # concurrency נפרדות). ניסיון חוזר עם rebase, ובקונפליקט על תוצר
    # מחולל מנצחת הגרסה החדשה — אותה הכרעה כמו ב-git_sync.sh.
    for i in 1 2 3 4; do
      if git pull --rebase --quiet origin main 2>/dev/null; then
        git push --quiet origin main && { echo "התוכן נדחף (ניסיון $i)"; exit 0; }
      else
        for p in filings/manifest.json calls/upcoming.json; do
          git ls-files -u -- "$p" | grep -q . && { git checkout --theirs -- "$p" 2>/dev/null || true; git add -- "$p"; }
        done
        if git diff --name-only --diff-filter=U | grep -q .; then
          echo "קונפליקט שאינו בתוצר מחולל" >&2
          git diff --name-only --diff-filter=U >&2
          git rebase --abort; exit 1
        fi
        GIT_EDITOR=true git rebase --continue >/dev/null 2>&1 || git rebase --abort
      fi
    done
    echo "דחיפת התוכן נכשלה" >&2; exit 1
    ;;
  *)
    echo "שימוש: content_repo.sh pull|push [הודעת קומיט]" >&2; exit 2 ;;
esac
