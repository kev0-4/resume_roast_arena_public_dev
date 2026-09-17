"""
backend/src/utils/telemetry.py

Structured event logging. One JSON object per line, written to stdout.

Why stdout: Azure Container Apps captures each container's stdout and ships
it to the environment's Log Analytics workspace (cae-resume-roast-arena is
configured with destination "log-analytics"). Anything printed here is
queryable in production within a minute or so. Nothing else has to exist --
no agent, no SDK, no extra cost.

This module used to append every event to a local file called
log_entry.json, and the only thing that reached production was the line
"Successfully appended entry to log_entry.json". The events themselves --
147 call sites across 19 modules -- went into a file inside the container
that no one could read and that was wiped on every restart and every new
revision. In effect the service had no logging at all.

The file approach was also quadratic: each event read the WHOLE file,
parsed it, appended one entry, and rewrote the WHOLE file. The copies
committed to this repo had reached 513KB and 157KB, which is the cost being
paid per event by the end.

Two rules this module must never break:

1. Logging must never take down a request. Every failure path here is
   swallowed; a broken logger is not worth a 500.
2. Never log secrets. Callers pass payloads straight through, so anything a
   caller puts in a payload ends up in Log Analytics -- see _REDACT_KEYS.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

# Payload keys whose values are replaced before anything is written. Logging
# runs on every request path, so one careless emit_event(..., {"password":
# ...}) would otherwise put credentials in a queryable store.
_REDACT_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "auth", "credential", "credentials", "connection_string",
    "sas", "sas_token", "access_key", "private_key", "id_token", "refresh_token",
})

_REDACTED = "[REDACTED]"

# Event-name fragments that imply a level when the caller didn't set one.
_ERROR_HINTS = ("error", "failed", "failure", "exception", "crash", "dead_letter")
_WARN_HINTS = ("warn", "retry", "timeout", "stale", "throttle", "rate_limit", "degraded")

_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _infer_level(event_name: str, payload: dict) -> str:
    """
    Caller's explicit status wins; otherwise read it off the event name.

    Without this everything arrives as "UNKNOWN", which makes the one query
    that matters -- "show me today's errors" -- impossible to write.
    """
    status = payload.get("status")
    if isinstance(status, str) and status.upper() in _VALID_LEVELS:
        return status.upper()

    name = event_name.lower()
    if any(h in name for h in _ERROR_HINTS):
        return "ERROR"
    if any(h in name for h in _WARN_HINTS):
        return "WARNING"
    return "INFO"


def _scrub(value: Any, depth: int = 0) -> Any:
    """Make a value JSON-safe, recursively, without ever raising."""
    if depth > 6:  # cheap cycle/runaway guard
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(k): (_REDACTED if str(k).lower() in _REDACT_KEYS
                     else _scrub(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_scrub(v, depth + 1) for v in value]
    return str(value)


def emit_event(event_name: str, payload: Optional[dict] = None) -> None:
    """
    Write one structured event as a single line of JSON on stdout.

    Signature is unchanged from the file-writing version so all 147 existing
    call sites keep working untouched.

    In Log Analytics the line lands in ContainerAppConsoleLogs_CL.Log_s, so:

        ContainerAppConsoleLogs_CL
        | where Log_s has "\"level\": \"ERROR\""
        | order by TimeGenerated desc
    """
    payload = payload if isinstance(payload, dict) else {}

    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_name,
            "level": _infer_level(event_name, payload),
        }

        # Payload fields sit alongside, but must never overwrite the three
        # fields above -- those are what every query filters on.
        for key, value in payload.items():
            key = str(key)
            if key in ("ts", "event", "level"):
                key = f"payload_{key}"
            entry[key] = (_REDACTED if key.lower() in _REDACT_KEYS
                          else _scrub(value))

        line = json.dumps(entry, default=str, separators=(",", ":"))
    except Exception:
        # Never let a malformed payload break the caller's request.
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": str(event_name),
            "level": "ERROR",
            "telemetry_error": "payload could not be serialised",
        })

    try:
        # flush because container stdout is block-buffered when not a TTY --
        # without this, events on a crashing worker are lost precisely when
        # they are most needed.
        print(line, file=sys.stdout, flush=True)
    except Exception:
        pass


def with_trace(event_name: str, payload: dict, trace_id: Optional[str] = None) -> None:
    """
    emit_event with a correlation id attached.

    Imported by three route/dependency modules and never called -- it was a
    stub returning None. Implemented rather than deleted so those imports
    keep working, and so there is an obvious place to hang request
    correlation when someone wants to follow one upload across all six
    workers.
    """
    payload = dict(payload) if isinstance(payload, dict) else {}
    if trace_id is not None:
        payload.setdefault("trace_id", trace_id)
    emit_event(event_name, payload)
