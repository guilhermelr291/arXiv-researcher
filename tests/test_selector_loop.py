"""Windows ProactorEventLoop is incompatible with psycopg async (API boot)."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path

from plan_based_researcher.selector_loop import (
    new_selector_event_loop,
    require_psycopg_compatible_loop,
)

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_MOD = _ROOT / "src" / "plan_based_researcher" / "__main__.py"


class SelectorLoopTest(unittest.TestCase):
    def test_factory_is_not_proactor(self) -> None:
        loop = new_selector_event_loop()
        try:
            if sys.platform == "win32":
                self.assertIsInstance(loop, asyncio.SelectorEventLoop)
                self.assertNotIsInstance(loop, asyncio.ProactorEventLoop)
        finally:
            loop.close()

    def test_require_passes_on_selector_loop(self) -> None:
        async def _inner() -> None:
            require_psycopg_compatible_loop()

        asyncio.run(_inner(), loop_factory=new_selector_event_loop)

    @unittest.skipUnless(sys.platform == "win32", "ProactorEventLoop is Windows-only")
    def test_require_raises_on_proactor_loop(self) -> None:
        async def _inner() -> None:
            with self.assertRaises(RuntimeError) as ctx:
                require_psycopg_compatible_loop()
            self.assertIn("python -m plan_based_researcher", str(ctx.exception))

        asyncio.run(_inner(), loop_factory=asyncio.ProactorEventLoop)

    def test_cli_entry_passes_selector_factory_to_uvicorn(self) -> None:
        source = _MAIN_MOD.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn(
            "plan_based_researcher.selector_loop:new_selector_event_loop",
            source,
        )


if __name__ == "__main__":
    unittest.main()
