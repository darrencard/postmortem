#!/usr/bin/env python3
"""Step 04 of the Landing Loop: a blameless review of one bet, from its record, its brief and its incidents.

Usage:
  python3 scripts/review.py --record landing/quote-drafting.json --incidents run/data/incidents.json \\
      --review review.json --as-of 2026-11-26 --html postmortem.html --md postmortem.md [--csv fixes.csv] [--illustrative]

  --incidents-csv incidents.csv --system "Statuspage export" instead of --incidents takes a CSV (id, started_at,
  restored_at, severity), checked by the Leader Report's own collect.py.

Inputs:
  record     the bet's landing/<bet>.json. Read: the brief it names, and portfolio, spec, cost, evals and landed.
  incidents  run/data/incidents.json, as the Leader Report's collectors write it: from_pagerduty.py or
             from_incidentio.py (live first), or collect.py incidents --csv (the fallback).
  review     the written parts: author, review_on, summary, what_changed, what_went_well, fixes (see SKILL.md).

What it writes: the record's `postmortem` key, and nothing else in the record. One HTML page in the Leader Report
style and its Markdown twin, and with --csv the fixes for a tracker import.

What it checks (errors block every write):
  missing-field        author, summary, what_changed or fixes is empty
  change-no-evidence   a change cites nothing, or a reference that does not resolve to a figure or an incident
  evidence-not-read    a change cites a record key this step does not read
  fix-no-owner         a fix has no owner, or a placeholder (TBD, the team, on-call)
  fix-many-owners      a fix names more than one owner
  fix-bad-due          a due date that is not YYYY-MM-DD, or falls before the review window opens
  fix-no-done-when     a fix does not say how anyone will know it is done
  fix-addresses-none   a fix points at no change, or at one that does not exist
  blame-language       wording that blames a person
  aggregate-claim      a mean or MTTR: a review of one bet has its own incidents, not a mean
  status-word          landed, watch or stalled in the prose: only did-it-land sets them, and the page prints landed.status
  figure-not-computed  a number in the prose that is not a figure on the page, an incident id or a date in the window
Warnings: change-no-fix, vague-fix, due-far-out (over 90 days), no-follow-up (no review_on), too-many-fixes (over 8),
single-root-cause.

The status is printed from landed.status and never computed. The kind of review follows it: a learning review for a
landed bet, a stall review for a stalled one, a mid-course review on watch, and an incident review when did-it-land
has not run.

Standard library only. Python 3.11 or later. Makes no network calls. Same inputs, same bytes.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import check  # noqa: E402  (sibling scripts, found through the path above)
import collect  # noqa: E402  (vendored unchanged, see VENDORED.json)
import loop  # noqa: E402
import render_html  # noqa: E402

VERSION = "0.3.0"
TOOL = f"postmortem {VERSION}"
REVIEW_KIND = {"landed": "learning review", "stalled": "stall review", "watch": "mid-course review", None: "incident review"}
NEXT_SKILL = {"portfolio": "bet-portfolio-review", "spec": "spec-auditor", "cost": "cost-budget-check", "evals": "eval-kit", "landed": "did-it-land"}
STATUS = re.compile(r"\b(landed|watch|watching|stalled)\b", re.IGNORECASE)
MAX_FIXES = 8
FAR_OUT_DAYS = 90
KINDS = ("prevent", "detect", "mitigate", "process")


class Refused(SystemExit):
    """Stops with one line that says what to do. Nothing is written."""


# Incidents in, from the Leader Report's incidents source.


def read_incidents(args: argparse.Namespace) -> dict[str, Any]:
    if args.incidents:
        try:
            data = json.loads(Path(args.incidents).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise Refused(f"review: cannot read {args.incidents} ({e}). Run from_pagerduty.py, from_incidentio.py or collect.py incidents first.") from None
        if not isinstance(data, dict) or data.get("source") != "incidents" or not isinstance(data.get("rows"), list):
            raise Refused(f"review: {args.incidents} is not the incidents source. It comes from from_pagerduty.py, from_incidentio.py or collect.py incidents.")
        return data
    if not args.system:
        raise Refused("review: --incidents-csv needs --system, the system the export came from, so every figure names its source.")
    rows = collect.load_rows(args.incidents_csv, "csv")
    retrieved = args.retrieved_at or args.as_of
    return collect.collect("incidents", rows, args.system, args.query, retrieved, args.incidents_csv)


def incidents_in(data: dict[str, Any], lo: str, hi: str, as_of: str) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """The incidents that started inside the window, each with its time to restore computed here."""
    source = f"{data['system']}: {data.get('query_or_url') or 'incidents'} ({data['origin']}, retrieved {data['retrieved_at']})"
    out = []
    for r in data["rows"]:
        began = datetime.datetime.fromisoformat(r["started_at"])
        restored = datetime.datetime.fromisoformat(r["restored_at"])
        if not lo <= began.date().isoformat() <= hi:
            continue
        if restored < began:
            raise Refused(f"review: incident {r['id']} is restored before it started. Fix the source; nothing was written.")
        minutes = round((restored - began).total_seconds() / 60)
        out.append(
            {
                "id": str(r["id"]),
                "severity": r.get("severity") or "",
                "started_at": began.isoformat(),
                "restored_at": restored.isoformat(),
                "time_to_restore": loop.figure(minutes, "minutes", f"{source}; restored_at - started_at", began.isoformat(), restored.isoformat(), as_of),
            }
        )
    out.sort(key=lambda i: (i["started_at"], i["id"]))
    return out, loop.figure(len(out), "incidents", f"{source}; incidents started in the window", lo, hi, as_of), source


# Evidence: what each change cites, resolved in code.


def resolve(ref: str, record: dict[str, Any], incidents: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None, str]:
    """(kind, figure, problem). A record reference is record:<key>/<path to a figure>; an incident is incident:<id>."""
    if ref.startswith("incident:"):
        found = next((i for i in incidents if i["id"] == ref[len("incident:") :]), None)
        return ("incident", found["time_to_restore"], "") if found else ("incident", None, f"{ref} is not an incident in the window.")
    if ref.startswith("record:"):
        path = ref[len("record:") :]
        key = path.split("/", 1)[0]
        if key not in loop.READS:
            return "record", None, f"{ref}: this step reads {', '.join(loop.READS)}, not {key}."
        node = loop.at(record, path)
        if not loop.is_figure(node):
            return "record", None, f"{ref} is not a figure in the record (value, unit, source, window, as_of)."
        return "record", node, ""
    return "", None, f"{ref} is neither record:<key>/<path> nor incident:<id>."


def context(record: dict[str, Any]) -> list[dict[str, Any]]:
    """What the earlier steps wrote, read from fixed places in the record. Each step's own words, printed as written."""
    rows: list[dict[str, Any]] = []

    def missing(key: str, label: str) -> None:
        rows.append({"key": key, "label": label, "word": None, "text": f"Not in the record: run {NEXT_SKILL[key]}.", "figures": []})

    p = record.get("portfolio")
    if p:
        figs = [p[k] for k in ("brief_score",) if loop.is_figure(p.get(k))]
        rows.append({"key": "portfolio", "label": "01 Decide", "word": None, "text": "Brief score at the portfolio review.", "figures": figs})
    else:
        missing("portfolio", "01 Decide")
    s = record.get("spec")
    if s:
        holds = (s.get("counts") or {}).get("hold")
        rows.append(
            {
                "key": "spec",
                "label": "02 Spec",
                "word": s.get("verdict"),
                "text": "spec-auditor's verdict on the PRD.",
                "figures": [holds] if loop.is_figure(holds) else [],
            }
        )
    else:
        missing("spec", "02 Spec")
    c = record.get("cost")
    if c:
        lines = c.get("lines") or {}
        figs = [lines[k][part] for k in ("tokens_per_task", "cost_per_task") for part in ("actual", "budget") if loop.is_figure((lines.get(k) or {}).get(part))]
        rows.append(
            {
                "key": "cost",
                "label": "03 Build, cost",
                "word": c.get("budget_status"),
                "text": "cost-budget-check, actual against the brief's budget.",
                "figures": figs,
            }
        )
    else:
        missing("cost", "03 Build, cost")
    ev = record.get("evals")
    if ev:
        fig = (ev.get("figures") or {}).get(f"pass_rate@{ev.get('version')}")
        rows.append(
            {
                "key": "evals",
                "label": "03 Build, evals",
                "word": ev.get("status"),
                "text": f"eval-kit, held-out pass rate for {ev.get('version')}.",
                "figures": [fig] if loop.is_figure(fig) else [],
            }
        )
    else:
        missing("evals", "03 Build, evals")
    landed = record.get("landed")
    if landed:
        figs = [landed["figures"][k] for k in ("current", "at_date", "bar") if loop.is_figure((landed.get("figures") or {}).get(k))]
        rows.append({"key": "landed", "label": "04 Learn, did-it-land", "word": None, "text": "did-it-land's read: now, at the date, and the bar.", "figures": figs})
    else:
        missing("landed", "04 Learn, did-it-land")
    return rows


