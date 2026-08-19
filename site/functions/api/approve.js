// הפעלת חשבון. הקישור חתום ב-HMAC, ולכן אי אפשר להרכיב אותו לכתובת
// שלא נרשמה — מילוי טופס ההרשמה לבדו לעולם אינו מעניק גישה.
import { getUser, putUser, timingSafeEqual, normEmail } from "../_lib/auth.js";

const RESEND = "https://api.resend.com/emails";

// הכתובת שבה משתמש workflow ה-access-flow-check. חסומה להפעלה בכוונה —
// הבדיקה שולחת מייל אמיתי עם כפתור עובד, וב-19/08/2026 הוא נלחץ בטעות.
const TEST_ADDRESS = "access-check@tlvtaseview.com";

function page(title, msg, ok) {
  return new Response(
    `<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
     <meta name="viewport" content="width=device-width,initial-scale=1">
     <title>${title}</title><link rel="stylesheet" href="/style.css"></head>
     <body><main style="max-width:34rem;margin:4rem auto;padding:0 1.2rem">
     <h1>${title}</h1><p>${msg}</p></main></body></html>`,
    { status: ok ? 200 : 400, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

async function sign(email, secret) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(email));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const email = normEmail(url.searchParams.get("email"));
  const token = url.searchParams.get("t") || "";

  if (!email || !token) return page("קישור חסר", "חסרים פרטים בקישור.", false);

  if (email === TEST_ADDRESS) {
    return page("כתובת בדיקה", "זו הכתובת שבה משתמש אימות הזרימה. " +
                "היא לא הופעלה, וזו התנהגות מכוונת.", false);
  }
  if (!env.APPROVAL_SECRET || !env.USERS) {
    return page("השירות אינו מוגדר", "חסרות הגדרות בצד השרת.", false);
  }
  if (!timingSafeEqual(token, await sign(email, env.APPROVAL_SECRET))) {
    return page("קישור לא תקף", "החתימה אינה תואמת.", false);
  }

  const user = await getUser(env, email);
  if (!user) {
    return page("לא נמצאה הרשמה", `אין הרשמה ממתינה עבור ${email}.`, false);
  }
  if (user.status === "active") {
    return page("כבר פעיל", `החשבון של ${email} כבר פעיל.`, true);
  }

  user.status = "active";
  user.approved = new Date().toISOString();
  await putUser(env, email, user);

  // הודעה למשתמש. כשל כאן אינו מבטל את ההפעלה שכבר בוצעה.
  if (env.RESEND_API_KEY) {
    const login = `https://app.tlvtaseview.com/login`;
    try {
      await fetch(RESEND, {
        method: "POST",
        headers: { "Authorization": `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          from: env.FROM_EMAIL || "TLV TASE View <noreply@tlvtaseview.com>",
          to: [email],
          subject: "החשבון שלך ב-TLV TASE View הופעל",
          html: `<div dir="rtl" style="font-family:Arial,sans-serif;line-height:1.7">
            <h2 style="margin:0 0 12px">החשבון הופעל</h2>
            <p>אפשר להיכנס עם כתובת המייל והסיסמה שבחרת בהרשמה.</p>
            <p style="margin:20px 0 8px">
              <a href="${login}" style="background:#0f4c63;color:#fff;text-decoration:none;
                 padding:10px 22px;border-radius:5px;display:inline-block;font-weight:bold">כניסה</a>
            </p>
            <p style="color:#888;font-size:13px">${login}</p>
          </div>`,
          text: `החשבון שלך ב-TLV TASE View הופעל.\n\nכניסה: ${login}\n\n` +
                `השתמש בכתובת המייל ובסיסמה שבחרת בהרשמה.`,
        }),
      });
    } catch (e) { console.log("notify failed", String(e)); }
  }

  return page("החשבון הופעל", `${email} יכול להיכנס מעכשיו עם הסיסמה שבחר.`, true);
}
