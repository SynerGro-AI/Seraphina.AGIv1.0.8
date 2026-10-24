"""Shared helpers for the test suite (no mocks: real processes, real files)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run_cli(args, home, cwd=None, module="seraphina.cli", input_text=None):
    """Run `python -m <module> <args>` in a subprocess with an isolated
    SERAPHINA_HOME. API-key env vars are removed so nothing can reach xAI."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("SERAPHINA_GROK_API_KEY", "XAI_API_KEY")}
    env["SERAPHINA_HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=str(cwd or home), env=env, input=input_text,
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


class TempDirMixin:
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()