# Checks on the written parts.


def prose(review: dict[str, Any]) -> list[tuple[str, str]]:
    out = [("summary", str(review.get("summary") or ""))]
    for i, c in enumerate(review.get("what_changed") or []):
        out.append((f"what_changed[{i}]", str(c.get("change") or "")))
    for i, t in enumerate(review.get("what_went_well") or []):
        out.append((f"what_went_well[{i}]", str(t or "")))
    for i, f in enumerate(review.get("fixes") or []):
        out.append((f"fixes[{i}]", str(f.get("fix") or "")))
        out.append((f"fixes[{i}].done_when", str(f.get("done_when") or "")))
    return out


def checks(review: dict[str, Any], record: dict[str, Any], incidents: list[dict[str, Any]], allowed: set[str], window: tuple[str, str]) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []

    def err(rule: str, msg: str) -> None:
        found.append(("error", rule, msg))

    def warn(rule: str, msg: str) -> None:
        found.append(("warning", rule, msg))

    for k in ("author", "summary"):
        if not str(review.get(k) or "").strip():
            err("missing-field", f"{k} is empty.")
    changes = [c for c in review.get("what_changed") or [] if isinstance(c, dict)]
    fixes = [f for f in review.get("fixes") or [] if isinstance(f, dict)]
    if not changes:
        err("missing-field", "what_changed is empty. Say what changed, each with the figure or incident it rests on.")
    if not fixes:
        err("missing-field", "fixes is empty. Every review ends with fixes, each with one owner and a due date.")
    change_ids = set()
    for c in changes:
        cid = str(c.get("id") or "?")
        change_ids.add(cid)
        if not str(c.get("change") or "").strip():
            err("missing-field", f"change {cid} is empty.")
        cited = c.get("evidence") or []
        if not isinstance(cited, list) or not cited:
            err("change-no-evidence", f"change {cid} cites nothing. Add record:<key>/<path> or incident:<id>.")
            continue
        for ref in cited:
            _, fig, problem = resolve(str(ref), record, incidents)
            if fig is None:
                err("evidence-not-read" if "this step reads" in problem else "change-no-evidence", f"change {cid}: {problem}")
    lo = datetime.date.fromisoformat(window[0])
    as_of = datetime.date.fromisoformat(window[1])
    addressed: set[str] = set()
    for f in fixes:
        fid = str(f.get("id") or "?")
        if not str(f.get("fix") or "").strip():
            err("missing-field", f"fix {fid} is empty.")
        owner: Any = f.get("owner")
        if isinstance(owner, list):
            err("fix-many-owners", f"fix {fid} lists {len(owner)} owners. Name one person; others can help.")
        elif str(owner or "").strip().lower() in check.PLACEHOLDER_OWNERS:
            err("fix-no-owner", f'fix {fid} has no owner ("{owner or ""}"). Name one person who will see it through.')
        elif check.MANY_OWNERS.search(str(owner)):
            err("fix-many-owners", f'fix {fid} names more than one owner ("{owner}"). Name one person.')
        due = str(f.get("due") or "")
        try:
            due_day = datetime.date.fromisoformat(due)
        except ValueError:
            err("fix-bad-due", f'fix {fid} has due "{due}". Use YYYY-MM-DD.')
        else:
            if due_day < lo:
                err("fix-bad-due", f"fix {fid} is due {due}, before the review window opens ({window[0]}).")
            elif (due_day - as_of).days > FAR_OUT_DAYS:
                warn("due-far-out", f"fix {fid} is due {due}, more than {FAR_OUT_DAYS} days out. Split it or bring it in.")
        if not str(f.get("done_when") or "").strip():
            err("fix-no-done-when", f"fix {fid} does not say how anyone will know it is done. Fill done_when.")
        targets = f.get("addresses") or []
        if not isinstance(targets, list) or not targets:
            err("fix-addresses-none", f"fix {fid} addresses no change.")
        for t in targets if isinstance(targets, list) else []:
            if str(t) not in change_ids:
                err("fix-addresses-none", f"fix {fid} addresses {t}, which is not a change.")
            addressed.add(str(t))
        if any(re.search(p, str(f.get("fix") or ""), re.IGNORECASE) for p in check.VAGUE):
            warn("vague-fix", f"fix {fid} cannot be checked as done. Say what will exist when it is.")
    for cid in sorted(change_ids - addressed):
        warn("change-no-fix", f"change {cid} has no fix. Say so in the review if none is needed.")
    try:
        datetime.date.fromisoformat(str(review.get("review_on") or ""))
    except ValueError:
        warn("no-follow-up", "review_on is not a YYYY-MM-DD date. Set the day the team checks the fixes were done.")
    if len(fixes) > MAX_FIXES:
        warn("too-many-fixes", f"{len(fixes)} fixes. Keep the {MAX_FIXES} that matter most.")
    dates = {window[0], window[1]} | {str(f.get("due")) for f in fixes} | {str(review.get("review_on"))}
    for i in incidents:
        dates |= {i["started_at"][:10], i["restored_at"][:10]}
    for where, text in prose(review):
        for p in check.BLAME:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                err("blame-language", f'{where}: "{m.group(0)}". Describe what the system and the process allowed, not who erred.')
        for p in check.AGGREGATE:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                err("aggregate-claim", f'{where}: "{m.group(0)}". Give each incident its own time, not a mean.')
        m = STATUS.search(text)
        if m:
            err("status-word", f'{where}: "{m.group(0)}". Only did-it-land sets a bet\'s status; the page prints it from landed.status.')
        if re.search(r"\bthe root cause\b", text, re.IGNORECASE):
            warn("single-root-cause", f"{where}: names one root cause. List what changed instead.")
        scrubbed = text
        for d in check.DATE.findall(text):
            if d not in dates:
                err("figure-not-computed", f"{where}: date {d} is not in the window, an incident or a due date.")
            scrubbed = scrubbed.replace(d, " ")
        for m in check.NUMBER.finditer(scrubbed):
            if m.group(1).replace(",", "") not in allowed:
                err("figure-not-computed", f'{where}: "{m.group(0).strip()}" is not a figure on the page. Cite it, so code prints it.')
    return found


