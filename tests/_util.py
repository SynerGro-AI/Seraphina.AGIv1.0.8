"""Shared helpers for the test suite (no mocks: real processes, real files)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run_cli(args, home, cwd=None, module="seraphina.cli", input_text=None,
            extra_env=None):
    """Run `python -m <module> <args>` in a subprocess with an isolated
    SERAPHINA_HOME. API-key env vars are removed so nothing can reach xAI;
    *extra_env* is applied last (tests point plan-grok at a local server)."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("SERAPHINA_GROK_API_KEY", "XAI_API_KEY",
                        "SERAPHINA_GROK_ENDPOINT", "SERAPHINA_GROK_RATE")}
    env["SERAPHINA_HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=str(cwd or home), env=env, input=input_text,
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        check=False,  # callers assert the exit code themselves
    )


class TempDirMixin:
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()


def require_tool(test, name):
    """Return the path of executable *name*, or skip *test* with the reason.
    With SERAPHINA_REQUIRE_ALL_TESTS=1 (CI) a missing tool is a failure, so
    a test can never pass by not running."""
    import shutil
    path = shutil.which(name)
    if path:
        return path
    msg = f"{name} not found on PATH; this test needs it to run for real"
    if os.environ.get("SERAPHINA_REQUIRE_ALL_TESTS") == "1":
        test.fail(msg)
    test.skipTest(msg)
