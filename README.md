# Postmortems with real times and owners

A free Claude skill that writes a blameless incident postmortem from your PagerDuty or incident.io export, Slack channel, deploy log and Sentry.

**Why it matters:** Postmortems fail in two places: times someone eyeballed and action items nobody owns. Here code builds the timeline and computes time to detect, mitigate and resolve, each with its source. An action item without one owner and a due date stops the render.

**Go deeper:** the worked example in [evals/fixtures/acme-invoice-outage](evals/fixtures/acme-invoice-outage), an invented company's invoice-sending outage. Every figure in it is illustrative.

## Install: paste one prompt into Claude Code

```text
Install the postmortem skill from https://github.com/darrencard/postmortem (the skills/postmortem folder). Then write a blameless postmortem for incident INCIDENT-ID from the tools already connected to this session: PagerDuty or incident.io, the incident's Slack channel, our deploy log and Sentry. Ask me only for what you cannot find, confirm the key moments with me, and give every action item one owner and a due date.
```

Replace `INCIDENT-ID`. Python 3.11 or later; standard library only.

## What it does

| Feature | What it does for you |
|---|---|
| Timeline in code | Merges every source into one numbered timeline, in UTC, quoted as written |
| Key times in code | Time to detect, acknowledge, mitigate and resolve, each naming the source of both ends |
| Sources that disagree | Listed as open questions, never silently averaged |
| One owner per action | Refuses "TBD", "the team", "on-call" and two names; every action has a due date |
| Evidence for every factor | Each contributing factor cites the timeline events it rests on |
| Blameless check | Blocks "human error", "careless", "should have caught" and similar |
| Figure check | Blocks any duration or count in the prose the scripts did not compute |
| Local | No network calls; incident data stays on your machine |

## Run the tests

```bash
python3 -m unittest discover -s evals -v
```

MIT licensed. Built by [Dacard](https://www.dacard.ai).
