# 脚本说明

所有 Python 脚本兼容 Python 3.10+。基础启动、模拟数据和校验链路仅使用标准库；个人 Excel 数据处理使用 pandas/openpyxl。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SELF_MEDIA_DATA_ROOT` | 空 | 可选外部数据根；未设置时读取 `config.json`，最终默认 `data/demo` |
| `SELF_MEDIA_DATA_MODE` | 空 | 与外部数据根配合，可设为 `demo` 或 `user` |

设置为真实数据目录即可切换数据源：

```powershell
$env:SELF_MEDIA_DATA_ROOT = "<你的授权数据目录>"
$env:SELF_MEDIA_DATA_MODE = "user"
```

## 脚本清单

### generate_demo_data.py — 完整模拟数据

从字段契约生成五个平台的模拟源文件和完整标准产物，不读取真实数据：

```powershell
python scripts/generate_demo_data.py
```

### console_server.py — 本地 Web 服务

启动 HTTP 服务提供看板页面和 JSON API。

```powershell
python scripts/console_server.py
# 自定义端口
python scripts/console_server.py --port 9000
```

- 静态文件：`console/` 目录
- API：`/api/dashboard`、`/api/meta`、`/api/hotlist`、`/api/refresh`、`/api/report`
- 默认地址：`http://127.0.0.1:8765/`

### launch_console.py — 桌面启动器

探测端口是否已运行，若否则后台启动 `console_server.py` 并打开浏览器。适合做成桌面快捷方式。

```powershell
python scripts/launch_console.py
```

### refresh_data.py — 刷新总入口

页面“刷新”按钮调用的完整链路。模拟模式重建当天模拟数据；个人模式依次执行服务器拉取、规范化、契约校验、紧凑看板、归因分析和日报生成。

```powershell
python scripts/refresh_data.py
```

任一步返回失败码时停止后续步骤，并把原因写入 `{DATA_ROOT}/dashboard-normalized/latest_refresh_check.json`。

### sync_server_data.py — 服务器数据拉取

读取被 Git 忽略的 `config.json` 中的 `server_sync` 配置，通过本机 SSH 拉取服务器最近变更的文件并合并到个人数据区。首次同步使用较长时间窗口，日常刷新默认只同步最近 3 天；仓库不保存服务器地址、密钥或个人远端路径。

```powershell
python scripts/sync_server_data.py --dry-run
python scripts/sync_server_data.py
```

### daily_pipeline.py — 每日流水线

读取 dashboard 数据和校验结果，生成日报 Markdown、运行 JSON 记录。

```powershell
python scripts/daily_pipeline.py --stage report
python scripts/daily_pipeline.py --stage screenshot
```

- `--stage report`：生成 `runtime-data/<mode>/reports/` 下的 Markdown 日报和 JSON 记录
- `--stage screenshot`：调用 `capture_console_screenshot.js` 截取看板页面

### normalize-self-media-dashboard.py — 数据归一化（核心）

从各平台原始数据（CSV/XLSX/JSON）归一化为统一的标准看板数据。这是数据链路的核心脚本。

```powershell
pip install pandas openpyxl
python scripts/normalize-self-media-dashboard.py
```

- 输入：`{DATA_ROOT}/` 下各平台目录（B站数据/、抖音数据/、小红书内容数据/ 等）
- 输出：`{DATA_ROOT}/dashboard-normalized/` 下的 7 个标准文件
- 依赖：`pandas`、`openpyxl`
- 详细采集方法和目录约定见 `docs/数据采集指南.md`
- 字段映射规则见 `docs/自媒体看板字段映射对照表.md`

### check-self-media-dashboard-contract.py — 数据契约校验

校验归一化后数据的完整性和一致性（总粉丝=各平台之和、粉丝变化率、内容标题、收入非负等）。

```powershell
python scripts/check-self-media-dashboard-contract.py --console-root .
```

- 输入：`{DATA_ROOT}/dashboard-normalized/self_media_dashboard.json`
- 输出：`{DATA_ROOT}/dashboard-normalized/latest_business_check.json`
- 依赖：标准库

### build_compact_dashboard.py — 看板数据派生

从 `self_media_dashboard.json` 派生 `compact_dashboard_data.json`，修复 net_revenue、interact_total、content_items_top 字段。

```powershell
python scripts/build_compact_dashboard.py
```

- 输入：`{DATA_ROOT}/dashboard-normalized/self_media_dashboard.json`
- 输出：`{DATA_ROOT}/dashboard-normalized/compact_dashboard_data.json`

### build_attribution.py — 粉丝增长归因

从内容明细数据构建归因分析，输出 Top N 涨粉贡献、按体裁/平台聚合。

```powershell
pip install openpyxl
python scripts/build_attribution.py
```

- 输入：`{DATA_ROOT}/dashboard-normalized/self_media_content_detail.csv`、抖音月度 XLSX
- 输出：`runtime-data/<mode>/console-state/attribution.json`
- 依赖：`openpyxl`（见 `requirements.txt`）

### capture_console_screenshot.js — 看板截图

使用 Puppeteer 截取本地中控台页面，输出 16:9 PNG。

```powershell
npm install
node scripts/capture_console_screenshot.js http://127.0.0.1:8765/ output.png
```

- 依赖：`puppeteer`（见 `package.json`）

## 数据处理流程

```
已配置服务器 → sync_server_data.py
                         ↓
各平台创作者后台导出 → 按目录约定存放 → normalize-self-media-dashboard.py
                                              ↓
                                    dashboard-normalized/ (7个标准文件)
                                              ↓
                              check-self-media-dashboard-contract.py (校验)
                                              ↓
                              build_compact_dashboard.py → compact_dashboard_data.json
                                              ↓
                                        console_server.py → 前端看板
                                              ↓
                                        daily_pipeline.py → 日报 + 截图
```

公开版已预置 `data/demo/` 模拟数据和 `runtime-data/demo/console-state/` 预生成结果，下载后直接运行 `launch_console.py` 即可看到完整看板。

如要使用自己的真实数据，请按 `docs/数据采集指南.md` 放入 `data/user/`，在 `config.json` 选择 user 模式，然后依次运行 normalize → contract check → build_compact。
