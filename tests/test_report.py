from evalarc.report import render_audit


def test_report_escapes_external_content(tmp_path):
    malicious = '<script>alert("x")</script>'
    report = {
        "killed": 1,
        "total": 1,
        "mutants": [
            {
                "name": malicious,
                "target_dimension": malicious,
                "score": 0,
                "killed": True,
                "failing_cases": [malicious],
            }
        ],
        "reference": {
            "score": 1,
            "runtime": {"backend": "local", "image_id": None},
            "dimensions": {},
            "task": {"id": malicious, "version": "0.1"},
            "seeds": [17],
            "grader_sha256": "abc",
            "cases_sha256": "def",
            "created_at": "2026-09-14",
        },
    }
    path = tmp_path / "index.html"
    render_audit(report, path)
    text = path.read_text()
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "Content-Security-Policy" in text
    assert "single-case dependency" in text
    assert '<div id="fault-0">' in text
    assert '<a href="#fault-0">' in text


def test_audit_report_uses_distinct_recorded_cases_and_preserves_unassessed(tmp_path):
    import json
    from pathlib import Path

    original = Path(__file__).resolve().parents[1] / "examples/audit/audit.json"
    data = json.loads(original.read_text())
    row = data["mutants"][0]
    row["failing_cases"] = ["one-case", "one-case"]
    row["detection_margin"] = 99  # Stale summaries cannot inflate the display.
    second = data["mutants"][1]
    second["valid"] = False
    data["valid"] = False
    path = tmp_path / "index.html"
    render_audit(data, path)
    text = path.read_text()
    assert "99" not in text.split("Inspect the detecting cases")[0]
    assert "Invalid audit: environment failure" in text
    assert "memory-only · unassessed" in text
    assert "one-case, one-case" not in text
