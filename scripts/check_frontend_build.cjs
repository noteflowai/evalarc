// The report enhancement script is written in TypeScript (frontend/) and compiled to
// src/evalarc/assets/report_enhance.js, which is committed so `pip install evalarc`
// never needs Node. Fail when the committed file differs from a fresh compile.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const committed = path.join(root, "src/evalarc/assets/report_enhance.js");
const out = fs.mkdtempSync(path.join(os.tmpdir(), "evalarc-frontend-"));
try {
  const tsc = path.join(root, "node_modules/.bin", process.platform === "win32" ? "tsc.cmd" : "tsc");
  execFileSync(tsc, ["-p", path.join(root, "frontend/tsconfig.json"), "--outDir", out],
    { stdio: "inherit" });
  const fresh = fs.readFileSync(path.join(out, "report_enhance.js"), "utf8");
  assert.equal(fs.readFileSync(committed, "utf8"), fresh,
    "src/evalarc/assets/report_enhance.js is stale; run `npm run build:frontend` and commit it");
  assert(!/^\s*(import|export)\s/m.test(fresh), "the compiled script must stay a classic script");
  console.log("Compiled frontend matches the committed asset.");
} finally {
  fs.rmSync(out, { recursive: true, force: true });
}
