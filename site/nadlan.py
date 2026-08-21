# -*- coding: utf-8 -*-
"""עמוד שוק הדיור. רינדור בלבד — כל החישוב ב-nadlan_stats.

הנתונים נאספים ב-ingest/nadlan_pull.py מ-Govmap (דיווחי רשות המסים).

שלושה סייגים שמעצבים את כל העמוד ולכן נאמרים בו במפורש:

· **פיגור דיווח.** רשות המסים מדווחת כשישה שבועות אחרי מועד העסקה,
  ולכן החודשיים האחרונים אינם נכללים כלל.
· **מדגם ולא מפקד.** בכל עיר נסרקות כמה שכונות, לא העיר כולה.
· **שם היזם אינו בנתוני העסקה.** הוא מוצלב ממקור נפרד לפי עיר ושכונה,
  ולכן הוא מועמד ולא ייחוס.
"""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import nadlan_stats as ns

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "output" / "nadlan"

REGIONS = [("dan", "גוש דן"), ("south", "דרום"), ("north", "צפון")]


def load() -> list[dict]:
    rows = []
    for f in sorted(DATA.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("date") or "")
    return rows


def missing_cities(present: set) -> list[str]:
    """ערים שהוגדרו לסריקה ולא הוחזרה בהן ולו עסקה אחת.

    עיר שנעדרת מהטבלה נקראת כאילו לא נסרקה, או גרוע מכך כאילו אין בה
    מסחר. שתי הקריאות שגויות: קרית שמונה, למשל, נסרקת בהצלחה ו-Govmap
    מחזיר עליה אפס עסקאות. פער במקור נאמר, לא מוסתר.
    """
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "nadlan.yaml").read_text(encoding="utf-8"))
    except Exception:
        return []
    return [c["name"] for r in cfg.get("regions", []) for c in r.get("cities", [])
            if c["name"] not in present]


def num(v) -> str:
    return f"{v:,}" if v else "—"


def money(v) -> str:
    if not v:
        return "—"
    if v >= 1_000_000:
        return f"{v / 1_000_000:,.2f} מ׳"
    return f"{v:,.0f}"


def signed(v, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{'+' if v > 0 else ''}{v:.{digits}f}%"


def cls(v, band: float = 1.0) -> str:
    if v is None:
        return "flat"
    return "up" if v > band else ("down" if v < -band else "flat")


def hebmonth(m: str) -> str:
    return f"{m[5:7]}/{m[:4]}" if len(m) >= 7 else m


def spark(series: dict, width: int = 62, height: int = 18) -> str:
    """קו מגמה זעיר. הצורה היא המידע — המספר המדויק בעמודה שלידו."""
    vals = [v for v in series.values() if v]
    if len(vals) < 3:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = width / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{height - (v - lo) / rng * (height - 3) - 1.5:.1f}"
                   for i, v in enumerate(vals))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" '
            f'stroke-width="1.4" stroke-linejoin="round"/></svg>')


def qlabel(q: str) -> str:
    return f"רבעון {q[-1]}/{q[:4]}"


# ── סעיפים ────────────────────────────────────────────────────────────

