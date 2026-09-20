import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.record_swe_pilot import (
    CONDITIONS,
    compact,
    prefix_messages,
    previous_attempt,
    require_arguments,
    schedule,
)
from scripts.swe_workspace import source_path


class SWEPilotTests(unittest.TestCase):
    def test_live_relative_source_does_not_strip_a_real_child_directory(self):
        self.assertEqual(source_path("testbed/file.txt"), "file.txt")
        self.assertEqual(source_path("./testbed/file.txt", root=None), "testbed/file.txt")

    def test_balanced_fixed_denominator_and_order_rotation(self):
        rows = schedule(["a", "b", "c"])
        self.assertEqual(len(rows), 36)
        self.assertEqual(len({(r["instance_id"], r["condition"], r["seed"]) for r in rows}), 36)
        self.assertEqual(Counter(r["condition"] for r in rows), dict.fromkeys(CONDITIONS, 9))
        self.assertEqual([r["condition"] for r in rows[:4]], list(CONDITIONS))
        self.assertNotEqual(rows[0]["condition"], rows[4]["condition"])
        self.assertNotEqual(rows[0]["condition"], rows[12]["condition"])

    def test_task_and_preload_survive_context_pressure_as_complete_groups(self):
        row = {"repo": "example/project", "problem_statement": "Repair behavior."}
        prefix = prefix_messages(row, {"content": "Frozen generic workflow."})
        groups = [
            [{"role": "assistant", "content": str(i)}, {"role": "tool", "content": "x" * 100}]
            for i in range(5)
        ]

        def measure(messages):
            return {"prompt_tokens": len(messages), "max_new_tokens": 2, "context_limit": 11}

        messages, record = compact(prefix, groups, measure)
        self.assertEqual(messages[: len(prefix)], prefix)
        self.assertEqual(record["removed_groups"], 3)
        self.assertEqual(messages[-4:], groups[3] + groups[4])
        with self.assertRaisesRegex(ValueError, "immutable prompt prefix"):
            compact(
                prefix,
                [],
                lambda _: {
                    "prompt_tokens": 100,
                    "max_new_tokens": 2,
                    "context_limit": 10,
                },
            )

    def test_malformed_tool_arguments_are_rejected_before_execution(self):
        for name, args in [
            ("unknown", {}),
            ("finish", {"command": "true"}),
            ("run_command", {}),
            ("read_file", {"path": "x", "start_line": True}),
            ("write_file", {"path": "x", "content": {"invalid": "object"}}),
        ]:
            with self.subTest(name=name, arguments=args), self.assertRaises(ValueError):
                require_arguments(name, args)
        require_arguments("read_file", {"path": "x", "start_line": 1})

    def test_resume_preserves_interruption_without_replaying_generation(self):
        planned = {"index": 0, "instance_id": "a", "condition": "none", "seed": 17}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertIsNone(previous_attempt({}, planned, root))
            destination = root / "00-a-none-17"
            destination.mkdir()
            path = destination / "record.json"
            original = {**planned, "status": "running", "model_requests": 3}
            path.write_text(json.dumps(original))
            record = previous_attempt({}, planned, root)
            self.assertEqual(record["status"], "interrupted")
            self.assertEqual(record["model_requests"], 3)
            self.assertFalse(record["usage_complete"])
            self.assertIsNone(record["native_resolved"])
            (observation,) = destination.glob("interruption-observation-*.json")
            self.assertEqual(json.loads(observation.read_text()), original)
            self.assertEqual(previous_attempt({}, planned, root), record)


if __name__ == "__main__":
    unittest.main()
