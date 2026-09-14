/* ============================================================
 * minis/badge.js —— M4《侦探证每日抽》（GAMEPLAY_V31 §9.4 / minis.md §M4）
 * 玩法：登录后每日一抽（日活钩子）——按 uid+日期确定性抽取：
 *   今日警衔花名（D §M4 花名池 22 条，关键词匹配无命中走通用档——对齐 C 组 pick_headline）
 *   + 今日运势 + 今日幸运话题。分享卡=侦探证 + 今日签（每日唯一可分享）。
 * 数据源：GET /api/profile/me（隐私三件套：fullname/headline/avatar_path/uid；
 *        无缓存时返回 authorize_url 引导 OAuth）——无后端降级 mock dossier。
 * 安放位：侦探档案页（登录后建局前）；#/mini/badge。
 * ============================================================ */
(function () {
  const { ref, computed, onMounted } = Vue;

  /* D 花名池降级版（minis.md §M4 通用档；关键词映射与 dossierRanks 对齐） */
  const GENERIC_NAMES = ['折叠区巡夜人', '鱼干线索特别调查员', '弹幕意识观察员', '热度降噪工程师', '热搜水位观察员', '真相质检实习生', '哈希残页收藏家', '档案局夜班门神'];
  const FORTUNES = [
    '今日宜搜证：你会在最不起眼的柜缝里，捡到最关键的便签。',
    '今日忌辟谣：引错卡被群嘲的概率 +47%，先对 tag 再出手。',
    '今日宜押注：眼光毒辣，赞数不赊账。',
    '今日忌私聊：你发出的每句话都会被弹幕复述一遍。',
    '今日宜偷听心声：但请温柔使用。',
    '今日忌吃金枪鱼：异端减速，罐身便签原话。',
    '今日宜跑酷：谣言追不上你，除非金枪鱼背叛你。',
    '今日宜认领微光点：三袋鱼干在等你，风扇转速平稳。'
  ];
  const LUCKY_TOPICS = ['#不出真相不出此门#', '#谁动了我的鱼干#', '#档案局连夜吃瓜#', '#折叠区冤案再调查#', '#心晴自习室不占线#'];

  function hashCode(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) { h = (h * 31 + str.charCodeAt(i)) >>> 0; }
    return h;
  }
  function todayKey() { return new Date().toISOString().slice(0, 10); }
  function rankOf(headline) {
    const M = window.MOCK || {};
    const rule = (M.dossierRanks || []).find(r => r.test.test(headline || ''));
    return rule ? rule.rank : GENERIC_NAMES[hashCode(headline || 'x') % GENERIC_NAMES.length];
  }

  const MiniBadge = {
    setup() {
      const S = window.Store ? window.Store.state : { dossier: null, netKind: 'mock' };
      const phase = ref('idle');       // idle | drawing | done
      const drawn = ref(null);         // 今日签 {rank, fortune, topic, date}
      const profileNote = ref('');
      const alreadyToday = ref(false);
      const prof = ref(null);          // /api/profile/me 结果
      const authUrl = ref('');         // 服务端下发知乎授权 URL（oauth_configured 时非空）
      const loginNote = ref('');       // OAuth 登录/回调消费的结果提示

      const daySeed = computed(() => hashCode((prof.value ? prof.value.uid : 'guest') + todayKey()));
      const canDraw = computed(() => !alreadyToday.value);

      async function fetchProfile() {
        const base = /^https?:/.test(location.protocol) ? location.origin : null;
        const q = window.Store ? `?session_id=${encodeURIComponent(window.Store.state.sessionId)}&player_id=player:1` : '';
        if (!base) { profileNote.value = '本机直开：用演示档案抽签。登录后可换成你的公开资料。'; return null; }
        try {
          const r = await fetch(base + '/api/profile/me' + q);
          const j = await r.json();
          if (j.ok && j.profile) {
            prof.value = j.profile;
            profileNote.value = '已读取你的公开昵称、头像和简介，不读取邮箱或手机。';
            return j;
          }
          // 未登录：给 authorize_url 引导（F 返回 oauth_configured）
          authUrl.value = j.authorize_url || '';
          profileNote.value = (window.Labels ? window.Labels.plain(j.notice, '尚未登录') : (j.notice || '尚未登录'))
            + (j.authorize_url ? '。可前往知乎授权页登录。' : '。先用演示档案抽签。');
        } catch (e) { profileNote.value = '档案局连不上，先用演示档案抽签。'; }
        return null;
      }
      function draw() {
        if (!canDraw.value) return;
        phase.value = 'drawing';
        setTimeout(() => {
          const seed = daySeed.value;
          const rank = prof.value ? rankOf(prof.value.headline) : GENERIC_NAMES[seed % GENERIC_NAMES.length];
          drawn.value = {
            rank,
            fortune: FORTUNES[seed % FORTUNES.length],
            topic: LUCKY_TOPICS[(seed >> 3) % LUCKY_TOPICS.length],
            date: todayKey(),
            owner: prof.value ? prof.value.fullname : (S.dossier ? S.dossier.name : '匿名侦探'),
            badgeNo: prof.value ? (prof.value.uid || '000000').slice(-6) : (S.dossier ? S.dossier.uid6 : '000000'),
            avatar: (prof.value && prof.value.avatar_path) || (S.dossier ? S.dossier.avatar : '../content/assets/official/kanshan/kanshan.png')
          };
          try { localStorage.setItem('kanshan_badge_daily', JSON.stringify({ date: todayKey(), ...drawn.value })); } catch (e) { }
          alreadyToday.value = true;
          phase.value = 'done';
        }, 700);
      }
      const doShare = () => window.Minis.download(window.Minis.REG.badge, {
        lines: [['今日警衔', drawn.value.rank], ['幸运话题', drawn.value.topic], ['编号', 'ZH-' + drawn.value.badgeNo]],
        report: '今日签：' + drawn.value.fortune
      }).then(r => { if (!r.ok) window.alert(r.notice); });

      const goAuthorize = () => {
        if (authUrl.value) location.href = authUrl.value;
      };

      onMounted(async () => {
        // OAuth 回调闭环：oauth.js 捕获的 code 在此消费（有对局才可换登录态）
        if (window.ZhihuOAuthFlow && window.ZhihuOAuthFlow.hasPendingCode()) {
          const sid = (window.Store && window.Store.state && window.Store.state.sessionId) || '';
          const res = await window.ZhihuOAuthFlow.consume(sid, 'player:1');
          if (res.attempted) {
            loginNote.value = res.ok ? '知乎授权成功——《特聘侦探证》已签发。' : (res.notice || '登录未完成。');
            if (!res.ok) console.warn('[badge] OAuth consume failed:', res.notice);
          } else if (res.notice) {
            loginNote.value = res.notice;
          }
        }
        await fetchProfile();
        try {
          const saved = JSON.parse(localStorage.getItem('kanshan_badge_daily') || 'null');
          if (saved && saved.date === todayKey()) { drawn.value = saved; alreadyToday.value = true; phase.value = 'done'; }
        } catch (e) { }
      });

      return { S, phase, drawn, profileNote, alreadyToday, canDraw, draw, doShare, authUrl, loginNote, goAuthorize };
    },
    template: `
    <div class="mini-badge">
      <div class="mb-hd">
        <span class="chip gold">侦探证每日抽</span>
        <span class="chip" v-if="prof">已读取公开档案</span>
      </div>
      <p class="dim">{{ profileNote || '只用公开昵称、头像和简介抽签，不读取邮箱或手机。' }}</p>
      <p v-if="loginNote" class="dim mono">{{ loginNote }}</p>
      <button v-if="!prof && authUrl" class="btn primary" @click="goAuthorize">前往知乎授权登录 → 签发《特聘侦探证》</button>

      <div v-if="phase==='idle' || (phase==='drawing' && !drawn)" class="mb-card">
        <h3>今日侦探签</h3>
        <p>每日一抽：今日警衔花名 + 运势 + 幸运话题。同一身份当天抽到的是同一张签——档案局不接受改命。</p>
        <button class="btn primary big" :disabled="!canDraw" @click="draw">{{ alreadyToday ? '今日已抽（明天再来）' : '抽取今日签' }}</button>
        <button class="btn ghost" @click="draw" v-if="false">重抽</button>
      </div>

      <div v-if="phase==='drawing'" class="mb-drawing mono">抽取中… ███░░░░░（档案局打印机预热）</div>

      <div v-if="drawn" class="mb-result">
        <div class="dossier-body mb-ticket">
          <div class="dossier-photo"><img :src="drawn.avatar" alt="证件照"></div>
          <div class="dossier-info">
            <span class="dossier-org">今日侦探签 · {{ drawn.date }}</span>
            <b class="dossier-name">{{ drawn.owner }}</b>
            <span class="dossier-rank">今日警衔：{{ drawn.rank }}</span>
            <span class="dossier-headline">{{ drawn.fortune }}</span>
            <span class="dossier-meta mono">幸运话题 {{ drawn.topic }} · 编号 ZH-{{ drawn.badgeNo }}</span>
          </div>
        </div>
        <div class="mh-start">
          <button class="btn warn" @click="doShare">分享今日签 → PNG（每日唯一可分享）</button>
          <button class="btn ghost" @click="$minisClose">回游戏厅</button>
        </div>
      </div>
    </div>`
  };

  window.Minis.register({
    id: 'badge', title: '侦探证每日抽', tagline: 'uid+日期确定性抽签——今日警衔/运势/幸运话题，每日唯一可分享。',
    entry: '侦探档案页（登录后建局前）', source: 'GET /api/profile/me（隐私三件套）；无后端降级 mock 档案 + D 花名池',
    component: MiniBadge
  });
})();
