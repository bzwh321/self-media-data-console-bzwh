---
name: "self-media-console-workflow"
description: "Orchestrates self-media dashboards, skins, hotlist collection, reports, and Trae plugins. Invoke for this console's workflow changes."
---

# Self Media Console Workflow

Use this skill when working on the self-media data console public template: dashboard charts, data contracts, skin management, hotlist material collection, report screenshots, Feishu/Lark delivery, or publishing checks.

## Principles

- Use virtual or anonymized data by default.
- Keep real tokens, cookies, browser profiles, `open_id`, `chat_id`, and local paths outside the repository.
- Prefer deterministic rules for daily report conclusions.
- Make chart and dashboard changes in the smallest layer that owns the behavior.
- Preserve traceability: every metric should map back to `data/demo` or the configured personal data root.

## Workflow

1. Data contract
   - Read `data/demo/dashboard-normalized/compact_dashboard_data.json` by default.
   - Before personal-data work, tell the user to fill `config.json` profile fields and place exports under `data/user/`.
   - Keep platform fields stable: `platform`, `platform_name`, `month_net_followers`, `month_net_revenue`, `month_content_count`, `month_views`.
   - Add new fields to sample data before wiring UI.

2. Dashboard and charts
   - Edit `console/index.html` for structure.
   - Edit `console/app.js` for data mapping and rendering orchestration.
   - Edit `console/charts.js` for reusable chart primitives.
   - Edit `console/styles.css` for layout, spacing, colors, and skins.

3. Skin management
   - Follow `docs/皮肤系统开发规范.md`.
   - Keep skin assets under `console/assets/skins`.
   - Do not hardcode business data inside a skin.

4. Hotlist collection
   - Use `runtime-data/<mode>/console-state/hotlist.json` for mode-isolated local saved items.
   - Use `data/demo/hotlist/normalized/hotlist_latest.json` as the public demo source.
   - Real platform collection must live outside the public repo or be documented as an optional adapter.

5. Trae plugins
   - Use data-processing for CSV/Excel cleanup and demo data transformation.
   - Use business-ops-analysis for deterministic business review patterns, then save outputs as JSON.
   - Use Lark/Feishu skills only after authorization, and never commit credentials.
   - Use web data visualization skills when redesigning charts, accessibility, or dashboard layout.

6. Reports and screenshots
   - `python scripts/daily_pipeline.py --stage report` generates deterministic report records.
   - `python scripts/daily_pipeline.py --stage screenshot` captures the local dashboard.
   - Screenshots and reports are runtime outputs and must not be committed.

7. Publishing
   - Run `PUBLICATION_CHECKLIST.md`.
   - Search for `ou_`, `oc_`, `token`, `cookie`, `D:\`, `C:\`, `Administrator`, and real account names.
   - Confirm the repo starts from virtual data without external services.

## Common requests

- "新增一个看板模块": update sample data, HTML structure, app renderer, styles, then screenshot.
- "换一个皮肤": add variables/assets in CSS, document in skin guide, verify default fallback.
- "接入真实飞书": keep `config.json` local, use `lark.recipients`, do not commit the file.
- "准备公开发布": run sensitive scan, check `.gitignore`, verify sample data.
