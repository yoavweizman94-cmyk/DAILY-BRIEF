// שומר סף לכתובת ה-pages.dev.
//
// Cloudflare Access מגן על tlvtaseview.com, אבל אותו פרויקט מוגש גם
// בכתובת forest-brief.pages.dev — ושם אין הגנה. נמדד: הדומיין החזיר 302
// למסך ההתחברות בעוד ה-pages.dev החזיר 200 עם האתר המלא. כלומר כל מי
// שיודע את הכתובת הזו עוקף את ההזדהות לחלוטין.
//
// הפונקציה הזו רצה לפני כל בקשה. בקשה שהגיעה דרך pages.dev מוסטת
// לדומיין המוגן במקום לקבל תוכן, כך שאין נתיב שמגיש את הברייפים בלי
// הזדהות. סגירה בשכבת האתר ולא בשכבת Access, כי היא אינה דורשת הרשאות
// נוספות ונפרסת יחד עם התוכן.
const CANONICAL = "tlvtaseview.com";

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.hostname.endsWith(".pages.dev")) {
    url.hostname = CANONICAL;
    url.protocol = "https:";
    url.port = "";
    return Response.redirect(url.toString(), 301);
  }
  return context.next();
}