def allowed_numbers(key: dict[str, Any]) -> set[str]:
    """Numbers the prose may use: every figure the page prints, and incident ids."""
    out: set[str] = {i["id"] for i in key["incidents"]}
    figs = [key["figures"]["incidents"], *(i["time_to_restore"] for i in key["incidents"])]
    figs += [f for c in key["what_changed"] for f in c["cited"].values()]
    figs += [f for row in key["context"] for f in row["figures"]]
    for f in figs:
        out |= check.numbers(loop.shown(f))
    return out


# The key, the Markdown twin and the tracker CSV.


def build(args: argparse.Namespace) -> tuple[Path, dict[str, Any], dict[str, Any], list[tuple[str, str, str]]]:
    record_path = Path(args.record)
    try:
        record = loop.load(record_path)
        folder = record_path.resolve().parent.parent
        brief_path, brief, brief_same = loop.brief(record, folder)
    except loop.RecordError as e:
        raise Refused(f"review: {e}") from None
    try:
        review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise Refused(f"review: cannot read {args.review} ({e}).") from None
    status = loop.status(record)
    lo = args.window_from or (record.get("landed") or {}).get("shipped")
    if not lo:
        raise Refused("review: no ship date in landed and no --from. Pass --from YYYY-MM-DD, the day the review window opens.")
    window = (lo, args.as_of)
    incidents, count, _ = incidents_in(read_incidents(args), lo, args.as_of, args.as_of)
    changes = []
    for c in review.get("what_changed") or []:
        cited = {}
        for ref in c.get("evidence") or []:
            _, fig, _ = resolve(str(ref), record, incidents)
            if fig is not None:
                cited[str(ref)] = fig
        changes.append({"id": str(c.get("id")), "change": c.get("change", ""), "evidence": list(c.get("evidence") or []), "cited": cited})
    fixes = [{k: f.get(k) for k in ("id", "fix", "done_when", "owner", "due", "addresses", "kind")} for f in review.get("fixes") or [] if isinstance(f, dict)]
    owned = sum(1 for f in fixes if str(f.get("owner") or "").strip().lower() not in check.PLACEHOLDER_OWNERS and f.get("due"))
    key = {
        "tool": TOOL,
        "as_of": args.as_of,
        "review": REVIEW_KIND[status],
        "landed_status": {"printed": status, "from": "landed.status", "computed_by": (record.get("landed") or {}).get("computed_by")},
        "window": {"from": lo, "to": args.as_of},
        "brief": {
            "title": loop.title_of(brief_path, record.get("bet", "")),
            "metric": brief.metric,
            "bar": brief.bar_text,
            "by": brief.by,
            "decides": brief.decides,
        },
        "brief_unchanged": brief_same,
        "author": review.get("author", ""),
        "review_on": review.get("review_on"),
        "summary": review.get("summary", ""),
        "figures": {
            "incidents": count,
            "fixes_owned": loop.figure(owned, "fixes", f"{Path(args.review).name}, checked by {TOOL}", lo, args.as_of, args.as_of),
            "fixes": loop.figure(len(fixes), "fixes", f"{Path(args.review).name}, checked by {TOOL}", lo, args.as_of, args.as_of),
        },
        "incidents": incidents,
        "context": context(record),
        "what_changed": changes,
        "what_went_well": list(review.get("what_went_well") or []),
        "fixes": fixes,
        "check": "",
        "illustrative": bool(args.illustrative),
    }
    key["check"] = f"what changed: {len(changes)} listed, each with its evidence. Who owns each fix: {owned} of {len(fixes)} with one owner and a due date."
    found = checks(review, record, incidents, allowed_numbers(key), window)
    return record_path, record, key, found


