# GitHub 发布说明

当前公开版项目已经初始化为本地 Git 仓库，默认分支为 `main`。

建议仓库名：

```text
self-media-data-console-bzwh
```

## 方式一：网页创建仓库后推送

1. 在 GitHub 创建一个公开仓库，名称使用 `self-media-data-console-bzwh`。
2. 不要勾选自动生成 README、License 或 `.gitignore`，本项目已经包含这些文件。
3. 在本项目目录执行：

```powershell
git remote add origin https://github.com/<你的用户名>/self-media-data-console-bzwh.git
git push -u origin main
```

如果你使用 SSH：

```powershell
git remote add origin git@github.com:<你的用户名>/self-media-data-console-bzwh.git
git push -u origin main
```

## 方式二：安装 GitHub CLI 后创建并推送

安装并登录 GitHub CLI 后，在本项目目录执行：

```powershell
gh auth login
gh repo create self-media-data-console-bzwh --public --source . --remote origin --push
```

## 发布前复查

执行：

```powershell
git status --short
git log --oneline -1
```

确认没有 `config.json`、`runtime-data/logs`、`runtime-data/reports`、`runtime-data/screenshots`、`node_modules` 等文件进入提交。
