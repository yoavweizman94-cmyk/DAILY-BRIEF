// הרשמה. יוצרת חשבון במצב "ממתין" בלבד — הפעלה נעשית רק בלחיצה על
// הקישור החתום שנשלח ליואב, כך שמילוי הטופס לעולם אינו מעניק גישה.
import {
  hashPassword, putUser, getUser, rateLimit, json,
  passwordProblem, normEmail, validEmail, b64url,
} from "../_lib/auth.js";

const RESEND = "https://api.resend.com/emails";

function esc(s) {
  return String(s || "").replace(/[<>&"]/g, c =>
    ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));
}

async function sign(email, secret) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(email));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequestPost(context) {
  const { request, env } = context;

  let body;
  try { body = await request.json(); } catch { return json({ error: "בקשה לא תקינה" }, 400); }

  const name = String(body.name || "").trim().slice(0, 80);
  const email = normEmail(body.email);
  const org = String(body.org || "").trim().slice(0, 120);
  const why = String(body.why || "").trim().slice(0, 500);
  const password = String(body.password || "");

  if (!name || !validEmail(email)) return json({ error: "שם וכתובת מייל תקינה הם שדות חובה" }, 400);
  const pwErr = passwordProblem(password);
  if (pwErr) return json({ error: pwErr }, 400);

  // רק מה שנדרש כדי **ליצור** את החשבון. שליחת ההתראה היא שלב נפרד:
  // מפתח דואר חסר או ספק שנפל אינם סיבה לאבד הרשמה של לקוח משלם —
  // החשבון נשמר כממתין, והבעלים רואה אותו ברשימת המשתמשים גם בלי מייל.
  if (!env.USERS || !env.APPROVAL_SECRET) {
    return json({ error: "השירות אינו מוגדר במלואו" }, 503);
  }

  // תקרה לפי כתובת IP — נרשם אחד לא אמור לפתוח עשרות חשבונות
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const rl = await rateLimit(env, `reg:${ip}`, 5, 3600);
  if (!rl.ok) return json({ error: "יותר מדי בקשות. נסה שוב בעוד שעה." }, 429);

  const existing = await getUser(env, email);
  if (existing && existing.status === "active") {
    return json({ error: "כתובת המייל הזו כבר רשומה. אפשר להתחבר." }, 409);
  }

  const { hash, salt, iterations } = await hashPassword(password);
  await putUser(env, email, {
    name, org, why, email,
    hash, salt, iterations,
    status: "pending",
    created: new Date().toISOString(),
    approved: null,
    lastLogin: null,
  });

  // נתיב ולא מחרוזת שאילתה: סימן שוויון בקישור נבלע בקידוד המייל
  // ושובר את הטוקן. הפירוט ב-api/approve/[token].js.
  const token = await sign(email, env.APPROVAL_SECRET);
  const base = new URL(request.url).origin;
  const approve = `${base}/api/approve/${b64url(new TextEncoder().encode(email))}.${token}`;

  const html = `<div dir="rtl" style="font-family:Arial,sans-serif;line-height:1.7">
    <h2 style="margin:0 0 12px">בקשת גישה חדשה</h2>
    <table style="border-collapse:collapse;font-size:15px">
      <tr><td style="padding:4px 12px 4px 0;color:#666">שם</td><td>${esc(name)}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#666">מייל</td><td>${esc(email)}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#666">גוף / תפקיד</td><td>${esc(org) || "—"}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#666;vertical-align:top">מה מעניין אותו</td>
          <td>${esc(why) || "—"}</td></tr>
    </table>
    <p style="margin:20px 0 8px">
      <a href="${approve}" style="background:#0f4c63;color:#fff;text-decoration:none;
         padding:10px 22px;border-radius:5px;display:inline-block;font-weight:bold">הפעל את החשבון</a>
    </p>
    <p style="color:#888;font-size:13px">
      החשבון כבר נוצר עם הסיסמה שהמשתמש בחר, אבל הוא מושבת ואינו מאפשר
      כניסה עד הלחיצה. התעלמות מהמייל הזה משאירה אותו מושבת — אין צורך
      בפעולה כדי לדחות.
    </p>
  </div>`;

  const text = [
    "בקשת גישה חדשה", "",
    `שם: ${name}`, `מייל: ${email}`,
    `גוף / תפקיד: ${org || "—"}`, `מה מעניין אותו: ${why || "—"}`, "",
    `הפעלת החשבון: ${approve}`, "",
    "החשבון נוצר מושבת ואינו מאפשר כניסה עד הלחיצה.",
  ].join("\n");

  if (!env.RESEND_API_KEY || !env.OWNER_EMAIL) {
    console.log("register: notification skipped, mail not configured");
    return json({ ok: true, notified: false, mail: "unconfigured" }, 200);
  }

  const res = await fetch(RESEND, {
    method: "POST",
    headers: { "Authorization": `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.FROM_EMAIL || "TLV TASE View <noreply@tlvtaseview.com>",
      to: [env.OWNER_EMAIL], reply_to: email,
      subject: `בקשת גישה: ${name}${org ? " · " + org : ""}`,
      html, text,
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    console.log("Resend failed", res.status, detail);
    // קוד התשובה מוחזר כדי שאפשר יהיה לאבחן מבחוץ: 401 הוא מפתח פסול,
    // 403 דומיין שאינו מאומת, 422 כתובת שולח שנדחתה. גוף השגיאה עצמו
    // אינו נחשף — הוא עלול להכיל פרטי חשבון.
    // החשבון כבר נשמר כממתין; רק ההתראה נכשלה, ולכן זו אינה שגיאת לקוח.
    return json({ ok: true, notified: false, mail: "rejected", mailStatus: res.status }, 200);
  }
  return json({ ok: true, notified: true }, 200);
}
