"""Fail closed on invalid embedded Python in source-pinned CI workflows.

This test uses only the Python standard library and runs before installing the
app dependencies. It checks syntax, not GitHub runner allocation or deployment.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ROOT / ".github/workflows/v89-source-quarantine.yml",
    ROOT / ".github/workflows/v84-full-regression.yml",
)
PYTHON_HEREDOC = re.compile(
    r"^\s*python(?:3(?:\.\d+)?)?\s+-\s+<<\s*(?P<quote>['\"]?)"
    r"(?P<marker>[A-Za-z_][A-Za-z_0-9]*)(?P=quote)\s*$"
)


def embedded_python_blocks(source: str) -> list[str]:
    """Extract YAML literal-block Python heredocs without YAML dependencies."""
    lines = source.splitlines()
    blocks: list[str] = []
    for index, line in enumerate(lines):
        match = PYTHON_HEREDOC.fullmatch(line)
        if match is None:
            continue
        indent = len(line) - len(line.lstrip(" "))
        marker = match.group("marker")
        for end in range(index + 1, len(lines)):
            candidate = lines[end]
            candidate_indent = len(candidate) - len(candidate.lstrip(" "))
            if candidate.strip() == marker and candidate_indent == indent:
                block = "\n".join(
                    item[indent:] if item.startswith(" " * indent) else item
                    for item in lines[index + 1 : end]
                )
                if not block.strip():
                    raise ValueError("EMPTY_EMBEDDED_PYTHON")
                blocks.append(block + "\n")
                break
        else:
            raise ValueError("UNTERMINATED_EMBEDDED_PYTHON_HEREDOC")
    return blocks


class EmbeddedWorkflowPythonTest(unittest.TestCase):
    def test_release_workflow_embedded_python_is_syntactically_valid(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                blocks = embedded_python_blocks(workflow.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(blocks), 1, "No inline Python found")
                for index, block in enumerate(blocks, 1):
                    with self.subTest(block=index):
                        compile(block, f"{workflow.name}::python-{index}", "exec")

    def test_rejects_shell_boolean_operator_inside_python(self):
        bad = "run: |\n  python - <<'PY'\n  assert 'ok' || 'bad'\n  PY\n"
        blocks = embedded_python_blocks(bad)
        self.assertEqual(len(blocks), 1)
        with self.assertRaises(SyntaxError):
            compile(blocks[0], "broken.yml::python-1", "exec")

    def test_rejects_unterminated_heredoc(self):
        bad = "run: |\n  python - <<'PY'\n  print('unclosed')\n"
        with self.assertRaisesRegex(ValueError, "UNTERMINATED"):
            embedded_python_blocks(bad)

    def test_keeps_python_nested_indentation(self):
        good = (
            "run: |\n"
            "  python - <<'PY'\n"
            "  for count in range(2):\n"
            "      assert count >= 0\n"
            "  PY\n"
        )
        blocks = embedded_python_blocks(good)
        self.assertEqual(len(blocks), 1)
        compile(blocks[0], "nested.yml::python-1", "exec")


if __name__ == "__main__":
    unittest.main()
