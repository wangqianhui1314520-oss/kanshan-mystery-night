/* ============================================================
 * views/clinic.js —— 心晴诊室（知识开导 2AP / 心晴档案 / 终局结算）
 * ============================================================ */
(function () {
  const { ref, computed } = Vue;

  const ClinicView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const tab = ref('counsel');
      const npc = ref('char_06');
      const kcId = ref('');
      const replay = ref(false);

      const npcs = computed(() => M.chars.filter(c => c.id !== 'dm'));
      const ownedKcs = computed(() => Object.keys(S.kcards).map(id => M.kcards.find(k => k.id === id)).filter(Boolean));
      const curNpc = computed(() => M.chars.find(c => c.id === npc.value));
      const match = computed(() => {
        const kc = M.kcards.find(k => k.id === kcId.value);
        if (!kc || !curNpc.value) return null;
        return kc.binds === curNpc.value.id || kc.binds === 'all' || (curNpc.value.kcAlt && kc.binds === curNpc.value.kcAlt);
      });
      const matchName = computed(() => {
        const kc = M.kcards.find(k => k.id === kcId.value); if (!kc) return '';
        if (kc.binds === 'all') return '全队通用（团队 buff）';
        const c = M.chars.find(x => x.id === kc.binds);
        return c ? `匹配对象：${c.name}` : kc.binds === 'org' ? '匹配对象：档案局（组织谜题）' : '';
      });
      const doCounsel = () => window.Store.send('counsel', { char_id: npc.value, kc_id: kcId.value });
      const charStatus = (c) => {
        const recs = (S.counsel || []).filter(r => r.char_id === c.id);
        const last = recs[recs.length - 1];
        if (last && last.ok) return { icon: '✓', label: '成功', cls: 'ok' };
        if (last && !last.ok) return { icon: '✕', label: '失败', cls: 'bad' };
        if (S.heartUnlocked[c.id]) return { icon: '✓', label: '成功', cls: 'ok' };
        return { icon: '·', label: '开导', cls: 'ready' };
      };
      const filmCards = computed(() => {
        const list = (S.counsel || []).map(x => ({
          id: x.char_id + (x.kc_id || '') + (x.at || ''),
          ok: x.ok,
          quote: (x.lines && x.lines[0]) || '（本次开导记录）',
          signer: whoOf(x.char_id)
        }));
        while (list.length < 8) list.push({ id: 'pad' + list.length, ok: null, quote: '第「' + (list.length + 1) + '」条开导记录，将在此显影。', signer: '—— 心晴档案' });
        return list.slice(0, 8);
      });
      const stripIdx = ref(Math.min(3, Math.max(0, (S.counsel || []).length - 1)));
      const stripMove = (d) => { stripIdx.value = Math.max(0, Math.min(filmCards.value.length - 1, stripIdx.value + d)); };
      const pickNpc = (id) => { npc.value = id; };
      const counselAt = (id) => {
        npc.value = id;
        if (!kcId.value) { window.Store.toast('先选一张知识卡', 'warn'); return; }
        doCounsel();
      };
      const okCount = computed(() => S.counsel.filter(r => r.ok).length);
      const tier = computed(() => okCount.value >= 4 ? { name: '隐藏结局线 · 全员心晴', desc: '开导 4+ 人：看山会自己推门回来认领鱼干。', cls: 'gold' }
        : okCount.value >= 2 ? { name: '心晴档案 · 放映中', desc: '开导 2-3 人：复盘时加映全员金句回放。', cls: 'good' }
        : { name: '普通档位', desc: '开导 0-1 人：结局照常，心病各自带走（不拆穿）。', cls: '' });
      const records = computed(() => S.counsel.slice().reverse());
      const whoOf = id => (window.Labels && window.Labels.who(id)) || (M.chars.find(c => c.id === id) || {}).name || '在场者';
      const kcOf = id => M.kcards.find(k => k.id === id) || {};
      const avatarOf = id => (M.chars.find(c => c.id === id) || {}).avatar || '';

      /* ---- V31 P1：心病急诊室（红灯 = 开导失败挂灯；下一轮内抢救 = 双倍） ---- */
      const erList = computed(() => Object.keys(S.er).map(cid => {
        const ch = M.chars.find(c => c.id === cid);
        return { cid, name: ch ? ch.name : ((window.Labels && window.Labels.who(cid)) || '在场者'), avatar: ch ? ch.avatar : '', expiry: S.er[cid], urgent: S.er[cid] <= S.round };
      }));
      const statusWord = cid => ((M.erLines.status || {})[cid] || {}).red || '病情恶化中（戏剧性病危）';
      const erHint = computed(() => '红灯规则：开导失败自动挂灯，有效期=当前轮+1；下一轮内带<b>对口</b>知识卡抢救=收益双倍；同一 NPC 每局限挂一次（第二次失败只群嘲）。');
      /* 红灯"啪"转绿闪光（抢救成功 0.5s 演出，3.5s 内可见） */
      const erGreen = computed(() => {
        if (!S.erGreen || Date.now() - S.erGreen.at > 3500) return null;
        const ch = M.chars.find(c => c.id === S.erGreen.cid);
        return ch ? ch.name : ((window.Labels && window.Labels.who(S.erGreen.cid)) || '在场者');
      });

      return { S, M, tab, npc, kcId, replay, npcs, ownedKcs, curNpc, match, matchName, doCounsel, okCount, tier, records, erList, statusWord, erHint, erGreen, whoOf, kcOf, avatarOf, charStatus, filmCards, stripIdx, stripMove, pickNpc, counselAt };
    },
    template: `
    <section class="view clinic-view mem-clinic">
      <header class="mc-hd">
        <span class="mc-tag">终局</span>
        <h2 class="mc-title">「心晴诊室」</h2>
      </header>

      <div class="er-strip" v-if="erList.length">
        <div v-for="e in erList" :key="e.cid" class="er-lamp" :class="{urgent: e.urgent}">
          <span class="er-bulb"></span>
          <div class="er-info">
            <b>{{ e.name }}</b>
            <span class="dim">{{ statusWord(e.cid) }}</span>
          </div>
          <button class="btn danger sm" @click="pickNpc(e.cid)">去抢救 →</button>
        </div>
        <p class="dim er-hint" v-html="erHint"></p>
      </div>
      <div class="er-strip idle" v-else-if="erGreen">
        <div class="er-green-flash"><span class="er-bulb green"></span><b>{{ erGreen }}</b> 的红灯转成了心晴绿。</div>
      </div>

      <div class="mc-row">
        <button class="mc-arrow" type="button" @click="stripMove(-1)" title="上一人">‹</button>
        <div class="mc-cards">
          <div v-for="c in npcs" :key="c.id"
               class="mc-char" :class="[{ sel: npc === c.id, healed: !!S.heartUnlocked[c.id] }, charStatus(c).cls]"
               @click="pickNpc(c.id)">
            <img :src="c.avatar" :alt="c.name">
            <button class="mc-act" type="button" :disabled="S.busy || S.ap < 2 || S.isSpectator"
                    @click.stop="counselAt(c.id)">开 导</button>
            <span class="mc-st" :class="charStatus(c).cls">{{ charStatus(c).icon }}</span>
            <b>{{ c.name }}</b>
            <span class="mc-st-label">{{ charStatus(c).label }}</span>
          </div>
        </div>
        <button class="mc-arrow" type="button" @click="stripMove(1)" title="下一人">›</button>
      </div>

      <div class="cl-kc">
        <div class="kc-pick">
          <button v-for="kc in ownedKcs" :key="kc.id" class="kc-pick-item" :class="{match: kc.id===kcId}" @click="kcId=kc.id">
            <b>《{{ kc.title }}》</b><span>{{ kc.author }}</span>
          </button>
          <ux-state v-if="!ownedKcs.length" dense glyph="🃏" title="暂无知识卡"
            desc="去「现场搜证 → 心晴自习室」抽卡。空着手去开导，只能得到一场真挚的尬聊。"></ux-state>
        </div>
        <p v-if="kcId" class="match-preview" :class="match ? 'good' : 'warn'">
          {{ match ? '心病匹配：先专业后破防' : '不匹配：尬聊现场 + 群嘲' }}
          <em class="dim">{{ matchName }}</em>
        </p>
      </div>

      <h3 class="mc-strip-hd">心晴档案</h3>
      <div class="mc-strip">
        <button class="mc-strip-arrow" type="button" @click="stripMove(-1)">‹</button>
        <div class="mc-films">
          <div v-for="(f, i) in filmCards" :key="f.id" class="mc-film"
               :class="{ gold: stripIdx === i, bad: f.ok === false, blank: f.ok === null }">
            <p>{{ f.quote }}</p>
            <span>—— {{ f.signer }}</span>
          </div>
        </div>
        <button class="mc-strip-arrow" type="button" @click="stripMove(1)">›</button>
      </div>

      <div class="mc-tier" :class="tier.cls">
        普通 / 心晴档案放映 / 隐藏结局「全员心晴」 —— 当前档位：<b>{{ tier.name }}</b>
      </div>
    </section>`
  };

  window.VIEWS.clinic = ClinicView;
})();
