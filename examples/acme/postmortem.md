# Quote drafting had two incidents since 2026-09-07. All four fixes have one owner and a due date.

Postmortem v0.3.2. As of 2026-11-26. Illustrative: Acme is an invented company, and every figure comes from a synthetic fixture.

Quote drafting is a project you expect to move a number: quote draft acceptance rate, to 40% by 2026-11-15. That target comes from its landing brief, a one-page plan: what good looks like, by when, at what cost. This after-action review is blameless: it says what changed in the system and the process, not who erred.

**Project status, from did-it-land:** landed · **Review:** learning review

## What to do next

Hold the fix review on 2026-12-17: check each fix against its done-when test, and decide what to do about any that slip. Decides: Head of Product, Quoting squad.

## What changed, and who fixes it

Two incidents touched quote drafting after launch. To stop the first, long drafts were sent to a larger model, and that routing stayed in place. It is the main driver of the cost running over the landing brief's budget in early November. Prices stayed in fixed code throughout, as the landing brief's split of who does what says.

### What changed

- **c1.** Long drafts now go to a larger model. The routing was added to stop the timeouts in incident 2141 and had no end date, so it stayed after the incident closed. Evidence: drafts timed out, fixed in 72 minutes; cost over budget from that model: $0.96.
- **c2.** AI usage per task rose past the landing brief's budget once the routing was in place. Evidence: AI usage per task, before: 8,400 units; AI usage per task, actual: 10,300 units; AI usage per task, budget: 9,000 units.
- **c3.** The quality test checks quality only. Version 1.4 met its quality target while cost per task ran over budget, and nothing put the two side by side before ship. Evidence: pass rate on test cases kept back, version 1.4: 80%; cost per task, actual: $0.03376.
- **c4.** When the price book sync lagged, drafts showed price pending. No draft priced a job itself, because prices come from the price book in fixed code. Evidence: price sync lagged, fixed in 22 minutes.

### Who fixes it, by when

| Fix | Done when | Owner | Due | Addresses |
|---|---|---|---|---|
| f1. Send only drafts over the standard model's length limit to the large model, and route the rest back. | The cost check reads AI usage per task within budget for a full two-week window. | Lead, Quoting squad | 2026-12-10 | c1, c2 |
| f2. Give every routing change made during an incident an end date, and list the open ones in the weekly incident review. | The incident template has an end-date field, and the weekly review shows the open list. | Product manager, Quoting squad | 2026-12-17 | c1 |
| f3. Put the cost check's result beside the quality test's result on every quote drafting release candidate. | The next release candidate's checklist links both, and a build over budget is held for a decision. | Tech lead, Quoting squad | 2027-01-08 | c3 |
| f4. Show 'price updating' and retry when the price book sync lags, instead of price pending. | A staged sync delay shows the message, and the draft fills in when the sync completes. | Product manager, Quoting squad | 2026-12-17 | c4 |

## Incidents: 2 incidents

| What happened | Severity | Started (UTC) | Fixed (UTC) | Time to fix |
|---|---|---|---|---|
| Drafts timed out | P2 | 2026-10-30 14:05 | 2026-10-30 15:17 | 72 minutes |
| Price sync lagged | P3 | 2026-11-18 09:40 | 2026-11-18 10:02 | 22 minutes |

## What went well

- The split of who does what held: the model drafts the text and fixed code sets every price.
- The timeouts were stopped the same afternoon they were reported.

## What the earlier steps found

Target: 40% quote draft acceptance rate by 2026-11-15.

- **Decide:** Plan score at the portfolio review. 14 points of 14
- **Build plan check:** hold. spec-auditor's verdict on the build plan. 2 findings
- **Cost check:** over budget. The cost check, actual against the landing brief's budget. AI usage 10,300 units per task, against a budget of 9,000 units; cost $0.03376 per task, against a budget of $0.027
- **Quality test:** not confirmed: too close to call. The quality test, pass rate on test cases kept back for version 1.4. 80%
- **Did it land:** did-it-land's read: now, at the date, and the target. now 43%, on the due date 41%, target 40%

## For your engineers

Skill: `postmortem` 0.3.2.

| Incident | What happened |
|---|---|
| 2141 | Drafts timed out |
| 2203 | Price sync lagged |

The written parts, as written:

