#!/usr/bin/env python3
"""Check the written parts of a postmortem against its timeline. Errors block the render.

Usage:
  python3 scripts/check.py --run run

Reads run/timeline.json (from timeline.py) and run/draft.json (the written parts). Prints each finding
as RULE: message and exits 1 if any is an error.

Errors (block the render):
  action-no-done-when    an action item does not say how anyone will know it is done
  aggregate-claim        a mean, average or trend ("MTTR", "mean time to"): one incident has no mean
  missing-field          title, author, summary or what_happened is empty, or there is no factor or action
  action-no-owner        an action item has no owner, or a placeholder (TBD, team, everyone, on-call)
  action-many-owners     an action item names more than one owner, or a list
  action-bad-due         a due date that is not YYYY-MM-DD, or falls before the incident
  action-addresses-none  an action item points at no contributing factor, or at one that does not exist
  factor-no-evidence     a contributing factor cites no timeline event, or one that does not exist
  blame-language         wording that blames a person ("human error", "careless", "should have known")
  figure-not-computed    a duration, percentage or count in the prose that timeline.json did not compute
Warnings (printed, do not block):
  single-root-cause      "the root cause": a postmortem lists contributing factors, not one cause
  factor-no-action       a contributing factor no action item addresses
  vague-action           an action that cannot be checked as done ("be more careful", "look into")
  due-far-out            an action due more than 90 days after the incident
  no-follow-up           no review_on date: when the team checks the action items were done
  too-many-actions       more than 8 action items: few owned actions get done, many get lost

Standard library only. Runs on Python 3.11 or later. Makes no network calls.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER_OWNERS = {
    "",
    "tbd",
    "tba",
    "tbc",
    "n/a",
    "na",
    "none",
    "unassigned",
    "unknown",
    "owner",
    "?",
    "-",
    "team",
    "the team",
    "everyone",
    "all",
    "engineering",
    "eng",
    "on-call",
    "oncall",
    "on call",
    "sre",
    "ops",
}
MANY_OWNERS = re.compile(r",|;|&|\+|/|\band\b|\bor\b", re.IGNORECASE)
BLAME = [
    r"human error",
    r"\bcareless",
    r"\bnegligen",
    r"\bincompeten",
    r"\bsloppy\b",
    r"\blazy\b",
    r"\bblame",
    r"\bat fault\b",
    r"\b(?:his|her|their) fault\b",
    r"\bfault of\b",
    r"should have known",
    r"should have caught",
    r"should have noticed",
    r"failed to notice",
    r"\bdidn'?t bother\b",
    r"\bmistake by\b",
    r"\bscrewed up\b",
    r"\bbe more careful\b",
    r"\bpay more attention\b",
]
AGGREGATE = [r"\bMTT[ADMR]\b", r"\bmean time\b", r"\baverage time\b", r"\bon average\b", r"\bmedian time\b"]
FAR_OUT_DAYS = 90
MAX_ACTIONS = 8
VAGUE = [r"\bbe more careful\b", r"\blook into\b", r"\btry to\b", r"\bpay more attention\b", r"\bremember to\b", r"\bconsider\b"]
NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(\s*(?:%|percent|minutes?|mins?|hours?|hrs?|h\b|seconds?|secs?|s\b|days?))?(?!\w)", re.IGNORECASE)
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")


def numbers(text: str) -> set[str]:
    return {m.group(1).replace(",", "") for m in NUMBER.finditer(text)}


def with_units(text: str) -> set[str]:
    """Number-and-unit tokens, normalised ("95 %" and "95%" match), so a source's own "below 95%" can be quoted."""
    return {norm(m) for m in NUMBER.finditer(text) if m.group(2)}


def norm(m: re.Match) -> str:
    return m.group(1).replace(",", "") + m.group(2).strip().lower()


