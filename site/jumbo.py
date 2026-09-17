# -*- coding: utf-8 -*-
"""עסקאות מתואמות, ואיחודן עם העסקאות מחוץ לבורסה, בעמוד offex.html.

**המקור.** קובץ ה-Excel החם של GTO ("מתואמות"), שנקרא מקומית ב-
ingest/gto_pull.py ונדחף לריפו התוכן אל output/jumbo/<שנה>.jsonl: רשומה
לכל נייר שהיו בו עסקאות מתואמות (האות J בקובץ), לכל יום.

**מה יש בקובץ ומה אין.** לכל נייר: תמורת העסקאות המתואמות ביום (₪), מחזור
היום, שער הבסיס, השער האחרון ושווי השוק. **אין מחיר לכל עסקה**, ולכן
הסטייה משער הבסיס — הציר המרכזי בעסקאות מחוץ לבורסה — אינה מחושבת כאן.
במקומה, באותו מבנה של יום, חודש ושנה:
  · **% ממחזור היום** — כמה מהמסחר בנייר נעשה בעסקאות מתואמות. מחזור היום
    ב-GTO כולל אותן (נבדק 17/09/2026: בכל 38 הניירות התמורה המתואמת קטנה
    ממנו), ולכן השיעור אינו עובר 100% — בשונה מעסקאות מחוץ לבורסה.
  · **% מההון, משוער** — יחידות משוערות (התמורה חלקי השער האחרון) מול ההון
    המונפק. ההנחה היא שהעסקאות נעשו סמוך לשער השוק, ולכן המספר מסומן כמשוער.
  · **שינוי המניה ביום** — הקשר לעסקאות, לא מחיר העסקה.

**חלון ההשוואה.** האיסוף מ-GTO התחיל ב-17/09/2026. הטבלאות המצטברות של
מתואמות, וכל הטבלאות המאוחדות, מתחילות ביום הראשון שנאסף — אחרת האיחוד היה
משווה שנה של עסקאות מחוץ לבורסה לשבועות של מתואמות, ומציג את הפער כממצא.
"""
import json
import statistics
from html import escape as _esc
from pathlib import Path

import otc

ROOT = Path(__file__).resolve().parent.parent
JUMBO = ROOT / "output" / "jumbo"

SRC_GTO = "מקור: נתוני המסחר בבורסה לניירות ערך בתל אביב, דרך GTO"
SRC_ALL = ("מקור: סקירת העסקאות מחוץ לבורסה של הבורסה לניירות ערך בתל אביב, "
           "ונתוני העסקאות המתואמות דרך GTO")
KICKER_J = "עסקאות מתואמות"
KICKER_A = "עסקאות מחוץ לבורסה ומתואמות"
# מעל זה העסקאות המתואמות הן רוב המסחר בנייר באותו יום.
MAJORITY = 50.0


