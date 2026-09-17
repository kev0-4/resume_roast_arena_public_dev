"""
Tests for backend/src/utils/telemetry.py

This module had no tests while being the only logging in the product, and
it was silently broken: every event went to a local file that production
could not read and that was wiped on each restart.

The rules pinned here are the ones that matter operationally:
  - one parseable JSON object per line (or Log Analytics queries fail)
  - a level you can filter on (or "show me today's errors" is unwritable)
  - secrets never reach the log store
  - a bad payload never takes down the caller's request

Run with:  python -m pytest backend/src/utils/test_telemetry.py -v
"""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.src.utils.telemetry import emit_event, with_trace


def _emit_and_parse(capsys, event, payload=None):
    emit_event(event, payload)
    out = capsys.readouterr().out.strip()
    assert out, "nothing was written to stdout"
    assert "\n" not in out, "an event must be exactly one line"
    return json.loads(out)


class TestOutputShape:
    def test_writes_one_parseable_json_line(self, capsys):
        entry = _emit_and_parse(capsys, "ingest.received", {"session_id": "abc"})
        assert entry["event"] == "ingest.received"
        assert entry["session_id"] == "abc"

    def test_carries_a_utc_timestamp(self, capsys):
        entry = _emit_and_parse(capsys, "ingest.received")
        # parses, and is timezone-aware -- a naive stamp is unusable across
        # six workers in different containers
        parsed = datetime.fromisoformat(entry["ts"])
        assert parsed.tzinfo is not None

    def test_payload_fields_sit_alongside_the_envelope(self, capsys):
        entry = _emit_and_parse(capsys, "scoring.done",
                                {"score": 71, "duration_ms": 1430})
        assert entry["score"] == 71
        assert entry["duration_ms"] == 1430

    def test_payload_cannot_overwrite_envelope_fields(self, capsys):
        # Queries filter on ts/event/level. A caller must not be able to
        # clobber them, deliberately or by accident.
        entry = _emit_and_parse(capsys, "real.event",
                                {"event": "spoofed", "level": "DEBUG"})
        assert entry["event"] == "real.event"
        assert entry["payload_event"] == "spoofed"

    def test_no_payload_at_all_is_fine(self, capsys):
        entry = _emit_and_parse(capsys, "worker.started")
        assert entry["event"] == "worker.started"


class TestLevel:
    def test_explicit_status_wins(self, capsys):
        entry = _emit_and_parse(capsys, "anything", {"status": "WARNING"})
        assert entry["level"] == "WARNING"

    def test_error_inferred_from_event_name(self, capsys):
        for name in ("llm.call_failed", "render.exception", "queue.dead_letter"):
            assert _emit_and_parse(capsys, name)["level"] == "ERROR"

    def test_warning_inferred_from_event_name(self, capsys):
        for name in ("http.timeout", "ingest.rate_limit_hit", "sweep.stale_found"):
            assert _emit_and_parse(capsys, name)["level"] == "WARNING"

    def test_defaults_to_info(self, capsys):
        assert _emit_and_parse(capsys, "ingest.received")["level"] == "INFO"

    def test_unknown_status_string_does_not_become_the_level(self, capsys):
        # The old module emitted level "UNKNOWN", which made error queries
        # impossible. Anything unrecognised must fall back to inference.
        entry = _emit_and_parse(capsys, "llm.call_failed", {"status": "banana"})
        assert entry["level"] == "ERROR"


class TestSecretsNeverLeak:
    def test_top_level_secret_keys_are_redacted(self, capsys):
        entry = _emit_and_parse(capsys, "auth.attempt", {
            "email": "a@b.com",
            "password": "hunter2",
            "api_key": "sk-live-123",
        })
        assert entry["email"] == "a@b.com"
        assert entry["password"] == "[REDACTED]"
        assert entry["api_key"] == "[REDACTED]"

    def test_nested_secret_keys_are_redacted(self, capsys):
        entry = _emit_and_parse(capsys, "config.loaded",
                                {"db": {"host": "pg", "password": "hunter2"}})
        assert entry["db"]["host"] == "pg"
        assert entry["db"]["password"] == "[REDACTED]"

    def test_secret_value_never_appears_anywhere_in_the_line(self, capsys):
        emit_event("auth.attempt", {"token": "super-secret-value"})
        assert "super-secret-value" not in capsys.readouterr().out


class TestNeverBreaksTheCaller:
    def test_unserialisable_values_do_not_raise(self, capsys):
        class Exploding:
            def __repr__(self):
                raise RuntimeError("boom")

        emit_event("weird.payload", {"thing": Exploding()})
        out = capsys.readouterr().out.strip()
        assert out, "a bad payload must still produce a line"
        json.loads(out)  # and it must still be valid JSON

    def test_uuid_and_datetime_are_serialised(self, capsys):
        sid = uuid4()
        entry = _emit_and_parse(capsys, "session.created", {
            "session_id": sid,
            "at": datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        })
        assert entry["session_id"] == str(sid)
        assert "2026-09-17" in entry["at"]

    def test_non_dict_payload_is_tolerated(self, capsys):
        emit_event("odd.call", "not a dict")  # type: ignore[arg-type]
        entry = json.loads(capsys.readouterr().out.strip())
        assert entry["event"] == "odd.call"

    def test_deeply_nested_payload_terminates(self, capsys):
        deep = cur = {}
        for _ in range(50):
            cur["next"] = {}
            cur = cur["next"]
        emit_event("deep.payload", deep)
        json.loads(capsys.readouterr().out.strip())


class TestWithTrace:
    def test_attaches_the_trace_id(self, capsys):
        with_trace("ingest.received", {"session_id": "s1"}, "trace-abc")
        entry = json.loads(capsys.readouterr().out.strip())
        assert entry["trace_id"] == "trace-abc"
        assert entry["session_id"] == "s1"

    def test_existing_trace_id_in_payload_is_not_overwritten(self, capsys):
        with_trace("ingest.received", {"trace_id": "original"}, "override")
        entry = json.loads(capsys.readouterr().out.strip())
        assert entry["trace_id"] == "original"

    def test_no_trace_id_still_emits(self, capsys):
        with_trace("ingest.received", {"session_id": "s1"}, None)
        entry = json.loads(capsys.readouterr().out.strip())
        assert entry["event"] == "ingest.received"


class TestNoFileIsWritten:
    def test_nothing_is_written_to_disk(self, tmp_path, monkeypatch, capsys):
        """
        The whole point of the change. The old module read and rewrote a
        growing JSON file on every single event; the copies in this repo had
        reached 513KB. Nothing may be created on disk now.
        """
        monkeypatch.chdir(tmp_path)
        for i in range(25):
            emit_event("ingest.received", {"n": i})
        capsys.readouterr()
        assert list(tmp_path.iterdir()) == [], (
            f"telemetry wrote to disk: {[p.name for p in tmp_path.iterdir()]}")
