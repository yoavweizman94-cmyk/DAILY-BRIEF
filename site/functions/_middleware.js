// ניתוב לפי שם המארח, ושער הסשן של האפליקציה.
//
// אותו פרויקט Pages מגיש שלושה דברים שונים, והפרדה ביניהם היא מה שמאפשר
// לעמוד הנחיתה להיות ציבורי בעוד התוכן מוגן:
//
//   tlvtaseview.com       → עמוד הנחיתה. ציבורי.
//   app.tlvtaseview.com   → הדשבורד והחיפושים. דורש סשן מחובר.
//   *.pages.dev           → מוסט, כדי שלא ישמש כניסה עוקפת לתוכן.
//
// ההגנה עברה מ-Cloudflare Access לאימות עצמי עם שם משתמש וסיסמה, כי
// Access יודע לזהות רק מול ספק זהות או בקוד חד-פעמי — ולא בסיסמה.
//
// **השער נכשל סגור.** בהיעדר SESSION_SECRET או מרחב המשתמשים, או בכל
// חריגה בדרך, התשובה היא הפניה לדף הכניסה ולא מעבר הלאה. תקלת תצורה
// שמפילה את השער פתוח היא בדיוק הכשל שאסור שיקרה כאן.
import { readCookie, readSession, COOKIE } from "./_lib/auth.js";

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

function toLogin(url) {
  const next = url.pathname + url.search;
  const q = next && next !== "/" ? `?next=${encodeURIComponent(next)}` : "";
  return Response.redirect(`https://${APP}/login${q}`, 302);
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  const host = url.hostname;

  if (host.endsWith(".pages.dev")) {
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

  if (host === APP) {
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
    try {
      if (!env.SESSION_SECRET) return toLogin(url);
      const s = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
      if (!s) return toLogin(url);
    } catch (e) {
      console.log("session gate error", String(e));
      return toLogin(url);
    }
    return next();
  }

  return next();
}
