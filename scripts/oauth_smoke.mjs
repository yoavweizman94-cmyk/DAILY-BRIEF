// בדיקת עשן לזרימת ה-OAuth של שרת ה-MCP — רצה מקומית ובפריסה, בלי Cloudflare.
//
// מריצה את הפונקציות עצמן (middleware, register, authorize, token, revoke,
// mcp) מול KV בזיכרון, ועוברת על הזרימה כפי ש-claude.ai עובר עליה: גילוי
// המטא-דאטה מתשובת 401, רישום לקוח, הפניה לכניסה, דף אישור, קוד, החלפה
// באסימונים עם PKCE, קריאת MCP, רענון והחלפת אסימון, וביטול. ולצידה כל
// מה שחייב להיכשל: משתמש שאינו הבעלים, PKCE שגוי, כתובת חזרה זרה, אסימון
// מזויף ואסימון שפג, לקוח חסוי בלי סוד, וחשבון שהושבת.
//
// שימוש: node scripts/oauth_smoke.mjs
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const F = (...p) => import(pathToFileURL(path.join(ROOT, "site", "functions", ...p)).href);

const auth = await F("_lib", "auth.js");
const middleware = await F("_middleware.js");
const register = await F("api", "oauth", "register.js");
const authorize = await F("api", "oauth", "authorize.js");
const token = await F("api", "oauth", "token.js");
const revoke = await F("api", "oauth", "revoke.js");
const mcp = await F("api", "mcp", "[[path]].js");

const APP = "https://app.tlvtaseview.com";
const OWNER = "owner@example.com";
const OTHER = "subscriber@example.com";
const CLAUDE_CB = "https://claude.ai/api/mcp/auth_callback";

// KV בזיכרון, עם תפוגה — כדי שחלון החסד של אסימון רענון ייבדק באמת.
const store = new Map();
const USERS = {
  async get(k, opt) {
    const e = store.get(k);
    if (!e || (e.exp && Date.now() > e.exp)) return null;
    return opt && opt.type === "json" ? JSON.parse(e.v) : e.v;
  },
  async put(k, v, opt) {
    store.set(k, { v, exp: opt && opt.expirationTtl ? Date.now() + opt.expirationTtl * 1000 : 0 });
  },
  async delete(k) { store.delete(k); },
};
const env = { USERS, SESSION_SECRET: "smoke-secret-" + Math.random().toString(36).slice(2), OWNER_EMAIL: OWNER };
await USERS.put(auth.userKey(OWNER), JSON.stringify({ email: OWNER, name: "בעלים", status: "active" }));
await USERS.put(auth.userKey(OTHER), JSON.stringify({ email: OTHER, name: "מנוי", status: "active" }));
const cookieOf = async (email) => `${auth.COOKIE}=${await auth.makeSession(email, env.SESSION_SECRET)}`;

let failed = 0;
function check(cond, msg) {
  if (cond) console.log("  ✓ " + msg);
  else { console.log("  ✗ " + msg); failed++; }
}

async function run(mod, method, url, { body, headers = {}, form, params } = {}) {
  const init = { method, headers: { ...headers }, redirect: "manual" };
  if (form) {
    init.headers["Content-Type"] = "application/x-www-form-urlencoded";
    init.body = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const request = new Request(url, init);
  const ctx = { request, env, params: params || {}, next: async () => new Response("next", { status: 299 }) };
  const fn = mod[`onRequest${method[0]}${method.slice(1).toLowerCase()}`] || mod.onRequest;
  return fn(ctx);
}

const b64url = (buf) => Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
async function pkce() {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  return { verifier, challenge };
}

const init = { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "smoke", version: "0" } } };
const mcpCall = (bearer, msg = init) => run(mcp, "POST", `${APP}/api/mcp`,
  { body: msg, headers: bearer ? { Authorization: `Bearer ${bearer}` } : {} });

console.log("=== גילוי ===");
{
  const r = await mcpCall("");
  const h = r.headers.get("WWW-Authenticate") || "";
  check(r.status === 401, "MCP בלי אסימון → 401");
  check(h.includes(`resource_metadata="${APP}/.well-known/oauth-protected-resource"`), "401 נושא resource_metadata");
  const pr = await run(middleware, "GET", `${APP}/.well-known/oauth-protected-resource`);
  const prj = await pr.json();
  check(pr.status === 200 && prj.resource === `${APP}/api/mcp` && prj.authorization_servers[0] === APP, "מטא-דאטה של המשאב");
  const pr2 = await run(middleware, "GET", `${APP}/.well-known/oauth-protected-resource/api/mcp`);
  check(pr2.status === 200, "מטא-דאטה של המשאב — גם בנתיב עם סיומת");
  const as = await (await run(middleware, "GET", `${APP}/.well-known/oauth-authorization-server`)).json();
  check(as.issuer === APP && as.token_endpoint === `${APP}/api/oauth/token`
    && as.code_challenge_methods_supported.includes("S256") && as.registration_endpoint, "מטא-דאטה של שרת ההרשאה");
  const other = await run(middleware, "GET", `${APP}/.well-known/security.txt`);
  check(other.status !== 200 || (await other.text()) === "next", ".well-known אחר אינו נבלע");
}

