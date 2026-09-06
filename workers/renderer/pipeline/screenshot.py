"""
workers/renderer/pipeline/screenshot.py

Renders an HTML string to PNG bytes via a headless browser.

Uses Playwright's ASYNC API deliberately -- process_render_job runs inside
an asyncio event loop (workers/renderer/consumer.py's receive loop), and
Playwright's sync API raises if called from a thread with a running loop.

Reuses one lazily-launched browser across messages (cold start is ~1-2s;
every consumer in this codebase processes one message at a time --
MAX_CONCURRENT_MESSAGES=1 -- so the asyncio.Lock below is cheap insurance
against a future concurrency bump, not something exercised today).

Launches Playwright's own managed Chromium (`chromium.launch()`, no
`channel=` override) -- pinned to whatever version the installed
`playwright` package resolves, reproducible via `playwright install
chromium` in the Dockerfile. Previously used channel="chrome" to reuse
an already-installed system Chrome and skip the ~300MB download during
local dev; switched for the real Azure deployment, where the container
image has no system Chrome preinstalled and channel="chrome" would just
fail outright, and where an implicit dependency on whatever Chrome apt
happens to resolve isn't reproducible anyway.
"""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Playwright, Error as PlaywrightError

from ..errors import TransientRenderError

_VIEWPORT = {"width": 420, "height": 525}
_DEVICE_SCALE_FACTOR = 1080 / 420  # exports at Instagram's recommended 1080x1350

_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_lock = asyncio.Lock()


async def _launch_browser() -> Browser:
    global _playwright
    if _playwright is None:
        _playwright = await async_playwright().start()
    return await _playwright.chromium.launch()


async def _get_browser() -> Browser:
    global _browser
    async with _lock:
        if _browser is None or not _browser.is_connected():
            _browser = await _launch_browser()
    return _browser


async def _render_once(html: str) -> bytes:
    browser = await _get_browser()
    page = await browser.new_page(
        viewport=_VIEWPORT,
        device_scale_factor=_DEVICE_SCALE_FACTOR,
    )
    try:
        await page.set_content(html, wait_until="load")
        await page.evaluate("document.fonts.ready")
        return await page.screenshot(type="png")
    finally:
        await page.close()


async def html_to_png(html: str) -> bytes:
    try:
        return await _render_once(html)
    except PlaywrightError as e:
        # Browser process likely crashed/disconnected -- relaunch once and retry.
        global _browser
        async with _lock:
            _browser = None
        try:
            return await _render_once(html)
        except Exception as retry_exc:
            raise TransientRenderError(
                f"Failed to render card screenshot after browser relaunch: {retry_exc}"
            ) from e


async def close_browser() -> None:
    """Call on worker shutdown for clean teardown."""
    global _browser, _playwright
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None
