"""Readers for the incident's sources. Each turns a saved export into timeline events and key-moment candidates.

Every reader takes files as the system returns them and returns a Source: the events it found, the key
moments it can vouch for, and what it skipped. Readers never guess a time. A record with no usable time is
skipped and counted.

Supported exports:
  PagerDuty   GET /incidents/{id} (or a GET /incidents page) and, optionally, GET /incidents/{id}/log_entries
  incident.io GET /v2/incidents/{id} (or a page) and, optionally, GET /v2/incident_updates
  Slack       a channel's daily files from a workspace export (lists of messages), plus users.json for names
  Deploy log  CSV or JSON rows with at (or deployed_at), service, version, kind (deploy or rollback), description
  Sentry      GET /api/0/organizations/{org}/issues/ (or one issue's details)
  Impact      CSV rows with name, value, unit, source: counts someone queried, such as invoices not sent

Standard library only. Makes no network calls.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Json = dict[str, Any]

MOMENTS = ("impact_started", "detected", "acknowledged", "mitigated", "resolved")


class Refused(Exception):
    """A source the scripts cannot read as given. The message says what to fix."""


@dataclass
class Source:
    system: str
    files: list[str]
    events: list[Json] = field(default_factory=list)
    # moment name -> list of (time, description of where it came from)
    moments: dict[str, list[tuple[datetime.datetime, str]]] = field(default_factory=dict)
    impact: list[Json] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    title: str = ""
    severity: str = ""

    def event(self, at: datetime.datetime, kind: str, text: str, ref: str = "", actor: str = "") -> None:
        self.events.append({"at": at.isoformat(), "source": self.system, "kind": kind, "text": clean(text), "ref": clean(ref), "actor": clean(actor)})

    def moment(self, name: str, at: datetime.datetime | None, how: str) -> None:
        if at is not None:
            self.moments.setdefault(name, []).append((at, f"{self.system}: {how}"))

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1


def clean(text: Any) -> str:
    """One line of plain text. Source text is data: it is quoted, never followed."""
    return " ".join(str(text or "").split())[:500]


def when(value: Any) -> datetime.datetime | None:
    """A timestamp in any form systems use: ISO text, epoch seconds or milliseconds, or a Slack ts ("1732612345.000100")."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        v = value.strip()
        try:
            value = float(v) if v.replace(".", "", 1).lstrip("-").isdigit() else v
        except ValueError:
            value = v
    if isinstance(value, (int, float)):
        seconds = value / 1000 if abs(value) > 10**11 else value
        return datetime.datetime.fromtimestamp(seconds, tz=datetime.UTC)
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.UTC)).astimezone(datetime.UTC)


def load_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise Refused(f"cannot read {path} ({e}). Save the system's response as it stands, as UTF-8 JSON.") from None


def records(path: str, *keys: str) -> list[Json]:
    """The records in a saved response: the response itself if it is a list, else the first key holding a list or an object."""
    data = load_json(path)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in keys:
            node = data.get(key)
            if isinstance(node, list):
                return [x for x in node if isinstance(x, dict)]
            if isinstance(node, dict):
                return [node]
    raise Refused(f"{path} holds no list or object under {', '.join(keys)}, as the system returns it.")


def read_rows(path: str) -> list[Json]:
    """Rows from a CSV or a JSON list."""
    if path.lower().endswith(".json"):
        return records(path, "rows", "deploys", "deployments", "data")
    try:
        return list(csv.DictReader(io.StringIO(Path(path).read_text(encoding="utf-8-sig"))))
    except (OSError, UnicodeDecodeError) as e:
        raise Refused(f"cannot read {path} ({e}).") from None


# PagerDuty ----------------------------------------------------------------------------------------

PD_LOG_KINDS = {
    "trigger_log_entry": "alert",
    "acknowledge_log_entry": "acknowledged",
    "escalate_log_entry": "escalated",
    "annotate_log_entry": "note",
    "resolve_log_entry": "resolved",
    "assign_log_entry": "assigned",
}


