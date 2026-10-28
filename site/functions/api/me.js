// מי מחובר. משמש את דף האפליקציה כדי להציג את השם ואת קישור היציאה, ואת
// הקישורים של הבעלים ("השיחות שלי") — owner הוא תצוגה בלבד; השער ב-_middleware.js.
import { readCookie, readSession, getUser, normEmail, COOKIE, json } from "../_lib/auth.js";

export async function onRequestGet(context) {
  const { request, env } = context;
  if (!env.SESSION_SECRET) return json({ error: "לא מוגדר" }, 503);
  const s = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!s) return json({ authenticated: false }, 401);
  const user = await getUser(env, s.e);
  if (!user || user.status !== "active") return json({ authenticated: false }, 401);
  const owner = normEmail(env.OWNER_EMAIL || "");
  return json({ authenticated: true, email: user.email, name: user.name,
                owner: Boolean(owner) && normEmail(user.email) === owner });
}
