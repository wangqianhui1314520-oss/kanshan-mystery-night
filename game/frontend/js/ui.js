/* ============================================================
 * ui.js —— 共享 UI 组件（HUD 芯片 / 弹幕层 / 卡片 / 手绘 SVG 场景）
 * 美术规约：真图 content/assets/images + CSS/SVG 手绘，零外链零占位。
 * ============================================================ */
(function () {
  const M = window.MOCK;
  const { ref, computed, watch } = Vue;  // bet-panel 等组合式 API 依赖（此前未解构，setup 抛 ReferenceError 致组件降级渲染）

  /* ---- 手绘 SVG 场景（无真图的地点用，规约③代码绘制） ---- */
  function svgScene(id) {
    const wrap = inner => `<svg class="scene-svg" viewBox="0 0 400 180" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="bg${id}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0d1424"/><stop offset="1" stop-color="#0a0e19"/>
        </linearGradient>
        <linearGradient id="glow${id}" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#0084ff" stop-opacity=".9"/><stop offset="1" stop-color="#0084ff" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <rect width="400" height="180" fill="url(#bg${id})"/>
      <g stroke="#1f2c4a" stroke-width="1">${[30,60,90,120,150].map(y=>`<line x1="0" y1="${y}" x2="400" y2="${y}"/>`).join('')}</g>
      <rect x="0" y="176" width="400" height="4" fill="url(#glow${id})"/>
      ${inner}
    </svg>`;
    const S = 'stroke="#5f8fd8" fill="none" stroke-width="2" stroke-linecap="round"';
    const B = 'stroke="#0084ff" fill="none" stroke-width="2" stroke-linecap="round"';
    const map = {
      loc_desk: `<rect x="60" y="120" width="200" height="10" rx="3" ${S}/><rect x="72" y="130" width="8" height="34" ${S}/><rect x="240" y="130" width="8" height="34" ${S}/>
        <rect x="110" y="70" width="86" height="50" rx="4" ${S}/><rect x="116" y="76" width="74" height="38" rx="2" fill="#0f1a30" stroke="#2c4370"/>
        <path d="M196 118 h80" ${S}/><rect x="206" y="96" width="34" height="22" rx="2" ${B}/>
        <path d="M212 100 l14 0 M212 105 l20 0 M212 110 l10 0" stroke="#0084ff" stroke-width="1.5"/>
        <rect x="292" y="92" width="26" height="30" rx="3" ${S}/><path d="M296 100 q6 -8 12 0 q4 6 8 0" ${B}/>
        <circle cx="150" cy="58" r="3" fill="#0084ff" opacity=".9"><animate attributeName="opacity" values=".9;.2;.9" dur="2.4s" repeatCount="indefinite"/></circle>`,
      loc_archive: `<g ${S}>${[0,1,2,3].map(r=>`<rect x="52" y="${26+r*34}" width="150" height="26" rx="3"/>`).join('')}</g>
        ${[0,1,2,3].map(r=>[0,1,2,3,4].map(c=>`<rect x="${60+c*28}" y="${32+r*34}" width="18" height="14" rx="2" fill="#111b31" stroke="#27406e"/>`).join('')).join('')}
        <rect x="200" y="60" width="150" height="92" rx="4" ${S}/>
        <rect x="236" y="92" width="52" height="30" rx="3" fill="#0d1e38" stroke="#0084ff"/>
        <text x="262" y="111" text-anchor="middle" fill="#7db8ff" font-size="10" font-family="Consolas">S-07</text>
        <circle cx="330" cy="70" r="3" fill="#0084ff"><animate attributeName="opacity" values="1;.2;1" dur="1.8s" repeatCount="indefinite"/></circle>`,
      loc_ac: `<circle cx="150" cy="86" r="52" ${S}/><circle cx="150" cy="86" r="14" ${B}/>
        <g ${B}><animateTransform attributeName="transform" type="rotate" from="0 150 86" to="360 150 86" dur="6s" repeatCount="indefinite"/>
        ${[0,60,120,180,240,300].map(a=>`<path d="M150 86 q${Math.cos(a*Math.PI/180)*38} ${Math.sin(a*Math.PI/180)*38} ${Math.cos((a+14)*Math.PI/180)*46} ${Math.sin((a+14)*Math.PI/180)*46}"/>`).join('')}</g>
        <rect x="238" y="46" width="110" height="80" rx="4" ${S}/>
        <rect x="250" y="60" width="86" height="40" rx="2" fill="#0c1730" stroke="#27406e"/>
        <text x="256" y="76" fill="#7db8ff" font-size="9" font-family="Consolas">WAKE&gt;_</text>
        <text x="256" y="90" fill="#3f5f96" font-size="9" font-family="Consolas">LOCK:███</text>
        <path d="M60 160 h280" ${S}/>`,
      loc_locker: `<g ${S}>${[0,1,2,3,4].map(c=>`<rect x="${48+c*58}" y="34" width="50" height="118" rx="3"/>`).join('')}</g>
        ${[0,1,2,3,4].map(c=>[0,1,2].map(r=>`<rect x="${54+c*58}" y="${42+r*36}" width="38" height="28" rx="2" fill="#101a30" stroke="#26406c"/>`).join('')).join('')}
        <rect x="286" y="150" width="12" height="4" fill="#ff4d5e"><animate attributeName="opacity" values="1;.15;1" dur="1.1s" repeatCount="indefinite"/></rect>
        <circle cx="292" cy="152" r="6" fill="none" stroke="#ff4d5e" stroke-width="1.5"><animate attributeName="r" values="3;9" dur="1.1s" repeatCount="indefinite"/><animate attributeName="opacity" values=".9;0" dur="1.1s" repeatCount="indefinite"/></circle>`,
      loc_clinic: `<path d="M80 150 q-24 -40 8 -52 q22 -8 34 12 q12 -20 34 -12 q32 12 8 52 q-20 28 -42 40 q-22 -12 -42 -40z" transform="translate(0,-8)" fill="rgba(0,132,255,.08)" stroke="#0084ff" stroke-width="2"/>
        <rect x="236" y="60" width="96" height="66" rx="4" ${S}/><path d="M244 76 q20 -14 40 0 q20 14 40 0 v34 q-20 14 -40 0 q-20 -14 -40 0z" ${B}/>
        <path d="M262 52 v-16 M262 36 l14 10 M262 36 l-14 10" ${S}/>
        <circle cx="262" cy="34" r="4" fill="#ffd76a"/>
        <path d="M118 128 l16 -10 l16 10 M118 142 l16 -10 l16 10" stroke="#7db8ff" stroke-width="1.5" fill="none"/>`
    };
    return wrap(map[id] || '');
  }

  /* ---- 导航图标 ---- */
  const ICONS = {
    map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14"/>',
    chat: '<path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"/><path d="M8 10h8M8 14h5"/>',
    bag: '<path d="M6 8h12l1 12H5L6 8z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    cards: '<rect x="4" y="6" width="12" height="15" rx="2"/><path d="M9 3h10a1 1 0 0 1 1 1v13"/>',
    memory: '<rect x="4" y="4" width="16" height="7" rx="1.5"/><rect x="4" y="13" width="16" height="7" rx="1.5"/><path d="M8 7.5h5M11 16.5h5"/>',
    fire: '<path d="M12 3s5 4 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-5 0 2 1 3 2 3 0-3 1-5 1-7z"/>',
    table: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 4v5M12 15v5M4 12h5M15 12h5"/>',
    heart: '<path d="M12 20s-7-4.5-9-9a4.6 4.6 0 0 1 8-3 4.6 4.6 0 0 1 8 3c-2 4.5-7 9-7 9z"/><path d="M12 9v4M10 11h4"/>',
    scroll: '<path d="M7 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M9 8h7M9 12h7M9 16h4"/>',
    gear: '<circle cx="12" cy="12" r="3.2"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
    badge: '<path d="M12 3l7 3v5c0 4.5-3 8.4-7 10-4-1.6-7-5.5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
    camera: '<rect x="3" y="7" width="18" height="13" rx="2"/><circle cx="12" cy="13.5" r="4"/><path d="M9 7l1.5-3h3L15 7"/>',
    compare: '<rect x="3" y="5" width="8" height="14" rx="1"/><rect x="13" y="5" width="8" height="14" rx="1"/><path d="M7 9h0.1M7 12h0.1M17 9h0.1M17 12h0.1"/>'
  };

  const TIER_META = {
    public: { label: '公开', cls: 't-public' },
    limited: { label: '限定', cls: 't-limited' },
    hidden: { label: '隐藏', cls: 't-hidden' },
    fake: { label: '伪造?', cls: 't-fake' },
    boss_flaw: { label: '看山破绽', cls: 't-boss' }
  };

  window.UI = { svgScene, ICONS, TIER_META };

  const comps = {
    'ui-icon': {
      props: { name: String },
      template: `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" v-html="ICONS[name]||''"></svg>`,
      created() { this.ICONS = window.UI.ICONS; },
      data() { return { ICONS: window.UI.ICONS }; }
    },
    'ui-chip': {
      props: ['tone'],
      template: `<span class="chip" :class="tone"><slot></slot></span>`
    },
    'ui-modal': {
      props: { title: String, wide: Boolean },
      emits: ['close'],
      template: `<transition name="fade">
        <div class="modal-mask" @click.self="$emit('close')">
          <div class="modal" :class="{wide}">
            <header class="modal-hd">
              <h3>{{title}}</h3>
              <button class="btn ghost sm" @click="$emit('close')">✕</button>
            </header>
            <div class="modal-bd"><slot></slot></div>
          </div>
        </div></transition>`
    },
    'danmaku-layer': {
      props: { items: Array },
      template: `<div class="danmaku-layer" aria-hidden="true">
        <span v-for="d in items" :key="d.id" class="dm-item" :class="d.cls"
              :style="{ top: d.top + '%', animationDelay: d.delay + 's' }">{{ d.text }}</span>
      </div>`
    },
    'heat-gauge': {
      props: { value: { type: Number, default: 0 } },
      computed: {
        arc() { const v = Math.max(0, Math.min(100, this.value)); const a = Math.PI * (1 - v / 100); return { x: 60 + 46 * Math.cos(a), y: 60 - 46 * Math.sin(a) }; },
        color() { return this.value >= 80 ? '#ff4d5e' : this.value >= 55 ? '#ffb648' : '#00e5a8'; }
      },
      template: `<div class="heat-gauge">
        <svg viewBox="0 0 120 74">
          <path d="M14 60 A46 46 0 0 1 106 60" fill="none" stroke="#1c2a4a" stroke-width="8" stroke-linecap="round"/>
          <path d="M14 60 A46 46 0 0 1 106 60" fill="none" :stroke="color" stroke-width="8" stroke-linecap="round"
                :stroke-dasharray="144.5" :stroke-dashoffset="144.5 * (1 - Math.min(100,value)/100)"/>
          <text x="60" y="56" text-anchor="middle" class="gauge-num" :fill="color">{{ value }}</text>
          <text x="60" y="70" text-anchor="middle" class="gauge-cap">舆论热度</text>
        </svg>
      </div>`
    },
    'clue-card': {
      props: { clue: Object, compact: Boolean },
      data() { return { meta: window.UI.TIER_META }; },
      emits: ['open'],
      computed: {
        t() { return this.meta[this.clue.tier] || this.meta.public; },
        thumb() { return (window.ASSETS && window.ASSETS.clueThumb(this.clue)) || ''; },
        access() {
          const map = { public: '可公开', limited: '仅持有者可见', hidden: '隐藏线索', fake: '公开池·存疑', boss_flaw: '隐藏伏笔', core: '核心证据' };
          return map[this.clue.tier] || '可公开';
        }
      },
      template: `<button class="clue-card" :class="[t.cls, {compact}]" @click="$emit('open', clue)">
        <span class="cc-thumb" v-if="thumb && !compact"><img :src="thumb" alt=""></span>
        <span class="cc-tier">{{ t.label }}</span>
        <span class="cc-name">{{ clue.name }}</span>
        <span class="cc-access">{{ access }}</span>
        <span class="cc-tags" v-if="!compact"><i v-for="tag in clue.tags" :key="tag">#{{tag}}</i></span>
        <span class="cc-flaw" v-if="clue.tier==='boss_flaw'">◉</span>
      </button>`
    },
    'kc-card': {
      props: { kc: Object, owned: Boolean },
      data() { return { flip: false, emblemOk: true }; },
      emits: ['open'],
      computed: {
        topic() { return (window.ASSETS && window.ASSETS.topicOf(this.kc.topic_tag)) || { hue: 'focus', mark: '知' }; }
      },
      template: `<div class="kc-card" :class="{owned, flip}" @click="owned ? $emit('open', kc) : null">
        <div class="kc-inner" :class="{ flipped: flip }">
          <div class="kc-face kc-front" :class="'hue-' + topic.hue">
            <template v-if="owned">
              <div class="kc-crest" aria-hidden="true">
                <img v-if="topic.emblem && emblemOk" :src="topic.emblem" alt="" @error="emblemOk=false">
                <span v-if="!topic.emblem || !emblemOk">{{ topic.mark }}</span>
              </div>
              <span class="kc-tag">{{ kc.topic_tag }}</span>
              <h4>《{{ kc.title }}》</h4>
              <p class="kc-author">知乎知识 · {{ kc.author }}</p>
              <p class="kc-quote">“{{ kc.golden[0] }}”</p>
              <span class="kc-credit">求真弹药 · 常驻署名</span>
            </template>
            <template v-else>
              <img src="/assets/images/card_back.png" alt="知识卡卡背">
              <span class="kc-back-label">知乎知识 · 待收集</span>
            </template>
          </div>
          <div class="kc-face kc-back" v-if="owned">
            <img src="/assets/images/card_back.png" alt="">
            <p class="kc-quote">“{{ kc.golden[1] || kc.golden[0] }}”</p>
            <span class="kc-back-label">知乎 · {{ kc.author }}</span>
          </div>
        </div>
        <button v-if="owned" class="kc-flipper" @click.stop="flip=!flip" title="翻面">↻</button>
      </div>`
    },
    'svg-scene': {
      props: { loc: Object },
      computed: { html() { return window.UI.svgScene(this.loc.id); } },
      template: `<div class="svg-scene" v-html="html"></div>`
    },
    'avatar': {
      props: { char: Object, size: { type: String, default: '' } },
      template: `<span class="avatar" :class="size"><img :src="char.avatar" :alt="char.name" loading="lazy"></span>`
    },
    /* ---- V31：官方雪碧图切帧 · DM 行走动画 ----
     * 图源 kanshan_big.png（4700×1740 = kanshan.png 的 @2x，10 列 × 3 行 30 帧）。
     * row 0=站立挥手 1=行走+挥手 2=赶路；steps(9) 播完 10 帧后循环。
     * 帧显示尺寸沿用 110×124（scale 换算）；位移终点经 --dmw-end 传给 keyframes 以适配任意 scale。 */
    'dm-walk': {
      props: {
        row: { type: Number, default: 1 },      // 雪碧图行（0 站立挥手 / 1 行走挥手 / 2 赶路）
        scale: { type: Number, default: 1 },    // 缩放（1 = 帧显示 110×124）
        speed: { type: Number, default: 0.9 },  // 整轮秒数
        flip: Boolean,                          // 水平翻转（往回走）
        still: Boolean                          // 定格第一帧（站立待机）
      },
      computed: {
        style() {
          const w = Math.round(110 * this.scale), h = Math.round(124 * this.scale);
          const bgW = Math.round(1100 * this.scale);
          return {
            width: w + 'px', height: h + 'px',
            backgroundSize: `${bgW}px ${Math.round(371 * this.scale)}px`,
            backgroundPositionY: `-${Math.round(124 * this.row * this.scale)}px`,
            '--dmw-end': `-${bgW}px`,
            transform: this.flip ? 'scaleX(-1)' : 'none',
            animation: this.still ? 'none' : `dm-walk-steps ${this.speed}s steps(9) infinite`
          };
        }
      },
      template: `<span class="dm-walk" :style="style" aria-hidden="true"></span>`
    },
    /* ---- V31：倒计时环（终局陈词 60s / 反诈剧场 30s 复用） ---- */
    'countdown-ring': {
      props: { seconds: { type: Number, default: 60 }, running: Boolean, label: { type: String, default: '' } },
      emits: ['done'],
      data() { return { left: this.seconds, timer: null }; },
      watch: {
        running(v) {
          clearInterval(this.timer);
          if (v) {
            this.left = this.seconds;
            this.timer = setInterval(() => {
              this.left -= 1;
              if (this.left <= 0) { clearInterval(this.timer); this.left = 0; this.$emit('done'); }
            }, 1000);
          }
        }
      },
      beforeUnmount() { clearInterval(this.timer); },
      computed: {
        dash() { const C = 138.2; return { strokeDashoffset: C * (1 - this.left / Math.max(1, this.seconds)) }; },
        urgent() { return this.left <= 10; }
      },
      template: `<span class="cd-ring" :class="{urgent}">
        <svg viewBox="0 0 52 52">
          <circle cx="26" cy="26" r="22" class="cd-bg"/>
          <circle cx="26" cy="26" r="22" class="cd-fg" :style="dash"/>
        </svg>
        <b>{{ left }}s</b><i v-if="label">{{ label }}</i>
      </span>`
    },
    /* ---- V31：幕间电梯转场（advance 跨幕时全屏演出） ---- */
    'elevator-cut': {
      props: { to: Number },
      emits: ['done'],
      data() { return { floor: 1, closing: true, open: false, floors: [] }; },
      mounted() {
        const target = this.to || 2;
        this.floors = []; for (let f = 1; f <= target; f++) this.floors.push(f);
        let i = 0;
        const step = () => {
          if (i < this.floors.length) { this.floor = this.floors[i++]; setTimeout(step, 620); }
          else { this.open = true; setTimeout(() => this.$emit('done'), 1400); }
        };
        setTimeout(step, 900);  // 先关门
      },
      computed: { floorName() { return this.to >= 3 ? '3F · 真相层' : this.floor + 'F'; } },
      template: `<transition name="fade"><div class="elevator-cut" @click="$emit('done')">
        <div class="elv-doors" :class="{closed: closing, opened: open}">
          <div class="elv-door l"><span class="elv-slit"></span></div>
          <div class="elv-door r"><span class="elv-slit"></span></div>
        </div>
        <div class="elv-lcd">
          <div class="elv-dot" :class="{on: true}">▲</div>
          <b class="mono">{{ floorName }}</b>
          <span class="elv-note">求真档案局 · 幕间电梯（不出真相，不出此门）</span>
          <dm-walk :row="1" :scale="0.42" :speed="0.7" v-if="open"></dm-walk>
        </div>
        <span class="elv-skip">点击跳过</span>
      </div></transition>`
    },
    /* ---- P3：看山Bot 隐藏语音演出（集齐 3 袋鱼干解锁；切片逐句播不合并，4 段暖场） ---- */
    'fish-voice': {
      setup() {
        const S = window.Store.state, M = window.Store.M;
        const typed = ref('');
        const shown = ref(0);
        const cur = computed(() => M.fishVoiceLines[S.fishVoice ? S.fishVoice.line : 0] || null);
        const done = computed(() => !S.fishVoice);
        let timer = null;
        const play = () => {
          clearInterval(timer);
          if (!S.fishVoice) return;
          const line = cur.value; if (!line) { S.fishVoice = null; return; }
          if (window.SFX && window.SFX.vo) window.SFX.vo('fish_' + (S.fishVoice.line + 1));
          typed.value = ''; shown.value = 0;
          timer = setInterval(() => {
            shown.value += 1;
            typed.value = line.text.slice(0, shown.value);
            if (shown.value >= line.text.length) clearInterval(timer);
          }, 36);
        };
        watch(() => S.fishVoice && S.fishVoice.line, (line) => { if (line != null) play(); }, { immediate: true });
        const next = () => {
          if (cur.value && shown.value < cur.value.text.length) { clearInterval(timer); shown.value = cur.value.text.length; typed.value = cur.value.text; return; }
          S.fishVoice = S.fishVoice && S.fishVoice.line + 1 < M.fishVoiceLines.length ? { line: S.fishVoice.line + 1 } : null;
        };
        return { S, M, cur, typed, done, next, lineNo: computed(() => (S.fishVoice ? S.fishVoice.line : M.fishVoiceLines.length) + 1) };
      },
      template: `<transition name="fade"><div class="fish-voice" v-if="!done" @click="next">
        <div class="fv-card">
          <header class="fv-hd">
            <span class="chip blue">看山Bot · 隐藏语音（Boss 线暖场）</span>
            <span class="chip mono">语音 {{ lineNo }}/4 · 切片逐句播</span>
          </header>
          <div class="fv-body">
            <span class="fv-ava"><img src="/assets/images/bust/char_kanshanbot.png" alt="看山Bot"></span>
            <p class="fv-line">{{ typed }}<span class="caret" v-if="cur && typed.length < cur.text.length">▌</span></p>
            <p class="fv-time mono" v-if="cur">{{ cur.t }}</p>
          </div>
          <footer class="fv-ft">
            <span class="dim">诚实协议：以上均为事实。感受协议：未安装。</span>
            <button class="btn ghost sm" @click.stop="next">继续 ▸</button>
          </footer>
        </div>
      </div></transition>`
    },
    /* ---- V31：押注面板（弹幕押注，币种=赞数；chat/hotfeed 双入口复用） ---- */
    'bet-panel': {
      setup() {
        const S = window.Store.state, M = window.Store.M;
        const amt = ref(1);
        const bet = computed(() => S.bet);
        const pool = computed(() => bet.value ? Object.values(bet.value.wagers).reduce((s, x) => s + x.amt, 0) : 0);
        const charName = id => (window.Labels && window.Labels.who(id)) || (M.chars.find(c => c.id === id) || {}).name || '在场者';
        const doBet = opt => window.Store.send('skill', { kind: 'place_bet', option: opt, amount: amt.value });
        return { S, M, amt, bet, pool, charName, doBet };
      },
      template: `<div class="bet-panel" v-if="bet && !S.demo">
        <header class="bet-hd">
          <span class="bet-live">● 开盘中</span>
          <b>{{ bet.subject }}</b>
          <span class="bet-zans mono">余额 {{ S.zans }} 赞</span>
        </header>
        <p class="dim">币种：<b class="hl">赞数</b>（不与热度/行动点混币）· 全池归胜方按投入比例分 · 猜错充公 + AI 免费锐评一条 · 押注给话题加热 +1~5</p>
        <div class="bet-opts">
          <button v-for="opt in bet.options" :key="opt" class="bet-opt" @click="doBet(opt)" :disabled="S.busy || S.zans < amt">
            <img :src="(M.chars.find(c=>c.id===opt)||{}).avatar" alt="">
            <b>{{ charName(opt) }}</b>
            <span class="mono" v-if="bet.wagers[opt]">池 {{ bet.wagers[opt].amt }} 赞 / 你 {{ bet.wagers[opt].my || 0 }}</span>
            <span class="mono dim" v-else>暂无人押注</span>
          </button>
          <button v-if="bet.settled" class="bet-opt closed" disabled>已结算</button>
        </div>
        <footer class="bet-ft">
          <span class="dim">押注额：</span>
          <button v-for="n in [1,2,3,5]" :key="n" class="chip pick" :class="{on: amt===n}" @click="amt=n">{{ n }} 赞</button>
          <span class="dim">奖池 {{ pool }} 赞</span>
        </footer>
      </div>
      <div class="bet-panel closed" v-else-if="!S.demo">
        <p class="dim">押注通道未开启——下一轮开盘（弹幕押注：本轮你信谁的口供？）。</p>
      </div>`
    }
  };

  window.UI.install = function (app) {
    Object.entries(comps).forEach(([name, def]) => app.component(name, def));
    if (window.Voice && window.Voice.install) window.Voice.install(app);
  };
  window.UI.comps = comps;  // 供 main.js 追加注册（fish-voice 等）
})();
