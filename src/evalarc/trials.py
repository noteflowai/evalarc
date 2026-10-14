"""Case-level trial outcomes, pass@k and pass^k for ``evalarc eval-health``.

A trial is one recorded attempt of a case (an Inspect epoch, a promptfoo repeat, a
repeated JUnit testcase). A trial fails when any check recorded for it failed. Otherwise
it is unassessed when a check has no outcome (error, timeout, skip), when it lacks a
check the case recorded on another attempt, when the Inspect sample itself recorded an
error, or when it has no checks at all; it succeeds only when none of these apply.
Unassessed trials are reported but excluded from the denominators, so missing evidence
never counts as a pass.

For a case with n assessed trials of which c succeeded, and k <= n:

* pass@k = 1 - C(n - c, k) / C(n, k): the chance that at least one of k trials drawn
  without replacement succeeds (the unbiased estimator of Chen et al., 2021).
* pass^k = C(c, k) / C(n, k): the chance that all k drawn trials succeed (Yao et al.,
  2024, tau-bench). At k = 1 both equal c / n; as k grows they diverge.

Rates average cases with at least k assessed trials. Cases are weighted equally, so a
case with many checks counts as much as a case with one.
"""

from __future__ import annotations

from math import comb

MAX_K = 10
# Placeholder checks results_diff records for an attempt that produced no scores. They
# mark that attempt unassessed; other attempts are not expected to carry them.
ERROR_CHECKS = {"sample error", "provider error"}
DEFINITION = (
    "A trial is one recorded attempt of a case; it succeeds only when every check recorded "
    "for it passed, and trials with no outcome are excluded. pass@k is the chance that at "
    "least one of k trials succeeds, pass^k the chance that all k succeed (unbiased "
    "estimators from n assessed trials, k <= n), averaged over cases with at least k "
    "assessed trials. pass@k suits tools where one success is enough; pass^k suits agents "
    "users expect to succeed every time."
)


def case_trials(run: dict) -> dict[str, dict]:
    """Per case: recorded, assessed and successful trials, in recorded order."""
    out: dict[str, dict] = {}
    samples = run.get("samples") or {}
    for case_id, checks in run["cases"].items():
        names = set(checks) - ERROR_CHECKS
        metas = samples.get(case_id)
        if metas:
            outcomes = [
                _trial(meta.get("verdicts") or {}, names, bool(meta.get("errored")))
                for meta in metas
            ]
        else:
            # Formats without per-attempt metadata (JUnit): align attempts by position.
            width = max((len(attempts) for attempts in checks.values()), default=0)
            outcomes = [
                _trial(
                    {
                        name: attempts[i]["passed"]
                        for name, attempts in checks.items()
                        if i < len(attempts)
                    },
                    names,
                )
                for i in range(width)
            ]
        assessed = [outcome for outcome in outcomes if outcome is not None]
        out[case_id] = {
            "trials": len(outcomes),
            "assessed": len(assessed),
            "successes": sum(assessed),
        }
    return out


def _trial(verdicts: dict, expected: set, errored: bool = False) -> bool | None:
    """False if any check failed; None if an outcome or check is missing; else True."""
    if any(verdict is False for verdict in verdicts.values()):
        return False
    if (
        errored
        or not verdicts
        or any(verdict is None for verdict in verdicts.values())
        or not expected <= set(verdicts)
    ):
        return None
    return True


def pass_at_k(n: int, c: int, k: int) -> float:
    if not 0 < k <= n or not 0 <= c <= n:
        raise ValueError("pass@k needs 0 < k <= n and 0 <= c <= n")
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    if not 0 < k <= n or not 0 <= c <= n:
        raise ValueError("pass^k needs 0 < k <= n and 0 <= c <= n")
    return comb(c, k) / comb(n, k)


