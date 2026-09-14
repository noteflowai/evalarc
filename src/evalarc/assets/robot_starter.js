// Implement the recording-review contract described in TASK.md.
const readline = require("node:readline");

function review(request) {
  throw new Error("Convert recorded observations and return the requested facts");
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on("line", (line) => {
  process.stdout.write(JSON.stringify({ ok: true, report: review(JSON.parse(line)) }) + "\n");
});
