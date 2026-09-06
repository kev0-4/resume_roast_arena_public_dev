"""
workers/llm/pipeline/assembler.py

Assembles the final roast.json artifact from parsed LLM output.
"""

from datetime import datetime
from typing import Dict

from ..schemas import RoastOutput, RoastResult, ROAST_VERSION


def assemble_roast(
    *,
    session_id: str,
    roast_result: RoastResult,
    model: str,
    usage: Dict[str, int],
    roasted_at: datetime,
) -> dict:
    """Build and return the roast.json payload as a plain dict."""
    output = RoastOutput(
        session_id=str(session_id),
        roast_version=ROAST_VERSION,
        verdict=roast_result.verdict,
        roast=roast_result.roast,
        fixes=roast_result.fixes,
        highlights=roast_result.highlights,
        model=model,
        usage=usage,
        timestamps={
            "roasted_at": roasted_at.isoformat(),
        },
    )
    return output.model_dump()