def allowed(timeline: dict) -> tuple[set[str], set[str], set[str], set[str]]:
    """Numbers the prose may print: (computed figures, numbers quoted in sources, dates, clock times).
    Quoted numbers include number-and-unit tokens as the source wrote them."""
    computed: set[str] = set()
    for d in timeline["durations"].values():
        if "seconds" in d:
            minutes = d["minutes"]
            computed |= {str(minutes), str(d["seconds"])} | numbers(d["display"])
            if minutes % 60 == 0:
                computed.add(str(minutes // 60))
            computed.add(f"{minutes / 60:.1f}".rstrip("0").rstrip("."))
    for i in timeline["impact"]:
        computed.add(str(i["value"]).replace(",", ""))
    quoted: set[str] = set()
    for e in timeline["events"]:
        quoted |= numbers(e["text"]) | numbers(e["ref"]) | with_units(e["text"])
    quoted |= numbers(timeline.get("title", "")) | with_units(timeline.get("title", ""))
    dates, clocks = set(), set()
    for e in timeline["events"]:
        at = datetime.datetime.fromisoformat(e["at"])
        dates.add(at.date().isoformat())
        clocks.add(at.strftime("%H:%M"))
    return computed, quoted, dates, clocks


def prose_fields(draft: dict) -> list[tuple[str, str]]:
    out = [(k, str(draft.get(k) or "")) for k in ("title", "summary", "what_happened")]
    for i, f in enumerate(draft.get("contributing_factors") or []):
        out.append((f"contributing_factors[{i}]", str(f.get("factor") or "")))
    for k in ("what_went_well", "where_we_got_lucky"):
        for i, t in enumerate(draft.get(k) or []):
            out.append((f"{k}[{i}]", str(t or "")))
    for i, a in enumerate(draft.get("action_items") or []):
        out.append((f"action_items[{i}]", str(a.get("action") or "")))
        out.append((f"action_items[{i}].done_when", str(a.get("done_when") or "")))
    return out


def check(timeline: dict, draft: dict) -> list[tuple[str, str, str]]:
    """Every finding as (level, rule, message), errors first in the order found."""
    found: list[tuple[str, str, str]] = []

    def err(rule: str, msg: str) -> None:
        found.append(("error", rule, msg))

    def warn(rule: str, msg: str) -> None:
        found.append(("warning", rule, msg))

    for key in ("title", "author", "summary", "what_happened"):
        if not str(draft.get(key) or "").strip():
            err("missing-field", f"{key} is empty.")
    factors = [f for f in draft.get("contributing_factors") or [] if isinstance(f, dict)]
    actions = [a for a in draft.get("action_items") or [] if isinstance(a, dict)]
    if not factors:
        err("missing-field", "there are no contributing factors.")
    if not actions:
        err("missing-field", "there are no action items.")

    event_ids = {e["id"] for e in timeline["events"]}
    factor_ids = {str(f.get("id")) for f in factors}
    for f in factors:
        fid = f.get("id") or "?"
        if not str(f.get("factor") or "").strip():
            err("missing-field", f"contributing factor {fid} is empty.")
        cited = f.get("evidence") or []
        if not isinstance(cited, list) or not cited:
            err("factor-no-evidence", f"contributing factor {fid} cites no timeline event. Add the ev-N ids it rests on.")
        else:
            for ev in cited:
                if ev not in event_ids:
                    err("factor-no-evidence", f"contributing factor {fid} cites {ev}, which is not in the timeline.")

    first = min((datetime.datetime.fromisoformat(e["at"]).date() for e in timeline["events"]), default=None)
    addressed: set[str] = set()
    for a in actions:
        aid = a.get("id") or "?"
        if not str(a.get("action") or "").strip():
            err("missing-field", f"action item {aid} is empty.")
        owner: Any = a.get("owner")
        if isinstance(owner, list):
            err("action-many-owners", f"action item {aid} lists {len(owner)} owners. Name one person; others can help.")
        elif str(owner or "").strip().lower() in PLACEHOLDER_OWNERS:
            err("action-no-owner", f'action item {aid} has no owner ("{owner or ""}"). Name one person who will see it through.')
        elif MANY_OWNERS.search(str(owner)):
            err("action-many-owners", f'action item {aid} names more than one owner ("{owner}"). Name one person.')
        due = str(a.get("due") or "")
        try:
            due_day = datetime.date.fromisoformat(due)
        except ValueError:
            err("action-bad-due", f'action item {aid} has due "{due}". Use YYYY-MM-DD.')
        else:
            if first and due_day < first:
                err("action-bad-due", f"action item {aid} is due {due}, before the incident ({first}).")
            elif first and (due_day - first).days > FAR_OUT_DAYS:
                warn("due-far-out", f"action item {aid} is due {due}, more than {FAR_OUT_DAYS} days after the incident. Split it or bring it in.")
        if not str(a.get("done_when") or "").strip():
            err("action-no-done-when", f"action item {aid} does not say how anyone will know it is done. Fill done_when.")
        targets = a.get("addresses") or []
        if not isinstance(targets, list) or not targets:
            err("action-addresses-none", f"action item {aid} addresses no contributing factor.")
        else:
            for t in targets:
                if str(t) not in factor_ids:
                    err("action-addresses-none", f"action item {aid} addresses {t}, which is not a contributing factor.")
                addressed.add(str(t))
        text = str(a.get("action") or "")
        if any(re.search(p, text, re.IGNORECASE) for p in VAGUE):
            warn("vague-action", f'action item {aid} ("{text[:60]}") cannot be checked as done. Say what will exist when it is.')
    review = str(draft.get("review_on") or "")
    try:
        datetime.date.fromisoformat(review)
    except ValueError:
        warn("no-follow-up", "review_on is not a YYYY-MM-DD date. Set the day the team checks the action items were done.")
    if len(actions) > MAX_ACTIONS:
        warn("too-many-actions", f"{len(actions)} action items. Keep the {MAX_ACTIONS} that matter most; list the rest as ideas.")
    for fid in sorted(factor_ids - addressed):
        warn("factor-no-action", f"contributing factor {fid} has no action item.")

    computed, quoted, dates, clocks = allowed(timeline)
    due_dates = {str(a.get("due")) for a in actions}
    for where, text in prose_fields(draft):
        for p in BLAME:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                err("blame-language", f'{where}: "{m.group(0)}". Describe what the system and the process allowed, not who erred.')
        for p in AGGREGATE:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                err("aggregate-claim", f'{where}: "{m.group(0)}". One incident has durations, not a mean. Use its own times.')
        if re.search(r"\bthe root cause\b", text, re.IGNORECASE):
            warn("single-root-cause", f"{where}: names one root cause. List the contributing factors instead.")
        scrubbed = re.sub(r"\bev-\d+\b", " ", text)
        for d in DATE.findall(text):
            if d not in dates and d not in due_dates:
                err("figure-not-computed", f"{where}: date {d} is not in the timeline.")
            scrubbed = scrubbed.replace(d, " ")
        for c in CLOCK.findall(scrubbed):
            if c not in clocks and c.zfill(5) not in clocks:
                err("figure-not-computed", f"{where}: time {c} matches no timeline event.")
            scrubbed = scrubbed.replace(c, " ")
        for m in NUMBER.finditer(scrubbed):
            n, unit = m.group(1).replace(",", ""), m.group(2)
            if unit:
                if n not in computed and norm(m) not in quoted:
                    err(
                        "figure-not-computed",
                        f'{where}: "{m.group(0).strip()}" is not a computed figure or quoted from a source. Use a duration or count from timeline.json.',
                    )
            elif n not in computed and n not in quoted:
                err("figure-not-computed", f'{where}: "{n}" is not computed and not quoted from a source.')
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a postmortem draft against its timeline.")
    ap.add_argument("--run", default="run")
    args = ap.parse_args(argv)
    run = Path(args.run)
    try:
        timeline = json.loads((run / "timeline.json").read_text(encoding="utf-8"))
        draft = json.loads((run / "draft.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"check: cannot read the run ({e}). Run timeline.py first.", file=sys.stderr)
        return 2
    found = check(timeline, draft)
    for level, rule, msg in found:
        print(f"{level.upper()} {rule}: {msg}")
    errors = sum(1 for f in found if f[0] == "error")
    print(f"check: {errors} error(s), {len(found) - errors} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
