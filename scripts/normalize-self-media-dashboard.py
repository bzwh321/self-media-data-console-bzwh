import csv
import json
import math
import os
import re
import sys
import warnings
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd


warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

DATA_ROOT = Path(
    os.environ.get(
        "SELF_MEDIA_DATA_ROOT",
        str(Path(__file__).resolve().parents[1] / "sample-data" / "self-media"),
    )
)
OUT_DIR = DATA_ROOT / "dashboard-normalized"
DATA_CONTRACT_VERSION = 9
SERVER_SYNC_DIR_NAME = "\u670d\u52a1\u5668\u540c\u6b65"
FILE_SELECTION_STATS = defaultdict(int)
FRESHNESS_READY_DAYS = 2
FRESHNESS_LATE_DAYS = 4

PLATFORMS = {
    "xhs": "\u5c0f\u7ea2\u4e66",
    "douyin": "\u6296\u97f3",
    "zhihu": "\u77e5\u4e4e",
    "bili": "B\u7ad9",
    "wechat": "\u516c\u4f17\u53f7",
}

PLATFORM_COLORS = {
    "xhs": "#234f72",
    "douyin": "#2f3f4b",
    "zhihu": "#6e8494",
    "bili": "#4f7a83",
    "wechat": "#8da0aa",
}

DAILY_FIELDS = [
    "platform",
    "platform_name",
    "date",
    "new_followers",
    "lost_followers",
    "net_followers",
    "gross_revenue",
    "refund_amount",
    "net_revenue",
    "content_count",
    "views",
    "exposure",
    "likes",
    "comments",
    "favorites",
    "shares",
    "coins",
    "danmaku",
    "quality_note",
    "source_file",
    "source_mtime",
]

SNAPSHOT_FIELDS = [
    "platform",
    "platform_name",
    "account_key",
    "date",
    "total_followers",
    "quality_note",
    "source_file",
    "source_mtime",
]

CONTENT_FIELDS = [
    "platform",
    "platform_name",
    "account_key",
    "content_partition",
    "snapshot_time",
    "snapshot_date",
    "publish_time",
    "date",
    "content_title",
    "content_type",
    "content_url",
    "content_id",
    "views",
    "exposure",
    "likes",
    "comments",
    "favorites",
    "shares",
    "new_followers",
    "quality_note",
    "source_file",
    "source_mtime",
]


def clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def number(value):
    text = clean(value)
    if text in {"", "-", "--", "nan", "None"}:
        return 0.0
    text = text.replace(",", "").replace("\uffe5", "").replace("\u00a5", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text), 4)
    except ValueError:
        return 0.0


