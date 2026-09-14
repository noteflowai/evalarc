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
