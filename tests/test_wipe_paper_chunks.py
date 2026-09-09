"""VOY-04: wipe_paper_chunks.py refuses without --yes and does not touch the DB."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "wipe_paper_chunks.py"


def _load_wipe_module():
    spec = importlib.util.spec_from_file_location("wipe_paper_chunks", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WipePaperChunksRefuseTest(unittest.TestCase):
    def test_subprocess_without_yes_exits_2_and_mentions_yes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=_ROOT,
        )
        self.assertEqual(result.returncode, 2)
        stderr = result.stderr.lower()
        self.assertTrue("--yes" in stderr or "refus" in stderr)

    def test_main_without_yes_does_not_call_settings_or_connect(self) -> None:
        module = _load_wipe_module()
        with (
            patch.object(sys, "argv", ["wipe_paper_chunks.py"]),
            patch.object(sys, "stderr", StringIO()),
            patch.object(module, "Settings") as settings_cls,
            patch.object(module.AsyncConnection, "connect") as connect,
        ):
            with self.assertRaises(SystemExit) as ctx:
                module.main()
            self.assertEqual(ctx.exception.code, 2)
            settings_cls.assert_not_called()
            connect.assert_not_called()
