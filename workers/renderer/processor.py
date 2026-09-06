"""
workers/renderer/processor.py

Renderer processor.

Orchestrates:
scored.json + roast.json -> render.png

Pipeline:
1. Fetch session
2. Idempotency guards
3. Mark RENDERING
4. Fetch user (display name)
5. Load scored.json + roast.json
6. Build card context (score, stamp, punchline, ...)
7. Render HTML -> screenshot PNG
8. Upload render.png
8b. Generate unique public slug
9. Mark DONE (sets render_blob_path + composite_score + slug + stamp)
"""

from sqlalchemy.ext.asyncio import AsyncSession
from playwright.async_api import Error as PlaywrightError

from backend.src.db.sessions import Sessions, JobStatusEnum
from backend.src.db.users import Users
from backend.src.services.session_service import get_session, get_session_by_slug
from backend.src.services.blob import upload_render
from backend.src.utils.slug import generate_slug
from backend.src.utils.telemetry import emit_event

from .schemas import RenderJobMessage
from .state import mark_rendering, mark_done, mark_failed
from .errors import TransientRenderError, PermanentRenderError

from .pipeline.loader import load_scored, load_roast
from .pipeline.card_data import build_card_context, compute_score
from .pipeline.template import render_html
from .pipeline.screenshot import html_to_png


async def process_render_job(
    *,
    db: AsyncSession,
    message: RenderJobMessage,
) -> None:
    """Main orchestrator for the render stage."""

    emit_event("render.job.started", {"session_id": str(message.session_id), "status": "INFO"})
    session_id = message.session_id

    # ----------------------------------------------------------------
    # 1. Fetch session
    # ----------------------------------------------------------------
    session: Sessions | None = await get_session(db=db, session_id=session_id)
    if session is None:
        emit_event("render.session.not_found", {"session_id": str(session_id), "status": "WARNING"})
        return

    # ----------------------------------------------------------------
    # 2. Idempotency guards
    # ----------------------------------------------------------------
    if session.status == JobStatusEnum.FAILED:
        emit_event("render.guard.session_failed", {"session_id": str(session_id), "status": "INFO"})
        return

    if session.status == JobStatusEnum.DONE:
        emit_event("render.guard.already_done", {"session_id": str(session_id), "status": "INFO"})
        return

    if session.status != JobStatusEnum.ROASTED:
        emit_event(
            "render.guard.not_roasted",
            {"session_id": str(session_id), "current_status": session.status, "status": "WARNING"},
        )
        return

    # ----------------------------------------------------------------
    # 3. Mark RENDERING
    # ----------------------------------------------------------------
    session = await mark_rendering(db=db, session=session)
    emit_event("render.marked_rendering", {"session_id": str(session_id), "status": "INFO"})

    try:
        # ------------------------------------------------------------
        # 4. Fetch user (display name for the card byline)
        # ------------------------------------------------------------
        try:
            user = await db.get(Users, session.user_id)
        except Exception as e:
            raise TransientRenderError(f"Failed to fetch user: {e}")
        display_name = user.display_name if user else "Anonymous Applicant"

        # ------------------------------------------------------------
        # 5. Load scored.json + roast.json
        # ------------------------------------------------------------
        try:
            scored = load_scored(message.scored_blob_path)
            roast = load_roast(message.roast_blob_path)
        except Exception as e:
            raise TransientRenderError(f"Failed to load upstream artifacts: {e}")
        emit_event("render.artifacts_loaded", {"session_id": str(session_id), "status": "INFO"})

        # ------------------------------------------------------------
        # 6. Build card context
        # ------------------------------------------------------------
        try:
            context = build_card_context(scored=scored, roast=roast, display_name=display_name)
        except Exception as e:
            raise PermanentRenderError(f"Failed to build card context: {e}")
        emit_event(
            "render.context_built",
            {"session_id": str(session_id), "score": context["score"], "stamp": context["stamp"], "status": "INFO"},
        )

        # ------------------------------------------------------------
        # 7. Render HTML -> screenshot PNG
        # ------------------------------------------------------------
        html = render_html(context)
        try:
            png_bytes = await html_to_png(html)
        except TransientRenderError:
            raise
        except PlaywrightError as e:
            raise TransientRenderError(f"Screenshot rendering failed: {e}")
        emit_event(
            "render.screenshot_complete",
            {"session_id": str(session_id), "byte_count": len(png_bytes), "status": "INFO"},
        )

        # ------------------------------------------------------------
        # 8. Upload render.png
        # ------------------------------------------------------------
        try:
            render_blob_path = upload_render(session_id=str(session_id), png_bytes=png_bytes)
        except Exception as e:
            raise TransientRenderError(f"Failed to upload render artifact: {e}")
        emit_event("render.png_uploaded", {"session_id": str(session_id), "status": "INFO"})

        # ------------------------------------------------------------
        # 8b. Generate a unique public slug
        # ------------------------------------------------------------
        slug = None
        for _ in range(5):
            candidate = generate_slug()
            if await get_session_by_slug(db=db, slug=candidate) is None:
                slug = candidate
                break
        if slug is None:
            raise TransientRenderError("Failed to generate a unique slug after 5 attempts")
        emit_event("render.slug_generated", {"session_id": str(session_id), "slug": slug, "status": "INFO"})

        # ------------------------------------------------------------
        # 9. Mark DONE
        # ------------------------------------------------------------
        await mark_done(
            db=db,
            session=session,
            render_blob_path=render_blob_path,
            composite_score=context["score"],
            slug=slug,
            stamp=context["stamp"],
        )
        await db.commit()
        emit_event("render.marked_done", {"session_id": str(session_id), "status": "INFO"})

    # ----------------------------------------------------------------
    # Error handling
    # ----------------------------------------------------------------
    except TransientRenderError:
        raise

    except PermanentRenderError as e:
        emit_event(
            "render.error.permanent",
            {"session_id": str(session_id), "reason": str(e), "status": "ERROR"},
        )
        await mark_failed(
            db=db,
            session=session,
            error_code="RENDER_FAILED",
            error_reason=str(e),
        )
        await db.commit()

    except Exception as e:
        emit_event(
            "render.error.unexpected",
            {"session_id": str(session_id), "reason": str(e), "status": "ERROR"},
        )
        raise TransientRenderError(str(e))
