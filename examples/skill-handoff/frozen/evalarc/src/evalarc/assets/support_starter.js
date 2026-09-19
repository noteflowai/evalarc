// Replace this policy with an agent that executes the task's tool operations.
"use strict";
const readline = require("node:readline");

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", () => {
  process.stdout.write('{"finish":true,"message":"Not implemented."}\n');
});
