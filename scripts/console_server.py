# -*- coding: utf-8 -*-
"""自媒体数据中控台本地 Web 服务。

仅使用 Python 标准库，提供两个能力：

1. 静态文件服务：把 console/ 目录作为前端资源根目录。
2. JSON API：
   - GET  /api/dashboard         读取紧凑版看板数据 (compact_dashboard_data.json)
   - GET  /api/meta               聚合新鲜度、业务校验、同步状态
   - GET  /api/hotlist           读取热榜素材库
   - POST /api/hot                添加热榜条目
   - PUT  /api/hot/<id>           更新热榜条目状态
   - DELETE /api/hot/<id>        删除热榜条目
   - POST /api/refresh            拉取/生成、规范化、校验并刷新数据
   - POST /api/report             生成 Markdown 报告并落盘
   - GET  /api/report/<id>       返回报告内容
   - GET  /api/platform-entries   返回各平台后台入口（白名单）

启动：
    python scripts/console_server.py
    python scripts/console_server.py --port 8765 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_paths import (
    PROJECT_ROOT,
    ensure_user_skeleton,
    hotlist_path,
    load_project_config,
    missing_dashboard_files,
    portable_path,
    resolve_data_context,
)


CONSOLE_DIR = PROJECT_ROOT / "console"
DATA_CONTEXT = resolve_data_context()
DATA_ROOT = DATA_CONTEXT.root
DASHBOARD_DIR = DATA_ROOT / "dashboard-normalized"
DASHBOARD_PATH = DASHBOARD_DIR / "self_media_dashboard.json"
COMPACT_DASHBOARD_PATH = DASHBOARD_DIR / "compact_dashboard_data.json"
BUSINESS_CHECK_PATH = DASHBOARD_DIR / "latest_business_check.json"
SERVER_SYNC_REPORT_PATH = DASHBOARD_DIR / "server_sync_refresh_report.json"
REFRESH_CHECK_PATH = DASHBOARD_DIR / "latest_refresh_check.json"
REFRESH_PIPELINE = PROJECT_ROOT / "scripts" / "refresh_data.py"

RUNTIME_DIR = PROJECT_ROOT / "runtime-data" / DATA_CONTEXT.mode
STATE_DIR = RUNTIME_DIR / "console-state"
HOTLIST_PATH = STATE_DIR / "hotlist.json"
ATTRIBUTION_PATH = STATE_DIR / "attribution.json"
OPS_ANALYSIS_PATH = STATE_DIR / "business_ops_analysis.json"
NOTES_PATH = STATE_DIR / "notes.json"            # 笔记灵感
AI_OUTPUTS_PATH = STATE_DIR / "ai_outputs.json"  # AI 生成素材留档
CONFIG_PATH = PROJECT_ROOT / "config.json"        # AI API 配置（使用者自行接入）
REPORTS_DIR = RUNTIME_DIR / "reports"
LOGS_DIR = RUNTIME_DIR / "logs"

# 平台后台入口白名单，由后端管理，避免前端自由拼接 URL
PLATFORM_ENTRIES = [
    {"platform": "xhs",    "name": "小红书", "url": "https://creator.xiaohongshu.com/creator/home"},
    {"platform": "bili",   "name": "B站",   "url": "https://member.bilibili.com/platform/upload-manager/article"},
    {"platform": "zhihu",  "name": "知乎",  "url": "https://www.zhihu.com/creator"},
    {"platform": "wechat", "name": "公众号", "url": "https://mp.weixin.qq.com/"},
    {"platform": "douyin", "name": "抖音",  "url": "https://creator.douyin.com/creator-matter/home"},
]


# ============================================================
# 工具
# ============================================================
def ensure_dirs() -> None:
    for p in (STATE_DIR, REPORTS_DIR, LOGS_DIR, CONSOLE_DIR):
        p.mkdir(parents=True, exist_ok=True)
    # 初始化空数据文件（仅当不存在时）
    for p in (NOTES_PATH, AI_OUTPUTS_PATH):
        if not p.exists():
            write_json(p, [])


def read_json(path: Path, fallback=None):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def number(v) -> float:
    try:
        out = float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if out != out or out in (float('inf'), float('-inf')):
        return 0.0
    return out


def sanitize_nan(obj):
    """递归把 NaN / Infinity 转成 null，避免浏览器 JSON 解析失败。

    compact_dashboard_data.json 由 Python 生成，缺失字段会出现 NaN，
    而 NaN 在标准 JSON 中是非法的，浏览器 JSON.parse 会抛错。
    """
    if isinstance(obj, dict):
        return {k: sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_nan(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj or obj in (float('inf'), float('-inf')):
            return None
        return obj
    return obj


# ============================================================
# 业务逻辑
# ============================================================
def load_dashboard() -> dict:
    """读取紧凑版看板数据，并从原始 JSON 补充 interact 字段。"""
    data = read_json(COMPACT_DASHBOARD_PATH, {}) or {}
    original = read_json(DASHBOARD_PATH, {}) or {}
    orig_platforms = {p.get("id"): p for p in (original.get("platforms") or [])}
    for p in data.get("platforms") or []:
        pid = p.get("platform")
        orig = orig_platforms.get(pid)
        if orig:
            p["month_interact"] = number(orig.get("interact"))
    return data


def load_meta() -> dict:
    """聚合 meta：新鲜度、业务校验、同步状态、平台状态摘要。"""
    dashboard = load_dashboard()
    business = read_json(BUSINESS_CHECK_PATH, {}) or {}
    sync_report = read_json(SERVER_SYNC_REPORT_PATH, {}) or {}
    refresh_check = read_json(REFRESH_CHECK_PATH, {}) or {}
    platforms = []
    for p in dashboard.get("platforms") or []:
        platforms.append({
            "id": p.get("platform"),
            "name": p.get("platform_name"),
            "freshness_status": p.get("freshness_status") or "unknown",
            "latest_daily_date": p.get("latest_daily_date"),
            "latest_total_followers_date": p.get("latest_total_followers_date"),
            "month_net_followers": number(p.get("month_net_followers")),
            "month_views": number(p.get("month_views")),
            "month_content_count": number(p.get("month_content_count")),
            "freshness_issues": p.get("freshness_issues") or [],
            "account_snapshots": p.get("account_snapshots") or [],
        })
    stale = [p for p in platforms if p["freshness_status"] != "ready"]
    business_status = str(business.get("status") or "unknown")
    sync_status = str(sync_report.get("status") or "unknown")
    refresh_status = str(refresh_check.get("status") or "unknown")
    if refresh_status == "failed" or business_status not in {"ready", "success"}:
        status = "failed"
    elif stale or (DATA_CONTEXT.mode == "user" and sync_status not in {"ready", "success"}):
        status = "partial"
    else:
        status = "ready"
    config = load_project_config()
    profile = config.get("profile") if isinstance(config.get("profile"), dict) else {}
    active_platforms = profile.get("active_platforms") if isinstance(profile.get("active_platforms"), list) else []
    onboarding_missing = []
    if not str(profile.get("display_name") or "").strip():
        onboarding_missing.append("展示名称或品牌别名")
    if not active_platforms:
        onboarding_missing.append("启用平台")
    if DATA_CONTEXT.mode == "user":
        onboarding_missing.extend(
            f"dashboard-normalized/{name}" for name in missing_dashboard_files(DATA_ROOT)
        )
    return {
        "status": status,
        "data_mode": DATA_CONTEXT.mode,
        "is_demo": DATA_CONTEXT.is_demo,
        "data_root": portable_path(DATA_ROOT),
        "onboarding": {
            "complete": not onboarding_missing and DATA_CONTEXT.mode == "user",
            "missing": onboarding_missing,
            "guide": "data/user/README.md",
        },
        "sync_status": sync_status,
        "business_status": business_status,
        "refresh_status": refresh_status,
        "refresh_errors": refresh_check.get("errors") or [],
        "refresh_checked_at": refresh_check.get("finished_at") or refresh_check.get("generated_at"),
        "generated_at": dashboard.get("generated_at"),
        "date_min": dashboard.get("date_min"),
        "date_max": dashboard.get("date_max"),
        "platforms": platforms,
        "stale_platforms": stale,
        "totals": dashboard.get("totals") or {},
    }


def load_hotlist() -> list:
    return read_json(HOTLIST_PATH, []) or []


def load_attribution() -> dict:
    """读取粉丝增长归因分析数据（由 build_attribution.py 预生成）。"""
    return read_json(ATTRIBUTION_PATH, {}) or {}


def load_ops_analysis() -> dict:
    """读取经营分析结果（由 daily_pipeline.py build-ops-analysis 预生成）。
    若文件不存在或为空，返回 fallback 骨架（避免前端报错）。"""
    data = read_json(OPS_ANALYSIS_PATH, None)
    if data:
        return data
    # Fallback：空骨架，等 pipeline 下次跑完即有数据
    return {
        "schema": "self-media-business-ops-analysis.v1",
        "generated_at": now_text(),
        "status": "stale",
        "notice": "经营分析数据暂未生成，请点击右上角刷新按钮或运行 daily_pipeline.py。",
        "exec_summary": {"one_sentence": "", "capsules": [], "level_counts": {}},
        "insights_per_module": {},
        "anomaly_list": [],
        "structure_analysis": {},
        "trend_analysis": {},
        "goals": {},
    }


def suggest_hotlist(keyword: str = "数据分析") -> list:
    """主流媒体"数据分析"相关热门内容推荐，取前 5 条。

    优先读取服务器采集的真实数据（hotlist_latest.json），
    回退到精选话题库（标注 source=curated）。
    """
    # 1) 尝试读取服务器采集的真实数据
    hotlist_data_paths = [hotlist_path(DATA_CONTEXT)]
    for p in hotlist_data_paths:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                items = data.get("items") or []
                if items:
                    # 补充 source_url 字段（采集数据已有 url 字段）
                    for it in items:
                        if not it.get("source_url"):
                            it["source_url"] = it.get("url") or ""
                        if not it.get("source"):
                            it["source"] = "server_collect"
                    return items[:5]
            except Exception:
                pass

    # 2) 回退：精选话题库（标注 curated）
    kw = (keyword or "数据分析").strip()
    pool = [
        {
            "title": f"{kw}入行指南：从工具学习到业务实战的完整路径",
            "platform": "xhs", "platform_name": "小红书",
            "keyword": kw, "heat": "9.2w", "source_url": "", "source": "curated",
        },
        {
            "title": f"用 SQL 做用户分层：{kw}在留存分析中的真实用法",
            "platform": "zhihu", "platform_name": "知乎",
            "keyword": kw, "heat": "8.7w", "source_url": "", "source": "curated",
        },
        {
            "title": f"B站 {kw}教程 Top5：Pandas / 可视化 / AB 实验全流程",
            "platform": "bili", "platform_name": "B站",
            "keyword": kw, "heat": "7.5w", "source_url": "", "source": "curated",
        },
        {
            "title": f"公众号 {kw}周报：本周 3 篇深度拆解与 1 个岗位机会",
            "platform": "wechat", "platform_name": "公众号",
            "keyword": kw, "heat": "6.8w", "source_url": "", "source": "curated",
        },
        {
            "title": f"抖音 {kw}短课：30 秒讲透转化漏斗与归因模型",
            "platform": "douyin", "platform_name": "抖音",
            "keyword": kw, "heat": "6.1w", "source_url": "", "source": "curated",
        },
        {
            "title": f"{kw}面试 50 问：大厂真实考题与回答框架",
            "platform": "xhs", "platform_name": "小红书",
            "keyword": kw, "heat": "5.9w", "source_url": "", "source": "curated",
        },
        {
            "title": f"从 0 搭建 {kw}指标体系：DAU / LTV / 留存的三层架构",
            "platform": "zhihu", "platform_name": "知乎",
            "keyword": kw, "heat": "5.4w", "source_url": "", "source": "curated",
        },
    ]
    # 按热度降序，取前 5
    def _heat_num(h):
        try:
            return float(str(h).replace("w", "").replace("k", ""))
        except Exception:
            return 0
    pool.sort(key=lambda x: _heat_num(x.get("heat")), reverse=True)
    return pool[:5]



def save_hotlist(items: list) -> None:
    write_json(HOTLIST_PATH, items)


def hot_add(payload: dict) -> dict:
    items = load_hotlist()
    now = now_text()
    item = {
        "id": uuid.uuid4().hex[:12],
        "title": str(payload.get("title") or "").strip(),
        "platform": payload.get("platform") or "xhs",
        "keyword": payload.get("keyword") or "",
        "heat": payload.get("heat") or "",
        "source_url": str(payload.get("source_url") or "").strip(),
        "source": payload.get("source") or "manual",
        "status": "unread",
        "created_at": now,
    }
    if not item["title"]:
        return {"ok": False, "error": "标题不能为空"}
    items.insert(0, item)
    save_hotlist(items)
    return {"ok": True, "item": item}


def hot_update(item_id: str, patch: dict) -> dict:
    items = load_hotlist()
    for it in items:
        if it.get("id") == item_id:
            if "status" in patch:
                if patch["status"] not in {"unread", "read", "to_topic", "ignored"}:
                    return {"ok": False, "error": "非法状态"}
                it["status"] = patch["status"]
            if "title" in patch:
                it["title"] = patch["title"]
            it["updated_at"] = now_text()
            save_hotlist(items)
            return {"ok": True, "item": it}
    return {"ok": False, "error": "条目不存在"}


def hot_remove(item_id: str) -> dict:
    items = load_hotlist()
    new_items = [it for it in items if it.get("id") != item_id]
    if len(new_items) == len(items):
        return {"ok": False, "error": "条目不存在"}
    save_hotlist(new_items)
    return {"ok": True}


# ============================================================
# 笔记灵感 + AI 素材转化
# ============================================================

# 平台对应的素材模板（约束 AI 输出结构）
PLATFORM_TEMPLATES = {
    "xhs": {
        "name": "小红书笔记",
        "prompt": "请把以下灵感转化为小红书笔记素材。要求：1）吸引人的标题（带 emoji）；2）正文 300-500 字，分段清晰；3）3-5 个话题标签；4）语气亲切、有干货。",
    },
    "douyin": {
        "name": "抖音脚本",
        "prompt": "请把以下灵感转化为抖音短视频脚本。要求：1）3 秒钩子开头；2）正文 200-400 字，节奏紧凑；3）结尾引导互动；4）建议画面/字幕说明。",
    },
    "zhihu": {
        "name": "知乎回答",
        "prompt": "请把以下灵感转化为知乎回答素材。要求：1）观点明确的开头；2）正文 500-800 字，逻辑严密；3）有数据或案例支撑；4）结尾总结升华。",
    },
    "bili": {
        "name": "B站视频文案",
        "prompt": "请把以下灵感转化为 B 站视频文案。要求：1）开场白引入话题；2）正文 400-600 字，信息密度高；3）分段标注画面建议；4）结尾求三连。",
    },
    "wechat": {
        "name": "公众号文章",
        "prompt": "请把以下灵感转化为公众号文章素材。要求：1）有悬念的标题；2）正文 800-1200 字，结构完整；3）小标题分段；4）结尾引导关注。",
    },
}


def load_notes() -> list:
    return read_json(NOTES_PATH, []) or []


def save_notes(items: list) -> None:
    write_json(NOTES_PATH, items)


def load_ai_outputs() -> list:
    return read_json(AI_OUTPUTS_PATH, []) or []


def save_ai_outputs(items: list) -> None:
    write_json(AI_OUTPUTS_PATH, items)


def load_ai_config() -> dict:
    """读取 AI API 配置。配置文件由使用者自行创建。

    config.json 示例：
    {
      "ai_api_url": "https://api.example.com/v1/chat/completions",
      "ai_api_key": "sk-your-api-key-here",
      "ai_model": "gpt-4o-mini",
      "timeout": 30
    }
    """
    return read_json(CONFIG_PATH, {}) or {}


def note_add(payload: dict) -> dict:
    items = load_notes()
    now = now_text()
    content = str(payload.get("content") or "").strip()
    if not content:
        return {"ok": False, "error": "笔记内容不能为空"}
    item = {
        "id": uuid.uuid4().hex[:12],
        "content": content,
        "tags": payload.get("tags") or [],
        "platform": payload.get("platform") or "xhs",
        "status": "draft",  # draft / converted / archived
        "created_at": now,
        "updated_at": now,
    }
    items.insert(0, item)
    save_notes(items)
    return {"ok": True, "item": item}


def note_update(item_id: str, patch: dict) -> dict:
    items = load_notes()
    for it in items:
        if it.get("id") == item_id:
            if "content" in patch:
                it["content"] = str(patch["content"]).strip()
            if "tags" in patch:
                it["tags"] = patch["tags"]
            if "platform" in patch:
                it["platform"] = patch["platform"]
            if "status" in patch:
                if patch["status"] not in {"draft", "converted", "archived"}:
                    return {"ok": False, "error": "非法状态"}
                it["status"] = patch["status"]
            it["updated_at"] = now_text()
            save_notes(items)
            return {"ok": True, "item": it}
    return {"ok": False, "error": "笔记不存在"}


def note_remove(item_id: str) -> dict:
    items = load_notes()
    new_items = [it for it in items if it.get("id") != item_id]
    if len(new_items) == len(items):
        return {"ok": False, "error": "笔记不存在"}
    save_notes(new_items)
    return {"ok": True}


def call_ai_api(prompt: str, config: dict) -> dict:
    """调用配置的 AI API（OpenAI 兼容格式）。

    使用者需在 config.json 中配置 ai_api_url / ai_api_key / ai_model。
    若未配置，返回 not_configured 状态，前端展示提示。
    """
    api_url = config.get("ai_api_url")
    api_key = config.get("ai_api_key")
    model = config.get("ai_model") or "gpt-4o-mini"
    timeout = int(config.get("timeout") or 30)

    if not api_url or not api_key:
        return {
            "ok": False,
            "status": "not_configured",
            "error": "AI API 未配置，请在 config.json 中填写 ai_api_url 和 ai_api_key",
        }

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位资深自媒体内容策划师，擅长把零散灵感转化为可发布的标准素材。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }).encode("utf-8")

    req = Request(api_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # OpenAI 兼容格式
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return {"ok": True, "content": text.strip(), "raw": data}
    except HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")[:500]
        except Exception:
            pass
        return {"ok": False, "error": f"AI API HTTP {e.code}: {err_body or e.reason}"}
    except URLError as e:
        return {"ok": False, "error": f"AI API 网络错误: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"AI API 调用异常: {e}"}


def note_ai_generate(item_id: str, payload: dict) -> dict:
    """把笔记内容通过 AI 转化为标准素材，并存档。"""
    items = load_notes()
    note = next((it for it in items if it.get("id") == item_id), None)
    if not note:
        return {"ok": False, "error": "笔记不存在"}

    platform = payload.get("platform") or note.get("platform") or "xhs"
    template = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES["xhs"])
    custom_prompt = payload.get("prompt") or ""

    prompt = f"{template['prompt']}\n\n灵感内容：\n{note['content']}"
    if custom_prompt:
        prompt += f"\n\n补充要求：{custom_prompt}"

    config = load_ai_config()
    result = call_ai_api(prompt, config)

    # 无论成功失败都留档，便于复查
    outputs = load_ai_outputs()
    output_item = {
        "id": uuid.uuid4().hex[:12],
        "note_id": item_id,
        "original_content": note["content"],
        "platform": platform,
        "template_name": template["name"],
        "prompt_snapshot": prompt,
        "generated_content": result.get("content") or "",
        "status": "generated" if result.get("ok") else "failed",
        "error": result.get("error") or "",
        "ai_model": config.get("ai_model") or "gpt-4o-mini",
        "created_at": now_text(),
    }
    outputs.insert(0, output_item)
    save_ai_outputs(outputs)

    # 更新笔记状态
    if result.get("ok"):
        note["status"] = "converted"
        note["updated_at"] = now_text()
        save_notes(items)

    return {
        "ok": result.get("ok", False),
        "status": result.get("status"),
        "output": output_item,
        "error": result.get("error"),
    }


def generate_report(payload: dict) -> dict:
    """根据前端传入的快照生成 Markdown 报告。"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_type = payload.get("reportType") or "daily"
    filt = payload.get("filter") or {}
    kpi = payload.get("kpi") or {}
    snap = payload.get("snapshot") or {}
    meta = load_meta()

    type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(report_type, "报告")
    platform_label = {
        "all": "全部平台",
        "xhs": "小红书",
        "bili": "B站",
        "zhihu": "知乎",
        "wechat": "公众号",
        "douyin": "抖音",
    }.get(filt.get("platform"), "全部平台")
    time_label = {"7d": "近7天", "30d": "近30天", "month": "本月", "custom": "自定义"}.get(
        filt.get("time"), "本月"
    )

    lines = [
        f"# 自媒体数据{type_label} {today_text()}",
        "",
        f"- 平台范围：{platform_label}",
        f"- 时间范围：{time_label}",
        f"- 数据区间：{snap.get('date_min') or '-'} 至 {snap.get('date_max') or '-'}",
        f"- 数据生成时间：{snap.get('generated_at') or '-'}",
        f"- 服务器同步：{meta.get('sync_status')}",
        f"- 业务校验：{meta.get('business_status')}",
        "",
        "## 核心指标",
        "",
        f"- 总粉丝：{int(number(kpi.get('total_followers'))):,}",
        f"- 净增粉丝：{int(number(kpi.get('net_followers'))):,}",
        f"- 新增内容：{int(number(kpi.get('content_count')))} 篇",
        f"- 总曝光：{int(number(kpi.get('total_exposure'))):,}",
        f"- 净收入：¥{number(kpi.get('net_revenue')):,.2f}",
        "",
        "## 平台新鲜度",
        "",
    ]
    for p in meta.get("platforms") or []:
        lines.append(
            f"- {p['name']}：{p['freshness_status']}，最新 {p.get('latest_daily_date') or '-'}"
        )
        for issue in p.get("freshness_issues") or []:
            lines.append(f"  - {issue}")

    content_top = snap.get("content_top") or []
    if content_top:
        lines.extend(["", "## 内容表现 Top", ""])
        lines.append("| # | 标题 | 平台 | 曝光 | 阅读 | 点赞 | 评论 | 收藏 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for i, c in enumerate(content_top[:10], 1):
            lines.append(
                f"| {i} | {c.get('content_title') or ''} | {c.get('platform_name') or ''} "
                f"| {int(number(c.get('exposure'))):,} | {int(number(c.get('views'))):,} "
                f"| {int(number(c.get('likes'))):,} | {int(number(c.get('comments'))):,} "
                f"| {int(number(c.get('favorites'))):,} |"
            )

    lines.extend(["", "## 结论", ""])
    if meta["status"] == "ready":
        lines.append("所有平台数据新鲜度通过，可按正常报告使用。")
    elif meta["status"] == "partial":
        names = "、".join(p["name"] for p in meta["stale_platforms"])
        lines.append(f"{names} 数据滞后，相关结论需谨慎。")
    else:
        lines.append("同步或业务校验未通过，请检查运行记录后再生成经营判断。")

    report_id = f"{report_type}-{today_text()}-{uuid.uuid4().hex[:6]}"
    report_path = REPORTS_DIR / f"{report_id}.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 记录运行日志
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "schema": "console-report.v1",
        "id": report_id,
        "type": report_type,
        "created_at": now_text(),
        "filter": filt,
        "kpi": kpi,
        "status": meta["status"],
        "report_path": str(report_path),
    }
    write_json(LOGS_DIR / f"console-report-{today_text()}.json", log_entry)

    return {"ok": True, "id": report_id, "path": str(report_path)}


