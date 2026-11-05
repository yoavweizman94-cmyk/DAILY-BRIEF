// מתג הגישה לכתובת החלופית (forest-brief.pages.dev), לבעלים בלבד.
//   GET  → { mode, host }
//   POST { mode: "owner" | "users" | "off" } → נשמר ב-KV
// השער עצמו ב-_middleware.js, והמצבים ב-_lib/alt.js.
//
// **KV מתעדכן בקצוות תוך כדקה**, ולכן שינוי אינו חל מיד בכל מקום. דף החשבון
// אומר זאת, כדי שבדיקה אחרי עשר שניות לא תיראה כמו מתג שלא עובד.
import { readCookie, readSession, getUser, normEmail, json, COOKIE }
  from "../_lib/auth.js";
import { ALT, ALT_KEY, ALT_MODES, altMode } from "../_lib/alt.js";

const NO_STORE = { "Cache-Control": "no-store" };

// **נכשל סגור**, באותו סדר כמו api/importance.js.
async function requireOwner(request, env) {
  if (!env.SESSION_SECRET || !env.USERS) return json({ error: "לא מוגדר" }, 503);
  const sess = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!sess) return json({ error: "נדרשת התחברות" }, 401);
  const me = await getUser(env, sess.e);
  if (!me || me.status !== "active") return json({ error: "נדרשת התחברות" }, 401);
  const owner = normEmail(env.OWNER_EMAIL || "");
  if (!owner || normEmail(sess.e) !== owner) return json({ error: "אין הרשאה" }, 403);
  return null;
}

export async function onRequestGet({ request, env }) {
  const denied = await requireOwner(request, env);
  if (denied) return denied;
  return json({ mode: await altMode(env), host: ALT }, 200, NO_STORE);
}

export async function onRequestPost({ request, env }) {
  const denied = await requireOwner(request, env);
  if (denied) return denied;

  // העוגייה היא SameSite=Lax, ולכן דפדפן אינו מצרף אותה ל-POST מאתר אחר
  // ממילא. בדיקת המקור היא שכבה שנייה, כמו ב-api/importance.js.
  const origin = request.headers.get("Origin");
  if (origin && origin !== new URL(request.url).origin) {
    return json({ error: "מקור לא מורשה" }, 403);
  }

  let body;
  try { body = await request.json(); } catch { return json({ error: "בקשה לא תקינה" }, 400); }
  const mode = String((body && body.mode) || "");
  if (!ALT_MODES.includes(mode)) return json({ error: "מצב לא מוכר" }, 400);
  await env.USERS.put(ALT_KEY, mode);
  return json({ ok: true, mode, host: ALT }, 200, NO_STORE);
}
