"""
Tests against real Postgres + real Azurite (same philosophy as every
other test this session -- no mocks). Same asyncio.run()-per-test +
engine.dispose() pattern as workers/cleanup/test_sweep.py; every
TestClient use is `with TestClient(app) as client:` (required, not
stylistic -- see test_sessions_status.py's module docstring for why: it
fires the app's lifespan shutdown hook, which is what disposes the
shared async engine cleanly between tests).
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions, get_session, get_session_rank
from backend.src.services.user_service import get_or_create_users_from_claims, create_anonymous_user
from backend.src.services.blob import initialize_blob_storage, upload_scored, upload_roast
from backend.src.config import ANONYMOUS_ROAST_TTL_DAYS
from backend.src import create_app


def _run(coro_fn):
    async def wrapped():
        try:
            await coro_fn()
        finally:
            await engine.dispose()

    asyncio.run(wrapped())


async def _make_user(db, suffix: str):
    return await get_or_create_users_from_claims(
        {
            "uid": f"public-data-test-{suffix}",
            "email": f"public-data-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"PublicDataTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )


SCORED_FIXTURE = {
    "summary": {
        "total_issues": 2,
        "critical_issues": 0,
        "high_issues": 1,
        "medium_issues": 1,
        "low_issues": 0,
        "total_strengths": 2,
    },
    "metrics": {"word_count": 312, "avg_sentence_length": 18.4, "lexical_diversity": 0.52},
    "issues": [
        {"code": "NO_PROJECTS", "message": "No projects section found", "severity": "high"},
        {"code": "FIRST_PERSON_USAGE", "message": "Uses first-person language", "severity": "medium"},
    ],
    "strengths": [
        {"code": "HAS_EXPERIENCE", "message": "Includes experience section"},
        {"code": "HAS_SKILLS", "message": "Includes skills section"},
    ],
}

ROAST_FIXTURE = {
    "verdict": "Competent but forgettable.",
    "roast": "The experience section is fine, but nothing here sticks.",
    "fixes": ["Quantify your impact.", "Cut the buzzwords."],
    "highlights": [{"quote": "team player", "comment": "Everyone says this. Nobody proves it."}],
}


async def _make_full_session(db, user_id, *, score, slug):
    initialize_blob_storage()
    session = await create_sessions(user_id=user_id, db=db)
    session_id = session.id
    upload_scored(session_id=str(session_id), data=SCORED_FIXTURE)
    upload_roast(session_id=str(session_id), data=ROAST_FIXTURE)
    session = await get_session(db=db, session_id=session_id)
    session.status = "DONE"
    session.slug = slug
    session.composite_score = score
    db.add(session)
    await db.commit()
    return session_id


class TestGetSessionRank:
    def test_rank_and_total_reflect_real_data(self):
        async def run():
            async with AsyncSessionLocal() as db:
                user = await _make_user(db, f"rank-{uuid.uuid4().hex[:6]}")
                user_id = user.id
                low_id = await _make_full_session(db, user_id, score=10, slug=f"lo{uuid.uuid4().hex[:6]}")
                mid_id = await _make_full_session(db, user_id, score=50, slug=f"md{uuid.uuid4().hex[:6]}")
                high_id = await _make_full_session(db, user_id, score=90, slug=f"hi{uuid.uuid4().hex[:6]}")

                mid_session = await get_session(db=db, session_id=mid_id)
                rank, total = await get_session_rank(
                    db=db, composite_score=mid_session.composite_score, created_at=mid_session.created_at,
                )
                # exactly one real session (the "high" one) scores above
                # "mid" among the three just created -- rank is at least 2
                # (could be higher if other tests left rows in the shared
                # dev DB, but never lower)
                assert rank >= 2
                assert total >= 3

        _run(run)

    def test_tie_broken_by_created_at(self):
        async def run():
            async with AsyncSessionLocal() as db:
                user = await _make_user(db, f"tie-{uuid.uuid4().hex[:6]}")
                user_id = user.id
                now = datetime.utcnow()
                earlier_id = await _make_full_session(db, user_id, score=77, slug=f"ea{uuid.uuid4().hex[:6]}")
                session = await get_session(db=db, session_id=earlier_id)
                session.created_at = now - timedelta(minutes=5)
                db.add(session)
                await db.commit()

                later_id = await _make_full_session(db, user_id, score=77, slug=f"la{uuid.uuid4().hex[:6]}")
                later_session = await get_session(db=db, session_id=later_id)

                rank, _ = await get_session_rank(
                    db=db, composite_score=later_session.composite_score, created_at=later_session.created_at,
                )
                # the earlier same-score session sorts ahead -- later's
                # rank must be at least 2, never 1
                assert rank >= 2

        _run(run)


class TestPublicDataRoute:
    def test_returns_full_analysis(self):
        ids = {}
        slug = f"pubdata{uuid.uuid4().hex[:6]}"

        async def setup():
            async with AsyncSessionLocal() as db:
                user = await _make_user(db, f"route-{slug}")
                session_id = await _make_full_session(db, user.id, score=62, slug=slug)
                ids["id"] = session_id

        _run(setup)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get(f"/r/{slug}/data")

        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == slug
        assert body["composite_score"] == 62
        assert body["stamp"] in ("ROASTED", "SOLID", "MID")
        assert body["rank"] >= 1
        assert body["total_ranked"] >= 1
        assert body["summary"]["total_issues"] == 2
        assert body["metrics"]["word_count"] == 312
        # NO_PROJECTS (high, -25) -> Structure=75; FIRST_PERSON_USAGE
        # (medium, -15) -> Clarity=85; everything else untouched by the
        # fixture's issues, Skills=100 from the HAS_SKILLS strength
        assert body["subscores"]["Structure"] == 75
        assert body["subscores"]["Clarity"] == 85
        assert body["subscores"]["Contact"] == 100
        assert body["subscores"]["Experience"] == 100
        assert body["subscores"]["Conciseness"] == 100
        assert body["subscores"]["Skills"] == 100
        # ROAST_FIXTURE has no quality_issues -- Quality stays untouched at 100
        assert body["subscores"]["Quality"] == 100
        assert body["verdict"] == "Competent but forgettable."
        assert body["fixes"] == ["Quantify your impact.", "Cut the buzzwords."]
        assert body["highlights"][0]["quote"] == "team player"
        assert "public" in resp.headers.get("cache-control", "")

    def test_quality_issues_lower_the_quality_subscore_and_stamp(self):
        # Rule engine alone (a fixture with zero structural issues) would
        # call this SOLID -- two LLM-issued HIGH quality flags should pull
        # it down to ROASTED, and the radar chart's Quality axis should
        # reflect the deduction. This is the actual feature: a resume with
        # clean structure but hollow content shouldn't score as if it had
        # neither problem.
        ids = {}
        slug = f"qual{uuid.uuid4().hex[:6]}"
        clean_scored = {
            "summary": {
                "total_issues": 0,
                "critical_issues": 0,
                "high_issues": 0,
                "medium_issues": 0,
                "low_issues": 0,
                "total_strengths": 3,
            },
            "metrics": {"word_count": 300},
            "issues": [],
            "strengths": [
                {"code": "HAS_EXPERIENCE", "message": "x"},
                {"code": "HAS_PROJECTS", "message": "x"},
                {"code": "HAS_SKILLS", "message": "x"},
            ],
        }
        flagged_roast = {
            "verdict": "Clean but hollow.",
            "roast": "Every section exists but says nothing real.",
            "fixes": ["Add real numbers.", "Cut the buzzwords."],
            "highlights": [],
            "quality_issues": [
                {"code": "GENERIC_BULLETS", "severity": "high"},
                {"code": "NO_QUANTIFIED_IMPACT", "severity": "high"},
            ],
        }

        async def setup():
            async with AsyncSessionLocal() as db:
                user = await _make_user(db, f"qual-{slug}")
                initialize_blob_storage()
                session = await create_sessions(user_id=user.id, db=db)
                session_id = session.id
                upload_scored(session_id=str(session_id), data=clean_scored)
                upload_roast(session_id=str(session_id), data=flagged_roast)
                session = await get_session(db=db, session_id=session_id)
                session.status = "DONE"
                session.slug = slug
                session.composite_score = 80
                db.add(session)
                await db.commit()
                ids["id"] = session_id

        _run(setup)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get(f"/r/{slug}/data")

        assert resp.status_code == 200
        body = resp.json()
        # 2 HIGH quality issues -> 25*2 = 50 deduction, floored logic n/a here
        assert body["subscores"]["Quality"] == 50
        # Same 2-HIGH threshold compute_stamp uses for rule-engine issues
        assert body["stamp"] == "ROASTED"
        # Unaffected axes stay at 100 -- the deduction is scoped to Quality only
        assert body["subscores"]["Structure"] == 100

    def test_unknown_slug_404s(self):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/r/does-not-exist-at-all/data")
        assert resp.status_code == 404

    def test_expired_anonymous_roast_returns_410(self):
        ids = {}
        slug = f"expired{uuid.uuid4().hex[:6]}"

        async def setup():
            async with AsyncSessionLocal() as db:
                anon_user = await create_anonymous_user(db)
                session_id = await _make_full_session(db, anon_user.id, score=40, slug=slug)
                session = await get_session(db=db, session_id=session_id)
                session.created_at = datetime.utcnow() - timedelta(days=ANONYMOUS_ROAST_TTL_DAYS + 1)
                db.add(session)
                await db.commit()
                ids["id"] = session_id

        _run(setup)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get(f"/r/{slug}/data")
        assert resp.status_code == 410


class TestComputeSubscores:
    """
    Unit tests against the pure function directly (no DB/blob involved) --
    the route-level test above only exercises one fixed issue/strength
    combination; these cover the parts of _compute_subscores that combo
    doesn't reach: multiple issues compounding in one category, the floor
    at 0, and the no-corresponding-issue Skills special case.
    """

    def test_multiple_issues_in_same_category_compound(self):
        from backend.src.routes.public import _compute_subscores

        scored = {
            "issues": [
                {"code": "NO_EXPERIENCE", "message": "x", "severity": "critical"},
                {"code": "NO_PROJECTS", "message": "x", "severity": "high"},
            ],
            "strengths": [],
        }
        # both land in Structure: 100 - 40 (critical) - 25 (high) = 35
        assert _compute_subscores(scored)["Structure"] == 35

    def test_floors_at_zero_not_negative(self):
        from backend.src.routes.public import _compute_subscores

        scored = {
            "issues": [
                {"code": "NO_CONTACT_INFO", "message": "x", "severity": "critical"},
                {"code": "NO_PROFESSIONAL_LINKS", "message": "x", "severity": "critical"},
                {"code": "NO_PROFESSIONAL_LINKS", "message": "x", "severity": "critical"},
            ],
            "strengths": [],
        }
        # 40 + 40 + 40 = 120 raw deduction -- must clamp at 0, not go negative
        assert _compute_subscores(scored)["Contact"] == 0

    def test_skills_without_strength_gets_neutral_default_not_zero(self):
        from backend.src.routes.public import _compute_subscores

        scored = {"issues": [], "strengths": []}
        result = _compute_subscores(scored)
        assert result["Skills"] == 55
        # every deduction-based category with zero issues stays at 100
        assert result["Structure"] == 100
        assert result["Contact"] == 100

    def test_skills_with_strength_is_100(self):
        from backend.src.routes.public import _compute_subscores

        scored = {"issues": [], "strengths": [{"code": "HAS_SKILLS", "message": "x"}]}
        assert _compute_subscores(scored)["Skills"] == 100

    def test_no_quality_issues_arg_defaults_quality_to_100(self):
        from backend.src.routes.public import _compute_subscores

        scored = {"issues": [], "strengths": []}
        assert _compute_subscores(scored)["Quality"] == 100

    def test_quality_issues_deduct_from_quality_only(self):
        from backend.src.routes.public import _compute_subscores

        scored = {
            "issues": [{"code": "NO_EXPERIENCE", "message": "x", "severity": "critical"}],
            "strengths": [],
        }
        quality_issues = [{"code": "BUZZWORD_FILLER", "severity": "medium"}]
        result = _compute_subscores(scored, quality_issues)
        # BUZZWORD_FILLER (medium, -15) only touches Quality
        assert result["Quality"] == 85
        # Structure's deduction is from the rule-engine issue, unaffected by quality_issues
        assert result["Structure"] == 60

    def test_unknown_quality_code_is_ignored_not_raised(self):
        from backend.src.routes.public import _compute_subscores

        scored = {"issues": [], "strengths": []}
        quality_issues = [{"code": "SOME_FUTURE_CODE", "severity": "high"}]
        assert _compute_subscores(scored, quality_issues)["Quality"] == 100


class TestMergeQualityIntoSummary:
    """
    Mirrors workers/renderer/pipeline/test_card_data.py's
    TestMergeQualityIntoSummary -- this file's _merge_quality_into_summary
    is a deliberate duplicate (see its own docstring for why), so it gets
    the same test coverage independently rather than assuming the two
    copies can't drift.
    """

    def test_no_quality_issues_is_a_no_op(self):
        from backend.src.routes.public import _merge_quality_into_summary

        summary = {"high_issues": 1, "total_issues": 1}
        assert _merge_quality_into_summary(summary, []) == summary

    def test_quality_issues_increment_matching_severity_and_total(self):
        from backend.src.routes.public import _merge_quality_into_summary

        summary = {"high_issues": 1, "total_issues": 1}
        quality_issues = [
            {"code": "GENERIC_BULLETS", "severity": "high"},
            {"code": "SHALLOW_CONTENT", "severity": "low"},
        ]
        merged = _merge_quality_into_summary(summary, quality_issues)
        assert merged["high_issues"] == 2
        assert merged["low_issues"] == 1
        assert merged["total_issues"] == 3

    def test_does_not_mutate_the_original_summary(self):
        from backend.src.routes.public import _merge_quality_into_summary

        summary = {"high_issues": 1, "total_issues": 1}
        _merge_quality_into_summary(summary, [{"code": "SHALLOW_CONTENT", "severity": "low"}])
        assert summary == {"high_issues": 1, "total_issues": 1}