def head(m: dict, drop: dict) -> str:
    lo, hi = m["span"]
    return "\n".join([
        '<div class="dash-head"><h1>שוק הדיור</h1>',
        f'<span class="stamp">{hebmonth(lo[:7])} – {hebmonth(hi[:7])} · '
        f'נבנה {datetime.now():%d/%m %H:%M}</span></div>',
        f'<p class="lead">מחירי דירות והיקפי עסקאות ב-{m["cities"]} ערים בגוש '
        'דן, בדרום ובצפון, לפי דיווחי רשות המסים דרך Govmap. ההבחנה בין '
        'רכישה <strong>מקבלן</strong> ליד שנייה מגיעה מהמקור עצמו.</p>',
        '<p class="lead"><strong>איך לקרוא את המספרים.</strong> ההשוואה היא '
        f'תמיד {qlabel(m["q_now"])} — הרבעון המלא האחרון — מול הרבעון שלפניו '
        f'ומול {qlabel(m["q_yoy"])}. רבעונים ולא חודשים, כי בעיר בינונית '
        'נסגרות שלוש עד חמש עסקאות בחודש בשכונות שנסרקות, וחציון של שלוש '
        'עסקאות אינו מגמה. שני החודשים האחרונים אינם כאן כלל: רשות המסים '
        'מדווחת כשישה שבועות אחרי העסקה, והם היו נראים כצניחה שהיא רק '
        'פיגור.</p>',
        f'<p class="note">מתוך {drop["total"]:,} עסקאות שנסרקו נכללות כאן '
        f'{drop["kept"]:,} דירות מגורים. הוסרו {drop["non_residential"]:,} '
        'עסקאות שאינן דיור — קרקע, בניינים שלמים, חנויות ומשרדים — '
        f'ו-{drop["out_of_band"]:,} עסקאות שהמחיר למ״ר בהן חורג מכל טווח '
        'אפשרי ומעיד על שגיאת מקור.</p>',
    ])


def tiles(m: dict) -> str:
    return "\n".join([
        '<section class="strip">',
        f'<div class="tile"><span class="lbl">העיר החציונית · {qlabel(m["q_now"])}</span>'
        f'<span class="val" dir="ltr">{num(m["level"])}</span>'
        f'<span class="chg">₪ למ״ר</span></div>',
        f'<div class="tile {cls(m["yoy"], 2)}"><span class="lbl">שינוי שנתי, '
        f'חציון הערים</span>'
        f'<span class="val" dir="ltr">{signed(m["yoy"])}</span>'
        f'<span class="chg">רבעוני {signed(m["qoq"])}</span></div>',
        f'<div class="tile"><span class="lbl">עולות מול יורדות</span>'
        f'<span class="val" dir="ltr">{m["rising"]} · {m["falling"]}</span>'
        f'<span class="chg">ועוד {m["flat"]} יציבות מתוך {m["panel"]}</span></div>',
        f'<div class="tile"><span class="lbl">חלק הרכישות מקבלן</span>'
        f'<span class="val" dir="ltr">{m["share_new"]}%</span>'
        f'<span class="chg">מכלל העסקאות בחלון</span></div>',
        '</section>',
    ])


def reading(m: dict) -> str:
    """הקריאה במילים. נגזרת מהמספרים שחושבו, ואינה חוות דעת."""
    lead = ", ".join(f'{c} {signed(v["yoy"])}' for c, v in m["leaders"][:3])
    lag = ", ".join(f'{c} {signed(v["yoy"])}' for c, v in m["laggards"][:3])
    spread = (m["leaders"][0][1]["yoy"] - m["laggards"][0][1]["yoy"]
              if m["leaders"] and m["laggards"] else None)
    mix = ""
    if m["used_yoy"] is not None and m["yoy"] is not None:
        gap = round(m["yoy"] - m["used_yoy"], 1)
        if abs(gap) >= 2:
            mix = (f' בחישוב על יד שנייה בלבד — תת-שוק שאינו מושפע מתמהיל '
                   f'הבנייה החדשה — השינוי הוא {signed(m["used_yoy"])}, '
                   f'פער של {abs(gap):.1f} נקודות. הפער הזה הוא תמהיל, לא '
                   f'מחיר.')
    return "\n".join([
        '<h2>מה המספרים אומרים</h2>',
        f'<p class="reading">העיר החציונית במדגם {m["label"]}: '
        f'{signed(m["yoy"])} מול {qlabel(m["q_yoy"])}, ו{signed(m["qoq"])} '
        f'מול הרבעון הקודם — {m["why"]}.{mix}</p>',
        f'<p class="reading"><strong>אבל הממוצע מסתיר את הסיפור.</strong> '
        f'מתוך {m["panel"]} הערים שיש בהן מדגם מספיק, {m["rising"]} עלו מעל '
        f'2%, {m["falling"]} ירדו מתחת ל-2%, ו-{m["flat"]} נשארו בתווך. '
        + (f'הפער בין הקצוות הוא {spread:.0f} נקודות אחוז: '
           if spread else '')
        + f'בראש {lead}; בתחתית {lag}. כשהתפזורת כזאת, "שוק הדיור" אינו '
          'יחידה אחת אלא עשרות שווקים מקומיים.</p>',
    ])


