"""The review as one self-contained HTML page, in the Leader Report style guide and the Landing Loop's one visual
family, and its Markdown twin.

The page uses the report's own stylesheet, taken whole from its template (assets/vendor/template.html, vendored
byte-identical at a pinned commit), and draws its picture with svgkit (scripts/vendor/svgkit.py, vendored
byte-identical from landing-loop). Only a few rules for this page's layout are added.

It reads top down for someone who has never seen the loop: the shared header, the verdict as the heading, the
project's status as did-it-land wrote it, then the picture as scorecard rows (svgkit 1.2.0): one row per incident,
named by what happened, with one ink bar for its time to fix scaled to the longest (there is no plan for time to fix,
so no plan bar and no hatching), then one row per fix with its due date and its one owner in brass. Geist Mono 12px
for labels and figures, Geist 14px for names, fixed-height bars with no text in them. One next step follows: the fix
review, owned by the person the landing brief names. What changed and who fixes it sit in two columns, then the
incidents and what went well; evidence, sources, model ids and the project file's key fold under "For your
engineers". Public copy uses plain words: after-action review, project, target, time to fix, AI usage per task, the
large model. Cited check words print in their skill's words: eval-kit's "not confirmed: too close to call",
did-it-land's "inside normal ups and downs".

Colour means one thing each: green, grey-white and red only inside the status word, printed from landed.status and
never computed; brass for a person's call (each fix's owner, and who decides); ink for what happened. Words are
text, never boxed chips. The picture draws only figures the page prints, and its aria-label states the answer.

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
# In the scorecard, a row with no picture (a fix) gives its name the picture column too, so names stay on one line,
# and the figure column prints in one case, numerals and capitals, as /update does.
PAGE_CSS = """
main.solo{margin-left:0}
.solo .slide{min-height:0}
.solo .slide.cover{min-height:0;padding-top:40px;padding-bottom:48px;justify-content:flex-start}
.solo h1{font-size:clamp(34px,4.6vw,60px);line-height:1;letter-spacing:-.04em;text-wrap:balance;margin-bottom:20px}
.solo .lede{margin-bottom:24px}
.solo .lede b{color:var(--t1);font-weight:500}
.marks{display:flex;flex-wrap:wrap;align-items:center;gap:10px 28px;margin:0 0 20px;font:400 11px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.marks>span{display:inline-flex;align-items:center;gap:10px}
.wd{font:400 12px/16px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--t1);white-space:nowrap}
.next{margin-top:28px;display:grid;grid-template-columns:200px minmax(0,1fr);gap:8px 32px;align-items:baseline;border:1px solid var(--brass);border-radius:12px;padding:20px 24px;background:var(--brass-bg)}
.next>b{font:400 11px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--brass)}
.next p{margin:0;font-size:16px;line-height:1.5;color:var(--t1)}
.next .who{display:flex;flex-wrap:wrap;gap:4px 24px;margin-top:10px;font:400 11.5px/16px var(--mono);color:var(--brass)}
.next .who span::before{font-size:11px;letter-spacing:.1em;color:var(--t3);margin-right:8px}
.next .who .o::before{content:"DECIDES"}.next .who .d::before{content:"ON"}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px 56px;align-items:start}
.cols h3{margin-bottom:8px}
.say{margin:0 0 28px;font-size:16px;line-height:1.55;color:var(--t1)}
.items{margin:0;padding:0;list-style:none}
.items li{display:grid;grid-template-columns:32px minmax(0,1fr);gap:4px 12px;border-top:1px solid var(--line);padding:12px 0;font-size:13.5px;line-height:1.55;color:var(--t2)}
.items .id{font:400 11px/22px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--t3)}
.items p{margin:0;color:var(--t1)}
.items small{display:block;margin-top:4px;font-size:12.5px;line-height:1.5;color:var(--t3)}
.items .own{display:flex;flex-wrap:wrap;gap:4px 18px;margin-top:6px;font:400 11.5px/18px var(--mono)}
.items .own .o{color:var(--brass)}
.items .own .d{color:var(--t2)}
.items .own .d::before{content:"DUE ";font-size:11px;letter-spacing:.1em;color:var(--t3)}
.figs{margin:0;display:grid}
.figs>div{display:grid;grid-template-columns:132px minmax(0,1fr);gap:4px 16px;border-top:1px solid var(--line);padding:11px 0}
.figs dt{font:400 11px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.figs dd{margin:0;font-size:13.5px;line-height:1.55;color:var(--t2)}
.figs dd b{color:var(--t1);font-weight:500}
.tgt{margin:0 0 8px;font-size:13px;color:var(--t2)}
.solo details{margin-top:4px}
.solo details>*:not(summary){margin-top:12px}
.solo details p,.solo details li{margin:0 0 10px;font-size:13px;color:var(--t2)}
.solo details ul{padding-left:18px}
.tablewrap td,.tablewrap th{overflow-wrap:anywhere}
::selection{background:var(--t1);color:var(--bg)}
:focus-visible{outline-color:var(--t1)}
.foot{max-width:1120px;margin:0 auto;padding:28px 40px 64px;color:var(--t3);font-size:12px}
@media (max-width:980px){.foot{padding:24px 16px 48px}.solo .slide.cover{padding-top:24px}.cols,.next{grid-template-columns:1fr}
.stack table,.stack tbody,.stack tr,.stack td{display:block}.stack tr:first-child{display:none}.stack tr{padding:10px 16px;border-bottom:1px solid var(--line)}
.stack td{border:0;padding:3px 0;display:grid;grid-template-columns:118px 1fr;gap:12px}.stack td.num{text-align:left;white-space:normal}
.stack td::before{content:attr(data-l);font:400 11px/20px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}}
@media (max-width:560px){.figs>div{grid-template-columns:1fr;gap:0}}
.scg .sc-l{text-transform:uppercase;letter-spacing:.06em}
@container sc (min-width:800px){.scg .sc-r:has(>.sc-p:empty)>.sc-n{grid-column:1/3}.scg .sc-r:has(>.sc-p:empty)>.sc-p{display:none}}
/* Full column (site rule since 2026-11-25): every title and text block runs the content column, the scorecard frame's width. */
.solo h1,.solo h2,.solo h3,.solo .lede,.solo .next,.solo p,.solo li,.solo .sk figcaption{max-width:none}
.solo h1{text-wrap:balance}.solo .lede,.solo p,.solo li,.solo .sk figcaption{text-wrap:pretty}
"""

# The smallest text the page prints, at every width. The vendored template and svgkit keep their own sizes on disk
# (both are hash-pinned); the page raises any smaller size to this one as it inlines their rules.
FONT_FLOOR = 11
FONT_SIZE = re.compile(r"(font-size:\s*|font:[^;{}]*?)(\d+(?:\.\d+)?)px")


def floor_fonts(css: str) -> str:
    """Every font size below FONT_FLOOR, raised to it: font-size and the size in a font shorthand."""
    return FONT_SIZE.sub(lambda m: m.group(1) + (str(FONT_FLOOR) if float(m.group(2)) < FONT_FLOOR else m.group(2)) + "px", css)


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
    (r"\bwithin[- ]noise\b", "inside normal ups and downs"),
    (r"\bthe PRD\b", "the build plan"),
    (r"\bthe bar\b", "the target"),
    (r"\bBrief score\b", "Plan score"),
)
STEP = {"01 Decide": "Decide", "02 Spec": "Build plan check", "03 Build, cost": "Cost check", "03 Build, evals": "Quality test", "04 Learn, did-it-land": "Did it land"}


# One check word per skill: eval-kit's word is "not confirmed: too close to call", and did-it-land's noise flag reads
# "inside normal ups and downs". An older project file may still carry the earlier wording; wherever this page cites
# either word, the fold included, it prints the contract's.
CITED = ((r"\binside noise\b", "too close to call"), (r"\bwithin[- ]noise\b", "inside normal ups and downs"))


def cited(word: str | None) -> str:
    out = word or ""
    for pattern, to in CITED:
        out = re.sub(pattern, to, out)
    return out


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


def ref_plain(ref: str, f: dict[str, Any], what: str = "") -> str:
    """One piece of evidence, named in plain words. An incident is named by what happened, when the team wrote it."""
    kind, _, rest = ref.partition(":")
    if kind == "incident":
        return f"{what or 'incident ' + rest}, fixed in {loop.shown(f)}"
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
        return '<span class="wd" data-from="landed">not read: run did-it-land</span>'
    return f'<span class="st {e(status)}" data-from="landed">{e(status)}</span>'


def happened(i: dict[str, Any]) -> str:
    """An incident by what happened, as the team wrote it; its id when they did not. The id itself is in the fold."""
    return i.get("what_happened") or f"Incident {i['id']}"


def short(i: dict[str, Any]) -> str:
    """Time to fix, short, for the picture: the figure's own value and a short unit."""
    f = i["time_to_restore"]
    return f"{f['value']:g} min" if f["unit"] == "minutes" else loop.shown(f)


def stamp(text: str) -> str:
    return text[:16].replace("T", " ")


def _day(text: str) -> int:
    return dt.date.fromisoformat(text[:10]).toordinal()


# The signature picture: scorecard rows (svgkit 1.2.0)


def minutes(f: dict[str, Any]) -> float:
    """A time to fix in minutes, so every incident's bar shares one scale."""
    per = {"minutes": 1, "hours": 60, "days": 1440}.get(f["unit"], 1)
    return f["value"] * per


PRIORITY = re.compile(r"^(?:P|SEV|S)[\s-]?(\d+)$", re.I)


def severity_word(source: str) -> str:
    """A severity in plain words: P1 or P2 (or SEV1, SEV2) is major, P3 and up minor. A source that names its own
    severities ("Critical", "Minor") keeps its own name. Empty stays empty. The source's code prints only in the
    engineers' fold."""
    found = PRIORITY.match((source or "").strip())
    if found:
        return "major" if int(found.group(1)) <= 2 else "minor"
    return (source or "").strip().lower()


def team_of(owners: list[str]) -> str:
    """The team every owner shares ("Lead, Quoting squad" and "Tech lead, Quoting squad" share "Quoting squad"), or
    "" when they do not all name the same one. The frame prints it once in its head; each row prints the role."""
    teams = {o.rpartition(", ")[2] for o in owners if ", " in o}
    if len(owners) < 2 or len(teams) != 1 or any(", " not in o for o in owners):
        return ""
    return teams.pop()


def role_of(owner: str, team: str) -> str:
    return owner[: -len(", " + team)] if team and owner.endswith(", " + team) else owner


def rows(key: dict[str, Any]) -> str:
    """Incidents, then fixes, as scorecard rows. An incident: what happened, one ink bar for its time to fix scaled to
    the longest in the frame (there is no plan for time to fix, so no plan bar and no hatching), the time, its severity.
    A fix: what it does, no picture, its due date as the figure, its one owner in brass."""
    longest = max([minutes(i["time_to_restore"]) for i in key["incidents"]] or [0])
    out = []
    for i in key["incidents"]:
        f = i["time_to_restore"]
        out.append(
            sk.sc_row(
                happened(i),
                picture=sk.share_bar(minutes(f), longest),
                figure=sk.figure_line(loop.shown(f).upper()),
                word=sk.check_word(severity_word(i["severity"]) or "no severity"),
            )
        )
    if not key["incidents"]:
        out.append(sk.sc_note("No incidents started in the window."))
    team = team_of([f["owner"] for f in key["fixes"]])
    for f in key["fixes"]:
        out.append(sk.sc_row(plain(f["fix"]), figure=sk.figure_line(f["due"]), word=sk.person_call(role_of(f["owner"], team))))
    legend = sk.legend("actual", "time to fix") if key["incidents"] else ""
    if team:
        legend += f'<span class="sc-k">{sk.person_mark()}{e(team)}</span>'
    return sk.sc_frame(
        out,
        label=heading(key),
        title="Time to fix, then fixes",
        head=["Incident, then fix", "", "Time to fix · due", "Severity · owner"],
        legend=legend,
        caption=caption(key),
        illustrative=bool(key["illustrative"]),
        word_max=220,
    )


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
    longest = max(key["incidents"], key=lambda i: minutes(i["time_to_restore"]), default=None)
    out = ""
    if longest:
        out = f"One row per incident since {key['window']['from']}, drawn as its time to fix against the longest, {loop.shown(longest['time_to_restore'])}. "
    team = team_of([f["owner"] for f in key["fixes"]])
    if team:
        return out + f"Then one row per fix, with its due date and its one owner's role in brass; every owner is in {team}, named once in the head."
    return out + "Then one row per fix, with its due date and its one owner in brass."


def evidence(c: dict[str, Any], key: dict[str, Any]) -> str:
    what = {f"incident:{i['id']}": happened(i).lower() for i in key["incidents"] if i.get("what_happened")}
    return "; ".join(ref_plain(ref, f, what.get(ref, "")) for ref, f in c["cited"].items())


def changes(key: dict[str, Any]) -> str:
    items = []
    for c in key["what_changed"]:
        ev = evidence(c, key)
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
    tab = Table(("What happened", "Severity", "Started (UTC)", "Time to fix"))
    for i in key["incidents"]:
        tab.row(
            ("", e(happened(i))),
            ("", e(severity_word(i["severity"]) or "not set")),
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
        chip = f'<span class="wd">{e(word)}</span> ' if word else ""
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
            ctx.row(("", e(r["label"])), ("mono", e(cited(r["word"]))), ("num", cells[0]), ("mo", cells[1]), ("", cells[2]))
    ids = Table(("Incident", "What happened", "Severity in the source", "Started (UTC)", "Fixed (UTC)"))
    for i in key["incidents"]:
        ids.row(("mono", e(i["id"])), ("", e(happened(i))), ("mono", e(i["severity"] or "not set")), ("mo", e(stamp(i["started_at"]))), ("mo", e(stamp(i["restored_at"]))))
    written = "".join(f"<li>{e(c['id'])}: {e(c['change'])}</li>" for c in key["what_changed"])
    written += "".join(f"<li>{e(f['id'])} ({e(f.get('kind') or 'fix')}): {e(f['fix'])} Done when: {e(f['done_when'])}</li>" for f in key["fixes"])
    status = f"printed from <code>{e(st['from'])}</code> as {e(st['computed_by'])} wrote it" if st["printed"] else "not read"
    notes = (
        f"<p>Status: {status}, never computed here. Review kind: {e(key['review'])}. Window {e(key['window']['from'])} to {e(key['window']['to'])}. "
        f"Author: {e(key['author'])}.</p><p>Check: {e(key['check'])}</p><p>Incidents: {e(key['figures']['incidents']['source'])}.</p>"
        "<p>The review adds its page to the project file: the <code>postmortem</code> key of <code>landing/&lt;bet&gt;.json</code>, and no other key. "
        "With --csv it also writes the fixes for a tracker import.</p>"
    )
    skill = f"<p>Skill: <code>postmortem</code> {e(key['tool'].rsplit(' ', 1)[-1])}.</p>"
    body = f"{skill}<p>The written parts, as written:</p><ul>{written}</ul>{ids.html() if key['incidents'] else ''}{ev.html()}{ctx.html()}{notes}"
    if not key["brief_unchanged"]:
        body = "<p>The landing brief changed after the project file opened. This review reads it as it is now.</p>" + body
    return fold("For your engineers", body)


def next_step(key: dict[str, Any]) -> str:
    on = key["review_on"]
    lead = f"Hold the fix review on {on}" if on else "Set a date for the fix review"
    return f"{lead}: check each fix against its done-when test, and decide what to do about any that slip."


def page(key: dict[str, Any]) -> str:
    b, st, ill = key["brief"], key["landed_status"], key["illustrative"]
    title = f"After-action review: {b['title']}"
    header = sk.page_header("Postmortem", date=f"As of {key['as_of']}", version="v" + key["tool"].rsplit(" ", 1)[-1], illustrative=ill)
    marks = f'<p class="marks"><span>Project status, from did-it-land {status_mark(st["printed"])}</span><span>Review <span class="wd">{e(key["review"])}</span></span></p>'
    step = (
        f'<div class="next"><b>What to do next</b><div><p>{e(next_step(key))}</p>'
        f'<span class="who"><span class="o">{e(b["decides"])}</span><span class="d">{e(key["review_on"] or "not set")}</span></span></div></div>'
    )
    cover = f'<section class="slide cover">{header}<h1>{e(heading(key))}</h1><p class="lede">{lede(key)}</p>{marks}{rows(key)}{step}</section>'
    first = (
        f'<section class="slide"><div class="meta"><span>What changed, and who fixes it</span></div><p class="say">{e(plain(key["summary"]))}</p><div class="cols">'
        f"<div><h3>What changed</h3>{changes(key)}</div><div><h3>Who fixes it, by when</h3>{fixes(key)}</div></div></section>"
    )
    well = "".join(f'<li><span class="id">+</span><span><p>{e(plain(t))}</p></span></li>' for t in key["what_went_well"])
    well_html = f'<h3 style="margin-top:28px">What went well</h3><ul class="items">{well}</ul>' if well else ""
    second = (
        '<section class="slide"><div class="meta"><span>The incidents, and the earlier steps</span></div><div class="cols">'
        f"<div><h3>Incidents ({e(key['figures']['incidents']['value'])})</h3>{incidents(key)}{well_html}</div>"
        f'<div><h3>What the earlier steps found</h3><p class="tgt">Target: {e(b["bar"])} {e(b["metric"].lower())} by {e(b["by"])}.</p>{earlier(key)}</div></div></section>'
    )
    more = f'<section class="slide"><div class="meta"><span>Detail</span></div>{engineers(key)}</section>'
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><style>{floor_fonts(stylesheet() + sk.CSS + sk.SCORECARD_CSS + PAGE_CSS)}</style></head><body><main class="solo">'
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
    w(f"Postmortem v{key['tool'].rsplit(' ', 1)[-1]}. As of {key['as_of']}.{ill}")
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
        ev = evidence(c, key)
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
        w("| What happened | Severity | Started (UTC) | Fixed (UTC) | Time to fix |")
        w("|---|---|---|---|---|")
        for i in key["incidents"]:
            w(
                f"| {md(happened(i))} | {md(severity_word(i['severity']) or 'not set')} | {stamp(i['started_at'])} | {stamp(i['restored_at'])} | {loop.shown(i['time_to_restore'])} |"
            )
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
    w(f"Skill: `postmortem` {key['tool'].rsplit(' ', 1)[-1]}.")
    w("")
    if key["incidents"]:
        w("| Incident | What happened | Severity in the source |")
        w("|---|---|---|")
        for i in key["incidents"]:
            w(f"| {md(i['id'])} | {md(happened(i))} | {md(i['severity'] or 'not set')} |")
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
            w(f"| {r['label']} | {md(cited(r['word']))} | {cells[0]} | {cells[1]} | {cells[2]} |")
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
        w("The landing brief changed after the project file opened. This review reads it as it is now.")
    return "\n".join(out) + "\n"
