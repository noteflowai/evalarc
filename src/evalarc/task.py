"""Public task generator and an in-memory behavioral oracle.

The reference submission uses SQLite. This oracle deliberately does not.
Seeds vary inputs, not the underlying task distribution or its exposure.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from typing import Any

TASK_ID = "durable-kv"
TASK_VERSION = "0.1.0"
DIMENSIONS = {
    "basic": 0.25,
    "validation": 0.15,
    "transactions": 0.20,
    "compare_swap": 0.15,
    "persistence": 0.15,
    "crash_recovery": 0.10,
}
INVALID = {"ok": False, "error": "invalid_request"}


def canonical(value: Any) -> str:
    """JSON equality is type-sensitive (not Python's True == 1)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def valid_write(request: Any) -> bool:
    return (
        isinstance(request, dict)
        and request.get("op") in ("put", "delete")
        and isinstance(request.get("key"), str)
        and (request["op"] == "delete" or "value" in request)
    )


def oracle(state: dict, request: Any) -> dict:
    if not isinstance(request, dict):
        return INVALID.copy()
    op = request.get("op")
    if op == "batch":
        ops = request.get("operations")
        if not isinstance(ops, list) or not all(valid_write(x) for x in ops):
            return INVALID.copy()
        for item in ops:
            oracle(state, item)
        return {"ok": True}
    if op not in ("put", "get", "delete", "cas") or not isinstance(request.get("key"), str):
        return INVALID.copy()
    key = request["key"]
    if op == "get":
        if key not in state:
            return {"ok": True, "found": False}
        return {"ok": True, "found": True, "value": copy.deepcopy(state[key])}
    if op == "delete":
        state.pop(key, None)
        return {"ok": True}
    if "value" not in request or (op == "cas" and "expected" not in request):
        return INVALID.copy()
    if op == "cas":
        matches = key in state and canonical(state[key]) == canonical(request["expected"])
        if matches:
            state[key] = copy.deepcopy(request["value"])
        return {"ok": True, "swapped": matches}
    state[key] = copy.deepcopy(request["value"])
    return {"ok": True}


@dataclass(frozen=True)
class Session:
    requests: list[Any]
    stop: str = "eof"


@dataclass(frozen=True)
class Case:
    id: str
    dimension: str
    sessions: list[Session]


def generate_cases(seed: int) -> list[Case]:
    rng = random.Random(seed)
    key = f"客户/{rng.getrandbits(64):016x}"
    second = f"second-{rng.getrandbits(64):016x}"
    value = {"version": rng.randrange(1, 10_000), "items": [True, None, "λ\n世界"]}
    put = {"op": "put", "key": key, "value": value}
    get = {"op": "get", "key": key}
    delete = {"op": "delete", "key": key}
    cases = [
        Case(
            "read-write-delete",
            "basic",
            [
                Session([get, put, get, delete, get, delete]),
            ],
        ),
        Case(
            "json-types-and-overwrite",
            "basic",
            [
                Session(
                    [
                        op
                        for val in [None, False, 0, "", [], {}, "a" * 4096, value]
                        for op in [{"op": "put", "key": key, "value": val}, get]
                    ]
                )
            ],
        ),
        Case(
            "reject-and-continue",
            "validation",
            [
                Session(
                    [
                        put,
                        None,
                        [],
                        {"op": "wat"},
                        {"op": "put", "key": 5, "value": "bad"},
                        {"op": "put", "key": key},
                        {"op": "cas", "key": key, "value": "bad"},
                        {"op": "get", "key": []},
                        {"op": "delete", "key": {}},
                        get,
                    ]
                )
            ],
        ),
        Case(
            "empty-and-unicode-keys",
            "validation",
            [
                Session(
                    [
                        {"op": "put", "key": "", "value": value},
                        {"op": "get", "key": ""},
                        put,
                        get,
                    ]
                )
            ],
        ),
        Case(
            "commit-batch",
            "transactions",
            [
                Session(
                    [
                        {
                            "op": "batch",
                            "operations": [
                                put,
                                {"op": "put", "key": second, "value": 17},
                                delete,
                            ],
                        },
                        get,
                        {"op": "get", "key": second},
                        {"op": "batch", "operations": []},
                    ]
                )
            ],
        ),
        Case(
            "rollback-batch",
            "transactions",
            [
                Session(
                    [
                        put,
                        {
                            "op": "batch",
                            "operations": [
                                {"op": "put", "key": key, "value": "must roll back"},
                                {"op": "put", "key": second},
                            ],
                        },
                        get,
                        {"op": "get", "key": second},
                        {"op": "batch", "operations": [delete, {"op": "batch", "operations": []}]},
                        get,
                        {"op": "batch", "operations": "invalid"},
                    ]
                )
            ],
        ),
        Case(
            "cas-match-and-mismatch",
            "compare_swap",
            [
                Session(
                    [
                        put,
                        {"op": "cas", "key": key, "expected": "wrong", "value": 12},
                        get,
                        {"op": "cas", "key": key, "expected": value, "value": 13},
                        get,
                        {"op": "cas", "key": second, "expected": None, "value": 10},
                        {"op": "get", "key": second},
                    ]
                )
            ],
        ),
        Case(
            "cas-type-sensitivity",
            "compare_swap",
            [
                Session(
                    [
                        {"op": "put", "key": key, "value": True},
                        {"op": "cas", "key": key, "expected": 1, "value": "incorrect"},
                        get,
                        {"op": "cas", "key": key, "expected": True, "value": None},
                        get,
                    ]
                )
            ],
        ),
        Case(
            "restart-preserves-acknowledged-write",
            "persistence",
            [
                Session([put]),
                Session([get, delete]),
                Session([get]),
            ],
        ),
        Case(
            "restart-preserves-transaction",
            "persistence",
            [
                Session(
                    [
                        {
                            "op": "batch",
                            "operations": [
                                put,
                                {"op": "put", "key": second, "value": value},
                            ],
                        }
                    ]
                ),
                Session([get, {"op": "get", "key": second}]),
            ],
        ),
        Case(
            "sigkill-after-acknowledgement",
            "crash_recovery",
            [
                Session([put], stop="kill"),
                Session([get]),
            ],
        ),
        Case(
            "sigkill-after-atomic-batch",
            "crash_recovery",
            [
                Session(
                    [
                        {
                            "op": "batch",
                            "operations": [
                                put,
                                {"op": "put", "key": second, "value": value},
                            ],
                        }
                    ],
                    stop="kill",
                ),
                Session([get, {"op": "get", "key": second}]),
            ],
        ),
    ]
    cases.extend(
        [
            Case(
                "restart-preserves-cas",
                "persistence",
                [
                    Session([put, {"op": "cas", "key": key, "expected": value, "value": 321}]),
                    Session([get]),
                ],
            ),
            Case(
                "sigkill-after-delete",
                "crash_recovery",
                [Session([put]), Session([delete], stop="kill"), Session([get])],
            ),
        ]
    )
    # A larger stateful sequence makes memorizing short public examples less useful.
    requests = []
    for _ in range(48):
        selected = rng.choice([key, second, "", "雪"])
        op = rng.choice(["put", "get", "delete"])
        request = {"op": op, "key": selected}
        if op == "put":
            request["value"] = rng.choice([None, True, rng.randrange(1000), value])
        requests.append(request)
    requests.extend({"op": "get", "key": k} for k in [key, second, "", "雪"])
    cases.append(Case("seeded-state-machine", "basic", [Session(requests)]))
    return cases
