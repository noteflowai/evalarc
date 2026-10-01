"""Recorded cost, token and duration usage for ``evalarc diff``.

When an evaluation is close to saturation, the useful change is often the same
quality at lower cost. This module reads the usage each tool recorded per attempt,
compares matched cases between two runs, and applies an optional cost ratio gate.
EvalArc never estimates prices: cost is only what the source tool recorded.
"""

from __future__ import annotations

import math

METRICS = (
    "cost_usd",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "duration_seconds",
)
COST_METRICS = {"cost": "cost_usd", "tokens": "total_tokens", "duration": "duration_seconds"}
USAGE_SCOPE = (
    "Usage is what the source tool recorded per attempt, averaged over cases present in "
    "both runs; missing values stay unknown and are never counted as zero. EvalArc does "
    "not price tokens. Token counts from different models use different tokenizers and "
    "prices, so compare recorded cost when models differ. Durations are the tool's own "
    "timing (Inspect sample working time, promptfoo provider latency, JUnit test time); "
    "a JUnit duration measures the test, which may not include the agent. Ratios come "
    "from single runs and carry no interval."
)


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def inspect_usage(sample: dict) -> dict:
    """Sum Inspect per-model usage for one sample; durations prefer working time."""
    usage: dict = {}
    models = sample.get("model_usage")
    if isinstance(models, dict):
        for item in models.values():
            if not isinstance(item, dict):
                continue
            for key, name in (
                ("total_cost", "cost_usd"),
                ("total_tokens", "total_tokens"),
                ("input_tokens", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("input_tokens_cache_read", "cached_input_tokens"),
                ("reasoning_tokens", "reasoning_tokens"),
            ):
                value = number(item.get(key))
                if value is not None:
                    usage[name] = usage.get(name, 0.0) + value
    duration = number(sample.get("working_time"))
    if duration is None:
        duration = number(sample.get("total_time"))
    if duration is not None:
        usage["duration_seconds"] = duration
    return usage


def promptfoo_usage(row: dict) -> dict:
    usage: dict = {}
    cost = number(row.get("cost"))
    if cost is not None:
        usage["cost_usd"] = cost
    tokens = row.get("tokenUsage")
    if isinstance(tokens, dict):
        for key, name in (
            ("total", "total_tokens"),
            ("prompt", "input_tokens"),
            ("completion", "output_tokens"),
            ("cached", "cached_input_tokens"),
        ):
            value = number(tokens.get(key))
            if value is not None:
                usage[name] = value
        details = tokens.get("completionDetails")
        if isinstance(details, dict):
            value = number(details.get("reasoning"))
            if value is not None:
                usage["reasoning_tokens"] = value
    latency = number(row.get("latencyMs"))
    if latency is not None:
        usage["duration_seconds"] = latency / 1000
    return usage


def junit_usage(case) -> dict:
    try:
        duration = number(float(case.get("time")))
    except (TypeError, ValueError):
        duration = None
    return {} if duration is None else {"duration_seconds": duration}


def compare_usage(baseline: dict, current: dict) -> dict:
    """Mean usage per attempt over cases recorded in both runs."""
    matched = sorted(set(baseline["cases"]) & set(current["cases"]))
    metrics = {}
    for name in METRICS:
        sides = {
            label: _side(run.get("usage", {}), matched, name)
            for label, run in (("baseline", baseline), ("current", current))
        }
        if not sides["baseline"]["reported"] and not sides["current"]["reported"]:
            continue
        before, after = sides["baseline"]["mean"], sides["current"]["mean"]
        sides["ratio"] = after / before if before and after is not None else None
        sides["complete"] = all(
            side["reported"] == side["attempts"] for side in (sides["baseline"], sides["current"])
        )
        metrics[name] = sides
    result = {"matched_cases": len(matched), "metrics": metrics, "scope": USAGE_SCOPE}
    cached, inputs = metrics.get("cached_input_tokens"), metrics.get("input_tokens")
    if cached and inputs:
        # Share of input tokens read from the prompt cache: a main cost driver.
        result["cache_read_share"] = {
            side: (
                cached[side]["total"] / inputs[side]["total"]
                if cached[side]["total"] is not None and inputs[side]["total"]
                else None
            )
            for side in ("baseline", "current")
        }
    return result


def cost_gate(usage: dict, metric: str, max_ratio: float) -> dict:
    """Require current mean usage per attempt <= max_ratio x baseline."""
    if not math.isfinite(max_ratio) or max_ratio <= 0:
        raise ValueError("--max-cost-ratio must be a positive number")
    if metric == "auto":
        chosen = next(
            (
                name
                for name in ("cost_usd", "total_tokens")
                if _gateable(usage["metrics"].get(name))
            ),
            None,
        )
        if chosen is None:
            raise ValueError(
                "neither run records cost or total tokens on every attempt of the matched "
                "cases with a nonzero baseline; pass --cost-metric duration to gate on "
                "recorded durations"
            )
    else:
        chosen = COST_METRICS[metric]
        if not _gateable(usage["metrics"].get(chosen)):
            raise ValueError(
                f"{chosen} is not recorded on every attempt of the matched cases in both "
                "runs, or its baseline mean is zero; the cost gate cannot be assessed"
            )
    row = usage["metrics"][chosen]
    return {
        "metric": chosen,
        "max_ratio": max_ratio,
        "baseline_mean": row["baseline"]["mean"],
        "current_mean": row["current"]["mean"],
        "ratio": row["ratio"],
        "passed": row["ratio"] <= max_ratio,
    }


def shown(result: dict) -> bool:
    """Render usage when cost or tokens were recorded, or a cost gate was requested."""
    if result.get("cost_gate"):
        return True
    metrics = (result.get("usage") or {}).get("metrics", {})
    return any(
        metrics.get(name) and any(metrics[name][side]["total"] for side in ("baseline", "current"))
        for name in ("cost_usd", "total_tokens")
    )


def render_markdown(result: dict) -> str:
    usage, gate = result["usage"], result.get("cost_gate")
    lines = ["#### Cost and usage", ""]
    if gate:
        lines += [
            f"Cost gate on `{gate['metric']}`: current/baseline = {gate['ratio']:.3f} "
            f"(limit {gate['max_ratio']:g}) — **{'pass' if gate['passed'] else 'fail'}**.",
            "",
        ]
    lines += [
        f"Mean per attempt over {usage['matched_cases']} matched case(s).",
        "",
        "| Metric | Baseline | Current | Ratio | Reported attempts |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, row in usage["metrics"].items():
        ratio = "—" if row["ratio"] is None else f"{row['ratio']:.3f}"
        lines.append(
            f"| `{name}` | {_value(row['baseline']['mean'], name)} | "
            f"{_value(row['current']['mean'], name)} | {ratio} | "
            f"{row['baseline']['reported']}/{row['baseline']['attempts']} → "
            f"{row['current']['reported']}/{row['current']['attempts']} |"
        )
    share = usage.get("cache_read_share")
    if share and any(value is not None for value in share.values()):
        lines += [
            "",
            "Prompt cache reads: "
            + " → ".join(
                "—" if share[s] is None else f"{share[s]:.1%}" for s in ("baseline", "current")
            )
            + " of input tokens.",
        ]
    lines += ["", f"<sub>{usage['scope']}</sub>", ""]
    return "\n".join(lines) + "\n"


def render_html(result: dict) -> str:
    from evalarc.report import _card, _esc

    usage, gate = result["usage"], result.get("cost_gate")
    body = "<h2>Cost and usage</h2>"
    if gate:
        # gate["metric"] is always one of METRICS; _card escapes the label anyway.
        body += (
            '<div class="cards">'
            + _card(
                f"{gate['ratio']:.3f}",
                f"{gate['metric']} ratio (limit {gate['max_ratio']:g})",
                alert=not gate["passed"],
            )
            + "</div>"
        )
    body += (
        f"<p>Mean per attempt over {usage['matched_cases']} matched case(s).</p>"
        '<div class="scroll"><table><thead><tr><th>Metric</th><th>Baseline</th>'
        "<th>Current</th><th>Ratio</th><th>Reported attempts</th></tr></thead><tbody>"
    )
    for name, row in usage["metrics"].items():
        ratio = "—" if row["ratio"] is None else f"{row['ratio']:.3f}"
        body += (
            f"<tr><td><code>{_esc(name)}</code></td>"
            f"<td>{_esc(_value(row['baseline']['mean'], name))}</td>"
            f"<td>{_esc(_value(row['current']['mean'], name))}</td><td>{_esc(ratio)}</td>"
            f"<td>{row['baseline']['reported']}/{row['baseline']['attempts']} → "
            f"{row['current']['reported']}/{row['current']['attempts']}</td></tr>"
        )
    return body + f'</tbody></table></div><p class="metadata">{_esc(usage["scope"])}</p>'


def _side(usage: dict, cases: list[str], name: str) -> dict:
    attempts = reported = 0
    total = 0.0
    for case_id in cases:
        for item in usage.get(case_id, []):
            attempts += 1
            if name in item:
                reported += 1
                total += item[name]
    return {
        "attempts": attempts,
        "reported": reported,
        "total": total if reported else None,
        "mean": total / reported if reported else None,
    }


def _gateable(row: dict | None) -> bool:
    return bool(
        row
        and row["complete"]
        and row["baseline"]["attempts"]
        and row["current"]["attempts"]
        and row["baseline"]["mean"]
        and row["ratio"] is not None
    )


def _value(value: float | None, name: str) -> str:
    if value is None:
        return "—"
    if name == "cost_usd":
        return f"${value:.6f}".rstrip("0").rstrip(".") if value else "$0"
    if name == "duration_seconds":
        return f"{value:.3f} s"
    return f"{value:,.1f}".rstrip("0").rstrip(".")