def regions(m: dict) -> str:
    import statistics
    out = ['<h2>לפי אזור</h2>',
           '<p class="lead">חציון השינוי השנתי של הערים באזור. עיר אחת, קול '
           'אחד — כדי שעיר גדולה לא תכריע את האזור בזכות מספר העסקאות '
           'שלה.</p>',
           '<div class="tw"><table class="nadlan"><thead><tr>'
           '<th>אזור</th><th>ערים</th><th>שינוי שנתי, חציון</th>'
           '<th>עולות</th><th>יורדות</th><th>הבולטת</th>'
           '</tr></thead><tbody>']
    for key, label in REGIONS:
        cities = m["by_region"].get(key) or []
        if not cities:
            continue
        ys = [v["yoy"] for _, v in cities]
        mid = round(statistics.median(ys), 1)
        top = max(cities, key=lambda kv: kv[1]["yoy"])
        out.append(
            f'<tr><td class="city">{label}</td>'
            f'<td dir="ltr">{len(cities)}</td>'
            f'<td class="trend {cls(mid, 2)}" dir="ltr">{signed(mid)}</td>'
            f'<td dir="ltr">{sum(1 for y in ys if y > 2)}</td>'
            f'<td dir="ltr">{sum(1 for y in ys if y < -2)}</td>'
            f'<td>{top[0]} <span class="q" dir="ltr">{signed(top[1]["yoy"])}</span></td>'
            f'</tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)


def city_table(st: dict, m: dict) -> str:
    out = ['<h2>הערים</h2>',
           '<p class="lead">עמודת <strong>יד שנייה</strong> היא אותו שינוי '
           'שנתי, מחושב על עסקאות יד שנייה בלבד. כשהיא רחוקה מהעמודה שלצידה, '
           'מה שזז הוא תמהיל הנמכרות ולא המחיר — והשורה מסומנת. '
           '<strong>פרמיית קבלן</strong> היא הפער בין החציון למ״ר בדירה '
           'מקבלן לבין יד שנייה באותה עיר.</p>']
    for key, label in REGIONS:
        cities = {c: v for c, v in st.items() if v["region"] == key}
        if not cities:
            continue
        order = sorted(cities.items(), key=lambda kv: -(kv[1]["yoy"] or -999))
        out.append(f'<h3>{label}</h3>')
        out.append('<div class="tw"><table class="nadlan"><thead><tr>'
                   '<th>עיר</th><th>₪/מ״ר ברבעון</th><th>שנתי</th><th>רבעוני</th>'
                   '<th>יד שנייה</th><th>פרמיית קבלן</th><th>עסקאות ברבעון</th>'
                   '<th>מקבלן</th><th>מגמה</th><th>מצב</th></tr></thead><tbody>')
        for city, v in order:
            thin = ('<span class="thin" title="פחות מ-8 עסקאות ברבעון האחרון">'
                    'מדגם דק</span>' if v["thin"] else "")
            mix = ('<span class="mix" title="השינוי הכולל רחוק מזה של יד שנייה — '
                   'מה שזז הוא תמהיל הנמכרות">תמהיל</span>' if v["mix_flag"] else "")
            vol = (f'<span class="q" dir="ltr">{signed(v["vol_change"], 0)}</span>'
                   if v["vol_change"] is not None else "")
            out.append(
                f'<tr><td class="city">{city}{thin}{mix}</td>'
                f'<td class="key" dir="ltr">{num(v["level"] or v["ppsm"])}</td>'
                f'<td class="trend {cls(v["yoy"], 2)}" dir="ltr">{signed(v["yoy"])}</td>'
                f'<td class="trend {cls(v["qoq"])}" dir="ltr">{signed(v["qoq"])}</td>'
                f'<td class="trend {cls(v["used_yoy"], 2)}" dir="ltr">'
                f'{signed(v["used_yoy"])}</td>'
                f'<td dir="ltr">{signed(v["premium_new"], 0)}</td>'
                f'<td dir="ltr">{v["vol"]} {vol}</td>'
                f'<td dir="ltr">{v["share_new"] if v["share_new"] is not None else "—"}%</td>'
                f'<td class="trend {cls(v["yoy"], 2)}" dir="ltr">{spark(v["series"])}</td>'
                f'<td class="state">{v["label"]}</td></tr>')
        out.append('</tbody></table></div>')
    if m["mix_cities"]:
        out.append('<p class="note">ערים שסומנו "תמהיל": '
                   f'{", ".join(m["mix_cities"])}. בהן הפער בין השינוי הכולל '
                   'לשינוי ביד שנייה הוא ארבע נקודות אחוז ומעלה, ולכן אין '
                   'לקרוא את השינוי הכולל כשינוי מחיר.</p>')
    return "\n".join(out)


def developer_premium(st: dict) -> str:
    rows = [(c, v) for c, v in st.items()
            if v["premium_new"] is not None and v["n_new"] >= ns.MIN_SAMPLE
            and v["n_used"] >= ns.MIN_SAMPLE]
    if len(rows) < 4:
        return ""
    rows.sort(key=lambda kv: -kv[1]["premium_new"])
    mx = max(abs(v["premium_new"]) for _, v in rows) or 1
    out = ['<h2>פרמיית הקבלן</h2>',
           '<p class="lead">כמה יקרה דירה מקבלן למ״ר לעומת יד שנייה באותה '
           'עיר. פרמיה גבוהה מצביעה על עודף ביקוש לחדש או על בנייה חדשה '
           'באזורים הטובים של העיר; פרמיה שלילית פירושה שהבנייה החדשה נמצאת '
           'בשוליה. <strong>זה אינו מדד לכדאיות</strong> — הוא אינו מנטרל '
           'מיקום, גודל או מפרט.</p>',
           '<ul class="offex-bars">']
    for city, v in rows[:14]:
        w = max(2, round(abs(v["premium_new"]) / mx * 100))
        sign = "up" if v["premium_new"] > 0 else "down"
        out.append(
            f'<li><span class="nm">{city}</span>'
            f'<span class="bar {sign}"><i style="width:{w}%"></i></span>'
            f'<span class="pv" dir="ltr">{signed(v["premium_new"], 0)}</span>'
            f'<span class="mv" dir="ltr">{num(v["ppsm_new"])} / {num(v["ppsm_used"])}</span>'
            f'</li>')
    out.append('</ul>')
    out.append('<p class="note">שני המספרים בקצה: חציון ₪/מ״ר מקבלן, ואחריו '
               'יד שנייה. הטבלה כוללת רק ערים עם לפחות שמונה עסקאות מכל סוג.</p>')
    return "\n".join(out)


def by_size(st: dict, rows: list[dict]) -> str:
    """מחיר למ״ר לפי גודל דירה — היכן השוק מתומחר."""
    agg = defaultdict(list)
    for r in rows:
        b = ns.rooms_bucket(r)
        if b and r.get("price_per_sqm"):
            agg[b].append(r["price_per_sqm"])
    have = [b for b in ns.ROOM_ORDER if len(agg.get(b, [])) >= 30]
    if len(have) < 2:
        return ""
    big = sorted(st.items(), key=lambda kv: -kv[1]["n"])[:10]
    out = ['<h2>מחיר למ״ר לפי גודל הדירה</h2>',
           '<p class="lead">דירה קטנה יקרה יותר למ״ר כמעט תמיד, כי המחיר '
           'אינו לינארי בשטח. מה שמעניין הוא <strong>גודל הפער</strong>: '
           'פער רחב מעיד על ביקוש מרוכז בדירות קטנות, ופער צר על שוק שבו '
           'המשפרים דיור מובילים.</p>',
           '<div class="tw"><table class="nadlan"><thead><tr><th>עיר</th>'
           + "".join(f'<th>{b}</th>' for b in have)
           + '<th>פער קטן־גדול</th></tr></thead><tbody>']
    for city, v in [(f"כלל הערים ({len(st)})", None)] + big:
        vals = []
        for b in have:
            x = (ns.med(agg[b]) if v is None else v["by_rooms"].get(b))
            vals.append(x)
        real = [x for x in vals if x]
        gap = (round((real[0] / real[-1] - 1) * 100) if len(real) >= 2 and real[-1]
               else None)
        cells = "".join(f'<td dir="ltr">{num(x)}</td>' for x in vals)
        out.append(f'<tr><td class="city">{city}</td>{cells}'
                   f'<td class="key" dir="ltr">{signed(gap, 0)}</td></tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)


def neighbourhoods(st: dict) -> str:
    """פיזור בתוך העיר — הממוצע העירוני מסתיר אותו."""
    pick = sorted(((c, v) for c, v in st.items() if len(v["hoods"]) >= 3),
                  key=lambda kv: -kv[1]["n"])[:6]
    if not pick:
        return ""
    out = ['<h2>הפיזור בתוך העיר</h2>',
           '<p class="lead">חציון עירוני אחד מכסה על שכונות שנבדלות זו מזו '
           'בעשרות אחוזים. לכל עיר מוצגות השכונות עם הכי הרבה עסקאות '
           'בשכונות שנסרקו.</p>',
           '<div class="hoods">']
    for city, v in pick:
        hs = v["hoods"][:6]
        vals = [h["ppsm"] for h in hs if h["ppsm"]]
        spread = (round((max(vals) / min(vals) - 1) * 100)
                  if len(vals) >= 2 and min(vals) else None)
        out.append(f'<div class="hood-city"><h3>{city}'
                   + (f' <span class="q" dir="ltr">פיזור {spread}%</span>'
                      if spread else "") + '</h3><ul>')
        for h in hs:
            share = round(h["new"] / h["n"] * 100) if h["n"] else 0
            out.append(
                f'<li><span class="nm">{h["name"]}</span>'
                f'<span class="pv" dir="ltr">{num(h["ppsm"])}</span>'
                f'<span class="mv" dir="ltr">{h["n"]} עסקאות · {share}% מקבלן</span>'
                f'</li>')
        out.append('</ul></div>')
    out.append('</div>')
    return "\n".join(out)


def projects(rows: list[dict]) -> str:
    new_deals = [r for r in rows if r.get("is_new")]
    tagged = [r for r in new_deals if r.get("developer_candidates")]
    if not tagged:
        return ""
    proj = defaultdict(list)
    for r in tagged:
        proj[(r["city"], r["neighborhood"], tuple(r["developer_candidates"]))].append(r)
    out = ['<h2>פרויקטים עם יזם מזוהה</h2>',
           '<p class="lead">שם היזם <strong>אינו חלק מנתוני העסקה</strong>. הוא '
           'מוצלב מקובץ "דירה בהנחה" של data.gov.il, שהוא המקור הציבורי היחיד '
           'שמקשר פרויקט ליזם — ולכן הוא מכסה רק תוכניות מסובסדות, וההתאמה היא '
           f'לפי עיר ושכונה. בפועל ניתן לשייך כך '
           f'{round(len(tagged) / len(new_deals) * 100)}% מעסקאות הקבלן '
           f'({len(tagged):,} מתוך {len(new_deals):,}). '
           '<strong>זהו מועמד ולא ייחוס:</strong> ייתכן שבאותה שכונה בונים כמה '
           'יזמים, והדירה שנמכרה אינה של מי שמופיע כאן.</p>',
           '<ul class="projects">']
    for (city, hood, devs), deals in sorted(proj.items(), key=lambda kv: -len(kv[1]))[:20]:
        ppsm = ns.med([d.get("price_per_sqm") for d in deals])
        lo = min(d["amount"] for d in deals)
        hi = max(d["amount"] for d in deals)
        last = max(d["date"] for d in deals)
        out.append(
            f'<li><div class="ph"><span class="c">{city}</span>'
            f'<span class="h">{hood}</span>'
            f'<span class="cnt" dir="ltr">{len(deals)} עסקאות</span></div>'
            f'<div class="pd">יזם אפשרי: {" · ".join(devs[:3])}</div>'
            f'<div class="pn"><span><b>חציון</b>'
            f'<i dir="ltr">{num(ppsm)} ₪/מ״ר</i></span>'
            f'<span><b>טווח</b><i dir="ltr">{money(lo)}–{money(hi)} ₪</i></span>'
            f'<span><b>אחרונה</b><i dir="ltr">{last[8:10]}/{last[5:7]}/{last[:4]}</i></span>'
            f'</div></li>')
    out.append('</ul>')
    return "\n".join(out)


def newest(rows: list[dict]) -> str:
    new_deals = [r for r in rows if r.get("is_new")]
    sel = list(reversed(new_deals))[:20]
    if not sel:
        return ""
    out = ['<h2>רכישות מקבלן אחרונות</h2>', '<ul class="newbuild">']
    for r in sel:
        devs = r.get("developer_candidates") or []
        dev = ('<span class="dev">יזם אפשרי: ' + " · ".join(devs[:2]) + '</span>'
               if devs else "")
        loc = " · ".join(x for x in (r.get("neighborhood"), r.get("street")) if x)
        out.append(
            f'<li><span class="d">{r["date"][8:10]}/{r["date"][5:7]}</span>'
            f'<span class="c">{r["city"]}</span>'
            f'<span class="l">{loc or "—"}</span>'
            f'<span class="n" dir="ltr">{r.get("rooms") or "—"} ח׳ · '
            f'{r.get("area_sqm") or "—"} מ״ר</span>'
            f'<span class="p" dir="ltr">{money(r.get("amount"))} ₪</span>'
            f'<span class="s" dir="ltr">{num(r.get("price_per_sqm"))} ₪/מ״ר</span>'
            f'{dev}</li>')
    out.append('</ul>')
    return "\n".join(out)


def method(st: dict, m: dict) -> str:
    out = ['<p class="note"><strong>שיטה.</strong> חציון ולא ממוצע: עסקה '
           'חריגה אחת מזיזה ממוצע ולא מזיזה חציון. השינוי המצרפי הוא חציון '
           'השינויים של הערים ולא חציון מאוחד של כל העסקאות — חציון מאוחד '
           'נשלט בתמהיל הערים, ובמדידה כאן הוא הצביע על ירידה של 10% בזמן '
           'שרוב הערים עלו. רבעון נכנס לחישוב רק עם שמונה עסקאות ומעלה, '
           'ועיר עם פחות משמונה עסקאות ברבעון האחרון מסומנת כמדגם דק '
           'ואינה נספרת במצרף.</p>']
    gap = missing_cities(set(st))
    if gap:
        out.append('<p class="note">ערים שנסרקו ולא הוחזרו בהן עסקאות: '
                   f'{", ".join(gap)}. היעדרן מהטבלה הוא פער בנתוני המקור '
                   'ולא עדות לכך שלא נסחרו בהן דירות.</p>')
    return "\n".join(out)


def page(rows: list[dict]) -> str:
    if not rows:
        return ('<div class="dash-head"><h1>שוק הדיור</h1></div>'
                '<p class="lead">טרם נאספו עסקאות. הסריקה רצה בכל בוקר.</p>')
    clean, drop = ns.clean_rows(rows)
    if not clean:
        return ('<div class="dash-head"><h1>שוק הדיור</h1></div>'
                '<p class="lead">נאספו עסקאות, אך אף אחת מהן אינה דירת '
                'מגורים בטווח מחיר אפשרי.</p>')
    st = ns.city_stats(clean)
    m = ns.market(clean, st)
    return "\n".join(p for p in [
        head(m, drop), tiles(m), reading(m), regions(m), city_table(st, m),
        developer_premium(st), by_size(st, clean), neighbourhoods(st),
        projects(clean), newest(clean), method(st, m),
    ] if p)
