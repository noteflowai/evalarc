"""Held-out split review and harness leakage scan for ``evalarc diff``.

A change tuned against some evaluation cases should also improve cases it was not
tuned on. The caller declares which cases were held out from tuning; this module
compares the pass rates of both partitions between the baseline and current runs
and scans declared harness files (prompts, skills, tool descriptions) for recorded
case inputs or expected answers copied verbatim. Everything is computed from saved
records; nothing is rerun and no model is called.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from pathlib import Path

from evalarc.results_diff import BLOCKING, _cell, _tally, _wilson_interval

SPLIT_SCHEMA = "evalarc.case-split.v1"
MAX_SPLIT_BYTES = 4 * 1024 * 1024
MAX_SPLIT_ENTRIES = 10_000
MAX_HARNESS_FILES = 2_000
MAX_HARNESS_BYTES = 16 * 1024 * 1024
MAX_HARNESS_FILE_BYTES = 2 * 1024 * 1024
MAX_LEAKAGE_HITS = 200
DEFAULT_MIN_LEAK_CHARS = 12
STATES = (
    "held_out_regressions",
    "generalizes",
    "overfitting_signal",
    "held_out_gain_within_noise",
    "no_measurable_gain",
)
STATE_TEXT = {
    "held_out_regressions": "A held-out check lost passes or coverage.",
    "generalizes": "Held-out cases improved beyond sampling noise.",
    "overfitting_signal": (
        "Tuning cases improved beyond sampling noise, but held-out cases did not."
    ),
    "held_out_gain_within_noise": (
        "Held-out cases improved, but within sampling noise at the recorded attempts."
    ),
    "no_measurable_gain": "Neither partition improved beyond sampling noise.",
}
GENERALIZATION_SCOPE = (
    "Compares check-attempt pass rates of caller-declared tuning and held-out cases. "
    "The split is only as independent as its declaration: EvalArc cannot confirm that "
    "held-out cases were hidden from whoever made the change. Attempts within one case "
    "are not independent, so the Wilson overlap is a descriptive noise flag, not a test."
)
LEAKAGE_SCOPE = (
    "Finds recorded case inputs and expected answers copied verbatim (case-insensitive, "
    "whitespace-normalized) into declared harness files. Paraphrased or encoded leakage "
    "is not detected, and a hit can be a legitimate shared phrase; review each one."
)


def load_split(path: Path) -> dict:
    """Read an evalarc.case-split.v1 file naming held-out case IDs or patterns."""
    raw = path.read_bytes()
    if len(raw) > MAX_SPLIT_BYTES:
        raise ValueError(f"{path.name} exceeds {MAX_SPLIT_BYTES} bytes")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} is not JSON: {error}") from None
    if not isinstance(document, dict):
        raise ValueError("case split must be a JSON object")
    unknown = set(document) - {"schema_version", "held_out", "description"}
    if unknown:
        raise ValueError(f"case split has unknown fields: {', '.join(sorted(unknown))}")
    if document.get("schema_version") != SPLIT_SCHEMA:
        raise ValueError(f"case split schema_version must be {SPLIT_SCHEMA!r}")
    entries = document.get("held_out")
    if (
        not isinstance(entries, list)
        or not entries
        or len(entries) > MAX_SPLIT_ENTRIES
        or not all(isinstance(item, str) and item for item in entries)
    ):
        raise ValueError(
            f"held_out must list 1–{MAX_SPLIT_ENTRIES} non-empty case IDs or glob patterns"
        )
    if len(set(entries)) != len(entries):
        raise ValueError("held_out lists the same entry twice")
    description = document.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError("description must be a string")
    return {
        "source": {"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()},
        "held_out": entries,
        "description": description,
    }


def partition(split: dict, case_ids: set[str]) -> set[str]:
    """Return the held-out case IDs; every entry must match at least one case."""
    held_out: set[str] = set()
    for entry in split["held_out"]:
        if any(character in entry for character in "*?["):
            matched = {case for case in case_ids if fnmatch.fnmatchcase(case, entry)}
        else:
            matched = {entry} & case_ids
        if not matched:
            raise ValueError(f"held-out entry {entry!r} matches no recorded case")
        held_out |= matched
    if held_out == case_ids:
        raise ValueError("every case is held out; no tuning cases remain to compare")
    return held_out


def review_split(baseline: dict, current: dict, result: dict, split: dict) -> dict:
    """Compare tuning and held-out pass rates; classify the change per FIG-6 rules."""
    case_ids = set(baseline["cases"]) | set(current["cases"])
    held_out = partition(split, case_ids)
    partitions = {}
    for name, members in (("tuning", case_ids - held_out), ("held_out", held_out)):
        before = _rate(baseline, members)
        after = _rate(current, members)
        delta = (
            None
            if before["pass_rate"] is None or after["pass_rate"] is None
            else after["pass_rate"] - before["pass_rate"]
        )
        noise = (
            None
            if delta is None
            else _overlap(before["passed"], before["assessed"], after["passed"], after["assessed"])
        )
        blocking = [
            row
            for row in result["changes"]
            if row["case_id"] in members and row["kind"] in BLOCKING
        ]
        partitions[name] = {
            "cases": len(members),
            "baseline": before,
            "current": after,
            "delta": delta,
            "within_sampling_noise": noise,
            "improved_beyond_noise": bool(delta is not None and delta > 0 and not noise),
            "blocking_changes": len(blocking),
        }
    tuning, holdout = partitions["tuning"], partitions["held_out"]
    if holdout["blocking_changes"]:
        state = "held_out_regressions"
    elif holdout["improved_beyond_noise"]:
        state = "generalizes"
    elif tuning["improved_beyond_noise"]:
        state = "overfitting_signal"
    elif holdout["delta"] is not None and holdout["delta"] > 0:
        state = "held_out_gain_within_noise"
    else:
        state = "no_measurable_gain"
    return {
        "split": {
            "source": split["source"],
            "description": split["description"],
            "entries": split["held_out"],
            "held_out_cases": sorted(held_out),
        },
        "partitions": partitions,
        "state": state,
        "explanation": STATE_TEXT[state],
        "scope": GENERALIZATION_SCOPE,
    }


def scan_harness(
    paths: list[Path] | list[tuple[Path, str]],
    runs: list[dict],
    held_out: set[str] | None = None,
    min_chars: int = DEFAULT_MIN_LEAK_CHARS,
) -> dict:
    """Search harness text files for recorded case material copied verbatim."""
    if min_chars < 4:
        raise ValueError("--leak-min-chars must be at least 4")
    needles: dict[str, list[dict]] = {}
    for run in runs:
        for case_id, items in run.get("material", {}).items():
            for item in items:
                normalized = _normalize(item["text"])
                if len(normalized) < min_chars:
                    continue
                entry = {"case_id": case_id, "role": item["role"], "text": item["text"]}
                bucket = needles.setdefault(normalized, [])
                if entry not in bucket:
                    bucket.append(entry)
    files, total = [], 0
    for path, label in harness_files(paths):
        data = path.read_bytes()
        total += len(data)
        if total > MAX_HARNESS_BYTES:
            raise ValueError(f"harness files exceed {MAX_HARNESS_BYTES} bytes")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        files.append((label, hashlib.sha256(data).hexdigest(), len(data), text))
    hits, truncated = [], False
    for label, sha256, _, text in files:
        lines = text.splitlines()
        normalized_lines = [_normalize(line) for line in lines]
        whole = _normalize(text)
        for needle, owners in needles.items():
            if needle not in whole:
                continue
            line = next(
                (index + 1 for index, value in enumerate(normalized_lines) if needle in value),
                None,
            )
            for owner in owners:
                if len(hits) >= MAX_LEAKAGE_HITS:
                    truncated = True
                    break
                hits.append(
                    {
                        "file": label,
                        "file_sha256": sha256,
                        "line": line,
                        "case_id": owner["case_id"],
                        "partition": None
                        if held_out is None
                        else ("held_out" if owner["case_id"] in held_out else "tuning"),
                        "role": owner["role"],
                        "text": owner["text"][:160] + ("…" if len(owner["text"]) > 160 else ""),
                    }
                )
    hits.sort(key=lambda hit: (hit["partition"] != "held_out", hit["file"], hit["line"] or 0))
    return {
        "files_scanned": [
            {"path": label, "sha256": sha256, "bytes": size} for label, sha256, size, _ in files
        ],
        "materials_considered": len(needles),
        "min_chars": min_chars,
        "hits": hits,
        "held_out_hits": sum(hit["partition"] == "held_out" for hit in hits),
        "truncated": truncated,
        "scope": LEAKAGE_SCOPE,
    }


def generalization_passed(result: dict) -> bool:
    """The opt-in --require-generalization rule."""
    review = result.get("generalization")
    leakage = result.get("leakage") or {}
    return bool(review and review["state"] == "generalizes" and not leakage.get("held_out_hits"))


def render_markdown(result: dict) -> str:
    lines: list[str] = []
    review = result.get("generalization")
    if review:
        lines += [
            f"#### Held-out split: `{review['state']}`",
            "",
            review["explanation"],
            "",
            "| Partition | Cases | Baseline | Current | Change | Within noise | Blocking |",
            "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
        ]
        for name, label in (("tuning", "Tuning"), ("held_out", "Held out")):
            row = review["partitions"][name]
            lines.append(
                f"| {label} | {row['cases']} | {_percent(row['baseline']['pass_rate'])} | "
                f"{_percent(row['current']['pass_rate'])} | {_signed(row['delta'])} | "
                f"{_yes(row['within_sampling_noise'])} | {row['blocking_changes']} |"
            )
        lines += ["", f"<sub>{review['scope']}</sub>", ""]
    leakage = result.get("leakage")
    if leakage:
        lines += [
            f"#### Harness leakage: {len(leakage['hits'])} hit(s)"
            + (f", {leakage['held_out_hits']} from held-out cases" if review else ""),
            "",
            f"Scanned {len(leakage['files_scanned'])} file(s) for "
            f"{leakage['materials_considered']} recorded input/expected strings of at least "
            f"{leakage['min_chars']} characters.",
            "",
        ]
        if leakage["hits"]:
            lines += [
                "| File | Line | Case | Partition | Role | Text |",
                "| --- | ---: | --- | --- | --- | --- |",
            ]
            for hit in leakage["hits"][:20]:
                lines.append(
                    f"| {_cell(hit['file'])} | {hit['line'] or '—'} | {_cell(hit['case_id'])} | "
                    f"{hit['partition'] or '—'} | {hit['role']} | {_cell(hit['text'][:80])} |"
                )
            if len(leakage["hits"]) > 20:
                lines.append(f"\n{len(leakage['hits']) - 20} more hits are in `diff.json`.")
            lines.append("")
        lines += [f"<sub>{leakage['scope']}</sub>", ""]
    return "\n".join(lines) + ("\n" if lines else "")


def render_html(result: dict) -> str:
    from evalarc.report import _card, _esc

    body = ""
    review = result.get("generalization")
    if review:
        body += (
            f"<h2>Held-out split</h2><p><strong>{_esc(review['state'])}</strong>: "
            f'{_esc(review["explanation"])}</p><div class="cards">'
        )
        for name, label in (("tuning", "tuning change"), ("held_out", "held-out change")):
            row = review["partitions"][name]
            body += _card(
                _signed(row["delta"]),
                f"{label} ({row['cases']} cases)",
                alert=name == "held_out" and review["state"] != "generalizes",
            )
        body += (
            '</div><div class="scroll"><table><thead><tr><th>Partition</th><th>Cases</th>'
            "<th>Baseline</th><th>Current</th><th>Within noise</th><th>Blocking</th>"
            "</tr></thead><tbody>"
        )
        for name, label in (("tuning", "Tuning"), ("held_out", "Held out")):
            row = review["partitions"][name]
            body += (
                f"<tr><td>{label}</td><td>{row['cases']}</td>"
                f"<td>{_esc(_fraction(row['baseline']))}</td>"
                f"<td>{_esc(_fraction(row['current']))}</td>"
                f"<td>{_esc(_yes(row['within_sampling_noise']))}</td>"
                f"<td>{row['blocking_changes']}</td></tr>"
            )
        body += (
            f'</tbody></table></div><p class="metadata">Split '
            f"{_esc(review['split']['source']['name'])} · SHA-256 "
            f"{_esc(review['split']['source']['sha256'])} · held-out cases: "
            f"{_esc(', '.join(review['split']['held_out_cases']))}</p>"
            f'<p class="metadata">{_esc(review["scope"])}</p>'
        )
    leakage = result.get("leakage")
    if leakage:
        body += (
            f"<h2>Harness leakage</h2><p>{len(leakage['hits'])} hit(s) in "
            f"{len(leakage['files_scanned'])} scanned file(s).</p>"
        )
        if leakage["hits"]:
            body += (
                '<div class="scroll"><table><thead><tr><th>File</th><th>Line</th><th>Case</th>'
                "<th>Partition</th><th>Role</th><th>Text</th></tr></thead><tbody>"
            )
            for hit in leakage["hits"]:
                tone = ' class="failed"' if hit["partition"] == "held_out" else ""
                body += (
                    f"<tr><td><code>{_esc(hit['file'])}</code></td><td>{hit['line'] or '—'}</td>"
                    f"<td><code>{_esc(hit['case_id'])}</code></td>"
                    f"<td{tone}>{_esc(hit['partition'] or '—')}</td><td>{_esc(hit['role'])}</td>"
                    f"<td>{_esc(hit['text'])}</td></tr>"
                )
            body += "</tbody></table></div>"
        body += f'<p class="metadata">{_esc(leakage["scope"])}</p>'
    return body


# --- helpers ----------------------------------------------------------------------


def _rate(run: dict, members: set[str]) -> dict:
    passed = assessed = attempts = 0
    for case_id in members:
        for check_attempts in run["cases"].get(case_id, {}).values():
            tally = _tally(check_attempts)
            passed += tally["passed"]
            assessed += tally["assessed"]
            attempts += tally["attempts"]
    return {
        "passed": passed,
        "assessed": assessed,
        "attempts": attempts,
        "pass_rate": passed / assessed if assessed else None,
    }


def _overlap(passed_a: int, assessed_a: int, passed_b: int, assessed_b: int) -> bool:
    low_a, high_a = _wilson_interval(passed_a, assessed_a)
    low_b, high_b = _wilson_interval(passed_b, assessed_b)
    return low_a <= high_b and low_b <= high_a


def harness_files(paths):
    """Yield (path, label) for scanned files; `paths` may already be (path, label) pairs.

    Pairs are used when verifying a saved report: the copies under harness/ are
    scanned under the labels the original scan reported.
    """
    if paths and isinstance(paths[0], tuple):
        yield from paths
        return
    seen, count = set(), 0
    for root in paths:
        if root.is_symlink():
            raise ValueError(f"harness path {root} is a symlink")
        if root.is_file():
            candidates = [(root, root.as_posix())]
        elif root.is_dir():
            candidates = []
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if path.is_symlink() or not path.is_file():
                    continue
                candidates.append((path, (root / relative).as_posix()))
        else:
            raise ValueError(f"harness path {root} does not exist")
        for path, label in candidates:
            resolved = path.resolve()
            if resolved in seen or path.stat().st_size > MAX_HARNESS_FILE_BYTES:
                continue
            seen.add(resolved)
            count += 1
            if count > MAX_HARNESS_FILES:
                raise ValueError(f"harness paths contain more than {MAX_HARNESS_FILES} files")
            yield path, label


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.1f} pp"


def _yes(value: bool | None) -> str:
    return "—" if value is None else ("yes" if value else "no")


def _fraction(side: dict) -> str:
    if side["pass_rate"] is None:
        return "—"
    return f"{side['passed']}/{side['assessed']} ({side['pass_rate']:.1%})"