console.log("=== רישום ===");
const reg = await run(register, "POST", `${APP}/api/oauth/register`,
  { body: { client_name: "Claude", redirect_uris: [CLAUDE_CB], token_endpoint_auth_method: "none" } });
const client = await reg.json();
check(reg.status === 201 && client.client_id && !client.client_secret, "רישום לקוח ציבורי → 201 בלי סוד");
check((await run(register, "POST", `${APP}/api/oauth/register`,
  { body: { redirect_uris: ["http://evil.example/cb"], token_endpoint_auth_method: "none" } })).status === 400,
  "כתובת חזרה ב-http לאתר זר → 400");

async function authorizeUrl(c, ch, extra = {}) {
  const q = new URLSearchParams({ response_type: "code", client_id: c.client_id, redirect_uri: CLAUDE_CB,
    code_challenge: ch, code_challenge_method: "S256", state: "st-1", scope: "mcp", resource: `${APP}/api/mcp`, ...extra });
  return `${APP}/api/oauth/authorize?${q}`;
}

// מעבר מלא על דף האישור ← קוד
async function getCode(c, ch, cookie, action = "approve") {
  const page = await run(authorize, "GET", await authorizeUrl(c, ch), { headers: { Cookie: cookie } });
  const html = await page.text();
  const form = {};
  for (const m of html.matchAll(/<input type="hidden" name="([a-z_]+)" value="([^"]*)">/g)) {
    form[m[1]] = m[2].replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
  }
  form.action = action;
  const res = await run(authorize, "POST", `${APP}/api/oauth/authorize`, { form, headers: { Cookie: cookie } });
  const loc = res.headers.get("Location") || "";
  return { page, html, res, loc: loc ? new URL(loc) : null };
}

console.log("=== הרשאה ===");
const p1 = await pkce();
{
  const r = await run(authorize, "GET", await authorizeUrl(client, p1.challenge));
  const loc = r.headers.get("Location") || "";
  check(r.status === 302 && loc.startsWith(`${APP}/login?next=`) && decodeURIComponent(loc).includes("/api/oauth/authorize?"),
    "בלי סשן → הפניה לדף הכניסה עם next");
  const bad = await run(authorize, "GET", (await authorizeUrl(client, p1.challenge)).replace(encodeURIComponent(CLAUDE_CB), encodeURIComponent("https://evil.example/cb")),
    { headers: { Cookie: await cookieOf(OWNER) } });
  check(bad.status === 400 && !bad.headers.get("Location"), "כתובת חזרה שאינה רשומה → שגיאה בדף, בלי הפניה");
  const noPkce = await run(authorize, "GET", (await authorizeUrl(client, p1.challenge)).replace("code_challenge_method=S256", "code_challenge_method=plain"),
    { headers: { Cookie: await cookieOf(OWNER) } });
  check(noPkce.status === 302 && (noPkce.headers.get("Location") || "").includes("error=invalid_request"), "PKCE plain → invalid_request ללקוח");
  const other = await run(authorize, "GET", await authorizeUrl(client, p1.challenge), { headers: { Cookie: await cookieOf(OTHER) } });
  check(other.status === 403, "מנוי שאינו הבעלים → 403");
}
const ownerCookie = await cookieOf(OWNER);
{
  const d = await getCode(client, p1.challenge, ownerCookie, "deny");
  check(d.loc && d.loc.searchParams.get("error") === "access_denied" && d.loc.searchParams.get("state") === "st-1", "ביטול → access_denied עם state");
  const page = await run(authorize, "GET", await authorizeUrl(client, p1.challenge), { headers: { Cookie: ownerCookie } });
  check(page.headers.get("X-Frame-Options") === "DENY", "דף האישור אסור במסגרת");
  const forged = await run(authorize, "POST", `${APP}/api/oauth/authorize`, { headers: { Cookie: ownerCookie }, form: {
    response_type: "code", client_id: client.client_id, redirect_uri: CLAUDE_CB, code_challenge: p1.challenge,
    code_challenge_method: "S256", state: "st-1", action: "approve", csrf: "1.abc" } });
  check(forged.status === 400 && !forged.headers.get("Location"), "אישור בלי אסימון טופס תקף → נדחה");
}
const c1 = await getCode(client, p1.challenge, ownerCookie);
check(c1.loc && c1.loc.origin + c1.loc.pathname === CLAUDE_CB && c1.loc.searchParams.get("code")
  && c1.loc.searchParams.get("state") === "st-1" && c1.loc.searchParams.get("iss") === APP, "אישור → קוד, state ו-iss בכתובת החזרה");

