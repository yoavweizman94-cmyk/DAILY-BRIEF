#!/usr/bin/env bash
# דחיפה בטוחה כשכמה workflows מקבעים לאותו ענף.
#
# שתי תקלות אמת שהובילו לקובץ הזה:
# - ריצה 31494461643: maya-watch רץ כל רבע שעה ומקבע את data/state.sqlite.
#   שתי ריצות חופפות → "CONFLICT (content)" על קובץ בינארי שאין דרך למזג,
#   הצעד נופל, וכל הסיכומים של המחזור אובדים.
# - ריצה 31568684938: מהדורת הבוקר הופקה במלואה ואז נפלה על קונפליקט
#   ב-output/calls/upcoming.json. הברייף כבר היה כתוב — ואבד.
#
# ההכללה הנכונה אינה "קבצים בינאריים" אלא **תוצרים מחוללים**: קבצים שאף
# אחד לא כותב ביד, שנבנים מחדש בכל ריצה, ושהגרסה המאוחרת שלהם היא הנכונה
# מעצם הגדרתם. בהם הקונפליקט נפתר לטובת הקומיט שמוחל (--theirs ברביס).
# בכל קובץ אחר — קוד, קונפיג, ברייף — הסקריפט עוצר במפורש ואינו מנחש.
set -uo pipefail

GENERATED_PATHS=(
  "data/state.sqlite"              # היסטוריית מחירים + IDs שדווחו
  "data/calls_links.json"          # קאש קישורי שיחות ועידה
  "data/maya_index_state.json"     # מצב מילוי היסטוריית הדוחות
  "output/calls/upcoming.json"     # לוח שיחות — נבנה מה-API בכל ריצה
  "output/filings/manifest.json"   # נגזר לחלוטין מקובצי השנה
)
ATTEMPTS=4

resolve_generated() {
  local resolved=1
  for p in "${GENERATED_PATHS[@]}"; do
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

  # ה-rebase נעצר. אם כל הקונפליקטים הם בתוצרים מחוללים — נפתרים וממשיכים;
  # אחרת זו התנגשות אמיתית שאין לפתור אותה בניחוש.
  if resolve_generated && ! git diff --name-only --diff-filter=U | grep -q .; then
    GIT_EDITOR=true git rebase --continue || { git rebase --abort; continue; }
  else
    echo "קונפליקט בקובץ שאינו תוצר מחולל — לא נפתר אוטומטית" >&2
    git diff --name-only --diff-filter=U >&2
    git rebase --abort
    exit 1
  fi
done

echo "הדחיפה נכשלה אחרי $ATTEMPTS ניסיונות" >&2
exit 1
