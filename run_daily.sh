#!/usr/bin/env bash
# FOREST Daily Brief — ingestion → Claude → רינדור אתר → טלגרם
# מקור שנכשל לא עוצר את הצנרת; הסוכן מדווח עליו בסעיף "תקלות מקורות".
set -uo pipefail
cd "$(dirname "$0")"

DATE="${BRIEF_DATE:-$(date +%F)}"
RAW="data/raw/$DATE"
mkdir -p "$RAW"
FAILED=()

# --- מהדורה -----------------------------------------------------------------
# שלוש מהדורות ביום. ה-cron של GitHub הוא ב-UTC בלבד, וישראל מזיזה שעון פעמיים
# בשנה — לכן כל מהדורה מתוזמנת לשתי שעות UTC (קיץ וחורף) והבחירה נעשית כאן לפי
# השעה המקומית בפועל. ריצה שנפלה על השעה ה"שנייה" יוצאת בשקט.
edition_from_hour() {
  case "$1" in
    05|06|07) echo morning ;;
    13|14|17|18|19) echo close ;;
    23|00|01) echo night ;;
    *) echo skip ;;
  esac
}

EDITION="${BRIEF_EDITION:-$(edition_from_hour "$(date +%H)")}"
if [ "$EDITION" = "skip" ]; then
  echo "השעה $(date +%H:%M) אינה שעת מהדורה — יוצאים בלי להפיק ברייף."
  exit 0
fi

case "$EDITION" in
  morning) ED_HE="בוקר";  ED_FOCUS="סקירת פתיחה: מה קרה בלילה בעולם, מה צפוי היום, ומה שדווח במאיה מאז המהדורה הקודמת. סעיף 'מה לעקוב היום' הוא לב המהדורה." ;;
  close)   ED_HE="נעילה"; ED_FOCUS="סיכום יום המסחר בתל אביב: תזוזות המדדים והמניות, כל דיווחי מאיה של היום ומשמעותם, ותגובת השוק. המיקוד ישראלי — שוק ארה\"ב עדיין נסחר ואינו הסיפור." ;;
  night)   ED_HE="לילה";  ED_FOCUS="סיכום היום כולו לאחר נעילת וול סטריט: סגירת המדדים בארה\"ב, מאקרו גלובלי, וגזירת המשמעות לחברות הכיסוי לקראת יום המסחר הבא." ;;
esac

SUFFIX="-$EDITION"
[ "$EDITION" = "morning" ] && SUFFIX=""     # שומר על שמות הברייפים הקיימים
BRIEF="output/brief_${DATE}${SUFFIX}.md"

# כל מהדורה מתוזמנת לשתי שעות UTC בגלל שעון הקיץ, ובפועל **שתיהן** נופלות
# בתוך חלון המהדורה: נמדד שמהדורת הלילה רצה ב-21:41 וב-22:36 באותו לילה
# (10/08 ו-11/08), הפיקה את הברייף פעמיים ודרסה את עצמה. זו הכפלה של עלות
# ה-API על תוצר זהה. לכן ריצה מתוזמנת שמוצאת ברייף קיים לאותו יום ומהדורה
# יוצאת. הרצה ידנית (BRIEF_FORCE=1) תמיד מפיקה מחדש.
#
# הבדיקה היא על **קיום** הקובץ ולא על גילו: actions/checkout כותב את כל
# הקבצים מחדש, וזמן השינוי שלהם בענן הוא תמיד "עכשיו" — מנגנון מבוסס-גיל
# היה מדלג בכל ריצה ומשתק את הברייף לחלוטין.
#
# כך גם מתקבל ניסיון חוזר בחינם: ריצה שנכשלה אינה כותבת את הקובץ (שלושת
# המחסומים למטה), ולכן הפעימה השנייה של אותה מהדורה תפיק אותו.
if [ -z "${BRIEF_FORCE:-}" ] && [ -s "$BRIEF" ]; then
  echo "$BRIEF כבר קיים — הפעימה הכפולה של מהדורת $ED_HE מדולגת."
  exit 0
fi