console.log("=== אסימונים ===");
{
  const w = await getCode(client, p1.challenge, ownerCookie);
  const wrong = await run(token, "POST", `${APP}/api/oauth/token`, { form: { grant_type: "authorization_code",
    code: w.loc.searchParams.get("code"), redirect_uri: CLAUDE_CB, client_id: client.client_id, code_verifier: (await pkce()).verifier } });
  check(wrong.status === 400 && (await wrong.json()).error === "invalid_grant", "PKCE שגוי → invalid_grant");
  const again = await run(token, "POST", `${APP}/api/oauth/token`, { form: { grant_type: "authorization_code",
    code: w.loc.searchParams.get("code"), redirect_uri: CLAUDE_CB, client_id: client.client_id, code_verifier: p1.verifier } });
  check(again.status === 400, "קוד שכבר נוסה — חד-פעמי, גם אחרי כשל");
}
const t1r = await run(token, "POST", `${APP}/api/oauth/token`, { form: { grant_type: "authorization_code",
  code: c1.loc.searchParams.get("code"), redirect_uri: CLAUDE_CB, client_id: client.client_id, code_verifier: p1.verifier } });
const t1 = await t1r.json();
check(t1r.status === 200 && t1.access_token && t1.refresh_token && t1.token_type === "Bearer" && t1.expires_in === 86400,
  "קוד + PKCE → אסימון גישה ואסימון רענון");
check(t1r.headers.get("Cache-Control") === "no-store", "תשובת האסימון no-store");
{
  const reuse = await run(token, "POST", `${APP}/api/oauth/token`, { form: { grant_type: "authorization_code",
    code: c1.loc.searchParams.get("code"), redirect_uri: CLAUDE_CB, client_id: client.client_id, code_verifier: p1.verifier } });
  check(reuse.status === 400, "שימוש חוזר בקוד → נדחה");
}

console.log("=== MCP עם האסימון ===");
{
  const r = await mcpCall(t1.access_token);
  const j = await r.json();
  check(r.status === 200 && j.result && j.result.serverInfo && j.result.serverInfo.name === "tlv-tase-view", "initialize עם אסימון OAuth → 200");
  const tl = await (await mcpCall(t1.access_token, { jsonrpc: "2.0", id: 2, method: "tools/list" })).json();
  check(tl.result && tl.result.tools && tl.result.tools.length > 5, `tools/list → ${tl.result ? tl.result.tools.length : 0} כלים`);
  const forged = t1.access_token.slice(0, -3) + (t1.access_token.endsWith("AAA") ? "BBB" : "AAA");
  const fr = await mcpCall(forged);
  check(fr.status === 401 && (fr.headers.get("WWW-Authenticate") || "").includes('error="invalid_token"'), "אסימון מזויף → 401 invalid_token");
  const real = Date.now;
  Date.now = () => real() + 2 * 86400000;
  const late = await mcpCall(t1.access_token);
  Date.now = real;
  check(late.status === 401, "אסימון גישה אחרי יממה → 401");
}

console.log("=== רענון ===");
const t2r = await run(token, "POST", `${APP}/api/oauth/token`,
  { form: { grant_type: "refresh_token", refresh_token: t1.refresh_token, client_id: client.client_id } });
