# Postmortems with real times and owners

A free Claude skill that writes a blameless incident postmortem from your PagerDuty or incident.io export, Slack channel, deploy log and Sentry.

**Why it matters:** Postmortems fail in two places: times someone eyeballed and action items nobody owns. Here code builds the timeline and computes time to detect, mitigate and resolve, each with its source. An action item without one owner and a due date stops the render.

**Go deeper:** [the postmortem it writes](skills/postmortem/examples/acme-postmortem.md) for an invented company's invoice-sending outage, from [these sources](skills/postmortem/examples/acme-invoice-outage). Every figure in it is illustrative.

## Install: paste one prompt into Claude Code

```text
Install the postmortem skill from https://github.com/darrencard/postmortem (the skills/postmortem folder). Then write a blameless postmortem for incident INCIDENT-ID from the tools already connected to this session: PagerDuty or incident.io, the incident's Slack channel, our deploy log and Sentry. Ask me only for what you cannot find, confirm the key moments with me, and give every action item one owner and a due date.
```

Replace `INCIDENT-ID`. Python 3.11 or later; standard library only. Tested so far on the Acme example only: no live PagerDuty, incident.io, Slack or Sentry export has been run through it yet.

**See it first, in one command:** `python3 skills/postmortem/scripts/run.py --demo` writes the example's facts, postmortem and action items CSV to `run/`.

**On your incident, the facts come first:** key times, impact, changes before impact and the timeline land in `run/facts.md` before anyone writes a word. Bring it to the review meeting.

## What it does

| Feature | What it does for you |
|---|---|
| Timeline in code | Merges every source into one numbered timeline, in UTC, quoted as written |
| Key times in code | Time to detect, acknowledge, mitigate and resolve, each naming the source of both ends |
| Sources that disagree | Listed as open questions, never silently averaged |
| One owner per action | Refuses "TBD", "the team", "on-call" and two names; every action has a due date and a test for done |
| Tracker-ready actions | Writes `action_items.csv` for a Linear or Jira import |
| Changes before impact | Lists every deploy in the 24 hours before impact, as a list, never as a cause |
| Evidence for every factor | Each contributing factor cites the timeline events it rests on |
| Blameless check | Blocks "human error", "careless", "should have caught" and similar |
| Figure check | Blocks any duration or count in the prose the scripts did not compute, and any MTTR or mean from one incident |
| Local | No network calls; incident data stays on your machine |

## Run the tests

```bash
python3 -m unittest discover -s evals -v
```

MIT licensed. Built by [Dacard](https://www.dacard.ai).
