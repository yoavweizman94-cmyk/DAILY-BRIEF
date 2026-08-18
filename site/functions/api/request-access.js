// קליטת בקשת גישה מעמוד הנחיתה, ושליחת התראה ליואב.
//
// הבקשה אינה מאשרת דבר בעצמה. היא שולחת מייל עם הפרטים ועם קישור חתום
// שרק לחיצה עליו מוסיפה את הכתובת לרשימת המורשים — כדי שאף אחד לא יוכל
// להעניק לעצמו גישה על ידי מילוי טופס.
const RESEND = "https://api.resend.com/emails";

function esc(s) {
  return String(s || "").replace(/[<>&"]/g, c =>
    ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));
}

// חתימה על הכתובת: קישור האישור נושא HMAC, ולכן אי אפשר לזייף אותו
// ולאשר כתובת שמעולם לא ביקשה.
async function sign(email, secret) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(email));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequestPost(context) {
  const { request, env } = context;
  const json = (obj, status) => new Response(JSON.stringify(obj),
    { status, headers: { "Content-Type": "application/json" } });

  let body;
  try { body = await request.json(); } catch { return json({ error: "בקשה לא תקינה" }, 400); }

  const name = String(body.name || "").trim().slice(0, 80);
  const email = String(body.email || "").trim().toLowerCase().slice(0, 120);
  const org = String(body.org || "").trim().slice(0, 120);
  const why = String(body.why || "").trim().slice(0, 500);

  if (!name || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return json({ error: "שם וכתובת מייל תקינה הם שדות חובה" }, 400);
  }
  if (!env.RESEND_API_KEY || !env.OWNER_EMAIL || !env.APPROVAL_SECRET) {
    return json({ error: "השירות אינו מוגדר במלואו" }, 503);
  }

  const token = await sign(email, env.APPROVAL_SECRET);
  const base = new URL(request.url).origin;
  const approve = `${base}/api/approve?email=${encodeURIComponent(email)}&t=${token}`;

  const html = `<div dir="rtl" style="font-family:Arial,sans-serif;line-height:1.7">
    <h2 style="margin:0 0 12px">בקשת גישה חדשה</h2>
    <table style="border-collapse:collapse;font-size:15px">
      <tr><td style="padding:4px 12px 4px 0;color:#666">שם</td><td>${esc(name)}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#666">מייל</td><td>${esc(email)}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#666">גוף</td><td>${esc(org) || "—"}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#666;vertical-align:top">מעניין אותו</td>
          <td>${esc(why) || "—"}</td></tr>
    </table>
    <p style="margin:20px 0 8px">
      <a href="${approve}" style="background:#17624a;color:#fff;text-decoration:none;
         padding:10px 22px;border-radius:6px;display:inline-block;font-weight:bold">אשר גישה</a>
    </p>
    <p style="color:#888;font-size:13px">
      התעלמות מהמייל הזה משאירה את הבקשה ללא מענה — אין צורך בפעולה כדי לדחות.
    </p>
  </div>`;

  const res = await fetch(RESEND, {
    method: "POST",
    headers: { "Authorization": `Bearer ${env.RESEND_API_KEY}`,
               "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.FROM_EMAIL || "TLV TASE View <noreply@tlvtaseview.com>",
      to: [env.OWNER_EMAIL],
      reply_to: email,
      subject: `בקשת גישה: ${name}${org ? " · " + org : ""}`,
      html,
    }),
  });

  if (!res.ok) {
    // הודעת השגיאה של הספק אינה נחשפת למבקר, אבל כן נרשמת ללוג
    console.log("Resend failed", res.status, await res.text());
    return json({ error: "שליחת הבקשה נכשלה" }, 502);
  }
  return json({ ok: true }, 200);
}
