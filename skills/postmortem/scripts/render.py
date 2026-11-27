#!/usr/bin/env python3
"""Render the postmortem as Markdown, after check.py passes.

Usage:
  python3 scripts/render.py --run run [--out run/postmortem.md] [--illustrative] [--facts-only]

Runs every check in check.py first and writes nothing if any error remains. Every time and duration in
the document comes from run/timeline.json; the written parts come from run/draft.json. Text from a
source is escaped so it shows as text and cannot change the document's structure.

--facts-only renders what the sources prove (key times, impact, changes, open questions, timeline) before
anything is written, so the team has the facts in front of them for the review meeting. It writes
run/facts.md and needs no draft. A full render also writes run/action_items.csv for a tracker import.

--illustrative adds a banner saying the figures come from an invented company's synthetic data.

Standard library only. Runs on Python 3.11 or later. Makes no network calls.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check  # noqa: E402  (sibling script, found through the path above)
import timeline as tl  # noqa: E402


def esc(text: object) -> str:
    """Plain text safe inside a Markdown table cell or paragraph."""
    s = " ".join(str(text or "").split())
    for a, b in (("\\", "\\\\"), ("|", "\\|"), ("<", "&lt;"), (">", "&gt;"), ("`", "\\`"), ("[", "\\["), ("]", "\\]"), ("*", "\\*"), ("_", "\\_")):
        s = s.replace(a, b)
    return "\\" + s if s.startswith("#") else s


def render(timeline: dict, draft: dict | None, illustrative: bool = False) -> str:
    """The postmortem. With draft None, the facts only: key times, impact, changes, open questions, timeline."""
    out: list[str] = []
    w = out.append
    title = draft["title"] if draft else timeline.get("title") or "incident"
    w(f"# Postmortem: {esc(title)}")
    w("")
    if illustrative:
        w("> **Illustrative.** Acme is an invented company. Every figure below comes from a synthetic fixture.")
        w("")
    if not draft:
        w("> **Facts only.** The written sections are not drafted yet. Every figure here is computed from the sources.")
        w("")
    first = min(datetime.datetime.fromisoformat(e["at"]) for e in timeline["events"])
    author = f" · **Author:** {esc(draft['author'])}" if draft else ""
    if draft and draft.get("review_on"):
        author += f" · **Action review:** {esc(draft['review_on'])}"
    w(f"**Date:** {first.date().isoformat()} · **Severity:** {esc(timeline.get('severity') or 'not set in the source')}{author}")
    w("")
    w("This postmortem is blameless. It describes what the system and the process allowed, not who erred.")
    w("")
    if draft:
        w("## Summary")
        w("")
        w(esc(draft["summary"]))
        w("")

    w("## Key times")
    w("")
    w("| Measure | Value | Measured from |")
    w("|---|---|---|")
    for d in timeline["durations"].values():
        w(f"| {d['label']} | {d['display']} | {esc(d['source'])} |")
    w("")
    w("| Moment | Time | Source |")
    w("|---|---|---|")
    for name, label in tl.LABELS.items():
        m = timeline["moments"].get(name)
        w(f"| {label} | {m['display'] if m else 'Unknown'} | {esc(m['source']) if m else 'no source marks it'} |")
    w("")

    if timeline["impact"]:
        w("## Impact")
        w("")
        w("| Measure | Value | Source |")
        w("|---|---|---|")
        for i in timeline["impact"]:
            value = f"{i['value']:,}" if isinstance(i["value"], int) else str(i["value"])
            w(f"| {esc(i['name'])} | {value} {esc(i['unit'])} | {esc(i['source'])} |")
        w("")

    changes = timeline.get("changes_before_impact") or []
    w(f"## Changes in the {tl.CHANGE_WINDOW_HOURS} hours before impact")
    w("")
    if changes:
        w("Listed because they came first, not because they caused it. A contributing factor says which, if any, did.")
        w("")
        for c in changes:
            who = f" ({esc(c['actor'])})" if c["actor"] else ""
            w(f"- {c['id']}, {c['display']}: {esc(c['text'])}{who}")
    else:
        w("No deploys in the sources in that window." if timeline["moments"].get("impact_started") else "Unknown: impact start is Unknown.")
    w("")

    if draft:
        render_written(w, timeline, draft)

    if timeline["open_questions"]:
        w("## Open questions on the data")
        w("")
        for q in timeline["open_questions"]:
            w(f"- {esc(q)}")
        w("")

    w("## Timeline")
    w("")
    w("All times UTC. Text is quoted from the source as it stands.")
    w("")
    w("| Event | Time | Source | Who | What | Reference |")
    w("|---|---|---|---|---|---|")
    for e in timeline["events"]:
        at = datetime.datetime.fromisoformat(e["at"]).strftime("%Y-%m-%d %H:%M:%S")
        w(f"| {e['id']} | {at} | {esc(e['source'])} | {esc(e['actor'])} | {esc(e['text'])} | {esc(e['ref'])} |")
    w("")

    w("## Sources")
    w("")
    w("| System | Files | Events | Skipped |")
    w("|---|---|---|---|")
    for s in timeline["sources"]:
        skipped = "; ".join(f"{n} {why}" for why, n in s["skipped"].items()) or "none"
        w(f"| {esc(s['system'])} | {esc(', '.join(s['files']))} | {s['events']} | {esc(skipped)} |")
    w("")
    checked = " The written parts passed `scripts/check.py`." if draft else ""
    w(f"Every time and duration above was computed by `scripts/timeline.py` from these files.{checked}")
    return "\n".join(out) + "\n"


def render_written(w, timeline: dict, draft: dict) -> None:
    w("## What happened")
    w("")
    w(esc(draft["what_happened"]))
    w("")

    w("## Contributing factors")
    w("")
    by_id = {e["id"]: e for e in timeline["events"]}
    for f in draft["contributing_factors"]:
        cites = ", ".join(f"{e} ({datetime.datetime.fromisoformat(by_id[e]['at']).strftime('%H:%M')}, {esc(by_id[e]['source'])})" for e in f["evidence"])
        w(f"- **{esc(f['id'])}.** {esc(f['factor'])} Evidence: {cites}.")
    w("")

    for key, heading in (("what_went_well", "What went well"), ("where_we_got_lucky", "Where we got lucky")):
        items = [t for t in draft.get(key) or [] if str(t).strip()]
        if items:
            w(f"## {heading}")
            w("")
            for t in items:
                w(f"- {esc(t)}")
            w("")

    w("## Action items")
    w("")
    w("Each has one owner, a due date and a test for done. `action_items.csv` holds the same rows for a tracker import.")
    w("")
    w("| # | Action | Done when | Kind | Owner | Due | Addresses |")
    w("|---|---|---|---|---|---|---|")
    for a in draft["action_items"]:
        addresses = ", ".join(map(str, a["addresses"]))
        w(f"| {esc(a['id'])} | {esc(a['action'])} | {esc(a.get('done_when'))} | {esc(a.get('kind', ''))} | {esc(a['owner'])} | {esc(a['due'])} | {esc(addresses)} |")
    w("")


def actions_csv(draft: dict) -> str:
    """The action items as CSV, for an import into Linear, Jira or any tracker."""
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\n")
    out.writerow(["id", "action", "done_when", "kind", "owner", "due", "addresses"])
    for a in draft["action_items"]:
        out.writerow([a["id"], a["action"], a.get("done_when", ""), a.get("kind", ""), a["owner"], a["due"], ";".join(map(str, a["addresses"]))])
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the postmortem after its checks pass.")
    ap.add_argument("--run", default="run")
    ap.add_argument("--out")
    ap.add_argument("--illustrative", action="store_true", help="add the banner for synthetic data")
    ap.add_argument("--facts-only", action="store_true", help="render the computed facts before anything is written")
    args = ap.parse_args(argv)
    run = Path(args.run)
    try:
        timeline = json.loads((run / "timeline.json").read_text(encoding="utf-8"))
        draft = None if args.facts_only else json.loads((run / "draft.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"render: cannot read the run ({e}). Run timeline.py first.", file=sys.stderr)
        return 2
    if draft is not None:
        errors = [f for f in check.check(timeline, draft) if f[0] == "error"]
        if errors:
            for _, rule, msg in errors:
                print(f"ERROR {rule}: {msg}", file=sys.stderr)
            print(f"render: {len(errors)} error(s). Nothing written. Fix the draft or the data, then run it again.", file=sys.stderr)
            return 1
    out = Path(args.out) if args.out else run / ("facts.md" if draft is None else "postmortem.md")
    out.write_text(render(timeline, draft, args.illustrative), encoding="utf-8")
    print(f"render: written to {out}.")
    if draft is not None:
        (out.parent / "action_items.csv").write_text(actions_csv(draft), encoding="utf-8")
        print(f"render: action items for a tracker in {out.parent / 'action_items.csv'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
