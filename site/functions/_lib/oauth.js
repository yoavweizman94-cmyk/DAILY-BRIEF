// OAuth 2.1 לשרת ה-MCP של האתר — כדי שמחבר ב-claude.ai יתחבר בשם המשתמש,
// פעם אחת, ויישאר מחובר.
//
// **למה OAuth ולא אסימון בכתובת.** מחבר מותאם ב-claude.ai מקבל כתובת בלבד,
// ומתחבר דרך OAuth: מגלה את שרת ההרשאה מהכתובת (RFC 9728 ← RFC 8414), נרשם
// בעצמו (RFC 7591), שולח את המשתמש לדף הכניסה של האתר, ומקבל אסימון גישה
// ואסימון רענון. אסימון קבוע בנתיב הוא סוד שעובר ביד, מופיע בצילומי מסך
// ואינו קשור לאף משתמש; כאן הגישה ניתנת מהחשבון באתר, בסיסמה שלו, והמחבר
// מתרענן לבד.
//
// **רק הבעלים.** הרשאה ניתנת רק למשתמש פעיל שהוא OWNER_EMAIL. מנוי אחר
// שיגיע לדף ההרשאה יקבל "אין הרשאה": המחבר מגיש את כל תוכן האתר, וההחלטה
// למי לפתוח אותו בהיקף כזה היא של הבעלים — לא ברירת מחדל של הקוד.
//
// **גישה תמידית.** אסימון הגישה חתום (אין קריאת KV בכל קריאת כלי) ותקף
// יממה; אסימון הרענון נשמר ב-KV בלי תפוגה, ומתחלף בכל רענון כפי ש-OAuth 2.1
// דורש מלקוח ציבורי. הישן נשאר תקף עשר דקות אחרי ההחלפה, כדי שרענון כפול
// או ניסיון חוזר של הלקוח לא ינתקו את המחבר. בכל רענון נבדק שהמשתמש עדיין
// פעיל ועדיין הבעלים, ולכן השבתת החשבון מנתקת את המחבר תוך יממה לכל היותר.
//
// **מה נשמר.** ב-KV של המשתמשים: לקוחות רשומים, קודי הרשאה (עשר דקות)
// ואסימוני רענון — כולם לפי גיבוב SHA-256 ולא האסימון עצמו. סוד החתימה
// נגזר מ-SESSION_SECRET ואינו הוא, כך שאסימון גישה אינו יכול לשמש כעוגיית
// סשן ולהפך.
import { b64url, unb64url, timingSafeEqual, normEmail, getUser } from "./auth.js";

export const SCOPE = "mcp";
export const AT_TTL = 24 * 3600;      // אסימון גישה: יממה
export const CODE_TTL = 600;          // קוד הרשאה: עשר דקות
export const RT_GRACE = 600;          // אסימון רענון שהוחלף: עשר דקות חסד
export const AT_PREFIX = "tlvat.";

const enc = new TextEncoder();
const dec = new TextDecoder();
const now = () => Math.floor(Date.now() / 1000);

// --------------------------------------------------------------------------
// כתובות ומטא-דאטה

export function origin(request) {
  const u = new URL(request.url);
  return `${u.protocol}//${u.host}`;
}

export const mcpResource = (request) => `${origin(request)}/api/mcp`;
export const resourceMetadataUrl = (request) => `${origin(request)}/.well-known/oauth-protected-resource`;

export function protectedResourceMetadata(request) {
  return {
    resource: mcpResource(request),
    authorization_servers: [origin(request)],
    scopes_supported: [SCOPE],
    bearer_methods_supported: ["header"],
    resource_name: "TLV TASE View",
    resource_documentation: "https://tlvtaseview.com/",
  };
}

export function authServerMetadata(request) {
  const o = origin(request);
  return {
    issuer: o,
    authorization_endpoint: `${o}/api/oauth/authorize`,
    token_endpoint: `${o}/api/oauth/token`,
    registration_endpoint: `${o}/api/oauth/register`,
    revocation_endpoint: `${o}/api/oauth/revoke`,
    response_types_supported: ["code"],
    response_modes_supported: ["query"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["none", "client_secret_post", "client_secret_basic"],
    revocation_endpoint_auth_methods_supported: ["none", "client_secret_post", "client_secret_basic"],
    scopes_supported: [SCOPE],
    authorization_response_iss_parameter_supported: true,
  };
}

// /.well-known/... — מוגש מה-middleware, לפני שער הסשן. מחזיר null על נתיב
// שאינו שלנו, והבקשה ממשיכה כרגיל.
export function wellKnown(request, path) {
  const pr = path === "/.well-known/oauth-protected-resource"
    || path.startsWith("/.well-known/oauth-protected-resource/");
  const as = path === "/.well-known/oauth-authorization-server"
    || path.startsWith("/.well-known/oauth-authorization-server/")
    || path === "/.well-known/openid-configuration";
  if (!pr && !as) return null;
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
  return jsonr(pr ? protectedResourceMetadata(request) : authServerMetadata(request), 200,
    { "Cache-Control": "public, max-age=300" });
}

// --------------------------------------------------------------------------
// HTTP

export const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, MCP-Protocol-Version",
};

