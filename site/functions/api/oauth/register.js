// רישום לקוח OAuth דינמי (RFC 7591) — כך claude.ai ו-Claude Code נרשמים
// בעצמם כשמוסיפים את המחבר, בלי client_id שמישהו צריך להעתיק ביד.
//
// הרישום פתוח, כפי שהמפרט מצפה, כי הוא לבדו אינו נותן דבר: גישה מתקבלת רק
// אחרי כניסה של הבעלים ואישור מפורש בדף ההרשאה. מה שנשאר לחסום הוא הצפה
// של ה-KV — ולכן מגבלת קצב לפי IP, ותקרה לאורך כל שדה.
import { rateLimit } from "../../_lib/auth.js";
import {
  jsonr, oauthError, preflight, putClient, randomToken, redirectUriOk, sha256,
} from "../../_lib/oauth.js";

const METHODS = ["none", "client_secret_post", "client_secret_basic"];

export const onRequestOptions = preflight;

export async function onRequestPost({ request, env }) {
  if (!env.USERS) return oauthError("temporarily_unavailable", "השירות אינו מוגדר", 503);

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const rl = await rateLimit(env, `oauthreg:${ip}`, 20, 3600);
  if (!rl.ok) return oauthError("temporarily_unavailable", "יותר מדי רישומים מהכתובת הזו — נסה בעוד שעה", 429);

  let meta;
  try { meta = await request.json(); } catch { meta = null; }
  if (!meta || typeof meta !== "object") return oauthError("invalid_client_metadata", "גוף JSON נדרש");

  const uris = Array.isArray(meta.redirect_uris) ? meta.redirect_uris : [];
  if (!uris.length || uris.length > 5 || !uris.every(redirectUriOk)) {
    return oauthError("invalid_redirect_uri", "נדרשות 1–5 כתובות חזרה ב-https (או http ל-localhost)");
  }
  // ברירת המחדל של RFC 7591 כשהשדה חסר היא client_secret_basic.
  const method = meta.token_endpoint_auth_method === undefined
    ? "client_secret_basic" : String(meta.token_endpoint_auth_method);
  if (!METHODS.includes(method)) {
    return oauthError("invalid_client_metadata", `token_endpoint_auth_method נתמך: ${METHODS.join(", ")}`);
  }

  const now = Math.floor(Date.now() / 1000);
  const client = {
    client_id: randomToken(16),
    client_name: String(meta.client_name || "לקוח MCP").slice(0, 100),
    redirect_uris: uris,
    token_endpoint_auth_method: method,
    created: now,
  };
  let secret = "";
  if (method !== "none") {
    secret = randomToken(32);
    client.secret_hash = await sha256(secret);
  }
  await putClient(env, client);

  return jsonr({
    client_id: client.client_id,
    client_id_issued_at: now,
    client_name: client.client_name,
    redirect_uris: client.redirect_uris,
    token_endpoint_auth_method: method,
    grant_types: ["authorization_code", "refresh_token"],
    response_types: ["code"],
    ...(secret ? { client_secret: secret, client_secret_expires_at: 0 } : {}),
  }, 201);
}
