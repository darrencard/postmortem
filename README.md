# Postmortem: what changed, and who owns each fix

```text
Install the postmortem skill from https://github.com/darrencard/postmortem and run a blameless review of one bet. Read its landing brief and its landing/<bet>.json record, pull the bet's incidents from PagerDuty or incident.io through the skill's collectors (or take my CSV), and draft what changed with the evidence for each. Ask me for each fix's owner and due date, run review.py until it passes, and show me the HTML page.
```

A free Claude skill that writes a blameless postmortem of a bet: what changed while it was live, with the evidence for each, and one owner and a due date for every fix.

**Why it matters:** postmortems fail in two places, claims nobody can trace and fixes nobody owns. Here code prints every figure with its source, and a fix without one owner stops the page.

## See it in one command

Acme is invented: invoicing software for trades businesses. Every figure is illustrative. From the repository root, on Python 3.11 or later:

```bash
python3 examples/acme/sample.py
```

It rebuilds [examples/acme/postmortem.html](examples/acme/postmortem.html) (and its [Markdown twin](examples/acme/postmortem.md)) in under a second: a learning review of Acme's quote drafting, two incidents, four changes and four owned fixes. A test checks the command reproduces the committed files byte for byte.

## Install

In Claude Code, with the Landing Loop:

```text
/plugin marketplace add darrencard/landing-loop
/plugin install postmortem@landing-loop
```

On its own: clone this repository and copy `skills/postmortem` into `~/.claude/skills/postmortem`. Python 3.11 or later, standard library only. Nothing else to install.

## Reads and writes

Step 04 (Learn) of the Landing Loop.

| Reads | Writes |
|---|---|
| The landing brief the record names, parsed by the Leader Report's `landing_brief.py` (vendored byte-identical); an incomplete brief is refused | The `postmortem` key of `landing/<bet>.json`, and no other key |
| Incidents: live from PagerDuty or incident.io through the Leader Report's collectors, vendored at a pinned commit; a CSV as the fallback | One HTML page in the Leader Report style, its Markdown twin, and the fixes as CSV for a tracker |
| The record's `portfolio`, `spec`, `cost`, `evals` and `landed` keys | |

The bet's status is did-it-land's. The page prints `landed.status` and never computes one. The review follows it: a learning review for a landed bet, a stall review for a stalled one. This skill's own check words are **what changed** and **who owns each fix**.

## The record key

```json
"postmortem": {
  "tool": "postmortem 0.3.0",
  "as_of": "2026-11-26",
  "review": "learning review",
  "landed_status": {"printed": "landed", "from": "landed.status", "computed_by": "did-it-land 0.3.1"},
  "figures": {
    "incidents": {"value": 2, "unit": "incidents", "source": "PagerDuty (acme): PagerDuty incidents ...",
                  "window": {"from": "2026-09-07", "to": "2026-11-26"}, "as_of": "2026-11-26"}
  },
  "what_changed": [{"id": "c2", "change": "Tokens per task rose past the brief's budget ...",
                    "evidence": ["record:cost/lines/tokens_per_task/actual"], "cited": {"...": "the figure, copied unchanged"}}],
  "fixes": [{"id": "f1", "fix": "Send only long drafts to the larger model ...", "done_when": "...",
             "owner": "Lead, Quoting squad", "due": "2026-12-10", "addresses": ["c1", "c2"], "kind": "prevent"}],
  "check": "what changed: 4 listed, each with its evidence. Who owns each fix: 4 of 4 with one owner and a due date."
}
```

## What it refuses

| Check | Why |
|---|---|
| A fix with no owner, a placeholder ("the team", "TBD", "on-call") or two owners | One person sees it through |
| A fix with no due date or no "done when" | You can tell when it is finished |
| A change with no evidence, or evidence that is not a figure in the record or an incident | Every claim traces to a source |
| A number the page does not print | The model never writes a figure |
| landed, watch or stalled in the prose | Only did-it-land sets a bet's status |
| "Human error", "careless", "should have caught" | Blameless: systems and process, not people |
| MTTR or a mean | Each incident keeps its own time |

It also writes a single incident's postmortem from PagerDuty or incident.io, Slack, the deploy log and Sentry, with time to detect, acknowledge, mitigate and resolve computed in code: `python3 skills/postmortem/scripts/run.py --demo`. See [SKILL.md](skills/postmortem/SKILL.md).

## Limits

- It says what changed, not what caused the metric to move. A change is listed with its evidence, never as proof.
- An incident still open is left out by the collectors and counted in their output, not on the page.
- This version does not read `decisions`, `release` or `signals`; it keeps them untouched in the record.
- The collectors read saved responses. Fetching them (a connector, or an API call the user runs) happens first.

Not yet run on a real team's data.

Run the tests: `python3 -m unittest discover -s evals`.

MIT licence. Made by [Dacard](https://www.dacard.ai). PagerDuty, incident.io, Slack and Sentry are trademarks of their owners; this skill is not affiliated with or endorsed by them.

Claude and Claude Code are trademarks of Anthropic, PBC. These skills are independent and not affiliated with or endorsed by Anthropic.
