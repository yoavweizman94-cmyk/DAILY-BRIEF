// שרת MCP של האתר — Streamable HTTP, ללא מצב, על Cloudflare Pages Functions.
//
// **מה זה נותן.** כל סשן של Claude (claude.ai, Claude Code, Cowork) שמחובר
// לכתובת הזו מקבל כלים שקוראים את מה שהאתר מגיש: הברייפים, רצועת
// השווקים, דיווחי מאיה המסוכמים, שוק הדיור, עסקאות מחוץ לבורסה, רשימת
// הכיסוי, הדוחות הכספיים ועוד. הכלים אינם מחשבים דבר — הם קוראים את
// site/dist/mcp/*.json שנכתבו בבנייה (site/mcp_data.py) מאותם אובייקטים
// שהעמודים נבנו מהם.
//
// **אימות: אסימון אחד, בשתי צורות.** `Authorization: Bearer <MCP_TOKEN>`,
// או האסימון כמקטע בנתיב — `/api/mcp/<MCP_TOKEN>`. הצורה השנייה קיימת כי
// מחברים מותאמים ב-claude.ai מקבלים כתובת בלבד ואינם יודעים לשלוח כותרת.
// ההשוואה בזמן קבוע, כמו בשאר שכבת האימות. **נכשל סגור**: בלי MCP_TOKEN
// בסביבת ה-Pages התשובה היא 503, לא מעבר חופשי.
//
// **ללא מצב בכוונה.** אין Mcp-Session-Id ואין זרם SSE: כל קריאה היא
// POST אחד עם תשובת JSON אחת. זה כל מה שהכלים האלה צריכים, וזה מה
// שמאפשר לפונקציה לרוץ בלי KV ובלי Durable Objects.
//
// פרוטוקול: JSON-RPC 2.0 לפי מפרט MCP (2025-06-18, ותואם לאחור ל-2025-03-26
// ו-2024-11-05). GET מחזיר 405 — השרת אינו פותח זרם משלו.
import { timingSafeEqual } from "../../_lib/auth.js";

const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];
const SERVER = { name: "tlv-tase-view", version: "1.0.0" };
const MAX_CHARS = 60000;                 // תקרת טקסט לתשובת כלי אחת
const MAYA_FILES = "https://mayafiles.tase.co.il/";
const SITE = "https://app.tlvtaseview.com";

const INSTRUCTIONS =
  "TLV TASE View — מחקר יומי על הבורסה בתל אביב, דרך רשימת כיסוי של כ-400 חברות. " +
  "הכלים מגישים את תוכן האתר כפי שנבנה לאחרונה: ברייפים (שלוש-ארבע מהדורות ביום), " +
  "רצועת שווקים ומאקרו, דיווחי מאיה מסוכמים, שיחות ועידה, שוק הדיור (Govmap/רשות המסים, " +
  "בפיגור של כשישה שבועות), עסקאות מחוץ לבורסה, סיכומי סקטורים, כותרות, למ\"ס, סחורות " +
  "ואינדקס דוחות כספיים. כל מספר נושא מקור ותאריך — ציין אותם. אין כאן ייעוץ השקעות.";

// --------------------------------------------------------------------------
// עזרים

function clip(text) {
  const s = String(text == null ? "" : text);
  return s.length > MAX_CHARS ? s.slice(0, MAX_CHARS) + "\n\n[נחתך — צמצם את הבקשה]" : s;
}

