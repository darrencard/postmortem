#!/usr/bin/env python3
"""Render the postmortem as Markdown, after check.py passes.

Usage:
  python3 scripts/render.py --run run [--out run/postmortem.md] [--illustrative]

Runs every check in check.py first and writes nothing if any error remains. Every time and duration in
the document comes from run/timeline.json; the written parts come from run/draft.json. Text from a
source is escaped so it shows as text and cannot change the document's structure.

--illustrative adds a banner saying the figures come from an invented company's synthetic data.

Standard library only. Runs on Python 3.11 or later. Makes no network calls.
"""

from __future__ import annotations

import argparse
import datetime
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


def render(timeline: dict, draft: dict, illustrative: bool = False) -> str:
    out: list[str] = []
    w = out.append
    w(f"# Postmortem: {esc(draft['title'])}")
    w("")
    if illustrative:
        w("> **Illustrative.** Acme is an invented company. Every figure below comes from a synthetic fixture.")
        w("")
    first = min(datetime.datetime.fromisoformat(e["at"]) for e in timeline["events"])
    w(f"**Date:** {first.date().isoformat()} · **Severity:** {esc(timeline.get('severity') or 'not set in the source')} · **Author:** {esc(draft['author'])}")
    w("")
    w("This postmortem is blameless. It describes what the system and the process allowed, not who erred.")
    w("")
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
    w("Each has one owner and a due date.")
    w("")
    w("| # | Action | Kind | Owner | Due | Addresses |")
    w("|---|---|---|---|---|---|")
    for a in draft["action_items"]:
        addresses = ", ".join(map(str, a["addresses"]))
        w(f"| {esc(a['id'])} | {esc(a['action'])} | {esc(a.get('kind', ''))} | {esc(a['owner'])} | {esc(a['due'])} | {esc(addresses)} |")
    w("")

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
    w("Every time and duration above was computed by `scripts/timeline.py` from these files. The written parts passed `scripts/check.py`.")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the postmortem after its checks pass.")
    ap.add_argument("--run", default="run")
    ap.add_argument("--out")
    ap.add_argument("--illustrative", action="store_true", help="add the banner for synthetic data")
    args = ap.parse_args(argv)
    run = Path(args.run)
    try:
        timeline = json.loads((run / "timeline.json").read_text(encoding="utf-8"))
        draft = json.loads((run / "draft.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"render: cannot read the run ({e}). Run timeline.py first.", file=sys.stderr)
        return 2
    errors = [f for f in check.check(timeline, draft) if f[0] == "error"]
    if errors:
        for _, rule, msg in errors:
            print(f"ERROR {rule}: {msg}", file=sys.stderr)
        print(f"render: {len(errors)} error(s). Nothing written. Fix the draft or the data, then run it again.", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else run / "postmortem.md"
    out.write_text(render(timeline, draft, args.illustrative), encoding="utf-8")
    print(f"render: written to {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