run_source() {
  local name="$1"; shift
  if "$@"; then
    echo "[$name] OK"
  else
    echo "[$name] FAILED (exit $?)"
    FAILED+=("$name")
  fi
}

echo "=== FOREST brief · $DATE · מהדורת $ED_HE ($EDITION) ==="
run_source rss     python ingest/rss_pull.py
run_source gmail   python ingest/gmail_pull.py
run_source maya    python ingest/maya_pull.py
run_source markets python ingest/markets_pull.py
run_source rmi     python ingest/rmi_pull.py
run_source te      python ingest/te_pull.py
run_source calls   python ingest/maya_calls.py
# אינדקס הדוחות מתוחזק ע"י maya-watch (כל רבע שעה) ולא כאן: כותב שלישי
# לאותם קבצים היה מוסיף מרוץ בלי להוסיף טריות.
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

# nadlan-mcp — עסקאות נדל"ן מ-Govmap, לשליפה לפי דרישה (לא מקור ingest).
# בניגוד לרמ"י, Govmap אינו חוסם את requests, ולכן השרת עצמו כן פעיל.
if [ ! -d vendor/nadlan-mcp ]; then
  if git clone --depth 1 https://github.com/nitzpo/nadlan-mcp vendor/nadlan-mcp; then
    python -m pip install --quiet "fastmcp>=2.13.0,<3.0.0" || \
      echo "אזהרה: התקנת fastmcp נכשלה — שרת nadlan לא יעלה"
  else
    echo "אזהרה: clone של nadlan-mcp נכשל — אין שליפת עסקאות נדל\"ן"
  fi
fi

PROMPT="היום $DATE, מהדורת $ED_HE, השעה $(date +%H:%M) שעון ישראל. \
בצע את הפייפליין היומי לפי CLAUDE.md: קרא את config/companies.yaml ואת הקבצים \
ב-data/raw/$DATE/, הפעל את הסקיל israeli-statistics לבדיקת פרסומי למ\"ס, \
וכתוב את $BRIEF לפי מבנה הפלט הקשיח. \
מיקוד המהדורה: $ED_FOCUS \
אם כבר קיימים ב-output/ ברייפים מהיום, קרא אותם קודם ואל תחזור על אותם אייטמים — \
דווח מה השתנה מאז וסמן במפורש מה חדש. שורת הכותרת תכלול 'מהדורת $ED_HE'. \
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
  --allowedTools "Read,Write,Edit,Glob,Grep,Skill,WebFetch,WebSearch,Bash(python:*),mcp__israel-statistics__*,mcp__nadlan__*" \
  ${CLAUDE_MODEL:+--model "$CLAUDE_MODEL"}
CLAUDE_RC=$?

# שלושת המחסומים האלה קיימים כי ריצה "ירוקה" בלי ברייף חדש היא הכשל המסוכן
# ביותר כאן: האתר נפרס מחדש עם התוכן של אתמול ואיש אינו מבחין.
if [ $CLAUDE_RC -ne 0 ]; then
  echo "שגיאה: claude נכשל (קוד יציאה $CLAUDE_RC) — אין ברייף חדש" >&2
  rm -f "$MARKER"; exit 1
fi
if [ ! -s "$BRIEF" ]; then
  echo "שגיאה: $BRIEF לא נוצר — אין מה לפרסם" >&2
  rm -f "$MARKER"; exit 1
fi
if [ ! "$BRIEF" -nt "$MARKER" ]; then
  echo "שגיאה: $BRIEF לא נכתב בריצה הזו — הקובץ קדם להרצת הסוכן." >&2
  echo "       פריסת התוכן הישן נמנעה במכוון." >&2
  rm -f "$MARKER"; exit 1
fi
rm -f "$MARKER"

python scripts/publish_status.py
python scripts/publish_news.py || echo "אזהרה: סיווג החדשות נכשל"
python scripts/summarize_topics.py || echo "אזהרה: סיכומי הנושאים נכשלו"
python site/build.py
python scripts/send_telegram.py --brief "$BRIEF" || echo "אזהרה: שליחת הטלגרם נכשלה"
echo "=== הושלם: $BRIEF (מהדורת $ED_HE) ==="
