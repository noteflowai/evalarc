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

from evalarc.usage import compare_usage, inspect_usage, junit_usage, promptfoo_usage

SCHEMA = "evalarc.results-diff.v1"
FORMATS = ("auto", "inspect", "promptfoo", "junit")
MAX_INPUT_BYTES = 512 * 1024 * 1024
# Kinds that fail the gate, in the order they are reported.
BLOCKING = ("regressed", "less_reliable", "unassessed", "less_covered", "removed")
KINDS = (*BLOCKING, "improved", "added")
INTERPRETATION = (
    "Compares recorded check outcomes only. A check counts as passed when the source tool "
    "marked it passed or its numeric score met the threshold. No regression does not mean "
    "the task is resolved, and the tool's own grading is not re-executed or authenticated."
)
SAMPLING_NOISE_NOTE = (
    "A change is marked within sampling noise when the baseline and current pass proportions "
    "have overlapping 95% Wilson intervals, so the recorded number of attempts cannot separate "
    "it from repeat-sampling variation. This is a descriptive flag, not a significance test, and "
    "it never relaxes the gate. To resolve a flagged change, record more attempts per check."
)
# Standard-normal quantile for a two-sided 95% interval, used only for the Wilson bound.
_WILSON_Z = 1.959963984540054


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
    # Recorded inputs and expected answers per case. Used only to scan harness files
    # for verbatim leakage; never part of the diff output.
    run.setdefault("material", {})
    run.setdefault("usage", {})
    run.setdefault("outputs", {})
    run.setdefault("samples", {})
    run.setdefault("generate_config", {})
    run.setdefault(
        "graders",
        {
            "subject_models": [],
            "grader_models": [],
            "self_graded": [],
            "default_grader_checks": [],
            "model_graded_checks": [],
        },
    )
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
            noise = _within_sampling_noise(before, after)
            if noise is not None:
                row["within_sampling_noise"] = noise
            conflicts = grading_conflicts(
                [
                    (before_checks.get(check), baseline["outputs"].get(case_id, {}).get(check)),
                    (after_checks.get(check), current["outputs"].get(case_id, {}).get(check)),
                ]
            )
            if conflicts:
                # The recorded output is byte-identical but the verdict differs, so this
                # change reflects the grader (nondeterminism or a revision), not the agent.
                row["same_output_different_verdict"] = conflicts
            changes.append(row)
    order = {kind: index for index, kind in enumerate(KINDS)}
    changes.sort(key=lambda row: (order[row["kind"]], row["case_id"], row["check"]))
    found = Counter(row["kind"] for row in changes)
    # less_covered is an additive schema-v1 value: it is listed only when present, so
    # comparisons with equal coverage keep exactly the counts earlier releases recorded.
    counts = {kind: found[kind] for kind in KINDS if kind != "less_covered" or found[kind]}
    counts["unchanged"] = unchanged
    blocking = sum(found[kind] for kind in BLOCKING)
    incomplete = current["incomplete"]
    # A baseline that did not finish is missing evidence: its absent checks would read as
    # "added", which never blocks, so an unfinished baseline fails the gate as well.
    baseline_incomplete = bool(baseline.get("incomplete"))
    # Article principle (low variance / gain must exceed eval noise): a change whose
    # baseline and current pass proportions have overlapping Wilson intervals cannot be
    # told apart from repeat-sampling variation at the recorded attempt count. This is a
    # descriptive annotation for reviewers, not a significance test; it never relaxes the
    # gate, which stays strict on every blocking change.
    grader_changes = sum(1 for row in changes if row.get("same_output_different_verdict"))
    blocking_within_noise = sum(
        1 for row in changes if row["kind"] in BLOCKING and row.get("within_sampling_noise") is True
    )
    return {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": baseline["format"],
        "baseline": _summary(baseline),
        "current": _summary(current),
        "counts": counts,
        "numeric_pass_threshold": current["threshold"],
        "blocking_changes": blocking,
        "blocking_changes_within_sampling_noise": blocking_within_noise,
        "changes_with_same_output_different_verdict": grader_changes,
        # Additive schema-v1 key, present only when true (the less_covered convention).
        **({"baseline_incomplete": True} if baseline_incomplete else {}),
        "current_incomplete": incomplete,
        "gate_passed": blocking == 0 and not incomplete and not baseline_incomplete,
        "changes": changes,
        "interpretation": INTERPRETATION,
        "sampling_noise_note": SAMPLING_NOISE_NOTE,
        "usage": compare_usage(baseline, current),
    }


