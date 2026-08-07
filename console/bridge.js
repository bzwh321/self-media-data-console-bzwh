/* ============================================================
 * bridge.js - Web 端桥接层
 *
 * 把原 Electron 设计稿中通过 preload 注入的 selfMediaBridge
 * 改写为 fetch 调用本地 Python 控制台服务（console_server.py）。
 *
 * 暴露的接口与原设计保持一致，使 app.js / report-modal.js 无需改动。
 * 服务器响应已是 {ok, data} / {ok, item} 等约定格式，这里直接透传。
 * ============================================================ */
(function () {
  'use strict';

  var BASE = ''; // 同源服务，无需配置

  function jsonOk(res) {
    if (!res.ok) {
      return res.text().then(function (t) {
        var msg = t;
        try { msg = JSON.parse(t).error || t; } catch (e) {}
        throw new Error(msg || ('HTTP ' + res.status));
      });
    }
    var ct = res.headers.get('Content-Type') || '';
    if (ct.indexOf('application/json') >= 0) return res.json();
    if (ct.indexOf('text/markdown') >= 0) return res.text();
    return res.text();
  }

  function getJSON(url) {
    return fetch(BASE + url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
      .then(jsonOk);
  }

  function postJSON(url, body) {
    return fetch(BASE + url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body || {}),
      credentials: 'same-origin'
    }).then(jsonOk);
  }

  function putJSON(url, body) {
    return fetch(BASE + url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body || {}),
      credentials: 'same-origin'
    }).then(jsonOk);
  }

  function delJSON(url) {
    return fetch(BASE + url, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    }).then(jsonOk);
  }

  function safeCatch(e) {
    return { ok: false, error: (e && e.message) || String(e) };
  }

  window.selfMediaBridge = {
    /* 看板数据：服务器返回 {ok, data}，直接透传给 app.js */
    getDashboard: function () {
      return getJSON('/api/dashboard').catch(safeCatch);
    },

    /* 元信息：服务器直接返回 meta 对象 */
    getMeta: function () {
      return getJSON('/api/meta').catch(function () { return null; });
    },

    /* 刷新：触发后端流水线，服务器返回 {ok, data} */
    refreshDashboard: function () {
      return postJSON('/api/refresh', {}).catch(safeCatch);
    },

    /* 热榜素材：服务器直接返回数组 */
    getHotlist: function () {
      return getJSON('/api/hotlist').catch(function () { return []; });
    },

    /* 热榜搜索推荐：返回主流媒体上与"数据分析"相关的 5 条热门内容 */
    suggestHot: function (keyword) {
      return getJSON('/api/hotlist/suggest?keyword=' + encodeURIComponent(keyword || '数据分析')).catch(safeCatch);
    },

    /* 粉丝增长归因分析数据：服务器返回 {ok, data} */
    getAttribution: function () {
      return getJSON('/api/attribution').catch(safeCatch);
    },

    /* 经营分析数据：服务器返回 {ok, data}（含摘要、结论文字、异常清单） */
    getOpsAnalysis: function () {
      return getJSON('/api/ops-analysis').catch(safeCatch);
    },

    /* 添加 / 更新 / 删除：服务器返回 {ok, item} 或 {ok, error} */
    addHot: function (payload) {
      return postJSON('/api/hot', payload || {}).catch(safeCatch);
    },
    updateHot: function (id, patch) {
      return putJSON('/api/hot/' + encodeURIComponent(id), patch || {}).catch(safeCatch);
    },
    removeHot: function (id) {
      return delJSON('/api/hot/' + encodeURIComponent(id)).catch(safeCatch);
    },

    /* 报告：服务器返回 {ok, id, path} 或 {ok, error} */
    generateReport: function (payload) {
      return postJSON('/api/report', payload || {}).catch(safeCatch);
    },
    /* 在新标签页打开 Markdown 报告 */
    openReport: function (id) {
      window.open('/api/report/' + encodeURIComponent(id), '_blank');
      return Promise.resolve({ ok: true });
    },

    /* 平台后台入口：通过白名单打开新窗口 */
    openPlatform: function (platform) {
      return postJSON('/api/open-platform', { platform: platform }).then(function (r) {
        if (r && r.ok && r.url) {
          window.open(r.url, '_blank', 'noopener,noreferrer');
        }
        return r || { ok: false };
      }).catch(safeCatch);
    },

    /* 平台入口列表（供 app.js 渲染浮层） */
    getPlatformEntries: function () {
      return getJSON('/api/platform-entries').then(function (r) {
        return (r && r.items) || [];
      }).catch(function () { return []; });
    },

    /* ---------- 笔记灵感 ---------- */
    getNotes: function () {
      return getJSON('/api/notes').then(function (r) {
        return (r && r.items) || [];
      }).catch(function () { return []; });
    },
    addNote: function (payload) {
      return postJSON('/api/notes', payload || {}).catch(safeCatch);
    },
    updateNote: function (id, patch) {
      return putJSON('/api/notes/' + encodeURIComponent(id), patch || {}).catch(safeCatch);
    },
    removeNote: function (id) {
      return delJSON('/api/notes/' + encodeURIComponent(id)).catch(safeCatch);
    },
    aiGenerate: function (noteId, payload) {
      return postJSON('/api/notes/' + encodeURIComponent(noteId) + '/ai-generate', payload || {}).catch(safeCatch);
    },
    getAiOutputs: function () {
      return getJSON('/api/ai-outputs').then(function (r) {
        return (r && r.items) || [];
      }).catch(function () { return []; });
    },
    getAiConfigStatus: function () {
      return getJSON('/api/ai-config-status').catch(safeCatch);
    }
  };
})();
