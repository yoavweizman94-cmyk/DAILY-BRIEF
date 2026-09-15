# -*- coding: utf-8 -*-
"""עמוד רשימת הכיסוי — כל החברות, ולבעלים גם דירוג חשיבות.

הרשימה נבנית כאן מ-config/companies.yaml ומוגשת כ-HTML מלא, כך שהיא
נקראת גם אם ה-JS נכשל. ה-JS מוסיף חיפוש, סינון ומיון — ולבעלים בלבד את
עמודת החשיבות.

**הדירוג אינו בריפו.** הריפו ציבורי, והדירוג הוא המבט הפנימי של הבעלים
על החברות. הוא נשמר ב-KV של האתר דרך site/functions/api/importance.js,
שמאמת סשן **וגם** שהכתובת היא OWNER_EMAIL. לקוח מחובר רואה את הרשימה
בלי העמודה, והקריאה ל-API מחזירה לו 403.
"""
import json
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "companies.yaml"

# מהחשובה לשולית. הסדר הזה הוא גם סדר הכפתורים — בעמוד RTL הדרגה
# הגבוהה עומדת מימין, במקום שבו העין מתחילה.
LEVELS = [(5, "ליבה"), (4, "גבוהה"), (3, "בינונית"), (2, "נמוכה"), (1, "שולית")]


def load() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}


def _label(profiles: dict, key: str) -> str:
    return (profiles.get(key) or {}).get("label") or key or "—"


