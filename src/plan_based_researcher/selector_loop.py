"""Event loop factory for psycopg async (rejects Windows ProactorEventLoop)."""

from __future__ import annotations

import asyncio
import sys


def new_selector_event_loop() -> asyncio.AbstractEventLoop:
    """Zero-arg factory for uvicorn ``--loop`` / ``asyncio.run(loop_factory=...)``."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy().new_event_loop()
    return asyncio.new_event_loop()


def require_psycopg_compatible_loop() -> None:
    """Fail fast on Windows ProactorEventLoop instead of hanging in the pool."""
    if sys.platform != "win32":
        return
    loop = asyncio.get_running_loop()
    if isinstance(loop, asyncio.ProactorEventLoop):
        raise RuntimeError(
            "psycopg async cannot use Windows ProactorEventLoop. "
            "Start the API with `uv run python -m plan_based_researcher` "
            "or pass `--loop plan_based_researcher.selector_loop:new_selector_event_loop`."
        )
