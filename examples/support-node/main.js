// Independent JavaScript policy speaking the same bounded JSONL protocol.
// No SDK or Python bridge is used.
"use strict";
const readline = require("node:readline");
let task;
let lastAction;
let actions = [];

const call = (tool, arguments_) => ({ tool, arguments: arguments_ });

function decide(observation) {
  if (observation.type === "start") {
    task = observation.task;
    return call("get_ticket", { ticket_id: task.ticket_id });
  }
  const result = observation.result;
  if (!result.ok) {
    return result.error.retryable ? lastAction : { finish: true };
  }
  if (lastAction.tool === "get_ticket") {
    const ticket = result.ticket;
    actions = [
      call("assign_queue", {
        ticket_id: task.ticket_id,
        queue: task.routing_rules[ticket.category],
      }),
      call("add_note", {
        ticket_id: task.ticket_id,
        body: task.note,
        request_id: `review-${task.ticket_id}`,
      }),
    ];
    if (ticket.resolved) {
      actions.push(call("close_ticket", { ticket_id: task.ticket_id }));
    }
  }
  return actions.length ? actions.shift() : { finish: true };
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
  lastAction = decide(JSON.parse(line));
  process.stdout.write(JSON.stringify(lastAction) + "\n");
});
