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
9. Mark DONE (sets render_blob_path + composite_score)
"""

from sqlalchemy.ext.asyncio import AsyncSession
from playwright.async_api import Error as PlaywrightError

from backend.src.db.sessions import Sessions, JobStatusEnum
from backend.src.db.users import Users
from backend.src.services.session_service import get_session
from backend.src.services.blob import upload_render

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

    print("--entered process_render_job")
    session_id = message.session_id

    # ----------------------------------------------------------------
    # 1. Fetch session
    # ----------------------------------------------------------------
    session: Sessions | None = await get_session(db=db, session_id=session_id)
    if session is None:
        print(f"Returning: session not found, session_id: {session_id}")
        return

    # ----------------------------------------------------------------
    # 2. Idempotency guards
    # ----------------------------------------------------------------
    if session.status == JobStatusEnum.FAILED:
        print(f"Returning: session is FAILED, session_id: {session_id}")
        return

    if session.status == JobStatusEnum.DONE:
        print(f"Returning: session already DONE, session_id: {session_id}")
        return

    if session.status != JobStatusEnum.ROASTED:
        print(
            f"Returning: session status is {session.status}, "
            f"expected ROASTED, session_id: {session_id}"
        )
        return

    # ----------------------------------------------------------------
    # 3. Mark RENDERING
    # ----------------------------------------------------------------
    session = await mark_rendering(db=db, session=session)
    print("--marked RENDERING")

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
        print(f"DEBUG: Loaded scored.json + roast.json for session_id: {session_id}")

        # ------------------------------------------------------------
        # 6. Build card context
        # ------------------------------------------------------------
        try:
            context = build_card_context(scored=scored, roast=roast, display_name=display_name)
        except Exception as e:
            raise PermanentRenderError(f"Failed to build card context: {e}")
        print(f"DEBUG: Card context built. score={context['score']} stamp={context['stamp']}")

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
        print(f"DEBUG: Rendered card PNG ({len(png_bytes)} bytes) for session_id: {session_id}")

        # ------------------------------------------------------------
        # 8. Upload render.png
        # ------------------------------------------------------------
        try:
            render_blob_path = upload_render(session_id=str(session_id), png_bytes=png_bytes)
        except Exception as e:
            raise TransientRenderError(f"Failed to upload render artifact: {e}")
        print(f"DEBUG: render.png uploaded for session_id: {session_id}")

        # ------------------------------------------------------------
        # 9. Mark DONE
        # ------------------------------------------------------------
        await mark_done(
            db=db,
            session=session,
            render_blob_path=render_blob_path,
            composite_score=context["score"],
        )
        await db.commit()
        print(f"DEBUG: Session marked DONE, session_id: {session_id}")

    # ----------------------------------------------------------------
    # Error handling
    # ----------------------------------------------------------------
    except TransientRenderError:
        raise

    except PermanentRenderError as e:
        print(f"DEBUG: Permanent render error: {e}, session_id: {session_id}")
        await mark_failed(
            db=db,
            session=session,
            error_code="RENDER_FAILED",
            error_reason=str(e),
        )
        await db.commit()

    except Exception as e:
        print(f"DEBUG: Unexpected error in render processor: {e}, session_id: {session_id}")
        raise TransientRenderError(str(e))
