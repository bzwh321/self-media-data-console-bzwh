# 个人信息与数据接入清单

这份清单用于把模拟数据模式切换为个人数据模式。所有路径均相对于项目根目录；只勾选你实际启用的平台。

## 一、运行环境

- [ ] 已将仓库 ZIP 完整解压，或使用 Git 克隆仓库。
- [ ] 已安装 Python 3.10 或更高版本。
- [ ] 在项目根目录运行 `python --version` 能看到版本号。
- [ ] 双击 `open_console.bat` 后能看到模拟数据成品。

## 二、本地配置

- [ ] 已将 `config.example.json` 复制为 `config.json`。
- [ ] 已将 `data.mode` 改为 `user`。
- [ ] 数据放在仓库内时，`data.root` 保持为空，自动使用 `data/user/`。
- [ ] 数据放在仓库外时，`data.root` 已填写本人有权读取的绝对路径。
- [ ] `profile.display_name` 已改为品牌名、公开昵称或自定义别名。
- [ ] `profile.active_platforms` 只保留本人实际使用的平台代码。
- [ ] 已按需填写时区和月度目标；不需要时保留默认值。
- [ ] 不使用 AI 或飞书时，相关配置保持空白。

## 三、账号目录

- [ ] 每个启用平台都建立了自己的账号别名目录。
- [ ] 目录名不包含手机号、身份证号、邮箱或其他不希望公开的信息。
- [ ] 原始文件按 `{数据类型}/YYYY-MM/` 分层保存。
- [ ] 没有手工修改 `dashboard-normalized/` 中的生成文件。

## 四、平台数据

### 小红书：`xhs`

- [ ] 已创建 `data/user/小红书内容数据/<账号别名>/raw/`。
- [ ] 已放入粉丝增长或粉丝快照数据。
- [ ] 已放入账号概览和内容分析数据。
- [ ] 如有店铺数据，已放入 `data/user/小红书电商数据/<店铺别名>/raw/datacenter_overview/YYYY-MM/`。
- [ ] 如有推广数据，已放入 `data/user/小红书推广数据/<账号别名>/`。

### 抖音：`douyin`

- [ ] 已创建 `data/user/抖音数据/<账号别名>/raw/`。
- [ ] 已放入运营数据。
- [ ] 已放入作品列表或内容分析数据。

### 知乎：`zhihu`

- [ ] 已创建 `data/user/知乎数据/<账号别名>/raw/`。
- [ ] 已放入关注者数据。
- [ ] 已放入内容分析数据。

### B站：`bili`

- [ ] 已创建 `data/user/B站数据/<账号别名>/raw/`。
- [ ] 已放入粉丝数据。
- [ ] 已放入播放、互动或内容数据。
- [ ] 如需收入统计，已放入可用的商品销售数据。

### 公众号：`wechat`

- [ ] 已创建 `data/user/公众号数据/<账号别名>/`。
- [ ] 已放入用户统计文件。
- [ ] 已放入内容统计或文章统计文件。

## 五、生成与校验

- [ ] 已运行 `pip install -r requirements.txt`。
- [ ] 已运行 `python scripts\normalize-self-media-dashboard.py`。
- [ ] 已运行 `python scripts\check-self-media-dashboard-contract.py --console-root .`。
- [ ] 契约检查结果为 `ready`，或已根据错误信息补齐数据。
- [ ] 已运行 `python scripts\build_compact_dashboard.py`。
- [ ] 已运行 `python scripts\launch_console.py`。
- [ ] 页面顶部显示“个人数据”和 `data/user`，没有显示“模拟数据”。

## 六、隐私检查

- [ ] 仓库中没有密码、Cookie、验证码、浏览器 Profile、平台登录态、token 或 SSH 密钥。
- [ ] `config.json` 没有被加入 Git。
- [ ] `data/user/` 中的个人业务文件没有被加入 Git。
- [ ] 已运行 `python scripts\check_public_safety.py` 且结果为 `ok: true`。

更详细的导出说明见 [`docs/数据采集指南.md`](docs/数据采集指南.md)，字段口径见 [`docs/自媒体看板字段映射对照表.md`](docs/自媒体看板字段映射对照表.md)。
