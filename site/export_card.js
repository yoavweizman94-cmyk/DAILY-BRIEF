/* ייצוא תמונות — עמוד העסקאות מחוץ לבורסה.
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
 */
(function () {
  "use strict";

  var W0 = 1200, WMAX = 1680, PAD = 56, GAP = 30;
  var C = {
    top: "#0d222c", bottom: "#07131a",
    panel: "#0f2531", band: "#0b1d26", hair: "#16303b", line: "#25444f",
    text: "#eef4f6", muted: "#a2b6bf", faint: "#718994",
    accent: "#6cc3e0", accent2: "#3d8db3",
    up: "#56d294", down: "#f47d70", warn: "#e8b35d",
    upBg: "rgba(86,210,148,0.15)", downBg: "rgba(244,125,112,0.16)",
    warnBg: "rgba(232,179,93,0.14)", zebra: "rgba(255,255,255,0.025)"
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

  // ---------------------------------------------------------------- גופנים

  var fontsP = null;
  function fontsReady() {
    if (fontsP) { return fontsP; }
    if (!document.fonts || !document.fonts.load) {
      fontsP = Promise.resolve();
      return fontsP;
    }
    // הטקסט לדוגמה קובע איזו תת-קבוצה של הגופן נטענת. בלי אותיות עבריות
    // Google Fonts טוען רק את הלטינית, והעברית נופלת לגופן המערכת.
    var he = "אבגדהוזחטיכלמנסעפצקרשת", num = "0123456789.,%+-₪";
    var want = [[F(900, 20, SERIF), "TLV TASE View"], [F(700, 20, SERIF), he],
      [F(400, 20), he], [F(600, 20), he], [F(700, 20), he],
      [F(500, 20, MONO), num], [F(600, 20, MONO), num]];
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
    x.font = F(o.w, o.s, MONO);
    if (!p) { return x.measureText(String(v == null ? "" : v)).width; }
    var nw = x.measureText(p.n).width;
    x.font = unitFont(o);
    return nw + Math.round(o.s * 0.3) + x.measureText(p.u).width;
  }
  function drawVal(x, v, right, y, o) {
    var p = numParts(v), t = String(v == null ? "" : v);
    x.direction = "ltr"; x.textAlign = "right";
    x.font = F(o.w, o.s, MONO); x.fillStyle = o.color;
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

  // כותרת גוש: תווית ואחריה קו דק עד הקצה השני.
  var SECTION_H = 50;
  function section(x, title, g, y) {
    x.direction = "rtl"; x.textAlign = "right";
    x.font = F(700, 17); x.fillStyle = C.muted;
    x.fillText(title, g.right, y + 22);
    var w = x.measureText(title).width;
    x.fillStyle = C.hair;
    x.fillRect(g.left, y + 16, Math.max(0, g.inner - w - 18), 1);
  }

  // ---------------------------------------------------------------- כותרת

  function header(x, d, g, draw) {
    var inner = g.inner, ts = 50, lines;
    for (;;) {
      x.font = F(700, ts, SERIF);
      lines = wrap(x, d.title || "", inner);
      if (lines.length === 1 || ts <= 34) { break; }
      ts -= 2;
    }
    var lh = Math.round(ts * 1.2);
    x.font = F(400, 20);
    var sub = d.sub ? wrap(x, d.sub, Math.min(inner, 900)) : [];

    // מיקום אחד לשני המעברים: אותו y מצטבר מודד את הגובה ומצייר.
    var y = g.top;
    if (draw) {
      x.direction = "ltr"; x.textAlign = "right";
      x.fillStyle = C.accent; x.font = F(900, 30, SERIF);
      x.fillText("TLV TASE View", g.right, y + 30);
      x.textAlign = "left"; x.fillStyle = C.faint; x.font = F(500, 15, MONO);
      x.fillText("tlvtaseview.com", g.left, y + 26);
      x.fillStyle = C.hair; x.fillRect(g.left, y + 50, inner, 1);
    }
    y += 50 + 42;
    x.direction = "rtl"; x.textAlign = "right";
    if (d.kicker) {
      if (draw) {
        x.fillStyle = C.accent; x.font = F(700, 18);
        x.fillText(d.kicker, g.right, y);
      }
      y += 18;
    }
    y += Math.round(ts * 0.98);
    lines.forEach(function (ln, k) {
      if (draw) {
        x.fillStyle = C.text; x.font = F(700, ts, SERIF);
        x.fillText(ln, g.right, y);
      }
      if (k < lines.length - 1) { y += lh; }
    });
    if (sub.length) {
      y += 40;
      sub.forEach(function (ln, k) {
        if (draw) {
          x.fillStyle = C.muted; x.font = F(400, 20);
          x.fillText(ln, g.right, y);
        }
        if (k < sub.length - 1) { y += 30; }
      });
    }
    y += 14;
    return y - g.top;
  }

  // ---------------------------------------------------------------- גושים

  // אריחי סיכום: תווית, מספר, ושורת הקשר אופציונלית.
  function statsBlock(x, b, g, draw) {
    var items = b.items || [];
    if (!items.length) { return 0; }
    var gap = 14, n = items.length;
    var hasCap = items.some(function (it) { return it.cap; });
    var h = hasCap ? 116 : 94;
    if (!draw) { return h; }
    var w = (g.inner - gap * (n - 1)) / n;
    items.forEach(function (it, i) {
      var px = g.right - w - i * (w + gap), py = g.top;
      x.fillStyle = C.panel; rr(x, px, py, w, h, 12); x.fill();
      x.strokeStyle = C.line; x.lineWidth = 1; x.stroke();
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.muted; x.font = F(600, 16);
      x.fillText(it.label, px + w - 20, py + 32);
      var v = String(it.value == null ? "—" : it.value), s = 36;
      var o = { w: 600, s: s, us: 0.56, uw: 600 };
      while (s > 16 && valWidth(x, v, o) > w - 40) { s -= 1; o.s = s; }
      o.color = it.tone === "up" ? C.up : it.tone === "down" ? C.down : C.text;
      o.ucolor = it.tone ? o.color : C.muted;
      drawVal(x, v, px + w - 20, py + 76, o);
      if (it.cap) {
        x.direction = "rtl"; x.fillStyle = C.faint; x.font = F(400, 15);
        x.fillText(it.cap, px + w - 20, py + 100);
      }
    });
    return h;
  }

  // עיקרי התקופה: משפטים מחושבים, כל אחד בנקודה משלו.
  function notesBlock(x, b, g, draw) {
    var items = (b.items || []).filter(function (t) { return t; });
    if (!items.length) { return 0; }
    var padX = 26, padY = 22, LH = 32, textW = g.inner - padX * 2 - 24;
    x.font = F(400, 20);
    var wrapped = items.map(function (t) { return wrap(x, isolateSigned(t), textW); });
    var h = padY * 2 + (b.title ? 38 : 0) +
      sum(wrapped.map(function (w) { return w.length * LH; })) + 10 * (wrapped.length - 1);
    if (!draw) { return h; }
    x.fillStyle = C.panel; rr(x, g.left, g.top, g.inner, h, 12); x.fill();
    x.strokeStyle = C.line; x.lineWidth = 1; x.stroke();
    var y = g.top + padY;
    x.direction = "rtl"; x.textAlign = "right";
    if (b.title) {
      x.fillStyle = C.accent; x.font = F(700, 17);
      x.fillText(b.title, g.right - padX, y + 20);
      y += 38;
    }
    wrapped.forEach(function (lines) {
      x.fillStyle = C.accent;
      x.beginPath(); x.arc(g.right - padX - 5, y + 14, 3.5, 0, Math.PI * 2); x.fill();
      x.fillStyle = C.text; x.font = F(400, 20);
      lines.forEach(function (ln, k) { x.fillText(ln, g.right - padX - 24, y + 22 + k * LH); });
      y += lines.length * LH + 10;
    });
    return h;
  }

  function cellFont(c, i, v, bold) {
    if (c[2] === "ltr") {
      return F(bold ? 700 : (/^[+\-−]/.test(v) || c[1] === "value") ? 600 : 500, 19, MONO);
    }
    if (i === 0) { return F(700, 20); }
    return F(bold ? 700 : 400, 19);
  }

  function cellVal(c, v, bold) {
    var signed = /^[+\-−]/.test(v);
    var color = signColor(v, c[1] === "value" || bold ? C.text : C.muted);
    return { w: bold ? 700 : (signed || c[1] === "value") ? 600 : 500, s: 19, color: color,
      ucolor: signed ? color : C.muted };
  }

  function cellColor(c, i, v, bold) {
    if (bold || i === 0) { return C.text; }
    var s = signColor(v, null);
    if (s) { return s; }
    if (c[1] === "value") { return C.text; }
    return C.muted;
  }

  function tableNat(x, b) {
    if (b._nat) { return b._nat; }
    var cols = b.cols, rows = b.rows || [];
    var all = b.totalRow ? rows.concat([b.totalRow]) : rows;
    var last = b.totalRow ? all.length - 1 : -1, GAPC = 30;
    var nat = [], min = [];
    cols.forEach(function (c, i) {
      x.font = F(600, 15);
      var head = x.measureText(c[0]).width, full = head, word = head;
      all.forEach(function (r, n) {
        var v = r[c[1]] == null ? "" : String(r[c[1]]);
        if (c[2] === "ltr") {
          full = Math.max(full, valWidth(x, v, cellVal(c, v, n === last)));
          return;
        }
        x.font = cellFont(c, i, v, n === last);
        full = Math.max(full, x.measureText(v).width);
        v.split(" ").forEach(function (w) { word = Math.max(word, x.measureText(w).width); });
      });
      nat.push(Math.ceil(full) + GAPC);
      // עמודת מספרים לעולם אינה נשברת. עמודת טקסט נשברת עד המילה הרחבה בה,
      // ומעבר ל-340 פיקסלים גם מילה נשברת — לפי תווים, בלי לאבד תו.
      min.push(c[2] === "rtl"
        ? Math.max(Math.ceil(head) + GAPC, Math.min(Math.ceil(word) + GAPC, 340))
        : Math.ceil(full) + GAPC);
    });
    b._nat = { all: all, last: last, nat: nat, min: min, sumNat: sum(nat), sumMin: sum(min) };
    return b._nat;
  }

  function tableBlock(x, b, g, draw) {
    if (!b.cols || !(b.rows || []).length) { return 0; }
    var T = tableNat(x, b), inner = g.inner, LINE = 29, HB = 48;
    var wid;
    if (T.sumNat <= inner) {
      wid = T.nat.slice();
      wid[0] += inner - T.sumNat;
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
        var v = r[c[1]] == null ? "" : String(r[c[1]]);
        x.font = cellFont(c, i, v, bold);
        return { v: v, lines: c[2] === "rtl" ? wrap(x, v, wid[i] - 30) : [v] };
      });
      var tall = cells.reduce(function (m, c) { return Math.max(m, c.lines.length); }, 1);
      return { cells: cells, bold: bold, h: 22 + LINE * tall };
    });
    x.font = F(400, 18);
    var more = b.moreText ? wrap(x, b.moreText, inner) : [];
    var th = b.title ? SECTION_H : 0;
    var h = th + HB + sum(rows.map(function (r) { return r.h; })) +
      (more.length ? 16 + more.length * 28 : 0) + (b.totalRow ? 10 : 0);
    if (!draw) { return h; }

    var y = g.top;
    if (b.title) { section(x, b.title, g, y); y += th; }
    x.fillStyle = C.band; rr(x, g.left, y, inner, HB, 10); x.fill();
    var cx = g.right;
    x.direction = "rtl"; x.textAlign = "right";
    x.font = F(600, 15); x.fillStyle = C.muted;
    b.cols.forEach(function (c, i) {
      // כותרת עמודה היא טקסט עברי גם כשהערכים בה LTR.
      x.fillText(c[0], cx - 14, y + 30);
      cx -= wid[i];
    });
    y += HB;

    // שורות; אחריהן שורת ה"ועוד", ורק אז שורת הסך — הסדר שבעמוד.
    var moreDone = false;
    function drawMore() {
      moreDone = true;
      if (!more.length) { return; }
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.muted; x.font = F(400, 18);
      more.forEach(function (ln, k) { x.fillText(ln, g.right - 14, y + 30 + k * 28); });
      y += 16 + more.length * 28;
    }
    rows.forEach(function (row, n) {
      if (row.bold) {
        drawMore();
        y += 10;
        x.fillStyle = C.line; x.fillRect(g.left, y, inner, 1.5);
      }
      var vx = g.right;
      row.cells.forEach(function (cell, i) {
        var c = b.cols[i];
        if (c[2] === "ltr") {
          drawVal(x, cell.v, vx - 14, y + 34, cellVal(c, cell.v, row.bold));
        } else {
          x.direction = c[2]; x.textAlign = "right";
          x.font = cellFont(c, i, cell.v, row.bold);
          x.fillStyle = cellColor(c, i, cell.v, row.bold);
          cell.lines.forEach(function (ln, k) { x.fillText(ln, vx - 14, y + 34 + k * LINE); });
        }
        vx -= wid[i];
      });
      y += row.h;
      if (!row.bold && n < rows.length - 1 && !(rows[n + 1] && rows[n + 1].bold)) {
        x.fillStyle = C.hair; x.fillRect(g.left + 8, y, inner - 16, 1);
      }
    });
    if (!moreDone) { drawMore(); }
    return h;
  }

  // פסים אופקיים: שם, פס יחסי, ושני מספרים.
  function barsBlock(x, b, g, draw) {
    var rows = b.rows || [];
    if (!rows.length) { return 0; }
    var th = b.title ? SECTION_H : 0;
    var PV = { w: 600, s: 20, color: C.accent }, MV = { w: 400, s: 16, color: C.faint, uw: 500 };
    var pvW = Math.max.apply(null, rows.map(function (r) { return valWidth(x, r.pctText, PV); })) + 30;
    var mvW = Math.max.apply(null, rows.map(function (r) { return valWidth(x, r.volText || "", MV); })) + 26;
    var labMax = Math.min(measureMax(x, F(600, 19), rows.map(function (r) { return r.label; })) + 26,
      g.inner * 0.36);
    x.font = F(600, 19);
    var lays = rows.map(function (r) {
      var lines = wrap(x, r.label, labMax - 26);
      return { lines: lines, h: Math.max(56, 24 + lines.length * 26) };
    });
    var h = th + sum(lays.map(function (l) { return l.h; }));
    if (!draw) { return h; }
    var y = g.top;
    if (b.title) { section(x, b.title, g, y); y += th; }
    var mx = Math.max.apply(null, rows.map(function (r) { return r.pct || 0; })) || 1;
    var barR = g.right - labMax, barW = g.inner - labMax - pvW - mvW - 18;
    rows.forEach(function (r, i) {
      var L = lays[i], cy = y + L.h / 2;
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.text; x.font = F(600, 19);
      var ly = cy - (L.lines.length - 1) * 13 + 7;
      L.lines.forEach(function (ln, k) { x.fillText(ln, g.right, ly + k * 26); });
      x.fillStyle = C.band; rr(x, barR - barW, cy - 7, barW, 14, 7); x.fill();
      var fw = Math.max(8, barW * (r.pct || 0) / mx);
      var gr = x.createLinearGradient(barR, 0, barR - barW, 0);
      gr.addColorStop(0, C.accent); gr.addColorStop(1, C.accent2);
      x.fillStyle = gr; rr(x, barR - fw, cy - 7, fw, 14, 7); x.fill();
      drawVal(x, r.pctText, g.left + mvW + pvW - 12, cy + 7, PV);
      drawVal(x, r.volText || "", g.left + mvW - 12, cy + 6, MV);
      y += L.h;
      if (i < rows.length - 1) { x.fillStyle = C.hair; x.fillRect(g.left, y, g.inner, 1); }
    });
    return h;
  }

  // עמודות לאורך זמן: הזמן זורם משמאל לימין, והיום האחרון מודגש.
  function columnsBlock(x, b, g, draw) {
    var items = b.items || [];
    if (items.length < 2) { return 0; }
    var th = b.title ? SECTION_H : 0, CH = 230, XL = 34;
    var h = th + CH + XL;
    if (!draw) { return h; }
    var y = g.top;
    if (b.title) { section(x, b.title, g, y); y += th; }
    var vals = items.map(function (it) { return it.value || 0; });
    var mx = Math.max.apply(null, vals.concat([b.median || 0])) || 1;
    var axisW = 96, left = g.left + axisW, right = g.right, plotW = right - left;
    var top = y + 16, bot = y + CH, ph = bot - top;
    function Y(v) { return bot - v / mx * ph; }
    x.fillStyle = C.hair;
    [0, 0.5, 1].forEach(function (f) { x.fillRect(left, Y(mx * f), plotW, 1); });
    var AX = { w: 400, s: 13, color: C.faint, uw: 500, us: 0.9 };
    drawVal(x, b.maxText || "", left - 12, Y(mx) + 5, AX);
    drawVal(x, "0", left - 12, bot + 4, AX);
    var n = items.length, slot = plotW / n, bw = Math.min(34, slot * 0.64);
    items.forEach(function (it, i) {
      var cx = left + slot * (i + 0.5), v = vals[i], last = i === n - 1;
      var yv = Y(v), hh = Math.max(2, bot - yv);
      x.fillStyle = last ? C.accent : "rgba(108,195,224,0.36)";
      rr(x, cx - bw / 2, bot - hh, bw, hh, Math.min(5, bw / 2)); x.fill();
      if (i % 3 === (n - 1) % 3) {
        x.textAlign = "center"; x.fillStyle = last ? C.text : C.faint;
        x.font = F(last ? 600 : 400, 13, MONO);
        x.fillText(it.label, cx, bot + 24);
      }
      if (last && it.text) {
        var LV = { w: 600, s: 15, color: C.text, ucolor: C.muted, us: 0.85 };
        drawVal(x, it.text, Math.min(right, cx + valWidth(x, it.text, LV) / 2), yv - 10, LV);
      }
    });
    if (b.median) {
      var my = Y(b.median);
      x.strokeStyle = C.muted; x.lineWidth = 1.2; x.setLineDash([6, 5]);
      x.beginPath(); x.moveTo(left, my); x.lineTo(right, my); x.stroke();
      x.setLineDash([]);
      x.direction = "rtl"; x.textAlign = "left";
      x.font = F(600, 14);
      var mw = x.measureText(b.medianText || "").width;
      x.fillStyle = C.band; rr(x, left + 2, my - 30, mw + 16, 24, 6); x.fill();
      x.fillStyle = C.muted;
      x.fillText(b.medianText || "", left + 10, my - 13);
    }
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

  function reportsNeed(x, b) {
    var L = reportsLayout(x, b, 0);
    return sum(L.colW) + 16 + 470;
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

  function reportsBlock(x, b, g, draw) {
    var groups = (b.groups || []).filter(function (grp) { return (grp.rows || []).length; });
    if (!groups.length) { return 0; }
    var L = reportsLayout(x, b, g.inner), HB = 46, GH = 56;
    var th = b.title ? SECTION_H : 0;
    var lays = groups.map(function (grp) {
      return grp.rows.map(function (r) { return reportRow(x, r, L.zone, b.dates); });
    });
    x.font = F(400, 18);
    var more = b.moreText ? wrap(x, b.moreText, g.inner - 28) : [];
    var h = th + HB + sum(groups.map(function (grp, gi) {
      return (grp.label ? GH : 0) + sum(lays[gi].map(function (l) { return l.h; }));
    })) + (more.length ? 18 + more.length * 28 : 0);
    if (!draw) { return h; }

    var y = g.top;
    if (b.title) { section(x, b.title, g, y); y += th; }
    x.fillStyle = C.band; rr(x, g.left, y, g.inner, HB, 10); x.fill();
    x.direction = "rtl"; x.textAlign = "right";
    x.font = F(600, 15); x.fillStyle = C.muted;
    x.fillText("חברה · מדווח", g.right - 14, y + 29);
    var colRight = [], cx = g.left + sum(L.colW);
    rcols(b).forEach(function (c, i) {
      colRight.push(cx);
      x.fillText(c[0], cx - 12, y + 29);
      cx -= L.colW[i];
    });
    y += HB;

    groups.forEach(function (grp, gi) {
      if (grp.label) {
        x.direction = "rtl"; x.textAlign = "right";
        x.fillStyle = C.accent; x.font = F(700, 19);
        x.fillText(grp.label, g.right, y + 36);
        var lw = x.measureText(grp.label).width;
        if (grp.count) {
          x.fillStyle = C.faint; x.font = F(400, 16);
          x.fillText(grp.count, g.right - lw - 14, y + 36);
          lw += 14 + x.measureText(grp.count).width;
        }
        x.fillStyle = C.line;
        x.fillRect(g.left, y + 30, Math.max(0, g.inner - lw - 20), 1);
        y += GH;
      }
      grp.rows.forEach(function (r, ri) {
        var R = lays[gi][ri], zr = g.right, base = y + 18 + 22;
        x.direction = "rtl"; x.textAlign = "right";
        x.fillStyle = C.text; x.font = F(700, 21);
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
          o.color = dim ? C.faint : c[1] === "pct" ? C.accent : c[1] === "v" ? C.text : C.muted;
          o.ucolor = dim ? C.faint : C.muted;
          drawVal(x, v, colRight[i] - 12, base, o);
        });
        y += R.h;
        if (ri < grp.rows.length - 1) { x.fillStyle = C.hair; x.fillRect(g.left + 8, y, g.inner - 16, 1); }
      });
    });
    if (more.length) {
      x.fillStyle = C.line; x.fillRect(g.left, y + 4, g.inner, 1);
      x.direction = "rtl"; x.textAlign = "right";
      x.fillStyle = C.muted; x.font = F(400, 18);
      more.forEach(function (ln, k) { x.fillText(ln, g.right - 14, y + 36 + k * 28); });
    }
    return h;
  }

  var BLOCKS = { stats: statsBlock, notes: notesBlock, table: tableBlock, bars: barsBlock,
    columns: columnsBlock, reports: reportsBlock };

  // ---------------------------------------------------------------- תחתית

  function footer(x, d, g, draw) {
    x.font = F(400, 16);
    var src = wrap(x, d.source || SRC_TASE, g.inner - 220);
    var h = 36 + src.length * 26 + 34;
    if (!draw) { return h; }
    var y = g.top;
    x.fillStyle = C.hair; x.fillRect(g.left, y, g.inner, 1);
    y += 36;
    x.direction = "rtl"; x.textAlign = "right";
    x.fillStyle = C.faint; x.font = F(400, 16);
    src.forEach(function (ln, k) { x.fillText(ln, g.right, y + k * 26); });
    y += src.length * 26 + 16;
    x.direction = "ltr"; x.textAlign = "right";
    x.fillStyle = C.accent; x.font = F(700, 18);
    x.fillText("© @Cigarbutthunte7", g.right, y);
    var now = new Date();
    var stamp = "הופק " + ("0" + now.getDate()).slice(-2) + "/" + ("0" + (now.getMonth() + 1)).slice(-2) +
      "/" + now.getFullYear();
    x.direction = "rtl"; x.textAlign = "left";
    x.fillStyle = C.faint; x.font = F(400, 15);
    x.fillText(stamp, g.left, y);
    return h;
  }

  function background(x, W, H) {
    var g = x.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, C.top); g.addColorStop(1, C.bottom);
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    var glow = x.createRadialGradient(W - 140, 20, 0, W - 140, 20, 760);
    glow.addColorStop(0, "rgba(108,195,224,0.12)");
    glow.addColorStop(1, "rgba(108,195,224,0)");
    x.fillStyle = glow; x.fillRect(0, 0, W, Math.min(H, 900));
    var bar = x.createLinearGradient(W, 0, 0, 0);
    bar.addColorStop(0, C.accent); bar.addColorStop(1, C.accent2);
    x.fillStyle = bar; x.fillRect(0, 0, W, 5);
  }

  // ---------------------------------------------------------------- כרטיס

  function render(d) {
    var probe = document.createElement("canvas").getContext("2d");
    var blocks = (d.blocks || []).filter(function (b) { return BLOCKS[b.type]; });
    var inner = W0 - PAD * 2, minInner = 0;
    blocks.forEach(function (b) {
      if (b.type === "table" && b.cols && (b.rows || []).length) {
        var T = tableNat(probe, b);
        inner = Math.max(inner, Math.min(T.sumNat, WMAX - PAD * 2));
        minInner = Math.max(minInner, T.sumMin);
      }
      if (b.type === "reports") {
        inner = Math.max(inner, Math.min(reportsNeed(probe, b), WMAX - PAD * 2));
      }
    });
    inner = Math.max(inner, minInner);
    var W = inner + PAD * 2;
    var g = { left: PAD, right: W - PAD, inner: inner, top: PAD };

    var H = PAD + header(probe, d, g, false) + 14;
    blocks.forEach(function (b) {
      var bh = BLOCKS[b.type](probe, b, g, false);
      if (bh) { H += bh + GAP; }
    });
    H += 6 + footer(probe, d, g, false) + PAD - 16;

    // **קנבס גדול מדי יוצא ריק, בלי שגיאה.** iOS Safari מגביל את שטח הקנבס
    // לכ-16.7 מיליון פיקסלים, ומעבר לכך toBlob מחזיר null. הרזולוציה יורדת
    // במקום שהתמונה תיעלם.
    var S = Math.min(2, Math.sqrt(16e6 / (W * H)), 16000 / W, 16000 / H);
    var cv = document.createElement("canvas");
    cv.width = Math.round(W * S); cv.height = Math.round(H * S);
    var x = cv.getContext("2d");
    x.scale(S, S);
    x.textBaseline = "alphabetic";
    background(x, W, H);
    g.top = PAD;
    g.top += header(x, d, g, true) + 14;
    blocks.forEach(function (b) {
      var bh = BLOCKS[b.type](x, b, g, true);
      if (bh) { g.top += bh + GAP; }
    });
    g.top += 6;
    footer(x, d, g, true);
    return cv;
  }

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
