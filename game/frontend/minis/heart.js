/* ============================================================
 * minis/heart.js —— M2《心声窃听器》（GAMEPLAY_V31 §9.4 / minis.md §M2）
 * 玩法：每题两句——一句口供（said）、一句心声（heart），指认哪句是心声；
 * 答完揭示教学点（"口供与心声对不上的地方 = 篡改点"，第二幕双层记忆教学）。
 * 数据源：GET /api/minis/memory-puzzle?tier=open（免登录外链，零额度）→
 *        POST /api/minis/heart-quiz 判定（answer/teaching 服务端持有，零透出）；
 *        无后端（file:// / Mock）降级 D 题库本地判定。
 * 安放位：免登录外链 #/mini/heart + 主线第二幕开场热身关 + 复盘页。
 * ============================================================ */
(function () {
  const { ref, computed, onMounted } = Vue;

  /* D 题库降级池（minis.md §M2 原文；answer 全 B=第二句为心声——展示时随机换位） */
  const LOCAL_BANK = [
    { tier: 'open', npc: '看山Bot', said: '系统日志：缓存清理，完成。', heart: '（内核）我留下了哈希值——这是我能做到的最大限度的诚实。', teaching: '机器不能撒谎，只能措辞' },
    { tier: 'open', npc: '沉底君', said: '档案室有动静，我没看清。[已折叠]', heart: '（心声）看清了，全部看清了。可是说了也会被折叠吧。', teaching: '被折叠的是勇气，不是发言' },
    { tier: 'open', npc: '盐值君', said: '我 21:47 发现异常，立刻留言了。', heart: '（心声）其实 21:40 就看到了，纠结了 7 分钟……我好怂。', teaching: '"立刻"是自我美化的常用词' },
    { tier: 'open', npc: 'V587', said: '新人报道！第一次见这种场面！！', heart: '（心声）新人味要足：感叹号多，问题傻，乱点赞。', teaching: '人设是演的，心声是实录' },
    { tier: 'open', npc: '流量酱', said: '我一直在茶水间泡面。', heart: '（心声）只有五分钟！发完就走！可我的手为什么在抖。', teaching: '时间对不上的地方要重点听' },
    { tier: 'open', npc: '路人甲', said: '我 20:55 就在前台值班了。', heart: '（心声）其实是代班……顺手赚杯奶茶的那种。', teaching: '"值班/代班"一字之差' },
    { tier: 'full', npc: '知之者', said: '我全程在大厅安抚人心。', heart: '（心声）后台数据很稳，47 个号都在岗。', teaching: '疑似组织者口径（剧情深水区）' },
    { tier: 'full', npc: '看山Bot', said: '系统日志：例行缓存清理。', heart: '（内核）本次清理由外部指令触发，\'例行\'二字存疑。', teaching: '机器措辞补丁=篡改点（tp_04）' },
    { tier: 'full', npc: '路人甲', said: '21:15 我什么都没看见。', heart: '（心声）毛茸茸的，拎着个袋子？我记不清了……', teaching: '目击被\'批量优化\'误伤（tp_02b）' },
    { tier: 'full', npc: '笔上仙', said: '我在档案室找灵感。', heart: '（心声）存证芯片目录很有戏剧性……我就看了标题！', teaching: '写手的心虚也带剧情感' }
  ];
  const SETTLE = { win: '叮——窃听成功。心声已解密，但请温柔使用。', lose: '叮——这是口供（嘴硬版）。心声从来不加班。', outro: '看懂了吗？接下来一整幕，你们都在听这个。' };
  const TOTAL_Q = 5;

  /* 后端探测：http(s) 页面 → 同源；file:// → 无后端（本地降级） */
  function apiBase() {
    try {
      const p = new URLSearchParams(location.search);
      const ws = p.get('ws');
      if (ws) return ws.replace(/^ws/, 'http').split('/ws')[0];
      if (/^https?:/.test(location.protocol)) return location.origin;
    } catch (e) { }
    return null;   // file:// 直开 → 本地降级
  }

  const MiniHeart = {
    setup() {
      const S = window.Store ? window.Store.state : { act: 1 };
      const phase = ref('ready');   // ready | play | over
      const q = ref(null);          // 展示题 {npc, A, B, heartIsB}
      const idx = ref(0), score = ref(0);
      const verdict = ref(null);    // {ok, teaching, settle}
      const lastReport = ref(null);
      const best = ref(window.Minis.bestOf('heart', 'score'));
      const sourceNote = ref('');
      const useFull = ref(false);   // 登录局内热身关可用 full 题

      function pickLocal(tier) {
        const pool = LOCAL_BANK.filter(x => x.tier === (tier || 'open'));
        return pool[Math.floor(Math.random() * pool.length)];
      }
      async function nextQuestion() {
        verdict.value = null;
        if (idx.value >= TOTAL_Q) return finish();
        let item = null;
        const base = apiBase();
        if (base) {
          try {
            const tierQ = useFull.value ? 'full' : 'open';
            const r = await fetch(`${base}/api/minis/memory-puzzle?tier=${tierQ}`);
            const j = await r.json();
            if (j.ok && j.item) { item = { npc: j.item.npc, said: j.item.said, heart: j.item.heart, _viaApi: true }; sourceNote.value = j.tier === 'open' ? '免登录热身题，不含案情词。' : '本局记忆对照题。'; }
          } catch (e) { sourceNote.value = '后端不可达——降级 D 题库本地判定（minis.md §M2 原题）'; }
        } else sourceNote.value = '本地降级：D 题库（minis.md §M2）';
        if (!item) item = pickLocal(useFull.value ? 'full' : 'open');
        // 展示换位：随机交换 said/heart 展示顺序（answer 坐标映射由选择句文本比对得出）
        const heartIsB = Math.random() < 0.5;
        q.value = { npc: item.npc, A: heartIsB ? item.said : item.heart, B: heartIsB ? item.heart : item.said, item };
        idx.value += 1;
        if (phase.value !== 'play') phase.value = 'play';
      }
      function answerPicked(which) {
        if (verdict.value || !q.value) return;
        const it = q.value.item;
        const pickedText = which === 'A' ? q.value.A : q.value.B;
        const answer = pickedText === it.heart ? 'B' : 'A';   // 回传题库坐标（B=心声位）
        const base = apiBase();
        const judgeLocal = () => {
          const ok = pickedText === it.heart;
          const teaching = (LOCAL_BANK.find(x => x.npc === it.npc && x.heart === it.heart) || {}).teaching || '';
          showVerdict(ok, teaching, true);
        };
        if (it._viaApi && base) {
          fetch(base + '/api/minis/heart-quiz', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item: { npc: it.npc, said: it.said, heart: it.heart }, answer })
          }).then(r => r.json()).then(j => {
            if (j && typeof j.correct === 'boolean') showVerdict(j.correct, j.teaching || '', false);
            else judgeLocal();
          }).catch(judgeLocal);
        } else judgeLocal();
      }
      function showVerdict(ok, teaching, local) {
        if (ok) score.value += 1;
        verdict.value = { ok, teaching, settle: ok ? SETTLE.win : SETTLE.lose, local };
      }
      function nextOrFinish() { if (idx.value >= TOTAL_Q) finish(); else nextQuestion(); }
      function finish() {
        phase.value = 'over';
        const grade = score.value >= 4 ? '金牌窃听员' : score.value >= 2 ? '入门窃听生' : '心声绝缘体';
        lastReport.value = { score: score.value, total: TOTAL_Q, grade };
        const rec = window.Minis.reportScore('heart', { score: score.value, total: TOTAL_Q });
        best.value = window.Minis.bestOf('heart', 'score');
      }
      function start(full) { useFull.value = !!full; idx.value = 0; score.value = 0; phase.value = 'play'; nextQuestion(); }
      const doShare = () => window.Minis.download(window.Minis.REG.heart, {
        lines: [['答对', lastReport.value.score + '/' + lastReport.value.total], ['评级', lastReport.value.grade], ['历史最佳', best.value + '/5']],
        report: `心声窃听器战报：${lastReport.value.score}/${lastReport.value.total}——${lastReport.value.grade}。口供与心声对不上的地方 = 篡改点。`
      }).then(r => { if (!r.ok) window.alert(r.notice); });

      onMounted(() => { if (!apiBase()) sourceNote.value = '本地降级：D 题库（minis.md §M2）'; });

      return { S, phase, q, idx, score, verdict, lastReport, best, sourceNote, start, answerPicked, nextOrFinish, doShare, TOTAL_Q, SETTLE };
    },
    template: `
    <div class="mini-heart">
      <div class="mh-hud">
        <span class="chip blue">第 {{ Math.min(idx, TOTAL_Q) }}/{{ TOTAL_Q }} 题</span>
        <span class="chip gold">答对 {{ score }}</span>
        <span class="chip">历史最佳 {{ best }}/5</span>
      </div>

      <div v-if="phase==='ready'" class="mh-card">
        <h3>心声窃听器</h3>
        <p>每题播两句——一句<b>口供</b>、一句<b>心声</b>，指认哪句是心声；答完揭示教学点："口供与心声对不上的地方 = 篡改点"（第二幕双层记忆教学）。</p>
        <p class="dim">{{ sourceNote || '免登录即可试玩。热身题不含案情词。' }}</p>
        <div class="mh-start">
          <button class="btn primary big" @click="start(false)">开始（免登录 · open 题）</button>
          <button class="btn ghost" v-if="S.netKind==='ws'" @click="start(true)">登录局内热身关（含 full 题）</button>
        </div>
      </div>

      <div v-else-if="phase==='play' && q" class="mh-card">
        <p class="mh-npc">🎧 正在窃听：<b>{{ q.npc }}</b></p>
        <button class="mh-line" :class="{picked: verdict && verdict.ok === (q.A===q.item.heart)}" @click="answerPicked('A')" :disabled="!!verdict">「{{ q.A }}」</button>
        <button class="mh-line" :class="{picked: verdict && verdict.ok === (q.B===q.item.heart)}" @click="answerPicked('B')" :disabled="!!verdict">「{{ q.B }}」</button>
        <p class="dim">哪句是心声？点它（口供与心声，必有一句在表演）。</p>
        <div v-if="verdict" class="mh-verdict" :class="{ok: verdict.ok}">
          <b>{{ verdict.settle }}</b>
          <span class="dim">教学点：{{ verdict.teaching || '——' }}</span>
          <button class="btn primary" @click="nextOrFinish">{{ idx >= TOTAL_Q ? '看战报' : '下一题' }}</button>
        </div>
      </div>

      <div v-else-if="phase==='over' && lastReport" class="mh-card">
        <h3>热身关收尾</h3>
        <p class="mh-final">答对 <b class="mono">{{ lastReport.score }}/{{ lastReport.total }}</b> · 评级「{{ lastReport.grade }}」</p>
        <p class="dim">{{ SETTLE.outro }}</p>
        <div class="mh-start">
          <button class="btn primary" @click="start(useFull)">再来一轮</button>
          <button class="btn warn" @click="doShare">生成分享卡 → PNG</button>
          <button class="btn ghost" @click="$minisClose">回游戏厅</button>
        </div>
      </div>
      <p class="dim mh-src">{{ sourceNote }}</p>
    </div>`
  };

  window.Minis.register({
    id: 'heart', title: '心声窃听器', tagline: '两句里指认真心声——口供与心声对不上的地方 = 篡改点。',
    entry: '免登录外链 #/mini/heart + 主线第二幕开场热身关 + 复盘页', source: 'GET /api/minis/memory-puzzle（open 免登录 / full 登录局内）→ POST /api/minis/heart-quiz 判定；无后端降级 D 题库',
    component: MiniHeart
  });
})();
