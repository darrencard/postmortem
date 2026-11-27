"""The review as one self-contained HTML page, in the Leader Report style guide.

The page uses the report's own stylesheet, taken whole from its template (assets/vendor/template.html, vendored
byte-identical at a pinned commit), so it is the same brand family as the deck. It follows the report's
references/design.md: mono capitals for labels, sans for sentences; hairlines, not boxes; green, grey-white and red
for status only, with the word always printed, and only as printed from landed.status; brass for a person's call
(each fix's owner, and who decides); grey for plan and ink for actual.

Nothing is loaded from the network, nothing depends on the clock or the machine, and every piece of text from a
source or a person is escaped.

Standard library only. Python 3.11 or later.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import loop

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "vendor" / "template.html"
STYLE = re.compile(r"<style>(.*?)</style>", re.S)

# Layout for this page only. Everything else comes from the template's stylesheet.
PAGE_CSS = """
main.solo{margin-left:0}
.solo .slide{min-height:0}
.solo .slide.cover{padding-top:72px;padding-bottom:40px}
.head{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:0 0 24px}
.rows>div{display:grid;grid-template-columns:168px minmax(0,1fr);gap:6px 36px;border-top:1px solid var(--line);padding:14px 0}
.rows>div>span:first-child{font:400 10px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.rows>div>span:last-child{color:var(--t2);font-size:13.5px}
.rows .chip{margin-right:10px}
.cite{display:block;overflow-wrap:anywhere;font:400 11.5px/18px var(--mono);color:var(--t3);margin-top:6px}
.cite b{color:var(--t1);font-weight:500}
.card li.own .dw{display:block;font-size:12.5px;color:var(--t3);margin-top:4px}
.foot{max-width:1120px;margin:0 auto;padding:28px 40px 64px;color:var(--t3);font-size:12px}
@media (max-width:980px){.rows>div{grid-template-columns:1fr;gap:2px}.foot{padding:24px 16px 48px}.solo .slide.cover{padding-top:48px}}
"""

MARK = (
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">'
    '<rect x="2" y="13" width="3" height="7" fill="var(--agent)"/><rect x="7" y="10" width="3" height="10" fill="var(--agent)"/>'
    '<rect x="12" y="2" width="1.5" height="20" fill="var(--brass)"/><rect x="16" y="4" width="4" height="16" fill="var(--t1)"/></svg>'
)


def e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def stylesheet() -> str:
    try:
        found = STYLE.search(TEMPLATE.read_text(encoding="utf-8"))
    except OSError:
        found = None
    return found.group(1) if found else ""


def status_mark(status: str | None) -> str:
    """landed.status as the template draws it, the word always printed. The only place a status colour appears."""
    if status is None:
        return '<span class="chip" data-from="landed">not read: run did-it-land</span>'
    return f'<span class="st {e(status)}" data-from="landed">{e(status)}</span>'


def fig_line(f: dict[str, Any]) -> str:
    return f"<b>{e(loop.shown(f))}</b> &middot; {e(loop.window_text(f))} &middot; {e(f['source'])}"


def context_rows(key: dict[str, Any]) -> str:
    rows = []
    for r in key["context"]:
        word = f'<span class="chip">{e(r["word"])}</span>' if r["word"] else ""
        cites = "".join(f'<span class="cite">{fig_line(f)}</span>' for f in r["figures"])
        rows.append(f"<div><span>{e(r['label'])}</span><span>{word}{e(r['text'])}{cites}</span></div>")
    return f'<div class="rows">{"".join(rows)}</div>'


def incidents(key: dict[str, Any]) -> str:
    n = key["figures"]["incidents"]
    if not key["incidents"]:
        return f'<p class="lede">No incidents started in the window. Source: {e(n["source"])}.</p>'
    body = "".join(
        f'<tr><td>{e(i["id"])}</td><td>{e(i["severity"] or "not set")}</td><td class="mo">{e(i["started_at"][:16].replace("T", " "))}</td>'
        f'<td class="mo">{e(i["restored_at"][:16].replace("T", " "))}</td><td class="num">{e(loop.shown(i["time_to_restore"]))}</td></tr>'
        for i in key["incidents"]
    )
    head = '<tr><th>Incident</th><th>Severity</th><th>Started (UTC)</th><th>Restored (UTC)</th><th class="num">Time to restore</th></tr>'
    return f'<div class="tablewrap"><table><thead>{head}</thead><tbody>{body}</tbody></table></div><p class="asof" style="margin-top:12px">Source: {e(n["source"])}</p>'


def changes(key: dict[str, Any]) -> str:
    rows = []
    for c in key["what_changed"]:
        cites = "".join(f'<span class="cite" title="{e(ref)}">{fig_line(f)}</span>' for ref, f in c["cited"].items())
        rows.append(f"<div><span>{e(c['id'])}</span><span>{e(c['change'])}{cites}</span></div>")
    return f'<div class="rows">{"".join(rows)}</div>'


def fixes(key: dict[str, Any]) -> str:
    items = "".join(
        f'<li class="own"><span><span class="li-t">{e(f["id"])} &middot; {e(f.get("kind") or "fix")}</span>{e(f["fix"])}'
        f'<span class="dw">Done when: {e(f["done_when"])}</span></span><span class="li-o">{e(f["owner"])}</span><span class="li-d">{e(f["due"])}</span></li>'
        for f in key["fixes"]
    )
    return f'<div class="card"><ul>{items}</ul></div>'


def page(key: dict[str, Any]) -> str:
    b = key["brief"]
    title = f"Postmortem: {b['title']}"
    meta = [f"As of {key['as_of']}", key["tool"], f"Window {key['window']['from']} to {key['window']['to']}"]
    meta_html = "".join(f"<span>{e(m)}</span>" for m in meta)
    if key["illustrative"]:
        meta_html += '<span class="ill">Illustrative</span>'
    st = key["landed_status"]
    head = f'<div class="head">{status_mark(st["printed"])}<span class="chip">{e(key["review"])}</span></div>'
    stale = "" if key["brief_unchanged"] else '<p class="lede">The brief changed after the record opened. This review reads it as it is now.</p>'
    decides = (
        f'<div class="need"><b>Decides the next step</b><div class="need-r"><p>Fix review on {e(key["review_on"] or "a date not yet set")}. '
        f"Author: {e(key['author'])}.</p>"
        f'<span class="mono" style="color:var(--brass);font-size:11px">{e(b["decides"])}</span>'
        f'<span class="mono t3" style="font-size:11px">{e(key["review_on"] or "")}</span></div></div>'
    )
    well = "".join(f"<li>{e(t)}</li>" for t in key["what_went_well"])
    well_html = f'<section class="slide"><div class="meta"><span>Went well</span></div><h2>What went well</h2><div class="card"><ul>{well}</ul></div></section>' if well else ""
    n = key["figures"]["incidents"]
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><style>{stylesheet()}{PAGE_CSS}</style></head><body><main class="solo">'
        f'<section class="slide cover"><div class="brand">{MARK}<span translate="no">DACARD</span></div><div class="meta">{meta_html}</div>'
        f'<h1>{e(title)}</h1>{head}<p class="lede">{e(key["summary"])}</p>{stale}'
        f'<div class="facts"><span><b>{e(len(key["incidents"]))}</b>incidents in the window</span><span><b>{e(len(key["what_changed"]))}</b>changes, each with evidence</span>'
        f"<span><b>{e(key['figures']['fixes_owned']['value'])} of {e(key['figures']['fixes']['value'])}</b>fixes with one owner and a due date</span></div></section>"
        f'<section class="slide"><div class="meta"><span>Fixes</span></div><h2>Who owns each fix</h2>{fixes(key)}{decides}</section>'
        f'<section class="slide"><div class="meta"><span>What changed</span></div><h2>What changed, and the evidence for each</h2>{changes(key)}</section>'
        f'<section class="slide"><div class="meta"><span>Incidents</span></div><h2>{e(loop.shown(n))} in the window</h2>{incidents(key)}</section>'
        f'<section class="slide"><div class="meta"><span>The record</span></div><h2>The bet, as the loop recorded it</h2>'
        f'<p class="lede">Bar: {e(b["bar"])} {e(b["metric"])} by {e(b["by"])}, from the landing brief. Each step\'s own words, as it wrote them.</p>{context_rows(key)}</section>'
        f"{well_html}"
        '<p class="foot">This review is blameless: it says what the system and the process allowed, not who erred. '
        "The status is did-it-land's, printed from landed.status, never computed here. Every figure is computed in code from the source named.</p>"
        "</main></body></html>\n"
    )
