/* ============================================================
 * views/review.js —— 复盘页（真相回放 + Boss 揭示演出 + 署名区）& 结局页
 * Boss 揭示：全屏演出（系统音故障 → 全息看山 → 独白 → 策划签名小字）
 * ============================================================ */
(function () {
  const { ref, computed, onMounted, watch } = Vue;

  /* 知识炼金场：本会话内见过的结局 id（Set 收集，跨局累加） */
  const seenEndings = new Set();

  /* ---------- Boss 全屏揭示演出 ---------- */
  const BossReveal = {
    emits: ['close'],
    setup(props, { emit }) {
      const S = window.Store.state, M = window.Store.M;
      const phase = ref(0);
      const lineIdx = ref(-1);
      const typed = ref('');
      let timers = [];

      // P3：终极层加播——集齐 3 袋鱼干时，bossLines 播完追加看山Bot 隐藏语音第 5 段
      const allLines = computed(() => {
        const lines = M.bossLines.slice();
        if (M.fishCollectibles.every(f => S.fish[f.id])) lines.push('（隐藏语音加播·终极层）' + M.fishVoiceBossExtra);
        return lines;
      });

      const typeLine = (idx) => {
        if (idx >= allLines.value.length) {
          phase.value = 3;
          timers.push(setTimeout(() => { phase.value = 4; }, 1200));
          return;
        }
        lineIdx.value = idx;
        if (window.SFX && window.SFX.vo) {
          if (idx < 4) window.SFX.vo('boss_' + (idx + 1));
          else window.SFX.vo('fish_5');
        }
        const text = allLines.value[idx]; typed.value = '';
        let i = 0;
        const tk = setInterval(() => {
          typed.value = text.slice(0, ++i);
          if (i >= text.length) { clearInterval(tk); timers.push(setTimeout(() => typeLine(idx + 1), 700)); }
        }, 42);
        timers.push(tk);
      };
      onMounted(() => {
        timers.push(setTimeout(() => phase.value = 1, 1400));
        timers.push(setTimeout(() => phase.value = 2, 3400));
        timers.push(setTimeout(() => typeLine(0), 4200));
      });
      const skip = () => {
        timers.forEach(t => { clearTimeout(t); clearInterval(t); });
        if (window.SFX && window.SFX.stopVo) window.SFX.stopVo();
        phase.value = 4;
      };
      const finish = () => { S.bossSeen = true; S.view = 'review'; emit('close'); };
      return { S, M, phase, lineIdx, typed, skip, finish, allLines };
    },
    template: `
    <div class="boss-reveal" :class="{ unmask: phase >= 3, revealed: phase >= 4 }" @click="phase < 4 && skip()">
      <div class="br-glitch" v-if="phase === 0">
        <div class="br-sys">叮——</div>
        <div class="br-check">系统提示音自检中… ██████████ 校验人：<b>刘看山</b></div>
      </div>
      <div class="br-stage" v-if="phase >= 1">
        <div class="br-holo" :class="{ glitch: phase >= 3 }">
          <img src="/assets/images/dm_kanshan_holo.png" alt="看山全息投影">
        </div>
        <div class="br-true" v-if="phase >= 3">
          <dm-walk :row="0" :scale="2.1" still></dm-walk>
          <span class="br-true-cap">刘看山形象 © 知乎 · 官方线稿</span>
        </div>
        <div class="br-scan"></div>
      </div>
      <div class="br-mono" v-if="phase >= 2">
        <p v-for="(l, i) in allLines.slice(0, lineIdx)" :key="i" class="br-line done" :class="{extra: l.startsWith('（隐藏语音')}">{{ l }}</p>
        <p v-if="lineIdx >= 0 && lineIdx < allLines.length" class="br-line live" :class="{extra: allLines[lineIdx] && allLines[lineIdx].startsWith('（隐藏语音')}">{{ typed }}<span class="caret">▌</span></p>
      </div>
      <transition name="fade">
        <div class="br-title" v-if="phase === 4">
          <h2>终极 · 看山还是山</h2>
          <p class="br-sub">你们破的局，正是看山设的局。</p>
          <p class="br-small">——本局由刘看山亲自策划：策划你的策划。</p>
          <button class="btn primary big" @click.stop="finish">进入完整复盘 →</button>
        </div>
      </transition>
      <span v-if="phase < 4" class="br-skip">点击跳过</span>
    </div>`
  };

  /* ---------- 结局页 ---------- */
  const EndingView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      if (S.ending) seenEndings.add(S.ending);
      const ending = computed(() => M.endings.find(e => e.id === S.ending) || M.endings[1]);
      const isBoss = computed(() => S.ending === 'kanshan' && !S.bossSeen);
      const replayBoss = () => { S.bossSeen = false; };
      const persona = computed(() => (S.report || {}).persona || null);
      const profile = computed(() => S.truthProfile || (S.report && S.report.profile) || null);
      return { S, M, ending, isBoss, replayBoss, persona, profile, Store: window.Store };
    },
    template: `
    <section class="view ending-view" :class="ending.cls">
      <div class="ending-card">
        <span class="ending-tag">结局解锁</span>
        <h1>{{ ending.name }}</h1>
        <p class="ending-desc">{{ (S.endingSummary && S.endingSummary.desc) || ending.desc }}</p>
        <p v-if="S.endingSummary && S.endingSummary.title && S.endingSummary.title !== ending.name" class="dim ending-engine-summary">引擎结算：{{ S.endingSummary.title }}</p>
        <div v-if="profile" class="tp-card">
          <truth-radar :profile="profile"></truth-radar>
          <div>
            <h4 class="tp-arch">{{ profile.archetype }} · {{ profile.overall }} 分</h4>
            <p class="tp-verdict">{{ profile.verdict }}</p>
            <ul class="tp-hi"><li v-for="(h, i) in (profile.highlights || [])" :key="i">{{ h }}</li></ul>
          </div>
        </div>
        <div v-else-if="persona" class="ending-persona">
          <span class="ep-name">🧭 {{ persona.name }}</span>
          <span class="ep-desc">{{ persona.desc }}</span>
        </div>
        <div class="ending-actions">
          <button class="btn primary big" @click="S.view='review'">查看完整复盘 →</button>
          <button class="btn ghost" @click="S.view='clinic'">心晴诊室</button>
          <button class="btn ghost" @click="Store.reset()">重开一局</button>
        </div>
      </div>
      <boss-reveal v-if="isBoss" @close="S.bossSeen = true" style="position:fixed; inset:0; z-index:80;"></boss-reveal>
    </section>`
  };

  /* ---------- 复盘页 ---------- */
  const ReviewView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const boss = ref(false);
      const ending = computed(() => M.endings.find(e => e.id === S.ending));
      const flawN = computed(() => window.Store.flawCount());
      const flawsOwned = computed(() => M.flaws.map(f => ({ ...f, got: !!S.flaws[f.id] })));
      const okCount = computed(() => S.counsel.filter(r => r.ok).length);
      const demoEnd = (id) => {
        window.Store.applyEvent({ type: 'vote', payload: { target: 'char_03', evidence: [], coverage: { pct: id === 'perfect' ? 100 : 66, hit: [] }, ending: id } });
        window.Store.applyEvent({ type: 'ending', payload: { ending_id: id, profile: window.Store.buildTruthProfile({ ending: id, accused_dm: id === 'kanshan' }) } });
      };
      const whoOf = id => (window.Labels && window.Labels.who(id)) || (M.chars.find(c => c.id === id) || {}).name || '在场者';
      const kcTitle = id => ((M.kcards.find(k => k.id === id) || {}).title) || '知识卡';
      /* ---- 知识炼金场：本局用过的知识卡（counsel 开导含心晴诊室 + refute 辟谣），去重 ---- */
      const learnedKcs = computed(() => {
        const used = new Set();
        (S.counsel || []).forEach(r => { if (r && r.kc_id) used.add(r.kc_id); });
        Object.values(S.refuted || {}).forEach(r => { if (r && r.kc_id) used.add(r.kc_id); });
        return Array.from(used).map(id => M.kcards.find(k => k.id === id)).filter(Boolean);
      });
      const kcGolden = kc => (kc.golden && kc.golden[0]) || kc.summary || '';
      /* ---- 结局图鉴进度：本会话内收集见过的 ending_id ---- */
      watch(() => S.ending, id => { if (id) seenEndings.add(id); }, { immediate: true });
      const seenCount = computed(() => seenEndings.size);
      return { S, M, boss, ending, flawN, flawsOwned, okCount, demoEnd, whoOf, kcTitle, learnedKcs, kcGolden, seenCount, Minis: window.Minis };
    },
    template: `
    <section class="view review-view">
      <header class="view-hd">
        <h2>复盘档案</h2>
        <div class="hd-chips">
          <span class="chip" v-if="ending" :class="ending.cls">{{ ending.name }}</span>
          <span class="chip" v-else>待指认结算后解锁完整复盘</span>
        </div>
      </header>

      <template v-if="ending">
        <p class="dim ending-progress">本局结局：{{ ending.name }}（已见证 {{ seenCount }} / {{ M.endings.length }}）</p>
        <div class="review-grid">
          <div class="rv-card">
            <h3>表层真相 · 时间线还原</h3>
            <ol class="tl-list">
              <li v-for="(t,i) in M.reviewTimeline" :key="i">
                <span class="tl-time">{{ t.time }}</span><p>{{ t.text }}</p>
              </li>
            </ol>
          </div>

          <div class="rv-card boss-card" @click="boss = true">
            <h3>里层真相 · Boss 揭示演出</h3>
            <div class="boss-visual"><img src="/assets/images/dm_kanshan_holo.png" alt="看山全息">
              <div class="boss-play">▶ 播放揭示演出</div>
            </div>
            <p>系统提示音 = 刘看山。大门、监控、横幅、鱼干——全是同一个"人"的手笔。</p>
          </div>

          <div class="rv-card">
            <h3>看山的五个破绽（{{ flawN }}/5）</h3>
            <ul class="flaw-list">
              <li v-for="f in flawsOwned" :key="f.id" :class="{got: f.got}">
                <b>{{ f.got ? '◉' : '○' }} {{ f.name }}</b><span>{{ f.got ? '已收录' : f.hint }}</span>
              </li>
            </ul>
          </div>

          <div class="rv-card">
            <h3>心晴诊室结算（{{ okCount }} 人被开导）</h3>
            <div class="clinic-recs-mini">
              <span v-for="(r,i) in S.counsel.filter(x=>x.ok)" :key="i" class="chip tiny good">
                {{ whoOf(r.char_id) }} ×《{{ kcTitle(r.kc_id) }}》
              </span>
              <span v-if="!okCount" class="dim">无人被开导——也是一种结局（扎心向）。</span>
            </div>
          </div>

          <div class="rv-card learned-card">
            <h3>今日学到（用过 {{ learnedKcs.length }} 张知识卡）</h3>
            <template v-if="learnedKcs.length">
              <p v-for="kc in learnedKcs" :key="kc.id">「{{ kcGolden(kc) }}」——{{ kc.topic_tag }} · 来自知乎《{{ kc.title }}》@{{ kc.author }}</p>
            </template>
            <p v-else class="dim">本局还没开导/辟谣任何人——去用知识卡撬开心声吧。</p>
          </div>
        </div>

        <div class="credits">
          <h3>署名区</h3>
          <div class="credit-cols">
            <div class="credit-col">
              <h4>剧情底座 · 盐言故事（常驻作者署名）</h4>
              <p v-for="c in M.credits.salt" :key="c.work"><b>{{ c.work }}</b><span>{{ c.note }}</span></p>
            </div>
            <div class="credit-col">
              <h4>知识卡 · 知乎知识作者（10 篇）</h4>
              <p class="kc-authors">{{ M.credits.knowledge.join(' · ') }}</p>
              <h4 class="mt">IP 与素材</h4>
              <p class="dim">{{ M.credits.ip }}</p>
            </div>
          </div>
          <p class="credit-small">{{ M.credits.small }}</p>
          <!-- flavor_5 常驻署名小字（D 内容组对接点：策划案落款 + 盐言三作，任何状态常驻） -->
          <p class="credit-small flavor5">{{ M.flavor5Credit }}</p>
          <div class="review-walk-strip"><dm-walk :row="1" :scale="0.42" :speed="1.2"></dm-walk></div>
          <button class="btn ghost sm" @click="S.view='report'">侦探档案 · 报告与分享卡 →</button>
        </div>
      </template>

      <div v-else class="empty-state big-pad">
        <div class="empty-art">▚▞</div>
        <b>复盘未解锁</b>
        <p>完整复盘在圆桌指认结算后开启。剧透保护中：连我都替你把 Boss 藏好了。</p>
        <div class="demo-row" v-if="S.demo">
          <span class="dim">演示模式快捷入口：</span>
          <button class="btn ghost sm" @click="demoEnd('truth')">模拟结局·真相大白</button>
          <button class="btn ghost sm" @click="demoEnd('kanshan')">模拟结局·终极看山还是山</button>
        </div>
        <div class="demo-row" v-else><button class="btn ghost sm" @click="S.demo=true; S.view='vote'">先去指认 →</button></div>
        <!-- flavor_5 常驻署名小字（未解锁态同样常驻——D 内容组对接点） -->
        <p class="credit-small flavor5 standby">{{ M.flavor5Credit }}</p>
        <!-- M2/M3 安放位：复盘页入口（minis.md 安放位图） -->
        <div class="demo-row mini-entry-row" v-if="!S.demo">
          <span class="dim">再玩点别的：</span>
          <button class="btn ghost sm" @click="Minis.open('heart')">🎧 心声窃听器</button>
          <button class="btn ghost sm" @click="Minis.open('refute3')">🧹 谣言消消乐</button>
          <button class="btn ghost sm" @click="Minis.open('runner')">🏃 看山快跑</button>
          <button class="btn ghost sm" @click="Minis.open('badge')">🎫 每日抽签</button>
        </div>
      </div>

      <boss-reveal v-if="boss" @close="boss = false" style="position:fixed; inset:0; z-index:80;"></boss-reveal>
    </section>`
  };

  window.VIEWS.review = ReviewView;
  window.VIEWS.ending = EndingView;
  window.VIEWS['boss-reveal'] = BossReveal;
})();
