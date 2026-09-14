// Independent durable-kv control: JSON snapshots, no Python or grader imports.
// Single process, sequential requests; fault toggles are for grader audits only.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const DURABLE = true;
const ATOMIC_BATCH = true;
const ENFORCE_CAS = true;
const TYPE_SENSITIVE = true;
const DELETE_ENABLED = true;
const VALIDATE_KEYS = true;
const ACK_ONLY = false;
const COMMIT_BEFORE_ACK = true;

if (
  typeof JSON.rawJSON !== "function" ||
  JSON.parse("1", (_key, _value, context) => context?.source) !== "1"
) {
  throw new Error("This reference requires Node.js 22+ with JSON source text access.");
}
if (!process.argv[2]) throw new Error("Usage: node main.js STATE_FILE");
const stateFile = path.resolve(process.argv[2]);

// Ordinary JSON.parse loses large integers and the distinction between 1 and
// 1.0. Keep numeric source text through requests, snapshots, and responses.
class JsonNumber {
  constructor(source) {
    this.source = source;
    this.decimal = /[.eE]/.test(source);
    this.value = this.decimal ? Number(source) : BigInt(source);
    if (this.decimal && !Number.isFinite(this.value)) {
      throw new SyntaxError("Only finite JSON numbers are supported.");
    }
  }
  toJSON() {
    return JSON.rawJSON(this.source);
  }
}

function parse(text) {
  return JSON.parse(text, (_key, value, context) =>
    typeof value === "number" ? new JsonNumber(context.source) : value
  );
}

function object(value) {
  return value !== null && typeof value === "object" &&
    !Array.isArray(value) && !(value instanceof JsonNumber);
}

function equal(left, right) {
  if (!TYPE_SENSITIVE) {
    const scalar = (value) => value instanceof JsonNumber ? Number(value.value) : value;
    if (
      (left instanceof JsonNumber || typeof left === "boolean") &&
      (right instanceof JsonNumber || typeof right === "boolean")
    ) return Number(scalar(left)) === Number(scalar(right));
  }
  if (left instanceof JsonNumber || right instanceof JsonNumber) {
    return left instanceof JsonNumber && right instanceof JsonNumber &&
      left.decimal === right.decimal && Object.is(left.value, right.value);
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length &&
      left.every((value, index) => equal(value, right[index]));
  }
  if (object(left) || object(right)) {
    return object(left) && object(right) &&
      Object.keys(left).length === Object.keys(right).length &&
      Object.keys(left).every((key) => Object.hasOwn(right, key) && equal(left[key], right[key]));
  }
  return left === right;
}

function load() {
  if (!DURABLE) return new Map();
  let text;
  try {
    text = fs.readFileSync(stateFile, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return new Map();
    throw error;
  }
  const entries = parse(text);
  if (
    !Array.isArray(entries) ||
    !entries.every((entry) => Array.isArray(entry) && entry.length === 2 &&
      typeof entry[0] === "string") ||
    new Set(entries.map(([key]) => key)).size !== entries.length
  ) throw new Error("Invalid state snapshot.");
  return new Map(entries);
}

let state = load();

function persist(next) {
  if (!DURABLE) return;
  const temporary = stateFile + ".pending";
  const fd = fs.openSync(temporary, "w", 0o600);
  try {
    fs.writeFileSync(fd, JSON.stringify([...next]), "utf8");
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(temporary, stateFile);
  const directory = fs.openSync(path.dirname(stateFile), "r");
  try {
    fs.fsyncSync(directory);
  } finally {
    fs.closeSync(directory);
  }
}

function commit(next) {
  if (COMMIT_BEFORE_ACK) persist(next);
  state = next;
}

function valid(item, batch = false) {
  return object(item) &&
    (batch ? ["put", "delete"] : ["put", "get", "delete", "cas"]).includes(item.op) &&
    Object.hasOwn(item, "key") && (!VALIDATE_KEYS || typeof item.key === "string") &&
    (!["put", "cas"].includes(item.op) || Object.hasOwn(item, "value")) &&
    (item.op !== "cas" || Object.hasOwn(item, "expected"));
}

function single(item, next) {
  const { op, key } = item;
  if (op === "get") {
    return next.has(key)
      ? { ok: true, found: true, value: next.get(key) }
      : { ok: true, found: false };
  }
  if (op === "delete") {
    if (DELETE_ENABLED) next.delete(key);
    return { ok: true };
  }
  if (op === "cas" && ENFORCE_CAS &&
      !(next.has(key) && equal(next.get(key), item.expected))) {
    return { ok: true, swapped: false };
  }
  next.set(key, item.value);
  return op === "cas" ? { ok: true, swapped: true } : { ok: true };
}

const invalid = () => ({ ok: false, error: "invalid_request" });

function handle(item) {
  if (ACK_ONLY) return { ok: true };
  if (object(item) && item.op === "batch") {
    const operations = item.operations;
    if (!Array.isArray(operations) ||
        (ATOMIC_BATCH && !operations.every((child) => valid(child, true)))) return invalid();
    const next = new Map(state);
    for (const child of operations) {
      if (!valid(child, true)) {
        // Deliberately faulty partial commit when ATOMIC_BATCH is disabled.
        commit(next);
        return invalid();
      }
      single(child, next);
    }
    commit(next);
    return { ok: true };
  }
  if (!valid(item)) return invalid();
  if (item.op === "get") return single(item, state);
  const next = new Map(state);
  const response = single(item, next);
  commit(next);
  return response;
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
  let item;
  try {
    item = parse(line);
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    process.stdout.write(JSON.stringify(invalid()) + "\n");
    return;
  }
  // Storage errors terminate the process. Never acknowledge a failed write.
  process.stdout.write(JSON.stringify(handle(item)) + "\n");
});
input.on("close", () => {
  if (!COMMIT_BEFORE_ACK) persist(state);
});