def render_markdown(result: dict, limit: int = 50) -> str:
    """A GitHub-flavored summary suitable for $GITHUB_STEP_SUMMARY or a PR comment."""
    counts = result["counts"]
    verdict = (
        "No check lost passes"
        if result["gate_passed"]
        else f"{result['blocking_changes']} check(s) lost passes or coverage"
        if result["blocking_changes"]
        else "the baseline and current runs are incomplete"
        if result.get("baseline_incomplete") and result["current_incomplete"]
        else "the baseline run is incomplete"
        if result.get("baseline_incomplete")
        else "the current run is incomplete"
    )
    lines = [f"### EvalArc: {verdict}", ""]
    lines += ["| | Baseline | Current |", "| --- | ---: | ---: |"]
    before, after = result["baseline"], result["current"]
    for label, key in (("Headline metric", "headline"), ("Checks passed", "check_pass_rate")):
        lines.append(f"| {label} | {_value(before[key])} | {_value(after[key])} |")
    if before["check_pass_rate"].get("interval_95") and after["check_pass_rate"].get("interval_95"):
        lines.append(
            f"| 95% interval | {_interval(before['check_pass_rate'])} | "
            f"{_interval(after['check_pass_rate'])} |"
        )
    lines.append(f"| Cases | {before['cases']} | {after['cases']} |")
    if result["current_incomplete"]:
        status = _inline_code_text(after["identity"].get("status"))
        lines += ["", f"The current run did not finish (status `{status}`); the gate fails."]
    if result.get("baseline_incomplete"):
        # Escape the untrusted status like a table cell, then code-format it explicitly
        # so the line matches the current-run message: (status `error`).
        status = _inline_code_text(before["identity"].get("status"))
        lines += [
            "",
            f"The baseline run did not finish (status `{status}`); the gate fails because "
            "checks missing from it cannot be compared. "
            f"{counts.get('added', 0)} check(s) appear only in the current run. "
            "Rerun the baseline to completion.",
        ]
    if before["headline"] and before["headline"].get("name"):
        name = _inline_code_text(before["headline"]["name"])
        lines += ["", f"Headline metric: `{name}` from the source tool."]
    graded = result.get("changes_with_same_output_different_verdict") or 0
    if graded:
        lines += [
            "",
            f"{graded} change(s) have a byte-identical recorded output graded differently: "
            "the grader changed or is nondeterministic, not the agent. Check the grader "
            "before attributing these to the change.",
        ]
    within = result.get("blocking_changes_within_sampling_noise") or 0
    if within:
        lines += [
            "",
            f"{within} of {result['blocking_changes']} blocking change(s) are within sampling "
            "noise: the recorded attempts cannot separate them from repeat-sampling variation. "
            "The gate still fails; record more attempts per check to resolve them.",
        ]
    lines += [
        "",
        " · ".join(
            f"**{counts.get(kind, 0)}** {kind.replace('_', ' ')}"
            for kind in (*KINDS, "unchanged")
            if counts.get(kind, 0) or kind in ("regressed", "unchanged")
        ),
        "",
    ]
    if result["changes"]:
        lines += [
            "| Change | Case | Check | Baseline | Current |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for row in result["changes"][:limit]:
            kind = row["kind"].replace("_", " ")
            if row.get("within_sampling_noise") is True:
                kind += " (within noise)"
            if row.get("same_output_different_verdict"):
                kind += " (same output, new verdict)"
            lines.append(
                f"| {kind} | {_cell(row['case_id'])} | "
                f"{_cell(row['check'])} | {_fraction(row['baseline'])} | "
                f"{_fraction(row['current'])} |"
            )
        if len(result["changes"]) > limit:
            lines.append(f"\n{len(result['changes']) - limit} more changes are in `diff.json`.")
        lines.append("")
    if result.get("generalization") or result.get("leakage"):
        from evalarc.generalization import render_markdown as split_markdown

        lines.append(split_markdown(result))
    from evalarc import usage as usage_report

    if usage_report.shown(result):
        lines.append(usage_report.render_markdown(result))
    lines.append(f"<sub>{result['interpretation']}</sub>")
    return "\n".join(lines) + "\n"


def render_html(result: dict, destination: Path) -> None:
    from evalarc.report import _card, _esc, _page, _tone, _verdict

    before, after = result["baseline"], result["current"]
    passed = (
        result["gate_passed"]
        and result.get("generalization_passed", True)
        and (result.get("cost_gate") or {}).get("passed", True)
    )
    reasons = []
    if result["blocking_changes"]:
        reasons.append(f"{result['blocking_changes']} check(s) lost passes or coverage")
    if result["current_incomplete"]:
        reasons.append("the current run is incomplete")
    if result.get("baseline_incomplete"):
        reasons.append("the baseline run is incomplete")
    if result.get("generalization_required") and not result.get("generalization_passed"):
        reasons.append("generalization was required and not shown")
    if result.get("cost_gate") and not result["cost_gate"]["passed"]:
        reasons.append("the cost gate failed")
    within = result.get("blocking_changes_within_sampling_noise") or 0
    if passed:
        next_step = ""
    elif result.get("baseline_incomplete") and not result["blocking_changes"]:
        # No blocking rows exist to read; the missing evidence is in the baseline.
        next_step = "Rerun the baseline to completion and compare again."
    else:
        next_step = "Read the blocking rows below and their evidence"
        if within:
            next_step += (
                f"; {within} {'is' if within == 1 else 'are'} within sampling noise, so record "
                "more attempts"
            )
        next_step += "."
    body = _verdict(
        passed,
        "Gate passed: no check lost passes" if passed else "Gate failed",
        "; ".join(reasons).capitalize() + "." if reasons else "",
        next_step,
    )
    body += (
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
            tone = "bad" if row["kind"] in BLOCKING else "ok"
            change_label = row["kind"].replace("_", " ")
            if row.get("within_sampling_noise") is True:
                change_label += " · within noise"
            if row.get("same_output_different_verdict"):
                change_label += " · same output, new verdict"
            body += (
                f"<tr><td>{_tone(change_label, tone)}</td>"
                f"<td><code>{_esc(row['case_id'])}</code></td><td>{_esc(row['check'])}</td>"
                f"<td>{_esc(_fraction(row['baseline']))}</td>"
                f"<td>{_esc(_fraction(row['current']))}</td>"
                f"<td>{_esc(evidence[:400] or '—')}</td></tr>"
            )
        body += "</tbody></table></div>"
    else:
        body += "<p>Every recorded check has the same pass count.</p>"
    if result.get("generalization") or result.get("leakage"):
        from evalarc.generalization import render_html as split_html

        body += split_html(result)
    from evalarc import usage as usage_report

    if usage_report.shown(result):
        body += usage_report.render_html(result)
    body += (
        '<h2>Inputs</h2><p class="metadata">'
        + "<br>".join(
            f"{label}: {_esc(run['source']['name'])} · SHA-256 {_esc(run['source']['sha256'])}"
            f" · {_esc(json.dumps(run['identity'], ensure_ascii=False))}"
            for label, run in (("Baseline", before), ("Current", after))
        )
        + '</p><p><a href="diff.json">Diff JSON</a> · <a href="summary.md">Markdown summary</a>'
        f"</p><footer>{_esc(result['interpretation'])}"
        + (
            f" {_esc(result['sampling_noise_note'])}"
            if result.get("blocking_changes_within_sampling_noise")
            else ""
        )
        + "</footer>"
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
    material: dict[str, list] = {}
    usage: dict[str, list] = {}
    outputs: dict[str, dict[str, list]] = {}
    samples_meta: dict[str, list] = {}
    seen: set[tuple[str, int]] = set()
    for sample in document["samples"]:
        case_id = str(sample["id"])
        epoch = sample.get("epoch")
        if isinstance(epoch, int) and not isinstance(epoch, bool):
            # A repeated (id, epoch) pair would silently count as an extra attempt and
            # overstate coverage. Ids 7 and "7" collide because case_id is str(id).
            key = (case_id, epoch)
            if key in seen:
                raise ValueError(
                    f"Inspect log has duplicate sample {_shown_id(sample['id'])} epoch {epoch}: "
                    "each sample and epoch must appear once, or the copy would count as an "
                    "extra attempt. Re-export the log from Inspect (inspect log dump) instead "
                    "of merging or editing it."
                )
            seen.add(key)
        checks = cases.setdefault(case_id, {})
        _add_material(material, case_id, "input", _message_text(sample.get("input")))
        usage.setdefault(case_id, []).append(inspect_usage(sample))
        meta = _inspect_output(sample)
        samples_meta.setdefault(case_id, []).append(meta)
        digest = meta["output_sha256"]
        target = sample.get("target")
        for item in target if isinstance(target, list) else [target]:
            _add_material(material, case_id, "expected", item)
        error = sample.get("error")
        scores = sample.get("scores") or {}
        if error and not scores:
            message = error.get("message") if isinstance(error, dict) else str(error)
            checks.setdefault("sample error", []).append(_attempt(None, message))
            _record(outputs, meta, case_id, "sample error", None, checks)
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
                    _record(outputs, meta, case_id, f"{scorer}/{key}", digest, checks)
            else:
                checks.setdefault(scorer, []).append(
                    _attempt(_inspect_passed(value, threshold), evidence, value)
                )
                _record(outputs, meta, case_id, scorer, digest, checks)
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
        "material": material,
        "usage": usage,
        "outputs": outputs,
        "samples": samples_meta,
        "graders": _inspect_graders(spec),
        "generate_config": _generate_config(spec.get("model_generate_config")),
        "incomplete": document.get("status") not in (None, "success"),
    }


def _shown_id(value: object, limit: int = 80) -> str:
    """Render an untrusted sample id safely: repr() escapes control characters."""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


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
    material: dict[str, list] = {}
    usage: dict[str, list] = {}
    outputs: dict[str, dict[str, list]] = {}
    samples_meta: dict[str, list] = {}
    grader_models: set[str] = set()
    model_graded: set[str] = set()
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
        # Test variables are the case inputs. The rendered prompt is built by the
        # harness itself, so scanning it would report the template as a leak.
        for value in (row.get("vars") or {}).values():
            _add_material(material, label, "input", value)
        usage.setdefault(label, []).append(promptfoo_usage(row))
        meta = _promptfoo_output(row)
        samples_meta.setdefault(label, []).append(meta)
        digest = meta["output_sha256"]
        grader_models |= _promptfoo_graders(row, components)
        declared = (row.get("testCase") or {}).get("assert")
        assertions = (
            declared
            if isinstance(declared, list)
            else [component.get("assertion") for component in components]
        )
        for assertion in assertions:
            if isinstance(assertion, dict) and _answer_assertion(assertion.get("type")):
                _add_material(material, label, "expected", assertion.get("value"))
        if row.get("failureReason") == 2 or (row.get("error") and not grading):
            checks.setdefault("provider error", []).append(_attempt(None, row.get("error")))
            _record(outputs, meta, label, "provider error", None, checks)
            continue
        if not components:
            passed = row.get("success")
            checks.setdefault("success", []).append(
                _attempt(passed if isinstance(passed, bool) else None, grading.get("reason"))
            )
            _record(outputs, meta, label, "success", digest, checks)
            continue
        names = Counter()
        for component in components:
            name = _assertion_name(component.get("assertion") or {})
            names[name] += 1
            if names[name] > 1:
                name = f"{name} #{names[name]}"
            passed = component.get("pass")
            if str((component.get("assertion") or {}).get("type") or "") in MODEL_ASSERTIONS:
                model_graded.add(name)
            checks.setdefault(name, []).append(
                _attempt(
                    passed if isinstance(passed, bool) else None,
                    component.get("reason"),
                    component.get("score"),
                )
            )
            _record(outputs, meta, label, name, digest, checks)
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
        "material": material,
        "usage": usage,
        "outputs": outputs,
        "samples": samples_meta,
        "graders": {
            "subject_models": sorted(providers),
            "grader_models": sorted(grader_models),
            "self_graded": sorted(providers & grader_models),
            "default_grader_checks": [],
            "model_graded_checks": sorted(model_graded),
        },
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
    usage: dict[str, list] = {}
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
            usage.setdefault(case_id, []).append(junit_usage(case))
            cases.setdefault(case_id, {}).setdefault("passed", []).append(
                _attempt(outcome, evidence)
            )
    return {
        "identity": {"suites": sorted(name for name in names if name)},
        "headline": None,
        "cases": cases,
        "usage": usage,
        "incomplete": False,
    }


# --- recorded outputs and graders -------------------------------------------------

# Stop reasons meaning the output was cut off by a length limit, not finished.
TRUNCATION_REASONS = {"max_tokens", "length", "model_length", "max_output_tokens"}
# Inspect scorers that call a model; without a `model` option or a `grader` model
# role, Inspect grades with the model under evaluation.
MODEL_GRADED_SCORERS = ("model_graded_qa", "model_graded_fact")
# promptfoo assertion types graded by a model.
MODEL_ASSERTIONS = {
    "llm-rubric",
    "model-graded-closedqa",
    "model-graded-factuality",
    "factuality",
    "g-eval",
    "answer-relevance",
    "context-faithfulness",
    "context-recall",
    "context-relevance",
    "select-best",
}


def _digest(text: object) -> str | None:
    if text is None:
        return None
    if not isinstance(text, str):
        text = json.dumps(text, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


MAX_OUTPUT_CHARS = 20_000


def _record(
    outputs: dict, meta: dict, case_id: str, check: str, digest: str | None, checks: dict
) -> None:
    """Align an output digest with the attempt just appended, and note its verdict."""
    outputs.setdefault(case_id, {}).setdefault(check, []).append(digest)
    meta.setdefault("verdicts", {})[check] = checks[check][-1]["passed"]


def _output_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return value[:MAX_OUTPUT_CHARS]


def _inspect_output(sample: dict) -> dict:
    output = sample.get("output") if isinstance(sample.get("output"), dict) else {}
    completion = output.get("completion")
    stop = output.get("stop_reason")
    choices = output.get("choices")
    if stop is None and isinstance(choices, list) and choices and isinstance(choices[0], dict):
        stop = choices[0].get("stop_reason")
    limit = sample.get("limit")
    limit_type = limit.get("type") if isinstance(limit, dict) else None
    return {
        "output_sha256": _digest(completion) if isinstance(completion, str) else None,
        "output_text": _output_text(completion) if isinstance(completion, str) else None,
        "stop_reason": stop if isinstance(stop, str) else None,
        "truncated": stop in TRUNCATION_REASONS or limit_type == "token",
        "limit": limit_type if isinstance(limit_type, str) else None,
    }


GENERATE_KEYS = (
    "reasoning_effort",
    "reasoning_tokens",
    "max_tokens",
    "temperature",
    "reasoning_history",
)


def _generate_config(config: object) -> dict:
    """The generation settings that change behavior and cost, as recorded."""
    if not isinstance(config, dict):
        return {}
    return {key: config[key] for key in GENERATE_KEYS if config.get(key) is not None}


def _inspect_graders(spec: dict) -> dict:
    subject = spec.get("model")
    roles = spec.get("model_roles") if isinstance(spec.get("model_roles"), dict) else {}
    graders, default = set(), []
    role = roles.get("grader")
    role_model = role.get("model") if isinstance(role, dict) else role
    for scorer in spec.get("scorers") or []:
        if not isinstance(scorer, dict):
            continue
        name = str(scorer.get("name") or "")
        if not name.split("/")[-1].startswith(MODEL_GRADED_SCORERS):
            continue
        options = scorer.get("options") if isinstance(scorer.get("options"), dict) else {}
        model = options.get("model")
        if isinstance(model, list):
            graders |= {str(item) for item in model}
        elif model:
            graders.add(str(model))
        elif role_model:
            graders.add(str(role_model))
        else:
            default.append(name)
    subjects = {str(subject)} if subject else set()
    self_graded = sorted(subjects & graders)
    if default and subjects:
        self_graded = sorted(set(self_graded) | subjects)
    model_graded = sorted(
        str(scorer.get("name"))
        for scorer in spec.get("scorers") or []
        if isinstance(scorer, dict)
        and str(scorer.get("name") or "").split("/")[-1].startswith(MODEL_GRADED_SCORERS)
    )
    return {
        "subject_models": sorted(subjects),
        "grader_models": sorted(graders),
        "self_graded": self_graded,
        "default_grader_checks": default,
        "model_graded_checks": model_graded,
    }


def _promptfoo_output(row: dict) -> dict:
    response = row.get("response") if isinstance(row.get("response"), dict) else {}
    output = response.get("output")
    stop = response.get("finishReason") or response.get("finish_reason")
    return {
        "output_sha256": _digest(output),
        "output_text": _output_text(output),
        "stop_reason": stop if isinstance(stop, str) else None,
        "truncated": stop in TRUNCATION_REASONS,
        "limit": None,
    }


def _promptfoo_graders(row: dict, components: list) -> set[str]:
    found = set()
    sources = [((row.get("testCase") or {}).get("options") or {}).get("provider")]
    sources += [
        (component.get("assertion") or {}).get("provider")
        for component in components
        if isinstance(component, dict)
    ]
    for provider in sources:
        if isinstance(provider, str) and provider:
            found.add(provider)
        elif isinstance(provider, dict) and (provider.get("id") or provider.get("label")):
            found.add(str(provider.get("id") or provider.get("label")))
    return found


# --- case material ----------------------------------------------------------------

MAX_MATERIAL_CHARS = 4096


def _message_text(value: object) -> str | None:
    """Inspect input is a string or a list of chat messages with text content."""
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return None
    parts = []
    for message in value:
        if not isinstance(message, dict) or message.get("role") == "system":
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts += [
                item["text"]
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
    return "\n".join(parts) or None


_CODE_ASSERTIONS = ("javascript", "python", "webhook", "ruby")


def _answer_assertion(kind: object) -> bool:
    """promptfoo assertions whose value states an expected answer or rubric.

    Negated checks (not-*) name forbidden text, and code assertions hold grader
    logic; neither is a reference answer that could leak into the harness.
    """
    kind = str(kind or "")
    return not kind.startswith("not-") and kind not in _CODE_ASSERTIONS


def _add_material(material: dict, case_id: str, role: str, text: object) -> None:
    if not isinstance(text, str) or not text.strip():
        return
    entry = {"role": role, "text": text[:MAX_MATERIAL_CHARS]}
    items = material.setdefault(case_id, [])
    if entry not in items:
        items.append(entry)


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
    # A smaller assessed sample cannot count as unchanged or improved: missing
    # evidence must never look like progress. More attempts are never penalized.
    if after["assessed"] < before["assessed"]:
        return "less_covered"
    if new > old:
        return "improved"
    return None


def _detail(attempts: list) -> list:
    return [item for item in attempts if item["passed"] is not True] or attempts[:1]


def _wilson_interval(passed: int, assessed: int) -> tuple[float, float]:
    """95% Wilson score interval for a pass proportion. Pure stdlib, no SciPy."""
    if assessed <= 0:
        return (0.0, 1.0)
    z = _WILSON_Z
    phat = passed / assessed
    denom = 1.0 + z * z / assessed
    center = phat + z * z / (2.0 * assessed)
    margin = z * math.sqrt(phat * (1.0 - phat) / assessed + z * z / (4.0 * assessed * assessed))
    low = (center - margin) / denom
    high = (center + margin) / denom
    return (max(0.0, low), min(1.0, high))


def grading_conflicts(sides: list[tuple[list | None, list | None]]) -> int:
    """Count recorded outputs graded both passed and failed across the given attempts.

    Each side is (attempts, output digests aligned with attempts). Attempts without a
    recorded output or without an outcome are ignored.
    """
    verdicts: dict[str, set] = {}
    for attempts, digests in sides:
        if not attempts or not digests or len(digests) != len(attempts):
            continue
        for attempt, digest in zip(attempts, digests):
            if digest is not None and attempt["passed"] is not None:
                verdicts.setdefault(digest, set()).add(attempt["passed"])
    return sum(1 for seen in verdicts.values() if len(seen) > 1)


def wilson(passed: int, assessed: int) -> list[float] | None:
    """Rounded 95% Wilson interval for reports, or None without assessed attempts."""
    if not assessed:
        return None
    low, high = _wilson_interval(passed, assessed)
    return [round(low, 6), round(high, 6)]


def _within_sampling_noise(before: dict | None, after: dict | None) -> bool | None:
    """True when a change cannot be told apart from repeat-sampling variation.

    The check must show variation we actually observed: at least one side passes on
    some attempts and fails on others, and the two pass proportions have overlapping
    95% Wilson intervals at the recorded attempt count. A clean all-pass to all-fail
    swing is the strongest signal available at that count and is never marked as noise.

    Returns None when the annotation does not apply: either side is absent (added or
    removed check) or neither side records more than one attempt, so there is no
    sampling spread to reason about.
    """
    if before is None or after is None:
        return None
    if before["assessed"] <= 1 and after["assessed"] <= 1:
        return None
    observed_flaky = (0 < before["passed"] < before["assessed"]) or (
        0 < after["passed"] < after["assessed"]
    )
    if not observed_flaky:
        return False
    low_b, high_b = _wilson_interval(before["passed"], before["assessed"])
    low_a, high_a = _wilson_interval(after["passed"], after["assessed"])
    return low_b <= high_a and low_a <= high_b


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
            "passed": sum(item["passed"] for item in tallies),
            "assessed": assessed,
            "interval_95": wilson(sum(item["passed"] for item in tallies), assessed),
        },
    }


def _interval(metric: dict) -> str:
    low, high = metric["interval_95"]
    return f"{low:.3f}–{high:.3f}"


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


def _inline_code_text(value: object) -> str:
    """Make an untrusted value safe inside one Markdown inline code span on one line.

    Pipes are escaped for table rows, backticks become apostrophes so they cannot
    close the span, and every CommonMark line ending (CRLF, CR, LF) becomes a space
    so the value cannot start a new line such as a fake verdict heading. Only the
    rendered text changes; result dicts and diff.json keep the raw value.
    """
    return (
        str(value)
        .replace("|", "\\|")
        .replace("`", "'")
        .replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
    )


# CommonMark punctuation that can open emphasis, links, raw HTML, code spans or table
# cells inside a line. Backslash-escaping any ASCII punctuation is always literal.
_MARKDOWN_PUNCTUATION = set("\\`*_[]<>|!#~&")


def markdown_text(value: object) -> str:
    """Make untrusted prose safe on one Markdown line outside a code span.

    Line endings (CRLF, CR, LF) become spaces so the value cannot start a heading
    or verdict line, and structural punctuation is backslash-escaped so it cannot
    create raw HTML, links, emphasis or table cells. Only rendered text changes.
    """
    text = str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return "".join("\\" + ch if ch in _MARKDOWN_PUNCTUATION else ch for ch in text)


def _cell(text: str) -> str:
    return "`" + _inline_code_text(text) + "`"
