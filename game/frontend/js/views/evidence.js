/* ============================================================
 * views/evidence.js —— 证据拼图（B 证据链可视化）+ 阵营博弈（C 策反）+ 茧房出口
 * 玩法：把已搜线索「钉」到真相网络 → 覆盖 8 个真相节点（其中 6 个核心节点决定指认覆盖度）；
 *       覆盖 ≥50% 可策反被裹挟者（流量酱 char_03 / 路人甲 char_04）；困于茧房时在此也能破茧。
 * 动作经 Store.send 映射为 skill（evidence_pin / defect / cocoon_break），Mock 与 WS 共用事件名。
 * ============================================================ */
(function () {
  const { ref, computed } = Vue;

  const CORE_NODES = ['tn_01', 'tn_02', 'tn_03', 'tn_04', 'tn_05', 'tn_06']; // 与 store.js GUILTY_NODES 对齐

  const EvidenceView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const Store = window.Store;

      const truthNodes = computed(() => M.truthNodes || []);
      const collected = computed(() =>
        Object.keys(S.clues).map(id => M.clues.find(c => c.id === id) || {
          id, name: (window.Labels && window.Labels.clue(id)) || '线索', linked: [], fact: '引擎发放的线索'
        }));
      const coveredArr = computed(() => S.evidenceLinks.flatMap(l => l.nodes || []));
      const cov = computed(() => Store.evidenceCoverage());
      const complicit = computed(() =>
        ['char_03', 'char_04'].map(id => M.chars.find(c => c.id === id)).filter(Boolean));
      const cocoonActive = computed(() => S.cocoon && S.cocoon.active && !(S.cocoon.broken > 0));

      const isCore = (id) => CORE_NODES.includes(id);
      const isCovered = (id) => coveredArr.value.includes(id);
      const isPinned = (id) => S.evidenceLinks.some(l => l.clueId === id || l.clue_id === id);
      const flipped = (id) => !!(S.defection[id] && S.defection[id].flipped);

      const pin = (c) => { if (!isPinned(c.id)) Store.send('evidence_pin', { clueId: c.id }); };
      const defect = (id) => Store.send('defect', { charId: id });
      const breakCocoon = () => Store.send('cocoon_break', {});

      const L = window.Labels;
      return { S, M, L, Store, truthNodes, collected, cov, complicit, cocoonActive,
               isCore, isCovered, isPinned, flipped, pin, defect, breakCocoon };
    },
    template: `
    <section class="view evidence-view">
      <header class="view-hd">
        <h2>证据拼图 · 真相网络</h2>
        <div class="hd-chips">
          <span class="chip" :class="{ good: cov.pct >= 75 }">核心真相节点覆盖 {{ cov.pct }}%</span>
          <span class="chip" v-if="S.cocoon && S.cocoon.active" :class="S.cocoon.broken > 0 ? 'good' : 'warn'">
            {{ S.cocoon.broken > 0 ? '🦋 已破茧' : '🫧 困于信息茧房' }}</span>
        </div>
      </header>

      <div class="ev-board">
        <!-- 左：真相节点 -->
        <div class="ev-col">
          <h3>真相节点（{{ truthNodes.length }}）</h3>
          <div class="ev-nodes">
            <div v-for="n in truthNodes" :key="n.id" class="ev-node" :class="{ on: isCovered(n.id), core: isCore(n.id) }">
              <b>{{ n.name }}</b>
              <em v-if="isCore(n.id)">核心</em>
            </div>
          </div>
          <div class="ev-meter">
            <div class="bar"><i :style="{ width: cov.pct + '%' }"></i></div>
            <span>{{ cov.pct }}% · 已拼 {{ cov.total }} 节点</span>
          </div>
        </div>

        <!-- 右：证据线索 -->
        <div class="ev-col">
          <h3>已搜线索（点选钉入拼图）</h3>
          <div v-if="!collected.length" class="ev-empty dim">先去「现场搜证」拿到线索，它们才会出现在这里。</div>
          <div class="ev-clues">
            <button v-for="c in collected" :key="c.id" class="ev-clue" :class="{ on: isPinned(c.id) }" @click="pin(c)">
              <b>{{ c.name }}</b>
              <small class="ev-access">{{ c.tier==='limited' ? '仅持有者可见' : c.tier==='fake' ? '公开池·存疑' : c.tier==='hidden' ? '隐藏线索' : '可公开' }}</small>
              <span class="ev-tags">{{ L.nodes(c.linked) || '暂无关联节点' }}</span>
              <em v-if="isPinned(c.id)">✓ 已钉</em>
            </button>
          </div>
        </div>
      </div>

      <!-- 阵营博弈 / 茧房出口 -->
      <div class="ev-foot">
        <div class="ev-war">
          <h3>C 阵营博弈 · 策反被裹挟者</h3>
          <p class="dim" v-if="cov.pct < 50">证据覆盖 ≥50% 才能说服被裹挟者跳反（当前 {{ cov.pct }}%）。</p>
          <div class="ev-defects">
            <button v-for="ch in complicit" :key="ch.id" class="ev-defect" :disabled="cov.pct < 50 || flipped(ch.id)"
                    :class="{ on: flipped(ch.id) }" @click="defect(ch.id)">
              {{ ch.name }} {{ flipped(ch.id) ? '✓ 已策反' : '策反' }}
            </button>
          </div>
        </div>
        <div class="ev-cocoon" v-if="cocoonActive">
          <p>🫧 信息茧房生效中——热搜已被折叠投喂。</p>
          <button class="hf-break" type="button" @click="breakCocoon">🦋 破茧见真相</button>
        </div>
      </div>
    </section>`
  };

  window.VIEWS.evidence = EvidenceView;
})();