def esc(text: Any) -> str:
    s = " ".join(str(text or "").split())
    for a, b in (("\\", "\\\\"), ("|", "\\|"), ("<", "&lt;"), (">", "&gt;"), ("`", "\\`"), ("[", "\\["), ("]", "\\]"), ("*", "\\*"), ("_", "\\_")):
        s = s.replace(a, b)
    return s


def markdown(key: dict[str, Any]) -> str:
    b = key["brief"]
    out: list[str] = []
    w = out.append
    w(f"# Postmortem: {esc(b['title'])}")
    w("")
    if key["illustrative"]:
        w("> **Illustrative.** Acme is an invented company. Every figure comes from a synthetic fixture.")
        w("")
    st = key["landed_status"]["printed"]
    w(f"**Status, printed from landed.status:** {st or 'not read (run did-it-land)'} · **Review:** {key['review']} · **Window:** {key['window']['from']} to {key['window']['to']}")
    w("")
    w(f"**Author:** {esc(key['author'])} · **Fix review:** {esc(key['review_on'] or 'not set')} · **Decides:** {esc(b['decides'])}")
    w("")
    w("This review is blameless. It says what changed in the system and the process, not who erred.")
    w("")
    w(esc(key["summary"]))
    w("")
    w("## The bet, as the record has it")
    w("")
    w(f"Bar: {esc(b['bar'])} {esc(b['metric'])} by {esc(b['by'])}.")
    w("")
    w("| Step | Says | Figures |")
    w("|---|---|---|")
    for row in key["context"]:
        figs = "; ".join(f"{loop.shown(f)} ({esc(f['source'])}, {loop.window_text(f)})" for f in row["figures"])
        word = f"{row['word']}. " if row["word"] else ""
        w(f"| {row['label']} | {esc(word + row['text'])} | {figs or 'none'} |")
    w("")
    n = key["figures"]["incidents"]
    w(f"## Incidents in the window: {loop.shown(n)}")
    w("")
    w(f"Source: {esc(n['source'])}.")
    w("")
    if key["incidents"]:
        w("| Incident | Severity | Started (UTC) | Restored (UTC) | Time to restore |")
        w("|---|---|---|---|---|")
        for i in key["incidents"]:
            w(
                f"| {esc(i['id'])} | {esc(i['severity'] or 'not set')} | {i['started_at'][:16].replace('T', ' ')} | "
                f"{i['restored_at'][:16].replace('T', ' ')} | {loop.shown(i['time_to_restore'])} |"
            )
        w("")
    w("## What changed")
    w("")
    for c in key["what_changed"]:
        w(f"- **{esc(c['id'])}.** {esc(c['change'])}")
        for ref, f in c["cited"].items():
            w(f"  - {esc(ref)}: {loop.shown(f)}, {loop.window_text(f)}. Source: {esc(f['source'])}.")
    w("")
    if key["what_went_well"]:
        w("## What went well")
        w("")
        for t in key["what_went_well"]:
            w(f"- {esc(t)}")
        w("")
    w("## Fixes: who owns each")
    w("")
    w("| Fix | Done when | Owner | Due | Addresses |")
    w("|---|---|---|---|---|")
    for f in key["fixes"]:
        w(f"| {esc(f['id'])}. {esc(f['fix'])} | {esc(f['done_when'])} | {esc(f['owner'])} | {esc(f['due'])} | {esc(', '.join(f.get('addresses') or []))} |")
    w("")
    w(f"Check: {key['check']}")
    w("")
    w(f"Written by {key['tool']} on {key['as_of']}. The status is did-it-land's, printed from landed.status. Every figure is computed in code from the source named.")
    return "\n".join(out) + "\n"


