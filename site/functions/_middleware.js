// ניתוב לפי שם המארח, ושער הסשן של האפליקציה.
//
// אותו פרויקט Pages מגיש שלושה דברים שונים, והפרדה ביניהם היא מה שמאפשר
// לעמוד הנחיתה להיות ציבורי בעוד התוכן מוגן:
//
//   tlvtaseview.com         → עמוד הנחיתה. ציבורי.
//   app.tlvtaseview.com     → הדשבורד והחיפושים. דורש סשן מחובר.
//   forest-brief.pages.dev  → הכתובת החלופית (_lib/alt.js): אותו שער כמו
//                             באפליקציה, ומעליו מתג הבעלים — רק הוא, כל
//                             המשתמשים, או הפניה לאפליקציה.
//   *.pages.dev אחר         → מוסט. אלה תצוגות מקדימות של פריסות קודמות,
//                             ואסור שישמשו כניסה עוקפת לתוכן.
//
// ההגנה עברה מ-Cloudflare Access לאימות עצמי עם שם משתמש וסיסמה, כי
// Access יודע לזהות רק מול ספק זהות או בקוד חד-פעמי — ולא בסיסמה.
//
// **השער נכשל סגור.** בהיעדר SESSION_SECRET או מרחב המשתמשים, או בכל
// חריגה בדרך, התשובה היא הפניה לדף הכניסה ולא מעבר הלאה. תקלת תצורה
// שמפילה את השער פתוח היא בדיוק הכשל שאסור שיקרה כאן.
import { readCookie, readSession, normEmail, COOKIE } from "./_lib/auth.js";
import { wellKnown } from "./_lib/oauth.js";
import { ALT, altMode } from "./_lib/alt.js";

const APEX = "tlvtaseview.com";
const APP = "app.tlvtaseview.com";

// הנתיבים שמותר להגיש באפקס: העמוד עצמו, הנכסים שהוא צריך, וה-API
// של ההרשמה. כל השאר שייך לאפליקציה.
//
// `/landing` ללא הסיומת חייב להיכלל: Pages מבצע הפניית 308 אוטומטית
// מ-`/landing.html` ל-`/landing`, וברשימה שכללה רק את הסיומת ההפניה הזו
// נפלה מחוץ לרשימה והוסטה לאפליקציה המוגנת — כלומר עמוד הנחיתה הציבורי
// שלח את המבקר למסך התחברות.
const PUBLIC_APEX = /^\/(landing(\.html)?)?$|^\/(style\.css|favicon\.ico|robots\.txt)$|^\/api\//;

// מה שמותר להגיש באפליקציה בלי סשן: דף הכניסה, ה-API (שמטפל בהרשאות
// בעצמו), והנכסים שדף הכניסה צריך כדי להיראות.
const PUBLIC_APP = /^\/(login(\.html)?)$|^\/(style\.css|favicon\.ico|robots\.txt)$|^\/api\//;

// "השיחות שלי" — הקלטות של פגישות הבעלים עם הנהלות. **לבעלים בלבד**, גם
// מול משתמש מחובר. meetings.html, ‏/meetings (Pages מוריד את הסיומת בהפניה)
// ו-/meetings/<id>. הנתיב מפוענח ומנורמל לפני הבדיקה: "/%6Deetings.html"
// ו-"//Meetings.html" מגיעים לאותו קובץ, ושער שבודק את הנתיב הגולמי היה
// מחמיץ אותם.
const OWNER_ONLY = /^\/meetings(\.html)?(\/|$)/;

function ownerOnly(pathname) {
  let p = pathname;
  try {
    p = decodeURIComponent(p);
  } catch (e) {
    return true;                       // נתיב שבור — נכשל סגור
  }
  return OWNER_ONLY.test(p.toLowerCase().replace(/\/{2,}/g, "/"));
}

// 404 ולא 403: מי שאינו הבעלים לא אמור לדעת שהעמוד קיים.
const notFound = () => new Response("Not found", { status: 404 });

