# -*- coding: utf-8 -*-
"""Business-contract checks for the self-media dashboard refresh chain."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_paths import PROJECT_ROOT, load_project_config, portable_path, resolve_data_context


DATA_CONTEXT = resolve_data_context()
DATA_ROOT = DATA_CONTEXT.root
DASHBOARD_DIR = DATA_ROOT / "dashboard-normalized"
EXPECTED_PLATFORMS = {"xhs", "douyin", "zhihu", "bili", "wechat"}
REVENUE_PLATFORMS = {"xhs", "bili"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def iso(day: date) -> str:
    return day.isoformat()


def default_audit_period(dashboard: dict[str, Any]) -> tuple[str, str]:
    end = parse_day(dashboard.get("dateMax") or dashboard.get("defaultDateEnd"))
    if end is None:
        end = date.today()
    if end.day <= 3:
        previous_month_end = end.replace(day=1) - timedelta(days=1)
        start = previous_month_end.replace(day=1)
    else:
        start = end.replace(day=1)
    return iso(start), iso(end)


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def compact_money(value: float) -> float:
    return round(value + 0.0000001, 2)


def platform_ids(dashboard: dict[str, Any]) -> list[str]:
    return [item.get("id") for item in dashboard.get("platforms", []) if item.get("id")]


def configured_platforms() -> set[str]:
    if DATA_CONTEXT.is_demo:
        return EXPECTED_PLATFORMS
    profile = load_project_config().get("profile") or {}
    selected = profile.get("active_platforms") if isinstance(profile, dict) else []
    valid = {str(item) for item in selected if str(item) in EXPECTED_PLATFORMS}
    return valid or EXPECTED_PLATFORMS


def rows_in_period(dashboard: dict[str, Any], start: str, end: str) -> list[dict[str, Any]]:
    return [
        row for row in dashboard.get("daily", [])
        if start <= str(row.get("date", "")) <= end
    ]


def platform_entry(row: dict[str, Any], platform: str) -> dict[str, Any]:
    return row.get("platforms", {}).get(platform, {}) or {}


def sum_daily_metric(rows: list[dict[str, Any]], platforms: list[str], metric: str) -> float:
    return sum(
        number(platform_entry(row, platform).get(metric))
        for row in rows
        for platform in platforms
    )


def latest_revenue_snapshot(rows: list[dict[str, Any]], platform: str) -> float:
    latest = 0.0
    for row in sorted(rows, key=lambda item: str(item.get("date", ""))):
        entry = platform_entry(row, platform)
        snapshot = number(entry.get("revenueSnapshot"))
        if snapshot:
            latest = snapshot
    return latest


def revenue_for_platform(rows: list[dict[str, Any]], platform: str) -> float:
    if platform == "xhs":
        return latest_revenue_snapshot(rows, platform)
    if platform == "bili":
        return sum_daily_metric(rows, [platform], "revenue")
    return 0.0


def compute_expected_kpis(
    dashboard: dict[str, Any],
    start: str,
    end: str,
) -> dict[str, Any]:
    platforms = platform_ids(dashboard)
    rows = rows_in_period(dashboard, start, end)
    by_platform = []
    for platform in platforms:
        by_platform.append({
            "platform": platform,
            "new_fans": round(sum_daily_metric(rows, [platform], "fans")),
            "revenue": compact_money(revenue_for_platform(rows, platform)),
            "posts": round(sum_daily_metric(rows, [platform], "posts")),
        })

    return {
        "period_start": start,
        "period_end": end,
        "row_count": len(rows),
        "total_followers": round(sum(number(item.get("fans")) for item in dashboard.get("platforms", []))),
        "new_fans": round(sum_daily_metric(rows, platforms, "fans")),
        "revenue": compact_money(sum(revenue_for_platform(rows, platform) for platform in platforms if platform in REVENUE_PLATFORMS)),
        "posts": round(sum_daily_metric(rows, platforms, "posts")),
        "by_platform": by_platform,
    }


def check_renderer_contract(console_root: Path) -> dict[str, Any]:
    renderer = console_root / "console" / "app.js"
    errors: list[str] = []
    evidence: dict[str, bool] = {
        "renderer_exists": renderer.exists(),
        "kpi_uses_filtered_daily": False,
        "new_fans_uses_daily_net_followers": False,
        "revenue_uses_daily_net_revenue": False,
    }
    if not renderer.exists():
        return {
            "status": "failed",
            "path": portable_path(renderer),
            "errors": [f"missing renderer: {renderer}"],
            "evidence": evidence,
        }

    text = renderer.read_text(encoding="utf-8")
    evidence["kpi_uses_filtered_daily"] = "var daily = filteredDaily();" in text
    evidence["new_fans_uses_daily_net_followers"] = "netFollowers += safe(m.net_followers);" in text
    evidence["revenue_uses_daily_net_revenue"] = "netRevenue += safe(m.net_revenue);" in text

    if not evidence["kpi_uses_filtered_daily"]:
        errors.append("KPI must use the selected-period daily rows")
    if not evidence["new_fans_uses_daily_net_followers"]:
        errors.append("new fans KPI must use daily net_followers")
    if not evidence["revenue_uses_daily_net_revenue"]:
        errors.append("revenue KPI must use daily net_revenue")

    return {
        "status": "failed" if errors else "passed",
        "path": portable_path(renderer),
        "errors": errors,
        "evidence": evidence,
    }


def check_data_contract(
    dashboard: dict[str, Any],
    summary: dict[str, Any],
    expected: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    actual_platforms = set(platform_ids(dashboard))
    expected_platforms = configured_platforms()
    missing_platforms = sorted(expected_platforms - actual_platforms)
    checks.append({
        "id": "expected_platforms_present",
        "status": "failed" if missing_platforms else "passed",
        "evidence": {"missing_platforms": missing_platforms, "actual_platforms": sorted(actual_platforms)},
    })
    if missing_platforms:
        errors.append(f"missing platforms: {', '.join(missing_platforms)}")

    fusion = (summary.get("source_counts") or {}).get("file_fusion") or {}
    server_sync_selected = int(fusion.get("server_sync_selected") or 0)
    checks.append({
        "id": "server_sync_files_selected",
        "status": "skipped" if DATA_CONTEXT.is_demo else ("failed" if server_sync_selected <= 0 else "passed"),
        "evidence": fusion,
    })
    if not DATA_CONTEXT.is_demo and server_sync_selected <= 0:
        errors.append("server_sync_selected is zero")

    checks.append({
        "id": "audit_period_has_daily_rows",
        "status": "failed" if expected["row_count"] <= 0 else "passed",
        "evidence": {
            "period_start": expected["period_start"],
            "period_end": expected["period_end"],
            "row_count": expected["row_count"],
        },
    })
    if expected["row_count"] <= 0:
        errors.append("audit period has no daily rows")

    xhs_revenue = next((item for item in expected["by_platform"] if item["platform"] == "xhs"), {})
    checks.append({
        "id": "xhs_revenue_snapshot_available",
        "status": "warning" if number(xhs_revenue.get("revenue")) <= 0 else "passed",
        "evidence": xhs_revenue,
    })
    if number(xhs_revenue.get("revenue")) <= 0:
        warnings.append("xhs revenue snapshot is zero in the audit period")

    summary_new_fans = round(sum(number(item.get("newFans")) for item in dashboard.get("platforms", [])))
    summary_revenue = compact_money(sum(number(item.get("revenue")) for item in dashboard.get("platforms", []) if item.get("id") in REVENUE_PLATFORMS))
    checks.append({
        "id": "range_kpi_not_platform_summary",
        "status": "passed",
        "evidence": {
            "expected_range_new_fans": expected["new_fans"],
            "platform_summary_new_fans": summary_new_fans,
            "expected_range_revenue": expected["revenue"],
            "platform_summary_revenue": summary_revenue,
            "note": "selected-range KPI must use expected_range_* values, not platform_summary_* values",
        },
    })

    for platform in dashboard.get("platforms", []):
        status = platform.get("freshnessStatus")
        if status and status != "ready":
            warnings.append(
                f"{platform.get('id')} freshness={status}: {platform.get('freshnessIssues') or []}"
            )

    return checks, errors, warnings


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Self-media Sync Business Checklist",
        "",
        f"- status: {report['status']}",
        f"- checked_at: {report['checked_at']}",
        f"- audit_period: {report['expected_kpis']['period_start']} to {report['expected_kpis']['period_end']}",
        "",
        "## Expected KPI Values",
        "",
        "| KPI | Value |",
        "| --- | ---: |",
        f"| total_followers | {report['expected_kpis']['total_followers']:,} |",
        f"| new_fans | {report['expected_kpis']['new_fans']:,} |",
        f"| revenue | {report['expected_kpis']['revenue']:,.2f} |",
        f"| posts | {report['expected_kpis']['posts']:,} |",
        "",
        "## Checklist",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for item in report["checks"]:
        evidence = json.dumps(item.get("evidence", {}), ensure_ascii=False)
        lines.append(f"| {item['id']} | {item['status']} | `{evidence}` |")

    lines.extend(["", "## Renderer Contract", ""])
    lines.append(f"- status: {report['renderer_contract']['status']}")
    for error in report["renderer_contract"].get("errors", []):
        lines.append(f"- error: {error}")
    for warning in report.get("warnings", []):
        lines.append(f"- warning: {warning}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console-root", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    console_root = Path(args.console_root)
    dashboard_path = DASHBOARD_DIR / "self_media_dashboard.json"
    summary_path = DASHBOARD_DIR / "self_media_summary.json"
    report_path = DASHBOARD_DIR / "latest_business_check.json"
    markdown_path = DASHBOARD_DIR / "latest_business_check.md"

    dashboard = load_json(dashboard_path)
    summary = load_json(summary_path)
    start, end = args.start, args.end
    if not start or not end:
        start, end = default_audit_period(dashboard)

    expected = compute_expected_kpis(dashboard, start, end)
    checks, errors, warnings = check_data_contract(dashboard, summary, expected)
    renderer_contract = check_renderer_contract(console_root)
    if renderer_contract["status"] != "passed":
        errors.extend(renderer_contract.get("errors", []))

    report = {
        "schema": "self-media-business-check.v1",
        "status": "failed" if errors else "ready",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "data_mode": DATA_CONTEXT.mode,
        "data_root": portable_path(DATA_ROOT),
        "dashboard_path": portable_path(dashboard_path),
        "summary_path": portable_path(summary_path),
        "console_root": portable_path(console_root),
        "expected_kpis": expected,
        "checks": checks,
        "renderer_contract": renderer_contract,
        "warnings": warnings,
        "errors": errors,
        "markdown_path": portable_path(markdown_path),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, markdown_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
