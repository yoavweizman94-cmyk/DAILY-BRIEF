// נקודת האסימון של OAuth: קוד הרשאה ← אסימונים, ורענון.
//
// **רענון הוא מה שהופך את החיבור לתמידי.** אסימון הגישה תקף יממה; לפני
// שהוא פג, Claude מחליף את אסימון הרענון בזוג חדש. אסימון רענון אינו פג
// מעצמו — הוא מתחלף בכל שימוש, והישן נשאר תקף עשר דקות כדי שרענון כפול לא
// ינתק את המחבר. בכל רענון נבדק מחדש שהמשתמש פעיל ושהוא הבעלים.
import {
  AT_TTL, RT_GRACE, SCOPE, allowedUser, authClient, dropRefresh, getRefresh, issueAccessToken,
  jsonr, mcpResource, oauthError, pkceOk, preflight, putRefresh, randomToken, readBody, takeCode,
} from "../../_lib/oauth.js";

export const onRequestOptions = preflight;

async function mint(env, request, client, sub, resource) {
  const aud = resource || mcpResource(request);
  const access_token = await issueAccessToken(env.SESSION_SECRET,
    { sub, client_id: client.client_id, scope: SCOPE, aud });
  const refresh_token = randomToken(32);
  await putRefresh(env, refresh_token, {
    client_id: client.client_id, sub, resource: aud, created: Math.floor(Date.now() / 1000),
  });
  return { access_token, token_type: "Bearer", expires_in: AT_TTL, refresh_token, scope: SCOPE };
}

export async function onRequestPost({ request, env }) {
  if (!env.USERS || !env.SESSION_SECRET) return oauthError("temporarily_unavailable", "השירות אינו מוגדר", 503);
  const body = await readBody(request);
  const client = await authClient(env, request, body);
  if (!client) return oauthError("invalid_client", "הלקוח אינו רשום או שהסוד שגוי", 401);

  if (body.grant_type === "authorization_code") {
    const c = await takeCode(env, body.code);
    if (!c || c.client_id !== client.client_id || Math.floor(Date.now() / 1000) > c.exp) {
      return oauthError("invalid_grant", "קוד ההרשאה אינו תקף");
    }
    if (body.redirect_uri && body.redirect_uri !== c.redirect_uri) {
      return oauthError("invalid_grant", "כתובת החזרה אינה תואמת");
    }
    if (!(await pkceOk(body.code_verifier, c.challenge))) {
      return oauthError("invalid_grant", "אימות PKCE נכשל");
    }
    if (!(await allowedUser(env, c.sub))) return oauthError("invalid_grant", "החשבון אינו מורשה");
    return jsonr(await mint(env, request, client, c.sub, c.resource));
  }

  if (body.grant_type === "refresh_token") {
    const r = await getRefresh(env, body.refresh_token);
    if (!r || r.client_id !== client.client_id) return oauthError("invalid_grant", "אסימון הרענון אינו תקף");
    if (!(await allowedUser(env, r.sub))) {
      await dropRefresh(env, body.refresh_token);
      return oauthError("invalid_grant", "החשבון אינו מורשה");
    }
    const out = await mint(env, request, client, r.sub, r.resource);
    // הישן נשאר בתוקף לחלון חסד ואז נמחק מעצמו — בלי להאריך אותו שוב.
    if (!r.rotated) await putRefresh(env, body.refresh_token, { ...r, rotated: Math.floor(Date.now() / 1000) }, RT_GRACE);
    return jsonr(out);
  }

  return oauthError("unsupported_grant_type", "נתמכים authorization_code ו-refresh_token");
}
