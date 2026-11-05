// הכתובת החלופית של האתר: forest-brief.pages.dev.
//
// **למה היא קיימת.** הדומיין tlvtaseview.com חדש, ומסנני רשת ארגוניים
// (FortiGuard במשרד) חוסמים אותו כ-"Newly Registered Domain". כתובת ה-pages.dev
// של אותו פרויקט מגישה את אותו אתר מאותה פריסה, ונפתחת מכל מחשב.
//
// **מי נכנס בה — מתג של הבעלים**, שנשמר ב-KV ונקבע בדף החשבון:
//   owner — רק הבעלים (OWNER_EMAIL). ברירת המחדל.
//   users — כל משתמש מאושר, באותו מייל וסיסמה כמו באתר.
//   off   — הכתובת מפנה לאתר הרגיל, כמו לפני שנפתחה.
// בכל המצבים נדרשת כניסה. מצב שבו נכנסים בלי סיסמה לא קיים, בכוונה: זה
// תוכן בתשלום, ו"השיחות שלי" לבעלים בלבד בכל מקרה.
//
// **נכשל אל המצב המצומצם.** ערך חסר, ערך שאינו מוכר או KV שאינו עונה —
// כל אלה נקראים "owner": הבעלים עדיין נכנס, ואף אחד אחר לא.

export const ALT = "forest-brief.pages.dev";
export const ALT_KEY = "config:alt_access";
export const ALT_MODES = ["owner", "users", "off"];

export async function altMode(env) {
  try {
    const v = env.USERS ? await env.USERS.get(ALT_KEY) : null;
    return ALT_MODES.includes(v) ? v : "owner";
  } catch (e) {
    return "owner";
  }
}
