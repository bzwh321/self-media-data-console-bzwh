# 自媒体数据中控台

一个可在 Windows 桌面直接启动的本地自媒体经营工作台。项目默认提供完全模拟的数据成品；用户接入个人数据后，继续使用同一套 Python 规范化、校验、看板和日报链路。

当前支持小红书、抖音、知乎、B站和公众号。数据层不包含知识星球。

## 第一次启动

Windows 用户双击项目根目录的 `open_console.bat`。脚本会：

1. 检查 Python 3.10+。
2. 检查完整模拟数据包，缺失时自动重新生成。
3. 创建受 Git 保护的 `data/user/` 个人数据目录骨架。
4. 启动本地服务并打开 `http://127.0.0.1:8765/`。

也可以在终端运行：

```powershell
python scripts\launch_console.py
```

基础看板只依赖 Python 标准库，不需要先运行 `npm install` 或配置外部服务。

## 数据模式

```text
data/demo/     可公开提交的模拟数据，下载后默认读取
data/user/     个人业务数据，只在本机保存，默认被 Git 忽略
```

页面顶部会持续显示当前数据模式和数据路径。两套数据不会静默混合。

详细目录规则见 `data/README.md`，个人文件放置示例见 `data/user/README.md`。

## 接入个人数据

1. 将 `config.example.json` 复制为 `config.json`。
2. 把 `data.mode` 改为 `user`；留空的 `data.root` 会自动使用 `data/user`。
3. 填写 `profile.display_name`、`profile.active_platforms` 和可选月度目标。
4. 按 `docs/数据采集指南.md` 导出文件并放入 `data/user/` 的平台目录。
5. 安装数据处理依赖并生成个人标准数据：

```powershell
pip install -r requirements.txt
python scripts\normalize-self-media-dashboard.py
python scripts\check-self-media-dashboard-contract.py --console-root .
python scripts\build_compact_dashboard.py
python scripts\launch_console.py
```

个人产物缺失时，启动器会明确列出缺失文件并停止，不会回退混用模拟数据。

## 项目 Agent 会提醒什么

- 必填：展示名称或品牌别名、启用平台、账号目录名、平台导出文件。
- 可选：时区、月度目标、AI 接口和飞书接收人。
- 禁止提供：密码、Cookie、验证码、浏览器 Profile、token、SSH 密钥和平台登录态。

## 数据处理脚本

| 脚本 | 用途 | 依赖 |
| --- | --- | --- |
| `generate_demo_data.py` | 生成可公开的完整模拟数据包 | 标准库 |
| `normalize-self-media-dashboard.py` | 平台原始数据转标准看板数据 | pandas、openpyxl |
| `check-self-media-dashboard-contract.py` | 数据与前端消费契约校验 | 标准库 |
| `build_compact_dashboard.py` | 派生前端紧凑数据 | 标准库 |
| `console_server.py` | 本地 Web 服务和 JSON API | 标准库 |
| `launch_console.py` | 桌面首次启动和浏览器拉起 | 标准库 |
| `daily_pipeline.py` | 日报、截图和经营分析编排 | 基础阶段标准库 |
| `build_attribution.py` | 内容涨粉归因 | openpyxl |
| `check_public_safety.py` | 发布前隐私与路径检查 | 标准库、Git |

详细说明见 `scripts/README.md`。

## 可选能力

- 截图：`npm install` 后运行 `python scripts\daily_pipeline.py --stage screenshot`。
- AI 文案：只在本地 `config.json` 中配置接口。
- 飞书推送：使用已授权工具或本地配置，不在仓库保存 token。

## 发布前检查

```powershell
python tests\test_portable_setup.py
python scripts\check_public_safety.py
```

同时检查 `PUBLICATION_CHECKLIST.md`。项目不会提交 `config.json`、个人业务数据、运行日志、报告、截图缓存或登录状态。

## 开源许可

MIT，见 `LICENSE`。
