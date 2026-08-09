# -*- coding: utf-8 -*-
"""Portable data-profile paths shared by every console script."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"
DEMO_DATA_ROOT = PROJECT_ROOT / "data" / "demo"
USER_DATA_ROOT = PROJECT_ROOT / "data" / "user"

USER_DATA_DIRS = (
    "B站数据",
    "抖音数据",
    "知乎数据",
    "公众号数据",
    "小红书内容数据",
    "小红书电商数据",
    "小红书推广数据",
    "dashboard-normalized",
    "hotlist/normalized",
)

REQUIRED_DASHBOARD_FILES = (
    "self_media_daily_metrics.csv",
    "self_media_platform_snapshots.csv",
    "self_media_content_detail.csv",
    "self_media_content_items.csv",
    "self_media_dashboard.json",
    "self_media_summary.json",
    "self_media_metric_check.md",
    "compact_dashboard_data.json",
    "latest_business_check.json",
)


@dataclass(frozen=True)
class DataContext:
    root: Path
    mode: str
    source: str

    @property
    def dashboard_dir(self) -> Path:
        return self.root / "dashboard-normalized"

    @property
    def is_demo(self) -> bool:
        return self.mode == "demo"


def load_project_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _configured_data(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("data")
    return value if isinstance(value, dict) else {}


def _absolute_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def resolve_data_context() -> DataContext:
    """Resolve one data root. Demo and personal data are never merged."""
    env_root = os.environ.get("SELF_MEDIA_DATA_ROOT", "").strip()
    if env_root:
        root = _absolute_path(env_root)
        requested_mode = os.environ.get("SELF_MEDIA_DATA_MODE", "").strip().lower()
        mode = requested_mode if requested_mode in {"demo", "user"} else "user"
        if root == DEMO_DATA_ROOT.resolve():
            mode = "demo"
        return DataContext(root=root, mode=mode, source="environment")

    config = load_project_config()
    data = _configured_data(config)
    mode = str(data.get("mode") or config.get("data_mode") or "demo").strip().lower()
    if mode not in {"demo", "user"}:
        mode = "demo"
    default_root = USER_DATA_ROOT if mode == "user" else DEMO_DATA_ROOT
    configured_root = str(data.get("root") or "").strip()
    root = _absolute_path(configured_root) if configured_root else default_root.resolve()
    return DataContext(root=root, mode=mode, source="config" if CONFIG_PATH.exists() else "default")


def ensure_user_skeleton() -> None:
    for relative in USER_DATA_DIRS:
        (USER_DATA_ROOT / Path(relative)).mkdir(parents=True, exist_ok=True)


def missing_dashboard_files(root: Path) -> list[str]:
    dashboard_dir = root / "dashboard-normalized"
    return [name for name in REQUIRED_DASHBOARD_FILES if not (dashboard_dir / name).exists()]


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def hotlist_path(context: DataContext | None = None) -> Path:
    override = os.environ.get("HOTLIST_DATA_PATH", "").strip()
    if override:
        return _absolute_path(override)
    selected = context or resolve_data_context()
    return selected.root / "hotlist" / "normalized" / "hotlist_latest.json"
