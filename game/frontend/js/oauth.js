/* ============================================================
 * js/oauth.js —— 知乎 OAuth 回调接收器（MEGA_MODE §一 / 契约 v2.1）
 *
 * 职责（仅此两件事，零副作用）：
 *   1. 页面加载时捕获知乎授权回跳带来的 code（实测回调参数为
 *      authorization_code，兼容 code），存入 sessionStorage；
 *   2. history.replaceState 清掉 query——防止刷新重放 code、避免
 *      URL 里的授权码被截图/分享泄露。
 *
 * code 的实际消费在侦探档案页（badge）：有对局 session 时
 * POST /api/session/{id}/login 换 token 并签发《特聘侦探证》。
 * token 只存服务端内存；本文件不接触 token，只搬运一次性 code。
 * ============================================================ */
(function () {
  'use strict';

  var KEY = 'kanshan_oauth_code';

  /** 页面加载即捕获：知乎回跳 redirect_uri?authorization_code=..&state=.. */
  function captureFromUrl() {
    try {
      var q = new URLSearchParams(location.search);
      var code = (q.get('authorization_code') || q.get('code') || '').trim();
      if (!code) return;
      sessionStorage.setItem(KEY, code);
      // 清 query 保留 hash；无 hash 时落到侦探档案页（code 消费入口）
      var hash = location.hash || '#/mini/badge';
      history.replaceState(null, '', location.pathname + hash);
    } catch (e) { /* 隐私模式等场景静默降级：不影响游戏 */ }
  }

  /** 供 badge 等调用：消费已捕获的 code，换取登录态。
   *  返回 {attempted, ok, notice} —— attempted=false 表示无可消费 code。 */
  async function consume(sessionId, playerId) {
    var code = '';
    try { code = sessionStorage.getItem(KEY) || ''; } catch (e) { }
    if (!code) return { attempted: false, ok: false, notice: '' };
    if (!sessionId) {
      // code 未消费：保留（知乎 code 有时效，约 10 分钟），建局后再回来签发
      return { attempted: false, ok: false,
               notice: '已拿到知乎授权，但还没有对局——建局后回到侦探档案页即可自动签发。' };
    }
    try {
      var r = await fetch('/api/session/' + encodeURIComponent(sessionId) + '/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_id: playerId || 'player:1', code: code })
      });
      var j = await r.json();
      // 原子消费：无论成败都清掉（知乎侧 code 一次性，重试无意义）
      try { sessionStorage.removeItem(KEY); } catch (e) { }
      if (r.ok && j.ok) return { attempted: true, ok: true, data: j };
      return { attempted: true, ok: false, notice: (j && j.detail) || ('登录失败 HTTP ' + r.status) };
    } catch (e) {
      try { sessionStorage.removeItem(KEY); } catch (e2) { }
      return { attempted: true, ok: false, notice: '登录请求发送失败，请重试。' };
    }
  }

  function hasPendingCode() {
    try { return !!sessionStorage.getItem(KEY); } catch (e) { return false; }
  }

  captureFromUrl();
  window.ZhihuOAuthFlow = { consume: consume, hasPendingCode: hasPendingCode };
})();
