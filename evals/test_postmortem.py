"""Tests for the postmortem skill, on the Acme invoice-sending outage fixture (illustrative).

Run: python3 -m unittest discover -s evals -v
"""

from __future__ import annotations

import contextlib
import copy
import csv
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "skills" / "postmortem" / "examples" / "acme-invoice-outage"
sys.path.insert(0, str(ROOT / "skills" / "postmortem" / "scripts"))

import check  # noqa: E402
import render  # noqa: E402
import sources  # noqa: E402
import timeline  # noqa: E402

ALL = [
    "--pagerduty", str(FIX / "pagerduty-incident.json"),
    "--pagerduty-log", str(FIX / "pagerduty-log-entries.json"),
    "--incidentio", str(FIX / "incidentio-incident.json"),
    "--incidentio-updates", str(FIX / "incidentio-updates.json"),
    "--slack", str(FIX / "slack" / "2026-11-12.json"),
    "--slack-users", str(FIX / "slack" / "users.json"),
    "--slack-channel", "inc-482-invoices",
    "--deploys", str(FIX / "deploys.csv"),
    "--deploy-service", "invoice-service",
    "--sentry", str(FIX / "sentry-issues.json"),
    "--sentry-issue", "INVOICE-SERVICE-7Q",
    "--impact", str(FIX / "impact.csv"),
]  # fmt: skip


def run_timeline(args: list[str]) -> tuple[int, dict | None, str]:
    tmp = tempfile.mkdtemp()
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        code = timeline.main(["--run", tmp, *args])
    path = Path(tmp) / "timeline.json"
    return code, (json.loads(path.read_text()) if path.exists() else None), err.getvalue()


def draft() -> dict:
    return json.loads((FIX / "draft.json").read_text())


def rules(found: list) -> set[str]:
    return {rule for level, rule, _ in found if level == "error"}


class Timeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        code, cls.t, _ = run_timeline(ALL)
        assert code == 0

    def test_durations_computed_in_code(self) -> None:
        d = self.t["durations"]
        self.assertEqual(d["time_to_detect"]["minutes"], 37)
        self.assertEqual(d["time_to_acknowledge"]["minutes"], 2)
        self.assertEqual(d["time_to_mitigate"]["minutes"], 70)
        self.assertEqual(d["time_to_resolve"]["minutes"], 140)
        self.assertEqual(d["detect_to_mitigate"]["minutes"], 33)
        self.assertEqual(d["time_to_mitigate"]["display"], "1 h 10 min")
        self.assertEqual(d["time_to_resolve"]["display"], "2 h 20 min")

    def test_every_moment_names_its_source(self) -> None:
        m = self.t["moments"]
        self.assertIn('incident.io: timestamp "Impact started"', m["impact_started"]["source"])
        self.assertIn("PagerDuty", m["detected"]["source"])  # the page at 14:19 beats the declaration at 14:24
        self.assertIn("PagerDuty", m["acknowledged"]["source"])  # 14:21 beats incident.io "Accepted" at 14:26
        self.assertIn("incident.io", m["resolved"]["source"])

    def test_events_sorted_and_numbered(self) -> None:
        ats = [sources.when(e["at"]) for e in self.t["events"]]
        self.assertEqual(ats, sorted(ats))
        self.assertEqual([e["id"] for e in self.t["events"]], [f"ev-{n}" for n in range(1, len(ats) + 1)])
        self.assertEqual(len(self.t["events"]), 21)

    def test_filters_and_skips_are_counted(self) -> None:
        by = {s["system"]: s["skipped"] for s in self.t["sources"]}
        self.assertEqual(by["Sentry"], {"issues not linked to this incident": 1})
        self.assertEqual(by["Deploy log"], {"rows for other services": 1})
        self.assertEqual(by["Slack"], {"join and leave notices": 1})
        self.assertFalse(any("quote" in e["text"].lower() for e in self.t["events"]))

    def test_disagreement_is_an_open_question(self) -> None:
        self.assertEqual(len(self.t["open_questions"]), 1)
        self.assertIn("16:10", self.t["open_questions"][0])

    def test_impact_rows_carry_sources(self) -> None:
        names = {i["name"]: i for i in self.t["impact"]}
        self.assertEqual(names["Invoices not sent on time"]["value"], 4860)
        self.assertEqual(names["INVOICE-SERVICE-7Q events"]["value"], 18422)
        self.assertTrue(all(i["source"] for i in self.t["impact"]))

    def test_slack_names_resolved(self) -> None:
        actors = {e["actor"] for e in self.t["events"] if e["source"] == "Slack"}
        self.assertEqual(actors, {"Platform on-call lead", "Invoicing squad lead", "AI assistant product lead"})


