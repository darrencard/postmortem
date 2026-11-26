#!/usr/bin/env python3
"""Build the incident's timeline and compute time to detect, acknowledge, mitigate and resolve.

Usage:
  python3 scripts/timeline.py --run run \\
      --pagerduty incident.json --pagerduty-log log_entries.json \\
      --incidentio incident.json --incidentio-updates updates.json \\
      --slack channel/2026-11-12.json --slack-users users.json --slack-channel inc-invoices \\
      --deploys deploys.csv --sentry issues.json --sentry-issue ACME-API-4F2 \\
      --impact impact.csv \\
      [--moment mitigated=ev-14] [--disagree-minutes 5]

Every source is optional, but the timeline needs at least one. It writes run/timeline.json (events,
key moments, durations, impact, sources, open questions) and, if it does not exist, run/draft.json for
the written parts. The model never computes a time or a duration: it reads them from timeline.json.

How each key moment is chosen, in code:
  impact_started  incident.io "Impact started"; else the earliest firstSeen of the linked Sentry issues
  detected        the earliest of PagerDuty created_at and incident.io created_at or "Reported"
  acknowledged    the earliest of PagerDuty's first acknowledge and incident.io "Accepted"
  mitigated       incident.io "Mitigated"; else the first rollback in the deploy log after detection
  resolved        incident.io "Resolved"; else PagerDuty resolved_at
  --moment NAME=ev-N sets a moment to a timeline event the author chose (a Slack message, say), and the
  postmortem says so. A moment no source marks stays Unknown, and so does every duration that needs it.

Durations, all from impact start except where named:
  time_to_detect       impact_started -> detected
  time_to_acknowledge  detected -> acknowledged
  time_to_mitigate     impact_started -> mitigated
  time_to_resolve      impact_started -> resolved
  detect_to_mitigate   detected -> mitigated

Changes: every deploy in the 24 hours before impact started is listed, with its event id. Listing a change
never claims it caused the incident; a contributing factor that says so must cite the evidence.

Sentry counts cover an issue's whole life. If an issue was seen more than an hour outside the incident,
its counts are flagged as an open question so they are not cited as the incident's impact.

Sources that disagree on a moment by more than --disagree-minutes are listed as open questions.
Moments out of order (resolved before detected, say) are refused: the sources need fixing first.

Standard library only. Runs on Python 3.11 or later. Makes no network calls.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sources  # noqa: E402  (sibling script, found through the path above)

DURATIONS = {
    "time_to_detect": ("impact_started", "detected", "Time to detect"),
    "time_to_acknowledge": ("detected", "acknowledged", "Time to acknowledge"),
    "time_to_mitigate": ("impact_started", "mitigated", "Time to mitigate"),
    "time_to_resolve": ("impact_started", "resolved", "Time to resolve"),
    "detect_to_mitigate": ("detected", "mitigated", "Detection to mitigation"),
}
LABELS = {
    "impact_started": "Impact started",
    "detected": "Detected",
    "acknowledged": "Acknowledged",
    "mitigated": "Mitigated",
    "resolved": "Resolved",
}
# Which source wins when several mark the same moment. "earliest" takes the first time any source saw it.
PRECEDENCE = {
    "impact_started": ["incident.io", "Sentry"],
    "detected": "earliest",
    "acknowledged": "earliest",
    "mitigated": ["incident.io"],
    "resolved": ["incident.io", "PagerDuty"],
}
ORDER = [("impact_started", "detected"), ("detected", "resolved"), ("impact_started", "mitigated"), ("mitigated", "resolved"), ("detected", "acknowledged")]

# Deploys this long before impact started are listed as changes. Listing a change is never a claim it caused the incident.
CHANGE_WINDOW_HOURS = 24

DRAFT = {
    "title": "",
    "author": "",
    "review_on": "YYYY-MM-DD",
    "summary": "",
    "what_happened": "",
    "contributing_factors": [{"id": "CF1", "factor": "", "evidence": ["ev-1"]}],
    "what_went_well": [""],
    "where_we_got_lucky": [""],
    "action_items": [{"id": "A1", "action": "", "owner": "", "due": "YYYY-MM-DD", "done_when": "", "addresses": ["CF1"], "kind": "prevent"}],
}


def fmt_time(at: datetime.datetime) -> str:
    return at.strftime("%Y-%m-%d %H:%M UTC")


def fmt_duration(seconds: int) -> str:
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def choose(name: str, candidates: list[tuple[datetime.datetime, str]]) -> tuple[datetime.datetime, str] | None:
    if not candidates:
        return None
    rule = PRECEDENCE[name]
    if rule == "earliest":
        return min(candidates, key=lambda c: c[0])
    for system in rule:
        mine = [c for c in candidates if c[1].startswith(system + ":")]
        if mine:
            return min(mine, key=lambda c: c[0])
    return min(candidates, key=lambda c: c[0])


def build(srcs: list[sources.Source], overrides: dict[str, str], disagree_minutes: int) -> dict:
    if not srcs:
        raise sources.Refused("no sources given. Pass at least one of --pagerduty, --incidentio, --slack, --deploys or --sentry.")
    events = sorted((e for s in srcs for e in s.events), key=lambda e: (sources.when(e["at"]), e["source"], e["text"]))
    for n, e in enumerate(events, 1):
        e["id"] = f"ev-{n}"
    by_id = {e["id"]: e for e in events}

    candidates: dict[str, list[tuple[datetime.datetime, str]]] = {}
    for s in srcs:
        for name, found in s.moments.items():
            candidates.setdefault(name, []).extend(found)

    moments: dict[str, dict | None] = {}
    questions: list[str] = []
    for name in sources.MOMENTS:
        found = candidates.get(name, [])
        picked = choose(name, found)
        if name == "mitigated" and not picked and moments.get("detected"):
            detected = sources.when(moments["detected"]["at"])
            rollbacks = [e for e in events if e["kind"] == "rollback" and sources.when(e["at"]) >= detected]
            if rollbacks:
                picked = (sources.when(rollbacks[0]["at"]), f"Deploy log: first rollback after detection ({rollbacks[0]['id']})")
        if name in overrides:
            ev = by_id.get(overrides[name])
            if not ev:
                raise sources.Refused(f"--moment {name}={overrides[name]}: no such event. Event ids are in timeline.json.")
            picked = (sources.when(ev["at"]), f"chosen by the author: {ev['id']} ({ev['source']}, {ev['text'][:80]})")
        if picked is None:
            moments[name] = None
            questions.append(f"{LABELS[name]} is Unknown: no source marks it. Pick a timeline event with --moment {name}=ev-N.")
            continue
        moments[name] = {"at": picked[0].isoformat(), "display": fmt_time(picked[0]), "source": picked[1]}
        others = [c for c in found if abs((c[0] - picked[0]).total_seconds()) > disagree_minutes * 60]
        for at, where in others:
            questions.append(f"{LABELS[name]}: {where} says {fmt_time(at)}, but the postmortem uses {fmt_time(picked[0])} ({picked[1]}).")

    for a, b in ORDER:
        if moments.get(a) and moments.get(b) and sources.when(moments[a]["at"]) > sources.when(moments[b]["at"]):
            raise sources.Refused(
                f"{LABELS[b]} ({moments[b]['display']}) is before {LABELS[a]} ({moments[a]['display']}). "
                f"The sources disagree; fix the export or pick the right event with --moment {a}=ev-N or --moment {b}=ev-N."
            )

    durations = {}
    for key, (a, b, label) in DURATIONS.items():
        if moments.get(a) and moments.get(b):
            seconds = int((sources.when(moments[b]["at"]) - sources.when(moments[a]["at"])).total_seconds())
            durations[key] = {
                "label": label,
                "seconds": seconds,
                "minutes": round(seconds / 60),
                "display": fmt_duration(seconds),
                "from": a,
                "to": b,
                "source": f"{LABELS[a]} ({moments[a]['source']}) to {LABELS[b]} ({moments[b]['source']})",
            }
        else:
            durations[key] = {"label": label, "display": "Unknown", "from": a, "to": b, "source": "a key moment is Unknown"}

    impact = [i for s in srcs for i in s.impact]
    start, end = moments.get("impact_started") or moments.get("detected"), moments.get("resolved")
    if start and end:
        lo, hi = sources.when(start["at"]) - datetime.timedelta(hours=1), sources.when(end["at"]) + datetime.timedelta(hours=1)
        for i in impact:
            first, last = sources.when(i.get("first_seen")), sources.when(i.get("last_seen"))
            if (first and first < lo) or (last and last > hi):
                questions.append(
                    f"{i['name']}: the count covers {fmt_time(first) if first else 'an unknown start'} to {fmt_time(last) if last else 'an unknown end'}, "
                    "wider than the incident. "
                    "Do not cite it as the incident's impact; query the incident window instead."
                )

    changes = []
    if start:
        before = sources.when(start["at"])
        changes = [
            {"id": e["id"], "display": fmt_time(sources.when(e["at"])), "text": e["text"], "actor": e["actor"]}
            for e in events
            if e["kind"] == "deploy" and before - datetime.timedelta(hours=CHANGE_WINDOW_HOURS) <= sources.when(e["at"]) <= before
        ]

    title = next((s.title for s in srcs if s.title), "")
    severity = next((s.severity for s in srcs if s.severity), "")
    return {
        "title": title,
        "severity": severity,
        "moments": moments,
        "durations": durations,
        "impact": impact,
        "changes_before_impact": changes,
        "events": events,
        "open_questions": questions,
        "sources": [{"system": s.system, "files": [Path(f).name for f in s.files], "events": len(s.events), "skipped": s.skipped} for s in srcs],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the incident timeline and compute its durations.")
    ap.add_argument("--run", default="run")
    ap.add_argument("--pagerduty", nargs="+", default=[], help="GET /incidents/{id} or a GET /incidents page")
    ap.add_argument("--pagerduty-log", nargs="+", default=[], help="GET /incidents/{id}/log_entries pages")
    ap.add_argument("--pagerduty-incident", help="the incident number, if a file holds several")
    ap.add_argument("--incidentio", nargs="+", default=[], help="GET /v2/incidents/{id} or a page")
    ap.add_argument("--incidentio-updates", nargs="+", default=[], help="GET /v2/incident_updates pages")
    ap.add_argument("--incidentio-incident", help="the incident reference, if a file holds several")
    ap.add_argument(
        "--incidentio-timestamp", action="append", default=[], help='moment=Name, for an account that names a timestamp differently, e.g. mitigated="Fixed"'
    )
    ap.add_argument("--slack", nargs="+", default=[], help="the incident channel's daily export files")
    ap.add_argument("--slack-users", help="users.json from the same export, for names")
    ap.add_argument("--slack-channel", default="incident", help="the channel name, for references")
    ap.add_argument("--deploys", nargs="+", default=[], help="deploy log, CSV or JSON")
    ap.add_argument("--deploy-service", help="keep only this service's deploys")
    ap.add_argument("--sentry", nargs="+", default=[], help="Sentry issues pages")
    ap.add_argument("--sentry-issue", action="append", default=[], help="a Sentry issue linked to the incident; repeat it. Default: every issue in the files")
    ap.add_argument("--impact", nargs="+", default=[], help="CSV of name,value,unit,source")
    ap.add_argument("--moment", action="append", default=[], help="NAME=ev-N: set a key moment to a timeline event")
    ap.add_argument("--disagree-minutes", type=int, default=5)
    args = ap.parse_args(argv)

    try:
        overrides = {}
        for m in args.moment:
            name, _, ev = m.partition("=")
            if name not in sources.MOMENTS or not ev:
                raise sources.Refused(f"--moment {m}: use NAME=ev-N, where NAME is one of {', '.join(sources.MOMENTS)}.")
            overrides[name] = ev
        names: dict[str, list[str]] = {}
        for t in args.incidentio_timestamp:
            name, _, label = t.partition("=")
            if name not in sources.MOMENTS or not label:
                raise sources.Refused(f"--incidentio-timestamp {t}: use moment=Name.")
            names[name] = [label]

        srcs = []
        if args.pagerduty:
            srcs.append(sources.pagerduty(args.pagerduty, args.pagerduty_log, args.pagerduty_incident))
        if args.incidentio:
            srcs.append(sources.incidentio(args.incidentio, args.incidentio_updates, names, args.incidentio_incident))
        if args.slack:
            srcs.append(sources.slack(args.slack, args.slack_users, args.slack_channel))
        if args.deploys:
            srcs.append(sources.deploys(args.deploys, args.deploy_service))
        if args.sentry:
            srcs.append(sources.sentry(args.sentry, args.sentry_issue))
        if args.impact:
            srcs.append(sources.impact(args.impact))
        result = build(srcs, overrides, args.disagree_minutes)
    except sources.Refused as e:
        print(f"timeline: {e}", file=sys.stderr)
        return 2

    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    (run / "timeline.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    draft = run / "draft.json"
    if not draft.exists():
        draft.write_text(json.dumps(DRAFT, indent=2) + "\n", encoding="utf-8")
    print(f"timeline: {len(result['events'])} events from {len(srcs)} source(s), written to {run / 'timeline.json'}.")
    for d in result["durations"].values():
        print(f"  {d['label']}: {d['display']}")
    for q in result["open_questions"]:
        print(f"  Open question: {q}")
    for s in srcs:
        for why, n in s.skipped.items():
            print(f"  {s.system}: skipped {n} {why}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
