"""Tests for step 04 of the Landing Loop: the bet review, on the Acme quote-drafting record (illustrative).

Run: python3 -m unittest discover -s evals -v   (pytest runs them too)
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "postmortem"
ACME = ROOT / "examples" / "acme"
LOOP_RECORD = Path.home() / "landing-loop" / "examples" / "acme" / "landing" / "quote-drafting.json"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(ROOT / "examples" / "acme"))

import loop  # noqa: E402
import render_html  # noqa: E402
import review  # noqa: E402
import sample  # noqa: E402
import svgkit  # noqa: E402

VERSION = "0.3.2"


def dumps(v: object) -> str:
    return json.dumps(v, indent=2, ensure_ascii=False)


def run_sample() -> Path:
    out = Path(tempfile.mkdtemp())
    run_sample_into(out)
    return out


def run_sample_into(out: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        assert sample.main(["--into", str(out)]) == 0  # noqa: S101


def figures(node: object, path: str = ""):
    """Every dict that has a value and a unit, with its path."""
    if isinstance(node, dict):
        if "value" in node and "unit" in node:
            yield path, node
        for k, v in node.items():
            yield from figures(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from figures(v, f"{path}/{i}")


class Setup:
    """A working folder with the brief, the upstream record and the collected incidents, ready for review.main."""

    def make(self, record: dict | None = None, review_doc: dict | None = None) -> Path:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "briefs").mkdir()
        (tmp / "landing").mkdir()
        shutil.copy(ACME / "briefs" / "quote-drafting.md", tmp / "briefs" / "quote-drafting.md")
        rec = record if record is not None else json.loads((ACME / "upstream" / "quote-drafting.json").read_text(encoding="utf-8"))
        (tmp / "landing" / "quote-drafting.json").write_text(dumps(rec) + "\n", encoding="utf-8")
        doc = review_doc if review_doc is not None else json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        (tmp / "review.json").write_text(dumps(doc), encoding="utf-8")
        return tmp

    def args(self, tmp: Path, *extra: str) -> list[str]:
        return [
            "--record", str(tmp / "landing" / "quote-drafting.json"),
            "--incidents-csv", str(ACME / "incidents" / "incidents.csv"),
            "--system", "Illustrative incident export",
            "--review", str(tmp / "review.json"),
            "--as-of", "2026-11-26",
            *extra,
        ]  # fmt: skip

    def go(self, tmp: Path, *extra: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = review.main(self.args(tmp, *extra))
        return code, buf.getvalue()


class Record(unittest.TestCase, Setup):
    def test_writes_only_its_own_key_and_keeps_read_keys_byte_identical(self):
        before = json.loads((ACME / "upstream" / "quote-drafting.json").read_text(encoding="utf-8"))
        after = json.loads((ACME / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))
        self.assertEqual(list(after), [*before, "postmortem"])
        for k, v in before.items():
            self.assertEqual(dumps(after[k]), dumps(v), k)

    def test_upstream_is_the_landing_loop_record_filtered(self):
        up = (ACME / "upstream" / "quote-drafting.json").read_text(encoding="utf-8")
        if LOOP_RECORD.exists():
            self.assertEqual(up, dumps(loop.upstream(json.loads(LOOP_RECORD.read_text(encoding="utf-8")))) + "\n")
        self.assertEqual(set(json.loads(up)) - {"schema", "bet", "brief"}, set(loop.READS))

    def test_brief_is_the_canonical_one(self):
        rec = json.loads((ACME / "upstream" / "quote-drafting.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256((ACME / "briefs" / "quote-drafting.md").read_bytes()).hexdigest()
        self.assertEqual(digest, rec["brief"]["sha256"])

    def test_keys_it_does_not_read_are_kept_and_never_cited(self):
        rec = json.loads((ACME / "upstream" / "quote-drafting.json").read_text(encoding="utf-8"))
        rec["signals"] = {"note": "written by another step", "n": 1.10}
        doc = json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        tmp = self.make(rec)
        self.assertEqual(self.go(tmp)[0], 0)
        after = json.loads((tmp / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))
        self.assertEqual(dumps(after["signals"]), dumps(rec["signals"]))
        doc["what_changed"][0]["evidence"] = ["record:signals/n"]
        code, out = self.go(self.make(rec, doc))
        self.assertEqual(code, 1)
        self.assertIn("evidence-not-read", out)

    def test_refused_run_writes_nothing(self):
        doc = json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        doc["fixes"][0]["owner"] = "the team"
        tmp = self.make(review_doc=doc)
        before = (tmp / "landing" / "quote-drafting.json").read_bytes()
        code, out = self.go(tmp, "--html", str(tmp / "p.html"))
        self.assertEqual(code, 1)
        self.assertIn("fix-no-owner", out)
        self.assertEqual((tmp / "landing" / "quote-drafting.json").read_bytes(), before)
        self.assertFalse((tmp / "p.html").exists())


ORG_CHART = {"Head of Product, Quoting squad", "Lead, Quoting squad", "Tech lead, Quoting squad", "Product manager, Quoting squad"}
ENTRY_SCRIPTS = [*sorted((SKILL / "scripts").glob("*.py")), ACME / "sample.py"]


class Floor(unittest.TestCase, Setup):
    """Python 3.11 is the floor: an older interpreter is stopped before anything is read or written."""

    def test_every_entry_script_stops_on_an_old_python_with_a_plain_message(self):
        mains = [p for p in ENTRY_SCRIPTS if "__main__" in p.read_text(encoding="utf-8")]
        self.assertGreaterEqual(len(mains), 6)
        for path in mains:
            code = f"import runpy, sys; sys.version_info = (3, 9, 6); runpy.run_path({str(path)!r}, run_name='__main__')"
            done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, check=False)  # noqa: S603
            self.assertEqual(done.returncode, 1, path.name)
            self.assertIn("needs Python 3.11 or later; try python3.12", done.stderr, path.name)

    def test_a_failed_sample_run_leaves_the_record_as_it_was(self):
        out = run_sample()
        before = (out / "landing" / "quote-drafting.json").read_bytes()
        with mock.patch.object(review.render_html, "page", side_effect=TypeError("boom")), self.assertRaises(TypeError):
            run_sample_into(out)
        self.assertEqual((out / "landing" / "quote-drafting.json").read_bytes(), before)
        self.assertIn(b'"postmortem"', before)

    def test_a_render_failure_in_review_writes_nothing(self):
        tmp = self.make()
        before = (tmp / "landing" / "quote-drafting.json").read_bytes()
        with mock.patch.object(review.render_html, "page", side_effect=TypeError("boom")), self.assertRaises(TypeError):
            self.go(tmp, "--html", str(tmp / "p.html"))
        self.assertEqual((tmp / "landing" / "quote-drafting.json").read_bytes(), before)
        self.assertFalse((tmp / "p.html").exists())


class OrgChart(unittest.TestCase):
    """Acme people are the Quoting squad's roles only: no invented names, no other squads, no on-call owner."""

    def test_loop_sample_owners_and_author_are_org_chart_roles(self):
        key = json.loads((ACME / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]
        self.assertLessEqual({f["owner"] for f in key["fixes"]} | {key["author"], key["brief"]["decides"]}, ORG_CHART)

    def test_team_sample_people_are_org_chart_roles(self):
        draft = json.loads((SKILL / "examples" / "acme-invoice-outage" / "draft.json").read_text(encoding="utf-8"))
        owners = {a["owner"] for a in draft["action_items"]} | {draft["author"]}
        self.assertLessEqual(owners, ORG_CHART)
        users = json.loads((SKILL / "examples" / "acme-invoice-outage" / "slack" / "users.json").read_text(encoding="utf-8"))
        self.assertLessEqual({u["profile"]["real_name"] for u in users}, ORG_CHART)

    def test_no_on_call_or_other_squad_owner_anywhere(self):
        for path in [ACME / "review.json", ACME / "postmortem.md", SKILL / "examples" / "acme-postmortem.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?i)on-call lead|squad lead|product lead|VP Product", path)


class Colour(unittest.TestCase):
    def test_selection_and_focus_print_in_ink_not_green(self):
        page = (ACME / "postmortem.html").read_text(encoding="utf-8")
        css = re.search(r"<style>(.*?)</style>", page, re.S).group(1)
        self.assertLess(css.index("::selection{background:var(--landed)"), css.index("::selection{background:var(--t1)"))
        self.assertLess(css.index("outline:2px solid var(--landed)"), css.index(":focus-visible{outline-color:var(--t1)}"))

    def test_chips_print_in_ink(self):
        page = (ACME / "postmortem.html").read_text(encoding="utf-8")
        for chip in re.findall(r'<span class="chip"[^>]*>', page):
            self.assertNotIn("brass", chip)


class Sample(unittest.TestCase):
    def test_sample_reproduces_byte_for_byte(self):
        out = run_sample()
        for name in ("postmortem.html", "postmortem.md", "landing/quote-drafting.json"):
            self.assertEqual((out / name).read_bytes(), (ACME / name).read_bytes(), name)

    def test_sample_runs_on_a_fresh_interpreter_in_under_a_minute(self):
        out = tempfile.mkdtemp()
        done = subprocess.run([sys.executable, str(ACME / "sample.py"), "--into", out], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_live_collector_and_csv_fallback_agree(self):
        live = json.loads((ACME / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]
        s = Setup()
        tmp = s.make()
        self.assertEqual(s.go(tmp)[0], 0)
        csv_key = json.loads((tmp / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]
        strip = [(i["id"], i["time_to_restore"]["value"], i["severity"]) for i in live["incidents"]]
        self.assertEqual(strip, [(i["id"], i["time_to_restore"]["value"], i["severity"]) for i in csv_key["incidents"]])
        self.assertEqual([i["id"] for i in live["incidents"]], ["2141", "2203"])  # other services and pre-launch left out

    def test_page_is_self_contained_and_marked_illustrative(self):
        page = (ACME / "postmortem.html").read_text(encoding="utf-8")
        self.assertNotRegex(page, r'(?:src|href)="https?://')
        self.assertNotIn("@import", page)
        self.assertIn('<span class="sk-ill">Illustrative</span>', page)
        self.assertIn(":root{--ill:#74A5DA}", page, "the Illustrative tag is blue")
        self.assertNotIn('class="ill"', page, "the template's grey tag")
        self.assertIn("Illustrative", (ACME / "postmortem.md").read_text(encoding="utf-8"))


class Figures(unittest.TestCase):
    def test_every_figure_carries_source_window_and_as_of(self):
        key = json.loads((ACME / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]
        found = list(figures(key))
        self.assertGreater(len(found), 10)
        for path, f in found:
            for field in loop.FIGURE_FIELDS:
                self.assertIn(field, f, path)
            self.assertTrue(f["source"], path)
            self.assertIn("to", f["window"], path)

    def test_time_to_restore_is_computed_in_code(self):
        key = json.loads((ACME / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]
        self.assertEqual([i["time_to_restore"]["value"] for i in key["incidents"]], [72, 22])
        self.assertEqual(key["figures"]["incidents"]["value"], 2)

    def test_a_number_the_page_does_not_print_is_refused(self):
        s = Setup()
        doc = json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        doc["summary"] += " Cost rose 37% in a week."
        code, out = s.go(s.make(review_doc=doc))
        self.assertEqual(code, 1)
        self.assertIn("figure-not-computed", out)

    def test_cited_figures_are_copied_unchanged(self):
        rec = json.loads((ACME / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))
        for c in rec["postmortem"]["what_changed"]:
            for ref, f in c["cited"].items():
                if ref.startswith("record:"):
                    self.assertEqual(f, loop.at(rec, ref[len("record:") :]))


class StatusWords(unittest.TestCase, Setup):
    def visible_words(self, page: str) -> str:
        page = re.sub(r"<style>.*?</style>", "", page, flags=re.S).replace("landed.status", "")
        page = re.sub(r'<span class="st [a-z]+" data-from="landed">[a-z]+</span>', "", page)
        return re.sub(r"<[^>]+>", " ", page)

    def test_no_status_word_outside_the_printed_status(self):
        page = (ACME / "postmortem.html").read_text(encoding="utf-8")
        self.assertEqual(page.count('data-from="landed"'), 1)
        self.assertIn('<span class="st landed" data-from="landed">landed</span>', page)
        self.assertNotRegex(self.visible_words(page), r"\b(landed|watch|stalled)\b")
        md = (ACME / "postmortem.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"\b(landed|watch|stalled)\b", md.replace("landed.status", ""))), 1)

    def test_status_is_printed_never_computed(self):
        rec = json.loads((ACME / "upstream" / "quote-drafting.json").read_text(encoding="utf-8"))
        rec["landed"]["status"] = "stalled"  # the figures still clear the bar: the page prints the word it was given
        tmp = self.make(rec)
        self.assertEqual(self.go(tmp, "--html", str(tmp / "p.html"))[0], 0)
        key = json.loads((tmp / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]
        self.assertEqual(key["landed_status"]["printed"], "stalled")
        self.assertEqual(key["review"], "stall review")
        page = (tmp / "p.html").read_text(encoding="utf-8")
        self.assertIn('<span class="st stalled" data-from="landed">stalled</span>', page)
        self.assertNotRegex(self.visible_words(page), r"\b(landed|watch|stalled)\b")

    def test_without_did_it_land_it_says_so(self):
        rec = json.loads((ACME / "upstream" / "quote-drafting.json").read_text(encoding="utf-8"))
        del rec["landed"]
        tmp = self.make(rec)
        code, _ = self.go(tmp, "--from", "2026-09-07")
        self.assertEqual(code, 0)
        key = json.loads((tmp / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]
        self.assertIsNone(key["landed_status"]["printed"])
        self.assertEqual(key["review"], "incident review")
        self.assertIn("run did-it-land", json.dumps(key["context"]))

    def test_status_word_in_prose_is_refused(self):
        doc = json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        doc["summary"] = "Quote drafting landed, but cost did not."
        code, out = self.go(self.make(review_doc=doc))
        self.assertEqual(code, 1)
        self.assertIn("status-word", out)


class Blameless(unittest.TestCase, Setup):
    def check(self, mutate) -> str:
        doc = json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        mutate(doc)
        code, out = self.go(self.make(review_doc=doc))
        self.assertEqual(code, 1, out)
        return out

    def test_blame_refused(self):
        self.assertIn("blame-language", self.check(lambda d: d["what_changed"][0].update(change="Human error in the routing config.")))

    def test_fix_rules(self):
        self.assertIn("fix-many-owners", self.check(lambda d: d["fixes"][0].update(owner="Priya Shah and Mei Lin")))
        self.assertIn("fix-bad-due", self.check(lambda d: d["fixes"][0].update(due="soon")))
        self.assertIn("fix-no-done-when", self.check(lambda d: d["fixes"][0].update(done_when="")))
        self.assertIn("fix-addresses-none", self.check(lambda d: d["fixes"][0].update(addresses=["c9"])))

    def test_change_needs_evidence(self):
        self.assertIn("change-no-evidence", self.check(lambda d: d["what_changed"][0].update(evidence=[])))
        self.assertIn("change-no-evidence", self.check(lambda d: d["what_changed"][0].update(evidence=["incident:9999"])))

    def test_mttr_refused(self):
        self.assertIn("aggregate-claim", self.check(lambda d: d.update(summary=d["summary"] + " MTTR improved.")))

    def test_source_text_is_escaped(self):
        doc = json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        doc["what_went_well"] = ['<script>alert("x")</script>']
        tmp = self.make(review_doc=copy.deepcopy(doc))
        self.assertEqual(self.go(tmp, "--html", str(tmp / "p.html"))[0], 0)
        self.assertNotIn("<script>", (tmp / "p.html").read_text(encoding="utf-8"))

    def test_fixes_csv_neutralises_formulas(self):
        doc = json.loads((ACME / "review.json").read_text(encoding="utf-8"))
        doc["fixes"][0]["fix"] = "=HYPERLINK('x') route the rest back"
        tmp = self.make(review_doc=doc)
        self.assertEqual(self.go(tmp, "--csv", str(tmp / "f.csv"))[0], 0)
        self.assertIn("'=HYPERLINK", (tmp / "f.csv").read_text(encoding="utf-8"))


class Visual(unittest.TestCase):
    """The page in the Landing Loop's one visual family: svgkit pinned, the picture honest, the words plain."""

    @classmethod
    def setUpClass(cls):
        cls.page = (ACME / "postmortem.html").read_text(encoding="utf-8")
        cls.md = (ACME / "postmortem.md").read_text(encoding="utf-8")
        cls.key = json.loads((ACME / "landing" / "quote-drafting.json").read_text(encoding="utf-8"))["postmortem"]

    def test_svgkit_matches_its_landing_loop_pin(self):
        pin = json.loads((SKILL / "VENDORED.json").read_text(encoding="utf-8"))["landing-loop"]
        self.assertEqual(pin["commit"], "78784efd2ecd5282f6ec264e545ce2075e459be2")
        self.assertEqual(set(pin["files"]), {"scripts/vendor/svgkit.py"})
        for rel, info in pin["files"].items():
            digest = hashlib.sha256((SKILL / rel).read_bytes()).hexdigest()
            self.assertEqual(digest, info["sha256"], f"{rel} changed. Copy it again from landing-loop at the pinned commit and update VENDORED.json.")

    def test_the_visual_draws_only_figures_the_page_prints(self):
        self.assertEqual(svgkit.unprinted(self.page), [])
        frame = svgkit.frames_in(self.page)[0]
        for i in self.key["incidents"]:
            # Each incident is named by what happened; its number is in the engineers' fold.
            self.assertIn(f'<span class="sc-n">{i["what_happened"]}</span>', frame)
            self.assertNotIn(i["id"], svgkit.page_text(frame))
            self.assertIn(i["id"], svgkit.page_text(self.page.split("For your engineers", 1)[1]))
            self.assertIn(f'<span class="sc-l"><b>{loop.shown(i["time_to_restore"]).upper()}</b></span>', frame)
        for f in self.key["fixes"]:
            self.assertIn(f'<span class="sc-l"><b>{f["due"]}</b></span>', frame)
            role = f["owner"].removesuffix(", Quoting squad")
            self.assertIn(f"</svg>{role}</span>", frame, "the role only; the team prints once in the head")
        # Brass is a person's call: one person mark per fix, none on an incident.
        self.assertEqual(frame.count('class="sc-o"'), len(self.key["fixes"]))

    def test_the_team_prints_once_in_the_frame_head_and_each_row_the_role(self):
        frame = svgkit.frames_in(self.page)[0]
        head, body = frame.split('<div class="sc-b">', 1)
        self.assertIn("</svg>Quoting squad</span>", head)
        self.assertNotIn("Quoting squad", body.split('<span class="sc-c">', 1)[0])
        self.assertEqual(render_html.team_of(["Lead, Quoting squad", "Tech lead, Quoting squad"]), "Quoting squad")
        self.assertEqual(render_html.team_of(["Lead, Quoting squad", "Tech lead, Billing"]), "")
        self.assertEqual(render_html.team_of(["Lead, Quoting squad", "CTO"]), "")
        self.assertEqual(render_html.role_of("Head of Product, Quoting squad", "Quoting squad"), "Head of Product")

    def test_severity_prints_major_or_minor_and_the_source_code_only_in_the_fold(self):
        self.assertEqual([render_html.severity_word(s) for s in ("P1", "P2", "p3", "P4", "SEV1", "SEV-3", "Critical", "")], ["major", "major", "minor", "minor", "major", "minor", "critical", ""])
        public, fold = self.page.split("For your engineers", 1)
        self.assertNotRegex(svgkit.page_text(public), r"\bP\d\b")
        frame = svgkit.frames_in(self.page)[0]
        self.assertIn('<span class="sc-w">major</span>', frame)
        self.assertIn('<span class="sc-w">minor</span>', frame)
        self.assertIn(">P2<", fold)
        md = (ACME / "postmortem.md").read_text(encoding="utf-8")
        md_public, md_fold = md.split("## For your engineers", 1)
        self.assertNotRegex(md_public, r"\| P\d \|")
        self.assertIn("| P2 |", md_fold)

    def test_a_fix_row_gives_its_name_the_picture_column_and_figures_print_in_one_case(self):
        css = self.page.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn("@container sc (min-width:800px){.scg .sc-r:has(>.sc-p:empty)>.sc-n{grid-column:1/3}.scg .sc-r:has(>.sc-p:empty)>.sc-p{display:none}}", css)
        self.assertIn(".scg .sc-l{text-transform:uppercase;letter-spacing:.06em}", css)

    def test_green_and_red_only_beside_their_words(self):
        body = self.page.split("</style>", 1)[1]
        rest = re.sub(r'<span class="st (landed|stalled)" data-from="landed">\1</span>', "", body)
        for word in ("landed", "stalled"):
            self.assertNotIn(f"var(--{word})", rest)
            self.assertNotIn(f"st {word}", rest)
        self.assertEqual(body.count('<span class="st landed" data-from="landed">landed</span>'), 1)
        # No status dot in the rows: time to fix has no status.
        for row in re.findall(r'<div class="sc-r">.*?</div>', body):
            self.assertNotRegex(row, r'class="ac (landed|stalled)"')

    def test_each_visual_states_its_answer(self):
        labels = re.findall(r'role="img" aria-label="([^"]+)"', self.page)
        self.assertEqual(labels, [render_html.heading(self.key)])

    # The scorecard grammar (landing-loop tools/SCORECARD-ROLLOUT.md, svgkit 1.2.0)

    def css(self) -> str:
        return self.page.split("<style>", 1)[1].split("</style>", 1)[0]

    def test_no_text_inside_a_picture_and_no_picture_scales(self):
        self.assertEqual(svgkit.svgs_with_text(self.page), [], "text inside an SVG")
        self.assertEqual(svgkit.scaled_svgs_in(self.page), [], "a picture with a viewBox would scale")

    def test_labels_render_12px_and_names_14px(self):
        css = self.css()
        self.assertEqual(set(svgkit.font_sizes(css)), {"var(--sc-m)", "var(--sc-n)"})
        self.assertIn("--sc-m:calc(12px / var(--sc-z))", css)
        self.assertIn("--sc-n:calc(14px / var(--sc-z))", css)
        self.assertIn(".scg{--sc-z:1;", css, "a sample page has no zoom")

    def test_no_box_inside_the_frame_and_no_overlap(self):
        self.assertEqual(svgkit.boxes_in_frames(self.page, self.css()), [])
        self.assertNotIn('class="chip"', self.page.split("For your engineers", 1)[0])
        self.assertNotIn("position:absolute", svgkit.SCORECARD_CSS)

    def test_no_legacy_svgkit_primitive_draws_on_the_page(self):
        import warnings

        self.assertEqual(svgkit.legacy_in(self.page), [])
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            render_html.page(self.key)

    def test_one_frame_one_row_per_incident_and_fix(self):
        frames = svgkit.frames_in(self.page)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].count('<div class="sc-r">'), len(self.key["incidents"]) + len(self.key["fixes"]))
        # One bar per incident, scaled to the longest: no plan bar and no hatching, as there is no plan for time to fix.
        self.assertEqual(frames[0].count('<svg class="sc-sh"'), len(self.key["incidents"]))
        self.assertNotIn("sc-pv", frames[0])
        self.assertNotIn("<pattern", frames[0])
        longest = max(render_html.minutes(i["time_to_restore"]) for i in self.key["incidents"])
        widths = re.findall(r'<rect class="a" x="0" y="0" width="([\d.]+)%"', frames[0])
        self.assertEqual(widths, [svgkit.num(render_html.minutes(i["time_to_restore"]) / longest * 100) for i in self.key["incidents"]])

    def test_cited_check_words_are_the_contract_words(self):
        text = svgkit.page_text(self.page)
        self.assertIn("NOT CONFIRMED: TOO CLOSE TO CALL", text)
        self.assertNotIn("inside noise", self.page)
        self.assertNotIn("inside noise", self.md)
        self.assertEqual(render_html.cited("within-noise"), "inside normal ups and downs")
        self.assertEqual(render_html.cited("not confirmed: inside noise"), "not confirmed: too close to call")

    def test_public_copy_uses_plain_words(self):
        public = svgkit.page_text(self.page.split("For your engineers", 1)[0]).lower()
        md = self.md.split("## For your engineers", 1)[0].lower()
        for text in (public, md):
            for word in ("vendor-a/xl", "tokens per task", "eval run", "eval target", "time to restore", "postmortem:", " bet ", " bar ", ".json", "the prd", "inside noise"):
                self.assertNotIn(word, text)
            # The words a reader outside the loop does not know, as whole words.
            self.assertEqual(re.findall(r"\b(records?|bets?|the bar|prds?|arr|tokens?)\b", text), [])
            self.assertIn("the large model", text)
            self.assertIn("after-action review", text)
            self.assertIn("time to fix", text)
        self.assertIn("<b>landing brief</b>, a one-page plan: what good looks like, by when, at what cost", self.page)
        # The engineers' fold keeps the words as written, model id included.
        self.assertIn("vendor-a/xl", self.page.split("For your engineers", 1)[1])

    def test_the_page_follows_the_sample_anatomy(self):
        body = self.page.split('<main class="solo">', 1)[1]
        order = ['class="sk-hdr"', "<h1>", 'class="marks"', 'class="sc scg"', "What to do next", 'class="cols"', "For your engineers"]
        at = [body.index(x) for x in order]
        self.assertEqual(at, sorted(at))
        self.assertIn("<h1>Quote drafting had two incidents since 2026-09-07. All four fixes have one owner and a due date.</h1>", body)
        self.assertEqual(body.count('<div class="next">'), 1, "one next step leads the page")
        self.assertIn('<span class="o">Head of Product, Quoting squad</span><span class="d">2026-12-17</span>', body)
        self.assertIn("<span>Postmortem</span><span>As of 2026-11-26</span><span>v0.3.2</span>", body)
        self.assertNotIn("Book a call", body, "a sample is the skill's own output: no call to action")
        self.assertTrue(self.md.startswith("# Quote drafting had two incidents since 2026-09-07."))

    def test_no_text_smaller_than_11px_at_any_width(self):
        css = " ".join(re.findall(r"<style>(.*?)</style>", self.page, re.S) + re.findall(r'style="([^"]*)"', self.page))
        sizes = [float(m) for m in re.findall(r"(?:font-size:\s*|font:[^;{}]*?)(\d+(?:\.\d+)?)px", css)]
        sizes += [float(m) for m in re.findall(r'font-size="(\d+(?:\.\d+)?)"', self.page)]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 11)
        # The vendored template is untouched on disk: the page raises its small sizes as it inlines them.
        self.assertIn("font:400 10px/16px", (SKILL / "assets" / "vendor" / "template.html").read_text(encoding="utf-8"))

    def test_header_prints_the_plain_name_and_the_fold_the_code_name(self):
        header = re.search(r'<header class="sk-hdr">.*?</header>', self.page, re.S).group(0)
        self.assertIn("<span>Postmortem</span>", header)
        self.assertIn("<code>postmortem</code>", self.page.split("For your engineers", 1)[1])
        self.assertTrue(self.md.startswith("# ") and "\nPostmortem v" in self.md)

    def test_markdown_twin_is_written_by_the_page_module(self):
        self.assertEqual(render_html.markdown(self.key), self.md)


class Repo(unittest.TestCase):
    TEXT = [
        p
        for p in ROOT.rglob("*")
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".toml", ".yml", ".html"} and not {".git", ".ruff_cache", "vendor", "__pycache__"} & set(p.parts)
    ]

    def test_no_em_dashes_or_banned_words(self):
        banned = re.compile(r"\b(AI-powered|unlock|supercharge|seamless|robust|get started|sign up|leverage)\b", re.I)
        for p in self.TEXT:
            text = p.read_text(encoding="utf-8")
            self.assertNotIn(chr(0x2014), text, p)
            if p.name != "test_loop.py":
                self.assertIsNone(banned.search(re.sub(r"<style>.*?</style>", "", text, flags=re.S)), p)

    def test_version_is_the_same_everywhere(self):
        self.assertEqual(tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"], VERSION)
        self.assertEqual(json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"], VERSION)
        self.assertIn(f'version: "{VERSION}"', (SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(review.VERSION, VERSION)
        self.assertIn(f"## {VERSION}, 2026-11-27", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_vendored_files_match_their_pins(self):
        pins = json.loads((SKILL / "VENDORED.json").read_text(encoding="utf-8"))
        for rel, pin in pins["files"].items():
            self.assertEqual(hashlib.sha256((SKILL / rel).read_bytes()).hexdigest(), pin["sha256"], rel)
        self.assertTrue(pins["files"]["scripts/vendor/landing_brief.py"]["sha256"].startswith("2d13573543c74ebe"))


if __name__ == "__main__":
    unittest.main()
