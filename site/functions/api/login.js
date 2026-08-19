// כניסה. מחזירה עוגיית סשן חתומה בלבד — הסיסמה עצמה אינה נשמרת בשום
// מקום מלבד הגיבוב, ואינה מוחזרת ללקוח.
import {
  verifyPassword, getUser, putUser, makeSession, sessionCookie,
  rateLimit, clearRate, json, normEmail,
} from "../../lib/auth.js";

// הודעה אחת לכל כשל. הפרדה בין "אין משתמש" ל"סיסמה שגויה" מסגירה
// אילו כתובות רשומות בשירות, וזו רשימת לקוחות.
const GENERIC = "שם משתמש או סיסמה שגויים";

export async function onRequestPost(context) {
  const { request, env } = context;

  if (!env.USERS || !env.SESSION_SECRET) {
    return json({ error: "השירות אינו מוגדר במלואו" }, 503);
  }

  let body;
  try { body = await request.json(); } catch { return json({ error: "בקשה לא תקינה" }, 400); }
  const email = normEmail(body.email);
  const password = String(body.password || "");
  if (!email || !password) return json({ error: GENERIC }, 401);

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  // שתי תקרות: לפי חשבון, כדי שלא ינחשו סיסמה למשתמש מסוים; ולפי IP,
  // כדי שלא יסרקו רשימת כתובות מאותו מקור.
  const byUser = await rateLimit(env, `login:${email}`, 8, 900);
  const byIp = await rateLimit(env, `loginip:${ip}`, 30, 900);
  if (!byUser.ok || !byIp.ok) {
    return json({ error: "יותר מדי ניסיונות. נסה שוב בעוד רבע שעה." }, 429);
  }

  const user = await getUser(env, email);
  const ok = await verifyPassword(password, user);
  if (!user || !ok) return json({ error: GENERIC }, 401);

  if (user.status === "pending") {
    return json({ error: "החשבון עדיין ממתין לאישור. תקבל מייל כשהוא יופעל." }, 403);
  }
  if (user.status !== "active") {
    return json({ error: "החשבון מושבת." }, 403);
  }

  await clearRate(env, `login:${email}`);
  user.lastLogin = new Date().toISOString();
  await putUser(env, email, user);

  const token = await makeSession(email, env.SESSION_SECRET);
  return json({ ok: true, name: user.name }, 200, {
    "Set-Cookie": sessionCookie(token),
  });
}
