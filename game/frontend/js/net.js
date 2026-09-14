/* ============================================================
 * net.js —— WebSocket 对接层（对齐 CONTRACTS §3.6 事件协议 / §3.7 路由）
 *
 * 事件上行（client→server）：search / chat / skill / counsel / vote / advance
 * 事件下行（server→client）：search_result | chat | clue_gained | memory_unlock |
 *   counsel_result | hotfeed_refresh | faction_skill | vote | ending | danmaku | system
 * 统一包络：{ type, session_id, round, actor, payload }
 *
 * 通道选择策略（Net.init，如实上报、绝不静默造假）：
 *  - ws 地址解析顺序：opts.wsUrl → URL ?ws= → http(s) 下默认同源 ws(s)://host/ws/{session_id}；
 *  - 仅三种情况允许 MockTransport（本地引擎演示）：a) file:// 直开；b) URL 显式 ?mock=1；c) opts.mock===true；
 *    mock 通道返回值如实为 mode:'mock'、fallback:false；
 *  - WS 连接失败不再静默降级 Mock：返回 mode:'error'、fallback:true（不建传输层，send 返回 false），
 *    由体验层提示「AI 对话不可用，请重试」；
 *  - http(s) 且无任何通道地址：返回 mode:'none'、fallback:true，不建本地假 AI。
 * ============================================================ */
