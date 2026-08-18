// אישור בקשת גישה — נקרא מהקישור שבמייל ליואב.
//
// שני מחסומים לפני שכתובת נוספת לרשימה:
// 1. הקישור חתום ב-HMAC, ולכן אי אפשר להרכיב אותו ידנית לכתובת אחרת.
// 2. ההשוואה לחתימה היא בזמן קבוע, כדי שלא ניתן יהיה לגלות אותה בניחוש
//    הדרגתי לפי זמן התגובה.
const CF = "https://api.cloudflare.com/client/v4";

async function sign(email, secret) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(email));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function page(title, msg, ok) {
  return new Response(
    `<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
     <meta name="viewport" content="width=device-width,initial-scale=1">
     <title>${title}</title><link rel="stylesheet" href="/style.css"></head>
     <body><main><h1>${title}</h1><p>${msg}</p></main></body></html>`,
    { status: ok ? 200 : 400, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const email = (url.searchParams.get("email") || "").toLowerCase();
  const token = url.searchParams.get("t") || "";

  if (!email || !token) return page("קישור חסר", "חסרים פרטים בקישור.", false);
  if (!env.APPROVAL_SECRET || !env.CF_API_TOKEN || !env.CF_ACCOUNT_ID || !env.ACCESS_APP_ID) {
    return page("השירות אינו מוגדר", "חסרות הגדרות בצד השרת.", false);
  }
  if (!timingSafeEqual(token, await sign(email, env.APPROVAL_SECRET))) {
    return page("קישור לא תקף", "החתימה אינה תואמת.", false);
  }

  const api = `${CF}/accounts/${env.CF_ACCOUNT_ID}/access/apps/${env.ACCESS_APP_ID}/policies`;
  const head = { "Authorization": `Bearer ${env.CF_API_TOKEN}`,
                 "Content-Type": "application/json" };

  const cur = await (await fetch(api, { headers: head })).json();
  const policy = (cur.result || [])[0];
  if (!policy) return page("לא נמצאה מדיניות", "אין מדיניות Access לעדכן.", false);

  const include = policy.include || [];
  const already = include.some(r => r.email && r.email.email === email);
  if (already) return page("כבר מאושר", `${email} כבר ברשימה.`, true);

  const res = await fetch(`${api}/${policy.id}`, {
    method: "PUT", headers: head,
    body: JSON.stringify({ name: policy.name, decision: policy.decision,
                           include: include.concat([{ email: { email } }]) }),
  });
  if (!res.ok) {
    console.log("Access update failed", res.status, await res.text());
    return page("העדכון נכשל", "לא ניתן היה לעדכן את רשימת המורשים.", false);
  }

  // הודעה למבקש. כשל כאן אינו מבטל את האישור שכבר בוצע.
  if (env.RESEND_API_KEY) {
    await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { "Authorization": `Bearer ${env.RESEND_API_KEY}`,
                 "Content-Type": "application/json" },
      body: JSON.stringify({
        from: env.FROM_EMAIL || "TLV TASE View <noreply@tlvtaseview.com>",
        to: [email],
        subject: "הגישה שלך ל-TLV TASE View אושרה",
        html: `<div dir="rtl" style="font-family:Arial,sans-serif;line-height:1.7">
          <h2>הגישה אושרה</h2>
          <p>אפשר להיכנס בכתובת
            <a href="https://app.tlvtaseview.com">app.tlvtaseview.com</a>.</p>
          <p>הכניסה היא בקוד חד-פעמי שנשלח לכתובת הזו — אין סיסמה ליצור או לזכור.</p>
        </div>`,
      }),
    }).catch(() => {});
  }
  return page("אושר", `${email} נוסף לרשימת המורשים ונשלחה אליו הודעה.`, true);
}
