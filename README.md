# FOREST Daily Brief

ברייף בוקר יומי בעברית למנהל השקעות: חדשות, מאקרו, סחורות ומט"ח — דרך העדשה של
82 חברות הכיסוי ב-[config/companies.yaml](config/companies.yaml). ההוראות המלאות לסוכן: [CLAUDE.md](CLAUDE.md).

## איך זה עובד

```
GitHub Actions (06:45 ישראל, יומי)
  └─ run_daily.sh
       1. ingest/  — feedly, gmail, maya, markets, rmi  →  data/raw/<היום>/
       2. claude -p — קורא את הקלט, כותב output/brief_<היום>.md
       3. site/build.py — רינדור ל-site/dist (RTL)
       4. scripts/send_telegram.py — תמצית + קישור
  └─ commit של data/state.sqlite + output/ חזרה לריפו
  └─ פריסת site/dist ל-GitHub Pages
```

מקור שנכשל אינו עוצר את הצנרת — הסוכן מדווח עליו בסעיף "תקלות מקורות" בברייף.

## הקמה חד-פעמית ב-GitHub

1. **Secrets** (Settings → Secrets and variables → Actions → New repository secret):

| Secret | מה זה | איך משיגים |
|--------|-------|------------|
| `ANTHROPIC_API_KEY` | מפתח API של Anthropic | console.anthropic.com → API Keys |
| `FEEDLY_TOKEN` | Access token של Feedly | feedly.com/v3/auth/dev (או Feedly Pro → API) |
| `GMAIL_CREDENTIALS` | JSON עם client_id/client_secret/refresh_token | להריץ מקומית `python scripts/gmail_authorize.py` (הוראות בראש הקובץ) ולהעתיק את הפלט |
| `TELEGRAM_BOT_TOKEN` | טוקן בוט | @BotFather בטלגרם → ‎/newbot |
| `TELEGRAM_CHAT_ID` | יעד השליחה | להוסיף את הבוט לקבוצה/ערוץ ולקרוא את ה-id דרך `getUpdates` |

2. **GitHub Pages**: Settings → Pages → Source = **GitHub Actions**.
3. **Gmail**: ליצור לייבל בשם `ברייף` ולתייג אליו את הניוזלטרים הרלוונטיים
   (אפשר עם פילטרים אוטומטיים).
4. הרצה ראשונה: Actions → Daily Brief → **Run workflow**.

## הרצה מקומית

```bash
pip install -r requirements.txt
python ingest/markets_pull.py      # עובד בלי סודות
python ingest/maya_pull.py         # עובד בלי סודות
FEEDLY_TOKEN=... python ingest/feedly_pull.py
python scripts/gmail_authorize.py  # פעם אחת; אח"כ gmail_pull עובד מקומית
bash run_daily.sh                  # הצנרת המלאה (דורש claude CLI)
```

הערות סביבה:

- **פרוקסי ארגוני (TLS)**: כל הסקריפטים קוראים ל-`ingest/_tls.py` שבונה bundle
  תעודות מחנות Windows — אין צורך בהגדרה ידנית.
- **מאיה**: הגישה דרך `curl_cffi` עם חיקוי דפדפן ועוגיות (עוקף WAF). פרטי
  ה-API המהונדסים-לאחור מתועדים ב-[ingest/_maya_api.py](ingest/_maya_api.py).
  לא לשלוח שדות בשם `page`/`pageNum`/`skip` — חתימת WAF.
- **רמ"י**: אותו סיפור — ה-API של `apps.land.gov.il` חוסם requests רגיל
  (וזו הסיבה ששרת ה-MCP remy-mcp נכשל מולו). המשיכה נעשית ב-[ingest/rmi_pull.py](ingest/rmi_pull.py):
  חיקוי דפדפן, `Accept: application/json` מפורש (אחרת חוזר XML של 6.6MB),
  וסינון תאריכים מקומי — פילטרי התאריכים בצד השרת אינם מיושמים.
- **MCP**: רק `israel-statistics`, ודורש Node.js (ב-CI מותקן אוטומטית).
  שרת `remy-land-authority` הוסר מ-`.mcp.json` — ה-API של רמ"י חוסם את
  ספריית ה-HTTP שהוא משתמש בה, ובמקומו יש `ingest/rmi_pull.py`. ה-clone של
  `vendor/remy-mcp` עדיין מתבצע ב-run_daily.sh, אך רק בשביל טבלת קודי היישוב שבו.

## מבנה הריפו

ראה "מפת הפרויקט" ב-[CLAUDE.md](CLAUDE.md). בקצרה: `config/` הגדרות,
`ingest/` משיכת נתונים דטרמיניסטית, `data/` קלט יומי + state, `output/`
הברייפים, `site/` הגנרטור, `scripts/` עזרים (אימות Gmail, טלגרם).

## תחזוקה שוטפת

- **עדכון רשימת הכיסוי**: עריכת `config/companies.yaml` ואז
  `python ingest/resolve_tase_ids.py` (ממלא tase_id לחברות חדשות; שם שלא
  נמצא במאיה → שגיאה מפורשת, לא ניחוש).
- **מכשירי שוק**: עריכת `markets.yfinance` ב-`config/sources.yaml`.
- תשואת ממשלתי שקלי 10ש עדיין ללא מקור חינמי אמין — מסומן `enabled: false`
  ב-sources.yaml; הברייף מציג US10Y בלבד.
