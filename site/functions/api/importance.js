// דירוג החשיבות של חברות הכיסוי — לבעלים בלבד, קריאה וכתיבה.
//
// **למה ב-KV ולא בריפו.** הריפו ציבורי, והדירוג הוא המבט הפנימי של
// הבעלים על החברות. ב-KV הוא פרטי ונקרא רק דרך הנתיב הזה.
//
// **מסמך אחד, עם מספר גרסה.** הדפדפן שולח את כל הדירוג בכל שמירה, יחד
// עם הגרסה שממנה התחיל. גרסה שאינה תואמת — לשונית אחרת שמרה בינתיים —
// מחזירה 409 ואת המסמך העדכני, והדפדפן ממזג את השינויים שלו מעליו. KV
// אינו מספק compare-and-set, ולכן זו הגנה מפני התנגשות בין לשוניות ולא
// נעילה הרמטית; לעורך יחיד זה מספיק.
//
// **בלי rateLimit כאן, בכוונה.** המונה שלו הוא בעצמו כתיבה ל-KV, ומכסת
// הכתיבות היומית משותפת עם ההתחברות — מונה על כל שמירה היה מכפיל את
// הכתיבות. הנתיב סגור לכל מי שאינו הבעלים, והדפדפן מאגד שינויים.
import { readCookie, readSession, getUser, normEmail, json, COOKIE }
  from "../_lib/auth.js";

const KEY = "coverage:importance";
const MAX_BODY = 64 * 1024;
const MAX_IDS = 2000;
const ID = /^[0-9]{3,12}$/;
const NO_STORE = { "Cache-Control": "no-store" };

// **נכשל סגור**, באותו סדר כמו api/pending.js: בלי סוד או KV אין דרך
// לאמת; בלי סשן תקף — 401; חשבון שאינו פעיל — 401; ורק אז הבעלות.
async function requireOwner(request, env) {
  if (!env.SESSION_SECRET || !env.USERS) return json({ error: "לא מוגדר" }, 503);
  const sess = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!sess) return json({ error: "נדרשת התחברות" }, 401);
  const me = await getUser(env, sess.e);
  if (!me || me.status !== "active") return json({ error: "נדרשת התחברות" }, 401);
  const owner = normEmail(env.OWNER_EMAIL || "");
  if (!owner || normEmail(sess.e) !== owner) {
    return json({
      error: owner ? "אין הרשאה" : "לא הוגדרה כתובת בעלים",
      owner: false, ownerConfigured: Boolean(owner),
    }, 403);
  }
  return null;
}

async function readDoc(env) {
  const d = await env.USERS.get(KEY, { type: "json" });
  if (!d || typeof d !== "object" || !d.levels || typeof d.levels !== "object") {
    return { levels: {}, rev: 0, updated: null };
  }
  return { levels: d.levels, rev: Number(d.rev) || 0, updated: d.updated || null };
}

export async function onRequestGet({ request, env }) {
  const denied = await requireOwner(request, env);
  if (denied) return denied;
  return json({ owner: true, ...(await readDoc(env)) }, 200, NO_STORE);
}

export async function onRequestPost({ request, env }) {
  const denied = await requireOwner(request, env);
  if (denied) return denied;

  // העוגייה היא SameSite=Lax, ולכן דפדפן אינו מצרף אותה ל-POST שנשלח
  // מאתר אחר ממילא. בדיקת המקור היא שכבה שנייה, לא הראשונה.
  const origin = request.headers.get("Origin");
  if (origin && origin !== new URL(request.url).origin) {
    return json({ error: "מקור לא מורשה" }, 403);
  }

  if (Number(request.headers.get("Content-Length") || 0) > MAX_BODY) {
    return json({ error: "הבקשה גדולה מדי" }, 413);
  }
  let text;
  try { text = await request.text(); } catch { return json({ error: "בקשה לא תקינה" }, 400); }
  if (text.length > MAX_BODY) return json({ error: "הבקשה גדולה מדי" }, 413);

  let body;
  try { body = JSON.parse(text); } catch { return json({ error: "בקשה לא תקינה" }, 400); }
  const src = body && body.levels;
  if (!src || typeof src !== "object" || Array.isArray(src)) {
    return json({ error: "חסר דירוג" }, 400);
  }
  const ids = Object.keys(src);
  if (ids.length > MAX_IDS) return json({ error: "יותר מדי חברות" }, 400);
  const levels = {};
  for (const id of ids) {
    const v = src[id];
    if (!ID.test(id) || !Number.isInteger(v) || v < 1 || v > 5) {
      return json({ error: `ערך לא תקין עבור ${String(id).slice(0, 20)}` }, 400);
    }
    levels[id] = v;
  }
  const base = Number.isInteger(body.rev) ? body.rev : -1;

  const cur = await readDoc(env);
  if (base !== cur.rev) {
    return json({ error: "הדירוג עודכן בינתיים", conflict: true, ...cur }, 409, NO_STORE);
  }
  const doc = { v: 1, rev: cur.rev + 1, updated: new Date().toISOString(), levels };
  await env.USERS.put(KEY, JSON.stringify(doc));
  return json({ ok: true, rev: doc.rev, updated: doc.updated }, 200, NO_STORE);
}
