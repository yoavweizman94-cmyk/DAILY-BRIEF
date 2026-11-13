// בדיקת עשן לכפתור "הפק" (site/functions/api/brief.js) — רצה מקומית, בלי Cloudflare ובלי GitHub.
//
// מריצה את הפונקציה עצמה מול KV בזיכרון ו-fetch מדומה, ובודקת את מה שהתור של daily-brief
// נשען עליו מאז 13/11/2026: כל לחיצה נרשמת ל-KV *לפני* השיגור, ואותה שעה בדיוק עוברת
// ב-requested_at; שיגור שנכשל מכל סיבה הופך לבקשה בתור ולא נעלם; ובלי KV ובלי אסימון —
// שגיאה ברורה. ולצידם מה שהיה קודם: בעלים בלבד, מקור זר, מהדורה לא מוכרת ומגבלת קצב.
//
// שימוש: node scripts/brief_smoke.mjs
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const F = (...p) => import(pathToFileURL(path.join(ROOT, "site", "functions", ...p)).href);
const auth = await F("_lib", "auth.js");
const brief = await F("api", "brief.js");

const APP = "https://app.example.com";
const OWNER = "owner@example.com";
const OTHER = "subscriber@example.com";
const QUEUE_KEY = "brief:request";

let failed = 0;
function check(cond, msg) {
  if (cond) console.log("  ✓ " + msg);
  else { console.log("  ✗ " + msg); failed++; }
}

// KV בזיכרון. failPut: מפתח שכתיבה אליו נכשלת, כדי לבדוק KV שאינו זמין.
function makeEnv({ token = "test-token", kv = true, failPut = null } = {}) {
  const store = new Map();
  const log = [];
  const USERS = {
    async get(k, opt) {
      const v = store.get(k);
      if (v === undefined) return null;
      return opt && opt.type === "json" ? JSON.parse(v) : v;
    },
    async put(k, v, opt) {
      if (k === failPut) throw new Error("KV down");
      log.push(["put", k, opt && opt.expirationTtl]);
      store.set(k, v);
    },
    async delete(k) { store.delete(k); },
  };
  const env = { SESSION_SECRET: "smoke-" + Math.random().toString(36).slice(2), OWNER_EMAIL: OWNER };
  if (kv) env.USERS = USERS;
  if (token) env.GITHUB_DISPATCH_TOKEN = token;
  return { env, store, log, USERS };
}

// fetch מדומה: מחזיר את הסטטוס שנקבע, ורושם מה נשלח ומתי ביחס לכתיבות ל-KV.
function mockFetch(ctx, status) {
  ctx.calls = [];
  globalThis.fetch = async (url, init) => {
    ctx.calls.push({ url, body: JSON.parse(init.body), afterPuts: ctx.log.length });
    if (status === "throw") throw new Error("network");
    return new Response(status === 204 ? null : "boom", { status });
  };
}

async function post(ctx, { edition = "night", email = OWNER, origin = APP } = {}) {
  // משתמש פעיל וסשן — כמו אחרי כניסה רגילה.
  const users = ctx.env.USERS || ctx.USERS;
  await users.put(auth.userKey(email), JSON.stringify({ email, status: "active" }));
  const cookie = `${auth.COOKIE}=${await auth.makeSession(email, ctx.env.SESSION_SECRET)}`;
  const headers = { Cookie: cookie, "Content-Type": "application/json" };
  if (origin) headers.Origin = origin;
  const request = new Request(`${APP}/api/brief`, { method: "POST", headers, body: JSON.stringify({ edition }) });
  const res = await brief.onRequestPost({ request, env: ctx.env });
  return { status: res.status, body: await res.json() };
}

const queued = (ctx) => {
  const v = ctx.store.get(QUEUE_KEY);
  return v ? JSON.parse(v) : null;
};