// נרמול לחיפוש בעברית: גרשיים, גרש, מירכאות ורווחים כפולים אינם חלק מהמילה.
function norm(s) {
  return String(s == null ? "" : s).toLowerCase()
    .replace(/["'״׳`]/g, "").replace(/\s+/g, " ").trim();
}

function has(hay, needle) {
  return needle ? norm(hay).includes(norm(needle)) : true;
}

function num(v, digits = 2) {
  if (v == null || v === "") return "—";
  const x = Number(v);
  if (!Number.isFinite(x)) return String(v);
  return x.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function signed(v, unit = "%") {
  if (v == null || v === "") return "—";
  const x = Number(v);
  if (!Number.isFinite(x)) return String(v);
  return (x > 0 ? "+" : "") + x + unit;
}

function money(v) {
  const x = Number(v);
  if (!Number.isFinite(x)) return "—";
  if (Math.abs(x) >= 1e6) return (x / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 }) + " מ׳ ₪";
  if (Math.abs(x) >= 1e3) return (x / 1e3).toLocaleString("en-US", { maximumFractionDigits: 0 }) + " א׳ ₪";
  return num(x, 0) + " ₪";
}

function int(v, dflt, lo, hi) {
  const n = Number.parseInt(v, 10);
  if (!Number.isFinite(n)) return dflt;
  return Math.min(hi, Math.max(lo, n));
}

function today() {
  // שעון ישראל, כי "היום" של השיחות והמסחר הוא שם ולא ב-UTC
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Jerusalem" });
}

async function asset(ctx, path, as = "json") {
  const url = new URL(path, ctx.request.url);
  const res = await ctx.env.ASSETS.fetch(new Request(url.toString(), { headers: { Accept: "*/*" } }));
  if (!res || !res.ok) return null;
  try {
    return as === "json" ? await res.json() : await res.text();
  } catch {
    return null;
  }
}

const EDITIONS = { morning: "בוקר", midday: "צהריים", close: "נעילה", night: "לילה" };

function normEdition(e) {
  const s = norm(e);
  if (!s) return "";
  for (const [k, he] of Object.entries(EDITIONS)) {
    if (s === k || s === he) return k;
  }
  return s;
}

async function briefIndex(ctx) {
  const idx = await asset(ctx, "/mcp/index.json");
  return idx && Array.isArray(idx.briefs) ? idx : { briefs: [] };
}

async function briefText(ctx, slug) {
  if (!/^\d{4}-\d{2}-\d{2}(-(morning|midday|close|night))?$/.test(slug)) return null;
  return asset(ctx, `/mcp/briefs/${slug}.md`, "text");
}

function briefHeader(b) {
  return `# ${b.title}\n_${b.slug} · מהדורת ${EDITIONS[b.edition] || b.edition} · ${SITE}/briefs/${b.slug}.html_\n\n`;
}

// --------------------------------------------------------------------------
// הכלים

const TOOLS = [
  {
    name: "latest_brief",
    description: "הברייף העדכני ביותר, בטקסט המלא (markdown). אפשר לבקש מהדורה מסוימת: morning / midday / close / night.",
    inputSchema: {
      type: "object",
      properties: { edition: { type: "string", description: "morning | midday | close | night (ריק = האחרון מכל סוג)" } },
    },
    async run(a, ctx) {
      const idx = await briefIndex(ctx);
      const ed = normEdition(a.edition);
      const b = idx.briefs.find((x) => !ed || x.edition === ed);
      if (!b) return ed ? `אין ברייף במהדורת ${ed} באתר.` : "אין עדיין ברייפים באתר.";
      const text = await briefText(ctx, b.slug);
      if (!text) return `הברייף ${b.slug} רשום באינדקס אך הקובץ חסר — תקלת בנייה.`;
      return briefHeader(b) + text;
    },
  },
  {
    name: "get_brief",
    description: "ברייף לפי תאריך (YYYY-MM-DD) ומהדורה. בלי מהדורה — כל המהדורות של אותו יום, מהמאוחרת למוקדמת.",
    inputSchema: {
      type: "object",
      required: ["date"],
      properties: {
        date: { type: "string", description: "YYYY-MM-DD" },
        edition: { type: "string", description: "morning | midday | close | night" },
      },
    },
    async run(a, ctx) {
      const date = String(a.date || "").slice(0, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("date חייב להיות YYYY-MM-DD");
      const idx = await briefIndex(ctx);
      const ed = normEdition(a.edition);
      const hits = idx.briefs.filter((x) => x.date === date && (!ed || x.edition === ed));
      if (!hits.length) {
        const near = idx.briefs.filter((x) => Math.abs(new Date(x.date) - new Date(date)) <= 3 * 86400000)
          .map((x) => x.slug).slice(0, 8);
        return `אין ברייף ל-${date}${ed ? ` במהדורת ${ed}` : ""}.`
          + (near.length ? ` קרובים: ${near.join(", ")}` : "");
      }
      const parts = [];
      for (const b of hits) {
        const t = await briefText(ctx, b.slug);
        parts.push(briefHeader(b) + (t || "(הקובץ חסר)"));
      }
      return parts.join("\n\n---\n\n");
    },
  },
  {
    name: "list_briefs",
    description: "רשימת הברייפים באתר, מהחדש לישן: תאריך, מהדורה, כותרת.",
    inputSchema: {
      type: "object",
      properties: { limit: { type: "integer", description: "ברירת מחדל 30, עד 400" } },
    },
    async run(a, ctx) {
      const idx = await briefIndex(ctx);
      const n = int(a.limit, 30, 1, 400);
      if (!idx.briefs.length) return "אין עדיין ברייפים באתר.";
      return `${idx.briefs.length} ברייפים (מציג ${Math.min(n, idx.briefs.length)}), נבנה ${idx.built}\n\n`
        + "| slug | מהדורה | כותרת |\n|---|---|---|\n"
        + idx.briefs.slice(0, n).map((b) => `| ${b.slug} | ${EDITIONS[b.edition] || b.edition} | ${b.title} |`).join("\n");
    },
  },
  {
    name: "search_briefs",
    description: "חיפוש טקסט בברייפים האחרונים (חברה, סחורה, נושא). מחזיר את הפסקאות התואמות עם תאריך ומהדורה.",
    inputSchema: {
      type: "object",
      required: ["query"],
      properties: {
        query: { type: "string", description: "מחרוזת לחיפוש, למשל שם חברה" },
        max_briefs: { type: "integer", description: "כמה ברייפים אחרונים לסרוק (ברירת מחדל 30, עד 60)" },
        limit: { type: "integer", description: "מספר פסקאות מרבי (ברירת מחדל 25)" },
      },
    },
    async run(a, ctx) {
      const q = String(a.query || "").trim();
      if (q.length < 2) throw new Error("query קצר מדי");
      const idx = await briefIndex(ctx);
      const scan = idx.briefs.slice(0, int(a.max_briefs, 30, 1, 60));
      const limit = int(a.limit, 25, 1, 100);
      const texts = await Promise.all(scan.map((b) => briefText(ctx, b.slug)));
      const out = [];
      for (let i = 0; i < scan.length && out.length < limit; i++) {
        const t = texts[i];
        if (!t) continue;
        for (const para of t.split(/\n\s*\n/)) {
          if (has(para, q)) {
            out.push(`**${scan[i].slug} · ${EDITIONS[scan[i].edition] || scan[i].edition}**\n${para.trim()}`);
            if (out.length >= limit) break;
          }
        }
      }
      if (!out.length) return `לא נמצא "${q}" ב-${scan.length} הברייפים האחרונים.`;
      return `${out.length} פסקאות עבור "${q}" (נסרקו ${scan.length} ברייפים):\n\n` + out.join("\n\n");
    },
  },
  {
    name: "markets",
    description: "רצועת השווקים של המהדורה האחרונה: מט\"ח, ברנט, סחורות, תשואות ומדדים עם שינוי יומי/שבועי/חודשי, תשואת ממשלתי שקלי 10ש ואינדיקטורי מאקרו ישראל (Trading Economics).",
    inputSchema: { type: "object", properties: {} },
    async run(_a, ctx) {
      const d = await asset(ctx, "/mcp/markets.json");
      const m = d && d.markets;
      const te = d && d.te;
      if (!m && !te) return "אין נתוני שווקים באתר.";
      const lines = [];
      if (m) {
        lines.push(`נתוני שווקים ל-${m.date || m.asof || "?"} (markets.json)`);
        lines.push("| מכשיר | ערך | יומי | שבועי | חודשי | נכון ל |", "|---|---|---|---|---|---|");
        const pool = { ...(m.fx || {}), ...(m.instruments || {}) };
        for (const [k, v] of Object.entries(pool)) {
          if (!v || typeof v !== "object") continue;
          const ch = v.changes || {};
          const u = v.change_unit === "pp" ? "pp" : "%";
          const stale = v.stale_days ? ` (ישן ${v.stale_days} ימים)` : "";
          lines.push(`| ${v.label || k} | ${num(v.value, 4)} | ${signed(ch.daily, u)} | ${signed(ch.weekly, u)} | ${signed(ch.monthly, u)} | ${(v.asof || "").slice(0, 10)}${stale} |`);
        }
        if (Array.isArray(m.stale_instruments) && m.stale_instruments.length) {
          lines.push(`\nמכשירים ללא סגירה חדשה: ${m.stale_instruments.join(", ")}`);
        }
      }
      if (te) {
        const il = te.il_gov_10y;
        if (il && il.yield != null) {
          lines.push(`\nממשלתי שקלי 10ש: ${il.yield}% (יומי ${signed(il.daily, "")}${il.date ? `, ${String(il.date).slice(0, 10)}` : ""}) — Trading Economics`);
        }
        if (Array.isArray(te.indicators) && te.indicators.length) {
          lines.push("\nאינדיקטורי מאקרו ישראל (Trading Economics):", "| מדד | ערך | קודם | לתאריך |", "|---|---|---|---|");
          for (const i of te.indicators) {
            lines.push(`| ${i.category || ""} | ${i.value ?? "—"} ${i.unit || ""} | ${i.previous ?? "—"} | ${String(i.date || "").slice(0, 10)} |`);
          }
        }
        if (te.calendar_unavailable) lines.push(`\nלוח אירועים: ${te.calendar_unavailable}`);
      }
      return lines.join("\n");
    },
  },
  {
    name: "maya_reports",
    description: "דיווחי מאיה שסוכמו (כל חברה נסחרת, לא רק הכיסוי): כותרת, מהותיות 1–3, כיוון, סיכום, מספרים מרכזיים והניתוח 'מתחת למספרים'. סינון לפי חברה, ימים, מהותיות וכיסוי.",
    inputSchema: {
      type: "object",
      properties: {
        company: { type: "string", description: "מחרוזת בשם החברה" },
        days: { type: "integer", description: "ימים אחורה (ברירת מחדל 3; באתר שמורים כחמישה ימי דיווח)" },
        min_materiality: { type: "integer", description: "1–3, ברירת מחדל 1" },
        coverage_only: { type: "boolean", description: "רק חברות כיסוי" },
        limit: { type: "integer", description: "ברירת מחדל 40" },
        full: { type: "boolean", description: "true = כולל ניתוח, מאזן, דגלים ומה שלא נאמר" },
      },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/reports.json");
      const rows = (d && d.reports) || [];
      if (!rows.length) return "אין דיווחי מאיה מסוכמים באתר.";
      const cut = new Date(Date.now() - int(a.days, 3, 1, 30) * 86400000).toISOString().slice(0, 10);
      const minm = int(a.min_materiality, 1, 1, 3);
      const sel = rows.filter((r) => (r.ts || "").slice(0, 10) >= cut
        && (r.materiality || 1) >= minm
        && (!a.coverage_only || (r.coverage && r.coverage.length))
        && (!a.company || (r.companies || []).some((c) => has(c, a.company)) || has(r.headline || r.title, a.company)));
      const limit = int(a.limit, 40, 1, 200);
      if (!sel.length) return `אין דיווחים תואמים (${rows.length} דיווחים באתר, מ-${rows[rows.length - 1].ts?.slice(0, 10)} עד ${rows[0].ts?.slice(0, 10)}).`;
      const out = sel.slice(0, limit).map((r) => {
        const figs = (r.key_figures || []).map((f) => `${f.label}: ${f.value}`).join(" · ");
        const parts = [
          `### ${(r.companies || []).join(", ") || "—"} · ${(r.ts || "").replace("T", " ").slice(0, 16)} · מהותיות ${r.materiality || 1}${r.direction ? ` · ${r.direction}` : ""}${r.coverage && r.coverage.length ? " · כיסוי" : ""}`,
          r.headline || r.title ? `**${r.headline || r.title}**` : "",
          r.summary || "",
          figs ? `מספרים: ${figs}` : "",
        ];
        if (a.full) {
          parts.push(
            r.trend || r.context ? `מגמה: ${r.trend || r.context}` : "",
            r.analysis ? `מתחת למספרים: ${r.analysis}` : "",
            r.balance ? `מאזן ומינוף: ${r.balance}` : "",
            (r.flags || []).length ? `דגלים: ${r.flags.join(" | ")}` : "",
            r.omissions ? `מה שלא נאמר: ${r.omissions}` : "",
            r.watch ? `לעקוב: ${r.watch}` : "",
          );
        }
        parts.push(
          (r.affected || []).length ? `נוגע ל: ${r.affected.join(", ")}${r.affected_why ? ` — ${r.affected_why}` : ""}` : "",
          r.url ? `מקור: ${r.url}` : "",
        );
        return parts.filter(Boolean).join("\n");
      });
      return `${sel.length} דיווחים (מציג ${Math.min(limit, sel.length)}):\n\n` + out.join("\n\n");
    },
  },
  {
    name: "coverage_companies",
    description: "רשימת הכיסוי (כ-400 חברות): שם, סקטור, מזהה TASE ומאיה, כינויים ודרייברים. חיפוש לפי שם או סקטור; בלי פרמטרים — ספירה לפי סקטור.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "מחרוזת בשם (עברית/אנגלית/כינוי)" },
        sector: { type: "string", description: "מפתח סקטור, למשל banks / income_real_estate" },
        limit: { type: "integer", description: "ברירת מחדל 50" },
      },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/coverage.json");
      const cos = (d && d.companies) || [];
      if (!cos.length) return "רשימת הכיסוי אינה זמינה באתר.";
      const profiles = (d && d.sector_profiles) || {};
      if (!a.query && !a.sector) {
        const by = {};
        for (const c of cos) by[c.sector || "?"] = (by[c.sector || "?"] || 0) + 1;
        return `${cos.length} חברות כיסוי. לפי סקטור:\n` + Object.entries(by).sort((x, y) => y[1] - x[1])
          .map(([k, n]) => `- ${k} (${(profiles[k] || {}).label || ""}): ${n}`).join("\n");
      }
      const sel = cos.filter((c) => (!a.sector || norm(c.sector) === norm(a.sector))
        && (!a.query || has(c.name_he, a.query) || has(c.name_en, a.query)
          || (c.aliases || []).some((x) => has(x, a.query))));
      if (!sel.length) return "לא נמצאה חברה תואמת.";
      const limit = int(a.limit, 50, 1, 400);
      return `${sel.length} חברות (מציג ${Math.min(limit, sel.length)}):\n` + sel.slice(0, limit).map((c) => {
        const bits = [c.name_he, c.name_en, `סקטור ${c.sector || "?"}`,
          c.tase_sector, c.tase_id ? `TASE ${c.tase_id}` : "", c.maya_company_id ? `מאיה ${c.maya_company_id}` : "",
          (c.aliases || []).length ? `כינויים: ${c.aliases.join(", ")}` : "",
          (c.drivers_extra || []).length ? `דרייברים: ${c.drivers_extra.join(", ")}` : "",
          c.generic_name ? "שם גנרי" : ""];
        return "- " + bits.filter(Boolean).join(" · ");
      }).join("\n");
    },
  },
  {
    name: "conference_calls",
    description: "לוח שיחות הוועידה: שיחות היום והקרובות של חברות נסחרות, עם קישור כניסה כשפורסם, וסימון משוער/לא ידוע.",
    inputSchema: {
      type: "object",
      properties: { include_past: { type: "boolean", description: "גם שיחות שכבר התקיימו" } },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/calls.json");
      const calls = (d && d.calls) || [];
      if (!calls.length) return "אין שיחות ועידה בלוח.";
      const t = today();
      const sel = calls.filter((c) => a.include_past || (c.date || "") >= t)
        .sort((x, y) => `${x.date} ${x.time}`.localeCompare(`${y.date} ${y.time}`));
      if (!sel.length) return `אין שיחות מ-${t} והלאה (${calls.length} בלוח).`;
      const lines = ["| תאריך | שעה | חברה | רבעון | כניסה |", "|---|---|---|---|---|"];
      for (const c of sel) {
        let link;
        if (c.ambiguous) link = `שני קישורים, השיוך אינו ידוע: ${(c.other_links || []).slice(0, 2).join(" · ")}`;
        else if (c.link) link = c.link + (c.link_certain === false ? " (משוער)" : "");
        else link = "לא פורסם קישור";
        if (c.report_url) link += ` · דיווח: ${c.report_url}`;
        lines.push(`| ${c.date || ""} | ${c.time || "—"} | ${c.company || "—"}${c.coverage ? " (כיסוי)" : ""} | ${c.period || ""} | ${link} |`);
      }
      return `היום (ישראל): ${t}\n\n` + lines.join("\n");
    },
  },
  {
    name: "housing_market",
    description: "שוק הדיור מעסקאות Govmap/רשות המסים: מצרף ארצי, וחציון ₪/מ\"ר לעיר עם שינוי רבעוני ושנתי, יד שנייה בנפרד, חלק מקבלן והיקפים. עיר מסוימת — פירוט כולל שכונות וגודל דירה. הנתונים בפיגור של כשישה שבועות ומדגם של שכונות.",
    inputSchema: {
      type: "object",
      properties: { city: { type: "string", description: "שם עיר בעברית (ריק = כל הערים)" } },
    },
    async run(a, ctx) {
      const h = await asset(ctx, "/mcp/housing.json");
      if (!h || !h.market) return (h && h.note) || "אין נתוני שוק דיור באתר.";
      const m = h.market;
      const lines = [`שוק הדיור · רבעון מלא אחרון, חתך ${h.cutoff_month || "?"} (חודשיים אחרונים מוחרגים — פיגור דיווח)`];
      lines.push(`מצרף ארצי (חציון השינויים בין ערים): שנתי ${signed(m.yoy)} · רבעוני ${signed(m.qoq)} · יד שנייה שנתי ${signed(m.used_yoy)}${m.label ? ` · ${m.label}` : ""}${m.why ? ` — ${m.why}` : ""}`);
      lines.push(`רבעון נמדד ${m.q_now || "?"} מול ${m.q_prev || "?"} (רבעוני) ו-${m.q_yoy || "?"} (שנתי) · ${m.panel ?? "?"} ערים במדגם (עולות ${m.rising ?? "?"}, יורדות ${m.falling ?? "?"}, יציבות ${m.flat ?? "?"}) · ${num(m.n, 0)} עסקאות בחלון · רמת העיר החציונית ${num(m.level, 0)} ₪/מ״ר · חלק מקבלן ${m.share_new ?? "—"}%`);
      const cities = h.cities || {};
      if (a.city) {
        const key = Object.keys(cities).find((c) => norm(c) === norm(a.city)) || Object.keys(cities).find((c) => has(c, a.city));
        if (!key) {
          const miss = (h.cities_without_deals || []).find((c) => has(c, a.city));
          return miss ? `${miss}: נסרקה אך המקור החזיר אפס עסקאות — אינה עדות להתמתנות.` : `העיר "${a.city}" אינה במדגם. ערים: ${Object.keys(cities).join(", ")}`;
        }
        const c = cities[key];
        lines.push(`\n## ${key} (${c.region || ""}) — ${c.label || ""}${c.thin ? " · מדגם דק" : ""}`);
        lines.push(`עסקאות ברבעון המלא האחרון: ${c.vol ?? "—"} (קודם ${c.vol_prev ?? "—"}, ${signed(c.vol_change)}) · סה"כ בחלון ${c.n} (מקבלן ${c.n_new}, יד שנייה ${c.n_used})`);
        lines.push(`חציון ₪/מ״ר: ${num(c.ppsm, 0)} · מקבלן ${num(c.ppsm_new, 0)} · יד שנייה ${num(c.ppsm_used, 0)} · פרמיית קבלן ${signed(c.premium_new)}`);
        lines.push(`שינוי: רבעוני ${signed(c.qoq)} · שנתי ${signed(c.yoy)} · יד שנייה שנתי ${signed(c.used_yoy)}${c.mix_flag ? " · **הפער הוא תמהיל, לא מחיר**" : ""}`);
        lines.push(`חלק מקבלן: ${c.share_new ?? "—"}% (קודם ${c.share_new_prev ?? "—"}%) · מחיר חציוני ${money(c.price)} · שטח חציוני ${num(c.area, 0)} מ״ר`);
        if (c.why) lines.push(`קריאה: ${c.why}`);
        if (c.quarters) lines.push("רבעונים (חציון ₪/מ״ר): " + Object.entries(c.quarters).map(([q, v]) => `${q} ${num(v, 0)}`).join(" · "));
        if (c.by_rooms) lines.push("לפי חדרים: " + Object.entries(c.by_rooms).map(([r, v]) => `${r} ${num(v, 0)}`).join(" · "));
        if ((c.hoods || []).length) lines.push("שכונות שנסרקו: " + c.hoods.map((x) => `${x.name} (${x.n} עסקאות, ${num(x.ppsm, 0)} ₪/מ״ר, ${x.new} מקבלן)`).join(" · "));
      } else {
        lines.push("\n| עיר | אזור | ₪/מ״ר | רבעוני | שנתי | יד שנייה שנתי | מקבלן % | עסקאות ברבעון | מגמה |", "|---|---|---|---|---|---|---|---|---|");
        for (const [k, c] of Object.entries(cities).sort((x, y) => (y[1].vol || 0) - (x[1].vol || 0))) {
          lines.push(`| ${k} | ${c.region || ""} | ${num(c.ppsm, 0)} | ${signed(c.qoq)} | ${signed(c.yoy)} | ${signed(c.used_yoy)}${c.mix_flag ? " (תמהיל)" : ""} | ${c.share_new ?? "—"} | ${c.vol ?? "—"}${c.thin ? " (דק)" : ""} | ${c.label || ""} |`);
        }
        if ((h.cities_without_deals || []).length) lines.push(`\nערים שנסרקו ללא עסקאות במקור: ${h.cities_without_deals.join(", ")}`);
      }
      lines.push("\nסייגים: " + (h.caveats || []).join(" "));
      return lines.join("\n");
    },
  },
  {
    name: "off_exchange_trades",
    description: "עסקאות מחוץ לבורסה בימים האחרונים משלושה ערוצים: סקירת הבורסה (בלי זהויות, עם סטייה משער הבסיס ומהנעילה), דיווחי בעלי עניין במאיה (עם זהות ושיעור מההון), ועסקאות מתואמות מ-GTO.",
    inputSchema: {
      type: "object",
      properties: {
        days: { type: "integer", description: "ימים אחורה, ברירת מחדל 3 (עד 10)" },
        security: { type: "string", description: "מחרוזת בשם הנייר/החברה או מספר נייר" },
        limit: { type: "integer", description: "שורות לערוץ, ברירת מחדל 40" },
      },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/offex.json");
      if (!d) return "אין נתוני עסקאות מחוץ לבורסה באתר.";
      const cut = new Date(Date.now() - int(a.days, 3, 1, 10) * 86400000).toISOString().slice(0, 10);
      const limit = int(a.limit, 40, 1, 300);
      const match = (r) => !a.security || ["name", "security", "company", "symbol", "security_id", "sid"]
        .some((k) => r[k] != null && has(String(r[k]), a.security));
      const pickRows = (rows) => (rows || []).filter((r) => (r.date || "") >= cut && match(r));
      const otc = pickRows(d.otc), off = pickRows(d.offex), jmb = pickRows(d.jumbo);
      const out = [`מ-${cut} (בקובץ: מ-${d.since})`];
      out.push(`\n## סקירת הבורסה — ${otc.length} עסקאות`);
      if (otc.length) {
        out.push("| תאריך | נייר | מחיר | מול בסיס | מול נעילה | שווי | % מהמחזור |", "|---|---|---|---|---|---|---|");
        for (const r of otc.slice(0, limit)) {
          out.push(`| ${r.traded_at || r.date} | ${r.name || r.security_id || ""}${r.src === "security" ? " (מהיסטוריית הנייר)" : ""} | ${num(r.price, 2)} | ${signed(r.premium_pct)} | ${signed(r.vs_close_pct)} | ${money(r.value)} | ${num(r.pct_of_day, 0)} |`);
        }
      }
      out.push(`\n## דיווחי בעלי עניין (מאיה) — ${off.length}`);
      if (off.length) {
        const DIR = { buy: "רכישה", sell: "מכירה" };
        for (const r of off.slice(0, limit)) {
          const flags = [r.kind, r.partial ? "partial — מאגד בתוך ומחוץ לבורסה" : "", r.counted === false ? "לא נספר (צד שני/הגשה חוזרת)" : ""].filter(Boolean).join(", ");
          const who = [r.holder, r.holder_type].filter(Boolean).join(" · ");
          out.push(`- ${r.date || (r.published || "").slice(0, 10)} · **${r.company || ""}**${r.security && r.security !== r.company ? ` (${r.security})` : ""} · ${DIR[r.direction] || r.direction || ""} · ${who} · ${money(r.value_ils)}${r.quantity ? ` · ${num(r.quantity, 0)} יח׳ ב-${num(r.price, 2)} ${r.currency || ""}` : ""}${r.pct_of_class != null ? ` · ${num(r.pct_of_class, 3)}% מההון` : ""}${r.holding_pct_after != null ? ` · אחרי: ${num(r.holding_pct_after, 2)}%` : ""}${flags ? ` · ${flags}` : ""}${r.url ? ` · ${r.url}` : ""}`);
        }
      }
      out.push(`\n## עסקאות מתואמות (GTO) — ${jmb.length}`);
      if (jmb.length) {
        out.push("| תאריך | נייר | תמורה | % ממחזור היום | שינוי יומי | סופי |", "|---|---|---|---|---|---|");
        for (const r of jmb.slice(0, limit)) {
          out.push(`| ${r.date} | ${r.name || r.security_id || ""} | ${money(r.value)} | ${num(r.pct_of_day, 0)} | ${signed(r.chg_pct ?? r.chg)} | ${r.final === false ? "לא" : "כן"} |`);
        }
      }
      out.push("\n" + (d.notes || []).join("\n"));
      return out.join("\n");
    },
  },
  {
    name: "headlines",
    description: "הכותרות המהותיות מהחדשות בארץ ובעולם ביממה האחרונה, עם סיכום, 'למה זה חשוב', חברות כיסוי נוגעות ומקורות.",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "integer", description: "ברירת מחדל 30" },
        important_only: { type: "boolean", description: "רק רמה 3" },
        query: { type: "string", description: "סינון טקסט" },
      },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/headlines.json");
      const items = (d && d.items) || [];
      if (!items.length) return "אין כותרות באתר.";
      const sel = items.filter((r) => (!a.important_only || r.level === 3)
        && (!a.query || has(`${r.headline} ${r.summary} ${(r.companies || []).join(" ")}`, a.query)));
      const limit = int(a.limit, 30, 1, 200);
      if (!sel.length) return "אין כותרות תואמות.";
      return `${sel.length} כותרות (${d.hours || 24} שעות אחרונות):\n\n` + sel.slice(0, limit).map((r) => [
        `### ${r.headline}${r.level === 3 ? " · חשוב" : ""} · ${(r.ts || "").replace("T", " ").slice(0, 16)}`,
        r.summary || "", r.why ? `למה זה חשוב: ${r.why}` : "",
        (r.companies || []).length ? `חברות: ${r.companies.join(", ")}` : "",
        (r.sources || []).length ? "מקורות: " + r.sources.map((s) => `${s.name} ${s.url || ""}`).join(" · ") : "",
      ].filter(Boolean).join("\n")).join("\n\n");
    },
  },
  {
    name: "topic_summary",
    description: "תמונת המצב הסקטוריאלית האחרונה (מרכזי נתונים, אנרגיה, פולימרים, חומרי בנייה, מתכות, שילוח, מזון וחקלאות, ביטחון ועוד): אייטמים עם כיוון השפעה וחברות נוגעות. בלי topic — רשימת הנושאים.",
    inputSchema: {
      type: "object",
      properties: { topic: { type: "string", description: "slug או שם הנושא" } },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/topics.json");
      if (!d || !d.summaries || !Object.keys(d.summaries).length) return "אין סיכומי סקטורים באתר.";
      const labels = d.labels || {};
      if (!a.topic) {
        return `סיכומים ל-${d.date || "?"}:\n` + Object.keys(d.summaries).map((k) => `- ${k}: ${labels[k] || ""} (${((d.summaries[k] || {}).items || []).length} אייטמים)`).join("\n");
      }
      const key = Object.keys(d.summaries).find((k) => norm(k) === norm(a.topic) || has(labels[k], a.topic));
      if (!key) return `אין נושא "${a.topic}". קיימים: ${Object.keys(d.summaries).join(", ")}`;
      const s = d.summaries[key] || {};
      const out = [`# ${labels[key] || key} · סיכום ל-${d.date || "?"}`];
      if (s.lead || s.summary) out.push(s.lead || s.summary);
      for (const it of s.items || []) {
        out.push(`\n**${it.title || ""}**\n${it.body || ""}${it.companies ? `\nחברות: ${it.companies}` : ""}${it.direction ? ` · כיוון: ${it.direction}` : ""}`);
      }
      if (s.takeaway) out.push(`\nמשמעות לכיסוי: ${s.takeaway}`);
      return out.join("\n");
    },
  },
  {
    name: "cbs_releases",
    description: "פרסומי הלמ\"ס האחרונים (מדד המחירים לצרכן, מחירי דירות, תשומות הבנייה, התחלות בנייה ועוד) עם הניתוח שנכתב עליהם, ותמונת המדדים העדכנית.",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "integer", description: "ברירת מחדל 12" },
        query: { type: "string", description: "סינון טקסט בכותרת" },
      },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/cbs.json");
      if (!d) return "אין נתוני למ\"ס באתר.";
      const out = [];
      const snap = d.snapshot || {};
      const snapKeys = Object.keys(snap);
      if (snapKeys.length) {
        out.push("תמונת מדדים (snapshot):");
        for (const k of snapKeys.slice(0, 30)) {
          const v = snap[k];
          out.push(`- ${k}: ${typeof v === "object" && v ? JSON.stringify(v).slice(0, 300) : v}`);
        }
      }
      const rel = (d.releases || []).filter((r) => !a.query || has(`${r.title} ${r.topic_label || ""} ${(r.subjects || []).join(" ")}`, a.query));
      const limit = int(a.limit, 12, 1, 40);
      out.push(`\nפרסומים (${rel.length}${a.query ? ` תואמים` : ""}):`);
      for (const r of rel.slice(0, limit)) {
        const an = (d.analyses || {})[String(r.id)];
        out.push(`\n### ${r.title || r.id} · ${String(r.date || r.published || "").slice(0, 10)}${r.topic_label ? ` · ${r.topic_label}` : ""}${r.relevant ? " · רלוונטי לכיסוי" : ""}${r.url ? `\n${r.url}` : ""}`);
        if (r.summary) out.push(r.summary);
        if (an && !an.skip) {
          if (an.headline) out.push(`**${an.headline}**`);
          if ((an.key_figures || []).length) out.push("מספרים: " + an.key_figures.map((f) => `${f.label} ${f.value}${f.change ? ` (${f.change})` : ""}${f.period ? ` ${f.period}` : ""}`).join(" · "));
          if (an.what_happened) out.push(an.what_happened);
          for (const m of an.macro || []) out.push(`- מאקרו · ${m.title}${m.direction ? ` · ${m.direction}` : ""}: ${m.body}`);
          for (const m of an.micro || []) out.push(`- ${m.sector || "ענף"} · ${m.title}${m.direction ? ` · ${m.direction}` : ""}: ${m.body}${(m.companies || []).length ? ` [${m.companies.join(", ")}]` : ""}`);
          if (an.caveats) out.push(`סייגים: ${an.caveats}`);
          if ((an.watch_next || []).length) out.push("לעקוב: " + an.watch_next.map((w) => `${w.what}${w.when ? ` (${w.when})` : ""}`).join(" · "));
        }
      }
      return out.join("\n");
    },
  },
  {
    name: "commodities",
    description: "מחירי הסחורות וחומרי הגלם האחרונים שהאתר עוקב אחריהם (פולימרים, מתכות, דשנים, אנרגיה, שילוח) מול המדידה הקודמת, הידיעות הענפיות האחרונות והניתוח האחרון.",
    inputSchema: {
      type: "object",
      properties: { query: { type: "string", description: "סינון לפי שם סחורה/קבוצה" } },
    },
    async run(a, ctx) {
      const d = await asset(ctx, "/mcp/commodities.json");
      if (!d || (!d.latest && !(d.items || []).length)) return "אין נתוני סחורות באתר.";
      const out = [];
      const L = d.latest || {}, P = d.previous || {};
      // Trading Economics: מחירי ספוט לפי סימבול
      const te = L.te || {};
      const teKeys = Object.keys(te).filter((k) => !a.query || has(`${k} ${te[k].Name || ""} ${te[k].Group || ""}`, a.query));
      if (teKeys.length) {
        out.push(`מחירי ספוט, Trading Economics (${L.date || "?"}, נמשך ${L.fetched_at || "?"}; קודם ${P.date || "—"})`);
        out.push("| סחורה | קבוצה | מחיר | יחידה | יומי % | קודם בקובץ | תאריך |", "|---|---|---|---|---|---|---|");
        for (const k of teKeys) {
          const v = te[k], p = (P.te || {})[k];
          out.push(`| ${v.Name || k} | ${v.Group || ""} | ${num(v.Last, 3)} | ${v.unit || ""} | ${signed(v.DailyPercentualChange)} | ${p ? num(p.Last, 3) : "—"} | ${String(v.Date || "").slice(0, 10)} |`);
        }
      }
      // עקומי חוזים מ-yfinance: חזית מול חודשים קדימה
      const cv = L.curves || {};
      const cvKeys = Object.keys(cv).filter((k) => !a.query || has(`${k} ${cv[k].label || ""}`, a.query));
      if (cvKeys.length) {
        out.push(`\nעקומי חוזים (yfinance, ${L.date || "?"}):`);
        for (const k of cvKeys) {
          const c = cv[k];
          const f = c.front || {};
          const pts = (c.points || []).map((p) => `${p.ahead != null ? `+${p.ahead}ח׳ ` : ""}${p.month || p.date || ""} ${num(p.price, 3)}${p.vs_front_pct != null ? ` (${signed(p.vs_front_pct)} מול החזית)` : ""}`).join(" · ");
          out.push(`- ${c.label || k} (${c.unit || ""}): חזית ${num(f.price, 3)}${f.date ? ` ב-${f.date}` : ""}${pts ? ` · ${pts}` : ""}`);
        }
      }
      if (!teKeys.length && !cvKeys.length && (L.te || L.curves)) out.push(`אין סחורה תואמת ל"${a.query}".`);
      const items = (d.items || []).filter((r) => !a.query || has(`${r.title} ${r.summary || ""} ${r.region || ""} ${(r.commodities || r.groups || []).join(" ")}`, a.query));
      if (items.length) {
        out.push(`\nידיעות ענפיות (${items.length}):`);
        for (const r of items.slice(0, 30)) out.push(`- ${(r.ts || "").slice(0, 10)} · ${r.title || r.headline || ""}${r.region ? ` · ${r.region}` : ""}${r.source ? ` · ${r.source}` : ""}${r.url ? ` ${r.url}` : ""}`);
      }
      const an = d.analysis;
      if (an) {
        out.push(`\nניתוח אחרון (${an.analyzed_at || an.date || ""}):`);
        if (an.headline) out.push(`**${an.headline}**`);
        if (an.overview) out.push(an.overview);
        for (const s of an.sections || []) {
          if (a.query && !has(`${s.group} ${s.title} ${s.body} ${(s.companies || []).join(" ")}`, a.query)) continue;
          out.push(`- ${s.group ? `${s.group} · ` : ""}${s.title}${s.direction ? ` · ${s.direction}` : ""}: ${s.body}${(s.companies || []).length ? ` [${s.companies.join(", ")}]` : ""}`);
        }
        for (const s of an.deals || []) out.push(`- עסקה · ${s.title}: ${s.body}${(s.companies || []).length ? ` [${s.companies.join(", ")}]` : ""}`);
        if ((an.watch || []).length) out.push("לעקוב: " + an.watch.map((w) => `${w.what}${w.when ? ` (${w.when})` : ""}`).join(" · "));
      }
      return out.length ? out.join("\n") : "אין נתוני סחורות באתר.";
    },
  },
  {
    name: "search_filings",
    description: "חיפוש באינדקס הדוחות הכספיים והמצגות של כל חברה נסחרת (ממאיה): תאריך, חברה, כותרת, סוג וקישור ל-PDF. ברירת המחדל: השנה הנוכחית.",
    inputSchema: {
      type: "object",
      required: ["company"],
      properties: {
        company: { type: "string", description: "מחרוזת בשם החברה או בכותרת" },
        year: { type: "integer", description: "שנה (ברירת מחדל: השנה האחרונה באינדקס)" },
        kind: { type: "string", description: "סינון סוג, למשל מצגת / רבעוני / שנתי" },
        limit: { type: "integer", description: "ברירת מחדל 20" },
      },
    },
    async run(a, ctx) {
      const q = String(a.company || "").trim();
      if (q.length < 2) throw new Error("company קצר מדי");
      const man = await asset(ctx, "/filings/manifest.json");
      const years = ((man && man.years) || []).map((y) => String(y.year)).sort().reverse();
      if (!years.length) return "אינדקס הדוחות אינו זמין באתר.";
      const year = a.year ? String(a.year) : years[0];
      if (!years.includes(year)) return `אין אינדקס לשנת ${year}. שנים: ${years.join(", ")}`;
      const txt = await asset(ctx, `/filings/${year}.jsonl`, "text");
      if (!txt) return `קובץ האינדקס לשנת ${year} חסר.`;
      const rows = [];
      for (const line of txt.split("\n")) {
        if (!line.trim()) continue;
        let r;
        try { r = JSON.parse(line); } catch { continue; }
        if (!(r.c || []).some((c) => has(c, q)) && !has(r.t, q)) continue;
        if (a.kind && !has(`${r.k || ""} ${r.t || ""}`, a.kind)) continue;
        rows.push(r);
      }
      rows.sort((x, y) => String(y.d || "").localeCompare(String(x.d || "")));
      const limit = int(a.limit, 20, 1, 100);
      if (!rows.length) return `לא נמצאו דוחות ל"${q}" ב-${year} (${man.total ? `${man.total} באינדקס, ` : ""}${man.earliest || ""}–${man.latest || ""}).`;
      return `${rows.length} דוחות ל"${q}" ב-${year} (מציג ${Math.min(limit, rows.length)}):\n` + rows.slice(0, limit).map((r) =>
        `- ${r.d} · ${(r.c || []).join(", ")} · ${r.t || ""}${r.k ? ` · ${r.k}` : ""}${r.cov ? " · כיסוי" : ""}${r.p && r.p !== "None" ? ` · ${MAYA_FILES}${r.p}` : ""}${r.id ? ` · id ${r.id}` : ""}`).join("\n");
    },
  },
];