def fixes_csv(key: dict[str, Any]) -> str:
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(["id", "fix", "done_when", "kind", "owner", "due", "addresses"])
    for f in key["fixes"]:
        cells = [f["id"], f["fix"], f["done_when"], f.get("kind") or "", f["owner"], f["due"], " ".join(f.get("addresses") or [])]
        wr.writerow(["'" + str(c) if str(c)[:1] in "=+-@" else c for c in cells])
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="A blameless review of one bet, from its Landing Loop record and its incidents.")
    ap.add_argument("--record", required=True, help="landing/<bet>.json")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--incidents", help="run/data/incidents.json, from the Leader Report's collectors")
    src.add_argument("--incidents-csv", help="a CSV with id, started_at, restored_at, severity (the fallback)")
    ap.add_argument("--system", help="with --incidents-csv: the system the export came from")
    ap.add_argument("--query", help="with --incidents-csv: the report or query that produced it")
    ap.add_argument("--retrieved-at", help="with --incidents-csv: YYYY-MM-DD it was exported (default --as-of)")
    ap.add_argument("--review", required=True, help="the written parts, as JSON")
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD: the review's date, and the end of its window")
    ap.add_argument("--from", dest="window_from", help="YYYY-MM-DD the window opens (default: landed.shipped)")
    ap.add_argument("--html", help="write the page here")
    ap.add_argument("--md", help="write the Markdown twin here")
    ap.add_argument("--csv", help="write the fixes here, for a tracker import")
    ap.add_argument("--illustrative", action="store_true", help="mark every figure as from an invented company")
    args = ap.parse_args(argv)
    try:
        datetime.date.fromisoformat(args.as_of)
    except ValueError:
        raise Refused(f"review: --as-of {args.as_of!r} is not YYYY-MM-DD.") from None
    record_path, record, key, found = build(args)
    for level, rule, msg in found:
        print(f"{level.upper()} {rule}: {msg}")
    errors = sum(1 for f in found if f[0] == "error")
    if errors:
        print(f"review: {errors} error(s). Nothing was written. Fix the review or the data, never the wording around a rule.")
        return 1
    loop.write(record_path, record, key)
    if args.html:
        Path(args.html).write_text(render_html.page(key), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(markdown(key), encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(fixes_csv(key), encoding="utf-8")
    print(f"review: {key['check']} Status printed from landed.status: {key['landed_status']['printed'] or 'not read'}. Wrote the postmortem key to {record_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
