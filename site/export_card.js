/* ייצוא תמונות — עמוד העסקאות מחוץ לבורסה, ומ-22/09/2026 גם עמודי הסחורות
 * והרכב (site/share.py, גושי lines ו-dbars).
 *
 * מוטמע בעמוד ע"י otc.export_js(). קובץ JS נפרד ולא מחרוזת בתוך Python: כך
 * אפשר לבדוק אותו ב-node --check ישירות, ובריחת לוכסנים אינה נאכלת בדרך.
 *
 * **כרטיס אחד, כמה סוגי גוש.** כל ייצוא בעמוד — טבלת יום/חודש/שנה, תמונת
 * המצב, בעלי העניין, השיעור המצטבר לפי חברה, ודיווחי מאיה ליום או לחודש —
 * הוא אותו כרטיס: כותרת, ואחריה רצף גושים (stats, notes, table, bars,
 * columns, reports), ובסוף מקור וקרדיט. כל גוש הוא פונקציה אחת שרצה פעמיים:
 * פעם למדידת הגובה ופעם לציור, כך שהמדידה והציור אינם יכולים להיפרד.
 *
 * **הטבלה בתמונה היא הטבלה שבעמוד, במלואה.** אותן שורות, אותן עמודות, שורת
 * "ועוד" ושורת הסך — מאותו מטען שממנו נבנה ה-HTML. רוחבי העמודות נמדדים
 * בגופן האמיתי; הקנבס מתרחב עד 1680 לפני שנשברת שורה, ומעבר לכך עמודות
 * הטקסט נשברות. **שום תא אינו מקוצר.**
 *
 * **הגופנים של האתר.** פרנק־ריהל לכותרות, Assistant לטקסט ו-IBM Plex Mono
 * למספרים — נטענים במפורש לפני הציור, כי קנבס אינו מחכה לגופן ומצייר
 * בגופן החלופי בשקט. הטעינה מוגבלת ל-2.5 שניות; אחריהן מציירים בכל מקרה.
 *
 * **הקרדיט נכתב בכיוון LTR.** בכיוון RTL המנוע מסדר מחדש את "©" ואת ה-"@"
 * סביב הטקסט הלטיני.
 *
 * **עיצוב אינפוגרפיקה (13/10/2026).** כרזה כחולה-כהה עם קו רקיע בראש הכרטיס;
 * אריחי סיכום לבנים עם סמל בעיגול צבעוני, שעולים על תחתית הכרזה; עיקרים
 * שבהם המספרים מודגשים; וכל גוש אחר בכרטיס לבן משלו — טבלה עם שורת כותרת
 * ושורת סך כהות, שורות מתחלפות, ופס יחסי בעמודת אחוזים. הסימן בכרזה הוא של
 * TLV TASE View ולא סמל הבורסה: התמונה מופצת ברשתות, וסמל הבורסה היה מציג
 * אותה כפרסום רשמי שלה.
 */
