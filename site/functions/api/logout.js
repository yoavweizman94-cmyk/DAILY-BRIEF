// יציאה. מנקה את העוגייה ומחזיר לדף הכניסה.
import { clearCookie } from "../../lib/auth.js";

function bye() {
  return new Response(null, {
    status: 302,
    headers: { "Location": "/login", "Set-Cookie": clearCookie() },
  });
}

export const onRequestGet = bye;
export const onRequestPost = bye;
