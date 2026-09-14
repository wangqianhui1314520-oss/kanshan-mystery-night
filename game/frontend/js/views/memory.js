/* ============================================================
 * views/memory.js —— 记忆修复 · 心晴诊室绿主题（仿参考设计稿 3）
 * 布局：标题「记忆修复 · 心晴诊室」→ 8 角色卡横排（立绘+修复/开导+状态图标+左右箭头）
 *       → 双层记忆对比（said/heart）+ 篡改点 → 心晴档案胶片条（开导语录）
 *       → 底部档位：普通/心晴档案放映/隐藏结局「全员心晴」
 * 保留：记忆修复(2AP)/知识开导(2AP)/记忆拼图对质/急诊红灯 全部逻辑
 * ============================================================ */
(function () {
  const { ref, computed, watch } = Vue;

  const MemoryView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const sel = ref('char_04');
      const cur = computed(() => M.chars.find(c => c.id === sel.value));
      const online = computed(() => window.Store.liveSession());
      const remote = computed(() => S.liveMemories[sel.value]);
      watch(() => [sel.value, S.sessionId, S.netKind], () => { if (online.value) window.Store.loadMemory(sel.value); }, { immediate: true });
      const mems = computed(() => M.memories[sel.value] || []);
      const ownedVer = computed(() => S.memVer[sel.value] || 1);
      const curMem = computed(() => online.value ? remote.value || null : mems.value[Math.min(ownedVer.value, mems.value.length) - 1] || null);

      const said = computed(() => curMem.value ? curMem.value.blocks.filter(b => b.layer === 'said') : []);
      const heartOpenFor = c => !!(S.heartUnlocked[c.id] || (S.memVer[c.id] || 1) > 1);
      const heart = computed(() => {
        if (!heartOpenFor({ id: sel.value })) return [];
        return curMem.value ? curMem.value.blocks.filter(b => b.layer === 'heart' || b.integrity === 'deleted') : [];
      });
      const diff = computed(() => curMem.value ? curMem.value.diff || [] : []);

      const canRepair = computed(() => online.value ? !!(remote.value && remote.value.can_repair) : mems.value.length > ownedVer.value);
      const repair = (cid) => { const target = typeof cid === 'string' ? cid : sel.value; sel.value = target; return window.Store.send('skill', { kind: 'memory_fix', target }); };
      const openClinic = () => { S.view = 'clinic'; };
      const reloadMemory = () => window.Store.loadMemory(sel.value);

      const integCls = b => ({ edited: b.integrity === 'edited', deleted: b.integrity === 'deleted', heart: b.layer === 'heart' });
      const verPips = c => { const n = (M.memories[c.id] || []).length; return Array.from({ length: n }, (_, i) => i + 1); };
      const hasHeart = c => {
        if (online.value) return !!(S.liveMemories[c.id] && S.liveMemories[c.id].heart_unlocked);
        if (!heartOpenFor(c)) return false;
        const v = S.memVer[c.id] || 1;
        return (M.memories[c.id] || []).slice(0, v).some(m => m.blocks.some(b => b.layer === 'heart'));
      };

      /* 角色卡状态（参考图：✅已修复 / 开导可 / ❌失败 / 未解锁） */
      const repaired = c => (S.memVer[c.id] || 1) > 1 || hasHeart(c);
      const counseled = c => (S.counsel || []).some(x => x.char_id === c.id && x.ok);
      const cardStatus = c => {
        if (repaired(c)) return { icon: '✅', label: '成功', cls: 'ok' };
        if (counseled(c)) return { icon: '✅', label: '已开导', cls: 'ok' };
        if (canRepairFor(c)) return { icon: '', label: '修复', cls: 'ready' };
        return { icon: '✖', label: '未解锁', cls: 'off' };
      };
      const canRepairFor = c => online.value ? (!S.liveMemories[c.id] || S.liveMemories[c.id].can_repair) : (M.memories[c.id] || []).length > (S.memVer[c.id] || 1);

      /* 心晴档案：开导记录语录（胶片条） */
      const clinicCards = computed(() => {
        const list = (S.counsel || []).map(x => ({
          id: x.char_id + x.kc_id, ok: x.ok,
          quote: (x.lines && x.lines[0]) || '（本次开导记录）',
          signer: (M.chars.find(c => c.id === x.char_id) || {}).name || ((window.Labels && window.Labels.who(x.char_id)) || '在场者')
        }));
        while (list.length < 7) list.push({ id: 'pad' + list.length, ok: null, quote: '第「' + (list.length + 1) + '」条开导记录，将在此显影。', signer: '—— 心晴档案' });
        return list.slice(0, 9);
      });
      const clinicTier = computed(() => {
        const n = (S.counsel || []).filter(x => x.ok).length;
        if (n >= 4) return { txt: '隐藏结局「全员心晴」已达线', cls: 'gold' };
        if (n >= 2) return { txt: '心晴档案放映', cls: 'green' };
        return { txt: '普通', cls: 'dim' };
      });
      const stripIdx = ref(3);
      const stripMove = d => { stripIdx.value = Math.max(0, Math.min(clinicCards.value.length - 1, stripIdx.value + d)); };

      /* ---- V31 P2：记忆拼图对质（保留既有逻辑） ---- */
      const puzzle = ref(null);
      const shuffle = arr => arr.map(v => [Math.random(), v]).sort((a, b) => a[0] - b[0]).map(x => x[1]);
      const openPuzzle = () => {
        if (online.value) {
          if (!remote.value || S.tamperPts < 2) return;
          const blocks = (remote.value.blocks || []).map((b, i) => ({ ...b, key: String(i), char: cur.value.name }));
          if (!blocks.length) return;
          S.memoryPuzzleResult = null;
          puzzle.value = { target: sel.value, online: true, blocks, order: shuffle(blocks.map(b => b.key)), running: true };
          return;
        }
        window.Store.send('skill', { kind: 'memory_puzzle' });
        setTimeout(startPuzzle, 400);
      };
      const startPuzzle = () => {
        const blocks = [];
        M.chars.filter(c => c.id !== 'dm' && M.memories[c.id]).forEach(c => {
          const v = Math.min(S.memVer[c.id] || 1, M.memories[c.id].length);
          M.memories[c.id].slice(0, v).forEach(mv => mv.blocks.forEach(b => {
            if (b.layer === 'heart' && !heartOpenFor(c)) return;
            if (b.time && blocks.length < 8 && !blocks.some(x => x.id === c.id + b.id)) blocks.push({ id: c.id + b.id, char: c.name, time: b.time, text: b.text.slice(0, 48), layer: b.layer });
          }));
        });
        const picked = shuffle(blocks).slice(0, 5);
        puzzle.value = { correct: picked.slice().sort((a, b) => a.time.localeCompare(b.time)).map(x => x.id), blocks: picked, order: shuffle(picked.map(x => x.id)), running: true };
      };
      const move = (idx, d) => {
        const p = puzzle.value; if (!p) return;
        const j = idx + d; if (j < 0 || j >= p.order.length) return;
        [p.order[idx], p.order[j]] = [p.order[j], p.order[idx]];
      };
      const submitPuzzle = () => {
        const p = puzzle.value; if (!p || !p.running) return;
        if (p.online) {
          const proposal = p.order.map(key => p.blocks.find(b => b.key === key).id);
          if (window.Store.send('skill', { kind: 'puzzle', target: p.target, proposal }) !== false) p.running = false;
          return;
        }
        p.running = false;
        const ok = p.order.join() === p.correct.join();
        window.Store.send('skill', { kind: 'memory_puzzle_submit', ok });
        setTimeout(() => { puzzle.value = null; }, 1600);
      };

      return { S, M, sel, cur, mems, ownedVer, curMem, said, heart, diff, canRepair, repair, integCls, verPips, hasHeart,
               repaired, counseled, cardStatus, canRepairFor, clinicCards, clinicTier, stripIdx, stripMove,
               puzzle, openPuzzle, move, submitPuzzle, online, remote, openClinic, reloadMemory };
    },
    template: `
    <section class="view memory-view mem-clinic">

      <!-- 标题：终局 tag + 心晴诊室 -->
      <header class="mc-hd">
        <span class="mc-tag">终局</span>
        <h2 class="mc-title">「心晴诊室」</h2>
        <span class="mc-hex right"></span>
      </header>

      <div class="inv-cta" v-if="S.act >= 2 || S.demo">
        <div>
          <b>记忆会被改，回答也会</b>
          <p class="dim">对照同一篇知乎原文和水军改写版——干扰项是「看起来像操纵的原句」。</p>
        </div>
        <button class="btn primary sm" type="button" @click="S.view='pollution'">去污染对照 →</button>
      </div>

      <!-- 角色卡横排（立绘 + 修复/开导 + 状态） -->
      <div class="mc-row">
        <button class="mc-arrow" @click="stripMove(-1)" title="上一人">‹</button>
        <div class="mc-cards">
          <div v-for="c in M.chars.filter(x=>x.id!=='dm' && M.memories[x.id])" :key="c.id"
               class="mc-char" :class="[{ sel: sel === c.id }, cardStatus(c).cls]" @click="sel = c.id">
            <img :src="c.avatar" :alt="c.name">
            <button class="mc-act" :disabled="S.busy || S.ap < 2 || (S.act < 2 && !S.demo) || !canRepairFor(c)"
                    @click.stop="repair(c.id)" :title="'记忆修复 → V' + ((S.memVer[c.id]||1)+1) + ' · 2AP'">
              {{ canRepairFor(c) ? '记忆修复' : '已修复' }}
            </button>
            <span class="mc-st" :class="cardStatus(c).cls">{{ cardStatus(c).icon || '·' }}</span>
            <b>{{ c.name }}</b>
            <span class="mc-st-label">{{ cardStatus(c).label }}</span>
          </div>
        </div>
        <button class="mc-arrow" @click="stripMove(1)" title="下一人">›</button>
      </div>

      <!-- 双层记忆对比（选中角色） -->
      <div class="mem-toolbar">
        <button class="btn ghost" @click="openClinic">去心晴诊室开导</button>
        <button v-if="online" class="btn ghost" @click="reloadMemory">刷新已解锁记忆</button>
        <span class="dim">{{ online ? '仅展示本局已解锁的口供和心声' : '本地演示档案' }}</span>
      </div>
      <div class="mem-body" v-if="curMem">
        <div class="mem-toolbar">
          <div><b>{{ cur.name }}</b> · 记忆 V{{ ownedVer }}<span class="dim">（其对话口径已随版本切换）</span></div>
          <button class="btn purple" :disabled="S.busy || S.tamperPts < 2 || !!puzzle" @click="openPuzzle" title="V31 记忆拼图对质">
            🧩 记忆拼图对质 · 2 篡改点（持有 {{ S.tamperPts }}）
          </button>
          <span v-if="S.act < 2 && !S.demo && canRepair" class="dim">第二幕解锁（设置面板可开演示模式提前体验）</span>
        </div>

        <div class="diff-zone" v-if="diff.length">
          <div v-for="(d,i) in diff" :key="i" class="diff-item" :class="{tamper: d.tamper}">
            <span class="diff-tag">{{ d.tamper ? '⚠ 篡改点 ' + (i+1) : '版本差异' }}</span>{{ d.change }}
          </div>
        </div>

        <div class="compare" :class="{single: !heart.length}">
          <div class="cmp-col said">
            <h4>口供层（对外版本）</h4>
            <div v-for="b in said" :key="b.id" class="mem-block" :class="integCls(b)">
              <span class="mb-time">{{ b.time }}</span>
              <span class="mb-int" v-if="b.integrity!=='original'">{{ b.integrity==='edited' ? '已篡改' : '已删除' }}</span>
              <p>{{ b.text }}</p>
            </div>
            <div v-if="!said.length" class="dim pad">该版本口供层为空。</div>
          </div>
          <div class="cmp-col heart-col">
            <h4>心声层（开导后才会浮现）</h4>
            <div v-for="b in heart" :key="b.id" class="mem-block" :class="integCls(b)">
              <span class="mb-time">{{ b.time }}</span>
              <span class="mb-int" v-if="b.integrity==='deleted'">被删除段</span>
              <p>{{ b.text }}</p>
            </div>
            <ux-state v-if="!heart.length" dense glyph="♡" title="心声层未解锁"
              desc="先在「心晴诊室」用知识卡开导成功，这里的真实记忆才会浮现——口供与心声对不上的那一段，就是被篡改过的。"></ux-state>
          </div>
        </div>
      </div>
      <ux-state v-else dense glyph="◫" title="该角色暂无记忆档案"
        desc="换一个当事人试试——八个人各自记得一段今晚，拼起来才是完整的时间线。"></ux-state>

      <!-- 心晴档案胶片条 -->
      <h3 class="mc-strip-hd">心晴档案</h3>
      <div class="mc-strip">
        <button class="mc-strip-arrow" @click="stripMove(-1)">‹</button>
        <div class="mc-films">
          <div v-for="(f, i) in clinicCards" :key="f.id" class="mc-film"
               :class="{ gold: stripIdx === i, bad: f.ok === false, blank: f.ok === null }">
            <p>{{ f.quote }}</p>
            <span>—— {{ f.signer }}</span>
          </div>
        </div>
        <button class="mc-strip-arrow" @click="stripMove(1)">›</button>
      </div>

      <!-- 档位显示 -->
      <div class="mc-tier" :class="clinicTier.cls">
        普通 / 心晴档案放映 / 隐藏结局「全员心晴」 —— 当前档位：<b>{{ clinicTier.txt }}</b>
      </div>

      <!-- V31 P2：记忆拼图对质面板（保留） -->
      <ui-modal v-if="puzzle" title="记忆拼图对质 · 60 秒" wide @close="puzzle=null">
        <div class="puzzle-panel">
          <div class="puzzle-hd">
            <span class="chip warn">消耗 2 篡改点</span>
            <span class="dim">把该角色已解锁的记忆块按<b>时间先后</b>排好。提交后由引擎核对，消耗 2 篡改点。</span>
            <countdown-ring :seconds="60" :running="puzzle.running" label="拼图倒计时" @done="submitPuzzle"></countdown-ring>
          </div>
          <div class="puzzle-list">
            <div v-for="(id,i) in puzzle.order" :key="id" class="puzzle-item">
              <span class="mono puzzle-idx">{{ i + 1 }}</span>
              <div class="puzzle-text">
                <b>{{ (puzzle.blocks.find(x=>(puzzle.online ? x.key : x.id)===id)||{}).char }}</b>
                <span class="dim">{{ (puzzle.blocks.find(x=>(puzzle.online ? x.key : x.id)===id)||{}).text }}</span>
              </div>
              <div class="puzzle-ops">
                <button class="btn ghost sm" @click="move(i,-1)" :disabled="i===0">↑</button>
                <button class="btn ghost sm" @click="move(i,1)" :disabled="i===puzzle.order.length-1">↓</button>
              </div>
            </div>
          </div>
          <button class="btn primary big" :disabled="!puzzle.running" @click="submitPuzzle">提交排序（引擎判定）</button>
          <p v-if="puzzle.online && !puzzle.running" role="status">{{ S.memoryPuzzleResult ? S.memoryPuzzleResult.text : '已提交，等待裁决；若收到错误提示，请关闭后重新打开。' }}</p>
        </div>
      </ui-modal>
    </section>`
  };

  window.VIEWS.memory = MemoryView;
})();
