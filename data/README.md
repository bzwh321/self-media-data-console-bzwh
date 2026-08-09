# 数据目录

本目录是中控台唯一的数据入口。默认读取 `demo/` 的模拟数据；个人数据只存放在 `user/`，两者不会混合。

## 目录结构

```text
data/
├── demo/                         可公开提交的模拟数据
│   ├── B站数据/
│   ├── 抖音数据/
│   ├── 知乎数据/
│   ├── 公众号数据/
│   ├── 小红书内容数据/
│   ├── 小红书电商数据/
│   ├── 小红书推广数据/
│   ├── hotlist/normalized/
│   └── dashboard-normalized/
└── user/                         个人数据区，业务文件默认被 Git 忽略
    ├── 各平台数据目录/
    ├── hotlist/normalized/
    └── dashboard-normalized/
```

数据层不包含知识星球数据。

## 存储规则

1. 平台数据按 `{平台数据}/{账号名}/raw/{数据类型}/YYYY-MM/` 保存原始导出。
2. 可复用的月度文件按 `{平台数据}/{账号名}/monthly/{数据类型}/` 保存。
3. 存在同类远程数据时，可放入平台目录下的 `服务器同步/`；融合时按去掉该路径段后的逻辑路径选择最新版。
4. `monthly/` 优先于 `raw/`；缺少月度文件时才回退读取原始文件。
5. `dashboard-normalized/` 是 Python 生成的标准产物，不要手工修改。
6. 标准表保留相对 `source_file` 和 `source_mtime`，用于数据追溯。

## 模拟数据

`demo/` 内的账号、标题、指标和路径均由 `scripts/generate_demo_data.py` 从零生成，不从真实数据抽样或遮盖。重新生成：

```powershell
python scripts\generate_demo_data.py
```

## 使用个人数据

1. 阅读 `data/user/README.md`，将平台导出放入对应目录。
2. 将 `config.example.json` 复制为 `config.json`。
3. 设置 `data.mode` 为 `user`；`data.root` 留空即可使用 `data/user`。再填写展示名称、启用平台和可选经营目标。
4. 安装数据处理依赖：`pip install -r requirements.txt`。
5. 运行：

```powershell
python scripts\normalize-self-media-dashboard.py
python scripts\check-self-media-dashboard-contract.py --console-root .
python scripts\build_compact_dashboard.py
python scripts\launch_console.py
```

切换失败时不会回退混合模拟数据；请根据脚本提示补齐缺失文件。

## 隐私边界

- 不要把密码、Cookie、验证码、浏览器 Profile、token、SSH 密钥放入本目录。
- `data/user/` 中除说明文件和空目录标记外的内容均不提交 Git。
- 发布前运行 `python scripts/check_public_safety.py`。
