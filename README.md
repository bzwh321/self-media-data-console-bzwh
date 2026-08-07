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

```powershell
python scripts\console_server.py
```

打开 `http://127.0.0.1:8765/`。

生成经营分析和日报记录：

```powershell
python scripts\daily_pipeline.py --stage report
python scripts\daily_pipeline.py --stage screenshot
```

如需截图能力，请安装依赖：

```powershell
npm install
```

## 目录

```text
console/                 前端看板、图表、皮肤资源
scripts/                 本地服务、日报流水线、截图脚本
sample-data/             可公开的虚拟数据
runtime-data/console-state/  本地状态示例
docs/                    产品、架构、皮肤、准确性和发布说明
.trae/skills/            项目 Skill
workflows/               日常流水线定义
```

## 数据安全

公开版不包含真实登录态、真实飞书 ID、真实账号数据、服务器路径、运行日志或截图缓存。发布前请查看 `PUBLICATION_CHECKLIST.md`。
