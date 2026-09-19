// Implement the durable-kv contract from TASK.md. Node.js 22+.
"use strict";
const readline = require("node:readline");

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", () => {
  process.stdout.write('{"ok":false,"error":"not_implemented"}\n');
});
