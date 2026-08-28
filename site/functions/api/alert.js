// התראת תקלה במייל, לבעלים בלבד.
//
// **למה דרך האתר ולא ישירות מ-Actions.** מפתח הדואר (RESEND_API_KEY)
// ו-OWNER_EMAIL יושבים בסביבת Cloudflare ולא בסודות של GitHub, ואין
// סיבה לשכפל סוד לשני מקומות. SCAN_KEY לעומת זאת כבר קיים בשניהם —
// הוא משמש את ממסר Govmap מאותה סיבה בדיוק — ולכן הוא המפתח כאן,
// והאתר הוא ששולח בפועל.
//
// **הנתיב הזה אינו שולח לכתובת שנשלחה אליו.** היעד קבוע: OWNER_EMAIL
// מהסביבה. גוף הבקשה קובע רק את הטקסט. בלי הכלל הזה זהו ממסר דואר
// פתוח לכל מי שהשיג את המפתח.
import { timingSafeEqual } from "../_lib/auth.js";

const RESEND = "https://api.resend.com/emails";
const MAX = 8000;

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export async function onRequestPost(context) {
  const { request, env } = context;

  if (!env.SCAN_KEY) return json(503, { error: "SCAN_KEY לא מוגדר" });
  if (!timingSafeEqual(request.headers.get("x-scan-key") || "", env.SCAN_KEY)) {
    return json(401, { error: "מפתח שגוי" });
  }
  if (!env.RESEND_API_KEY || !env.OWNER_EMAIL) {
    return json(503, { error: "הדואר אינו מוגדר" });
  }

  let body;
  try { body = await request.json(); } catch { return json(400, { error: "בקשה לא תקינה" }); }

  const subject = String(body.subject || "התראה מ-TLV TASE View").slice(0, 140);
  const text = String(body.text || "").slice(0, MAX);
  if (!text.trim()) return json(400, { error: "אין תוכן להתראה" });

  const html =
    `<div dir="rtl" style="font-family:Arial,sans-serif;line-height:1.7">` +
    `<h2 style="margin:0 0 12px">${esc(subject)}</h2>` +
    `<pre style="white-space:pre-wrap;font-family:inherit;margin:0">${esc(text)}</pre>` +
    `</div>`;

  const res = await fetch(RESEND, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.FROM_EMAIL || "TLV TASE View <noreply@tlvtaseview.com>",
      to: [env.OWNER_EMAIL],
      subject,
      html,
      text,
    }),
  });

  if (!res.ok) {
    // קוד התשובה מוחזר לאבחון; גוף השגיאה אינו נחשף.
    return json(502, { error: "השליחה נכשלה", mailStatus: res.status });
  }
  return json(200, { ok: true });
}
