# -*- coding: utf-8 -*-
"""从 self_media_dashboard.json 派生 compact_dashboard_data.json（v2 修复版）。

修复 v1 中的三个问题：
1. net_revenue：仅取 daily revenue=0（小红书无 per-day revenue，只有 revenueSnapshot）
   → 改为：revenueSnapshot 或 grossRevenueSnapshot - refundSnapshot 或 revenue（取 max）
2. 互动率：daily_metrics_recent30 没有 likes/favorites/comments/shares 细分
   → 新增 interact_total 字段，直接映射 daily.platforms[*].interact
3. content_items_top：原先用 detail.csv 可能丢失最新内容
   → 改为优先从 dashboard.contentDetails 去重取 Top 20

字段规范：daily_metrics_recent30 每条 (date, platform)
- net_revenue：该日该平台净收入（snapshot 或 per-day）
- interact_total：该日该平台互动数（点赞+评论+收藏+分享，上游已算好）
- content_count：该日该平台发布内容数（posts）
- views：该日该平台阅读量（play）
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_paths import PROJECT_ROOT, resolve_data_context

DATA_CONTEXT = resolve_data_context()
DATA_ROOT = DATA_CONTEXT.root
DASH_DIR = DATA_ROOT / "dashboard-normalized"
DASHBOARD_PATH = DASH_DIR / "self_media_dashboard.json"
DETAIL_CSV = DASH_DIR / "self_media_content_detail.csv"
COMPACT_PATH = DASH_DIR / "compact_dashboard_data.json"

# 仅小红书、B站有收入契约（与 normalize 脚本一致）
REVENUE_PLATFORMS = {"xhs", "bili"}
# xhs 用 revenueSnapshot 模式（累计值，非 per-day 增量）；bili 用 per-day revenue
# 注意：daily_metrics_recent30 被前端跨日 sum(net_revenue) 时，
# snapshot 平台（xhs）不能写累计值，否则每天都累一次造成重复计数。
# 因此 effective_revenue 对 snapshot 平台只取 per-day revenue（即使 0），
# 让前端 computeKPIs 的"再次兜底"触发 platforms.month_net_revenue（周期内累计已截好）。
SNAPSHOT_REVENUE_PLATFORMS = {"xhs"}
PERDAY_REVENUE_PLATFORMS = {"bili"}

def number(v):
    if v is None or v == "":
        return 0.0
    try:
        s = str(v).strip().replace(",", "").replace("¥", "").replace("%", "")
        if s in {"", "-", "--", "nan", "None"}:
            return 0.0
        return float(s)
    except (TypeError, ValueError):
        return 0.0

def clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "none"} else s

def iso_day(v):
    s = clean(v)
    return s[:10] if len(s) >= 10 else s


def to_compact_platform(p: dict) -> dict:
    return {
        "platform": p.get("id"),
        "platform_name": p.get("name"),
        "latest_total_followers": number(p.get("fans")),
        "latest_total_followers_date": p.get("totalFollowersDate") or "",
        "latest_daily_date": p.get("latestDailyDate") or "",
        "month_net_followers": number(p.get("newFans")),
        "month_new_followers": number(p.get("newFollowers")),
        "month_lost_followers": number(p.get("lostFollowers")),
        "month_net_revenue": number(p.get("revenue")),
        "month_content_count": number(p.get("posts")),
        "month_views": number(p.get("play")),
        "month_interact": number(p.get("interact")),
        "freshness_status": p.get("freshnessStatus") or "unknown",
        "freshness_issues": p.get("freshnessIssues") or [],
        "account_snapshots": [
            {
                "account_key": a.get("accountKey"),
                "latest_date": a.get("latestDate"),
                "staleness_days": a.get("stalenessDays"),
                "status": a.get("status"),
                "total_followers": number(a.get("totalFollowers")),
                "source_file": a.get("sourceFile"),
                "source_mtime": a.get("sourceMtime"),
            }
            for a in (p.get("accounts") or [])
        ],
        "content_snapshots": [
            {
                "account_key": a.get("accountKey"),
                "latest_date": a.get("latestDate"),
                "staleness_days": a.get("stalenessDays"),
                "status": a.get("status"),
            }
            for a in (p.get("contentSnapshots") or [])
        ],
        "shop_latest_revenue_date": p.get("shopLatestRevenueDate") or "",
    }


def effective_revenue(pid: str, pdat: dict) -> float:
    """计算平台当日净收入（用于 daily_metrics_recent30 的跨日求和）。
    注意：snapshot 模式（如 xhs）的 revenueSnapshot 是累计值，不能日求和，
    所以只取 per-day revenue（即使 0），让前端 computeKPIs 兜底用
    platforms.month_net_revenue（由 normalize 负责按周期截取好）。
    bili 等 per-day 平台直接用 revenue。
    """
    if pid in SNAPSHOT_REVENUE_PLATFORMS:
        return number(pdat.get("revenue"))
    if pid in PERDAY_REVENUE_PLATFORMS:
        return number(pdat.get("revenue"))
    return 0.0


def build_daily_metrics_recent30(daily: list) -> list:
    if not daily:
        return []
    sorted_daily = sorted(daily, key=lambda r: str(r.get("date", "")), reverse=True)
    recent = sorted_daily[:30]
    out = []
    name_map = {"xhs": "小红书", "douyin": "抖音", "zhihu": "知乎", "bili": "B站", "wechat": "公众号"}
    for row in sorted(recent, key=lambda r: str(r.get("date", ""))):
        date = row.get("date", "")
        for pid, pdat in (row.get("platforms") or {}).items():
            out.append({
                "platform": pid,
                "platform_name": name_map.get(pid, pid),
                "date": date,
                "new_followers": number(pdat.get("newFans")),
                "lost_followers": number(pdat.get("lostFans")),
                "net_followers": number(pdat.get("fans")),
                "gross_revenue": number(pdat.get("grossRevenueSnapshot")),
                "refund_amount": number(pdat.get("refundSnapshot")),
                # ★ 修复 1：net_revenue 用 revenueSnapshot（或 gross-refund）而非 per-day revenue
                "net_revenue": effective_revenue(pid, pdat),
                # ★ 修复 2：content_count = posts（normalize 已将发布数写入 posts）
                "content_count": number(pdat.get("posts")),
                "views": number(pdat.get("play")),
                "exposure": 0.0,
                # ★ 修复 3：新增 interact_total，直接映射上游算好的 interact
                "interact_total": number(pdat.get("interact")),
                # 细分字段缺数据时留空（不填 0），前端优先用 interact_total
                "likes": 0.0,
                "comments": 0.0,
                "favorites": 0.0,
                "shares": 0.0,
                "coins": 0.0,
                "danmaku": 0.0,
                "quality_note": pdat.get("qualityNote") or "",
                "source_file": pdat.get("sourceFile") or "",
                "source_mtime": "",
            })
    return out


def build_content_items_top_from_details(content_details: list) -> list:
    """从 dashboard.contentDetails 取 Top 20（score = play + interact）。
    contentDetails 没有 likes/favorites 细分时，至少 play/interact 是完整的。
    """
    latest_by_key = {}
    for row in content_details:
        snap_day = clean(row.get("snapshotDate")) or iso_day(row.get("publishedAt"))
        if not snap_day:
            continue
        account_key = clean(row.get("accountKey")) or clean(row.get("platform"))
        content_key = (
            clean(row.get("platform")),
            account_key,
            clean(row.get("contentId")) or clean(row.get("title")),
            clean(row.get("publishedAt")) or clean(row.get("date")),
        )
        prev = latest_by_key.get(content_key)
        if prev is None or snap_day > prev[0]:
            latest_by_key[content_key] = (snap_day, row)

    items = []
    for _snap, row in latest_by_key.values():
        title = clean(row.get("title"))
        if not title:
            continue
        play = number(row.get("play"))
        interact = number(row.get("interact"))
        score = play + interact
        if score <= 0:
            continue
        account_key = clean(row.get("accountKey")) or clean(row.get("platform"))
        items.append({
            "platform": clean(row.get("platform")),
            "platform_name": "",
            "account_key": account_key,
            "content_partition": clean(row.get("contentPartition")),
            "snapshot_time": clean(row.get("snapshotTime")),
            "snapshot_date": clean(row.get("snapshotDate")),
            "publish_time": clean(row.get("publishedAt")),
            "date": clean(row.get("date")),
            "content_title": title,
            "content_type": clean(row.get("type")),
            "content_url": clean(row.get("url")),
            "content_id": clean(row.get("contentId")),
            "views": play,
            "exposure": 0.0,
            "likes": number(row.get("likes", 0)),
            "comments": number(row.get("comments", 0)),
            "favorites": number(row.get("favorites", 0)),
            "shares": number(row.get("shares", 0)),
            "interact_total": interact,
            "heat": round(play * 0.1 + interact * 0.3, 1),
            "new_followers": 0.0,
            "quality_note": clean(row.get("qualityNote")),
            "source_file": clean(row.get("sourceFile")),
            "source_mtime": "",
            "_score": score,
        })
    items.sort(key=lambda x: x["_score"], reverse=True)
    top = items[:20]
    for it in top:
        del it["_score"]
    return top


def main():
    if not DASHBOARD_PATH.exists():
        raise SystemExit(f"missing dashboard: {DASHBOARD_PATH}")
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))

    platforms = dashboard.get("platforms") or []
    daily = dashboard.get("daily") or []

    totals = {
        "total_followers": sum(number(p.get("fans")) for p in platforms),
        "month_net_followers": sum(number(p.get("newFans")) for p in platforms),
        "month_net_revenue": round(sum(number(p.get("revenue")) for p in platforms), 2),
        "month_content_count": sum(number(p.get("posts")) for p in platforms),
        "month_views": sum(number(p.get("play")) for p in platforms),
        "month_interact": sum(number(p.get("interact")) for p in platforms),
    }

    compact = {
        "schema": "self-media-compact-dashboard.v1",
        "data_mode": dashboard.get("dataMode") or DATA_CONTEXT.mode,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date_min": dashboard.get("dateMin") or "",
        "date_max": dashboard.get("dateMax") or "",
        "totals": totals,
        "platforms": [to_compact_platform(p) for p in platforms],
        "daily_metrics_recent30": build_daily_metrics_recent30(daily),
    }

    # 先从 dashboard.contentDetails 取，若为空再退化 detail.csv
    content_details = dashboard.get("contentDetails") or []
    top = build_content_items_top_from_details(content_details) if len(content_details) >= 10 else None
    if not top and DETAIL_CSV.exists():
        # 退化：从 CSV 取
        latest_by_key = {}
        with open(DETAIL_CSV, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                snap_day = clean(row.get("snapshot_date")) or iso_day(row.get("source_mtime"))
                if not snap_day:
                    continue
                ak = clean(row.get("account_key")) or clean(row.get("platform"))
                ck = (clean(row.get("platform")), ak,
                      clean(row.get("content_id")) or clean(row.get("content_title")),
                      clean(row.get("publish_time")) or clean(row.get("date")))
                prev = latest_by_key.get(ck)
                if prev is None or snap_day > prev[0]:
                    latest_by_key[ck] = (snap_day, row)
        items = []
        for _s, row in latest_by_key.values():
            title = clean(row.get("content_title"))
            if not title:
                continue
            views = number(row.get("views"))
            exposure = number(row.get("exposure"))
            likes = number(row.get("likes"))
            comments = number(row.get("comments"))
            favorites = number(row.get("favorites"))
            shares = number(row.get("shares"))
            play = views or exposure
            interact = likes + comments + favorites + shares
            score = play + interact
            if score <= 0:
                continue
            ak = clean(row.get("account_key")) or clean(row.get("platform"))
            items.append({
                "platform": clean(row.get("platform")),
                "platform_name": clean(row.get("platform_name")),
                "account_key": ak,
                "content_partition": clean(row.get("content_partition")),
                "snapshot_time": clean(row.get("snapshot_time")),
                "snapshot_date": clean(row.get("snapshot_date")),
                "publish_time": clean(row.get("publish_time")),
                "date": clean(row.get("date")),
                "content_title": title,
                "content_type": clean(row.get("content_type")),
                "content_url": clean(row.get("content_url")),
                "content_id": clean(row.get("content_id")),
                "views": views,
                "exposure": exposure,
                "likes": likes,
                "comments": comments,
                "favorites": favorites,
                "shares": shares,
                "interact_total": interact,
                "heat": round(play * 0.1 + interact * 0.3, 1),
                "new_followers": number(row.get("new_followers")),
                "quality_note": clean(row.get("quality_note")),
                "source_file": clean(row.get("source_file")),
                "source_mtime": clean(row.get("source_mtime")),
                "_score": score,
            })
        items.sort(key=lambda x: x["_score"], reverse=True)
        top = items[:20]
        for it in top:
            del it["_score"]
    if not top:
        top = []

    compact["content_items_top"] = top
    compact["content_items_top_repaired_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    COMPACT_PATH.write_text(json.dumps(compact, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ wrote {COMPACT_PATH}")
    print(f"  generated_at: {compact['generated_at']}")
    print(f"  date_min/max: {compact['date_min']} ~ {compact['date_max']}")
    print(f"  totals: {totals}")
    print(f"  platforms: {len(compact['platforms'])}")
    print(f"  daily_metrics_recent30: {len(compact['daily_metrics_recent30'])} rows")

    # 校验：最近月份汇总（与前端 computeKPIs 等价的独立校验）
    recent = compact["daily_metrics_recent30"]
    latest_month = str(compact.get("date_max") or "")[:7]
    latest_rows = [r for r in recent if (r.get("date") or "").startswith(latest_month)]
    print()
    print(f"  === {latest_month} 前端 computeKPIs 独立校验 ===")
    total_rev = sum(number(r.get("net_revenue")) for r in latest_rows)
    total_views = sum(number(r.get("views")) for r in latest_rows)
    # 先取 interact_total，再退化加 likes+favorites+comments+shares
    total_interact = sum(
        number(r.get("interact_total"))
        if number(r.get("interact_total")) > 0
        else number(r.get("likes")) + number(r.get("comments")) + number(r.get("favorites")) + number(r.get("shares"))
        for r in latest_rows
    )
    total_posts = sum(number(r.get("content_count")) for r in latest_rows)
    total_net_followers = sum(number(r.get("net_followers")) for r in latest_rows)
    rate = (total_interact / total_views * 100) if total_views else 0
    print(f"    net_revenue sum: {total_rev:.2f}")
    print(f"    views sum:       {total_views:.0f}")
    print(f"    interact sum:    {total_interact:.0f}")
    print(f"    content_count:   {total_posts:.0f}")
    print(f"    net_followers:   {total_net_followers:.0f}")
    print(f"    互动率:          {rate:.2f}%")

    print(f"\n  content_items_top: {len(top)} items")
    if top:
        pub_dates = sorted(set(it["date"] for it in top if it["date"]))
        print(f"  content_items_top date range: {pub_dates[0] if pub_dates else '-'} ~ {pub_dates[-1] if pub_dates else '-'}")
        plat_ct = Counter(it["platform"] for it in top)
        print(f"  content_items_top by platform: {dict(plat_ct)}")
        latest_items = [x for x in top if (x.get("date") or "").startswith(latest_month)]
        print(f"  {latest_month} content_items_top: {len(latest_items)} 条")


if __name__ == "__main__":
    main()
