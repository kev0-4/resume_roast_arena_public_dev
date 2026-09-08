"""
Runs the eval resume set through the *shipped* code path, not a
standalone prompt harness.

The A/B/C variant test that chose the holistic design compared prompts in
isolation. This instead drives exactly what production runs --
build_roast_prompt -> call_roast_llm (real Gemini, real response_schema)
-> parse_roast_output -> compute_score/compute_stamp -- so a wiring
mistake anywhere in the chain shows up as a wrong score rather than
hiding behind a passing unit test.

Usage:
    python quality-scoring-eval/run_shipped_eval.py [--out results.json]
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "workers" / ".env")

from workers.normalization.pipeline.signals import compute_signals  # noqa: E402
from workers.normalization.pipeline.metrics import compute_metrics  # noqa: E402
from workers.scoring.pipeline.prompt_builder import build_roast_prompt  # noqa: E402
from workers.scoring.pipeline.scorer import score_resume  # noqa: E402
from workers.scoring.pipeline.assembler import _build_summary  # noqa: E402
from workers.llm.pipeline.client import call_roast_llm  # noqa: E402
from workers.llm.pipeline.validator import parse_roast_output  # noqa: E402
from workers.renderer.pipeline.card_data import compute_score, compute_stamp  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resumes import TOP_TIER, MID_TIER, BAD_TIER  # noqa: E402

try:
    # Not in the repo: real people's self-published CVs, kept local-only.
    # The bullets are near-verbatim from two identifiable individuals and
    # would be reverse-searchable if committed to a public repo, so the
    # file is gitignored. The synthetic set below runs without it.
    from real_resumes import REAL_TOP_TIER  # noqa: E402
except ImportError:
    REAL_TOP_TIER = {}


# Gemini free tier is 15 RPM. Run serially with spacing rather than
# firing concurrently -- a burst just converts into 429s and retry
# backoff, which is slower overall and pollutes the results.
_SECONDS_BETWEEN_CALLS = 4.5
_MAX_RETRIES = 4

# Every real upload carries contact details and links; the anonymization
# worker replaces them with placeholders but the *entities* it extracted
# still drive NO_CONTACT_INFO / NO_PROFESSIONAL_LINKS. The fixtures are
# bullet excerpts with no header, so passing entities={} would make all 25
# eat a 25-point penalty no real resume would -- measuring the fixtures'
# shape instead of their content. These stand in for that header.
_TYPICAL_ENTITIES = {
    "emails": [{"value": "[EMAIL]"}],
    "phones": [{"value": "[PHONE]"}],
    "urls": [
        {"value": "https://linkedin.com/in/[REDACTED]"},
        {"value": "https://github.com/[REDACTED]"},
    ],
}


def _as_anonymized(fixture: dict) -> dict:
    """
    Shape a fixture the way the anonymization worker would emit it,
    running the real signal/metric extractors rather than hand-faking
    them -- structural deductions are half the composite score, so
    stubbing them would only test half the pipeline.
    """
    blocks = {k: v for k, v in fixture.items() if k not in ("vertical", "note")}
    raw_text = "\n".join(
        b.get("text", "") for section in blocks.values() for b in section
    )
    entities = _TYPICAL_ENTITIES
    return {
        "content": {"blocks": blocks},
        "signals": compute_signals(blocks=blocks, entities=entities, raw_text=raw_text),
        "metrics": compute_metrics(blocks, entities, raw_text),
    }


async def _call_with_retry(prompt: str):
    """Retry 429s with backoff -- a rate-limited call is a missing data
    point, and silently dropping it would bias the tier medians."""
    for attempt in range(_MAX_RETRIES):
        try:
            return await call_roast_llm(prompt)
        except Exception as exc:  # noqa: BLE001 -- retrying on the message
            if "RESOURCE_EXHAUSTED" not in str(exc) or attempt == _MAX_RETRIES - 1:
                raise
            await asyncio.sleep(20 * (attempt + 1))
    raise RuntimeError("unreachable")


async def _evaluate(name: str, tier: str, fixture: dict) -> dict:
    anonymized = _as_anonymized(fixture)
    blocks = anonymized["content"]["blocks"]
    scoring_result = score_resume(
        signals=anonymized["signals"],
        metrics=anonymized["metrics"],
        blocks=blocks,
    )
    prompt = build_roast_prompt(anonymized=anonymized, scoring_result=scoring_result)

    parsed, usage, model = await _call_with_retry(prompt)
    result = parse_roast_output(parsed, source_text=prompt)

    summary = _build_summary(scoring_result.issues, scoring_result.strengths)
    score = compute_score(summary, result.substance_score)

    return {
        "name": name,
        "tier": tier,
        "vertical": fixture.get("vertical", "?"),
        "substance_score": result.substance_score,
        "substance_reasoning": result.substance_reasoning,
        "word_count": anonymized["metrics"].get("word_count", 0),
        "structural_codes": [i.code for i in scoring_result.issues],
        "structural_deduction": summary.get("critical_issues", 0) * 20
        + summary.get("high_issues", 0) * 10
        + summary.get("medium_issues", 0) * 5
        + summary.get("low_issues", 0) * 2,
        "composite_score": score,
        "stamp": compute_stamp(score),
        "quality_flags": [f.value for f in result.quality_flags],
        "verdict": result.verdict,
        "highlights_kept": len(result.highlights),
        "model": model,
        "usage": usage,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="quality-scoring-eval/shipped_eval_results.json")
    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    sets = [
        ("top", TOP_TIER),
        ("mid", MID_TIER),
        ("bad", BAD_TIER),
        ("real_top", REAL_TOP_TIER),
    ]

    jobs = [(tier, name, fx) for tier, group in sets for name, fx in group.items()]
    total = len(jobs)

    results, failures = [], []
    for i, (tier, name, fixture) in enumerate(jobs, 1):
        print(f"[{i}/{total}] {tier}/{name}", file=sys.stderr)
        try:
            results.append(await _evaluate(name, tier, fixture))
        except Exception as exc:  # noqa: BLE001
            failures.append({"name": name, "tier": tier, "error": repr(exc)[:300]})
        if i < total:
            await asyncio.sleep(_SECONDS_BETWEEN_CALLS)

    Path(args.out).write_text(json.dumps({"results": results, "failures": failures}, indent=2))

    print(f"\n{'tier':<9} {'name':<26} {'sub':>4} {'ded':>4} {'comp':>5}  {'stamp':<8} flags")
    print("-" * 84)
    for r in sorted(results, key=lambda x: (-x["substance_score"],)):
        flags = ",".join(f[:4] for f in r["quality_flags"]) or "-"
        print(
            f"{r['tier']:<9} {r['name']:<26} {r['substance_score']:>4} "
            f"{r['structural_deduction']:>4} {r['composite_score']:>5}  "
            f"{r['stamp']:<8} {flags}"
        )

    def _report(field: str, label: str) -> None:
        by_tier: dict[str, list[int]] = {}
        for r in results:
            by_tier.setdefault(r["tier"], []).append(r[field])
        print(f"\n{label} by tier:")
        for tier in ("top", "real_top", "mid", "bad"):
            scores = sorted(by_tier.get(tier, []))
            if not scores:
                continue
            median = scores[len(scores) // 2]
            print(f"  {tier:<9} n={len(scores):<3} median={median:<4} "
                  f"range={scores[0]}-{scores[-1]}")
        allv = [r[field] for r in results]
        if allv:
            print(f"  overall spread: {min(allv)}-{max(allv)} ({max(allv) - min(allv)} points)")

    _report("substance_score", "SUBSTANCE (the LLM's content judgment)")
    _report("composite_score", "COMPOSITE (substance - structural deductions)")

    # Vertical skew was a named finding of the first eval -- check it
    # didn't survive the redesign.
    by_vertical: dict[str, list[int]] = {}
    for r in results:
        if r["tier"] == "top":
            by_vertical.setdefault(r["vertical"], []).append(r["substance_score"])
    print("\ntop-tier substance by vertical (skew check):")
    for vertical, scores in sorted(by_vertical.items()):
        scores.sort()
        print(f"  {vertical:<6} n={len(scores):<3} median={scores[len(scores) // 2]:<4} "
              f"range={scores[0]}-{scores[-1]}")

    if failures:
        print(f"\n{len(failures)} FAILURES:")
        for f in failures:
            print(f"  {f['tier']}/{f['name']}: {f['error'][:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
