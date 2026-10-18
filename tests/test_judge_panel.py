"""judge-score with several annotators, and unsure answers in pairwise packets."""

import json

import pytest

from evalarc.cli import main
from evalarc.judging import _cohen, _fleiss, annotator_agreement, consensus_answers, score
from tests.test_judging import INSPECT, make_packet


def verdicts(tmp_path, packet_dir, answers, name, judge=None):
    key = json.loads((packet_dir / "key.json").read_text())
    template = json.loads((packet_dir / "share/verdicts.template.json").read_text())
    for item_id, hidden in key["items"].items():
        template["verdicts"][item_id] = answers(item_id, hidden)
    template["judge"] = judge or {"kind": "human", "description": name}
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(template))
    return path


def truth(item_id, hidden):
    return "pass" if hidden["recorded_passed"] else "fail"


def flipped(*ids):
    def answer(item_id, hidden):
        value = truth(item_id, hidden)
        if item_id in ids:
            return "fail" if value == "pass" else "pass"
        return value

    return answer


# --- statistics against hand computations -----------------------------------------


def test_cohen_kappa_matches_a_hand_computation():
    # 10 items: both pass 4, both fail 3, a pass/b fail 2, a fail/b pass 1.
    pairs = [("p", "p")] * 4 + [("f", "f")] * 3 + [("p", "f")] * 2 + [("f", "p")]
    # observed 0.7; a pass 0.6, b pass 0.5; expected 0.6*0.5 + 0.4*0.5 = 0.5
    assert _cohen(pairs, ["p", "f"]) == pytest.approx(0.4)
    assert _cohen([("p", "p")] * 3, ["p", "f"]) is None  # chance agreement is 1


def test_fleiss_kappa_matches_the_textbook_example():
    # Fleiss (1971)-style toy: 3 raters, 4 items, 2 categories.
    rows = [["a", "a", "a"], ["a", "a", "b"], ["b", "b", "b"], ["a", "b", "b"]]
    # P_i = 1, 1/3, 1, 1/3 -> P_bar = 2/3; p_a = 6/12, p_b = 6/12 -> P_e = 0.5
    assert _fleiss(rows, ["a", "b"]) == pytest.approx((2 / 3 - 0.5) / 0.5)
    assert _fleiss([], ["a", "b"]) is None


def test_consensus_rules_and_unsure():
    marks = [
        {"x": "pass", "y": "pass", "z": "unsure", "w": "pass"},
        {"x": "pass", "y": "fail", "z": "pass", "w": None},
        {"x": "fail", "y": "fail", "z": "unsure", "w": "pass"},
    ]
    items = ["w", "x", "y", "z"]
    majority, undecided = consensus_answers(marks, items, ["pass", "fail"], "majority")
    assert majority == {"w": "pass", "x": "pass", "y": "fail"}
    assert undecided == ["z"]  # unsure never counts toward a majority
    unanimous, undecided = consensus_answers(marks, items, ["pass", "fail"], "unanimous")
    assert unanimous == {} and undecided == items
    two = [{"x": "pass"}, {"x": "fail"}]
    assert consensus_answers(two, ["x"], ["pass", "fail"], "majority") == ({}, ["x"])
    agreement = annotator_agreement(marks, items, ["pass", "fail"])
    pair01 = agreement["pairs"][0]
    assert pair01["annotators"] == [0, 1] and pair01["items"] == 2 and pair01["agreement"] == 0.5
    assert agreement["fleiss_items"] == 2  # only x and y are decided by everyone


# --- scoring ----------------------------------------------------------------------


