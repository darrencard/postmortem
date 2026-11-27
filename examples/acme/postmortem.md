# Postmortem: Quote drafting

> **Illustrative.** Acme is an invented company. Every figure comes from a synthetic fixture.

**Status, printed from landed.status:** landed · **Review:** learning review · **Window:** 2026-09-07 to 2026-11-26

**Author:** Priya Shah, Quoting squad lead · **Fix review:** 2026-12-17 · **Decides:** Head of Product, Quoting squad

This review is blameless. It says what changed in the system and the process, not who erred.

Two incidents touched quote drafting after launch. To stop the first, long drafts were sent to a larger model, and that routing stayed in place. It is the main driver of the cost running over the brief's budget in early November. Prices stayed in fixed code throughout, as the brief's line says.

## The bet, as the record has it

Bar: 40% Quote draft acceptance rate by 2026-11-15.

| Step | Says | Figures |
|---|---|---|
| 01 Decide | Brief score at the portfolio review. | 14 points of 14 (briefs/quote-drafting.md, 2026-07-27) |
| 02 Spec | hold. spec-auditor's verdict on the PRD. | 2 findings (spec-auditor 0.3.0, audit of examples/acme/specs/quote-drafting.md, 2026-08-03) |
| 03 Build, cost | over budget. cost-budget-check, actual against the brief's budget. | 10,300 tokens per task (cost-budget-check 0.3.0: tokens / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15), 2026-11-01 to 2026-11-14); 9,000 tokens per task (landing brief quote-drafting.md, 2026-11-01 to 2026-11-14); $0.03376 per task (cost-budget-check 0.3.0: priced cost / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15), 2026-11-01 to 2026-11-14); $0.027 per task (landing brief quote-drafting.md (tokens per task x price per token), 2026-11-01 to 2026-11-14) |
| 03 Build, evals | meets target. eval-kit, held-out pass rate for v1.4. | 80% (quote-drafting.csv (sha256 ee43a12a2395), 2026-11-15) |
| 04 Learn, did-it-land | did-it-land's read: now, at the date, and the bar. | 43% (Illustrative product analytics export, quote\_drafts\_weekly.csv, 2026-09-07 to 2026-11-23); 41% (Illustrative product analytics export, quote\_drafts\_weekly.csv, 2026-09-07 to 2026-11-09); 40% (landing brief: quote-drafting.md, to 2026-11-15) |

## Incidents in the window: 2 incidents

Source: PagerDuty (acme): PagerDuty incidents, created\_at to resolved\_at, services Quote drafting (pagerduty-incidents.json, retrieved 2026-11-26); incidents started in the window.

| Incident | Severity | Started (UTC) | Restored (UTC) | Time to restore |
|---|---|---|---|---|
| 2141 | P2 | 2026-10-30 14:05 | 2026-10-30 15:17 | 72 minutes |
| 2203 | P3 | 2026-11-18 09:40 | 2026-11-18 10:02 | 22 minutes |

## What changed

- **c1.** Long drafts now go to a larger model, vendor-a/xl. The routing was added to stop the timeouts in incident 2141 and had no end date, so it stayed after the incident closed.
  - incident:2141: 72 minutes, 2026-10-30 14:05 UTC to 2026-10-30 15:17 UTC. Source: PagerDuty (acme): PagerDuty incidents, created\_at to resolved\_at, services Quote drafting (pagerduty-incidents.json, retrieved 2026-11-26); restored\_at - started\_at.
  - record:cost/driver/over\_budget: $0.96, 2026-11-01 to 2026-11-14. Source: cost-budget-check 0.3.0: model cost - model token share x budgeted cost; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15); quote-drafting.md.
- **c2.** Tokens per task rose past the brief's budget once the routing was in place.
  - record:cost/lines/tokens\_per\_task/prior: 8,400 tokens per task, 2026-10-18 to 2026-10-31. Source: cost-budget-check 0.3.0: tokens / tasks, 2026-10-18..2026-10-31; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15).
  - record:cost/lines/tokens\_per\_task/actual: 10,300 tokens per task, 2026-11-01 to 2026-11-14. Source: cost-budget-check 0.3.0: tokens / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15).
  - record:cost/lines/tokens\_per\_task/budget: 9,000 tokens per task, 2026-11-01 to 2026-11-14. Source: landing brief quote-drafting.md.
- **c3.** The eval run checks quality only. v1.4 met its eval target while cost per task ran over budget, and nothing put the two side by side before ship.
  - record:evals/figures/pass\_rate@v1.4: 80%, 2026-11-15. Source: quote-drafting.csv (sha256 ee43a12a2395).
  - record:cost/lines/cost\_per\_task/actual: $0.03376 per task, 2026-11-01 to 2026-11-14. Source: cost-budget-check 0.3.0: priced cost / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15).
- **c4.** When the price book sync lagged, drafts showed price pending. No draft priced a job itself, because prices come from the price book in fixed code.
  - incident:2203: 22 minutes, 2026-11-18 09:40 UTC to 2026-11-18 10:02 UTC. Source: PagerDuty (acme): PagerDuty incidents, created\_at to resolved\_at, services Quote drafting (pagerduty-incidents.json, retrieved 2026-11-26); restored\_at - started\_at.

## What went well

- The line held: the model drafts the text and fixed code sets every price.
- The timeouts were stopped the same afternoon they were reported.

## Fixes: who owns each

| Fix | Done when | Owner | Due | Addresses |
|---|---|---|---|---|
| f1. Send only drafts over the standard model's context limit to vendor-a/xl, and route the rest back. | cost-budget-check reads tokens per task within budget for a full two-week window. | Priya Shah | 2026-12-10 | c1, c2 |
| f2. Give every routing change made during an incident an end date, and list the open ones in the weekly incident review. | The incident template has an end-date field, and the weekly review shows the open list. | Tomás Reyes | 2026-12-17 | c1 |
| f3. Put the cost-budget-check result beside the eval-kit result on every quote drafting release candidate. | The next release candidate's checklist links both, and a build over budget is held for a decision. | Sam Okafor | 2027-01-08 | c3 |
| f4. Show 'price updating' and retry when the price book sync lags, instead of price pending. | A staged sync delay shows the message, and the draft fills in when the sync completes. | Mei Lin | 2026-12-17 | c4 |

Check: what changed: 4 listed, each with its evidence. Who owns each fix: 4 of 4 with one owner and a due date.

Written by postmortem 0.3.0 on 2026-11-26. The status is did-it-land's, printed from landed.status. Every figure is computed in code from the source named.