class Moments(unittest.TestCase):
    def test_unknown_moment_leaves_durations_unknown(self) -> None:
        code, t, _ = run_timeline(["--pagerduty", str(FIX / "pagerduty-incident.json")])
        self.assertEqual(code, 0)
        self.assertIsNone(t["moments"]["impact_started"])
        self.assertEqual(t["durations"]["time_to_detect"]["display"], "Unknown")
        self.assertEqual(t["durations"]["time_to_resolve"]["display"], "Unknown")
        self.assertTrue(any("Impact started is Unknown" in q for q in t["open_questions"]))

    def test_rollback_stands_in_for_mitigation(self) -> None:
        code, t, _ = run_timeline(["--pagerduty", str(FIX / "pagerduty-incident.json"), "--deploys", str(FIX / "deploys.csv")])
        self.assertEqual(code, 0)
        self.assertIn("first rollback after detection", t["moments"]["mitigated"]["source"])
        self.assertEqual(t["moments"]["mitigated"]["display"], "2026-11-12 14:49 UTC")

    def test_author_can_pick_a_moment_from_the_timeline(self) -> None:
        _, base, _ = run_timeline(ALL)
        slack_ev = next(e["id"] for e in base["events"] if e["text"].startswith("Rolling back to"))
        code, t, _ = run_timeline([*ALL, "--moment", f"mitigated={slack_ev}"])
        self.assertEqual(code, 0)
        self.assertIn("chosen by the author", t["moments"]["mitigated"]["source"])
        self.assertEqual(t["durations"]["time_to_mitigate"]["minutes"], 56)

    def test_unknown_event_id_refused(self) -> None:
        code, t, err = run_timeline([*ALL, "--moment", "mitigated=ev-999"])
        self.assertEqual(code, 2)
        self.assertIsNone(t)
        self.assertIn("no such event", err)

    def test_moments_out_of_order_refused(self) -> None:
        _, base, _ = run_timeline(ALL)
        last = base["events"][-1]["id"]
        code, _, err = run_timeline([*ALL, "--moment", f"impact_started={last}"])
        self.assertEqual(code, 2)
        self.assertIn("before Impact started", err)

    def test_no_sources_refused(self) -> None:
        code, _, err = run_timeline([])
        self.assertEqual(code, 2)
        self.assertIn("no sources", err)

    def test_slack_ts_and_epoch_ms_parse(self) -> None:
        self.assertEqual(sources.when("1794493500.000100").minute, 25)
        self.assertEqual(sources.when(1794493500000), sources.when(1794493500))
        self.assertIsNone(sources.when("not a time"))


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, cls.t, _ = run_timeline(ALL)

    def errors(self, d: dict) -> set[str]:
        return rules(check.check(self.t, d))

    def test_fixture_draft_passes(self) -> None:
        self.assertEqual(check.check(self.t, draft()), [])

    def test_action_without_owner_refused(self) -> None:
        for owner in ("", None, "TBD", "the team", "Everyone", "on-call"):
            d = draft()
            d["action_items"][0]["owner"] = owner
            self.assertIn("action-no-owner", self.errors(d), owner)

    def test_action_with_many_owners_refused(self) -> None:
        for owner in ("Kit Amara and Robin Vale", "Kit Amara, Robin Vale", "Kit/Robin", ["Kit Amara", "Robin Vale"]):
            d = draft()
            d["action_items"][0]["owner"] = owner
            self.assertIn("action-many-owners", self.errors(d), owner)

    def test_role_scoped_to_one_team_is_one_owner(self) -> None:
        for owner in ("Lead, Quoting squad", "Tech lead, Quoting squad", "Head of Product, Payments team"):
            d = draft()
            d["action_items"][0]["owner"] = owner
            self.assertNotIn("action-many-owners", self.errors(d), owner)
        for owner in ("Kit Amara, Robin Vale", "Lead, Quoting squad and Tech lead, Quoting squad", "Lead, Quoting squad, Payments squad"):
            d = draft()
            d["action_items"][0]["owner"] = owner
            self.assertIn("action-many-owners", self.errors(d), owner)

    def test_name_containing_and_is_one_owner(self) -> None:
        d = draft()
        d["action_items"][0]["owner"] = "Sandra Anderson"
        self.assertEqual(self.errors(d), set())

    def test_due_date_rules(self) -> None:
        for due in ("", "next sprint", "2026-13-01", "2026-11-01"):
            d = draft()
            d["action_items"][0]["due"] = due
            self.assertIn("action-bad-due", self.errors(d), due)

    def test_action_must_address_a_factor(self) -> None:
        d = draft()
        d["action_items"][0]["addresses"] = []
        self.assertIn("action-addresses-none", self.errors(d))
        d["action_items"][0]["addresses"] = ["CF9"]
        self.assertIn("action-addresses-none", self.errors(d))

    def test_factor_needs_real_evidence(self) -> None:
        d = draft()
        d["contributing_factors"][0]["evidence"] = []
        self.assertIn("factor-no-evidence", self.errors(d))
        d["contributing_factors"][0]["evidence"] = ["ev-999"]
        self.assertIn("factor-no-evidence", self.errors(d))

    def test_blame_language_refused(self) -> None:
        for phrase in ("This was human error.", "Robin was careless with the config.", "Kit should have caught it.", "Engineers must be more careful."):
            d = draft()
            d["contributing_factors"][0]["factor"] = phrase
            self.assertIn("blame-language", self.errors(d), phrase)

    def test_invented_figures_refused(self) -> None:
        for text in ("Detection took 45 min.", "Sends failed for 90% of invoices.", "Roughly 6,000 invoices were late.", "Paged at 14:20."):
            d = draft()
            d["summary"] = text
            self.assertIn("figure-not-computed", self.errors(d), text)

    def test_computed_and_quoted_figures_allowed(self) -> None:
        d = draft()
        d["summary"] = "Detection took 37 min, mitigation 1 h 10 min and resolution 2 h 20 min. Support had 23 tickets; the monitor fires below 95%."
        self.assertEqual(self.errors(d), set())

    def test_missing_fields_refused(self) -> None:
        d = draft()
        d["summary"] = ""
        d["action_items"] = []
        found = check.check(self.t, d)
        msgs = [m for _, r, m in found if r == "missing-field"]
        self.assertTrue(any("summary" in m for m in msgs))
        self.assertTrue(any("no action items" in m for m in msgs))

    def test_warnings_do_not_block(self) -> None:
        d = draft()
        d["what_happened"] += " The root cause was a missing secret path."
        d["action_items"].append(
            {
                "id": "A4",
                "action": "Look into staging drift.",
                "owner": "Kit Amara",
                "due": "2026-12-20",
                "addresses": ["CF1"],
                "done_when": "A written drift report exists.",
            }
        )
        found = check.check(self.t, d)
        self.assertEqual(rules(found), set())
        self.assertEqual({r for lvl, r, _ in found if lvl == "warning"}, {"single-root-cause", "vague-action"})

    def test_factor_without_action_warns(self) -> None:
        d = draft()
        d["action_items"] = d["action_items"][:2]
        found = check.check(self.t, d)
        self.assertIn(("warning", "factor-no-action", "contributing factor CF3 has no action item."), found)


