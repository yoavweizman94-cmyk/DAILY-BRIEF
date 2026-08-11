#!/usr/bin/env bash
# דחיפה בטוחה כשכמה workflows מקבעים לאותו ענף.
#
# הבעיה שנצפתה בפועל (ריצה 31494461643): maya-watch רץ כל רבע שעה ומקבע את
# data/state.sqlite. כששתי ריצות חופפות, `git pull --rebase` נופל על
# "CONFLICT (content): Merge conflict in data/state.sqlite" — קובץ בינארי
# שאין דרך למזג — הצעד מסתיים בקוד 1, וכל הסיכומים של אותו מחזור אובדים.
#
# ההכרעה: בקונפליקט על קובץ בינארי מנצחת הגרסה של הקומיט שמוחל (--theirs
# ברביס), שהיא המאוחרת והמצטברת יותר. מה שמפסידים הוא נקודת מחיר אחת של
# מחזור חופף; מה שמרוויחים הוא שהמחזור לא נופל כולו.
set -uo pipefail

BINARY_PATHS=("data/state.sqlite")
ATTEMPTS=4

resolve_binaries() {
  local resolved=1
  for p in "${BINARY_PATHS[@]}"; do
    if git ls-files -u -- "$p" | grep -q .; then
      git checkout --theirs -- "$p" 2>/dev/null || git checkout --ours -- "$p" 2>/dev/null || true
      git add -- "$p"
      resolved=0
      echo "  קונפליקט ב-$p נפתר לטובת הגרסה החדשה"
    fi
  done
  return $resolved
}

for i in $(seq 1 $ATTEMPTS); do
  if git pull --rebase origin main; then
    if git push; then
      echo "נדחף (ניסיון $i)"
      exit 0
    fi
    echo "הדחיפה נדחתה — מישהו הקדים. ניסיון נוסף."
    continue
  fi

  # ה-rebase נעצר. אם כל הקונפליקטים הם בקבצים הבינאריים המוכרים — נפתרים
  # וממשיכים; אחרת זו התנגשות אמיתית בקוד ואין לפתור אותה אוטומטית.
  if resolve_binaries && ! git diff --name-only --diff-filter=U | grep -q .; then
    GIT_EDITOR=true git rebase --continue || { git rebase --abort; continue; }
  else
    echo "קונפליקט שאינו בקובץ בינארי מוכר — לא נפתר אוטומטית" >&2
    git diff --name-only --diff-filter=U >&2
    git rebase --abort
    exit 1
  fi
done

echo "הדחיפה נכשלה אחרי $ATTEMPTS ניסיונות" >&2
exit 1
