#!/usr/bin/env python3
"""One command from the incident's exports to the facts, or to the Acme demo.

Usage:
  python3 scripts/run.py --demo
      Runs the Acme example end to end (illustrative) and writes run/facts.md, run/postmortem.md and
      run/action_items.csv. Use it to see the output before you touch your own data.

  python3 scripts/run.py --run run --pagerduty incident.json --slack channel/*.json ...
      Takes every timeline.py flag. Builds the timeline, then renders run/facts.md: key times, impact,
      changes before impact, open questions and the timeline, with nothing written by a model yet.
      If run/draft.json is filled in, it also checks it and renders run/postmortem.md.

Standard library only. Runs on Python 3.11 or later. Makes no network calls.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render  # noqa: E402  (sibling scripts, found through the path above)
import timeline  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "acme-invoice-outage"
DEMO = [
    "--pagerduty", str(EXAMPLE / "pagerduty-incident.json"),
    "--pagerduty-log", str(EXAMPLE / "pagerduty-log-entries.json"),
    "--incidentio", str(EXAMPLE / "incidentio-incident.json"),
    "--incidentio-updates", str(EXAMPLE / "incidentio-updates.json"),
    "--slack", str(EXAMPLE / "slack" / "2026-11-12.json"),
    "--slack-users", str(EXAMPLE / "slack" / "users.json"),
    "--slack-channel", "inc-482-invoices",
    "--deploys", str(EXAMPLE / "deploys.csv"),
    "--deploy-service", "invoice-service",
    "--sentry", str(EXAMPLE / "sentry-issues.json"),
    "--sentry-issue", "INVOICE-SERVICE-7Q",
    "--impact", str(EXAMPLE / "impact.csv"),
]  # fmt: skip


def run_dir(argv: list[str]) -> Path:
    return Path(argv[argv.index("--run") + 1]) if "--run" in argv else Path("run")


def drafted(path: Path) -> bool:
    try:
        return bool(str(json.loads(path.read_text(encoding="utf-8")).get("summary") or "").strip())
    except (OSError, json.JSONDecodeError):
        return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    demo = "--demo" in argv
    if demo:
        argv = [a for a in argv if a != "--demo"]
        argv = (["--run", str(run_dir(argv))] if "--run" in argv else []) + DEMO
    run = run_dir(argv)
    code = timeline.main(argv)
    if code:
        return code
    extra = ["--illustrative"] if demo else []
    code = render.main(["--run", str(run), "--facts-only", *extra])
    if code:
        return code
    if demo:
        shutil.copyfile(EXAMPLE / "draft.json", run / "draft.json")
    if drafted(run / "draft.json"):
        return render.main(["--run", str(run), *extra])
    print("run: next, fill run/draft.json (see SKILL.md, step 4), then run scripts/check.py and scripts/render.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
