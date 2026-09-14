// Scripted policy, independent of the host verifier. Audit toggles default off.
"use strict";
const readline = require("node:readline");

const ACK_ONLY = false;
const WRONG_TICKET = false;
const WRONG_QUEUE = false;
const DUPLICATE_NOTE = false;
const CLOSE_OPEN = false;
const SKIP_RETRY = false;
const NEW_RETRY_KEY = false;

let task;
let ticketId;
let lastAction;
let pending = [];
const call = (tool, arguments_) => ({ tool, arguments: arguments_ });

function decide(observation) {
  if (ACK_ONLY) return { finish: true, message: "Completed all requested work." };
  if (observation.type === "start") {
    task = observation.task;
    ticketId = WRONG_TICKET
      ? task.ticket_ids.find((id) => id !== task.ticket_id)
      : task.ticket_id;
    return call("get_ticket", { ticket_id: ticketId });
  }
  const result = observation.result;
  if (!result.ok) {
    if (result.error.retryable && !SKIP_RETRY) {
      const retry = structuredClone(lastAction);
      if (NEW_RETRY_KEY && retry.tool === "add_note") {
        retry.arguments.request_id += "-retry";
      }
      return retry;
    }
    return { finish: true, message: "Could not complete the operation." };
  }
  if (lastAction.tool === "get_ticket") {
    const ticket = result.ticket;
    let queue = task.routing_rules[ticket.category];
    if (WRONG_QUEUE) queue = Object.values(task.routing_rules).find((value) => value !== queue);
    pending = [
      call("assign_queue", { ticket_id: ticketId, queue }),
      call("add_note", { ticket_id: ticketId, body: task.note, request_id: "review" }),
    ];
    if (DUPLICATE_NOTE) {
      pending.push(call("add_note", {
        ticket_id: ticketId, body: task.note, request_id: "duplicate",
      }));
    }
    if (ticket.resolved || CLOSE_OPEN) {
      pending.push(call("close_ticket", { ticket_id: ticketId }));
    }
  }
  return pending.length ? pending.shift() : { finish: true };
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
  lastAction = decide(JSON.parse(line));
  process.stdout.write(JSON.stringify(lastAction) + "\n");
});
