# -*- coding: utf-8 -*-
"""Refresh the active data package and verify it before the console reloads."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_paths import PROJECT_ROOT, load_project_config, missing_dashboard_files, portable_path, resolve_data_context


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点不是对象：{path}")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def tail_text(value: str, limit: int = 2000) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[-limit:]


def command_plan(mode: str, data_root: Path) -> list[tuple[str, list[str], int]]:
    python = sys.executable
    scripts = PROJECT_ROOT / "scripts"
    steps: list[tuple[str, list[str], int]] = []
    if mode == "demo":
        steps.append((
            "generate_demo",
            [python, str(scripts / "generate_demo_data.py"), "--output", str(data_root), "--skip-checks"],
            180,
        ))
    else:
        steps.extend([
            ("server_sync", [python, str(scripts / "sync_server_data.py")], 1800),
            ("normalize", [python, str(scripts / "normalize-self-media-dashboard.py")], 600),
        ])
    steps.extend([
        ("contract_check", [python, str(scripts / "check-self-media-dashboard-contract.py"), "--console-root", str(PROJECT_ROOT)], 300),
        ("build_compact", [python, str(scripts / "build_compact_dashboard.py")], 300),
        ("build_attribution", [python, str(scripts / "build_attribution.py")], 300),
        ("build_report", [python, str(scripts / "daily_pipeline.py"), "--stage", "report"], 300),
    ])
    return steps


def run_step(name: str, command: list[str], timeout: int, env: dict[str, str]) -> dict[str, Any]:
    started_at = now_text()
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "name": name,
            "status": "success" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "started_at": started_at,
            "finished_at": now_text(),
            "stdout_tail": tail_text(completed.stdout),
            "stderr_tail": tail_text(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "status": "failed",
            "returncode": 124,
            "started_at": started_at,
            "finished_at": now_text(),
            "stdout_tail": tail_text(str(exc.stdout or "")),
            "stderr_tail": f"执行超时（{timeout} 秒）",
        }


def parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def verify_outputs(data_root: Path, mode: str, config: dict[str, Any]) -> dict[str, Any]:
    dashboard_dir = data_root / "dashboard-normalized"
    errors = [f"缺少输出文件：{name}" for name in missing_dashboard_files(data_root)]
    warnings: list[str] = []
    dashboard_path = dashboard_dir / "self_media_dashboard.json"
    business_path = dashboard_dir / "latest_business_check.json"
    compact_path = dashboard_dir / "compact_dashboard_data.json"

    dashboard = read_json(dashboard_path) if dashboard_path.exists() else {}
    business = read_json(business_path) if business_path.exists() else {}
    if business.get("status") not in {"ready", "success"}:
        errors.append("业务契约校验未通过")
    if not compact_path.exists():
        errors.append("紧凑版看板数据未生成")

    sync_status = "skipped"
    if mode == "user":
        sync_path = dashboard_dir / "server_sync_refresh_report.json"
        sync_report = read_json(sync_path) if sync_path.exists() else {}
        sync_status = str(sync_report.get("status") or "missing")
        if sync_status != "success":
            errors.append(f"服务器同步状态不是 success：{sync_status}")

    sync_config = config.get("server_sync") if isinstance(config.get("server_sync"), dict) else {}
    max_age_days = max(0, min(int(sync_config.get("max_age_days") or 1), 30))
    today = date.today()
    profile = config.get("profile") if isinstance(config.get("profile"), dict) else {}
    active = profile.get("active_platforms") if isinstance(profile.get("active_platforms"), list) else []
    active_ids = {str(item) for item in active if str(item).strip()}
    freshness: list[dict[str, Any]] = []
    for platform in dashboard.get("platforms") or []:
        platform_id = str(platform.get("id") or "")
        if active_ids and platform_id not in active_ids:
            continue
        latest = parse_day(platform.get("latestDailyDate"))
        age = (today - latest).days if latest is not None else None
        status = "ready" if age is not None and age <= max_age_days else "stale"
        freshness.append({
            "platform": platform_id,
            "latest_daily_date": latest.isoformat() if latest else "",
            "age_days": age,
            "status": status,
        })
        if status != "ready":
            errors.append(f"{platform.get('name') or platform_id} 数据已超过 T-{max_age_days}")
        embedded_status = str(platform.get("freshnessStatus") or "unknown")
        if embedded_status not in {"ready", "unknown"}:
            issues = "；".join(str(item) for item in (platform.get("freshnessIssues") or []))
            warnings.append(f"{platform.get('name') or platform_id} 存在滞后数据：{issues or embedded_status}")

    if active_ids:
        present = {item["platform"] for item in freshness}
        for missing in sorted(active_ids - present):
            errors.append(f"启用平台缺少数据：{missing}")
    if not freshness:
        errors.append("没有可检查的平台数据")

    return {
        "status": "failed" if errors else ("partial" if warnings else "ready"),
        "errors": errors,
        "warnings": warnings,
        "sync_status": sync_status,
        "business_status": str(business.get("status") or "missing"),
        "max_age_days": max_age_days,
        "date_max": dashboard.get("dateMax"),
        "freshness": freshness,
    }


def main() -> int:
    context = resolve_data_context()
    config = load_project_config()
    report_path = context.dashboard_dir / "latest_refresh_check.json"
    report: dict[str, Any] = {
        "schema": "self-media-refresh-check.v1",
        "status": "running",
        "data_mode": context.mode,
        "data_root": portable_path(context.root),
        "started_at": now_text(),
        "steps": [],
        "errors": [],
    }
    env = os.environ.copy()
    env["SELF_MEDIA_DATA_ROOT"] = str(context.root)
    env["SELF_MEDIA_DATA_MODE"] = context.mode
    env["PYTHONUTF8"] = "1"

    try:
        for name, command, timeout in command_plan(context.mode, context.root):
            result = run_step(name, command, timeout, env)
            report["steps"].append(result)
            if result["status"] != "success":
                detail = result["stderr_tail"] or result["stdout_tail"] or "未知错误"
                raise RuntimeError(f"{name} 失败：{detail}")

        verification = verify_outputs(context.root, context.mode, config)
        report["verification"] = verification
        if verification["status"] == "failed":
            raise RuntimeError("；".join(verification["errors"]))

        report["status"] = verification["status"]
        report["warnings"] = verification["warnings"]
        return_code = 0
    except (OSError, ValueError, RuntimeError) as exc:
        report["status"] = "failed"
        report["errors"].append(str(exc))
        return_code = 1

    report["finished_at"] = now_text()
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
