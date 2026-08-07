/* ============================================================
 * charts.js - 自媒体数据工作台图表绘制
 *
 * 全部使用原生 Canvas，不引入第三方图表库。
 * 暴露在 window.SMCharts 命名空间下，由 app.js 调用。
 * ============================================================ */
(function () {
  'use strict';

  var FONT = '13px -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif';

  /* ---------- 通用工具 ---------- */
  function fmtShort(n) {
    if (n == null || isNaN(n)) return '0';
    n = Math.round(n);
    var a = Math.abs(n);
    if (a >= 10000) return (n / 10000).toFixed(1) + 'w';
    if (a >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  function niceCeil(v) {
    if (v <= 0) return 1;
    var pow = Math.pow(10, Math.floor(Math.log10(v)));
    var n = v / pow;
    var nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
    return nice * pow;
  }

  function roundRect(ctx, x, y, w, h, r) {
    if (h < 0) { y += h; h = -h; }
    r = Math.min(r, w / 2, h / 2);
    if (r < 0) r = 0;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function prepCanvas(canvas, logicalH) {
    var dpr = Math.max(window.devicePixelRatio || 1, 2);
    var w = canvas.clientWidth || (canvas.parentElement && canvas.parentElement.clientWidth) || 600;
    var h;
    if (logicalH) {
      h = logicalH;
      canvas.style.height = h + 'px';
    } else {
      h = canvas.clientHeight || (canvas.parentElement && canvas.parentElement.clientHeight) || 240;
      if (h < 50) h = 240;
    }
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h };
  }

  /* ============================================================
   * 柱状图 - 净增趋势
   * ============================================================ */
  function drawBarChart(canvas, labels, values, color, opts) {
    if (!canvas) return;
    opts = opts || {};
    var unit = opts.unit || '';
    var isPercent = (unit === '%');
    var fmtVal = function (v) {
      if (isPercent) return (+v).toFixed(1) + unit;
      return fmtShort(v) + unit;
    };
    var p = prepCanvas(canvas, opts.height || 220);
    var ctx = p.ctx, w = p.w, h = p.h;
    ctx.clearRect(0, 0, w, h);

    var padL = 48, padR = 16, padT = 20, padB = 34;
    var cw = w - padL - padR, ch = h - padT - padB;
    var max = Math.max.apply(null, values.concat([1]));
    var min = Math.min.apply(null, values.concat([0]));
    if (min > 0) min = 0;
    var niceMax = niceCeil(max);
    var range = niceMax - min || 1;

    ctx.font = '11px ' + FONT;
    ctx.textBaseline = 'middle';
    for (var i = 0; i <= 4; i++) {
      var gy = padT + ch - ch * i / 4;
      ctx.strokeStyle = 'rgba(15,23,42,0.06)';
      ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke();
      ctx.fillStyle = '#8590a8'; ctx.textAlign = 'right';
      ctx.fillText(fmtVal(min + range * i / 4), padL - 8, gy);
    }

    var n = values.length, slot = cw / n, bw = Math.min(slot * 0.55, 36);
    ctx.textAlign = 'center';
    var lastIdx = n - 1;
    for (var j = 0; j < n; j++) {
      var v = values[j];
      var x = padL + slot * j + (slot - bw) / 2;
      var bh = ch * (v - min) / range;
      if (bh < 1) bh = 1;
      var y = padT + ch - bh;
      var isLast = (j === lastIdx);
      var grad = ctx.createLinearGradient(0, y, 0, padT + ch);
      if (isLast) {
        grad.addColorStop(0, color);
        grad.addColorStop(1, color);
      } else {
        grad.addColorStop(0, '#60A5FA');
        grad.addColorStop(1, 'rgba(96,165,250,0.6)');
      }
      ctx.fillStyle = grad;
      roundRect(ctx, x, y, bw, bh, 5);
      ctx.fill();
      if (v !== 0) {
        ctx.fillStyle = '#1A1A1A';
        ctx.textBaseline = 'bottom';
        ctx.font = '11px ' + FONT;
        ctx.fillText(fmtVal(v), x + bw / 2, y - 4);
      }
      ctx.fillStyle = '#8590a8';
      ctx.textBaseline = 'top';
      ctx.fillText(labels[j], x + bw / 2, padT + ch + 8);
    }

    // tooltip
    var hitMap = [];
    for (var jj = 0; jj < n; jj++) {
      var bx = padL + slot * jj + (slot - bw) / 2;
      hitMap.push({ x: bx + bw/2, y: padT + ch, r: Math.max(bw, 16), bar: { label: labels[jj], value: values[jj] } });
    }
    bindTooltip(canvas, hitMap, function (hit) {
      return '<div class="tt-row"><span>' + esc(hit.bar.label) + '</span><b>' + fmtVal(hit.bar.value) + '</b></div>';
    });
  }

  /* ============================================================
   * 环形图 - 粉丝分布
   * ============================================================ */
  function drawDonutChart(canvas, slices, total) {
    if (!canvas) return;
    var p = prepCanvas(canvas, 120);
    var ctx = p.ctx, w = p.w, h = p.h;
    ctx.clearRect(0, 0, w, h);
    var cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2 - 10;
    if (r < 10) r = 10;
    var a0 = -Math.PI / 2;
    slices.forEach(function (s) {
      var frac = Math.max(0, s.value) / total;
      if (frac <= 0) return;
      var a1 = a0 + frac * Math.PI * 2;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, a0, a1); ctx.closePath();
      ctx.fillStyle = s.color; ctx.fill();
      a0 = a1;
    });
    ctx.beginPath(); ctx.arc(cx, cy, r * 0.6, 0, Math.PI * 2); ctx.fillStyle = '#ffffff'; ctx.fill();
    ctx.fillStyle = '#1A1A1A'; ctx.font = '700 18px ' + FONT; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(fmtShort(total), cx, cy - 8);
    ctx.fillStyle = '#8590a8'; ctx.font = '12px ' + FONT;
    ctx.fillText('总粉丝', cx, cy + 12);

    // tooltip：按角度命中
    var hitArcs = [];
    var aStart = -Math.PI / 2;
    slices.forEach(function (s) {
      var frac = Math.max(0, s.value) / total;
      var aEnd = aStart + frac * Math.PI * 2;
      hitArcs.push({ a0: aStart, a1: aEnd, slice: s });
      aStart = aEnd;
    });
    bindTooltip(canvas, [{ x: cx, y: cy, r: r, isDonut: true, arcs: hitArcs, cx: cx, cy: cy, r: r }], function (hit) {
      var arcs = hit.arcs;
      var rect = canvas.getBoundingClientRect();
      var mx = (lastMouseX - rect.left) * (canvas.clientWidth / rect.width);
      var my = (lastMouseY - rect.top) * (canvas.clientHeight / rect.height);
      var angle = Math.atan2(my - hit.cy, mx - hit.cx);
      if (angle < -Math.PI / 2) angle += Math.PI * 2;
      for (var i = 0; i < arcs.length; i++) {
        if (angle >= arcs[i].a0 && angle <= arcs[i].a1) {
          var s = arcs[i].slice;
          var pct = (s.value / total * 100).toFixed(1);
          return '<div class="tt-title">' + esc(s.label || '') + '</div>' +
            '<div class="tt-row"><span>粉丝</span><b>' + fmtShort(s.value) + '</b></div>' +
            '<div class="tt-row"><span>占比</span><b>' + pct + '%</b></div>';
        }
      }
      return '';
    });
  }

  var lastMouseX = 0, lastMouseY = 0;
  document.addEventListener('mousemove', function (e) { lastMouseX = e.clientX; lastMouseY = e.clientY; });

  /* ============================================================
   * 横向条形图 - 平台粉丝体量
   * items: [{label, value, color, sub}]
   * ============================================================ */
  function drawHBarChart(canvas, items, opts) {
    if (!canvas) return;
    opts = opts || {};
    var p = prepCanvas(canvas, opts.height || 180);
    var ctx = p.ctx, w = p.w, h = p.h;
    ctx.clearRect(0, 0, w, h);

    if (!items || items.length === 0) {
      ctx.fillStyle = '#8590a8'; ctx.font = '13px ' + FONT;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('暂无数据', w / 2, h / 2);
      return;
    }

    var padL = 70, padR = 60, padT = 8, padB = 8;
    var cw = w - padL - padR;
    var max = Math.max.apply(null, items.map(function (it) { return it.value || 0; }).concat([1]));
    var niceMax = niceCeil(max);
    var rowH = (h - padT - padB) / items.length;
    var barH = Math.min(rowH * 0.55, 22);

    ctx.font = '12px ' + FONT;
    items.forEach(function (it, i) {
      var y = padT + rowH * i + (rowH - barH) / 2;
      // 标签
      ctx.fillStyle = '#1A1A1A'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillText(it.label, padL - 8, y + barH / 2);
      // 条
      var bw = cw * (it.value || 0) / niceMax;
      if (bw < 1) bw = 1;
      var grad = ctx.createLinearGradient(padL, 0, padL + bw, 0);
      grad.addColorStop(0, it.color || '#2563EB');
      grad.addColorStop(1, (it.color || '#2563EB'));
      ctx.fillStyle = grad;
      roundRect(ctx, padL, y, bw, barH, 4);
      ctx.fill();
      // 数值
      ctx.fillStyle = '#1A1A1A'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.font = '600 12px ' + FONT;
      ctx.fillText(fmtShort(it.value), padL + bw + 6, y + barH / 2);
      if (it.sub) {
        ctx.fillStyle = '#8590a8'; ctx.font = '11px ' + FONT;
        ctx.fillText(it.sub, padL + bw + 6 + 36, y + barH / 2);
      }
      ctx.font = '12px ' + FONT;
    });

    // tooltip
    var hitMap2 = [];
    items.forEach(function (it, i) {
      var yy = padT + rowH * i + (rowH - barH) / 2;
      hitMap2.push({ x: padL + cw / 2, y: yy + barH / 2, r: Math.max(rowH / 2, 14), item: it });
    });
    bindTooltip(canvas, hitMap2, function (hit) {
      return '<div class="tt-title">' + esc(hit.item.label || '') + '</div>' +
        '<div class="tt-row"><span>粉丝</span><b>' + fmtShort(hit.item.value) + '</b></div>' +
        (hit.item.sub ? '<div class="tt-row"><span>' + esc(hit.item.sub.replace(/[()]/g,'').trim()) + '</span></div>' : '');
    });
  }

  /* ============================================================
   * 平台净增条形图（水平，支持正负，可点击筛选）
   * items: [{ key, label, value (net), color, active }]
   * opts: { height, onClick }
   * ============================================================ */
  function drawPlatformNetBar(canvas, items, opts) {
    if (!canvas) return;
    opts = opts || {};
    console.log('[drawPlatformNetBar] items count=', items ? items.length : 0,
      items ? items.map(function(it){return it.label+':'+it.value;}) : []);
    var p = prepCanvas(canvas, opts.height || 220);
    var ctx = p.ctx, w = p.w, h = p.h;
    ctx.clearRect(0, 0, w, h);
    console.log('[drawPlatformNetBar] canvas logical size:', w, 'x', h);

    if (!items || items.length === 0) {
      ctx.fillStyle = '#8590a8'; ctx.font = '13px ' + FONT;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('当前筛选下暂无净增数据', w / 2, h / 2);
      return;
    }

    var padL = 72, padR = 64, padT = 14, padB = 14;
    var cw = w - padL - padR;
    var values = items.map(function (it) { return it.value || 0; });
    var maxAbs = Math.max.apply(null, values.map(Math.abs).concat([1]));
    var niceAbs = niceCeil(maxAbs);
    // 零点（0）的 X 位置：若全部 >=0，零点在左边；若全部 <=0，零点在右边；否则在中间
    var hasPos = values.some(function (v) { return v > 0; });
    var hasNeg = values.some(function (v) { return v < 0; });
    var zeroX;
    if (hasPos && hasNeg) {
      zeroX = padL + cw * niceAbs / (niceAbs * 2); // 中间
    } else if (hasPos) {
      zeroX = padL;
    } else {
      zeroX = padL + cw;
    }
    var xRange = niceAbs;
    var unitPx = (cw) / (hasPos && hasNeg ? niceAbs * 2 : niceAbs); // 每单位的像素
    var rowH = (h - padT - padB) / items.length;
    var barH = Math.min(rowH * 0.58, 24);

    // 绘制零点竖线
    ctx.strokeStyle = 'rgba(15,23,42,0.25)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(zeroX, padT); ctx.lineTo(zeroX, h - padB); ctx.stroke();

    // 命中检测缓存
    var hitMap3 = [];

    ctx.font = '12px ' + FONT;
    items.forEach(function (it, i) {
      var y = padT + rowH * i + (rowH - barH) / 2;
      var cy = y + barH / 2;
      var v = it.value || 0;
      var bw = Math.abs(v) * unitPx;
      if (v !== 0 && bw < 1.5) bw = 1.5;
      var bx = v >= 0 ? zeroX : zeroX - bw;

      // 左侧标签：平台名
      ctx.fillStyle = it.active ? 'var(--accent-text)' : '#1A1A1A';
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      if (it.active) {
        ctx.fillStyle = '#ffffff';
        // 给选中的标签画背景
        var lbl = it.label || '';
        var lblW = ctx.measureText(lbl).width + 10;
        var lblX = padL - 6, lblY = cy - 10;
        ctx.fillStyle = it.color || '#2563EB';
        roundRect(ctx, lblX - lblW, lblY, lblW, 20, 6);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
      }
      ctx.fillText(it.label || '', padL - 8, cy);

      // 背景轨道
      ctx.fillStyle = 'rgba(148,163,184,0.1)';
      roundRect(ctx, padL, y, cw, barH, 5);
      ctx.fill();

      // 条形
      var grad = ctx.createLinearGradient(bx, 0, bx + bw, 0);
      var c = it.color || '#2563EB';
      if (v >= 0) {
        grad.addColorStop(0, c);
        grad.addColorStop(1, lighten(c, 0.15));
      } else {
        grad.addColorStop(0, lighten(c, 0.2));
        grad.addColorStop(1, c);
      }
      ctx.fillStyle = grad;
      roundRect(ctx, bx, y, bw, barH, 5);
      ctx.fill();
      if (it.active) {
        ctx.strokeStyle = c;
        ctx.lineWidth = 2;
        roundRect(ctx, bx - 1, y - 1, bw + 2, barH + 2, 6);
        ctx.stroke();
      }

      // 右侧数值
      var sign = v > 0 ? '+' : '';
      var numTxt = sign + fmtNum(v);
      ctx.fillStyle = '#1A1A1A';
      ctx.textAlign = (v >= 0 ? 'left' : 'right');
      ctx.textBaseline = 'middle';
      ctx.font = '700 12px ' + FONT;
      var numX = v >= 0 ? bx + bw + 6 : bx - 6;
      // 若条太长，数值可能超出画布，做个钳制
      if (v >= 0) numX = Math.min(numX, w - padR + 4);
      else numX = Math.max(numX, padL - 4);
      ctx.fillText(numTxt, numX, cy);
      ctx.font = '12px ' + FONT;

      hitMap3.push({
        x: padL + cw / 2,
        y: cy,
        r: Math.max(rowH / 2, 16),
        rect: { x: padL, y: y, w: cw, h: barH },
        item: it
      });
    });

    // tooltip
    bindTooltip(canvas, hitMap3, function (hit) {
      var it = hit.item;
      var v = it.value || 0;
      var sign = v > 0 ? '+' : '';
      return '<div class="tt-title">' + esc(it.label || '') + '</div>' +
        '<div class="tt-row"><span>净增</span><b style="color:' + (v >= 0 ? 'var(--accent)' : '#F97316') + '">' + sign + fmtNum(v) + '</b></div>' +
        '<div class="tt-row" style="color:#93C5FD">点击条形筛选该平台 ›</div>';
    });

    // 点击：筛选对应平台
    if (opts.onClick && typeof opts.onClick === 'function') {
      if (canvas._netBarClick) {
        canvas.removeEventListener('click', canvas._netBarClick);
      }
      var clickFn = opts.onClick;
      var ref = hitMap3;
      canvas._netBarClick = function (e) {
        var rect = canvas.getBoundingClientRect();
        var mx = (e.clientX - rect.left) * (canvas.clientWidth / rect.width);
        var my = (e.clientY - rect.top) * (canvas.clientHeight / rect.height);
        for (var i = 0; i < ref.length; i++) {
          var r = ref[i].rect;
          if (mx >= r.x - 8 && mx <= r.x + r.w + 8 && my >= r.y - 4 && my <= r.y + r.h + 4) {
            clickFn(ref[i].item);
            return;
          }
        }
      };
      canvas.addEventListener('click', canvas._netBarClick);
    }
  }

  function lighten(hex, amt) {
    var h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
    if (!/^[0-9A-Fa-f]{6}$/.test(h)) return hex;
    var r = parseInt(h.substring(0, 2), 16);
    var g = parseInt(h.substring(2, 4), 16);
    var b = parseInt(h.substring(4, 6), 16);
    r = Math.round(r + (255 - r) * amt);
    g = Math.round(g + (255 - g) * amt);
    b = Math.round(b + (255 - b) * amt);
    return '#' + [r, g, b].map(function (x) { return x.toString(16).padStart(2, '0'); }).join('');
  }

  /* ============================================================
   * 四象限散点图 - 阅读 × 互动率
   * points: [{x, y, label, color, size, platform, data}]
   * 中位数作为分隔线，分四类内容
   * ============================================================ */
  function drawQuadrantChart(canvas, points, opts) {
    if (!canvas) return;
    opts = opts || {};
    var p = prepCanvas(canvas, opts.height || 260);
    var ctx = p.ctx, w = p.w, h = p.h;
    ctx.clearRect(0, 0, w, h);

    var xLabel = opts.xLabel || '阅读量';
    var yLabel = opts.yLabel || '互动率(%)';

    if (!points || points.length === 0) {
      ctx.fillStyle = '#8590a8'; ctx.font = '13px ' + FONT;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('暂无内容数据', w / 2, h / 2);
      return;
    }

    // 更均衡的内边距，视觉重心居中
    var padL = 44, padR = 20, padT = 18, padB = 36;
    var cw = w - padL - padR, ch = h - padT - padB;

    var xs = points.map(function (p) { return p.x || 0; });
    var ys = points.map(function (p) { return p.y || 0; });
    // 用对数刻度处理阅读量的长尾分布
    var useLogX = Math.max.apply(null, xs) / Math.max(Math.min.apply(null, xs.filter(function(v){return v>0})), 1) > 50;
    var xMaxRaw = Math.max.apply(null, xs.concat([1]));
    var xMax = useLogX ? Math.pow(10, Math.ceil(Math.log10(xMaxRaw))) : niceCeil(xMaxRaw);
    var yMax = niceCeil(Math.max.apply(null, ys.concat([1])));

    // 计算中位数
    var sortedX = xs.slice().sort(function(a,b){return a-b;});
    var sortedY = ys.slice().sort(function(a,b){return a-b;});
    var midIdx = Math.floor(sortedX.length / 2);
    var xMedian = sortedX.length % 2 === 0 ? (sortedX[midIdx-1] + sortedX[midIdx]) / 2 : sortedX[midIdx];
    var yMedian = sortedY.length % 2 === 0 ? (sortedY[midIdx-1] + sortedY[midIdx]) / 2 : sortedY[midIdx];
    // 避免中位数为0
    if (xMedian <= 0) xMedian = xMax / 2;
    if (yMedian <= 0) yMedian = yMax / 2;

    function xPos(x) {
      if (useLogX && x > 0) {
        return padL + cw * Math.log10(x) / Math.log10(xMax);
      }
      return padL + cw * (x || 0) / xMax;
    }
    function yPos(y) { return padT + ch - ch * (y || 0) / yMax; }

    // 四象限背景色
    var medXpx = xPos(xMedian);
    var medYpx = yPos(yMedian);
    ctx.fillStyle = 'rgba(37,99,235,0.04)';  // 右上：明星内容
    ctx.fillRect(medXpx, padT, w - padR - medXpx, medYpx - padT);
    ctx.fillStyle = 'rgba(96,165,250,0.04)';  // 右下：流量内容
    ctx.fillRect(medXpx, medYpx, w - padR - medXpx, padT + ch - medYpx);
    ctx.fillStyle = 'rgba(147,197,253,0.05)';  // 左上：社群内容
    ctx.fillRect(padL, padT, medXpx - padL, medYpx - padT);
    ctx.fillStyle = 'rgba(203,213,225,0.04)';  // 左下：长尾内容
    ctx.fillRect(padL, medYpx, medXpx - padL, padT + ch - medYpx);

    // 网格 + 坐标轴
    ctx.font = '11px ' + FONT;
    ctx.textBaseline = 'middle';
    for (var i = 0; i <= 4; i++) {
      var gy = padT + ch - ch * i / 4;
      ctx.strokeStyle = 'rgba(15,23,42,0.06)';
      ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke();
      ctx.fillStyle = '#8590a8'; ctx.textAlign = 'right';
      ctx.fillText(fmtShort(yMax * i / 4), padL - 8, gy);
    }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (var k = 0; k <= 4; k++) {
      var gx = padL + cw * k / 4;
      var xVal = useLogX ? Math.pow(10, Math.log10(xMax) * k / 4) : xMax * k / 4;
      ctx.fillStyle = '#8590a8';
      ctx.fillText(fmtShort(xVal), gx, padT + ch + 8);
    }

    // 中位数分隔线（虚线）
    ctx.strokeStyle = 'rgba(37,99,235,0.5)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(medXpx, padT); ctx.lineTo(medXpx, padT + ch); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(padL, medYpx); ctx.lineTo(w - padR, medYpx); ctx.stroke();
    ctx.setLineDash([]);

    // 中位数标注：放在坐标轴外侧，避免遮挡
    ctx.fillStyle = 'rgba(37,99,235,0.7)'; ctx.font = '10px ' + FONT;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText('阅读中位 ' + fmtShort(xMedian), medXpx, padT + ch + 4);
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText('互动中位 ' + (yMedian).toFixed(1) + '%', padL - 4, medYpx - 10);

    // 象限标注：居中偏内，视觉重心靠中
    ctx.font = '600 11px ' + FONT;
    var labelOffsetY = ch * 0.12;
    ctx.textAlign = 'center';
    // 右上：明星内容
    ctx.fillStyle = 'rgba(37,99,235,0.35)';
    ctx.textBaseline = 'top';
    ctx.fillText('明星内容', medXpx + (w - padR - medXpx) / 2, padT + labelOffsetY);
    // 右下：流量内容
    ctx.fillStyle = 'rgba(59,130,246,0.35)';
    ctx.textBaseline = 'bottom';
    ctx.fillText('流量内容', medXpx + (w - padR - medXpx) / 2, padT + ch - labelOffsetY);
    // 左上：社群内容
    ctx.fillStyle = 'rgba(147,197,253,0.4)';
    ctx.textBaseline = 'top';
    ctx.fillText('社群内容', padL + (medXpx - padL) / 2, padT + labelOffsetY);
    // 左下：长尾内容
    ctx.fillStyle = 'rgba(148,163,184,0.35)';
    ctx.textBaseline = 'bottom';
    ctx.fillText('长尾内容', padL + (medXpx - padL) / 2, padT + ch - labelOffsetY);

    // 轴标签
    ctx.fillStyle = '#5A6378'; ctx.font = '11px ' + FONT;
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    ctx.fillText(yLabel, 4, padT - 4);
    ctx.textAlign = 'right';
    ctx.fillText(xLabel + (useLogX ? ' (对数)' : ''), w - padR, h - 14);

    // 散点 + 存储位置用于 tooltip
    var hitMap = [];
    points.forEach(function (pt) {
      var px = xPos(pt.x || 0);
      var py = yPos(pt.y || 0);
      var r = pt.size || 5;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fillStyle = (pt.color || '#2563EB') + 'CC';
      ctx.fill();
      ctx.strokeStyle = pt.color || '#2563EB';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      hitMap.push({ x: px, y: py, r: r + 3, point: pt });
    });

    // 绑定 tooltip
    bindTooltip(canvas, hitMap, function (hit) {
      var pt = hit.point;
      var d = pt.data || {};
      var quadrant = (pt.x >= xMedian && pt.y >= yMedian) ? '明星内容'
        : (pt.x >= xMedian && pt.y < yMedian) ? '流量内容'
        : (pt.x < xMedian && pt.y >= yMedian) ? '社群内容'
        : '长尾内容';
      return '<div class="tt-title">' + esc(pt.label || '') + '</div>' +
        '<div class="tt-row"><span>平台</span><b>' + esc(pt.platform || '') + '</b></div>' +
        '<div class="tt-row"><span>阅读</span><b>' + fmtShort(pt.x) + '</b></div>' +
        '<div class="tt-row"><span>互动率</span><b>' + (pt.y || 0).toFixed(1) + '%</b></div>' +
        '<div class="tt-row"><span>分类</span><b>' + quadrant + '</b></div>' +
        (pt.data && pt.data.content_url ? '<div class="tt-row" style="color:#93C5FD">点击圆点打开原文 ›</div>' : '');
    });

    // 绑定点击事件：点击圆点触发 onClick 回调
    if (opts.onClick && typeof opts.onClick === 'function') {
      if (canvas._scatterClickHandler) {
        canvas.removeEventListener('click', canvas._scatterClickHandler);
      }
      var onClickFn = opts.onClick;
      var hitMapRef = hitMap;
      canvas._scatterClickHandler = function (e) {
        var rect = canvas.getBoundingClientRect();
        var mx = (e.clientX - rect.left) * (canvas.clientWidth / rect.width);
        var my = (e.clientY - rect.top) * (canvas.clientHeight / rect.height);
        var bestDist = Infinity, bestHit = null;
        for (var i = 0; i < hitMapRef.length; i++) {
          var h = hitMapRef[i];
          var dx = mx - h.x, dy = my - h.y;
          var dist = Math.sqrt(dx * dx + dy * dy);
          if (dist <= h.r && dist < bestDist) {
            bestDist = dist;
            bestHit = h;
          }
        }
        if (bestHit) {
          onClickFn(bestHit.point);
        }
      };
      canvas.addEventListener('click', canvas._scatterClickHandler);
    }
  }

  /* ============================================================
   * 通用 Tooltip 绑定
   * ============================================================ */
  var tooltipEl = null;
  function getTooltipEl() {
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.className = 'chart-tooltip';
      tooltipEl.style.display = 'none';
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }
  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function bindTooltip(canvas, hitMap, formatFn) {
    if (!canvas) return;
    // 移除旧监听
    if (canvas._tooltipHandler) {
      canvas.removeEventListener('mousemove', canvas._tooltipHandler.move);
      canvas.removeEventListener('mouseleave', canvas._tooltipHandler.leave);
    }
    var tt = getTooltipEl();
    function findHit(mx, my) {
      var rect = canvas.getBoundingClientRect();
      var scaleX = canvas.clientWidth / rect.width;
      var scaleY = canvas.clientHeight / rect.height;
      var bestDist = Infinity, bestHit = null;
      for (var i = 0; i < hitMap.length; i++) {
        var h = hitMap[i];
        var dx = mx - h.x, dy = my - h.y;
        var dist = Math.sqrt(dx * dx + dy * dy);
        if (dist <= h.r && dist < bestDist) {
          bestDist = dist;
          bestHit = h;
        }
      }
      return bestHit;
    }
    var moveHandler = function (e) {
      var rect = canvas.getBoundingClientRect();
      var mx = (e.clientX - rect.left) * (canvas.clientWidth / rect.width);
      var my = (e.clientY - rect.top) * (canvas.clientHeight / rect.height);
      var hit = findHit(mx, my);
      if (hit) {
        tt.innerHTML = formatFn(hit);
        tt.style.display = 'block';
        var tx = e.clientX + 14;
        var ty = e.clientY + 14;
        if (tx + tt.offsetWidth > window.innerWidth) tx = e.clientX - tt.offsetWidth - 14;
        if (ty + tt.offsetHeight > window.innerHeight) ty = e.clientY - tt.offsetHeight - 14;
        tt.style.left = tx + 'px';
        tt.style.top = ty + 'px';
        canvas.style.cursor = 'pointer';
      } else {
        tt.style.display = 'none';
        canvas.style.cursor = 'default';
      }
    };
    var leaveHandler = function () {
      tt.style.display = 'none';
      canvas.style.cursor = 'default';
    };
    canvas.addEventListener('mousemove', moveHandler);
    canvas.addEventListener('mouseleave', leaveHandler);
    canvas._tooltipHandler = { move: moveHandler, leave: leaveHandler };
  }

  /* ============================================================
   * 折线图 - 净收入趋势 / 移动平均
   * series: [{label, values, color, dashed}]
   * labels: x 轴标签
   * ============================================================ */
  function drawLineChart(canvas, labels, series, opts) {
    if (!canvas) return;
    opts = opts || {};
    var p = prepCanvas(canvas, opts.height || 200);
    var ctx = p.ctx, w = p.w, h = p.h;
    ctx.clearRect(0, 0, w, h);

    var padL = 56, padR = 16, padT = 20, padB = 34;
    var cw = w - padL - padR, ch = h - padT - padB;

    var allVals = [];
    series.forEach(function (s) { allVals = allVals.concat(s.values || []); });
    var max = Math.max.apply(null, allVals.concat([1]));
    var min = 0;
    var niceMax = niceCeil(max);
    var range = niceMax - min || 1;

    // 网格 + Y轴
    ctx.font = '11px ' + FONT;
    ctx.textBaseline = 'middle';
    for (var i = 0; i <= 4; i++) {
      var gy = padT + ch - ch * i / 4;
      ctx.strokeStyle = 'rgba(15,23,42,0.06)';
      ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke();
      ctx.fillStyle = '#8590a8'; ctx.textAlign = 'right';
      var unit = opts.money ? '¥' : '';
      ctx.fillText(unit + fmtShort(min + range * i / 4), padL - 8, gy);
    }

    // X 轴标签
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    var n = labels.length;
    var step = Math.ceil(n / 8);
    for (var j = 0; j < n; j++) {
      if (j % step !== 0 && j !== n - 1) continue;
      var x = padL + cw * (n === 1 ? 0.5 : j / (n - 1));
      ctx.fillStyle = '#8590a8';
      ctx.fillText(labels[j], x, padT + ch + 8);
    }

    // 折线
    series.forEach(function (s) {
      var vals = s.values || [];
      ctx.strokeStyle = s.color || '#2563EB';
      ctx.lineWidth = s.dashed ? 1.5 : 2;
      if (s.dashed) ctx.setLineDash([4, 3]); else ctx.setLineDash([]);
      ctx.beginPath();
      vals.forEach(function (v, idx) {
        var x = padL + cw * (n === 1 ? 0.5 : idx / (n - 1));
        var y = padT + ch - ch * (v - min) / range;
        if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);

      // 数据点
      if (!s.dashed) {
        vals.forEach(function (v, idx) {
          var x = padL + cw * (n === 1 ? 0.5 : idx / (n - 1));
          var y = padT + ch - ch * (v - min) / range;
          ctx.beginPath();
          ctx.arc(x, y, 3, 0, Math.PI * 2);
          ctx.fillStyle = '#fff';
          ctx.fill();
          ctx.strokeStyle = s.color || '#2563EB';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        });
      }
    });

    // 图例
    if (series.length > 1) {
      var legendX = w - padR;
      var legendY = padT + 4;
      ctx.textBaseline = 'middle'; ctx.textAlign = 'right'; ctx.font = '11px ' + FONT;
      series.slice().reverse().forEach(function (s, i) {
        var lw = 12;
        ctx.strokeStyle = s.color; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(legendX - lw, legendY + i * 16); ctx.lineTo(legendX, legendY + i * 16); ctx.stroke();
        ctx.fillStyle = '#5A6378';
        ctx.fillText(s.label, legendX - lw - 4, legendY + i * 16);
      });
    }

    // tooltip
    var slotW = cw / n;
    var hitMapL = [];
    for (var li = 0; li < n; li++) {
      hitMapL.push({ x: padL + slotW * li + slotW/2, y: padT + ch/2, r: Math.max(slotW/2, 16), label: labels[li], series: series, idx: li, money: opts.money });
    }
    bindTooltip(canvas, hitMapL, function (hit) {
      var html = '<div class="tt-title">' + esc(hit.label) + '</div>';
      hit.series.forEach(function (s) {
        var val = s.values[hit.idx] || 0;
        var display = hit.money ? '¥' + val.toFixed(1) : fmtShort(val);
        html += '<div class="tt-row"><span style="color:' + s.color + '">● ' + esc(s.label) + '</span><b>' + display + '</b></div>';
      });
      return html;
    });
  }

  /* ============================================================
   * 半圆仪表（用于 HHI、目标达成率等 0~100% / 0~10000 指标）
   * ============================================================ */
  /**
   * opts:
   *   value     : 实际值（Number）
   *   max       : 值域最大值（默认 100）
   *   thresholds: {danger,warn,good,ok} 或数组区间 [[0,val,'danger'],...]
   *   color     : 可选：指定 arc 颜色（覆盖区间判断）
   *   unit      : 中心单位文字（如 '%', 'HHI', '¥w'）
   *   labelFn   : 可选：(value, max) => String，自定义中心文字
   *   showTicks : 是否画刻度（默认 true）
   */
  function drawSemiGauge(canvasOrId, opts) {
    var canvas = typeof canvasOrId === 'string' ? document.getElementById(canvasOrId) : canvasOrId;
    if (!canvas) return;
    var o = opts || {};
    var value = Math.max(0, Math.min(o.value != null ? o.value : 0, o.max != null ? o.max : 100));
    var max = o.max != null ? o.max : 100;
    var pct = max > 0 ? value / max : 0;

    // 根据阈值确定颜色
    var level = 'ok';
    if (o.thresholds) {
      if (Array.isArray(o.thresholds)) {
        for (var ti = 0; ti < o.thresholds.length; ti++) {
          var t = o.thresholds[ti];
          if (value >= t[0] && value < t[1]) { level = t[2]; break; }
        }
      } else {
        var tr = o.thresholds;
        if (tr.danger != null && value >= tr.danger) level = 'danger';
        else if (tr.warn != null && value >= tr.warn) level = 'warn';
        else if (tr.good != null && value >= tr.good) level = 'good';
        else if (tr.ok != null && value >= tr.ok) level = 'ok';
      }
    }
    var arcColor = o.color || ({
      danger: '#DC2626',
      warn:   '#F59E0B',
      good:   '#10B981',
      ok:     '#2563EB'
    }[level] || '#2563EB');

    var dpr = prepCanvas(canvas);
    var ctx = canvas.getContext('2d');
    var W = canvas.clientWidth || 160, H = canvas.clientHeight || 90;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var cx = W / 2, cy = H * 1.02;
    var r = Math.min(W / 2 - 4, H * 0.95);
    var start = Math.PI, end = 0; // 半圆（从左 180° 到右 0°）

    // 背景轨道
    ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 14; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.arc(cx, cy, r - 7, start, end); ctx.stroke();

    // 刻度
    var showTicks = o.showTicks !== false;
    if (showTicks) {
      var nTick = 10;
      ctx.strokeStyle = '#CBD5E1'; ctx.lineWidth = 1;
      for (var k = 0; k <= nTick; k++) {
        var a = start + (end - start) * (k / nTick);
        var r1 = r - 2, r2 = r - 11;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
        ctx.lineTo(cx + Math.cos(a) * r2, cy + Math.sin(a) * r2);
        ctx.stroke();
      }
    }

    // 值弧
    ctx.strokeStyle = arcColor; ctx.lineWidth = 14; ctx.lineCap = 'round';
    var pctEnd = start + (end - start) * pct;
    ctx.beginPath(); ctx.arc(cx, cy, r - 7, start, pctEnd); ctx.stroke();

    // 中心文字（value）
    var centerText;
    if (typeof o.labelFn === 'function') centerText = o.labelFn(value, max);
    else if (max === 100) centerText = (pct * 100).toFixed(0) + '%';
    else centerText = fmtShort(value);
    var fontBig = '700 26px -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = '#0F172A';
    ctx.font = fontBig;
    ctx.fillText(centerText, cx, cy - 8);

    return { level: level, value: value, pct: pct };
  }

  /* ============================================================
   * 瀑布图（纯 DOM 渲染，收入结构 / 平台净增贡献都可复用）
   * ============================================================ */
  /**
   * container: HTMLElement 或 id
   * rows: [{label, value, type?:'up'|'down'|'total', start?}]
   * opts: { money?:boolean, totalPrefix?:'上月'/'期初' }
   */
  function drawWaterfall(container, rows, opts) {
    var el = typeof container === 'string' ? document.getElementById(container) : container;
    if (!el) return;
    var o = opts || {};
    el.innerHTML = '';
    var absMax = 1;
    rows.forEach(function (r) { if (Math.abs(r.value || 0) > absMax) absMax = Math.abs(r.value || 0); });

    var cumStart = 0;
    rows.forEach(function (row, i) {
      var type = row.type || (row.value >= 0 ? 'up' : 'down');
      if (type === 'total' && row.start == null) {
        // 总和条：起点 0
        cumStart = 0;
      } else if (row.start != null) {
        cumStart = row.start;
      }
      var v = row.value || 0;
      var abs = Math.abs(v);
      var startPct = absMax > 0 ? (cumStart / absMax) * 100 : 0;
      var widthPct = absMax > 0 ? Math.max(abs / absMax * 100, 2) : 2;
      if (type === 'total') { startPct = 0; widthPct = absMax > 0 ? Math.max(Math.abs(v) / absMax * 100, 2) : 2; }

      var rowEl = document.createElement('div');
      rowEl.className = 'wf-row';

      var label = document.createElement('div');
      label.className = 'wf-label';
      label.innerHTML = row.label || '';
      rowEl.appendChild(label);

      var wrap = document.createElement('div');
      wrap.className = 'wf-bar-wrap';
      var bar = document.createElement('div');
      bar.className = 'wf-bar ' + type;
      if (type === 'up') {
        bar.style.left = startPct + '%';
        bar.style.width = widthPct + '%';
      } else if (type === 'down') {
        bar.style.left = (startPct - widthPct) + '%';
        bar.style.width = widthPct + '%';
      } else {
        bar.style.left = 0;
        bar.style.width = widthPct + '%';
      }
      wrap.appendChild(bar);
      rowEl.appendChild(wrap);

      var valEl = document.createElement('div');
      valEl.className = 'wf-val ' + type;
      var display;
      if (o.money) {
        display = (v >= 0 ? '+' : '-') + '¥' + Math.abs(v).toFixed(0);
        if (type === 'total') display = '¥' + Math.abs(v).toFixed(0);
      } else {
        display = (v >= 0 ? '+' : '') + fmtShort(v);
        if (type === 'total') display = fmtShort(Math.abs(v));
      }
      valEl.textContent = display;
      rowEl.appendChild(valEl);

      // 悬停 tooltip
      if (row.label) {
        rowEl.title = row.label + ': ' + display + (row.sub ? ' (' + row.sub + ')' : '');
      }

      el.appendChild(rowEl);

      if (type !== 'total') cumStart = cumStart + v;
    });
  }

  /* ============================================================
   * 通用饼图/甜甜圈（用于收入类型、成本类型分布等）
   * slices: [{label, value, color}]
   * opts: { centerLabel, centerValue, donutRatio(0.6) }
   * ============================================================ */
  function drawPieChart(canvasOrId, slices, opts) {
    var canvas = typeof canvasOrId === 'string' ? document.getElementById(canvasOrId) : canvasOrId;
    if (!canvas) return;
    var o = opts || {};
    var total = slices.reduce(function (s, x) { return s + Math.max(0, x.value); }, 0);
    if (total <= 0) {
      var p0 = prepCanvas(canvas);
      p0.ctx.clearRect(0, 0, p0.w, p0.h);
      p0.ctx.fillStyle = '#94A3B8'; p0.ctx.font = '12px ' + FONT;
      p0.ctx.textAlign = 'center'; p0.ctx.textBaseline = 'middle';
      p0.ctx.fillText('暂无数据', p0.w / 2, p0.h / 2);
      return;
    }
    var p = prepCanvas(canvas);
    var ctx = p.ctx, w = p.w, h = p.h;
    ctx.clearRect(0, 0, w, h);
    var cx = w / 2, cy = h / 2;
    var r = Math.min(w, h) / 2 - 8;
    if (r < 10) r = 10;
    var donutRatio = o.donutRatio != null ? o.donutRatio : 0.62;
    var a0 = -Math.PI / 2;
    slices.forEach(function (s) {
      var frac = Math.max(0, s.value) / total;
      if (frac <= 0) return;
      var a1 = a0 + frac * Math.PI * 2;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, a0, a1); ctx.closePath();
      ctx.fillStyle = s.color; ctx.fill();
      // 白色分隔线
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
      a0 = a1;
    });
    // 甜甜圈中心镂空
    if (donutRatio > 0) {
      ctx.beginPath(); ctx.arc(cx, cy, r * donutRatio, 0, Math.PI * 2);
      ctx.fillStyle = '#fff'; ctx.fill();
    }
    // 中心文字
    if (o.centerValue) {
      ctx.fillStyle = o.centerColor || '#0F172A';
      ctx.font = '800 18px ' + FONT;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(o.centerValue, cx, cy - 6);
    }
    if (o.centerLabel) {
      ctx.fillStyle = '#94A3B8'; ctx.font = '10px ' + FONT;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(o.centerLabel, cx, cy + 10);
    }
  }

  /* ============================================================
   * 通用 SVG Donut 渲染函数（参照粉丝分布饼图）
   * container: 容器元素或 ID
   * slices: [{key, label, value, color}]
   * opts: { centerValue, centerLabel, centerColor,
   *         compactCenterValue,       // 超长压缩 fallback（如 ¥15,000 → ¥15k），字号不变
   *         onSliceClick(key), onLegendClick(key),
   *         showLegend(true), showTooltip(true),
   *         svgSize(42), rOuter(18), rInner(13),
   *         centerFontSize(6.8), labelFontSize(3.5) }
   * 生成的 DOM: .donut-wrap > svg, .donut-tooltip, .legend-col
   * ============================================================ */
  function renderSvgDonut(container, slices, opts) {
    var box = typeof container === 'string' ? document.getElementById(container) : container;
    if (!box) return;
    var o = opts || {};
    if (!slices || !slices.length) slices = [{ key: 'empty', label: '暂无数据', value: 1, color: '#E5E7EB' }];
    var total = slices.reduce(function (a, s) { return a + Math.max(0, s.value); }, 0) || 1;

    // 排序
    slices = slices.slice().sort(function (a, b) { return b.value - a.value; });

    var size = o.svgSize || 42;
    var cx = size / 2, cy = size / 2;
    var rOuter = o.rOuter != null ? o.rOuter : (size / 2) - 3;
    var rInner = o.rInner != null ? o.rInner : rOuter * 0.72;
    var innerDiameter = rInner * 2 - 2;   // 可用内宽（留1px安全边）
    var centerFontSize = o.centerFontSize != null ? o.centerFontSize : 6.8;
    var labelFontSize = o.labelFontSize != null ? o.labelFontSize : 3.5;

    function arcPath(startAngle, endAngle) {
      var sRad = (startAngle - 90) * Math.PI / 180;
      var eRad = (endAngle - 90) * Math.PI / 180;
      var x1 = cx + rOuter * Math.cos(sRad);
      var y1 = cy + rOuter * Math.sin(sRad);
      var x2 = cx + rOuter * Math.cos(eRad);
      var y2 = cy + rOuter * Math.sin(eRad);
      var x3 = cx + rInner * Math.cos(eRad);
      var y3 = cy + rInner * Math.sin(eRad);
      var x4 = cx + rInner * Math.cos(sRad);
      var y4 = cy + rInner * Math.sin(sRad);
      var largeArc = (endAngle - startAngle) > 180 ? 1 : 0;
      return 'M' + x1.toFixed(3) + ',' + y1.toFixed(3) +
        ' A' + rOuter + ',' + rOuter + ' 0 ' + largeArc + ' 1 ' + x2.toFixed(3) + ',' + y2.toFixed(3) +
        ' L' + x3.toFixed(3) + ',' + y3.toFixed(3) +
        ' A' + rInner + ',' + rInner + ' 0 ' + largeArc + ' 0 ' + x4.toFixed(3) + ',' + y4.toFixed(3) + ' Z';
    }

    var angleAcc = 0;
    var svgSlices = slices.map(function (s) {
      var frac = Math.max(0, s.value) / total;
      var startA = angleAcc * 360;
      var endA = (angleAcc + frac) * 360;
      angleAcc += frac;
      if (frac <= 0) return '';
      var d = frac >= 0.999 ? arcPath(0, 180) + ' ' + arcPath(180, 360) : arcPath(startA, endA);
      return '<path class="donut-slice" data-key="' + esc(s.key) + '" data-label="' + esc(s.label) + '" data-value="' + s.value + '" data-pct="' + (frac * 100).toFixed(1) + '"' +
        ' d="' + d + '" fill="' + s.color + '" stroke="#fff" stroke-width="0.4"/>';
    }).join('');

    var isEmpty = slices.length === 1 && slices[0].key === 'empty';
    var centerText = isEmpty ? '—' : (o.centerValue != null ? String(o.centerValue) : fmtShort(total));
    // 超模检测：字符宽度 ≈ 字号 × 0.62，若超长则使用 compactCenterValue（字号保持不变）
    var avgCharW = centerFontSize * 0.62;
    var estW = centerText.length * avgCharW;
    if (estW > innerDiameter && o.compactCenterValue != null) {
      centerText = String(o.compactCenterValue);
    }
    var centerLabel = o.centerLabel || '';
    var centerColor = o.centerColor || '#0F172A';

    var svgHtml =
      '<svg viewBox="0 0 ' + size + ' ' + size + '" xmlns="http://www.w3.org/2000/svg">' +
        svgSlices +
        '<text x="' + cx + '" y="' + (cy - 0.5) + '" text-anchor="middle" font-size="' + centerFontSize + '" font-weight="700" fill="' + centerColor + '">' + centerText + '</text>' +
        '<text x="' + cx + '" y="' + (cy + 4) + '" text-anchor="middle" font-size="' + labelFontSize + '" fill="var(--text-tertiary)" font-weight="500">' + centerLabel + '</text>' +
      '</svg>';

    var showLegend = o.showLegend != null ? o.showLegend : true;
    var showTooltip = o.showTooltip != null ? o.showTooltip : true;

    var legendHtml = '';
    if (showLegend) {
      legendHtml = slices.map(function (s) {
        if (s.key === 'empty') return '';
        var pct = total ? (Math.max(0, s.value) / total * 100).toFixed(1) : '0';
        return '<div class="legend-item" data-key="' + esc(s.key) + '">' +
          '<span class="lw" style="background:' + s.color + '"></span>' +
          '<span class="li-label">' + esc(s.label) + '</span>' +
          '<span class="li-absolute">' + fmtShort(s.value) + '</span>' +
          '<span class="li-pct">' + pct + '%</span></div>';
      }).filter(Boolean).join('');
    }

    var tooltipHtml = showTooltip ? '<div class="donut-tooltip"></div>' : '';

    box.innerHTML =
      '<div class="donut-wrap">' + svgHtml + tooltipHtml + '</div>' +
      (showLegend ? '<div class="legend-col">' + legendHtml + '</div>' : '');

    // 绑定交互
    if (showTooltip) {
      var tooltip = box.querySelector('.donut-tooltip');
      box.querySelectorAll('.donut-slice').forEach(function (slice) {
        slice.addEventListener('mouseenter', function () {
          var pct = slice.getAttribute('data-pct');
          var val = slice.getAttribute('data-value');
          var label = slice.getAttribute('data-label');
          if (tooltip) {
            tooltip.innerHTML = esc(label) + '<br><b>' + fmtShort(Number(val)) + ' (' + pct + '%)</b>';
            tooltip.style.display = 'block';
          }
          box.querySelectorAll('.donut-slice').forEach(function (s) {
            if (s !== slice) s.classList.add('dimmed');
          });
          box.querySelectorAll('.legend-item').forEach(function (li) {
            if (li.getAttribute('data-key') !== slice.getAttribute('data-key')) {
              li.style.opacity = '0.35';
            }
          });
        });
        slice.addEventListener('mousemove', function (e) {
          if (tooltip) {
            var rect = box.querySelector('.donut-wrap').getBoundingClientRect();
            tooltip.style.left = (e.clientX - rect.left) + 'px';
            tooltip.style.top = (e.clientY - rect.top) + 'px';
          }
        });
        slice.addEventListener('mouseleave', function () {
          if (tooltip) tooltip.style.display = 'none';
          box.querySelectorAll('.donut-slice').forEach(function (s) { s.classList.remove('dimmed'); });
          box.querySelectorAll('.legend-item').forEach(function (li) { li.style.opacity = ''; });
        });
        slice.addEventListener('click', function () {
          if (typeof o.onSliceClick === 'function') {
            o.onSliceClick(slice.getAttribute('data-key'));
          }
        });
      });
    }

    // 图例交互
    if (showLegend) {
      box.querySelectorAll('.legend-item').forEach(function (item) {
        item.addEventListener('mouseenter', function () {
          var key = item.getAttribute('data-key');
          box.querySelectorAll('.donut-slice').forEach(function (s) {
            if (s.getAttribute('data-key') !== key) s.classList.add('dimmed');
          });
        });
        item.addEventListener('mouseleave', function () {
          box.querySelectorAll('.donut-slice').forEach(function (s) { s.classList.remove('dimmed'); });
        });
        item.addEventListener('click', function () {
          if (typeof o.onLegendClick === 'function') {
            o.onLegendClick(item.getAttribute('data-key'));
          }
        });
      });
    }
  }

  /* ---------- 暴露 ---------- */
  window.SMCharts = {
    fmtShort: fmtShort,
    niceCeil: niceCeil,
    prepCanvas: prepCanvas,
    drawBarChart: drawBarChart,
    drawDonutChart: drawDonutChart,
    drawHBarChart: drawHBarChart,
    drawPlatformNetBar: drawPlatformNetBar,
    drawQuadrantChart: drawQuadrantChart,
    drawLineChart: drawLineChart,
    drawSemiGauge: drawSemiGauge,
    drawWaterfall: drawWaterfall,
    drawPieChart: drawPieChart,
    renderSvgDonut: renderSvgDonut,
    bindTooltip: bindTooltip
  };
})();
