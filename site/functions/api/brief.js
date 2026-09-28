// הפקת ברייף לפי דרישה — כפתור בעמוד, לא רק cron.
//
// **למה בעלים בלבד.** ריצה עולה כסף אמיתי: מהדורה באופוס היא דולרים בודדים,
// והיתרה כבר אזלה פעמיים בשבועיים. לכן אותו שער כמו דירוג החשיבות — סשן פעיל
// ו-OWNER_EMAIL — ומעליו מגביל קצב על אותו KV, כדי ששתי לחיצות עצבניות לא
// יפיקו שתי מהדורות.
//
// **מה זה מפעיל.** workflow_dispatch של daily-brief.yml דרך ה-API של GitHub.
// הריצה עצמה היא זו שכבר רצה בתזמון, עם אותם מעקות: `reviews` נשאר ריק כדי
// שלא ייכתבו סקירות דוחות בטעות, והמהדורה נבחרת מרשימה סגורה.
//
// **שתי דרכים, ושתיהן חיות.** עם GITHUB_DISPATCH_TOKEN — אסימון fine-grained
// לריפו הזה עם הרשאת Actions: Read and write — הריצה משוגרת מיד. בלעדיו
// הבקשה נרשמת ל-KV, ו-.github/workflows/brief-request.yml תובע אותה בפעימה
// הקרובה (עד עשר דקות) ומריץ את המהדורה. כך הכפתור עובד בלי שום הגדרה,
// והאסימון הוא שדרוג לזמן תגובה ולא תנאי לקיום.
import { readCookie, readSession, getUser, normEmail, json, COOKIE, rateLimit } from "../_lib/auth.js";

const REPO = "yoavweizman94-cmyk/DAILY-BRIEF";
const WORKFLOW = "daily-brief.yml";
const EDITIONS = ["", "morning", "midday", "close", "night"];
const LABEL = { "": "לפי השעה", morning: "בוקר", midday: "צהריים", close: "נעילה", night: "לילה" };
const PER_HOUR = 6;
const NO_STORE = { "Cache-Control": "no-store" };
const QUEUE_KEY = "brief:request";
const QUEUE_TTL = 14400;         // ארבע שעות. שעתיים לא הספיקו: הפעימה שאמורה
                                 // לרוץ כל עשר דקות מאחרת שעה וחצי ויותר, ובקשה
                                 // שפגה לפני שנתבעה היא לחיצה שנעלמה בשקט.
// **לא "עשר דקות".** הפעימה מתוזמנת לכל עשר דקות, אבל GitHub מריץ תזמונים
// באיחור ובדילוגים: נמדד 28/09/2026 שריצה שאמורה להיות כל חצי שעה יצאה
// אחת לשעתיים, ופעימת ה-10 דקות לא יצאה כלל במשך שעה וחצי. להבטיח לקורא
// עשר דקות זה לשקר לו, ולכן הניסוח אומר מה באמת ידוע.
const QUEUE_WAIT = "בפעימה הקרובה של GitHub (לעיתים שעה ויותר)";
const SETUP = "צור אסימון GitHub fine-grained לריפו DAILY-BRIEF עם הרשאת Actions: Read and write, "
  + "והוסף אותו ב-Cloudflare Pages → Settings → Environment variables בשם GITHUB_DISPATCH_TOKEN. "
  + "בלעדיו ההפקה עדיין עובדת, אבל מתחילה בפעימה הקרובה ולא מיד.";

async function requireOwner(request, env) {
  if (!env.SESSION_SECRET || !env.USERS) return { denied: json({ error: "לא מוגדר" }, 503) };
  const sess = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!sess) return { denied: json({ error: "נדרשת התחברות" }, 401) };
  const me = await getUser(env, sess.e);
  if (!me || me.status !== "active") return { denied: json({ error: "נדרשת התחברות" }, 401) };
  const owner = normEmail(env.OWNER_EMAIL || "");
  if (!owner || normEmail(sess.e) !== owner) {
    return { denied: json({ error: owner ? "אין הרשאה" : "לא הוגדרה כתובת בעלים", owner: false }, 403) };
  }
  return { email: normEmail(sess.e) };
}

// המצב לכפתור: האם המשתמש בעלים, ואילו מהדורות אפשר לבקש.
export async function onRequestGet({ request, env }) {
  const { denied } = await requireOwner(request, env);
  if (denied) return denied;
  const direct = Boolean(env.GITHUB_DISPATCH_TOKEN);
  return json({
    owner: true,
    ready: direct || Boolean(env.USERS),
    mode: direct ? "direct" : (env.USERS ? "queued" : "none"),
    wait: direct ? null : QUEUE_WAIT,
    setup: direct ? null : SETUP,
    editions: EDITIONS.map((v) => ({ value: v, label: LABEL[v] })),
  }, 200, NO_STORE);
}

export async function onRequestPost({ request, env }) {
  const { denied, email } = await requireOwner(request, env);
  if (denied) return denied;

  // העוגייה היא SameSite=Lax ולכן בקשה חוצת־אתר אינה נושאת אותה, אבל בקשה
  // מאותו אתר כן — ולכן בדיקת Origin, כמו ב-api/importance.js.
  const origin = request.headers.get("Origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) {
    return json({ error: "מקור לא מורשה" }, 403);
  }

  let body = {};
  try {
    body = await request.json();
  } catch { /* גוף ריק = מהדורה לפי השעה */ }
  const edition = String(body.edition || "");
  if (!EDITIONS.includes(edition)) return json({ error: "מהדורה לא מוכרת" }, 400);

  const rl = await rateLimit(env, `brief:${email}`, PER_HOUR, 3600);
  if (!rl.ok) return json({ error: `עד ${PER_HOUR} הפקות בשעה` }, 429);

  // בלי אסימון: הבקשה נרשמת ל-KV ונתבעת בפעימה הקרובה. מפתח אחד בכוונה —
  // שתי לחיצות עוקבות הן בקשה אחת, לא שתי מהדורות.
  if (!env.GITHUB_DISPATCH_TOKEN) {
    if (!env.USERS) return json({ error: "לא הוגדר אסימון הפעלה", setup: SETUP }, 501);
    await env.USERS.put(QUEUE_KEY, JSON.stringify({
      edition, at: new Date().toISOString(), by: email,
    }), { expirationTtl: QUEUE_TTL });
    return json({
      ok: true,
      edition,
      queued: true,
      label: LABEL[edition],
      message: `נרשמה בקשה להפקת ברייף (${LABEL[edition]}). ההפקה מתחילה ${QUEUE_WAIT} ונמשכת 10–15 דקות. `
        + "להתחלה מיידית צריך אסימון — ראה המדריך.",
      runs: `https://github.com/${REPO}/actions/workflows/brief-request.yml`,
    }, 202, NO_STORE);
  }

  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "tlv-tase-view",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs: { edition, reviews: "" } }),
  });
  if (res.status !== 204) {
    const detail = (await res.text().catch(() => "")).slice(0, 200);
    return json({ error: `GitHub השיב ${res.status}`, detail }, 502);
  }
  return json({
    ok: true,
    edition,
    label: LABEL[edition],
    message: `הופעלה הפקת ברייף (${LABEL[edition]}). היא נמשכת 10–15 דקות, והעמוד יתעדכן בסיומה.`,
    runs: `https://github.com/${REPO}/actions/workflows/${WORKFLOW}`,
  }, 202, NO_STORE);
}