def parse_day(value):
    if value is None or clean(value) == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not math.isnan(value):
        digits = str(int(value))
        if len(digits) >= 8 and digits.startswith("20"):
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    text = clean(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8 and digits.startswith("20"):
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def iso_day(value):
    parsed = parse_day(value)
    return parsed.isoformat() if parsed else ""


def parse_datetime_text(value):
    text = clean(value)
    if not text:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return parsed.to_pydatetime().isoformat(timespec="seconds")
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 14 and digits.startswith("20"):
        try:
            return datetime(
                int(digits[:4]),
                int(digits[4:6]),
                int(digits[6:8]),
                int(digits[8:10]),
                int(digits[10:12]),
                int(digits[12:14]),
            ).isoformat(timespec="seconds")
        except ValueError:
            pass
    day = iso_day(text)
    return day


def relative_source_file(path):
    try:
        return str(path.relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def is_server_sync_path(path):
    return SERVER_SYNC_DIR_NAME in path.parts


def logical_file_key(path):
    parts = [
        part
        for part in relative_source_file(path).replace("\\", "/").split("/")
        if part and part != SERVER_SYNC_DIR_NAME
    ]
    return "/".join(parts).casefold()


def file_freshness_key(path):
    return (
        path.stat().st_mtime,
        1 if is_server_sync_path(path) else 0,
        str(path).casefold(),
    )


def select_latest_logical_files(paths):
    grouped = defaultdict(list)
    for path in paths:
        grouped[logical_file_key(path)].append(path)

    if not grouped:
        return []

    selected = []
    for candidates in grouped.values():
        selected.append(max(candidates, key=file_freshness_key))

    FILE_SELECTION_STATS["candidate_files"] += sum(len(candidates) for candidates in grouped.values())
    FILE_SELECTION_STATS["logical_files"] += len(grouped)
    FILE_SELECTION_STATS["deduped_file_versions"] += sum(max(0, len(candidates) - 1) for candidates in grouped.values())
    FILE_SELECTION_STATS["server_sync_candidates"] += sum(
        1
        for candidates in grouped.values()
        for path in candidates
        if is_server_sync_path(path)
    )
    FILE_SELECTION_STATS["server_sync_selected"] += sum(1 for path in selected if is_server_sync_path(path))
    FILE_SELECTION_STATS["local_selected"] += sum(1 for path in selected if not is_server_sync_path(path))
    return sorted(selected, key=lambda path: relative_source_file(path).casefold())


def source_meta(path):
    return {
        "source_file": relative_source_file(path),
        "source_mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def account_key_from_source(source_file):
    normalized = clean(source_file).replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part != SERVER_SYNC_DIR_NAME]
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else ""


def add_daily(daily, platform, day, note="", source=None, **metrics):
    if not day:
        return
    key = (platform, day)
    row = daily[key]
    row["platform"] = platform
    row["platform_name"] = PLATFORMS[platform]
    row["date"] = day
    if note:
        notes = set(filter(None, row.get("quality_note", "").split(";")))
        notes.add(note)
        row["quality_note"] = ";".join(sorted(notes))
    if source:
        row["source_file"] = source["source_file"]
        row["source_mtime"] = source["source_mtime"]
    for metric, value in metrics.items():
        row[metric] = round(number(row.get(metric, 0)) + number(value), 4)


def add_snapshot(snapshots, platform, day, total, note, source, account_key=""):
    if not day:
        return
    row = {
        "platform": platform,
        "platform_name": PLATFORMS[platform],
        "account_key": clean(account_key) or account_key_from_source(source.get("source_file", "")),
        "date": day,
        "total_followers": number(total),
        "quality_note": note,
        **source,
    }
    snapshots.append(row)


def add_content(
    content_rows,
    platform,
    title,
    publish_time,
    note,
    source,
    content_url="",
    content_id="",
    content_type="",
    content_partition="",
    snapshot_time="",
    account_key="",
    **metrics,
):
    title = clean(title)
    day = iso_day(publish_time)
    if not title or not day:
        return
    stable_content_id = clean(content_id) or f"title:{title}|time:{clean(publish_time)}"
    partition = clean(content_partition) or day[:7]
    snapshot_value = snapshot_time or source.get("source_mtime", "")
    snapshot_iso = parse_datetime_text(snapshot_value)
    snapshot_day = iso_day(snapshot_value)
    row = {
        "platform": platform,
        "platform_name": PLATFORMS[platform],
        "account_key": clean(account_key) or account_key_from_source(source.get("source_file", "")),
        "content_partition": partition,
        "snapshot_time": snapshot_iso,
        "snapshot_date": snapshot_day,
        "publish_time": parse_datetime_text(publish_time),
        "date": day,
        "content_title": title,
        "content_type": clean(content_type),
        "content_url": clean(content_url),
        "content_id": stable_content_id,
        "quality_note": note,
        **source,
    }
    for field in CONTENT_FIELDS:
        row.setdefault(field, "")
    for metric, value in metrics.items():
        row[metric] = number(value)
    content_rows.append(row)


def first_present(row, candidates):
    for candidate in candidates:
        if candidate in row and clean(row.get(candidate)):
            return row.get(candidate)
    return ""


def read_csv(path):
    return pd.read_csv(path, encoding="utf-8-sig")


def read_excel(path, **kwargs):
    return pd.read_excel(path, **kwargs)


def files(root, pattern):
    if not root.exists():
        return []
    return select_latest_logical_files(sorted(root.rglob(pattern)))


def child_startswith(root, prefix):
    for item in root.iterdir():
        if item.is_dir() and item.name.startswith(prefix):
            return item
    return None


def choose_latest_by_mtime(paths):
    paths = list(paths)
    if not paths:
        return None
    return max(paths, key=lambda item: (item.stat().st_mtime, str(item)))


def end_date_from_filename(path):
    matches = re.findall(r"20\d{2}-\d{2}-\d{2}", path.name)
    return matches[-1] if matches else ""


def extract_metric_after_label(text, label):
    if not text:
        return 0
    compact = clean(text).replace("\r\n", "\n")
    pattern = re.compile(re.escape(label) + r"\s*\n?\s*([+-]?\d[\d,]*)")
    match = pattern.search(compact)
    return number(match.group(1)) if match else 0


def xhs_follower_growth_metric_type(value):
    text = clean(value)
    if text in {"lost_followers", "new_followers", "net_followers"}:
        return text
    if any(token in text for token in ["取消关注", "取关", "流失"]):
        return "lost_followers"
    if any(token in text for token in ["新增关注", "新增粉丝"]):
        return "new_followers"
    if any(token in text for token in ["净涨粉", "净增", "涨粉趋势"]):
        return "net_followers"
    return ""


def find_column(df, tokens):
    for col in df.columns:
        name = clean(col)
        if any(token in name for token in tokens):
            return col
    return None


def ingest_xhs_account_follower_growth_file(path, daily):
    meta = source_meta(path)
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except Exception:
        return 0

    added = 0
    for sheet_name, df in sheets.items():
        if df is None or df.empty:
            continue
        date_col = find_column(df, ["日期", "时间"])
        if date_col is None:
            continue

        sheet_metric_type = xhs_follower_growth_metric_type(sheet_name)
        for _, row in df.iterrows():
            day = iso_day(row.get(date_col))
            if not day:
                continue
            row_metric_type = (
                xhs_follower_growth_metric_type(row.get("metric_type"))
                or xhs_follower_growth_metric_type(row.get("source_sheet"))
                or sheet_metric_type
            )
            metrics = {}
            for col in df.columns:
                if col == date_col:
                    continue
                col_name = clean(col)
                if col_name in {"source_file", "source_mtime", "source_sheet", "metric_type"}:
                    continue
                metric_type = xhs_follower_growth_metric_type(col_name)
                if not metric_type and col_name in {"数值", "值", "指标值"}:
                    metric_type = row_metric_type
                if not metric_type:
                    continue
                if clean(row.get(col)) == "":
                    continue
                metrics[metric_type] = number(row.get(col))

            if "net_followers" not in metrics and "new_followers" in metrics and "lost_followers" in metrics:
                metrics["net_followers"] = round(
                    number(metrics.get("new_followers")) - number(metrics.get("lost_followers")),
                    4,
                )
            if not metrics:
                continue
            add_daily(
                daily,
                "xhs",
                day,
                note="account_follower_growth",
                source=meta,
                **metrics,
            )
            added += 1
    return added


def scan_xhs(daily, snapshots, content_rows, source_counts):
    content_root = child_startswith(DATA_ROOT, "\u5c0f\u7ea2\u4e66\u5185\u5bb9")
    shop_root = child_startswith(DATA_ROOT, "\u5c0f\u7ea2\u4e66\u7535\u5546")
    if content_root:
        fan_files = files(content_root, "monthly/fans_snapshot/*.xlsx")
        source_counts["xhs_fans_snapshot"] = len(fan_files)
        for path in fan_files:
            df = read_excel(path)
            meta = source_meta(path)
            for _, row in df.iterrows():
                day = iso_day(row.get("\u65e5\u671f"))
                add_snapshot(
                    snapshots,
                    "xhs",
                    day,
                    row.get("\u603b\u7c89\u4e1d"),
                    "account_total_snapshot",
                    meta,
                    account_key=row.get("\u8d26\u53f7"),
                )

        growth_files = files(content_root, "raw/account_follower_growth/**/*.xlsx")
        growth_source = "raw"
        if not growth_files:
            growth_files = files(content_root, "monthly/account_follower_growth/*.xlsx")
            growth_source = "monthly_fallback"
        source_counts["xhs_account_follower_growth"] = len(growth_files)
        source_counts["xhs_account_follower_growth_source"] = growth_source if growth_files else ""
        source_counts["xhs_account_follower_growth_daily_rows"] = sum(
            ingest_xhs_account_follower_growth_file(path, daily)
            for path in growth_files
        )

        content_files = files(content_root, "monthly/content_analysis/*.xlsx")
        raw_content_files = files(content_root, "raw/content_analysis/**/*.xlsx")
        source_counts["xhs_content_monthly"] = len(content_files)
        source_counts["xhs_content_raw"] = len(raw_content_files)
        source_counts["xhs_content_dashboard_source"] = "monthly_snapshot" if content_files else "raw_fallback"
        seen = set()
        display_content_files = content_files or raw_content_files
        for path in display_content_files:
            meta = source_meta(path)
            df = read_excel(path) if content_files else read_excel(path, header=1)
            note = "monthly_content_snapshot" if content_files else "raw_content_analysis"
            ingest_xhs_content_dataframe(df, daily, content_rows, meta, seen, note)

        overview_files = files(content_root, "monthly/account_overview/*.xlsx")
        source_counts["xhs_account_overview"] = len(overview_files)
        for path in overview_files:
            meta = source_meta(path)
            df = read_excel(path)
            if df.shape[1] < 2:
                continue
            metrics = {}
            for _, row in df.iterrows():
                label = clean(row.iloc[0])
                value = row.iloc[1]
                if label == "\u89c2\u770b":
                    metrics["views"] = value
                elif label == "\u66dd\u5149":
                    metrics["exposure"] = value
            if metrics:
                day = meta["source_mtime"][:10]
                add_daily(
                    daily,
                    "xhs",
                    day,
                    note="rolling_30d_account_overview",
                    source=meta,
                    **metrics,
                )

    if shop_root:
        shop_files = files(shop_root, "raw/datacenter_overview/**/*.xlsx")
        source_counts["xhs_shop_datacenter"] = len(shop_files)
        latest_by_end_date = {}
        for path in shop_files:
            end_day = end_date_from_filename(path)
            if not end_day:
                continue
            prev = latest_by_end_date.get(end_day)
            if prev is None or path.stat().st_mtime > prev.stat().st_mtime:
                latest_by_end_date[end_day] = path
        for end_day, path in sorted(latest_by_end_date.items()):
            meta = source_meta(path)
            df = read_excel(path)
            if df.empty:
                continue
            row = df.iloc[0]
            gross = number(row.get("\u652f\u4ed8\u91d1\u989d"))
            refund = number(row.get("\u9000\u6b3e\u91d1\u989d\uff08\u9000\u6b3e\u65f6\u95f4\uff09"))
            add_daily(
                daily,
                "xhs",
                end_day,
                note="rolling_window_revenue_snapshot",
                source=meta,
                gross_revenue=gross,
                refund_amount=refund,
                net_revenue=round(gross - refund, 4),
            )


def ingest_xhs_content_dataframe(df, daily, content_rows, meta, seen, note):
    required = ["\u7b14\u8bb0\u6807\u9898", "\u9996\u6b21\u53d1\u5e03\u65f6\u95f4"]
    if any(col not in df.columns for col in required):
        return
    for _, row in df.iterrows():
        title = row.get("\u7b14\u8bb0\u6807\u9898")
        publish = row.get("\u9996\u6b21\u53d1\u5e03\u65f6\u95f4")
        account_key = account_key_from_source(meta.get("source_file", ""))
        key = ("xhs", account_key, clean(title), parse_datetime_text(publish))
        if key in seen:
            continue
        seen.add(key)
        day = iso_day(publish)
        add_daily(
            daily,
            "xhs",
            day,
            note="content_attributed",
            source=meta,
            content_count=1,
            views=row.get("\u89c2\u770b\u91cf"),
            exposure=row.get("\u66dd\u5149"),
            likes=row.get("\u70b9\u8d5e"),
            comments=row.get("\u8bc4\u8bba"),
            favorites=row.get("\u6536\u85cf"),
            shares=row.get("\u5206\u4eab"),
        )
        add_content(
            content_rows,
            "xhs",
            title,
            publish,
            note,
            meta,
            content_url=first_present(row, ["\u7b14\u8bb0\u94fe\u63a5", "\u94fe\u63a5", "URL", "url"]),
            content_id=first_present(row, ["\u5185\u5bb9\u552f\u4e00\u952e", "\u7b14\u8bb0ID", "\u7b14\u8bb0id", "note_id", "id"]),
            content_type=row.get("\u4f53\u88c1"),
            content_partition=row.get("\u5185\u5bb9\u5206\u533a"),
            snapshot_time=first_present(row, ["\u5feb\u7167\u91c7\u96c6\u65f6\u95f4", "source_mtime"]),
            account_key=account_key,
            views=row.get("\u89c2\u770b\u91cf"),
            exposure=row.get("\u66dd\u5149"),
            likes=row.get("\u70b9\u8d5e"),
            comments=row.get("\u8bc4\u8bba"),
            favorites=row.get("\u6536\u85cf"),
            shares=row.get("\u5206\u4eab"),
            new_followers=row.get("\u6da8\u7c89"),
        )


def scan_douyin(daily, snapshots, content_rows, source_counts):
    root = child_startswith(DATA_ROOT, "\u6296\u97f3")
    if not root:
        return
    operation_files = files(root, "monthly/operation/*.xlsx")
    source_counts["douyin_operation"] = len(operation_files)
    for path in operation_files:
        meta = source_meta(path)
        df = read_excel(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("\u65e5\u671f"))
            add_snapshot(snapshots, "douyin", day, row.get("\u603b\u7c89\u4e1d\u91cf"), "account_total_snapshot", meta)
            add_daily(
                daily,
                "douyin",
                day,
                source=meta,
                new_followers=row.get("\u51c0\u589e\u7c89\u4e1d"),
                lost_followers=row.get("\u53d6\u5173\u7c89\u4e1d"),
                net_followers=row.get("\u51c0\u589e\u7c89\u4e1d"),
                views=row.get("\u64ad\u653e\u91cf"),
                likes=row.get("\u4f5c\u54c1\u70b9\u8d5e"),
                comments=row.get("\u4f5c\u54c1\u8bc4\u8bba"),
                shares=row.get("\u4f5c\u54c1\u5206\u4eab"),
            )

    monthly_content_files = files(root, "monthly/content_list/*.xlsx")
    raw_content_files = files(root, "raw/content_list/**/*.xlsx")
    # 合并 monthly + raw，按文件路径中的年月（如 2026-08）降序排序：最新月份
    # 的快照先处理，同一内容第一次入 seen 即最新版本，旧 monthly/raw 中的
    # 重复行被跳过。修复 8 月 raw 已下载但 monthly 缺 8 月导致内容快照停在
    # 7 月的问题。不能用 source_mtime 排序：monthly 文件 mtime 是同步时间
    # （8-7），raw 文件 mtime 是原始采集时间（6-7 月），会让 monthly 先入
    # seen 反而把 8 月 raw 跳过。
    def _sort_key(p):
        # 年月（如 2026-08）+ 文件 mtime，均降序：8 月 raw 先于 7 月 monthly，
        # 同年月内最新 mtime 先处理（8-7 raw 先于 8-2 raw）。
        m = re.search(r"(20\d{2}-\d{2})", str(p))
        ym = m.group(1) if m else ""
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (ym, mtime)
    content_files = sorted(
        set(monthly_content_files) | set(raw_content_files),
        key=_sort_key,
        reverse=True,
    )
    source_counts["douyin_content_list"] = len(content_files)
    source_counts["douyin_content_dashboard_source"] = "monthly_and_raw_merged"
    seen = set()
    for path in content_files:
        meta = source_meta(path)
        df = read_excel(path)
        for _, row in df.iterrows():
            title = row.get("\u4f5c\u54c1\u540d\u79f0")
            publish = row.get("\u53d1\u5e03\u65f6\u95f4")
            account_key = account_key_from_source(meta.get("source_file", ""))
            key = ("douyin", account_key, clean(title), parse_datetime_text(publish))
            if key in seen:
                continue
            seen.add(key)
            day = iso_day(publish)
            add_daily(
                daily,
                "douyin",
                day,
                note="content_item",
                source=meta,
                content_count=1,
            )
            add_content(
                content_rows,
                "douyin",
                title,
                publish,
                "content_item",
                meta,
                content_url=first_present(row, ["\u4f5c\u54c1\u94fe\u63a5", "\u94fe\u63a5", "URL", "url"]),
                content_id=first_present(row, ["\u5185\u5bb9\u552f\u4e00\u952e", "\u4f5c\u54c1ID", "\u4f5c\u54c1id", "item_id", "id"]),
                content_type=row.get("\u4f53\u88c1"),
                content_partition=row.get("\u5185\u5bb9\u5206\u533a"),
                snapshot_time=first_present(row, ["\u5feb\u7167\u91c7\u96c6\u65f6\u95f4", "source_mtime"]),
                account_key=account_key,
                views=row.get("\u64ad\u653e\u91cf"),
                likes=row.get("\u70b9\u8d5e\u91cf"),
                comments=row.get("\u8bc4\u8bba\u91cf"),
                favorites=row.get("\u6536\u85cf\u91cf"),
                shares=row.get("\u5206\u4eab\u91cf"),
                new_followers=row.get("\u7c89\u4e1d\u589e\u91cf"),
            )


def scan_zhihu(daily, snapshots, content_rows, source_counts):
    root = child_startswith(DATA_ROOT, "\u77e5\u4e4e")
    if not root:
        return
    follower_files = files(root, "monthly/followers/*.xlsx")
    source_counts["zhihu_followers"] = len(follower_files)
    for path in follower_files:
        meta = source_meta(path)
        df = read_excel(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("\u65e5\u671f"))
            add_snapshot(snapshots, "zhihu", day, row.get("\u5173\u6ce8\u8005\u603b\u6570"), "account_total_snapshot", meta)
            add_daily(
                daily,
                "zhihu",
                day,
                source=meta,
                new_followers=row.get("\u65b0\u589e\u5173\u6ce8\u8005"),
                lost_followers=row.get("\u51cf\u5c11\u5173\u6ce8\u8005"),
                net_followers=row.get("\u5173\u6ce8\u8005\u53d8\u5316"),
            )

    content_files = files(root, "monthly/content_analytics/*.xlsx")
    source_counts["zhihu_content_analytics"] = len(content_files)
    for path in content_files:
        meta = source_meta(path)
        df = read_excel(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("\u65e5\u671f"))
            add_daily(
                daily,
                "zhihu",
                day,
                note="daily_content_summary",
                source=meta,
                views=number(row.get("\u9605\u8bfb")) + number(row.get("\u64ad\u653e")),
                likes=number(row.get("\u70b9\u8d5e")) + number(row.get("\u559c\u6b22")),
                comments=row.get("\u8bc4\u8bba"),
                favorites=row.get("\u6536\u85cf"),
                shares=row.get("\u5206\u4eab"),
            )


def scan_bili(daily, snapshots, content_rows, source_counts):
    root = child_startswith(DATA_ROOT, "B")
    if not root:
        return
    fan_files = files(root, "monthly/\u7c89\u4e1d\u6570\u636e/*.xlsx")
    source_counts["bili_fans"] = len(fan_files)
    for path in fan_files:
        meta = source_meta(path)
        df = read_excel(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("\u65f6\u95f4"))
            new_followers = number(row.get("\u65b0\u589e\u5173\u6ce8"))
            lost_followers = number(row.get("\u53d6\u6d88\u5173\u6ce8"))
            add_snapshot(snapshots, "bili", day, row.get("\u7c89\u4e1d\u603b\u6570"), "account_total_snapshot", meta)
            add_daily(
                daily,
                "bili",
                day,
                source=meta,
                new_followers=new_followers,
                lost_followers=lost_followers,
                net_followers=round(new_followers - lost_followers, 4),
            )

    daily_files = files(root, "monthly/\u535a\u4e3b\u65e5\u5e38\u6570\u636e/*.xlsx")
    source_counts["bili_daily"] = len(daily_files)
    for path in daily_files:
        meta = source_meta(path)
        df = read_excel(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("\u65f6\u95f4"))
            add_daily(
                daily,
                "bili",
                day,
                note="daily_account_summary",
                source=meta,
                views=row.get("\u64ad\u653e\u91cf"),
                likes=row.get("\u70b9\u8d5e"),
                comments=row.get("\u8bc4\u8bba"),
                favorites=row.get("\u6536\u85cf"),
                shares=row.get("\u5206\u4eab"),
                coins=row.get("\u786c\u5e01"),
                danmaku=row.get("\u5f39\u5e55"),
            )

    sales_files = files(root, "monthly/\u5546\u54c1\u9500\u552e\u6570\u636e/*.xlsx")
    source_counts["bili_sales"] = len(sales_files)
    for path in sales_files:
        meta = source_meta(path)
        df = read_excel(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("\u4e0b\u5355\u65f6\u95f4"))
            amount = row.get("\u5b9e\u9645\u6210\u4ea4\u91d1\u989d")
            add_daily(
                daily,
                "bili",
                day,
                source=meta,
                gross_revenue=amount,
                net_revenue=amount,
            )


def scan_wechat(daily, snapshots, content_rows, source_counts):
    root = child_startswith(DATA_ROOT, "\u516c\u4f17\u53f7")
    if not root:
        return
    user_files = files(root, "user_stats/*.csv")
    source_counts["wechat_user_stats"] = len(user_files)
    for path in user_files:
        meta = source_meta(path)
        df = read_csv(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("date"))
            add_snapshot(snapshots, "wechat", day, row.get("total_followers"), "account_total_snapshot", meta)
            add_daily(
                daily,
                "wechat",
                day,
                source=meta,
                new_followers=row.get("new_followers"),
                lost_followers=row.get("unfollowed"),
                net_followers=row.get("net_increase"),
            )

    content_files = files(root, "content_stats/*.csv")
    source_counts["wechat_content_stats"] = len(content_files)
    for path in content_files:
        meta = source_meta(path)
        df = read_csv(path)
        for _, row in df.iterrows():
            day = iso_day(row.get("date"))
            add_daily(
                daily,
                "wechat",
                day,
                note="daily_content_engagement_summary",
                source=meta,
                views=row.get("reads"),
                shares=row.get("shares"),
                comments=row.get("comments"),
            )

    article_candidates = sorted(root.rglob("article_stats/**/article_list.json")) + sorted(
        root.rglob("article_stats/raw/**/*_article_list.json")
    )
    article_files = select_latest_logical_files(article_candidates)
    source_counts["wechat_article_stats"] = len(article_files)
    latest_articles = {}
    for path in article_files:
        meta = source_meta(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("article_list", []):
            article_id = clean(f"{item.get('msg_id', '')}:{item.get('item_idx', '')}")
            if article_id == ":":
                article_id = f"title:{clean(item.get('title'))}|date:{iso_day(item.get('ref_date'))}"
            account_key = account_key_from_source(meta.get("source_file", ""))
            key = ("wechat", account_key, article_id)
            current = latest_articles.get(key)
            if current and current["source"].get("source_mtime", "") >= meta.get("source_mtime", ""):
                continue
            latest_articles[key] = {
                "item": item,
                "source": meta,
                "account_key": account_key,
                "article_id": article_id,
            }

    for article in latest_articles.values():
        item = article["item"]
        meta = article["source"]
        day = iso_day(item.get("ref_date"))
        add_daily(
            daily,
            "wechat",
            day,
            note="article_publish_item",
            source=meta,
            content_count=1,
        )
        add_content(
            content_rows,
            "wechat",
            item.get("title"),
            item.get("ref_date"),
            "article_list_snapshot",
            meta,
            content_id=article["article_id"],
            account_key=article["account_key"],
            views=item.get("total_read_uv"),
        )


def prepare_rows(daily):
    rows = []
    for platform in PLATFORMS:
        platform_dates = sorted(day for current_platform, day in daily if current_platform == platform)
        for day in platform_dates:
            row = dict(daily[(platform, day)])
            for field in DAILY_FIELDS:
                row.setdefault(field, 0 if field not in {"platform", "platform_name", "date", "quality_note", "source_file", "source_mtime"} else "")
            rows.append({field: row.get(field, "") for field in DAILY_FIELDS})
    return rows


def latest_content_snapshot_rows(content_rows):
    # 按 (platform, account, content_id 或 title+publish) 分组，每组取最新 snapshot_day。
    # 旧逻辑按 (platform, account) 取最新快照日再保留该日所有行，对按月分区的小红书
    # 内容文件会丢失非最新快照日所在分区的内容（如 8-05 快照日只含 2 月分区时，
    # 3~7 月内容全部缺失）。新逻辑按内容维度去重，保留所有月份内容，仅对同一内容
    # 的多次快照取最新一次，避免重复。
    latest_by_content = {}
    for row in content_rows:
        snapshot_day = row.get("snapshot_date") or iso_day(row.get("source_mtime"))
        if not snapshot_day:
            continue
        account_key = row.get("account_key") or row.get("platform")
        content_key = (
            row.get("platform"),
            account_key,
            row.get("content_id") or row.get("content_title"),
            row.get("publish_time") or row.get("date"),
        )
        prev = latest_by_content.get(content_key)
        if prev is None or snapshot_day > prev[0]:
            latest_by_content[content_key] = (snapshot_day, row)
    if not latest_by_content:
        return content_rows

    latest_rows = []
    seen = set()
    for _snap_day, row in latest_by_content.values():
        account_key = row.get("account_key") or row.get("platform")
        content_key = (
            row.get("platform"),
            account_key,
            row.get("content_id") or row.get("content_title"),
            row.get("publish_time") or row.get("date"),
        )
        if content_key in seen:
            continue
        seen.add(content_key)
        latest_rows.append(row)
    return latest_rows


def content_snapshot_dates(content_rows):
    latest = {}
    for row in content_rows:
        account_key = row.get("account_key") or row.get("platform")
        key = f"{row.get('platform')}:{account_key}"
        snapshot_day = row.get("snapshot_date") or iso_day(row.get("source_mtime"))
        if snapshot_day and (key not in latest or snapshot_day > latest[key]):
            latest[key] = snapshot_day
    return latest


def snapshot_account_key(row):
    return row.get("account_key") or account_key_from_source(row.get("source_file", "")) or row.get("platform", "")


def latest_account_snapshots(snapshots):
    latest = {}
    for row in snapshots:
        key = (row.get("platform"), snapshot_account_key(row))
        current = latest.get(key)
        row_order = (row.get("date", ""), row.get("source_mtime", ""))
        current_order = (current.get("date", ""), current.get("source_mtime", "")) if current else ("", "")
        if current is None or row_order > current_order:
            latest[key] = row
    return latest


def latest_snapshots(snapshots):
    latest = {}
    for row in latest_account_snapshots(snapshots).values():
        platform = row["platform"]
        aggregate = latest.setdefault(
            platform,
            {
                "platform": platform,
                "platform_name": PLATFORMS[platform],
                "date": "",
                "total_followers": 0,
            },
        )
        aggregate["total_followers"] = round(
            number(aggregate.get("total_followers")) + number(row.get("total_followers")),
            4,
        )
        if row.get("date", "") > aggregate.get("date", ""):
            aggregate["date"] = row.get("date", "")
    return latest


def snapshot_month_delta(snapshots, platform, month_start, date_max):
    by_account = defaultdict(list)
    for row in snapshots:
        if row.get("platform") != platform:
            continue
        day = row.get("date", "")
        if not (month_start <= day <= date_max):
            continue
        by_account[snapshot_account_key(row)].append(row)

    delta = 0
    account_count = 0
    first_date = ""
    latest_date = ""
    for rows in by_account.values():
        ordered = sorted(rows, key=lambda row: (row.get("date", ""), row.get("source_mtime", "")))
        if not ordered:
            continue
        first = ordered[0]
        latest = ordered[-1]
        delta += number(latest.get("total_followers")) - number(first.get("total_followers"))
        account_count += 1
        if first.get("date") and (not first_date or first.get("date") < first_date):
            first_date = first.get("date")
        if latest.get("date") and latest.get("date") > latest_date:
            latest_date = latest.get("date")

    return {
        "delta": round(delta, 4),
        "account_count": account_count,
        "first_date": first_date,
        "latest_date": latest_date,
    }


def day_diff(later_day, earlier_day):
    later = parse_day(later_day)
    earlier = parse_day(earlier_day)
    if not later or not earlier:
        return None
    return (later - earlier).days


def freshness_status(as_of_day, latest_day):
    if not latest_day:
        return "missing"
    age = day_diff(as_of_day, latest_day)
    if age is None:
        return "unknown"
    if age <= FRESHNESS_READY_DAYS:
        return "ready"
    if age <= FRESHNESS_LATE_DAYS:
        return "late"
    return "stale"


def worst_freshness_status(statuses):
    order = {
        "ready": 0,
        "unknown": 1,
        "late": 2,
        "stale": 3,
        "missing": 4,
    }
    return max((status for status in statuses if status), key=lambda status: order.get(status, 1), default="missing")


def account_snapshot_health(snapshots, platform, as_of_day):
    rows = []
    for (row_platform, account_key), row in sorted(latest_account_snapshots(snapshots).items()):
        if row_platform != platform:
            continue
        latest_day = row.get("date", "")
        age = day_diff(as_of_day, latest_day)
        rows.append({
            "account_key": account_key,
            "latest_date": latest_day,
            "staleness_days": age if age is not None else "",
            "status": freshness_status(as_of_day, latest_day),
            "total_followers": row.get("total_followers", 0),
            "source_file": row.get("source_file", ""),
            "source_mtime": row.get("source_mtime", ""),
        })
    return rows


def content_snapshot_health(content_rows, platform, as_of_day):
    latest = {}
    for row in content_rows:
        if row.get("platform") != platform:
            continue
        account_key = row.get("account_key") or row.get("platform")
        snapshot_day = row.get("snapshot_date") or iso_day(row.get("source_mtime"))
        if snapshot_day and snapshot_day > latest.get(account_key, ""):
            latest[account_key] = snapshot_day
    rows = []
    for account_key, latest_day in sorted(latest.items()):
        age = day_diff(as_of_day, latest_day)
        rows.append({
            "account_key": account_key,
            "latest_date": latest_day,
            "staleness_days": age if age is not None else "",
            "status": freshness_status(as_of_day, latest_day),
        })
    return rows


def latest_daily_row_with_note(daily_rows, platform, note_token):
    rows = [
        row for row in daily_rows
        if row.get("platform") == platform and note_token in clean(row.get("quality_note"))
    ]
    return max(rows, key=lambda row: row.get("date", ""), default=None)


def date_bounds(daily_rows, snapshots):
    dates = [row["date"] for row in daily_rows if row.get("date")] + [row["date"] for row in snapshots if row.get("date")]
    if not dates:
        today = date.today().isoformat()
        return today, today, today[:7]
    latest_day = max(dates)
    return min(dates), latest_day, latest_day[:7]


def summarize(daily_rows, snapshots, content_rows, content_detail_rows, source_counts):
    date_min, date_max, latest_month = date_bounds(daily_rows, snapshots)
    month_start = f"{latest_month}-01"
    latest = latest_snapshots(snapshots)
    summary_platforms = []
    for platform, name in PLATFORMS.items():
        month_rows = [
            row for row in daily_rows
            if row["platform"] == platform and month_start <= row["date"] <= date_max
        ]
        follower_rows = [
            row for row in month_rows
            if "period_fans_snapshot" not in clean(row.get("quality_note"))
        ]
        all_rows = [row for row in daily_rows if row["platform"] == platform]
        latest_daily_date = max((row["date"] for row in all_rows), default="")
        if platform == "xhs":
            revenue_rows = [
                row for row in month_rows
                if "rolling_window_revenue_snapshot" in clean(row.get("quality_note"))
            ]
            latest_revenue_row = max(revenue_rows, key=lambda row: row["date"], default=None)
            month_net_revenue = number(latest_revenue_row.get("net_revenue")) if latest_revenue_row else 0
        else:
            month_net_revenue = round(sum(number(row["net_revenue"]) for row in month_rows), 4)
        month_net_followers = round(sum(number(row["net_followers"]) for row in follower_rows), 4)
        month_new_followers = round(sum(number(row["new_followers"]) for row in follower_rows), 4)
        month_lost_followers = round(sum(number(row["lost_followers"]) for row in follower_rows), 4)
        if platform == "xhs" and not source_counts.get("xhs_account_follower_growth_daily_rows"):
            xhs_snapshot_delta = snapshot_month_delta(snapshots, platform, month_start, date_max)
            if xhs_snapshot_delta["account_count"]:
                month_net_followers = xhs_snapshot_delta["delta"]
                month_new_followers = 0
                month_lost_followers = 0
                source_counts["xhs_follower_snapshot_delta"] = xhs_snapshot_delta
        account_health = account_snapshot_health(snapshots, platform, date_max)
        content_health = content_snapshot_health(content_detail_rows, platform, date_max)
        freshness_statuses = [freshness_status(date_max, latest_daily_date)]
        freshness_statuses.extend(item["status"] for item in account_health)
        freshness_statuses.extend(item["status"] for item in content_health)
        freshness_issues = []
        for item in account_health:
            if item["status"] not in {"ready", "unknown"}:
                freshness_issues.append(
                    f"{item['account_key']} total followers latest {item['latest_date']}"
                )
        for item in content_health:
            if item["status"] not in {"ready", "unknown"}:
                freshness_issues.append(
                    f"{item['account_key']} content snapshot latest {item['latest_date']}"
                )
        shop_latest_revenue_date = ""
        if platform == "xhs":
            latest_revenue_row = latest_daily_row_with_note(daily_rows, platform, "rolling_window_revenue_snapshot")
            shop_latest_revenue_date = latest_revenue_row.get("date", "") if latest_revenue_row else ""
            shop_status = freshness_status(date_max, shop_latest_revenue_date)
            freshness_statuses.append(shop_status)
            if shop_status not in {"ready", "unknown"}:
                freshness_issues.append(f"xhs shop revenue latest {shop_latest_revenue_date}")
        summary_platforms.append({
            "platform": platform,
            "platform_name": name,
            "latest_total_followers": latest.get(platform, {}).get("total_followers", 0),
            "latest_total_followers_date": latest.get(platform, {}).get("date", ""),
            "latest_daily_date": latest_daily_date,
            "month_net_followers": month_net_followers,
            "month_new_followers": month_new_followers,
            "month_lost_followers": month_lost_followers,
            "month_net_revenue": month_net_revenue,
            "month_content_count": round(sum(number(row["content_count"]) for row in month_rows), 4),
            "month_views": round(sum(number(row["views"]) for row in month_rows), 4),
            "freshness_status": worst_freshness_status(freshness_statuses),
            "freshness_issues": freshness_issues,
            "account_snapshots": account_health,
            "content_snapshots": content_health,
            "shop_latest_revenue_date": shop_latest_revenue_date,
        })
    total_followers = round(sum(number(row["latest_total_followers"]) for row in summary_platforms), 4)
    total_revenue = round(sum(number(row["month_net_revenue"]) for row in summary_platforms), 4)
    total_net_followers = round(sum(number(row["month_net_followers"]) for row in summary_platforms), 4)
    total_content = round(sum(number(row["month_content_count"]) for row in summary_platforms), 4)
    return {
        "schema": "self-media-normalized.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(DATA_ROOT),
        "normalized_dir": str(OUT_DIR),
        "date_min": date_min,
        "date_max": date_max,
        "latest_month": latest_month,
        "current_month_start": month_start,
        "totals": {
            "total_followers": total_followers,
            "month_net_followers": total_net_followers,
            "month_net_revenue": total_revenue,
            "month_content_count": total_content,
        },
        "platforms": summary_platforms,
        "row_counts": {
            "daily_metrics": len(daily_rows),
            "platform_snapshots": len(snapshots),
            "content_items": len(content_rows),
            "content_detail_items": len(content_detail_rows),
        },
        "source_counts": source_counts,
        "content_snapshot_dates": content_snapshot_dates(content_detail_rows),
        "notes": [
            "\u5c0f\u7ea2\u4e66\u6bcf\u65e5\u7c89\u4e1d\u589e\u957f\u53ea\u4f7f\u7528\u8d26\u53f7\u6982\u89c8-\u6da8\u7c89\u6570\u636e\u5bfc\u51fa\uff0cquality_note=account_follower_growth\uff0c\u4e0d\u7528\u603b\u7c89\u4e1d\u5feb\u7167\u53cd\u63a8\u6216\u5747\u644a\u3002",
            "\u5c0f\u7ea2\u4e66\u672c\u6708\u51c0\u589e\u7c89\u4e1d\u4f18\u5148\u6c47\u603b account_follower_growth \u65e5\u7c92\u5ea6\u51c0\u6da8\u7c89\uff1b\u82e5\u7f3a\u5c11\u8be5\u5bfc\u51fa\uff0c\u624d\u9000\u56de\u603b\u7c89\u4e1d\u5feb\u7167\u6708\u521d/\u6708\u672b\u5dee\u503c\u3002",
            "\u5c0f\u7ea2\u4e66\u5185\u5bb9\u8868\u4e2d\u7684\u6da8\u7c89\u53ea\u4fdd\u7559\u5728\u5185\u5bb9\u660e\u7ec6\uff0cquality_note=content_attributed\u3002",
            "\u5c0f\u7ea2\u4e66\u89c2\u770b/\u66dd\u5149\u6765\u81ea\u8d26\u53f7\u6982\u89c8\u8fd130\u65e5\u5feb\u7167\uff0cquality_note=rolling_30d_account_overview\u3002",
            "\u5c0f\u7ea2\u4e66\u5e97\u94fa\u6536\u5165\u76ee\u524d\u662f\u533a\u95f4\u6c47\u603b\u5feb\u7167\uff0cquality_note=rolling_window_revenue_snapshot\u3002",
            "B\u7ad9\u51c0\u589e\u7c89\u4e1d=\u65b0\u589e\u5173\u6ce8-\u53d6\u6d88\u5173\u6ce8\u3002",
            "\u6296\u97f3\u3001\u77e5\u4e4e\u3001\u516c\u4f17\u53f7\u6536\u5165\u6309 0 \u5904\u7406\u3002",
            "\u5185\u5bb9\u660e\u7ec6\u5168\u91cf\u4fdd\u7559\u5728 self_media_content_detail.csv\uff1bself_media_content_items.csv \u548c\u770b\u677f\u53ea\u4f7f\u7528\u6bcf\u4e2a\u5e73\u53f0/\u8d26\u53f7\u6700\u65b0\u5feb\u7167\u65e5\u7684\u884c\u3002",
            "\u670d\u52a1\u5668\u540c\u6b65\u6570\u636e\u4e0e\u672c\u5730\u539f\u6709\u6587\u6863\u6309\u53bb\u6389\u201c\u670d\u52a1\u5668\u540c\u6b65\u201d\u540e\u7684\u903b\u8f91\u6587\u4ef6\u8def\u5f84\u878d\u5408\uff0c\u540c\u8def\u5f84\u53ea\u53d6\u6700\u65b0\u7248\u672c\uff0c\u5e76\u4fdd\u7559 source_file/source_mtime \u4fbf\u4e8e\u56de\u6eaf\u3002",
        ],
    }


def interaction_total(row):
    return round(
        sum(number(row.get(field)) for field in ["likes", "comments", "favorites", "shares", "coins", "danmaku"]),
        4,
    )


def build_dashboard_payload(daily_rows, snapshots, content_rows, summary):
    platform_summary = {row["platform"]: row for row in summary["platforms"]}
    current_month_start = summary["current_month_start"]
    date_max = summary["date_max"]
    interactions_by_platform = defaultdict(float)
    for row in daily_rows:
        if current_month_start <= row["date"] <= date_max:
            interactions_by_platform[row["platform"]] += interaction_total(row)

    platforms_payload = []
    for platform, name in PLATFORMS.items():
        row = platform_summary.get(platform, {})
        platforms_payload.append({
            "id": platform,
            "name": name,
            "color": PLATFORM_COLORS[platform],
            "fans": round(number(row.get("latest_total_followers"))),
            "newFans": round(number(row.get("month_net_followers"))),
            "revenue": round(number(row.get("month_net_revenue")), 2),
            "posts": round(number(row.get("month_content_count"))),
            "play": round(number(row.get("month_views"))),
            "interact": round(interactions_by_platform[platform]),
            "hasDailyFollowerMetric": platform != "xhs" or bool(summary.get("source_counts", {}).get("xhs_account_follower_growth_daily_rows")),
            "hasTotalFollowers": bool(row.get("latest_total_followers_date")),
            "totalFollowersDate": row.get("latest_total_followers_date", ""),
            "latestDailyDate": row.get("latest_daily_date", ""),
            "newFollowers": round(number(row.get("month_new_followers"))),
            "lostFollowers": round(number(row.get("month_lost_followers"))),
            "freshnessStatus": row.get("freshness_status", "missing"),
            "freshnessIssues": row.get("freshness_issues", []),
            "accounts": [
                {
                    "accountKey": item.get("account_key", ""),
                    "latestDate": item.get("latest_date", ""),
                    "stalenessDays": item.get("staleness_days", ""),
                    "status": item.get("status", "unknown"),
                    "totalFollowers": round(number(item.get("total_followers"))),
                    "sourceFile": item.get("source_file", ""),
                    "sourceMtime": item.get("source_mtime", ""),
                }
                for item in row.get("account_snapshots", [])
            ],
            "contentSnapshots": [
                {
                    "accountKey": item.get("account_key", ""),
                    "latestDate": item.get("latest_date", ""),
                    "stalenessDays": item.get("staleness_days", ""),
                    "status": item.get("status", "unknown"),
                }
                for item in row.get("content_snapshots", [])
            ],
            "shopLatestRevenueDate": row.get("shop_latest_revenue_date", ""),
        })

    daily_by_date = {}
    for row in daily_rows:
        day = row["date"]
        platform = row["platform"]
        note = clean(row.get("quality_note"))
        is_rolling_xhs_revenue = platform == "xhs" and "rolling_window_revenue_snapshot" in note
        is_rolling_xhs_view = platform == "xhs" and "rolling_30d_account_overview" in note
        is_real_xhs_growth = platform == "xhs" and "account_follower_growth" in note
        is_period_xhs_fans = platform == "xhs" and "period_fans_snapshot" in note and not is_real_xhs_growth
        entry = daily_by_date.setdefault(day, {"date": day, "platforms": {}})
        entry["platforms"][platform] = {
            "fans": 0 if is_period_xhs_fans else round(number(row.get("net_followers"))),
            "newFans": 0 if is_period_xhs_fans else round(number(row.get("new_followers"))),
            "lostFans": 0 if is_period_xhs_fans else round(number(row.get("lost_followers"))),
            "revenue": 0 if is_rolling_xhs_revenue else round(number(row.get("net_revenue")), 2),
            "revenueSnapshot": round(number(row.get("net_revenue")), 2) if is_rolling_xhs_revenue else 0,
            "grossRevenueSnapshot": round(number(row.get("gross_revenue")), 2) if is_rolling_xhs_revenue else 0,
            "refundSnapshot": round(number(row.get("refund_amount")), 2) if is_rolling_xhs_revenue else 0,
            "posts": round(number(row.get("content_count"))),
            "play": 0 if is_rolling_xhs_view else round(number(row.get("views"))),
            "interact": round(interaction_total(row)),
            "qualityNote": note,
            "sourceFile": row.get("source_file", ""),
        }
    daily_payload = [daily_by_date[day] for day in sorted(daily_by_date)]

    content_type = {
        "xhs": "\u56fe\u6587",
        "douyin": "\u89c6\u9891",
        "zhihu": "\u6587\u7ae0",
        "bili": "\u89c6\u9891",
        "wechat": "\u957f\u6587",
    }
    scored_content = []
    for row in content_rows:
        play = number(row.get("views")) or number(row.get("exposure"))
        interact = (
            number(row.get("likes"))
            + number(row.get("comments"))
            + number(row.get("favorites"))
            + number(row.get("shares"))
        )
        score = play + interact
        if not clean(row.get("content_title")) or score <= 0:
            continue
        scored_content.append({
            "platform": row["platform"],
            "accountKey": row.get("account_key", ""),
            "title": row["content_title"],
            "date": row.get("date", ""),
            "publishedAt": row.get("publish_time", ""),
            "snapshotDate": row.get("snapshot_date", ""),
            "snapshotTime": row.get("snapshot_time", ""),
            "contentPartition": row.get("content_partition", ""),
            "play": round(play),
            "interact": round(interact),
            "likes": number(row.get("likes")),
            "comments": number(row.get("comments")),
            "favorites": number(row.get("favorites")),
            "shares": number(row.get("shares")),
            "score": score,
            "type": row.get("content_type") or content_type.get(row["platform"], "\u5185\u5bb9"),
            "url": row.get("content_url", ""),
            "contentId": row.get("content_id", ""),
            "sourceFile": row.get("source_file", ""),
        })
    top_content = sorted(scored_content, key=lambda row: row["score"], reverse=True)[:10]
    total_content_score = max(1, sum(item["score"] for item in top_content))
    content_payload = []
    for item in top_content:
        content_payload.append({
            "platform": item["platform"],
            "accountKey": item["accountKey"],
            "title": item["title"],
            "date": item["date"],
            "publishedAt": item["publishedAt"],
            "snapshotDate": item["snapshotDate"],
            "snapshotTime": item["snapshotTime"],
            "contentPartition": item["contentPartition"],
            "share": round((item["score"] / total_content_score) * 100, 1),
            "play": item["play"],
            "interact": item["interact"],
            "type": item["type"],
            "url": item["url"],
            "contentId": item["contentId"],
            "sourceFile": item["sourceFile"],
        })

    content_details = []
    for item in sorted(scored_content, key=lambda row: (row.get("publishedAt") or row["date"], row["score"]), reverse=True):
        content_details.append({
            "platform": item["platform"],
            "accountKey": item["accountKey"],
            "title": item["title"],
            "date": item["date"],
            "publishedAt": item["publishedAt"],
            "snapshotDate": item["snapshotDate"],
            "snapshotTime": item["snapshotTime"],
            "contentPartition": item["contentPartition"],
            "play": item["play"],
            "interact": item["interact"],
            "likes": item.get("likes", 0),
            "comments": item.get("comments", 0),
            "favorites": item.get("favorites", 0),
            "shares": item.get("shares", 0),
            "type": item["type"],
            "url": item["url"],
            "contentId": item["contentId"],
            "sourceFile": item["sourceFile"],
        })

    coverage = []
    for platform in platforms_payload:
        coverage.append({
            "platform": platform["id"],
            "platformName": platform["name"],
            "status": platform.get("freshnessStatus") or ("ready" if platform["latestDailyDate"] else "missing"),
            "latestDailyDate": platform["latestDailyDate"],
            "latestTotalFollowersDate": platform["totalFollowersDate"],
            "freshnessIssues": platform.get("freshnessIssues", []),
            "accounts": platform.get("accounts", []),
            "contentSnapshots": platform.get("contentSnapshots", []),
            "shopLatestRevenueDate": platform.get("shopLatestRevenueDate", ""),
        })

    return {
        "schema": "self-media-dashboard.v1",
        "dataContractVersion": DATA_CONTRACT_VERSION,
        "generatedAt": summary["generated_at"],
        "sourceRoot": summary["source_root"],
        "normalizedDir": summary["normalized_dir"],
        "dateMin": summary["date_min"],
        "dateMax": summary["date_max"],
        "latestMonth": summary["latest_month"],
        "defaultDateStart": summary["current_month_start"],
        "defaultDateEnd": summary["date_max"],
        "platforms": platforms_payload,
        "daily": daily_payload,
        "contentItems": content_payload,
        "contentDetails": content_details,
        "contentSnapshotDates": summary.get("content_snapshot_dates", {}),
        "coverage": coverage,
        "sources": summary["source_counts"],
        "sourceCounts": summary["source_counts"],
        "rowCounts": summary["row_counts"],
        "notes": summary["notes"],
        "totals": summary["totals"],
    }


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_check_markdown(path, summary):
    lines = [
        "# 自媒体看板最近数据核对",
        "",
        f"生成时间：{summary['generated_at']}",
        f"数据根目录：`{summary['source_root']}`",
        f"当前统计月：{summary['current_month_start']} 至 {summary['date_max']}",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 总粉丝 | {summary['totals']['total_followers']:,.0f} |",
        f"| 本月净增粉丝 | {summary['totals']['month_net_followers']:,.0f} |",
        f"| 本月净收入 | {summary['totals']['month_net_revenue']:,.2f} |",
        f"| 本月内容发布数 | {summary['totals']['month_content_count']:,.0f} |",
        "",
        "## 分平台",
        "",
        "| 平台 | 最新总粉丝 | 总粉丝日期 | 本月净增粉丝 | 本月新增粉丝 | 本月取消/减少 | 本月净收入 | 本月内容发布数 | 本月播放/阅读 | 最近日数据 |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in summary["platforms"]:
        lines.append(
            "| {platform_name} | {latest_total_followers:,.0f} | {latest_total_followers_date} | "
            "{month_net_followers:,.0f} | {month_new_followers:,.0f} | {month_lost_followers:,.0f} | "
            "{month_net_revenue:,.2f} | {month_content_count:,.0f} | {month_views:,.0f} | {latest_daily_date} |".format(**row)
        )
    lines.extend([
        "",
        "## 口径备注",
        "",
    ])
    for note in summary["notes"]:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build():
    if not DATA_ROOT.exists():
        raise FileNotFoundError(f"Data root does not exist: {DATA_ROOT}")
    FILE_SELECTION_STATS.clear()
    daily = defaultdict(dict)
    snapshots = []
    content_rows = []
    source_counts = {}

    scan_xhs(daily, snapshots, content_rows, source_counts)
    scan_douyin(daily, snapshots, content_rows, source_counts)
    scan_zhihu(daily, snapshots, content_rows, source_counts)
    scan_bili(daily, snapshots, content_rows, source_counts)
    scan_wechat(daily, snapshots, content_rows, source_counts)

    daily_rows = prepare_rows(daily)
    content_detail_rows = sorted(
        ({field: row.get(field, "") for field in CONTENT_FIELDS} for row in content_rows),
        key=lambda row: (row["date"], row["platform"], row["account_key"], row["content_title"]),
    )
    content_rows = latest_content_snapshot_rows(content_rows)
    content_rows = sorted(
        ({field: row.get(field, "") for field in CONTENT_FIELDS} for row in content_rows),
        key=lambda row: (row["date"], row["platform"], row["content_title"]),
    )
    snapshots = sorted(
        ({field: row.get(field, "") for field in SNAPSHOT_FIELDS} for row in snapshots),
        key=lambda row: (row["date"], row["platform"]),
    )
    source_counts["file_fusion"] = dict(FILE_SELECTION_STATS)
    summary = summarize(daily_rows, snapshots, content_rows, content_detail_rows, source_counts)
    return daily_rows, snapshots, content_rows, content_detail_rows, summary


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    daily_rows, snapshots, content_rows, content_detail_rows, summary = build()
    dashboard = build_dashboard_payload(daily_rows, snapshots, content_rows, summary)
    write_csv(OUT_DIR / "self_media_daily_metrics.csv", daily_rows, DAILY_FIELDS)
    write_csv(OUT_DIR / "self_media_platform_snapshots.csv", snapshots, SNAPSHOT_FIELDS)
    write_csv(OUT_DIR / "self_media_content_items.csv", content_rows, CONTENT_FIELDS)
    write_csv(OUT_DIR / "self_media_content_detail.csv", content_detail_rows, CONTENT_FIELDS)
    (OUT_DIR / "self_media_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "self_media_dashboard.json").write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_check_markdown(OUT_DIR / "self_media_metric_check.md", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"error": str(error), "sourceRoot": str(DATA_ROOT)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
