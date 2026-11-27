# Changelog

## 0.3.0, 2026-11-26

- Step 04 of the Landing Loop. `scripts/review.py` reads a bet's landing brief, its incidents and its `landing/<bet>.json` record up to `landed` (portfolio, spec, cost, evals, landed), and writes only the `postmortem` key. Every other key is kept byte for byte.
- Check words: what changed, each with the figure or incident it rests on, and who owns each fix, with one owner and a due date. The bet's status is printed from `landed.status` and never computed; a status word in the prose is refused.
- Works for a landed bet (learning review), a stalled one (stall review), one on watch, and one did-it-land has not read yet.
- Live data first: the Leader Report's PagerDuty and incident.io collectors, vendored unchanged at a pinned commit (`VENDORED.json`). CSV is the fallback, checked by the Leader Report's own `collect.py`.
- The brief is parsed by `landing_brief.py`, vendored byte-identical, and its own completeness check refuses an incomplete brief.
- One self-contained HTML page in the Leader Report style, with a Markdown twin and the fixes as CSV.
- Sample: `examples/acme/postmortem.html` for Acme's quote drafting, rebuilt byte for byte by `python3 examples/acme/sample.py`.
- Version 0.3.0 matches the other Landing Loop skills; there was no 0.2.0.
- Every entry script stops on Python older than 3.11 before it reads or writes anything. The sample builds in a scratch folder and moves its outputs into place only on success, and `review.py` renders every output before it writes the record, so a failed run never strips the `postmortem` key.
- Acme people in both samples are the Quoting squad's org-chart roles only; no on-call or other-squad owner.
- Text selection and keyboard focus print in ink, not the template's green, which is kept for landed.

## 0.1.0, 2026-11-26

- First version: a blameless incident postmortem from PagerDuty or incident.io, Slack, the deploy log and Sentry, with every time computed in code and one owner per action item.
