#!/usr/bin/env node
// Thin wrapper: forwards all argv to the Python `seraphina` CLI.
// Requires Python 3.9+ and `pip install seraphina-agi` in the same env.

"use strict";
const { spawn } = require("child_process");

function pickPython() {
  if (process.env.SERAPHINA_PYTHON) return process.env.SERAPHINA_PYTHON;
  return process.platform === "win32" ? "py" : "python3";
}

function tryRun(cmd, args) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { stdio: "inherit" });
    child.on("error", () => resolve({ ok: false, code: 127 }));
    child.on("exit", (code) => resolve({ ok: true, code: code == null ? 0 : code }));
  });
}

(async () => {
  const args = process.argv.slice(2);
  const py = pickPython();

  // Prefer `<python> -m seraphina <args>` so we don't depend on PATH for the
  // entry-point shim.
  let result = await tryRun(py, ["-m", "seraphina", ...args]);
  if (!result.ok && py === "py") {
    result = await tryRun("python", ["-m", "seraphina", ...args]);
  }
  if (!result.ok) {
    console.error(
      "[seraphina] Python interpreter not found. Install Python 3.9+ and run:\n" +
      "  pip install seraphina-agi"
    );
    process.exit(127);
  }
  process.exit(result.code);
})();
