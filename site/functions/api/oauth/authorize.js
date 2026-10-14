// נקודת ההרשאה של OAuth: כאן הבעלים מאשר ש-Claude יקרא את האתר בשמו.
//
// הזרימה: claude.ai פותח את הדף הזה בחלון → בלי סשן מפנים לדף הכניסה של
// האתר, שמחזיר לכאן (next) → דף אישור עם שם הלקוח והחשבון → "אישור" יוצר
// קוד חד-פעמי (עשר דקות) ומחזיר אותו לכתובת החזרה הרשומה של הלקוח.
//
// **שגיאה לפני שכתובת החזרה אומתה מוצגת כאן, לא מוחזרת.** הפניה לכתובת
// שהלקוח לא רשם היא בדיוק מה שהופך שרת הרשאה למפנה פתוח.
import { readCookie, readSession, COOKIE, normEmail } from "../../_lib/auth.js";
import {
  SCOPE, CODE_TTL, allowedUser, consentOk, consentToken, esc, getClient, messagePage,
  mcpResource, origin, page, putCode, randomToken, readBody,
} from "../../_lib/oauth.js";

const FIELDS = ["response_type", "client_id", "redirect_uri", "code_challenge",
  "code_challenge_method", "state", "scope", "resource"];

function pick(src) {
  const get = (k) => (typeof src.get === "function" ? src.get(k) : src[k]);
  const p = {};
  for (const k of FIELDS) {
    const v = get(k);
    p[k] = typeof v === "string" ? v.slice(0, 2000) : "";
  }
  return p;
}

// בדיקת הבקשה. fatal — מוצג למשתמש; error — חוזר ללקוח בכתובת שאומתה.
async function check(env, request, p) {
  const client = await getClient(env, p.client_id);
  if (!client) return { fatal: "הלקוח אינו רשום. הסר את המחבר ב-Claude והוסף אותו מחדש." };
  let redirect = p.redirect_uri;
  if (!redirect && client.redirect_uris.length === 1) redirect = client.redirect_uris[0];
  if (!redirect || !client.redirect_uris.includes(redirect)) {
    return { fatal: "כתובת החזרה אינה רשומה ללקוח הזה." };
  }
  const v = { client, redirect };
  if (p.response_type !== "code") return { ...v, error: "unsupported_response_type" };
  if (!p.code_challenge || p.code_challenge_method !== "S256") {
    return { ...v, error: "invalid_request", desc: "PKCE עם S256 נדרש" };
  }
  if (p.resource && !p.resource.startsWith(origin(request))) {
    return { ...v, error: "invalid_target", desc: "המשאב אינו שרת ה-MCP של האתר" };
  }
  return v;
}

function back(redirect, q) {
  const u = new URL(redirect);
  for (const [k, v] of Object.entries(q)) if (v != null && v !== "") u.searchParams.set(k, v);
  return Response.redirect(u.toString(), 302);
}

const NOT_ALLOWED = (email) => messagePage("אין הרשאה",
  `החיבור של Claude לאתר פתוח לחשבון הבעלים בלבד, והחשבון <span class="who">${esc(email)}</span> אינו מורשה.`, 403);

export async function onRequestGet({ request, env }) {
  if (!env.USERS || !env.SESSION_SECRET) return messagePage("השירות אינו מוגדר", "חסרה תצורה בצד השרת.", 503);
  const url = new URL(request.url);
  const p = pick(url.searchParams);
  const v = await check(env, request, p);
  if (v.fatal) return messagePage("הבקשה אינה תקינה", esc(v.fatal), 400);
  if (v.error) return back(v.redirect, { error: v.error, error_description: v.desc, state: p.state, iss: origin(request) });

  const sess = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!sess) {
    return Response.redirect(`${origin(request)}/login?next=${encodeURIComponent(url.pathname + url.search)}`, 302);
  }
  const sub = normEmail(sess.e);
  if (!(await allowedUser(env, sub))) return NOT_ALLOWED(sub);

  const csrf = await consentToken(env.SESSION_SECRET, sub, { ...p, redirect_uri: v.redirect });
  const hidden = FIELDS.map((k) => `<input type="hidden" name="${k}" value="${esc(k === "redirect_uri" ? v.redirect : p[k])}">`).join("\n    ");
  const host = new URL(v.redirect).host;
  return page("חיבור Claude לאתר", `<section class="auth">
  <h1>חיבור לאתר</h1>
  <p class="auth-sub"><b>${esc(v.client.client_name)}</b> מבקש גישה לתוכן של TLV TASE View בשם החשבון <span class="who">${esc(sub)}</span>.</p>
  <ul class="grant">
    <li>קריאה בלבד: הברייפים, דיווחי מאיה, השווקים, הסחורות, שוק הדיור, עסקאות מחוץ לבורסה ושאר עמודי האתר.</li>
    <li>החיבור נשאר פעיל עד שתנתק אותו ב-Claude, או עד שהחשבון יושבת.</li>
    <li>אחרי האישור תוחזר אל <span class="who">${esc(host)}</span>.</li>
  </ul>
  <form method="post" action="/api/oauth/authorize">
    ${hidden}
    <input type="hidden" name="csrf" value="${esc(csrf)}">
    <div class="acts">
      <button type="submit" name="action" value="approve">אישור</button>
      <button type="submit" name="action" value="deny" class="secondary">ביטול</button>
    </div>
  </form>
</section>`);
}

export async function onRequestPost({ request, env }) {
  if (!env.USERS || !env.SESSION_SECRET) return messagePage("השירות אינו מוגדר", "חסרה תצורה בצד השרת.", 503);
  const body = await readBody(request);
  const p = pick(body);
  const v = await check(env, request, p);
  if (v.fatal) return messagePage("הבקשה אינה תקינה", esc(v.fatal), 400);
  if (v.error) return back(v.redirect, { error: v.error, error_description: v.desc, state: p.state, iss: origin(request) });

  const sess = await readSession(readCookie(request, COOKIE), env.SESSION_SECRET);
  if (!sess) return messagePage("פג תוקף הכניסה", "היכנס שוב לאתר והתחל את החיבור מחדש מ-Claude.", 401);
  const sub = normEmail(sess.e);
  if (!(await allowedUser(env, sub))) return NOT_ALLOWED(sub);
  if (!(await consentOk(env.SESSION_SECRET, sub, { ...p, redirect_uri: v.redirect }, body.csrf))) {
    return messagePage("הבקשה פגה", "דף האישור היה פתוח יותר מרבע שעה, או ששונה. התחל את החיבור מחדש מ-Claude.", 400);
  }

  if (body.action !== "approve") {
    return back(v.redirect, { error: "access_denied", state: p.state, iss: origin(request) });
  }
  const code = randomToken(32);
  await putCode(env, code, {
    client_id: v.client.client_id,
    redirect_uri: v.redirect,
    challenge: p.code_challenge,
    sub,
    scope: SCOPE,
    resource: p.resource || mcpResource(request),
    exp: Math.floor(Date.now() / 1000) + CODE_TTL,
  });
  return back(v.redirect, { code, state: p.state, iss: origin(request) });
}
