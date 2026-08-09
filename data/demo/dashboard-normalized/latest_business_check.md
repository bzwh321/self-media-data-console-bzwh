# Self-media Sync Business Checklist

- status: ready
- checked_at: 2026-08-09T21:21:02
- audit_period: 2026-08-01 to 2026-08-09

## Expected KPI Values

| KPI | Value |
| --- | ---: |
| total_followers | 43,035 |
| new_fans | 280 |
| revenue | 1,242.66 |
| posts | 14 |

## Checklist

| Check | Status | Evidence |
| --- | --- | --- |
| expected_platforms_present | passed | `{"missing_platforms": [], "actual_platforms": ["bili", "douyin", "wechat", "xhs", "zhihu"]}` |
| server_sync_files_selected | skipped | `{"demo_selected": 5, "server_sync_selected": 0}` |
| audit_period_has_daily_rows | passed | `{"period_start": "2026-08-01", "period_end": "2026-08-09", "row_count": 9}` |
| xhs_revenue_snapshot_available | passed | `{"platform": "xhs", "new_fans": 37, "revenue": 907.73, "posts": 3}` |
| range_kpi_not_platform_summary | passed | `{"expected_range_new_fans": 280, "platform_summary_new_fans": 280, "expected_range_revenue": 1242.66, "platform_summary_revenue": 1242.66, "note": "selected-range KPI must use expected_range_* values, not platform_summary_* values"}` |

## Renderer Contract

- status: passed