export function jsonr(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", Pragma: "no-cache", ...CORS, ...extra },
  });
}

export function oauthError(error, description, status = 400) {
  return jsonr({ error, error_description: description }, status);
}

export const preflight = () => new Response(null, { status: 204, headers: CORS });

// גוף בקשה: טופס, כפי שהמפרט דורש בנקודת האסימון — או JSON, שחלק מהלקוחות שולחים.
export async function readBody(request) {
  const ct = (request.headers.get("Content-Type") || "").toLowerCase();
  try {
    if (ct.includes("application/json")) {
      const o = await request.json();
      return o && typeof o === "object" ? o : {};
    }
    const f = await request.formData();
    const o = {};
    for (const [k, v] of f.entries()) o[k] = typeof v === "string" ? v : "";
    return o;
  } catch {
    return {};
  }
}

// --------------------------------------------------------------------------
// אסימונים

export function randomToken(n = 32) {
  return b64url(crypto.getRandomValues(new Uint8Array(n)));
}

export async function sha256(s) {
  return b64url(await crypto.subtle.digest("SHA-256", enc.encode(String(s))));
}

let keyCache = null;
async function signingKey(secret) {
  if (keyCache && keyCache.secret === secret) return keyCache.key;
  const base = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const raw = await crypto.subtle.sign("HMAC", base, enc.encode("tlv-mcp-oauth-v1"));
  const key = await crypto.subtle.importKey(
    "raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  keyCache = { secret, key };
  return key;
}

async function sign(secret, data) {
  return b64url(await crypto.subtle.sign("HMAC", await signingKey(secret), enc.encode(data)));
}

export async function issueAccessToken(secret, { sub, client_id, scope, aud }) {
  const payload = b64url(enc.encode(JSON.stringify(
    { typ: "at", sub, cid: client_id, scope, aud, exp: now() + AT_TTL })));
  return `${AT_PREFIX}${payload}.${await sign(secret, payload)}`;
}

export async function readAccessToken(secret, token) {
  if (!secret || typeof token !== "string" || !token.startsWith(AT_PREFIX)) return null;
  const parts = token.slice(AT_PREFIX.length).split(".");
  if (parts.length !== 2) return null;
  if (!timingSafeEqual(parts[1], await sign(secret, parts[0]))) return null;
  let c;
  try { c = JSON.parse(dec.decode(unb64url(parts[0]))); } catch { return null; }
  if (!c || c.typ !== "at" || !c.sub || !c.exp || now() > c.exp) return null;
  return c;
}

export async function pkceOk(verifier, challenge) {
  if (typeof verifier !== "string" || !/^[A-Za-z0-9._~-]{43,128}$/.test(verifier)) return false;
  return timingSafeEqual(await sha256(verifier), String(challenge || ""));
}

// אסימון הטופס בדף האישור: קושר את האישור לסשן ולפרמטרים שהוצגו, ופג
// אחרי רבע שעה. העוגייה היא SameSite=Lax, ולכן POST מאתר זר ממילא אינו
// נושא סשן — זה החגור השני.
function consentData(sub, p, exp) {
  return "consent|" + JSON.stringify([sub, p.client_id, p.redirect_uri, p.code_challenge,
    p.state || "", p.resource || "", exp]);
}

export async function consentToken(secret, sub, p) {
  const exp = now() + 900;
  return `${exp}.${await sign(secret, consentData(sub, p, exp))}`;
}

export async function consentOk(secret, sub, p, token) {
  const [exp, sig] = String(token || "").split(".");
  if (!exp || !sig || !/^\d+$/.test(exp) || now() > Number(exp)) return false;
  return timingSafeEqual(sig, await sign(secret, consentData(sub, p, Number(exp))));
}

// --------------------------------------------------------------------------
// מי רשאי

// משתמש פעיל שהוא הבעלים — ומחזיר אותו, או null.
export async function allowedUser(env, email) {
  const owner = normEmail(env.OWNER_EMAIL || "");
  const e = normEmail(email || "");
  if (!owner || !e || e !== owner) return null;
  const user = await getUser(env, e);
  return user && user.status === "active" ? user : null;
}

// כתובת חזרה: https, או http ל-localhost בלבד (Claude Code ולקוחות מקומיים).
export function redirectUriOk(u) {
  if (typeof u !== "string" || u.length > 400 || u.includes("#")) return false;
  let url;
  try { url = new URL(u); } catch { return false; }
  if (url.protocol === "https:") return true;
  return url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
}

// --------------------------------------------------------------------------
// KV

const K = {
  client: (id) => `oauth:client:${id}`,
  code: (h) => `oauth:code:${h}`,
  rt: (h) => `oauth:rt:${h}`,
};

export async function getClient(env, id) {
  if (typeof id !== "string" || !/^[A-Za-z0-9_-]{10,64}$/.test(id)) return null;
  return env.USERS.get(K.client(id), { type: "json" });
}

export async function putClient(env, client) {
  await env.USERS.put(K.client(client.client_id), JSON.stringify(client));
}

export async function putCode(env, code, data) {
  await env.USERS.put(K.code(await sha256(code)), JSON.stringify(data), { expirationTtl: CODE_TTL });
}

// קוד הרשאה הוא חד-פעמי: נמחק בקריאה הראשונה, גם אם הבדיקות שאחריה נכשלות.
export async function takeCode(env, code) {
  if (typeof code !== "string" || !code) return null;
  const k = K.code(await sha256(code));
  const d = await env.USERS.get(k, { type: "json" });
  if (d) await env.USERS.delete(k);
  return d;
}

export async function putRefresh(env, token, data, ttl) {
  await env.USERS.put(K.rt(await sha256(token)), JSON.stringify(data),
    ttl ? { expirationTtl: ttl } : undefined);
}

export async function getRefresh(env, token) {
  if (typeof token !== "string" || !token) return null;
  return env.USERS.get(K.rt(await sha256(token)), { type: "json" });
}

export async function dropRefresh(env, token) {
  if (typeof token === "string" && token) await env.USERS.delete(K.rt(await sha256(token)));
}

// אימות הלקוח בנקודת האסימון: client_id בגוף או ב-Basic, וסוד אם נרשם עם סוד.
export async function authClient(env, request, body) {
  let id = body.client_id;
  let secret = body.client_secret;
  const m = /^Basic\s+(\S+)$/i.exec(request.headers.get("Authorization") || "");
  if (m) {
    try {
      const raw = atob(m[1]);
      const i = raw.indexOf(":");
      id = decodeURIComponent(i < 0 ? raw : raw.slice(0, i));
      secret = decodeURIComponent(i < 0 ? "" : raw.slice(i + 1));
    } catch {
      return null;
    }
  }
  const client = await getClient(env, id);
  if (!client) return null;
  if (client.secret_hash) {
    if (typeof secret !== "string" || !secret
      || !timingSafeEqual(await sha256(secret), client.secret_hash)) return null;
  }
  return client;
}

// --------------------------------------------------------------------------
// דף

export function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// דף HTML בעיצוב של דף הכניסה. אסור להטמעה במסגרת — דף אישור שאפשר להלביש
// עליו שכבה שקופה הוא דף שאפשר לגרום ללחוץ עליו בלי לדעת.
export function page(title, body, status = 200) {
  const html = `<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta name="color-scheme" content="light dark">
<title>${esc(title)} · TLV TASE View</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700&family=Frank+Ruhl+Libre:wght@500;700;900&display=swap">
<link rel="stylesheet" href="/style.css">
<style>
.auth .grant { margin: 0 0 1.2rem; padding: 0; list-style: none; display: grid; gap: 0.55rem; font-size: 0.88rem; }
.auth .grant li { padding-inline-start: 1.1rem; position: relative; }
.auth .grant li::before { content: ""; position: absolute; inset-inline-start: 0; top: 0.55em; width: 0.4rem; height: 0.4rem; border-radius: 50%; background: var(--accent); }
.auth .who { font-family: "IBM Plex Mono", monospace; font-size: 0.85rem; direction: ltr; unicode-bidi: isolate; }
.auth .acts { display: flex; gap: 0.6rem; flex-wrap: wrap; }
.auth .acts button { flex: 1 1 8rem; }
.auth button.secondary { background: transparent; color: var(--fg); border-color: var(--border-strong); }
.auth button.secondary:hover { background: var(--bg); border-color: var(--border-strong); }
</style>
</head>
<body class="authpage">
<header>
  <a class="brand" href="https://tlvtaseview.com/">TLV TASE View<em>מחקר יומי · הבורסה בתל אביב</em></a>
</header>
<main>
${body}
</main>
<footer>
  <b>TLV TASE View</b>
  <span>אין באמור ייעוץ השקעות, שיווק השקעות או המלצה לפעולה בניירות ערך.</span>
</footer>
</body>
</html>`;
  return new Response(html, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Frame-Options": "DENY",
      "Content-Security-Policy": "frame-ancestors 'none'",
      "Referrer-Policy": "no-referrer",
    },
  });
}

export function messagePage(title, text, status) {
  return page(title, `<section class="auth">
  <h1>${esc(title)}</h1>
  <p class="auth-sub">${text}</p>
</section>`, status);
}
