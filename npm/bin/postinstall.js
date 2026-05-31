#!/usr/bin/env node
// Friendly nudge that this is a wrapper around the Python package.
"use strict";
const { spawnSync } = require("child_process");

const py = process.platform === "win32" ? "py" : "python3";
const check = spawnSync(py, ["-c", "import seraphina, sys; print(seraphina.__version__ if hasattr(seraphina,'__version__') else 'ok')"], {
  encoding: "utf8",
});

if (check.status === 0) {
  console.log("[seraphina] Python package detected: " + (check.stdout || "").trim());
  console.log("[seraphina] Run:  seraphina");
} else {
  console.log("[seraphina] Node wrapper installed.");
  console.log("[seraphina] One more step - install the Python package:");
  console.log("    pip install seraphina-agi");
  console.log("[seraphina] Then run:  seraphina");
}
