#!/usr/bin/env bash
# FOREST Daily Brief — ingestion → Claude → רינדור אתר → טלגרם
# מקור שנכשל לא עוצר את הצנרת; הסוכן מדווח עליו בסעיף "תקלות מקורות".
set -uo pipefail
cd "$(dirname "$0")"

DATE="${BRIEF_DATE:-$(date +%F)}"
RAW="data/raw/$DATE"
mkdir -p "$RAW"
FAILED=()

run_source() {
  local name="$1"; shift
  if "$@"; then
    echo "[$name] OK"
  else
    echo "[$name] FAILED (exit $?)"
    FAILED+=("$name")
  fi
}

echo "=== FOREST daily brief · $DATE ==="
run_source feedly  python ingest/feedly_pull.py
run_source gmail   python ingest/gmail_pull.py
run_source maya    python ingest/maya_pull.py
run_source markets python ingest/markets_pull.py
run_source rmi     python ingest/rmi_pull.py
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "מקורות שנכשלו: ${FAILED[*]}"
fi

# ה-clone של remy-mcp משמש רק לטבלת קודי היישוב שבו (data/kod_yeshuv.py),
# ש-rmi_pull.py מייבא כדי לתרגם KodYeshuv לשם יישוב. שרת ה-MCP עצמו אינו בשימוש:
# ה-API של רמ"י חוסם את requests שהוא משתמש בו. rmi_pull עובד גם בלי ה-clone,
# אבל אז יישובים יופיעו כקודים מספריים.
if [ ! -d vendor/remy-mcp ]; then
  git clone --depth 1 https://github.com/barvhaim/remy-mcp vendor/remy-mcp || \
    echo "אזהרה: clone של remy-mcp נכשל — שמות יישובים יוצגו כקודים"
fi

PROMPT="היום $DATE. בצע את הפייפליין היומי לפי CLAUDE.md: קרא את config/companies.yaml \
ואת הקבצים ב-data/raw/$DATE/, הפעל את הסקילים israeli-statistics ו-israeli-land-tenders \
לבדיקת פרסומי למ\"ס ומכרזי רמ\"י, וכתוב את output/brief_$DATE.md לפי מבנה הפלט הקשיח. \
מקורות שנכשלו בשלב ה-ingest: ${FAILED[*]:-אין}."

if ! command -v claude >/dev/null 2>&1; then
  echo "שגיאה: ה-CLI של claude לא נמצא ב-PATH — אי אפשר להפיק ברייף" >&2
  exit 1
fi

# סמן זמן: הברייף חייב להיכתב אחריו, אחרת מדובר בקובץ מריצה קודמת
MARKER="$(mktemp)"

# Bash(python:*) נדרש לסקיל israeli-statistics — נתוני הלמ"ס מגיעים
# מ-scripts/fetch_cbs_data.py שלו, לא מ-WebFetch.
claude -p "$PROMPT" \
  --mcp-config .mcp.json \
  --permission-mode acceptEdits \
  --allowedTools "Read,Write,Edit,Glob,Grep,Skill,WebFetch,WebSearch,Bash(python:*),mcp__israel-statistics__*" \
  ${CLAUDE_MODEL:+--model "$CLAUDE_MODEL"}
CLAUDE_RC=$?

# שלושת המחסומים האלה קיימים כי ריצה "ירוקה" בלי ברייף חדש היא הכשל המסוכן
# ביותר כאן: האתר נפרס מחדש עם התוכן של אתמול ואיש אינו מבחין.
if [ $CLAUDE_RC -ne 0 ]; then
  echo "שגיאה: claude נכשל (קוד יציאה $CLAUDE_RC) — אין ברייף חדש" >&2
  rm -f "$MARKER"; exit 1
fi
if [ ! -s "output/brief_$DATE.md" ]; then
  echo "שגיאה: output/brief_$DATE.md לא נוצר — אין מה לפרסם" >&2
  rm -f "$MARKER"; exit 1
fi
if [ ! "output/brief_$DATE.md" -nt "$MARKER" ]; then
  echo "שגיאה: output/brief_$DATE.md לא נכתב בריצה הזו — הקובץ קדם להרצת הסוכן." >&2
  echo "       פריסת התוכן הישן נמנעה במכוון." >&2
  rm -f "$MARKER"; exit 1
fi
rm -f "$MARKER"

python site/build.py
python scripts/send_telegram.py --date "$DATE" || echo "אזהרה: שליחת הטלגרם נכשלה"
echo "=== הושלם: output/brief_$DATE.md ==="
