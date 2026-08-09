# -*- coding: utf-8 -*-
"""Generate a complete, deterministic and fully synthetic demo data package."""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_paths import DEMO_DATA_ROOT, PROJECT_ROOT, portable_path


PLATFORMS = (
    {"id": "xhs", "name": "小红书", "folder": "小红书内容数据", "account": "示例账号", "color": "#EF4444", "base": 12000},
    {"id": "douyin", "name": "抖音", "folder": "抖音数据", "account": "示例账号", "color": "#111827", "base": 8600},
    {"id": "zhihu", "name": "知乎", "folder": "知乎数据", "account": "示例账号", "color": "#2563EB", "base": 6400},
    {"id": "bili", "name": "B站", "folder": "B站数据", "account": "示例账号", "color": "#00A1D6", "base": 9800},
    {"id": "wechat", "name": "公众号", "folder": "公众号数据", "account": "示例账号", "color": "#10B981", "base": 5200},
)

DAILY_FIELDS = (
    "platform", "platform_name", "date", "new_followers", "lost_followers",
    "net_followers", "gross_revenue", "refund_amount", "net_revenue",
    "content_count", "views", "exposure", "likes", "comments", "favorites",
    "shares", "coins", "danmaku", "quality_note", "source_file", "source_mtime",
)
SNAPSHOT_FIELDS = (
    "platform", "platform_name", "account_key", "date", "total_followers",
    "quality_note", "source_file", "source_mtime",
)
CONTENT_FIELDS = (
    "platform", "platform_name", "account_key", "content_partition", "snapshot_time",
    "snapshot_date", "publish_time", "date", "content_title", "content_type",
    "content_url", "content_id", "views", "exposure", "likes", "comments",
    "favorites", "shares", "new_followers", "quality_note", "source_file", "source_mtime",
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def month_start(day: date) -> date:
    return day.replace(day=1)


def platform_source(platform: dict[str, Any], month: str, source_root: str) -> str:
    return f"{source_root}/{platform['folder']}/{platform['account']}/monthly/demo_metrics/{month}_模拟指标.csv"


def make_rows(end_day: date, days: int, seed: int, source_root: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    rng = random.Random(seed)
    start_day = end_day - timedelta(days=days - 1)
    totals = {item["id"]: int(item["base"]) for item in PLATFORMS}
    daily_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    xhs_revenue_by_month: dict[str, float] = {}

    for offset in range(days):
        day = start_day + timedelta(days=offset)
        month = day.strftime("%Y-%m")
        for index, platform in enumerate(PLATFORMS):
            pid = platform["id"]
            new_followers = rng.randint(2 + index, 10 + index * 2)
            lost_followers = rng.randint(0, 3 + index // 2)
            net_followers = new_followers - lost_followers
            totals[pid] += net_followers
            content_count = 1 if (offset + index) % (3 + index % 2) == 0 else 0
            views = 900 + index * 260 + offset * 18 + rng.randint(0, 180)
            likes = round(views * (0.035 + index * 0.002))
            comments = round(views * 0.006)
            favorites = round(views * 0.011)
            shares = round(views * 0.004)
            gross_revenue = refund_amount = net_revenue = 0.0
            if pid == "xhs":
                gross_revenue = round(75 + rng.random() * 65, 2)
                refund_amount = round(gross_revenue * 0.08, 2)
                xhs_revenue_by_month[month] = round(
                    xhs_revenue_by_month.get(month, 0.0) + gross_revenue - refund_amount,
                    2,
                )
            elif pid == "bili":
                gross_revenue = round(20 + rng.random() * 45, 2)
                net_revenue = gross_revenue
            source = platform_source(platform, month, source_root)
            daily_rows.append({
                "platform": pid,
                "platform_name": platform["name"],
                "date": day.isoformat(),
                "new_followers": new_followers,
                "lost_followers": lost_followers,
                "net_followers": net_followers,
                "gross_revenue": gross_revenue,
                "refund_amount": refund_amount,
                "net_revenue": net_revenue,
                "content_count": content_count,
                "views": views,
                "exposure": round(views * 1.35),
                "likes": likes,
                "comments": comments,
                "favorites": favorites,
                "shares": shares,
                "coins": round(views * 0.003) if pid == "bili" else 0,
                "danmaku": round(views * 0.002) if pid == "bili" else 0,
                "quality_note": "synthetic_demo",
                "source_file": source,
                "source_mtime": f"{day.isoformat()}T12:00:00+08:00",
                "revenue_snapshot": xhs_revenue_by_month.get(month, 0.0) if pid == "xhs" else 0,
            })

    for platform in PLATFORMS:
        source = platform_source(platform, end_day.strftime("%Y-%m"), source_root)
        snapshots.append({
            "platform": platform["id"],
            "platform_name": platform["name"],
            "account_key": platform["account"],
            "date": end_day.isoformat(),
            "total_followers": totals[platform["id"]],
            "quality_note": "synthetic_demo",
            "source_file": source,
            "source_mtime": f"{end_day.isoformat()}T12:00:00+08:00",
        })
    return daily_rows, snapshots, totals


def make_content(end_day: date, seed: int, source_root: str) -> list[dict[str, Any]]:
    rng = random.Random(seed + 97)
    subjects = ("内容复盘方法", "数据看板搭建", "选题验证流程", "运营指标入门", "增长实验记录")
    rows: list[dict[str, Any]] = []
    for platform_index, platform in enumerate(PLATFORMS):
        for item_index in range(4):
            published = end_day - timedelta(days=platform_index + item_index * 3)
            views = 1800 + rng.randint(0, 5200)
            likes = round(views * 0.05)
            comments = round(views * 0.008)
            favorites = round(views * 0.016)
            shares = round(views * 0.006)
            source = platform_source(platform, published.strftime("%Y-%m"), source_root)
            rows.append({
                "platform": platform["id"],
                "platform_name": platform["name"],
                "account_key": platform["account"],
                "content_partition": "demo",
                "snapshot_time": f"{end_day.isoformat()}T12:00:00+08:00",
                "snapshot_date": end_day.isoformat(),
                "publish_time": f"{published.isoformat()}T10:00:00+08:00",
                "date": published.isoformat(),
                "content_title": f"{subjects[(platform_index + item_index) % len(subjects)]}（模拟）",
                "content_type": ("教程", "案例", "复盘")[item_index % 3],
                "content_url": "",
                "content_id": f"demo-{platform['id']}-{item_index + 1:02d}",
                "views": views,
                "exposure": round(views * 1.4),
                "likes": likes,
                "comments": comments,
                "favorites": favorites,
                "shares": shares,
                "new_followers": round(views * 0.006),
                "quality_note": "synthetic_demo",
                "source_file": source,
                "source_mtime": f"{end_day.isoformat()}T12:00:00+08:00",
            })
    return rows


def build_payload(root: Path, end_day: date, days: int, seed: int) -> None:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    start_day = end_day - timedelta(days=days - 1)
    current_start = month_start(end_day)
    relative_root = portable_path(root)
    daily_rows, snapshots, follower_totals = make_rows(end_day, days, seed, relative_root)
    content_rows = make_content(end_day, seed, relative_root)
    dash_dir = root / "dashboard-normalized"
    relative_dash = f"{relative_root}/dashboard-normalized"
    current_rows = [row for row in daily_rows if row["date"] >= current_start.isoformat()]
    source_counts = {
        "demo_generated_files": len(PLATFORMS),
        "file_fusion": {"demo_selected": len(PLATFORMS), "server_sync_selected": 0},
    }

    platform_payload = []
    for platform in PLATFORMS:
        pid = platform["id"]
        rows = [row for row in current_rows if row["platform"] == pid]
        all_rows = [row for row in daily_rows if row["platform"] == pid]
        source = platform_source(platform, end_day.strftime("%Y-%m"), relative_root)
        revenue = 0.0
        if pid == "xhs":
            revenue = max((float(row["revenue_snapshot"]) for row in rows), default=0.0)
        elif pid == "bili":
            revenue = sum(float(row["net_revenue"]) for row in rows)
        platform_payload.append({
            "id": pid,
            "name": platform["name"],
            "color": platform["color"],
            "fans": follower_totals[pid],
            "newFans": sum(int(row["net_followers"]) for row in rows),
            "revenue": round(revenue, 2),
            "posts": sum(int(row["content_count"]) for row in rows),
            "play": sum(int(row["views"]) for row in rows),
            "interact": sum(int(row["likes"] + row["comments"] + row["favorites"] + row["shares"]) for row in rows),
            "hasDailyFollowerMetric": True,
            "hasTotalFollowers": True,
            "totalFollowersDate": end_day.isoformat(),
            "latestDailyDate": end_day.isoformat(),
            "newFollowers": sum(int(row["new_followers"]) for row in rows),
            "lostFollowers": sum(int(row["lost_followers"]) for row in rows),
            "freshnessStatus": "ready",
            "freshnessIssues": [],
            "accounts": [{
                "accountKey": platform["account"], "latestDate": end_day.isoformat(),
                "stalenessDays": 0, "status": "ready", "totalFollowers": follower_totals[pid],
                "sourceFile": source, "sourceMtime": f"{end_day.isoformat()}T12:00:00+08:00",
            }],
            "contentSnapshots": [{
                "accountKey": platform["account"], "latestDate": end_day.isoformat(),
                "stalenessDays": 0, "status": "ready",
            }],
            "shopLatestRevenueDate": end_day.isoformat() if pid == "xhs" else "",
            "_all_rows": all_rows,
        })

    daily_payload = []
    for day_offset in range(days):
        day_text = (start_day + timedelta(days=day_offset)).isoformat()
        platform_map = {}
        for platform in PLATFORMS:
            row = next(item for item in daily_rows if item["date"] == day_text and item["platform"] == platform["id"])
            platform_map[platform["id"]] = {
                "fans": row["net_followers"], "newFans": row["new_followers"], "lostFans": row["lost_followers"],
                "revenue": row["net_revenue"], "revenueSnapshot": row["revenue_snapshot"],
                "grossRevenueSnapshot": row["gross_revenue"], "refundSnapshot": row["refund_amount"],
                "posts": row["content_count"], "play": row["views"],
                "interact": row["likes"] + row["comments"] + row["favorites"] + row["shares"],
                "qualityNote": row["quality_note"], "sourceFile": row["source_file"],
            }
        daily_payload.append({"date": day_text, "platforms": platform_map})

    for platform in platform_payload:
        platform.pop("_all_rows", None)
    content_details = [{
        "platform": row["platform"], "accountKey": row["account_key"], "title": row["content_title"],
        "date": row["date"], "publishedAt": row["publish_time"], "snapshotDate": row["snapshot_date"],
        "snapshotTime": row["snapshot_time"], "contentPartition": row["content_partition"],
        "play": row["views"], "interact": row["likes"] + row["comments"] + row["favorites"] + row["shares"],
        "likes": row["likes"], "comments": row["comments"], "favorites": row["favorites"], "shares": row["shares"],
        "type": row["content_type"], "url": "", "contentId": row["content_id"], "sourceFile": row["source_file"],
    } for row in content_rows]
    totals = {
        "total_followers": sum(item["fans"] for item in platform_payload),
        "month_net_followers": sum(item["newFans"] for item in platform_payload),
        "month_net_revenue": round(sum(float(item["revenue"]) for item in platform_payload), 2),
        "month_content_count": sum(item["posts"] for item in platform_payload),
    }
    notes = [
        "全部账号、标题、数值和来源路径均为程序生成的模拟信息。",
        "仅小红书和 B站包含收入；抖音、知乎、公众号收入固定为 0。",
        "模拟数据与 data/user 个人数据不混合。",
    ]
    row_counts = {
        "daily_metrics": len(daily_rows), "platform_snapshots": len(snapshots),
        "content_items": len(content_rows), "content_detail_items": len(content_rows),
    }
    summary_platforms = [{
        "platform": item["id"], "platform_name": item["name"],
        "latest_total_followers": item["fans"], "latest_total_followers_date": end_day.isoformat(),
        "latest_daily_date": end_day.isoformat(), "month_net_followers": item["newFans"],
        "month_new_followers": item["newFollowers"], "month_lost_followers": item["lostFollowers"],
        "month_net_revenue": item["revenue"], "month_content_count": item["posts"],
        "month_views": item["play"], "freshness_status": "ready", "freshness_issues": [],
        "account_snapshots": item["accounts"], "content_snapshots": item["contentSnapshots"],
        "shop_latest_revenue_date": item["shopLatestRevenueDate"],
    } for item in platform_payload]
    summary = {
        "schema": "self-media-normalized.v1", "data_mode": "demo", "generated_at": generated_at,
        "source_root": relative_root, "normalized_dir": relative_dash,
        "date_min": start_day.isoformat(), "date_max": end_day.isoformat(),
        "latest_month": end_day.strftime("%Y-%m"), "current_month_start": current_start.isoformat(),
        "totals": totals, "platforms": summary_platforms, "row_counts": row_counts,
        "source_counts": source_counts, "content_snapshot_dates": {}, "notes": notes,
    }
    dashboard = {
        "schema": "self-media-dashboard.v1", "dataContractVersion": 9, "dataMode": "demo",
        "generatedAt": generated_at, "sourceRoot": relative_root, "normalizedDir": relative_dash,
        "dateMin": start_day.isoformat(), "dateMax": end_day.isoformat(),
        "latestMonth": end_day.strftime("%Y-%m"), "defaultDateStart": current_start.isoformat(),
        "defaultDateEnd": end_day.isoformat(), "platforms": platform_payload, "daily": daily_payload,
        "contentItems": content_details, "contentDetails": content_details, "contentSnapshotDates": {},
        "coverage": [{
            "platform": item["id"], "platformName": item["name"], "status": "ready",
            "latestDailyDate": end_day.isoformat(), "latestTotalFollowersDate": end_day.isoformat(),
            "freshnessIssues": [], "accounts": item["accounts"], "contentSnapshots": item["contentSnapshots"],
            "shopLatestRevenueDate": item["shopLatestRevenueDate"],
        } for item in platform_payload],
        "sources": source_counts, "sourceCounts": source_counts, "rowCounts": row_counts,
        "notes": notes, "totals": totals,
    }

    write_csv(dash_dir / "self_media_daily_metrics.csv", daily_rows, DAILY_FIELDS)
    write_csv(dash_dir / "self_media_platform_snapshots.csv", snapshots, SNAPSHOT_FIELDS)
    write_csv(dash_dir / "self_media_content_items.csv", content_rows, CONTENT_FIELDS)
    write_csv(dash_dir / "self_media_content_detail.csv", content_rows, CONTENT_FIELDS)
    write_json(dash_dir / "self_media_summary.json", summary)
    write_json(dash_dir / "self_media_dashboard.json", dashboard)
    (dash_dir / "self_media_metric_check.md").write_text(
        "# 模拟数据指标核对\n\n"
        f"- 数据模式：demo\n- 区间：{start_day.isoformat()} 至 {end_day.isoformat()}\n"
        f"- 平台数：{len(PLATFORMS)}\n- 日指标行数：{len(daily_rows)}\n"
        "- 脱敏方式：依据字段契约从零生成，不从真实数据抽样。\n",
        encoding="utf-8",
    )
    write_json(dash_dir / "server_sync_refresh_report.json", {
        "schema": "self-media-sync-report.v1", "status": "skipped", "data_mode": "demo",
        "generated_at": generated_at, "source": "synthetic_generator",
        "message": "模拟模式不执行服务器同步。",
    })
    write_json(dash_dir / "latest_refresh_check.json", {
        "schema": "self-media-refresh-check.v1", "status": "ready", "data_mode": "demo",
        "generated_at": generated_at, "checks": ["synthetic_generation", "portable_paths"],
    })
    write_json(root / "demo-manifest.json", {
        "schema": "self-media-demo-manifest.v1", "data_mode": "demo", "synthetic": True,
        "seed": seed, "days": days, "date_min": start_day.isoformat(), "date_max": end_day.isoformat(),
        "contains_real_user_data": False,
    })

    for platform in PLATFORMS:
        rows = [row for row in daily_rows if row["platform"] == platform["id"]]
        for month in sorted({row["date"][:7] for row in rows}):
            target = root / platform["folder"] / platform["account"] / "monthly" / "demo_metrics" / f"{month}_模拟指标.csv"
            write_csv(target, [row for row in rows if row["date"].startswith(month)], DAILY_FIELDS)
    xhs_rows = [row for row in current_rows if row["platform"] == "xhs"]
    shop_path = (
        root / "小红书电商数据" / "示例店铺" / "raw" / "datacenter_overview"
        / end_day.strftime("%Y-%m") / "商家经营核心数据汇总_模拟.csv"
    )
    write_csv(shop_path, [{
        "统计结束日": end_day.isoformat(),
        "支付金额": round(sum(float(row["gross_revenue"]) for row in xhs_rows), 2),
        "退款金额（退款时间）": round(sum(float(row["refund_amount"]) for row in xhs_rows), 2),
        "数据标记": "synthetic_demo",
    }], ("统计结束日", "支付金额", "退款金额（退款时间）", "数据标记"))
    promotion_dir = root / "小红书推广数据"
    promotion_dir.mkdir(parents=True, exist_ok=True)
    (promotion_dir / "README.md").write_text(
        "# 小红书推广模拟目录\n\n当前看板不消费推广指标，本目录只保留公开版目录契约。\n",
        encoding="utf-8",
    )


def run_derived_steps(root: Path) -> None:
    env = os.environ.copy()
    env["SELF_MEDIA_DATA_ROOT"] = str(root)
    env["SELF_MEDIA_DATA_MODE"] = "demo"
    commands = (
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_compact_dashboard.py")],
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check-self-media-dashboard-contract.py"), "--console-root", str(PROJECT_ROOT)],
    )
    for command in commands:
        subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)
    if root.resolve() == DEMO_DATA_ROOT.resolve():
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "build_attribution.py")],
            cwd=PROJECT_ROOT, env=env, check=True,
        )
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "daily_pipeline.py"), "--stage", "build-ops-analysis"],
            cwd=PROJECT_ROOT, env=env, check=True,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEMO_DATA_ROOT)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--skip-checks", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.days < 14:
        raise SystemExit("--days must be at least 14")
    root = args.output.resolve()
    build_payload(root, args.end_date, args.days, args.seed)
    if not args.skip_checks:
        run_derived_steps(root)
    print(json.dumps({"ok": True, "data_mode": "demo", "root": portable_path(root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
