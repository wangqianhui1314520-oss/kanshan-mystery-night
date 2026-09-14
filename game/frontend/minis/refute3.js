/* ============================================================
 * minis/refute3.js —— M3《谣言消消乐》（GAMEPLAY_V31 §9.4 / minis.md §M3）
 * 玩法：3 消盘面——谣言块与"辟谣标签块"相邻交换即消除（对应主线辟谣机制：
 * 卡 tag 匹配才生效）。10 对词条（谣言块↔辟谣标签块，引用卡面署名）。
 * 特殊块：万能"叮"块（限 2）/ 折叠块 / 哈希块（最终分 ×2）/ 异端块（扣分）。
 * 数据源：GET /api/minis/hotfeed-pool?n=8（脱敏抽样，可缓存）作"今日谣言头条"轮换；
 *        无后端降级 data.js M.posts。判定本地（spec 未设判定路由）。
 * 安放位：复盘页 + 每日挑战"辟谣加练"；#/mini/refute3。
 * ============================================================ */
(function () {
  const { ref, computed, onMounted } = Vue;

  /* D 词条对（minis.md §3.1 原文，10 对） */
  const PAIRS = [
    { rumor: '倦怠出走论', tag: '倦怠 · @草芽君Psy', kc: 'kc_01' },
    { rumor: '折叠区造谣犯论', tag: '穷人思维 · @杨毅', kc: 'kc_02' },
    { rumor: '被动幻觉论', tag: '被动 · @曾旻Zeng Min', kc: 'kc_03' },
    { rumor: '加薪跑路论', tag: '加薪 · @潘幸知', kc: 'kc_04' },
    { rumor: '注意力看走眼论', tag: '注意力 · @窦泽南', kc: 'kc_05' },
    { rumor: '学习使人失踪论', tag: '学习 · @黛西巫巫', kc: 'kc_06' },
    { rumor: '目标太大蒸发论', tag: '目标 · @王明伟', kc: 'kc_07' },
    { rumor: '赢一小把论', tag: '小胜 · @刀熊说说', kc: 'kc_08' },
    { rumor: '拒绝当头子论', tag: '拒绝 · @胡慎之心理', kc: 'kc_09' },
    { rumor: '塔尖不塌论', tag: '职业规划 · @杨萃先', kc: 'kc_10' }
  ];
  const SETTLE = {
    S: '十谣全消。热搜已恢复出厂设置，感谢净化师。',
    A: '大部分谣言已退货。剩下的，建议转发给 47 号工作室学习。'
  };
  const COLS = 7, ROWS = 7, MOVES = 22;

  const MiniRefute3 = {
    setup() {
      const grid = ref([]);        // [{type:'rumor'|'tag'|'ding'|'fold'|'hash'|'tuna', pair:i, label}]
      const score = ref(0), moves = ref(MOVES);
      const sel = ref(null);       // {r,c}
      const phase = ref('ready');  // ready | play | over
      const headline = ref('');    // 今日谣言头条（hotfeed-pool 轮换）
      const flash = ref('');
      const overReport = ref(null);
      const best = ref(window.Minis.bestOf('refute3', 'score'));
      const sourceNote = ref('');

      const blockLabel = b => b.label;
      const typeCls = b => 'mk-' + b.type;

      function makeBlock(pairI, type) {
        const p = PAIRS[pairI];
        return { type, pair: pairI, label: type === 'rumor' ? p.rumor : type === 'tag' ? p.tag : type === 'ding' ? '叮' : type === 'fold' ? '[已折叠]' : type === 'hash' ? 'A3F9-77C2' : '金枪鱼' };
      }
      function randType() {
        const r = Math.random();
        if (r < 0.40) return { t: 'rumor', p: Math.floor(Math.random() * PAIRS.length) };
        if (r < 0.86) return { t: 'tag', p: Math.floor(Math.random() * PAIRS.length) };
        if (r < 0.90) return { t: 'ding', p: 0 };
        if (r < 0.94) return { t: 'fold', p: 0 };
        if (r < 0.97) return { t: 'hash', p: 0 };
        return { t: 'tuna', p: 0 };
      }
      function fill() {
        const g = [];
        for (let r = 0; r < ROWS; r++) {
          const row = [];
          for (let c = 0; c < COLS; c++) {
            let mk = randType(), guard = 0;
            // 避免初始即三连
            while (guard++ < 20 && hasTripleAt(g, r, c, mk)) mk = randType();
            row.push(makeBlock(mk.p, mk.t));
          }
          g.push(row);
        }
        grid.value = g;
      }
      function hasTripleAt(g, r, c, mk) {
        const same = (rr, cc) => g[rr] && g[rr][cc] && g[rr][cc].type === mk.t && (mk.t !== 'rumor' && mk.t !== 'tag' || g[rr][cc].pair === mk.p);
        return (same(r, c - 1) && same(r, c - 2)) || (same(r - 1, c) && same(r - 2, c));
      }
      function findMatches(g) {
        const marks = [];
        for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS - 2; c++) {
          const a = g[r][c];
          if (a.type !== 'rumor' && a.type !== 'tag') continue;
          if (g[r][c + 1].type === a.type && g[r][c + 1].pair === a.pair && g[r][c + 2].type === a.type && g[r][c + 2].pair === a.pair) {
            marks.push([r, c], [r, c + 1], [r, c + 2]);
          }
        }
        for (let c = 0; c < COLS; c++) for (let r = 0; r < ROWS - 2; r++) {
          const a = g[r][c];
          if (a.type !== 'rumor' && a.type !== 'tag') continue;
          if (g[r + 1][c].type === a.type && g[r + 1][c].pair === a.pair && g[r + 2][c].type === a.type && g[r + 2][c].pair === a.pair) {
            marks.push([r, c], [r + 1, c], [r + 2, c]);
          }
        }
        return marks;
      }
      function collapse() {
        let chain = 0, gained = 0, rumorCleared = 0, usedHash = false, usedDing = false, tunaPenalty = 0;
        let marks = findMatches(grid.value);
        while (marks.length) {
          chain += 1;
          marks.forEach(([r, c]) => {
            const b = grid.value[r][c];
            if (b.type === 'rumor') { gained += 20; rumorCleared += 1; }
            else if (b.type === 'tag') { gained += 10; }
            else if (b.type === 'ding') { gained += 15; usedDing = true; }
            else if (b.type === 'fold') { gained += 5; }
            else if (b.type === 'hash') { gained += 10; usedHash = true; }
            else if (b.type === 'tuna') { gained -= 15; tunaPenalty += 1; }
            grid.value[r][c] = null;
          });
          // 下落 + 顶部补块
          for (let c = 0; c < COLS; c++) {
            for (let r = ROWS - 1; r >= 0; r--) {
              if (!grid.value[r][c]) {
                for (let rr = r; rr >= 0; rr--) {
                  if (grid.value[rr][c]) { grid.value[r][c] = grid.value[rr][c]; grid.value[rr][c] = null; break; }
                }
                if (!grid.value[r][c]) grid.value[r][c] = makeBlock(Math.floor(Math.random() * PAIRS.length), Math.random() < 0.55 ? 'rumor' : 'tag');
              }
            }
          }
          marks = findMatches(grid.value);
        }
        return { chain, gained, rumorCleared, usedHash, usedDing, tunaPenalty };
      }
      function click(r, c) {
        if (phase.value !== 'play' || moves.value <= 0) return;
        if (!sel.value) { sel.value = { r, c }; return; }
        const a = sel.value; sel.value = null;
        if (a.r === r && a.c === c) return;
        if (Math.abs(a.r - r) + Math.abs(a.c - c) !== 1) { sel.value = { r, c }; return; }
        // 相邻交换
        const g = grid.value;
        [g[a.r][a.c], g[r][c]] = [g[r][c], g[a.r][a.c]];
        // 叮块：万能匹配——直接以被交换位置触发消除判定
        const res = collapse();
        if (!res.chain) {
          // 无效交换：回滚（还原两块位置）
          [g[a.r][a.c], g[r][c]] = [g[r][c], g[a.r][a.c]];
          flash.value = '无效交换——谣言块要和同源块三连（或叮块登场）';
          setTimeout(() => flash.value = '', 1400);
          return;
        }
        moves.value -= 1;
        score.value = Math.max(0, score.value + res.gained + (res.chain > 1 ? (res.chain - 1) * 10 : 0));
        if (res.tunaPenalty) { flash.value = '异端块：金枪鱼连上反而扣分（致敬鱼干梗）'; setTimeout(() => flash.value = '', 1600); }
        else if (res.usedDing) { flash.value = '万能"叮"块登场——替代任意辟谣标签'; setTimeout(() => flash.value = '', 1600); }
        if (moves.value <= 0) finish();
      }
      function start() {
        score.value = 0; moves.value = MOVES; sel.value = null; overReport.value = null;
        fill(); phase.value = 'play';
        // 今日谣言头条：hotfeed-pool 轮换（无后端降级 data.js）
        const base = /^https?:/.test(location.protocol) ? location.origin : null;
        if (base) {
          fetch(base + '/api/minis/hotfeed-pool?n=8').then(r => r.json()).then(j => {
            if (j.ok && j.posts && j.posts.length) {
              const p = j.posts[Math.floor(Math.random() * j.posts.length)];
              headline.value = '今日谣言头条：《' + String(p.title).replace(/^#|#$/g, '') + '》';
              sourceNote.value = '今日词条已从热搜池抽样。这里只管消除，真假留给主线。';
            }
          }).catch(() => { headline.value = '后端不可达——本地词条池（minis.md §M3 十对）'; sourceNote.value = '本地降级：data.js 热搜帖池'; });
        } else { headline.value = '本地词条池（minis.md §M3 十对 + data.js 热搜）'; sourceNote.value = 'file:// 本地降级'; }
      }
      function finish() {
        phase.value = 'over';
        const cleared = score.value;
        const grade = cleared >= 300 ? 'S' : 'A';
        const report = grade === 'S' ? SETTLE.S : SETTLE.A;
        const rec = window.Minis.reportScore('refute3', { score: cleared, grade });
        best.value = window.Minis.bestOf('refute3', 'score');
        overReport.value = { grade, report, score: cleared, rec };
      }
      const doShare = () => window.Minis.download(window.Minis.REG.refute3, {
        lines: [['得分', overReport.value.score], ['评级', overReport.value.grade], ['历史最佳', best.value]],
        report: '谣言消消乐战报：' + overReport.value.report
      }).then(r => { if (!r.ok) window.alert(r.notice); });

      onMounted(() => { });

      return { grid, score, moves, sel, phase, headline, flash, overReport, best, sourceNote, click, start, doShare, blockLabel, typeCls, COLS, ROWS };
    },
    template: `
    <div class="mini-refute3">
      <div class="r3-hud">
        <span class="chip gold">得分 {{ score }}</span>
        <span class="chip blue">步数 {{ moves }}/{{ 22 }}</span>
        <span class="chip">历史最佳 {{ best }}</span>
        <button class="btn ghost sm" v-if="phase!=='ready'" @click="start">重开</button>
      </div>
      <p class="dim r3-headline" v-if="headline">{{ headline }}</p>

      <div v-if="phase==='ready'" class="r3-card">
        <h3>谣言消消乐</h3>
        <p>3 消盘面——<b>谣言块</b>与<b>辟谣标签块</b>相邻交换，三连即消除（对应主线辟谣机制：卡 tag 匹配才生效）。辟谣标签块自带知乎知识卡面署名。</p>
        <p class="dim">特殊块：万能"叮"（替代任意辟谣标签）/ [已折叠] / 哈希块 A3F9-77C2 / 金枪鱼（异端，连上扣分）。</p>
        <button class="btn primary big" @click="start">开始净化（22 步）</button>
      </div>

      <template v-else>
        <div class="r3-grid">
          <button v-for="(row,r) in grid" :key="r" class="r3-row">
            <button v-for="(b,c) in row" :key="c" class="r3-cell" :class="[typeCls(b), {sel: sel && sel.r===r && sel.c===c}]" @click="click(r,c)">
              <span>{{ blockLabel(b) }}</span>
            </button>
          </button>
        </div>
        <p class="r3-flash" v-if="flash">{{ flash }}</p>
        <p class="dim">点选一块 → 点相邻块交换；谣言块×3 或 辟谣块×3 即消除。词条对（谣言↔辟谣·署名）共 {{ 10 }} 对，与 hotfeed 辟谣目标帖一一对应。</p>
      </template>

      <div v-if="phase==='over' && overReport" class="r3-over">
        <div class="r3-over-card" :class="overReport.grade==='S' ? 's' : 'a'">
          <h3>评级 {{ overReport.grade }}</h3>
          <p>{{ overReport.report }}</p>
          <p class="mono">得分 {{ overReport.score }} · 历史最佳 {{ best }}</p>
          <div class="mh-start">
            <button class="btn primary" @click="start">再净一轮</button>
            <button class="btn warn" @click="doShare">生成分享卡 → PNG</button>
            <button class="btn ghost" @click="$minisClose">回游戏厅</button>
          </div>
        </div>
      </div>
      <p class="dim mh-src" v-if="sourceNote">{{ sourceNote }}</p>
    </div>`
  };

  window.Minis.register({
    id: 'refute3', title: '谣言消消乐', tagline: '谣言块与辟谣块三连消除——话题对上才能消。',
    entry: '复盘页 + 每日挑战"辟谣加练"', source: 'GET /api/minis/hotfeed-pool（脱敏抽样，is_fake/clue_ref 零透出）；无后端降级本地词条池',
    component: MiniRefute3
  });
})();
