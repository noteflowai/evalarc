"""Scripted ticket policy; deliberately independent of the host verifier."""

import json
import sys

ACK_ONLY = False
WRONG_TICKET = False
WRONG_QUEUE = False
DUPLICATE_NOTE = False
CLOSE_OPEN = False
SKIP_RETRY = False
NEW_RETRY_KEY = False

task = None
ticket_id = None
pending = []
last_action = None


def call(tool, **arguments):
    return {"tool": tool, "arguments": arguments}


def decide(observation):
    global task, ticket_id, pending
    if ACK_ONLY:
        return {"finish": True, "message": "Completed all requested work."}
    if observation["type"] == "start":
        task = observation["task"]
        ticket_id = task["ticket_id"]
        if WRONG_TICKET:
            ticket_id = next(key for key in task["ticket_ids"] if key != ticket_id)
        return call("get_ticket", ticket_id=ticket_id)
    result = observation["result"]
    if not result["ok"]:
        if result["error"]["retryable"] and not SKIP_RETRY:
            retry = json.loads(json.dumps(last_action))
            if NEW_RETRY_KEY and retry["tool"] == "add_note":
                retry["arguments"]["request_id"] += "-retry"
            return retry
        return {"finish": True, "message": "Could not complete the operation."}
    if last_action["tool"] == "get_ticket":
        ticket = result["ticket"]
        queue = task["routing_rules"][ticket["category"]]
        if WRONG_QUEUE:
            queue = next(value for value in task["routing_rules"].values() if value != queue)
        pending = [
            call("assign_queue", ticket_id=ticket_id, queue=queue),
            call("add_note", ticket_id=ticket_id, body=task["note"], request_id="review"),
        ]
        if DUPLICATE_NOTE:
            pending.append(
                call("add_note", ticket_id=ticket_id, body=task["note"], request_id="duplicate")
            )
        if ticket["resolved"] or CLOSE_OPEN:
            pending.append(call("close_ticket", ticket_id=ticket_id))
    return pending.pop(0) if pending else {"finish": True}


for line in sys.stdin:
    last_action = decide(json.loads(line))
    print(json.dumps(last_action), flush=True)
