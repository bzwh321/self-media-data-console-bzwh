# 自媒体数据中控台

一个可在 Windows 桌面启动的本地自媒体经营工作台。下载后先用完整模拟数据查看成品，再按同一套目录规范接入自己的小红书、抖音、知乎、B站和公众号数据。

项目把 `data/demo/` 和 `data/user/` 完全隔离，不包含知识星球数据，也不会把个人数据自动提交到 Git。

## 皮肤效果

### 翡翠矩阵

![翡翠矩阵皮肤下的自媒体数据中控台桌面看板](docs/screenshots/skin-emerald-matrix.webp)

### 工业信标

![工业信标皮肤下的自媒体数据中控台桌面看板](docs/screenshots/skin-industrial-beacon.webp)

皮肤可以通过页面右上角的主题按钮随时切换，选择结果会保存在当前浏览器。

## 下载后如何使用

### 方式一：下载 ZIP

1. 打开本仓库页面，点击 `Code` → `Download ZIP`。
2. 解压 ZIP，不要直接在压缩包预览窗口中运行。
3. 确认电脑已安装 Python 3.10 或更高版本，并在安装时勾选 `Add Python to PATH`。
4. 双击项目根目录的 `open_console.bat`。

启动脚本会自动完成以下工作：

1. 检查 Python 版本。
2. 检查模拟数据，文件不完整时自动重新生成。
3. 创建受 Git 保护的 `data/user/` 个人数据目录。
4. 启动本地服务并打开 `http://127.0.0.1:8765/`。

第一次打开时，页面顶部应显示：

```text
模拟数据 · 当前展示开箱示例 · data/demo
```

这表示项目已经成功运行。基础看板只使用 Python 标准库，不需要先运行 `npm install`，也不需要配置 AI、飞书或其他外部服务。

### 方式二：Git 克隆

```powershell
git clone https://github.com/bzwh321/self-media-data-console-bzwh.git
cd self-media-data-console-bzwh
python scripts\launch_console.py
```

如果端口 `8765` 被其他程序占用，启动器会停止并给出提示，不会替换或关闭其他进程。

## 使用个人数据前要补充什么

完整的逐项勾选文件见 [`PERSONAL_SETUP_CHECKLIST.md`](PERSONAL_SETUP_CHECKLIST.md)。至少需要补充下面三类内容。

### 1. 本地配置路径

把根目录的 `config.example.json` 复制为 `config.json`：

```powershell
Copy-Item config.example.json config.json
```

`config.json` 已被 `.gitignore` 排除，只在本机保存。把其中的数据模式改为：

```json
{
  "data": {
    "mode": "user",
    "root": ""
  }
}
```

`root` 留空时固定读取 `data/user/`；只有明确要把数据放在项目外部时，才填写你自己电脑上的绝对路径。

### 2. 个人信息

在 `config.json` 的 `profile` 中填写：

| 字段 | 是否必填 | 填写内容 |
| --- | --- | --- |
| `display_name` | 必填 | 品牌名、公开昵称或自定义别名，不要求真实姓名 |
| `active_platforms` | 必填 | 只保留实际使用的平台代码 |
| `timezone` | 可选 | 默认 `Asia/Shanghai` |
| `monthly_goals.new_fans` | 可选 | 月度净增粉丝目标 |
| `monthly_goals.revenue` | 可选 | 月度收入目标 |

平台代码对应关系：

| 平台 | 代码 |
| --- | --- |
| 小红书 | `xhs` |
| 抖音 | `douyin` |
| 知乎 | `zhihu` |
| B站 | `bili` |
| 公众号 | `wechat` |

`ai_api_url`、`ai_api_key`、`ai_model` 和 `lark.recipients` 都是可选项。只看本地中控台时保持空白即可。

### 3. 个人数据路径

只需要为 `active_platforms` 中启用的平台补数据。`<账号别名>` 可以使用公开昵称或自定义名称。

| 平台 | 建议放置路径 | 主要数据 |
| --- | --- | --- |
| 小红书 | `data/user/小红书内容数据/<账号别名>/raw/` | 粉丝增长、账号概览、内容分析 |
| 抖音 | `data/user/抖音数据/<账号别名>/raw/` | 运营数据、作品列表、内容分析 |
| 知乎 | `data/user/知乎数据/<账号别名>/raw/` | 关注者数据、内容分析 |
| B站 | `data/user/B站数据/<账号别名>/raw/` | 粉丝数据、播放与互动数据 |
| 公众号 | `data/user/公众号数据/<账号别名>/` | 用户统计、内容统计、文章统计 |

可选经营数据放在：

```text
data/user/小红书电商数据/<店铺别名>/raw/datacenter_overview/YYYY-MM/
data/user/小红书推广数据/<账号别名>/
```

原始导出建议继续按 `{数据类型}/YYYY-MM/` 分层。完整文件类型、后台导出入口和字段映射见：

- [`data/README.md`](data/README.md)：数据目录总规范
- [`data/user/README.md`](data/user/README.md)：个人数据放置示例
- [`docs/数据采集指南.md`](docs/数据采集指南.md)：五个平台的导出步骤
- [`docs/自媒体看板字段映射对照表.md`](docs/自媒体看板字段映射对照表.md)：字段映射与口径

## 生成个人看板

完成配置和文件放置后，在项目根目录运行：

```powershell
pip install -r requirements.txt
python scripts\normalize-self-media-dashboard.py
python scripts\check-self-media-dashboard-contract.py --console-root .
python scripts\build_compact_dashboard.py
python scripts\launch_console.py
```

通过后，页面顶部应显示“个人数据”和 `data/user`。如果标准产物不完整，启动器会列出缺失文件并停止，不会回退到模拟数据。

## 隐私边界

- 不要把密码、Cookie、验证码、浏览器 Profile、平台登录态、token 或 SSH 密钥放入仓库。
- `config.json` 和 `data/user/` 中的业务文件默认被 Git 忽略。
- `data/user/dashboard-normalized/` 由 Python 脚本生成，不要手工修改。
- 发布前运行 `python scripts\check_public_safety.py`。

项目 Agent 首次接入时只应询问展示别名、启用平台、账号目录名和平台导出文件；不得索取上述敏感凭据。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `python scripts\generate_demo_data.py` | 重新生成完整模拟数据 |
| `python scripts\launch_console.py` | 准备数据、启动服务并打开浏览器 |
| `python scripts\daily_pipeline.py --stage report` | 生成本地日报 |
| `python tests\test_portable_setup.py` | 检查开箱数据与目录隔离 |
| `python scripts\check_public_safety.py` | 检查公开文件中的敏感信息和本地路径 |

完整脚本说明见 [`scripts/README.md`](scripts/README.md)。截图能力需要先运行 `npm install`，其他基础功能不需要 Node.js。

## 贡献与许可

贡献说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，发布前检查见 [`PUBLICATION_CHECKLIST.md`](PUBLICATION_CHECKLIST.md)。

本项目使用 [MIT License](LICENSE)。
