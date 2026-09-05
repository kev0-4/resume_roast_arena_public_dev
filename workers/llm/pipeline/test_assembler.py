"""
Unit tests for workers/llm/pipeline/assembler.py

Run with:  python -m pytest workers/llm/pipeline/test_assembler.py -v
"""

import pytest
from datetime import datetime
from .assembler import assemble_roast
from ..schemas import RoastResult, ROAST_VERSION


def _make_roast_result(**kwargs) -> RoastResult:
    defaults = {
        "verdict": "Your resume is spectacularly mediocre.",
        "roast": "The work experience reads like a job description, not a career.",
        "fixes": ["Quantify impact", "Remove filler phrases", "Shorten skills list"],
    }
    defaults.update(kwargs)
    return RoastResult(**defaults)


class TestAssembleRoast:
    def test_returns_dict(self):
        result = assemble_roast(
            session_id="abc-123",
            roast_result=_make_roast_result(),
            model="claude-haiku-4-5",
            usage={"input_tokens": 500, "output_tokens": 300},
            roasted_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        assert isinstance(result, dict)

    def test_session_id_present(self):
        result = assemble_roast(
            session_id="my-session",
            roast_result=_make_roast_result(),
            model="claude-haiku-4-5",
            usage={"input_tokens": 500, "output_tokens": 300},
            roasted_at=datetime(2024, 1, 1),
        )
        assert result["session_id"] == "my-session"

    def test_roast_version_set(self):
        result = assemble_roast(
            session_id="s",
            roast_result=_make_roast_result(),
            model="claude-haiku-4-5",
            usage={"input_tokens": 100, "output_tokens": 50},
            roasted_at=datetime(2024, 1, 1),
        )
        assert result["roast_version"] == ROAST_VERSION

    def test_verdict_matches(self):
        roast = _make_roast_result(verdict="A bold statement.")
        result = assemble_roast(
            session_id="s",
            roast_result=roast,
            model="claude-haiku-4-5",
            usage={},
            roasted_at=datetime(2024, 1, 1),
        )
        assert result["verdict"] == "A bold statement."

    def test_roast_body_matches(self):
        roast = _make_roast_result(roast="The body of the roast.")
        result = assemble_roast(
            session_id="s",
            roast_result=roast,
            model="claude-haiku-4-5",
            usage={},
            roasted_at=datetime(2024, 1, 1),
        )
        assert result["roast"] == "The body of the roast."

    def test_fixes_list_preserved(self):
        fixes = ["Fix A", "Fix B", "Fix C"]
        roast = _make_roast_result(fixes=fixes)
        result = assemble_roast(
            session_id="s",
            roast_result=roast,
            model="claude-haiku-4-5",
            usage={},
            roasted_at=datetime(2024, 1, 1),
        )
        assert result["fixes"] == fixes

    def test_model_field_present(self):
        result = assemble_roast(
            session_id="s",
            roast_result=_make_roast_result(),
            model="claude-opus-5",
            usage={},
            roasted_at=datetime(2024, 1, 1),
        )
        assert result["model"] == "claude-opus-5"

    def test_usage_field_present(self):
        usage = {"input_tokens": 1000, "output_tokens": 400}
        result = assemble_roast(
            session_id="s",
            roast_result=_make_roast_result(),
            model="claude-haiku-4-5",
            usage=usage,
            roasted_at=datetime(2024, 1, 1),
        )
        assert result["usage"] == usage

    def test_timestamps_roasted_at(self):
        ts = datetime(2024, 6, 15, 10, 30, 0)
        result = assemble_roast(
            session_id="s",
            roast_result=_make_roast_result(),
            model="claude-haiku-4-5",
            usage={},
            roasted_at=ts,
        )
        assert "roasted_at" in result["timestamps"]
        assert "2024-06-15" in result["timestamps"]["roasted_at"]

    def test_required_keys_present(self):
        result = assemble_roast(
            session_id="s",
            roast_result=_make_roast_result(),
            model="claude-haiku-4-5",
            usage={"input_tokens": 1, "output_tokens": 1},
            roasted_at=datetime(2024, 1, 1),
        )
        required = {"session_id", "roast_version", "verdict", "roast", "fixes", "model", "usage", "timestamps"}
        assert required.issubset(result.keys())
