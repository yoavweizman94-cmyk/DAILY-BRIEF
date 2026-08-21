// ממסר לקריאות Govmap, כי הראנרים של GitHub חסומים שם.
//
// Govmap מחזיר 403 לכל בקשה מטווחי הענן של Azure — כולל דף הבית, וגם
// ב-HTTP client רגיל בלי חיקוי TLS. זו חסימה לפי כתובת ולא לפי טביעה,
// ולכן אין תיקון בצד הלקוח. Cloudflare, שהאתר יושב עליו ממילא, מגיע
// למקור (נבדק 21/08/2026, 200). הסריקה עוברת דרך כאן.
//
// שני מעקים, כי הנתיב ציבורי (המידלוור מוותר על סשן ב-/api/):
//   · מפתח משותף בכותרת, בהשוואה בזמן קבוע.
//   · רשימת היתר לנתיבים. היעד קבוע בקוד ואינו נלקח מהבקשה, כך שאין
//     כאן ממסר כללי שאפשר להפנות לכל שרת.
import { timingSafeEqual } from "../_lib/auth.js";

const UPSTREAM = "https://www.govmap.gov.il/api";

const ALLOWED = [
  /^\/real-estate\/deals\/[\d.,-]+\/\d+$/,
  /^\/real-estate\/neighborhood-deals\/[\w-]+$/,
  /^\/search-service\/autocomplete$/,
];

const HEADERS = {
  Accept: "application/json",
  Referer: "https://www.govmap.gov.il/",
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/127.0 Safari/537.36",
};

function deny(status, msg) {
  return new Response(JSON.stringify({ error: msg }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export async function onRequest(context) {
  const { request, env } = context;
  const key = env.SCAN_KEY;
  if (!key) return deny(503, "SCAN_KEY לא מוגדר");
  if (!timingSafeEqual(request.headers.get("x-scan-key") || "", key))
    return deny(401, "מפתח שגוי");

  const url = new URL(request.url);
  const path = url.searchParams.get("path") || "";
  if (!ALLOWED.some((re) => re.test(path))) return deny(400, "נתיב לא מורשה");

  // ה-query מועבר כמות שהוא חוץ מ-path עצמו, שהוא פרמטר הניתוב שלנו.
  const qs = new URLSearchParams(url.searchParams);
  qs.delete("path");
  const target = `${UPSTREAM}${path}${qs.toString() ? `?${qs}` : ""}`;

  const init = { method: request.method, headers: { ...HEADERS } };
  if (request.method === "POST") {
    init.body = await request.text();
    init.headers["Content-Type"] = "application/json";
  }

  const r = await fetch(target, init);
  return new Response(r.body, {
    status: r.status,
    headers: { "content-type": r.headers.get("content-type") || "application/json" },
  });
}