(function () {
  "use strict";

  var W0 = 1200, WMAX = 1680, PAD = 56, GAP = 32, FOOT_GAP = 24;
  var C = {
    page: "#edf1f7", page2: "#e2e8f1",
    navy: "#0b2545", navy2: "#15396a",
    card: "#ffffff", edge: "rgba(16,38,72,0.08)", zebra: "#f5f8fc", track: "#e8eef6",
    ink: "#13243b", muted: "#55667c", faint: "#8493a6",
    hair: "#e6ebf2", line: "#d2dbe7",
    accent: "#1f5fc4", accent2: "#5b93e6", soft: "#e5edfb", pale: "#c3d4ef",
    up: "#12804d", down: "#c4392f", warn: "#a86f0c",
    upBg: "#e1f3e9", downBg: "#fbe6e3", warnBg: "#fbefd6",
    onNavy: "#ffffff", onNavy2: "#c5d4ea", onNavy3: "#8ea6c6", brand: "#a3c5ff",
    upOn: "#8fe3b5", downOn: "#ffab9f"
  };
  var SERIF = "'Frank Ruhl Libre', 'David Libre', Georgia, serif";
  var SANS = "Assistant, 'Segoe UI', Arial, sans-serif";
  var MONO = "'IBM Plex Mono', Consolas, Assistant, monospace";
  var SRC_TASE = "מקור: סקירת העסקאות מחוץ לבורסה של הבורסה לניירות ערך בתל אביב";
  var SRC_MAYA = "מקור: דיווחי בעלי עניין במערכת מאיה של הבורסה לניירות ערך";
  var MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט",
    "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"];
  var WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
  var MONTH_TOP = 25;

  function F(w, s, fam) { return w + " " + s + "px " + (fam || SANS); }
  function sum(a) { return a.reduce(function (s, v) { return s + v; }, 0); }

  // **סדרות קטגוריאליות — פלטה מאומתת, בסדר קבוע.** כחול, כתום, טורקיז, צהוב:
  // עברו בדיקת בהירות, כרומה והפרדה לעיוורון צבעים (scripts של dataviz, על לבן).
  // הצבע שייך לסדרה ולא לדירוג שלה — "מחוץ לבורסה" כחולה בכל כרטיס.
  var CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];
  var SPARK = "#7d8ea3";          // קו מגמה: גוון מושתק; הנקודה האחרונה בכחול

  function hexA(hex, a) {
    var n = parseInt(String(hex).slice(1), 16);
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
  }

  // מספר מתוך טקסט של תא: "22.8 מ׳ ₪", "631 א׳ ₪", "1.02 מיליארד ₪", "+2.59%",
  // "12,704". null כשאין מספר ("—"). היחידה הופכת לסדר גודל, כדי שפס יחסי
  // ישווה בין "631 א׳" ל-"22.8 מ׳" נכון.
  var MULT = [[/מיליארד/, 1e9], [/מ׳|מ'|מיליון/, 1e6], [/א׳|א'|אלף/, 1e3]];
  function parseNum(t) {
    if (typeof t === "number") { return isFinite(t) ? t : null; }
    var s = String(t == null ? "" : t).replace(/,/g, "").replace(/−/g, "-");
    var m = /([+\-]?\d+(?:\.\d+)?)/.exec(s);
    if (!m) { return null; }
    var v = parseFloat(m[1]);
    for (var i = 0; i < MULT.length; i++) {
      if (MULT[i][0].test(s)) { v *= MULT[i][1]; break; }
    }
    return v;
  }

  // פס: ריבוע בקו הבסיס, ופינות מעוגלות רק בקצה הנתון (dataviz: קצה 4px).
  // side — באיזה צד הקצה: "left" (פס שגדל משמאל לבסיס בימין) או "right".
  function barPath(x, l, t, w, h, r, side) {
    r = Math.max(0, Math.min(r, w, h / 2));
    x.beginPath();
    if (side === "right") {
      x.moveTo(l, t); x.lineTo(l + w - r, t); x.arcTo(l + w, t, l + w, t + r, r);
      x.lineTo(l + w, t + h - r); x.arcTo(l + w, t + h, l + w - r, t + h, r); x.lineTo(l, t + h);
    } else if (side === "top") {
      x.moveTo(l, t + h); x.lineTo(l, t + r); x.arcTo(l, t, l + r, t, r);
      x.lineTo(l + w - r, t); x.arcTo(l + w, t, l + w, t + r, r); x.lineTo(l + w, t + h);
    } else {
      x.moveTo(l + w, t); x.lineTo(l + r, t); x.arcTo(l, t, l, t + r, r);
      x.lineTo(l, t + h - r); x.arcTo(l, t + h, l + r, t + h, r); x.lineTo(l + w, t + h);
    }
    x.closePath();
  }

  // קו מגמה קטן: קו 2px בגוון מושתק, שטיפה עדינה מתחתיו, ונקודת סיום כחולה
  // עם טבעת לבנה — הערך האחרון הוא הדגש, השאר הקשר.
  function sparkline(x, vals, l, t, w, h) {
    var pts = (vals || []).filter(function (v) { return typeof v === "number" && isFinite(v); });
    if (pts.length < 2) { return; }
    var lo = Math.min.apply(null, pts), hi = Math.max.apply(null, pts);
    // **טווח מינימלי של 4% מהרמה.** בלעדיו קו נמתח מקצה לקצה: DAP שנע בין 800
    // ל-802.5 (0.3%) צויר כצניחה ועלייה חדות. כך תזוזה זעירה נשארת זעירה.
    var mid = (lo + hi) / 2, floor = Math.abs(mid) * 0.04;
    if (hi - lo < floor) { lo = mid - floor / 2; hi = mid + floor / 2; }
    var span = (hi - lo) || 1;
    function X(i) { return l + w * i / (pts.length - 1); }
    function Y(v) { return t + h - 4 - (v - lo) / span * (h - 8); }
    x.beginPath();
    pts.forEach(function (v, i) { if (i) { x.lineTo(X(i), Y(v)); } else { x.moveTo(X(i), Y(v)); } });
    x.lineTo(X(pts.length - 1), t + h); x.lineTo(X(0), t + h); x.closePath();
    x.fillStyle = hexA(SPARK, 0.1); x.fill();
    x.beginPath();
    pts.forEach(function (v, i) { if (i) { x.lineTo(X(i), Y(v)); } else { x.moveTo(X(i), Y(v)); } });
    x.strokeStyle = SPARK; x.lineWidth = 2; x.lineJoin = "round"; x.lineCap = "round"; x.stroke();
    var ex = X(pts.length - 1), ey = Y(pts[pts.length - 1]);
    x.fillStyle = C.card; x.beginPath(); x.arc(ex, ey, 6, 0, Math.PI * 2); x.fill();
    x.fillStyle = CAT[0]; x.beginPath(); x.arc(ex, ey, 4, 0, Math.PI * 2); x.fill();
  }

  // מקרא: נקודה צבעונית ושם לכל סדרה, מימין לשמאל. מחזיר את הגובה.
  function legendRow(x, names, right, y, draw) {
    if (!names || !names.length) { return 0; }
    if (draw) {
      x.direction = "rtl"; x.textAlign = "right"; x.font = F(600, 16);
      var cx = right;
      names.forEach(function (n, i) {
        x.fillStyle = CAT[i % CAT.length];
        rr(x, cx - 14, y + 9, 14, 14, 4); x.fill();
        x.fillStyle = C.muted; x.fillText(n, cx - 22, y + 21);
        cx -= 22 + x.measureText(n).width + 26;
      });
    }
    return 36;
  }

  // ---------------------------------------------------------------- גופנים

  var fontsP = null;
  function fontsReady() {
    if (fontsP) { return fontsP; }
    if (!document.fonts || !document.fonts.load) {
      fontsP = Promise.resolve();
      return fontsP;
    }
    // הטקסט לדוגמה קובע איזו תת-קבוצה של הגופן נטענת. בלי אותיות עבריות
    // Google Fonts טוען רק את הלטינית, והעברית נופלת לגופן המערכת — ובלי
    // ספרות, מספר מודגש בתוך משפט נופל לגופן אחר מהמשפט שסביבו.
    var he = "אבגדהוזחטיכלמנסעפצקרשת", num = "0123456789.,%+-₪", lat = "TLV TASE View";
    var want = [[F(900, 20, SERIF), lat], [F(700, 20, SERIF), he + num],
      [F(400, 20), he + num + lat], [F(500, 20), he + num], [F(600, 20), he + num],
      [F(700, 20), he + num + lat], [F(500, 20, MONO), num + lat], [F(600, 20, MONO), num]];
    var all = Promise.all(want.map(function (w) {
      return document.fonts.load(w[0], w[1]).catch(function () { return null; });
    }));
    fontsP = Promise.race([all, new Promise(function (r) { setTimeout(r, 2500); })]);
    return fontsP;
  }

  // ---------------------------------------------------------------- עזרים

  function rr(x, l, t, w, h, r) {
    r = Math.max(0, Math.min(r, w / 2, h / 2));
    x.beginPath();
    x.moveTo(l + r, t);
    x.arcTo(l + w, t, l + w, t + h, r);
    x.arcTo(l + w, t + h, l, t + h, r);
    x.arcTo(l, t + h, l, t, r);
    x.arcTo(l, t, l + w, t, r);
    x.closePath();
  }

  // כרטיס לבן עם צל רך. הצל אינו מושפע מ-scale של הקנבס, ולכן מוכפל בקנה
  // המידה של הציור — אחרת בתמונה ברזולוציה כפולה הוא יוצא בחצי גודל.
  var SC = 1;
  function card(x, l, t, w, h, r) {
    x.save();
    x.shadowColor = "rgba(15,36,68,0.11)";
    x.shadowBlur = 26 * SC; x.shadowOffsetY = 8 * SC;
    x.fillStyle = C.card; rr(x, l, t, w, h, r); x.fill();
    x.restore();
    x.strokeStyle = C.edge; x.lineWidth = 1;
    rr(x, l + 0.5, t + 0.5, w - 1, h - 1, r); x.stroke();
  }

  // **שבירת שורות, לא קיצור.** טקסט שרחב מהמקום נשבר לפי מילים; מילה בודדת
  // שרחבה מהמקום נשברת לפי תווים. בשום מקרה לא נזרק תו.
  function wrap(x, text, max) {
    var words = String(text == null ? "" : text).split(" "), lines = [], cur = "";
    words.forEach(function (w) {
      var t = cur ? cur + " " + w : w;
      if (!cur || x.measureText(t).width <= max) {
        cur = t;
      } else {
        lines.push(cur);
        cur = w;
      }
      while (cur.length > 1 && x.measureText(cur).width > max) {
        var k = cur.length - 1;
        while (k > 1 && x.measureText(cur.slice(0, k)).width > max) { k--; }
        lines.push(cur.slice(0, k));
        cur = cur.slice(k);
      }
    });
    lines.push(cur);
    return lines;
  }

  // מספר חתום בתוך משפט עברי: בלי בידוד המינוס נודד לצד השני של המספר
  // ("0.35%-"). LRI…PDI מבודדים את המספר כריצה משמאל לימין.
  function isolateSigned(t) {
    return String(t).replace(/(^|[\s(])([+\-−][\d.,]+%?)/g, function (m, p, n) {
      return p + "\u2066" + n + "\u2069";
    });
  }

  // "ל-6.9%" ו"ב-104.67" בתוך משפט עברי: המקף אחרי אות השימוש ניטרלי, ובקנבס
  // המספר עלול לנדוד לצד השני שלו. מקף עברי (U+05BE) הוא תו עברי לכל דבר,
  // והמספר אחריו נשאר ריצה אחת משמאל לימין. בטקסט של הסקירות זה המקרה הנפוץ.
  function hebPrefix(t) {
    return String(t).replace(/([א-ת])-(?=\d)/g, "$1־");
  }

  // כל טקסט עברי חופשי שנכנס לכרטיס — כותרת, תת-כותרת, הערות ותאי טבלה —
  // עובר כאן. נבדק בהשוואת פיקסלים על הקנבס (22/09/2026): בלי הבידוד, "(יום
  // -0.8%" מצויר עם המינוס מימין למספר; איתו — משמאל, כמו שנכתב.
  function bidi(t) { return isolateSigned(hebPrefix(t)); }

  function measureMax(x, font, texts) {
    x.font = font;
    return texts.reduce(function (m, t) { return Math.max(m, x.measureText(String(t)).width); }, 0);
  }

  // **מספר ויחידה בשני גופנים, ביחידה משמאל למספר.** "326.8 מ׳ ₪" שצויר כולו
  // בגופן המספרים יצא עם האותיות העבריות בגופן מכונת כתיבה (לגופן המספרים אין
  // עברית), ובכיוון LTR — היחידה מימין למספר, כך שבקריאה מימין היא באה לפניו.
  // כאן המספר מיושר לימין העמודה בגופן המספרים, והיחידה אחריו בקריאה, בגופן
  // הטקסט ובגודל קטן יותר.
  var NUM_RE = /^([+\-−]?\d[\d.,]*%?)\s+(\S.*)$/;
  function numParts(v) {
    var m = NUM_RE.exec(String(v == null ? "" : v));
    return m ? { n: m[1], u: m[2] } : null;
  }
  function unitFont(o) { return F(o.uw || 600, Math.round(o.s * (o.us || 0.78))); }
  function valWidth(x, v, o) {
    var p = numParts(v);
    x.font = F(o.w, o.s, o.fam || MONO);
    if (!p) { return x.measureText(String(v == null ? "" : v)).width; }
    var nw = x.measureText(p.n).width;
    x.font = unitFont(o);
    return nw + Math.round(o.s * 0.3) + x.measureText(p.u).width;
  }
  function drawVal(x, v, right, y, o) {
    var p = numParts(v), t = String(v == null ? "" : v);
    x.direction = "ltr"; x.textAlign = "right";
    x.font = F(o.w, o.s, o.fam || MONO); x.fillStyle = o.color;
    if (!p) { x.fillText(t, right, y); return; }
    x.fillText(p.n, right, y);
    var nw = x.measureText(p.n).width;
    x.direction = "rtl"; x.textAlign = "right";
    x.font = unitFont(o); x.fillStyle = o.ucolor || o.color;
    x.fillText(p.u, right - nw - Math.round(o.s * 0.3), y);
  }

  function signColor(v, dflt) {
    var c = String(v).charAt(0);
    if (c === "-" || c === "−") { return C.down; }
    if (c === "+") { return C.up; }
    return dflt;
  }

  // ---------------------------------------------------------------- טקסט מעורב

  // **מספר מודגש בתוך משפט עברי.** המשפט מצויר בקטעים — רצף מילים רגילות
  // כקטע אחד, ומספר (עם יחידתו) כקטע מודגש — והקטעים מונחים מימין לשמאל.
  // קטע אחד שלם נשאר בידי הקנבס, כך שריצה לטינית בתוכו ("S&P 500") מסודרת
  // נכון. הדגשה רק כשהתו החזק שלפני המספר עברי: אחרי מילה לטינית המספר שייך
  // לריצה שלה, ופיצולו היה הופך את סדרן. תאריכים ושנים אינם מודגשים.
  var HE_CH = /[א-ת]/, LA_CH = /[A-Za-z]/;
  var NUM_TOK = /^([("'«[]*(?:[א-ת]{1,3}־)?)(\u2066?[+\-−]?[₪$€]?\d(?:[\d.,]*\d)?%?\u2069?)([)"'».,;:!?\]]*)$/;
  var NOT_NUM = /^((19|20)\d\d|\d{1,2}\.\d{1,2}\.\d{2,4})$/;
  var UNIT_TOK = /^(מ׳|מ'|מיליון|מיליארד|אלף|א׳|א'|₪|ש"ח|דולר|אירו|נקודות|טון)([)"'».,;:!?\]]*)$/;
  // "15 באוקטובר" הוא תאריך ולא כמות — מספר שלם קצר לפני שם חודש אינו מודגש.
  var MONTH_TOK = /^[בלמו]?(ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)/;

  function lastStrong(w, prev) {
    for (var i = w.length - 1; i >= 0; i--) {
      var ch = w.charAt(i);
      if (HE_CH.test(ch)) { return "R"; }
      if (LA_CH.test(ch)) { return "L"; }
    }
    return prev;
  }

  // קטעים: {t טקסט, st סגנון ("" רגיל, hi מודגש), sp רווח לפניו, nb רווח שאין
  // לשבור בו — בין מספר ליחידה שלו}.
  function hiPieces(text) {
    var out = [], strong = "R", carry = false;
    bidi(text).split(/ +/).forEach(function (w, i, ws) {
      if (!w) { return; }
      var sp = out.length > 0, u;
      var m = NUM_TOK.exec(w);
      // יום בחודש ("15 באוקטובר") — אבל לא "ל־22.0% בספטמבר" ולא "9,979 באוגוסט".
      if (m && /^\d{1,2}$/.test(m[2]) && MONTH_TOK.test(ws[i + 1] || "")) { m = null; }
      // אות שימוש עברית ("ו־1,024") היא התו החזק שלפני המספר גם אחרי מילה לטינית.
      if (m && strong !== "R" && !HE_CH.test(m[1])) { m = null; }
      if (m && !NOT_NUM.test(m[2].replace(/[\u2066-\u2069]/g, ""))) {
        if (m[1]) { out.push({ t: m[1], st: "", sp: sp }); sp = false; }
        out.push({ t: m[2], st: "hi", sp: sp });
        if (m[3]) { out.push({ t: m[3], st: "", sp: false }); }
        carry = !m[3];
      } else if (carry && (u = UNIT_TOK.exec(w))) {
        out.push({ t: u[1], st: "hi", sp: sp, nb: true });
        if (u[2]) { out.push({ t: u[2], st: "", sp: false }); }
        carry = !u[2];
      } else {
        out.push({ t: w, st: "", sp: sp });
        carry = false;
      }
      strong = lastStrong(w, strong);
    });
    return out;
  }

  // שורת הקשר באריח: "יום ▲1.1% · חודש ▼0.4%" — החצים בצבע הכיוון. חץ אינו
  // נשבר מהמילה שלפניו ויחידה אינה נשברת מהמספר: "שנה" בסוף שורה ו-"▲67%"
  // בתחילת הבאה נקראו כשני דברים נפרדים.
  function capPieces(text) {
    var out = [], strong = "R", num = false;
    bidi(text).split(/ +/).forEach(function (w) {
      if (!w) { return; }
      var c = w.charAt(0), arrow = c === "▲" || c === "▼", unit = num && UNIT_TOK.test(w);
      out.push({ t: w, st: strong === "R" && arrow ? (c === "▲" ? "up" : "down") : "",
        sp: out.length > 0, nb: arrow || unit });
      num = NUM_TOK.test(w) || unit;
      strong = lastStrong(w, strong);
    });
    return out;
  }

  // שבירה לשורות לפי מילים, כל קטע נמדד בגופן שלו. קטעים בלי רווח ביניהם
  // ("(" ו-"12.1%" ו-")") הם מילה אחת, וכך גם קטע שמסומן nb עם הקטע שלפניו.
  function richWrap(x, pieces, max, fonts) {
    x.font = fonts[""];
    var spW = x.measureText(" ").width, words = [], lines = [], cur = [], curW = 0;
    pieces.forEach(function (p) {
      x.font = fonts[p.st] || fonts[""];
      var q = { t: p.t, st: p.st, w: x.measureText(p.t).width, sp: p.sp };
      if ((p.sp && !p.nb) || !words.length) {
        words.push({ ps: [q], w: q.w });
      } else {
        var lw = words[words.length - 1];
        lw.ps.push(q);
        lw.w += q.w + (p.sp ? spW : 0);
      }
    });
    words.forEach(function (wd) {
      if (cur.length && curW + spW + wd.w > max) {
        lines.push(cur);
        cur = []; curW = 0;
      }
      curW += (cur.length ? spW : 0) + wd.w;
      wd.ps.forEach(function (q, k) {
        cur.push({ t: q.t, st: q.st, sp: k === 0 ? cur.length > 0 : q.sp });
      });
    });
    if (cur.length) { lines.push(cur); }
    return lines;
  }

  function richDraw(x, line, right, y, fonts, colors) {
    var segs = [];
    line.forEach(function (p) {
      var s = segs[segs.length - 1];
      if (s && s.st === p.st) {
        s.t += (p.sp ? " " : "") + p.t;
      } else {
        segs.push({ t: p.t, st: p.st, sp: p.sp });
      }
    });
    x.font = fonts[""];
    var spW = x.measureText(" ").width, cx = right;
    x.direction = "rtl"; x.textAlign = "right";
    segs.forEach(function (s) {
      if (s.sp) { cx -= spW; }
      x.font = fonts[s.st] || fonts[""];
      x.fillStyle = colors[s.st] || colors[""];
      x.fillText(s.t, cx, y);
      cx -= x.measureText(s.t).width;
    });
  }

  // ---------------------------------------------------------------- סמלים

  // סמל קטן בקווים, סביב (cx, cy), בגודל בסיס של כ-22 פיקסלים כפול k.
  function icon(x, kind, cx, cy, fg, bg, k) {
    x.save();
    x.translate(cx, cy);
    x.scale(k || 1, k || 1);
    x.strokeStyle = fg; x.fillStyle = fg;
    x.lineWidth = 2.2; x.lineCap = "round"; x.lineJoin = "round";
    function path(pts, close) {
      x.beginPath();
      pts.forEach(function (p, i) { if (i) { x.lineTo(p[0], p[1]); } else { x.moveTo(p[0], p[1]); } });
      if (close) { x.closePath(); }
      x.stroke();
    }
    function ring(dx, dy, r, fill) {
      x.beginPath(); x.arc(dx, dy, r, 0, Math.PI * 2);
      if (fill) { x.fill(); } else { x.stroke(); }
    }
    var i;
    switch (kind) {
      case "coins":
        [7, 1, -5].forEach(function (dy) {
          x.beginPath(); x.ellipse(0, dy, 10, 3.8, 0, 0, Math.PI * 2);
          x.fillStyle = bg; x.fill(); x.stroke();
        });
        break;
      case "doc":
        path([[-7, -10], [3, -10], [8, -5], [8, 10], [-7, 10]], true);
        path([[3, -10], [3, -5], [8, -5]]);
        path([[-3, 0], [4, 0]]); path([[-3, 5], [4, 5]]);
        break;
      case "link":
        ring(-4.5, 0, 6.5); ring(4.5, 0, 6.5);
        break;
      case "swap":
        path([[-9, -4], [8, -4]]); path([[4, -8], [8, -4], [4, 0]]);
        path([[9, 5], [-8, 5]]); path([[-4, 1], [-8, 5], [-4, 9]]);
        break;
      case "users":
        ring(-3, -5, 4);
        x.beginPath(); x.arc(-3, 10, 7.5, Math.PI, Math.PI * 2); x.stroke();
        ring(7, -3, 3);
        x.beginPath(); x.arc(7, 9, 5.5, Math.PI * 1.15, Math.PI * 2); x.stroke();
        break;
      case "building":
        x.strokeRect(-7, -10, 14, 20);
        for (i = 0; i < 6; i++) { x.fillRect(-4 + (i % 2) * 5, -7 + Math.floor(i / 2) * 5, 2.6, 2.6); }
        break;
      case "pie":
        ring(0, 0, 9.5);
        x.beginPath(); x.moveTo(0, 0); x.arc(0, 0, 9.5, -Math.PI / 2, 0); x.closePath(); x.fill();
        break;
      case "car":
        rr(x, -11, -1, 22, 8, 3); x.stroke();
        path([[-6, -1], [-3, -7], [4, -7], [7, -1]]);
        ring(-6, 8, 2.6, true); ring(6, 8, 2.6, true);
        break;
      case "bolt":
        x.beginPath(); x.moveTo(2, -11); x.lineTo(-6, 1); x.lineTo(0, 1);
        x.lineTo(-2, 11); x.lineTo(6, -1); x.lineTo(0, -1); x.closePath(); x.fill();
        break;
      case "drop":
        x.beginPath(); x.moveTo(0, -11);
        x.bezierCurveTo(3, -5, 8, -1, 8, 3);
        x.arc(0, 3, 8, 0, Math.PI);
        x.bezierCurveTo(-8, -1, -3, -5, 0, -11);
        x.fill();
        break;
      case "ingot":
        path([[-11, 9], [-1, 9], [-3, 3], [-9, 3]], true);
        path([[1, 9], [11, 9], [9, 3], [3, 3]], true);
        path([[-5, 0], [5, 0], [3, -6], [-3, -6]], true);
        break;
      case "leaf":
        x.beginPath(); x.moveTo(-8, 8);
        x.bezierCurveTo(-9, -4, -1, -10, 9, -9);
        x.bezierCurveTo(9, 1, 3, 9, -8, 8); x.stroke();
        path([[-8, 8], [2, -2]]);
        break;
      case "hex":
        x.beginPath();
        for (i = 0; i < 6; i++) {
          var an = Math.PI / 6 + i * Math.PI / 3;
          if (i) { x.lineTo(9.5 * Math.cos(an), 9.5 * Math.sin(an)); } else { x.moveTo(9.5 * Math.cos(an), 9.5 * Math.sin(an)); }
        }
        x.closePath(); x.stroke(); ring(0, 0, 2.6, true);
        break;
      case "ship":
        path([[-11, 3], [11, 3], [8, 9], [-8, 9]], true);
        x.strokeRect(-7, -4, 6, 7); x.strokeRect(1, -4, 6, 7);
        break;
      case "calendar":
        rr(x, -9, -8, 18, 17, 3); x.stroke();
        path([[-9, -3], [9, -3]]); path([[-4.5, -11], [-4.5, -6]]); path([[4.5, -11], [4.5, -6]]);
        for (i = 0; i < 6; i++) { x.fillRect(-6.2 + (i % 3) * 5, 0.5 + Math.floor(i / 3) * 4.5, 2.4, 2.4); }
        break;
      case "list":
        for (i = 0; i < 3; i++) { ring(-7, -6 + i * 6, 1.7, true); path([[-2.5, -6 + i * 6], [8, -6 + i * 6]]); }
        break;
      case "layers":
        x.beginPath(); x.moveTo(0, -11); x.lineTo(10, -6); x.lineTo(0, -1); x.lineTo(-10, -6); x.closePath();
        x.fillStyle = bg; x.fill(); x.stroke();
        path([[-10, -1], [0, 4], [10, -1]]); path([[-10, 4], [0, 9], [10, 4]]);
        break;
      case "globe":
        ring(0, 0, 9.5);
        x.beginPath(); x.ellipse(0, 0, 4.2, 9.5, 0, 0, Math.PI * 2); x.stroke();
        path([[-9.5, 0], [9.5, 0]]);
        break;
      default:
        rr(x, -9.5, 1, 5, 8, 1.5); x.fill();
        rr(x, -2.5, -4, 5, 13, 1.5); x.fill();
        rr(x, 4.5, -9, 5, 18, 1.5); x.fill();
    }
    x.restore();
  }

  // הסמל לפי התווית. הסדר קובע: "מתחילת החודש" הוא לוח שנה, "מתחילת 2026" גרף.
  var ICONS = [[/מתואמ/, "link"], [/מחוץ לבורסה|עסקאות|עסקה/, "swap"], [/דיווח/, "doc"],
    [/מדווח|בעלי עניין|מחזיק/, "users"], [/ניירות|נייר/, "layers"],
    [/חבר(ות|ה)|יבואנ|מותג|יצרנ/, "building"], [/מההון|שיעור|נתח|אחוז/, "pie"],
    [/חשמל|אנרגי|סולאר/, "bolt"], [/תוצרת|יבוא|ארץ/, "globe"], [/יצאו|יציא/, "swap"],
    [/רכב|ליסינג|מסיר|נרשמ|מכונית|רישוי/, "car"], [/נפט|ברנט|דלק|גז|סולר|בנזין|WTI/, "drop"],
    [/אלומיניום|נחושת|פלדה|ניקל|ברזל|מתכ|אבץ|בדיל|HRC|LME/, "ingot"],
    [/חיטה|תירס|סוכר|קפה|סויה|אשלג|דשן|קקאו|חלב|אורז/, "leaf"],
    [/פולי|PVC|פלסטי|פולימר/, "hex"], [/מכול|הובל|שילוח|SCFI|ספנ|BDI/, "ship"],
    [/היקף|סה"כ|סה״כ|סכום|מחזור|שווי|תמורה|^היום|^יום/, "coins"],
    [/חודש/, "calendar"], [/מתחילת|שנה|מאז|שבוע/, "chart"]];
  function iconFor(label) {
    for (var i = 0; i < ICONS.length; i++) {
      if (ICONS[i][0].test(label)) { return ICONS[i][1]; }
    }
    return "chart";
  }
  var TINTS = [["#e3ecfb", "#1f5fc4"], ["#dff2e8", "#12804d"], ["#fcefd8", "#b3700b"],
    ["#ebe5fa", "#6145c2"], ["#dbf0f2", "#117c86"], ["#fae3e8", "#b8334f"]];

  // כותרת גוש: סימן קטן, תווית, וקו דק עד הקצה השני.
  var SECTION_H = 50;
  function section(x, title, g, y) {
    var t = bidi(title);
    x.fillStyle = C.accent; rr(x, g.right - 5, y + 8, 5, 22, 2.5); x.fill();
    x.direction = "rtl"; x.textAlign = "right";
    x.font = F(700, 21); x.fillStyle = C.ink;
    x.fillText(t, g.right - 15, y + 26);
    var w = x.measureText(t).width;
    x.fillStyle = C.line;
    x.fillRect(g.left, y + 19, Math.max(0, g.inner - w - 15 - 20), 1);
  }

  // ---------------------------------------------------------------- כרזה

  // קו רקיע מופשט בתחתית הכרזה, גבוה בשוליים ונמוך מתחת לכותרת. מחולל מזרע
  // קבוע: אותו נוף בכל ייצוא, לא רעש שמשתנה מתמונה לתמונה.
  function skyline(x, W, base) {
    var seed = 20261013;
    function rnd() { seed = (seed * 48271) % 2147483647; return seed / 2147483647; }
    [[0.06, 0.72, -46], [0.12, 1, -12]].forEach(function (L, li) {
      var px = L[2];
      while (px < W + 20) {
        var bw = 24 + rnd() * 44;
        var t = Math.min(1, Math.abs((px + bw / 2) / W - 0.5) * 2);
        var bh = (30 + 130 * Math.pow(t, 1.6)) * L[1] * (0.5 + rnd() * 0.5), top = base - bh;
        x.fillStyle = "rgba(146,186,244," + L[0] + ")";
        x.fillRect(px, top, bw - 4, bh);
        var r = rnd();
        if (r < 0.2 && bh > 50) {
          x.fillRect(px + (bw - 4) / 2 - 1.5, top - 16, 3, 16);
        } else if (r < 0.34) {
          x.beginPath(); x.moveTo(px, top); x.lineTo(px + bw - 4, top); x.lineTo(px, top - 14);
          x.closePath(); x.fill();
        }
        if (li && bh > 60) {
          x.fillStyle = "rgba(255,214,150,0.22)";
          for (var wy = top + 10; wy < base - 12; wy += 11) {
            for (var wx = px + 6; wx < px + bw - 12; wx += 8) {
              if (rnd() < 0.16) { x.fillRect(wx, wy, 3, 5); }
            }
          }
        }
        px += bw;
      }
    });
  }

  // סימן TLV TASE View: ריבוע מעוגל ובו שלוש עמודות עולות.
  function brandMark(x, right, top, s) {
    var gr = x.createLinearGradient(right - s, top, right, top + s);
    gr.addColorStop(0, "#3d84f2"); gr.addColorStop(1, "#1b4ea6");
    x.fillStyle = gr; rr(x, right - s, top, s, s, s * 0.27); x.fill();
    x.fillStyle = "#ffffff";
    var k = s / 48;
    [[0, 11], [1, 18], [2, 26]].forEach(function (p) {
      rr(x, right - 37 * k + p[0] * 9.5 * k, top + (37 - p[1]) * k, 6.5 * k, p[1] * k, 2 * k); x.fill();
    });
  }

  // הכרזה: סימן ושם בשורה העליונה, ובמרכז תווית, כותרת ותת-כותרת. כשהגוש
  // הראשון הוא אריחי סיכום, הכרזה ארוכה ב-OVER והאריחים עולים עליה.
  // מחזירה את ה-y שבו מתחיל הגוש הראשון.
  var OVER = 48;
  function header(x, d, g, draw, over) {
    var W = g.W, cw = Math.min(g.inner, 1000), ts = 54, lines;
    for (;;) {
      x.font = F(700, ts, SERIF);
      lines = wrap(x, bidi(d.title || ""), cw);
      if (lines.length === 1 || ts <= 36) { break; }
      ts -= 2;
    }
    var lh = Math.round(ts * 1.18);
    x.font = F(400, 21);
    var sub = d.sub ? wrap(x, bidi(d.sub), Math.min(cw, 860)) : [];
    var top = 30, kickY = top + 48 + 36, y = kickY;
    if (d.kicker) { y += 34 + 24; }
    var t0 = y + Math.round(ts * 0.9);
    y = t0 + (lines.length - 1) * lh;
    var s0 = y + 42;
    if (sub.length) { y = s0 + (sub.length - 1) * 31; }
    var bh = y + 66 + (over ? OVER : 0);
    if (draw) {
      var gr = x.createLinearGradient(W, 0, 0, bh);
      gr.addColorStop(0, C.navy); gr.addColorStop(1, C.navy2);
      x.fillStyle = gr; x.fillRect(0, 0, W, bh);
      var glow = x.createRadialGradient(W * 0.14, bh, 0, W * 0.14, bh, W * 0.55);
      glow.addColorStop(0, "rgba(86,150,240,0.30)"); glow.addColorStop(1, "rgba(86,150,240,0)");
      x.fillStyle = glow; x.fillRect(0, 0, W, bh);
      skyline(x, W, bh);

      brandMark(x, g.right, top, 48);
      x.direction = "ltr"; x.textAlign = "right";
      x.fillStyle = C.onNavy; x.font = F(900, 28, SERIF);
      x.fillText("TLV TASE View", g.right - 48 - 16, top + 34);
      x.textAlign = "left"; x.fillStyle = C.onNavy3; x.font = F(500, 15, MONO);
      x.fillText("tlvtaseview.com", g.left, top + 30);
      x.fillStyle = "rgba(255,255,255,0.12)"; x.fillRect(g.left, top + 48 + 16, g.inner, 1);

      x.direction = "rtl"; x.textAlign = "center";
      if (d.kicker) {
        x.font = F(700, 16);
        var kw = x.measureText(d.kicker).width + 40;
        x.fillStyle = "rgba(255,255,255,0.08)"; rr(x, W / 2 - kw / 2, kickY, kw, 34, 17); x.fill();
        x.strokeStyle = "rgba(163,197,255,0.38)"; x.lineWidth = 1;
        rr(x, W / 2 - kw / 2 + 0.5, kickY + 0.5, kw - 1, 33, 16.5); x.stroke();
        x.fillStyle = C.brand; x.fillText(d.kicker, W / 2, kickY + 23);
      }
      x.fillStyle = C.onNavy; x.font = F(700, ts, SERIF);
      lines.forEach(function (ln, k) { x.fillText(ln, W / 2, t0 + k * lh); });
      x.fillStyle = C.onNavy2; x.font = F(400, 21);
      sub.forEach(function (ln, k) { x.fillText(ln, W / 2, s0 + k * 31); });

      var al = x.createLinearGradient(0, 0, W, 0);
      al.addColorStop(0, "rgba(91,147,230,0)"); al.addColorStop(0.5, C.accent2);
      al.addColorStop(1, "rgba(91,147,230,0)");
      x.fillStyle = al; x.fillRect(0, bh - 3, W, 3);
    }
    return over ? bh - OVER : bh + 38;
  }

  // ---------------------------------------------------------------- גושים

  // אריחי סיכום: סמל בעיגול צבעוני ותווית, מספר, ושורת הקשר. עד ארבעה בשורה;
  // חמישה ומעלה — בשתי שורות, כי אריח צר מכווץ את המספר עד שאינו נקרא.
  function statsBlock(x, b, g, draw) {
    var items = b.items || [];
    if (!items.length) { return 0; }
    var n = items.length, per = n <= 4 ? n : Math.ceil(n / 2), rowsN = Math.ceil(n / per);
    var gap = 18, P = 24, IC = 52;
    var capF = { "": F(500, 15), up: F(700, 15), down: F(700, 15) };
    var lay = items.map(function (it, i) {
      var r = Math.floor(i / per), inRow = Math.min(per, n - r * per);
      var w = (g.inner - gap * (inRow - 1)) / inRow, tw = w - P * 2 - IC - 14, ls = 17;
      x.font = F(600, ls);
      while (ls > 14 && x.measureText(it.label || "").width > tw) { ls -= 1; x.font = F(600, ls); }
      // שורת הקשר יכולה להיות רשימה — כל פריט בשורה משלו ("מחוץ לבורסה X",
      // "מתואמות Y"), כמו באריח שבעמוד.
      var caps = (Array.isArray(it.cap) ? it.cap : [it.cap]).filter(function (c) { return c; });
      var hasSpark = (it.spark || []).filter(function (v) { return typeof v === "number"; }).length >= 5;
      return { r: r, c: i - r * per, w: w, ls: ls, lab: wrap(x, bidi(it.label || ""), tw),
        spark: hasSpark, chips: chipRows(x, it.deltas || [], w - P * 2),
        cap: [].concat.apply([], caps.map(function (c) {
          return richWrap(x, capPieces(c), w - P * 2, capF);
        })) };
    });
    var labL = Math.max.apply(null, lay.map(function (l) { return l.lab.length; }));
    var capL = Math.max.apply(null, lay.map(function (l) { return l.cap.length; }));
    var chipL = Math.max.apply(null, lay.map(function (l) { return l.chips.length; }));
    var head = Math.max(IC, labL * 22);
    var ch = P + head + 18 + 40 + (chipL ? 14 + chipL * 34 - 6 : 0) + (capL ? 12 + capL * 23 : 0) + P - 2;
    var h = rowsN * ch + (rowsN - 1) * gap;
    if (!draw) { return h; }
    items.forEach(function (it, i) {
      var L = lay[i], px = g.right - L.w - L.c * (L.w + gap), py = g.top + L.r * (ch + gap);
      var R = px + L.w - P, tint = TINTS[i % TINTS.length];
      card(x, px, py, L.w, ch, 18);
      var icx = R - IC / 2, icy = py + P + head / 2;
      x.fillStyle = tint[0]; x.beginPath(); x.arc(icx, icy, IC / 2, 0, Math.PI * 2); x.fill();
      icon(x, iconFor(it.label || ""), icx, icy, tint[1], tint[0], 1.15);
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.muted; x.font = F(600, L.ls);
      var ly = icy - (L.lab.length - 1) * 11 + 6;
      L.lab.forEach(function (ln, k) { x.fillText(ln, R - IC - 14, ly + k * 22); });
      // **המספר באותו גופן כמו הטקסט, בספרות פרופורציונליות** — גופן המספרים
      // רוחב קבוע שמור לעמודות שצריכות להתיישר; מספר גדול שעומד לבדו נראה בו מרווח.
      var v = String(it.value == null ? "—" : it.value), s = 40;
      var sw = L.spark ? Math.min(150, (L.w - P * 2) * 0.4) : 0;
      var room = L.w - P * 2 - (sw ? sw + 16 : 0);
      var o = { w: 700, s: s, us: 0.48, uw: 600, fam: SANS };
      while (s > 18 && valWidth(x, v, o) > room) { s -= 1; o.s = s; }
      o.color = it.tone === "up" ? C.up : it.tone === "down" ? C.down : C.ink;
      o.ucolor = it.tone ? o.color : C.muted;
      var vy = py + P + head + 18 + 34;
      drawVal(x, v, R, vy, o);
      if (L.spark) { sparkline(x, it.spark, px + P, vy - 38, sw, 44); }
      var cy = vy + 14;
      L.chips.forEach(function (row) { drawChips(x, row, R, cy); cy += 34; });
      if (L.chips.length) { cy += 4; }
      L.cap.forEach(function (ln, k) {
        richDraw(x, ln, R, cy + 20 + k * 23, capF, { "": C.faint, up: C.up, down: C.down });
      });
    });
    return h;
  }

  // שבבי שינוי: "יום +1.2%" — תווית מושתקת ומספר בצבע הכיוון על רקע בגוון שלו.
  // הסימן נכתב תמיד, כך שהכיוון אינו נישא בצבע לבדו.
  var CHIP_L = F(500, 14), CHIP_V = F(700, 15);
  function deltaChipW(x, d) {
    x.font = CHIP_L;
    var lw = d.label ? x.measureText(d.label).width + 6 : 0;
    x.font = CHIP_V;
    return lw + x.measureText(String(d.text)).width + 20;
  }
  function chipRows(x, ds, max) {
    var rows = [], cur = [], w = 0;
    (ds || []).filter(function (d) { return d && d.text != null && d.text !== ""; }).forEach(function (d) {
      var cw = deltaChipW(x, d);
      if (cur.length && w + 8 + cw > max) { rows.push(cur); cur = []; w = 0; }
      cur.push({ d: d, w: cw });
      w += (cur.length > 1 ? 8 : 0) + cw;
    });
    if (cur.length) { rows.push(cur); }
    return rows;
  }
  function drawChips(x, row, right, top) {
    var cx = right;
    row.forEach(function (c) {
      var v = parseNum(c.d.value != null ? c.d.value : c.d.text);
      var fg = v > 0 ? C.up : v < 0 ? C.down : C.muted;
      var bg = v > 0 ? C.upBg : v < 0 ? C.downBg : C.track;
      x.fillStyle = bg; rr(x, cx - c.w, top, c.w, 28, 8); x.fill();
      x.direction = "rtl"; x.textAlign = "right";
      var tx = cx - 10;
      if (c.d.label) {
        x.font = CHIP_L; x.fillStyle = C.muted; x.fillText(c.d.label, tx, top + 19);
        tx -= x.measureText(c.d.label).width + 6;
      }
      x.direction = "ltr"; x.font = CHIP_V; x.fillStyle = fg;
      x.fillText(String(c.d.text), tx, top + 19);
      cx -= c.w + 8;
    });
  }

  // עיקרי התקופה: משפטים מחושבים, כל אחד בנקודה משלו, והמספרים בהם מודגשים.
  function notesBlock(x, b, g, draw) {
    var items = (b.items || []).filter(function (t) { return t; });
    if (!items.length) { return 0; }
    var P = 30, PT = 26, LH = 33, BUL = 24;
    var fonts = { "": F(400, 20), hi: F(700, 20) };
    var paras = items.map(function (t) { return richWrap(x, hiPieces(t), g.inner - P * 2 - BUL, fonts); });
    var TH = b.title ? 56 : 0;
    var h = PT * 2 + TH + sum(paras.map(function (p) { return p.length * LH; })) +
      12 * (paras.length - 1) - 8;
    if (!draw) { return h; }
    card(x, g.left, g.top, g.inner, h, 18);
    var y = g.top + PT, R = g.right - P;
    if (b.title) {
      x.fillStyle = C.soft; x.beginPath(); x.arc(R - 17, y + 17, 17, 0, Math.PI * 2); x.fill();
      icon(x, "list", R - 17, y + 17, C.accent, C.soft, 0.8);
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.ink; x.font = F(700, 21);
      x.fillText(bidi(b.title), R - 34 - 12, y + 24);
      x.fillStyle = C.hair; x.fillRect(g.left + P, y + 44, g.inner - P * 2, 1);
      y += TH;
    }
    paras.forEach(function (lines) {
      x.fillStyle = C.accent; x.beginPath(); x.arc(R - 5, y + 15, 4, 0, Math.PI * 2); x.fill();
      lines.forEach(function (ln, k) {
        richDraw(x, ln, R - BUL, y + 22 + k * LH, fonts, { "": C.ink, hi: C.accent });
      });
      y += lines.length * LH + 12;
    });
    return h;
  }

  function cellFont(c, i, v, bold) {
    if (c[2] === "ltr") {
      return F(bold || /^[+\-−]/.test(v) || c[1] === "value" ? 600 : 500, 19, MONO);
    }
    if (i === 0) { return F(700, 20); }
    return F(bold ? 700 : 400, 19);
  }

  // שורת הסך יושבת על פס כהה, ולכן צבעיה בהירים.
  function cellVal(c, v, bold) {
    var signed = /^[+\-−]/.test(v);
    if (bold) {
      return { w: 600, s: 19, color: signed ? (v.charAt(0) === "+" ? C.upOn : C.downOn) : C.onNavy,
        ucolor: C.onNavy2 };
    }
    var color = signColor(v, c[1] === "value" ? C.ink : C.muted);
    return { w: (signed || c[1] === "value") ? 600 : 500, s: 19, color: color,
      ucolor: signed ? color : C.faint };
  }

  // כיוון השפעה, כמו השבב שבעמוד.
  var DIR_COLOR = { "חיובי": C.up, "שלילי": C.down, "מעורב": C.warn };

  function cellColor(c, i, v, bold) {
    if (bold) { return C.onNavy; }
    if (i === 0) { return C.ink; }
    if (DIR_COLOR[v]) { return DIR_COLOR[v]; }
    var s = signColor(v, null);
    if (s) { return s; }
    if (c[1] === "value") { return C.ink; }
    return C.muted;
  }

  // **עמודת אחוזים מקבלת פס יחסי בתוך התא.** רק כשכל ערכיה אחוז לא חתום
  // ("12.3%"): שינוי חתום כבר צבוע לפי הכיוון, ופס לצידו היה סותר את הצבע.
  // הפס יחסי לערך הגבוה בעמודה — הוא משווה בין השורות, לא מול 100%.
  // **עמודה עם צורה משלה.** מפרט עמודה הוא [כותרת, מפתח, כיוון, אפשרויות], והאפשרות
  // viz בוחרת את הצורה שמתאימה לתוכן — כי טבלה של מספרים בלבד מבקשת מהקורא
  // להשוות בראש את מה שפס משווה בעין:
  //   bar    — פס יחסי לגבוה בעמודה (היקף כספי, נתח)
  //   meter  — פס מול תקרה קבועה, max (אחוז מתוך שלם: ממחזור היום, החזקה)
  //   div    — פס סביב אפס, לפי הסימן (פרמיה מול שער הבסיס, שינוי נטו)
  //   chip   — שבב צבעוני מאחורי מספר חתום (שינוי ביום/חודש/שנה)
  //   stack  — פס מוערם מעמודות אחרות, parts (מחוץ לבורסה + מתואמות)
  //   spark  — קו מגמה מתוך מערך מספרים בשורה
  // swatch — ריבוע צבעוני בכותרת, שמזהה עמודה כחלק בפס מוערם.
  // בלי viz בכל הטבלה, עמודת אחוזים לא חתומים מקבלת פס כמו קודם.
  var BARW = 104, TX = 12, SPW = 112;
  var BARRED = { bar: 1, meter: 1, div: 1, stack: 1 };

  function isPctCol(c, rows) {
    if (c[2] !== "ltr") { return false; }
    var vals = rows.map(function (r) { return r[c[1]] == null ? "" : String(r[c[1]]); })
      .filter(function (v) { return v && v !== "—"; });
    return vals.length >= 2 && vals.every(function (v) { return /^\d[\d.,]*%$/.test(v); });
  }

  function colOpt(c) { return (c[3] && typeof c[3] === "object") ? c[3] : {}; }

  function tableNat(x, b) {
    if (b._nat) { return b._nat; }
    var cols = b.cols, rows = b.rows || [];
    var all = b.totalRow ? rows.concat([b.totalRow]) : rows;
    var last = b.totalRow ? all.length - 1 : -1, GAPC = 30;
    var explicit = cols.some(function (c) { return colOpt(c).viz; });
    var nat = [], min = [], loose = [], vz = [], pv = [], nums = [];
    cols.forEach(function (c, i) {
      var o = colOpt(c);
      var kind = o.viz || (!explicit && isPctCol(c, rows) ? "bar" : "");
      vz.push(kind);
      x.font = F(600, 15);
      var head = x.measureText(c[0]).width + (o.swatch != null ? 20 : 0), full = head, word = head, vals = 0;
      if (kind !== "spark") {
        all.forEach(function (r, n) {
          var v = r[c[1]] == null ? "" : String(r[c[1]]);
          if (c[2] === "ltr") {
            var vw = valWidth(x, v, cellVal(c, v, n === last));
            full = Math.max(full, vw);
            vals = Math.max(vals, vw);
            return;
          }
          x.font = cellFont(c, i, v, n === last);
          full = Math.max(full, x.measureText(v).width);
          v.split(" ").forEach(function (w) { word = Math.max(word, x.measureText(w).width); });
        });
      }
      pv.push(vals);
      if (BARRED[kind]) { full = Math.max(head, vals + BARW); }
      else if (kind === "chip") { full = Math.max(head, vals + 20); }
      else if (kind === "spark") { full = Math.max(head, SPW); }
      nums.push(BARRED[kind] && kind !== "stack" ? rows.map(function (r) { return parseNum(r[c[1]]); }) : null);
      nat.push(Math.ceil(full) + GAPC);
      // עמודת מספרים לעולם אינה נשברת. עמודת טקסט נשברת עד המילה הרחבה בה,
      // ומעבר ל-340 פיקסלים גם מילה נשברת — לפי תווים, בלי לאבד תו.
      // עמודת טקסט קצרה (שם חברה) אינה נשברת: "ניו-מד אנרג יהש" נשבר לשתי שורות
      // כשעמודת הערות ארוכה לידה מכרה רוחב. הכיווץ שייך לעמודות הארוכות.
      var soft = Math.max(Math.ceil(head) + GAPC, Math.min(Math.ceil(word) + GAPC, 340));
      loose.push(c[2] === "rtl" ? soft : Math.ceil(full) + GAPC);
      min.push(c[2] === "rtl" ? (full <= 280 ? Math.ceil(full) + GAPC : soft) : Math.ceil(full) + GAPC);
    });
    // טבלה שגם במינימום הקשיח רחבה מהקנבס — חוזרים לשבירה לפי מילים גם בעמודה קצרה.
    if (sum(min) > WMAX - PAD * 2 - TX * 2) { min = loose; }
    b._nat = { all: all, last: last, nat: nat, min: min, vz: vz, pv: pv, nums: nums,
      sumNat: sum(nat), sumMin: sum(min) };
    return b._nat;
  }

  // הסקאלה של כל עמודה מצוירת: הגבוה בעמודה, התקרה, או הגבוה בערך מוחלט.
  function tableScales(b, T) {
    var rows = b.rows || [];
    var sc = b.cols.map(function (c, i) {
      var o = colOpt(c), kind = T.vz[i], vals = (T.nums[i] || []).filter(function (v) { return v != null; });
      if (kind === "meter") { return o.max || 100; }
      if (kind === "div") { return Math.max.apply(null, [0].concat(vals.map(Math.abs))) || 1; }
      if (kind === "stack") {
        return Math.max.apply(null, [0].concat(rows.map(function (r) {
          return sum((o.parts || []).map(function (k) { return Math.max(0, parseNum(r[k]) || 0); }));
        }))) || 1;
      }
      if (kind === "bar") { return Math.max.apply(null, [0].concat(vals)) || 1; }
      return 0;
    });
    // **שתי עמודות אחוז באותו סדר גודל — סקאלה אחת.** "חלק מהליסינג" מול
    // "אשתקד" הם אותו מדד בשתי שנים, ובסקאלה נפרדת 13.3% ו-14.4% קיבלו פס
    // מלא שניהם. אחוז ממחזור (עד 100) ואחוז מההון (שברירי אחוז) נשארים נפרדים.
    var pctBars = b.cols.map(function (c, i) { return T.vz[i] === "bar" && isPctCol(c, rows) ? sc[i] : 0; })
      .filter(function (v) { return v > 0; });
    if (pctBars.length > 1 && Math.max.apply(null, pctBars) <= 3 * Math.min.apply(null, pctBars)) {
      var top = Math.max.apply(null, pctBars);
      sc = sc.map(function (v, i) { return T.vz[i] === "bar" && isPctCol(b.cols[i], rows) ? top : v; });
    }
    return sc;
  }

  // הצורה שבתוך התא, משמאל למספר. bx — הקצה הימני של אזור הפס, bl — אורכו.
  function cellViz(x, kind, o, raw, row, bx, bl, top, scale) {
    var v = parseNum(raw);
    if (kind === "stack") {
      var parts = (o.parts || []).map(function (k) { return Math.max(0, parseNum(row[k]) || 0); });
      x.fillStyle = C.track; rr(x, bx - bl, top, bl, 10, 5); x.fill();
      var k2 = bl / (scale || 1), cur = bx;
      var lastOn = -1;
      parts.forEach(function (p, k) { if (p * k2 >= 1) { lastOn = k; } });
      parts.forEach(function (p, k) {
        var w = p * k2;
        if (w < 1) { return; }
        x.fillStyle = CAT[k % CAT.length];
        if (k === lastOn) { barPath(x, cur - w, top, w, 10, 4, "left"); }
        else { x.beginPath(); x.rect(cur - w + 2, top, Math.max(0, w - 2), 10); }
        x.fill();
        cur -= w;
      });
      return;
    }
    if (v == null) { return; }
    x.fillStyle = C.track; rr(x, bx - bl, top, bl, 10, 5); x.fill();
    if (kind === "div") {
      var mid = bx - bl / 2, half = bl / 2 - 2, w2 = Math.max(3, half * Math.min(1, Math.abs(v) / (scale || 1)));
      if (Math.abs(v) > 1e-9) {
        x.fillStyle = v > 0 ? C.up : C.down;
        if (v > 0) { barPath(x, mid, top, w2, 10, 4, "right"); } else { barPath(x, mid - w2, top, w2, 10, 4, "left"); }
        x.fill();
      }
      x.fillStyle = C.line; x.fillRect(mid - 0.5, top - 5, 1, 20);
      return;
    }
    if (v <= 0) { return; }
    var w = Math.max(4, bl * Math.min(1, v / (scale || 1)));
    x.fillStyle = CAT[0]; barPath(x, bx - w, top, w, 10, 4, "left"); x.fill();
  }

  // הטבלה ממלאת את הכרטיס שלה עד הקצוות: מקרא (אם יש), שורת כותרת כהה, שורות
  // מתחלפות, ושורת הסך כפס כהה בתחתית.
  function tableBlock(x, b, g, draw) {
    if (!b.cols || !(b.rows || []).length) { return 0; }
    var T = tableNat(x, b), inner = g.inner - TX * 2, R = g.right - TX, LINE = 30, HB = 52;
    var LEG = (b.legend || []).length ? 48 : 0;
    var wid;
    if (T.sumNat <= inner) {
      // **המרווח מתחלק בין העמודות**, כפול לעמודה הראשונה. כשכולו הלך לעמודה
      // הראשונה, בטבלה צרה המספרים נדחסו לקצה אחד והשמות לקצה השני.
      var spare = inner - T.sumNat, wts = T.nat.map(function (w, i) { return i ? 1 : 2; });
      var sw = sum(wts);
      wid = T.nat.map(function (w, i) { return w + spare * wts[i] / sw; });
    } else {
      // רק עמודות הטקסט מתכווצות, כל אחת לפי המרווח שלה מעל המינימום.
      var over = T.sumNat - inner;
      var slack = T.nat.map(function (w, i) { return w - T.min[i]; });
      var sumSlack = sum(slack) || 1;
      wid = T.nat.map(function (w, i) { return w - over * slack[i] / sumSlack; });
    }
    var rows = T.all.map(function (r, n) {
      var bold = n === T.last;
      var cells = b.cols.map(function (c, i) {
        var raw = r[c[1]];
        var v = raw == null || Array.isArray(raw) ? "" : String(raw);
        x.font = cellFont(c, i, v, bold);
        return { v: v, raw: raw, lines: c[2] === "rtl" ? wrap(x, bidi(v), wid[i] - 30) : [v] };
      });
      var tall = cells.reduce(function (m, c) { return Math.max(m, c.lines.length); }, 1);
      return { cells: cells, bold: bold, src: r, h: 24 + LINE * tall };
    });
    x.font = F(400, 17);
    var more = b.moreText ? wrap(x, b.moreText, inner - 28) : [];
    var MH = more.length ? 20 + more.length * 26 : 0;
    var h = LEG + HB + sum(rows.map(function (r) { return r.h; })) + MH + (b.totalRow ? 6 : 8);
    if (!draw) { return h; }

    var y = g.top;
    if (LEG) { legendRow(x, b.legend, R - 14, y + 6, true); y += LEG; }
    x.fillStyle = C.navy; x.fillRect(g.left, y, g.inner, HB);
    var cx = R;
    x.direction = "rtl"; x.textAlign = "right";
    x.font = F(600, 15);
    b.cols.forEach(function (c, i) {
      // כותרת עמודה היא טקסט עברי גם כשהערכים בה LTR.
      var o = colOpt(c), tx = cx - 14;
      if (o.swatch != null) {
        x.fillStyle = CAT[o.swatch % CAT.length]; rr(x, tx - 12, y + 20, 12, 12, 3); x.fill();
        tx -= 20;
      }
      x.fillStyle = C.onNavy2; x.fillText(c[0], tx, y + 32);
      cx -= wid[i];
    });
    y += HB;
    var scales = tableScales(b, T);

    // שורות; אחריהן שורת ה"ועוד", ורק אז שורת הסך — הסדר שבעמוד.
    var moreDone = false;
    function drawMore() {
      moreDone = true;
      if (!more.length) { return; }
      x.fillStyle = C.hair; x.fillRect(g.left, y, g.inner, 1);
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.muted; x.font = F(400, 17);
      more.forEach(function (ln, k) { x.fillText(ln, R - 14, y + 31 + k * 26); });
      y += MH;
    }
    rows.forEach(function (row, n) {
      if (row.bold) {
        drawMore();
        x.fillStyle = C.navy; x.fillRect(g.left, y, g.inner, row.h + 6);
      } else if (n % 2 === 1) {
        x.fillStyle = C.zebra; x.fillRect(g.left, y, g.inner, row.h);
      }
      var vx = R;
      row.cells.forEach(function (cell, i) {
        var c = b.cols[i], kind = T.vz[i], o = colOpt(c);
        if (kind === "spark") {
          if (!row.bold && Array.isArray(cell.raw)) {
            sparkline(x, cell.raw, vx - wid[i] + 12, y + 12, wid[i] - 30, 34);
          }
        } else if (c[2] === "ltr") {
          var ov = cellVal(c, cell.v, row.bold);
          if (kind === "chip" && !row.bold && cell.v && cell.v !== "—") {
            var sv = parseNum(cell.v), tw = valWidth(x, cell.v, ov);
            x.fillStyle = sv > 0 ? C.upBg : sv < 0 ? C.downBg : C.track;
            rr(x, vx - 14 - tw - 9, y + 13, tw + 18, 30, 8); x.fill();
          }
          drawVal(x, cell.v, vx - 14, y + 35, ov);
          if (BARRED[kind] && !row.bold) {
            var bx = vx - 14 - T.pv[i] - 14, bl = Math.min(92, bx - (vx - wid[i] + 10));
            if (bl > 20) { cellViz(x, kind, o, cell.raw, row.src, bx, bl, y + 24, scales[i]); }
          }
        } else {
          x.direction = c[2]; x.textAlign = "right";
          x.font = cellFont(c, i, cell.v, row.bold);
          x.fillStyle = cellColor(c, i, cell.v, row.bold);
          cell.lines.forEach(function (ln, k) { x.fillText(ln, vx - 14, y + 35 + k * LINE); });
        }
        vx -= wid[i];
      });
      y += row.h;
    });
    if (!moreDone) { drawMore(); }
    return h;
  }

  // פסים אופקיים: שם, פס יחסי, ושני מספרים. הפס בצבע אחד — זו סדרה אחת, והאורך
  // הוא שמשווה; המספרים בדיו ולא בצבע הפס.
  function barsBlock(x, b, g, draw) {
    var rows = b.rows || [];
    if (!rows.length) { return 0; }
    var PV = { w: 700, s: 20, color: C.ink, fam: SANS }, MV = { w: 400, s: 16, color: C.faint, uw: 500 };
    var pvW = Math.max.apply(null, rows.map(function (r) { return valWidth(x, r.pctText, PV); })) + 30;
    var mvW = Math.max.apply(null, rows.map(function (r) { return valWidth(x, r.volText || "", MV); })) + 26;
    var labMax = Math.min(measureMax(x, F(600, 19), rows.map(function (r) { return r.label; })) + 26,
      g.inner * 0.36);
    x.font = F(600, 19);
    var lays = rows.map(function (r) {
      var lines = wrap(x, r.label, labMax - 26);
      return { lines: lines, h: Math.max(56, 24 + lines.length * 26) };
    });
    var h = sum(lays.map(function (l) { return l.h; }));
    if (!draw) { return h; }
    var y = g.top;
    var mx = Math.max.apply(null, rows.map(function (r) { return r.pct || 0; })) || 1;
    var barR = g.right - labMax, barW = g.inner - labMax - pvW - mvW - 18;
    rows.forEach(function (r, i) {
      var L = lays[i], cy = y + L.h / 2;
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.ink; x.font = F(600, 19);
      var ly = cy - (L.lines.length - 1) * 13 + 7;
      L.lines.forEach(function (ln, k) { x.fillText(ln, g.right, ly + k * 26); });
      x.fillStyle = C.track; rr(x, barR - barW, cy - 8, barW, 16, 5); x.fill();
      var fw = Math.max(6, barW * (r.pct || 0) / mx);
      x.fillStyle = CAT[0]; barPath(x, barR - fw, cy - 8, fw, 16, 4, "left"); x.fill();
      drawVal(x, r.pctText, g.left + mvW + pvW - 12, cy + 7, PV);
      drawVal(x, r.volText || "", g.left + mvW - 12, cy + 6, MV);
      y += L.h;
      if (i < rows.length - 1) { x.fillStyle = C.hair; x.fillRect(g.left, y, g.inner, 1); }
    });
    return h;
  }

  // עמודות לאורך זמן: הזמן זורם משמאל לימין, והיום האחרון מודגש. פריט עם parts הוא
  // עמודה מוערמת — חלק לכל סדרה, עם מקרא — והימים שלפני האחרון שקופים למחצה, כדי
  // שהעין תיפול על היום ועדיין תראה ממה הוא בנוי.
  function columnsBlock(x, b, g, draw) {
    var items = b.items || [];
    if (items.length < 2) { return 0; }
    var stacked = items.some(function (it) { return Array.isArray(it.parts); });
    var LEG = stacked && (b.series || []).length ? 42 : 0;
    var CH = 230, XL = 34;
    var h = LEG + CH + XL;
    if (!draw) { return h; }
    var y = g.top;
    if (LEG) { legendRow(x, b.series, g.right, y, true); y += LEG; }
    var vals = items.map(function (it) {
      return stacked ? sum((it.parts || []).map(function (p) { return Math.max(0, p || 0); })) : (it.value || 0);
    });
    var mx = Math.max.apply(null, vals.concat([b.median || 0])) || 1;
    var axisW = 96, left = g.left + axisW, right = g.right, plotW = right - left;
    var top = y + 16, bot = y + CH, ph = bot - top;
    function Y(v) { return bot - v / mx * ph; }
    x.fillStyle = C.hair;
    [0.5, 1].forEach(function (f) { x.fillRect(left, Y(mx * f), plotW, 1); });
    x.fillStyle = C.line; x.fillRect(left, bot, plotW, 1);
    var AX = { w: 400, s: 13, color: C.faint, uw: 500, us: 0.9 };
    drawVal(x, b.maxText || "", left - 12, Y(mx) + 5, AX);
    drawVal(x, "0", left - 12, bot + 4, AX);
    var n = items.length, slot = plotW / n, bw = Math.min(24, slot * 0.62);
    items.forEach(function (it, i) {
      var cx = left + slot * (i + 0.5), v = vals[i], last = i === n - 1;
      var yv = Y(v);
      if (stacked) {
        x.globalAlpha = last ? 1 : 0.42;
        var base = bot, parts = (it.parts || []).map(function (p) { return Math.max(0, p || 0); });
        var lastOn = -1;
        parts.forEach(function (p, k) { if (p / mx * ph >= 1) { lastOn = k; } });
        parts.forEach(function (p, k) {
          var hh = p / mx * ph;
          if (hh < 1) { return; }
          x.fillStyle = CAT[k % CAT.length];
          if (k === lastOn) { barPath(x, cx - bw / 2, base - hh, bw, hh, 4, "top"); }
          else { x.beginPath(); x.rect(cx - bw / 2, base - hh + 2, bw, Math.max(0, hh - 2)); }
          x.fill();
          base -= hh;
        });
        x.globalAlpha = 1;
      } else {
        var hh2 = Math.max(2, bot - yv);
        x.fillStyle = last ? CAT[0] : "#c4d8f3";
        barPath(x, cx - bw / 2, bot - hh2, bw, hh2, 4, "top"); x.fill();
      }
      if (i % 3 === (n - 1) % 3) {
        x.direction = "ltr"; x.textAlign = "center"; x.fillStyle = last ? C.ink : C.faint;
        x.font = F(last ? 600 : 400, 13, MONO);
        x.fillText(it.label, cx, bot + 24);
      }
      if (last && it.text) {
        // התווית יושבת על רקע לבן: כשהיום האחרון קרוב לחציון, הקו עובר דרכה.
        var LV = { w: 700, s: 15, color: C.ink, ucolor: C.muted, us: 0.85, fam: SANS };
        var tw = valWidth(x, it.text, LV), tr = Math.min(right, cx + tw / 2);
        x.fillStyle = C.card; rr(x, tr - tw - 8, yv - 30, tw + 16, 26, 7); x.fill();
        x.strokeStyle = C.line; x.lineWidth = 1; rr(x, tr - tw - 7.5, yv - 29.5, tw + 15, 25, 7); x.stroke();
        drawVal(x, it.text, tr, yv - 12, LV);
      }
    });
    if (b.median) {
      // קו ייחוס רציף ולא מקווקו (dataviz): מקווקו נקרא כתחזית.
      var my = Y(b.median);
      x.fillStyle = C.muted; x.fillRect(left, my - 0.75, plotW, 1.5);
      x.direction = "rtl"; x.textAlign = "left";
      x.font = F(600, 14);
      var mw = x.measureText(b.medianText || "").width;
      x.fillStyle = C.card; rr(x, left + 2, my - 30, mw + 16, 24, 6); x.fill();
      x.strokeStyle = C.line; x.lineWidth = 1; rr(x, left + 2.5, my - 29.5, mw + 15, 23, 6); x.stroke();
      x.fillStyle = C.muted;
      x.fillText(b.medianText || "", left + 10, my - 13);
    }
    return h;
  }

  // ---- דירוג: הגדולות, כפסים עם הערך בקצה. חלקים (parts) — פס מוערם עם מקרא.
  function rankBlock(x, b, g, draw) {
    var rows = (b.rows || []).filter(function (r) { return r && r.value != null; });
    if (!rows.length) { return 0; }
    var LEG = (b.legend || []).length ? 42 : 0;
    var VAL = { w: 700, s: 19, color: C.ink, ucolor: C.muted, us: 0.74, uw: 600, fam: SANS };
    // עמודת השם רחבה מספיק גם לשורת המשנה, כדי ש"4 עסקאות · 0.85% מההון" לא
    // יישבר באמצע — עד שליש מהרוחב, ומעבר לו נשבר.
    var labW = Math.min(Math.max(measureMax(x, F(700, 19), rows.map(function (r) { return r.label; })),
      measureMax(x, F(400, 15), rows.map(function (r) { return bidi(r.meta || ""); }))) + 28,
      g.inner * 0.34);
    var valW = Math.max.apply(null, rows.map(function (r) { return valWidth(x, r.text || "", VAL); })) + 18;
    var lays = rows.map(function (r) {
      x.font = F(700, 19);
      var lines = wrap(x, r.label, labW - 28);
      x.font = F(400, 15);
      var meta = r.meta ? wrap(x, bidi(r.meta), labW - 28) : [];
      return { lines: lines, meta: meta, h: Math.max(60, 22 + lines.length * 25 + meta.length * 21 + 12) };
    });
    var h = LEG + sum(lays.map(function (l) { return l.h; }));
    if (!draw) { return h; }
    var y = g.top;
    if (LEG) { legendRow(x, b.legend, g.right, y, true); y += LEG; }
    var mx = Math.max.apply(null, rows.map(function (r) { return r.value || 0; })) || 1;
    var barR = g.right - labW, barMax = g.inner - labW - valW - 6;
    rows.forEach(function (r, i) {
      var L = lays[i], cy = y + L.h / 2;
      var ty = y + (L.h - (L.lines.length * 25 + L.meta.length * 21)) / 2 + 19;
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.ink; x.font = F(700, 19);
      L.lines.forEach(function (ln, k) { x.fillText(ln, g.right, ty + k * 25); });
      x.fillStyle = C.muted; x.font = F(400, 15);
      L.meta.forEach(function (ln, k) { x.fillText(ln, g.right, ty + L.lines.length * 25 + k * 21 - 2); });
      var len = Math.max(4, barMax * (r.value || 0) / mx);
      if (Array.isArray(r.parts)) {
        var cur = barR, parts = r.parts.map(function (p) { return Math.max(0, p || 0); });
        var tot = sum(parts) || 1, lastOn = -1;
        parts.forEach(function (p, k) { if (len * p / tot >= 1) { lastOn = k; } });
        parts.forEach(function (p, k) {
          var w = len * p / tot;
          if (w < 1) { return; }
          x.fillStyle = CAT[k % CAT.length];
          if (k === lastOn) { barPath(x, cur - w, cy - 10, w, 20, 4, "left"); }
          else { x.beginPath(); x.rect(cur - w + 2, cy - 10, Math.max(0, w - 2), 20); }
          x.fill();
          cur -= w;
        });
      } else {
        x.fillStyle = CAT[0]; barPath(x, barR - len, cy - 10, len, 20, 4, "left"); x.fill();
      }
      drawVal(x, r.text || "", barR - len - 10, cy + 7, VAL);
      y += L.h;
      if (i < rows.length - 1) { x.fillStyle = C.hair; x.fillRect(g.left, y, g.inner, 1); }
    });
    return h;
  }

  // ---- לפני ואחרי לכל שורה (dumbbell): נקודה אפורה לתקופה הקודמת, נקודה כחולה
  // לעכשיו, וקו ביניהן בצבע הכיוון. ציר משותף, כדי שהשוואה בין שורות תהיה אמיתית.
  function dumbbellBlock(x, b, g, draw) {
    var rows = (b.rows || []).filter(function (r) { return r && r.b != null; });
    if (!rows.length) { return 0; }
    var LEG = 42, AXH = 30;
    var labW = Math.min(measureMax(x, F(700, 19), rows.map(function (r) { return r.label; })) + 28,
      g.inner * 0.3);
    var DV = { w: 700, s: 16, fam: SANS, color: C.ink };
    var dW = Math.max(74, Math.max.apply(null, rows.map(function (r) { return valWidth(x, r.delta_text || "", DV); })) + 28);
    var RH = 58;
    var h = LEG + AXH + rows.length * RH;
    if (!draw) { return h; }
    var y = g.top;
    // מקרא: אפור לקודם, כחול לעכשיו
    var lg = b.legend || ["קודם", "עכשיו"];
    x.direction = "rtl"; x.textAlign = "right"; x.font = F(600, 16);
    var lx = g.right;
    [["#a9b4c2", lg[0]], [CAT[0], lg[1]]].forEach(function (p) {
      x.fillStyle = p[0]; x.beginPath(); x.arc(lx - 7, y + 16, 7, 0, Math.PI * 2); x.fill();
      x.fillStyle = C.muted; x.fillText(p[1], lx - 22, y + 22);
      lx -= 22 + x.measureText(p[1]).width + 28;
    });
    y += LEG;
    var mxv = Math.max.apply(null, rows.map(function (r) { return Math.max(r.a || 0, r.b || 0); })) || 1;
    var step = niceStep(mxv, 4), top = Math.ceil(mxv / step) * step;
    var pl = g.left + dW + 14, pr = g.right - labW - 20, pw = pr - pl;
    function X(v) { return pl + pw * v / top; }
    x.direction = "ltr"; x.textAlign = "center"; x.font = F(400, 13, MONO); x.fillStyle = C.faint;
    for (var t = 0; t <= top + step / 2; t += step) {
      x.fillStyle = C.faint;
      x.fillText(fmtNum(t, step < 1 ? 1 : 0) + (b.suffix || ""), X(t), y + 18);
      x.fillStyle = t === 0 ? C.line : C.hair;
      x.fillRect(X(t) - 0.5, y + AXH, 1, rows.length * RH);
    }
    y += AXH;
    rows.forEach(function (r, i) {
      var cy = y + RH / 2;
      if (i % 2 === 1) { x.fillStyle = C.zebra; x.fillRect(g.left, y, g.inner, RH); }
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.ink; x.font = F(700, 19);
      x.fillText(r.label, g.right, r.sub ? cy - 2 : cy + 7);
      if (r.sub) { x.fillStyle = C.muted; x.font = F(400, 14); x.fillText(r.sub, g.right, cy + 18); }
      var xa = X(r.a || 0), xb = X(r.b || 0), up = (r.b || 0) >= (r.a || 0);
      x.fillStyle = up ? C.up : C.down;
      x.fillRect(Math.min(xa, xb), cy - 1.5, Math.abs(xb - xa), 3);
      [[xa, "#a9b4c2", 6], [xb, CAT[0], 7]].forEach(function (d) {
        x.fillStyle = C.card; x.beginPath(); x.arc(d[0], cy, d[2] + 2, 0, Math.PI * 2); x.fill();
        x.fillStyle = d[1]; x.beginPath(); x.arc(d[0], cy, d[2], 0, Math.PI * 2); x.fill();
      });
      // הערך של עכשיו, בצד שאינו פונה לנקודה הקודמת
      var BV = { w: 600, s: 15, fam: SANS, color: C.ink };
      var bt = r.text || "", bw2 = valWidth(x, bt, BV);
      var bxr = up ? xb + 14 + bw2 : xb - 14;
      if (bxr > pr) { bxr = xb - 14; }
      if (bxr - bw2 < pl) { bxr = xb + 14 + bw2; }
      drawVal(x, bt, bxr, cy + 6, BV);
      // השינוי — שבב בעמודה השמאלית
      if (r.delta_text) {
        var dv = parseNum(r.delta_text);
        var tw = valWidth(x, r.delta_text, DV);
        x.fillStyle = dv > 0 ? C.upBg : dv < 0 ? C.downBg : C.track;
        rr(x, g.left + dW - tw - 22, cy - 15, tw + 18, 30, 8); x.fill();
        DV.color = dv > 0 ? C.up : dv < 0 ? C.down : C.muted;
        drawVal(x, r.delta_text, g.left + dW - 13, cy + 6, DV);
      }
      y += RH;
    });
    return h;
  }

  // ---- ריבוי קטן (small multiples) של עקומי חוזים: לכל סחורה גרף משלה, אבל ציר
  // אחוזים משותף — כך שעקום תלול באמת נראה תלול גם ליד שכנו. הזמן משמאל לימין.
  function curvesBlock(x, b, g, draw) {
    var items = (b.items || []).filter(function (it) { return (it.points || []).length >= 2; });
    if (!items.length) { return 0; }
    var cols = g.inner >= 900 ? 2 : 1, gap = 18, cw = (g.inner - gap * (cols - 1)) / cols, CH = 206;
    var rowsN = Math.ceil(items.length / cols);
    var h = rowsN * CH + (rowsN - 1) * gap;
    if (!draw) { return h; }
    var all = [0];
    items.forEach(function (it) { it.points.forEach(function (p) { all.push(p[1]); }); });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    var step = niceStep(hi - lo, 3);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    if (hi === lo) { hi = lo + step; }
    var hmax = Math.max.apply(null, items.map(function (it) {
      return Math.max.apply(null, it.points.map(function (p) { return p[0]; }));
    })) || 1;
    var SH = { "בקוורדיישן": "↘", "קונטנגו": "↗", "שטוח": "→" };
    items.forEach(function (it, i) {
      var col = i % cols, row = Math.floor(i / cols);
      var cr = g.right - col * (cw + gap), cl = cr - cw, ct = g.top + row * (CH + gap);
      x.fillStyle = "#f7f9fc"; rr(x, cl, ct, cw, CH, 12); x.fill();
      x.strokeStyle = C.hair; x.lineWidth = 1; rr(x, cl + 0.5, ct + 0.5, cw - 1, CH - 1, 12); x.stroke();
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.ink; x.font = F(700, 18);
      x.fillText(it.name, cr - 16, ct + 30);
      if (it.front) {
        x.fillStyle = C.muted; x.font = F(400, 14);
        x.fillText("חוזה קרוב: ", cr - 16, ct + 52);
        var fw = x.measureText("חוזה קרוב: ").width;
        drawVal(x, it.front, cr - 16 - fw, ct + 52, { w: 600, s: 14, fam: SANS, color: C.ink, ucolor: C.muted, us: 0.9 });
      }
      if (it.shape) {
        x.font = F(700, 14);
        var st = (SH[it.shape] ? SH[it.shape] + " " : "") + it.shape, sw = x.measureText(st).width + 20;
        x.fillStyle = C.card; rr(x, cl + 14, ct + 14, sw, 28, 14); x.fill();
        x.strokeStyle = C.line; rr(x, cl + 14.5, ct + 14.5, sw - 1, 27, 14); x.stroke();
        x.fillStyle = C.ink; x.textAlign = "center"; x.fillText(st, cl + 14 + sw / 2, ct + 33);
      }
      var pl = cl + 52, pr = cr - 66, pt = ct + 70, pb = ct + CH - 34;
      function X(m) { return pl + (pr - pl) * m / hmax; }
      function Y(v) { return pb - (v - lo) / (hi - lo) * (pb - pt); }
      for (var t = lo; t <= hi + step / 2; t += step) {
        x.fillStyle = Math.abs(t) < step / 1e6 ? C.line : C.hair;
        x.fillRect(pl, Y(t) - 0.5, pr - pl, 1);
        drawVal(x, fmtNum(t, step < 1 ? 1 : 0) + "%", pl - 8, Y(t) + 4, { w: 400, s: 12, color: C.faint });
      }
      x.direction = "ltr"; x.textAlign = "center"; x.font = F(400, 12, MONO); x.fillStyle = C.faint;
      (b.ticks || [0, 6, 12, 24]).forEach(function (m) {
        if (m <= hmax) { x.fillText(m ? m + "m" : "0", X(m), pb + 18); }
      });
      var pts = it.points;
      x.beginPath();
      pts.forEach(function (p, k) { if (k) { x.lineTo(X(p[0]), Y(p[1])); } else { x.moveTo(X(p[0]), Y(p[1])); } });
      x.strokeStyle = CAT[0]; x.lineWidth = 2; x.lineJoin = "round"; x.lineCap = "round"; x.stroke();
      var e = pts[pts.length - 1], ex = X(e[0]), ey = Y(e[1]);
      x.fillStyle = C.card; x.beginPath(); x.arc(ex, ey, 6, 0, Math.PI * 2); x.fill();
      x.fillStyle = CAT[0]; x.beginPath(); x.arc(ex, ey, 4, 0, Math.PI * 2); x.fill();
      var et = (e[1] > 0 ? "+" : "") + fmtNum(e[1], 1) + "%";
      var EV = { w: 700, s: 14, fam: SANS, color: e[1] > 0 ? C.up : e[1] < 0 ? C.down : C.muted };
      drawVal(x, et, ex + 10 + valWidth(x, et, EV), ey + 5, EV);
    });
    return h;
  }

  // ---- כרטיסים: פריט לכל חברה — שם, שבב כיוון (סמל ומילה, לא צבע לבדו) והסבר.
  // שתי עמודות כשהרוחב מאפשר.
  var TONE = {
    up: ["▲ חיובי", "#e1f3e9", "#12804d"], down: ["▼ שלילי", "#fbe6e3", "#c4392f"],
    mixed: ["◆ מעורב", "#fbefd6", "#a86f0c"], flat: ["● ניטרלי", "#e8eef6", "#55667c"]
  };
  function toneOf(t) {
    var s = String(t || "");
    if (TONE[s]) { return s; }
    return s.indexOf("חיובי") >= 0 ? "up" : s.indexOf("שלילי") >= 0 ? "down" : s.indexOf("מעורב") >= 0 ? "mixed" : "flat";
  }
  function cardsBlock(x, b, g, draw) {
    var items = (b.items || []).filter(function (it) { return it && it.title; });
    if (!items.length) { return 0; }
    var cols = g.inner >= 1000 ? 2 : 1, gap = 16, cw = (g.inner - gap * (cols - 1)) / cols, P = 22, LH = 28;
    var lays = items.map(function (it) {
      x.font = F(400, 18);
      var lines = it.text ? wrap(x, bidi(it.text), cw - P * 2) : [];
      return { lines: lines, h: P + 34 + (lines.length ? 8 + lines.length * LH : 0) + P - 6 };
    });
    var rowH = [];
    for (var r = 0; r < Math.ceil(items.length / cols); r++) {
      rowH.push(Math.max.apply(null, lays.slice(r * cols, r * cols + cols).map(function (l) { return l.h; })));
    }
    var TH = b.title ? SECTION_H : 0;
    var h = TH + sum(rowH) + gap * (rowH.length - 1);
    if (!draw) { return h; }
    if (b.title) { section(x, b.title, g, g.top); }
    var top = g.top + TH;
    rowH.forEach(function (rh, r) {
      for (var c = 0; c < cols; c++) {
        var i = r * cols + c;
        if (i >= items.length) { break; }
        var it = items[i], L = lays[i], cr = g.right - c * (cw + gap), cl = cr - cw;
        card(x, cl, top, cw, rh, 14);
        var t = TONE[toneOf(it.tone || it.pill)];
        x.direction = "rtl"; x.textAlign = "right";
        x.fillStyle = C.ink; x.font = F(700, 20);
        x.fillText(it.title, cr - P, top + P + 22);
        x.font = F(700, 14);
        var pw = x.measureText(it.pill || t[0]).width + 22;
        x.fillStyle = t[1]; rr(x, cl + P, top + P + 2, pw, 28, 14); x.fill();
        x.fillStyle = t[2]; x.textAlign = "center";
        x.fillText(it.pill || t[0], cl + P + pw / 2, top + P + 21);
        x.textAlign = "right"; x.fillStyle = C.ink; x.font = F(400, 18);
        L.lines.forEach(function (ln, k) { x.fillText(ln, cr - P, top + P + 34 + 8 + 20 + k * LH); });
      }
      top += rh + gap;
    });
    return h;
  }

  // ---- עמודי הסחורות והרכב: קווים לאורך זמן, ופסים סביב אפס.

  var SERIES = CAT.concat(["#e87ba4"]);

  // צעד "עגול" לציר: 1, 2, 2.5 או 5 כפול חזקה של 10.
  function niceStep(span, n) {
    var raw = (span || 1) / n, p = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var m = raw / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }

  function fmtNum(v, dg) {
    return Number(v).toLocaleString("en-US", { minimumFractionDigits: dg, maximumFractionDigits: dg });
  }

  // קווים: כמה סדרות על ציר זמן משותף. הזמן זורם משמאל לימין, כמו בעמוד;
  // המקרא למעלה, והערך האחרון של כל סדרה ליד סוף הקו שלה — מופרדים אנכית
  // כששני קווים מסתיימים קרוב זה לזה.
  function linesBlock(x, b, g, draw) {
    var labels = b.labels || [];
    var series = (b.series || []).filter(function (s) {
      return (s.values || []).some(function (v) { return v != null; });
    });
    if (!series.length || labels.length < 2) { return 0; }
    var LEG = 44, CH = 270, XL = 36;
    var h = LEG + CH + XL;
    if (!draw) { return h; }
    var dg = b.decimals == null ? 1 : b.decimals, suf = b.suffix || "";
    var y = g.top;

    var lx = g.right;
    x.direction = "rtl"; x.textAlign = "right"; x.font = F(600, 17);
    series.forEach(function (s, i) {
      var col = s.color || SERIES[i % SERIES.length];
      x.fillStyle = col; rr(x, lx - 24, y + 13, 24, 6, 3); x.fill();
      x.fillStyle = C.muted; x.fillText(s.name, lx - 34, y + 22);
      lx -= 34 + x.measureText(s.name).width + 30;
    });
    y += LEG;

    var all = [];
    series.forEach(function (s) { s.values.forEach(function (v) { if (v != null) { all.push(v); } }); });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    if (b.zero) { lo = Math.min(0, lo); }
    var step = niceStep(hi - lo, 4);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    if (hi === lo) { hi = lo + step; }
    var sdg = step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
    var AX = { w: 400, s: 14, color: C.faint };
    var axisW = Math.max(valWidth(x, fmtNum(hi, sdg) + suf, AX), valWidth(x, fmtNum(lo, sdg) + suf, AX)) + 18;
    var endW = 34 + Math.max.apply(null, series.map(function (s) {
      var last = null;
      s.values.forEach(function (v) { if (v != null) { last = v; } });
      return valWidth(x, fmtNum(last, dg) + suf, { w: 700, s: 17, fam: SANS });
    }));
    var left = g.left + axisW, right = g.right - endW, plotW = right - left;
    var top = y + 10, bot = y + CH, ph = bot - top, n = labels.length;
    function X(i) { return left + plotW * i / (n - 1); }
    function Y(v) { return bot - (v - lo) / (hi - lo) * ph; }

    for (var t = lo; t <= hi + step / 2; t += step) {
      x.fillStyle = Math.abs(t) < step / 1e6 ? C.line : C.hair;
      x.fillRect(left, Y(t), plotW, 1);
      drawVal(x, fmtNum(t, sdg) + suf, left - 10, Y(t) + 5, AX);
    }
    var every = Math.max(1, Math.ceil(n / 9));
    x.font = F(400, 14, MONO); x.fillStyle = C.faint; x.textAlign = "center"; x.direction = "ltr";
    labels.forEach(function (lb, i) {
      if ((n - 1 - i) % every === 0) { x.fillText(lb, X(i), bot + 26); }
    });

    var ends = [];
    series.forEach(function (s, si) {
      var col = s.color || SERIES[si % SERIES.length], pts = [];
      s.values.forEach(function (v, i) { if (v != null) { pts.push([X(i), Y(v), v]); } });
      if (pts.length < 2) { return; }
      x.strokeStyle = col; x.lineWidth = 2.5; x.lineJoin = "round"; x.lineCap = "round";
      x.beginPath();
      pts.forEach(function (p, k) { if (k) { x.lineTo(p[0], p[1]); } else { x.moveTo(p[0], p[1]); } });
      x.stroke();
      var e = pts[pts.length - 1];
      x.fillStyle = C.card; x.beginPath(); x.arc(e[0], e[1], 6.5, 0, Math.PI * 2); x.fill();
      x.fillStyle = col; x.beginPath(); x.arc(e[0], e[1], 4.5, 0, Math.PI * 2); x.fill();
      ends.push({ y: e[1], x: e[0], v: e[2], col: col });
    });
    // תוויות הסוף: לפחות 24 פיקסלים בין שתיים, בתוך תחום הגרף.
    ends.sort(function (a, c) { return a.y - c.y; });
    var ly = [];
    ends.forEach(function (e, k) {
      var want = e.y + 6;
      if (k && want - ly[k - 1] < 24) { want = ly[k - 1] + 24; }
      ly.push(Math.min(want, bot + 6));
    });
    for (var k = ends.length - 2; k >= 0; k--) {
      if (ly[k + 1] - ly[k] < 24) { ly[k] = ly[k + 1] - 24; }
    }
    // הערך בדיו ולא בצבע הסדרה (צהוב על לבן אינו קריא). תווית שהוזזה מסוף הקו
    // כדי לא לעלות על שכנתה מקבלת ריבוע בצבע הקו — בלעדיו לא ברור של מי היא.
    ends.forEach(function (e, k) {
      var o = { w: 700, s: 17, color: C.ink, fam: SANS }, tx = e.x + 14;
      if (Math.abs(ly[k] - (e.y + 6)) > 3) {
        x.fillStyle = e.col; rr(x, tx, ly[k] - 11, 10, 10, 3); x.fill();
        tx += 16;
      }
      drawVal(x, fmtNum(e.v, dg) + suf, tx + valWidth(x, fmtNum(e.v, dg) + suf, o), ly[k], o);
    });
    return h;
  }

  // פסים סביב אפס: תווית ומחיר מימין, פס מציר אמצעי — חיובי ימינה ושלילי
  // שמאלה, כמו ב-.cm-rbar שבעמוד — והשינוי בקצה השמאלי.
  function dbarsBlock(x, b, g, draw) {
    var rows = (b.rows || []).filter(function (r) { return r.value != null; });
    if (!rows.length) { return 0; }
    var NV = { w: 400, s: 16, color: C.faint, uw: 500, us: 0.85 };
    var CV = { w: 600, s: 20 };
    // **רוחבים קבועים, לא נמדדים.** כמה גושים בכרטיס אחד (גז, נפט, פלדה, חשמל)
    // מדדו כל אחד את התוויות שלו, וציר האפס זז מגוש לגוש. שבר קבוע מהרוחב
    // מיישר את כולם; מה שרחב מדי נשבר לשתי שורות ולא נחתך.
    var noteW = Math.max(g.inner * 0.17, Math.max.apply(null, rows.map(function (r) {
      return valWidth(x, r.note || "", NV); })) + 26);
    var chgW = Math.max(g.inner * 0.085, Math.max.apply(null, rows.map(function (r) {
      return valWidth(x, r.text || "", CV); })) + 22);
    var labMax = g.inner * 0.3;
    x.font = F(600, 19);
    var lays = rows.map(function (r) {
      var lines = wrap(x, r.label, labMax - 26);
      return { lines: lines, h: Math.max(52, 22 + lines.length * 26) };
    });
    var h = sum(lays.map(function (l) { return l.h; }));
    if (!draw) { return h; }
    var y = g.top;
    var mx = Math.max.apply(null, rows.map(function (r) { return Math.abs(r.value); })) || 1;
    var trR = g.right - labMax - noteW, trL = g.left + chgW, trW = trR - trL, mid = trL + trW / 2;
    rows.forEach(function (r, i) {
      var L = lays[i], cy = y + L.h / 2;
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.ink; x.font = F(600, 19);
      var ly = cy - (L.lines.length - 1) * 13 + 7;
      L.lines.forEach(function (ln, k) { x.fillText(ln, g.right, ly + k * 26); });
      drawVal(x, r.note || "", g.right - labMax - 12, cy + 6, NV);
      x.fillStyle = C.track; rr(x, trL, cy - 7, trW, 14, 4); x.fill();
      var bw = Math.max(3, (trW / 2 - 4) * Math.abs(r.value) / mx);
      // חיובי בירוק ושלילי באדום, כמו המספר שבקצה: הצבע חוזר על הסימן ואינו
      // נושא אותו לבד — הכיוון קריא גם מצד הציר וגם מהמינוס.
      x.fillStyle = r.value >= 0 ? C.up : C.down;
      if (r.value >= 0) { barPath(x, mid, cy - 7, bw, 14, 4, "right"); } else { barPath(x, mid - bw, cy - 7, bw, 14, 4, "left"); }
      x.fill();
      x.fillStyle = C.line; x.fillRect(mid - 0.5, cy - 12, 1, 24);
      var o = { w: 600, s: 20, color: signColor(r.text || "", C.ink) };
      drawVal(x, r.text || "", g.left + valWidth(x, r.text || "", o), cy + 7, o);
      y += L.h;
      if (i < rows.length - 1) { x.fillStyle = C.hair; x.fillRect(g.left, y, g.inner, 1); }
    });
    return h;
  }

  // דיווחי בעלי עניין: שורה לדיווח — חברה, כיוון, טופס, מדווח — ומספרים.
  var RCOLS = [["כמות", "q"], ["שער", "px"], ["היקף", "v"], ["מההון", "pct"], ["החזקה אחרי", "after"]];
  function rcols(b) { return b.cols || RCOLS; }
  function rval(c) { return { w: c[1] === "pct" ? 600 : 500, s: 18, uw: 500, us: 0.8 }; }

  function chipList(r, withDate) {
    var chips = [];
    if (withDate && r.d) { chips.push({ t: r.d.slice(8, 10) + "/" + r.d.slice(5, 7), fg: C.muted, bg: null, mono: true }); }
    chips.push({ t: r.dir === "buy" ? "רכישה" : "מכירה", fg: r.dir === "buy" ? C.up : C.down,
      bg: r.dir === "buy" ? C.upBg : C.downBg, bold: true });
    if (r.form) { chips.push({ t: r.form, fg: C.muted, bg: null, mono: true }); }
    if (r.partial) { chips.push({ t: "מאגד", fg: C.warn, bg: C.warnBg }); }
    if (r.restated) { chips.push({ t: "הוגש שוב", fg: C.warn, bg: C.warnBg }); }
    if (r.other) { chips.push({ t: "הצד השני", fg: C.warn, bg: C.warnBg }); }
    return chips;
  }

  function chipW(x, c) {
    x.font = c.mono ? F(500, 13, MONO) : F(c.bold ? 700 : 600, 14);
    return Math.ceil(x.measureText(c.t).width) + 20;
  }

  function reportsLayout(x, b, inner) {
    var rows = [];
    (b.groups || []).forEach(function (grp) { rows = rows.concat(grp.rows || []); });
    var colW = rcols(b).map(function (c) {
      var head = measureMax(x, F(600, 15), [c[0]]);
      var vals = Math.max.apply(null, [0].concat(rows.map(function (r) {
        return valWidth(x, (r[c[1]] || "—") + (c[1] === "pct" && r.inh ? "*" : ""), rval(c));
      })));
      return Math.ceil(Math.max(head, vals)) + 30;
    });
    var zone = inner - sum(colW) - 16;
    return { colW: colW, zone: zone };
  }

  // הרוחב שהגוש צריך: עמודות המספרים, 470 לחברה ולמדווח, ושוליים פנימיים.
  function reportsNeed(x, b) {
    var L = reportsLayout(x, b, 0);
    return sum(L.colW) + 16 + 470 + 14 + TX * 2;
  }

  function reportRow(x, r, zone, withDate) {
    x.font = F(700, 21);
    var coW = x.measureText(r.co || "—").width;
    var chips = chipList(r, withDate), cw = sum(chips.map(function (c) { return chipW(x, c) + 8; }));
    var ownLine = coW + 14 + cw > zone;
    x.font = F(400, 18);
    var who = wrap(x, (r.who || "—") + (r.type ? " · " + r.type : ""), zone);
    x.font = F(400, 16);
    var ctrl = r.ctrl ? wrap(x, "בעל השליטה בו: " + r.ctrl, zone) : [];
    var h = 18 + 30 + (ownLine ? 34 : 0) + who.length * 27 + ctrl.length * 23 + 16;
    return { chips: chips, ownLine: ownLine, who: who, ctrl: ctrl, h: h };
  }

  // הדיווחים ממלאים את הכרטיס כמו טבלה: שורת כותרת כהה ושורות מתחלפות.
  function reportsBlock(x, b, g, draw) {
    var groups = (b.groups || []).filter(function (grp) { return (grp.rows || []).length; });
    if (!groups.length) { return 0; }
    var left = g.left + TX, right = g.right - TX - 14, inner = g.inner - TX * 2 - 14;
    var L = reportsLayout(x, b, inner), HB = 50, GH = 56;
    var lays = groups.map(function (grp) {
      return grp.rows.map(function (r) { return reportRow(x, r, L.zone, b.dates); });
    });
    x.font = F(400, 17);
    var more = b.moreText ? wrap(x, b.moreText, inner) : [];
    var h = HB + sum(groups.map(function (grp, gi) {
      return (grp.label ? GH : 0) + sum(lays[gi].map(function (l) { return l.h; }));
    })) + (more.length ? 20 + more.length * 26 : 0) + 8;
    if (!draw) { return h; }

    var y = g.top;
    x.fillStyle = C.navy; x.fillRect(g.left, y, g.inner, HB);
    x.direction = "rtl"; x.textAlign = "right";
    x.font = F(600, 15); x.fillStyle = C.onNavy2;
    x.fillText("חברה · מדווח", right, y + 31);
    var colRight = [], cx = left + sum(L.colW);
    rcols(b).forEach(function (c, i) {
      colRight.push(cx);
      x.fillText(c[0], cx - 12, y + 31);
      cx -= L.colW[i];
    });
    y += HB;

    var zi = 0;
    groups.forEach(function (grp, gi) {
      if (grp.label) {
        x.direction = "rtl"; x.textAlign = "right";
        x.fillStyle = C.accent; x.font = F(700, 19);
        x.fillText(grp.label, right, y + 36);
        var lw = x.measureText(grp.label).width;
        if (grp.count) {
          x.fillStyle = C.faint; x.font = F(400, 16);
          x.fillText(grp.count, right - lw - 14, y + 36);
          lw += 14 + x.measureText(grp.count).width;
        }
        x.fillStyle = C.line;
        x.fillRect(left, y + 30, Math.max(0, right - left - lw - 20), 1);
        y += GH;
      }
      grp.rows.forEach(function (r, ri) {
        var R = lays[gi][ri], zr = right, base = y + 18 + 22;
        if (zi % 2 === 1) { x.fillStyle = C.zebra; x.fillRect(g.left, y, g.inner, R.h); }
        zi += 1;
        x.direction = "rtl"; x.textAlign = "right";
        x.fillStyle = C.ink; x.font = F(700, 21);
        x.fillText(r.co || "—", zr, base);
        var coW = x.measureText(r.co || "—").width;
        var chipX = R.ownLine ? zr : zr - coW - 14;
        var chipY = R.ownLine ? base + 12 : base - 20;
        R.chips.forEach(function (c) {
          var w = chipW(x, c);
          if (c.bg) {
            x.fillStyle = c.bg; rr(x, chipX - w, chipY, w, 26, 7); x.fill();
          } else {
            x.strokeStyle = C.line; x.lineWidth = 1;
            rr(x, chipX - w + 0.5, chipY + 0.5, w - 1, 25, 7); x.stroke();
          }
          x.fillStyle = c.fg; x.textAlign = "center";
          x.font = c.mono ? F(500, 13, MONO) : F(c.bold ? 700 : 600, 14);
          x.fillText(c.t, chipX - w / 2, chipY + 18);
          chipX -= w + 8;
        });
        x.textAlign = "right";
        var ty = base + (R.ownLine ? 34 : 0) + 30;
        x.fillStyle = C.muted; x.font = F(400, 18);
        R.who.forEach(function (ln, k) { x.fillText(ln, zr, ty + k * 27); });
        ty += R.who.length * 27;
        if (R.ctrl.length) {
          x.fillStyle = C.faint; x.font = F(400, 16);
          R.ctrl.forEach(function (ln, k) { x.fillText(ln, zr, ty - 4 + k * 23); });
        }
        var dim = r.cnt === false;
        rcols(b).forEach(function (c, i) {
          var v = (r[c[1]] || "—") + (c[1] === "pct" && r.inh ? "*" : "");
          var o = rval(c);
          o.color = dim || v.charAt(0) === "—" ? C.faint : c[1] === "pct" ? C.accent : c[1] === "v" ? C.ink : C.muted;
          o.ucolor = dim ? C.faint : C.muted;
          drawVal(x, v, colRight[i] - 12, base, o);
        });
        y += R.h;
      });
    });
    if (more.length) {
      x.fillStyle = C.hair; x.fillRect(g.left, y, g.inner, 1);
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.muted; x.font = F(400, 17);
      more.forEach(function (ln, k) { x.fillText(ln, right, y + 31 + k * 26); });
    }
    return h;
  }

  var BLOCKS = { stats: statsBlock, notes: notesBlock, table: tableBlock, bars: barsBlock,
    columns: columnsBlock, reports: reportsBlock, lines: linesBlock, dbars: dbarsBlock,
    rank: rankBlock, dumbbell: dumbbellBlock, curves: curvesBlock, cards: cardsBlock };

  // **כל גוש מלבד האריחים והעיקרים — בכרטיס לבן, וכותרתו מעליו.** הריפוד
  // הפנימי לפי הסוג: טבלה ודיווחים ממלאים את הכרטיס עד הקצה (שורת הכותרת
  // הכהה נחתכת בפינות המעוגלות), וגרף יושב בתוכו עם שוליים. הגוש עצמו מצויר
  // בגיאומטריה הפנימית ואינו יודע על הכרטיס.
  var FRAME = { table: 0, reports: 0, bars: 26, columns: 26, lines: 26, dbars: 26,
    rank: 26, dumbbell: 26, curves: 22 };
  var RADIUS = 16;
  function runBlock(x, b, g, draw) {
    var fn = BLOCKS[b.type];
    if (!Object.prototype.hasOwnProperty.call(FRAME, b.type)) { return fn(x, b, g, draw); }
    var p = FRAME[b.type], th = b.title ? SECTION_H : 0;
    var gi = { left: g.left + p, right: g.right - p, inner: g.inner - p * 2, top: g.top + th + p, W: g.W };
    var ih = fn(x, b, gi, false);
    if (!ih) { return 0; }
    var h = th + ih + p * 2;
    if (!draw) { return h; }
    if (b.title) { section(x, b.title, g, g.top); }
    var ct = g.top + th, chh = ih + p * 2;
    card(x, g.left, ct, g.inner, chh, RADIUS);
    x.save();
    rr(x, g.left, ct, g.inner, chh, RADIUS); x.clip();
    fn(x, b, gi, true);
    x.restore();
    return h;
  }

  // ---------------------------------------------------------------- תחתית

  // פס כהה לכל הרוחב: מקור והסתייגות מימין, קרדיט ותאריך משמאל.
  function footer(x, d, g, draw) {
    x.font = F(400, 16);
    var src = wrap(x, d.source || SRC_TASE, g.inner - 300);
    var h = 74 + src.length * 25;
    if (!draw) { return h; }
    var y = g.top, W = g.W;
    x.fillStyle = C.navy; x.fillRect(0, y, W, h);
    var al = x.createLinearGradient(0, 0, W, 0);
    al.addColorStop(0, C.accent); al.addColorStop(1, C.accent2);
    x.fillStyle = al; x.fillRect(0, y, W, 3);
    x.direction = "rtl"; x.textAlign = "right";
    x.fillStyle = C.onNavy2; x.font = F(400, 16);
    src.forEach(function (ln, k) { x.fillText(ln, g.right, y + 38 + k * 25); });
    x.fillStyle = C.onNavy3; x.font = F(400, 14);
    x.fillText("מידע ונתונים בלבד — אינו המלצת השקעה.", g.right, y + 38 + src.length * 25 + 6);
    x.direction = "ltr"; x.textAlign = "left";
    x.fillStyle = C.brand; x.font = F(700, 18);
    x.fillText("© @Cigarbutthunte7", g.left, y + 40);
    var now = new Date();
    var stamp = "הופק " + ("0" + now.getDate()).slice(-2) + "/" + ("0" + (now.getMonth() + 1)).slice(-2) +
      "/" + now.getFullYear();
    x.direction = "rtl"; x.textAlign = "left";
    x.fillStyle = C.onNavy3; x.font = F(400, 14);
    x.fillText(stamp, g.left, y + 66);
    return h;
  }

  function background(x, W, H) {
    var g = x.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, C.page); g.addColorStop(1, C.page2);
    x.fillStyle = g; x.fillRect(0, 0, W, H);
  }

  // ---------------------------------------------------------------- כרטיס

  function render(d) {
    var probe = document.createElement("canvas").getContext("2d");
    var blocks = (d.blocks || []).filter(function (b) { return BLOCKS[b.type]; });
    var inner = W0 - PAD * 2, minInner = 0, cap = WMAX - PAD * 2;
    blocks.forEach(function (b) {
      if (b.type === "table" && b.cols && (b.rows || []).length) {
        var T = tableNat(probe, b);
        inner = Math.max(inner, Math.min(T.sumNat + TX * 2, cap));
        minInner = Math.max(minInner, T.sumMin + TX * 2);
      }
      if (b.type === "reports") {
        inner = Math.max(inner, Math.min(reportsNeed(probe, b), cap));
      }
    });
    inner = Math.max(inner, minInner);
    var W = inner + PAD * 2;
    var g = { left: PAD, right: W - PAD, inner: inner, top: 0, W: W };
    var over = blocks.length > 0 && blocks[0].type === "stats" && (blocks[0].items || []).length > 0;

    var H = header(probe, d, g, false, over);
    blocks.forEach(function (b) {
      var bh = runBlock(probe, b, g, false);
      if (bh) { H += bh + GAP; }
    });
    H += FOOT_GAP + footer(probe, d, g, false);

    // **קנבס גדול מדי יוצא ריק, בלי שגיאה.** iOS Safari מגביל את שטח הקנבס
    // לכ-16.7 מיליון פיקסלים, ומעבר לכך toBlob מחזיר null. הרזולוציה יורדת
    // במקום שהתמונה תיעלם.
    var S = Math.min(2, Math.sqrt(16e6 / (W * H)), 16000 / W, 16000 / H);
    var cv = document.createElement("canvas");
    cv.width = Math.round(W * S); cv.height = Math.round(H * S);
    var x = cv.getContext("2d");
    x.scale(S, S);
    x.textBaseline = "alphabetic";
    SC = S;
    background(x, W, H);
    g.top = header(x, d, g, true, over);
    blocks.forEach(function (b) {
      var bh = runBlock(x, b, g, true);
      if (bh) { g.top += bh + GAP; }
    });
    g.top += FOOT_GAP;
    footer(x, d, g, true);
    return cv;
  }

  // חשוף לבדיקה: חלוקת משפט לקטעים מודגשים והנחתם, כדי להשוות את הציור
  // בקטעים לציור של אותה שורה בבת אחת.
  window.tlvRich = { hiPieces: hiPieces, capPieces: capPieces, richWrap: richWrap, richDraw: richDraw };

  // ---------------------------------------------------------------- דיווחי מאיה

  var DATA = null;
  function data() {
    if (DATA) { return DATA; }
    var el = document.getElementById("offex-data");
    try { DATA = JSON.parse(el ? el.textContent : "{}"); } catch (e) { DATA = {}; }
    DATA.rows = DATA.rows || [];
    return DATA;
  }

  function fmt(n, dg) {
    return Number(n).toLocaleString("en-US", { minimumFractionDigits: dg, maximumFractionDigits: dg });
  }

  // אותו עיגול כמו money() ב-offex.py, כדי שהסכום בתמונה ייראה כמו בעמוד.
  function money(v) {
    if (!v) { return "—"; }
    if (v >= 1e9) { return fmt(v / 1e9, 2) + " מיליארד ₪"; }
    if (v >= 1e6) { return fmt(v / 1e6, 1) + " מ׳ ₪"; }
    if (v >= 1e3) { return fmt(v / 1e3, 0) + " א׳ ₪"; }
    return fmt(v, 0) + " ₪";
  }

  function dmy(iso) { return iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4); }
  function dayName(iso) {
    var dt = new Date(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
    return "יום " + WEEKDAYS[dt.getDay()];
  }
  function uniq(a) {
    var seen = {}, out = [];
    a.forEach(function (v) { if (v && !seen[v]) { seen[v] = 1; out.push(v); } });
    return out;
  }
  function bySignificance(a, b) {
    var pa = a.pn == null ? -1 : a.pn, pb = b.pn == null ? -1 : b.pn;
    return (pb - pa) || ((b.vn || 0) - (a.vn || 0));
  }

  function reportsCard(scope, key) {
    var rows = data().rows.filter(function (r) {
      return scope === "day" ? r.d === key : (r.d || "").slice(0, 7) === key;
    });
    if (!rows.length) { return null; }
    var counted = rows.filter(function (r) { return r.cnt; });
    var vol = sum(counted.map(function (r) { return r.vn || 0; }));
    var buys = rows.filter(function (r) { return r.dir === "buy"; }).length;
    var cos = uniq(rows.map(function (r) { return r.co; }));
    var holders = uniq(rows.map(function (r) { return r.who; }));

    var notes = [];
    var big = counted.filter(function (r) { return r.vn; }).sort(function (a, b) { return b.vn - a.vn; })[0];
    if (big) {
      notes.push("הגדולה בהיקף: " + big.co + " — " + (big.who || "מדווח") +
        (big.dir === "buy" ? " רכש" : " מכר") + " ב-" + big.v + ".");
    }
    var share = counted.filter(function (r) { return r.pn; }).sort(bySignificance)[0];
    if (share && (!big || share !== big)) {
      notes.push("החלק הגדול ביותר מההון: " + share.co + " — " + share.pct + " מהון המניות (" +
        (share.who || "מדווח") + ").");
    }
    if (scope === "month") {
      var per = {};
      rows.forEach(function (r) { per[r.co] = (per[r.co] || 0) + 1; });
      var busy = Object.keys(per).sort(function (a, b) { return per[b] - per[a]; })[0];
      if (busy && per[busy] > 2) {
        notes.push("החברה עם מירב הדיווחים: " + busy + " — " + per[busy] + " דיווחים.");
      }
      var bb = rows.filter(function (r) { return r.kind === "buyback"; }).length;
      if (bb) { notes.push("רכישה עצמית של חברות במניותיהן (ת085): " + bb + " דיווחים."); }
    }

    // **היום — כל הדיווחים; החודש — הבולטים שבהם.** חודש עמוס הוא 60–80 דיווחים,
    // ותמונה של כולם יצאה בגובה 10,676 פיקסלים: כשהיא מוקטנת לתצוגה ברשת
    // חברתית אי אפשר לקרוא בה שורה. תמונת החודש מציגה את הדיווחים עם החלק
    // הגדול מההון, ואומרת במפורש כמה נשארו בחוץ. הצד השני של עסקה שכבר מוצגת
    // והגשה חוזרת אינם תופסים שורה שנייה.
    var groups, moreText = "";
    if (scope === "day") {
      groups = [{ label: "", rows: rows.slice().sort(bySignificance) }];
    } else {
      var uniqueRows = rows.filter(function (r) { return !r.other && !r.restated; });
      var ranked = uniqueRows.slice().sort(bySignificance);
      var shown = ranked.slice(0, MONTH_TOP);
      groups = [{ label: "", rows: shown }];
      var rest = ranked.length - shown.length, dup = rows.length - uniqueRows.length;
      if (rest > 0) {
        moreText = "ועוד " + rest + " דיווחים בחודש, בחלק קטן יותר מההון.";
      }
      if (dup > 0) {
        moreText += (moreText ? " " : "") + (dup === 1 ? "דיווח אחד נוסף הוא" : dup + " דיווחים נוספים הם") +
          " הצד השני של עסקה שמוצגת או הגשה חוזרת.";
      }
    }

    var blocks = [{ type: "stats", items: [
      { label: "דיווחים", value: String(rows.length), cap: buys + " רכישה · " + (rows.length - buys) + " מכירה" },
      { label: "היקף", value: money(vol), cap: "בלי ספירה כפולה" },
      { label: "חברות", value: String(cos.length), cap: holders.length + " מדווחים" }
    ] }];
    if (notes.length && (scope === "month" || rows.length > 2)) {
      blocks.push({ type: "notes", title: scope === "month" ? "עיקרי החודש" : "עיקרי היום", items: notes });
    }
    blocks.push(scope === "month"
      ? { type: "reports", title: groups[0].rows.length + " הדיווחים עם החלק הגדול מההון", groups: groups,
          cols: [["היקף", "v"], ["מההון", "pct"], ["החזקה אחרי", "after"]], dates: true, moreText: moreText }
      : { type: "reports", title: "הדיווחים", groups: groups });
    var month = MONTHS[+key.slice(5, 7) - 1] + " " + key.slice(0, 4);
    return {
      kicker: "דיווחי בעלי עניין · עסקאות מחוץ לבורסה",
      title: scope === "day" ? dayName(key) + " · " + dmy(key) : month,
      sub: scope === "day"
        ? "כל הדיווחים במאיה על עסקאות מחוץ לבורסה שבוצעו ביום זה, מהחלק הגדול בהון אל הקטן."
        : "הדיווחים במאיה על עסקאות מחוץ לבורסה שבוצעו בחודש — סיכום, עיקרים, והדיווחים עם החלק הגדול מהון החברה.",
      blocks: blocks,
      source: SRC_MAYA,
      file: "tlv-offex-" + key
    };
  }

  // ---------------------------------------------------------------- הורדה

  function save(c, name, fail) {
    // toBlob מחזיר null כשהקנבס גדול מדי לדפדפן. בלי הבדיקה הכפתור אמר
    // "התמונה הורדה" ושום קובץ לא נוצר.
    c.toBlob(function (b) {
      if (!b) { fail(); return; }
      var u = URL.createObjectURL(b), a = document.createElement("a");
      a.href = u; a.download = name; document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(u); }, 1500);
    }, "image/png");
  }

  function label(btn, text) {
    var s = btn.querySelector(".lbl");
    if (s) { s.textContent = text; } else { btn.textContent = text; }
  }

  function cardFor(btn) {
    var key = btn.getAttribute("data-key");
    if (key) {
      var el = document.getElementById("otc-" + key);
      if (!el) { return null; }
      try { return JSON.parse(el.textContent); } catch (e) { return null; }
    }
    if (btn.getAttribute("data-day")) { return reportsCard("day", btn.getAttribute("data-day")); }
    if (btn.getAttribute("data-month")) { return reportsCard("month", btn.getAttribute("data-month")); }
    return null;
  }

  Array.prototype.forEach.call(document.querySelectorAll("button.otc-png"), function (b) {
    b.addEventListener("click", function () {
      if (b.disabled) { return; }
      var lblEl = b.querySelector(".lbl"), was = lblEl ? lblEl.textContent : b.textContent;
      b.disabled = true;
      label(b, "מייצא…");
      function reset(text) {
        label(b, text);
        setTimeout(function () { label(b, was); b.disabled = false; }, 2400);
      }
      fontsReady().then(function () {
        var d = cardFor(b);
        if (!d) { reset("אין נתונים"); return; }
        save(render(d), (d.file || "tlv-otc") + ".png", function () {
          if (window.console) { console.error("otc export: toBlob returned null"); }
          reset("הייצוא נכשל");
        });
        reset("התמונה הורדה");
      }).catch(function (e) {
        // הכשל נאמר לקונסולה. בליעה מוחלטת הפכה באג בציור לכפתור שאינו מגיב.
        if (window.console) { console.error("otc export", e); }
        reset("הייצוא נכשל");
      });
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll("button.otc-copy"), function (b) {
    b.addEventListener("click", function () {
      var el = document.getElementById("tw-" + b.getAttribute("data-key"));
      if (!el) { return; }
      var t = (el.textContent || "").trim(), was = b.textContent;
      function done(msg) {
        b.textContent = msg;
        setTimeout(function () { b.textContent = was; }, 2200);
      }
      // דחייה של ה-clipboard נופלת לבחירת הטקסט, כדי שאפשר יהיה להעתיק ידנית.
      function pick() {
        try {
          var r = document.createRange();
          r.selectNodeContents(el);
          var sel = window.getSelection();
          sel.removeAllRanges(); sel.addRange(r);
          done("סומן — Ctrl+C");
        } catch (e) { done(was); }
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t).then(function () { done("הועתק"); }, pick);
        return;
      }
      pick();
    });
  });

  // חשוף לבדיקה: מציירים כרטיס ומשווים אותו לטבלה שבעמוד, בלי להוריד קובץ.
  window.tlvRender = render;
  window.tlvReportsCard = reportsCard;
  window.tlvFontsReady = fontsReady;
})();
