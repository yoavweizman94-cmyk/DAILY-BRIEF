// ניתוב לפי שם המארח.
//
// אותו פרויקט Pages מגיש שלושה דברים שונים, והפרדה ביניהם היא מה שמאפשר
// לעמוד הנחיתה להיות ציבורי בעוד התוכן מוגן:
//
//   tlvtaseview.com       → עמוד הנחיתה. ציבורי. Access אינו חוסם אותו.
//   app.tlvtaseview.com   → הדשבורד והחיפושים. מאחורי Cloudflare Access.
//   *.pages.dev           → מוסט, כדי שלא ישמש כניסה עוקפת לתוכן.
//
// ההפרדה חייבת להיות כאן ולא רק ב-Access: בלעדיה, ברגע שהאפקס משוחרר
// מהגנה הוא היה מגיש את הדשבורד עצמו לכל אחד.
const APEX = "tlvtaseview.com";
const APP = "app.tlvtaseview.com";

// הנתיבים שמותר להגיש באפקס: העמוד עצמו, הנכסים שהוא צריך, וה-API
// של בקשת הגישה. כל השאר שייך לאפליקציה.
const PUBLIC = /^\/(landing\.html)?$|^\/(style\.css|favicon\.ico|robots\.txt)$|^\/api\//;

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);
  const host = url.hostname;

  if (host.endsWith(".pages.dev")) {
    return Response.redirect(`https://${APP}${url.pathname}${url.search}`, 301);
  }

  if (host === APEX || host === `www.${APEX}`) {
    if (!PUBLIC.test(url.pathname)) {
      // תוכן האפליקציה אינו מוגש כאן — מפנים לכתובת המוגנת
      return Response.redirect(`https://${APP}${url.pathname}${url.search}`, 302);
    }
    if (url.pathname === "/") {
      url.pathname = "/landing.html";
      return next(new Request(url.toString(), request));
    }
    return next();
  }

  if (host === APP && url.pathname === "/landing.html") {
    return Response.redirect(`https://${APEX}/`, 302);
  }
  return next();
}
