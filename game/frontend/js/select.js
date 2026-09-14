/* ============================================================
 * select.js —— 「剧本工坊」选本面板（非侵入式，不改动 data.js/store.js）
 *
 * 职责：
 *  - http(s) 同源运行时：拉取 GET /api/studio/catalog，渲染 gen_* 剧本卡片；
 *    点击「开始游戏」复用现有建局封装 Store.playStudio(id)
 *    （其内部走 GET /api/studio/{id}/public 水合 + POST /api/session {scenario_id} + WS 接线）。
 *  - mock 模式（file:// 直开或 ?mock=1）：如实提示需要服务端，不发任何请求。
 * ============================================================ */
(function () {
  'use strict';

  function isMockMode() {
    try {
      const q = new URLSearchParams(location.search);
      return location.protocol === 'file:' || q.get('mock') === '1';
    } catch (e) { return location.protocol === 'file:'; }
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  let panel = null;

  function ensurePanel() {
    if (panel) return panel;
    panel = document.createElement('div');
    panel.id = 'select-panel';
    panel.setAttribute('style', [
      'position:fixed', 'inset:0', 'z-index:9999', 'display:none',
      'background:rgba(4,8,18,.72)', 'backdrop-filter:blur(4px)'
    ].join(';'));
    panel.innerHTML =
      '<div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);' +
      'width:min(560px,92vw);max-height:78vh;overflow:auto;background:#0d1526;' +
      'border:1px solid #2a3a5c;border-radius:14px;padding:18px 20px;color:#dbe6fa;' +
      'font:14px/1.6 system-ui,sans-serif;box-shadow:0 12px 48px rgba(0,0,0,.5)">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px">' +
      '<b style="font-size:16px">剧本工坊 · 生成剧本选本</b>' +
      '<button data-close="1" style="background:none;border:1px solid #2a3a5c;color:#9fb2d8;' +
      'border-radius:8px;padding:4px 10px;cursor:pointer">关闭</button></div>' +
      '<div data-body style="margin-top:12px">加载中…</div></div>';
    panel.addEventListener('click', function (ev) {
      const t = ev.target;
      if (t && (t.getAttribute('data-close') || t === panel)) { panel.style.display = 'none'; return; }
      const sid = t && t.getAttribute && t.getAttribute('data-sid');
      if (sid && window.Store && typeof window.Store.playStudio === 'function') {
        panel.style.display = 'none';
        window.Store.playStudio(sid);
      }
    });
    document.body.appendChild(panel);
    return panel;
  }

  function badge(status) {
    return status === 'ready'
      ? '<span style="color:#7ce38b">● 闸门绿 · 可开局</span>'
      : '<span style="color:#e0a04c">● 未过闸 · 不可开局</span>';
  }

  function render(items) {
    const body = panel.querySelector('[data-body]');
    if (!items || !items.length) {
      body.innerHTML = '<div style="color:#9fb2d8">还没有生成剧本。到「创作工坊」用一句话生成一个吧。</div>';
      return;
    }
    body.innerHTML = items.map(function (it) {
      const playable = it.status === 'ready';
      return '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;' +
        'border:1px solid #22314f;border-radius:10px;padding:10px 14px;margin-bottom:10px">' +
        '<div style="min-width:0"><div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' +
        esc(it.title) + '</div><div style="font-size:12px;color:#8fa3c8">' + esc(it.scenario_id) +
        ' · ' + badge(it.status) + '</div></div>' +
        (playable
          ? '<button data-sid="' + esc(it.scenario_id) + '" style="flex:none;background:#2456c4;' +
            'border:none;color:#fff;border-radius:8px;padding:7px 14px;cursor:pointer">开始游戏</button>'
          : '<span style="flex:none;color:#71809c;font-size:12px">不可选</span>') +
        '</div>';
    }).join('');
  }

  function openPanel() {
    ensurePanel();
    panel.style.display = 'block';
    const body = panel.querySelector('[data-body]');
    if (isMockMode()) {
      body.textContent = '剧本工坊需要服务端运行，当前为离线演示模式。';
      return;
    }
    body.textContent = '加载中…';
    fetch('/api/studio/catalog')
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) { render(j && j.items); })
      .catch(function (e) {
        body.textContent = '剧本目录获取失败（' + e.message + '）：请确认服务端已启动。';
      });
  }

  function ensureEntry() {
    if (document.getElementById('select-entry')) return;
    const btn = document.createElement('button');
    btn.id = 'select-entry';
    btn.type = 'button';
    btn.textContent = '剧本工坊';
    btn.setAttribute('style', 'position:fixed;left:14px;bottom:14px;z-index:9998;' +
      'background:rgba(13,21,38,.88);border:1px solid #2a3a5c;color:#dbe6fa;' +
      'border-radius:999px;padding:8px 16px;cursor:pointer;font:13px system-ui,sans-serif');
    btn.addEventListener('click', openPanel);
    document.body.appendChild(btn);
  }

  function boot() {
    if (!document.body) { setTimeout(boot, 60); return; }
    ensureEntry();
  }
  boot();
})();
