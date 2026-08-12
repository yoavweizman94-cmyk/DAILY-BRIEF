# הקמת אתר פרטי עם דומיין והרשמה מאושרת

מסמך הקמה חד-פעמי. כל שלב מסומן במי מבצע אותו.

## למה המבנה הזה

האתר היום ב-GitHub Pages, ש**אינו יודע לעשות הזדהות בכלל** — כל מי שיש לו את
הקישור נכנס. בנוסף הריפו ציבורי, כך שהברייפים קריאים ישירות מ-GitHub וגדר סביב
האתר בלבד לא הייתה שווה דבר.

המעבר: **Cloudflare Pages** מארח את האתר, **Cloudflare Access** יושב לפניו
וחוסם כברירת מחדל, והתוכן עובר לריפו פרטי.

ריפו פרטי מאבד את דקות ה-Actions החינמיות. נמדד: המערכת צורכת ~150–310 דקות
ביום, כלומר חריגה של 20–60 דולר בחודש מהמכסה של 2,000. לכן הפיצול:

| ריפו | מה יש בו | נראות | Actions |
|------|----------|-------|---------|
| `DAILY-BRIEF` | קוד, workflows, קונפיג | ציבורי | **חינם, ללא הגבלה** |
| `DAILY-BRIEF-content` | ברייפים, אינדקסים, state | **פרטי** | לא רץ שם |

הקוד ממילא אינו רגיש; תוצרי המחקר כן. ה-CI ממשיך לרוץ בריפו הציבורי ולכן נשאר
חינם, מושך וכותב תוכן לריפו הפרטי, ופורס את האתר הבנוי ישירות ל-Cloudflare.
Cloudflare אינו מקבל גישה לאף ריפו.

## מה יואב צריך לעשות

### 1. ריפו תוכן פרטי
צור ריפו חדש בשם `DAILY-BRIEF-content`, **Private**, בלי README.

### 2. Personal Access Token
GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained**.
- Repository access: רק `DAILY-BRIEF-content`
- Permissions → Repository → **Contents: Read and write**
- תוקף: שנה

העתק את הטוקן ושמור אותו כ-secret בריפו **הציבורי**:
`Settings → Secrets and variables → Actions → New secret`
- שם: `CONTENT_REPO_TOKEN`

### 3. חשבון Cloudflare
הרשמה חינם ב-<https://dash.cloudflare.com/sign-up>. אין צורך בכרטיס אשראי
לשלב הזה.

### 4. דומיין
הכי פשוט לקנות דרך **Cloudflare Registrar** (Dash → Domain Registration →
Register Domain). הוא מוכר במחיר עלות בלי תוספת רווח, כולל הסתרת WHOIS חינם,
וה-DNS כבר מחובר — אין מה להגדיר ידנית.

`.com` עולה בערך 10–11 דולר לשנה. הצעות: `forestbrief.com`,
`forest-research.com`, או כל שם שתעדיף.

אם תעדיף רשם אחר — זה עובד גם, אבל תצטרך להעביר את ה-nameservers ל-Cloudflare
ולהמתין להתפשטות. תגיד לי מה בחרת ואכין את רשומות ה-DNS המדויקות.

### 5. API token של Cloudflare
Dash → My Profile → API Tokens → Create Token → תבנית **Edit Cloudflare Workers**
(היא כוללת את ההרשאה ל-Pages). שמור בריפו הציבורי כ-secret:
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID` — מופיע בעמוד הבית של ה-Dash מימין

### 6. הפעלת Zero Trust
Dash → Zero Trust → בחר את התוכנית **Free** (עד 50 משתמשים). היא מבקשת פרטי
תשלום לאימות בלבד ואינה מחייבת.

## מה אני עושה אחרי שהשלבים למעלה בוצעו

1. מעביר את `output/` ואת `data/state.sqlite` לריפו התוכן הפרטי, עם ההיסטוריה.
2. משנה את שלושת ה-workflows: משיכת התוכן הפרטי בתחילת הריצה, כתיבה חזרה
   אליו בסוף, ופריסה ל-Cloudflare Pages במקום ל-GitHub Pages.
3. מגדיר את אפליקציית ה-Access ואת מדיניות ההרשאות.
4. מכבה את GitHub Pages כדי שלא יישאר עותק ציבורי.

## מדיניות הגישה

חסימה כברירת מחדל. שיטת ההתחברות: **One-time PIN** — המשתמש מקבל קוד חד-פעמי
למייל. אין סיסמאות לנהל ואין ספק זהות להקים.

הרשימה נשלטת ב-Zero Trust → Access → Applications → Policies:
- **Emails** — כתובת בודדת שאתה מאשר.
- **Emails ending in** — דומיין שלם, למשל כל `@forest-ih.com`, אם תרצה בהמשך.

מי שאינו ברשימה מקבל דף חסימה. אפשר להתאים אותו כך שיציג הוראה לפנות אליך
לאישור — זו "ההרשמה": הם מבקשים, אתה מוסיף את הכתובת, והם נכנסים.

**חשוב:** אין תור אישורים אוטומטי ב-Access. ההוספה ידנית, וזו בדיוק השליטה
ההדוקה שביקשת.
