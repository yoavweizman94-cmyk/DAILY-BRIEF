// בדיקת עשן לשרת ה-MCP של האתר — רצה מקומית ובפריסה, בלי Cloudflare.
//
// מריצה את site/functions/api/mcp/[[path]].js עם סביבה מזויפת: ASSETS שמגיש
// את site/dist מהדיסק, ו-MCP_TOKEN ידוע. בודקת את שער האימות, את לחיצת
// היד, ושכל כלי מחזיר טקסט בלי isError — גם על dist בלי תוכן, כי כלי
// שנופל על נתון חסר הוא כלי שנופל בפריסה הראשונה.
//
// שימוש: node scripts/mcp_smoke.mjs            (אחרי python site/build.py)
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIST = path.join(ROOT, "site", "dist");
const TOKEN = "smoke-token-" + Math.random().toString(36).slice(2);

const mod = await import(pathToFileURL(path.join(ROOT, "site", "functions", "api", "mcp", "[[path]].js")).href);

const env = {
  MCP_TOKEN: TOKEN,
  ASSETS: {
    async fetch(req) {
      const p = decodeURIComponent(new URL(req.url).pathname);
      const file = path.join(DIST, p);
      if (!file.startsWith(DIST)) return new Response("nope", { status: 403 });
      try {
        await stat(file);
        return new Response(await readFile(file), { status: 200 });
      } catch {
        return new Response("not found", { status: 404 });
      }
    },
  },
};

let failed = 0;
function check(cond, msg) {
  if (cond) console.log("  ✓ " + msg);
  else { console.log("  ✗ " + msg); failed++; }
}

async function call(body, { token = TOKEN, pathSeg = [], headerAuth = true, method = "POST" } = {}) {
  const headers = { "Content-Type": "application/json", Accept: "application/json, text/event-stream" };
  if (headerAuth && token) headers.Authorization = `Bearer ${token}`;
  const url = "https://app.tlvtaseview.com/api/mcp" + (pathSeg.length ? "/" + pathSeg.join("/") : "");
  const request = new Request(url, { method, headers, body: method === "POST" ? JSON.stringify(body) : undefined });
  const res = await mod.onRequest({ request, env, params: { path: pathSeg.length ? pathSeg : undefined } });
  const text = await res.text();
  return { status: res.status, json: text ? JSON.parse(text) : null };
}

const init = { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "smoke", version: "0" } } };

console.log("=== אימות ===");
check((await call(init, { token: "" })).status === 401, "בלי אסימון → 401");
check((await call(init, { token: "wrong" })).status === 401, "אסימון שגוי → 401");
check((await call(init, { headerAuth: false, pathSeg: ["wrong"] })).status === 401, "אסימון שגוי בנתיב → 401");
check((await call(init, { headerAuth: false, pathSeg: [TOKEN] })).status === 200, "אסימון בנתיב → 200");
check((await call(init, { method: "GET" })).status === 405, "GET → 405");
{
  const r = await mod.onRequest({ request: new Request("https://x/api/mcp", { method: "POST", body: "{}" }), env: { ASSETS: env.ASSETS }, params: {} });
  check(r.status === 503, "בלי MCP_TOKEN בסביבה → 503 (נכשל סגור)");
}

console.log("=== לחיצת יד ===");
{
  const r = await call(init);
  check(r.status === 200 && r.json.result && r.json.result.protocolVersion === "2025-06-18", "initialize מחזיר גרסת פרוטוקול");
  check(r.json.result.capabilities && r.json.result.capabilities.tools, "initialize מצהיר על כלים");
  const n = await call({ jsonrpc: "2.0", method: "notifications/initialized" });
  check(n.status === 202 && n.json === null, "notification → 202 בלי גוף");
  const p = await call({ jsonrpc: "2.0", id: 2, method: "ping" });
  check(p.status === 200 && p.json.result && Object.keys(p.json.result).length === 0, "ping → {}");
  const bad = await call({ jsonrpc: "2.0", id: 3, method: "nope" });
  check(bad.json.error && bad.json.error.code === -32601, "שיטה לא מוכרת → -32601");
}

console.log("=== כלים ===");
const list = await call({ jsonrpc: "2.0", id: 4, method: "tools/list" });
const tools = (list.json.result && list.json.result.tools) || [];
check(tools.length >= 15, `tools/list מחזיר ${tools.length} כלים`);
for (const t of tools) {
  check(/^[a-z_]+$/.test(t.name) && t.description && t.inputSchema && t.inputSchema.type === "object",
    `סכמה תקינה: ${t.name}`);
}

// ארגומנטים לכל כלי, כדי שגם נתיבי הסינון ירוצו — לא רק ברירות המחדל.
const ARGS = {
  latest_brief: [{}, { edition: "morning" }],
  get_brief: [{ date: "2026-01-01" }],
  list_briefs: [{ limit: 5 }],
  search_briefs: [{ query: "ריבית" }],
  markets: [{}],
  maya_reports: [{}, { company: "לאומי", days: 5, full: true }],
  coverage_companies: [{}, { query: "טבע" }, { sector: "banks" }],
  conference_calls: [{}, { include_past: true }],
  housing_market: [{}, { city: "חיפה" }],
  off_exchange_trades: [{}, { days: 10, security: "x" }],
  headlines: [{}, { important_only: true, query: "א" }],
  topic_summary: [{}, { topic: "energy" }],
  cbs_releases: [{}, { query: "מדד" }],
  commodities: [{}, { query: "פלדה" }],
  search_filings: [{ company: "טבע" }, { company: "טבע", year: 2020 }],
};
let id = 10;
for (const t of tools) {
  for (const args of ARGS[t.name] || [{}]) {
    const r = await call({ jsonrpc: "2.0", id: id++, method: "tools/call", params: { name: t.name, arguments: args } });
    const res = r.json && r.json.result;
    const ok = r.status === 200 && res && Array.isArray(res.content) && res.content[0] && typeof res.content[0].text === "string" && !res.isError;
    check(ok, `${t.name} ${JSON.stringify(args)} → ${ok ? res.content[0].text.slice(0, 60).replace(/\n/g, " ") : JSON.stringify(r.json).slice(0, 200)}`);
  }
}
{
  const r = await call({ jsonrpc: "2.0", id: id++, method: "tools/call", params: { name: "get_brief", arguments: { date: "bad" } } });
  check(r.json.result && r.json.result.isError, "ארגומנט לא תקין → isError ולא קריסה");
  const r2 = await call({ jsonrpc: "2.0", id: id++, method: "tools/call", params: { name: "no_such_tool" } });
  check(r2.json.error && r2.json.error.code === -32602, "כלי לא מוכר → -32602");
}

console.log(failed ? `\n${failed} בדיקות נכשלו` : "\nהכל עבר");
process.exit(failed ? 1 : 0);
