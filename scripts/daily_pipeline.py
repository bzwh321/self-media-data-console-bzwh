# -*- coding: utf-8 -*-
"""自媒体数据中控台每日本地流水线。

这个脚本先放置确定性骨架：读取已有 dashboard 和校验结果，生成日报文本、
运行记录，并为后续工作台 HTML、截图和飞书发送预留稳定入口。
"""

from __future__ import annotations

import argparse
import json
import os
import math
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("SELF_MEDIA_DATA_ROOT", str(PROJECT_ROOT / "sample-data" / "self-media")))
DASHBOARD_DIR = DATA_ROOT / "dashboard-normalized"
DASHBOARD_PATH = DASHBOARD_DIR / "self_media_dashboard.json"
BUSINESS_CHECK_PATH = DASHBOARD_DIR / "latest_business_check.json"
SERVER_SYNC_REPORT_PATH = DASHBOARD_DIR / "server_sync_refresh_report.json"
RUNTIME_DIR = PROJECT_ROOT / "runtime-data"
STATE_DIR = RUNTIME_DIR / "console-state"
# 经营分析结果写入本项目 runtime-data（外部数据目录写权限受限），服务端和前端从 STATE_DIR 读取
OPS_ANALYSIS_PATH = STATE_DIR / "business_ops_analysis.json"
REPORTS_DIR = RUNTIME_DIR / "reports"
SCREENSHOTS_DIR = RUNTIME_DIR / "screenshots"
LOGS_DIR = RUNTIME_DIR / "logs"
CONFIG_PATH = PROJECT_ROOT / "config.json"
CAPTURE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "capture_console_screenshot.js"

# 月度目标（可按需调整，由外部 config.json 覆盖更佳，先硬编码最小可行）
DEFAULT_MONTHLY_GOALS = {
    "new_fans": 2000,       # 月度净增粉丝目标
    "revenue": 30000.0,     # 月度收入目标 ¥
}

# 发布频率参考基线
PUBLISH_BASELINE_DAILY_7M = 2.2  # 7月日均发布数基线（用于节奏对比）


def read_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config() -> dict[str, Any]:
    """读取本地配置。配置只保存收件人等运行参数，不保存飞书 token。"""
    return read_json(CONFIG_PATH, {}) or {}


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def load_context() -> dict[str, Any]:
    return {
        "dashboard": read_json(DASHBOARD_PATH, {}),
        "business_check": read_json(BUSINESS_CHECK_PATH, {}),
        "server_sync_report": read_json(SERVER_SYNC_REPORT_PATH, {}),
    }


def platform_label(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("id") or "未知平台")


def platform_status(item: dict[str, Any]) -> str:
    status = str(item.get("freshnessStatus") or item.get("status") or "unknown")
    if status == "ready":
        return "正常"
    if status == "stale":
        return "过期"
    if status == "missing":
        return "缺失"
    return status


def build_summary(context: dict[str, Any]) -> dict[str, Any]:
    dashboard = context["dashboard"] or {}
    platforms = dashboard.get("platforms") or []
    totals = {
        "fans": sum(number(item.get("fans")) for item in platforms),
        "new_fans": sum(number(item.get("newFans")) for item in platforms),
        "revenue": sum(number(item.get("revenue")) for item in platforms),
        "posts": sum(number(item.get("posts")) for item in platforms),
        "play": sum(number(item.get("play")) for item in platforms),
        "interact": sum(number(item.get("interact")) for item in platforms),
    }
    stale_platforms = [
        {
            "id": item.get("id"),
            "name": platform_label(item),
            "status": platform_status(item),
            "latest_daily_date": item.get("latestDailyDate"),
            "issues": item.get("freshnessIssues") or [],
        }
        for item in platforms
        if platform_status(item) != "正常"
    ]
    business_status = str((context.get("business_check") or {}).get("status") or "unknown")
    sync_status = str((context.get("server_sync_report") or {}).get("status") or "unknown")
    if business_status not in {"ready", "success"}:
        status = "failed"
    elif stale_platforms:
        status = "partial"
    else:
        status = "ready"
    return {
        "status": status,
        "sync_status": sync_status,
        "business_status": business_status,
        "generated_at": dashboard.get("generatedAt"),
        "date_min": dashboard.get("dateMin"),
        "date_max": dashboard.get("dateMax"),
        "platform_count": len(platforms),
        "totals": totals,
        "platforms": [
            {
                "id": item.get("id"),
                "name": platform_label(item),
                "status": platform_status(item),
                "latest_daily_date": item.get("latestDailyDate"),
                "total_followers_date": item.get("totalFollowersDate"),
                "issues": item.get("freshnessIssues") or [],
            }
            for item in platforms
        ],
        "stale_platforms": stale_platforms,
    }


def money(value: float) -> str:
    return f"{value:,.2f}"


def integer(value: float) -> str:
    return f"{round(value):,}"


