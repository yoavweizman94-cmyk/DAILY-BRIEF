// בקשות גישה שממתינות לאישור — לבעלים בלבד.
//
// **למה זה קיים.** עד עכשיו הדרך היחידה לדעת שמישהו ביקש גישה הייתה
// מייל התראה. ב-26/08/2026 נרשם אדם ולא הגיעה הודעה, ולברר מה קרה
// דרש הרצת workflow וקריאת לוג. ערוץ יחיד שנכשל בשקט הוא ערוץ שאי
// אפשר לסמוך עליו; הרשימה כאן היא המקור, והמייל הוא רק התראה עליו.
//
// **אין כאן נתיב שינוי חדש.** האישור נעשה דרך קישור ה-HMAC הקיים,
// אותו קישור בדיוק שנשלח במייל — כלומר משטח הכתיבה נשאר אחד, נבדק,
// ומוגן בשומר של כתובת הבדיקה. הנתיב הזה קורא בלבד.
import { readCookie, readSession, getUser, normEmail, b64url, COOKIE, json }
  from "../_lib/auth.js";

// אותה כתובת ש-access-flow-check משתמש בה. היא מסומנת ולא מוסתרת:
// חשבון בדיקה שנשאר תקוע הוא עצמו תקלה שכדאי לראות.
const TEST_ADDRESS = "access-check@tlvtaseview.com";

async function sign(email, secret) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(email));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequestGet(context) {
  const { request, env } = context;

  // **נכשל סגור.** בהיעדר סוד אין דרך לאמת מי הפונה, ולכן דוחים.
  if (!env.SESSION_SECRET || !env.USERS) return json({ error: "לא מוגדר" }, 503);

  const sess = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!sess) return json({ error: "נדרשת התחברות" }, 401);

  const me = await getUser(env, sess.e);
  if (!me || me.status !== "active") return json({ error: "נדרשת התחברות" }, 401);

  // הרשימה מחזיקה שמות וכתובות של אנשים, ולכן היא לבעלים בלבד. משתמש
  // מחובר רגיל מקבל 403 ולא רשימה חלקית — אין כאן דרגות ביניים.
  const owner = normEmail(env.OWNER_EMAIL || "");
  if (!owner || normEmail(sess.e) !== owner) {
    return json({ error: "אין הרשאה" }, 403);
  }

  const base = new URL(request.url).origin;
  const out = [];
  let cursor;
  do {
    const page = await env.USERS.list({ prefix: "user:", cursor });
    for (const k of page.keys) {
      const email = k.name.slice(5);
      const u = await getUser(env, email);
      if (!u || u.status !== "pending") continue;
      const rec = {
        email, name: u.name || "", org: u.org || "", why: u.why || "",
        created: u.created || u.createdAt || null,
        test: email === TEST_ADDRESS,
      };
      // קישור האישור נוצר רק כשיש סוד, ורק לכתובת אמיתית. לחשבון
      // הבדיקה אין קישור בכוונה — הוא חסום להפעלה ממילא.
      if (env.APPROVAL_SECRET && !rec.test) {
        const t = await sign(email, env.APPROVAL_SECRET);
        rec.approve = `${base}/api/approve/${b64url(new TextEncoder().encode(email))}.${t}`;
      }
      out.push(rec);
    }
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);

  out.sort((a, b) => String(b.created || "").localeCompare(String(a.created || "")));
  return json({ pending: out, count: out.length });
}
