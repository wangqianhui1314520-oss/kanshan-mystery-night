/* ============================================================
 * ux.js —— 体验层：引擎状态探针 / 三态占位 / 首屏新手引导 / HUD 数字动效
 * 规约：零新增依赖（仅用全局 Vue + 原生 API）；不改动既有事件语义；
 *       fail-safe：任何异常都退化为静默，不影响既有对局流程。
 * ============================================================ */
(function () {
  const { reactive, ref, computed, watch, onMounted, onBeforeUnmount, nextTick } = Vue;

  /* ------------------------------------------------------------------
   * 一、引擎状态探针（消费 GET /api/health，只读，不改服务端）
   *  - engine.mode === 'engine' → 规则引擎 · 确定性裁决
   *  - 其他已知模式            → 如实显示服务端自己的降级说明
   *  - 请求失败                → 引擎状态未知（离线）
   * ---------------------------------------------------------------- */
  const engine = reactive({
    probe: 'loading',          // loading | ok | degraded | offline
    mode: 'unknown',           // engine | unknown
    label: '正在核对引擎…',
    tone: 'pending',
    detail: '正在核对引擎状态',
    checkedAt: 0
  });

  // AI 能力状态与规则引擎分开显示：规则引擎在线不代表 NPC 模型已可用。
  const ai = reactive({
    provider: '检测中…', zhida: false,
    state: 'loading', label: '正在检测 AI', detail: '正在核对 NPC AI 配置', seats: []
  });

  const ENGINE_TEXT = {
    ok: { label: '规则引擎 · 确定性裁决', tone: 'ok' },
    degraded: { label: '规则引擎 · 降级模式', tone: 'warn' },
    offline: { label: '引擎状态未知（离线）', tone: 'offline' },
    loading: { label: '正在核对引擎…', tone: 'pending' }
  };

  function parseHealth(j) {
    const eng = (j && j.engine) || {};
    const a = (j && j.ai) || {};
    Object.assign(ai, {
      provider: a.npc_provider || '未声明',
      zhida: !!a.zhida_available,
      state: a.state || 'unknown',
      label: ({configured: 'AI 已配置 · 首次发言时验证', missing: 'AI 未配置',
        success: 'AI 最近调用成功', failed: 'AI 最近调用失败',
        cache: 'AI 最近使用缓存', offline_demo: '离线演示 · 非实时 AI'})[a.state] || 'AI 状态未确认',
      detail: a.notice || '服务端未提供新版 AI 状态，请重启服务后重新检测。',
      seats: Array.isArray(a.seats) ? a.seats : []
    });
    const rawNotice = (window.Labels && window.Labels.plain(eng.notice, '')) || String(eng.notice || '');
    const notice = rawNotice.replace(/\bengine\/\s*/gi, '规则引擎 · ').replace(/\s+/g, ' ').trim();
    if (eng.mode === 'engine' && eng.available !== false) {
      return { probe: 'ok', mode: 'engine', detail: notice || '服务端已接确定性规则引擎：七模块裁决，同样输入必得同样结果。' };
    }
    if (eng.mode) {
      // 服务端明确上报了非引擎模式：如实呈现它的说明，不臆造也不美化
      return { probe: 'degraded', mode: String(eng.mode), detail: notice || '服务端当前为降级模式，部分裁决可能简化。' };
    }
    return { probe: 'degraded', mode: 'unknown', detail: notice || '健康检查返回体未声明引擎模式。' };
  }

  let probeId = 0;
  async function probeEngine(opts) {
    const id = ++probeId;
    const timeout = (opts && opts.timeout) || 4000;
    if (typeof fetch !== 'function') {
      Object.assign(engine, ENGINE_TEXT.offline, { probe: 'offline', mode: 'unknown', detail: '当前环境不支持网络请求，无法核对服务端引擎状态。' });
      Object.assign(ai, {state: 'offline', label: 'AI 状态无法检测', detail: '无法访问服务端。', seats: []});
      return engine;
    }
    if (!opts || opts.silent !== true) {
      Object.assign(engine, ENGINE_TEXT.loading, { probe: 'loading', detail: '正在核对引擎状态' });
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const sid = window.Store && window.Store.state && window.Store.state.sessionId;
      const url = '/api/health' + (sid && !sid.startsWith('mock_') ? '?session_id=' + encodeURIComponent(sid) : '');
      const headers = {Accept: 'application/json'};
      /* 设置面板的配置保存在本机；健康探针也必须携带它，
         否则服务端只能看到环境变量，误报“未配置”。 */
      try {
        const cfg = JSON.parse(localStorage.getItem('kanshan_api') || '{}');
        if (cfg.llmBase) headers['X-LLM-BASE'] = cfg.llmBase;
        if (cfg.llmKey) headers['X-LLM-KEY'] = cfg.llmKey;
        if (cfg.llmModel) headers['X-LLM-MODEL'] = cfg.llmModel;
        if (cfg.zhihuSecret) headers['X-ZHIHU-SECRET'] = cfg.zhihuSecret;
      } catch (e) { /* 本地存储不可用时仍执行无凭证探针 */ }
      const res = await fetch(url, {cache: 'no-store', headers, signal: controller.signal});
      if (!res || !res.ok) throw new Error('HTTP ' + ((res && res.status) || '—'));
      const data = await res.json();
      if (id !== probeId) return engine;
      const parsed = parseHealth(data);
      Object.assign(engine, ENGINE_TEXT[parsed.probe], parsed, { checkedAt: Date.now() });
    } catch (e) {
      if (id !== probeId) return engine;
      Object.assign(ai, {state: 'offline', label: 'AI 状态无法检测', detail: '服务端未响应，不能确认模型状态。', seats: []});
      Object.assign(engine, ENGINE_TEXT.offline, {
        probe: 'offline', mode: 'unknown',
        detail: '引擎连不上（' + (e && e.message ? e.message : '网络异常') + '）——点击可重试。',
        checkedAt: Date.now()
      });
    } finally {
      clearTimeout(timer);
    }
    return engine;
  }

  async function testAi() {
    try {
      const cfg = JSON.parse(localStorage.getItem('kanshan_api') || '{}');
      const headers = {'Content-Type':'application/json'};
      if (cfg.llmBase) headers['X-LLM-BASE']=cfg.llmBase;
      if (cfg.llmKey) headers['X-LLM-KEY']=cfg.llmKey;
      if (cfg.llmModel) headers['X-LLM-MODEL']=cfg.llmModel;
      if (cfg.zhihuSecret) headers['X-ZHIHU-SECRET']=cfg.zhihuSecret;
      const r = await fetch('/api/ai/test',{method:'POST',headers,body:'{}'});
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || '请求失败');
      const prov = j.provider === 'main' ? (j.model || '自建模型(main)') : '知乎直答(zhida)';
      /* panel_fallback：面板填的凭证连接失败，服务端已回落赛事默认通道——
         必须如实标红并带出真实错误（key 失效/模型名错/网络），否则用户会误判。 */
      if (j.panel_fallback) {
        Object.assign(ai,{state:'failed',label:'面板凭证无效（已回落）',
          detail:'面板填写的模型连接失败：' + (j.panel_error || '未知错误')
            + '。探针已回落赛事默认通道（' + prov + '）——请核对面板的 API 地址 / API Key / 模型名。'});
        return false;
      }
      Object.assign(ai,{state:'success',label:'AI 调用成功',provider:prov,
        detail:'真实请求成功 · ' + j.elapsed_ms + 'ms · 实际通道：' + prov});
      return true;
    } catch(e) {
      Object.assign(ai,{state:'failed',label:'AI 调用失败',detail:String(e.message || e)});
      return false;
    }
  }

  /* ------------------------------------------------------------------
   * 二、连接状态（WS 断线 / 重连反馈）
   * ---------------------------------------------------------------- */
  const conn = reactive({
    state: 'idle',      // idle | online | reconnecting | offline
    attempts: 0,
    note: '',
    transport: ''
  });

  /* ------------------------------------------------------------------
   * 三、首屏新手引导（单人自助体验：没有主持人，只能靠它）
   * ---------------------------------------------------------------- */
  const GUIDE_KEY = 'kanshan_onboarded_v1';

  const GUIDE_STEPS = [
    {
      id: 'file', tour: 'hud', tag: '① 立案',
      title: '这是一桩「没人承认的失踪」',
      desc: '周五盘点夜，21:00 首席荣誉侦探刘看山进档案室后失踪。大门横幅写着——不出真相，不出此门。23:00 封控确认后你被特许入局。今晚你要对抗的不只是嫌疑人，更是信息被操纵的方式。'
    },
    {
      id: 'chat', tour: 'chat', tag: '② 圆桌对话',
      title: '先上桌提问：听口供，也听心跳',
      desc: '八位当事人由 AI 实时演出，各怀立场与隐瞒。追问他们说法里的矛盾点——口供会漏，心声漏得更多。'
    },
    {
      id: 'map', tour: 'map', tag: '③ 现场搜证',
      title: '别只信他们说的，去现场自己看',
      desc: '进入「现场搜证」：选地点 → 输入关键词（消耗 1 行动点）。线索进「个人证物袋」；凑齐 3 条指向同一真相节点的线索，会自动合成证据卡。'
    },
    {
      id: 'kcards', tour: 'kcards', tag: '④ 知识开导',
      title: '用知乎知识卡，给一颗心松土',
      desc: '第二章解锁「记忆修复」和「污染对照」：口供与心声对不上=篡改点；同一篇知乎原文被水军改写后，圈出真正植入的 3 处——看起来像操纵的，也可能是作者原句。'
    },
    {
      id: 'hotfeed', tour: 'hotfeed', tag: '⑤ 热搜舆论',
      title: '热度升起来的时候，真相会缺氧',
      desc: '第三章「热搜面板」：你可以买热搜，也可以辟谣。买热搜会把热度推上去，辟谣必须用对知识卡——引错卡会被当事人当场群嘲。对照赢来的弹药，在辟谣成功时会再压一截热度。'
    },
    {
      id: 'vote', tour: 'vote', tag: '⑥ 圆桌指认',
      title: '收网：至少 2 张证据卡才能锤人',
      desc: '终局先过回声档案（你说过的话会被投影）和 AI 法官（热度越高他越怀疑你），再提交指认。集齐 5 个看山破绽可指控 DM。通关拿到五维求真画像。'
    }
  ];

  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 隐私模式下静默 */ } }

  const isOnboarded = () => !!lsGet(GUIDE_KEY);
  const markOnboarded = () => lsSet(GUIDE_KEY, String(Date.now()));
  function resetOnboarded() { try { localStorage.removeItem(GUIDE_KEY); } catch (e) { /* noop */ } }

  /* ------------------------------------------------------------------
   * 四、组件
   * ---------------------------------------------------------------- */
  const comps = {
    /* ---- 三态占位：空 / 加载中 / 错误（含 WS 断线） ---- */
    'ux-state': {
      props: {
        mode: { type: String, default: 'empty' },   // empty | loading | error
        glyph: { type: String, default: '▦' },
        title: { type: String, default: '' },
        desc: { type: String, default: '' },
        action: { type: String, default: '' },
        dense: Boolean
      },
      emits: ['action'],
      template: `<div class="ux-state" :class="[mode, { dense }]"
        :role="mode === 'loading' ? 'status' : null" :aria-live="mode === 'loading' ? 'polite' : null">
        <span class="uxs-art" aria-hidden="true">
          <i v-if="mode === 'loading'" class="uxs-spin"></i>
          <i v-else class="uxs-glyph">{{ mode === 'error' ? '⚠' : glyph }}</i>
        </span>
        <b class="uxs-title">{{ title || '这里还什么都没有' }}</b>
        <p class="uxs-desc" v-if="desc">{{ desc }}</p>
        <button v-if="action" class="btn sm ghost uxs-btn" type="button" @click="$emit('action')">{{ action }}</button>
      </div>`
    },

    /* ---- HUD 数字：变化时轻量跳动（≤300ms，尊重 reduced-motion） ---- */
    'ux-num': {
      props: { value: { type: [Number, String], default: 0 } },
      setup(props) {
        const pop = ref(false);
        let timer = null;
        watch(() => props.value, () => {
          clearTimeout(timer);
          pop.value = false;
          requestAnimationFrame(() => { requestAnimationFrame(() => { pop.value = true; }); });
          timer = setTimeout(() => { pop.value = false; }, 240);
        });
        onBeforeUnmount(() => clearTimeout(timer));
        return { cls: computed(() => ({ pop: pop.value })) };
      },
      template: `<b class="ux-num" :class="cls">{{ value }}</b>`
    },

    /* ---- 首屏新手引导 ---- */
    'ux-guide': {
      props: { open: Boolean },
      emits: ['close'],
      setup(props, ctx) {
        const i = ref(0);
        const spot = ref(null);
        const nextBtn = ref(null);
        const total = GUIDE_STEPS.length;
        const step = computed(() => GUIDE_STEPS[i.value] || GUIDE_STEPS[0]);
        const isLast = computed(() => i.value === total - 1);
        const hasSpot = computed(() => !!spot.value);

        let raf = 0;
        function measure() {
          if (!props.open || typeof document === 'undefined' || !document.querySelector) { spot.value = null; return; }
          const el = (typeof document !== 'undefined' && document.querySelector)
            ? (document.querySelector('[data-tour="' + step.value.tour + '"]') || document.querySelector('[data-tour="next"]'))
            : null;
          if (!el) { spot.value = null; return; }
          const r = el.getBoundingClientRect();
          if (!r.width || !r.height) { spot.value = null; return; }
          const pad = 6;
          spot.value = {
            x: Math.round(r.left - pad), y: Math.round(r.top - pad),
            w: Math.round(r.width + pad * 2), h: Math.round(r.height + pad * 2)
          };
        }
        function scheduleMeasure() {
          if (typeof requestAnimationFrame !== 'function') return;
          cancelAnimationFrame(raf);
          raf = requestAnimationFrame(measure);
        }
        const onWin = () => measure();

        watch(() => props.open, async (v) => {
          if (v) {
            i.value = 0;
            await nextTick();
            scheduleMeasure();
            setTimeout(() => { if (nextBtn.value && nextBtn.value.focus) nextBtn.value.focus(); }, 40);
          } else {
            spot.value = null;
          }
        }, { immediate: true });
        watch(i, scheduleMeasure);

        const next = () => { if (isLast.value) finish(); else i.value += 1; };
        const prev = () => { if (i.value > 0) i.value -= 1; };
        const finish = () => { markOnboarded(); ctx.emit('close'); };
        const skip = () => { markOnboarded(); ctx.emit('close'); };
        const goTo = (n) => { i.value = n; };

        function onKey(e) {
          if (!props.open || !e) return;
          if (e.key === 'Escape') { e.preventDefault(); skip(); }
          else if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
          else if (e.key === 'ArrowLeft') { e.preventDefault(); prev(); }
        }

        onMounted(() => {
          if (typeof window === 'undefined') return;
          window.addEventListener('resize', onWin);
          window.addEventListener('scroll', onWin, true);
          window.addEventListener('keydown', onKey);
          if (document.addEventListener) document.addEventListener('keydown', onKey);
        });
        onBeforeUnmount(() => {
          if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(raf);
          if (typeof window === 'undefined') return;
          window.removeEventListener('resize', onWin);
          window.removeEventListener('scroll', onWin, true);
          window.removeEventListener('keydown', onKey);
          if (document.removeEventListener) document.removeEventListener('keydown', onKey);
        });

        const spotStyle = computed(() => spot.value
          ? { left: spot.value.x + 'px', top: spot.value.y + 'px', width: spot.value.w + 'px', height: spot.value.h + 'px' }
          : null);
        const cardStyle = computed(() => {
          if (!spot.value || typeof window === 'undefined') return null;
          const vw = window.innerWidth, vh = window.innerHeight;
          const w = Math.min(vw - 24, 380);
          let left = spot.value.x + spot.value.w / 2 - w / 2;
          left = Math.max(12, Math.min(left, vw - w - 12));
          const below = spot.value.y + spot.value.h + 12;
          const cardH = 260;
          const top = (below + cardH < vh) ? below : Math.max(12, spot.value.y - cardH - 12);
          return { left: left + 'px', top: top + 'px', width: w + 'px' };
        });

        return { i, total, step, isLast, next, prev, finish, skip, nextBtn, spotStyle, cardStyle, steps: GUIDE_STEPS, goTo, hasSpot };
      },
      template: `<transition name="ugfade">
        <div class="ux-guide" v-if="open" role="dialog" aria-modal="true" aria-labelledby="ux-guide-title">
          <div class="ug-dim" @click="skip"></div>
          <div class="ug-spot" v-if="spotStyle" :style="spotStyle" aria-hidden="true"></div>
          <div class="ug-card" :class="{ floating: hasSpot }" :style="cardStyle">
            <header class="ug-hd">
              <span class="ug-tag mono">{{ step.tag }}</span>
              <span class="ug-step mono">{{ i + 1 }}/{{ total }}</span>
            </header>
            <h3 id="ux-guide-title">{{ step.title }}</h3>
            <p class="ug-desc">{{ step.desc }}</p>
            <div class="ug-dots" role="tablist" aria-label="引导步骤">
              <button v-for="(s, n) in steps" :key="s.id" class="ug-dot" :class="{ on: n === i }" type="button"
                      role="tab" :aria-selected="n === i" :aria-label="'第 ' + (n + 1) + ' 步 · ' + s.tag"
                      @click="goTo(n)"></button>
            </div>
            <footer class="ug-ft">
              <button class="btn ghost sm" type="button" @click="skip">跳过引导</button>
              <div class="ug-ft-r">
                <button class="btn ghost sm" type="button" v-if="i > 0" @click="prev">上一步</button>
                <button class="btn primary sm" type="button" ref="nextBtn" @click="next">{{ isLast ? '开始调查 ▸' : '下一步 ▸' }}</button>
              </div>
            </footer>
          </div>
        </div></transition>`
    }
  };

  function install(app) {
    Object.entries(comps).forEach(([name, def]) => app.component(name, def));
  }

  window.UX = { engine, ai, conn, probeEngine, testAi, install, comps, GUIDE_STEPS, GUIDE_KEY, isOnboarded, markOnboarded, resetOnboarded };
})();