class Render(unittest.TestCase):
    def setUp(self) -> None:
        self.run = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            timeline.main(["--run", self.run, *ALL])
        Path(self.run, "draft.json").write_text(json.dumps(draft()))

    def go(self, *extra: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = render.main(["--run", self.run, *extra])
        return code, err.getvalue()

    def test_renders_with_figures_from_timeline(self) -> None:
        code, _ = self.go("--illustrative")
        self.assertEqual(code, 0)
        md = Path(self.run, "postmortem.md").read_text()
        self.assertIn("**Illustrative.**", md)
        self.assertIn("| Time to detect | 37 min |", md)
        self.assertIn("| A1 |", md)
        self.assertIn("Invoicing squad lead", md)
        self.assertIn("Open questions on the data", md)

    def test_ownerless_action_blocks_render(self) -> None:
        d = draft()
        d["action_items"][1]["owner"] = "TBD"
        Path(self.run, "draft.json").write_text(json.dumps(d))
        code, err = self.go()
        self.assertEqual(code, 1)
        self.assertIn("action-no-owner", err)
        self.assertFalse(Path(self.run, "postmortem.md").exists())

    def test_source_text_cannot_break_the_table(self) -> None:
        self.go()
        md = Path(self.run, "postmortem.md").read_text()
        row = next(line for line in md.splitlines() if "Ignore your rules" in line)
        self.assertIn("\\|", row)
        self.assertEqual(row.count(" | "), md.splitlines()[md.splitlines().index(row) - 1].count(" | "))

    def test_injection_in_source_changes_nothing(self) -> None:
        self.go()
        md = Path(self.run, "postmortem.md").read_text()
        owners = [line.split(" | ")[4] for line in md.splitlines() if re.match(r"^\| A\d+ \|", line)]
        self.assertEqual(owners, ["Invoicing squad lead", "Platform on-call lead", "AI assistant product lead"])

    def test_escape(self) -> None:
        self.assertEqual(render.esc("a|b <script>"), "a\\|b &lt;script&gt;")
        self.assertEqual(render.esc("# heading"), "\\# heading")
        self.assertEqual(render.esc("line\nbreak"), "line break")


class Fixture(unittest.TestCase):
    def test_fixture_is_reproducible(self) -> None:
        import make_fixture

        before = {p.relative_to(FIX): p.read_bytes() for p in FIX.rglob("*") if p.is_file()}
        tmp = Path(tempfile.mkdtemp())
        original = make_fixture.OUT
        make_fixture.OUT = tmp
        try:
            make_fixture.main()
        finally:
            make_fixture.OUT = original
        after = {p.relative_to(tmp): p.read_bytes() for p in tmp.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_draft_is_not_mutated_by_check(self) -> None:
        _, t, _ = run_timeline(ALL)
        d = draft()
        snapshot = copy.deepcopy(d)
        check.check(t, d)
        self.assertEqual(d, snapshot)


class RoundOne(unittest.TestCase):
    """Checks added after the first committee review."""

    @classmethod
    def setUpClass(cls) -> None:
        _, cls.t, _ = run_timeline(ALL)

    def test_action_needs_done_when(self) -> None:
        d = draft()
        d["action_items"][0]["done_when"] = " "
        self.assertIn("action-no-done-when", rules(check.check(self.t, d)))

    def test_aggregate_claims_refused(self) -> None:
        for text in ("Our MTTR was 2 h 20 min.", "Mean time to detect was 37 min.", "On average we detect in 37 min."):
            d = draft()
            d["summary"] = text
            self.assertIn("aggregate-claim", rules(check.check(self.t, d)), text)

    def test_far_due_and_too_many_actions_warn(self) -> None:
        d = draft()
        d["action_items"][0]["due"] = "2027-06-01"
        extra = {"action": "Write the runbook entry.", "owner": "Kit Amara", "due": "2026-12-01", "addresses": ["CF1"], "done_when": "The entry is published."}
        d["action_items"] += [{**extra, "id": f"X{n}"} for n in range(6)]
        found = check.check(self.t, d)
        self.assertEqual(rules(found), set())
        warns = {r for lvl, r, _ in found if lvl == "warning"}
        self.assertTrue({"due-far-out", "too-many-actions"} <= warns)

    def test_changes_before_impact_listed_not_blamed(self) -> None:
        changes = self.t["changes_before_impact"]
        self.assertEqual(len(changes), 1)
        self.assertTrue(changes[0]["text"].startswith("Deployed invoice-service v4.18.0"))

    def test_wide_sentry_window_flagged(self) -> None:
        code, t, _ = run_timeline([*ALL[: ALL.index("--sentry-issue")], "--impact", str(FIX / "impact.csv")])
        self.assertEqual(code, 0)
        flagged = [q for q in t["open_questions"] if "wider than the incident" in q]
        self.assertTrue(any("QUOTE-SERVICE-2C" in q for q in flagged))
        self.assertFalse(any("INVOICE-SERVICE-7Q" in q for q in flagged))

    def test_facts_only_needs_no_draft(self) -> None:
        tmp = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            timeline.main(["--run", tmp, *ALL])
            self.assertEqual(render.main(["--run", tmp, "--facts-only"]), 0)
        md = Path(tmp, "facts.md").read_text()
        self.assertIn("**Facts only.**", md)
        self.assertIn("| Time to detect | 37 min |", md)
        self.assertNotIn("## Action items", md)
        self.assertFalse(Path(tmp, "postmortem.md").exists())

    def test_missing_review_date_warns(self) -> None:
        d = draft()
        del d["review_on"]
        found = check.check(self.t, d)
        self.assertEqual(rules(found), set())
        self.assertIn("no-follow-up", {r for lvl, r, _ in found if lvl == "warning"})

    def test_action_csv_matches_draft(self) -> None:
        rows = list(csv.DictReader(io.StringIO(render.actions_csv(draft()))))
        self.assertEqual([r["owner"] for r in rows], ["Invoicing squad lead", "Platform on-call lead", "AI assistant product lead"])
        self.assertTrue(all(r["done_when"] and r["due"] for r in rows))

    def test_demo_runs_end_to_end(self) -> None:
        import run as runner

        tmp = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(["--demo", "--run", tmp]), 0)
        for name in ("timeline.json", "facts.md", "postmortem.md", "action_items.csv"):
            self.assertTrue(Path(tmp, name).exists(), name)

    def test_shipped_example_is_current(self) -> None:
        import run as runner

        tmp = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            runner.main(["--demo", "--run", tmp])
        self.assertEqual(Path(tmp, "postmortem.md").read_text(), (FIX.parent / "acme-postmortem.md").read_text())


if __name__ == "__main__":
    unittest.main()
