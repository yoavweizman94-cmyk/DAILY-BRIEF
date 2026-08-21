// Couple budget tracker — single Cloudflare Worker.
// Serves the HTML app at /<APP_PATH>, and a JSON API under /api/*.
// Auth: every /api/* request (except login) must carry header X-Pin === env.APP_PIN.

import HTML from "./index.html";

const JSON_HEADERS = { "Content-Type": "application/json; charset=utf-8" };

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });

const err = (message, status = 400) => json({ error: message }, status);

// ---------- date helpers (all in Israel time) ----------

function todayIsrael() {
  // en-CA gives YYYY-MM-DD
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem" }).format(new Date());
}

function nowIsraelISO() {
  const d = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Jerusalem",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const p = Object.fromEntries(d.map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}

const daysInMonth = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();

// The budget month starting on `startDay` that contains `todayStr` (YYYY-MM-DD).
// Returns its key ('YYYY-MM' of the month it starts in) and days left until the
// next budget month starts (minimum 1, so daily-rate never divides by zero).
function budgetMonthInfo(startDay, todayStr) {
  const [y, m, d] = todayStr.split("-").map(Number);
  let sy = y, sm = m;
  const effStart = Math.min(startDay, daysInMonth(y, m));
  if (d < effStart) { sm -= 1; if (sm === 0) { sm = 12; sy -= 1; } }
  const monthKey = `${sy}-${String(sm).padStart(2, "0")}`;
  let ny = sy, nm = sm + 1;
  if (nm === 13) { nm = 1; ny += 1; }
  const nextStart = Date.UTC(ny, nm - 1, Math.min(startDay, daysInMonth(ny, nm)));
  const today = Date.UTC(y, m - 1, d);
  const daysLeft = Math.max(1, Math.round((nextStart - today) / 86400000));
  return { monthKey, daysLeft };
}

// ---------- data access ----------

async function getSettings(db) {
  const row = await db.prepare("SELECT * FROM settings WHERE id = 1").first();
  return {
    monthly_income: row.monthly_income,
    savings_goal: row.savings_goal,
    month_start_day: row.month_start_day,
    categories: JSON.parse(row.categories || "[]"),
    users: JSON.parse(row.users || "[]"),
    setup_done: !!row.setup_done,
  };
}

async function buildState(db) {
  const settings = await getSettings(db);
  const { monthKey, daysLeft } = budgetMonthInfo(settings.month_start_day, todayIsrael());

  const fixed = (await db.prepare(
    "SELECT id, name, amount, category, active FROM fixed_expenses ORDER BY id"
  ).all()).results;

  const txs = (await db.prepare(
    "SELECT id, ts, amount, description, category, created_by, source FROM transactions WHERE budget_month = ? ORDER BY ts DESC, id DESC"
  ).bind(monthKey).all()).results;

  const archive = (await db.prepare(
    "SELECT month, budget, total_spent, balance FROM months_archive ORDER BY month DESC LIMIT 24"
  ).all()).results;

  const fixedTotal = fixed.filter(f => f.active).reduce((s, f) => s + f.amount, 0);
  const budget = settings.monthly_income - fixedTotal - settings.savings_goal;
  const spent = txs.reduce((s, t) => s + t.amount, 0);
  const remaining = budget - spent;

  const byCategory = {};
  for (const t of txs) byCategory[t.category] = (byCategory[t.category] || 0) + t.amount;

  return {
    settings,
    fixed,
    transactions: txs,
    archive,
    summary: {
      monthKey, daysLeft, fixedTotal, budget, spent, remaining,
      dailyAllowed: remaining > 0 ? remaining / daysLeft : 0,
      usedPct: budget > 0 ? (spent / budget) * 100 : 100,
    },
  };
}

// ---------- request handling ----------

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === `/${env.APP_PATH}` || path === `/${env.APP_PATH}/`) {
      return new Response(HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }

    if (path.startsWith("/api/")) {
      try {
        return await handleApi(request, env, path);
      } catch (e) {
        return err("server error: " + e.message, 500);
      }
    }

    return new Response("Not found", { status: 404 });
  },
};

