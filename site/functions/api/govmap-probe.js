// בדיקה אם Cloudflare מצליח להגיע ל-Govmap, אחרי ש-GitHub Actions לא.
//
// הראנרים של GitHub יוצאים מ-Azure, ו-Govmap מחזיר להם 403 על **כל**
// בקשה — כולל דף הבית, וגם ב-requests רגיל בלי חיקוי TLS. זו חסימה לפי
// טווח כתובות, ולכן השאלה היחידה שנותרה היא מאיזו רשת כן אפשר לסרוק.
//
// אין כאן פרוקסי כללי: הכתובת קבועה בקוד ואינה נלקחת מהבקשה, כדי שלא
// ייווצר ממסר פתוח בנתיב ציבורי.
const TARGET =
  "https://www.govmap.gov.il/api/real-estate/deals/3874000,3671000/1000";

export async function onRequestGet() {
  const out = { target: TARGET };
  try {
    const r = await fetch(TARGET, {
      headers: {
        Accept: "application/json",
        Referer: "https://www.govmap.gov.il/",
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
          "(KHTML, like Gecko) Chrome/127.0 Safari/537.36",
      },
    });
    out.status = r.status;
    const body = await r.text();
    out.length = body.length;
    out.snippet = body.slice(0, 160);
  } catch (e) {
    out.error = String(e);
  }
  return new Response(JSON.stringify(out, null, 2), {
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}
