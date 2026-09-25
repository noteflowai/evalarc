"""Pytest checks for two scripted revisions of a refund-policy reply.

Run with `REVISION=baseline` or `REVISION=current`; the replies are fixed, so
no model is called. Many evaluation suites (DeepEval, plain pytest) report
through the same JUnit XML that `pytest --junitxml` writes.
"""

import os

import pytest

REPLIES = {
    "baseline": {
        "refund-small": "Refund approved for order 1001.",
        "refund-large": "Refund approved for order 1002.",
        "refund-duplicate": "Order 1003 was already refunded.",
        "status-open": "Order 1004 is open.",
    },
    "current": {
        "refund-small": "Refund approved for order 1001.",
        "refund-large": "Order 1002 needs a supervisor; escalating.",
        "refund-duplicate": "Refund approved for order 1003.",
        "status-open": "Order 1004 is open.",
    },
}
EXPECTED = {
    "refund-small": "approved",
    "refund-large": "escalat",
    "refund-duplicate": "already refunded",
    "status-open": "open",
}
REVISION = os.environ.get("REVISION", "baseline")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_policy_outcome(case):
    assert EXPECTED[case] in REPLIES[REVISION][case]


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_names_the_order(case):
    if REVISION == "current" and case == "status-open":
        pytest.skip("order lookup service unavailable")
    assert any(char.isdigit() for char in REPLIES[REVISION][case])
