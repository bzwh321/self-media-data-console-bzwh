# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import console_server  # noqa: E402
import refresh_data  # noqa: E402
from sync_server_data import local_target  # noqa: E402


class RefreshPipelineTests(unittest.TestCase):
    def test_user_refresh_order_starts_with_sync_and_checks_before_compact(self) -> None:
        plan = refresh_data.command_plan("user", PROJECT_ROOT / "data" / "user")
        self.assertEqual(
            [name for name, _command, _timeout in plan],
            ["server_sync", "normalize", "contract_check", "build_compact", "build_attribution", "build_report"],
        )

    def test_demo_refresh_regenerates_without_server_sync(self) -> None:
        plan = refresh_data.command_plan("demo", PROJECT_ROOT / "data" / "demo")
        names = [name for name, _command, _timeout in plan]
        self.assertEqual(names[0], "generate_demo")
        self.assertNotIn("server_sync", names)
        self.assertIn("contract_check", names)

    def test_sync_target_cannot_escape_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                local_target(Path(temporary), "../outside")

    def test_refresh_endpoint_does_not_report_failed_pipeline_as_success(self) -> None:
        completed = type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "pipeline failed"})()
        with patch.object(console_server.subprocess, "run", return_value=completed), \
             patch.object(console_server, "read_json", return_value={"errors": ["contract_check 失败"]}):
            result = console_server.refresh_dashboard()
        self.assertFalse(result["ok"])
        self.assertIn("contract_check", result["error"])

    def test_refresh_endpoint_preserves_partial_check_status(self) -> None:
        completed = type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch.object(console_server.subprocess, "run", return_value=completed), \
             patch.object(console_server, "read_json", return_value={"status": "partial", "warnings": ["一个账号滞后"]}), \
             patch.object(console_server, "load_dashboard", return_value={"schema": "compact-dashboard.v1"}):
            result = console_server.refresh_dashboard()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["warnings"], ["一个账号滞后"])


if __name__ == "__main__":
    unittest.main()
