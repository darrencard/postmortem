# Changelog

## 0.3.1, 2026-11-27

- The HTML page follows the Landing Loop sample anatomy: the shared header (mark, DACARD, skill, date, version, blue Illustrative tag), the verdict as the heading ("Quote drafting had two incidents since 2026-09-07. All four fixes have one owner and a due date."), the project's status from did-it-land, the signature picture, one next step (the fix review) with the brief's decider in brass and its date, then what changed and who fixes it in two columns, and the incidents, what went well and the earlier steps in two more. Evidence with its sources, the written parts as written, the check line and the record key fold under "For your engineers".
- The signature picture: one timeline from the window opening through each incident (with its time to fix) and the review to each fix's due date, each fix's owner in a brass chip and the fix review as a brass person mark. A 640 wide variant for desktop and a 340 wide one for phones; the aria-label states the answer. Drawn with svgkit, vendored byte-identical from landing-loop and pinned in `VENDORED.json` under `landing-loop`.
- Public copy in plain words, on the page and in the Markdown twin, which `render_html.markdown` now writes: after-action review, project, target, landing brief (defined at first use), time to fix, AI usage per task, the large model, quality test. The record keeps the written parts as written.
- The Illustrative tag is the family's blue, not the template's grey.
- Tests: the picture draws only printed figures, green appears only beside the word landed, the aria-label states the answer, public copy uses the plain words, and the vendored svgkit matches its pin.

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
