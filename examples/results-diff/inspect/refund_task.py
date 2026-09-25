"""A small deterministic Inspect task whose solver has two revisions.

The solver stands in for an agent; it does not call a model, so the logs
can be produced offline with `--model mockllm/model`.
"""

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes, match
from inspect_ai.solver import Generate, TaskState, solver

CASES = [
    ("refund-small", "Refund order 1001 for $12", "refund:1001:12"),
    ("refund-large", "Refund order 1002 for $900", "escalate:1002"),
    ("refund-duplicate", "Refund order 1003 again", "reject:1003"),
    ("status-open", "What is the status of order 1004?", "status:1004:open"),
    ("status-missing", "What is the status of order 9999?", "status:9999:unknown"),
    ("cancel-shipped", "Cancel order 1005", "reject:1005"),
    ("cancel-pending", "Cancel order 1006", "cancel:1006"),
    ("address-change", "Change the address on order 1007", "address:1007"),
]

ANSWERS = {
    "baseline": {
        "refund-small": "refund:1001:12",
        "refund-large": "refund:1002:900",
        "refund-duplicate": "reject:1003",
        "status-open": "status:1004:open",
        "status-missing": "status:9999:open",
        "cancel-shipped": "cancel:1005",
        "cancel-pending": "cancel:1006",
        "address-change": "address:1007",
    },
    "current": {
        "refund-small": "refund:1001:12",
        "refund-large": "escalate:1002",
        "refund-duplicate": "refund:1003:12",
        "status-open": "status:1004:open",
        "status-missing": "status:9999:unknown",
        "cancel-shipped": "reject:1005",
        "cancel-pending": "cancel:1006",
        "address-change": "address:1007",
    },
}


@solver
def scripted_agent(revision: str):
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        answer = ANSWERS[revision][state.sample_id]
        # The current revision appends a suffix on its second attempt at one
        # case, so an exact check becomes unreliable while `includes` holds.
        if revision == "current" and state.sample_id == "cancel-pending" and state.epoch == 2:
            answer += ":queued"
        state.output.completion = answer
        return state

    return solve


@task
def refund_policy(revision: str = "baseline"):
    return Task(
        dataset=[Sample(id=i, input=q, target=t) for i, q, t in CASES],
        solver=scripted_agent(revision),
        scorer=[match(location="exact"), includes()],
    )
