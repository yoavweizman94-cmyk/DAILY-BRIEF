// סקירת דוח כספי לפי דרישה — נוצרת בלחיצה, ולא מראש.
//
// **למה כאן ולא בצנרת.** הכנה מראש שילמה על כל דוח בין אם מישהו פתח
// אותו ובין אם לא. כאן משלמים רק על מה שנקרא בפועל, והתוצאה נשמרת
// ב-KV כך שהלחיצה השנייה — של אותו קורא או של אחר — חינם.
//
// **מה מגן על הכיס.** שלושה דברים, ולא אחד:
//   1. סשן מחובר. הנתיב הזה תחת /api/ ולכן המידלוור מוותר על השער,
//      והבדיקה נעשית כאן במפורש. בלעדיה כל אדם ברשת יכול להוציא כסף.
//   2. מגביל קצב לכל משתמש, על אותו KV שמשמש את ההרשמה.
//   3. רשימת היתר. הדפדפן שולח **מזהה בלבד**, והנתיב ל-PDF נקרא
//      מ-`filings/pdfmap.json` שנבנה בזמן פריסה ומכיל רק דוחות כספיים
//      של חברות כיסוי. מזהה שאינו שם — נדחה, ואין דרך להזרים כתובת.
//
// **HTTP גולמי ולא ה-SDK.** ל-Functions כאן אין package.json ואין
// שלב התקנה; הוספת toolchain שלם בשביל בקשה אחת אינה מידתית. אותו
// שיקול שהוביל ל-WebCrypto ב-_lib/auth.js במקום ספריית הצפנה.
import { readCookie, readSession, COOKIE, rateLimit } from "../../_lib/auth.js";

const FILES = "https://mayafiles.tase.co.il/";
const API = "https://api.anthropic.com/v1/messages";
const MODEL = "claude-opus-5";
// מגבלת הבקשה ל-API היא 32MB אחרי base64; נשארים מתחת בבטחה.
const MAX_PDF = 20 * 1024 * 1024;
// כמה סקירות חדשות מותר למשתמש בשעה. סקירה שכבר במטמון אינה נספרת.
const PER_HOUR = 12;

const SYSTEM = `אתה אנליסט מחקר שכותב עבור מנהל השקעות מקצועי. אתה מקבל דוח
כספי של חברה ציבורית בבורסה בתל אביב, וכותב עליו סקירה בעברית.

הקורא יודע לפתוח את הדוח בעצמו. מה שהוא קונה ממך הוא הקריאה **מתחת**
למספרים — לא ציטוט של שורת ההכנסות והרווח.

כללים שאין לחרוג מהם:

1. **כל מספר מגוף הדוח בלבד.** אין לך ידע עצמאי על החברה. אם נתון אינו
   בדוח, כתוב שהוא אינו שם — אל תשלים מהזיכרון ואל תעריך.
2. **אין המלצות השקעה.** ניתוח השפעה — כן. "כדאי לקנות/למכור", "המניה
   זולה/יקרה", "מומלץ" — לעולם לא. גם לא ברמז.
3. **הפרד עובדה מפרשנות.** מספר מהדוח הוא עובדה; מה שהוא אומר הוא
   פרשנות, ויש לסמן אותה במילה "משמעות:" בתחילת המשפט.
4. עברית בלבד. מונחים באנגלית מותרים היכן שמקובל (FFO, EBITDA, cap rate).
5. ענייני וישיר. בלי סופרלטיבים, בלי "חשוב לציין", בלי ריפוד.

כתוב **בדיוק** את המבנה הבא, בכותרות markdown, ובלי שום טקסט לפניו או
אחריו:

## בשורה אחת
משפט אחד, עד 25 מילים, שאומר מה קרה בדוח הזה.

## המספרים
טבלת markdown: שורה לכל נתון מרכזי שיש בדוח — הכנסות, רווח גולמי, רווח
תפעולי, רווח נקי, EBITDA, תזרים מפעילות שוטפת, הון עצמי, וכל מדד שהחברה
עצמה מדגישה (NOI, FFO, צבר). עמודות: מדד | התקופה | מקבילה | שינוי.
אם נתון אינו בדוח — אל תמציא שורה עבורו.

## מה הניע את התוצאה
מחיר מול כמות מול תמהיל מול מט"ח. "ההכנסות עלו 12%" הוא נתון; "ההכנסות
עלו 12% כולן ממחיר בעוד הכמויות ירדו 3%" הוא ניתוח. אם הדוח מפרט מגזרים,
אמור איזה מגזר הזיז את התוצאה ובכמה.

## האם זה חוזר על עצמו
רווח שנשען על מימוש נכס, שערוך, הפרשי שער או הכנסה חד-פעמית — לציין
במפורש ולהפריד מהרווח התפעולי השוטף. אם ההנהלה מציגה נתון מנוטרל, הבא
אותו ואמור מה נוטרל.

## שולי הרווח
בכל רמה שהדוח מפרט — גולמי, תפעולי, נקי. חשב את השיעור ואמור למה זז.
שים לב לפער בין כיוון המרווח לכיוון ההכנסות; זה לרוב עיקר הסיפור.

## תזרים מול רווח
האם התזרים התפעולי תומך ברווח החשבונאי. פער מתמשך בין השניים הוא האייטם,
לא הרווח.

## מה השתנה במבנה
מגזרים, צבר, ריכוזיות לקוחות, כושר ייצור, מינוף, אמות מידה פיננסיות,
מועדי פירעון, שינויים בהון.

## סימנים שדורשים מבט
לקוחות או מלאי שגדלים מהר מההכנסות, היוון עלויות, שינוי מדיניות
חשבונאית, עסקאות בעלי עניין, הערת עסק חי, הפניית תשומת לב של רואה
החשבון. אם אין — כתוב "לא נמצאו".

## מה הדוח לא אומר
נתון שהופסק פרסומו, מגזר שאוחד, תחזית שנמשכה בלי הסבר, וכל דבר שציפית
למצוא ולא מצאת. אם חלק מהדוח לא היה קריא — אמור זאת כאן במפורש.`;

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