async function handleApi(request, env, path) {
  const db = env.DB;
  const method = request.method;
  const body = method === "POST" || method === "PUT"
    ? await request.json().catch(() => ({}))
    : {};

  if (path === "/api/login" && method === "POST") {
    if (String(body.pin || "") === String(env.APP_PIN)) return json({ ok: true });
    return err("PIN שגוי", 401);
  }

  // Everything below requires the PIN header.
  if (request.headers.get("X-Pin") !== String(env.APP_PIN)) {
    return err("unauthorized", 401);
  }

  if (path === "/api/state" && method === "GET") {
    return json(await buildState(db));
  }

  if (path === "/api/setup" && method === "POST") {
    const income = Number(body.monthly_income) || 0;
    const savings = Number(body.savings_goal) || 0;
    const startDay = Math.min(28, Math.max(1, Number(body.month_start_day) || 1));
    const users = Array.isArray(body.users) ? body.users.filter(Boolean).slice(0, 4) : [];
    await db.prepare(
      "UPDATE settings SET monthly_income=?, savings_goal=?, month_start_day=?, users=?, setup_done=1 WHERE id=1"
    ).bind(income, savings, startDay, JSON.stringify(users)).run();
    for (const f of (Array.isArray(body.fixed) ? body.fixed : [])) {
      if (!f.name || !Number(f.amount)) continue;
      await db.prepare(
        "INSERT INTO fixed_expenses (name, amount, category) VALUES (?, ?, ?)"
      ).bind(String(f.name), Number(f.amount), String(f.category || "בית")).run();
    }
    return json(await buildState(db));
  }

  if (path === "/api/settings" && method === "PUT") {
    const cur = await getSettings(db);
    const next = {
      monthly_income: body.monthly_income !== undefined ? Number(body.monthly_income) : cur.monthly_income,
      savings_goal: body.savings_goal !== undefined ? Number(body.savings_goal) : cur.savings_goal,
      month_start_day: body.month_start_day !== undefined
        ? Math.min(28, Math.max(1, Number(body.month_start_day))) : cur.month_start_day,
      categories: Array.isArray(body.categories) ? body.categories.filter(Boolean) : cur.categories,
      users: Array.isArray(body.users) ? body.users.filter(Boolean).slice(0, 4) : cur.users,
    };
    await db.prepare(
      "UPDATE settings SET monthly_income=?, savings_goal=?, month_start_day=?, categories=?, users=? WHERE id=1"
    ).bind(next.monthly_income, next.savings_goal, next.month_start_day,
           JSON.stringify(next.categories), JSON.stringify(next.users)).run();
    return json(await buildState(db));
  }

  if (path === "/api/fixed" && method === "POST") {
    if (!body.name || !Number(body.amount)) return err("שם וסכום נדרשים");
    await db.prepare(
      "INSERT INTO fixed_expenses (name, amount, category) VALUES (?, ?, ?)"
    ).bind(String(body.name), Number(body.amount), String(body.category || "בית")).run();
    return json(await buildState(db));
  }

  let m = path.match(/^\/api\/fixed\/(\d+)$/);
  if (m) {
    const id = Number(m[1]);
    if (method === "PUT") {
      const row = await db.prepare("SELECT * FROM fixed_expenses WHERE id=?").bind(id).first();
      if (!row) return err("לא נמצא", 404);
      await db.prepare(
        "UPDATE fixed_expenses SET name=?, amount=?, category=?, active=? WHERE id=?"
      ).bind(
        body.name !== undefined ? String(body.name) : row.name,
        body.amount !== undefined ? Number(body.amount) : row.amount,
        body.category !== undefined ? String(body.category) : row.category,
        body.active !== undefined ? (body.active ? 1 : 0) : row.active,
        id
      ).run();
      return json(await buildState(db));
    }
    if (method === "DELETE") {
      await db.prepare("DELETE FROM fixed_expenses WHERE id=?").bind(id).run();
      return json(await buildState(db));
    }
  }

  if (path === "/api/tx" && method === "POST") {
    const amount = Number(body.amount);
    if (!amount || amount <= 0) return err("סכום לא תקין");
    const settings = await getSettings(db);
    const { monthKey } = budgetMonthInfo(settings.month_start_day, todayIsrael());
    await db.prepare(
      "INSERT INTO transactions (ts, amount, description, category, created_by, source, budget_month) VALUES (?, ?, ?, ?, ?, 'web', ?)"
    ).bind(
      nowIsraelISO(), amount,
      String(body.description || ""), String(body.category || "אחר"),
      String(body.created_by || ""), monthKey
    ).run();
    return json(await buildState(db));
  }

  m = path.match(/^\/api\/tx\/(\d+)$/);
  if (m) {
    const id = Number(m[1]);
    if (method === "PUT") {
      const row = await db.prepare("SELECT * FROM transactions WHERE id=?").bind(id).first();
      if (!row) return err("לא נמצא", 404);
      const amount = body.amount !== undefined ? Number(body.amount) : row.amount;
      if (!amount || amount <= 0) return err("סכום לא תקין");
      await db.prepare(
        "UPDATE transactions SET amount=?, description=?, category=? WHERE id=?"
      ).bind(
        amount,
        body.description !== undefined ? String(body.description) : row.description,
        body.category !== undefined ? String(body.category) : row.category,
        id
      ).run();
      return json(await buildState(db));
    }
    if (method === "DELETE") {
      await db.prepare("DELETE FROM transactions WHERE id=?").bind(id).run();
      return json(await buildState(db));
    }
  }

  return err("not found", 404);
}
