"""Known-good SQLite submission. Fault toggles are used only in grader audits."""

import json
import sqlite3
import sys

DURABLE = True
ATOMIC_BATCH = True
ENFORCE_CAS = True
TYPE_SENSITIVE = True
DELETE_ENABLED = True
VALIDATE_KEYS = True
ACK_ONLY = False
COMMIT_BEFORE_ACK = True

db = sqlite3.connect(sys.argv[1] if DURABLE else ":memory:")
db.execute("PRAGMA synchronous=FULL")
db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
db.commit()


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def valid(item, batch=False):
    if not isinstance(item, dict):
        return False
    op = item.get("op")
    if op not in (("put", "delete") if batch else ("put", "get", "delete", "cas")):
        return False
    if VALIDATE_KEYS and not isinstance(item.get("key"), str):
        return False
    if op in ("put", "cas") and "value" not in item:
        return False
    return op != "cas" or "expected" in item


def single(item):
    op, key = item["op"], item["key"]
    if op == "get":
        row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if row is None:
            return {"ok": True, "found": False}
        return {"ok": True, "found": True, "value": json.loads(row[0])}
    if op == "delete":
        if DELETE_ENABLED:
            db.execute("DELETE FROM kv WHERE key=?", (key,))
        return {"ok": True}
    if op == "cas":
        row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        matches = row is not None and (
            row[0] == encode(item["expected"])
            if TYPE_SENSITIVE
            else json.loads(row[0]) == item["expected"]
        )
        if ENFORCE_CAS and not matches:
            return {"ok": True, "swapped": False}
    db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, encode(item["value"])))
    return {"ok": True, "swapped": True} if op == "cas" else {"ok": True}


def handle(item):
    if ACK_ONLY:
        return {"ok": True}
    if isinstance(item, dict) and item.get("op") == "batch":
        ops = item.get("operations")
        if not isinstance(ops, list):
            return {"ok": False, "error": "invalid_request"}
        if ATOMIC_BATCH and not all(valid(x, batch=True) for x in ops):
            return {"ok": False, "error": "invalid_request"}
        for child in ops:
            if not valid(child, batch=True):
                return {"ok": False, "error": "invalid_request"}
            single(child)
        return {"ok": True}
    if not valid(item):
        return {"ok": False, "error": "invalid_request"}
    return single(item)


for line in sys.stdin:
    try:
        result = handle(json.loads(line))
        if COMMIT_BEFORE_ACK:
            db.commit()
    except (ValueError, TypeError, KeyError, sqlite3.Error):
        db.rollback()
        result = {"ok": False, "error": "invalid_request"}
    print(json.dumps(result, ensure_ascii=True, allow_nan=False), flush=True)
db.commit()
db.close()