// --------------------------------------------------------------------------
// JSON-RPC

class RpcError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

async function handle(method, params, ctx) {
  switch (method) {
    case "initialize": {
      const asked = params && params.protocolVersion;
      return {
        protocolVersion: PROTOCOLS.includes(asked) ? asked : PROTOCOLS[0],
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER,
        instructions: INSTRUCTIONS,
      };
    }
    case "ping":
      return {};
    case "tools/list":
      return { tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })) };
    case "tools/call": {
      const tool = TOOLS.find((t) => t.name === (params && params.name));
      if (!tool) throw new RpcError(-32602, `כלי לא מוכר: ${params && params.name}`);
      try {
        const text = await tool.run((params && params.arguments) || {}, ctx);
        return { content: [{ type: "text", text: clip(text) }] };
      } catch (e) {
        return { content: [{ type: "text", text: `שגיאה בכלי ${tool.name}: ${e && e.message ? e.message : String(e)}` }], isError: true };
      }
    }
    case "resources/list":
      return { resources: [] };
    case "prompts/list":
      return { prompts: [] };
    default:
      throw new RpcError(-32601, `שיטה לא נתמכת: ${method}`);
  }
}

async function rpc(msg, ctx) {
  if (!msg || typeof msg !== "object" || typeof msg.method !== "string") {
    return { jsonrpc: "2.0", id: (msg && msg.id) ?? null, error: { code: -32600, message: "Invalid Request" } };
  }
  const notification = msg.id === undefined || msg.id === null;
  try {
    const result = await handle(msg.method, msg.params || {}, ctx);
    return notification ? null : { jsonrpc: "2.0", id: msg.id, result };
  } catch (e) {
    if (notification) return null;
    return { jsonrpc: "2.0", id: msg.id, error: { code: e instanceof RpcError ? e.code : -32603, message: String(e && e.message ? e.message : e) } };
  }
}