SCRIPT = """<script>
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var table = $("cov-table");
  if (!table) { return; }
  var tbody = table.tBodies[0];
  var q = $("cov-q"), prof = $("cov-prof"), lvlSel = $("cov-lvl"), sortSel = $("cov-sort");
  var msg = $("cov-msg"), count = $("cov-count"), sum = $("cov-sum");
  var saveMsg = $("cov-save"), retry = $("cov-retry");
  var LEVELS = JSON.parse($("cov-levels").textContent);

  // נרמול לחיפוש: גרשיים, נקודות ומקפים נכתבים בכמה צורות (נדל"ן מול
  // נדל״ן, או.פי.סי מול או פי סי), וחיפוש מילולי היה מחמיץ התאמות ברורות.
  var STRIP = ['"', "'", "״", "׳", "`", ".", "-", ",", "(", ")"];
  function norm(s) {
    s = String(s || "").toLowerCase();
    STRIP.forEach(function (ch) { s = s.split(ch).join(" "); });
    return s.split(" ").filter(Boolean).join(" ");
  }

  var items = Array.prototype.map.call(tbody.rows, function (tr) {
    return { tr: tr, id: tr.getAttribute("data-id"), name: tr.getAttribute("data-name"),
             profile: tr.getAttribute("data-profile"), plabel: tr.getAttribute("data-plabel"),
             hay: norm(tr.getAttribute("data-search")) };
  });
  var byId = {};
  items.forEach(function (it) { byId[it.id] = it; });

  var owner = false, levels = {}, rev = 0, dirty = {}, timer = null,
      saving = false, again = false, conflicts = 0;

  function say(el, t, cls) { el.className = "msg " + (cls || ""); el.textContent = t || ""; }
  function two(n) { return ("0" + n).slice(-2); }
  function hm(iso) { var t = iso ? new Date(iso) : new Date(); return two(t.getHours()) + ":" + two(t.getMinutes()); }
  function dmhm(iso) { var t = new Date(iso); return two(t.getDate()) + "/" + two(t.getMonth() + 1) + " " + hm(iso); }

  function apply() {
    var nq = norm(q.value), p = prof.value, lv = owner ? lvlSel.value : "", mode = sortSel.value;
    var list = items.slice().sort(function (a, b) {
      if (mode === "imp") {
        var d = (levels[b.id] || 0) - (levels[a.id] || 0);
        if (d) { return d; }
      } else if (mode === "profile") {
        var c = a.plabel.localeCompare(b.plabel, "he");
        if (c) { return c; }
      }
      return a.name.localeCompare(b.name, "he");
    });
    var frag = document.createDocumentFragment(), shown = 0;
    list.forEach(function (it) {
      var ok = (!nq || it.hay.indexOf(nq) >= 0) && (!p || it.profile === p) &&
               (lv === "" || String(levels[it.id] || 0) === lv);
      it.tr.hidden = !ok;
      if (ok) { shown++; }
      frag.appendChild(it.tr);
    });
    tbody.appendChild(frag);
    count.textContent = shown === items.length
      ? items.length + " חברות"
      : "מוצגות " + shown + " מתוך " + items.length;
  }

  function paint(it) {
    var td = it.tr.querySelector("td.imp");
    if (!td) { return; }
    if (!td.firstChild) {
      var box = document.createElement("span");
      box.className = "lv-set";
      box.setAttribute("role", "group");
      box.setAttribute("aria-label", "חשיבות: " + it.name);
      LEVELS.forEach(function (l) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "lv";
        b.textContent = String(l[0]);
        b.title = l[0] + " · " + l[1];
        b.setAttribute("data-v", String(l[0]));
        box.appendChild(b);
      });
      td.appendChild(box);
    }
    var cur = levels[it.id] || 0;
    Array.prototype.forEach.call(td.querySelectorAll("button.lv"), function (b) {
      b.setAttribute("aria-pressed", Number(b.getAttribute("data-v")) === cur ? "true" : "false");
    });
  }

  function summary() {
    var n = {}, rated = 0;
    LEVELS.forEach(function (l) { n[l[0]] = 0; });
    items.forEach(function (it) {
      var v = levels[it.id];
      if (v) { n[v] = (n[v] || 0) + 1; rated++; }
    });
    sum.textContent = "דורגו " + rated + " מתוך " + items.length + " · " +
      LEVELS.map(function (l) { return l[1] + " " + n[l[0]]; }).join(" · ");
  }

  function read(r) {
    return r.text().then(function (t) {
      var d = null;
      try { d = JSON.parse(t); } catch (e) { d = null; }
      return { ok: r.ok, status: r.status, d: d };
    });
  }

  function pending() { return Object.keys(dirty).length > 0; }

  function schedule() {
    retry.hidden = true;
    say(saveMsg, "יש שינויים שטרם נשמרו…", "wait");
    if (timer) { clearTimeout(timer); }
    timer = setTimeout(function () { timer = null; save(false); }, 1500);
  }

  // **כל הדירוג נשלח בכל שמירה, יחד עם הגרסה שממנה התחיל.** שינוי בודד
  // שנשלח לבד היה נדרס בשקט אם לשונית אחרת שמרה בינתיים. כאן השרת מחזיר
  // 409 ואת המסמך העדכני, והשינויים שטרם נשמרו מכאן גוברים עליו.
  // השמירות מאוגדות כי ל-KV יש מכסת כתיבות יומית, משותפת עם ההתחברות.
  function save(keep) {
    if (saving) { again = true; return; }
    if (!pending()) { return; }
    var sent = dirty;
    dirty = {};
    saving = true;
    say(saveMsg, "שומר…", "wait");
    fetch("/api/importance", {
      method: "POST", keepalive: !!keep, credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ levels: levels, rev: rev })
    }).then(read).then(function (res) {
      saving = false;
      if (res.status === 409 && res.d && res.d.levels) {
        conflicts++;
        var merged = res.d.levels;
        Object.keys(sent).concat(Object.keys(dirty)).forEach(function (id) {
          if (levels[id]) { merged[id] = levels[id]; } else { delete merged[id]; }
          dirty[id] = true;
        });
        levels = merged;
        rev = Number(res.d.rev) || 0;
        items.forEach(paint);
        summary();
        if (conflicts > 3) {
          say(saveMsg, "הדירוג משתנה במקביל מלשונית אחרת. סגור אותה ונסה שוב.", "err");
          retry.hidden = false;
          return;
        }
        save(false);
        return;
      }
      if (!res.ok || !res.d) {
        Object.keys(sent).forEach(function (id) { dirty[id] = true; });
        say(saveMsg, "השמירה נכשלה: " + ((res.d && res.d.error) || "תשובה לא צפויה") +
            " (קוד " + res.status + "). השינויים עדיין כאן.", "err");
        retry.hidden = false;
        return;
      }
      conflicts = 0;
      retry.hidden = true;
      rev = Number(res.d.rev) || rev;
      say(saveMsg, "נשמר " + hm(res.d.updated), "ok");
      if (again || pending()) { again = false; schedule(); }
    }).catch(function (e) {
      saving = false;
      Object.keys(sent).forEach(function (id) { dirty[id] = true; });
      say(saveMsg, "השמירה נכשלה (" + ((e && e.message) || "שגיאת רשת") +
          "). השינויים עדיין כאן.", "err");
      retry.hidden = false;
    });
  }

  tbody.addEventListener("click", function (e) {
    if (!owner) { return; }
    var b = e.target && e.target.closest ? e.target.closest("button.lv") : null;
    if (!b) { return; }
    var tr = b.closest("tr"), id = tr && tr.getAttribute("data-id");
    if (!id || !byId[id]) { return; }
    var v = Number(b.getAttribute("data-v"));
    if (levels[id] === v) { delete levels[id]; } else { levels[id] = v; }
    dirty[id] = true;
    // המיון והסינון אינם מתעדכנים כאן בכוונה: שורה שקופצת ממקומה
    // ברגע שדירגת אותה היא דרך בטוחה לדרג בטעות את השכנה שלה.
    paint(byId[id]);
    summary();
    schedule();
  });

  retry.addEventListener("click", function () { conflicts = 0; save(false); });
  [q, prof, lvlSel, sortSel].forEach(function (el) {
    el.addEventListener(el === q ? "input" : "change", apply);
  });
  $("cov-form").addEventListener("submit", function (e) { e.preventDefault(); });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden && owner && pending()) {
      if (timer) { clearTimeout(timer); timer = null; }
      save(true);
    }
  });
  window.addEventListener("beforeunload", function (e) {
    if (owner && (pending() || saving)) { e.preventDefault(); e.returnValue = ""; }
  });

  function enableOwner() {
    owner = true;
    Array.prototype.forEach.call(table.querySelectorAll(".imp"), function (el) { el.hidden = false; });
    $("cov-lvl-wrap").hidden = false;
    $("cov-owner").hidden = false;
    var o = document.createElement("option");
    o.value = "imp";
    o.textContent = "חשיבות";
    sortSel.insertBefore(o, sortSel.firstChild);
    sortSel.value = "imp";
    items.forEach(paint);
    summary();
    apply();
  }

  apply();

  // **403 אינו תקלה, אבל גם אינו שקט.** לקוח אינו הבעלים ולכן אינו רואה
  // את העמודה — וזה נאמר בשורה אחת, כדי שבעלים שמחובר בחשבון אחר ידע
  // למה העמודה חסרה ולא יחשוב שהדירוג נמחק.
  fetch("/api/importance", { headers: { "Accept": "application/json" }, credentials: "same-origin" })
    .then(read)
    .then(function (res) {
      if (res.status === 401) { return; }
      if (res.status === 403 && res.d) {
        say(msg, res.d.ownerConfigured === false
          ? "דירוג החשיבות אינו זמין: לא הוגדרה כתובת בעלים בשירות."
          : "דירוג החשיבות מוצג לבעלי האתר בלבד.", "wait");
        return;
      }
      if (!res.d) {
        say(msg, "דירוג החשיבות לא נטען: השרת החזיר תשובה שאינה JSON (קוד " + res.status + ").", "err");
        return;
      }
      if (!res.ok) {
        say(msg, "דירוג החשיבות לא נטען: " + (res.d.error || "שגיאה") + " (קוד " + res.status + ").", "err");
        return;
      }
      levels = res.d.levels || {};
      rev = Number(res.d.rev) || 0;
      enableOwner();
      if (res.d.updated) { say(saveMsg, "עודכן לאחרונה " + dmhm(res.d.updated), "ok"); }
    })
    .catch(function (e) {
      say(msg, "דירוג החשיבות לא נטען (" + ((e && e.message) || "שגיאת רשת") + ").", "err");
    });
})();
</script>"""