def refresh_dashboard() -> dict:
    """运行拉取/生成、规范化、校验和看板派生的完整刷新链路。"""
    if not REFRESH_PIPELINE.exists():
        return {"ok": False, "error": "未找到 refresh_data.py"}
    try:
        completed = subprocess.run(
            [sys.executable, str(REFRESH_PIPELINE)],
            check=False,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2100,
        )
    except Exception as exc:
        return {"ok": False, "error": f"流水线执行失败：{exc}"}
    if completed.returncode != 0:
        refresh_check = read_json(REFRESH_CHECK_PATH, {}) or {}
        errors = refresh_check.get("errors") or []
        detail = "；".join(str(item) for item in errors if str(item).strip())
        if not detail:
            detail = (completed.stderr or completed.stdout or "未知错误").strip()[-2000:]
        return {"ok": False, "error": detail}
    refresh_check = read_json(REFRESH_CHECK_PATH, {}) or {}
    return {
        "ok": True,
        "status": refresh_check.get("status") or "ready",
        "warnings": refresh_check.get("warnings") or [],
        "data": load_dashboard(),
    }


# ============================================================
# HTTP Handler
# ============================================================
class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "SelfMediaConsole/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- 通用响应 ----------
    def _json(self, payload, status=200):
        # 统一过滤 NaN / Infinity，避免浏览器 JSON.parse 失败
        safe_payload = sanitize_nan(payload)
        body = json.dumps(safe_payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, body: str, status=200, content_type="text/plain; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path: Path):
        if not path.exists() or not path.is_file():
            self._text("Not Found", 404, "text/plain; charset=utf-8")
            return
        ext = path.suffix.lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
        }.get(ext, "application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if ext in {".css", ".js", ".svg", ".woff", ".woff2", ".ttf", ".png", ".jpg", ".ico"}:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8-sig"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):
        # 简化日志，去掉默认的 stderr 噪声
        sys.stderr.write(
            "[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args)
        )

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            self._static(CONSOLE_DIR / "index.html")
            return
        if path.startswith("/api/"):
            self._handle_api_get(path, parse_qs(parsed.query))
            return
        # 兜底静态文件
        rel = path.lstrip("/")
        target = CONSOLE_DIR / rel
        # 防止路径穿越
        try:
            target.resolve().relative_to(CONSOLE_DIR.resolve())
        except ValueError:
            self._text("Forbidden", 403)
            return
        self._static(target)

    def _handle_api_get(self, path: str, qs: dict):
        if path == "/api/dashboard":
            data = load_dashboard()
            self._json({"ok": True, "data": data})
            return
        if path == "/api/meta":
            self._json(load_meta())
            return
        if path == "/api/hotlist":
            self._json(load_hotlist())
            return
        if path == "/api/attribution":
            self._json({"ok": True, "data": load_attribution()})
            return
        if path == "/api/ops-analysis":
            self._json({"ok": True, "data": load_ops_analysis()})
            return
        if path == "/api/hotlist/suggest":
            # 主流媒体"数据分析"相关热门内容推荐（取前 5 条）
            keyword = (qs.get("keyword", ["数据分析"])[0] if qs else "数据分析")
            self._json({"ok": True, "items": suggest_hotlist(keyword)})
            return
        if path == "/api/platform-entries":
            self._json({"ok": True, "items": PLATFORM_ENTRIES})
            return
        if path == "/api/notes":
            self._json({"ok": True, "items": load_notes()})
            return
        if path == "/api/ai-outputs":
            self._json({"ok": True, "items": load_ai_outputs()})
            return
        if path == "/api/ai-config-status":
            cfg = load_ai_config()
            self._json({"ok": True, "configured": bool(cfg.get("ai_api_url") and cfg.get("ai_api_key")),
                        "model": cfg.get("ai_model") or ""})
            return
        if path == "/api/note-templates":
            self._json({"ok": True, "items": [{"platform": k, "name": v["name"]} for k, v in PLATFORM_TEMPLATES.items()]})
            return
        m = re.match(r"^/api/report/([^/]+)$", path)
        if m:
            report_id = m.group(1)
            target = REPORTS_DIR / f"{report_id}.md"
            if not target.exists():
                self._json({"ok": False, "error": "报告不存在"}, 404)
                return
            self._text(target.read_text(encoding="utf-8"), 200, "text/markdown; charset=utf-8")
            return
        self._json({"ok": False, "error": "Not Found"}, 404)

    # ---------- POST ----------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/hot":
            body = self._read_body()
            self._json(hot_add(body))
            return
        if path == "/api/notes":
            body = self._read_body()
            self._json(note_add(body))
            return
        m = re.match(r"^/api/notes/([^/]+)/ai-generate$", path)
        if m:
            body = self._read_body()
            self._json(note_ai_generate(m.group(1), body))
            return
        if path == "/api/refresh":
            self._json(refresh_dashboard())
            return
        if path == "/api/report":
            body = self._read_body()
            self._json(generate_report(body))
            return
        if path == "/api/open-platform":
            # Web 端不可由服务端打开浏览器，仅记录意图。前端应直接 window.open(url)
            body = self._read_body()
            entry = next((e for e in PLATFORM_ENTRIES if e["platform"] == body.get("platform")), None)
            if not entry:
                self._json({"ok": False, "error": "未知平台"})
                return
            self._json({"ok": True, "url": entry["url"], "name": entry["name"]})
            return
        self._json({"ok": False, "error": "Not Found"}, 404)

    # ---------- PUT ----------
    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        m = re.match(r"^/api/hot/([^/]+)$", path)
        if m:
            body = self._read_body()
            self._json(hot_update(m.group(1), body))
            return
        m = re.match(r"^/api/notes/([^/]+)$", path)
        if m:
            body = self._read_body()
            self._json(note_update(m.group(1), body))
            return
        self._json({"ok": False, "error": "Not Found"}, 404)

    # ---------- DELETE ----------
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        m = re.match(r"^/api/hot/([^/]+)$", path)
        if m:
            self._json(hot_remove(m.group(1)))
            return
        m = re.match(r"^/api/notes/([^/]+)$", path)
        if m:
            self._json(note_remove(m.group(1)))
            return
        self._json({"ok": False, "error": "Not Found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_HEAD(self):
        # 把 HEAD 委托给 GET 的元数据获取逻辑（不写 body）
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            target = CONSOLE_DIR / "index.html"
        elif path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            return
        else:
            target = CONSOLE_DIR / path.lstrip("/")
            try:
                target.resolve().relative_to(CONSOLE_DIR.resolve())
            except ValueError:
                self.send_response(403)
                self.end_headers()
                return
        if not target.exists() or not target.is_file():
            self.send_response(404)
            self.end_headers()
            return
        ext = target.suffix.lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()


def main() -> int:
    parser = argparse.ArgumentParser(description="自媒体数据中控台本地 Web 服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    args = parser.parse_args()

    ensure_user_skeleton()
    ensure_dirs()

    # 启动时如果 hotlist 不存在，写入空数组占位
    if not HOTLIST_PATH.exists():
        save_hotlist([])

    # 启动时如果 console 目录为空，给出明显提示
    if not (CONSOLE_DIR / "index.html").exists():
        sys.stderr.write(
            "[warn] console/index.html 未找到。请先放置前端资源到 console/ 目录。\n"
        )

    server = ThreadingHTTPServer((args.host, args.port), ConsoleHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"[console] 自媒体数据中控台已启动：{url}", flush=True)
    print(f"[console] 静态目录：{CONSOLE_DIR}", flush=True)
    print(f"[console] 数据目录：{DASHBOARD_DIR}", flush=True)
    print(f"[console] 按 Ctrl+C 退出。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[console] 已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
