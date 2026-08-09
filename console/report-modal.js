/* ============================================================
 * report-modal.js - 报告生成弹层
 *
 * 用户点击"生成报告"后弹出确认层，确认当前筛选范围、报告类型，再生成报告。
 * 报告由本地服务生成，按数据模式落盘到 runtime-data/<mode>/reports。
 * 数据快照由渲染层传入，避免主进程与渲染层数据口径不一致。
 * ============================================================ */
(function () {
  'use strict';

  var bridge = window.selfMediaBridge;

  var reportModal = document.getElementById('reportModal');
  var reportType = 'daily';

  document.getElementById('btnReport').addEventListener('click', openReportModal);
  document.getElementById('reportClose').addEventListener('click', closeReportModal);
  document.getElementById('reportCancel').addEventListener('click', closeReportModal);
  reportModal.addEventListener('click', function (e) {
    if (e.target === reportModal) closeReportModal();
  });

  document.querySelectorAll('.rt-option').forEach(function (opt) {
    opt.addEventListener('click', function () {
      document.querySelectorAll('.rt-option').forEach(function (o) { o.classList.remove('active'); });
      opt.classList.add('active');
      reportType = opt.getAttribute('data-type');
    });
  });

  function openReportModal() {
    var sm = window.SMApp;
    if (!sm) return;
    var filter = sm.getFilter();
    var data = sm.getData();
    var meta = sm.getMeta();

    document.getElementById('rptPlatform').textContent = sm.getPlatformLabel();
    document.getElementById('rptTime').textContent = sm.getTimeLabel();
    var dMin = data && data.date_min ? data.date_min : '—';
    var dMax = data && data.date_max ? data.date_max : '—';
    document.getElementById('rptRange').textContent = dMin + ' 至 ' + dMax;

    // 数据质量提示：影响报告准确性时弹层内提示
    var warn = document.getElementById('reportWarn');
    if (meta && meta.platforms) {
      var stale = meta.platforms.filter(function (p) { return p.freshness_status === 'stale'; });
      if (stale.length > 0) {
        var names = stale.map(function (p) { return p.name; }).join('、');
        warn.style.display = 'block';
        warn.textContent = '注意：' + names + ' 数据滞后，可能影响报告准确性。';
      } else {
        warn.style.display = 'none';
      }
    } else {
      warn.style.display = 'none';
    }

    reportModal.classList.add('show');
  }

  function closeReportModal() {
    reportModal.classList.remove('show');
  }

  /* ---------- 生成 ---------- */
  document.getElementById('reportConfirm').addEventListener('click', async function () {
    var sm = window.SMApp;
    if (!sm) return;
    var typeLabel = ({ daily: '日报', weekly: '周报', monthly: '月报' })[reportType] || '报告';
    toast('正在生成' + typeLabel + '...');
    closeReportModal();

    var data = sm.getData() || {};
    var kpi = sm.getKPIs();
    var contentTop = sm.getContentTop().map(function (c) {
      return {
        content_title: c.content_title,
        platform: c.platform,
        platform_name: c.platform_name,
        exposure: c.exposure,
        views: c.views,
        likes: c.likes,
        comments: c.comments,
        favorites: c.favorites,
        shares: c.shares
      };
    });

    var payload = {
      reportType: reportType,
      filter: sm.getFilter(),
      kpi: {
        total_followers: kpi.total_followers,
        net_followers: kpi.net_followers,
        content_count: kpi.content_count,
        total_exposure: kpi.total_exposure,
        net_revenue: kpi.net_revenue
      },
      snapshot: {
        date_min: data.date_min,
        date_max: data.date_max,
        generated_at: data.generated_at,
        content_top: contentTop
      }
    };

    try {
      var r = await bridge.generateReport(payload);
      if (r && r.ok) {
        toast(typeLabel + '已生成');
        // 询问是否打开报告
        setTimeout(function () {
          if (confirm('报告已生成，是否立即打开？')) {
            bridge.openReport(r.id);
          }
        }, 400);
      } else {
        toast('生成失败：' + (r && r.error || '未知错误'), true);
      }
    } catch (e) {
      toast('生成异常：' + (e && e.message || e), true);
    }
  });

  /* ---------- 复用 app.js 的 toast ---------- */
  function toast(msg, isErr) {
    var t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.toggle('err', !!isErr);
    t.classList.add('show');
    clearTimeout(t._tid);
    t._tid = setTimeout(function () { t.classList.remove('show'); }, 2000);
  }
})();
