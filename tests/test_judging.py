import json
from pathlib import Path

import pytest

from evalarc.cli import main
from evalarc.eval_health import health
from evalarc.judging import prepare, score
from evalarc.provenance import load as load_manifest
from evalarc.results_diff import load_results

ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "examples/results-diff/inspect"


def runs(*names):
    return [load_results(INSPECT / f"{name}.json") for name in names]


def make_packet(tmp_path, mode, *names, sample=40, seed=0):
    output = tmp_path / f"packet-{mode}"
    assert (
        main(
            [
                "judge-packet",
                mode,
                *(str(INSPECT / f"{name}.json") for name in names),
                "--sample",
                str(sample),
                "--seed",
                str(seed),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    return output


def write_verdicts(tmp_path, packet_dir, answer, judge=None):
    key = json.loads((packet_dir / "key.json").read_text())
    template = json.loads((packet_dir / "share/verdicts.template.json").read_text())
    for item_id, hidden in key["items"].items():
        template["verdicts"][item_id] = answer(item_id, hidden)
    if judge:
        template["judge"] = judge
    path = tmp_path / f"verdicts-{packet_dir.name}.json"
    path.write_text(json.dumps(template))
    return path


# --- grader spot check ------------------------------------------------------------


def test_grader_packet_is_stratified_and_hides_verdicts(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=10)
    share = sorted(p.name for p in (packet_dir / "share").iterdir())
    assert share == ["index.html", "packet.json", "verdicts.template.json"]
    shared_text = "".join(p.read_text() for p in (packet_dir / "share").iterdir())
    assert "recorded_passed" not in shared_text and "seed" not in shared_text
    key = json.loads((packet_dir / "key.json").read_text())
    verdicts = [item["recorded_passed"] for item in key["items"].values()]
    # current.json has 27 passing and 5 failing check attempts: every failure is sampled.
    assert verdicts.count(False) == 5 and verdicts.count(True) == 5
    assert key["eligible"] == 32
    packet = json.loads((packet_dir / "share/packet.json").read_text())
    assert {"input", "expected", "output", "check"} <= set(packet["items"][0])


def test_grader_agreement_kappa_and_gate(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=10)
    flip = {"item-001", "item-002"}

    def answer(item_id, hidden):
        agrees = hidden["recorded_passed"] != (item_id in flip)
        return "pass" if agrees else "fail"

    verdicts = write_verdicts(tmp_path, packet_dir, answer)
    result = score(packet_dir, verdicts, min_agreement=0.75)
    assert result["agreement"] == 0.8 and result["decided"] == 10
    assert result["confusion"]["false_accept"] + result["confusion"]["false_reject"] == 2
    assert {row["item_id"] for row in result["disagreements"]} == flip
    assert -1 <= result["cohen_kappa"] <= 1
    assert result["gate"]["passed"] is True
    assert score(packet_dir, verdicts, min_agreement=0.9)["gate"]["passed"] is False


def test_unanswered_and_unsure_items(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=6)
    verdicts = write_verdicts(
        tmp_path, packet_dir, lambda item_id, hidden: None if item_id == "item-001" else "unsure"
    )
    result = score(packet_dir, verdicts, min_agreement=0.5)
    assert result["missing"] == ["item-001"] and not result["complete"]
    assert result["unsure"] == 5 and result["agreement"] is None
    assert result["gate"]["passed"] is False


# --- pairwise -------------------------------------------------------------------


def test_pairwise_packet_randomizes_and_skips_identical_outputs(tmp_path):
    packet_dir = make_packet(tmp_path, "pairwise", "baseline", "current", seed=3)
    key = json.loads((packet_dir / "key.json").read_text())
    assert key["skipped"] == {"identical_outputs": 7, "unmatched_attempts": 0}
    positions = {hidden["current_is"] for hidden in key["items"].values()}
    assert positions == {"A", "B"}
    packet = json.loads((packet_dir / "share/packet.json").read_text())
    assert "current_is" not in json.dumps(packet)
    assert {"output_a", "output_b"} <= set(packet["items"][0])


def test_pairwise_score_unblinds_and_flags_self_judging(tmp_path, capsys):
    packet_dir = make_packet(tmp_path, "pairwise", "baseline", "current", seed=3)
    prefer_current = write_verdicts(tmp_path, packet_dir, lambda i, h: h["current_is"])
    result = score(packet_dir, prefer_current, require_current_preferred=True)
    assert result["current_wins"] == 9 and result["baseline_wins"] == 0
    assert result["state"] == "current_preferred" and result["gate"]["passed"]
    self_judged = write_verdicts(
        tmp_path,
        packet_dir,
        lambda i, h: h["current_is"],
        judge={"kind": "model", "model": "mockllm/model"},
    )
    flagged = score(packet_dir, self_judged, require_current_preferred=True)
    assert flagged["self_judged"] and not flagged["gate"]["passed"]
    always_a = write_verdicts(tmp_path, packet_dir, lambda i, h: "A")
    biased = score(packet_dir, always_a)
    assert biased["position_a_rate"] == 1.0 and biased["position_bias"] is True
    assert (
        main(["judge-score", str(packet_dir), str(self_judged), "--require-current-preferred"]) == 1
    )
    assert "model under evaluation" in capsys.readouterr().out


def test_score_rejects_tampering_and_bad_verdicts(tmp_path, capsys):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=4)
    good = write_verdicts(tmp_path, packet_dir, lambda i, h: "pass")
    bad = json.loads(good.read_text())
    bad["verdicts"]["item-001"] = "maybe"
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    assert main(["judge-score", str(packet_dir), str(tmp_path / "bad.json")]) == 2
    assert "must be one of" in capsys.readouterr().err
    other = dict(bad, packet_sha256="0" * 64)
    other["verdicts"]["item-001"] = "pass"
    (tmp_path / "other.json").write_text(json.dumps(other))
    assert main(["judge-score", str(packet_dir), str(tmp_path / "other.json")]) == 2
    packet = packet_dir / "share/packet.json"
    packet.write_text(packet.read_text().replace("item-001", "item-999", 1))
    assert main(["judge-score", str(packet_dir), str(good)]) == 2
    assert "differs from the packet" in capsys.readouterr().err


def test_score_cli_writes_report(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=4)
    verdicts = write_verdicts(tmp_path, packet_dir, lambda i, h: "pass")
    output = tmp_path / "scored"
    assert main(["judge-score", str(packet_dir), str(verdicts), "--output", str(output)]) == 0
    assert sorted(p.name for p in output.iterdir()) == [
        "index.html",
        "score.json",
        "summary.md",
        "verdicts.json",
    ]


@pytest.mark.parametrize(
    "args,message",
    [
        (["grader", "baseline", "current"], "exactly one"),
        (["pairwise", "current"], "baseline and a current"),
    ],
)
def test_packet_mode_arity(tmp_path, capsys, args, message):
    mode, *names = args
    code = main(
        [
            "judge-packet",
            mode,
            *(str(INSPECT / f"{n}.json") for n in names),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert code == 2 and message in capsys.readouterr().err


def test_junit_has_no_outputs_to_judge(tmp_path, capsys):
    junit = ROOT / "examples/results-diff/junit/current.xml"
    assert main(["judge-packet", "grader", str(junit), "--output", str(tmp_path / "o")]) == 2
    assert "no attempts with recorded output text" in capsys.readouterr().err


def test_prepare_is_deterministic_for_a_seed():
    first, _ = prepare("pairwise", runs("baseline", "current"), 5, 11)
    second, _ = prepare("pairwise", runs("baseline", "current"), 5, 11)
    assert first == second


# --- provenance -----------------------------------------------------------------


def manifest(tmp_path, cases):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema_version": "evalarc.case-manifest.v1", "cases": cases}))
    return load_manifest(path)


def test_example_manifest_flags_unexplained_model_failure():
    report = health(
        runs("baseline", "current"), cases_manifest=load_manifest(INSPECT / "cases.json")
    )
    ids = {finding["id"] for finding in report["findings"]}
    assert "adversarial_sampling" in ids and "no_real_cases" not in ids
    assert report["provenance"]["counts"] == {
        "production": 2,
        "bug_report": 1,
        "support_ticket": 3,
        "synthetic": 1,
        "model_failure": 1,
    }


def test_synthetic_only_and_traffic_only(tmp_path):
    synthetic = manifest(tmp_path, [{"match": "*", "source": "synthetic"}])
    ids = {f["id"] for f in health(runs("current"), cases_manifest=synthetic)["findings"]}
    assert {"no_real_cases", "mostly_synthetic"} <= ids
    traffic = manifest(tmp_path, [{"match": "*", "source": "user_traffic"}])
    ids = {f["id"] for f in health(runs("current"), cases_manifest=traffic)["findings"]}
    assert "traffic_only" in ids and "no_real_cases" not in ids
    partial = manifest(tmp_path, [{"match": "refund-*", "source": "production"}])
    report = health(runs("current"), cases_manifest=partial)
    assert len(report["provenance"]["undeclared"]) == 5


@pytest.mark.parametrize(
    "cases,message",
    [
        ([{"match": "x", "source": "production"}], "matches no recorded case"),
        ([{"match": "*", "source": "guess"}], "source must be one of"),
        ([{"match": "*", "source": "manual", "extra": 1}], "unknown fields"),
        ([], "non-empty"),
    ],
)
def test_invalid_manifests(tmp_path, cases, message):
    with pytest.raises(ValueError, match=message):
        health(runs("current"), cases_manifest=manifest(tmp_path, cases))