console.log("=== שיגור ישיר ===");
{
  const ctx = makeEnv();
  mockFetch(ctx, 204);
  const r = await post(ctx);
  const q = queued(ctx);
  const sent = ctx.calls[0] && ctx.calls[0].body;
  check(r.status === 202 && r.body.ok && !r.body.queued, "GitHub 204 → הופעל, לא בתור");
  check(q && q.edition === "night" && q.by === OWNER && q.at, "הלחיצה נרשמה ב-KV");
  check(ctx.log.some(([op, k, ttl]) => op === "put" && k === QUEUE_KEY && ttl === 14400), "לארבע שעות");
  check(sent && sent.ref === "main" && sent.inputs.edition === "night" && sent.inputs.reviews === "", "השיגור נושא את המהדורה");
  check(sent && sent.inputs.requested_at === q.at, "requested_at זהה ל-at שב-KV");
  const putIdx = ctx.log.findIndex(([op, k]) => op === "put" && k === QUEUE_KEY);
  check(putIdx >= 0 && ctx.calls[0].afterPuts > putIdx, "הרישום ל-KV קודם לשיגור");
  check(/ממתינה לסיומה/.test(r.body.message), "ההודעה אומרת שלחיצה בזמן ריצה ממתינה");
}

console.log("=== שיגור שנכשל → בתור ===");
for (const [status, re, name, hint] of [[401, /דחה את אסימון/, "401", true], [404, /דחה את אסימון/, "404", true],
                                         [500, /השיב 500/, "500", false], ["throw", /לא ענה/, "אין תשובה", false]]) {
  const ctx = makeEnv();
  mockFetch(ctx, status);
  const r = await post(ctx);
  check(r.status === 202 && r.body.queued && re.test(r.body.message) && queued(ctx), `${name} → בקשה בתור, עם הסיבה`);
  check(/צריך אסימון/.test(r.body.message) === hint, `${name} → ${hint ? "שולח למדריך האסימון" : "בלי הפניה לאסימון"}`);
}

console.log("=== בלי אסימון ===");
{
  const ctx = makeEnv({ token: null });
  mockFetch(ctx, 204);
  const r = await post(ctx);
  check(r.status === 202 && r.body.queued && queued(ctx) && ctx.calls.length === 0, "בלי אסימון → KV בלבד, בלי שיגור");
}

console.log("=== KV לא זמין ===");
{
  const ctx = makeEnv({ failPut: QUEUE_KEY });
  mockFetch(ctx, 204);
  const r = await post(ctx);
  const sent = ctx.calls[0] && ctx.calls[0].body;
  check(r.status === 202 && !r.body.queued && sent && sent.inputs.requested_at, "KV נכשל, GitHub 204 → משוגר, והלחיצה ב-inputs");
}
{
  const ctx = makeEnv({ failPut: QUEUE_KEY });
  mockFetch(ctx, 500);
  const r = await post(ctx);
  check(r.status === 502 && r.body.error, "KV נכשל וגם GitHub → שגיאה, לא 'בתור'");
}
{
  const ctx = makeEnv({ token: null, failPut: QUEUE_KEY });
  mockFetch(ctx, 204);
  const r = await post(ctx);
  check(r.status === 501 && r.body.setup, "בלי אסימון וה-KV נכשל → 501 עם הוראות");
}

console.log("=== מה שהיה קודם ===");
{
  const ctx = makeEnv();
  mockFetch(ctx, 204);
  check((await post(ctx, { email: OTHER })).status === 403, "לא בעלים → 403");
  check((await post(ctx, { origin: "https://evil.example.net" })).status === 403, "מקור זר → 403");
  check((await post(ctx, { edition: "weekly" })).status === 400, "מהדורה לא מוכרת → 400");
  check(ctx.calls.length === 0 && !queued(ctx), "אף אחת מהן לא נרשמה ולא שוגרה");
  let last;
  for (let i = 0; i < 7; i++) last = await post(ctx, { edition: "" });
  check(last.status === 429, "השביעית בשעה → 429");
  check(queued(ctx) && queued(ctx).edition === "", "\"לפי השעה\" נרשם כמחרוזת ריקה");
}

console.log(failed ? `\n${failed} בדיקות נכשלו` : "\nהכל עבר");
process.exit(failed ? 1 : 0);
