"""Offline review of explicitly bounded AgentCore Evaluate exports and skill receipts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from evalarc.artifacts import new_run
from evalarc.records import numeric, read_bytes

INPUT_SCHEMA = "evalarc.trace-input.v1"
SCHEMA = "evalarc.trace-review.v1"
MAX_BYTES = 4 * 1024 * 1024
SCOPE = (
    "Imported evaluator judgments and caller-declared trace coverage. "
    "Identity and consistency checks do not authenticate the producer, rerun a judge, "
    "enforce permissions or independently verify task completion."
)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode()


def obj(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected an object")
    return value


def text(value: object, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label}: expected nonempty text (maximum {maximum} characters)")
    return value


def sha(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("expected a lowercase SHA-256")
    return value


def array(value: object, label: str, maximum: int = 200) -> list:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label}: expected an array of at most {maximum} entries")
    return value


def number(value: object) -> bool:
    return numeric(value)


def unique(values: list, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label}: duplicate identity")


def decode(content: bytes, limit: int = MAX_BYTES) -> dict:
    if len(content) > limit:
        raise ValueError(f"trace JSON exceeds {limit} bytes")

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(content, object_pairs_hook=pairs)
        canonical(value)  # Reject NaN/infinity, including those in preserved opaque payloads.
        json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError("invalid UTF-8 JSON or excessive nesting") from error
    return obj(value, "trace input")


def attributes(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    result = {}
    for row in array(raw, "span attributes", 512):
        row = obj(row, "attribute")
        key = text(row.get("key"), "attribute key")
        if key in result:
            raise ValueError("duplicate span attribute")
        value = obj(row.get("value"), "typed attribute")
        result[key] = value.get("stringValue")
    return result


def evaluator_specs(raw: object) -> list[dict]:
    specs = array(raw, "evaluators", 32)
    if not specs:
        raise ValueError("declare at least one evaluator")
    for spec in specs:
        obj(spec, "evaluator")
        text(spec.get("id"), "evaluator id")
        text(spec.get("revision"), "evaluator revision")
        if spec.get("level") not in ("session", "trace", "skill"):
            raise ValueError("evaluator level must be session, trace or skill")
        rating = obj(spec.get("rating"), "rating")
        if rating.get("kind") == "numeric":
            values = [rating.get(k) for k in ("min", "pass_at_least", "max")]
            if not all(number(v) for v in values) or not values[0] <= values[1] <= values[2]:
                raise ValueError("numeric scale requires min <= pass_at_least <= max")
            if values[0] == values[2]:
                raise ValueError("numeric scale needs a nonzero range")
        elif rating.get("kind") == "categorical":
            labels = array(rating.get("labels"), "rating labels", 32)
            passes = array(rating.get("pass_labels"), "passing labels", 32)
            for label in labels + passes:
                text(label, "rating label", 128)
            unique(labels, "rating labels")
            unique(passes, "passing labels")
            if not labels or not passes or not set(passes) <= set(labels):
                raise ValueError("passing labels must be a nonempty subset of the scale")
        else:
            raise ValueError("rating kind must be numeric or categorical")
    unique([spec["id"] for spec in specs], "evaluators")
    if not any(spec["level"] == "session" for spec in specs):
        raise ValueError("declare a session evaluator for every golden case")
    return specs


def score(raw: dict, spec: dict) -> dict:
    value, label = raw.get("value"), raw.get("label")
    error = raw.get("errorCode")
    for field in ("label", "explanation", "errorCode", "errorMessage"):
        if field in raw and not isinstance(raw[field], str):
            raise ValueError(f"result {field} must be text")
    if value is not None and not number(value):
        raise ValueError("result value must be a finite number, never a boolean")
    if error:
        status = "skipped" if error.casefold() == "skipped" else "error"
    elif label and label.casefold() == "skipped" and label not in spec["rating"].get("labels", []):
        status = "skipped"
    elif value is None and label is None:
        status = "unassessed"
    else:
        status = "assessed"
    accepted = None
    if status == "assessed":
        rating = spec["rating"]
        if rating["kind"] == "numeric":
            if value is None:
                status = "unassessed"
            elif not rating["min"] <= value <= rating["max"]:
                raise ValueError("result is outside the declared numeric scale")
            else:
                accepted = value >= rating["pass_at_least"]
        else:
            if value is not None:
                raise ValueError("categorical result cannot contain a numeric value")
            if label not in rating["labels"]:
                raise ValueError("result label is outside the declared categorical scale")
            accepted = label in rating["pass_labels"]
    return {
        "status": status,
        "value": value if status == "assessed" else None,
        "label": label,
        "accepted": accepted,
        "explanation": raw.get("explanation", ""),
        "error": raw.get("errorMessage", error),
    }


def receipt(raw: object, name: str) -> dict | None:
    if raw is None:
        return None
    row = obj(raw, "skill receipt")
    if row.get("schema") != "skills-anywhere-load-1" or row.get("name") != name:
        raise ValueError("skill receipt schema or name mismatch")
    if row.get("provider") != "dsh-skills-anywhere" or row.get("permissions_enforced") is not False:
        raise ValueError("unsupported receipt provider or permission claim")
    for key in ("load_id", "loaded_at", "provider_version"):
        text(row.get(key), f"receipt {key}")
    for key in ("skill_sha256", "content_sha256"):
        sha(row.get(key))
    if row.get("bundle_sha256") is not None:
        sha(row["bundle_sha256"])
    if row.get("declared_tools") is not None:
        for tool in array(row["declared_tools"], "declared tools", 128):
            text(tool, "declared tool")
    return row


def review(content: bytes) -> dict:
    data = decode(content)
    if data.get("schema_version") != INPUT_SCHEMA:
        raise ValueError(f"expected {INPUT_SCHEMA}")
    provenance = obj(data.get("provenance"), "provenance")
    if provenance.get("kind") not in ("synthetic", "recorded"):
        raise ValueError("provenance kind must be synthetic or recorded")
    text(provenance.get("description"), "provenance description")
    text(data.get("run_id"), "run id")
    dataset = obj(data.get("dataset"), "dataset")
    text(dataset.get("id"), "dataset id")
    text(dataset.get("version"), "dataset version")
    golden = array(dataset.get("cases"), "golden cases")
    if not golden:
        raise ValueError("golden set cannot be empty")
    for case in golden:
        obj(case, "golden case")
        text(case.get("id"), "case id")
        text(case.get("goal"), "case goal")
        names = array(case.get("expected_skills"), "expected skills", 32)
        for name in names:
            text(name, "expected skill", 128)
        unique(names, "expected skills")
    unique([case["id"] for case in golden], "golden cases")
    config = obj(data.get("configuration"), "configuration")
    text(config.get("model"), "model identity")
    obj(config.get("model_parameters"), "model parameters")
    sha(config.get("prompt_sha256"))
    sha(config.get("tools_sha256"))
    pins = obj(config.get("skills"), "reviewed skill bundles")
    for name, pin in pins.items():
        text(name, "skill name", 128)
        if pin is not None:
            sha(pin)
    specs = evaluator_specs(data.get("evaluators"))
    runs = array(data.get("cases"), "case runs")
    if [row.get("case_id") for row in runs if isinstance(row, dict)] != [
        row["id"] for row in golden
    ]:
        raise ValueError("case runs must exactly match golden case order and inventory")
    sessions, traces, loads = set(), set(), set()
    output = []
    for definition, case in zip(golden, runs, strict=True):
        sid = text(case.get("session_id"), "session id")
        if sid in sessions:
            raise ValueError("a session cannot belong to two golden cases")
        sessions.add(sid)
        tids = array(case.get("trace_ids"), "trace ids", 64)
        for tid in tids:
            text(tid, "trace id", 128)
            if tid in traces:
                raise ValueError("trace IDs must be globally unique within a run")
            traces.add(tid)
        if not tids:
            raise ValueError("every case must declare at least one trace")
        spans = {}
        for span in array(case.get("spans"), "spans", 512):
            obj(span, "span")
            tid = text(span.get("traceId"), "span traceId", 128)
            spid = text(span.get("spanId"), "span spanId", 128)
            if tid not in tids or (tid, spid) in spans:
                raise ValueError("span outside the case or duplicate span identity")
            attrs = attributes(span.get("attributes", {}))
            if "session.id" in attrs and attrs["session.id"] != sid:
                raise ValueError("span session differs from the declared case")
            spans[tid, spid] = span
        if {key[0] for key in spans} != set(tids):
            raise ValueError("each declared trace must have at least one exported span")
        complete = case.get("skill_observation_complete")
        if type(complete) is not bool:
            raise ValueError("declare skill_observation_complete as a boolean")
        calls = []
        for call in array(case.get("skill_calls"), "skill calls", 128):
            obj(call, "skill call")
            key = (call.get("trace_id"), call.get("span_id"))
            if key not in spans:
                raise ValueError("skill call has no matching exported span")
            name = text(call.get("name"), "skill name", 128)
            loaded = receipt(call.get("receipt"), name)
            if loaded:
                if loaded["load_id"] in loads:
                    raise ValueError("a skill load receipt cannot be reused")
                loads.add(loaded["load_id"])
            expected = pins.get(name)
            observed = loaded["bundle_sha256"] if loaded else None
            identity = (
                "unknown"
                if expected is None or observed is None
                else ("matched" if expected == observed else "changed")
            )
            calls.append({**call, "receipt": loaded, "identity": identity})
        unique([(c["trace_id"], c["span_id"]) for c in calls], "skill call spans")
        call_keys = {(c["trace_id"], c["span_id"]) for c in calls}
        response = obj(case.get("evaluation_response"), "evaluation response")
        results = array(response.get("evaluationResults"), "evaluationResults", 1024)
        found = {}
        by_id = {spec["id"]: spec for spec in specs}
        for raw in results:
            obj(raw, "evaluation result")
            spec = by_id.get(raw.get("evaluatorId"))
            if spec is None:
                raise ValueError("result uses an undeclared evaluator")
            ctx = obj(obj(raw.get("context"), "context").get("spanContext"), "span context")
            rsid, tid, spid = ctx.get("sessionId"), ctx.get("traceId"), ctx.get("spanId")
            if rsid != sid:
                raise ValueError("evaluation result session differs from its case")
            level = spec["level"]
            if level == "session" and (tid is not None or spid is not None):
                raise ValueError("session evaluator must target the session only")
            if level == "trace" and (tid not in tids or spid is not None):
                raise ValueError("trace evaluator must target a declared trace only")
            if level == "skill" and (tid, spid) not in call_keys:
                raise ValueError("skill evaluator must target an annotated skill span")
            key = (spec["id"], tid, spid)
            if key in found:
                raise ValueError(
                    "duplicate evaluator target; keep judge repetitions in separate runs"
                )
            found[key] = score(raw, spec)
        rows = []
        for spec in specs:
            targets = (
                [(None, None)]
                if spec["level"] == "session"
                else [(tid, None) for tid in tids]
                if spec["level"] == "trace"
                else [(c["trace_id"], c["span_id"]) for c in calls]
            )
            if not targets:
                rows.append(
                    {
                        "evaluator": spec["id"],
                        "revision": spec["revision"],
                        "trace_id": None,
                        "span_id": None,
                        "status": "not_applicable" if complete else "missing",
                        "value": None,
                        "label": None,
                        "accepted": None,
                        "explanation": "No annotated skill calls; coverage is caller-declared.",
                        "error": None,
                    }
                )
            for tid, spid in targets:
                result = found.get(
                    (spec["id"], tid, spid),
                    {
                        "status": "missing",
                        "value": None,
                        "label": None,
                        "accepted": None,
                        "explanation": "No result for this declared target.",
                        "error": None,
                    },
                )
                rows.append(
                    {
                        "evaluator": spec["id"],
                        "revision": spec["revision"],
                        "trace_id": tid,
                        "span_id": spid,
                        **result,
                    }
                )
        skills = []
        for name in definition["expected_skills"]:
            matching = [call for call in calls if call["name"] == name]
            state = (
                "not_called"
                if not matching and complete
                else "unknown"
                if not matching
                else "changed"
                if any(c["identity"] == "changed" for c in matching)
                else "unknown"
                if any(c["identity"] == "unknown" for c in matching)
                else "matched"
            )
            skills.append({"name": name, "status": state})
        incomplete = any(
            row["status"] not in ("assessed", "not_applicable") for row in rows
        ) or any(row["status"] == "unknown" for row in skills)
        if not complete and (skills or any(spec["level"] == "skill" for spec in specs)):
            incomplete = True
        rejected = (
            any(row["accepted"] is False for row in rows)
            or any(row["status"] in ("not_called", "changed") for row in skills)
            or any(call["identity"] == "changed" for call in calls)
        )
        output.append(
            {
                "case_id": definition["id"],
                "goal": definition["goal"],
                "session_id": sid,
                "trace_ids": tids,
                "span_count": len(spans),
                "skill_observation_complete": complete,
                "skill_calls": calls,
                "expected_skills": skills,
                "results": rows,
                "gate": "incomplete" if incomplete else "rejected" if rejected else "accepted",
                "has_rejection": rejected,
            }
        )
    counts = {
        state: sum(c["gate"] == state for c in output)
        for state in ("accepted", "rejected", "incomplete")
    }
    return {
        "schema_version": SCHEMA,
        "source_sha256": digest(content),
        "source_bytes": len(content),
        "run_id": data["run_id"],
        "provenance": provenance,
        "dataset": dataset,
        "dataset_sha256": digest(canonical(dataset)),
        "configuration": config,
        "evaluators": specs,
        "cases": output,
        "summary": counts,
        "scope": SCOPE,
    }


def compare_reviews(baseline: dict, current: dict) -> dict:
    for field in ("dataset", "evaluators"):
        if canonical(baseline[field]) != canonical(current[field]):
            raise ValueError(f"comparison requires the same {field}, including versions and rules")
    if baseline["provenance"]["kind"] != current["provenance"]["kind"]:
        raise ValueError("cannot compare synthetic and recorded runs")
    if baseline["source_sha256"] == current["source_sha256"]:
        raise ValueError("choose two different run records")
    differences = {}
    for key in sorted(set(baseline["configuration"]) | set(current["configuration"])):
        before, after = baseline["configuration"].get(key), current["configuration"].get(key)
        if canonical(before) != canonical(after):
            differences[key] = {"baseline": before, "current": after}
    return {
        "baseline_source_sha256": baseline["source_sha256"],
        "configuration_changes": differences,
        "cases": [
            {
                "case_id": old["case_id"],
                "baseline": old["gate"],
                "current": new["gate"],
                "regressed": old["gate"] == "accepted" and new["gate"] != "accepted",
            }
            for old, new in zip(baseline["cases"], current["cases"], strict=True)
        ],
        "interpretation": "Paired descriptive comparison; no causal or statistical gain claim.",
    }


def import_trace(source: Path, output: Path, baseline: Path | None = None) -> dict:
    content = read_bytes(source, limit=MAX_BYTES)
    record = review(content)
    before = read_bytes(baseline, limit=MAX_BYTES) if baseline else None
    if before is not None:
        record["comparison"] = compare_reviews(review(before), record)
    from evalarc.trace_report import render

    with new_run(output) as folder:
        (folder / "input.json").write_bytes(content)
        if before is not None:
            (folder / "baseline-input.json").write_bytes(before)
        (folder / "review.json").write_bytes(canonical(record) + b"\n")
        render(record, folder / "index.html")
    return record


def verify_trace(folder: Path) -> dict:
    if any(p.is_symlink() for p in (folder, *folder.parents)):
        raise ValueError("trace evidence path must not contain symlinks")
    recorded = decode(read_bytes(folder / "review.json", limit=MAX_BYTES * 2), MAX_BYTES * 2)
    current = review(read_bytes(folder / "input.json", limit=MAX_BYTES))
    if "comparison" in recorded:
        before = review(read_bytes(folder / "baseline-input.json", limit=MAX_BYTES))
        current["comparison"] = compare_reviews(before, current)
    if canonical(recorded) != canonical(current):
        raise ValueError("trace review differs from its original input evidence")
    return {
        "verified": True,
        "source_sha256": current["source_sha256"],
        "summary": current["summary"],
        "scope": SCOPE + " HTML is not verified.",
    }
