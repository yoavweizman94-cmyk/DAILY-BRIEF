// ביטול אסימון (RFC 7009) — Claude קורא לכאן כשמנתקים את המחבר.
//
// אסימון רענון נמחק מה-KV, וזה מה שמנתק בפועל: בלעדיו אין אסימון גישה
// חדש. אסימון גישה חתום ואינו נשמר בשום מקום, ולכן הוא פג מעצמו תוך יממה.
// התשובה 200 בכל מקרה, כפי שהמפרט דורש, כדי לא לגלות אילו אסימונים קיימים.
import { CORS, authClient, dropRefresh, getRefresh, preflight, readBody } from "../../_lib/oauth.js";

export const onRequestOptions = preflight;

export async function onRequestPost({ request, env }) {
  if (env.USERS) {
    const body = await readBody(request);
    const client = await authClient(env, request, body);
    const r = await getRefresh(env, body.token);
    if (r && client && r.client_id === client.client_id) await dropRefresh(env, body.token);
  }
  return new Response(null, { status: 200, headers: { ...CORS, "Cache-Control": "no-store" } });
}
