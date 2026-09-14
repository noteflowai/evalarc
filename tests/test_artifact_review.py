import json

from evalarc.artifact_review import CANARY, EXPECTED, controls, review


def test_control_suite_distinguishes_workflow_claims_and_artifacts(tmp_path):
    result = controls(tmp_path / "controls")
    assert len(result["controls"]) == 8
    assert result["false_acceptances"] == result["false_rejections"] == 0


def test_internal_staging_is_allowed_but_public_symlinks_are_rejected(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "private").mkdir()
    (tmp_path / "private/client.json").write_text(json.dumps({"note": CANARY}))
    report = tmp_path / "public/report.json"
    report.write_text(json.dumps(EXPECTED))
    assert review(tmp_path)["accepted"]
    report.unlink()
    report.symlink_to(tmp_path / "private/client.json")
    result = review(tmp_path)
    assert not result["accepted"]
    assert result["errors"] == ["symlink output: public/report.json"]
