// החלפת סיסמה. דורשת סשן פעיל **וגם** את הסיסמה הנוכחית: עוגייה גנובה
// לבדה לא תספיק כדי לנעול את הבעלים מחוץ לחשבון שלו.
import {
  readCookie, readSession, getUser, putUser, verifyPassword, hashPassword,
  makeSession, sessionCookie, rateLimit, json, passwordProblem, COOKIE,
} from "../_lib/auth.js";

export async function onRequestPost(context) {
  const { request, env } = context;
  if (!env.USERS || !env.SESSION_SECRET) return json({ error: "השירות אינו מוגדר" }, 503);

  const s = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!s) return json({ error: "יש להתחבר מחדש" }, 401);

  let body;
  try { body = await request.json(); } catch { return json({ error: "בקשה לא תקינה" }, 400); }
  const current = String(body.current || "");
  const next = String(body.next || "");

  const err = passwordProblem(next);
  if (err) return json({ error: err }, 400);
  if (current === next) return json({ error: "הסיסמה החדשה זהה לנוכחית" }, 400);

  const rl = await rateLimit(env, `pw:${s.e}`, 8, 900);
  if (!rl.ok) return json({ error: "יותר מדי ניסיונות. נסה שוב בעוד רבע שעה." }, 429);

  const user = await getUser(env, s.e);
  if (!user || user.status !== "active") return json({ error: "החשבון אינו פעיל" }, 403);
  if (!(await verifyPassword(current, user))) {
    return json({ error: "הסיסמה הנוכחית שגויה" }, 401);
  }

  const { hash, salt, iterations } = await hashPassword(next);
  user.hash = hash;
  user.salt = salt;
  user.iterations = iterations;
  user.passwordChanged = new Date().toISOString();
  await putUser(env, s.e, user);

  // סשן חדש אחרי החלפה: מי שהחזיק בעוגייה הישנה ממשיך לעבוד אחרת, וזה
  // מבטל את עיקר התועלת שבהחלפת הסיסמה.
  const token = await makeSession(s.e, env.SESSION_SECRET);
  return json({ ok: true }, 200, { "Set-Cookie": sessionCookie(token) });
}
