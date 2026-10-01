"""Start an evaluation project and review its inputs before running anything.

``eval-init`` writes a runnable project (cases, application stub, programmatic grader,
evaluation runner writing Inspect-format logs, hillclimb configuration) wired to every
EvalArc command. ``review-inputs`` renders the cases for a person to read before any
run, checks the declared sources, and derives the held-out split and case manifest
from ``cases.jsonl``, so the case file stays the single source of truth.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from evalarc import provenance
from evalarc.artifacts import new_run
from evalarc.templates import asset

CASE_FIELDS = {"id", "input", "expected", "check", "source", "labels", "difficulty", "held_out"}
CHECKS = ("exact", "contains", "label", "json_keys")
MAX_CASES_BYTES = 16 * 1024 * 1024
MAX_CASES = 10_000
SCHEMA = "evalarc.input-review.v1"

EXAMPLE_PROMPT = """# Ticket routing

Route the ticket to one queue: billing, oncall, accounts or general.

- refund -> billing
- invoice -> billing
"""
EXAMPLE_CASES = [
    {
        "id": "refund-double",
        "input": "I was charged twice for order 4471",
        "expected": "billing",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "support_ticket",
    },
    {
        "id": "refund-return",
        "input": "Please refund the lamp I sent back",
        "expected": "billing",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "support_ticket",
    },
    {
        "id": "invoice-blank",
        "input": "My invoice PDF is blank",
        "expected": "billing",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "bug_report",
    },
    {
        "id": "outage-dashboard",
        "input": "The dashboard is down since noon",
        "expected": "oncall",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "production",
    },
    {
        "id": "password-reset",
        "input": "The password reset link never arrives",
        "expected": "accounts",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "production",
        "difficulty": "mentions email delivery, which looks like an outage but is an account issue",
    },
    {
        "id": "hours",
        "input": "What are your opening hours?",
        "expected": "general",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "manual",
    },
    {
        "id": "holdout-refund",
        "input": "Refund the duplicate subscription charge",
        "expected": "billing",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "support_ticket",
        "held_out": True,
    },
    {
        "id": "holdout-outage",
        "input": "Webhooks stopped firing an hour ago",
        "expected": "oncall",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "production",
        "held_out": True,
    },
    {
        "id": "holdout-shipping",
        "input": "Do you ship to Norway?",
        "expected": "general",
        "check": "label",
        "labels": ["billing", "oncall", "accounts", "general"],
        "source": "synthetic",
        "held_out": True,
    },
]
HILLCLIMB_TOML = """# evalarc hillclimb-run hillclimb.toml --output ../climb --trust-local
workspace = "."
allow = ["prompt.md"]
held_out = "split.json"
evaluate = ["{python}", "evaluate.py", "{output}", "--epochs", "3"]
propose = ["{python}", "propose.py", "{failures}"]
objective = "quality"
max_iterations = 5
stall_after = 2
timeout_seconds = 600
"""


def load_cases(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if len(raw) > MAX_CASES_BYTES:
        raise ValueError(f"{path.name} exceeds {MAX_CASES_BYTES} bytes")
    cases, seen = [], set()
    for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name}:{number}"
        try:
            case = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{where} is not JSON: {error}") from None
        if not isinstance(case, dict):
            raise ValueError(f"{where} must be a JSON object")
        unknown = set(case) - CASE_FIELDS
        if unknown:
            raise ValueError(f"{where} has unknown fields: {', '.join(sorted(unknown))}")
        for field in ("id", "input", "check", "source"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f"{where} needs a non-empty string {field}")
        if case["id"] in seen:
            raise ValueError(f"{where} repeats case id {case['id']!r}")
        seen.add(case["id"])
        if case["check"] not in CHECKS:
            raise ValueError(f"{where} check must be one of {', '.join(CHECKS)}")
        if case["source"] not in provenance.SOURCES:
            raise ValueError(f"{where} source must be one of {', '.join(provenance.SOURCES)}")
        expected = case.get("expected")
        if case["check"] == "json_keys":
            if (
                not isinstance(expected, list)
                or not expected
                or not all(isinstance(key, str) for key in expected)
            ):
                raise ValueError(f"{where} json_keys needs expected as a list of key names")
        elif not isinstance(expected, str) or not expected:
            raise ValueError(f"{where} needs a non-empty string expected")
        if case["check"] == "label":
            labels = case.get("labels")
            if not isinstance(labels, list) or len(labels) < 2 or expected not in labels:
                raise ValueError(f"{where} label needs labels (2+) that include expected")
        if "held_out" in case and not isinstance(case["held_out"], bool):
            raise ValueError(f"{where} held_out must be true or false")
        if "difficulty" in case and (
            not isinstance(case["difficulty"], str) or not case["difficulty"].strip()
        ):
            raise ValueError(f"{where} difficulty must be a non-empty string")
        cases.append(case)
    if not cases:
        raise ValueError(f"{path.name} contains no cases")
    if len(cases) > MAX_CASES:
        raise ValueError(f"{path.name} has more than {MAX_CASES} cases")
    return cases


def split_document(cases: list[dict]) -> dict:
    held_out = sorted(case["id"] for case in cases if case.get("held_out"))
    if not held_out:
        raise ValueError("no case is marked held_out; mark about a third as held out")
    if len(held_out) == len(cases):
        raise ValueError("every case is held out; keep some tuning cases")
    return {
        "schema_version": "evalarc.case-split.v1",
        "description": "Generated by evalarc review-inputs from held_out in cases.jsonl.",
        "held_out": held_out,
    }


def manifest_document(cases: list[dict]) -> dict:
    entries = []
    for case in cases:
        entry = {"match": case["id"], "source": case["source"]}
        if case.get("difficulty"):
            entry["difficulty"] = case["difficulty"]
        entries.append(entry)
    return {"schema_version": provenance.SCHEMA, "cases": entries}


def review(cases: list[dict], source: dict) -> dict:
    manifest = {
        "source": source,
        "rules": [
            {"match": e["match"], "source": e["source"], "difficulty": e.get("difficulty")}
            for e in manifest_document(cases)["cases"]
        ],
    }
    sources = provenance.review(manifest, {case["id"] for case in cases})
    findings = provenance.findings(sources, len(cases), _finding)
    held_out = sum(1 for case in cases if case.get("held_out"))
    if not held_out:
        findings.append(
            _finding(
                "no_held_out",
                "warning",
                "No case is marked held_out, so "
                "overfitting to the tuning cases cannot be detected.",
            )
        )
    elif not 0.15 <= held_out / len(cases) <= 0.5:
        findings.append(
            _finding(
                "held_out_share",
                "info",
                f"{held_out} of {len(cases)} cases are held out; about a third is a common choice.",
            )
        )
    duplicates = [
        text
        for text, count in Counter(
            " ".join(case["input"].split()).casefold() for case in cases
        ).items()
        if count > 1
    ]
    if duplicates:
        findings.append(
            _finding(
                "duplicate_inputs",
                "warning",
                f"{len(duplicates)} input(s) "
                "appear in more than one case; duplicates inflate agreement and "
                "can leak between tuning and held-out cases.",
            )
        )
    if len(cases) < 20:
        findings.append(
            _finding(
                "few_cases",
                "info",
                f"{len(cases)} case(s): enough to start, "
                "but small changes will be within noise. Plan for more cases "
                "or repetitions (see eval-health --min-effect).",
            )
        )
    expected = Counter(
        case["expected"] for case in cases if isinstance(case["expected"], str)
    ).most_common(1)
    if expected and len(cases) >= 5 and expected[0][1] / len(cases) > 0.6:
        findings.append(
            _finding(
                "dominant_answer",
                "info",
                f"{expected[0][1]} of {len(cases)} "
                f"cases expect {expected[0][0]!r}; a constant answer would "
                "score well.",
            )
        )
    warnings = sum(item["severity"] == "warning" for item in findings)
    return {
        "schema_version": SCHEMA,
        "source": source,
        "cases": len(cases),
        "held_out": held_out,
        "checks": dict(Counter(case["check"] for case in cases)),
        "sources": sources["counts"],
        "findings": findings,
        "warnings": warnings,
        "clean": warnings == 0,
        "scope": provenance.SCOPE,
    }


def render_html(result: dict, cases: list[dict], destination: Path) -> None:
    from evalarc.report import _card, _esc, _findings, _page, _verdict

    body = _verdict(
        result["clean"],
        "Inputs ready to run" if result["clean"] else f"{result['warnings']} warning(s) to fix",
        "Read every case below before the first run.",
        "Run the baseline: python evaluate.py OUTPUT.json --epochs 3"
        if result["clean"]
        else "Fix the warnings in cases.jsonl, then rerun review-inputs.",
    )
    body += (
        '<div class="cards">'
        + _card(result["cases"], "cases")
        + _card(result["held_out"], "held out")
        + _card(result["warnings"], "warnings", alert=not result["clean"])
        + "</div><p>Sources: "
        + _esc(", ".join(f"{k} {v}" for k, v in result["sources"].items()))
        + " · checks: "
        + _esc(", ".join(f"{k} {v}" for k, v in result["checks"].items()))
        + "</p>"
    )
    if result["findings"]:
        body += _findings([(f["severity"], f["id"], f["message"]) for f in result["findings"]])
    body += (
        "<h2>Cases</h2><p>Read every case. Would two domain experts grade it the same way? "
        "Is every condition the grader checks stated in the input?</p>"
        '<div class="scroll"><table><thead><tr><th>Case</th><th>Split</th><th>Source</th>'
        "<th>Input</th><th>Check</th><th>Expected</th><th>Why hard</th></tr></thead><tbody>"
    )
    for case in cases:
        expected = case["expected"]
        if case["check"] == "label":
            expected = f"{expected} (of {', '.join(case['labels'])})"
        elif not isinstance(expected, str):
            expected = ", ".join(expected)
        body += (
            f"<tr><td><code>{_esc(case['id'])}</code></td>"
            f"<td>{'held out' if case.get('held_out') else 'tuning'}</td>"
            f"<td>{_esc(case['source'])}</td><td>{_esc(case['input'])}</td>"
            f"<td>{_esc(case['check'])}</td><td>{_esc(expected)}</td>"
            f"<td>{_esc(case.get('difficulty') or '—')}</td></tr>"
        )
    body += f"</tbody></table></div><footer>{_esc(result['scope'])}</footer>"
    _page("Input review", "Review the inputs before running.", body, destination)


def initialize(destination: Path) -> None:
    with new_run(destination) as staged:
        for name, target in (
            ("eval_app.py", "app.py"),
            ("eval_grader.py", "grader.py"),
            ("eval_evaluate.py", "evaluate.py"),
            ("eval_propose.py", "propose.py"),
            ("EVAL_README.md", "README.md"),
        ):
            (staged / target).write_text(asset(name), encoding="utf-8")
        (staged / "prompt.md").write_text(EXAMPLE_PROMPT, encoding="utf-8")
        (staged / "cases.jsonl").write_text(
            "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in EXAMPLE_CASES),
            encoding="utf-8",
        )
        (staged / "hillclimb.toml").write_text(HILLCLIMB_TOML, encoding="utf-8")
        _write_json(staged / "split.json", split_document(EXAMPLE_CASES))
        _write_json(staged / "cases.manifest.json", manifest_document(EXAMPLE_CASES))


def init_command(args) -> int:
    try:
        initialize(args.destination)
    except (OSError, ValueError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    print(
        f"Created {args.destination}. Next: replace cases.jsonl and app.py, then\n"
        f"  evalarc review-inputs {args.destination / 'cases.jsonl'} --output review "
        "--write-split split.json --write-manifest cases.manifest.json\n"
        f"See {args.destination / 'README.md'} for the full workflow."
    )
    return 0


def review_command(args) -> int:
    from evalarc.evaluate import write_json

    try:
        cases = load_cases(args.cases)
        source = {
            "name": args.cases.name,
            "sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        }
        result = review(cases, source)
        targets = []
        if args.write_split:
            targets.append((args.write_split, split_document(cases)))
        if args.write_manifest:
            targets.append((args.write_manifest, manifest_document(cases)))
        if args.output:
            with new_run(args.output) as output:
                write_json(output / "review.json", result)
                render_html(result, cases, output / "index.html")
        for path, document in targets:
            _write_json(path, document)
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print(f"evalarc: {error}", file=sys.stderr)
        return 2
    print(
        f"Input review: {result['cases']} cases, {result['held_out']} held out, "
        f"{result['warnings']} warning(s)"
    )
    for finding in result["findings"]:
        print(f"  {finding['severity']}: {finding['id']} — {finding['message']}")
    for path, _ in targets:
        print(f"Wrote {path}")
    if args.output:
        print(f"Report: {args.output / 'index.html'}")
    return 1 if args.require_clean and not result["clean"] else 0


def _write_json(path: Path, document: dict) -> None:
    """Derived files are regenerated in place from cases.jsonl."""
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _finding(identifier: str, severity: str, message: str, *, items=None, value=None) -> dict:
    finding = {"id": identifier, "severity": severity, "message": message}
    if value is not None:
        finding["value"] = value
    if items is not None:
        finding["items"] = items
    return finding
