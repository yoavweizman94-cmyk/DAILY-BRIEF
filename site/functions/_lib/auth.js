// שכבת האימות — גיבוב סיסמאות, עוגיות סשן, והגבלת קצב.
//
// הערות תכנון:
//   · PBKDF2-SHA256 ולא bcrypt/argon2: ל-Workers אין אותם, ו-WebCrypto
//     נותן PBKDF2 מקורי. 210,000 סבבים הוא ההמלצה של OWASP ל-SHA-256.
//   · ההשוואה בזמן קבוע בכל מקום שמשווים בו סוד — גם על הגיבוב וגם על
//     חתימת הסשן. השוואת === דולפת מידע דרך זמן הריצה.
//   · המשתמשים ב-KV ולא ב-D1: רשימת מנויים קטנה, גישה לפי מפתח בלבד,
//     ואין שאילתות. D1 היה מוסיף תפעול בלי להוסיף יכולת.

// Workers חוסם PBKDF2 מעל 100,000 סבבים בקריאה אחת:
//   NotSupportedError: iteration counts above 100000 are not supported
// לכן הגזירה משורשרת — כל קריאה בתקרה, והפלט של אחת מזין את הבאה
// כסיסמה. שלושה סבבים נותנים 300,000 אפקטיבי, מעל בסיס ההמלצה של OWASP,
// בלי לחרוג ממגבלת הפלטפורמה.
const ROUND_ITERS = 100000;
const ROUNDS = 3;
const ITERATIONS = ROUND_ITERS * ROUNDS;
const KEYLEN = 32;
const SESSION_DAYS = 30;
export const COOKIE = "tlv_session";

const enc = new TextEncoder();

export function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function unb64url(str) {
  const s = str.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(s + "=".repeat((4 - (s.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// השוואה בזמן קבוע. אורך שונה מוחזר כשקר מיד — האורך עצמו אינו סוד.
export function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function derive(material, salt) {
  const key = await crypto.subtle.importKey("raw", material, "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: ROUND_ITERS, hash: "SHA-256" }, key, KEYLEN * 8);
  return new Uint8Array(bits);
}

export async function hashPassword(password, saltB64) {
  const salt = saltB64 ? unb64url(saltB64) : crypto.getRandomValues(new Uint8Array(16));
  let out = enc.encode(password);
  for (let i = 0; i < ROUNDS; i++) out = await derive(out, salt);
  return { hash: b64url(out), salt: b64url(salt), iterations: ITERATIONS };
}

export async function verifyPassword(password, user) {
  if (!user || !user.hash || !user.salt) return false;
  const { hash } = await hashPassword(password, user.salt);
  return timingSafeEqual(hash, user.hash);
}

async function hmac(secret, data) {
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}

export async function makeSession(email, secret) {
  const payload = b64url(enc.encode(JSON.stringify({
    e: email, x: Date.now() + SESSION_DAYS * 86400000,
  })));
  return `${payload}.${await hmac(secret, payload)}`;
}

export async function readSession(token, secret) {
  if (!token || token.indexOf(".") < 0) return null;
  const [payload, sig] = token.split(".");
  if (!timingSafeEqual(sig || "", await hmac(secret, payload))) return null;
  let data;
  try {
    data = JSON.parse(new TextDecoder().decode(unb64url(payload)));
  } catch { return null; }
  if (!data || !data.e || !data.x || Date.now() > data.x) return null;
  return data;
}

export function sessionCookie(token, host) {
  const maxAge = SESSION_DAYS * 86400;
  return `${COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

export function clearCookie() {
  return `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

export function readCookie(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

export const userKey = (email) => `user:${email.toLowerCase()}`;

export async function getUser(env, email) {
  if (!env.USERS) return null;
  return await env.USERS.get(userKey(email), { type: "json" });
}

export async function putUser(env, email, user) {
  await env.USERS.put(userKey(email), JSON.stringify(user));
}

// הגבלת קצב. ה-KV הוא eventually consistent, ולכן זו האטה ולא מחסום
// הרמטי — די בה כדי להפוך ניחוש סיסמאות בכוח לבלתי מעשי.
export async function rateLimit(env, key, limit, windowSec) {
  if (!env.USERS) return { ok: true, left: limit };
  const k = `rl:${key}`;
  const cur = parseInt((await env.USERS.get(k)) || "0", 10);
  if (cur >= limit) return { ok: false, left: 0 };
  await env.USERS.put(k, String(cur + 1), { expirationTtl: windowSec });
  return { ok: true, left: limit - cur - 1 };
}

export async function clearRate(env, key) {
  if (env.USERS) await env.USERS.delete(`rl:${key}`);
}

export function json(obj, status = 200, headers = {}) {
  return new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json", ...headers },
  });
}

// מדיניות סיסמה. אורך הוא הגורם היחיד שבאמת משנה כאן; דרישות תווים
// דוחפות משתמשים לדפוסים צפויים ואינן מוסיפות אנטרופיה של ממש.
export function passwordProblem(pw) {
  if (typeof pw !== "string" || pw.length < 10) return "הסיסמה חייבת להיות באורך 10 תווים לפחות";
  if (pw.length > 200) return "הסיסמה ארוכה מדי";
  if (/^\s|\s$/.test(pw)) return "הסיסמה אינה יכולה להתחיל או להסתיים ברווח";
  return null;
}

export function normEmail(s) {
  return String(s || "").trim().toLowerCase().slice(0, 120);
}

export function validEmail(s) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s);
}