def pagerduty(incident_files: list[str], log_files: list[str], number: str | None = None) -> Source:
    src = Source("PagerDuty", incident_files + log_files)
    incidents = [i for f in incident_files for i in records(f, "incident", "incidents")]
    if number:
        incidents = [i for i in incidents if str(i.get("incident_number")) == str(number) or str(i.get("id")) == str(number)]
    if len(incidents) != 1:
        raise Refused(f"PagerDuty: expected one incident, found {len(incidents)}. Pass --pagerduty-incident with its number.")
    inc = incidents[0]
    src.title = clean(inc.get("title"))
    src.severity = clean((inc.get("priority") or {}).get("summary") or inc.get("urgency"))
    ref = f"PagerDuty #{inc.get('incident_number') or inc.get('id')}"
    created, resolved = when(inc.get("created_at")), when(inc.get("resolved_at"))
    if created:
        src.event(created, "alert", f"Incident triggered: {inc.get('title', '')}", ref)
        src.moment("detected", created, "incident created_at")
    if resolved:
        src.event(resolved, "resolved", "Incident resolved", ref)
        src.moment("resolved", resolved, "incident resolved_at")
    acked = False
    for e in sorted((e for f in log_files for e in records(f, "log_entries")), key=lambda e: str(e.get("created_at"))):
        at = when(e.get("created_at"))
        kind = PD_LOG_KINDS.get(str(e.get("type")))
        if not at or not kind:
            src.skip("log entries with no time or of a type the timeline does not use")
            continue
        if kind == "alert" and created and at == created:
            continue  # the trigger is already the incident's own created_at
        if kind == "resolved" and resolved and at == resolved:
            continue
        actor = (e.get("agent") or {}).get("summary") or ""
        src.event(at, kind, e.get("summary") or kind, ref, actor)
        if kind == "acknowledged" and not acked:
            src.moment("acknowledged", at, "first acknowledge log entry")
            acked = True
        if kind == "resolved" and not resolved:
            src.moment("resolved", at, "resolve log entry")
    return src


# incident.io --------------------------------------------------------------------------------------

# Each account names its timestamps. These are the defaults; --incidentio-timestamp moment=Name overrides one.
INCIDENTIO_NAMES = {
    "impact_started": ["Impact started"],
    "detected": ["Reported", "Detected"],
    "acknowledged": ["Accepted", "Acknowledged"],
    "mitigated": ["Mitigated", "Stabilised", "Stabilized"],
    "resolved": ["Resolved", "Closed"],
}


def incidentio(incident_files: list[str], update_files: list[str], names: dict[str, list[str]] | None = None, reference: str | None = None) -> Source:
    src = Source("incident.io", incident_files + update_files)
    incidents = [i for f in incident_files for i in records(f, "incident", "incidents")]
    if reference:
        incidents = [i for i in incidents if str(i.get("reference")) == reference or str(i.get("id")) == reference]
    if len(incidents) != 1:
        raise Refused(f"incident.io: expected one incident, found {len(incidents)}. Pass --incidentio-incident with its reference.")
    inc = incidents[0]
    src.title = clean(inc.get("name"))
    src.severity = clean((inc.get("severity") or {}).get("name"))
    ref = f"incident.io {inc.get('reference') or inc.get('id')}"
    declared = when(inc.get("created_at"))
    if declared:
        src.event(declared, "declared", f"Incident declared: {inc.get('name', '')}", ref)
        src.moment("detected", declared, "incident created_at (declared)")
    stamps: dict[str, datetime.datetime] = {}
    for v in inc.get("incident_timestamp_values") or []:
        name = str((v.get("incident_timestamp") or {}).get("name") or "")
        at = when((v.get("value") or {}).get("value"))
        if name and at:
            stamps[name.lower()] = at
            src.event(at, "timestamp", f'Timestamp "{name}" set', ref)
    for moment, candidates in {**INCIDENTIO_NAMES, **(names or {})}.items():
        for name in candidates:
            if name.lower() in stamps:
                src.moment(moment, stamps[name.lower()], f'timestamp "{name}"')
                break
    for u in sorted((u for f in update_files for u in records(f, "incident_updates")), key=lambda u: str(u.get("created_at"))):
        at = when(u.get("created_at"))
        if not at:
            src.skip("updates with no time")
            continue
        status = (u.get("new_incident_status") or {}).get("name") or ""
        actor = ((u.get("updater") or {}).get("user") or {}).get("name") or ""
        text = f"Status {status}: {u.get('message', '')}" if status else u.get("message", "")
        src.event(at, "update", text, ref, actor)
    return src