// הכניסה נשארת באותה כתובת: עוגיית הסשן שייכת למארח שבו נכנסו, ומי שנכנס
// דרך הכתובת החלופית לא היה מגיע לאפליקציה — היא חסומה אצלו, ולכן הוא שם.
function toLogin(url, host) {
  const next = url.pathname + url.search;
  const q = next && next !== "/" ? `?next=${encodeURIComponent(next)}` : "";
  return Response.redirect(`https://${host}/login${q}`, 302);
}

// מצב "רק אני" בכתובת החלופית, למשתמש מחובר שאינו הבעלים. 403 עם הסבר ולא
// 404: הוא הגיע לכאן מקישור שקיבל, והתשובה צריכה לומר לו לאן ללכת.
function altDenied() {
  return new Response(
    `<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width, initial-scale=1"><title>TLV TASE View</title></head>` +
    `<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;line-height:1.6">` +
    `<h1 style="font-size:1.25rem">הכתובת הזו פתוחה כרגע לבעלים בלבד</h1>` +
    `<p>האתר זמין בכתובת <a href="https://${APP}/">${APP}</a>, באותו מייל ובאותה סיסמה.</p>` +
    `</body></html>`,
    { status: 403, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  const host = url.hostname;

  // **הכתובת החלופית עוברת את אותו שער כמו האפליקציה, ולא את הנפילה בסוף.**
  // מארח שאינו מוכר כאן ממשיך בלי סשן, וזו בדיוק הסיבה ש-*.pages.dev הוסט
  // מלכתחילה. כל מארח אחר תחת pages.dev ממשיך להיות מוסט.
  let alt = null;
  if (host === ALT) {
    alt = await altMode(env);
    if (alt === "off") {
      return Response.redirect(`https://${APP}${url.pathname}${url.search}`, 301);
    }
  } else if (host.endsWith(".pages.dev")) {
    return Response.redirect(`https://${APP}${url.pathname}${url.search}`, 301);
  }

  if (host === APEX || host === `www.${APEX}`) {
    if (!PUBLIC_APEX.test(url.pathname)) {
      return Response.redirect(`https://${APP}${url.pathname}${url.search}`, 302);
    }
    if (url.pathname === "/") {
      // בלי הסיומת: כך Pages מגיש את הנכס ישירות במקום להפנות אליו
      url.pathname = "/landing";
      return next(new Request(url.toString(), request));
    }
    return next();
  }

  if (host === APP || alt) {
    // מטא-דאטה של OAuth לשרת ה-MCP (site/functions/_lib/oauth.js). ציבורית
    // מעצם הגדרתה — ממנה המחבר ב-claude.ai מוצא את דף ההרשאה — ולכן לפני השער.
    // באפליקציה בלבד: המחבר רשום על הכתובת שלה.
    if (host === APP && url.pathname.startsWith("/.well-known/")) {
      const meta = wellKnown(request, url.pathname);
      if (meta) return meta;
    }
    if (url.pathname === "/landing.html" || url.pathname === "/landing") {
      return Response.redirect(`https://${APEX}/`, 302);
    }
    if (PUBLIC_APP.test(url.pathname)) {
      if (url.pathname === "/login.html") {
        url.pathname = "/login";
        return next(new Request(url.toString(), request));
      }
      return next();
    }
    let s;
    try {
      if (!env.SESSION_SECRET) return toLogin(url, host);
      s = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
      if (!s) return toLogin(url, host);
    } catch (e) {
      console.log("session gate error", String(e));
      return toLogin(url, host);
    }
    // נכשל סגור: בלי OWNER_EMAIL אין לאיש גישה למה שלבעלים בלבד.
    const owner = normEmail(env.OWNER_EMAIL || "");
    const isOwner = Boolean(owner) && normEmail(s.e) === owner;
    if (alt === "owner" && !isOwner) return altDenied();
    if (ownerOnly(url.pathname) && !isOwner) return notFound();
    return next();
  }

  if (ownerOnly(url.pathname)) return notFound();

  return next();
}