def summarize(run: dict) -> dict:
    """Trial counts and pass@k / pass^k for k = 1 .. min(MAX_K, most assessed trials)."""
    cases = case_trials(run)
    assessed = [item["assessed"] for item in cases.values()]
    largest = min(MAX_K, max(assessed, default=0))
    by_k = []
    for k in range(1, largest + 1):
        eligible = [item for item in cases.values() if item["assessed"] >= k]
        by_k.append(
            {
                "k": k,
                "cases": len(eligible),
                "pass_at_k": _round(
                    sum(pass_at_k(i["assessed"], i["successes"], k) for i in eligible)
                    / len(eligible)
                ),
                "pass_hat_k": _round(
                    sum(pass_hat_k(i["assessed"], i["successes"], k) for i in eligible)
                    / len(eligible)
                ),
            }
        )
    total = sum(item["trials"] for item in cases.values())
    return {
        "file": run["source"]["name"],
        "cases": len(cases),
        "trials": total,
        "assessed_trials": sum(assessed),
        "unassessed_trials": total - sum(assessed),
        "successful_trials": sum(item["successes"] for item in cases.values()),
        "cases_without_assessed_trials": sorted(
            case for case, item in cases.items() if not item["assessed"]
        ),
        "min_assessed_trials": min(assessed, default=0),
        "by_k": by_k,
        "per_case": dict(sorted(cases.items())),
    }


def _round(value: float) -> float:
    # Rounded so reports recompute byte-identically across platforms.
    return round(value, 6)


def suite_findings(
    trials: dict, suites: dict[str, str], last_file: str, shown_file: str, finding
) -> list[dict]:
    """Capability/regression findings for the last file, from declared suite roles.

    ``shown_file`` is the file name already formatted for finding messages. Regression
    cases should succeed on every trial: any failed, unassessed or missing trial is a
    warning. Capability cases that succeeded on every one of at least two
    assessed trials are reported as candidates to graduate into the regression suite.
    """
    per_case = trials["per_case"]
    out = []
    failing = []
    for case_id in sorted(case for case, role in suites.items() if role == "regression"):
        item = per_case.get(case_id)
        if item is None:
            detail = "not recorded in the last file"
        elif not item["assessed"]:
            detail = f"0 of {item['trials']} trial(s) assessed"
        elif item["successes"] < item["assessed"] or item["assessed"] < item["trials"]:
            detail = f"{item['successes']}/{item['assessed']} assessed trial(s) succeeded" + (
                f", {item['trials'] - item['assessed']} unassessed"
                if item["assessed"] < item["trials"]
                else ""
            )
        else:
            continue
        failing.append(_item(last_file, case_id, item, detail))
    if failing:
        out.append(
            finding(
                "regression_case_failing",
                "warning",
                f"{len(failing)} regression-suite case(s) did not succeed on every trial of "
                f"{shown_file}. A regression suite should pass close to 100%; a failing, "
                "unassessed or missing regression case means something the agent used to "
                "do is broken or unmeasured. Fix it before tuning capability cases.",
                items=failing,
            )
        )
    ready = []
    for case_id in sorted(case for case, role in suites.items() if role == "capability"):
        item = per_case.get(case_id)
        if (
            item
            and item["assessed"] >= 2
            and item["successes"] == item["assessed"] == item["trials"]
        ):
            ready.append(
                _item(last_file, case_id, item, f"{item['successes']}/{item['trials']} trials")
            )
    if ready:
        out.append(
            finding(
                "graduation_candidates",
                "info",
                f"{len(ready)} capability case(s) succeeded on every trial of {shown_file}. "
                "They no longer give a hill to climb; consider moving them to the regression "
                'suite (set "suite": "regression" in the case manifest) and adding harder '
                "capability cases.",
                items=ready,
            )
        )
    return out


def _item(file: str, case_id: str, item: dict | None, detail: str) -> dict:
    item = item or {"trials": 0, "assessed": 0, "successes": 0}
    return {
        "file": file,
        "case_id": case_id,
        "check": "(case)",
        "passed": item["successes"],
        "assessed": item["assessed"],
        "attempts": item["trials"],
        "detail": detail,
    }
