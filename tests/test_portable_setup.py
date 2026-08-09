# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_paths import DEMO_DATA_ROOT, USER_DATA_DIRS, missing_dashboard_files  # noqa: E402


class PortableSetupTests(unittest.TestCase):
    def test_demo_contract_is_complete(self) -> None:
        self.assertEqual(missing_dashboard_files(DEMO_DATA_ROOT), [])

    def test_demo_is_explicit_and_revenue_contract_is_respected(self) -> None:
        path = DEMO_DATA_ROOT / "dashboard-normalized" / "self_media_dashboard.json"
        dashboard = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(dashboard.get("dataMode"), "demo")
        by_id = {item["id"]: item for item in dashboard["platforms"]}
        for platform in ("douyin", "zhihu", "wechat"):
            self.assertEqual(float(by_id[platform]["revenue"]), 0.0)

    def test_user_skeleton_excludes_knowledge_planet(self) -> None:
        self.assertFalse(any("知识星球" in item for item in USER_DATA_DIRS))
        expected = {"B站数据", "抖音数据", "知乎数据", "公众号数据", "小红书内容数据", "小红书电商数据", "小红书推广数据"}
        self.assertTrue(expected.issubset(set(USER_DATA_DIRS)))

    def test_demo_source_paths_are_portable(self) -> None:
        path = DEMO_DATA_ROOT / "dashboard-normalized" / "self_media_daily_metrics.csv"
        text = path.read_text(encoding="utf-8-sig")
        self.assertNotRegex(text, r"[A-Za-z]:\\")
        self.assertIn("data/demo/", text)


if __name__ == "__main__":
    unittest.main()