def load() -> list[dict]:
    rows = []
    for f in sorted(JUMBO.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("date") and r.get("security_id") and (r.get("value") or 0) > 0:
                rows.append(r)
    rows.sort(key=lambda r: (r["date"], -r["value"]))
    return rows


def _name(n) -> str:
    # שם עם רווחים כפולים ("דיסקונט       א") נשבר בתמונה למילים ריקות.
    return " ".join(str(n or "").split())


def _units(r: dict) -> float:
    """יחידות משוערות: התמורה חלקי השער האחרון (השער באגורות)."""
    last = r.get("last")
    return r["value"] / (last / 100) if last else 0.0


def _pct(v, digits: int = 1) -> str:
    return "—" if v is None else f"{v:,.{digits}f}%"


def _share(v: float) -> str:
    """שיעור במשפט. 99.9% נשאר 99.9% — "100%" היה אומר שכל המחזור היה מתואם."""
    return f"{v:.1f}%" if 99.5 <= v < 100 else f"{v:.0f}%"


def _days(n: int) -> str:
    return "יום אחד" if n == 1 else f"{n} ימים"


def _window(first: str, start: str) -> bool:
    """האם האיסוף התחיל אחרי תחילת התקופה — ואז התקופה נקראת "מאז"."""
    return first > start


# --- צבירה ---------------------------------------------------------------------------

def aggregate(rows: list[dict]) -> list[dict]:
    """סיכום מתואמות לפי נייר."""
    cap = otc.capital()
    out: dict[str, dict] = {}
    for r in rows:
        e = out.setdefault(r["security_id"], {
            "sid": r["security_id"], "name": _name(r.get("name")), "covered": r.get("covered"),
            "value": 0.0, "day_value": 0.0, "units": 0.0, "days": set(), "chg": [],
            "issued": None})
        e["value"] += r["value"]
        e["day_value"] += r.get("day_value") or 0
        e["units"] += _units(r)
        e["days"].add(r["date"])
        if r.get("chg_pct") is not None:
            e["chg"].append(r["chg_pct"])
        e["issued"] = r.get("issued") or e["issued"]
    for e in out.values():
        e["days"] = len(e["days"])
        # בתקופה: התמורה המתואמת מול המחזור באותם ימים שבהם היו מתואמות.
        e["pct_day"] = round(e["value"] / e["day_value"] * 100, 1) if e["day_value"] else None
        issued = (cap.get(e["sid"]) or {}).get("issued") or e["issued"]
        e["pct_capital"] = round(e["units"] / issued * 100, 3) if issued and e["units"] else None
        e["chg_mean"] = round(statistics.fmean(e["chg"]), 2) if e["chg"] else None
    return sorted(out.values(), key=lambda e: -e["value"])


def aggregate_all(otc_rows: list[dict], j_rows: list[dict]) -> list[dict]:
    """מחוץ לבורסה ומתואמות יחד, לפי נייר.

    **ההון מצטבר מיחידות.** ביחידות מחוץ לבורסה בפועל, ובמתואמות משוערות —
    כך שנייר שהיו בו שני הסוגים נספר פעם אחת, מול אותו הון מונפק.
    """
    cap = otc.capital()
    out: dict[str, dict] = {}

    def ent(r: dict) -> dict:
        e = out.setdefault(r["security_id"], {
            "sid": r["security_id"], "name": _name(r.get("name")), "covered": False,
            "otc": 0.0, "jumbo": 0.0, "units": 0.0, "n_otc": 0, "days": set(),
            "issued": None})
        e["covered"] = e["covered"] or bool(r.get("covered"))
        e["days"].add(r["date"])
        return e

    for r in otc_rows:
        e = ent(r)
        e["otc"] += r["value"]
        e["units"] += r.get("units") or 0
        e["n_otc"] += 1
    for r in j_rows:
        e = ent(r)
        e["jumbo"] += r["value"]
        e["units"] += _units(r)
        e["issued"] = r.get("issued") or e["issued"]
    for e in out.values():
        e["days"] = len(e["days"])
        e["value"] = e["otc"] + e["jumbo"]
        issued = (cap.get(e["sid"]) or {}).get("issued") or e["issued"]
        e["pct_capital"] = round(e["units"] / issued * 100, 3) if issued and e["units"] else None
    return sorted(out.values(), key=lambda e: -e["value"])


# --- סקירה ותקציר ---------------------------------------------------------------------
# מעקה 5 חל כאן במלואו: כל משפט הוא עובדה מחושבת מהטבלה, בלי המלצה.

def review_bits_j(agg: list[dict], label: str) -> list[str]:
    total = sum(e["value"] for e in agg)
    if not agg or not total:
        return []
    top = agg[0]
    bits = [f"{label}: עסקאות מתואמות ב-{len(agg)} ניירות בהיקף {otc.money(total)}."]
    if len(agg) >= 3:
        top3 = sum(e["value"] for e in agg[:3]) / total * 100
        bits.append(f"שלושת הגדולים ריכזו {top3:.0f}% מההיקף, "
                    f"והגדול בהם — {top['name']} — {top['value'] / total * 100:.0f}%.")
    else:
        bits.append(f"הגדול בהם הוא {top['name']}.")
    maj = [e for e in agg if (e["pct_day"] or 0) >= MAJORITY]
    if maj:
        m = max(maj, key=lambda e: e["pct_day"])
        if len(maj) == 1:
            bits.append(f"ב{m['name']} העסקאות המתואמות היו {_share(m['pct_day'])} מהמחזור.")
        else:
            bits.append(f"ב-{len(maj)} ניירות העסקאות המתואמות היו יותר ממחצית המחזור, "
                        f"ובולט בהם {m['name']} — {_share(m['pct_day'])}.")
    withcap = [e for e in agg if e["pct_capital"]]
    if withcap:
        big = max(withcap, key=lambda e: e["pct_capital"])
        bits.append(f"החלק הגדול ביותר מהון החברה עבר ב{big['name']} — "
                    f"{big['pct_capital']:.2f}% מההון המונפק (משוער).")
    rec = [e for e in agg if e["days"] >= 3]
    if rec:
        r = max(rec, key=lambda e: e["days"])
        bits.append(f"{len(rec)} ניירות חזרו בשלושה ימים או יותר, "
                    f"והחוזר שבהם {r['name']} ב-{r['days']} ימים.")
    return bits


def review_bits_a(agg: list[dict], label: str) -> list[str]:
    total = sum(e["value"] for e in agg)
    if not agg or not total:
        return []
    o = sum(e["otc"] for e in agg)
    j = sum(e["jumbo"] for e in agg)
    top = agg[0]
    bits = [f"{label}: {otc.money(total)} ב-{len(agg)} ניירות — "
            f"{otc.money(o)} מחוץ לבורסה ({o / total * 100:.0f}%) "
            f"ו-{otc.money(j)} בעסקאות מתואמות ({j / total * 100:.0f}%)."]
    if len(agg) >= 3:
        top3 = sum(e["value"] for e in agg[:3]) / total * 100
        bits.append(f"שלושת הגדולים ריכזו {top3:.0f}% מההיקף, "
                    f"והגדול בהם — {top['name']} — {top['value'] / total * 100:.0f}%.")
    both = [e for e in agg if e["otc"] and e["jumbo"]]
    if both:
        b = both[0]
        bits.append(f"ב-{len(both)} ניירות היו גם עסקאות מחוץ לבורסה וגם מתואמות"
                    + (f", והגדול שבהם {b['name']} — {otc.money(b['value'])}." if len(both) > 1
                       else f": {b['name']}, {otc.money(b['value'])}."))
    withcap = [e for e in agg if e["pct_capital"]]
    if withcap:
        big = max(withcap, key=lambda e: e["pct_capital"])
        bits.append(f"החלק הגדול ביותר מהון החברה עבר ב{big['name']} — "
                    f"{big['pct_capital']:.2f}% מההון המונפק (משוער).")
    return bits


def _clip(lines: list[str]) -> str:
    out = ""
    for ln in lines:
        nxt = (out + "\n" + ln) if out else ln
        if len(nxt) > 268:
            break
        out = nxt
    return out + "\ntlvtaseview.com"


def tweet_j(agg: list[dict], label: str) -> str:
    total = sum(e["value"] for e in agg)
    if not agg or not total:
        return ""
    big = agg[0]
    share = f" — {_share(big['pct_day'])} מהמחזור" if big["pct_day"] is not None else ""
    lines = [f"עסקאות מתואמות · {label}",
             f"{otc.money(total)} ב-{len(agg)} ניירות",
             f"הגדולה: {big['name']} {otc.money(big['value'])}{share}"]
    maj = max(agg, key=lambda e: e["pct_day"] or 0)
    if (maj["pct_day"] or 0) >= MAJORITY and maj["sid"] != big["sid"]:
        lines.append(f"רוב המחזור: {maj['name']} {_share(maj['pct_day'])}")
    withcap = [e for e in agg if e["pct_capital"]]
    if withcap:
        top = max(withcap, key=lambda e: e["pct_capital"])
        lines.append(f"החלק הגדול מההון: {top['name']} {top['pct_capital']:.2f}% (משוער)")
    return _clip(lines)


def tweet_a(agg: list[dict], label: str) -> str:
    total = sum(e["value"] for e in agg)
    if not agg or not total:
        return ""
    big = agg[0]
    return _clip([f"עסקאות מחוץ לבורסה ומתואמות · {label}",
                  f"{otc.money(total)} ב-{len(agg)} ניירות",
                  f"מחוץ לבורסה {otc.money(sum(e['otc'] for e in agg))} · "
                  f"מתואמות {otc.money(sum(e['jumbo'] for e in agg))}",
                  f"הגדולה: {big['name']} {otc.money(big['value'])}"])


# --- טבלה אחת: HTML ומטען לתמונה מאותו מבנה --------------------------------------------

def _cell(key: str, v, trend: str = "", bold: bool = False) -> str:
    t = _esc(str(v), quote=False)
    if key == "name":
        return f'<td class="city">{"<b>" + t + "</b>" if bold and t else t}</td>'
    if bold and not t:
        return "<td></td>"
    if key == "value":
        return f'<td class="key" dir="ltr">{"<b>" + t + "</b>" if bold else t}</td>'
    if key == "chg":
        return f'<td class="trend {trend}" dir="ltr">{t}</td>'
    return f'<td dir="ltr">{"<b>" + t + "</b>" if bold else t}</td>'


def _section(title: str, sub: str, key: str, cols: list, cells: list[dict], total_row: dict,
             stats: list[dict], bits: list[str], more: str, file: str, kicker: str,
             source: str, tweet_text: str, notes: str = "") -> str:
    """אותה תבנית כמו otc.period_table: כותרת, סקירה, תקציר, ייצוא וטבלה.

    **הטבלה והתמונה נבנות מאותן שורות** — אותו כלל כמו בטבלאות מחוץ
    לבורסה, כדי שהתמונה לא תציג חתך אחר מהעמוד.
    """
    payload = otc.card(title, sub, [
        {"type": "stats", "items": stats},
        {"type": "notes", "title": "עיקרי התקופה", "items": bits[1:]} if len(bits) > 1 else None,
        {"type": "table", "title": "לפי נייר", "cols": cols,
         "rows": [otc._public(c) for c in cells], "moreText": more, "totalRow": total_row},
    ], file=file, kicker=kicker, source=source)
    out = [f"<h2>{_esc(title, quote=False)}</h2>",
           f'<p class="note">{_esc(sub, quote=False)}</p>',
           notes,
           ('<p class="otc-review">' + _esc(" ".join(bits), quote=False) + "</p>") if bits else "",
           otc.tweet_block(tweet_text, key),
           otc.embed(key, payload),
           f'<p class="otc-acts">{otc.png_button(key=key)}'
           + (f'<button type="button" class="otc-copy" data-key="{key}">העתקת התקציר</button>'
              if tweet_text else "")
           + "</p>",
           '<div class="tw"><table class="nadlan"><thead><tr>'
           + "".join(f"<th>{c[0]}</th>" for c in cols) + "</tr></thead><tbody>"]
    for r in cells:
        out.append("<tr>" + "".join(_cell(c[1], r[c[1]], r.get("_cls", "")) for c in cols) + "</tr>")
    if more:
        out.append(f'<tr><td colspan="{len(cols)}" class="note">{more}</td></tr>')
    out.append("<tr>" + "".join(_cell(c[1], total_row.get(c[1], ""), "", bold=True) for c in cols)
               + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(o for o in out if o)


def _empty(title: str, sub: str, what: str) -> str:
    return (f"<h2>{_esc(title, quote=False)}</h2><p class=\"note\">{_esc(sub, quote=False)}</p>"
            f'<p class="note">{what}</p>')


def table_j(title: str, sub: str, rows: list[dict], key: str, label: str,
            day_mode: bool, limit: int = 30) -> str:
    if not rows:
        return _empty(title, sub, "אין עסקאות מתואמות בתקופה הזו.")
    agg = aggregate(rows)
    total = sum(e["value"] for e in agg)
    cols = [["נייר", "name", "rtl"]]
    if not day_mode:
        cols.append(["ימים", "days", "ltr"])
    cols += [["היקף", "value", "ltr"],
             ["% ממחזור היום" if day_mode else "% מהמחזור", "pday", "ltr"],
             ["% מההון (משוער)", "cap", "ltr"]]
    if day_mode:
        cols.append(["שינוי המניה", "chg", "ltr"])
    shown = agg[:limit]
    cells = [{"name": e["name"], "days": str(e["days"]), "value": otc.money(e["value"]),
              "pday": _pct(e["pct_day"]), "cap": _pct(e["pct_capital"], 2),
              "chg": otc.signed(e["chg_mean"]), "_cls": otc.cls(e["chg_mean"])} for e in shown]
    rest = len(agg) - len(shown)
    more = (f"ועוד {rest} ניירות בהיקף {otc.money(sum(e['value'] for e in agg[limit:]))}."
            if rest > 0 else "")
    total_row = {"name": "סך הכל", "days": "", "value": otc.money(total),
                 "pday": "", "cap": "", "chg": ""}
    maj = sum(1 for e in agg if (e["pct_day"] or 0) >= MAJORITY)
    days = len({r["date"] for r in rows})
    stats = [{"label": "היקף", "value": otc.money(total)},
             {"label": "ניירות", "value": str(len(agg))},
             ({"label": "רוב המחזור", "value": f"{maj} ניירות", "cap": "מעל מחצית מהמסחר בנייר"}
              if day_mode else {"label": "ימי מסחר", "value": str(days)})]
    return _section(title, sub, key, cols, cells, total_row, stats, review_bits_j(agg, label),
                    more, f"tlv-jumbo-{key}-{max(r['date'] for r in rows)}", KICKER_J, SRC_GTO,
                    tweet_j(agg, label))


def table_a(title: str, sub: str, otc_rows: list[dict], j_rows: list[dict], key: str,
            label: str, day_mode: bool, notes: str = "", limit: int = 30) -> str:
    if not otc_rows and not j_rows:
        return _empty(title, sub, "אין עסקאות בתקופה הזו.")
    agg = aggregate_all(otc_rows, j_rows)
    total = sum(e["value"] for e in agg)
    o = sum(e["otc"] for e in agg)
    j = sum(e["jumbo"] for e in agg)
    cols = [["נייר", "name", "rtl"]]
    if not day_mode:
        cols.append(["ימים", "days", "ltr"])
    cols += [["מחוץ לבורסה", "otc", "ltr"], ["מתואמות", "jumbo", "ltr"],
             ["סה\"כ", "value", "ltr"], ["% מההון (משוער)", "cap", "ltr"]]
    shown = agg[:limit]
    cells = [{"name": e["name"], "days": str(e["days"]),
              "otc": otc.money(e["otc"]) if e["otc"] else "—",
              "jumbo": otc.money(e["jumbo"]) if e["jumbo"] else "—",
              "value": otc.money(e["value"]), "cap": _pct(e["pct_capital"], 2)} for e in shown]
    rest = len(agg) - len(shown)
    more = (f"ועוד {rest} ניירות בהיקף {otc.money(sum(e['value'] for e in agg[limit:]))}."
            if rest > 0 else "")
    total_row = {"name": "סך הכל", "days": "", "otc": otc.money(o), "jumbo": otc.money(j),
                 "value": otc.money(total), "cap": ""}
    stats = [{"label": "סה\"כ", "value": otc.money(total), "cap": f"{len(agg)} ניירות"},
             {"label": "מחוץ לבורסה", "value": otc.money(o)},
             {"label": "מתואמות", "value": otc.money(j)}]
    last = max([r["date"] for r in otc_rows] + [r["date"] for r in j_rows])
    return _section(title, sub, key, cols, cells, total_row, stats, review_bits_a(agg, label),
                    more, f"tlv-blocks-{key}-{last}", KICKER_A, SRC_ALL,
                    tweet_a(agg, label), notes)


# --- שלוש תקופות, לכל לשונית ------------------------------------------------------------

def _day_state(j_day: list[dict]) -> tuple[bool, str]:
    final = all(r.get("final") for r in j_day)
    asof = max((r.get("asof") or "") for r in j_day)[11:16] if j_day else ""
    return final, asof


def periods_j(j_rows: list[dict], year: str) -> str:
    days = sorted({r["date"] for r in j_rows})
    first, latest = days[0], days[-1]
    day_rows = [r for r in j_rows if r["date"] == latest]
    final, asof = _day_state(day_rows)
    hd = otc.hebdate
    if final:
        title, dlabel = f"יום המסחר האחרון · {hd(latest)}", "יום המסחר האחרון"
        sub = "כל הניירות שבהם היו עסקאות מתואמות באותו יום."
    else:
        title, dlabel = f"היום · {hd(latest)}", "היום"
        sub = (f"יום המסחר טרם הסתיים — הנתונים נכונים ל-{asof}, "
               "ויתעדכנו עד הנעילה." if asof else "יום המסחר טרם הסתיים.")
    parts = [table_j(title, sub, day_rows, "j-day", f"{dlabel} {hd(latest)}", day_mode=True)]

    month = latest[:7]
    mtd = [r for r in j_rows if r["date"][:7] == month]
    ytd = [r for r in j_rows if r["date"][:4] == year]
    if _window(first, f"{month}-01"):
        # החודש והשנה הם אותו חלון עד שהאיסוף יעבור חודש מלא — טבלה אחת.
        parts.append(table_j(f"מאז תחילת האיסוף · {hd(first)}",
                             f"מצטבר מ-{hd(first)}, היום הראשון שנאסף מ-GTO.",
                             mtd, "j-mtd", f"מאז {hd(first)}", day_mode=False))
        return "\n".join(parts)
    parts.append(table_j(f"מתחילת החודש · {month[5:7]}/{month[:4]}",
                         "מצטבר מהראשון בחודש ועד היום האחרון שנאסף.",
                         mtd, "j-mtd", "החודש", day_mode=False))
    since = _window(first, f"{year}-01-01")
    parts.append(table_j(f"מתחילת {year}" + (f" · מאז {hd(first)}" if since else ""),
                         (f"מצטבר מ-{hd(first)}, היום הראשון שנאסף מ-GTO."
                          if since else "מצטבר לכל השנה. עמודת הימים מראה נייר שחוזר."),
                         ytd, "j-ytd", f"מתחילת {year}", day_mode=False))
    return "\n".join(parts)


def periods_a(a: dict, j_rows: list[dict], year: str) -> str:
    hd = otc.hebdate
    first = min(r["date"] for r in j_rows)
    j_latest = max(r["date"] for r in j_rows)
    shares = [r for r in a["shares"] if r["date"] >= first]
    latest = max(a["latest"] or "", j_latest)
    o_day = [r for r in shares if r["date"] == latest]
    j_day = [r for r in j_rows if r["date"] == latest]
    open_otc = bool(o_day) and latest == a["latest"] and a["latest"] != a["ref"]
    j_final, j_asof = _day_state(j_day)
    open_day = open_otc or (bool(j_day) and not j_final)

    gaps = []
    if not j_day:
        gaps.append(f"אין עדיין נתוני עסקאות מתואמות ליום הזה (האחרון שנאסף: {hd(j_latest)}).")
    if not o_day:
        gaps.append("הסקירה של הבורסה לעסקאות מחוץ לבורסה ליום הזה טרם נאספה.")
    notes = ('<p class="note">' + " ".join(gaps) + "</p>") if gaps else ""
    if open_day:
        title, dlabel = f"היום · {hd(latest)}", "היום"
        sub = "יום המסחר טרם הסתיים, ולכן זהו חתך חלקי ולא יום שלם."
    else:
        title, dlabel = f"יום המסחר האחרון · {hd(latest)}", "יום המסחר האחרון"
        sub = "העסקאות מחוץ לבורסה והמתואמות באותו יום, מסוכמות לפי נייר."
    parts = [table_a(title, sub, o_day, j_day, "a-day", f"{dlabel} {hd(latest)}",
                     day_mode=True, notes=notes)]

    month = latest[:7]
    o_m = [r for r in shares if r["date"][:7] == month]
    j_m = [r for r in j_rows if r["date"][:7] == month]
    if _window(first, f"{month}-01"):
        parts.append(table_a(f"מאז תחילת האיסוף · {hd(first)}",
                             f"מצטבר מ-{hd(first)}, היום הראשון שנאסף מ-GTO — גם לעסקאות "
                             "מחוץ לבורסה, כדי ששני הסוגים יימדדו על אותם ימים.",
                             o_m, j_m, "a-mtd", f"מאז {hd(first)}", day_mode=False))
        return "\n".join(parts)
    parts.append(table_a(f"מתחילת החודש · {month[5:7]}/{month[:4]}",
                         "מצטבר מהראשון בחודש ועד היום האחרון שנאסף.",
                         o_m, j_m, "a-mtd", "החודש", day_mode=False))
    o_y = [r for r in shares if r["date"][:4] == year]
    j_y = [r for r in j_rows if r["date"][:4] == year]
    since = _window(first, f"{year}-01-01")
    parts.append(table_a(f"מתחילת {year}" + (f" · מאז {hd(first)}" if since else ""),
                         (f"מצטבר מ-{hd(first)}, היום הראשון שנאסף מ-GTO — גם לעסקאות מחוץ "
                          "לבורסה." if since else "מצטבר לכל השנה."),
                         o_y, j_y, "a-ytd", f"מתחילת {year}", day_mode=False))
    return "\n".join(parts)


# --- תמונת מצב ------------------------------------------------------------------------

def _strip(tiles: list[tuple], key: str, payload: dict, button: str) -> str:
    """רצועת המספרים. כיתוב של כמה שורות (רשימה) נשבר בשורות ולא באמצע סכום."""
    out = ['<section class="strip wide">']
    for lbl, val, cap in tiles:
        lines = cap if isinstance(cap, list) else [cap]
        out.append(f'<div class="tile"><span class="lbl">{_esc(lbl, quote=False)}</span>'
                   f'<span class="val" dir="ltr">{val}</span>'
                   f'<span class="chg txt">{"<br>".join(_esc(x, quote=False) for x in lines)}'
                   '</span></div>')
    out += ["</section>", otc.embed(key, payload),
            f'<p class="otc-acts otc-acts-strip">{otc.png_button(button, key=key)}</p>']
    return "\n".join(out)


def _windows(first: str, latest: str, year: str) -> list[tuple[str, str]]:
    """(תווית, תחילה) לחודש ולשנה — ואחד בלבד כשהאיסוף התחיל החודש."""
    hd = otc.hebdate
    month = latest[:7]
    if _window(first, f"{month}-01"):
        return [(f"מאז {hd(first)}", first)]
    return [("מתחילת החודש", f"{month}-01"),
            ((f"מתחילת {year}" if not _window(first, f"{year}-01-01") else f"מאז {hd(first)}"),
             max(first, f"{year}-01-01"))]


def tiles_j(j_rows: list[dict], year: str) -> str:
    hd = otc.hebdate
    days = sorted({r["date"] for r in j_rows})
    first, ref = days[0], days[-1]
    day_rows = [r for r in j_rows if r["date"] == ref]
    final, asof = _day_state(day_rows)
    dlabel = f"{'יום המסחר האחרון' if final else 'היום'} · {hd(ref)}"
    day = sum(r["value"] for r in day_rows)
    tiles = [(dlabel, otc.money(day), f"{len(day_rows)} ניירות"
              + ("" if final else f" · נכון ל-{asof}"))]
    for lbl, start in _windows(first, ref, year):
        rows = [r for r in j_rows if start <= r["date"] <= ref]
        tiles.append((lbl, otc.money(sum(r["value"] for r in rows)),
                      f"{_days(len({r['date'] for r in rows}))} · "
                      f"{len({r['security_id'] for r in rows})} ניירות"))

    per_day = [(d, sum(r["value"] for r in j_rows if r["date"] == d)) for d in days[-22:]]
    med = statistics.median([v for _, v in per_day]) if per_day else 0
    top = aggregate(day_rows)[:6]
    blocks = [
        {"type": "stats", "items": [{"label": l, "value": v, "cap": c} for l, v, c in tiles]},
        {"type": "columns", "title": f"העסקאות המתואמות ביום · {len(per_day)} ימי המסחר האחרונים",
         "items": [{"label": f"{d[8:10]}/{d[5:7]}", "value": v, "text": otc.money(v)} for d, v in per_day],
         "maxText": otc.money(max(v for _, v in per_day)), "median": med,
         "medianText": f"חציון: {otc.money(med)}"} if len(per_day) >= 2 else None,
        {"type": "table", "title": f"הגדולות · {dlabel}",
         "cols": [["נייר", "name", "rtl"], ["היקף", "value", "ltr"],
                  ["% ממחזור היום", "pday", "ltr"], ["% מההון (משוער)", "cap", "ltr"]],
         "rows": [{"name": e["name"], "value": otc.money(e["value"]), "pday": _pct(e["pct_day"]),
                   "cap": _pct(e["pct_capital"], 2)} for e in top]} if top else None,
    ]
    payload = otc.card(f"עסקאות מתואמות · {hd(ref)}",
                       "היקף העסקאות המתואמות במניות — ביום ובמצטבר.",
                       blocks, file=f"tlv-jumbo-summary-{ref}", kicker=KICKER_J, source=SRC_GTO)
    return _strip(tiles, "j-summary", payload, "ייצוא תמונת המצב")


def tiles_a(a: dict, j_rows: list[dict], year: str) -> str:
    hd = otc.hebdate
    first = min(r["date"] for r in j_rows)
    shares = [r for r in a["shares"] if r["date"] >= first]
    ref = max(a["latest"] or "", max(r["date"] for r in j_rows))

    def split(rows_o: list[dict], rows_j: list[dict]) -> tuple[float, list[str]]:
        o = sum(r["value"] for r in rows_o)
        j = sum(r["value"] for r in rows_j)
        return o + j, [f"מחוץ לבורסה {otc.money(o)}", f"מתואמות {otc.money(j)}"]

    o_day = [r for r in shares if r["date"] == ref]
    j_day = [r for r in j_rows if r["date"] == ref]
    tot, cap = split(o_day, j_day)
    tiles = [(f"{'היום' if ref == a['latest'] and a['latest'] != a['ref'] else 'יום המסחר האחרון'}"
              f" · {hd(ref)}", otc.money(tot), cap)]
    for lbl, start in _windows(first, ref, year):
        tot, cap = split([r for r in shares if start <= r["date"] <= ref],
                         [r for r in j_rows if start <= r["date"] <= ref])
        tiles.append((lbl, otc.money(tot), cap))

    days = sorted({r["date"] for r in shares} | {r["date"] for r in j_rows})[-22:]
    per_day = [(d, sum(r["value"] for r in shares if r["date"] == d)
                + sum(r["value"] for r in j_rows if r["date"] == d)) for d in days]
    med = statistics.median([v for _, v in per_day]) if per_day else 0
    top = aggregate_all(o_day, j_day)[:6]
    blocks = [
        {"type": "stats", "items": [{"label": l, "value": v, "cap": " · ".join(c)} for l, v, c in tiles]},
        {"type": "columns", "title": f"מחוץ לבורסה ומתואמות ביום · {len(per_day)} ימים",
         "items": [{"label": f"{d[8:10]}/{d[5:7]}", "value": v, "text": otc.money(v)} for d, v in per_day],
         "maxText": otc.money(max(v for _, v in per_day)), "median": med,
         "medianText": f"חציון: {otc.money(med)}"} if len(per_day) >= 2 else None,
        {"type": "table", "title": f"הגדולות · {hd(ref)}",
         "cols": [["נייר", "name", "rtl"], ["מחוץ לבורסה", "otc", "ltr"],
                  ["מתואמות", "jumbo", "ltr"], ["סה\"כ", "value", "ltr"]],
         "rows": [{"name": e["name"], "otc": otc.money(e["otc"]) if e["otc"] else "—",
                   "jumbo": otc.money(e["jumbo"]) if e["jumbo"] else "—",
                   "value": otc.money(e["value"])} for e in top]} if top else None,
    ]
    payload = otc.card(f"מחוץ לבורסה ומתואמות · {hd(ref)}",
                       "העסקאות הגדולות במניות, משני המנגנונים יחד.",
                       blocks, file=f"tlv-blocks-summary-{ref}", kicker=KICKER_A, source=SRC_ALL)
    return _strip(tiles, "a-summary", payload, "ייצוא תמונת המצב")


def method_j(j_rows: list[dict]) -> str:
    hd = otc.hebdate
    first = min(r["date"] for r in j_rows)
    last = max(r["date"] for r in j_rows)
    asof = max((r.get("asof") or "") for r in j_rows if r["date"] == last)
    return ('<p class="note"><strong>איך נגזרו המספרים.</strong> GTO מסמן באות J נייר שהיו '
            'בו עסקאות מתואמות באותו יום, ומוסר את התמורה שלהן בשקלים — אבל לא את מחיר כל '
            'עסקה. לכן אין כאן סטייה משער הבסיס כמו בעסקאות מחוץ לבורסה. "% ממחזור היום" הוא '
            'התמורה המתואמת חלקי מחזור הנייר באותו יום, שכבר כולל אותה, ולכן אינו עובר 100%. '
            '"% מההון" מחושב ביחידות משוערות — התמורה חלקי השער האחרון — מול ההון המונפק. '
            f'הנתונים נאספים מ-{hd(first)}; העדכון האחרון: {hd(last)}'
            + (f" {asof[11:16]}" if len(asof) >= 16 else "") + ".</p>")


def method_a() -> str:
    return ('<p class="note"><strong>איך חוברו שני המקורות.</strong> לכל נייר, ההיקף מחוץ '
            'לבורסה מסקירת הבורסה וההיקף במתואמות מ-GTO, באותם ימים. "% מההון" מצרף את '
            'היחידות מחוץ לבורסה בפועל ואת היחידות המשוערות במתואמות, מול ההון המונפק. '
            'כל הטבלאות כאן מתחילות ביום הראשון שנאסף מ-GTO — גם לעסקאות מחוץ לבורסה — '
            'כדי ששני הסוגים יימדדו על אותה תקופה.</p>')


# --- לשוניות --------------------------------------------------------------------------

TABS_JS = """<script>
(function () {
  var bar = document.querySelector(".otc-tabs");
  if (!bar) return;
  var tabs = Array.prototype.slice.call(bar.querySelectorAll("[role=tab]"));
  function show(id, remember) {
    var hit = tabs.filter(function (t) { return t.getAttribute("data-tab") === id; })[0];
    if (!hit) return;
    tabs.forEach(function (t) {
      var on = t === hit;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      var pane = document.getElementById(t.getAttribute("aria-controls"));
      if (pane) pane.hidden = !on;
    });
    if (remember && window.history && history.replaceState) {
      history.replaceState(null, "", hit === tabs[0]
        ? location.pathname + location.search : "#" + id);
    }
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { show(t.getAttribute("data-tab"), true); });
    t.addEventListener("keydown", function (e) {
      // מימין לשמאל: החץ השמאלי מתקדם ללשונית הבאה
      var n = tabs.length, j = -1;
      if (e.key === "ArrowLeft") j = (i + 1) % n;
      else if (e.key === "ArrowRight") j = (i - 1 + n) % n;
      else if (e.key === "Home") j = 0;
      else if (e.key === "End") j = n - 1;
      if (j < 0) return;
      e.preventDefault();
      tabs[j].focus();
      show(tabs[j].getAttribute("data-tab"), true);
    });
  });
  var h = (location.hash || "").slice(1);
  if (h) show(h, false);
})();
</script>"""


def tabs(a: dict, otc_html: str, j_rows: list[dict], year: str) -> str:
    """שלוש לשוניות: מחוץ לבורסה (ברירת המחדל), מתואמות, והכל יחד.

    **ברירת המחדל נשארת מחוץ לבורסה.** זה מה שהעמוד הציג עד היום, וקישורים
    קיימים אליו צריכים להמשיך להראות את אותו דבר. #jumbo ו-#all פותחים
    ישירות את הלשוניות האחרות. בלי JS — שלושתן מוצגות זו אחר זו.
    """
    panes = [
        ("otc", "מחוץ לבורסה", otc_html),
        ("jumbo", "מתואמות", "\n".join([tiles_j(j_rows, year), periods_j(j_rows, year),
                                        method_j(j_rows)])),
        ("all", "הכל יחד", "\n".join([tiles_a(a, j_rows, year), periods_a(a, j_rows, year),
                                      method_a()])),
    ]
    bar = ['<div class="otc-tabs" role="tablist" aria-label="סוג העסקאות">']
    body = []
    for i, (tid, label, html) in enumerate(panes):
        sel = i == 0
        bar.append(f'<button type="button" role="tab" id="tab-{tid}" data-tab="{tid}" '
                   f'aria-controls="pane-{tid}" aria-selected="{"true" if sel else "false"}" '
                   f'tabindex="{0 if sel else -1}">{label}</button>')
        body.append(f'<div class="otc-pane" role="tabpanel" id="pane-{tid}" '
                    f'aria-labelledby="tab-{tid}"{"" if sel else " hidden"}>\n{html}\n</div>')
    bar.append("</div>")
    return "\n".join(bar + body + [
        '<noscript><style>.otc-pane[hidden]{display:block!important}.otc-tabs{display:none}'
        '</style></noscript>', TABS_JS])