def page(cfg: dict) -> str:
    cos = cfg.get("companies") or []
    profiles = cfg.get("sector_profiles") or {}
    if not cos:
        return ('<h1>רשימת הכיסוי</h1>'
                '<p class="lead">לא נמצאו חברות ב-config/companies.yaml.</p>')

    used = sorted({c.get("sector") or "" for c in cos}, key=lambda k: _label(profiles, k))
    missing_maya = sum(1 for c in cos if not c.get("maya_company_id"))

    rows = []
    for c in sorted(cos, key=lambda c: c.get("name_he") or ""):
        name = c.get("name_he") or ""
        tid = str(c.get("tase_id") or "")
        prof = c.get("sector") or ""
        search = " ".join([name, c.get("name_en") or ""]
                          + [str(a) for a in (c.get("aliases") or [])] + [tid])
        tags = []
        if c.get("generic_name"):
            tags.append('<span class="cov-tag" title="שם שהוא גם מילה רגילה — '
                        'מותאם רק בהקשר עסקי מובהק">שם גנרי</span>')
        if not c.get("maya_company_id"):
            tags.append('<span class="cov-tag warn" title="בלי מזהה מאיה הדיווחים '
                        'של החברה אינם נאספים">אין מזהה מאיה</span>')
        rows.append(
            f'<tr data-id="{escape(tid)}" data-name="{escape(name)}" '
            f'data-profile="{escape(prof)}" data-plabel="{escape(_label(profiles, prof))}" '
            f'data-search="{escape(search)}">'
            f'<td class="city">{escape(name)}{"".join(tags)}</td>'
            '<td class="imp" hidden></td>'
            f'<td>{escape(_label(profiles, prof))}</td>'
            f'<td>{escape(c.get("tase_sector") or "—")}</td>'
            f'<td dir="ltr">{escape(tid) or "—"}</td></tr>')

    opts = "".join(f'<option value="{escape(k)}">{escape(_label(profiles, k))}</option>'
                   for k in used)
    lvl_opts = "".join(f'<option value="{v}">{v} · {t}</option>' for v, t in LEVELS)
    warn = (f'<p class="msg warn">{missing_maya} חברות בלי מזהה מאיה, מסומנות בטבלה — '
            'הדיווחים שלהן עדיין אינם נאספים.</p>' if missing_maya else "")

    return "\n".join([
        '<h1>רשימת הכיסוי</h1>',
        f'<p class="lead">{len(cos)} חברות ב-{len(used)} פרופילי סקטור. הפרופיל קובע '
        'אילו דרייברים משפיעים על החברה — ולכן גם אילו ידיעות ענפיות נוגעות בה בלי '
        'שהוזכרה בשמה.</p>',
        warn,
        '<form class="srch" id="cov-form" autocomplete="off"><div class="row">'
        '<label class="grow">חיפוש'
        '<input type="search" id="cov-q" placeholder="שם, כינוי או מספר נייר"></label>'
        f'<label>פרופיל<select id="cov-prof"><option value="">הכל</option>{opts}</select></label>'
        '<label id="cov-lvl-wrap" hidden>חשיבות<select id="cov-lvl">'
        '<option value="">הכל</option><option value="0">לא דורגו</option>'
        + lvl_opts + '</select></label>'
        '<label>מיון<select id="cov-sort"><option value="name">שם</option>'
        '<option value="profile">פרופיל</option></select></label>'
        '</div></form>',
        '<p class="stamp" id="cov-count"></p>',
        '<div id="cov-owner" class="cov-owner" hidden>'
        '<p class="cov-legend">דרג כל חברה מ-5 (ליבה) עד 1 (שולית); לחיצה חוזרת על '
        'אותה דרגה מבטלת אותה. הדירוג נשמר אוטומטית, מוצג לך בלבד, ואינו חלק מהריפו '
        'הציבורי. המיון והסינון מתעדכנים כשמשנים את הבחירה למעלה — כך ששורה לא קופצת '
        'ממקומה בזמן שמדרגים.</p>'
        '<p class="cov-sum" id="cov-sum"></p>'
        '<p class="msg" id="cov-save"></p>'
        '<button type="button" class="cov-retry" id="cov-retry" hidden>נסה לשמור שוב</button>'
        '</div>',
        '<div id="cov-msg" class="msg"></div>',
        '<div class="tw"><table class="nadlan" id="cov-table"><thead><tr>'
        '<th>חברה</th><th class="imp" hidden>חשיבות</th><th>פרופיל</th>'
        '<th>סיווג הבורסה</th><th>מספר נייר</th>'
        '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>',
        '<script type="application/json" id="cov-levels">'
        + json.dumps([[v, t] for v, t in LEVELS], ensure_ascii=False) + '</script>',
        SCRIPT,
    ])
