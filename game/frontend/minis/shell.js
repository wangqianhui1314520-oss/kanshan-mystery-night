/* ============================================================
 * minis/shell.js —— 小游戏统一壳（GAMEPLAY_V31 §9.2 架构约定 / minis.md 安放位图）
 * 职责：
 *   1) 注册表：每个 mini 是一个注册模块（id/标题/入口位/数据源声明/组件）；
 *   2) 路由：`#/mini/{id}` 前端 hash 路由（M2 免登录外链由静态托管直接服务，不过 session）；
 *   3) 计分/战报：成绩历史 localStorage（kanshan_minis_v1），战报模板输出；
 *   4) 分享：Canvas 合图与侦探报告同管线（logo_badge + scene_exterior + 成绩 + flavor_5 署名），
 *      只导出图片不做自动发布（铁律沿用）。
 * 依赖：主页面已加载 Vue / data.js（M 用于署名）。本文件不依赖 Store。
 * ============================================================ */
(function () {
  const SAVE_KEY = 'kanshan_minis_v1';

  /* ---------- 成绩/战报（localStorage，不上传） ---------- */
  function loadAll() {
    try { return JSON.parse(localStorage.getItem(SAVE_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function saveAll(all) {
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(all)); } catch (e) { /* 隐身模式忽略 */ }
  }
  function reportScore(id, meta) {
    const all = loadAll();
    const arr = all[id] = all[id] || [];
    const rec = { at: Date.now(), ...meta };
    arr.unshift(rec);
    if (arr.length > 20) arr.length = 20;
    saveAll(all);
    return rec;
  }
  function bestOf(id, key) {
    const arr = loadAll()[id] || [];
    return arr.reduce((b, r) => Math.max(b, Number(r[key]) || 0), 0);
  }
  function historyOf(id, n) {
    return (loadAll()[id] || []).slice(0, n || 5);
  }

  /* ---------- 分享卡（Canvas 合图，900×1200；与侦探报告同管线） ---------- */
  function wrapText(ctx, text, x, y, maxW, lh) {
    let line = '', yy = y;
    for (const ch of String(text)) {
      if (ctx.measureText(line + ch).width > maxW) { ctx.fillText(line, x, yy); line = ch; yy += lh; }
      else line += ch;
    }
    if (line) ctx.fillText(line, x, yy);
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function shareCard(mini, score) {
    const W = 900, H = 1200;
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d');
    const img = src => new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
    const M = window.MOCK || {};
    const stat = (score.lines || []).map(l => [l[0], String(l[1])]);
    return Promise.all([
      img('../content/assets/images/scene_exterior.png'),
      img('../content/assets/images/logo_badge.png'),
      img('../content/assets/official/kanshan/kanshan.png')
    ]).then(([bg, logo, ks]) => {
      if (bg) { const s = Math.max(W / bg.width, H / bg.height); ctx.drawImage(bg, (W - bg.width * s) / 2, (H - bg.height * s) / 2, bg.width * s, bg.height * s); }
      const grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, 'rgba(5,9,20,.9)'); grad.addColorStop(.5, 'rgba(5,9,20,.74)'); grad.addColorStop(1, 'rgba(5,9,20,.94)');
      ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = 'rgba(0,132,255,.5)'; ctx.lineWidth = 3; roundRect(ctx, 24, 24, W - 48, H - 48, 20); ctx.stroke();
      if (logo) ctx.drawImage(logo, 60, 56, 84, 84);
      ctx.fillStyle = '#dbe6fa'; ctx.font = 'bold 40px "Microsoft YaHei"';
      ctx.fillText('求真档案局 · 迷你游戏厅', 160, 98);
      ctx.fillStyle = '#4da8ff'; ctx.font = '22px Consolas';
      ctx.fillText('KANSHAN MINI GAMES / 知乎黑客松 2026', 160, 134);
      // mini 标题 + 一句话
      ctx.fillStyle = '#f5c451'; ctx.font = 'bold 56px "Microsoft YaHei"';
      ctx.fillText(mini.title, 60, 240);
      ctx.fillStyle = '#8296bd'; ctx.font = '24px "Microsoft YaHei"';
      wrapText(ctx, mini.tagline || '', 60, 282, W - 130, 34);
      // 成绩行
      ctx.font = '26px "Microsoft YaHei"';
      stat.forEach((r, i) => {
        const x = 60 + (i % 2) * 400, y = 380 + Math.floor(i / 2) * 72;
        ctx.fillStyle = 'rgba(0,132,255,.12)'; roundRect(ctx, x, y - 30, 370, 54, 12); ctx.fill();
        ctx.fillStyle = '#8296bd'; ctx.fillText(r[0], x + 18, y + 7);
        ctx.fillStyle = '#6fe3ff'; ctx.font = 'bold 26px Consolas'; ctx.fillText(r[1], x + 200, y + 7);
        ctx.font = '26px "Microsoft YaHei"';
      });
      // 战报一句话
      const ry = 380 + Math.ceil(stat.length / 2) * 72 + 30;
      ctx.fillStyle = '#dbe6fa'; ctx.font = '26px "Microsoft YaHei"';
      wrapText(ctx, score.report || '', 60, ry, W - 130, 40);
      // 看山印章（雪碧图第 1 行站立挥手帧）
      if (ks && ks.width) { try { cv.getContext('2d').drawImage(ks, 0, 0, 110, 124, W - 170, ry + 30, 110, 124); } catch (e) { } }
      // 署名小字（flavor_5 常驻）
      ctx.fillStyle = 'rgba(130,150,189,.85)'; ctx.font = '18px "Microsoft YaHei"';
      wrapText(ctx, M.flavor5Credit || '本局由刘看山亲自策划——策划你的策划。', 60, H - 120, W - 130, 26);
      const done = blob => blob;
      return new Promise(res => {
        if (cv.toBlob) cv.toBlob(b => res(done(b)), 'image/png');
        else { try { res(done(dataURLtoBlob(cv.toDataURL('image/png')))); } catch (e) { res(null); } }
      });
    });
  }
  function dataURLtoBlob(dataurl) {
    const [h, b64] = dataurl.split(','), mime = h.match(/:(.*?);/)[1];
    const bin = atob(b64), u8 = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    return new Blob([u8], { type: mime });
  }
  function download(mini, score) {
    return shareCard(mini, score).then(blob => {
      if (!blob) return { ok: false, notice: '导出失败（file:// 直开受 Canvas 安全限制）——用 http 服务打开，或直接截图分享。' };
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'mini_' + mini.id + '_' + Date.now() + '.png';
      a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      return { ok: true };
    });
  }

  /* ---------- 注册表与路由 ---------- */
  const REG = {};   // id -> def {id, title, tagline, entry, source, component}
  function register(def) { REG[def.id] = def; }
  function currentId() {
    const m = (location.hash || '').match(/^#\/mini\/([\w-]+)/);
    return m ? m[1] : null;
  }
  function open(id) { location.hash = '#/mini/' + id; }
  function close() { location.hash = ''; }

  window.Minis = { REG, register, currentId, open, close, reportScore, bestOf, historyOf, download, shareCard };
})();
