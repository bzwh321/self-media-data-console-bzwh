# 脚本说明

所有 Python 脚本兼容 Python 3.8+，除 `build_attribution.py` 外均仅使用标准库。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SELF_MEDIA_DATA_ROOT` | `<项目根>/sample-data/self-media` | 数据根目录，指向你的 `dashboard-normalized` 所在的上级目录 |

设置为真实数据目录即可切换数据源：

```powershell
$env:SELF_MEDIA_DATA_ROOT = "D:\your-data\self-media"
```

## 脚本清单

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

### daily_pipeline.py — 每日流水线

读取 dashboard 数据和校验结果，生成日报 Markdown、运行 JSON 记录。

```powershell
python scripts/daily_pipeline.py --stage report
python scripts/daily_pipeline.py --stage screenshot
```

- `--stage report`：生成 `runtime-data/reports/` 下的 Markdown 日报和 JSON 记录
- `--stage screenshot`：调用 `capture_console_screenshot.js` 截取看板页面

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
- 输出：`runtime-data/console-state/attribution.json`
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
真实数据 → build_compact_dashboard.py → compact_dashboard_data.json
                                           ↓
                                     console_server.py → 前端看板
                                           ↓
                                     daily_pipeline.py → 日报 + 截图
```

公开版已预置 `sample-data/` 虚拟数据和 `runtime-data/console-state/` 预生成结果，下载后直接运行 `console_server.py` 即可看到完整看板。
