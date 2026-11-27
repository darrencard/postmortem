#!/usr/bin/env python3
"""Regenerate the committed Acme sample: postmortem.html, postmortem.md and the postmortem key of landing/quote-drafting.json.

Inputs, all illustrative (Acme is an invented company): the canonical brief in briefs/ (copied from the landing-loop
repo, unchanged); upstream/quote-drafting.json, the landing-loop record filtered to the keys this step reads
(portfolio, spec, cost, evals, landed); a PagerDuty incidents page in incidents/, read through the Leader Report's
from_pagerduty.py collector, vendored unchanged; and review.json, the written parts. Same inputs, same bytes.

Usage, from the repo root:
  python3 examples/acme/sample.py [--into DIR]

--into writes the outputs somewhere else (the test uses it); paths inside the outputs stay the same.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path("examples/acme")
SCRIPTS = ROOT / "skills" / "postmortem" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import review  # noqa: E402

BET = "quote-drafting"
AS_OF = "2026-11-26"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--into", help="output folder (default examples/acme)")
    args = p.parse_args(argv)
    os.chdir(ROOT)
    into = Path(args.into).resolve() if args.into else ROOT / HERE
    (into / "landing").mkdir(parents=True, exist_ok=True)
    if into != ROOT / HERE:
        (into / "briefs").mkdir(exist_ok=True)
        shutil.copy(HERE / "briefs" / f"{BET}.md", into / "briefs" / f"{BET}.md")
    # Start from the record as did-it-land left it: postmortem reads up to landed and writes only its own key.
    shutil.copy(HERE / "upstream" / f"{BET}.json", into / "landing" / f"{BET}.json")
    with tempfile.TemporaryDirectory() as tmp:
        # Live first: the PagerDuty page goes through the Leader Report's own collector, filtered to the bet's service.
        subprocess.run(  # noqa: S603  (fixed arguments, this interpreter)
            [
                sys.executable, str(SCRIPTS / "vendor" / "from_pagerduty.py"),
                "--incidents", str(HERE / "incidents" / "pagerduty-incidents.json"),
                "--severity-from", "priority",
                "--service", "Quote drafting",
                "--account", "acme",
                "--retrieved-at", AS_OF,
                "--run", tmp,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )  # fmt: skip
        code = review.main(
            [
                "--record", str(into / "landing" / f"{BET}.json"),
                "--incidents", str(Path(tmp) / "data" / "incidents.json"),
                "--review", str(HERE / "review.json"),
                "--as-of", AS_OF,
                "--html", str(into / "postmortem.html"),
                "--md", str(into / "postmortem.md"),
                "--illustrative",
            ]
        )  # fmt: skip
    if code == 0:
        print(f"sample: wrote postmortem.html, postmortem.md and landing/{BET}.json to {into}")
    return code


if __name__ == "__main__":
    sys.exit(main())
