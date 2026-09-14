/* ============================================================
 * views/chat.js —— 圆桌对话（上帝俯视）
 * 左角色栏 + DM 面板 | 中央圆桌（桌心知乎）| 右常驻热搜 TOP5
 * 底栏：【知乎搜索】搜证 + 对话发送。切页仍走全局动作条。
 * ============================================================ */
(function () {
  const { ref, computed, nextTick, watch } = Vue;

  const ChatView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const input = ref('');
      const kw = ref('');
      const listEl = ref(null);
      const showBet = ref(false);
      const loc = ref((M.locations && M.locations[0] && M.locations[0].name) || '监控室');
      const studioPack = computed(() => !!(S.scenarioId && S.studioModules));
      const modOn = (key) => !studioPack.value || S.studioModules[key] !== false;

      const suspects = computed(() => M.chars.filter(c => c.id !== 'dm'));
      const cur = computed(() => M.chars.find(c => c.id === S.currentNpc)
        || { id: 'dm', name: '刘看山', avatar: '/assets/images/bust/dm_kanshan_holo.png', archetype: '档案局 DM' });

      const playerCharId = computed(() => window.Store.playerCharacterId());
      const selectTarget = id => window.Store.selectChatTarget(id);
      const seats = computed(() => {
        const chars = suspects.value;
        const playerIndex = chars.findIndex(c => c.id === playerCharId.value);
        return chars.map((c, i) => {
          // 以玩家扮演的角色为主视角，旋转座位使其始终位于圆桌下方。
          const a = playerIndex >= 0
            ? ((i - playerIndex) / chars.length) * Math.PI * 2 + Math.PI / 2
            : (i / chars.length) * Math.PI * 2 - Math.PI / 2;
          return { ...c, x: 50 + 40 * Math.cos(a), y: 50 + 36 * Math.sin(a) };
        });
      });

      const lastDm = computed(() => {
        for (let i = S.chat.length - 1; i >= 0; i--)
          if (S.chat[i].actor === 'dm') return S.chat[i];
        return null;
      });

      const myPid = computed(() => S.playerId || 'player:1');
      const whisperOn = ref(false);
      const whisperTo = ref('');
      const sendingPrivate = ref(false);
      const fvHide = ref(false);
      const chatMode = ref('public'); // public | team | private
      const teamMembers = ref([]);
      /* 单人局由 AI 补位组成临时小队；多人局由真人队友组成小队。 */
      const teamAvailable = computed(() => S.mode === 'party'
        ? (S.partySeats || []).filter(s => s && (s.player_id || s.id)).length > 1
        : (window.UX && window.UX.ai && window.UX.ai.seats ? window.UX.ai.seats.length > 0 : true));
      const aiCandidates = computed(() => suspects.value.filter(c => c.id !== playerCharId.value));
      const toggleTeamMember = (id) => { const i = teamMembers.value.indexOf(id); if (i >= 0) teamMembers.value.splice(i, 1); else teamMembers.value.push(id); };
      const canWhisper = computed(() => !S.isSpectator);
      const socialReady = computed(() => !!S.sessionId && S.sessionId !== '-' && !S.demo && !S.ended);
      const partyPeers = computed(() => {
        const me = myPid.value;
        return (S.partySeats || []).filter(s => {
          const id = (s && (s.player_id || s.id)) || '';
          return String(id).indexOf('player:') === 0 && id !== me && !s.is_ai && !s.ai_takeover;
        }).map(s => {
          const id = s.player_id || s.id;
          const ch = M.chars.find(c => c.id === s.char_id);
          return { id, name: s.name || s.player_name || (ch && ch.name) || ((window.Labels && window.Labels.who(id)) || '队友') };
        });
      });
      const whisperTargets = computed(() => {
        const humanRoles = new Set((S.partySeats || []).filter(s => s.player_id && !s.is_ai && !s.ai_takeover).map(s => s.char_id));
        const npcs = suspects.value.filter(c => c.id !== playerCharId.value && !humanRoles.has(c.id))
          .map(c => ({ id: 'npc:' + c.id, name: 'AI · ' + c.name, npc: true }));
        return partyPeers.value.concat(npcs);
      });

      const shown = computed(() => S.chat.filter(m => {
        if (m.whisper) {
          const me = myPid.value;
          if (chatMode.value !== 'private') return false;
          return m.to === me || m.from === me || m.player_id === me || m.actor === 'me';
        }
        if (chatMode.value === 'team') return m.actor === 'peer' || m.team === true || (m.actor === 'npc' && (!teamMembers.value.length || teamMembers.value.includes(m.char_id))) || (m.actor === 'me' && m.team);
        if (chatMode.value === 'private') return false;
        /* DM 播报只进左上「DM 面板」（lastDm 从 S.chat 全量取，不受本过滤影响），
           不再重复渲染进公共聊天流（2026-09-14 需求：DM 专属框单通道展示）。 */
        return m.actor === 'sys' || m.actor === 'npc' || m.actor === 'me' || m.actor === 'peer' || m.aiAct || m.wave;
      }));

      watch(shown, async () => { await nextTick(); if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight; });
      watch(() => S.firstVote && S.firstVote.open, (open) => { if (open) fvHide.value = false; });

      const send = async () => {
        if (sendingPrivate.value) return;
        const t = input.value.trim(); if (!t) return;
        /* 串联发言制：AI 依次发言期间你的消息自动排队，说完轮到你（不丢失） */
        if (window.Store.aiSpeaking && window.Store.aiSpeaking()) {
          window.Store.toast('大家正在依次发言，你的消息已排在后面', 'ok');
        }
        if ((whisperOn.value || chatMode.value === 'private') && canWhisper.value) {
          if (!whisperTo.value) { window.Store.toast('先选私聊对象', 'warn'); return; }
          if (window.Store.whisper) {
            sendingPrivate.value = true;
            try {
              const ok = await (whisperTo.value.indexOf('npc:') === 0
                ? window.Store.npcWhisper(whisperTo.value, t)
                : window.Store.whisper(whisperTo.value, t));
              if (ok && input.value.trim() === t) input.value = '';
            } finally { sendingPrivate.value = false; }
          } else {
            window.Store.toast('私聊通道未接通', 'warn');
          }
          return;
        }
        if (chatMode.value === 'team' && !teamAvailable.value) { window.Store.toast(S.mode === 'party' ? '小队频道需要至少两名玩家组队' : 'AI 队友尚未就位，请先开始对局', 'warn'); return; }
        const target = String(S.currentNpc || 'dm').replace(/^npc:/, '');
        if (window.Store.send('chat', { char_id: target, target, text: t, team: chatMode.value === 'team' }) !== false) input.value = '';
      };

      const fvShow = computed(() => {
        const fv = S.firstVote;
        if (!fv) return false;
        return !!(fv.open || (fv.done && !fvHide.value));
      });
      const fvName = computed(() => {
        const fv = S.firstVote || {};
        let id = fv.pick;
        if (!id && fv.tally) {
          const top = Object.entries(fv.tally).sort((a, b) => b[1] - a[1])[0];
          if (top) id = top[0];
        }
        return ((M.chars.find(c => c.id === id) || {}).name) || id || '（未决）';
      });
      const castFirstVote = (id) => window.Store.send('skill', { kind: 'first_vote_cast', target: id });
      const closeFirstVote = () => { fvHide.value = true; };

      const v587On = computed(() => !!(S.v587Exposed || (S.v587 && S.v587.exposed)));
      const canExposeV587 = computed(() => (S.act >= 2 || S.demo) && !v587On.value);
      const exposeV587 = () => window.Store.send('skill', { kind: 'expose_v587' });

      const kwPool = computed(() => {
        const pool = [];
        const seen = new Set();
        (M.locations || []).forEach(l => (l.keywords || []).forEach(k => {
          if (!seen.has(k)) { seen.add(k); pool.push({ k, loc: l.name }); }
        }));
        return pool.slice(0, 8);
      });
      const pickKw = (item) => { kw.value = item.k; loc.value = item.loc; };
      // 搜证命令提示：公共聊天直接说「去<地点>搜证<关键词>」即可执行（引擎裁决扣 AP）。
      const searchHint = computed(() => {
        if (chatMode.value !== 'public' || whisperOn.value) return '';
        if (S.stage !== 'investigate') return '';
        const l0 = (M.locations || [])[0];
        if (!l0) return '';
        const k0 = (l0.keywords || [])[0] || '线索';
        return '试试对桌说：去' + l0.name + '搜证' + k0;
      });
      const iceLocked = computed(() => !!(window.Store.iceBlocksSearch && window.Store.iceBlocksSearch()));
      const doSearch = () => {
        if (iceLocked.value) { window.Store.toast('破冰结束才能搜证', 'warn'); return; }
        const keyword = kw.value.trim();
        if (!keyword) { window.Store.toast('先输入或点选一个搜证关键词', 'warn'); return; }
        window.Store.send('search', { location: loc.value, keyword });
      };
      const hotTop = computed(() => {
        const ps = Object.values(S.posts || {});
        if (ps.length) return ps.slice(0, 5).map(p => ({ title: p.title || p.name, hot: p.heat_delta || '' }));
        const packPosts = (M.posts || []).slice(0, 5);
        if (packPosts.length) return packPosts.map(p => ({ title: p.title || p.name, hot: p.delta || p.heat_delta || '' }));
        return [
          { title: '#看山失踪#', hot: '爆' }, { title: '#谁动了我的鱼干#', hot: '热' },
          { title: '#档案局夜班之谜#', hot: '新' }, { title: '#折叠区危机#', hot: '' },
          { title: '#求真还是求热度#', hot: '' }
        ];
      });

      const speakId = computed(() => {
        for (let i = S.chat.length - 1; i >= 0; i--) {
          const m = S.chat[i];
          if (m.actor === 'npc' || m.actor === 'dm') return m.actor === 'dm' ? 'dm' : m.char_id;
        }
        return null;
      });
      const seatCls = (c) => ({
        on: S.currentNpc === c.id,
        'is-player': playerCharId.value === c.id,
        speaking: speakId.value === c.id,
        dim: !!speakId.value && speakId.value !== c.id,
        heart: !!S.heartUnlocked[c.id]
      });

      const showSearch = computed(() => (S.act === 1 || !!S.demo) && !iceLocked.value);
      const showHot = computed(() => !studioPack.value || S.studioModules.hotfeed !== false);

      const startInvestigate = () => window.Store.finishStudioBreakIce();
      const askNpcWave = () => window.Store.requestNpcWave && window.Store.requestNpcWave();

      /* AI 来源徽章（契约：chat payload.ai_provider）：
         缓存→缓存 / mock→本地 / fallback→兜底 / zhida→知乎直答 / main→自建模型 / 其余→AI。
         评委现场由此一眼看出这条台词走的是哪条通道（知乎直答 vs 玩家自设模型）。 */
      const aiSrcBadge = (p) => {
        const s = String(p || '').toLowerCase();
        if (s.indexOf('cache') >= 0) return { text: '缓存', cls: 'blue' };
        if (s.indexOf('mock') >= 0) return { text: '本地', cls: 'warn' };
        if (s.indexOf('fallback') >= 0) return { text: '兜底', cls: 'warn' };
        if (s.indexOf('zhida') >= 0) return { text: '知乎直答', cls: 'good' };
        if (s.indexOf('main') >= 0) return { text: '自建模型', cls: 'blue' };
        return { text: 'AI', cls: '' };
      };

      return { S, M, input, kw, listEl, showBet, loc, suspects, cur, seats, lastDm, shown, chatMode, teamAvailable, aiCandidates, teamMembers, toggleTeamMember,
               send, kwPool, pickKw, doSearch, searchHint, hotTop, speakId, seatCls, startInvestigate, askNpcWave,
               studioPack, modOn, whisperOn, whisperTo, canWhisper, partyPeers, whisperTargets, sendingPrivate, socialReady,
               fvShow, fvName, castFirstVote, closeFirstVote,
               v587On, canExposeV587, exposeV587, showSearch, showHot, playerCharId, selectTarget, aiSrcBadge };
    },
    template: `
    <section class="view chat-view cs">
      <div class="cs-grid">
        <div class="cs-rail">
          <button v-for="(c, i) in suspects" :key="c.id" class="cs-rail-ava" :class="seatCls(c)"
                  @click="selectTarget(c.id)" :disabled="c.id === playerCharId" :title="c.name + (c.id === playerCharId ? ' · 你' : '')">
            <em>{{ i + 1 }}</em>
            <img :src="c.avatar" :alt="c.name">
          </button>
        </div>

        <div class="cs-dm">
          <div class="cs-dm-tag">DM 面板</div>
          <img class="cs-dm-ava" src="/assets/images/bust/dm_kanshan_holo.png" alt="DM">
          <b class="cs-dm-name">{{ studioPack ? '系统提示音' : '刘看山' }}</b>
          <div class="cs-dm-brief">
            <span class="cs-dm-sub">系统播报</span>
            <p>{{ lastDm ? lastDm.text : '全员已在圆桌就座。点座位选人，底栏提问或搜证。' }}</p>
          </div>
          <details v-if="S.actBrief"><summary>本幕目标</summary><p>{{ S.actBrief.title }}</p><p>{{ S.actBrief.text }}</p></details>
          <details v-if="S.caseIntro"><summary>案件卷宗</summary><p>{{ S.caseIntro.title }}</p><p>{{ S.caseIntro.summary }}</p><small>{{ S.caseIntro.attribution }}</small></details>
          <button v-if="canExposeV587" type="button" class="btn ghost sm" @click="exposeV587">观察笔记</button>
          <button v-if="canWhisper" type="button" class="btn ghost sm" :disabled="!socialReady || S.npcWaveBusy" @click="askNpcWave">{{ S.npcWaveBusy ? '正在依次发言…' : '请 AI 角色依次发言' }}</button>
          <p v-if="!socialReady && canWhisper" class="dim tiny">{{ S.ended ? '本局已结束' : '单人局和联机局均通过服务端 AI，对局连接建立后可用' }}</p>
        </div>

        <div class="cs-mid">
          <div class="chat-tabs" role="tablist" aria-label="聊天频道">
            <button :class="{on: chatMode==='public'}" @click="chatMode='public'">公共群聊</button>
            <button v-if="teamAvailable" :class="{on: chatMode==='team'}" @click="chatMode='team'">{{ S.mode === 'party' ? '小队频道' : 'AI 小队' }}</button>
            <button :class="{on: chatMode==='private'}" @click="chatMode='private'">私聊</button>
          </div>
          <div v-if="chatMode==='team'" class="team-picker"><span>本小队成员</span><button v-for="c in aiCandidates" :key="c.id" :class="{on: teamMembers.includes(c.id)}" @click="toggleTeamMember(c.id)">{{ c.name }}</button><small v-if="!teamMembers.length">未选择时显示全部 AI</small></div>
          <div class="cs-stage">
            <div class="cs-ring r1"></div>
            <div class="cs-ring r2"></div>
            <div class="cs-hub"><span>知乎</span></div>
            <button v-for="c in seats" :key="c.id" class="cs-seat" :class="seatCls(c)"
                    :style="{ left: c.x + '%', top: c.y + '%' }"
                    @click="selectTarget(c.id)" :disabled="c.id === playerCharId" :title="c.name + (c.id === playerCharId ? ' · 你' : '')">
              <img :src="c.avatar" :alt="c.name">
              <i v-if="speakId === c.id" class="cs-seat-live"></i>
              <span class="cs-seat-name">{{ c.name }}{{ c.id === playerCharId ? ' · 你' : '' }}</span>
              <em v-if="c.id === 'char_08' && v587On" class="chip tiny">三层已揭</em>
            </button>
          </div>
          <div class="cs-feed" ref="listEl">
            <div v-for="m in shown" :key="m.id" class="cs-bubble" :class="m.actor">
              <span v-if="m.whisper" class="pp-whisper-badge">私</span>
              <b v-if="m.actor === 'npc'">{{ m.name || (M.chars.find(c => c.id === m.char_id) || {}).name || '嫌疑人' }}</b>
              <b v-else-if="m.actor === 'dm'">DM · {{ studioPack ? '系统提示音' : '刘看山' }}</b>
              <b v-else-if="m.actor === 'me'">我</b>
              <b v-else-if="m.actor === 'peer'">{{ m.name || '队友' }}</b>
              <span v-if="m.heart" class="heart-tag">心声 · 未公开</span>
              <span v-if="m.ai_provider && (m.actor === 'npc' || m.actor === 'dm')" class="chip tiny" :class="aiSrcBadge(m.ai_provider).cls">{{ aiSrcBadge(m.ai_provider).text }}</span>
              {{ m.text }}
            </div>
            <div v-if="!shown.length" class="cs-bubble sys">当前频道还没有消息。</div>
            <div v-if="S.aiTyping" class="cs-bubble npc typing">
              <b>{{ S.aiTyping.name }}</b>
              <span class="typing-dots"><i></i><i></i><i></i></span> 正在发言…
            </div>
            <div class="pp-v587" v-if="v587On">
              <b>V587 · 三层身份</b>
              <ol>
                <li>新用户</li>
                <li>侦探爱好者联盟</li>
                <li>影子学徒</li>
              </ol>
            </div>
          </div>
        </div>

        <aside class="cs-hot" v-if="showHot">
          <div class="cs-hot-hd"><b>常驻热搜榜</b><span>TOP5</span></div>
          <div v-for="(h, i) in hotTop" :key="i" class="cs-hot-item" :class="{ top: i === 0 }"
               @click="S.view='hotfeed'">
            <img src="/assets/official/kanshan/kanshan_portrait.png" alt="">
            <span class="t">{{ h.title }}</span>
            <span class="hot">{{ h.hot || 'TOP' + (i + 1) }}</span>
          </div>
        </aside>
      </div>

      <div class="cs-bottom">
        <div class="cs-compose-group" role="group" aria-label="搜证">
        <span class="cs-compose-label">知乎搜索 · 寻找线索</span>
        <template v-if="showSearch">
          <button v-for="item in kwPool.slice(0, 3)" :key="item.k + item.loc" class="cs-kw" type="button"
                  :class="{ on: kw === item.k }" @click="pickKw(item)">{{ item.k }}</button>
          <input v-model="kw" maxlength="30" aria-label="搜证关键词" placeholder="输入关键词搜证…" @keyup.enter="doSearch">
          <voice-mic v-model="kw" :submit="doSearch" :maxlength="30"></voice-mic>
          <button class="cs-chip" type="button" @click="doSearch">搜证 1AP</button>
        </template>
        <span v-else class="cs-btag dim">破冰结束才能搜证</span>
        </div>
        <div class="cs-compose-group" role="group" aria-label="对话">
        <span class="cs-compose-label">{{ chatMode === 'public' ? '公共群聊' : chatMode === 'team' ? (S.mode === 'party' ? '小队频道' : 'AI 小队') : '私聊 · ' + cur.name }}</span>
        <span v-if="searchHint" class="dim tiny" aria-live="polite">{{ searchHint }}（会消耗 1 行动力）</span>
        <template v-if="canWhisper">
          <button type="button" class="btn ghost sm" :class="{ on: chatMode === 'private' || whisperOn }" :disabled="!socialReady || sendingPrivate" @click="chatMode = chatMode === 'private' ? 'public' : 'private'; whisperOn = chatMode === 'private'">私聊</button>
          <select v-if="whisperOn || chatMode === 'private'" v-model="whisperTo" class="pp-whisper" aria-label="私聊对象">
            <option value="" disabled>{{ whisperTargets.length ? '选队友或 AI' : '暂无目标' }}</option>
            <option v-for="p in whisperTargets" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </template>
        <input v-model="input" maxlength="200" aria-label="对话内容" :placeholder="whisperOn ? '输入私聊内容…' : '请输入内容…'"
               @keyup.enter="send" :disabled="S.busy || S.isSpectator">
        <voice-mic v-model="input" :submit="send" :disabled="S.busy || S.isSpectator" :maxlength="200"></voice-mic>
        <button class="cs-send" type="button" @click="send" :disabled="S.busy || S.isSpectator || sendingPrivate">{{ sendingPrivate ? '等待回复…' : '发送' }}</button>
        </div>
      </div>

      <div class="cs-advance-bar" v-if="S.studioNeedAdvance">
        <button type="button" @click="startInvestigate">开始搜证 ▸</button>
      </div>

      <div class="pp-firstvote modal-mask" v-if="fvShow">
        <div class="modal">
          <div class="modal-hd">
            <h3>举手表决（非正式，只喂弹幕）</h3>
          </div>
          <div class="modal-bd">
            <p class="dim">本轮指认只喂弹幕梗，不影响结局。</p>
            <div class="pp-firstvote-grid" v-if="S.firstVote.open && !S.firstVote.done">
              <button v-for="c in suspects" :key="c.id" type="button" class="btn ghost sm"
                      :disabled="S.busy || S.isSpectator" @click="castFirstVote(c.id)">{{ c.name }}</button>
            </div>
            <div v-if="S.firstVote.done">
              <p>本轮最可疑：<b>{{ fvName }}</b></p>
              <button type="button" class="btn primary sm" @click="closeFirstVote">关闭</button>
            </div>
          </div>
        </div>
      </div>

      <bet-panel v-if="showBet && !S.demo && modOn('bet')"></bet-panel>
      <danmaku-layer :items="S.dmaku"></danmaku-layer>
    </section>`
  };

  window.VIEWS.chat = ChatView;
})();
