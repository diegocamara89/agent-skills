from __future__ import annotations

import unittest

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_ai_cli  # noqa: E402


class RunAiCliTests(unittest.TestCase):
    def test_build_provider_command_adds_model_for_claude(self) -> None:
        command = run_ai_cli.build_provider_command(
            "claude",
            "opus",
            "planeje a tarefa",
            None,
            False,
            executable="claude.exe",
        )

        self.assertIn("--model", command)
        self.assertIn("opus", command)
        self.assertIn("-p", command)
        self.assertIn("planeje a tarefa", command)


if __name__ == "__main__":
    unittest.main()