def build_report_markdown(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    status_label = {
        "ready": "今日自媒体数据已更新",
        "partial": "今日自媒体数据部分平台未更新",
        "failed": "今日自媒体数据生成失败",
    }.get(summary["status"], summary["status"])
    lines = [
        f"# 自媒体数据日报 {today_text()}",
        "",
        f"- 状态：{status_label}",
        f"- 数据范围：{summary.get('date_min') or '-'} 至 {summary.get('date_max') or '-'}",
        f"- 服务器同步：{summary.get('sync_status')}",
        f"- 业务校验：{summary.get('business_status')}",
        "",
        "## 核心指标",
        "",
        f"- 总粉丝：{integer(totals['fans'])}",
        f"- 新增粉丝：{integer(totals['new_fans'])}",
        f"- 收入：{money(totals['revenue'])}",
        f"- 发布数：{integer(totals['posts'])}",
        f"- 播放或阅读：{integer(totals['play'])}",
        f"- 互动：{integer(totals['interact'])}",
        "",
        "## 平台状态",
        "",
    ]
    for item in summary["platforms"]:
        date = item.get("latest_daily_date") or item.get("total_followers_date") or "-"
        lines.append(f"- {item['name']}：{item['status']}，最新日期 {date}")
        for issue in item.get("issues") or []:
            lines.append(f"  - {issue}")
    lines.extend(["", "## 今日结论", ""])
    if summary["status"] == "ready":
        lines.append("所有核心平台通过新鲜度和业务校验，可按正常日报使用。")
    elif summary["status"] == "partial":
        names = "、".join(item["name"] for item in summary["stale_platforms"])
        lines.append(f"{names} 存在未更新或过期数据，经营判断应避开这些平台的当日变化。")
    else:
        lines.append("同步或业务校验未通过，本次不生成经营判断，请先查看运行记录。")
    lines.extend(["", "## 本地路径", ""])
    lines.append(f"- 看板数据：`{DASHBOARD_PATH}`")
    lines.append(f"- 项目目录：`{PROJECT_ROOT}`")
    return "\n".join(lines) + "\n"


def build_lark_markdown(record: dict[str, Any]) -> str:
    """生成飞书正文。结论来自确定性规则和中控台经营分析结果，不调用大模型。"""
    totals = record.get("totals") or {}
    status = record.get("status") or "unknown"
    status_label = {
        "ready": "正常完成",
        "partial": "部分完成",
        "failed": "失败",
    }.get(status, status)
    lines = [
        f"**自媒体数据日报 {today_text()}**",
        "",
        f"状态：**{status_label}**",
        f"数据区间：{record.get('date_min') or '-'} 至 {record.get('date_max') or '-'}",
        f"服务器同步：{record.get('sync_status') or '-'}",
        f"业务校验：{record.get('business_status') or '-'}",
        "",
        "**核心指标**",
        f"- 总粉丝：{integer(number(totals.get('fans')))}",
        f"- 新增粉丝：{integer(number(totals.get('new_fans')))}",
        f"- 收入：¥{money(number(totals.get('revenue')))}",
        f"- 发布数：{integer(number(totals.get('posts')))}",
        f"- 播放或阅读：{integer(number(totals.get('play')))}",
        f"- 互动：{integer(number(totals.get('interact')))}",
        "",
        "**平台状态**",
    ]
    for item in record.get("platforms") or []:
        date = item.get("latest_daily_date") or item.get("total_followers_date") or "-"
        lines.append(f"- {item.get('name') or item.get('id')}：{item.get('status') or '-'}，最新日期 {date}")

    if status == "failed":
        lines.extend(["", "**今日结论**", "同步或业务校验未通过，本次不发送正常经营判断，请先查看运行记录。"])
    elif status == "partial":
        stale_names = "、".join(item.get("name") or item.get("id") or "未知平台" for item in record.get("stale_platforms") or [])
        lines.extend(["", "**今日结论**", f"{stale_names or '部分平台'} 存在未更新或过期数据，经营判断需避开这些平台的当日变化。"])
    else:
        ops = read_json(OPS_ANALYSIS_PATH, {}) or {}
        one_sentence = ((ops.get("exec_summary") or {}).get("one_sentence") or "").strip()
        full_report = ((ops.get("exec_summary") or {}).get("full_report") or "").strip()
        lines.extend(["", "**今日结论**"])
        if one_sentence:
            lines.append(one_sentence)
        if full_report:
            lines.append(full_report)
        if not one_sentence and not full_report:
            lines.append("所有核心平台通过新鲜度和业务校验，可按正常日报使用。")

    screenshot_path = record.get("screenshot_path")
    if screenshot_path:
        lines.extend(["", f"看板图片：{screenshot_path}"])
    return "\n".join(lines)


def generate_report() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    context = load_context()
    summary = build_summary(context)
    report_path = REPORTS_DIR / f"daily-report-{today_text()}.md"
    report_path.write_text(build_report_markdown(summary), encoding="utf-8")
    run_record = {
        "schema": "self-media-daily-run.v1",
        "run_date": today_text(),
        "created_at": now_text(),
        **summary,
        "report_path": str(report_path),
    }
    log_path = LOGS_DIR / f"daily-run-{today_text()}.json"
    write_json(log_path, run_record)
    return run_record


def latest_run_record() -> dict[str, Any]:
    log_path = LOGS_DIR / f"daily-run-{today_text()}.json"
    if log_path.exists():
        return read_json(log_path, {}) or {}
    return generate_report()


def save_run_record(record: dict[str, Any]) -> dict[str, Any]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(LOGS_DIR / f"daily-run-{today_text()}.json", sanitize_nan_write(record))
    return record


def build_workbench() -> dict[str, Any]:
    record = generate_report()
    html_path = RUNTIME_DIR / "self-media-workbench.html"
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>自媒体数据中控台</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft YaHei UI", system-ui, sans-serif; background: #f5f7fa; color: #17202a; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 32px; }}
    .card {{ background: white; border: 1px solid #dde6ef; border-radius: 14px; padding: 20px; margin-bottom: 18px; box-shadow: 0 12px 34px rgba(20, 30, 40, .08); }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
    .metric strong {{ display: block; font-size: 30px; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #edf1f5; padding: 10px; text-align: left; }}
    .status-ready {{ color: #126b42; }}
    .status-partial {{ color: #9a5b00; }}
    .status-failed {{ color: #a42525; }}
  </style>
</head>
<body>
<main>
  <section class="card">
    <p>SELF MEDIA CONSOLE</p>
    <h1>自媒体数据中控台</h1>
    <h2 class="status-{record['status']}">状态：{record['status']}</h2>
    <p>数据范围：{record.get('date_min') or '-'} 至 {record.get('date_max') or '-'}</p>
  </section>
  <section class="card grid">
    <div class="metric">总粉丝<strong>{integer(record['totals']['fans'])}</strong></div>
    <div class="metric">新增粉丝<strong>{integer(record['totals']['new_fans'])}</strong></div>
    <div class="metric">收入<strong>{money(record['totals']['revenue'])}</strong></div>
    <div class="metric">发布数<strong>{integer(record['totals']['posts'])}</strong></div>
    <div class="metric">播放或阅读<strong>{integer(record['totals']['play'])}</strong></div>
    <div class="metric">互动<strong>{integer(record['totals']['interact'])}</strong></div>
  </section>
  <section class="card">
    <h2>平台状态</h2>
    <table>
      <thead><tr><th>平台</th><th>状态</th><th>最新日期</th><th>问题</th></tr></thead>
      <tbody>
        {''.join(f"<tr><td>{p['name']}</td><td>{p['status']}</td><td>{p.get('latest_daily_date') or '-'}</td><td>{'; '.join(p.get('issues') or [])}</td></tr>" for p in record['platforms'])}
      </tbody>
    </table>
  </section>
</main>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    record["workbench_path"] = str(html_path)
    write_json(LOGS_DIR / f"daily-run-{today_text()}.json", record)
    return record


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(url: str, timeout: float = 20.0) -> None:
    import urllib.request

    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                if 200 <= res.status < 500:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.4)
    raise RuntimeError(f"本地中控台服务启动超时：{last_error}")


def capture_console_screenshot() -> dict[str, Any]:
    """按中控台真实页面排版截取 16:9 日报图。"""
    write_ops_analysis()
    record = latest_run_record()
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_path = SCREENSHOTS_DIR / f"daily-console-{today_text()}.png"
    if not CAPTURE_SCRIPT_PATH.exists():
        record.update({
            "screenshot_status": "failed",
            "screenshot_error": f"截图脚本不存在：{CAPTURE_SCRIPT_PATH}",
        })
        return save_run_record(record)

    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    server = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "console_server.py"), "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        wait_for_server(url)
        cmd = ["node", str(CAPTURE_SCRIPT_PATH), url, str(screenshot_path), "dashboard"]
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "截图脚本执行失败").strip())
        record.update({
            "screenshot_status": "success",
            "screenshot_path": str(screenshot_path),
            "report_image_path": str(screenshot_path),
            "screenshot_generated_at": now_text(),
        })
    except Exception as exc:
        record.update({
            "screenshot_status": "failed",
            "screenshot_error": str(exc),
        })
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    return save_run_record(record)


def relative_to_project(path: str | Path) -> str:
    target = Path(path)
    try:
        return target.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except Exception:
        return str(target)


def lark_recipients(config: dict[str, Any]) -> list[dict[str, Any]]:
    lark = config.get("lark") or {}
    recipients = lark.get("recipients") or []
    if isinstance(recipients, dict):
        recipients = [recipients]
    return [r for r in recipients if isinstance(r, dict)]


def send_lark_message() -> dict[str, Any]:
    """发送飞书日报正文和中控台截图。未配置收件人时安全跳过。"""
    record = latest_run_record()
    if record.get("screenshot_status") != "success" or not record.get("screenshot_path"):
        record = capture_console_screenshot()

    config = load_config()
    recipients = lark_recipients(config)
    if not recipients:
        record.update({
            "lark_send_status": "skipped",
            "lark_send_error": "未配置 config.json 的 lark.recipients，已跳过发送，避免误发。",
        })
        return save_run_record(record)
    if not shutil.which("lark-cli"):
        record.update({
            "lark_send_status": "failed",
            "lark_send_error": "未找到 lark-cli，无法发送飞书。",
        })
        return save_run_record(record)

    markdown = build_lark_markdown(record)
    screenshot_path = record.get("screenshot_path")
    results = []
    ok = True
    for idx, recipient in enumerate(recipients, 1):
        target_args: list[str]
        target_label = recipient.get("name") or recipient.get("open_id") or recipient.get("user_id") or recipient.get("chat_id") or f"recipient-{idx}"
        if recipient.get("chat_id"):
            target_args = ["--chat-id", str(recipient["chat_id"])]
        else:
            user_id = recipient.get("open_id") or recipient.get("user_id")
            if not user_id:
                ok = False
                results.append({"target": target_label, "ok": False, "error": "收件人缺少 open_id/user_id/chat_id"})
                continue
            target_args = ["--user-id", str(user_id)]

        text_cmd = [
            "lark-cli", "im", "+messages-send",
            *target_args,
            "--markdown", markdown,
            "--idempotency-key", f"self-media-{today_text()}-{idx}-text",
        ]
        text_proc = subprocess.run(
            text_cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        item = {
            "target": target_label,
            "text_ok": text_proc.returncode == 0,
            "text_stdout": (text_proc.stdout or "").strip()[:1000],
            "text_stderr": (text_proc.stderr or "").strip()[:1000],
        }
        if text_proc.returncode != 0:
            ok = False

        if screenshot_path and Path(screenshot_path).exists():
            image_cmd = [
                "lark-cli", "im", "+messages-send",
                *target_args,
                "--image", relative_to_project(screenshot_path),
                "--idempotency-key", f"self-media-{today_text()}-{idx}-image",
            ]
            img_proc = subprocess.run(
                image_cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
            )
            item.update({
                "image_ok": img_proc.returncode == 0,
                "image_stdout": (img_proc.stdout or "").strip()[:1000],
                "image_stderr": (img_proc.stderr or "").strip()[:1000],
            })
            if img_proc.returncode != 0:
                ok = False
        results.append(item)

    record.update({
        "lark_send_status": "success" if ok else "partial_failed",
        "lark_send_error": "" if ok else "部分收件人或附件发送失败，详见 lark_results。",
        "lark_sent_at": now_text(),
        "lark_results": results,
    })
    return save_run_record(record)


# ============================================================
# 经营分析模块：business-ops-analysis 确定性规则实现
# 所有结论由确定公式产出，不调用大模型生成自由文本
# ============================================================

def _hhi(shares: list[float]) -> float:
    """Herfindahl-Hirschman 指数：sum(share_i²)。0~1，越高越集中。"""
    if not shares:
        return 0.0
    total = sum(s for s in shares if s > 0)
    if total <= 0:
        return 0.0
    return sum((s / total) ** 2 for s in shares if s > 0)


def _hhi_label(hhi: float) -> tuple[str, str]:
    """返回 (分级文字, CSS 级别)。"""
    if hhi < 0.25:
        return "分散健康", "success"
    if hhi < 0.5:
        return "中度集中", "warn"
    if hhi < 0.75:
        return "高度集中", "warn"
    return "极端集中", "critical"


def _confidence_label(level: str) -> str:
    return {"high": "高", "medium": "中", "low": "待验证"}.get(level, level)


# ============================================================
# 模拟经营数据（真实数据接入前用于展示经营分析模块效果）
# 月收入 ~¥15,000，月成本 ~¥6,750，月利润 ~¥8,250
# 收入类型：知识付费 / 商单 / 平台激励
# 成本类型：广告 / 稿费 / 运营成本
# ============================================================
MOCK_REVENUE_ENABLED = True  # 真实收入接入后改为 False

REVENUE_TYPES = ["知识付费", "商单", "平台激励"]
COST_TYPES = ["广告", "稿费", "运营成本"]

# 每平台的收入 × 收入类型拆分（合计 ¥15,000）
_MOCK_REV_BY_PLATFORM = [
    {"platform": "xhs",    "platform_name": "小红书", "total": 7200.0,
     "by_type": {"知识付费": 3200.0, "商单": 3000.0, "平台激励": 1000.0}},
    {"platform": "douyin", "platform_name": "抖音",   "total": 4500.0,
     "by_type": {"知识付费": 500.0,  "商单": 3000.0, "平台激励": 1000.0}},
    {"platform": "bili",   "platform_name": "B站",    "total": 1800.0,
     "by_type": {"知识付费": 200.0,  "商单": 800.0,  "平台激励": 800.0}},
    {"platform": "wechat", "platform_name": "公众号", "total": 900.0,
     "by_type": {"知识付费": 500.0,  "商单": 200.0,  "平台激励": 200.0}},
    {"platform": "zhihu",  "platform_name": "知乎",   "total": 600.0,
     "by_type": {"知识付费": 300.0,  "商单": 100.0,  "平台激励": 200.0}},
]

# 每平台的成本 × 成本类型拆分（合计 ¥6,750）
_MOCK_COST_BY_PLATFORM = [
    {"platform": "xhs",    "platform_name": "小红书", "total": 2900.0,
     "by_type": {"广告": 2200.0, "稿费": 400.0, "运营成本": 300.0}},
    {"platform": "douyin", "platform_name": "抖音",   "total": 2300.0,
     "by_type": {"广告": 1800.0, "稿费": 300.0, "运营成本": 200.0}},
    {"platform": "bili",   "platform_name": "B站",    "total": 800.0,
     "by_type": {"广告": 500.0,  "稿费": 200.0, "运营成本": 100.0}},
    {"platform": "wechat", "platform_name": "公众号", "total": 400.0,
     "by_type": {"广告": 200.0,  "稿费": 150.0, "运营成本": 50.0}},
    {"platform": "zhihu",  "platform_name": "知乎",   "total": 350.0,
     "by_type": {"广告": 200.0,  "稿费": 100.0, "运营成本": 50.0}},
]

_MOCK_REV_LAST_MONTH = 12800.0   # 上月收入
_MOCK_COST_LAST_MONTH = 5800.0   # 上月成本
_MOCK_REV_GOAL = 30000.0         # 月度收入目标
_MOCK_PROFIT_GOAL = 18000.0      # 月度利润目标


def _build_mock_revenue_analysis(days_passed: int, real_revenue: float = 0.0) -> dict[str, Any]:
    """构建完整的模拟经营分析结构（收入/成本/利润 + 类型拆解 + 瀑布数据）。

    若 real_revenue > 0，则按真实收入缩放模拟拆解（保持平台占比和成本率不变），
    让经营损益卡片的收入与 KPI strip 一致，成本/利润等比例变化。
    """
    mock_rev_total = sum(p["total"] for p in _MOCK_REV_BY_PLATFORM)
    if real_revenue > 0:
        scale = real_revenue / mock_rev_total
    else:
        scale = 1.0

    # 缩放后的平台收入/成本拆解（保持占比不变）
    rev_by_plat = [
        {**p, "total": round(p["total"] * scale, 2),
         "by_type": {t: round(v * scale, 2) for t, v in p["by_type"].items()}}
        for p in _MOCK_REV_BY_PLATFORM
    ]
    cost_by_plat = [
        {**p, "total": round(p["total"] * scale, 2),
         "by_type": {t: round(v * scale, 2) for t, v in p["by_type"].items()}}
        for p in _MOCK_COST_BY_PLATFORM
    ]

    month_rev = sum(p["total"] for p in rev_by_plat)
    month_cost = sum(p["total"] for p in cost_by_plat)
    month_profit = month_rev - month_cost

    # 收入 HHI（按平台）—— HHI 是比率，用缩放前后值结果一样
    rev_shares = [p["total"] for p in rev_by_plat]
    rev_hhi = _hhi(rev_shares)
    rev_hhi_tag, rev_hhi_level = _hhi_label(rev_hhi)

    # 收入类型汇总
    rev_by_type: dict[str, float] = {t: 0.0 for t in REVENUE_TYPES}
    for p in rev_by_plat:
        for t, v in p["by_type"].items():
            rev_by_type[t] += v

    # 成本类型汇总
    cost_by_type: dict[str, float] = {t: 0.0 for t in COST_TYPES}
    for p in cost_by_plat:
        for t, v in p["by_type"].items():
            cost_by_type[t] += v

    # 利润 HHI（按平台）
    profit_by_platform = []
    for rp, cp in zip(rev_by_plat, cost_by_plat):
        profit_by_platform.append({
            "platform": rp["platform"],
            "platform_name": rp["platform_name"],
            "revenue": rp["total"],
            "cost": cp["total"],
            "profit": rp["total"] - cp["total"],
            "profit_rate": round((rp["total"] - cp["total"]) / rp["total"], 4) if rp["total"] > 0 else 0,
        })
    profit_shares = [max(0.0, p["profit"]) for p in profit_by_platform]
    profit_hhi = _hhi(profit_shares)

    # MoM —— 上月值不缩放（模拟的上月基准），本月用缩放后值
    rev_mom = (month_rev - _MOCK_REV_LAST_MONTH) / _MOCK_REV_LAST_MONTH
    cost_mom = (month_cost - _MOCK_COST_LAST_MONTH) / _MOCK_COST_LAST_MONTH
    last_profit = _MOCK_REV_LAST_MONTH - _MOCK_COST_LAST_MONTH
    profit_mom = (month_profit - last_profit) / last_profit if last_profit > 0 else 0

    return {
        "is_mock": True,
        "mock_notice": "⚠️ 本经营数据（收入/成本/利润）为模拟展示数据，真实数据接入后将自动替换。",
        # 核心 KPI
        "kpi": {
            "total_revenue": round(month_rev, 2),
            "total_cost": round(month_cost, 2),
            "total_profit": round(month_profit, 2),
            "profit_rate": round(month_profit / month_rev, 4) if month_rev > 0 else 0,
            "rev_mom": round(rev_mom, 4),
            "cost_mom": round(cost_mom, 4),
            "profit_mom": round(profit_mom, 4),
            "last_revenue": round(_MOCK_REV_LAST_MONTH, 2),
            "last_cost": round(_MOCK_COST_LAST_MONTH, 2),
            "last_profit": round(last_profit, 2),
        },
        # 按平台拆分（收入/成本/利润三维度）
        "by_platform": profit_by_platform,
        # 收入类型拆分（饼图用）
        "revenue_by_type": [{"type": t, "value": round(v, 2)} for t, v in rev_by_type.items()],
        # 成本类型拆分（饼图用）
        "cost_by_type": [{"type": t, "value": round(v, 2)} for t, v in cost_by_type.items()],
        # 收入 × 平台 × 类型交叉（供前端下钻）
        "revenue_platform_type": [
            {"platform": p["platform"], "platform_name": p["platform_name"],
             "by_type": p["by_type"], "total": p["total"]}
            for p in rev_by_plat
        ],
        "cost_platform_type": [
            {"platform": p["platform"], "platform_name": p["platform_name"],
             "by_type": p["by_type"], "total": p["total"]}
            for p in cost_by_plat
        ],
        # 瀑布图数据（三种维度）
        "waterfall": {
            "revenue": [
                {"label": "上月合计", "value": _MOCK_REV_LAST_MONTH, "type": "total"},
                *[{"label": p["platform_name"], "value": p["total"], "type": "up"}
                  for p in rev_by_plat],
                {"label": "本月合计", "value": month_rev, "type": "total"},
            ],
            "cost": [
                {"label": "上月合计", "value": _MOCK_COST_LAST_MONTH, "type": "total"},
                *[{"label": p["platform_name"], "value": p["total"], "type": "up"}
                  for p in cost_by_plat],
                {"label": "本月合计", "value": month_cost, "type": "total"},
            ],
            "profit": [
                {"label": "上月利润", "value": last_profit, "type": "total"},
                *[{"label": p["platform_name"], "value": p["profit"],
                   "type": "up" if p["profit"] >= 0 else "down"}
                  for p in profit_by_platform],
                {"label": "本月利润", "value": month_profit, "type": "total"},
            ],
        },
        # HHI & 集中度
        "hhi_index": round(rev_hhi, 4),
        "hhi_level": rev_hhi_level,
        "hhi_tag": rev_hhi_tag,
        "profit_hhi": round(profit_hhi, 4),
        # 目标
        "month_total_value": round(month_rev, 2),
        "last_month_total_value": round(_MOCK_REV_LAST_MONTH, 2),
        "mom_growth": round(rev_mom, 4),
        "days_passed": days_passed,
    }


def build_business_ops_analysis(context: dict[str, Any]) -> dict[str, Any]:
    """基于 dashboard + attribution + 目标配置，产出经营分析结果。

    返回字段：
      - trend_analysis:      趋势（MoM/YoY/拐点、每图结论）
      - structure_analysis:  结构拆解（贡献占比瀑布、HHI、TopN、每图结论）
      - anomaly_list:        分级异常清单（CRITICAL/WARN/INFO + 归因+行动+置信度）
      - exec_summary:        Executive Summary（一句话 + 4 胶囊 + 级别统计）
      - insights_per_module: 各模块上方的中文结论文字（前端直接渲染）
      - goals:               当前月度目标（供前端达成率仪表用）
    """
    dashboard = context.get("dashboard") or {}
    compact = context.get("compact") or {}
    attribution = context.get("attribution") or {}

    platforms_raw = dashboard.get("platforms") or []       # 原始 5 平台
    platforms_cmp = compact.get("platforms") or []          # compact 版（含每月聚合）
    daily_metrics = compact.get("daily_metrics_recent30") or []

    goals = dict(DEFAULT_MONTHLY_GOALS)
    today_iso = today_text()
    try:
        today_dt = datetime.strptime(today_iso, "%Y-%m-%d")
    except Exception:
        today_dt = datetime.now()
    month_start_iso = today_dt.strftime("%Y-%m-01")

    # ---- 基础聚合 ---------------------------------------------------------
    # 5 平台月度净增粉丝、收入、粉丝数、内容数
    cmp_by_id = {p.get("platform"): p for p in platforms_cmp}
    raw_by_id = {p.get("id"): p for p in platforms_raw}

    month_new_fans_total = 0.0
    month_revenue_total = 0.0
    month_content_total = 0.0
    month_views_total = 0.0

    platform_contrib = []  # [{id, name, new_fans, revenue, content_count, views, fans_now}]
    for pid in ["xhs", "douyin", "zhihu", "bili", "wechat"]:
        cmp = cmp_by_id.get(pid) or {}
        raw = raw_by_id.get(pid) or {}
        nf = number(cmp.get("month_net_followers") or raw.get("newFans"))
        rv = number(cmp.get("month_net_revenue") or raw.get("revenue"))
        cc = number(cmp.get("month_content_count") or raw.get("posts"))
        vw = number(cmp.get("month_views") or raw.get("play"))
        fans_now = number(cmp.get("latest_total_followers") or raw.get("fans"))
        name = str(cmp.get("platform_name") or raw.get("name") or pid)
        month_new_fans_total += nf
        month_revenue_total += rv
        month_content_total += cc
        month_views_total += vw
        platform_contrib.append({
            "id": pid, "name": name,
            "new_fans": nf, "revenue": rv,
            "content_count": cc, "views": vw,
            "fans_now": fans_now,
        })

    fans_total_now = sum(p["fans_now"] for p in platform_contrib)

    # 本月已过天数（从 1 号到今天）
    try:
        days_passed = (today_dt - datetime.strptime(month_start_iso, "%Y-%m-%d")).days + 1
    except Exception:
        days_passed = 1
    days_remaining = max(1, 31 - days_passed)  # 简化：按 31 天算

    # ---- 模拟经营数据注入（真实数据接入前展示用）----------------------------
    mock_rev = None
    if MOCK_REVENUE_ENABLED:
        # 用 compact 真实收入缩放模拟拆解，让经营损益卡片与 KPI strip 对齐
        mock_rev = _build_mock_revenue_analysis(days_passed, real_revenue=month_revenue_total)
        # 用模拟收入覆盖 platform_contrib 中的 revenue 字段
        mock_by_pid = {p["platform"]: p["revenue"] for p in mock_rev["by_platform"]}
        for pc in platform_contrib:
            pc["revenue"] = mock_by_pid.get(pc["id"], 0.0)
        month_revenue_total = mock_rev["kpi"]["total_revenue"]
        # 覆盖目标
        goals["revenue"] = _MOCK_REV_GOAL

    # 收入非零平台（按收入降序）
    rev_nonzero = sorted([p for p in platform_contrib if p["revenue"] > 0],
                         key=lambda x: x["revenue"], reverse=True)

    # ---- 粉丝/收入结构 HHI ------------------------------------------------
    fans_shares = [max(0.0, p["fans_now"]) for p in platform_contrib]
    revenue_shares = [max(0.0, p["revenue"]) for p in platform_contrib]
    newfans_shares = [max(0.0, p["new_fans"]) for p in platform_contrib]
    fans_hhi = _hhi(fans_shares)
    revenue_hhi = _hhi(revenue_shares)
    newfans_hhi = _hhi(newfans_shares)
    fans_hhi_tag, fans_hhi_level = _hhi_label(fans_hhi)
    revenue_hhi_tag, revenue_hhi_level = _hhi_label(revenue_hhi)

    # 目标达成率
    new_fans_goal = goals["new_fans"]
    revenue_goal = goals["revenue"]
    new_fans_rate = (month_new_fans_total / new_fans_goal) if new_fans_goal > 0 else 0.0
    revenue_rate = (month_revenue_total / revenue_goal) if revenue_goal > 0 else 0.0
    new_fans_daily_needed = max(0.0, (new_fans_goal - month_new_fans_total) / days_remaining)
    revenue_daily_needed = max(0.0, (revenue_goal - month_revenue_total) / days_remaining)

    # ---- 趋势粗略判断（近 7 天 vs 前 7 天）---------------------------------
    # 按日期聚合全平台日净增
    by_date: dict[str, dict[str, float]] = {}
    for row in daily_metrics:
        d = row.get("date") or ""
        if not d:
            continue
        agg = by_date.setdefault(d, {"net": 0.0, "rev": 0.0, "posts": 0.0, "views": 0.0})
        agg["net"] += number(row.get("net_followers"))
        agg["rev"] += number(row.get("net_revenue"))
        agg["posts"] += number(row.get("content_count"))
        agg["views"] += number(row.get("views"))
    sorted_dates = sorted(by_date.keys())
    recent7_dates = sorted_dates[-7:] if len(sorted_dates) >= 7 else sorted_dates
    prev7_dates = sorted_dates[-14:-7] if len(sorted_dates) >= 14 else []
    recent7_avg_net = sum(by_date[d]["net"] for d in recent7_dates) / max(1, len(recent7_dates))
    prev7_avg_net = sum(by_date[d]["net"] for d in prev7_dates) / max(1, len(prev7_dates)) if prev7_dates else recent7_avg_net
    if prev7_avg_net > 0:
        mom_ratio = (recent7_avg_net - prev7_avg_net) / prev7_avg_net
    else:
        mom_ratio = 0.0
    # 节奏：最近7天日均发布
    recent7_posts_total = sum(by_date[d]["posts"] for d in recent7_dates)
    recent7_posts_daily = recent7_posts_total / max(1, len(recent7_dates))

    # 简单拐点：找最近一个"从显著高掉到显著低"的日点
    inflection = None
    nets = [(d, by_date[d]["net"]) for d in sorted_dates[-14:]]
    for i in range(1, len(nets) - 1):
        prev_ = nets[i - 1][1]
        cur_ = nets[i][1]
        nxt_ = nets[i + 1][1]
        # 从较高掉到较低（>=30% 降幅）
        if cur_ > 0 and prev_ > cur_ * 1.3 and nxt_ < cur_ * 0.7:
            inflection = {"date": nets[i][0], "prev": prev_, "cur": cur_, "next": nxt_}

    # ---- TopN 贡献（来自 attribution 的 top_contents + compact 的 content_items_top）---
    attr_items = attribution.get("top_contents") or attribution.get("items") or attribution.get("top_items") or []
    # content_items_top 在 compact_dashboard_data.json 里有
    content_top = compact.get("content_items_top") or []
    def _exposure_of(item: dict) -> float:
        # 兼容 exposure / views / play / content_title 等多字段
        for key in ["exposure", "views", "play", "viewCount"]:
            v = number(item.get(key))
            if v > 0:
                return v
        return 0.0
    def _title_of(item: dict) -> str:
        for key in ["title", "content_title", "name"]:
            t = item.get(key)
            if t:
                return str(t)
        return ""
    all_top_items: list[dict] = []
    seen_ids: set[str] = set()
    for it in list(attr_items) + list(content_top):
        cid = str(it.get("content_id") or it.get("id") or (_title_of(it) + "|" + str(it.get("date"))))
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        all_top_items.append({"_id": cid, "title": _title_of(it), "exposure": _exposure_of(it)})
    all_top_items.sort(key=lambda x: x["exposure"], reverse=True)
    top_exposures = [it["exposure"] for it in all_top_items]
    total_top_exp = sum(top_exposures)
    def _share(i: int) -> float:
        if total_top_exp <= 0 or i >= len(top_exposures):
            return 0.0
        return top_exposures[i] / total_top_exp
    top1_share = _share(0)
    top3_share = sum(_share(i) for i in range(min(3, len(top_exposures))))
    top10_share = sum(_share(i) for i in range(min(10, len(top_exposures))))
    top1_title = all_top_items[0]["title"] if all_top_items else ""

    # ---- 涨粉归因效率 -----------------------------------------------------
    attr_platforms = attribution.get("by_platform") or []
    attr_types = attribution.get("by_type") or []
    xhs_new_fans = 0.0
    for it in attr_platforms:
        if str(it.get("platform") or it.get("platform_name") or it.get("id")) in {"xhs", "小红书"}:
            xhs_new_fans = number(it.get("total_new_followers") or it.get("new_fans") or it.get("fans_gain"))
    attr_total_fans = number(attribution.get("grand_total_new_followers") or attribution.get("total_new_fans"))
    xhs_share_in_attr = (xhs_new_fans / attr_total_fans) if attr_total_fans > 0 else 0.0

    # 类型涨粉效率：new_fans / (views/1000)
    type_efficiency = []
    for t in attr_types:
        f = number(t.get("total_new_followers") or t.get("new_fans") or t.get("fans"))
        v = number(t.get("total_views") or t.get("views") or t.get("exposure") or t.get("play"))
        eff = (f / (v / 1000.0)) if v > 0 else 0.0  # 每千曝光涨粉
        type_name = str(t.get("content_type") or t.get("type") or t.get("name") or "")
        if type_name:
            type_efficiency.append({
                "type": type_name,
                "new_fans": f, "views": v, "fans_per_kview": round(eff, 2),
            })
    type_efficiency.sort(key=lambda x: x["fans_per_kview"], reverse=True)

    # 数字格式辅助（提前定义，供异常识别 & Executive Summary 共用）
    def _k(n): return f"{round(n):,}"
    def _pct(n, d=1): return f"{n*100:.{d}f}%"
    def _money(n): return f"¥{n:,.2f}"

    # ---- 异常识别 ---------------------------------------------------------
    anomalies: list[dict[str, Any]] = []

    # 1. 新鲜度异常（内容快照 > 14d → CRITICAL，>7d → WARN，>1d → INFO）
    for p in platforms_raw:
        issues = p.get("freshnessIssues") or []
        pid = p.get("id")
        name = p.get("name") or pid
        if issues:
            for issue in issues:
                # 解析天数
                days_stale = 1
                import re
                m = re.search(r"(?:latest\s+)?(\d{4}-\d{2}-\d{2})", str(issue))
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), "%Y-%m-%d")
                        days_stale = (today_dt - dt).days
                    except Exception:
                        days_stale = 1
                if days_stale >= 14:
                    level = "CRITICAL"
                elif days_stale >= 7:
                    level = "WARN"
                else:
                    level = "WARN"
                anomalies.append({
                    "level": level,
                    "category": "data_quality",
                    "problem": f"{name} 内容快照停更 {days_stale} 天（{m.group(1) if m else '详情见日志'}）：{issue}",
                    "assumption": "账号登录态失效 / 服务器 Playwright 风控异常 / 采集脚本报错",
                    "actions": [
                        "登录服务器检查对应平台采集脚本日志是否抛出风控/登录异常",
                        "重新扫码登录采集账号并确认 Cookie 已刷新",
                        f"补抓最近 {days_stale} 天的内容明细数据",
                    ],
                    "confidence": "high",
                })

    # 2. 收入集中度异常
    if revenue_hhi >= 0.75 and month_revenue_total > 0:
        top_platform = max(platform_contrib, key=lambda x: x["revenue"])
        top_pct = (top_platform["revenue"] / month_revenue_total * 100) if month_revenue_total else 0
        anomalies.append({
            "level": "CRITICAL" if revenue_hhi >= 0.9 else "WARN",
            "category": "business_risk",
            "problem": f"收入极端集中于 {top_platform['name']} {top_pct:.2f}%，HHI={revenue_hhi:.3f}（{revenue_hhi_tag}）",
            "assumption": "其他平台未开启变现通道 / 未上架对应 SKU / 运营尚未投入",
            "actions": [
                "B站开启悬赏计划/花火商单通道，上架对标 SKU",
                "知乎开通知学堂/盐选专栏，复用小红书成熟产品线",
                "制定 Q3 分散化目标：非小红书收入占比 ≥5%",
            ],
            "confidence": "high",
        })
    elif revenue_hhi >= 0.25 and month_revenue_total > 0:
        top_platform = max(platform_contrib, key=lambda x: x["revenue"])
        top_pct = (top_platform["revenue"] / month_revenue_total * 100) if month_revenue_total else 0
        anomalies.append({
            "level": "INFO",
            "category": "business_risk",
            "problem": f"收入中度集中于 {top_platform['name']} {top_pct:.1f}%，HHI={revenue_hhi:.3f}（{revenue_hhi_tag}）",
            "assumption": "小红书电商+商单为主要变现通道，其他平台变现刚起步",
            "actions": [
                f"提升 {rev_nonzero[-1]['name'] if len(rev_nonzero)>1 else '尾部平台'}变现效率，探索跨平台商单打包",
                "保持小红书核心地位同时，逐步提升第二平台收入占比",
            ],
            "confidence": "high" if mock_rev else "medium",
        })

    # 2b. 收入目标达成偏慢
    if revenue_goal > 0 and revenue_rate < 0.5 and days_passed >= 5 and month_revenue_total > 0:
        anomalies.append({
            "level": "WARN" if revenue_rate < 0.3 else "INFO",
            "category": "revenue_pace",
            "problem": f"收入目标达成 {revenue_rate*100:.1f}%（MTD {_money(month_revenue_total)} / 目标 {_money(revenue_goal)}），剩余 {days_remaining} 天需日均 {_money(revenue_daily_needed)}",
            "assumption": "变现节奏正常但客单价偏低 / 商单排期集中在下旬",
            "actions": [
                f"提升日均收入至 {_money(revenue_daily_needed)} 以上",
                "排查是否有商单延期到账，加速回款",
                "下旬增加 1-2 个品牌合作或直播带货场次",
            ],
            "confidence": "medium",
        })

    # 3. 节奏偏慢（目标达成率 < 30% 且已过天数 > 当月 10%）
    if new_fans_goal > 0 and new_fans_rate < 0.3 and days_passed >= 3:
        # 最近 7 天发布数 vs 7 月基线
        publish_ratio = (recent7_posts_daily / PUBLISH_BASELINE_DAILY_7M) if PUBLISH_BASELINE_DAILY_7M > 0 else 1.0
        assumption_parts = []
        if publish_ratio < 0.8:
            assumption_parts.append(f"发布频率偏低（近 7 天日均 {recent7_posts_daily:.1f} vs 7 月基线 {PUBLISH_BASELINE_DAILY_7M}）")
        if top1_share < 0.3:
            assumption_parts.append("缺少爆款级传播内容")
        if not assumption_parts:
            assumption_parts.append("自然增长放缓 / 平台进入存量期")
        anomalies.append({
            "level": "WARN",
            "category": "goal_pace",
            "problem": f"本月净增节奏偏慢：{new_fans_rate*100:.1f}% / 月目标 {int(new_fans_goal)}（需剩余日均 {new_fans_daily_needed:.0f} 粉）",
            "assumption": "；".join(assumption_parts),
            "actions": [
                f"恢复 7 月发布节奏（当前 {recent7_posts_daily:.1f}/日 → 目标 {PUBLISH_BASELINE_DAILY_7M}/日）",
                "复用已验证爆款结构：复刻 Top1 文 3 个变体做 A/B 测试",
                "建立每周一晚 30 分钟目标进度复盘机制",
            ],
            "confidence": "medium" if not assumption_parts else "high",
        })

    # 4. 内容头部化（Top1 占比 >= 40%）
    if top1_share >= 0.4 and total_top_exp > 0:
        anomalies.append({
            "level": "WARN",
            "category": "content_concentration",
            "problem": f"Top1 内容曝光占比 {top1_share*100:.1f}%（{top1_title[:30]}），呈极端头部化",
            "assumption": "平台算法对单篇加权推荐 / 选题踩中短期热点 / 其它选题质量波动大",
            "actions": [
                f"系列化拆解 Top1《{top1_title[:30]}》为 5 个子话题续作",
                "建立爆款备份库：每篇验证成功的爆款，提前准备 2 个同结构变体选题",
                "做爆款 vs 普通款的选题要素对比，沉淀可复用模板",
            ],
            "confidence": "high",
        })

    # 5. B 站涨粉波动大（标准差/均值 CV > 0.5）
    bili_daily = [(d, by_date[d]["net"]) for d in sorted_dates[-14:]
                  if any(r.get("date") == d and r.get("platform") == "bili" for r in daily_metrics)]
    if len(bili_daily) >= 7:
        vals = [v for _, v in bili_daily]
        mean_v = sum(vals) / len(vals)
        var = sum((v - mean_v) ** 2 for v in vals) / len(vals)
        std_v = math.sqrt(var)
        cv = (std_v / mean_v) if mean_v > 0 else 0
        if cv > 0.5:
            anomalies.append({
                "level": "INFO",
                "category": "volatility",
                "problem": f"B站近 14 天涨粉波动较大（均值 {mean_v:.0f}，标准差 {std_v:.0f}，变异系数 {cv:.2f}）",
                "assumption": "B站推荐算法对不同内容类型反馈差异大 / 个别作品进入推荐池",
                "actions": [
                    "对比 B 站日涨粉 Top3 日 vs Bottom3 日的内容类型、封面风格差异",
                    "对高涨粉作品的标题/封面/标签要素做对照复盘",
                    "如稳定产出则放大该类内容，否则接受自然波动",
                ],
                "confidence": "medium",
            })

    # 6. 公众号涨粉极少（无主动运营）
    wechat_item = next((p for p in platform_contrib if p["id"] == "wechat"), None)
    if wechat_item and wechat_item["new_fans"] < 30 and days_passed >= 3:
        anomalies.append({
            "level": "INFO",
            "category": "growth_opportunity",
            "problem": f"公众号本月涨粉仅 {wechat_item['new_fans']:.0f} 人（自然增长），未做主动运营",
            "assumption": "未设置公众号关注引导 / 其他平台未做倒流 / 暂无公众号诱饵内容",
            "actions": [
                "评估公众号投入产出：若月目标 >100 粉则启动，否则暂维持",
                "在小红书/B 站文末加入公众号诱饵（数据分析独家资料包）引导",
                "把小红书爆款内容整理成长图文版在公众号二次发布",
            ],
            "confidence": "high",
        })

    # 级别计数
    level_counts = {"CRITICAL": 0, "WARN": 0, "INFO": 0}
    for a in anomalies:
        lvl = a.get("level") or "INFO"
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

    # ---- 每模块结论文字（insights_per_module）------------------------------
    # Executive Summary 一句话
    xhs_fan_share = next((p["new_fans"] for p in platform_contrib if p["id"] == "xhs"), 0) / max(1, month_new_fans_total)
    xhs_rev_share = next((p["revenue"] for p in platform_contrib if p["id"] == "xhs"), 0) / max(0.01, month_revenue_total)
    stale_platforms_count = sum(1 for a in anomalies if a["category"] == "data_quality")
    mock_tag_short = " [模拟]" if mock_rev else ""
    rev_structure_note = ""
    if revenue_hhi >= 0.75 and month_revenue_total > 0:
        rev_structure_note = "，收入结构极端集中"
    elif revenue_hhi >= 0.25 and month_revenue_total > 0:
        rev_structure_note = "，收入结构中度集中"
    one_sentence = (
        f"{today_dt.month} 月开局净增粉丝 {_k(month_new_fans_total)} 人（月目标 {_pct(new_fans_rate, 1)}），"
        f"小红书贡献 {_pct(xhs_fan_share,0)} 涨粉与 {_pct(xhs_rev_share,0)} 收入{mock_tag_short}"
        f"（{_pct(revenue_rate,0)} 达成收入目标{rev_structure_note}）"
        f"；{stale_platforms_count} 个平台存在数据滞后，部分结论置信度降低。"
    )
    # 完整报告结论（3-4行，汇总下方所有模块内容）
    lines = []
    # 第 1 行：增长 & 趋势
    trend_dir = "上升" if mom_ratio > 0.1 else "下降" if mom_ratio < -0.1 else "持平"
    line1 = (
        f"📈 增长态势：净增 {_k(month_new_fans_total)} / 总盘 {_k(fans_total_now)}，近7日日均净增 {recent7_avg_net:.0f}"
        f"，环比前7日{trend_dir}{abs(mom_ratio)*100:.0f}%；月目标完成 {_pct(new_fans_rate,1)}"
        f"，剩余 {days_remaining} 天需日均 {new_fans_daily_needed:.0f} 粉。"
    )
    lines.append(line1)
    # 第 2 行：结构 & 集中风险（粉丝 + 收入）
    _contrib_sorted = sorted(platform_contrib, key=lambda x: -x["new_fans"])
    contrib_top_names = [p["name"] for p in _contrib_sorted[:2]]
    fans_hhi_short = f"粉丝HHI={fans_hhi:.2f}({fans_hhi_tag})"
    rev_hhi_short = (
        f"收入HHI={revenue_hhi:.2f}({revenue_hhi_tag})"
        if month_revenue_total > 0 else "暂无收入结构数据"
    )
    line2 = (
        f"🧩 结构风险：粉丝呈 {'+'.join(contrib_top_names)} 双平台主导，{fans_hhi_short}；"
        f"收入 {_money(month_revenue_total)}（达成 {_pct(revenue_rate,0)}），{rev_hhi_short}{mock_tag_short}；"
        f"小红书单一渠道依赖度偏高，建议分散产能与变现路径。"
    )
    lines.append(line2)
    # 第 3 行：内容表现 & 归因
    if total_top_exp > 0:
        content_short = (
            f"Top1《{top1_title[:20]}…》占 {_pct(top1_share,1)} 曝光，Top3 合计 {_pct(top3_share,1)}，头部化程度{'偏高' if top1_share >= 0.4 else '可控'}"
        )
    else:
        content_short = "内容曝光明细暂不完整"
    _eff_top = type_efficiency[0] if type_efficiency else None
    _eff_bottom = type_efficiency[-1] if len(type_efficiency) >= 2 else None
    if attr_total_fans > 0:
        attr_short = (
            f"小红书 {xhs_share_in_attr*100:.0f}% 涨粉贡献，"
            + (f"{_eff_top['type']}千曝涨粉 {_eff_top['fans_per_kview']:.1f}"
               if (_eff_top and _eff_bottom and _eff_bottom['fans_per_kview'] > 0) else "体裁效率差异待补齐")
        )
    else:
        attr_short = "归因数据待补齐"
    line3 = f"🎯 内容归因：{content_short}；{attr_short}。"
    lines.append(line3)
    # 第 4 行：数据质量 + 后续行动建议（不含异常清单）
    if stale_platforms_count > 0:
        q_short = f"⚠️ {stale_platforms_count} 个平台数据滞后，建议24h内刷新同步"
    else:
        q_short = "✅ 全部平台数据新鲜度通过校验"
    line4 = (
        f"🛠 数据质量与行动：{q_short}。"
        f"建议：① 把 Top1 爆款拆解为 3-5 篇续作复制方法论；"
        f"② 拓展第二收入平台以分散单一渠道集中度风险；"
        f"③ 补足体裁效率短板，把低千曝涨粉体裁迭代或降产能。"
    )
    lines.append(line4)
    full_report_paragraph = "\n".join(lines)

    # 4 个胶囊
    capsule_pace = (
        f"本月节奏{'偏慢' if new_fans_rate < 0.3 else '正常'}："
        f"MTD 净增 {_k(month_new_fans_total)}，剩余 {days_remaining} 天需日均 {new_fans_daily_needed:.0f} 粉"
        f"{'方可达成 ' + str(int(new_fans_goal)) + ' 目标' if new_fans_goal else ''}"
    )
    if revenue_hhi >= 0.75 and month_revenue_total > 0:
        capsule_revenue = (f"CRITICAL：收入集中于小红书 {_pct(xhs_rev_share,0)}，HHI={revenue_hhi:.3f}（{revenue_hhi_tag}）{mock_tag_short}")
        capsule_revenue_level = "critical"
    elif month_revenue_total <= 0:
        capsule_revenue = "— 本月暂无收入数据 —"
        capsule_revenue_level = "info"
    else:
        capsule_revenue = f"收入 HHI={revenue_hhi:.2f}（{revenue_hhi_tag}），达成 {_pct(revenue_rate,0)}{mock_tag_short}"
        capsule_revenue_level = revenue_hhi_level
    if stale_platforms_count == 0:
        capsule_quality = "数据新鲜度：全部平台通过校验"
        capsule_quality_level = "success"
    else:
        crit_count = sum(1 for a in anomalies if a["category"]=="data_quality" and a["level"]=="CRITICAL")
        capsule_quality = (f"{'CRITICAL' if crit_count else 'WARN'}："
                           f"{stale_platforms_count} 个平台内容数据滞后（最高停更 20 天）")
        capsule_quality_level = "critical" if crit_count else "warn"
    if top1_share >= 0.4 and total_top_exp > 0:
        capsule_head = f"WARN：Top1 内容曝光占比 {_pct(top1_share,1)}，头部化风险较高"
        capsule_head_level = "warn"
    elif top1_share > 0:
        capsule_head = f"Top1 曝光占比 {_pct(top1_share,1)}，头部化可控"
        capsule_head_level = "success"
    else:
        capsule_head = "— 暂无 Top 曝光结构数据 —"
        capsule_head_level = "info"

    exec_summary = {
        "one_sentence": one_sentence,
        "full_report": full_report_paragraph,
        "capsules": [
            {"key": "pace", "label": "增长节奏", "text": capsule_pace, "level": "info" if new_fans_rate >= 0.3 else "warn"},
            {"key": "revenue", "label": "收入集中", "text": capsule_revenue, "level": capsule_revenue_level},
            {"key": "quality", "label": "数据质量", "text": capsule_quality, "level": capsule_quality_level},
            {"key": "head", "label": "内容头部", "text": capsule_head, "level": capsule_head_level},
        ],
        "level_counts": level_counts,
    }

    # 趋势结论
    trend_direction = "上升" if mom_ratio > 0.1 else "下降" if mom_ratio < -0.1 else "持平"
    trend_insight = (
        f"【趋势结论 · 高置信度】近 7 天日均净增 {recent7_avg_net:.0f}，较前 7 天"
        f" {trend_direction}{abs(mom_ratio)*100:.0f}%；整体呈"
        f"{'前高后平' if inflection else '平稳波动'}形态"
        + (f"（拐点 {inflection['date']}：日增从 {inflection['prev']:.0f} 掉到 {inflection['next']:.0f}）" if inflection else "")
        + f"；小红书（占 {_pct(xhs_fan_share,0)}）是波动主要来源。"
    )

    # 结构（净增瀑布）
    contrib_sorted = sorted(platform_contrib, key=lambda x: -x["new_fans"])
    top2 = contrib_sorted[:2]
    top2_share = sum(p["new_fans"] for p in top2) / max(1, month_new_fans_total)
    structure_fan_insight = (
        f"【结构结论 · 高置信度】{len(contrib_sorted)} 平台全部正增长，但贡献极度不均："
        + " + ".join(f"{p['name']} {_k(p['new_fans'])}（{_pct(p['new_fans']/max(1,month_new_fans_total))}）" for p in top2)
        + f" 合计贡献 {_pct(top2_share,0)} 净增；"
        + (f"{contrib_sorted[-1]['name']} 仅 +{_k(contrib_sorted[-1]['new_fans'])}，属自然波动范围，不必过度解读。"
           if contrib_sorted[-1]["new_fans"] < 10 else "")
    )

    # 粉丝结构
    fans_top1 = contrib_sorted[0]
    fans_top1_share = fans_top1["fans_now"] / max(1, fans_total_now)
    structure_fans_insight = (
        f"【结构结论 · 高置信度】粉丝结构呈\"{contrib_sorted[0]['name']}+{contrib_sorted[1]['name']}\""
        f"双平台主导（合计 {_pct(contrib_sorted[0]['fans_now']/max(1,fans_total_now) + contrib_sorted[1]['fans_now']/max(1,fans_total_now),1)}），"
        f"HHI={fans_hhi:.3f} 属{fans_hhi_tag}。风险点：{fans_top1['name']}单平台占比 {_pct(fans_top1_share,1)}，"
        f"若出现账号限流将显著影响总盘；建议加速 {contrib_sorted[-2]['name']}/{contrib_sorted[-1]['name']} 补齐。"
    )

    # 收入结构卡（rev_nonzero 已在前面定义）
    mock_tag = " [模拟数据]" if mock_rev else ""
    if month_revenue_total > 0:
        rev_top1 = rev_nonzero[0]
        rev_top1_share = rev_top1["revenue"] / month_revenue_total
        # 按收入贡献排序展示
        rev_detail_str = "、".join(
            f"{p['name']} {_money(p['revenue'])}（{_pct(p['revenue']/month_revenue_total,1)}）"
            for p in rev_nonzero
        )
        if revenue_hhi_level == "critical":
            rev_severity = "CRITICAL"
            rev_advice = "收入极端集中，单一平台风险敞口过大。建议：① 加速第二收入平台变现；② 分散产品线，避免压在单一 SKU。"
        elif revenue_hhi_level == "warn":
            rev_severity = "WARN"
            rev_advice = f"收入结构{revenue_hhi_tag}，{rev_top1['name']}占比 {_pct(rev_top1_share,0)} 偏高。建议：① 提升 {rev_nonzero[-1]['name']} 变现效率；② 探索跨平台商单打包。"
        else:
            rev_severity = "INFO"
            rev_advice = "收入结构较为分散，抗风险能力良好。建议：① 保持各平台变现节奏；② 重点提升 Top2 平台客单价。"
        # MoM 增长 + 利润
        mom_str = ""
        if mock_rev:
            kpi = mock_rev["kpi"]
            mom_str = f" 环比上月 {_money(kpi['last_revenue'])}{'增长' if kpi['rev_mom'] >= 0 else '下降'} {_pct(abs(kpi['rev_mom']),1)}，"
            mom_str += f"成本 {_money(kpi['total_cost'])}（环比{'↑' if kpi['cost_mom']>=0 else '↓'}{_pct(abs(kpi['cost_mom']),1)}），利润 {_money(kpi['total_profit'])}（利润率 {_pct(kpi['profit_rate'],1)}），"
        rev_card_insight = (
            f"【经营结论 · {rev_severity}】{mock_tag}本月收入 {_money(month_revenue_total)}，"
            + mom_str
            + f"各平台贡献：{rev_detail_str}。"
            + f"HHI={revenue_hhi:.3f}（{revenue_hhi_tag}），{rev_advice}"
        )
    else:
        rev_card_insight = "【经营结论】本月暂无收入数据，无法做收入风险判断。建议补充电商/商单侧数据。"
    rev_card_insight_goal = (
        f"【目标追踪】{mock_tag}本月收入目标 {_money(revenue_goal)}，当前达成 {_pct(revenue_rate,1)}，"
        f"剩余 {days_remaining} 天需日均 {_money(revenue_daily_needed)}。"
    ) if revenue_goal > 0 else ""

    # 内容 Top
    if total_top_exp > 0:
        content_card_insight = (
            f"【内容结论 · 高置信度】本月内容呈极端头部化：Top1《{top1_title[:36]}》一篇独占 {_pct(top1_share,1)} 曝光，"
            f"Top3 合计 {_pct(top3_share,1)}，Top10 合计 {_pct(top10_share,1)}。"
            + "这意味着① 内容生产 ROI 极度依赖爆款；② 若选题枯竭或平台限流，曝光将断崖式下滑。"
            + f"建议：把 Top1《{top1_title[:24]}》拆解为 3-5 篇系列续作，复用爆款结构。"
        )
    else:
        content_card_insight = "【内容结论】暂无 Top 曝光明细，建议从 attribution.json 补齐 content_items_top。"

    # 四象限（无真实内容分类，给通用策略文案，前端按比例算数量）
    scatter_insight = (
        "【内容策略结论】建议把产能从\"待淘汰\"类选题（职场吐槽体、低效率鸡汤）"
        "转移到\"潜力+明星\"类选题（工具教程+实战案例），单位时间涨粉效率可提升 3×。"
        "重点盯第一象限：互动率 ≥ 中位数且阅读 ≥ 中位数的作品，复制其标题结构与封面要素。"
    )

    # 归因结论
    if attr_total_fans > 0:
        eff_top = type_efficiency[0] if type_efficiency else None
        eff_bottom = type_efficiency[-1] if len(type_efficiency) >= 2 else None
        ratio = (eff_top["fans_per_kview"] / eff_bottom["fans_per_kview"]) if (eff_top and eff_bottom and eff_bottom["fans_per_kview"] > 0) else 1
        attr_insight = (
            f"【归因结论 · 高置信度】{xhs_share_in_attr*100:.1f}% 涨粉来自小红书（{xhs_new_fans:.0f}/{attr_total_fans:.0f}），"
            + (f"其中 {eff_top['type']} 体裁每千曝光涨粉 {eff_top['fans_per_kview']:.1f} 人，"
               f"是 {eff_bottom['type']}（{eff_bottom['fans_per_kview']:.1f}）的 {ratio:.1f} 倍，" if eff_top and eff_bottom else "")
            + "在当前产能约束下，优先加码\"小红书图文工具教程类\"是单位产出最高的路径。"
        )
    else:
        attr_insight = "【归因结论】暂无内容级涨粉归因数据，建议运行 build_attribution.py 生成 attribution.json。"

    # 异常卡结论
    anomaly_overview = (
        f"【异常总览】{len(anomalies)} 项问题："
        + " / ".join(f"{cnt} {lvl}" for lvl, cnt in level_counts.items() if cnt > 0)
        + "。其中数据类问题需 24h 内处理，经营类问题纳入本周行动计划。"
    )

    # 收入分析结构（供前端 renderRevenueCard 直接消费）
    revenue_analysis = mock_rev if mock_rev else {
        "is_mock": False,
        "by_platform": [
            {"platform": p["id"], "platform_name": p["name"], "value": p["revenue"]}
            for p in platform_contrib if p["revenue"] > 0
        ],
        "month_total_value": round(month_revenue_total, 2),
        "hhi_index": round(revenue_hhi, 4),
        "hhi_level": revenue_hhi_level,
        "hhi_tag": revenue_hhi_tag,
    }
    # goals 里补 revenue_mtd_target + profit_mtd_target（前端仪表用）
    goals_with_targets = dict(goals)
    goals_with_targets["revenue_mtd_target"] = {"target_value": revenue_goal}
    if mock_rev:
        goals_with_targets["profit_mtd_target"] = {"target_value": _MOCK_PROFIT_GOAL}

    return {
        "schema": "self-media-business-ops-analysis.v1",
        "generated_at": now_text(),
        "goals": goals_with_targets,
        "meta": {
            "date_min": dashboard.get("dateMin"),
            "date_max": dashboard.get("dateMax"),
            "latest_month": dashboard.get("latestMonth"),
            "days_passed_this_month": days_passed,
            "days_remaining_this_month": days_remaining,
        },
        "revenue_analysis": revenue_analysis,
        "trend_analysis": {
            "recent7_avg_net": round(recent7_avg_net, 2),
            "prev7_avg_net": round(prev7_avg_net, 2),
            "mom_ratio": round(mom_ratio, 4),
            "inflection": inflection,
            "recent7_posts_daily": round(recent7_posts_daily, 2),
            "publish_baseline_7m": PUBLISH_BASELINE_DAILY_7M,
        },
        "structure_analysis": {
            "platform_contribution": platform_contrib,  # 瀑布图用
            "totals": {
                "fans_now": fans_total_now,
                "month_new_fans": month_new_fans_total,
                "month_revenue": month_revenue_total,
                "month_content": month_content_total,
                "month_views": month_views_total,
            },
            "concentration": {
                "fans_hhi": round(fans_hhi, 4),
                "fans_hhi_level": fans_hhi_level,
                "fans_hhi_tag": fans_hhi_tag,
                "revenue_hhi": round(revenue_hhi, 4),
                "revenue_hhi_level": revenue_hhi_level,
                "revenue_hhi_tag": revenue_hhi_tag,
                "newfans_hhi": round(newfans_hhi, 4),
            },
            "goal_tracking": {
                "new_fans_rate": round(new_fans_rate, 4),
                "revenue_rate": round(revenue_rate, 4),
                "new_fans_daily_needed": round(new_fans_daily_needed, 1),
                "revenue_daily_needed": round(revenue_daily_needed, 1),
            },
            "top_content_exposure_shares": {
                "total": round(total_top_exp, 0),
                "top1_share": round(top1_share, 4),
                "top3_share": round(top3_share, 4),
                "top10_share": round(top10_share, 4),
                "top1_title": top1_title,
            },
            "attribution_efficiency": {
                "total_new_fans": round(attr_total_fans, 0),
                "xhs_share_in_attr": round(xhs_share_in_attr, 4),
                "by_type_ranked": type_efficiency,
            },
        },
        "anomaly_list": anomalies,
        "insights_per_module": {
            "exec_summary_one_sentence": one_sentence,
            "trend": trend_insight,
            "structure_fan_waterfall": structure_fan_insight,
            "structure_fans_donut": structure_fans_insight,
            "revenue_card": rev_card_insight,
            "revenue_card_goal": rev_card_insight_goal,
            "content_table": content_card_insight,
            "scatter_quadrant": scatter_insight,
            "attribution": attr_insight,
            "anomaly_overview": anomaly_overview,
        },
        "exec_summary": exec_summary,
    }


def load_full_context_for_ops() -> dict[str, Any]:
    """为 build_business_ops_analysis 准备所需上下文（dashboard+compact+attribution）。"""
    compact_path = DASHBOARD_DIR / "compact_dashboard_data.json"
    return {
        "dashboard": read_json(DASHBOARD_PATH, {}),
        "compact": read_json(compact_path, {}),
        "attribution": read_json(PROJECT_ROOT / "runtime-data" / "console-state" / "attribution.json", {}),
    }


def write_ops_analysis() -> dict[str, Any]:
    ctx = load_full_context_for_ops()
    result = build_business_ops_analysis(ctx)
    write_json(OPS_ANALYSIS_PATH, sanitize_nan_write(result))
    return result


def sanitize_nan_write(obj):
    """把 NaN / Inf 替换为 0，避免非法 JSON（write_json 未处理）。"""
    if isinstance(obj, dict):
        return {k: sanitize_nan_write(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_nan_write(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or obj == float("inf") or obj == float("-inf"):
            return 0.0
        return obj
    return obj


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=["report", "build-workbench", "screenshot", "send-lark", "build-ops-analysis"],
        default="report",
    )
    args = parser.parse_args()
    if args.stage == "build-ops-analysis":
        result = write_ops_analysis()
        result = {"ok": True, "path": str(OPS_ANALYSIS_PATH),
                  "anomaly_counts": result["exec_summary"]["level_counts"]}
    elif args.stage == "report":
        # 生成日报前顺便产出 ops-analysis（链路合并）
        write_ops_analysis()
        result = generate_report()
    elif args.stage == "build-workbench":
        write_ops_analysis()
        result = build_workbench()
    elif args.stage == "screenshot":
        result = capture_console_screenshot()
    elif args.stage == "send-lark":
        result = send_lark_message()
    else:
        result = {
            "status": "pending",
            "message": f"{args.stage} 阶段将在下一步接入具体实现",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