// --------------------------------------------------------------------------
// HTTP

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version",
  "Access-Control-Expose-Headers": "MCP-Protocol-Version",
};
const NO_STORE = { "Cache-Control": "no-store" };

function reply(obj, status = 200, extra = {}) {
  return new Response(obj === null ? null : JSON.stringify(obj), {
    status,
    headers: { ...(obj === null ? {} : { "Content-Type": "application/json" }), ...NO_STORE, ...CORS, ...extra },
  });
}

function presentedToken(request, pathParam) {
  const auth = request.headers.get("Authorization") || "";
  const m = /^Bearer\s+(\S+)$/i.exec(auth.trim());
  if (m) return m[1];
  const segs = Array.isArray(pathParam) ? pathParam : (pathParam ? [pathParam] : []);
  return segs.length ? String(segs[0]) : "";
}

export async function onRequest(context) {
  const { request, env, params } = context;
  if (request.method === "OPTIONS") return reply(null, 204);
  if (request.method !== "POST") {
    return reply({ error: "שרת ה-MCP של TLV TASE View מקבל POST בלבד (Streamable HTTP, ללא זרם)" },
      405, { Allow: "POST, OPTIONS" });
  }

  if (!env.MCP_TOKEN) return reply({ error: "שרת ה-MCP אינו מוגדר (MCP_TOKEN חסר)" }, 503);
  const tok = presentedToken(request, params && params.path);
  if (!tok || !timingSafeEqual(tok, String(env.MCP_TOKEN))) {
    return reply({ error: "נדרש אסימון" }, 401, { "WWW-Authenticate": 'Bearer realm="tlv-tase-view"' });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return reply({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, 400);
  }

  const ctx = { request, env };
  if (Array.isArray(body)) {
    const out = (await Promise.all(body.map((m) => rpc(m, ctx)))).filter(Boolean);
    return out.length ? reply(out) : reply(null, 202);
  }
  const res = await rpc(body, ctx);
  return res ? reply(res) : reply(null, 202);
}