def test_panel_scores_the_grader_against_consensus(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=10)
    a = verdicts(tmp_path, packet_dir, truth, "a")
    b = verdicts(tmp_path, packet_dir, flipped("item-001"), "b")
    c = verdicts(tmp_path, packet_dir, flipped("item-002"), "c")
    result = score(packet_dir, [a, b, c], min_agreement=0.95, min_annotator_agreement=0.8)
    # Each flip is outvoted, so the consensus equals the recorded grader everywhere.
    assert result["agreement"] == 1.0 and result["consensus"]["undecided"] == []
    assert result["judge"] == {"kind": "consensus", "description": "majority of 3 annotators"}
    assert [pair["agreement"] for pair in result["annotator_agreement"]["pairs"]] == [
        0.9,
        0.9,
        0.8,
    ]
    assert result["gate"]["passed"] is True and result["gate"]["judge_gate_passed"] is True
    both = score(packet_dir, [a, b, c], min_agreement=0.95, min_annotator_agreement=0.85)
    assert both["gate"]["judge_gate_passed"] is True and both["gate"]["passed"] is False
    strict = score(packet_dir, [a, b, c], min_annotator_agreement=0.85)
    assert strict["gate"] == {
        "min_annotator_agreement": 0.85,
        "passed": False,
        "reason": "annotators_disagree",
    }
    unanimous = score(packet_dir, [a, b, c], consensus="unanimous")
    assert unanimous["consensus"]["undecided"] == ["item-001", "item-002"]
    assert unanimous["decided"] == 8


def test_panel_flags_a_self_judging_annotator_and_missing_answers(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=6)
    key = json.loads((packet_dir / "key.json").read_text())
    subject = key["subject_models"][0]
    a = verdicts(tmp_path, packet_dir, truth, "a")
    b = verdicts(
        tmp_path,
        packet_dir,
        lambda i, h: None if i == "item-001" else truth(i, h),
        "b",
        judge={"kind": "model", "model": subject},
    )
    result = score(packet_dir, [a, b], min_agreement=0.5)
    assert result["self_judged"] is True and result["missing"] == ["item-001"]
    assert [item["self_judged"] for item in result["annotators"]] == [False, True]
    assert result["gate"]["passed"] is False


def test_panel_input_errors(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=4)
    a = verdicts(tmp_path, packet_dir, truth, "a")
    copy = tmp_path / "copy.json"
    copy.write_bytes(a.read_bytes())
    with pytest.raises(ValueError, match="byte-identical"):
        score(packet_dir, [a, copy])
    with pytest.raises(ValueError, match="appear once"):
        score(packet_dir, [a, a])
    with pytest.raises(ValueError, match="two or more"):
        score(packet_dir, [a], min_annotator_agreement=0.5)
    b = verdicts(tmp_path, packet_dir, flipped("item-001"), "b")
    with pytest.raises(ValueError, match="--consensus"):
        score(packet_dir, [a, b], consensus="mean")
    other = make_packet(tmp_path / "o", "grader", "current", sample=4, seed=9)
    c = verdicts(tmp_path, other, truth, "c")
    with pytest.raises(ValueError, match="c.json: verdicts were recorded for a different packet"):
        score(packet_dir, [a, c])


def test_single_file_output_is_unchanged(tmp_path, capsys):
    """One verdicts file keeps the 0.20.0 result keys and the verdicts.json copy."""
    packet_dir = make_packet(tmp_path, "grader", "current", sample=6)
    a = verdicts(tmp_path, packet_dir, truth, "a")
    out = tmp_path / "score"
    assert main(["judge-score", str(packet_dir), str(a), "--output", str(out)]) == 0
    result = json.loads((out / "score.json").read_text())
    assert "annotators" not in result and "consensus" not in result
    assert isinstance(result["verdicts_sha256"], str)
    assert sorted(p.name for p in out.iterdir()) == [
        "index.html",
        "score.json",
        "summary.md",
        "verdicts.json",
    ]