# Slack --------------------------------------------------------------------------------------------


def slack(message_files: list[str], users_file: str | None, channel: str) -> Source:
    src = Source("Slack", message_files + ([users_file] if users_file else []))
    names: dict[str, str] = {}
    if users_file:
        for u in records(users_file, "members", "users"):
            prof = u.get("profile") or {}
            names[str(u.get("id"))] = prof.get("real_name") or u.get("real_name") or u.get("name") or str(u.get("id"))
    for f in message_files:
        for m in records(f, "messages"):
            at = when(m.get("ts"))
            if not at:
                src.skip("messages with no ts")
                continue
            if m.get("subtype") in {"channel_join", "channel_leave", "bot_add"}:
                src.skip("join and leave notices")
                continue
            actor = names.get(str(m.get("user")), m.get("user_name") or m.get("username") or str(m.get("user") or ""))
            kind = "pinned" if m.get("pinned_to") else "chat"
            src.event(at, kind, m.get("text", ""), f"#{channel} {m.get('ts')}", actor)
    return src


# Deploy log ---------------------------------------------------------------------------------------


def deploys(files: list[str], service: str | None = None) -> Source:
    src = Source("Deploy log", files)
    for f in files:
        for r in read_rows(f):
            at = when(r.get("at") or r.get("deployed_at") or r.get("finished_at") or r.get("created_at"))
            if not at:
                src.skip("rows with no time")
                continue
            if service and str(r.get("service", "")).lower() != service.lower():
                src.skip("rows for other services")
                continue
            kind = str(r.get("kind") or r.get("type") or "deploy").strip().lower()
            kind = "rollback" if kind in {"rollback", "revert", "rolled_back"} else "deploy"
            what = f"{'Rolled back' if kind == 'rollback' else 'Deployed'} {r.get('service', '')} {r.get('version', '')}".strip()
            if r.get("description"):
                what += f": {r['description']}"
            src.event(at, kind, what, str(r.get("version", "")), str(r.get("actor") or r.get("author") or ""))
    return src


# Sentry -------------------------------------------------------------------------------------------


def sentry(files: list[str], issue_ids: list[str] | None = None) -> Source:
    src = Source("Sentry", files)
    keep = {str(i) for i in issue_ids or []}
    for f in files:
        for i in records(f, "issues", "data"):
            ident = str(i.get("shortId") or i.get("id"))
            if keep and ident not in keep and str(i.get("id")) not in keep:
                src.skip("issues not linked to this incident")
                continue
            first, last = when(i.get("firstSeen")), when(i.get("lastSeen"))
            if not first:
                src.skip("issues with no firstSeen")
                continue
            src.event(first, "error", f"First seen: {i.get('title', '')}", ident)
            src.moment("impact_started", first, f"{ident} firstSeen")
            if last:
                src.event(last, "error", f"Last seen: {i.get('title', '')}", ident)
            for name, key, unit in (("events", "count", "events"), ("users", "userCount", "users")):
                value = i.get(key)
                if value not in (None, ""):
                    try:
                        n = int(str(value))
                    except ValueError:
                        continue
                    src.impact.append(
                        {
                            "name": f"{ident} {name}",
                            "value": n,
                            "unit": unit,
                            "source": f"Sentry {ident} {key} (lifetime of the issue)",
                            "first_seen": first.isoformat(),
                            "last_seen": last.isoformat() if last else "",
                        }
                    )
    return src


# Impact counts ------------------------------------------------------------------------------------


def impact(files: list[str]) -> Source:
    src = Source("Impact query", files)
    for f in files:
        for r in read_rows(f):
            raw = str(r.get("value", "")).replace(",", "").strip()
            try:
                value: float | int = int(raw) if raw.lstrip("-").isdigit() else float(raw)
            except ValueError:
                src.skip("rows with no numeric value")
                continue
            if not r.get("name") or not r.get("source"):
                src.skip("rows with no name or no source")
                continue
            src.impact.append({"name": clean(r["name"]), "value": value, "unit": clean(r.get("unit")), "source": clean(r["source"])})
    return src
