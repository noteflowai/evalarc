"""Compare two saved result files from other evaluation tools, check by check.

Supported inputs are Inspect AI logs (JSON, or ``.eval`` when this Python can
decompress it), promptfoo ``--output`` JSON and JUnit XML. Each input is reduced
to cases, named checks and repeated attempts. The comparison then reports every
check whose pass count fell, even when the tool's headline metric improved.
"""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

SCHEMA = "evalarc.results-diff.v1"
FORMATS = ("auto", "inspect", "promptfoo", "junit")
MAX_INPUT_BYTES = 512 * 1024 * 1024
# Kinds that fail the gate, in the order they are reported.
BLOCKING = ("regressed", "less_reliable", "unassessed", "removed")
KINDS = (*BLOCKING, "improved", "added")
INTERPRETATION = (
    "Compares recorded check outcomes only. A check counts as passed when the source tool "
    "marked it passed or its numeric score met the threshold. No regression does not mean "
    "the task is resolved, and the tool's own grading is not re-executed or authenticated."
)


def load_results(path: Path, fmt: str = "auto", threshold: float = 1.0) -> dict:
    """Read one result file into cases -> checks -> attempts."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")
    if not math.isfinite(threshold):
        raise ValueError("threshold must be a finite number")
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"{path.name} exceeds {MAX_INPUT_BYTES} bytes")
    detected = _detect(path, raw) if fmt == "auto" else fmt
    if detected == "junit":
        run = _junit(raw)
    elif detected == "inspect":
        run = _inspect(_inspect_document(path, raw), threshold)
    else:
        run = _promptfoo(_json(raw, path))
    if not run["cases"]:
        raise ValueError(f"{path.name} contains no scored cases")
    run["format"] = detected
    run["threshold"] = threshold
    run["source"] = {"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
    return run


def diff(baseline: dict, current: dict) -> dict:
    """Classify every (case, check) by how its pass count changed."""
    if baseline["format"] != current["format"]:
        raise ValueError(
            f"inputs use different formats: {baseline['format']} and {current['format']}"
        )
    for field in ("task",):
        before, after = baseline["identity"].get(field), current["identity"].get(field)
        if before is not None and after is not None and before != after:
            raise ValueError(f"inputs are not comparable: {field} {before!r} != {after!r}")
    changes, unchanged = [], 0
    for case_id in sorted(set(baseline["cases"]) | set(current["cases"])):
        before_checks = baseline["cases"].get(case_id, {})
        after_checks = current["cases"].get(case_id, {})
        for check in sorted(set(before_checks) | set(after_checks)):
            before = _tally(before_checks.get(check))
            after = _tally(after_checks.get(check))
            kind = _classify(before, after)
            if kind is None:
                unchanged += 1
                continue
            row = {"case_id": case_id, "check": check, "kind": kind}
            for label, tally, attempts in (
                ("baseline", before, before_checks.get(check)),
                ("current", after, after_checks.get(check)),
            ):
                row[label] = tally
                if attempts:
                    row[f"{label}_detail"] = _detail(attempts)
            changes.append(row)
    order = {kind: index for index, kind in enumerate(KINDS)}
    changes.sort(key=lambda row: (order[row["kind"]], row["case_id"], row["check"]))
    counts = {kind: 0 for kind in KINDS}
    counts.update(Counter(row["kind"] for row in changes))
    counts["unchanged"] = unchanged
    blocking = sum(counts[kind] for kind in BLOCKING)
    incomplete = current["incomplete"]
    return {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": baseline["format"],
        "baseline": _summary(baseline),
        "current": _summary(current),
        "counts": counts,
        "numeric_pass_threshold": current["threshold"],
        "blocking_changes": blocking,
        "current_incomplete": incomplete,
        "gate_passed": blocking == 0 and not incomplete,
        "changes": changes,
        "interpretation": INTERPRETATION,
    }


def render_markdown(result: dict, limit: int = 50) -> str:
    """A GitHub-flavored summary suitable for $GITHUB_STEP_SUMMARY or a PR comment."""
    counts = result["counts"]
    verdict = (
        "No check lost passes"
        if result["gate_passed"]
        else f"{result['blocking_changes']} check(s) lost passes or coverage"
        if result["blocking_changes"]
        else "the current run is incomplete"
    )
    lines = [f"### EvalArc: {verdict}", ""]
    lines += ["| | Baseline | Current |", "| --- | ---: | ---: |"]
    before, after = result["baseline"], result["current"]
    for label, key in (("Headline metric", "headline"), ("Checks passed", "check_pass_rate")):
        lines.append(f"| {label} | {_value(before[key])} | {_value(after[key])} |")
    lines.append(f"| Cases | {before['cases']} | {after['cases']} |")
    if result["current_incomplete"]:
        status = after["identity"].get("status")
        lines += ["", f"The current run did not finish (status `{status}`); the gate fails."]
    if before["headline"] and before["headline"].get("name"):
        lines += ["", f"Headline metric: `{before['headline']['name']}` from the source tool."]
    lines += [
        "",
        " · ".join(
            f"**{counts[kind]}** {kind.replace('_', ' ')}"
            for kind in (*KINDS, "unchanged")
            if counts[kind] or kind in ("regressed", "unchanged")
        ),
        "",
    ]
    if result["changes"]:
        lines += [
            "| Change | Case | Check | Baseline | Current |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for row in result["changes"][:limit]:
            lines.append(
                f"| {row['kind'].replace('_', ' ')} | {_cell(row['case_id'])} | "
                f"{_cell(row['check'])} | {_fraction(row['baseline'])} | "
                f"{_fraction(row['current'])} |"
            )
        if len(result["changes"]) > limit:
            lines.append(f"\n{len(result['changes']) - limit} more changes are in `diff.json`.")
        lines.append("")
    lines.append(f"<sub>{result['interpretation']}</sub>")
    return "\n".join(lines) + "\n"


def render_html(result: dict, destination: Path) -> None:
    from evalarc.report import _card, _esc, _page

    before, after = result["baseline"], result["current"]
    body = (
        f"<p>{_esc(result['format'])} results · {_esc(before['source']['name'])} → "
        f'{_esc(after["source"]["name"])}</p><div class="cards">'
        + _card(_value(before["headline"]), f"baseline {_metric_name(before)}")
        + _card(_value(after["headline"]), f"current {_metric_name(after)}")
        + _card(
            result["blocking_changes"],
            "checks lost passes or coverage",
            alert=not result["gate_passed"],
        )
        + _card(result["counts"]["improved"], "checks improved")
        + "</div>"
    )
    if result["changes"]:
        body += (
            '<h2>Changed checks</h2><div class="scroll"><table><thead><tr><th>Change</th>'
            "<th>Case</th><th>Check</th><th>Baseline passes</th><th>Current passes</th>"
            "<th>Current evidence</th></tr></thead><tbody>"
        )
        for row in result["changes"]:
            detail = row.get("current_detail") or row.get("baseline_detail") or []
            evidence = "; ".join(dict.fromkeys(i["evidence"] for i in detail if i.get("evidence")))
            tone = "failed" if row["kind"] in BLOCKING else "passed"
            body += (
                f'<tr><td class="{tone}">{_esc(row["kind"].replace("_", " "))}</td>'
                f"<td><code>{_esc(row['case_id'])}</code></td><td>{_esc(row['check'])}</td>"
                f"<td>{_esc(_fraction(row['baseline']))}</td>"
                f"<td>{_esc(_fraction(row['current']))}</td>"
                f"<td>{_esc(evidence[:400] or '—')}</td></tr>"
            )
        body += "</tbody></table></div>"
    else:
        body += "<p>Every recorded check has the same pass count.</p>"
    body += (
        '<h2>Inputs</h2><p class="metadata">'
        + "<br>".join(
            f"{label}: {_esc(run['source']['name'])} · SHA-256 {_esc(run['source']['sha256'])}"
            f" · {_esc(json.dumps(run['identity'], ensure_ascii=False))}"
            for label, run in (("Baseline", before), ("Current", after))
        )
        + '</p><p><a href="diff.json">Diff JSON</a> · <a href="summary.md">Markdown summary</a>'
        f"</p><footer>{_esc(result['interpretation'])}</footer>"
    )
    _page("Results diff", "Changed checks.", body, destination)


# --- input formats -----------------------------------------------------------


def _detect(path: Path, raw: bytes) -> str:
    if path.suffix == ".eval" or raw[:4] == b"PK\x03\x04":
        return "inspect"
    if path.suffix == ".xml" or raw.lstrip()[:1] == b"<":
        return "junit"
    document = _json(raw, path)
    if isinstance(document, dict) and isinstance(document.get("eval"), dict):
        return "inspect"
    if isinstance(document, dict) and isinstance(document.get("results"), dict):
        return "promptfoo"
    raise ValueError(f"cannot detect the format of {path.name}; pass --format")


def _json(raw: bytes, path: Path) -> object:
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} is not JSON: {error}") from None


def _inspect_document(path: Path, raw: bytes) -> dict:
    if raw[:4] != b"PK\x03\x04":
        document = _json(raw, path)
        if not isinstance(document, dict):
            raise ValueError("Inspect log must be a JSON object")
        return document
    try:
        with zipfile.ZipFile(path) as archive:
            members = {PurePosixPath(item.filename): item for item in archive.infolist()}
            if sum(item.file_size for item in members.values()) > MAX_INPUT_BYTES:
                raise ValueError(f"{path.name} expands beyond {MAX_INPUT_BYTES} bytes")
            header = PurePosixPath("header.json")
            if header not in members:
                raise ValueError(f"{path.name} has no header.json; the run may be incomplete")
            document = json.loads(archive.read(members[header]))
            document["samples"] = [
                json.loads(archive.read(item))
                for name, item in sorted(members.items())
                if name.parent == PurePosixPath("samples") and name.suffix == ".json"
            ]
    except NotImplementedError:
        raise ValueError(
            f"this Python cannot decompress {path.name} (Inspect uses zstd; Python 3.14+ "
            "reads it). Convert it with `inspect log dump LOG.eval > LOG.json`, or run "
            "Inspect with `--log-format json`."
        ) from None
    except zipfile.BadZipFile as error:
        raise ValueError(f"{path.name} is not a readable Inspect log: {error}") from None
    return document


def _inspect(document: dict, threshold: float) -> dict:
    spec = document.get("eval")
    if not isinstance(spec, dict) or not isinstance(document.get("samples"), list):
        raise ValueError("not an Inspect log: expected `eval` and `samples`")
    if not document["samples"]:
        raise ValueError("Inspect log has no samples; rerun without --no-log-samples")
    cases: dict[str, dict[str, list]] = {}
    for sample in document["samples"]:
        case_id = str(sample["id"])
        checks = cases.setdefault(case_id, {})
        error = sample.get("error")
        scores = sample.get("scores") or {}
        if error and not scores:
            message = error.get("message") if isinstance(error, dict) else str(error)
            checks.setdefault("sample error", []).append(_attempt(None, message))
            continue
        for scorer, score in scores.items():
            value, evidence = score, None
            if isinstance(score, dict):
                value = score.get("value")
                evidence = score.get("explanation") or score.get("answer")
            if isinstance(value, dict):
                for key, item in value.items():
                    checks.setdefault(f"{scorer}/{key}", []).append(
                        _attempt(_inspect_passed(item, threshold), evidence, item)
                    )
            else:
                checks.setdefault(scorer, []).append(
                    _attempt(_inspect_passed(value, threshold), evidence, value)
                )
    headline = None
    results = document.get("results") or {}
    marker = results.get("headline") or {}
    for group in results.get("scores") or []:
        metrics = group.get("metrics") or {}
        wanted = marker.get("metric") if group.get("name") == marker.get("score") else None
        if not marker and metrics:
            wanted = next(iter(metrics))
        if wanted in metrics:
            value = metrics[wanted].get("value")
            finite = isinstance(value, (int, float)) and math.isfinite(value)
            headline = {"name": f"{group['name']} {wanted}", "value": value if finite else None}
            break
    return {
        "identity": {
            "task": spec.get("task"),
            "model": spec.get("model"),
            "status": document.get("status"),
            "epochs": (spec.get("config") or {}).get("epochs"),
        },
        "headline": headline,
        "cases": cases,
        "incomplete": document.get("status") not in (None, "success"),
    }


def _inspect_passed(value: object, threshold: float) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in ("C",):
        return True
    if value in ("I", "N", "P"):
        return False
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value >= threshold
    return None


def _promptfoo(document: object) -> dict:
    summary = document.get("results") if isinstance(document, dict) else None
    if not isinstance(summary, dict) or not isinstance(summary.get("results"), list):
        raise ValueError("not a promptfoo output: expected results.results[]")
    rows = summary["results"]
    providers = {_provider(row) for row in rows}
    prompts = {row.get("promptIdx") for row in rows}
    # Repeats (--repeat) share a description and vars but get new test indexes, so
    # only distinct vars distinguish two tests that have the same description.
    variants: dict[str, set] = {}
    for row in rows:
        variants.setdefault(_test_label(row), set()).add(_vars(row))
    cases: dict[str, dict[str, list]] = {}
    for row in rows:
        label = _test_label(row)
        if len(variants[label]) > 1 and label != _vars(row):
            label = f"{label} {_vars(row)}"
        if len(providers) > 1:
            label += f" · {_provider(row)}"
        if len(prompts) > 1:
            label += f" · prompt {row.get('promptIdx')}"
        checks = cases.setdefault(label, {})
        grading = row.get("gradingResult") or {}
        components = grading.get("componentResults") or []
        if row.get("failureReason") == 2 or (row.get("error") and not grading):
            checks.setdefault("provider error", []).append(_attempt(None, row.get("error")))
            continue
        if not components:
            passed = row.get("success")
            checks.setdefault("success", []).append(
                _attempt(passed if isinstance(passed, bool) else None, grading.get("reason"))
            )
            continue
        names = Counter()
        for component in components:
            name = _assertion_name(component.get("assertion") or {})
            names[name] += 1
            if names[name] > 1:
                name = f"{name} #{names[name]}"
            passed = component.get("pass")
            checks.setdefault(name, []).append(
                _attempt(
                    passed if isinstance(passed, bool) else None,
                    component.get("reason"),
                    component.get("score"),
                )
            )
    stats = summary.get("stats") or {}
    total = sum(stats.get(key) or 0 for key in ("successes", "failures", "errors"))
    headline = (
        {"name": "promptfoo pass rate", "value": (stats.get("successes") or 0) / total}
        if total
        else None
    )
    return {
        "identity": {
            "description": (document.get("config") or {}).get("description"),
            "providers": sorted(providers),
            "version": summary.get("version"),
        },
        "headline": headline,
        "cases": cases,
        "incomplete": False,
    }


def _provider(row: dict) -> str:
    provider = row.get("provider") or {}
    if isinstance(provider, str):
        return provider
    return str(provider.get("label") or provider.get("id") or "provider")


def _vars(row: dict) -> str:
    return json.dumps(row.get("vars") or {}, sort_keys=True, ensure_ascii=False)


def _test_label(row: dict) -> str:
    test = row.get("testCase") or {}
    if test.get("description"):
        return str(test["description"])
    return _vars(row) if row.get("vars") else f"test {row.get('testIdx')}"


def _assertion_name(assertion: dict) -> str:
    if assertion.get("metric"):
        return str(assertion["metric"])
    kind = str(assertion.get("type") or "assertion")
    value = assertion.get("value")
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value).replace("\n", " ")
        return f"{kind}: {text[:60]}{'…' if len(text) > 60 else ''}"
    return kind


def _junit(raw: bytes) -> dict:
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("JUnit XML with a DTD or entities is not accepted")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise ValueError(f"not JUnit XML: {error}") from None
    if root.tag not in ("testsuites", "testsuite"):
        raise ValueError("not JUnit XML: expected <testsuites> or <testsuite>")
    cases: dict[str, dict[str, list]] = {}
    suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
    names = set()
    for suite in suites:
        names.add(suite.get("name"))
        for case in suite.findall("testcase"):
            owner = case.get("classname") or suite.get("name") or ""
            case_id = f"{owner}::{case.get('name')}" if owner else str(case.get("name"))
            outcome, evidence = True, None
            for tag, value in (("failure", False), ("error", None), ("skipped", None)):
                element = case.find(tag)
                if element is not None:
                    outcome = value
                    evidence = f"{tag}: {element.get('message') or (element.text or '').strip()}"
                    break
            cases.setdefault(case_id, {}).setdefault("passed", []).append(
                _attempt(outcome, evidence)
            )
    return {
        "identity": {"suites": sorted(name for name in names if name)},
        "headline": None,
        "cases": cases,
        "incomplete": False,
    }


# --- comparison helpers -----------------------------------------------------------


def _attempt(passed: bool | None, evidence: object = None, value: object = None) -> dict:
    row: dict = {"passed": passed}
    if value is not None:
        row["value"] = value
    if evidence:
        text = str(evidence)
        row["evidence"] = text[:500] + ("…" if len(text) > 500 else "")
    return row


def _tally(attempts: list | None) -> dict | None:
    if attempts is None:
        return None
    return {
        "passed": sum(item["passed"] is True for item in attempts),
        "assessed": sum(item["passed"] is not None for item in attempts),
        "attempts": len(attempts),
    }


def _classify(before: dict | None, after: dict | None) -> str | None:
    if before is None:
        return "added"
    if after is None:
        # Dropping a failing check can turn a red gate green, so any removal counts.
        return "removed"
    if before["passed"] and not after["assessed"]:
        return "unassessed"
    rate = lambda tally: tally["passed"] / tally["assessed"] if tally["assessed"] else 0.0  # noqa: E731
    old, new = rate(before), rate(after)
    if new < old:
        return "regressed" if after["passed"] == 0 else "less_reliable"
    if new > old:
        return "improved"
    return None


def _detail(attempts: list) -> list:
    return [item for item in attempts if item["passed"] is not True] or attempts[:1]


def _summary(run: dict) -> dict:
    tallies = [_tally(attempts) for checks in run["cases"].values() for attempts in checks.values()]
    assessed = sum(item["assessed"] for item in tallies)
    return {
        "source": run["source"],
        "identity": run["identity"],
        "incomplete": run["incomplete"],
        "headline": run["headline"],
        "cases": len(run["cases"]),
        "checks": len(tallies),
        "check_pass_rate": {
            "name": "passed check attempts",
            "value": sum(item["passed"] for item in tallies) / assessed if assessed else None,
        },
    }


def _metric_name(run: dict) -> str:
    return (run["headline"] or {}).get("name") or "headline (none recorded)"


def _value(metric: dict | None) -> str:
    if not metric or metric.get("value") is None:
        return "—"
    return f"{metric['value']:.4f}".rstrip("0").rstrip(".")


def _fraction(tally: dict | None) -> str:
    if tally is None:
        return "absent"
    text = f"{tally['passed']}/{tally['assessed']}"
    if tally["assessed"] != tally["attempts"]:
        text += f" ({tally['attempts'] - tally['assessed']} unassessed)"
    return text


def _cell(text: str) -> str:
    return "`" + str(text).replace("|", "\\|").replace("`", "'").replace("\n", " ") + "`"