const t2 = await t2r.json();
check(t2r.status === 200 && t2.refresh_token && t2.refresh_token !== t1.refresh_token, "רענון → זוג חדש, אסימון רענון מוחלף");
check((await mcpCall(t2.access_token)).status === 200, "אסימון הגישה החדש עובד");
{
  const grace = await run(token, "POST", `${APP}/api/oauth/token`,
    { form: { grant_type: "refresh_token", refresh_token: t1.refresh_token, client_id: client.client_id } });
  check(grace.status === 200, "הישן תקף בחלון החסד (רענון כפול אינו מנתק)");
  const real = Date.now;
  Date.now = () => real() + 11 * 60 * 1000;
  const after = await run(token, "POST", `${APP}/api/oauth/token`,
    { form: { grant_type: "refresh_token", refresh_token: t1.refresh_token, client_id: client.client_id } });
  const still = await run(token, "POST", `${APP}/api/oauth/token`,
    { form: { grant_type: "refresh_token", refresh_token: t2.refresh_token, client_id: client.client_id } });
  Date.now = real;
  check(after.status === 400, "הישן פג אחרי חלון החסד");
  check(still.status === 200, "החדש לא פג — אין תפוגה לאסימון רענון שלא הוחלף");
  const t3 = await still.json();
  const otherClient = await (await run(register, "POST", `${APP}/api/oauth/register`,
    { body: { redirect_uris: [CLAUDE_CB], token_endpoint_auth_method: "none" } })).json();
  const cross = await run(token, "POST", `${APP}/api/oauth/token`,
    { form: { grant_type: "refresh_token", refresh_token: t3.refresh_token, client_id: otherClient.client_id } });
  check(cross.status === 400, "אסימון רענון של לקוח אחר → נדחה");

  console.log("=== ביטול והשבתה ===");
  await run(revoke, "POST", `${APP}/api/oauth/revoke`, { form: { token: t3.refresh_token, client_id: client.client_id } });
  const revoked = await run(token, "POST", `${APP}/api/oauth/token`,
    { form: { grant_type: "refresh_token", refresh_token: t3.refresh_token, client_id: client.client_id } });
  check(revoked.status === 400, "אחרי ביטול → רענון נדחה");
}
{
  const p = await pkce();
  const c = await getCode(client, p.challenge, ownerCookie);
  const t = await (await run(token, "POST", `${APP}/api/oauth/token`, { form: { grant_type: "authorization_code",
    code: c.loc.searchParams.get("code"), redirect_uri: CLAUDE_CB, client_id: client.client_id, code_verifier: p.verifier } })).json();
  await USERS.put(auth.userKey(OWNER), JSON.stringify({ email: OWNER, name: "בעלים", status: "disabled" }));
  const off = await run(token, "POST", `${APP}/api/oauth/token`,
    { form: { grant_type: "refresh_token", refresh_token: t.refresh_token, client_id: client.client_id } });
  check(off.status === 400, "חשבון שהושבת → רענון נדחה");
  await USERS.put(auth.userKey(OWNER), JSON.stringify({ email: OWNER, name: "בעלים", status: "active" }));
}

console.log("=== לקוח חסוי ===");
{
  const reg2 = await (await run(register, "POST", `${APP}/api/oauth/register`,
    { body: { client_name: "חסוי", redirect_uris: [CLAUDE_CB] } })).json();
  check(reg2.client_secret && reg2.token_endpoint_auth_method === "client_secret_basic", "בלי שיטה מוצהרת → client_secret_basic עם סוד (RFC 7591)");
  const p = await pkce();
  const c = await getCode(reg2, p.challenge, ownerCookie);
  const code = c.loc.searchParams.get("code");
  const noSecret = await run(token, "POST", `${APP}/api/oauth/token`, { form: { grant_type: "authorization_code",
    code, redirect_uri: CLAUDE_CB, client_id: reg2.client_id, code_verifier: p.verifier } });
  check(noSecret.status === 401, "לקוח חסוי בלי סוד → invalid_client");
  const c2 = await getCode(reg2, p.challenge, ownerCookie);
  const basic = "Basic " + Buffer.from(`${reg2.client_id}:${reg2.client_secret}`).toString("base64");
  const ok = await run(token, "POST", `${APP}/api/oauth/token`, { headers: { Authorization: basic }, form: {
    grant_type: "authorization_code", code: c2.loc.searchParams.get("code"), redirect_uri: CLAUDE_CB, code_verifier: p.verifier } });
  check(ok.status === 200, "לקוח חסוי עם Basic → אסימונים");
}

console.log("=== האסימון הקבוע עדיין עובד ===");
{
  env.MCP_TOKEN = "static-" + Math.random().toString(36).slice(2);
  check((await mcpCall(env.MCP_TOKEN)).status === 200, "MCP_TOKEN בכותרת → 200");
  const pathOk = await run(mcp, "POST", `${APP}/api/mcp/${env.MCP_TOKEN}`, { body: init, params: { path: [env.MCP_TOKEN] } });
  check(pathOk.status === 200, "MCP_TOKEN בנתיב → 200");
  delete env.MCP_TOKEN;
  const none = { ...env };
  delete none.SESSION_SECRET;
  const r = await mcp.onRequest({ request: new Request(`${APP}/api/mcp`, { method: "POST", body: JSON.stringify(init), headers: { "Content-Type": "application/json" } }), env: none, params: {} });
  check(r.status === 503, "בלי MCP_TOKEN ובלי SESSION_SECRET → 503 (נכשל סגור)");
}

console.log(failed ? `\n${failed} בדיקות נכשלו` : "\nכל בדיקות ה-OAuth עברו");
process.exit(failed ? 1 : 0);
