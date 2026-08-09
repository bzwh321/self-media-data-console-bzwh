# 公开发布检查清单

- 不提交 `config.json`。
- 不提交 `data/user/` 下的个人业务文件。
- 不提交 `runtime-data/logs`、`runtime-data/reports`、`runtime-data/screenshots`。
- 不提交真实平台后台导出、账号 Cookie、浏览器 Profile、token、open_id、chat_id。
- 不提交 `node_modules`、`__pycache__`、临时调试脚本。
- 使用 `data/demo` 的模拟数据验证看板能正常打开。
- 运行 `python scripts/check_public_safety.py`，确认无本地路径、邮箱、密钥和自定义敏感词。
- 确认模拟数据的 `source_file` 全部为 `data/demo/...` 相对路径。
- 确认 `data/` 中不存在知识星球数据目录。
- 如启用飞书、AI API 或外部采集，把真实配置放在本地 `config.json` 或环境变量中。
