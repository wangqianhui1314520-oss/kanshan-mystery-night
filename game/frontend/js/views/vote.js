/* ============================================================
 * views/vote.js —— 圆桌投票（≥2 证据卡；破绽 5/5 动态出「指认：DM」）
 * 事件：vote → vote + ending
 * ============================================================ */
(function () {
  const { ref, computed, onMounted } = Vue;

  const VoteView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const echoPicks = ref([]);
      const claim = ref('');
      const citedEv = ref([]);
      const citedKc = ref([]);
      const admit = ref(false);
      const STANCE = { hostile: '敌视', skeptical: '怀疑', open: '开放', convinced: '采信' };
      const echoCh = computed(() => S.echo && S.echo.challenge);
      const echoRes = computed(() => S.echo && S.echo.result);
      const evCites = computed(() => S.synth.concat(
        Object.keys(S.clues).map(id => M.clues.find(c => c.id === id)).filter(Boolean)
          .map(c => ({ id: c.id, name: c.name }))
      ));
      const kcCites = computed(() => Object.keys(S.kcards).map(id => M.kcards.find(k => k.id === id)).filter(Boolean));
      const toggleEcho = (idx) => {
        const i = echoPicks.value.indexOf(idx);
        if (i >= 0) echoPicks.value.splice(i, 1);
        else if (echoPicks.value.length < 2) echoPicks.value.push(idx);
        else { echoPicks.value = [echoPicks.value[1], idx]; }
      };
      const openEcho = () => window.Store.send('skill', { kind: 'echo_open' });
      const defendEcho = () => window.Store.send('skill', { kind: 'echo_defend', picks: echoPicks.value.slice() });
      const defendConsistent = () => window.Store.send('skill', { kind: 'echo_defend', picks: [] });
      const openDebate = () => window.Store.send('skill', { kind: 'debate_open' });
      const toggleCiteEv = (name) => {
        const i = citedEv.value.indexOf(name);
        if (i >= 0) citedEv.value.splice(i, 1); else citedEv.value.push(name);
      };
      const toggleCiteKc = (title) => {
        const i = citedKc.value.indexOf(title);
        if (i >= 0) citedKc.value.splice(i, 1); else citedKc.value.push(title);
      };
      const submitDebate = () => {
        const bits = [];
        if (citedEv.value.length) bits.push('出示实证：' + citedEv.value.join('、'));
        if (citedKc.value.length) bits.push('引用知识卡：' + citedKc.value.join('、'));
        if (admit.value) bits.push('我承认我曾经动摇过。');
        const body = (claim.value || '').trim();
        const text = (bits.join('。') + (body ? '。' + body : '')).trim();
        if (text.length < 8) return window.Store.toast('点选证据或知识卡，再写一句陈词', 'warn');
        window.Store.send('skill', { kind: 'debate_submit', claim: text });
      };
      onMounted(() => {
        if (S.act >= 3 && window.Store.grantFinaleFlaw) window.Store.grantFinaleFlaw();
        if (S.ended) return;
        if (!(S.echo && S.echo.challenge) && !(S.echo && S.echo.result)) {
          setTimeout(() => { if (!S.busy) openEcho(); }, 280);
        }
      });
      const pickable = computed(() => {
        const resolve = id => (window.Store.clueById && window.Store.clueById(id)) || M.clues.find(c => c.id === id);
        return Object.keys(S.clues).map(resolve).filter(c => c && c.tier !== 'fake');
      });
      const evidenceList = computed(() => {
        const synths = S.synth.map(s => ({ id: s.id, name: s.name, nodes: [s.node], synth: true }));
        return synths.concat(pickable.value.map(c => ({ id: c.id, name: c.name, nodes: c.linked || [], synth: false })));
      });
      const suspects = computed(() => M.chars.filter(c => c.id !== 'dm'));
      const flawN = computed(() => window.Store.flawCount());
      const dmUnlocked = computed(() => flawN.value >= 5);
      const toggleEv = id => {
        const ix = S.voteEvidence.indexOf(id);
        if (ix >= 0) S.voteEvidence.splice(ix, 1); else S.voteEvidence.push(id);
      };
      const cov = computed(() => window.Store.coverage(S.voteEvidence));
      const doVote = () => window.Store.send('vote', { target: S.voteTarget, evidence: S.voteEvidence.slice() });
      const pick = id => { S.voteTarget = id; };
      const charName = id => id === 'dm' ? 'DM 刘看山（系统提示音）' : ((window.Labels && window.Labels.who(id)) || (M.chars.find(c => c.id === id) || {}).name || '在场者');
      const result = computed(() => S.voteResult);
      const endingOf = id => M.endings.find(e => e.id === id);
      const hungEnding = computed(() => (M.endings || []).find(e => e.id === 'hung')
        || { id: 'hung', name: '悬而未决', desc: '票数分裂，真相随夜色搁置——平票也是一种答案。', cls: 'fun' });
      const showHung = computed(() => !!(S.voteResult && (S.voteResult.tie || S.ending === 'hung')));

      /* ---- V31 P2：终局陈词轮（60s/人 + 弹幕"最想锤的人"分池；不影响指认，影响群嘲结局与成就） ---- */
      const extraFinale = ref(false);
      const closing = ref('');
      const closingRunning = ref(false);
      const hammerPick = ref('');
      const hammerOut = computed(() => S.hammer);
      const startClosing = () => {
        closingRunning.value = true;
        if (window.SFX) window.SFX.play('countdown');
      };
      const closingTimeout = () => {
        if (window.SFX && window.SFX.stopHeld) window.SFX.stopHeld();
        closingRunning.value = false;
        if (closing.value.trim()) doClosing();
        else window.Store.toast('60 秒到了也没说上话——也算一种陈词', 'warn');
      };
      const doClosing = () => {
        if (window.SFX && window.SFX.stopHeld) window.SFX.stopHeld();
        window.Store.send('skill', { kind: 'closing_speech', text: closing.value });
        closingRunning.value = false;
      };
      const doHammer = () => {
        if (!hammerPick.value) return window.Store.toast('先选"最想锤的人"（弹幕分池投票）', 'warn');
        window.Store.send('skill', { kind: 'hammer_vote', target: hammerPick.value });
      };
      const tallyName = id => id === 'player:1' || (window.Store && id === window.Store.state.playerId)
        ? '你' : ((window.Labels && window.Labels.who(id)) || (M.chars.find(c => c.id === id) || {}).name || '在场者');

      return { S, M, suspects, evidenceList, dmUnlocked, flawN, toggleEv, cov, doVote, pick, charName, result, endingOf, hungEnding, showHung, extraFinale, closing, closingRunning, startClosing, closingTimeout, doClosing, hammerPick, hammerOut, doHammer, tallyName,
        echoPicks, claim, citedEv, citedKc, admit, STANCE, echoCh, echoRes, evCites, kcCites,
        toggleEcho, openEcho, defendEcho, defendConsistent, openDebate, toggleCiteEv, toggleCiteKc, submitDebate };
    },
    template: `
    <section class="view vote-view">
      <header class="view-hd">
        <h2>圆桌投票 · 指认</h2>
        <div class="hd-chips">
          <span class="chip">指认必须提交 ≥2 张证据卡</span>
          <span class="chip flaw">破绽 {{ flawN }}/5</span>
          <span class="chip good" v-if="dmUnlocked">「指认：DM」已解锁</span>
        </div>
      </header>

      <div class="pp-hung ending-mini fun" v-if="showHung">
        <h3>平票 · 悬而未决</h3>
        <p>{{ hungEnding.desc }}</p>
      </div>

      <div class="vote-layout">
        <div class="vote-col">
          <h3 class="col-hd">① 指认对象</h3>
          <div class="suspect-grid">
            <button v-for="c in suspects" :key="c.id" class="suspect" :class="{on: S.voteTarget===c.id}" @click="pick(c.id)">
              <img :src="c.avatar" :alt="c.name"><b>{{ c.name }}</b><span>{{ c.archetype }}</span>
            </button>
            <button class="suspect dm-slot" :class="{on: S.voteTarget==='dm', unlocked: dmUnlocked}" @click="dmUnlocked && pick('dm')">
              <img src="/assets/images/bust/dm_kanshan_holo.png" alt="DM">
              <b>？？？（DM）</b>
              <span v-if="dmUnlocked" class="dm-btn-label">◉ 指认：DM</span>
              <span v-else class="dim">第三幕署名破绽入袋后解锁（{{ flawN }}/5）</span>
            </button>
          </div>
        </div>
        <div class="vote-col">
          <h3 class="col-hd">② 提交证据卡（已选 {{ S.voteEvidence.length }}）</h3>
          <div class="ev-pool">
            <button v-for="ev in evidenceList" :key="ev.id" class="ev-item" :class="{on: S.voteEvidence.includes(ev.id), synth: ev.synth}"
                    @click="toggleEv(ev.id)">
              <span class="ev-mark">{{ ev.synth ? '◆' : '□' }}</span>{{ ev.name }}
            </button>
          </div>
          <div class="cov-preview" v-if="S.voteTarget">
            覆盖预览（对水军头子）：真相节点命中 <b>{{ cov.hit.length }}/6</b> · 强度
            <div class="cov-bar"><i :style="{width: cov.pct + '%'}" :class="{good: cov.pct>=85, mid: cov.pct>=60}"></i></div>
            <span class="dim">散卡凑节点也行，合成证据卡一次顶一格。</span>
          </div>
          <button class="btn danger big vote-btn" :disabled="!S.voteTarget || S.voteEvidence.length < 2 || S.busy || S.ended" @click="doVote">
            提交指认（{{ S.voteEvidence.length }}/2 张证据卡）
          </button>
        </div>
      </div>

      <div class="echo-wall" v-if="!S.ended">
        <h3>回声档案 · 你说过的话</h3>
        <p class="dim">档案局静默记录了你的原话。指出互相矛盾的两句，或证明自己全程一致。</p>
        <p class="echo-proj" v-if="echoCh">{{ echoCh.text }}</p>
        <div class="inv-cta" v-if="echoCh && echoCh.mode === 'empty'">
          <div>
            <b>回声档案几乎是空的</b>
            <p class="dim">去圆桌留下两句会被归档的话，终局才能用你自己的话对质。</p>
          </div>
          <button class="btn primary sm" type="button" @click="S.view='chat'">去圆桌说话 →</button>
        </div>
        <div class="echo-cands" v-if="echoCh && echoCh.candidates && echoCh.candidates.length">
          <button v-for="c in echoCh.candidates" :key="c.idx" type="button" class="echo-line"
                  :class="{ on: echoPicks.includes(c.idx) }" @click="toggleEcho(c.idx)">
            {{ c.text }}<em>R{{ c.round }} · #{{ c.idx }}</em>
          </button>
        </div>
        <div class="echo-actions" v-if="echoCh && !echoRes">
          <button class="btn primary sm" :disabled="S.busy || echoPicks.length !== 2" @click="defendEcho">引自证 · 就是这两句矛盾</button>
          <button class="btn ghost sm" :disabled="S.busy" @click="defendConsistent">我全程一致</button>
        </div>
        <div class="echo-actions" v-if="!echoCh">
          <button class="btn ghost sm" :disabled="S.busy" @click="openEcho">投影回声档案</button>
        </div>
        <div v-if="echoRes" class="echo-out" :class="echoRes.passed ? 'ok' : 'bad'">{{ echoRes.text || echoRes.reason }}</div>
      </div>

      <div class="debate-bench" v-if="!S.ended">
        <h3>AI 法官 · 说服一个会被热度带偏的裁判</h3>
        <div class="db-stance">
          <span class="chip" :class="{ warn: S.heat >= 60 }">热度 {{ S.heat }}</span>
          <span class="chip" v-if="S.debate.open">立场：{{ STANCE[S.debate.stance] || '开放' }}</span>
          <span class="chip" v-if="S.debate.open">采信 {{ S.debate.score }}/{{ S.debate.need }}</span>
        </div>
        <p class="dim" v-if="S.debate.text">{{ S.debate.text }}</p>
        <div class="echo-actions" v-if="!S.debate.open">
          <button class="btn primary sm" :disabled="S.busy" @click="openDebate">请法官入席</button>
        </div>
        <template v-else>
          <p class="dim">点选要出示的证据 / 知识卡（写入陈词，按引用计分）。单轮最多 +3，采信要 4 分，通常陈词两轮。</p>
          <div class="inv-cta" v-if="!evCites.length && !kcCites.length">
            <div>
              <b>还没有可引用的卷宗</b>
              <p class="dim">搜到线索或抽一张知识卡，再来点选陈词。评委线会预置一张。</p>
            </div>
            <button class="btn ghost sm" type="button" @click="window.Store.startJudgeLine()">补一张评委线弹药 →</button>
          </div>
          <div class="db-cites">
            <button v-for="ev in evCites" :key="'e'+ev.id" type="button" :class="{ on: citedEv.includes(ev.name) }" @click="toggleCiteEv(ev.name)">{{ ev.name }}</button>
            <button v-for="kc in kcCites" :key="kc.id" type="button" :class="{ on: citedKc.includes(kc.title) }" @click="toggleCiteKc(kc.title)">《{{ kc.title }}》</button>
            <button type="button" :class="{ on: admit }" @click="admit = !admit" v-if="S.echo.defended">我承认我动摇过</button>
          </div>
          <textarea class="db-claim" v-model="claim" maxlength="280" placeholder="再用一句人话说明：这些证据如何指向真相"></textarea>
          <div class="db-actions">
            <voice-mic v-model="claim" :maxlength="280"></voice-mic>
            <button class="btn primary sm" :disabled="S.busy || S.debate.convinced" @click="submitDebate">提交陈词</button>
            <span class="dim" v-if="S.debate.convinced">本庭已采信。可以去指认了。</span>
          </div>
        </template>
        <div v-if="S.debate.rounds.length" class="db-out" :class="S.debate.convinced ? 'ok' : ''">
          最近一轮：{{ (S.debate.rounds[S.debate.rounds.length-1].gain >= 0 ? '+' : '') + S.debate.rounds[S.debate.rounds.length-1].gain }} 分
        </div>
      </div>

      <div class="extra-finale-toggle" v-if="!S.ended && !extraFinale">
        <button class="btn ghost sm" type="button" @click="extraFinale=true">更多终局玩法 · 60 秒陈词 / 弹幕锤票</button>
      </div>
      <!-- V31 P2：终局陈词轮（投票前的最后一口气） -->
      <div class="closing-zone" v-if="!S.ended && extraFinale">
        <header class="cz-hd">
          <span class="chip gold">终局陈词轮</span>
          <b>提交指认前，每人 60 秒最后陈词</b>
          <span class="dim">弹幕同步开启"最想锤的人"分池投票——不影响指认，影响群嘲结局与成就（全场公敌 / 黄金六十秒）。</span>
        </header>
        <div class="cz-body">
          <div class="cz-left">
            <div class="cz-timer">
              <countdown-ring :seconds="60" :running="closingRunning" label="陈词计时" @done="closingTimeout"></countdown-ring>
              <button v-if="!closingRunning" class="btn ghost sm" @click="startClosing">开始 60s</button>
            </div>
            <div class="kw-input">
              <input v-model="closing" maxlength="120" @keyup.enter="doClosing" placeholder="说点想让人记住的（120 字内，弹幕实时收货）" :disabled="!closingRunning" />
              <voice-mic v-model="closing" :submit="doClosing" :disabled="!closingRunning" :maxlength="120"></voice-mic>
              <button class="btn primary" :disabled="!closingRunning || !closing.trim()" @click="doClosing">登记陈词</button>
            </div>
          </div>
          <div class="cz-right">
            <b class="dim">最想锤的人（弹幕分池 · 1 票）</b>
            <div class="hammer-picks">
              <button v-for="c in suspects" :key="c.id" class="chip pick" :class="{on: hammerPick===c.id}" @click="hammerPick=c.id">{{ c.name }}</button>
            </div>
            <button class="btn danger sm" :disabled="S.busy || !hammerPick" @click="doHammer">投出锤票</button>
            <div v-if="hammerOut" class="hammer-result">
              <span class="chip warn">本轮"最想锤的人"：{{ tallyName(hammerOut.most) }}（锤声一片）</span>
              <span class="dim mono">票池：{{ Object.entries(hammerOut.tally).map(([k,v]) => tallyName(k)+'×'+v).join(' / ') }}</span>
            </div>
          </div>
        </div>
      </div>

      <ui-modal v-if="result" title="指认结算" @close="S.voteResult=null">
        <div class="vote-result">
          <p>指认对象：<b>{{ charName(result.target) }}</b></p>
          <p>证据 {{ (result.evidence && result.evidence.length) || 0 }} 张 · 已投 {{ result.voters || 0 }}/{{ result.needed || 0 }}
            <template v-if="result.coverage"> · 覆盖 <b>{{ result.coverage.pct }}%</b></template></p>
          <div class="cov-bar big" v-if="result.coverage"><i :style="{width: result.coverage.pct + '%'}"></i></div>
          <div class="pp-hung ending-mini fun" v-if="result.tie || S.ending==='hung'">
            <h3>平票 · 悬而未决</h3>
            <p>{{ hungEnding.desc }}</p>
          </div>
          <div class="ending-mini" v-if="result.ending && endingOf(result.ending)" :class="endingOf(result.ending).cls">
            <h3>{{ endingOf(result.ending).name }}</h3>
            <p>{{ endingOf(result.ending).desc }}</p>
          </div>
          <p class="dim" v-else-if="result.needed && result.voters < result.needed">等待其余调查员提交指认…</p>
          <button class="btn primary big" @click="S.voteResult=null; S.view='review'">进入复盘 →</button>
        </div>
      </ui-modal>
    </section>`
  };

  window.VIEWS.vote = VoteView;
})();