- c1: Long drafts now go to a larger model, vendor-a/xl. The routing was added to stop the timeouts in incident 2141 and had no end date, so it stayed after the incident closed.
- c2: Tokens per task rose past the brief's budget once the routing was in place.
- c3: The eval run checks quality only. v1.4 met its eval target while cost per task ran over budget, and nothing put the two side by side before ship.
- c4: When the price book sync lagged, drafts showed price pending. No draft priced a job itself, because prices come from the price book in fixed code.
- f1 (prevent): Send only drafts over the standard model's context limit to vendor-a/xl, and route the rest back. Done when: cost-budget-check reads tokens per task within budget for a full two-week window.
- f2 (process): Give every routing change made during an incident an end date, and list the open ones in the weekly incident review. Done when: The incident template has an end-date field, and the weekly review shows the open list.
- f3 (detect): Put the cost-budget-check result beside the eval-kit result on every quote drafting release candidate. Done when: The next release candidate's checklist links both, and a build over budget is held for a decision.
- f4 (mitigate): Show 'price updating' and retry when the price book sync lags, instead of price pending. Done when: A staged sync delay shows the message, and the draft fills in when the sync completes.

| Change | Evidence | Figure | Window | Source |
|---|---|---|---|---|
| c1 | incident:2141 | 72 minutes | 2026-10-30 14:05 UTC to 2026-10-30 15:17 UTC | PagerDuty (acme): PagerDuty incidents, created\_at to resolved\_at, services Quote drafting (pagerduty-incidents.json, retrieved 2026-11-26); restored\_at - started\_at |
| c1 | record:cost/driver/over\_budget | $0.96 | 2026-11-01 to 2026-11-14 | cost-budget-check 0.3.2: model cost - model token share x budgeted cost; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15); quote-drafting.md |
| c2 | record:cost/lines/tokens\_per\_task/prior | 8,400 tokens per task | 2026-10-18 to 2026-10-31 | cost-budget-check 0.3.2: tokens / tasks, 2026-10-18..2026-10-31; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15) |
| c2 | record:cost/lines/tokens\_per\_task/actual | 10,300 tokens per task | 2026-11-01 to 2026-11-14 | cost-budget-check 0.3.2: tokens / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15) |
| c2 | record:cost/lines/tokens\_per\_task/budget | 9,000 tokens per task | 2026-11-01 to 2026-11-14 | landing brief quote-drafting.md |
| c3 | record:evals/figures/pass\_rate@v1.4 | 80% | 2026-11-15 | quote-drafting.csv (sha256 ee43a12a2395) |
| c3 | record:cost/lines/cost\_per\_task/actual | $0.03376 per task | 2026-11-01 to 2026-11-14 | cost-budget-check 0.3.2: priced cost / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15) |
| c4 | incident:2203 | 22 minutes | 2026-11-18 09:40 UTC to 2026-11-18 10:02 UTC | PagerDuty (acme): PagerDuty incidents, created\_at to resolved\_at, services Quote drafting (pagerduty-incidents.json, retrieved 2026-11-26); restored\_at - started\_at |

| Step | Word | Figure | Window | Source |
|---|---|---|---|---|
| 01 Decide |  | 14 points of 14 | 2026-07-27 | briefs/quote-drafting.md |
| 02 Spec | hold | 2 findings | 2026-08-03 | spec-auditor 0.3.2, audit of examples/acme/specs/quote-drafting.md |
| 03 Build, cost | over budget | 10,300 tokens per task | 2026-11-01 to 2026-11-14 | cost-budget-check 0.3.2: tokens / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15) |
| 03 Build, cost | over budget | 9,000 tokens per task | 2026-11-01 to 2026-11-14 | landing brief quote-drafting.md |
| 03 Build, cost | over budget | $0.03376 per task | 2026-11-01 to 2026-11-14 | cost-budget-check 0.3.2: priced cost / tasks; distinct task ids in gateway.jsonl; gateway.jsonl; pricing.json (Illustrative prices for the Acme sample. Not any provider's list price., retrieved 2026-10-15) |
| 03 Build, cost | over budget | $0.027 per task | 2026-11-01 to 2026-11-14 | landing brief quote-drafting.md (tokens per task x price per token) |
| 03 Build, evals | not confirmed: too close to call | 80% | 2026-11-15 | quote-drafting.csv (sha256 ee43a12a2395) |
| 04 Learn, did-it-land |  | 43% | 2026-09-07 to 2026-11-23 | Illustrative product analytics export, quote\_drafts\_weekly.csv |
| 04 Learn, did-it-land |  | 41% | 2026-09-07 to 2026-11-09 | Illustrative product analytics export, quote\_drafts\_weekly.csv |
| 04 Learn, did-it-land |  | 40% | to 2026-11-15 | landing brief: quote-drafting.md |

Status: printed from `landed.status` as did-it-land 0.3.2 wrote it, never computed here. Review kind: learning review. Window 2026-09-07 to 2026-11-26. Author: Lead, Quoting squad.

Check: what changed: 4 listed, each with its evidence. Who owns each fix: 4 of 4 with one owner and a due date.

Incidents: PagerDuty (acme): PagerDuty incidents, created\_at to resolved\_at, services Quote drafting (pagerduty-incidents.json, retrieved 2026-11-26); incidents started in the window.

The review adds its page to the project file: the `postmortem` key of `landing/<bet>.json`, and no other key.