// base64 בלי לבנות מחרוזת ענקית בבת אחת: btoa על מערך של מיליוני
// בתים חורג ממחסנית הקריאה, ולכן נבנה במנות.
function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let out = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    out += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(out);
}

export async function onRequestGet(context) {
  const { request, env, params } = context;

  const id = String(params.id || "").replace(/[^0-9]/g, "");
  if (!id) return json(400, { error: "מזהה חסר" });

  // 1. סשן. בלעדיו אין גישה — ואין הוצאה. **נכשל סגור**: בהיעדר
  //    SESSION_SECRET אין דרך לאמת, ולכן דוחים ולא מוותרים על הבדיקה.
  if (!env.SESSION_SECRET) return json(503, { error: "האימות אינו מוגדר" });
  const sess = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!sess) return json(401, { error: "נדרשת התחברות" });

  // 2. מטמון. לחיצה חוזרת אינה עולה דבר ואינה נספרת במגביל הקצב.
  const key = `review:${id}`;
  if (env.USERS) {
    const hit = await env.USERS.get(key);
    if (hit) return json(200, { id, cached: true, md: hit });
  }

  // 3. רשימת ההיתר — מזהה שאינו דוח כספי של חברת כיסוי אינו מגיע ל-API.
  let map;
  try {
    const r = await env.ASSETS.fetch(new URL("/filings/pdfmap.json", request.url));
    map = await r.json();
  } catch {
    return json(503, { error: "מפת הדוחות אינה זמינה" });
  }
  const rec = map[id];
  if (!rec) return json(404, { error: "הדוח אינו ברשימת הדוחות שניתן לסקור" });

  if (!env.ANTHROPIC_API_KEY) return json(503, { error: "המפתח אינו מוגדר" });

  // 4. מגביל קצב, אחרי המטמון ואחרי רשימת ההיתר — כדי שבקשה שנדחית
  //    ממילא לא תבזבז את המכסה של המשתמש.
  const rl = await rateLimit(env, `rev:${sess.e}`, PER_HOUR, 3600);
  if (!rl.ok) {
    return json(429, { error: `מכסת הסקירות לשעה נוצלה (${PER_HOUR})` });
  }

  const pdf = await fetch(FILES + rec.p, {
    headers: { "User-Agent": "Mozilla/5.0", Referer: "https://maya.tase.co.il/" },
  });
  if (!pdf.ok) return json(502, { error: `הדוח לא נמשך (${pdf.status})` });
  const buf = await pdf.arrayBuffer();
  if (buf.byteLength > MAX_PDF) {
    return json(413, {
      error: `הדוח גדול מדי לסקירה בזמן אמת (${Math.round(buf.byteLength / 1e6)}MB)`,
    });
  }

  const who = Array.isArray(rec.c) ? rec.c.join(", ") : rec.c || "";
  const head = `חברה: ${who}\nכותרת הדיווח: ${rec.t}\nתאריך הדיווח: ${rec.d}\n` +
               `מזהה מאיה: ${id}`;

  const res = await fetch(API, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 16000,
      system: SYSTEM,
      thinking: { type: "adaptive" },
      output_config: { effort: "high" },
      messages: [{
        role: "user",
        content: [
          {
            type: "document",
            source: {
              type: "base64",
              media_type: "application/pdf",
              data: toBase64(buf),
            },
          },
          { type: "text", text: head + "\n\nכתוב את הסקירה." },
        ],
      }],
    }),
  });

  if (!res.ok) {
    const detail = await res.text();
    // הודעת ה-API מדויקת ושימושית ("Credit balance is too low"), ולכן
    // היא מועברת כלשונה במקום "שגיאה" גנרית שאין מה לעשות איתה.
    return json(502, {
      error: "יצירת הסקירה נכשלה",
      status: res.status,
      detail: detail.slice(0, 300),
    });
  }

  const data = await res.json();
  if (data.stop_reason === "refusal") {
    return json(422, { error: "המודל סירב לנתח את הדוח הזה" });
  }
  const md = (data.content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("")
    .trim();
  if (!md) return json(502, { error: "התקבלה סקירה ריקה" });

  // נשמר בלי תפוגה: דוח כספי אינו משתנה אחרי פרסומו, ולכן סקירה שנוצרה
  // פעם אחת נכונה לתמיד.
  if (env.USERS) await env.USERS.put(key, md);
  return json(200, { id, cached: false, md });
}