def test_panel_cli_writes_every_verdicts_file_and_exits_by_gate(tmp_path, capsys):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=10)
    a = verdicts(tmp_path, packet_dir, truth, "a")
    b = verdicts(tmp_path, packet_dir, flipped("item-001", "item-002", "item-003"), "b")
    out = tmp_path / "panel"
    args = ["judge-score", str(packet_dir), str(a), str(b), "--output", str(out)]
    assert main([*args, "--min-annotator-agreement", "0.9"]) == 1
    assert (out / "verdicts-01.json").is_file() and (out / "verdicts-02.json").is_file()
    summary = (out / "summary.md").read_text()
    assert "lowest pairwise agreement 70.0%" in summary and "**fail**" in summary
    html = (out / "index.html").read_text()
    assert "<h2>Annotators</h2>" in html and "annotators disagree" in html


def test_annotator_names_are_escaped(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=4)
    a = verdicts(tmp_path, packet_dir, truth, "a", judge={"kind": "human", "description": "x"})
    b = verdicts(
        tmp_path, packet_dir, truth, "b", judge={"kind": "model", "model": "<img src=x>|`\r###"}
    )
    out = tmp_path / "s"
    assert main(["judge-score", str(packet_dir), str(a), str(b), "--output", str(out)]) == 0
    assert "<img" not in (out / "index.html").read_text()
    assert not any(
        line.startswith("###") for line in (out / "summary.md").read_text().splitlines()[1:]
    )


# --- pairwise unsure --------------------------------------------------------------


def test_pairwise_unsure_is_opt_in_and_excluded_from_the_win_rate(tmp_path, capsys):
    base = [
        "judge-packet",
        "pairwise",
        str(INSPECT / "baseline.json"),
        str(INSPECT / "current.json"),
    ]
    default = tmp_path / "default"
    assert main([*base, "--output", str(default)]) == 0
    assert json.loads((default / "share/packet.json").read_text())["allowed_verdicts"] == [
        "A",
        "B",
        "tie",
    ]
    unsure_dir = tmp_path / "unsure"
    assert main([*base, "--allow-unsure", "--output", str(unsure_dir)]) == 0
    packet = json.loads((unsure_dir / "share/packet.json").read_text())
    assert packet["allowed_verdicts"] == ["A", "B", "tie", "unsure"]
    assert "unsure" in packet["instructions"]
    first = sorted(json.loads((unsure_dir / "key.json").read_text())["items"])[0]

    def answer(item_id, hidden):
        return "unsure" if item_id == first else hidden["current_is"]

    path = verdicts(tmp_path, unsure_dir, answer, "u")
    result = score(unsure_dir, path)
    assert result["unsure"] == 1 and result["current_win_rate"] == 1.0
    assert result["current_wins"] == len(packet["items"]) - 1
    # The default packet still rejects unsure, and its result has no unsure key.
    bad = verdicts(tmp_path, default, lambda i, h: "unsure", "bad")
    with pytest.raises(ValueError, match="answer must be one of A, B, tie"):
        score(default, bad)
    ok = verdicts(tmp_path, default, lambda i, h: h["current_is"], "ok")
    assert "unsure" not in score(default, ok)
    capsys.readouterr()
    assert (
        main(
            [
                "judge-packet",
                "grader",
                str(INSPECT / "current.json"),
                "--allow-unsure",
                "--output",
                str(tmp_path / "g"),
            ]
        )
        == 2
    )
    assert "applies to pairwise" in capsys.readouterr().err


def test_shared_unsure_is_undecided_not_a_consensus(tmp_path):
    packet_dir = make_packet(tmp_path, "grader", "current", sample=4)

    def unsure_first(item_id, hidden):
        return "unsure" if item_id == "item-001" else truth(item_id, hidden)

    a = verdicts(tmp_path, packet_dir, unsure_first, "a")
    b = verdicts(
        tmp_path, packet_dir, unsure_first, "b", judge={"kind": "human", "description": "b"}
    )
    result = score(packet_dir, [a, b])
    assert result["consensus"]["undecided"] == ["item-001"]
    assert result["annotator_agreement"]["pairs"][0]["items"] == 3
    assert result["annotator_agreement"]["fleiss_items"] == 3
