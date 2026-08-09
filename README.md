# 自媒体数据中控台 Demo

一个可公开分享的本地自媒体经营数据中控台模板。它保留了看板样式、皮肤系统、日报生成、截图、热榜素材、经营分析和 Trae Skill 工作流，但所有数据均为虚拟示例数据。

## 特性

- 本地 HTML 看板：KPI、趋势、平台分布、经营损益、内容 Top、热榜素材和笔记灵感。
- 虚拟数据开箱可跑：默认读取 `sample-data/self-media/dashboard-normalized`。
- 可替换数据源：设置环境变量 `SELF_MEDIA_DATA_ROOT` 指向你的数据目录。
- 可选飞书推送：只使用 `config.json` 中的收件人配置，不保存 token。
- 皮肤系统：保留默认、Portal、Endfield、Nebula 等样式资源和开发规范。
- Trae Skill：内置工作流 Skill，便于串联图表看板、插件、皮肤、热榜和发布检查。

## 快速开始

### 1. 启动看板

```powershell
python scripts\console_server.py
```

打开 `http://127.0.0.1:8765/`，即可看到包含虚拟数据的完整看板。

### 2. 安装依赖（可选）

截图功能需要 Node.js + Puppeteer：

```powershell
npm install
```

归因分析需要 openpyxl：

```powershell
pip install -r requirements.txt
```

### 3. 生成日报和截图

```powershell
python scripts\daily_pipeline.py --stage report
python scripts\daily_pipeline.py --stage screenshot
```

### 4. 桌面一键启动

```powershell
python scripts\launch_console.py
```

自动探测端口、后台启动服务并打开浏览器，适合做成桌面快捷方式。

## 目录

```text
console/                 前端看板、图表、皮肤资源
scripts/                 本地服务、日报流水线、截图脚本（详见 scripts/README.md）
sample-data/             可公开的虚拟数据（开箱即用）
runtime-data/console-state/  本地状态示例（归因、经营分析预生成）
docs/                    产品、架构、采集指南、字段映射、皮肤、发布说明
.trae/skills/            项目 Skill
workflows/               日常流水线定义
requirements.txt         Python 依赖（pandas + openpyxl）
```

## 脚本说明

| 脚本 | 用途 | 依赖 |
|------|------|------|
| `normalize-self-media-dashboard.py` | **核心**：各平台原始数据 → 标准看板数据 | pandas, openpyxl |
| `check-self-media-dashboard-contract.py` | 数据契约校验 | 标准库 |
| `build_compact_dashboard.py` | 派生看板紧凑数据 | 标准库 |
| `console_server.py` | 本地 Web 服务 + JSON API | 标准库 |
| `launch_console.py` | 桌面一键启动器 | 标准库 |
| `daily_pipeline.py` | 日报生成 + 截图编排 | 标准库 |
| `build_attribution.py` | 粉丝增长归因分析 | openpyxl |
| `capture_console_screenshot.js` | 看板页面截图 | puppeteer |

详见 `scripts/README.md`。

## 使用自己的数据

公开版默认使用 `sample-data/` 虚拟数据，开箱即用。如要接入自己的真实数据：

1. 按 `docs/数据采集指南.md` 从各平台创作者后台导出数据
2. 按指南中的目录约定存放原始文件
3. 安装依赖：`pip install -r requirements.txt`
4. 运行归一化：`python scripts/normalize-self-media-dashboard.py`
5. 运行校验：`python scripts/check-self-media-dashboard-contract.py`
6. 派生看板数据：`python scripts/build_compact_dashboard.py`
7. 启动看板：`python scripts/console_server.py`

字段映射规则见 `docs/自媒体看板字段映射对照表.md`，数据目录结构见 `docs/数据目录结构说明.md`。

## 数据安全

公开版不包含真实登录态、真实飞书 ID、真实账号数据、服务器路径、运行日志或截图缓存。发布前请查看 `PUBLICATION_CHECKLIST.md`。