(function () {
  /* 每个浏览器一个稳定唯一 player_id（localStorage 持久化）——
     联机时房间靠它区分玩家；缺它则所有人动作都会被当成同一个人。 */
  function myPlayerId() {
    try {
      let pid = localStorage.getItem('kanshan_pid');
      if (!pid) {
        pid = 'player:' + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4);
        localStorage.setItem('kanshan_pid', pid);
      }
      return pid;
    } catch (e) {
      return 'player:' + Math.random().toString(36).slice(2, 8);
    }
  }

  class Emitter {
    constructor() { this._h = {}; }
    on(ev, fn) { (this._h[ev] = this._h[ev] || []).push(fn); }
    emit(ev, data) { (this._h[ev] || []).forEach(fn => { try { fn(data); } catch (e) { console.error('[net]', ev, e); } }); }
  }

  class MockTransport extends Emitter {
    constructor(engine) { super(); this.kind = 'mock'; this.engine = engine; this.sessionId = 'mock_' + Date.now().toString(36); }
    async boot() { return { session_id: this.sessionId, mode: 'mock' }; }
    send(action, payload) {
      // 本地引擎异步回放协议事件，保持与 WS 相同的时序手感
      setTimeout(() => { this.engine(action, payload, (type, pl, actor) => this._emitEvt(type, pl, actor)); }, 220 + Math.random() * 260);
    }
    _emitEvt(type, payload, actor) {
      this.emit(type, { type, session_id: this.sessionId, round: window.Store ? window.Store.state.round : 0, actor: actor || 'dm', payload });
    }
  }

  class WSTransport extends Emitter {
    constructor(url, sessionId, playerId) {
      super(); this.kind = 'ws'; this.url = url; this.sessionId = sessionId || null;
      this.playerId = playerId || myPlayerId();
      this.ws = null; this.ready = false; this.booted = false;
      this.attempts = 0; this.rcTimer = null; this.dead = false;
      this.MAX_RETRY = 6;
      this.BACKOFF = [800, 1500, 2500, 4000, 6000, 8000];
    }
    /* 连接状态广播（仅供体验层做提示，不改变任何既有事件语义） */
    _status(state, note) {
      this.emit('_status', { state: state, attempts: this.attempts, note: note || '', transport: 'ws' });
    }
    _wire(ws) {
      ws.onmessage = (m) => { try { const evt = JSON.parse(m.data); this.emit(evt.type, evt); this.emit('*', evt); } catch (e) { console.warn('[ws] bad frame', e); } };
      ws.onopen = () => {
        this.ready = true; this.booted = true; this.attempts = 0;
        clearTimeout(this.rcTimer); this.rcTimer = null;
        this._status('online', this.bootedOnce ? '实时通道已恢复' : '实时通道已建立');
        this.bootedOnce = true;
      };
      ws.onclose = () => {
        const wasReady = this.ready;
        this.ready = false; this.ws = null;
        this.emit('_closed');
        if (!wasReady && !this.bootedOnce) { this._status('offline', '连接已断开'); return; }
        if (!this.dead) this._scheduleReconnect();
      };
      return ws;
    }
    /* 断线自动重连（指数退避，上限 6 次；失败如实上报给体验层） */
    _scheduleReconnect() {
      if (this.dead || this.rcTimer) return;
      const tick = () => {
        this.rcTimer = null;
        if (this.dead || this.ready) return;
        if (this.attempts >= this.MAX_RETRY) { this._status('offline', '自动重连已达上限（' + this.MAX_RETRY + ' 次）'); return; }
        this.attempts += 1;
        this._status('reconnecting', '正在第 ' + this.attempts + ' 次重连…');
        try { this.ws = this._wire(new WebSocket(this.realUrl)); } catch (e) { this._status('offline', '重连失败：' + ((e && e.message) || '未知错误')); }
        this.rcTimer = setTimeout(tick, this.BACKOFF[Math.min(this.attempts - 1, this.BACKOFF.length - 1)]);
      };
      this._status('offline', '实时通道已断开');
      this.rcTimer = setTimeout(tick, 600);
    }
    /* 体验层「立即重连」入口 */
    retryNow() {
      if (this.dead) return false;
      this.attempts = 0;
      clearTimeout(this.rcTimer); this.rcTimer = null;
      const t = this;
      setTimeout(function () { if (!t.ready) { t.attempts = 0; t._status('reconnecting', '正在重连…'); try { t.ws = t._wire(new WebSocket(t.realUrl)); } catch (e) { t._status('offline', '重连失败'); } } }, 0);
      return true;
    }
    async boot() {
      // 1) 无 session 则先 REST 创建对局
      if (!this.sessionId) {
        const base = this.url.replace(/^ws/, 'http').split('/ws')[0];
        try {
          const apiCfg = (() => { try { return JSON.parse(localStorage.getItem('kanshan_api') || '{}'); } catch (e) { return {}; } })();
          const hdrs = { 'Content-Type': 'application/json' };
          if (apiCfg.llmBase) hdrs['X-LLM-BASE'] = apiCfg.llmBase;
          if (apiCfg.llmKey) hdrs['X-LLM-KEY'] = apiCfg.llmKey;
          if (apiCfg.llmModel) hdrs['X-LLM-MODEL'] = apiCfg.llmModel;
          if (apiCfg.zhihuSecret) hdrs['X-ZHIHU-SECRET'] = apiCfg.zhihuSecret;
          const r = await fetch(base + '/api/session', { method: 'POST', headers: hdrs, body: JSON.stringify({ mode: 'main', player_id: this.playerId }) });
          /* 服务端 /api/session 返回的是嵌套结构 { ok, session: { session_id, engine, ... } }。
             只读顶层 session_id/id 会拿到 undefined，拼出的 WS 地址会变成 /ws/undefined，
             结果是连上但立刻收到 session_not_found（表现为「对局不存在」）。
             store.js 那条建局路径读的是 sj.session.session_id，一直是对的，所以只有
             ?ws= 显式指定地址这条路会踩到 —— 这里对齐成同样的读法。 */
          const j = await r.json();
          const sess = (j && j.session) || j || {};
          this.sessionId = sess.session_id || (j && j.session_id) || (j && j.id);
          if (!this.sessionId) throw new Error('服务端未返回 session_id');
        } catch (e) { throw new Error('创建对局失败：' + e.message); }
      }
      this.realUrl = this.url.replace('{session_id}', this.sessionId);
      if (this.playerId && this.realUrl.indexOf('player_id=') < 0) {
        this.realUrl += (this.realUrl.indexOf('?') >= 0 ? '&' : '?') + 'player_id=' + encodeURIComponent(this.playerId);
      }
      // 2) 打开事件流
      return new Promise((resolve, reject) => {
        const ws = this._wire(new WebSocket(this.realUrl));
        this.ws = ws;
        ws.onopen = () => { this.ready = true; this.booted = true; this.bootedOnce = true; this.attempts = 0; this._status('online', '实时通道已建立'); resolve({ session_id: this.sessionId, mode: 'ws' }); };
        ws.onerror = () => { if (!this.ready) { this._status('offline', 'WebSocket 连接失败'); reject(new Error('WebSocket 连接失败')); } };
      });
    }
    send(action, payload) {
      if (!this.ready) return false;
      this.ws.send(JSON.stringify({ type: action, session_id: this.sessionId, round: window.Store ? window.Store.state.round : 0, actor: this.playerId, payload }));
      return true;
    }
  }

  const Net = {
    t: null,
    _lastKind: '-',
    async init(opts) {
      if (this.t && this.t.kind === 'ws') {
        this.t.dead = true;
        try { if (this.t.ws) this.t.ws.close(); } catch (e) { }
      }
      const q = new URLSearchParams(location.search);
      const proto = location.protocol;
      const explicitMock = q.get('mock') === '1' || !!(opts && opts.mock === true);
      const fileMode = proto === 'file:';   /* 评委本地直开：无服务器可言，mock 是有意为之 */
      /* ws 地址：opts.wsUrl → URL ?ws= → http(s) 下默认同源（url 为模板，含 {session_id} 占位符，
         REST base 由 WSTransport.boot 按 split('/ws')[0] 推导，见本文件 boot() 现有约定） */
      const wsUrl = (opts && opts.wsUrl) || q.get('ws')
        || (!fileMode && (proto === 'http:' || proto === 'https:')
          ? (proto === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/{session_id}'
          : '');
      if (wsUrl && !explicitMock) {
        try {
          const t = new WSTransport(wsUrl, (opts && opts.sessionId) || q.get('session'), (opts && opts.playerId) || myPlayerId());
          const info = await t.boot();
          this.t = t; this._lastKind = 'ws';
          return { ...info, fallback: false };
        } catch (e) {
          /* WS 失败禁止静默降级 Mock：不建传输层，如实上报 error，由体验层提示重试 */
          console.warn('[net] WS 连接失败，AI 对话不可用（未回退本地演示）：', e.message);
          this.t = null; this._lastKind = 'error';
          return { mode: 'error', fallback: true, err: e.message };
        }
      }
      if (explicitMock || fileMode) {
        const t = new MockTransport(window.Engine);
        const info = await t.boot(); this.t = t; this._lastKind = 'mock';
        return { ...info, fallback: false };   /* 如实：mode:'mock'、fallback:false（本地直开是有意为之） */
      }
      /* http(s) 且无通道地址：不建本地假 AI */
      this.t = null; this._lastKind = '-';
      return { mode: 'none', fallback: true, err: '未配置实时通道地址' };
    },
    send(action, payload) {
      if (!this.t) return false;
      return this.t.send(action, payload);
    },
    on(type, fn) { if (this.t) this.t.on(type, fn); },
    /* 体验层：WS 断线后的手动重试（本地自持传输返回 false） */
    retryNow() { return !!(this.t && this.t.retryNow && this.t.retryNow()); },
    id() { return this.t ? this.t.sessionId : '-'; },
    pid() { return (this.t && this.t.playerId) || myPlayerId(); },
    kind() { return this.t ? this.t.kind : '-'; }
  };

  window.myPlayerId = myPlayerId;
  window.Net = Net;
})();
