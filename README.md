# FOREST Daily Brief

ברייף בעברית למנהל השקעות, שלוש פעמים ביום: חדשות, מאקרו, סחורות ומט"ח — דרך העדשה של
82 חברות הכיסוי ב-[config/companies.yaml](config/companies.yaml). ההוראות המלאות לסוכן: [CLAUDE.md](CLAUDE.md).

## איך זה עובד

```
GitHub Actions — שלוש מהדורות ביום (בוקר 06:45 · נעילה 18:00/14:30 · לילה 00:00)
  └─ run_daily.sh
       1. ingest/  — rss, gmail, maya, markets, rmi, te  →  data/raw/<היום>/
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
| `GMAIL_CREDENTIALS` | JSON עם client_id/client_secret/refresh_token | להריץ מקומית `python scripts/gmail_authorize.py` (הוראות בראש הקובץ) ולהעתיק את הפלט |
| `TRADINGECONOMICS_KEY` | מפתח Trading Economics בפורמט `key:secret` | developer.tradingeconomics.com → Dashboard. **חשבון האורח בוטל** — נדרש מנוי |
| `TELEGRAM_BOT_TOKEN` | טוקן בוט (אופציונלי) | @BotFather בטלגרם → ‎/newbot |
| `TELEGRAM_CHAT_ID` | יעד השליחה (אופציונלי) | להוסיף את הבוט לקבוצה/ערוץ ולקרוא את ה-id דרך `getUpdates` |

2. **GitHub Pages**: Settings → Pages → Source = **GitHub Actions**.
3. **Gmail**: ליצור לייבל בשם `ברייף` ולתייג אליו את הניוזלטרים הרלוונטיים
   (אפשר עם פילטרים אוטומטיים).
4. הרצה ראשונה: Actions → Daily Brief → **Run workflow** (אפשר לבחור מהדורה
   בשדה `edition`; ריק = לפי השעה).

**שלוש מהדורות ביום**, כל אחת עם דגש אחר — בוקר (מה צפוי היום), נעילה (סיכום
המסחר בת"א) ולילה (סיכום היום אחרי נעילת וול סטריט). כל מהדורה קוראת את
קודמותיה מאותו יום ומדווחת רק על מה שהשתנה. הפירוט ב-[CLAUDE.md](CLAUDE.md).

שעון: ה-cron של GitHub הוא UTC וישראל מזיזה שעון פעמיים בשנה, ולכן כל מהדורה
מתוזמנת לשתי שעות UTC ו-`run_daily.sh` בוחר לפי השעה המקומית — הריצה המיותרת
יוצאת בשקט בלי להפיק ברייף.

## הרצה מקומית

```bash
pip install -r requirements.txt
python ingest/markets_pull.py      # עובד בלי סודות
python ingest/maya_pull.py         # עובד בלי סודות
python ingest/rmi_pull.py          # עובד בלי סודות
python ingest/rss_pull.py          # עובד בלי סודות
python scripts/gmail_authorize.py  # פעם אחת; אח"כ gmail_pull עובד מקומית
bash run_daily.sh                  # הצנרת המלאה (דורש claude CLI)
```

**קובץ `.env` להרצה מקומית** (מוחרג מ-git). משתנה שכבר מוגדר בסביבה גובר עליו,
כך שב-CI ה-Secrets תמיד מנצחים:

```
TRADINGECONOMICS_KEY=key:secret
```

**Feedly הוסר מהפרויקט** (08/2026). הוא היה מוגבל ל-50 קריאות API ליום לחשבון,
ועם שלוש מהדורות ביום המכסה נשברה כמעט מדי יום. `ingest/rss_pull.py` קורא את
אותם פידים ישירות מהמקור — בלי מכסה, בלי תלות בצד שלישי, ובנפח כפול.

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

## ניטור דיווחי מאיה (רציף)

בנוסף לשלוש המהדורות רץ workflow שני, `maya-watch`, **כל רבע שעה מסביב לשעון**.
חברות מדווחות גם אחרי הנעילה ובסופי שבוע, ולכן אין חלון בטוח לדלג עליו.
הוא מזהה דיווחים חדשים, מוריד את **גוף הדוח** (ה-htm לכותרת וה-PDF המצורף
לתוכן — בת053 ובת930 ה-htm הוא דף שער בלבד), ומפיק ניתוח לכל דיווח:
כותרת אנליטית, סיכום עם הנתונים מגוף הדוח, **מספרי מפתח**, השוואה לתקופה
קודמת, דירוג מהותיות 1–3, כיוון השפעה, **חברות כיסוי מושפעות (כולל בעקיפין)**
ומה לעקוב בהמשך.

**עלות ותדירות.** ריצה מלאה נמדדה ב-4.1 דקות; ב-96 ריצות ביום זה כ-11,900
דקות בחודש, פי ארבעה מהמכסה הכלולה ב-GitHub Pro (3,000). לכן ה-workflow מפוצל:
שלב הזיהוי זול (checkout + pip מהמטמון), ורק כשנמצאו דיווחים חדשים מותקנים
ה-CLI ושאר התלויות ומופעל הסיכום. רוב מחזורי הלילה מסתיימים בפחות מדקה.
כדאי לעקוב אחרי Settings → Billing בחודש הראשון.
התוצאה מתפרסמת ל-`output/reports/<date>.jsonl`, ומוצגת בעמוד `reports.html`
ובפיד שבדשבורד.

**היקף** נשלט ב-`config/sources.yaml` תחת `maya_watch.scope`:

| ערך | מה מסוכם | נפח יומי |
|-----|----------|----------|
| `coverage` | חברות הכיסוי בלבד | ~14 |
| `material` (ברירת מחדל) | חברות הכיסוי + 10 סוגי טפסים מהותיים בכל הבורסה | ~50–70 |
| `all` | כל דיווח בבורסה | ~100–175 |

`all` מכפיל את צריכת ה-API של Anthropic פי שלושה על דיווחים שרובם טכניים
(שינויי שם, מרשמי מניות). התקרה `MAX_PER_RUN` ב-`scripts/summarize_reports.py`
מגבילה כל מחזור ל-16 דיווחים; מה שנחתך נאסף במחזור הבא בלי לאבד דבר.

## מבנה האתר

| עמוד | תוכן |
|------|------|
| `index.html` | דשבורד: מצב מקורות, רצועת שווקים, אינדיקטורי מאקרו, ניווט נושאים, הברייף האחרון וארכיון |
| `topics/<slug>.html` | 12 עמודי נושא — מרכזי נתונים, אנרגיה, פולימרים, מלט וחומרי בנייה, מתכות, שילוח, מזון וחקלאות, ביטחון, רכב/EV, נדל"ן, טק וסייבר, מאקרו |
| `reports.html` | סיכומי דיווחים ודוחות **מכל חברה נסחרת**, מחולק למהותיים ולשאר |
| `archive.html` | כל המהדורות |

הסיווג לנושאים נעשה במילות מפתח (`topics` ב-sources.yaml) ולא ב-LLM — כ-330
אייטמים ביום, וסיווג במודל היה מכפיל את עלות ההרצה בלי דיוק משמעותי נוסף.
האייטמים המסווגים נשמרים ל-`output/news/<date>.jsonl` כדי שעמודי הנושא
יצטברו לאורך זמן; `data/raw/` מוחרג מהריפו ונמחק.

## מבנה הריפו

ראה "מפת הפרויקט" ב-[CLAUDE.md](CLAUDE.md). בקצרה: `config/` הגדרות,
`ingest/` משיכת נתונים דטרמיניסטית, `data/` קלט יומי + state, `output/`
הברייפים, `site/` הגנרטור, `scripts/` עזרים (אימות Gmail, טלגרם).

## תחזוקה שוטפת

- **עדכון רשימת הכיסוי**: עריכת `config/companies.yaml` ואז
  `python ingest/resolve_tase_ids.py` (ממלא tase_id לחברות חדשות; שם שלא
  נמצא במאיה → שגיאה מפורשת, לא ניחוש).
- **מכשירי שוק**: עריכת `markets.yfinance` ב-`config/sources.yaml`.
- **תשואת ממשלתי שקלי 10ש** מגיעה מ-Trading Economics (`te.json`). השדה
  `markets.il_gov_10y` ב-sources.yaml נשאר `enabled: false` — אין לו מקור
  חינמי, ו-TE הוא המוסמך.
- **היקף ניטור מאיה**: `maya_watch.scope` ב-sources.yaml (ראה הטבלה למעלה).
