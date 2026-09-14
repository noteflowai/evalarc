"""An assessed surviving control is zero coverage, not an absent measurement."""

import importlib

from evalarc.runner import Runtime


def test_surviving_controls_are_included_in_the_weakest_margin(monkeypatch):
    module = importlib.import_module("evalarc.audit")
    monkeypatch.setattr(
        module,
        "evaluate",
        lambda *args, **kwargs: {
            "valid": True,
            "resolved": True,
            "score": 1.0,
            "candidate_sha256": "0" * 64,
            "cases": [{"case_id": "permissive", "checks": {}}],
        },
    )
    result = module.audit(Runtime(backend="local"), [17])
    assert result["valid"] and not result["passed"]
    assert result["mutation_score"] == 0
    assert result["detection"]["weakest_margin"] == 0
    assert result["detection"]["single_case_detections"] == []
