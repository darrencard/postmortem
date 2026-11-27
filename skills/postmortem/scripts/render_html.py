"""The review as one self-contained HTML page, in the Leader Report style guide and the Landing Loop's one visual
family, and its Markdown twin.

The page uses the report's own stylesheet, taken whole from its template (assets/vendor/template.html, vendored
byte-identical at a pinned commit), and draws its picture with svgkit (scripts/vendor/svgkit.py, vendored
byte-identical from landing-loop). Only a few rules for this page's layout are added.

It reads top down for someone who has never seen the loop: the shared header, the verdict as the heading, the
project's status as did-it-land wrote it, then the picture: one timeline from the window opening, through each
incident and the review, to each fix's due date with its owner. One next step follows: the fix review, owned by the
person the landing brief names. What changed and who fixes it sit in two columns, then the incidents and what went
well; evidence, sources, model ids and the record key fold under "For your engineers". Public copy uses plain words:
after-action review, project, target, time to fix, AI usage per task, the large model.

Colour means one thing each: green, grey-white and red only inside the status word, printed from landed.status and
never computed; brass for a person's call (each fix's owner, and who decides); ink for what happened. The picture
draws only figures the page prints, and its aria-label states the answer.

Nothing is loaded from the network, nothing depends on the clock or the machine, and every piece of text from a
source or a person is escaped.

Standard library only. Python 3.11 or later.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import loop  # noqa: E402
import svgkit as sk  # noqa: E402  (vendored, unchanged; see VENDORED.json)

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "vendor" / "template.html"
STYLE = re.compile(r"<style>(.*?)</style>", re.S)

# Layout for this page only. Everything else comes from the template's stylesheet and svgkit.CSS.
PAGE_CSS = """
main.solo{margin-left:0}
.solo .slide{min-height:0}
.solo .slide.cover{min-height:0;padding-top:40px;padding-bottom:48px;justify-content:flex-start}
.solo h1{font-size:clamp(34px,4.6vw,60px);line-height:1;letter-spacing:-.04em;max-width:22ch;margin-bottom:20px}
.solo .lede{margin-bottom:24px}
.solo .lede b{color:var(--t1);font-weight:500}
.marks{display:flex;flex-wrap:wrap;align-items:center;gap:10px 28px;margin:0 0 20px;font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.marks>span{display:inline-flex;align-items:center;gap:10px}
.chip{font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t1);border:1px solid var(--line3);border-radius:3px;padding:1px 6px;white-space:nowrap}
.panel{border:1px solid var(--line);border-radius:12px;background:var(--s1);padding:24px 28px 20px}
@media (min-width:1100px){.panel .sk{display:grid;grid-template-columns:640px minmax(0,1fr);gap:16px 40px;align-items:center}.panel .sk figcaption{margin-top:0;flex-direction:column;align-items:flex-start}}
.next{margin-top:28px;display:grid;grid-template-columns:200px minmax(0,1fr);gap:8px 32px;align-items:baseline;border:1px solid var(--brass);border-radius:12px;padding:20px 24px;background:var(--brass-bg)}
.next>b{font:400 10px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--brass)}
.next p{margin:0;font-size:16px;line-height:1.5;color:var(--t1)}
.next .who{display:flex;flex-wrap:wrap;gap:4px 24px;margin-top:10px;font:400 11.5px/16px var(--mono);color:var(--brass)}
.next .who span::before{font-size:10px;letter-spacing:.1em;color:var(--t3);margin-right:8px}
.next .who .o::before{content:"DECIDES"}.next .who .d::before{content:"ON"}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px 56px;align-items:start}
.cols h3{margin-bottom:8px}
.say{max-width:76ch;margin:0 0 28px;font-size:16px;line-height:1.55;color:var(--t1)}
.items{margin:0;padding:0;list-style:none}
.items li{display:grid;grid-template-columns:32px minmax(0,1fr);gap:4px 12px;border-top:1px solid var(--line);padding:12px 0;font-size:13.5px;line-height:1.55;color:var(--t2)}
.items .id{font:400 11px/22px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--t3)}
.items p{margin:0;color:var(--t1)}
.items small{display:block;margin-top:4px;font-size:12.5px;line-height:1.5;color:var(--t3)}
.items .own{display:flex;flex-wrap:wrap;gap:4px 18px;margin-top:6px;font:400 11.5px/18px var(--mono)}
.items .own .o{color:var(--brass)}
.items .own .d{color:var(--t2)}
.items .own .d::before{content:"DUE ";font-size:10px;letter-spacing:.1em;color:var(--t3)}
.figs{margin:0;display:grid}
.figs>div{display:grid;grid-template-columns:132px minmax(0,1fr);gap:4px 16px;border-top:1px solid var(--line);padding:11px 0}
.figs dt{font:400 10px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.figs dd{margin:0;font-size:13.5px;line-height:1.55;color:var(--t2)}
.figs dd b{color:var(--t1);font-weight:500}
.tgt{margin:0 0 8px;font-size:13px;color:var(--t2)}
.solo details{margin-top:4px}
.solo details>*:not(summary){margin-top:12px}
.solo details p,.solo details li{margin:0 0 10px;font-size:13px;color:var(--t2);max-width:80ch}
.solo details ul{padding-left:18px}
.tablewrap td,.tablewrap th{overflow-wrap:anywhere}
::selection{background:var(--t1);color:var(--bg)}
:focus-visible{outline-color:var(--t1)}
.foot{max-width:1120px;margin:0 auto;padding:28px 40px 64px;color:var(--t3);font-size:12px}
@media (max-width:980px){.foot{padding:24px 16px 48px}.solo .slide.cover{padding-top:24px}.cols,.next{grid-template-columns:1fr}.panel{padding:18px 16px 16px}
.stack table,.stack tbody,.stack tr,.stack td{display:block}.stack tr:first-child{display:none}.stack tr{padding:10px 16px;border-bottom:1px solid var(--line)}
.stack td{border:0;padding:3px 0;display:grid;grid-template-columns:118px 1fr;gap:12px}.stack td.num{text-align:left;white-space:normal}
.stack td::before{content:attr(data-l);font:400 10px/20px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}}
@media (max-width:560px){.figs>div{grid-template-columns:1fr;gap:0}}
"""

NUMBER_WORDS = ("No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve")

# The written parts and the record's own sentences, in the page's words. The record keeps its words; the engineers'
# fold prints them as written.
WORDS = (
    (r", vendor-[a-z0-9]+/xl\b", ""),
    (r"\bvendor-[a-z0-9]+/xl\b", "the large model"),
    (r"\bcontext limit\b", "length limit"),
    (r"\b[Tt]okens per task\b", "AI usage per task"),
    (r"\bThe eval run\b", "The quality test"),
    (r"\beval target\b", "quality target"),
    (r"\bthe cost-budget-check result\b", "the cost check's result"),
    (r"\bthe eval-kit result\b", "the quality test's result"),
    (r"\bcost-budget-check\b", "the cost check"),
    (r"\beval-kit\b", "the quality test"),
    (r"\bas the brief's line says\b", "as the landing brief's split of who does what says"),
    (r"\bThe line held\b", "The split of who does what held"),
    (r"\bthe brief's\b", "the landing brief's"),
    (r"(^|\. )v(\d+(?:\.\d+)+)\b", r"\1Version \2"),
    (r"\bv(\d+(?:\.\d+)+)\b", r"version \1"),
    (r"\bheld-out pass rate\b", "pass rate on test cases kept back"),
    (r"\binside noise\b", "too close to call"),
    (r"\bthe PRD\b", "the build plan"),
    (r"\bthe bar\b", "the target"),
    (r"\bBrief score\b", "Plan score"),
)
STEP = {"01 Decide": "Decide", "02 Spec": "Build plan check", "03 Build, cost": "Cost check", "03 Build, evals": "Quality test", "04 Learn, did-it-land": "Did it land"}


def e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def plain(text: str) -> str:
    out = text
    for pattern, to in WORDS:
        out = re.sub(pattern, to, out)
    # A sentence that now opens with a replaced name ("the cost check") starts with a capital.
    return out[:1].upper() + out[1:] if out[:4] != text[:4] else out


# The record's figure names, in plain words, for the evidence lines.
LINE = {"tokens_per_task": "AI usage per task", "cost_per_task": "cost per task", "price_per_token": "AI price per unit"}
PART = {"prior": "before", "actual": "actual", "budget": "budget"}


def fig_plain(f: dict[str, Any], labelled: bool = False) -> str:
    """A figure as the page prints it, with tokens in plain words: units of AI usage. A labelled figure drops the
    "per task" its label already says."""
    if f["unit"] == "tokens per task":
        return f"{f['value']:,.10g} units" if labelled else f"{f['value']:,.10g} units of AI usage per task"
    shown = loop.shown(f).replace("per token", "per unit")
    return shown.removesuffix(" per task") if labelled else shown


def ref_plain(ref: str, f: dict[str, Any]) -> str:
    """One piece of evidence, named in plain words."""
    kind, _, rest = ref.partition(":")
    if kind == "incident":
        return f"incident {rest}, fixed in {loop.shown(f)}"
    parts = rest.split("/")
    if parts[:2] == ["cost", "lines"] and len(parts) == 4:
        return f"{LINE.get(parts[2], parts[2].replace('_', ' '))}, {PART.get(parts[3], parts[3])}: {fig_plain(f, labelled=True)}"
    if parts[:2] == ["cost", "driver"]:
        return f"cost over budget from that model: {fig_plain(f)}"
    if parts[:2] == ["evals", "figures"] and parts[2].startswith("pass_rate@"):
        return f"pass rate on test cases kept back, version {parts[2].split('@', 1)[1].removeprefix('v')}: {fig_plain(f)}"
    return fig_plain(f)


def stylesheet() -> str:
    try:
        found = STYLE.search(TEMPLATE.read_text(encoding="utf-8"))
    except OSError:
        found = None
    return found.group(1) if found else ""


def count_word(n: int) -> str:
    return NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else str(n)


def status_mark(status: str | None) -> str:
    """landed.status as the template draws it, the word always printed. The only place a status colour appears."""
    if status is None:
        return '<span class="chip" data-from="landed">not read: run did-it-land</span>'
    return f'<span class="st {e(status)}" data-from="landed">{e(status)}</span>'


def short(i: dict[str, Any]) -> str:
    """Time to fix, short, for the picture: the figure's own value and a short unit."""
    f = i["time_to_restore"]
    return f"{f['value']:g} min" if f["unit"] == "minutes" else loop.shown(f)


def stamp(text: str) -> str:
    return text[:16].replace("T", " ")


def _day(text: str) -> int:
    return dt.date.fromisoformat(text[:10]).toordinal()


# The signature picture


def timeline(key: dict[str, Any], variant: str) -> str:
    """One axis in time: the window opening, each incident (ink) with its time to fix, the review, the fix review (a
    person's call, brass), and one row per fix from the review to its due date, its owner in a brass chip."""
    wide = variant == "wide"
    width = 640.0 if wide else float(sk.TALL)
    x0, x1 = (64.0, 540.0) if wide else (8.0, 252.0)
    fixes = [f for f in key["fixes"] if f.get("due")]
    days = [_day(key["window"]["from"]), _day(key["as_of"])] + [_day(f["due"]) for f in fixes]
    if key.get("review_on"):
        days.append(_day(key["review_on"]))
    lo, hi = min(days), max(days)
    x = sk.scale((lo, hi), (x0, x1))
    axis = 104.0
    parts = [sk.rule(x0, axis, x1, axis, tone=sk.LINE2)]
    # Month ticks: the names only, so the picture adds no number of its own.
    d = dt.date.fromordinal(lo).replace(day=1)
    while d.toordinal() <= hi:
        if d.toordinal() >= lo:
            mx = x(d.toordinal())
            parts.append(sk.rule(mx, axis - 3, mx, axis + 3, tone=sk.LINE3))
            parts.append(sk.label(mx + 4, axis + 16, d.strftime("%b")))
        d = (d + dt.timedelta(days=32)).replace(day=1)
    parts.append(sk.deadline(x(lo), 14, axis, tone=sk.LINE3))
    parts.append(sk.label(x(lo) + 6, 24, f"From {key['window']['from']}"))
    # Incidents: an ink mark on the day it started, its id and time to fix beside it. A label that would cross the
    # review line sits on the left; one that would touch another drops a row.
    rx = x(_day(key["as_of"]))
    placed: list[tuple[int, float, float]] = []
    for i in key["incidents"]:
        cx = x(_day(i["started_at"]))
        w = max(sk.label_width(i["id"]), sk.label_width(short(i)))
        left = cx < rx < cx + 12 + w + 4
        span = (cx - 12 - w, cx - 12) if left else (cx + 12, cx + 12 + w)
        row = next((r for r in range(4) if not any(pr == r and span[0] < b + 8 and a < span[1] + 8 for pr, a, b in placed)), 3)
        placed.append((row, cx - 6, span[1]) if not left else (row, span[0], cx + 6))
        y = 44 + row * 30
        parts.append(sk.rule(cx, y + 12, cx, axis, tone=sk.INK))
        parts.append(sk.tile(cx - 6, y, 12, 12, filled=True, tone=sk.INK))
        lx, anchor = (cx - 12, "end") if left else (cx + 12, "start")
        parts.append(sk.label(lx, y + 10, i["id"], anchor=anchor, tone=sk.INK))
        parts.append(sk.label(lx, y + 24, short(i), anchor=anchor))
    # The review, and the fix review, where the person who decides makes the call.
    top = axis + 40
    step = 30.0 if wide else 50.0
    bottom = top + step * max(len(fixes), 1)
    parts.append(sk.rule(rx, 14, rx, bottom - step + 10, tone=sk.LINE3, dashed=True))
    # The review's label sits left of its line on desktop, right of it on a phone, clear of the window's label.
    gx, ga = (rx - 6, "end") if wide else (rx + 6, "start")
    parts.append(sk.label(gx, 24, "Review", anchor=ga, tone=sk.INK2))
    parts.append(sk.label(gx, 38, key["as_of"], anchor=ga))
    if key.get("review_on"):
        fx = x(_day(key["review_on"]))
        parts.append(sk.person(fx, axis - 3, size=14))
        parts.append(sk.label(fx + 10, axis - 20, "Fix review", tone=sk.BRASS))
    # One row per fix: its owner in a brass chip, a line from the review to the due date, and the date.
    for n, f in enumerate(fixes):
        y = top + step * n
        if wide:
            parts.append(sk.label(0, y + 4, f["id"], tone=sk.INK2))
            parts.append(sk.chip(rx - 12 - sk.chip_width(f["owner"]), y - 9, f["owner"], tone=sk.BRASS))
            by = y
        else:
            parts.append(sk.label(0, y + 4, f["id"], tone=sk.INK2))
            parts.append(sk.chip(28, y - 9, f["owner"], tone=sk.BRASS))
            by = y + 22
        dx = x(_day(f["due"]))
        parts.append(sk.rule(rx, by, dx, by, tone=sk.INK, width=sk.STROKE))
        parts.append(sk.point(dx, by, r=4))
        parts.append(sk.label(dx + 9, by + 4, f["due"], tone=sk.INK2))
    n = len(key["incidents"])
    aria = f"{count_word(n)} incident{'' if n == 1 else 's'} from {key['window']['from']} to {key['as_of']}"
    if key["incidents"]:
        aria += ": " + "; ".join(f"{i['id']} on {i['started_at'][:10]}, fixed in {loop.shown(i['time_to_restore'])}" for i in key["incidents"])
    aria += f". {len(fixes)} fix{'' if len(fixes) == 1 else 'es'}, each with one owner"
    aria += f", due from {min(f['due'] for f in fixes)} to {max(f['due'] for f in fixes)}." if fixes else "."
    if key.get("review_on"):
        aria += f" The fix review is on {key['review_on']}."
    return sk.frame("".join(parts), label=aria, height=bottom + (4 if wide else 12), width=width, variant=variant)


# The words


def heading(key: dict[str, Any]) -> str:
    """The verdict, with no status word of its own: how many incidents, and whether every fix is owned and dated."""
    n = len(key["incidents"])
    owned, total = key["figures"]["fixes_owned"]["value"], key["figures"]["fixes"]["value"]
    first = f"{key['brief']['title']} had {count_word(n).lower()} incident{'' if n == 1 else 's'} since {key['window']['from']}."
    if total and owned == total:
        every = "Both" if total == 2 else "The one" if total == 1 else f"All {count_word(total).lower()}"
        return f"{first} {every} fix{'' if total == 1 else 'es'} {'has' if total == 1 else 'have'} one owner and a due date."
    return f"{first} {count_word(owned)} of {total} fixes have one owner and a due date."


def lede(key: dict[str, Any]) -> str:
    b = key["brief"]
    return (
        f"{e(b['title'])} is a project you expect to move a number: {e(b['metric'].lower())}, to {e(b['bar'])} by {e(b['by'])}. "
        "That target comes from its <b>landing brief</b>, a one-page plan: what good looks like, by when, at what cost. "
        "This after-action review is blameless: it says what changed in the system and the process, not who erred."
    )


def caption(key: dict[str, Any]) -> str:
    return (
        f"Time runs left to right from {key['window']['from']}. Ink marks are incidents, with how long each took to fix. "
        f"The dashed line is this review, {key['as_of']}; each row runs from it to a fix's due date, its owner in brass."
        + (f" The brass figure marks the fix review, {key['review_on']}." if key.get("review_on") else "")
    )


def evidence(c: dict[str, Any]) -> str:
    return "; ".join(ref_plain(ref, f) for ref, f in c["cited"].items())


def changes(key: dict[str, Any]) -> str:
    items = []
    for c in key["what_changed"]:
        ev = evidence(c)
        why = f"<small>Evidence: {e(ev)}.</small>" if ev else ""
        items.append(f'<li><span class="id">{e(c["id"])}</span><span><p>{e(plain(c["change"]))}</p>{why}</span></li>')
    return f'<ul class="items">{"".join(items)}</ul>'


def fixes(key: dict[str, Any]) -> str:
    items = []
    for f in key["fixes"]:
        addresses = ", ".join(f.get("addresses") or [])
        items.append(
            f'<li><span class="id">{e(f["id"])}</span><span><p>{e(plain(f["fix"]))}</p><small>Done when: {e(plain(f["done_when"]))} Addresses {e(addresses)}.</small>'
            f'<span class="own"><span class="o">{e(f["owner"])}</span><span class="d">{e(f["due"])}</span></span></span></li>'
        )
    return f'<ul class="items">{"".join(items)}</ul>'


class Table:
    """A table whose cells carry their column name, so a phone shows each row as labelled lines."""

    def __init__(self, heads: tuple[str, ...]) -> None:
        self.heads = heads
        self.rows: list[str] = []

    def row(self, *cells: tuple[str, str]) -> None:
        tds = []
        for head, (cls, body) in zip(self.heads, cells, strict=True):
            attr = f' class="{cls}"' if cls else ""
            tds.append(f'<td{attr} data-l="{e(head)}">{body}</td>')
        self.rows.append("<tr>" + "".join(tds) + "</tr>")

    def html(self) -> str:
        head = "<tr>" + "".join(f"<th>{e(h)}</th>" for h in self.heads) + "</tr>"
        return f'<div class="tablewrap stack"><table>{head}{"".join(self.rows)}</table></div>'


def incidents(key: dict[str, Any]) -> str:
    if not key["incidents"]:
        return "<p>No incidents started in the window.</p>"
    tab = Table(("Incident", "Severity", "Started (UTC)", "Time to fix"))
    for i in key["incidents"]:
        tab.row(
            ("", e(i["id"])),
            ("", e(i["severity"] or "not set")),
            ("mo", e(stamp(i["started_at"]))),
            ("num", e(loop.shown(i["time_to_restore"]))),
        )
    return tab.html()


def context_figures(r: dict[str, Any]) -> str:
    """A step's figures in one plain sentence. Cost reads each line's actual against its budget; did-it-land reads
    now, on the due date and the target, in the order review.context() takes them."""
    figs = r["figures"]
    if r["key"] == "cost" and len(figs) % 2 == 0:
        pairs = [(figs[i], figs[i + 1]) for i in range(0, len(figs), 2)]
        return "; ".join(
            f"{'AI usage' if a['unit'] == 'tokens per task' else 'cost'} {fig_plain(a, labelled=True)} per task, against a budget of {fig_plain(b, labelled=True)}"
            for a, b in pairs
        )
    if r["key"] == "landed" and len(figs) in (2, 3):
        names = ("now", "on the due date", "target") if len(figs) == 3 else ("now", "target")
        return ", ".join(f"{n} {fig_plain(f)}" for n, f in zip(names, figs, strict=True))
    return "; ".join(fig_plain(f) for f in figs)


def earlier_rows(key: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """Each earlier step: its plain name, its word (if any), what it says and its figures, as printed."""
    rows = []
    for r in key["context"]:
        word = plain(r["word"]).lower() if r["word"] else ""
        rows.append((STEP.get(r["label"], r["label"]), word, plain(r["text"]), context_figures(r)))
    return rows


def earlier(key: dict[str, Any]) -> str:
    out = []
    for name, word, text, figs in earlier_rows(key):
        chip = f'<span class="chip">{e(word)}</span> ' if word else ""
        out.append(f"<div><dt>{e(name)}</dt><dd>{chip}{e(text)}{' <b>' + e(figs) + '</b>' if figs else ''}</dd></div>")
    return f'<dl class="figs">{"".join(out)}</dl>'


def fold(title: str, body: str) -> str:
    return f"<details><summary>{e(title)}</summary>{body}</details>"


def engineers(key: dict[str, Any]) -> str:
    """Evidence with its sources, the written parts as written (model ids included), and the record key."""
    st = key["landed_status"]
    ev = Table(("Change", "Evidence", "Figure", "Window", "Source"))
    for c in key["what_changed"]:
        for ref, f in c["cited"].items():
            ev.row(("mono", e(c["id"])), ("mono", e(ref)), ("num", e(loop.shown(f))), ("mo", e(loop.window_text(f))), ("", e(f["source"])))
    ctx = Table(("Step", "Word", "Figure", "Window", "Source"))
    for r in key["context"]:
        for f in r["figures"] or [None]:
            cells = (e(loop.shown(f)), e(loop.window_text(f)), e(f["source"])) if f else ("none", "", e(r["text"]))
            ctx.row(("", e(r["label"])), ("mono", e(r["word"] or "")), ("num", cells[0]), ("mo", cells[1]), ("", cells[2]))
    written = "".join(f"<li>{e(c['id'])}: {e(c['change'])}</li>" for c in key["what_changed"])
    written += "".join(f"<li>{e(f['id'])} ({e(f.get('kind') or 'fix')}): {e(f['fix'])} Done when: {e(f['done_when'])}</li>" for f in key["fixes"])
    status = f"printed from <code>{e(st['from'])}</code> as {e(st['computed_by'])} wrote it" if st["printed"] else "not read"
    notes = (
        f"<p>Status: {status}, never computed here. Review kind: {e(key['review'])}. Window {e(key['window']['from'])} to {e(key['window']['to'])}. "
        f"Author: {e(key['author'])}.</p><p>Check: {e(key['check'])}</p><p>Incidents: {e(key['figures']['incidents']['source'])}.</p>"
        "<p>The review adds its page to the project file: the <code>postmortem</code> key of <code>landing/&lt;bet&gt;.json</code>, and no other key. "
        "With --csv it also writes the fixes for a tracker import.</p>"
    )
    body = f"<p>The written parts, as written:</p><ul>{written}</ul>{ev.html()}{ctx.html()}{notes}"
    if not key["brief_unchanged"]:
        body = "<p>The landing brief changed after the record opened. This review reads it as it is now.</p>" + body
    return fold("For your engineers", body)


def next_step(key: dict[str, Any]) -> str:
    on = key["review_on"]
    lead = f"Hold the fix review on {on}" if on else "Set a date for the fix review"
    return f"{lead}: check each fix against its done-when test, and decide what to do about any that slip."


def page(key: dict[str, Any]) -> str:
    b, st, ill = key["brief"], key["landed_status"], key["illustrative"]
    title = f"After-action review: {b['title']}"
    header = sk.page_header("postmortem", date=f"As of {key['as_of']}", version="v" + key["tool"].rsplit(" ", 1)[-1], illustrative=ill)
    marks = f'<p class="marks"><span>Project status, from did-it-land {status_mark(st["printed"])}</span><span>Review <span class="chip">{e(key["review"])}</span></span></p>'
    pic = sk.figure(timeline(key, "wide"), timeline(key, "tall"), caption=caption(key), illustrative=ill)
    step = (
        f'<div class="next"><b>What to do next</b><div><p>{e(next_step(key))}</p>'
        f'<span class="who"><span class="o">{e(b["decides"])}</span><span class="d">{e(key["review_on"] or "not set")}</span></span></div></div>'
    )
    cover = f'<section class="slide cover">{header}<h1>{e(heading(key))}</h1><p class="lede">{lede(key)}</p>{marks}<div class="panel">{pic}</div>{step}</section>'
    first = (
        f'<section class="slide"><div class="meta"><span>What changed, and who fixes it</span></div><p class="say">{e(plain(key["summary"]))}</p><div class="cols">'
        f"<div><h3>What changed</h3>{changes(key)}</div><div><h3>Who fixes it, by when</h3>{fixes(key)}</div></div></section>"
    )
    well = "".join(f'<li><span class="id">+</span><span><p>{e(plain(t))}</p></span></li>' for t in key["what_went_well"])
    well_html = f'<h3 style="margin-top:28px">What went well</h3><ul class="items">{well}</ul>' if well else ""
    second = (
        '<section class="slide"><div class="meta"><span>The record</span></div><div class="cols">'
        f"<div><h3>Incidents ({e(key['figures']['incidents']['value'])})</h3>{incidents(key)}{well_html}</div>"
        f'<div><h3>What the earlier steps found</h3><p class="tgt">Target: {e(b["bar"])} {e(b["metric"].lower())} by {e(b["by"])}.</p>{earlier(key)}</div></div></section>'
    )
    more = f'<section class="slide"><div class="meta"><span>Detail</span></div>{engineers(key)}</section>'
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><style>{stylesheet()}{sk.CSS}{PAGE_CSS}</style></head><body><main class="solo">'
        f"{cover}{first}{second}{more}"
        '<p class="foot">This review is blameless: it says what the system and the process allowed, not who erred. '
        "The project's status is did-it-land's, printed as it wrote it, never computed here. Every figure is computed in code from the source named.</p>"
        "</main></body></html>\n"
    )


# The Markdown twin


def md(text: Any) -> str:
    s = " ".join(str(text or "").split())
    for a, b in (("\\", "\\\\"), ("|", "\\|"), ("<", "&lt;"), (">", "&gt;"), ("`", "\\`"), ("[", "\\["), ("]", "\\]"), ("*", "\\*"), ("_", "\\_")):
        s = s.replace(a, b)
    return s


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def markdown(key: dict[str, Any]) -> str:
    """The plain-text twin of the page: the same words and figures, in the same order."""
    b, st = key["brief"], key["landed_status"]
    out: list[str] = []
    w = out.append
    w(f"# {md(heading(key))}")
    w("")
    ill = " Illustrative: Acme is an invented company, and every figure comes from a synthetic fixture." if key["illustrative"] else ""
    w(f"postmortem v{key['tool'].rsplit(' ', 1)[-1]}. As of {key['as_of']}.{ill}")
    w("")
    w(md(_text(lede(key))))
    w("")
    w(f"**Project status, from did-it-land:** {st['printed'] or 'not read (run did-it-land)'} · **Review:** {key['review']}")
    w("")
    w("## What to do next")
    w("")
    w(f"{md(next_step(key))} Decides: {md(b['decides'])}.")
    w("")
    w("## What changed, and who fixes it")
    w("")
    w(md(plain(key["summary"])))
    w("")
    w("### What changed")
    w("")
    for c in key["what_changed"]:
        ev = evidence(c)
        w(f"- **{md(c['id'])}.** {md(plain(c['change']))}" + (f" Evidence: {md(ev)}." if ev else ""))
    w("")
    w("### Who fixes it, by when")
    w("")
    w("| Fix | Done when | Owner | Due | Addresses |")
    w("|---|---|---|---|---|")
    for f in key["fixes"]:
        w(f"| {md(f['id'])}. {md(plain(f['fix']))} | {md(plain(f['done_when']))} | {md(f['owner'])} | {md(f['due'])} | {md(', '.join(f.get('addresses') or []))} |")
    w("")
    w(f"## Incidents: {loop.shown(key['figures']['incidents'])}")
    w("")
    if key["incidents"]:
        w("| Incident | Severity | Started (UTC) | Fixed (UTC) | Time to fix |")
        w("|---|---|---|---|---|")
        for i in key["incidents"]:
            w(f"| {md(i['id'])} | {md(i['severity'] or 'not set')} | {stamp(i['started_at'])} | {stamp(i['restored_at'])} | {loop.shown(i['time_to_restore'])} |")
    else:
        w("No incidents started in the window.")
    w("")
    if key["what_went_well"]:
        w("## What went well")
        w("")
        for t in key["what_went_well"]:
            w(f"- {md(plain(t))}")
        w("")
    w("## What the earlier steps found")
    w("")
    w(f"Target: {md(b['bar'])} {md(b['metric'].lower())} by {md(b['by'])}.")
    w("")
    for name, word, text, figs in earlier_rows(key):
        w(f"- **{name}:** {md(word) + '. ' if word else ''}{md(text)}" + (f" {md(figs)}" if figs else ""))
    w("")
    w("## For your engineers")
    w("")
    w("The written parts, as written:")
    w("")
    for c in key["what_changed"]:
        w(f"- {md(c['id'])}: {md(c['change'])}")
    for f in key["fixes"]:
        w(f"- {md(f['id'])} ({md(f.get('kind') or 'fix')}): {md(f['fix'])} Done when: {md(f['done_when'])}")
    w("")
    w("| Change | Evidence | Figure | Window | Source |")
    w("|---|---|---|---|---|")
    for c in key["what_changed"]:
        for ref, f in c["cited"].items():
            w(f"| {md(c['id'])} | {md(ref)} | {loop.shown(f)} | {loop.window_text(f)} | {md(f['source'])} |")
    w("")
    w("| Step | Word | Figure | Window | Source |")
    w("|---|---|---|---|---|")
    for r in key["context"]:
        for f in r["figures"] or [None]:
            cells = (loop.shown(f), loop.window_text(f), md(f["source"])) if f else ("none", "", md(r["text"]))
            w(f"| {r['label']} | {md(r['word'] or '')} | {cells[0]} | {cells[1]} | {cells[2]} |")
    w("")
    status = f"printed from `{st['from']}` as {st['computed_by']} wrote it" if st["printed"] else "not read"
    w(f"Status: {status}, never computed here. Review kind: {key['review']}. Window {key['window']['from']} to {key['window']['to']}. Author: {md(key['author'])}.")
    w("")
    w(f"Check: {key['check']}")
    w("")
    w(f"Incidents: {md(key['figures']['incidents']['source'])}.")
    w("")
    w("The review adds its page to the project file: the `postmortem` key of `landing/<bet>.json`, and no other key.")
    if not key["brief_unchanged"]:
        w("")
        w("The landing brief changed after the record opened. This review reads it as it is now.")
    return "\n".join(out) + "\n"
