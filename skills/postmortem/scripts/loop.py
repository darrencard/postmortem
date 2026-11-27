"""The Landing Loop record: one JSON file per bet, landing/<bet-slug>.json, shared by the loop's skills and the Leader Report.

postmortem is step 04 (Learn). It reads the brief and the keys written before it (portfolio, spec, cost, evals,
landed) and writes only its own key, `postmortem`. Every other key, including any it does not read, is kept
exactly as it was found. Every figure it writes carries value, unit, source, window (from, to) and as_of.

The bet's status (landed, watch or stalled) is did-it-land's. This file reads `landed.status` and hands it on to
be printed; it never computes one.

Standard library only. Python 3.11 or later.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import landing_brief  # noqa: E402  (vendored unchanged, see VENDORED.json)

SCHEMA = "landing-loop/1"
KEY = "postmortem"
# The keys this step reads, all earlier in the record order. decisions, release and signals are earlier too,
# but this version does not read them; they stay in the record untouched.
READS = ("portfolio", "spec", "cost", "evals", "landed")
STATUS_WORDS = ("landed", "watch", "stalled")
MAX_RECORD_BYTES = 2_000_000
FIGURE_FIELDS = ("value", "unit", "source", "window", "as_of")


class RecordError(ValueError):
    """A record or brief that cannot be used. Nothing is written when this is raised."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    """The record as it stands. Refused if it is not a landing-loop/1 record."""
    if not path.is_file():
        raise RecordError(f"{path} does not exist. Run the loop's earlier steps first, or pass the record's path.")
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise RecordError(f"{path} is over {MAX_RECORD_BYTES:,} bytes, so it is not a loop record.")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RecordError(f"{path} is not valid JSON ({e}). It is left as it is.") from None
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise RecordError(f"{path} is not a {SCHEMA} record. It is left as it is.")
    if not isinstance(record.get("brief"), dict) or not record["brief"].get("path"):
        raise RecordError(f"{path} names no brief. Every loop record starts from one landing brief.")
    return record


def brief(record: dict[str, Any], folder: Path) -> tuple[Path, landing_brief.Brief, bool]:
    """The brief the record names, parsed by the vendored parser, and whether it still matches the record's hash.
    A brief the parser refuses is refused here too, with the parser's own list of problems."""
    path = folder / record["brief"]["path"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise RecordError(f"the record's brief {record['brief']['path']} is not at {path}.") from None
    try:
        parsed = landing_brief.parse(text)
    except landing_brief.BriefError as e:
        raise RecordError(str(e)) from None
    return path, parsed, sha256(path) == record["brief"].get("sha256")


def title_of(brief_path: Path, fallback: str) -> str:
    for line in brief_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def is_figure(node: Any) -> bool:
    return isinstance(node, dict) and all(k in node for k in FIGURE_FIELDS) and isinstance(node.get("window"), dict)


def at(record: dict[str, Any], ref: str) -> Any:
    """The node at a record path such as cost/lines/tokens_per_task/actual, or None."""
    parts = ref.split("/")
    node: Any = record
    for p in parts:
        node = node.get(p) if isinstance(node, dict) else None
    return node


def status(record: dict[str, Any]) -> str | None:
    """landed.status exactly as did-it-land wrote it, or None when did-it-land has not run. Never computed here."""
    value = (record.get("landed") or {}).get("status")
    return value if value in STATUS_WORDS else None


def figure(value: Any, unit: str, source: str, window_from: str | None, window_to: str | None, as_of: str) -> dict[str, Any]:
    return {"value": value, "unit": unit, "source": source, "window": {"from": window_from, "to": window_to}, "as_of": as_of}


def upstream(record: dict[str, Any]) -> dict[str, Any]:
    """The record filtered to what this step reads: schema, bet, brief and the READS keys present."""
    return {k: v for k, v in record.items() if k in ("schema", "bet", "brief", *READS)}


def write(path: Path, record: dict[str, Any], value: dict[str, Any]) -> Path:
    """Write the `postmortem` key and keep every other key as it was. Written whole, then moved into place."""
    out = dict(record)
    out[KEY] = value
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def shown(f: dict[str, Any]) -> str:
    """A figure as the page prints it. Every number on the page comes through here."""
    v, u = f["value"], f["unit"]
    if not isinstance(v, int | float) or isinstance(v, bool):
        return f"{v} {u}".strip()
    if u == "%":
        return f"{v:g}%"
    if u == "USD per token":
        return f"${v:.8f}".rstrip("0") + " per token"
    if u in ("USD per task", "$"):
        return f"${v:.4g} per task"
    if u == "USD":
        return f"${v:,.2f}"
    if u.startswith("share "):
        return f"{v * 100:.0f}% {u[len('share ') :]}"
    return f"{v:,.10g} {u}"


def window_text(f: dict[str, Any]) -> str:
    w = f.get("window") or {}
    lo, hi = (str(x)[:16].replace("T", " ") + " UTC" if x and "T" in str(x) else x for x in (w.get("from"), w.get("to")))
    return f"{lo} to {hi}" if lo and lo != hi else f"to {hi}" if not lo else str(hi)
