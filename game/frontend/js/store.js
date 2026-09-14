/* ============================================================
 * store.js —— Vue3 响应式状态 + 本地引擎（Mock 裁决逻辑）
 * 职责：state 唯一真源；Engine 只算不发（产出协议事件），applyEvent 只收不改协议。
 * 破绽计数 / 证据合成 / 覆盖度打分 均按 CONTRACTS §3.3-3.5 与 DM_BOSS_DESIGN 实现。
 * ============================================================ */
(function () {
  const { reactive, watch } = Vue;
  const M = window.MOCK;
  const SAVE_KEY = 'kanshan_save_v1';

  const state = reactive({
    phase: 'menu', prologueStep: 0, playerHeadline: '',
    mode: 'solo', roomCode: '', sessionId: '', playerId: '', isHost: false, shareUrl: '', lanBase: '',
    aiWaveKicked: '',
    npcWaveBusy: false,
    creatingRoom: false, roomFull: null, isSpectator: false,
    playerAvatar: '/assets/official/kanshan/kanshan_portrait.png',
    view: 'map',
    act: 1, round: 1, ap: 3, apMax: 3,
    heat: 35,
    joy: 0,               // 欢乐值：整蛊、搜错和彩蛋产生，可兑换欢乐技能
    goals: { faction: '', personal: '', fun: '' },
    flaws: {},            // flaw_id -> {at}
    clues: {},            // clueId -> {at}
    kcards: {},           // kcId -> {at}
    memVer: {},           // charId -> 拥有的版本数（默认 1）
    liveMemories: {}, memoryPuzzleResult: null,
    actBrief: null, heatReport: null,
    caseIntro: null, engineFlawCount: null,
    heartUnlocked: {},    // charId -> bool
    counsel: [],          // {char_id,kc_id,ok,reward,lines,at}
    refuted: {},          // postId -> {ok, kc_id}
    synth: [],            // 证据卡 {id,name,nodes,clueIds}
    posts: {},            // postId -> {refuted}
    hotfeedPanel: null,   // null=尚无服务端面板；[]=权威空面板
    hotfeedSignals: null,
    lastSearchResult: null,
    exposedFakes: {},     // fake clueId -> true（交叉验证拆穿）
    salt: 0,              // 盐言彩蛋碎片
    chat: [],
    aiLastDecision: null, // 最近一次 AI 行动诊断（来源/耗时/原因）
    currentNpc: 'dm',
    ended: false, ending: null, voteResult: null,
    dmaku: [], banners: [], toasts: [],
    /* 本地行为指标：只记录动作类型/结果/耗时，不采集文本或身份信息。 */
    telemetry: { actions: {}, events: {}, startedAt: Date.now() },
    searched: {},         // locId -> 次数
    busy: false, demo: false, bossSeen: false,
    netKind: 'mock', sessionId: '-',
    voteTarget: null, voteEvidence: [],
    /* ---- V31 增量（E 组）：押注/抽风/急诊/头条/电梯/侦探证/暗拍/拼图/反诈/陈词 ---- */
    zans: 10,               // 押注币=赞数（A 裁决 #3：不与热度/行动点混币）
    glitchFree: false,      // ap_free：下次行动免扣
    glitchPerAct: {},       // 每幕抽风计数（每幕至多 2 次）
    tamperPts: 0,           // 篡改点（记忆拼图对质消耗 2）
    photos: [],             // 暗拍照片 {id, clue_id, name, loc, at, shared, claim, exposed}
    er: {},                 // 急诊红灯 charId -> expiryRound
    erLimit: {},            // 急诊每局限一次 charId -> true
    bet: null,              // 押注局 {id, subject, options, wagers:{opt:{n,amt}}, round, open}
    betStreak: { target: null, count: 0 },
    headline: null,         // 头条竞标 {round, topic, note, bids:[{who,amount}], settled, winner}
    elevator: null,         // 幕间电梯转场 {to}
    dossier: null,          // 侦探证 {name, headline, avatar, uid6, rank, issued}
    report: null,           // 侦探报告 {report_text, badges, achievements, builtAt}
    hammer: null,           // 终局陈词 {speech, target, tally, most, at}
    antifraud: { count: 0, score: 0, active: false, act: 0, answers: [] },
    fish: {},               // P3 鱼干收集品 fish_01/02/03 -> {at}（微光点拾取）
    fishVoice: null,        // 集齐后看山Bot 隐藏语音演出 {line}（active 由非 null 表示）
    erGreen: null,          // 红灯转绿闪光 {cid, at}（抢救成功 0.5s 演出）
    /* ---- V4 综艺流程（G2）：showtime 状态机 intro/case_file/act/accuse/reveal + 幕转场 cut ----
     * intro=开场覆盖层（phase cover/prologue/license）；case_file=案件卷宗页（进入圆桌前）；
     * act=正常游玩；accuse=最终指认；reveal=揭晓复盘。cut={act:1|2|3} 幕转场全屏页（瞬时演出态）。
     * 默认 step='act'：回访玩家（localStorage 存档直进）不重播卷宗页。不入存档（纯演出态）。 */
    showtime: { step: 'act', cut: null },
    /* ---- V5 章节独占式（G2）：章首前情提要 {fromAct, text, gains:[]} ----
     * 消费 G4 memory_doc（服务端 system.recap 事件覆盖）；Mock 模式由 actSet 本地兜底生成。不入存档。 */
    recap: null,
    /* ---- 创新冲刺（A 信息茧房 / B 证据链 / C 策反 / D 求真人格） ---- */
    searchBias: {},          // tag -> 命中次数（玩家搜证偏好的隐形画像）
    cocoon: { active: false, broken: 0, revealed: 0 },  // 信息茧房态：active=已入茧, broken=破茧次数, revealed=本次破茧解封的真相帖数
    evidenceLinks: [],       // {a, b, node} 玩家手连的证据链
    defection: {},           // charId -> {flipped, by}（策反态：被裹挟者跳反）
    persona: null,           // 求真人格卡（结局生成）
    /* ---- V5 反操纵三件套（污染对照 / 回声 / 法官）+ 求真画像 ---- */
    pollution: { case: null, result: null, ammo: 0, earned: 0, done: {}, summary: null },
    echo: { log: [], seq: 0, challenge: null, result: null, defended: false, tease: 0 },
    debate: { open: false, stance: 'open', score: 0, need: 4, text: '', rounds: [], convinced: false },
    truthProfile: null,
    buyHeats: 0,
    /* ---- Studio 工作台（S3）：创一本 / 水合快本 ---- */
    studioJob: null,
    studioId: '',
    scenarioId: '',
    studioMeta: null,        // { title, hook, summary, logline, acts } 卷宗文案
    studioNeedAdvance: false, // 快本 break_ice：advance 前禁止进地图
    studioModules: null,     // 快本机制开关；null=看山全开
    studioMinis: null,       // 勾选的小游戏 id；null=看山全开
    studioVibe: '',
    studioType: '',
    studioCamp: null,
    studioBooks: [],         // /public 封面；旧本 / 看山本为 []
    stage: 'break_ice',        // break_ice | investigate | round_table | accuse（引擎 snapshot 覆盖）
    /* ---- 可玩补全：综艺/模式/隐藏层（不入瓜田废案） ---- */
    playMode: 'main',          // main | daily | quick
    skipIce: false,            // 每日/快速局：跳过破冰听介绍，仍留在搜证章
    dailyTopic: null,          // { topic, body, source }
    quiz: { open: false, idx: 0, q: '', options: [], score: 0, asked: 0, done: false, last: null, seen: [] },
    radio: { open: false, text: '', log: [], requestLeft: 3 },
    firstVote: { open: false, poll_id: '', pick: '', done: false, tally: null },
    officeOpen: false,
    office: { open: false, tries: 0 },
    flipped: {},               // clue_id -> { back, at }
    v587Exposed: false,
    v587: { exposed: false },
    partySeats: [],
    partyChar: '',
    playerBook: null,          // 领取后的故事本全本；无则为 null
    bookOpen: false,           // 局内重读遮罩
    bookletRole: 'investigator',
    bookletPack: null,
    bookletForced: null,
    bookletOpen: false,
    dmBookRead: false,       // DM 导演门控：玩家必须先读本再进入交流/搜证流程
    dmMiniSeen: {},           // DM 插入小游戏已接收节点
    myFactionHint: '',         // 仅自己可见的一句，不含他人阵营
    gradient: '',              // assist|normal|hard 展示用
    memoText: ''
  });
  M.chars.forEach(c => { if (!state.memVer[c.id]) state.memVer[c.id] = 1; });
  /* V31：R1 即开盘（押注 + 头条竞标），advance 后每轮重开（演示开局即可玩） */
  (function openRoundOne() {
    const bj = M.betLines.subjects[0];
    state.bet = { id: 'bet_r1', subject: bj.subject, options: bj.options.slice(), wagers: {}, round: 1, open: true };
    const ht = M.headlineTopics[0];
    state.headline = { round: 1, topic: ht.topic, note: ht.note, bids: [], settled: false, winner: null };
  })();
  // URL 直达视图（?view=chat 等导航 id），便于联调定位与验收
  // URL 直达视图（?view=chat 等导航 id），便于联调定位与验收；#/mini/{id} hash 路由由 minis 层接管
  try {
    const qv = new URLSearchParams(location.search).get('view');
    if (qv && ['map','chat','bag','kcards','memory','hotfeed','vote','clinic','review','ending','report','mini','pollution','quiz','radio'].includes(qv)) state.view = qv;
    if (window.__MINI_BOOT__ && window.Minis && window.Minis.REG[window.__MINI_BOOT__]) state.view = 'mini';
  } catch (e) { }

  /* ---------- 工具 ---------- */
  const rnd = arr => arr[Math.floor(Math.random() * arr.length)];
  const uid = () => 'x' + Math.random().toString(36).slice(2, 9);
  /* 引擎权威 id → 前端 mock 卡。WS 搜到 clue_028 时不能落到 data.js 里同名的「空调维保」。 */
  const ENGINE_TO_UI_CLUE = {
    clue_028: 'clue_001', clue_029: 'flavor_2', clue_030: 'flavor_3',
    clue_031: 'flavor_4', clue_032: 'flavor_5'
  };
  function uiClueId(id) {
    return ENGINE_TO_UI_CLUE[id] || id;
  }
  function mergeClueRecord(base, rec, id) {
    if (!rec) return base || null;
    const linked = [];
    const push = arr => (arr || []).forEach(x => { if (x && linked.indexOf(x) < 0) linked.push(x); });
    if (base) push(base.linked);
    push(rec.linked);
    if (!base) {
      if (!rec.name && !rec.text) return null;
      return {
        id, name: rec.name || id, fact: rec.text || '', flavor: rec.flavor || '',
        tier: rec.tier || 'public', tags: rec.tags || [], linked,
        flaw_id: rec.flaw_id || null, fake_of: rec.fake_of || null
      };
    }
    if (!rec.name && !rec.text && !rec.tier) return base;
    return Object.assign({}, base, {
      name: rec.name || base.name,
      fact: rec.text || rec.fact || base.fact,
      tier: rec.tier || base.tier,
      tags: (rec.tags && rec.tags.length) ? rec.tags : base.tags,
      linked: linked.length ? linked : base.linked,
      flaw_id: rec.flaw_id || base.flaw_id
    });
  }
  const clueById = id => {
    const uid = uiClueId(id);
    const base = M.clues.find(c => c.id === uid) || M.clues.find(c => c.id === id);
    const rec = (state.clues && (state.clues[uid] || state.clues[id])) || null;
    return mergeClueRecord(base, rec, uid);
  };
  function migrateEngineClues() {
    Object.keys(state.clues || {}).forEach(id => {
      const uid = uiClueId(id);
      if (uid === id) return;
      if (!state.clues[uid]) state.clues[uid] = state.clues[id];
      delete state.clues[id];
    });
  }
  const charById = id => M.chars.find(c => c.id === id);
  const kcById = id => M.kcards.find(k => k.id === id);
  const emitOwnedClue = (emit, id, extra) => {
    const c = clueById(id);
    if (!c || state.clues[c.id]) return;
    emit('clue_gained', Object.assign({
      clue_id: c.id, tier: c.tier, name: c.name,
      text: (c.fact || '') + ' ' + (c.flavor || ''),
      tags: c.tags || [], linked: c.linked || [], fake_of: null, flaw_id: c.flaw_id || null
    }, extra || {}));
  };
  const LOC_ALIAS = {
    loc_reception: { scene: 'reception', name: '前台' },
    loc_desk: { scene: 'desk_kanshan', name: '看山工位' },
    loc_teahouse: { scene: 'teahouse', name: '茶水间' },
    loc_locker: { scene: 'parcel_locker', name: '快递柜' },
    loc_monitor: { scene: 'monitor_room', name: '监控室' },
    loc_server: { scene: 'server_room', name: '服务器机房' },
    loc_archive: { scene: 'archive_room', name: '档案室' },
    loc_hotfeed: { scene: 'hotfeed_backstage', name: '热搜后台' },
    loc_ac: { scene: 'hvac_room', name: '空调机房' },
    loc_roof: { scene: 'roof', name: '天台' },
    loc_clinic: { scene: 'study_room', name: '心晴自习室' },
    loc_office: { scene: 'director_office', name: '局长办公室' }
  };
  function resolveLoc(raw) {
    const s = String(raw || '').trim();
    const loc = M.locations.find(l => l.id === s || l.name === s);
    if (loc) return { id: loc.id, scene: loc.id, name: loc.name };
    if (LOC_ALIAS[s]) return { id: s, ...LOC_ALIAS[s] };
    const byScene = Object.entries(LOC_ALIAS).find(([, v]) => v.scene === s);
    if (byScene) return { id: byScene[0], ...byScene[1] };
    const byName = Object.entries(LOC_ALIAS).find(([, v]) => v.name === s);
    if (byName) return { id: byName[0], ...byName[1] };
    return { id: s, scene: s, name: s };
  }
  const locById = id => {
    const r = resolveLoc(id);
    return M.locations.find(l => l.id === r.id) || { id: r.id, name: r.name };
  };

  /* 玩家可见明文：对象/接口体/内部 ID 一律收成中文，禁止 JSON 键上屏 */
  const Labels = (function () {
    const TIER = { public: '公开', limited: '限定', hidden: '隐藏', fake: '疑似伪造', boss_flaw: '看山破绽', core: '核心' };
    const MOD = {
      hotfeed: '热搜舆论', memory: '记忆修复', counsel: '开导策反', kcards: '知识卡',
      evidence: '证据拼图', pollution: '污染对照', bet: '弹幕押注', headline: '头条竞标',
      stealth: '暗拍', puzzle: '记忆拼图', antifraud: '反诈剧场', comedy_search: '搜错彩蛋',
      inner_boss: '里层 Boss', search: '现场搜证', chat: '圆桌对话', vote: '终局指认'
    };
    const MINI = { runner: '看山快跑', heart: '心声窃听器', refute3: '谣言消消乐', badge: '侦探证每日抽' };
    const EFFECT = { evidence: '证据', boss_key: '关键钥匙', memory_unlock: '记忆解锁', buff_ap: '行动点加成', plot_fragment: '剧情碎片' };
    const STAGE = { break_ice: '破冰', investigate: '搜证', round_table: '对质', accuse: '指认' };
    const MOOD = { comedy: '欢乐', horror: '恐怖', variety: '综艺', grim: '冷硬' };
    const JOB = { ready: '可开玩', compiled: '已编译', error: '未通过', failed: '未通过', pending: '生成中', ok: '已写成' };
    const STANCE = { hostile: '敌视', skeptical: '怀疑', open: '开放', convinced: '采信' };
    const ACT = { act1: '第一幕', act2: '第二幕', act3: '第三幕' };
    const PROVIDER = { llm: '模型代写', mock: '本地骨架', engine: '规则引擎', local: '本地草稿' };

    function zh(s) { return /[\u4e00-\u9fff]/.test(String(s || '')); }
    function who(id) {
      if (!id) return '在场者';
      const s = String(id);
      if (s.indexOf('player:') === 0) return '队友';
      if (s === 'dm') return '刘看山';
      if (s === 'investigator') return '特聘调查员';
      const ch = (M.chars || []).find(c => c.id === s);
      return (ch && ch.name) || '在场者';
    }
    function node(id) {
      const n = (M.truthNodes || []).find(t => t.id === id);
      return (n && n.name) || '真相节点';
    }
    function nodes(ids) {
      return (ids || []).map(node).filter(Boolean).join(' · ');
    }
    function place(id) {
      if (!id) return '现场';
      const raw = String(id);
      if (LOC_ALIAS[raw]) return LOC_ALIAS[raw].name;
      const loc = (M.locations || []).find(l => l.id === raw || l.name === raw);
      if (loc) return loc.name;
      const byScene = Object.entries(LOC_ALIAS).find(([, v]) => v.scene === raw);
      if (byScene) return byScene[1].name;
      if (raw.indexOf('loc_') === 0 || /^[a-z][a-z0-9_]*$/.test(raw)) return '现场';
      return raw;
    }
    function clue(id) {
      const c = (M.clues || []).find(x => x.id === id);
      if (c && c.name) return c.name;
      const s = String(id || '');
      if (s.indexOf('tamper_') === 0) return '篡改点';
      if (s.indexOf('salt_') === 0) return '盐言碎片';
      return '线索';
    }
    function cover(k) {
      return { A: '封甲 · 破冰', B: '封乙 · 心声', C: '封丙 · 热搜' }[k] || '已开封';
    }
    function unlock(s) {
      if (!s || s === '默认') return '';
      return scrub(String(s));
    }
    function scrub(s) {
      s = String(s || '');
      if (!s) return s;
      s = s.replace(/\bmemory:char_0?(\d):(\d+)\b/g, (_, n, v) => who('char_0' + n) + ' 的第 ' + v + ' 层记忆解锁后');
      s = s.replace(/\bevidence:([a-z0-9_]+)\b/g, (_, id) => '持有《' + clue(id) + '》后');
      s = s.replace(/\bcounsel:kc_\d+\b/g, '对口开导成功后');
      s = s.replace(/\becho:contradiction\b/g, '回声自证后');
      s = s.replace(/\bdebate:convinced\b/g, '法官采信后');
      s = s.replace(/\bact>=(\d)\b/g, (_, n) => '第' + '一二三'[Number(n) - 1] + '幕起');
      s = s.replace(/\bchar_0?(\d)\b/g, (_, n) => who('char_0' + n));
      s = s.replace(/\bloc_[a-z0-9_]+\b/g, m => place(m));
      s = s.replace(/\btn_\d+\b/g, m => node(m));
      s = s.replace(/\bclue_\d+\b/g, m => clue(m));
      s = s.replace(/\bsalt_f?\d+\b/g, '盐言碎片');
      s = s.replace(/\bfish_\d+\b/g, '鱼干');
      s = s.replace(/\bplayer:[A-Za-z0-9_:-]+\b/g, '队友');
      s = s.replace(/\bgen_pack_[a-z0-9_]+\b/gi, '工作台快本');
      s = s.replace(/\b(sess|session)[_-]?[A-Za-z0-9-]{6,}\b/gi, '本局');
      s = s.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, '本局');
      s = s.replace(/\bbreak_ice\b/g, '破冰');
      s = s.replace(/\bround_table\b/g, '对质');
      s = s.replace(/\bchat\/advance\b/g, '对话与进入下一章');
      s = s.replace(/\bengine\/\s*/gi, '规则引擎 · ');
      s = s.replace(/\bscenario_id\b/g, '剧本编号');
      s = s.replace(/\bsession_id\b/g, '本局');
      s = s.replace(/\bplayer_id\b/g, '玩家');
      s = s.replace(/\bchar_id\b/g, '角色');
      s = s.replace(/\bclue_id\b/g, '线索');
      s = s.replace(/\btopic_tag\b/g, '话题');
      s = s.replace(/\bfield required\b/gi, '缺少必填项');
      s = s.replace(/\bvalue is not a valid [A-Za-z]+\b/gi, '格式不对');
      s = s.replace(/^QUOTA:\s*/i, '配额：');
      s = s.replace(/^REF:\s*/i, '引用：');
      s = s.replace(/^FAKE:\s*/i, '伪证：');
      s = s.replace(/^TAG:\s*/i, '标签：');
      s = s.replace(/^KC:\s*/i, '知识卡：');
      s = s.replace(/^BLACKLIST:\s*/i, '禁写：');
      s = s.replace(/^READ:\s*/i, '读取：');
      return s;
    }
    function plain(v, fallback) {
      if (v == null || v === '') return fallback != null ? fallback : '';
      const t = typeof v;
      if (t === 'string') return scrub(v);
      if (t === 'number' || t === 'boolean') return String(v);
      if (Array.isArray(v)) {
        const parts = v.map(x => {
          if (typeof x === 'string') return scrub(x);
          if (x && typeof x === 'object') return scrub(x.msg || x.message || (typeof x.detail === 'string' ? x.detail : '') || x.text || x.notice || '');
          return '';
        }).filter(Boolean);
        return parts.length ? parts.join('；') : (fallback != null ? fallback : '操作未完成');
      }
      if (t === 'object') {
        if (typeof v.detail === 'string') return scrub(v.detail);
        if (Array.isArray(v.detail)) return plain(v.detail, fallback);
        const s = v.msg || v.message || v.notice || v.text || v.hint || v.title || v.name;
        if (s != null && typeof s !== 'object') return scrub(String(s));
        return fallback != null ? fallback : '操作未完成';
      }
      return fallback != null ? fallback : '';
    }
    function line(v) {
      if (v == null) return '';
      if (typeof v === 'string') return scrub(v);
      if (typeof v === 'object' && !Array.isArray(v))
        return scrub(v.text || v.hint || v.name || v.title || v.msg || v.you_are || '');
      return plain(v, '');
    }
    function tier(t) { return TIER[t] || '公开'; }
    function module(k) {
      if (window.STUDIO && window.STUDIO.MECHS) {
        const m = window.STUDIO.MECHS.find(x => x.key === k) || (window.STUDIO.CORE_MECHS || []).find(x => x.key === k);
        if (m && m.name) return m.name;
      }
      return MOD[k] || '机制';
    }
    function mini(id) {
      if (window.STUDIO && window.STUDIO.MINIS) {
        const m = window.STUDIO.MINIS.find(x => x.id === id);
        if (m && m.name) return m.name;
      }
      return MINI[id] || '小游戏';
    }
    function effect(e) { return EFFECT[e] || '特殊效果'; }
    function stage(s) {
      if (!s) return '本章';
      if (STAGE[s]) return STAGE[s];
      return zh(s) ? String(s) : '本章';
    }
    function mood(s) { return MOOD[s] || '欢乐'; }
    function stance(s) { return STANCE[s] || '开放'; }
    function act(id) { return ACT[id] || '本幕'; }
    function jobStatus(s) { return JOB[s] || '已写成'; }
    function provider(s) { return PROVIDER[s] || '档案局草稿'; }
    function jobLine(job) {
      if (!job) return '';
      return provider(job.provider) + ' · ' + jobStatus(job.status);
    }
    function session(id) {
      if (!id || id === '-' || String(id).indexOf('mock') === 0) return '本地试玩';
      return '本局已接通';
    }
    function packCaption(id, meta) {
      if (meta && meta.title) return meta.title;
      return id ? '工作台快本' : '看山失踪夜';
    }
    function gateLine(e) { return scrub(plain(e, '')); }
    function apiErr(detail, fallback) { return plain(detail, fallback || '操作未完成'); }
    return {
      plain, line, who, node, nodes, place, clue, cover, unlock, scrub, tier, module, mini, effect,
      stage, mood, stance, act, jobStatus, provider, jobLine, session, packCaption,
      gateLine, apiErr
    };
  })();
  window.Labels = Labels;
  function partyWsUrl(sid, pid, spectator) {
    const q = [];
    if (pid) q.push('player_id=' + encodeURIComponent(pid));
    if (spectator) q.push('spectator=1');
    // 单端口部署（M4）：前端与 API 同源同端口，WS 直接用本页 origin。
    // 旧版在这里硬编码回指 127.0.0.1:8899 —— 服务换端口后 WS 全部断连
    // （表现为"API 连接丢失"），已废弃该回指；跨端口打开请用 /api/lan-info。
    const origin = location.origin;
    return origin.replace(/^http/, 'ws') + '/ws/' + sid + (q.length ? '?' + q.join('&') : '');
  }
  async function resolveShareBase() {
    let base = location.origin;
    const host = location.hostname;
    const isLoopback = host === 'localhost' || host === '127.0.0.1';
    if (isLoopback) {
      try {
        const lr = await fetch('/api/lan-info');
        if (lr.ok) {
          const li = await lr.json();
          if (li.lan_ok && li.base_url) base = li.base_url;
        }
      } catch (e) { /* 探测失败则退回本页 origin */ }
    }
    return base;
  }
  function savePartyTicket(extra) {
    try {
      const cur = JSON.parse(sessionStorage.getItem('party_ticket') || '{}');
      sessionStorage.setItem('party_ticket', JSON.stringify(Object.assign(cur, extra || {})));
    } catch (e) { /* 隐私模式忽略 */ }
  }
  const now = () => `R${state.round}`;

  // 弹幕去重：同一条文案在可视窗口或短时间冷却内只展示一次，避免
  // 搜证/AI/重连重复事件造成刷屏。按文本归一化，保留不同样式的首次出现。
  function pushDmaku(items, cls) {
    if (!state._dmRecent) state._dmRecent = Object.create(null);
    const nowTs = Date.now();
    const seen = new Set((state.dmaku || []).map(x => String(x.text || '').trim()));
    const cooldown = 12000;
    (items || []).forEach((raw, i) => {
      const text = String(raw == null ? '' : raw).trim();
      if (!text) return;
      const last = state._dmRecent[text] || 0;
      if (seen.has(text) || nowTs - last < cooldown) return;
      state._dmRecent[text] = nowTs;
      seen.add(text);
      const item = { id: uid(), text, cls: cls || '', top: 8 + Math.floor(Math.random() * 70), delay: i * 0.45 };
      state.dmaku.push(item);
      setTimeout(() => { const ix = state.dmaku.indexOf(item); if (ix >= 0) state.dmaku.splice(ix, 1); }, 7000);
    });
    // 限制冷却表大小，避免长局积累。
    const cutoff = nowTs - cooldown;
    Object.keys(state._dmRecent).forEach(k => { if (state._dmRecent[k] < cutoff) delete state._dmRecent[k]; });
  }
  function track(kind, key, extra) {
    const bucket = state.telemetry && state.telemetry[kind]; if (!bucket) return;
    bucket[key] = (bucket[key] || 0) + 1;
    if (extra && extra.ms != null) { const k = key + '_ms'; bucket[k] = Math.round(((bucket[k] || 0) + extra.ms) / 2); }
  }
  function toast(text, kind) { const t = { id: uid(), text: Labels.plain(text), kind: kind || '' }; state.toasts.push(t); setTimeout(() => { const ix = state.toasts.indexOf(t); if (ix >= 0) state.toasts.splice(ix, 1); }, 3200); }
  function banner(text, cls) { const b = { id: uid(), text: Labels.plain(text), cls: cls || '' }; state.banners.push(b); setTimeout(() => { const ix = state.banners.indexOf(b); if (ix >= 0) state.banners.splice(ix, 1); }, 4200); }
  function chat(actor, text, opts) {
    state.chat.push({ id: uid(), actor, text: Labels.plain(text, ''), ...(opts || {}), t: now() });
    /* 一期 TTS：npc / dm / sys 新气泡播报；me / peer 不播（防回放自己）。罐头 VO 与静音由 Voice 内部跳过。 */
    if (!(opts && opts.whisper) && (actor === 'npc' || actor === 'dm' || actor === 'sys')) {
      try {
        if (window.Voice && window.Voice.speak) {
          window.Voice.speak(Labels.plain(text, ''), {
            actor: actor,
            charId: (opts && (opts.char_id || opts.charId)) || (actor === 'dm' ? 'dm' : ''),
            heart: !!(opts && opts.heart)
          });
        }
      } catch (e) { /* 无语音宿主时静默 */ }
    }
  }

  /* ---------- 派生 ---------- */
  const locClueLeft = (locId) => M.clues.filter(c => c.location === locId && !state.clues[c.id]).length;
  const locTier = (locId) => { const n = locClueLeft(locId); return n >= 2 ? 'hot' : (n === 1 ? 'warm' : 'cold'); };
  const flawCount = () => state.netKind === 'ws' && state.engineFlawCount !== null ? state.engineFlawCount : Object.keys(state.flaws).length;
  const ownedClues = () => Object.keys(state.clues).map(clueById).filter(Boolean);
  const hasKc = id => !!state.kcards[id];
  const heartOf = (cid) => {
    const v = state.memVer[cid] || 1;
    const mem = M.memories[cid]; if (!mem) return null;
    const blocks = [];
    mem.slice(0, v).forEach(mv => mv.blocks.forEach(b => { if (b.layer === 'heart' || b.integrity === 'deleted') blocks.push(b); }));
    return blocks.length ? blocks : null;
  };
  // 证据合成：≥3 条线索共享 truth node
  function synthCheck() {
    if (state.netKind === 'ws') return;
    const groups = {};
    ownedClues().forEach(c => (c.linked || []).forEach(tn => { (groups[tn] = groups[tn] || []).push(c); }));
    Object.entries(groups).forEach(([tn, arr]) => {
      if (arr.length >= 3) {
        const id = 'ev_' + tn;
        if (!state.synth.find(s => s.id === id)) {
          state.synth.push({ id, name: '证据卡·' + Labels.node(tn), node: tn, clueIds: arr.map(c => c.id) });
          toast('证据合成：' + Labels.node(tn) + '（' + arr.length + ' 条线索互证）', 'good');
          pushDmaku(['证据链合成！这就是知乎精神', '叉腰，这波严谨'], 'sys');
        }
      }
    });
  }
  // 覆盖度：指认知之者（矩阵_K）需要 tn_01/02/03/05/06(+tn_04)；与权威 truth.json culprit=char_01 对齐
  const GUILTY_NODES = ['tn_01', 'tn_02', 'tn_03', 'tn_04', 'tn_05', 'tn_06'];
  /* 前端 data.js 与引擎 kanshan 卡同 id 不同 linked。钉拼图时：有核心节点用核心；
   * 否则用引擎起步包口径，避免 clue_001 只钉 tn_07 导致覆盖度永远 0%。 */
  const PIN_NODE_FALLBACK = {
    clue_001: ['tn_02'], clue_002: ['tn_01'], clue_005: ['tn_05', 'tn_06']
  };
  function pinNodesOf(id, extra) {
    const raw = (extra && extra.length)
      ? extra
      : ((clueById(id) && (clueById(id).linked || clueById(id).linked_truth_nodes)) || []);
    const core = raw.filter(n => GUILTY_NODES.indexOf(n) >= 0);
    if (core.length) return core;
    return PIN_NODE_FALLBACK[id] || PIN_NODE_FALLBACK[uiClueId(id)] || raw;
  }
  const ENDING_TO_UI = {
    perfect_restoration: 'perfect', truth_revealed: 'truth', vindicated: 'redeem',
    pollution_win: 'pollution', deleted_chapter7: 'chapter7', kanshan_fish: 'fish',
    all_hearts_clear: 'sunshine', kanshan_still_mountain: 'kanshan',
    dm_mock: 'mock_dm', wrong: 'wrong', hung: 'hung'
  };
  const UI_TO_OUTCOME = {
    perfect: 'perfect_restoration', truth: 'truth_revealed', redeem: 'vindicated',
    pollution: 'pollution_win', chapter7: 'deleted_chapter7', fish: 'kanshan_fish',
    sunshine: 'all_hearts_clear', kanshan: 'kanshan_still_mountain',
    mock_dm: 'dm_mock', wrong: 'wrong', hung: 'hung'
  };
  function endingPair(uiOrOutcome) {
    if (ENDING_TO_UI[uiOrOutcome]) return { outcome: uiOrOutcome, ending_id: ENDING_TO_UI[uiOrOutcome] };
    return { ending_id: uiOrOutcome, outcome: UI_TO_OUTCOME[uiOrOutcome] || uiOrOutcome };
  }
  function finaleFlawClue() {
    return clueById('flavor_5') || clueById('clue_032');
  }
  function grantFinaleFlaw(emit) {
    const c = finaleFlawClue();
    if (!c) return false;
    const fid = c.flaw_id || 'flavor_5';
    if (state.flaws[fid] || state.clues[c.id]) return false;
    const payload = {
      clue_id: c.id, tier: c.tier || 'boss_flaw', name: c.name,
      text: (c.fact || '') + (c.flavor ? ' ' + c.flavor : ''),
      tags: c.tags || [], linked: c.linked || c.linked_truth_nodes || [],
      flaw_id: fid, danmaku: (M.danmaku && M.danmaku.flaw) || []
    };
    if (emit) emit('clue_gained', payload);
    else applyEvent({ type: 'clue_gained', payload: payload, actor: 'sys' });
    return true;
  }
  function coverage(evidenceIds) {
    const set = new Set();
    evidenceIds.forEach(id => {
      const ev = state.synth.find(s => s.id === id);
      if (ev) return set.add(ev.node);
      const c = clueById(id); if (c) (c.linked || []).forEach(n => set.add(n));
    });
    const hit = GUILTY_NODES.filter(n => set.has(n));
    return { hit, pct: Math.round(hit.length / GUILTY_NODES.length * 100) };
  }
  // 证据拼图覆盖度（B 证据链可视化）：基于玩家手钉的 evidenceLinks，与指认覆盖度同源 GUILTY_NODES
  function evidenceCoverage() {
    const set = new Set();
    (state.evidenceLinks || []).forEach(l => (l.nodes || []).forEach(n => set.add(n)));
    const hit = GUILTY_NODES.filter(n => set.has(n));
    return { hit, pct: Math.round(hit.length / GUILTY_NODES.length * 100), total: set.size };
  }
  function noteSearchTags(tags) {
    (tags || []).forEach(t => {
      if (!t) return;
      state.searchBias[t] = (state.searchBias[t] || 0) + 1;
    });
    if (!state.cocoon.active) {
      const top = Object.entries(state.searchBias).sort((a, b) => b[1] - a[1])[0];
      if (top && top[1] >= 2) {
        state.cocoon.active = true;
        toast('叮——算法已读懂你的口味：热搜开始只喂你爱看的。', 'warn');
        return true;
      }
    }
    return false;
  }
  function applyCocoonEnter(p) {
    const bias = p && p.bias;
    if (bias && typeof bias === 'object') {
      Object.keys(bias).forEach(t => {
        state.searchBias[t] = Math.max(state.searchBias[t] || 0, Number(bias[t]) || 0);
      });
    }
    if (!state.cocoon.active) {
      state.cocoon.active = true;
      toast((p && p.text) || '叮——算法已读懂你的口味：热搜开始只喂你爱看的。', 'warn');
    }
  }
  function applyCocoonBreak() {
    state.cocoon.broken = (state.cocoon.broken || 0) + 1;
    const top = Object.entries(state.searchBias).sort((a, b) => b[1] - a[1])[0];
    const topTag = top ? top[0] : null;
    state.cocoon.revealed = M.posts.filter(x => x.round <= state.round && !x.fake && x.tag !== topTag).length;
    toast('🦋 破茧成功——你主动戳穿了算法投喂，异见重新可见', 'good');
    banner('信息茧房已打破', 'good');
  }
  function applyEvidencePin(p) {
    const id = (p && (p.clueId || p.clue_id)) || '';
    if (!id) return;
    const nodes = pinNodesOf(id, (p && (p.nodes || p.linked || p.linked_truth_nodes)) || []);
    if (!state.evidenceLinks.some(l => l.clueId === id || l.clue_id === id))
      state.evidenceLinks.push({ clueId: id, nodes });
    const cov = evidenceCoverage();
    if (!(p && p.silent))
      toast('已钉入证据拼图：覆盖 ' + cov.pct + '% 核心真相节点' + (cov.pct >= 75 ? '（接近拼图完成！）' : ''), 'good');
  }
  function applyDefect(p) {
    const cid = (p && (p.charId || p.char_id)) || '';
    if (!cid) return;
    state.defection[cid] = { flipped: true, by: 'player' };
    const nm = Labels.who(cid);
    chat('npc', nm + '：我……其实不想这么干的。看山让我闭嘴，但我还是想说——证据都在这了，随便查。', { char_id: cid, heart: true });
    banner('🤝 策反成功：' + nm + ' 跳反，提供证词', 'good');
  }

  /* ---------- 反操纵三件套（与 engine/pollution_check · echo_log · judge_debate · truth_profile 对齐） ---------- */
  const ECHO_POS = ['相信', '信任', '清白', '没问题', '靠谱', '支持', '没错', '可信', '我信'];
  const ECHO_NEG = ['怀疑', '不信', '有鬼', '凶手', '撒谎', '假的', '不对', '可疑', '骗', '我疑'];
  const ECHO_ASSERT = ['一定', '肯定', '绝对', '就是', '必然', '百分百', '我确定', '毫无疑问'];
  const DEBATE_ABUSE = ['傻', '蠢', '废物', '去死', '滚', '脑残', '智障', '闭嘴', '垃圾'];
  const DEBATE_REFLECT = ['我承认', '我曾经', '我改口', '我说过', '我动摇', '我错了', '我之前'];
  const TP_ARCH = {
    '流量操盘手': '你很懂流量怎么运作——正因如此，你比谁都清楚水军是怎么赢的。',
    '追光者': '你指认了主持人。在所有人都看向嫌疑人的时候，你抬头看向了那个递给你线索的人。',
    '求真派': '你不轻信任何一句通顺的话，包括对你有利的那句。这是求真的基本功。',
    '心晴派': '你把行动点花在了别人的心上。真相之外，你也救了几个人的这一夜。',
    '稳健调查员': '你不抢风头，但卷宗里每一条实证都有你的签名。',
    '见习档案员': '第一夜而已。档案局的大门永远为还想再查一次的人开着。'
  };
  function _pct(v) { return Math.max(0, Math.min(100, Math.round(v))); }
  function playSfx(kind) { try { if (window.SFX) window.SFX.play(kind); } catch (e) { } }
  function archiveEcho(text, target) {
    const t = String(text || '').trim();
    if (!t || t.length < 2) return null;
    state.echo.seq += 1;
    const item = { idx: state.echo.seq, actor: 'player:1', text: t.slice(0, 500),
      target: String(target || '').replace('npc:', '').trim(), round: state.round };
    state.echo.log.push(item);
    if (state.echo.tease < 2) {
      state.echo.tease += 1;
      banner('叮——这句话已被归档。终局时，你自己的话也会成为证据。', 'echo');
      playSfx('archive');
    }
    return item;
  }
  function echoPolarity(text) {
    if (ECHO_POS.some(w => text.includes(w))) return 'pos';
    if (ECHO_NEG.some(w => text.includes(w))) return 'neg';
    return '';
  }
  function echoContradictions() {
    const items = state.echo.log;
    const out = [];
    for (let i = 0; i < items.length; i++) {
      const px = echoPolarity(items[i].text);
      if (!px) continue;
      for (let j = i + 1; j < items.length; j++) {
        if (items[i].target && items[j].target && items[i].target !== items[j].target) continue;
        const py = echoPolarity(items[j].text);
        if (!py || py === px) continue;
        out.push({
          a: items[i].idx, b: items[j].idx,
          target: items[i].target || items[j].target,
          a_text: items[i].text, b_text: items[j].text,
          reason: '你先说「' + items[i].text.slice(0, 24) + '」，后又说「' + items[j].text.slice(0, 24) + '」——同一件事，两种立场。'
        });
      }
    }
    return out;
  }
  function echoChallengeOf() {
    const pairs = echoContradictions();
    if (pairs.length) {
      const p = pairs[0];
      const cands = state.echo.log.filter(i => i.idx === p.a || i.idx === p.b).slice(0, 2);
      const noise = state.echo.log.filter(i => i.idx !== p.a && i.idx !== p.b).slice(0, 1);
      return {
        mode: 'contradiction', pair: p,
        candidates: cands.concat(noise).map(i => ({ idx: i.idx, text: i.text, round: i.round })),
        text: '看山把你说过的话投影在墙上：「' + p.a_text.slice(0, 30) + '」……可你后来又说「' + p.b_text.slice(0, 30) + '」。你连自己都前后不一，凭什么指认我？'
      };
    }
    const lines = state.echo.log.filter(i => ECHO_ASSERT.some(w => i.text.includes(w)))
      .sort((a, b) => b.text.length - a.text.length).slice(0, 3);
    if (lines.length) {
      return {
        mode: 'assertion',
        candidates: lines.map(i => ({ idx: i.idx, text: i.text, round: i.round })),
        text: '看山念出你最笃定的那句：「' + lines[0].text.slice(0, 30) + '」。「现在，你还敢这么说吗？」'
      };
    }
    return { mode: 'empty', candidates: [], pair: null, text: '（你几乎没留下可以被引用的话——看山找不到攻击你的材料。）' };
  }
  function echoDefendOf(picks) {
    const pairs = echoContradictions();
    if (!pairs.length) {
      return { ok: true, passed: true, mode: 'consistent',
        reason: '全场检索完毕：你的每一句话都前后一致，看山挑不出矛盾。',
        transcript_hint: '自证成功：翻遍回声档案，你没有自相矛盾过——在一个人人改口的游戏里，保持一致本身就是证据。' };
    }
    const picked = new Set((picks || []).map(n => +n).filter(n => !isNaN(n)));
    const hit = pairs.find(p => picked.size === 2 && picked.has(p.a) && picked.has(p.b));
    if (hit) {
      return { ok: true, passed: true, mode: 'contradiction', reason: hit.reason,
        transcript_hint: '自证成功：你承认了自己动摇过——「' + hit.a_text.slice(0, 20) + '」到「' + hit.b_text.slice(0, 20) + '」。承认被带过节奏，才是求真的起点。' };
    }
    return { ok: true, passed: false, mode: 'contradiction', reason: '你指的不是真正互相矛盾的那两句。',
      transcript_hint: '自证失败：你指出的两句并不矛盾，看山笑着把这一段也记进了档案——「连自己说过什么都找不准的人，怎么找真相？」' };
  }
  function shuffleCopy(arr, seed) {
    const a = arr.slice();
    let s = seed || 1;
    for (let i = a.length - 1; i > 0; i--) {
      s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
      const j = s % (i + 1);
      const t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }
  function pollutionPublicCase(raw) {
    return {
      id: raw.id, title: raw.title, author: raw.author, card_id: raw.card_id,
      topic_tag: raw.topic_tag, original: raw.original, polluted: raw.polluted,
      source_note: raw.source_note, manipulation: raw.manipulation || [],
      spans: shuffleCopy((raw.spans || []).map(s => ({ id: s.id, text: s.text })), state.round * 17 + raw.id.length),
      changed_total: (raw.spans || []).filter(s => s.changed).length
    };
  }
  function pollutionMarkOf(pcId, picks) {
    const raw = (M.pollutionCases || []).find(c => c.id === pcId);
    if (!raw) return { ok: false, transcript_hint: '（这道题不存在——档案局没有这份对照记录）' };
    const changed = new Set((raw.spans || []).filter(s => s.changed).map(s => s.id));
    const picked = new Set((picks || []).map(String));
    const correct = [...picked].filter(id => changed.has(id));
    const wrong = [...picked].filter(id => !changed.has(id));
    const missed = [...changed].filter(id => !picked.has(id));
    const passed = !missed.length && !wrong.length;
    const firstTry = !state.pollution.done[pcId];
    let ammo = state.pollution.ammo, apRefund = 0, heatDelta = 0;
    const earned = (state.pollution.earned || 0) + (passed && firstTry ? 1 : 0);
    if (passed && firstTry) { ammo += 1; apRefund = 1; heatDelta = -2; }
    else if (wrong.length) heatDelta = 3;
    const revealed = (raw.spans || []).filter(s => s.changed).map(s => ({ text: s.text, why: s.why || '' }));
    let hint;
    if (passed && firstTry) hint = '对照完成：《' + raw.title + '》' + correct.length + ' 处操纵全部识别。辟谣弹药 +1（当前 ' + ammo + '），行动力返还 1 点，热度 -2——你刚刚亲手拆掉了一条水军话术。';
    else if (passed) hint = '《' + raw.title + '》复核通过：本题已计过分，不再重复给弹药。';
    else {
      hint = '《' + raw.title + '》命中 ' + correct.length + '/' + (correct.length + missed.length) + ' 处。';
      if (wrong.length) hint += ' 误判 ' + wrong.length + ' 处——有些话刺耳，但它是作者原句；判断操纵不能只靠语感。';
      if (missed.length) hint += ' 还漏了 ' + missed.length + ' 处没圈出来，再对照原文读一遍。';
    }
    return { ok: true, correct: correct.length, missed: missed.length, wrong: wrong.length, passed, first_try: firstTry,
      changed_total: changed.size, ammo, ammo_earned: earned, ap_refund: apRefund, heat_delta: heatDelta, transcript_hint: hint, revealed };
  }
  function debateSubmitOf(claim) {
    const text = String(claim || '').trim();
    if (text.length < 8) {
      return { gain: -1, total: state.debate.score, stance: state.debate.stance, convinced: state.debate.convinced,
        reasons: ['陈词过短，法官视为敷衍'], transcript_hint: '法官皱眉：「这不是陈词，这是打卡。」（本轮不计）' };
    }
    const evTerms = state.synth.map(s => s.name).concat(ownedClues().map(c => c.name)).filter(Boolean);
    const cards = Object.keys(state.kcards).map(id => (kcById(id) || {}).title).filter(Boolean);
    let gain = 0;
    const reasons = [];
    if (evTerms.some(t => text.includes(t))) { gain += 2; reasons.push('引用了卷宗里的实证'); }
    if (cards.some(t => text.includes(t))) { gain += 1; reasons.push('引用了知乎答主的专业意见'); }
    if (state.echo.defended && DEBATE_REFLECT.some(w => text.includes(w))) { gain += 1; reasons.push('承认自己曾被带过节奏——诚实也是证据'); }
    if (DEBATE_ABUSE.some(w => text.includes(w))) { gain -= 1; reasons.push('情绪化表述，法官不予采信'); }
    const prev = (state.debate.rounds[state.debate.rounds.length - 1] || {}).text || '';
    if (prev) {
      const grams = s => { const g = new Set(); for (let i = 0; i < s.length - 1; i++) g.add(s.slice(i, i + 2)); return g; };
      const a = grams(text), b = grams(prev);
      let inter = 0; a.forEach(x => { if (b.has(x)) inter++; });
      if (a.size && b.size && inter / (a.size + b.size - inter) > 0.6) { gain -= 1; reasons.push('与上一轮陈词高度重复，法官失去耐心'); }
    }
    gain = Math.max(-2, Math.min(3, gain));
    const total = Math.max(0, state.debate.score + gain);
    let stance = 'skeptical', convinced = false;
    if (total >= 4) { stance = 'convinced'; convinced = true; }
    else if (total > 0) stance = 'open';
    let hint = (gain >= 0 ? ('本轮 +' + gain + ' 分') : ('本轮 ' + gain + ' 分')) + '（' + (reasons.join('；') || '法官未置可否') + '）。';
    if (convinced) hint += '法官放下笔：「证据链成立，本庭采信你的陈述。」——线索「法官采信」已入卷宗。';
    else if (stance === 'skeptical') hint += '法官摇头：「情绪与重复不是证据，请继续。」';
    else hint += '法官记录中，距离采信还需 ' + Math.max(0, 4 - total) + ' 分。';
    return { gain, total, stance, convinced, reasons, transcript_hint: hint };
  }
  function buildTruthProfile(extra) {
    extra = extra || {};
    const polDone = Object.keys(state.pollution.done || {});
    const polPassed = polDone.filter(id => state.pollution.done[id] && state.pollution.done[id].passed).length;
    const polTotal = (M.pollutionCases || []).length || polDone.length;
    const refutes = Object.values(state.refuted || {}).filter(r => r.ok).length;
    const buyHeats = extra.buy_heats != null ? extra.buy_heats : (state.buyHeats || 0);
    const counsel = state.counsel.filter(r => r.ok).length;
    const echoDef = !!(state.echo && state.echo.defended);
    const echoContra = echoContradictions().length;
    const convinced = !!(state.debate && state.debate.convinced);
    const accusedDm = !!extra.accused_dm;
    const heat = state.heat;
    const cov = coverage(state.voteEvidence.concat(Object.keys(state.clues)));
    const coverage01 = (cov.pct || 0) / 100;
    const clueCount = Object.keys(state.clues).length;
    const rigor = _pct(coverage01 * 70 + Math.min(clueCount, 12) / 12 * 30);
    const ammoFlag = (state.pollution.earned || 0) || state.pollution.ammo;
    const skepticism = _pct((polTotal ? polPassed / polTotal * 60 : 0) + Math.min(refutes, 3) / 3 * 25 + (ammoFlag > 0 ? 15 : 0));
    const empathy = _pct(Math.min(counsel, 5) / 5 * 100);
    const courage = _pct((accusedDm ? 40 : 0) + (convinced ? 30 : 0) + (echoDef ? 30 : 0));
    const independence = _pct(100 - Math.min(4, buyHeats) * 25 - Math.max(0, heat - 50) * 0.6);
    let arch = '见习档案员';
    if (buyHeats >= 2) arch = '流量操盘手';
    else if (accusedDm && convinced) arch = '追光者';
    else if (skepticism >= 70) arch = '求真派';
    else if (empathy >= 60) arch = '心晴派';
    else if (rigor >= 60) arch = '稳健调查员';
    const highlights = [];
    if (polTotal && polPassed) highlights.push('识破 ' + polPassed + '/' + polTotal + ' 条被改写的知乎回答——你能在「看起来很像原文」的话里认出操纵');
    if (refutes) highlights.push('完成 ' + refutes + ' 次有效辟谣：用专业回答对冲了水军话术');
    if (echoDef) highlights.push('你承认了自己前后矛盾过——在被 AI 用你自己的话反将一军时，你没抵赖');
    else if (echoContra) highlights.push('回声档案记录了 ' + echoContra + ' 处你前后不一的发言（下次可以更稳）');
    if (convinced) highlights.push('说服了那个被舆论带偏的 AI 法官（陈词 ' + (state.debate.score || 0) + ' 分）');
    if (accusedDm) highlights.push('你指认了主持人刘看山——本作最难的一个选择');
    if (counsel >= 3) highlights.push('开导了 ' + counsel + ' 位角色：查案之外，你没把人当工具');
    if (!highlights.length) highlights.push('这一局你走完了全流程：在一个人人改口的夜里，你至少没有中途离场');
    const scores = { rigor, skepticism, empathy, courage, independence };
    const overall = _pct((rigor + skepticism + empathy + courage + independence) / 5);
    const tail = heat < 40
      ? '（本局舆论热度 ' + heat + '，你的判断没有被声量牵着走。）'
      : '（本局舆论热度 ' + heat + '——注意：热度越高，越难保持独立。）';
    return {
      archetype: arch, archetype_desc: TP_ARCH[arch], scores, overall,
      verdict: TP_ARCH[arch] + ' ' + tail,
      highlights: highlights.slice(0, 3),
      share: { title: '我在《求真档案局》的求真画像：' + arch, lines: ['综合求真力 ' + overall + ' 分', '严谨 ' + rigor + ' · 怀疑 ' + skepticism + ' · 共情 ' + empathy + ' · 勇气 ' + courage + ' · 独立 ' + independence, TP_ARCH[arch]] },
      ending: extra.ending || state.ending || ''
    };
  }

  /* ---------- 引擎（client→server 动作 → 协议事件） ---------- */
  const Engine = {
    search(p, emit) {
      const location = resolveLoc(p.location).id;
      const keyword = p.keyword;
      const kw = (keyword || '').trim();
      if (!kw) return emit('system', { toast: '先输入一个搜证关键词', kind: 'warn' });
      if (state.ap < 1 && !state.glitchFree) return emit('system', { toast: '行动点不足，等下一轮', kind: 'warn' });
      if (state.glitchFree) { state.glitchFree = false; emit('system', { toast: '抽风免扣已生效：本次行动 0AP', kind: 'good' }); }
      else emit('system', { apDelta: -1 });
      state.searched[location] = (state.searched[location] || 0) + 1;
      const pool = M.clues.filter(c => c.location === location && !state.clues[c.id]);
      const matched = pool.filter(c => (c.tags || []).some(t => kw.includes(t) || t.includes(kw)));
      const gateOk = c => {
        const u = c.unlock;
        if (u === '默认') return true;
        if (u.startsWith('evidence:')) return !!state.clues[u.split(':')[1]];
        if (u.startsWith('memory:')) { const [, cid, v] = u.split(':'); return (state.memVer[cid] || 1) >= +v; }
        if (u.startsWith('counsel:')) return state.counsel.some(r => r.ok && r.kc_id === u.split(':')[1]);
        if (u.startsWith('act>=')) return state.act >= +u.split('=')[1];
        return true;
      };
      const hit = matched.find(gateOk) || null;
      if (hit) {
        emit('search_result', { location, keyword: kw, hit: true, clue_id: hit.id });
        emit('clue_gained', {
          clue_id: hit.id, tier: hit.tier, name: hit.name, text: hit.fact + ' ' + hit.flavor,
          tags: hit.tags, linked: hit.linked, fake_of: hit.fake_of || null, flaw_id: hit.flaw_id || null,
          danmaku: hit.tier === 'boss_flaw' ? M.danmaku.flaw : M.danmaku.hit
        });
      } else {
        noteSearchTags((matched.length ? matched : pool).flatMap(c => c.tags || []));
        emit('search_result', { location, keyword: kw, hit: false, ambient: rnd(M.ambient[location] || ['一无所获，但收获了一段平静。']), danmaku: rnd2(M.danmaku.miss) });
      }
      function rnd2(a) { return a.slice(0, 2); }
    },

    chat(p, emit) {
      // 兼容旧客户端：统一使用 target/char_id，并移除 npc: 前缀。
      const char_id = String(p.char_id || p.target || 'dm').replace(/^npc:/, '');
      const text = p.text;
      archiveEcho(text, char_id);
      emit('chat', { char_id, text, actor_kind: 'player' });
      // 彩蛋：唤醒词
      if (/看山[,，]?\s*关门/.test(text)) {
        if (!state.clues['flavor_4']) {
          const c = clueById('flavor_4');
          emit('clue_gained', { clue_id: c.id, tier: c.tier, name: c.name, text: c.fact + ' ' + c.flavor, tags: c.tags, linked: c.linked, flaw_id: 'flavor_4', danmaku: M.danmaku.flaw });
          emit('system', { banner: '彩蛋触发——「看山，关门」。门：吱呀一声，锁得更死了。', cls: 'egg' });
        } else {
          emit('system', { banner: '门表示已经锁得很服帖了。', cls: 'egg' });
        }
      }
      // 唤醒词单独触发横幅（不重复发线索）
      else if (/看山/.test(text) && /关门|开门|锁门/.test(text)) emit('system', { banner: '叮——门已锁好。不出真相，不出此门。', cls: 'egg' });
      const ch = charById(char_id);
      if (!ch) return;
      if (char_id === 'dm') { emit('chat', { char_id: 'dm', text: rnd(ch.replies), actor_kind: 'dm' }); }
      else {
        emit('chat', { char_id, text: rnd(ch.replies), actor_kind: 'npc' });
        if (state.heartUnlocked[char_id] && ch.heartLine) emit('chat', { char_id, text: ch.heartLine, actor_kind: 'heart' });
      }
      emit('danmaku', { items: pick3(M.danmaku.chat) });
    },

    skill(p, emit) {
      const k = p.kind;
      if (k === 'memory_repair' || k === 'memory_fix') {  // 别名：driver 契约=memory_fix（G09 后统一）
        const cid = p.char_id || p.target;  // 别名：driver 契约用 target
        const mem = M.memories[cid]; const cur = state.memVer[cid] || 1;
        if (!mem || cur >= mem.length) return emit('system', { toast: '该角色记忆版本已全部解锁', kind: 'warn' });
        if (state.act < 2 && !state.demo) return emit('system', { toast: '记忆修复为第二幕解锁（演示模式可跳过）', kind: 'warn' });
        if (state.ap < 2) return emit('system', { toast: '记忆修复消耗 2 行动点', kind: 'warn' });
        emit('system', { apDelta: -2 });
        const next = mem[cur];
        emit('memory_unlock', { char_id: cid, version: next.version, diff: next.diff, blocks: next.blocks.filter(b => b.layer === 'heart' || b.integrity === 'deleted'), danmaku: pick3(M.danmaku.hit) });
        // 心声层自动解锁（v2 起含 heart）
        if (next.blocks.some(b => b.layer === 'heart')) emit('system', { heartUnlock: cid });
        // 篡改点 → 自动转线索
        if (next.diff.some(d => d.tamper)) {
          const c = clueById('clue_017');
          emit('clue_gained', { clue_id: 'tamper_' + cid + '_v' + next.version, tier: 'hidden', name: `篡改点·${charById(cid).name} V${cur}→V${next.version}`, text: next.diff.map(d => d.change).join('；') + '。两层矛盾已被引擎固化为证据。', tags: ['记忆', '篡改'], linked: ['tn_08'], fake_of: null, flaw_id: null, danmaku: ['记忆对不上了！切片，存证', '这就是双层记忆的含金量'] });
        }
      }
      else if (k === 'draw_card') {
        if (state.ap < 1) return emit('system', { toast: '行动点不足', kind: 'warn' });
        const left = M.kcards.filter(kc => !state.kcards[kc.id]);
        if (!left.length) return emit('system', { toast: '十张知识卡已全部集齐，知乎学分 +1', kind: 'good' });
        emit('system', { apDelta: -1 });
        const kc = rnd(left);
        emit('faction_skill', { kind: 'draw_card', kc_id: kc.id, danmaku: ['抽卡区风景真好看', '知识卡：知乎知识的具象化'] });
      }
      else if (k === 'refute') {
        const post = M.posts.find(x => x.id === (p.post || p.post_id));
        const kc = kcById(p.card || p.kc_id);
        if (!post || !kc) return emit('system', { toast: '请选择帖子与知识卡', kind: 'warn' });
        if (state.refuted[post.id]) return emit('system', { toast: '该帖已被处理', kind: 'warn' });
        if (state.ap < 2) return emit('system', { toast: '辟谣消耗 2 行动点', kind: 'warn' });
        emit('system', { apDelta: -2 });
        const ok = kc.topic_tag === post.tag;
        let ammoSpent = 0, ammoLeft = state.pollution.ammo || 0;
        if (ok && ammoLeft > 0) { ammoSpent = 1; ammoLeft -= 1; }
        const heatDelta = ok ? -(post.delta + (ammoSpent ? 2 : 0)) : post.delta;
        emit('system', {
          event: 'refute_result', ok, post: post.id, card: kc.id,
          heat_delta: heatDelta, heat: Math.max(0, Math.min(100, state.heat + heatDelta)),
          ammo_spent: ammoSpent, ammo: ammoLeft,
          unlocked_clue: (ok && post.clue_ref && !state.clues[post.clue_ref]) ? post.clue_ref : null,
          crowd_mocks: ok ? [] : pick3(M.danmaku.refute_fail),
          text: ok
            ? ('辟谣成功：热度 ' + heatDelta + (ammoSpent ? '（对照弹药加码，热度再降 2）' : ''))
            : ('辟谣失败：热度 +' + post.delta + '，弹幕群嘲')
        });
      }
      else if (k === 'buy_hot' || k === 'buy_heat') {
        if (state.ap < 1) return emit('system', { toast: '行动点不足', kind: 'warn' });
        emit('system', { apDelta: -1 });
        const title = p.title || '#档案局连夜吃瓜#';
        emit('system', {
          event: 'buy_heat_result', ok: true, heat: Math.min(100, state.heat + 5),
          heat_delta: 5, title, text: '买热搜成功：' + title + ' 置顶，热度 +5'
        });
      }
      else if (k === 'cross_check') {
        /* 缺口2修复：WS 通道该动作直达服务端 cross_check 技能流（cross_check_result
           事件裁决）；此处仅本地演示/mock 传输的降级路径——判定在本机生成，如实标注 degraded */
        const c = clueById(p.clue_id);
        if (!c || c.tier !== 'fake') return emit('system', { toast: '该卡无需交叉验证', kind: 'warn' });
        const real = clueById(c.fake_of);
        const exposed = real && !!state.clues[real.id];
        emit('faction_skill', { kind: 'cross_check', clue_id: c.id, exposed, degraded: true, real_name: real ? real.name : null, danmaku: exposed ? ['伪证当场去世', '交叉验证，学到了'] : ['证据不足，先存疑'] });
      }
      /* ---- V31 P1：押注（单位=赞数） ---- */
      else if (k === 'place_bet') {
        const bet = state.bet;
        if (!bet || !bet.open) return emit('system', { toast: '押注通道未开启', kind: 'warn' });
        if (!bet.options.includes(p.option)) return emit('system', { toast: '押注选项不存在', kind: 'warn' });
        const amt = Math.max(1, Math.min(5, p.amount | 0));
        if (state.zans < amt) return emit('system', { toast: '赞数不足（当前 ' + state.zans + '）', kind: 'warn' });
        state.zans -= amt;
        const w = bet.wagers[p.option] = bet.wagers[p.option] || { n: 0, amt: 0 };
        w.n += 1; w.amt += amt;           // my 记录玩家本人投入
        w.my = (w.my || 0) + amt;
        if (state.betStreak.target === p.option) state.betStreak.count += 1;
        else { state.betStreak.target = p.option; state.betStreak.count = 1; }
        emit('system', { event: 'bet_placed', option: p.option, amount: amt, pool: Object.values(bet.wagers).reduce((s, x) => s + x.amt, 0) });
      }
      /* ---- V31 P1：头条竞标（出价=行动点，平价先到先得；事件形态对齐服务端 headline_result） ---- */
      else if (k === 'bid_headline') {
        const hl = state.headline;
        if (!hl || hl.settled) return emit('system', { toast: '本轮头条位未开标或已结算', kind: 'warn' });
        const amount = Math.max(1, Math.min(3, p.amount | 0));
        if (state.ap < amount) return emit('system', { toast: '行动点不足（出价=行动点）', kind: 'warn' });
        emit('system', { apDelta: -amount });
        // AI 对手确定性竞价：热度越高抢得越凶（1~2AP）
        const aiAmt = state.heat >= 70 ? 2 : 1;
        hl.bids.push({ who: 'player:1', amount });
        hl.bids.push({ who: 'ai', amount: aiAmt });
        const meFirst = amount >= aiAmt;  // 平价先到先得：玩家挂单在前即胜
        const bid = meFirst ? { who: 'player:1', amount } : { who: 'ai', amount: aiAmt };
        hl.settled = true; hl.winner = bid.who;
        // 欢乐位（#8《本局最想请客吃饭的人》）不进热度结算（segments_p1 §3.3）
        const heatDelta = meFirst ? (hl.fun ? 0 : 8) : 2;  // 中标翻倍结算；流拍/被截标 +2（§3.1）
        emit('system', {
          event: 'headline_result',
          bid, settle: { winner: bid.who, amount: bid.amount, heat_delta: heatDelta },
          host_line: M.headlineLines.open.replace('{topic}', hl.topic),
          result_line: meFirst
            ? (hl.fun ? '叮——欢乐位头条成交：友谊第一，热度第零。' : M.headlineLines.win)
            : M.headlineLines.lose,
          outbid_line: meFirst ? '' : M.headlineLines.outbid,
          heatDelta, pinned: meFirst
        });
      }
      /* ---- V31 P2：暗拍（2AP：原件留场，玩家持照片） ---- */
      else if (k === 'stealth_photo') {
        const location = resolveLoc(p.location_id || p.location).id, kw2 = (p.keyword || '').trim();
        if (!kw2) return emit('system', { toast: '暗拍也需要关键词（对准再按快门）', kind: 'warn' });
        if (state.ap < 2) return emit('system', { toast: '暗拍消耗 2 行动点（溢价=信息不消耗线索供给）', kind: 'warn' });
        emit('system', { apDelta: -2 });
        const pool = M.clues.filter(c => c.location === location && !state.clues[c.id] && !state.photos.some(ph => ph.clue_id === c.id));
        const hit = pool.find(c => c.tags.some(t => kw2.includes(t) || t.includes(kw2)) && c.tier !== 'fake') || null;
        if (!hit) {
          emit('system', { event: 'stealth_photo', photo: null, text: '快门按了，什么也没拍着（该地点该关键词无线索可拍）' });
          return;
        }
        const photo = { id: 'photo_' + hit.id, clue_id: hit.id, name: hit.name, text: hit.fact, loc: location, at: state.round, shared: false, claim: '', exposed: false };
        state.photos.push(photo);
        emit('system', { event: 'stealth_photo', photo: { id: photo.id, clue_id: hit.id, name: hit.name }, text: '叮——暗拍成功：线索原件留原地（他人仍可搜），你持有照片。热度照常 -1，手感 +100。' });
      }
      else if (k === 'share_photo') {
        /* 缺口1修复：WS 通道该动作直达服务端 share_photo 技能流（owner 校验 +
           photo_shared 广播）；此处仅本地演示/mock 传输的降级路径，不与联机状态同步 */
        const ph = state.photos.find(x => x.id === p.photo_id);
        if (!ph) return emit('system', { toast: '照片不存在', kind: 'warn' });
        ph.shared = true; ph.claim = String(p.claim || '').slice(0, 60) || '（未填声称）';
        emit('system', { event: 'photo_shared', photo_id: ph.id, claim: ph.claim, text: '叮——照片已流出。照片是真的，"声称"可不一定——圆桌见。' });
      }
      /* ---- V31 P2：记忆拼图对质（消耗 2 篡改点，60s 排时间线） ---- */
      else if (k === 'memory_puzzle') {
        if (state.tamperPts < 2) return emit('system', { toast: '记忆拼图需消耗 2 个篡改点（先去修复记忆找矛盾）', kind: 'warn' });
        state.tamperPts -= 2;
        emit('system', { event: 'memory_puzzle_open' });
      }
      else if (k === 'memory_puzzle_submit') {
        const ok = !!p.ok;   // 判定在视图层排序比对后上报（引擎语义：排对全场得线索，排错 DM 锐评）
        if (ok) {
          const c = clueById('clue_020') || null;
          emit('system', { event: 'memory_puzzle_result', ok: true, text: '叮——时间线严丝合缝。奖励线索已发，历史今天被你们按住了。（成就：时间线钉子户）', clue: c ? { clue_id: c.id, name: c.name, text: c.fact } : null });
        } else {
          emit('system', { event: 'memory_puzzle_result', ok: false, text: '叮——排序翻车。DM 锐评：你们把深夜排成了悬疑片，可惜剪错了帧。' });
        }
      }
      /* ---- V31 P2：反诈剧场答题 ---- */
      else if (k === 'antifraud_answer') {
        const right = !!p.right;
        if (right) {
          state.antifraud.score += 1;
          emit('system', { event: 'antifraud_result', right: true, text: M.antifraudScript.settleOk, score: state.antifraud.score });
        } else {
          emit('system', { event: 'antifraud_result', right: false, text: M.antifraudScript.settleFail });
        }
      }
      /* ---- V31 P2：终局陈词 + 锤人分池（不影响指认） ---- */
      else if (k === 'closing_speech') {
        const text = String(p.text || '').slice(0, 120);
        if (!text) return emit('system', { toast: '60 秒总要说点什么', kind: 'warn' });
        emit('system', { event: 'closing_registered', text, mock: rnd(M.closingLines.mock) });
      }
      else if (k === 'hammer_vote') {
        const target = p.target;
        if (!target) return emit('system', { toast: '先选"最想锤的人"', kind: 'warn' });
        // AI 分池：热度最高者承受主要锤意（确定性倾向+微扰）
        const tally = {};
        M.chars.filter(c => c.id !== 'dm').forEach(c => tally[c.id] = c.id === target ? 2 + (state.heat >= 60 ? 2 : 1) : (Math.floor(Math.random() * 2)));
        tally['player:1'] = 0; tally[target] = (tally[target] || 0) + 1;
        const most = Object.keys(tally).sort((a, b) => tally[b] - tally[a])[0];
        state.hammer = { speech: state.hammer ? state.hammer.speech : '', target, tally, most, at: state.round };
        emit('system', { event: 'hammer_result', target, most_hammered: most, tally, text: M.closingLines.settle.replace('{who}', (M.chars.find(c => c.id === most) || { name: most }).name) });
      }
      /* ---- MEGA_MODE：侦探证领取（登录后；WS 模式优先 GET /api/profile/me，失败降级本地） ---- */
      else if (k === 'claim_dossier') {
        const name = String(p.name || '匿名侦探').slice(0, 16);
        const headlineTxt = String(p.headline || '').slice(0, 30);
        // 真实授权路径：F 的 dossier 结构（badge_no=uid 后 6 位 / rank=花名）优先透传
        const uid6 = String(p.uid6 || (100000 + Math.floor(Math.random() * 900000)));
        const rule = p.rank ? null : M.dossierRanks.find(r => r.test.test(headlineTxt));
        const rank = p.rank || (rule ? rule.rank : rnd(M.dossierFallbackRanks));
        const avatar = p.avatar || M.dossierAvatars[0].src;
        state.dossier = { name, headline: headlineTxt, avatar, uid6, rank, issued: '2026-09-12', source: p.source || 'mock' };
        emit('system', { event: 'dossier_ready', dossier: state.dossier, personal_line: headlineTxt ? M.dossierLine(headlineTxt) : '' });
      }
      /* ---- P3：鱼干收集品拾取（微光点点击，0AP；事件形态对齐 F 的 rt collect_result） ---- */
      else if (k === 'collect') {
        const item = M.fishCollectibles.find(f => f.id === p.item);
        if (!item) return emit('system', { event: 'collect_result', item: p.item, collected: false, reason: 'unknown_item', text: '未知收集品：' + p.item });
        if (state.fish[item.id]) return emit('system', { event: 'collect_result', item: item.id, collected: false, reason: 'already', text: '这袋鱼干已经在你兜里了（重复拾取已被引擎拒绝）' });
        if (state.act < item.act) return emit('system', { event: 'collect_result', item: item.id, collected: false, reason: 'locked', text: `微光还很微弱——第 ${'一二三'[item.act - 1]}幕起才会显形（当前第 ${'一二三'[state.act - 1]}幕）` });
        state.fish[item.id] = { at: state.round };
        const all = M.fishCollectibles.every(f => state.fish[f.id]);
        emit('system', {
          event: 'collect_result', item: item.id, collected: true, all_collected: all,
          show: { pickup: item.pickup, dm: item.dm, bot: item.bot },
          notice: '收集品拾取（彩蛋层，不进证据链、零行动点）', source: 'rt'
        });
      }
      else if (k === 'fish_voice_next') {
        // 隐藏语音逐句推进（切片播不合并；语音 4 播完自动收束）
        if (!state.fishVoice) return;
        state.fishVoice.line += 1;
        if (state.fishVoice.line >= M.fishVoiceLines.length) state.fishVoice = null;
      }
      /* ---- V5 反操纵三件套（事件名对齐 engine_driver） ---- */
      else if (k === 'pollution_open') {
        if (state.act < 2 && !state.demo) return emit('system', { toast: '污染对照为第二幕解锁（演示模式可跳过）', kind: 'warn' });
        const raw = (M.pollutionCases || []).find(c => !state.pollution.done[c.id]);
        if (!raw) {
          return emit('system', { event: 'pollution_done', summary: { total: (M.pollutionCases || []).length, done: Object.keys(state.pollution.done).length, passed: Object.values(state.pollution.done).filter(v => v.passed).length, ammo: state.pollution.ammo },
            text: '全部对照题已完成——水军的话术已经被你拆干净了。' });
        }
        emit('system', { event: 'pollution_case', case: pollutionPublicCase(raw),
          text: '对照题《' + raw.title + '》（原作者 ' + raw.author + '）：下栏是水军改写版，圈出被植入的 ' + (raw.spans || []).filter(s => s.changed).length + ' 处操纵。',
          summary: { ammo: state.pollution.ammo } });
      }
      else if (k === 'pollution_mark') {
        const res = pollutionMarkOf(String(p.case || ''), p.picks || []);
        if (!res.ok) return emit('system', { event: 'bad_target', notice: res.transcript_hint });
        emit('system', {
          event: 'pollution_result', case_id: String(p.case || ''),
          correct: res.correct, missed: res.missed, wrong: res.wrong, passed: res.passed,
          first_try: res.first_try,
          changed_total: res.changed_total, ammo: res.ammo, ammo_earned: res.ammo_earned,
          ap_refund: res.ap_refund,
          heat_delta: res.heat_delta, heat: Math.max(0, Math.min(100, state.heat + (res.heat_delta || 0))),
          revealed: res.revealed, text: res.transcript_hint,
          summary: { ammo: res.ammo, passed: res.passed }
        });
      }
      else if (k === 'echo_open') {
        const ch = echoChallengeOf();
        emit('system', { event: 'echo_challenge', challenge: ch, log: state.echo.log.slice(),
          summary: { lines: state.echo.log.length, contradictions: echoContradictions().length },
          text: ch.text });
      }
      else if (k === 'echo_defend') {
        const res = echoDefendOf(p.picks || []);
        emit('system', { event: 'echo_defend_result', passed: !!res.passed, mode: res.mode,
          reason: res.reason, ap_refund: res.passed ? 1 : 0, text: res.transcript_hint });
        if (res.passed) emitOwnedClue(emit, 'clue_033', { danmaku: ['你自己的话成了证据', '回声入卷'] });
      }
      else if (k === 'debate_open') {
        let stance = 'open', text = '法官点头：案卷干净，本庭愿意听你说话。请陈词。';
        if (state.heat >= 60) { stance = 'skeptical'; text = '法官敲了敲桌面：热搜上全是你的负面消息——在本庭，声量也是一种证词。请陈词。'; }
        else if (state.heat >= 30) text = '法官抬眼：舆论场杂音不小，但本庭仍愿听你陈述。请陈词。';
        emit('system', { event: 'debate_open', stance, score: state.debate.score, need: 4,
          summary: { score: state.debate.score, stance, convinced: state.debate.convinced, need: 4 },
          text });
      }
      else if (k === 'debate_submit') {
        const res = debateSubmitOf(p.claim || '');
        emit('system', { event: 'debate_result', gain: res.gain, total: res.total, stance: res.stance,
          convinced: res.convinced, reasons: res.reasons, claim: String(p.claim || '').slice(0, 300),
          summary: { score: res.total, stance: res.stance, convinced: res.convinced, need: 4 },
          text: res.transcript_hint });
        if (res.convinced) emitOwnedClue(emit, 'clue_034', { danmaku: ['本庭采信', '法官放下了笔'] });
      }
      else if (k === 'cocoon_break') Engine.cocoon_break(p, emit);
      else if (k === 'evidence_pin') Engine.evidence_pin(p, emit);
      else if (k === 'defect') Engine.defect(p, emit);
      else if (k === 'judge_line') Engine.judge_line(p, emit);
      else if (k === 'flood_comments') {
        if (state.act < 3 && !state.demo) return emit('system', { toast: '控评是第三幕舆论技', kind: 'warn' });
        if (state.ap < 2) return emit('system', { toast: '控评消耗 2 行动点', kind: 'warn' });
        emit('system', { apDelta: -2 });
        emit('system', { event: 'flood_result', ok: true, post: p.post, heat_delta: 6,
          heat: Math.min(100, state.heat + 6), text: '控评成功：水军声量淹没真线索，热度 +6' });
      }
      else if (k === 'report_spam') {
        if (state.act < 3 && !state.demo) return emit('system', { toast: '举报是第三幕舆论技', kind: 'warn' });
        const evN = Number(p.evidence_n || Object.keys(state.clues).length || 0);
        if (evN < 1) return emit('system', { event: 'report_spam_result', ok: false, reason: 'need_evidence', text: '举报失败：至少要有 1 条证物' });
        if (state.ap < 2) return emit('system', { toast: '举报消耗 2 行动点', kind: 'warn' });
        emit('system', { apDelta: -2 });
        emit('system', { event: 'report_spam_result', ok: true, post: p.post, heat_delta: -4,
          heat: Math.max(0, state.heat - 4), text: '举报受理：假帖下架，热度 -4' });
      }
      else if (k === 'plant_fake') {
        const id = p.clue || p.clue_id;
        const c = clueById(id);
        if (!c || c.tier !== 'fake') return emit('system', { toast: '只能投放伪造线索', kind: 'warn' });
        emit('clue_gained', { clue_id: c.id, tier: c.tier, name: c.name, text: (c.fact || '') + ' ' + (c.flavor || ''), tags: c.tags, linked: c.linked, fake_of: c.fake_of });
        emit('system', { event: 'plant_fake_result', ok: true, clue_id: c.id, text: '伪证已混入公开池：《' + c.name + '》——圆桌见真章' });
      }
      else if (k === 'flip_side') {
        const id = p.clue_id || p.clue;
        const c = clueById(id);
        if (!c || !c.sides) return emit('system', { toast: '这条没有背面', kind: 'warn' });
        if (state.flipped[id]) return emit('system', { event: 'flip_result', clue_id: id, back: state.flipped[id].back, text: '背面已经翻过了' });
        const need = String((c.sides.back_condition || '默认')).replace('evidence:', '');
        if (need && need !== '默认' && !state.clues[need] && !state.clues[uiClueId(need)])
          return emit('system', { toast: '翻面条件未达成，背面继续装睡', kind: 'warn' });
        emit('system', { event: 'flip_result', clue_id: id, back: c.sides.back, front: c.sides.front || c.fact, text: '叮——背面解锁' });
      }
      else if (k === 'quiz_draw') playplusQuizDraw(emit);
      else if (k === 'quiz_answer') playplusQuizAnswer(p, emit);
      else if (k === 'radio_tune') playplusRadio(emit, false, p.note);
      else if (k === 'radio_request') {
        if (state.ap < 1) return emit('system', { toast: '点播消耗 1 行动点', kind: 'warn' });
        emit('system', { apDelta: -1 });
        playplusRadio(emit, true, p.note);
      }
      else if (k === 'first_vote_cast') {
        const target = p.target;
        const nm = Labels.who(target);
        emit('system', { event: 'first_vote_cast', target, binding: false, text: '非正式举手：本轮最可疑是' + nm + '（不影响结局）' });
      }
      else if (k === 'unlock_office') {
        const code = String(p.code || '').replace(/\s+/g, '');
        if (code !== '4729') return emit('system', { event: 'office_result', ok: false, text: '密码不对。金字塔：黄金→砖→泥的层数。' });
        emit('system', { event: 'office_result', ok: true, text: '咔哒——局长办公室门开了。桌上有策划手稿和一袋鱼干。' });
      }
      else if (k === 'expose_v587') {
        if (state.act < 2 && !state.demo) return emit('system', { toast: '第二幕才能翻开观察笔记', kind: 'warn' });
        emit('system', { event: 'v587_exposed', text: 'V587 三层身份摊开：新用户 → 侦探爱好者联盟 → 看山的影子学徒。' });
      }
    },

    counsel(p, emit) {
      const kc = kcById(p.kc_id), ch = charById(p.char_id);
      if (!kc || !ch) return;
      if (state.ap < 2) return emit('system', { toast: '开导消耗 2 行动点', kind: 'warn' });
      emit('system', { apDelta: -2 });
      const bindOk = kc.binds === ch.id || kc.binds === 'all' || (ch.kcAlt && kc.binds === ch.kcAlt) || (kc.binds === 'org' && false);
      const orgOk = kc.binds === 'org';
      if (orgOk) {
        emit('counsel_result', { ok: true, char_id: ch.id, kc_id: kc.id, reward: 'clue:clue_gate', lines: ['你把金字塔架构图摊在桌上："层级即密码。"', ch.name + '盯着 4-7-2-9 念了三遍，局长办公室的门锁"咔哒"一声。'], danmaku: ['用知识开锁，物理老师哭了', '这就是读文档的重要性'] });
        return;
      }
      if (bindOk) {
        const lines = [
          `你翻开《${kc.title}》（知乎 · ${kc.author}），念出第一句：`,
          `「${kc.golden[0]}」`,
          `${ch.name}沉默了三秒，肩膀塌下来一点点——`,
          `「${kc.golden[1]}」……这话戳到我了。`,
          ch.heartLine || '（心声）谢谢你，我好像可以说了。',
          `最后一句，你把卡片推过去：「${kc.golden[2]}」`
        ];
        // V31：急诊红灯抢救（红灯活跃 + 本轮内用对卡 = 收益双倍）
        let doubled = false;
        if (state.er[ch.id] && state.er[ch.id] >= state.round) {
          doubled = true;
          delete state.er[ch.id];
          emit('system', { event: 'er_rescue', char_id: ch.id, text: M.erLines.rescue, tag: M.erLines.rescueTag, statusWord: (M.erLines.status[ch.id] || {}).saved || '' });
        }
        const rewards = { kc_01: 'clue:clue_jie', kc_02: 'heart', kc_03: 'clue:clue_door', kc_04: 'salt', kc_05: 'flaw:flavor_3', kc_06: 'chapter', kc_07: 'memory', kc_08: 'memory', kc_09: 'buff', kc_10: 'clue:clue_gate' };
        emit('counsel_result', { ok: true, char_id: ch.id, kc_id: kc.id, reward: rewards[kc.id] || 'none', lines, doubled, danmaku: pick3(M.danmaku.counsel_ok) });
      } else {
        emit('counsel_result', { ok: false, char_id: ch.id, kc_id: kc.id, lines: [`你掏出《${kc.title}》，${ch.name}礼貌微笑，眼神逐渐放空……`, '「你说得对，但是这和我的心病没有任何关系。」', '（尬聊现场，弹幕已就位）'], danmaku: pick3(M.danmaku.counsel_fail) });
        // V31：开导失败 → 急诊红灯（同一 NPC 每局限一次；expiry=当前轮+1）
        if (!state.erLimit[ch.id]) {
          state.erLimit[ch.id] = true;
          state.er[ch.id] = state.round + 1;
          emit('system', { event: 'er_light', char_id: ch.id, expiry: state.round + 1, text: M.erLines.light.replace('{name}', ch.name), dm: rnd(M.erLines.dmMock), statusWord: (M.erLines.status[ch.id] || {}).red || '' });
        } else {
          emit('system', { event: 'er_limit', char_id: ch.id, text: M.erLines.limit, mocks: M.erLines.mocks.slice(0, 2) });
        }
      }
    },

    vote(p, emit) {
      if (state.ended) return;
      const { target, evidence } = p;
      if (!target) return emit('system', { toast: '先选择指认对象', kind: 'warn' });
      if (!evidence || evidence.length < 2) return emit('system', { toast: '指认必须提交 ≥2 张证据卡', kind: 'warn' });
      const settle = (ui, extra) => {
        const pair = endingPair(ui);
        const profile = buildTruthProfile(Object.assign({ ending: pair.ending_id }, extra || {}));
        emit('vote', Object.assign({ target, evidence, ending: pair.ending_id, outcome: pair.outcome }, extra && extra.coverage ? { coverage: extra.coverage } : {}));
        emit('ending', { ending_id: pair.ending_id, outcome: pair.outcome, accused: target === 'dm' ? 'dm' : ('npc:' + target), profile });
      };
      if (target !== 'dm' && state.salt >= 5) {
        settle('chapter7', { accused_dm: false, coverage: coverage(evidence) });
        return;
      }
      if (target !== 'dm' && (state.v587Exposed || (state.v587 && state.v587.exposed)) &&
          state.counsel.some(r => r.ok && (r.reward === 'chapter' || r.kc_id === 'kc_01'))) {
        settle('fish', { accused_dm: false, coverage: coverage(evidence) });
        return;
      }
      if (target === 'dm') {
        if (flawCount() >= 5) {
          const enough = state.counsel.filter(r => r.ok).length >= 2;
          settle(enough ? 'kanshan' : 'truth', { accused_dm: true, coverage: { pct: 100, hit: GUILTY_NODES } });
        } else {
          settle('mock_dm', { accused_dm: true, coverage: { pct: 0, hit: [] } });
        }
        return;
      }
      if (target === 'char_01') {
        const cov = coverage(evidence);
        const ui = state.heat >= 90 ? 'pollution' : (cov.pct >= 90 ? 'perfect' : 'truth');
        settle(ui, { accused_dm: false, coverage: cov });
      } else {
        const rescued = ['char_03', 'char_04'].some(id => state.counsel.some(r => r.ok && r.char_id === id));
        const ui = state.heat >= 90 ? 'pollution' : (rescued ? 'redeem' : 'wrong');
        settle(ui, { accused_dm: false, coverage: coverage(evidence) });
      }
    },

    /* ---- 创新冲刺：A 信息茧房 / B 证据链 / C 策反（经 skill 上行；window.Engine 直调保留给 e2e） ---- */
    cocoon_break(p, emit) {
      if (!state.cocoon.active) return emit('system', { toast: '你还没掉进茧房，破什么茧', kind: 'warn' });
      if (state.cocoon.broken > 0) return emit('system', { toast: '茧已破，保持清醒就好', kind: 'good' });
      emit('system', { event: 'cocoon_break' });
    },
    evidence_pin(p, emit) {
      const id = p.clueId || p.clue_id;
      if (!id) return emit('system', { toast: '缺少线索 id', kind: 'warn' });
      if (!state.clues[id]) return emit('system', { toast: '还没搜到这条线索', kind: 'warn' });
      if (state.evidenceLinks.some(l => l.clueId === id || l.clue_id === id)) return emit('system', { toast: '这条已在拼图上', kind: 'warn' });
      const c = clueById(id); if (!c) return emit('system', { toast: '线索不存在', kind: 'warn' });
      emit('system', { event: 'evidence_pin', clueId: id, nodes: pinNodesOf(id) });
    },
    judge_line(p, emit) {
      ['clue_001', 'clue_002', 'clue_007'].forEach(id => {
        if (!state.clues[id] && !state.clues[uiClueId(id)]) {
          const c = clueById(id);
          if (c) emit('clue_gained', {
            clue_id: c.id, tier: c.tier, name: c.name,
            text: (c.fact || '') + ' ' + (c.flavor || ''),
            tags: c.tags || [], linked: pinNodesOf(c.id)
          });
        }
        const uid = (state.clues[id] && id) || uiClueId(id);
        if (!state.evidenceLinks.some(l => l.clueId === uid || l.clue_id === uid || l.clueId === id))
          emit('system', { event: 'evidence_pin', clueId: uid, nodes: pinNodesOf(uid), silent: true });
      });
      const cov = evidenceCoverage();
      emit('system', { event: 'judge_line_ready', coverage: cov,
        text: '评委线已开：对照 → 回声 → 法官 → 画像（拼图覆盖 ' + cov.pct + '%）' });
    },
    defect(p, emit) {
      const cid = p.charId || p.char_id;
      if (!['char_03', 'char_04'].includes(cid)) return emit('system', { toast: '这位不是被裹挟者', kind: 'warn' });
      if (state.defection[cid] && state.defection[cid].flipped) return emit('system', { toast: '已经策反过了', kind: 'good' });
      if (evidenceCoverage().pct < 50) return emit('system', { toast: '证据不足，无法说服被裹挟者跳反（需 ≥50% 真相节点）', kind: 'warn' });
      emit('system', { event: 'defect', charId: cid });
    },

    advance(p, emit) {
      if (state.ended) return emit('system', { toast: '对局已结束，去复盘页看看', kind: 'warn' });
      /* --- V31：押注结算（全池归胜方按比例；猜错充公；押注加热 +1~5 封顶） --- */
      const bet = state.bet;
      if (bet && bet.open) {
        bet.open = false;
        const pool = Object.values(bet.wagers).reduce((s, x) => s + x.amt, 0);
        // AI 舆论确定性倾向：热度最高倾向首位选项（演示语义：多数人信流量酱以外的第一个人选）
        const winning = pool ? Object.keys(bet.wagers).sort((a, b) => bet.wagers[b].amt - bet.wagers[a].amt)[0] : null;
        if (winning && bet.wagers[winning].my) {
          const share = bet.wagers[winning];
          const payout = Math.floor(pool * share.my / Math.max(1, share.amt));
          state.zans += payout;
          emit('system', { event: 'bet_settle', win: true, payout, pool, text: M.betLines.win[0], heatAdd: Math.min(5, 1 + Object.keys(bet.wagers).length) });
        } else if (winning) {
          emit('system', { event: 'bet_settle', win: false, payout: 0, pool, text: M.betLines.lose[0], heatAdd: Math.min(5, 1 + Object.keys(bet.wagers).length) });
        }
        // 连押彩蛋：连续 3 轮押同一人
        if (state.betStreak.count >= 3) emit('system', { event: 'bet_streak', text: M.betLines.streak[0] });
      }
      /* --- V31：急诊红灯过期检查（expiry=当前轮+1） --- */
      Object.keys(state.er).forEach(cid => {
        if (state.er[cid] < state.round + 1) {
          const ch = charById(cid);
          emit('system', { event: 'er_expire', char_id: cid, text: M.erLines.expire.replace('{name}', ch ? ch.name : cid) });
        }
      });
      /* --- V31：头条流拍结算（上轮开标无人出价 → 热度自己涨 +2） --- */
      if (state.headline && !state.headline.settled) {
        state.headline.settled = true; state.headline.winner = null;
        state.heat = Math.min(100, state.heat + 2);
        emit('system', { event: 'headline_result', bid: null, settle: { winner: null, amount: 0, heat_delta: 2 }, host_line: '', result_line: M.headlineLines.lose, heatDelta: 2, pinned: false });
      }
      const nextRound = state.round + 1;
      if (state.stage === 'break_ice') state.stage = 'investigate';
      emit('system', { roundSet: nextRound, apSet: 3 });
      emit('hotfeed_refresh', { round: nextRound });
      const nextAct = Math.min(3, Math.ceil(nextRound / 3));
      if (nextAct !== state.act) { emit('system', { actSet: nextAct }); emit('system', { event: 'elevator_run', to: nextAct }); }
      if (!state.firstVote.done && !state.firstVote.poll_id && nextRound >= 2)
        emit('system', { event: 'first_vote', kind: 'informal', binding: false, poll_id: 'first_vote_mock' });
      if (nextRound % 2 === 0) playplusRadio(emit, false);
      emit('chat', { char_id: 'dm', text: rnd(M.dmLines.roundStart), actor_kind: 'dm' });
      if (nextRound === 4) emit('chat', { char_id: 'dm', text: M.dmLines.act2[0], actor_kind: 'dm' });
      if (nextRound === 7) emit('chat', { char_id: 'dm', text: M.dmLines.act3[0], actor_kind: 'dm' });
      /* --- V31：抽风掷骰（每幕至多 2 次）→ 横幅 + effect --- */
      const gActN = state.glitchPerAct[nextAct] || 0;
      if (gActN < 2 && Math.random() < 0.45) {
        state.glitchPerAct[nextAct] = gActN + 1;
        const r = Math.random();
        const poolPick = r < 0.4 ? M.glitch.punish : r < 0.75 ? M.glitch.fault : M.glitch.bonus;
        const g = rnd(poolPick);
        emit('system', { event: 'glitch', glitch: g.glitch, rewrite: g.rewrite, effect: g.effect, heatAdd: g.effect === 'heat_bump' ? 3 : 0 });
      }
      /* --- V31：新押注开盘（每轮 1 场） --- */
      const bj = rnd(M.betLines.subjects);
      state.bet = { id: 'bet_r' + nextRound, subject: bj.subject, options: bj.options.slice(), wagers: {}, round: nextRound, open: true };
      emit('system', { event: 'bet_open', bet: { id: state.bet.id, subject: state.bet.subject, options: state.bet.options }, text: M.betLines.open[0] });
      /* --- V31：头条位开标 --- */
      const ht = rnd(M.headlineTopics);
      state.headline = { round: nextRound, topic: ht.topic, note: ht.note, bids: [], settled: false, winner: null };
      emit('system', { event: 'headline_open', topic: ht.topic, note: ht.note, text: M.headlineLines.open.replace('{topic}', ht.topic) });
    }
  };
  function pick3(a) { return a.slice(0, 3); }

  const QUIZ_BANK = [
    { q: '横幅上写的八个字是？', options: ['不出真相不出此门', '不开门不出门', '真不出门了'] },
    { q: '案发夜 DM 的口头禅是？', options: ['叮——', '汪——', '喵——'] },
    { q: '监控被删除的时段是？', options: ['21:07-21:15', '22:30-22:40', '全删了'] },
    { q: '删除监控用的账号权限是？', options: ['局长级 KS-000', '实习生号', '访客号'] },
    { q: '看山的鱼干口味是？', options: ['彩虹鳟鱼味', '金枪鱼味', '香辣味'] },
    { q: '热搜热度曲线从几点开始"纪律严明"？', options: ['21:10', '22:00', '23:00'] },
    { q: '路人甲的口供把什么说成了什么？', options: ['代班→值班', '值班→代班', '上班→下班'] },
    { q: '水军矩阵有多少个设备指纹同源的号？', options: ['47', '14', '404'] },
    { q: '看山Bot 删日志后留下了什么？', options: ['哈希值 A3F9-77C2', '道歉信', '什么都没留'] },
    { q: '盐值君在门禁系统留言板上写了？', options: ['建议关注', '强烈谴责', '我不管了'] },
    { q: '流量酱真正在后台待了多久？', options: ['15 分钟', '0 分钟', '3 小时'] },
    { q: '笔上仙的剧中剧叫？', options: ['学科修仙', '修仙学科', '学科修罗场'] },
    { q: '沉底君被折叠的答案序号是？', options: ['被折叠的第 7 章', '第 1 章', '第 100 章'] },
    { q: 'V587 的老号曾用什么身份活跃？', options: ['侦探爱好者联盟', '钓鱼佬联盟', '吃瓜联盟'] },
    { q: '集齐几个破绽可以指认 DM？', options: ['5', '3', '2'] },
    { q: '系统唤醒词是？', options: ['看山，关门', '看山，开门', '芝麻关门'] },
    { q: '心晴自习室的正确用法是？', options: ['抽知识卡开导心病', '睡午觉', '避难'] },
    { q: '辟谣需要消耗？', options: ['2AP+对应知识卡', '0AP', '喊得够大声'] },
    { q: '二十年前的大力丸在哪里被搜出？', options: ['空调机房', '茶水间', '天台'] },
    { q: '终极结局的名字是？', options: ['看山还是山', '看山不是山', '看山去哪了'] }
  ];
  const RADIO_LINES = [
    '【广播台】现在是档案局时间。封控第 {n} 小时，泡面消耗 4 桶，线索 {c} 条，真相进度：本台不便透露。',
    '【广播台】天气预报：档案局今夜有雾，能见度不足一条热搜。请各位不要出门——反正门也锁着。',
    '【广播台】本台提醒：折叠区怨灵沉底君的发言没有被折叠，请大家正常倾听，不要围观。',
    '【广播台】寻物启事：一袋彩虹鳟鱼味鱼干，最后出现于 21:00 前的档案室。知情者请勿私聊，直接喊出来。',
    '【广播台】寻人启事：首席侦探刘看山，男，北极狐，最后出现时说「谁都不许跟来」。',
    '【广播台】点播台规则：1 行动点 = 30 秒广播时间。本台保留因内容太尬而提前掐断的权利。'
  ];
  function saltIdList() {
    return (M.salt7Ids && M.salt7Ids.length) ? M.salt7Ids.slice() : ['salt_f1', 'salt_f2', 'salt_f3', 'salt_f4', 'clue_022'];
  }
  function recountSalt() {
    let n = 0;
    const seen = {};
    saltIdList().forEach(id => { if (state.clues[id] && !seen[id]) { seen[id] = 1; n++; } });
    Object.keys(state.clues).forEach(id => {
      if (seen[id]) return;
      const rec = state.clues[id] || {};
      const c = clueById(id);
      const name = rec.name || (c && c.name) || '';
      if ((c && c.series === 'salt7') || /彩蛋碎片|学科修仙|第\s*7\s*章/.test(name)) {
        seen[id] = 1; n++;
      }
    });
    state.salt = Math.min(5, n);
    return state.salt;
  }
  function playplusQuizDraw(emit) {
    const qz = state.quiz;
    if (qz.asked >= 10) {
      qz.done = true; qz.q = '';
      return emit('system', { event: 'quiz_question', asked: qz.asked, score: qz.score, done: true, text: '十题已问完。分数已记入本局报告。' });
    }
    const seen = qz.seen || [];
    const left = QUIZ_BANK.map((_, i) => i).filter(i => seen.indexOf(i) < 0);
    const idx = left.length ? left[Math.floor(Math.random() * left.length)] : (qz.asked % QUIZ_BANK.length);
    const row = QUIZ_BANK[idx];
    seen.push(idx);
    qz.seen = seen; qz.idx = idx; qz.q = row.q; qz.options = row.options.slice(); qz.last = null; qz.open = true;
    emit('system', { event: 'quiz_question', idx, q: row.q, options: row.options.slice(), asked: qz.asked, score: qz.score });
  }
  function playplusQuizAnswer(p, emit) {
    const qz = state.quiz;
    const choice = Number(p.choice);
    if (!qz.q) return emit('system', { toast: '先抽一题', kind: 'warn' });
    const ok = choice === 0;
    qz.asked += 1;
    if (ok) qz.score += 1;
    qz.last = { ok, choice };
    qz.q = ''; qz.options = [];
    emit('system', { event: 'quiz_result', ok, score: qz.score, asked: qz.asked,
      toast: ok ? '答对。赞数 +2' : '答错。弹幕已经就位，不扣进度。',
      text: ok ? '叮——答对。' : '叮——答错。记住横幅上那八个字就好。' });
  }
  function playplusRadio(emit, request, note) {
    const n = state.round;
    const c = Object.keys(state.clues).length;
    let text = RADIO_LINES[(n + (request ? 3 : 0)) % RADIO_LINES.length]
      .replace('{n}', String(n)).replace('{c}', String(c));
    if (request && note) text += ' 点播附言：' + String(note).slice(0, 40);
    emit('system', { event: 'radio_broadcast', text, request: !!request });
  }

  /* ---------- V31 系统事件应用（Mock 产出 / F 服务端转发 共用） ---------- */
  function applyV31SystemEvent(p) {
    const ev = p.event;
    if (!ev) return;
    const chName = cid => Labels.who(cid);
    /* 头条竞价出价者显示名：复用 Labels.who（既有玩家名解析），本人特判为「你」 */
    const hlBidderName = id => {
      if (!id) return '神秘人';
      if (id === (state.playerId || 'player:1')) return '你';
      const nm = chName(id);
      return nm && nm !== '在场者' ? nm : String(id);
    };
    switch (ev) {
      case 'case_intro':
        state.caseIntro = { title: p.title, summary: p.summary, attribution: p.attribution };
        break;
      case 'evidence_composed': {
        const e = p.evidence || {};
        if (e.evidence_id && !state.synth.some(x => x.id === e.evidence_id)) state.synth.push({
          id: e.evidence_id, name: '证据卡 · ' + Labels.node((e.truth_nodes || [])[0]),
          node: (e.truth_nodes || [])[0], clueIds: e.clue_ids || [] });
        if (p.text) chat('sys', p.text, { kind: 'clue' });
        break;
      }
      case 'flaw_progress':
      case 'boss_ready':
        if (p.flaw_count !== undefined) state.engineFlawCount = p.flaw_count;
        if (p.text) chat('sys', p.text, { kind: 'flaw' });
        break;
      case 'vote_pending':
      case 'advance_noop':
        if (p.text) chat('dm', p.text);
        break;
      case 'stage_changed':
        if (p.stage) state.stage = p.stage;
        if (p.actions_left !== undefined && state.mode !== 'party') state.ap = p.actions_left;
        break;
      case 'act_transition':
        state.actBrief = { title: p.act_name, text: p.act_brief, stage: p.stage };
        if (p.act_name || p.act_brief) chat('dm', [p.act_name, p.act_brief].filter(Boolean).join('：'));
        break;
      case 'difficulty_set':
      case 'memory_no_op':
        if (p.text) chat('sys', p.text);
        break;
      case 'ai_takeover':
        state.partySeats = (state.partySeats || []).map(s => s.char_id === p.char_id ? { ...s, is_ai: true, ai_takeover: true, connected: false } : s);
        chat('sys', p.notice || '该角色已由 AI 接管');
        break;
      case 'heat_report':
        state.heatReport = { heat: p.heat, blocked: (p.blocked_clues || []).length, text: p.text };
        if (p.heat !== undefined) state.heat = p.heat;
        break;
      case 'snapshot':
        (p.clues_gained || []).forEach(id => {
          const uid = uiClueId(id);
          if (!id) return;
          if (!state.clues[uid] && !state.clues[id]) state.clues[uid] = { at: state.round, engineId: id };
          else if (state.clues[id] && uid !== id) {
            if (!state.clues[uid]) state.clues[uid] = state.clues[id];
            delete state.clues[id];
          }
        });
        if (p.heat != null) state.heat = p.heat;
        if (p.flaw_count !== undefined) state.engineFlawCount = p.flaw_count;
        if (p.round != null) state.round = p.round;
        /* 与引擎 actSet 对齐：破冰+搜证=第1章，圆桌对质=第2章，指认/舆论=第3章。
           investigate 切到 2 会摘掉「现场搜证」（P4 已踩过的坑）。 */
        if (p.stage) state.stage = p.stage;
        if (p.stage && ({ break_ice: 1, investigate: 1, round_table: 2, accuse: 3 })[p.stage])
          state.act = ({ break_ice: 1, investigate: 1, round_table: 2, accuse: 3 })[p.stage];
        break;
      case 'ap_sync':
        if (!p.player_id || p.player_id === state.playerId) {
          if (p.apSet !== undefined) state.ap = p.apSet;
          if (p.apMax) state.apMax = p.apMax;
        }
        break;
      case 'card_drawn': {
        if (p.booklet_act && (!p.player_id || p.player_id !== state.playerId)) break;
        const kid = (p.card && p.card.id) || p.kc_id;
        if (kid && !state.kcards[kid]) {
          state.kcards[kid] = { at: state.round };
          const kc = kcById(kid);
          toast('抽中知识卡' + (kc ? '《' + kc.title + '》' : ''), 'good');
          playSfx('page');
        }
        break;
      }
      /* 抽风横幅：故障句 → 1.6s 后 DM 重写句；effect: ap_free / heat_bump */
      case 'glitch':
        playSfx('glitch');
        banner(p.glitch, 'glitch');
        if (p.rewrite) setTimeout(() => banner(p.rewrite, 'glitch-fix'), 1600);
        if (p.effect === 'ap_free') { state.glitchFree = true; toast('抽风补偿：下次行动免扣 AP', 'good'); }
        if (p.effect === 'heat_bump') { state.heat = Math.min(100, state.heat + (p.heatAdd || 3)); toast('抽风加成：热度 +' + (p.heatAdd || 3), 'warn'); }
        pushDmaku(['系统又抽风了', '这 bug 好带感', '截图截图'], 'sys');
        break;
      /* 押注（币种=赞数） */
      case 'bet_open':
        toast('押注通道开启：' + p.bet.subject + '（币种：赞数）', 'gold');
        banner(p.text, 'bet');
        break;
      case 'bet_placed':
        toast('押注成功：' + p.amount + ' 赞 → ' + chName(p.option) + '（奖池 ' + p.pool + '）', 'gold');
        pushDmaku(['赌狗启动', '压上全部家当（不是）'], 'sys');
        break;
      case 'bet_settle': {
        playSfx('ding');
        if (p.win) { state.zans += 0; toast('押中！赔付 +' + p.payout + ' 赞（奖池 ' + p.pool + '）', 'good'); pushDmaku(['眼光毒辣', '跟押的都赢了'], 'sys'); }
        else { toast('押错了。本金充公，赠 AI 锐评一条（不接受退款）', 'warn'); pushDmaku(['血本无归（+5 赞那种）', '下一把必中'], 'gray'); }
        if (p.heatAdd) state.heat = Math.min(100, state.heat + p.heatAdd);
        break;
      }
      case 'bet_streak':
        banner(p.text, 'egg');
        break;
      /* 急诊红灯 */
      case 'er_light':
        playSfx('buzz');
        state.er[p.char_id] = p.expiry;
        banner(p.text, 'er');
        chat('sys', '【急诊红灯 · ' + chName(p.char_id) + '】' + (p.statusWord || '病情恶化'), { kind: 'warn' });
        pushDmaku(['红灯了红灯了', '快带对口知识卡急救', '抢救窗口：下一轮'], 'sys');
        break;
      case 'er_rescue':
        playSfx('green');
        delete state.er[p.char_id];
        state.erGreen = { cid: p.char_id, at: Date.now() };  // 红灯"啪"转绿（clinic 0.5s 闪光演出）
        banner(p.text, 'er-ok');
        if (p.statusWord) chat('sys', '【抢救成功 · ' + chName(p.char_id) + '】' + p.statusWord, { kind: 'counsel' });
        pushDmaku(['抢救回来了', '医生说很成功', '双倍收益，酸了'], 'sys');
        break;
      case 'er_limit':
        toast(p.text, 'warn');
        (p.mocks || []).forEach(m => pushDmaku([m], 'gray'));
        break;
      case 'er_expire':
        delete state.er[p.char_id];
        toast(p.text, 'warn');
        break;
      /* 头条竞标：新契约 window_id 竞价轮次（headline_open/bid/outbid/settle）；
         无 window_id 走本地演示单话题开盘（一次性结算，行为不变） */
      case 'headline_open':
        playSfx('ding');
        playSfx('auction');
        if (p.window_id && Array.isArray(p.topics)) {
          state.headline = {
            mode: 'auction', windowId: p.window_id, round: p.round || state.round,
            topics: p.topics.slice(), minBid: p.min_bid || 1,
            deadlineTs: p.deadline_ts || null, deadlineIn: p.deadline_in || 0,
            openedAt: Date.now(), bids: [], top: null, topAmount: 0,
            settled: false, winner: null, result: null
          };
          banner('头条竞价窗口开启：' + p.topics.length + ' 个话题，底价 ' + state.headline.minBid + 'AP', 'headline');
          chat('sys', '【头条竞价】窗口已开——出价=行动点，按底价 ' + state.headline.minBid + 'AP 步进，被反超可加价或弃拍。', { kind: 'clue' });
          pushDmaku(['竞价开始了', '头条不等人', '拍下它'], 'sys');
        } else {
          state.headline = { round: state.round, topic: p.topic, note: p.note, bids: [], settled: false, winner: null };
          banner(p.text, 'headline');
        }
        break;
      case 'headline_bid':
        if (state.headline && state.headline.mode === 'auction' && (!p.window_id || p.window_id === state.headline.windowId)) {
          state.headline.bids = state.headline.bids || [];
          state.headline.bids.push({ who: p.bidder, amount: p.amount });
          if (p.is_top) {
            state.headline.top = p.bidder;
            state.headline.topAmount = p.top_amount !== undefined ? p.top_amount : p.amount;
            if (p.bidder === (state.playerId || 'player:1')) toast('你的出价目前领先：' + p.amount + 'AP', 'good');
          }
        }
        break;
      case 'headline_outbid':
        if (state.headline && state.headline.mode === 'auction' && (!p.window_id || p.window_id === state.headline.windowId)) {
          state.headline.top = p.bidder;
          state.headline.topAmount = p.new_amount;
          const meId = state.playerId || 'player:1';
          if (p.prev_bidder === meId || p.prev_bidder === 'player:1') {
            playSfx('miss');
            toast('你的出价被 ' + hlBidderName(p.bidder) + ' 反超（当前最高 ' + p.new_amount + 'AP）', 'warn');
            pushDmaku(['手速被针对了', '加价还是弃拍？'], 'sys');
          }
        }
        break;
      case 'headline_settle': {
        playSfx('heat');
        const meId2 = state.playerId || 'player:1';
        const line = p.winner
          ? '叮——头条成交：《' + (p.topic_title || '话题') + '》由 ' + hlBidderName(p.winner) + ' 以 ' + p.amount + 'AP 拍下。'
          : '叮——流拍。头条位空着，热度自己涨了——热搜从来不等谁。';
        if (state.headline && state.headline.mode === 'auction') {
          state.headline.settled = true;
          state.headline.closed = true;          // 关竞价窗口，面板回结算展示态
          state.headline.winner = p.winner || null;
          state.headline.topicTitle = p.topic_title || '';
          state.headline.cost = p.amount || 0;
          state.headline.effect = p.effect || null;
          state.headline.result = line;
        }
        banner(line, p.winner === meId2 ? 'headline' : 'warn');
        chat('sys', '【头条竞价】' + line, { kind: p.winner === meId2 ? 'counsel' : 'warn' });
        pushDmaku(p.winner ? ['成交！', '头条易主'] : ['流拍了', '热搜自己涨'], 'sys');
        break;
      }
      case 'headline_result':
        playSfx('heat');
        state.headline = state.headline || { round: state.round, topic: '', bids: [], settled: false };
        state.headline.settled = true;
        state.headline.winner = (p.settle || {}).winner;
        state.headline.topic = p.topic || (p.settle || {}).post_id || state.headline.topic;
        state.headline.result = p.result_line || p.notice;
        state.headline.cost = p.cost;
        if (p.heatSet !== undefined) state.heat = p.heatSet;
        if (p.heatDelta) state.heat = Math.max(0, Math.min(100, state.heat + p.heatDelta));
        banner(p.result_line || '头条结算完成', (p.settle || {}).winner === (state.playerId || 'player:1') ? 'headline' : 'warn');
        chat('sys', '【头条竞标】' + (p.result_line || ''), { kind: (p.settle || {}).winner === (state.playerId || 'player:1') ? 'counsel' : 'warn' });
        pushDmaku(['头条不保证真相，只保证热度', '手速就是公信力'], 'sys');
        break;
      /* 幕间电梯转场 */
      case 'elevator_run':
        state.elevator = { to: p.to || (state.act + 1), startedAt: Date.now() };
        break;
      /* 暗拍 */
      case 'stealth_photo':
      case 'stealth_photo_result':
        if (p.ok === false) { playSfx('miss'); toast(p.notice || p.text || '什么也没拍着', 'warn'); }
        else if (p.photo) {
          /* owner 隔离（缺口1）：照片只进持有者本人的私密照片墙；
             他人暗拍的照片不入墙（公共流出走 photo_shared） */
          const ph = p.photo, owner = ph.owner || p.owner || null;
          const mine = !owner || owner === (state.playerId || 'player:1');
          const pid = ph.photo_id || ph.id;
          if (mine && pid && !state.photos.some(x => x.id === pid)) {
            state.photos.push({ id: pid, clue_id: ph.clue_id, name: ph.name, text: ph.fact || ph.text || '', loc: ph.location || ph.loc, at: ph.round || state.round, shared: !!ph.shared, claim: ph.claim || '', exposed: false, owner: owner || state.playerId || 'player:1' });
          }
          playSfx('camera'); toast('暗拍成功：《' + ph.name + '》已入袋（原件留原地）', 'good'); chat('sys', '【暗拍 · ' + ph.name + '】' + (p.text || p.notice || ''), { kind: 'clue' });
        }
        else { playSfx('miss'); toast(p.text || p.notice || '什么也没拍着', 'warn'); }
        break;
      case 'photo_shared':
        /* 缺口1：流出照片进入公共视野——本人照片回写状态；他人照片以只读
           「已流出」形态入墙（claim 为声称内容，真伪留圆桌对质） */
        {
          const pid2 = p.photo_id;
          let ph2 = state.photos.find(x => x.id === pid2);
          if (ph2) { ph2.shared = true; ph2.claim = p.claim || ph2.claim; }
          else if (pid2) {
            state.photos.push({ id: pid2, clue_id: p.clue_id || null, name: p.name || '照片', text: '', loc: '', at: state.round, shared: true, claim: p.claim || '（未填声称）', exposed: false, owner: p.owner || 'player:?' });
          }
          chat('sys', '【照片流出】声称：' + (p.claim || '（未填）') + '——' + (p.notice || p.text || ''), { kind: 'warn' });
          pushDmaku(['照片是真的，话可不一定', '圆桌对质走起'], 'sys');
        }
        break;
      case 'cross_check_result':
        /* 缺口2：交叉验证裁决权威=服务端（verdict: exposed/insufficient）；
           degraded=true 表示服务端不可用回退的本地演示判定（如实标注） */
        {
          const exposed = p.verdict === 'exposed' || p.exposed === true;
          const fakeName = (window.Labels && window.Labels.clue(p.clue_id)) || p.clue_id || '伪证';
          const degradeTag = p.degraded ? '（本地演示判定，未经服务端裁决）' : '';
          chat('sys', '【交叉验证】伪造线索《' + fakeName + '》' + (exposed ? '被拆穿——与《' + (p.real_name || '真线索') + '》矛盾实锤，自动标记为伪证。' : '暂时拿不出实锤，先标记存疑。') + degradeTag, { kind: exposed ? 'clue' : 'warn' });
          if (exposed && p.clue_id) state.exposedFakes[p.clue_id] = true;
          pushDmaku(p.danmaku || (exposed ? ['伪证当场去世', '交叉验证，学到了'] : ['证据不足，先存疑']), 'sys');
        }
        break;
      /* 记忆拼图对质 */
      case 'memory_snapshot':
        state.liveMemories[p.char_id] = p;
        state.memVer[p.char_id] = p.version;
        state.heartUnlocked[p.char_id] = !!p.heart_unlocked;
        state.tamperPts = p.tamper_available;
        break;
      case 'puzzle_result':
      case 'puzzle_rejected':
        state.memoryPuzzleResult = { correct: !!p.correct, text: p.notice || '', char_id: p.char_id };
        if (p.tamper_available !== undefined) state.tamperPts = p.tamper_available;
        chat('sys', p.notice || '拼图已结算', { kind: p.correct ? 'counsel' : 'warn' });
        break;
      case 'memory_puzzle_open':
        toast('记忆拼图发起：60 秒，把已解锁记忆按时间排好（消耗 2 篡改点）', 'gold');
        break;
      case 'memory_puzzle_result':
        if (p.ok) {
          banner('时间线严丝合缝——历史今天被你们按住了', 'egg');
          if (p.clue && !state.clues[p.clue.clue_id]) { state.clues[p.clue.clue_id] = { at: state.round }; chat('sys', '【拼图奖励 · ' + p.clue.name + '】' + p.clue.text, { kind: 'clue' }); synthCheck(); }
          pushDmaku(['排对全场得线索', '时间线钉子户+1'], 'sys');
        } else {
          banner(p.text, 'warn');
          pushDmaku(['剪错了帧', 'DM 锐评暴击'], 'gray');
        }
        break;
      /* 反诈剧场 */
      case 'antifraud_result':
        state.antifraud.active = false;
        if (p.right) { toast(p.text, 'good'); banner('反诈学分 +1（成就：反诈先锋）', 'egg'); }
        else toast(p.text, 'warn');
        break;
      /* 终局陈词 + 锤人分池 */
      case 'closing_registered':
        chat('sys', '【终局陈词登记】' + p.text, { kind: 'counsel' });
        if (p.mock) pushDmaku([p.mock], 'sys');
        break;
      case 'hammer_result':
        playSfx('hammer');
        state.hammer = { speech: (state.hammer || {}).speech || '', target: p.target, tally: p.tally, most: p.most_hammered, at: state.round };
        banner(p.text, 'hammer');
        pushDmaku(['锤声一片', '锤你说明你有热度'], 'sys');
        break;
      /* 心声广播事故（白名单外壳） */
      case 'broadcast_accident':
        banner('【突发广播】' + (p.text || '').slice(0, 60), 'broadcast');
        chat('sys', '【心声广播事故】' + p.text, { kind: 'warn' });
        pushDmaku(['心声串台了哈哈哈哈', '5 秒尴尬事故现场'], 'sys');
        break;
      /* 侦探报告（终局；服务端 rt.report_flow 产物） */
      case 'detective_report':
        state.report = { report_text: p.report_text || '', badges: p.badges || [], achievements: p.achievements || [], builtAt: Date.now() };
        banner('《侦探报告》已生成——推理评分与高光回放入档', 'gold');
        break;
      /* 侦探证（登录后） */
      case 'dossier_ready':
        state.dossier = p.dossier;
        banner('《求真档案局特聘侦探证》已签发：' + p.dossier.rank, 'dossier');
        if (p.personal_line) chat('npc', p.personal_line, { char_id: 'char_04' });
        pushDmaku(['警衔也太欢乐了', '这证我想裱起来'], 'sys');
        break;
      /* 收集品（P3 鱼干寻物：彩蛋层，不进证据链、零行动点） */
      case 'collect_result': {
        if (!p.collected) { toast(p.text || '这里没有可拾取的收集品', 'warn'); break; }
        const fishMeta = M.fishCollectibles.find(f => f.id === p.item);
        state.fish[p.item] = state.fish[p.item] || { at: state.round };
        toast('鱼干收集品入手：' + (fishMeta ? fishMeta.anchor : '鱼干') + '（0AP · 彩蛋层）', 'gold');
        if (p.show) {
          chat('sys', '【拾取 · ' + (fishMeta ? Labels.place(fishMeta.loc) : '现场') + '】' + p.show.pickup, { kind: 'counsel' });
          chat('dm', p.show.bot, {});
          pushDmaku([p.show.dm], 'sys');
        }
        const gotN = M.fishCollectibles.filter(f => state.fish[f.id]).length;
        pushDmaku(['鱼干进度 ' + gotN + '/3', '微光点 Scanner 上线'], 'sys');
        playSfx('ding');
        if (p.all_collected) {
          banner('🏆 成就解锁：鱼干线人——看山Bot 隐藏语音已解锁', 'gold');
          state.fishVoice = { line: 0 };  // 4 段逐句切片播（演出组件接管）
          pushDmaku(['隐藏语音！Bot 要说真心话了', '风扇转速：平稳'], 'sys');
        }
        break;
      }
      /* ---- V5 反操纵三件套 ---- */
      case 'pollution_case':
        state.pollution.case = p.case || null;
        state.pollution.result = null;
        if (p.text) chat('sys', '【污染对照】' + p.text, { kind: 'counsel' });
        banner('对照题已展开：圈出被植入的操纵', 'gold');
        playSfx('ding');
        break;
      case 'pollution_done':
        state.pollution.case = null;
        state.pollution.summary = p.summary || state.pollution.summary;
        toast(p.text || '对照题已全部完成', 'good');
        break;
      case 'pollution_result': {
        state.pollution.result = p;
        state.pollution.ammo = p.ammo != null ? p.ammo : state.pollution.ammo;
        if (p.ammo_earned != null) state.pollution.earned = p.ammo_earned;
        else if (p.passed && p.first_try) state.pollution.earned = (state.pollution.earned || 0) + 1;
        if (p.case_id) state.pollution.done[p.case_id] = { passed: !!p.passed };
        if (p.heat != null) state.heat = p.heat;
        else if (p.heat_delta) state.heat = Math.max(0, Math.min(100, state.heat + p.heat_delta));
        if (p.ap_refund) state.ap = Math.min(state.apMax, state.ap + p.ap_refund);
        chat('sys', '【污染对照】' + (p.text || ''), { kind: p.passed ? 'counsel' : 'warn' });
        toast(p.passed ? '对照全对——辟谣弹药 +1' : '对照未过关：判断操纵不能只靠语感', p.passed ? 'good' : 'warn');
        playSfx(p.passed ? 'pass' : 'fail');
        pushDmaku(p.passed ? ['拆穿水军了', '这才是求真'] : ['原句也能长得像操纵', '再读一遍'], p.passed ? 'sys' : 'gray');
        break;
      }
      case 'echo_challenge':
        state.echo.challenge = p.challenge || null;
        state.echo.result = null;
        if (p.text) chat('dm', p.text, {});
        banner('回声档案已投影——指出你自己矛盾的两句，或证明全程一致', 'echo');
        playSfx('archive');
        break;
      case 'echo_defend_result':
        state.echo.result = p;
        state.echo.defended = !!p.passed;
        if (p.ap_refund) state.ap = Math.min(state.apMax, state.ap + p.ap_refund);
        chat('sys', '【引自证】' + (p.text || p.reason || ''), { kind: p.passed ? 'counsel' : 'warn' });
        toast(p.passed ? '自证成立：你的原话被你自己认领了' : '自证失败：看山把这段也记进了档案', p.passed ? 'good' : 'warn');
        playSfx(p.passed ? 'pass' : 'fail');
        break;
      case 'debate_open':
        state.debate.open = true;
        state.debate.stance = p.stance || 'open';
        state.debate.score = p.score != null ? p.score : state.debate.score;
        state.debate.need = p.need || 4;
        state.debate.text = p.text || '';
        chat('sys', '【AI 法官】' + (p.text || ''), { kind: 'counsel' });
        banner('法官入席——热度越高，他越怀疑你', 'gold');
        playSfx('gavel');
        break;
      case 'debate_result':
        state.debate.score = p.total != null ? p.total : state.debate.score;
        state.debate.stance = p.stance || state.debate.stance;
        state.debate.convinced = !!p.convinced;
        state.debate.rounds.push({ text: p.claim || '', gain: p.gain, at: state.round });
        chat('sys', '【法官】' + (p.text || ''), { kind: p.convinced ? 'counsel' : 'warn' });
        toast(p.convinced ? '本庭采信——关键线索入卷' : ('陈词 ' + (p.gain >= 0 ? '+' : '') + p.gain + ' · 累计 ' + p.total + '/' + (p.need || 4)), p.convinced ? 'good' : 'warn');
        playSfx(p.convinced ? 'pass' : 'gavel');
        break;
      case 'buy_heat_result':
        if (p.ok) state.buyHeats = (state.buyHeats || 0) + 1;
        if (p.heat != null) state.heat = p.heat;
        else if (p.heat_delta) state.heat = Math.min(100, state.heat + p.heat_delta);
        toast(p.text || (p.ok ? '买热搜成功' : '买热搜失败'), p.ok ? 'warn' : 'warn');
        break;
      case 'refute_result': {
        const postId = p.post || p.post_id;
        if (postId) state.refuted[postId] = { ok: !!p.ok, kc_id: p.card || p.kc_id };
        if (p.heat != null) state.heat = p.heat;
        else if (p.heat_delta) state.heat = Math.max(0, Math.min(100, state.heat + p.heat_delta));
        if (p.ammo != null) state.pollution.ammo = p.ammo;
        else if (p.ammo_spent) state.pollution.ammo = Math.max(0, (state.pollution.ammo || 0) - p.ammo_spent);
        if (p.ok && p.unlocked_clue && !state.clues[p.unlocked_clue]) {
          const c = clueById(p.unlocked_clue);
          if (c) { state.clues[c.id] = { at: state.round }; chat('sys', '【辟谣解锁真线索 · ' + c.name + '】' + c.fact, { kind: 'clue', tier: c.tier }); synthCheck(); }
        }
        chat('sys', '【辟谣 ' + (p.ok ? '成功' : '失败') + '】' + (p.text || ''), { kind: p.ok ? 'counsel' : 'warn' });
        toast(p.ok ? (p.ammo_spent ? '辟谣成功 · 对照弹药加码' : '辟谣成功') : '辟谣失败：判断操纵不能只靠语感', p.ok ? 'good' : 'warn');
        pushDmaku(p.ok ? (M.danmaku.refute_ok || ['辟谣成功']) : (p.crowd_mocks || M.danmaku.refute_fail || []), p.ok ? 'sys' : 'gray');
        if (p.ok && !state.demo && state.antifraud.count < 2 && Math.random() < 0.34) {
          state.antifraud.count += 1;
          state.antifraud.active = true;
          state.antifraud.act = 0;
          state.antifraud.answers = [];
        }
        break;
      }
      case 'cocoon_enter':
        applyCocoonEnter(p);
        break;
      case 'cocoon_break':
        applyCocoonBreak();
        break;
      case 'evidence_pin':
        applyEvidencePin(p);
        break;
      case 'defect':
        applyDefect(p);
        break;
      case 'judge_line_ready':
        state.demo = true;
        if (state.act < 2) state.act = 2;
        toast(p.text || '评委线已开', 'good');
        break;
      case 'pin_rejected':
      case 'cocoon_rejected':
      case 'defect_rejected':
        break;
      case 'flood_result':
        if (p.heat != null) state.heat = p.heat;
        else if (p.heat_delta) state.heat = Math.min(100, state.heat + p.heat_delta);
        toast(p.text || (p.ok ? '控评成功' : '控评失败'), p.ok ? 'warn' : 'warn');
        if (p.text) chat('sys', '【控评】' + p.text, { kind: 'warn' });
        break;
      case 'report_spam_result':
        if (p.heat != null) state.heat = p.heat;
        else if (p.ok && p.heat_delta) state.heat = Math.max(0, state.heat + p.heat_delta);
        toast(p.text || (p.ok ? '举报受理' : '举报失败'), p.ok ? 'good' : 'warn');
        if (p.text) chat('sys', '【举报水军】' + p.text, { kind: p.ok ? 'counsel' : 'warn' });
        break;
      case 'plant_fake_result':
        toast(p.text || (p.ok ? '伪证已投放' : (p.notice || '投放失败')), p.ok ? 'warn' : 'warn');
        if (p.text || p.notice) chat('sys', '【投放伪证】' + (p.text || p.notice), { kind: 'warn' });
        break;
      case 'flip_result':
        if (p.clue_id && (p.back || p.ok !== false)) {
          state.flipped[p.clue_id] = { back: p.back, at: state.round };
          const c = clueById(p.clue_id);
          if (c) c.back = p.back;
        }
        toast(p.text || '翻面结果', p.ok === false ? 'warn' : 'good');
        break;
      case 'quiz_question':
        state.quiz.open = true;
        state.quiz.idx = p.idx;
        state.quiz.q = p.done ? '' : (p.q || '');
        state.quiz.options = p.options || [];
        if (p.asked != null) state.quiz.asked = p.asked;
        if (p.score != null) state.quiz.score = p.score;
        state.quiz.done = !!p.done;
        if (p.done) toast(p.text || '十题已问完', 'gold');
        break;
      case 'quiz_result':
        state.quiz.last = { ok: !!p.ok, choice: p.choice };
        state.quiz.q = '';
        state.quiz.options = [];
        if (p.asked != null) state.quiz.asked = p.asked;
        if (p.score != null) state.quiz.score = p.score;
        if (p.ok) state.zans += 2;
        toast(p.toast || p.text || (p.ok ? '答对' : '答错'), p.ok ? 'good' : 'warn');
        break;
      case 'radio_broadcast':
        state.radio.open = true;
        state.radio.text = p.text || '';
        state.radio.log = (state.radio.log || []).concat([p.text || '']).slice(-8);
        if (p.request) state.radio.requestLeft = Math.max(0, (state.radio.requestLeft == null ? 3 : state.radio.requestLeft) - 1);
        banner((p.text || '广播台').slice(0, 60), 'broadcast');
        chat('sys', p.text || '【广播台】', { kind: 'counsel' });
        break;
      case 'first_vote':
        state.firstVote.open = true;
        state.firstVote.poll_id = p.poll_id || '';
        state.firstVote.done = false;
        toast(p.text || '非正式举手：选出本轮最可疑的人（不影响结局）', 'gold');
        if (state.view !== 'vote') state.view = 'chat';
        break;
      case 'first_vote_cast': {
        const tid = String(p.target || '').replace(/^npc:/, '');
        state.firstVote.pick = tid;
        state.firstVote.done = true;
        state.firstVote.open = false;
        const nm = Labels.who(tid);
        toast(p.text || ('非正式举手：本轮最可疑是' + nm), 'gold');
        chat('sys', '【举手表决】本轮最可疑：' + nm + '（不影响结局）', { kind: 'counsel' });
        break;
      }
      case 'office_result':
        if (p.ok) { state.officeOpen = true; state.office.open = true; }
        else state.office.tries = (state.office.tries || 0) + 1;
        toast(p.text || (p.ok ? '门开了' : '密码不对'), p.ok ? 'good' : 'warn');
        if (p.text) chat('sys', '【局长办公室】' + p.text, { kind: p.ok ? 'counsel' : 'warn' });
        break;
      case 'v587_exposed':
        if (p.ok !== false) {
          state.v587Exposed = true;
          state.v587.exposed = true;
        }
        toast(p.text || 'V587 观察笔记', p.ok === false ? 'warn' : 'gold');
        if (p.text) chat('sys', '【V587】' + p.text, { kind: p.ok === false ? 'warn' : 'counsel' });
        break;
      case 'mode_setup':
        state.playMode = p.mode || state.playMode;
        if (p.mode === 'quick' || p.mode === 'daily') {
          state.skipIce = true;
          state.stage = 'investigate';
        }
        toast(p.text || '模式已就绪', 'good');
        break;
      case 'daily_topic':
        state.playMode = 'daily';
        state.skipIce = true;
        state.stage = 'investigate';
        state.dailyTopic = { topic: p.topic || '#档案局夜班纪律#', body: p.text || '', source: 'session' };
        toast((p.topic || '') + ' ' + (p.text || '每日挑战已开'), 'gold');
        chat('sys', '【每日挑战】' + (p.topic || '') + ' ' + (p.text || ''), { kind: 'counsel' });
        break;
    }
  }

  /* ---------- V5 章节独占式：章末条件 + 前情提要兜底 ---------- */
  /* 章末条件（CHAPTER_UX_SPEC §三）：章一=拿到芯片线索(clue_021)、章二=篡改点≥2、章三=随时可进终局指认。
   * G3 driver 的 actCleared 事件（真引擎）将来可覆盖本地判定。演示模式跳章不受限。 */
  const CHAPTER_DEFS = {
    1: { name: '第一章 · 出不去的档案局', tag: '搜证章', next: '第二章 · 心声泄露' },
    2: { name: '第二章 · 心声泄露', tag: '对质章', next: '第三章 · 披着虎皮的猫' },
    3: { name: '第三章 · 披着虎皮的猫', tag: '舆论章', next: '终局指认' }
  };
  function chapterProgress() {
    const act = state.act || 1;
    const def = CHAPTER_DEFS[act] || CHAPTER_DEFS[1];
    let cleared = true, hint = '';
    if (state.demo) {
      hint = '演示模式：章节门控已豁免，可直接跳章';
    } else if (act === 1) {
      cleared = !!(state.clues['clue_021'] || state.clues['clue_004']
        || state.clues['clue_002'] || state.clues['clue_007']
        || state.clues['clue_001'] || state.clues['clue_006']);
      hint = cleared ? '「记忆芯片空盒」已入袋——芯片去向有了第一条实线' : '还差关键证物「记忆芯片空盒」（提示：去档案室搜「芯片」）';
    } else if (act === 2) {
      cleared = state.tamperPts >= 2;
      hint = cleared ? '篡改点 ' + state.tamperPts + '/2——时间线的裂缝已经攥在手里' : '还差 ' + (2 - state.tamperPts) + ' 个篡改点（提示：记忆修复找出两层矛盾）';
    } else if (act === 3) {
      hint = '证据齐全即可提交指认（≥2 张证据卡；破绽 5/5 解锁「指认 DM」）';
    }
    return { act, name: def.name, tag: def.tag, next: def.next, cleared, hint };
  }
  /* Mock 兜底前情提要（服务端 memory_doc 经 system.recap 覆盖；200 字摘要+关键收获） */
  function mockRecap(fromAct, toAct) {
    if (!fromAct || fromAct >= toAct) return null;
    const clueN = Object.keys(state.clues).length;
    const flawN = flawCount();
    const base = fromAct === 1
      ? '上一章「出不去的档案局」：你翻遍了档案局的角落，' + clueN + ' 条线索入袋、破绽 ' + flawN + '/5。监控空窗钉在 21:07–21:15；记忆芯片若失踪或被改，动的是目击存证，不是监控原片。而现在——有人昨晚的记忆和今晚对不上了。'
      : '上一章「心声泄露」：心声层屡屡漏点，篡改点已攒下 ' + state.tamperPts + ' 个，开导让几位当事人卸下了心防。就在这时，热搜后台的灯全部亮起——舆论风暴要来了。';
    return {
      fromAct, text: base,
      gains: ['线索 ' + clueN + ' 条', '破绽 ' + flawN + '/5', fromAct === 1 ? ('知识卡 ' + Object.keys(state.kcards).length + '/10') : ('篡改点 ' + state.tamperPts)]
    };
  }

  /* ---------- 侦探报告 mock 生成（WS 模式消费服务端 detective_report 事件） ---------- */
  function buildReport() {
    const chName = cid => Labels.who(cid);
    const flawN = flawCount();
    const cov = coverage(state.voteEvidence.concat(Object.keys(state.clues)));
    const okN = state.counsel.filter(r => r.ok).length;
    const badges = [];
    if (state.ending === 'kanshan') badges.push('ach_kanshan');
    if (okN >= 4) badges.push('ach_xinqing');
    if (state.ending === 'pollution') badges.push('ach_baolei');
    if (Object.keys(state.clues).length >= 20) badges.push('ach_yugan');
    if (state.antifraud.score >= 3) badges.push('ach_fanzha');
    if (state.photos.filter(x => !x.exposed).length >= 3) badges.push('ach_anfang');
    if (state.hammer && Object.values(state.hammer.tally || {}).reduce((s, x) => s + x, 0) >= 4 && state.hammer.most === 'player:1') badges.push('ach_gongdi');
    const text = '推理评分：truth_node 覆盖 ' + cov.pct + '%；' + Object.keys(state.clues).length + ' 条线索入袋（含破绽 ' + flawN + '/5）；'
      + '开导 ' + okN + ' 人；暗拍 ' + state.photos.length + ' 张（干净 ' + state.photos.filter(x => !x.exposed).length + ' 张）；'
      + '反诈学分 ' + state.antifraud.score + '；赞数余额 ' + state.zans + '。'
      + (state.hammer ? '「最想锤的人」：' + chName(state.hammer.most) + '（锤声一片）。' : '')
      + (state.ending === 'kanshan' ? '高光：你们破的局，正是看山设的局。' : '高光：在热度里保持了（基本）清醒。');
    /* D 求真人格卡：综合茧房 / 证据 / 策反 / 辟谣 生成可分享人格 */
    const ec = evidenceCoverage();
    const broke = (state.cocoon.broken || 0) > 0;
    const flips = Object.values(state.defection || {}).filter(d => d.flipped).length;
    const refOk = Object.values(state.refuted || {}).filter(r => r.ok).length;
    let persona = { name: '信息囚徒', desc: '你被算法投喂裹挟着走完了全程——但至少，你走完了。' };
    if (broke && ec.pct >= 75 && flips >= 1) persona = { name: '求真卫士', desc: '戳破茧房 + 拼出真相 + 策反内鬼，三件套拉满的硬核求真者。' };
    else if (broke && ec.pct >= 50) persona = { name: '破壁调查员', desc: '你主动破茧，并在噪声中拼出了大半真相。' };
    else if (ec.pct >= 75) persona = { name: '证据拼图师', desc: '未必破茧，但证据链拼得漂亮。' };
    else if (refOk >= 3) persona = { name: '辟谣老兵', desc: '谣言在你这翻过车——你没被带节奏带跑。' };
    state.persona = { ...persona, evidencePct: ec.pct, broke, flips, refOk };
    return { report_text: text, badges, achievements: badges.map(id => (M.badgeDefs.find(b => b.id === id) || {}).name).filter(Boolean), persona: state.persona, builtAt: Date.now() };
  }

  /* ---------- 空席 AI：角色在行动，不当玩家自己 ---------- */
  function extractAiChar(actor) {
    const a = String(actor || '');
    if (a.indexOf('player:ai:') === 0) return a.slice(10);
    if (a.indexOf('ai:') === 0) return a.slice(3);
    const m = a.match(/char_\d+/);
    return m ? m[0] : '';
  }
  function isHumanPlayerActor(actor, p) {
    const a = String(actor || '');
    const pid = String((p && p.player_id) || '');
    if (a.indexOf('player:ai:') === 0 || a.indexOf('ai:') === 0) return false;
    if (pid.indexOf('player:ai:') === 0 || pid.indexOf('ai:') === 0) return false;
    if (state.playerId && (a === state.playerId || pid === state.playerId)) return true;
    if (a.indexOf('player:') === 0 || pid.indexOf('player:') === 0) return true;
    return false;
  }
  function isAiAct(evt) {
    const p = evt.payload || {};
    const actor = String(evt.actor || '');
    if (actor.indexOf('player:ai:') === 0 || actor.indexOf('ai:') === 0) return true;
    if (p.booklet_act) return true;
    const ak = p.actor_kind;
    if ((ak === 'npc' || ak === 'ai') && !isHumanPlayerActor(actor, p)) return true;
    return false;
  }
  function aiActWho(evt) {
    const p = evt.payload || {};
    const role = p.booklet_role || extractAiChar(evt.actor) || p.char_id || '';
    return { role: role, name: Labels.who(role) };
  }
  function eventForCurrentPlayer(evt) {
    const p = evt.payload || {};
    const me = state.playerId;
    if (!me) return false;
    return p.player_id === me || p.to === me || evt.actor === me;
  }
  function aiSearchSys(evt) {
    const p = evt.payload || {};
    const who = aiActWho(evt).name;
    const loc = p.location ? Labels.place(p.location) : '';
    const thing = p.keyword || p.name || '';
    const text = (loc || thing)
      ? (who + '去' + (loc || '现场') + '搜了' + (thing || '现场'))
      : (who + '在现场搜证');
    chat('sys', text, { kind: 'ambient', aiAct: true });
  }
  function aiSkillSys(evt) {
    chat('sys', aiActWho(evt).name + '使用了技能', { kind: 'counsel', aiAct: true });
  }

  /* ---------- 事件应用（Mock / WS 共用入口） ---------- */
  const socialMessagesSeen = new Set();
  const aiSpeechQueue = [];
  let aiSpeechBusy = false;
  function drainAiSpeech() {
    if (aiSpeechBusy || !aiSpeechQueue.length) return;
    aiSpeechBusy = true;
    const evt = aiSpeechQueue.shift();
    applyEvent(evt, true);
    // 给气泡/TTS 留出完整的接话间隔，再轮到下一名 AI。
    setTimeout(() => { aiSpeechBusy = false; drainAiSpeech(); }, 1300);
  }
  function applyEvent(evt, fromSpeechQueue) {
    const p = evt.payload || {};
    track('events', String(evt.type || 'unknown'));
    if (p.message_id) {
      const key = String(evt.session_id || state.sessionId) + ':' + p.message_id;
      if (socialMessagesSeen.has(key)) return;
      socialMessagesSeen.add(key);
      if (socialMessagesSeen.size > 2000) socialMessagesSeen.delete(socialMessagesSeen.values().next().value);
    }
    const aiAct = isAiAct(evt);
    if (aiAct && (p.booklet_reason || p.booklet_act || p.meta)) {
      state.aiLastDecision = {
        role: p.booklet_role || p.char_id || evt.actor || '',
        action: p.booklet_act || evt.type,
        reason: p.booklet_reason || p.reason || '',
        provider: p.provider || (p.meta && p.meta.provider) || 'heuristic',
        latency_ms: p.latency_ms || (p.meta && p.meta.latency_ms) || null,
        at: Date.now()
      };
    }
    if (aiAct && evt.type === 'chat' && !fromSpeechQueue) {
      aiSpeechQueue.push(evt);
      drainAiSpeech();
      return;
    }
    const aiMine = eventForCurrentPlayer(evt);
    switch (evt.type) {
      case 'system': {
        if (p.event === 'ai_reply_failed') chat('sys', p.notice, { kind: 'warn' });
        const apForMe = aiAct ? aiMine : (!p.player_id || p.player_id === state.playerId);
        if (p.apDelta !== undefined && apForMe)
          state.ap = Math.max(0, state.ap + p.apDelta);
        if (p.apSet !== undefined && apForMe)
          state.ap = p.apSet;
        if (p.roundSet !== undefined) state.round = p.roundSet;
        if (p.actSet !== undefined) {
          const prevAct = state.act;
          state.act = Math.min(3, Math.max(1, Number(p.actSet) || 1));
          banner(`第 ${'一二三'[state.act - 1]}幕开启`, 'act'); pushDmaku(M.danmaku.start, 'sys');
          if (state.act >= 3) grantFinaleFlaw();
          /* V4 综艺流程：幕切换插入转场全屏页（act_t2/act_t3，2.5s 自动过或点击跳过） */
          if (state.showtime) state.showtime.cut = { act: p.actSet };
          /* V5 章节独占式：切章后视图归位大圆桌（章舞台主体）+ 章首前情提要
           * （服务端 memory_doc 摘要经 system.recap 事件到达时覆盖本地兜底） */
          state.view = 'chat';
          state.recap = p.recap || mockRecap(prevAct, p.actSet);
          if (state.act === 2) state.bookletForced = 'B';
          if (state.act === 3) state.bookletForced = 'C';
          Store.hydrateBooklet();
        }
        if (p.recap !== undefined && p.actSet === undefined) state.recap = p.recap;  // V5：独立 recap 事件（G4 memory_doc）
        if (p.heartUnlock) { state.heartUnlocked[p.heartUnlock] = true; toast(Labels.who(p.heartUnlock) + ' 的心声层已解锁', 'good'); }
        if (p.toast) toast(p.toast, p.kind);
        else if (p.event === 'error' && p.notice) toast(p.notice, 'warn');
        else         if (p.notice && ['bad_location', 'vote_rejected', 'advance_blocked', 'locked',
          'pin_rejected', 'cocoon_rejected', 'defect_rejected', 'card_not_held',
          'bad_skill', 'bad_target', 'search_empty_result', 'judge_line_rejected'].indexOf(p.event) >= 0)
          toast(p.notice, 'warn');
        if (Array.isArray(p.seats)) state.partySeats = p.seats;
        if (p.banner) banner(p.banner, p.cls);
        applyV31SystemEvent(p);
        break;
      }
      case 'danmaku': pushDmaku(p.items || [], evt.actor === 'dm' ? 'dm' : ''); break;
      case 'search_result':
        if (!evt.actor || !String(evt.actor).startsWith('player:') || evt.actor === state.playerId) {
          state.lastSearchResult = evt;
        }
        if (p.booklet_act) {
          aiSearchSys(evt);
          break;
        }
        if (!p.hit) {
          playSfx('miss');
          const locName = Labels.place(p.location);
          chat('sys', `【搜证 · ${locName}】${p.ambient || '一无所获。'}`, { kind: 'ambient' });
          pushDmaku(p.danmaku || M.danmaku.miss, 'gray');
        }
        break;
      case 'clue_gained': {
        if (p.booklet_act && !aiMine) {
          aiSearchSys(evt);
          break;
        }
        if (aiAct && !aiMine && !p.booklet_act) break;
        const uid = uiClueId(p.clue_id);
        const prev = state.clues[uid] || state.clues[p.clue_id] || {};
        state.clues[uid] = Object.assign({}, prev, {
          at: prev.at || state.round,
          engineId: p.clue_id,
          name: p.name || prev.name,
          text: p.text || prev.text,
          tier: p.tier || prev.tier,
          tags: p.tags || prev.tags,
          linked: p.linked || p.linked_truth_nodes || prev.linked,
          flaw_id: p.flaw_id || prev.flaw_id
        });
        if (p.clue_id !== uid) delete state.clues[p.clue_id];
        noteSearchTags(p.tags || []);
        if (p.flaw_id && !state.flaws[p.flaw_id]) {
          state.flaws[p.flaw_id] = { at: state.round };
          const meta = M.flaws.find(f => f.id === p.flaw_id);
          banner(`看山的破绽 ${flawCount()}/5 —— ${p.name}`, 'flaw');
          if (flawCount() >= 5) { banner('破绽 5/5：圆桌指认新增「指认：DM」选项！', 'flaw'); pushDmaku(['五连破绽！！', '指认 DM 走起'], 'sys'); }
          if (meta) toast('破绽笔记已更新：' + meta.hint, 'flaw');
        }
        chat('sys', `【线索入手 · ${p.name}】${p.text}`, { kind: p.tier === 'boss_flaw' ? 'flaw' : 'clue', tier: p.tier, clue_id: p.clue_id });
        pushDmaku(p.danmaku || M.danmaku.hit, p.tier === 'boss_flaw' ? 'sys' : '');
        playSfx('hit');
        synthCheck();
        recountSalt();
        break;
      }
      case 'chat': {
        /* npc/dm 新气泡经 chat() 触发 Voice.speak；me/peer 不播。心声走 actor_kind=heart → npc+heart。 */
        if (aiAct) {
          const who = aiActWho(evt);
          const cid = who.role || String(p.char_id || '').replace(/^npc:/, '');
          const emptySeat = !!(p.booklet_act
            || String(evt.actor || '').indexOf('player:ai:') === 0
            || String(evt.actor || '').indexOf('ai:') === 0);
          chat('npc', p.text, {
            char_id: cid, name: who.name, aiAct: emptySeat, wave: !!p.wave,
            heart: p.actor_kind === 'heart',
            whisper: !!p.whisper, to: p.to, ai_provider: p.ai_provider
          });
          break;
        }
        const pid = p.player_id || evt.actor || '';
        const mine = pid === state.playerId || (!pid && p.actor_kind === 'player') || (pid === 'player:1' && !state.playerId);
        const cid = p.char_id || String(p.target || evt.actor || '').replace(/^npc:/, '');
        if (p.whisper) {
          chat(mine ? 'me' : 'peer', p.text, {
            char_id: cid, player_id: pid, name: p.player_name || (mine ? '我' : Labels.who(pid)),
            whisper: true, to: p.to, from: pid
          });
          break;
        }
        if (p.actor_kind === 'player') {
          chat(mine ? 'me' : 'peer', p.text, { char_id: cid, player_id: pid, name: p.player_name || (mine ? '我' : Labels.who(pid)) });
        } else if (p.actor_kind === 'heart') {
          chat('npc', p.text, { char_id: cid, heart: true });
        } else {
          const kind = p.actor_kind === 'dm' || cid === 'dm' || String(evt.actor || '').indexOf('dm') === 0 ? 'dm' : 'npc';
          chat(kind, p.text, { char_id: cid || (kind === 'dm' ? 'dm' : ''), ai_provider: p.ai_provider });
          if (kind === 'dm' && /^[「]?叮/.test(String(p.text || ''))) playSfx('ding');
        }
        break;
      }
      case 'memory_unlock': {
        const cid = p.char_id || String(p.owner || '').replace(/^npc:/, '');
        const version = p.version || p.unlocked_version;
        if (!cid || !version) break;
        state.memVer[cid] = version;
        if (p.source === 'engine' && Array.isArray(p.blocks)) state.liveMemories[cid] = { ...p, char_id: cid, version };
        if (p.heart_unlocked !== undefined) state.heartUnlocked[cid] = p.heart_unlocked;
        if (p.tamper_available !== undefined) state.tamperPts = p.tamper_available;
        if ((p.diff || []).some(d => d.tamper)) state.tamperPts += 1;  // V31：篡改点计数（拼图对质货币）
        chat('sys', `【记忆修复 · ${Labels.who(cid)} → 第 ${version} 层】${(p.diff || []).map(d => d.change).join('；') || '记忆档案已更新，请对照口供与心声。'}`, { kind: 'memory' });
        pushDmaku(p.danmaku || M.danmaku.hit, 'sys');
        break;
      }
      case 'counsel_result': {
        if (p.source === 'engine') {
          p.char_id = p.char_id || String(p.target || '').replace(/^npc:/, '');
          p.kc_id = p.kc_id || p.card;
          p.ok = p.matched;
          p.lines = p.lines || (p.transcript_hint ? [p.transcript_hint] : []);
        }
        if (p.booklet_act || aiAct) {
          if (p.booklet_act) aiSkillSys(evt);
          break;
        }
        state.counsel.push({ char_id: p.char_id, kc_id: p.kc_id, ok: p.ok, reward: p.reward, lines: p.lines, at: state.round });
        playSfx(p.ok ? 'heal' : 'fail');
        chat('sys', `【心晴开导 · ${Labels.who(p.char_id)} × 《${(kcById(p.kc_id) || {}).title || '知识卡'}》】${p.ok ? '匹配成功' : '匹配失败'}`, { kind: p.ok ? 'counsel' : 'warn' });
        (p.lines || []).forEach(l => chat('npc', l, { char_id: p.char_id, heart: l.startsWith('（心声') }));
        pushDmaku(p.danmaku, p.ok ? 'sys' : 'gray');
        if (p.ok) {
          const r = p.reward;
          const dbl = !!p.doubled;  // V31：急诊抢救双倍收益
          if (r === 'heart') state.heartUnlocked[p.char_id] = true;
          if (r === 'salt') {
            const need = dbl ? 2 : 1;
            let granted = 0;
            saltIdList().forEach(id => {
              if (granted >= need) return;
              if (!state.clues[id]) { state.clues[id] = { at: state.round }; granted++; }
            });
            recountSalt();
            toast('盐言彩蛋碎片 +' + granted + '（' + state.salt + '/5）' + (dbl ? '【抢救双倍】' : ''), 'gold');
          }
          if (r === 'memory') state.heartUnlocked[p.char_id] = true;
          if (r === 'buff') { state.apMax += 1; state.ap += dbl ? 2 : 1; toast('全队 buff「合群又独立」：行动点上限 +1' + (dbl ? '【抢救双倍 +2】' : ''), 'good'); }
          if (r === 'chapter') toast('沉底君的第 7 章答案重新上架——隐藏真结局钥匙 +1', 'gold');
          if (r && r.startsWith('clue:')) { const c = clueById(r.split(':')[1]); if (c && !state.clues[c.id]) { state.clues[c.id] = { at: state.round }; chat('sys', `【开导收益 · ${c.name}】${c.fact}`, { kind: 'clue', tier: c.tier }); synthCheck(); } }
          if (r === 'flaw:flavor_3') { /* clue_gained 由下面 flaw 分支处理 */ }
        }
        if (p.ok && p.reward === 'flaw:flavor_3') {
          const c = clueById('flavor_3');
          if (!state.clues[c.id]) { state.clues[c.id] = { at: state.round }; state.memVer['char_05'] = Math.max(state.memVer['char_05'], 2); state.heartUnlocked['char_05'] = true; state.flaws['flavor_3'] = { at: state.round }; banner(`看山的破绽 ${flawCount()}/5 —— 主人级签名`, 'flaw'); chat('sys', `【线索入手 · ${c.name}】${c.fact} ${c.flavor}`, { kind: 'flaw', tier: 'boss_flaw' }); }
        }
        break;
      }
      case 'hotfeed_refresh':
        if (Array.isArray(p.panel)) {
          state.hotfeedPanel = p.panel.map(post => Object.assign({}, post, {
            delta: post.heat_delta ?? post.delta ?? 0,
            tag: post.topic_tag ?? post.tag ?? '',
            fake: post.is_fake ?? post.fake ?? false,
            pinned: post._pinned ?? post.pinned ?? false
          }));
          state.posts = Object.fromEntries(state.hotfeedPanel.map(post => [post.id, post]));
        }
        state.hotfeedSignals = p.signals || null;
        if (Number.isFinite(p.heat)) state.heat = p.heat;
        banner('热搜刷新：新一轮话题已上线', 'feed');
        pushDmaku(['热搜换血，谣言上新', '冲浪时间到'], 'sys');
        break;
      case 'faction_skill': {
        if (p.booklet_act || aiAct) {
          if (p.booklet_act) aiSkillSys(evt);
          break;
        }
        if (p.kind === 'draw_card') { playSfx('page'); state.kcards[p.kc_id] = { at: state.round }; toast('抽中知识卡《' + kcById(p.kc_id).title + '》· ' + kcById(p.kc_id).author, 'good'); pushDmaku(p.danmaku, 'sys'); }
        else if (p.kind === 'refute') {
          state.refuted[p.post_id] = { ok: p.ok, kc_id: p.kc_id };
          state.heat = Math.max(0, Math.min(100, state.heat + (p.ok ? -p.delta : p.delta)));
          chat('sys', `【辟谣 ${p.ok ? '成功' : '失败'}】${p.ok ? '知识卡 tag 匹配，' : 'tag 不匹配，'}热度 ${p.ok ? '-' : '+'}${p.delta} → 当前 ${state.heat}`, { kind: p.ok ? 'counsel' : 'warn' });
          if (p.ok && p.clue) { const c = p.clue; if (!state.clues[c.clue_id]) { state.clues[c.clue_id] = { at: state.round }; chat('sys', `【辟谣解锁真线索 · ${c.name}】${c.text}`, { kind: 'clue', tier: c.tier }); synthCheck(); } }
          playSfx(p.ok ? 'heal' : 'fail');
          pushDmaku(p.danmaku, p.ok ? 'sys' : 'gray');
          // V31 P2：辟谣成功 30% 触发反诈小剧场（每局至多 2 次）
          if (p.ok && !state.demo && state.antifraud.count < 2 && Math.random() < 0.34) {
            state.antifraud.count += 1;
            state.antifraud.active = true;
            state.antifraud.act = 0;
            state.antifraud.answers = [];
          }
        }
        else if (p.kind === 'buy_hot') { playSfx('heat'); state.heat = Math.min(100, state.heat + p.delta); state.buyHeats = (state.buyHeats || 0) + 1; chat('sys', `【买热搜】${p.title} 热度 +${p.delta} → ${state.heat}（这操作本身就很值得辟谣）`, { kind: 'warn' }); pushDmaku(p.danmaku, 'gray'); }
        else if (p.kind === 'cross_check') {
          const degradeTag = p.degraded ? '（本地演示判定）' : '';
          chat('sys', p.exposed ? `【交叉验证】伪造线索《${clueById(p.clue_id).name}》被拆穿——与《${p.real_name}》矛盾实锤，自动标记为伪证。${degradeTag}` : `【交叉验证】暂时拿不出实锤，先标记存疑。${degradeTag}`, { kind: p.exposed ? 'clue' : 'warn' });
          if (p.exposed) state.exposedFakes[p.clue_id] = true;
          pushDmaku(p.danmaku, 'sys');
        }
        break;
      }
      case 'vote':
        if (p.ending || p.outcome || p.tie) {
          state.voteResult = Object.assign({
            evidence: p.evidence || [], coverage: p.coverage || { pct: 0 }
          }, p);
          if (p.tie) {
            state.voteResult.tie = true;
            state.ending = state.ending || 'hung';
          }
        } else {
          toast('指认已记录 ' + (p.voters || 0) + '/' + (p.needed || '?'), 'ok');
        }
        state.busy = false;
        if (p.ending || p.outcome) playSfx('hammer');
        if (state.showtime && (p.ending || p.outcome)) state.showtime.step = 'accuse';
        break;
      case 'ending':
        /* 引擎 outcome 与 mock ending_id 共用 ENDING_TO_UI */
        state.ended = true; state.ending = p.ending_id || ENDING_TO_UI[p.outcome] || p.outcome || null; state.view = 'ending';
        if (state.showtime) state.showtime.step = 'reveal';  // V4 综艺流程：揭晓复盘环节
        pushDmaku(M.danmaku.vote.concat(M.danmaku.boss), 'sys');
        if (p.profile) {
          state.truthProfile = p.profile;
        } else if (!state.truthProfile) {
          state.truthProfile = buildTruthProfile({
            accused_dm: p.accused === 'dm' || state.voteTarget === 'dm',
            ending: state.ending
          });
        }
        if (!state.report) state.report = buildReport();  // mock 报告；WS 模式由服务端 detective_report 事件覆盖
        if (state.report && state.truthProfile) state.report.profile = state.truthProfile;
        break;
      case 'achievement_unlocked': {
        playSfx('achievement');
        const a = p.achievement || {};
        const name = a.name || a.show || '成就解锁';
        const def = (a.id && M.badgeDefs.find(b => b.id === a.id)) || null;
        banner('🏆 成就解锁：' + (def ? def.name : name), 'gold');
        if (def && def.desc) toast(def.name + '——' + def.desc, 'gold');
        pushDmaku(['成就 Get！', '截图发给朋友'], 'sys');
        break;
      }

      /* ---- 创新冲刺事件（Mock 顶层类型；WS 走 system.event，见 applyV31） ---- */
      case 'cocoon_break':
        applyCocoonBreak();
        break;
      case 'evidence_pin':
        applyEvidencePin(p);
        break;
      case 'defect':
        applyDefect(p);
        break;
    }
  }

  /* ---------- 存档 ---------- */
  function save() {
    try {
      const snap = JSON.parse(JSON.stringify({
        act: state.act, round: state.round, ap: state.ap, apMax: state.apMax, heat: state.heat,
        flaws: state.flaws, clues: state.clues, kcards: state.kcards, memVer: state.memVer,
        heartUnlocked: state.heartUnlocked, counsel: state.counsel, refuted: state.refuted,
        synth: state.synth, posts: state.posts, hotfeedPanel: state.hotfeedPanel, hotfeedSignals: state.hotfeedSignals, salt: state.salt, ended: state.ending ? true : false,
        ending: state.ending, searched: state.searched, demo: state.demo, bossSeen: state.bossSeen,
        /* V31 增量 */
        zans: state.zans, glitchFree: state.glitchFree, glitchPerAct: state.glitchPerAct,
        tamperPts: state.tamperPts, photos: state.photos, er: state.er, erLimit: state.erLimit,
        bet: state.bet, betStreak: state.betStreak, headline: state.headline,
        dossier: state.dossier, report: state.report, hammer: state.hammer,
        fish: state.fish,
        mode: state.mode, roomCode: state.roomCode, sessionId: state.sessionId, playerId: state.playerId,
        antifraud: { count: state.antifraud.count, score: state.antifraud.score, active: false, act: 0, answers: [] },
        pollution: state.pollution, echo: state.echo, debate: state.debate,
        truthProfile: state.truthProfile, buyHeats: state.buyHeats,
        searchBias: state.searchBias, cocoon: state.cocoon,
        evidenceLinks: state.evidenceLinks, defection: state.defection,
        playMode: state.playMode, skipIce: state.skipIce, dailyTopic: state.dailyTopic,
        stage: state.stage,
        quiz: { score: state.quiz.score, asked: state.quiz.asked, done: state.quiz.done, seen: state.quiz.seen, open: false, q: '', options: [], last: null, idx: 0 },
        radio: { requestLeft: state.radio.requestLeft, log: state.radio.log, text: state.radio.text, open: false },
        officeOpen: state.officeOpen, flipped: state.flipped,
        v587Exposed: state.v587Exposed, v587: state.v587,
        partyChar: state.partyChar, playerBook: state.playerBook, bookletRole: state.bookletRole,
        scenarioId: state.scenarioId, studioBooks: state.studioBooks, studioMeta: state.studioMeta,
        firstVote: { open: false, poll_id: state.firstVote.poll_id, pick: state.firstVote.pick, done: state.firstVote.done, tally: state.firstVote.tally }
      }));
      localStorage.setItem(SAVE_KEY, JSON.stringify(snap));
    } catch (e) { /* 隐身模式等忽略 */ }
  }
  function load() {
    try {
      const raw = localStorage.getItem(SAVE_KEY); if (!raw) return;
      const s = JSON.parse(raw);
      Object.keys(s).forEach(k => { if (k in state) state[k] = s[k]; });
      if (state.mode !== 'party') {
        state.roomCode = '';
        state.shareUrl = '';
        state.isHost = false;
        state.roomFull = null;
      }
      if (!state.stage) {
        if (state.skipIce || state.playMode === 'daily' || state.playMode === 'quick') state.stage = 'investigate';
        else if (state.act > 1 || state.round > 1 || Object.keys(state.searched || {}).length) state.stage = 'investigate';
        else state.stage = 'break_ice';
      }
      migrateEngineClues();
      try {
        if (!new URLSearchParams(location.search).get('room')) state.phase = 'menu';
      } catch (e2) { state.phase = 'menu'; }
    } catch (e) { }
  }
  function reset() { localStorage.removeItem(SAVE_KEY); state.phase = 'cover'; location.reload(); }
  // 回访玩家：保留存档但一律先见主菜单（菜单上提供「继续上次对局」入口）
  state.hasSave = !!localStorage.getItem(SAVE_KEY);
  watch(state, save, { deep: true });

  /* ---------- Studio 水合（只替换 MOCK 子集，保留看山壳） ---------- */
  let _origDm = null;
  function applyStudioPack(pack) {
    if (!pack) return;
    if (!_origDm) _origDm = M.chars.find(c => c.id === 'dm') ? JSON.parse(JSON.stringify(M.chars.find(c => c.id === 'dm'))) : null;
    M.locations = (pack.locations || []).slice();
    M.clues = (pack.clues || []).slice();
    M.kcards = (pack.kcards || []).slice();
    M.posts = (pack.posts || []).slice();
    M.memories = (function (src) {
      if (!src) return {};
      const out = JSON.parse(JSON.stringify(src));
      Object.keys(out).forEach(k => {
        (Array.isArray(out[k]) ? out[k] : []).forEach(v => {
          if (v && Array.isArray(v.blocks)) v.blocks = v.blocks.filter(b => !b || b.layer !== 'heart');
        });
      });
      return out;
    })(pack.memories);
    M.truthNodes = (pack.truthNodes || []).slice();
    M.chars = (pack.characters || []).map(c => {
      const row = { ...c };
      delete row.faction;
      delete row.secret;
      return row;
    });
    const dmSrc = pack.dm || _origDm;
    if (dmSrc) {
      M.chars.push({
        id: 'dm',
        name: dmSrc.name || '叮——系统提示音',
        archetype: '档案局系统（自称）',
        avatar: dmSrc.avatar || '/assets/images/bust/dm_kanshan_holo.png',
        heartache: null,
        bio: '档案局广播系统，语气热情得可疑。',
        speech: '叮——',
        goal: '维持秩序（自称）',
        replies: dmSrc.replies || ['叮——检测到发言，已被记录进本局档案。', '叮——大门已锁定。不出真相，不出此门。', '叮——系统建议：先对话，再搜证。'],
        heartLine: null
      });
    }
    state.studioMeta = {
      title: pack.title || '',
      hook: pack.hook || '',
      summary: pack.summary || '',
      logline: pack.logline || pack.summary || '',
      genre: pack.genre || '',
      acts: pack.acts || []
    };
    state.scenarioId = pack.id || '';
    state.studioModules = pack.modules || {
      hotfeed: true, memory: true, counsel: true, kcards: true,
      inner_boss: false, comedy_search: true, bet: true, headline: true,
      stealth: true, puzzle: true, antifraud: true, evidence: true, pollution: true
    };
    state.studioMinis = Array.isArray(pack.minis) ? pack.minis.slice() : null;
    state.studioVibe = pack.vibe || '';
    state.studioType = pack.pack_type || '';
    state.studioCamp = pack.camp || null;
    state.studioBooks = (pack.books || []).slice();
  }

  function resetPlayForStudio() {
    state.act = 1; state.round = 1; state.ap = 3; state.apMax = 3; state.heat = 35;
    state.flaws = {}; state.clues = {}; state.kcards = {}; state.heartUnlocked = {};
    state.memVer = {};
    M.chars.filter(c => c.id !== 'dm').forEach(c => { state.memVer[c.id] = 1; });
    state.counsel = []; state.refuted = {}; state.synth = []; state.posts = {};
    state.hotfeedPanel = null; state.hotfeedSignals = null;
    state.lastSearchResult = null;
    state.exposedFakes = {}; state.salt = 0; state.chat = []; state.currentNpc = 'dm';
    state.ended = false; state.ending = null; state.voteResult = null;
    state.pollution = { case: null, result: null, ammo: 0, earned: 0, done: {}, summary: null };
    state.echo = { log: [], seq: 0, challenge: null, result: null, defended: false, tease: 0 };
    state.debate = { open: false, stance: 'open', score: 0, need: 4, text: '', rounds: [], convinced: false };
    state.truthProfile = null; state.buyHeats = 0;
    state.searchBias = {}; state.cocoon = { active: false, broken: 0, revealed: 0 };
    state.evidenceLinks = []; state.defection = {};
    state.searched = {}; state.busy = false; state.demo = false;
    state.report = null; state.persona = null;
    state.voteTarget = null; state.voteEvidence = []; state.voteResult = null;
    state.antifraud = { count: 0, score: 0, active: false, act: 0, answers: [] };
    state.studioNeedAdvance = true;
    state.stage = 'break_ice';
    state.dmBookRead = false;
    state.dmMiniSeen = {};
    if (state.showtime) state.showtime = { step: 'case_file', cut: null };
    state.recap = null; state.elevator = null;
    state.quiz = { open: false, idx: 0, q: '', options: [], score: 0, asked: 0, done: false, last: null, seen: [] };
    state.radio = { open: false, text: '', log: [], requestLeft: 3 };
    state.firstVote = { open: false, poll_id: '', pick: '', done: false, tally: null };
    state.skipIce = false;
    state.officeOpen = false; state.office = { open: false, tries: 0 };
    state.flipped = {}; state.v587Exposed = false; state.v587 = { exposed: false };
  }

  /* ---------- 对外 API ---------- */
  function demoRailSteps() {
    const polDone = Object.keys(state.pollution.done || {}).length;
    const echoN = (state.echo.log || []).length;
    return [
      { id: 'pollution', label: '对照改写', hint: '圈出 3 处植入', done: polDone > 0 || (state.pollution.ammo || 0) > 0 || (state.pollution.earned || 0) > 0, view: 'pollution', act: 2 },
      { id: 'speak', label: '圆桌留档', hint: '说两句会被归档的话', done: echoN >= 2, view: 'chat', act: 2 },
      { id: 'echo', label: '回声自证', hint: '指出矛盾或证明一致', done: !!(state.echo.result || state.echo.defended), view: 'vote', act: 3 },
      { id: 'debate', label: '说服法官', hint: '点选证据陈词两轮', done: !!(state.debate.convinced || ((state.debate.rounds || []).length)), view: 'vote', act: 3 },
      { id: 'profile', label: '求真画像', hint: '终局五维雷达', done: !!state.truthProfile, view: state.ended ? 'ending' : 'review', act: 3 }
    ];
  }
  function startJudgeLine() {
    if (state.phase !== 'play') {
      toast('先进局后再开评委线', 'warn');
      return false;
    }
    state.demo = true;
    if (state.act < 2) state.act = 2;
    if (state.showtime) {
      state.showtime.cut = null;
      state.showtime.step = 'act';
    }
    state.recap = null;
    state.elevator = null;
    if (state.netKind !== 'ws' && state.echo.log.length < 2) {
      state.echo.seq += 1;
      state.echo.log.push({ idx: state.echo.seq, actor: 'player:1', text: '我相信流量酱清白', target: 'char_03', round: state.round });
      state.echo.seq += 1;
      state.echo.log.push({ idx: state.echo.seq, actor: 'player:1', text: '我怀疑流量酱在撒谎', target: 'char_03', round: state.round });
    }
    if (!state.kcards['kc_01']) state.kcards['kc_01'] = { at: state.round };
    if (state.netKind === 'ws') {
      Store.send('skill', { kind: 'judge_line', skill: 'judge_line' });
    } else {
      Engine.judge_line({}, (type, pl) => applyEvent({ type: type, payload: pl, actor: 'sys' }));
    }
    state.view = 'pollution';
    banner('评委线：对照 → 回声 → 法官 → 画像（约 20 分钟）', 'gold');
    toast(state.netKind === 'ws' ? '联机局评委线已提交引擎：发三张核心线索并钉上拼图' : '演示门控已开。按顶栏五步走完主创新', 'good');
    return true;
  }
  function ensureJudgeProfile() {
    if (state.ended && state.truthProfile) {
      state.view = 'ending';
      return true;
    }
    if (state.netKind === 'ws') {
      toast('联机局请在圆桌提交指认后查看画像', 'warn');
      state.view = 'vote';
      return false;
    }
    if (state.act < 3) state.act = 3;
    grantFinaleFlaw();
    if (!state.clues['clue_001']) state.clues['clue_001'] = { at: state.round };
    const ids = Object.keys(state.clues);
    if (ids.length < 2) {
      const extra = finaleFlawClue();
      if (extra && !state.clues[extra.id]) state.clues[extra.id] = { at: state.round };
    }
    const evidence = Object.keys(state.clues).slice(0, 2);
    if (evidence.length < 2) {
      toast('还缺证据卡，先走完对照或搜一条线索', 'warn');
      state.view = 'vote';
      return false;
    }
    state.voteTarget = 'char_01';
    state.voteEvidence = evidence;
    Engine.vote({ target: 'char_01', evidence: evidence }, function (type, pl) {
      applyEvent({ type: type, payload: pl, actor: 'player:1' });
    });
    return !!state.truthProfile;
  }
  function goDemoRail(stepId) {
    const step = demoRailSteps().find(s => s.id === stepId);
    if (!step) return;
    state.demo = true;
    if (step.act && state.act < step.act) state.act = step.act;
    if (state.act >= 3) grantFinaleFlaw();
    if (stepId === 'profile') {
      ensureJudgeProfile();
      return;
    }
    state.view = step.view;
  }

  const Store = {
    openStudio() { state.phase = 'studio'; state.studioJob = null; state.studioId = ''; },
    closeStudio() { state.phase = 'menu'; },
    applyStudioPack,
    async playStudio(id) {
      id = String(id || '').trim();
      if (!id) { toast('还没有选定要开的本', 'warn'); return false; }
      try {
        const r = await fetch('/api/studio/' + encodeURIComponent(id) + '/public');
        if (!r.ok) {
          if (!window.STUDIO_FALLBACK) {
            toast('请先启动本机服务后再试', 'warn');
            return false;
          }
        }
        let pack = null;
        if (r.ok) {
          const j = await r.json();
          pack = j.pack;
          if (!j.ok || !pack || !pack.playable) {
            toast('闸门未通过或本不可玩', 'warn');
            return false;
          }
        }
        if (!pack && window.STUDIO_FALLBACK) pack = window.STUDIO_FALLBACK(id);
        if (!pack) return false;
        applyStudioPack(pack);
        resetPlayForStudio();
        state.playerBook = null;
        state.bookOpen = false;
        const pid = (window.myPlayerId ? window.myPlayerId() : 'player:1');
        try {
          const sr = await fetch('/api/session', {
            method: 'POST',
            headers: this.llmHeaders(),
            body: JSON.stringify({ mode: 'quick', scenario_id: id, player_id: pid })
          });
          if (sr.ok) {
            const sj = await sr.json();
            if (sj.ok && sj.session) {
              state.sessionId = sj.session.session_id;
              state.playerId = pid;
              const wsUrl = partyWsUrl(sj.session.session_id, pid, false);
              await Store.connectParty(wsUrl);
            }
          } else {
            toast('会话创建失败，仍可本地试玩水合数据', 'warn');
          }
        } catch (e) {
          toast('会话/WS 未接通，仍可本地试玩水合数据', 'warn');
        }
        if ((state.studioBooks || []).length) {
          state.playerBook = null;
          state.bookOpen = false;
          state.phase = 'seat';
          if (window.UX && window.UX.markOnboarded) window.UX.markOnboarded();
          save();
          return true;
        }
        state.phase = 'play';
        state.view = 'chat';
        if (window.UX && window.UX.markOnboarded) window.UX.markOnboarded();
        chat('dm', pack.hook || state.studioMeta.hook || '叮——新本已装载，请先圆桌破冰。', {});
        chat('sys', '【快本 · ' + (state.studioMeta.title || '未命名本') + '】第一幕破冰：只许圆桌对话，点「开始搜证」后再进地图。', { kind: 'counsel' });
        save();
        return true;
      } catch (e) {
        toast('请先启动本机服务后再试', 'warn');
        return false;
      }
    },
    finishStudioBreakIce() {
      if (!state.studioNeedAdvance) return;
      Store.send('advance', {});
      state.studioNeedAdvance = false;
      state.stage = 'investigate';
      toast('破冰结束，可以进入现场搜证了', 'good');
    },
    startPrologue() {
      // 从剧本入口开始即视为新局：清除旧的本地快照，避免菜单继续提示恢复上局。
      try { localStorage.removeItem(SAVE_KEY); } catch (e) { }
      state.hasSave = false;
      if ((state.studioBooks || []).length && !state.playerBook) {
        toast('先领取一本故事本', 'warn');
        return;
      }
      if (!state.partyChar) {
        try { state.partyChar = sessionStorage.getItem('party_char') || ''; } catch (e) { }
      }
      if ((state.mode === 'party' || state.playMode === 'main') && !state.partyChar) {
        toast('先点一名角色，领取今晚身份', 'warn');
        return;
      }
      if (state.partyChar) this.applyLocalSeat(state.partyChar);
      if (state.mode !== 'party' && state.playMode === 'main') {
        this.ensureSoloSession();
      }
      state.phase = 'prologue';
      state.prologueStep = 0;
    },
    applyLocalSeat(id) {
      id = String(id || '').trim();
      if (!id) return;
      state.partyChar = id;
      state.bookletRole = id;
      try { sessionStorage.setItem('party_char', id); } catch (e) { }
      const ch = charById(id);
      state.myFactionHint = ch
        ? ('你领取了「' + ch.name + '」。先读闭卷，立场只在终局揭晓。')
        : '先读你的闭卷。立场只在终局揭晓。';
    },
    liveSession() {
      const sid = state.sessionId;
      return !!(sid && sid !== '-' && state.netKind === 'ws' && String(sid).indexOf('mock_') !== 0);
    },
    llmHeaders() {
      const hdrs = { 'Content-Type': 'application/json' };
      let apiCfg = {};
      try { apiCfg = JSON.parse(localStorage.getItem('kanshan_api') || '{}'); } catch (e) { }
      if (apiCfg.llmBase) hdrs['X-LLM-BASE'] = apiCfg.llmBase;
      if (apiCfg.llmKey) hdrs['X-LLM-KEY'] = apiCfg.llmKey;
      if (apiCfg.llmModel) hdrs['X-LLM-MODEL'] = apiCfg.llmModel;
      if (apiCfg.zhihuSecret) hdrs['X-ZHIHU-SECRET'] = apiCfg.zhihuSecret;
      return hdrs;
    },
    async requestAiWave(opts) {
      const retries = (opts && opts.retries) || 0;
      const force = !!(opts && opts.force);
      if (state.demo) return;
      if (!this.liveSession()) {
        if (retries > 0) {
          const self = this;
          setTimeout(function () { self.requestAiWave({ retries: retries - 1, force: force }); }, 450);
        }
        return;
      }
      const sid = state.sessionId;
      if (!force && state.aiWaveKicked === sid) return;
      const pid = state.playerId || (window.myPlayerId ? window.myPlayerId() : 'player:1');
      try {
        const r = await fetch('/api/session/' + encodeURIComponent(sid) + '/ai_wave', {
          method: 'POST', headers: this.llmHeaders(),
          body: JSON.stringify({ player_id: pid })
        });
        if (!r.ok) {
          if (retries > 0) {
            const self = this;
            setTimeout(function () { self.requestAiWave({ retries: retries - 1, force: force }); }, 450);
          }
          return;
        }
        state.aiWaveKicked = sid;
        const j = await r.json();
        /* WS 在线时事件已由通道广播，避免双份气泡 */
        if (state.netKind !== 'ws') {
          (j.events || []).forEach(evt => applyEvent(evt));
        }
        const acted = j.acted;
        if (acted && acted.length) toast('空席已按坐席开打', 'ok');
      } catch (e) {
        if (retries > 0) {
          const self = this;
          setTimeout(function () { self.requestAiWave({ retries: retries - 1, force: force }); }, 450);
        }
      }
    },
    async ensureSoloSession() {
      if (this._soloP) return this._soloP;
      const self = this;
      this._soloP = this._ensureSoloSessionBody().finally(function () { self._soloP = null; });
      return this._soloP;
    },
    async _ensureSoloSessionBody() {
      const pid = state.playerId || (window.myPlayerId ? window.myPlayerId() : 'player:1');
      if (this.liveSession()) {
        if (!state.partyChar) return true;
        try {
          await fetch('/api/session/' + encodeURIComponent(state.sessionId) + '/claim', {
            method: 'POST', headers: this.llmHeaders(),
            body: JSON.stringify({ player_id: pid, char_id: state.partyChar })
          });
        } catch (e) { /* 本地闭卷仍可用 */ }
        return true;
      }
      try {
        const sr = await fetch('/api/session', {
          method: 'POST', headers: this.llmHeaders(),
          body: JSON.stringify({ mode: 'main', player_id: pid, char_id: state.partyChar || undefined })
        });
        if (!sr.ok) return false;
        const sj = await sr.json();
        if (sj.ok && sj.session) {
          state.sessionId = sj.session.session_id;
          state.playerId = pid;
          const wsUrl = partyWsUrl(sj.session.session_id, pid, false);
          await this.connectParty(wsUrl);
          return true;
        }
      } catch (e) { }
      return false;
    },
    leaveToMenu() {
      try { if (window.VoiceRTC && window.VoiceRTC.leave) window.VoiceRTC.leave(); } catch (e) { }
      if (state.showtime) {
        state.showtime.cut = null;
        if (state.showtime.step === 'case_file') state.showtime.step = 'act';
      }
      state.recap = null;
      state.elevator = null;
      save();
      state.hasSave = true;
      state.phase = 'menu';
      toast(state.mode === 'party' && state.roomCode
        ? ('进度已保存。主菜单「继续上次对局」可回到房间 ' + state.roomCode)
        : '进度已保存。主菜单点「继续上次对局」可回来', 'ok');
      return true;
    },
    resumeGame() {
      load();
      if (state.mode === 'party' && state.roomCode) {
        this.joinRoom(state.roomCode).then(ok => {
          if (ok) { state.phase = 'play'; state.view = 'chat'; if (state.showtime) state.showtime.step = 'act'; }
        });
        return;
      }
      state.phase = 'play';
      state.view = 'chat';
    },
    clearPartySession() {
      try { if (window.VoiceRTC && window.VoiceRTC.leave) window.VoiceRTC.leave(); } catch (e) { }
      state.roomCode = '';
      state.shareUrl = '';
      state.isHost = false;
      state.isSpectator = false;
      state.roomFull = null;
      state.lanBase = '';
      try {
        sessionStorage.removeItem('party_ticket');
        sessionStorage.removeItem('party_ws');
        sessionStorage.removeItem('party_char');
      } catch (e) { }
      try {
        const q = new URLSearchParams(location.search);
        if (q.has('room')) {
          q.delete('room');
          const rest = q.toString();
          history.replaceState(null, '', location.pathname + (rest ? '?' + rest : '') + location.hash);
        }
      } catch (e) { }
    },
    chooseMode(m) {
      playSfx('click');
      state.studioBooks = [];
      state.playerBook = null;
      state.bookOpen = false;
      if (m === 'party') {
        state.mode = 'party';
        state.playMode = 'main';
        state.skipIce = false;
        state.phase = 'party';
        return;
      }
      this.clearPartySession();
      state.mode = 'solo';
      state.playMode = (m === 'daily' || m === 'quick') ? m : 'main';
      state.skipIce = (m === 'daily' || m === 'quick');
      state.stage = state.skipIce ? 'investigate' : 'break_ice';
      state.bookletRole = (m === 'daily' || m === 'quick') ? 'investigator' : '';
      state.partyChar = '';
      state.myFactionHint = '';
      state.bookletForced = null;
      state.phase = 'seat';
    },
    async pickPartyChar(id) {
      id = String(id || '').trim();
      if (!id) return false;
      const prev = state.partyChar;
      this.applyLocalSeat(id);
      const pid = state.playerId || (window.myPlayerId ? window.myPlayerId() : 'player:1');
      if (this.liveSession() && state.mode === 'party' && state.roomCode) {
        try {
          const jr = await fetch('/api/session/' + encodeURIComponent(state.sessionId) + '/join', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room_code: state.roomCode, player_id: pid, char_id: id })
          });
          if (!jr.ok) {
            let msg = '入席失败';
            try { msg = Labels.apiErr((await jr.json()).detail, msg); } catch (e) { }
            toast(msg, 'warn');
            if (prev) this.applyLocalSeat(prev); else { state.partyChar = ''; state.bookletRole = ''; }
            return false;
          }
          const body = await jr.json().catch(() => ({}));
          if (body.seats) state.partySeats = body.seats;
        } catch (e) {
          toast('入席通道未接通', 'warn');
          if (prev) this.applyLocalSeat(prev); else { state.partyChar = ''; state.bookletRole = ''; }
          return false;
        }
      } else if (this.liveSession()) {
        try {
          const cr = await fetch('/api/session/' + encodeURIComponent(state.sessionId) + '/claim', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_id: pid, char_id: id })
          });
          if (cr.ok) {
            const j = await cr.json();
            if (j.char_id) this.applyLocalSeat(j.char_id);
            if (j.booklet) state.bookletPack = j.booklet;
            if (j.seats) state.partySeats = j.seats;
          }
        } catch (e) { /* 本地闭卷仍可用 */ }
      }
      this.hydrateBooklet();
      return true;
    },
    bookletRoleId() {
      if (state.mode === 'party' && state.partyChar) return state.partyChar;
      return state.bookletRole || 'investigator';
    },
    hydrateBooklet() {
      const role = this.bookletRoleId();
      const local = ((!state.scenarioId || state.scenarioId === 'kanshan') && window.Booklets && window.Booklets.pack)
        ? window.Booklets.pack(role, state.act || 1, { mine: true }) : null;
      if (local) state.bookletPack = local;
      if (!state.sessionId || !state.netKind || state.netKind === 'mock') return Promise.resolve(local);
      const pid = encodeURIComponent(state.playerId || 'player:1');
      return fetch('/api/session/' + encodeURIComponent(state.sessionId) + '/booklet?player_id=' + pid)
        .then(r => r.ok ? r.json() : null)
        .then(j => {
          if (j && j.booklet) {
            // A running server may still cache the previous asset revision. Only
            // supplement the same role and chapters that the server has opened.
            if (local && j.booklet.role_id === local.role_id) {
              (j.booklet.unlocked || []).forEach(k => {
                const cover = (j.booklet.covers || {})[k];
                const source = (local.covers || {})[k];
                if (cover && source && !(cover.milestones || []).length) {
                  cover.milestones = (source.milestones || []).slice();
                }
              });
            }
            const rid = String(j.booklet.role_id || j.booklet.id || '');
            const want = state.partyChar || state.bookletRole;
            if (want && want !== 'investigator' && rid === 'investigator' && local) {
              return state.bookletPack;
            }
            state.bookletPack = j.booklet;
          }
          return state.bookletPack;
        })
        .catch(() => state.bookletPack);
    },
    async openBooklet() {
      if (state.isSpectator) return false;
      state.bookletOpen = true;
      /* 先同步灌入本地闭卷，避免单人模式等待网络请求时点击无响应。 */
      if (!state.bookletPack && window.Booklets && window.Booklets.pack) {
        const local = window.Booklets.pack(this.bookletRoleId(), state.act || 1, { mine: true });
        if (local) state.bookletPack = local;
      }
      const pack = await this.hydrateBooklet();
      if (!state.bookletPack && !pack) { state.bookletOpen = false; toast('剧本尚未加载，请先领取角色或重试', 'warn'); return false; }
      state.dmBookRead = true;
      chat('dm', '叮——已记录你读完本幕剧本。接下来请回到圆桌，听完角色亮相并开始提问。', { kind: 'guide' });
      return true;
    },
    async openRoleScript() {
      if (state.isSpectator) return false;
      if (state.scenarioId && state.scenarioId !== 'kanshan') return this.openMyBook();
      return this.openBooklet();
    },
    currentRoleGoals() {
      if (state.scenarioId && state.scenarioId !== 'kanshan') {
        return (state.playerBook && state.playerBook.goals) || [];
      }
      const pack = state.bookletPack;
      const key = ['A', 'B', 'C'][Math.max(0, Math.min(2, (state.act || 1) - 1))];
      const cover = pack && (pack.covers || {})[key];
      return cover ? (cover.milestones || []) : [];
    },
    openGoals() { this.hydrateBooklet(); },
    bookletDismiss() { state.bookletForced = null; state.bookletOpen = false; },
    async pickStudioChar(id) {
      id = String(id || '').trim();
      if (!id) return false;
      state.partyChar = id;
      try { sessionStorage.setItem('party_char', id); } catch (e) { }
      const sid = state.scenarioId;
      if (!sid) { toast('缺少剧本编号', 'warn'); return false; }
      try {
        const r = await fetch('/api/studio/' + encodeURIComponent(sid) + '/book/' + encodeURIComponent(id));
        let j = null;
        try { j = await r.json(); } catch (e) { j = null; }
        if (!r.ok || !j || !j.ok || !j.book) {
          toast(Labels.apiErr(j && (j.detail || j.message), '领取故事本失败'), 'warn');
          return false;
        }
        state.playerBook = j.book;
        return true;
      } catch (e) {
        toast('领取故事本失败', 'warn');
        return false;
      }
    },
    openMyBook() {
      if (!state.playerBook) { toast('还没有领取故事本', 'warn'); return false; }
      this.hydrateBooklet();
      state.bookOpen = true;
      return true;
    },
    closeMyBook() { state.bookOpen = false; },
    async refreshSessionAp() {
      if (!this.liveSession()) return;
      const sid = state.sessionId;
      try {
        const r = await fetch('/api/session/' + encodeURIComponent(sid));
        if (!r.ok || sid !== state.sessionId) return;
        const j = await r.json(), snapshot = j.session || j;
        const ap = snapshot.ap_state && snapshot.ap_state[state.playerId];
        if (ap !== undefined) state.ap = ap;
        else if (snapshot.actions_left !== undefined) state.ap = snapshot.actions_left;
      } catch (e) { toast('行动点同步失败，请稍后重试', 'warn'); }
    },
    loadMemory(cid) {
      if (!this.liveSession()) return false;
      return window.Net.send('skill', { skill: 'memory_read', target: cid });
    },
    async whisper(to, text) {
      text = String(text || '').trim();
      if (!text) return false;
      if (!to) { toast('先选私聊对象', 'warn'); return false; }
      if (state.netKind === 'ws' && state.sessionId) {
        try {
          const r = await fetch('/api/session/' + encodeURIComponent(state.sessionId) + '/whisper', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from: state.playerId || 'player:1', to: to, text: text })
          });
          if (!r.ok) {
            let msg = '私聊失败';
            try { msg = Labels.apiErr((await r.json()).detail, msg); } catch (e) { }
            toast(msg, 'warn');
            return false;
          }
          return true;
        } catch (e) {
          toast('私聊通道未接通', 'warn');
          return false;
        }
      }
      applyEvent({ type: 'chat', actor: state.playerId || 'player:1', payload: {
        whisper: true, to: to, text: text, actor_kind: 'player',
        player_id: state.playerId || 'player:1'
      } });
      return true;
    },
    async npcWhisper(to, text) {
      text = String(text || '').trim();
      if (!text || !to) return false;
      if (state.demo || state.ended || state.isSpectator) { toast('当前模式不可私聊 AI', 'warn'); return false; }
      if (!this.liveSession()) {
        const ready = await this.ensureSoloSession();
        if (!ready || !this.liveSession()) { toast('单人局服务端未连接，请重试', 'warn'); return false; }
      }
      try {
        const r = await fetch('/api/session/' + encodeURIComponent(state.sessionId) + '/npc-whisper', {
          method: 'POST', headers: this.llmHeaders(),
          body: JSON.stringify({ from: state.playerId || 'player:1', to: to, text: text })
        });
        if (!r.ok) { let msg = 'NPC 私聊失败'; try { msg = Labels.apiErr((await r.json()).detail, msg); } catch (e) {} toast(msg, 'warn'); return false; }
        const j = await r.json(); (j.events || (j.event ? [j.event] : [])).forEach(applyEvent);
        return true;
      } catch (e) { toast('NPC 私聊通道未接通', 'warn'); return false; }
    },
    async requestNpcWave() {
      if (state.npcWaveBusy) return false;
      if (state.demo || state.ended || state.isSpectator) { toast('当前模式不可邀请 AI 发言', 'warn'); return false; }
      state.npcWaveBusy = true;
      try {
        if (!this.liveSession()) { const ready = await this.ensureSoloSession(); if (!ready || !this.liveSession()) { toast('单人局服务端未连接，请重试', 'warn'); return false; } }
        const r = await fetch('/api/session/' + encodeURIComponent(state.sessionId) + '/npc-wave', {
          method: 'POST', headers: this.llmHeaders(), body: JSON.stringify({ player_id: state.playerId || 'player:1' })
        });
        if (!r.ok) { let msg = 'AI 角色发言失败'; try { msg = Labels.apiErr((await r.json()).detail, msg); } catch (e) {} toast(msg, 'warn'); return false; }
        const j = await r.json();
        /* AI 介绍按席位依次播报：服务端返回一组事件，前端逐条落地，
           每位角色之间留出阅读和语音播放时间，避免同一时刻抢麦。 */
        const events = j.events || [];
        for (let i = 0; i < events.length; i++) {
          const ev = events[i];
          applyEvent(ev);
          if (i < events.length - 1 && ev && ev.type === 'chat') {
            await new Promise(resolve => setTimeout(resolve, 1800));
          }
        }
        if ((j.failed_roles || []).length) toast('部分角色未能回应，可以稍后再试', 'warn');
        else if (!j.count) toast('当前没有可发言的 AI 席位', 'warn');
        return true;
      } catch (e) { toast('AI 角色发言通道未接通', 'warn'); return false; }
      finally { state.npcWaveBusy = false; }
    },
    async bootPlayMode(mode) {
      mode = mode || state.playMode;
      /* 跳过破冰听介绍，但留在搜证章（act=1）。强行 act=2 会摘掉现场搜证。 */
      state.skipIce = true;
      state.stage = 'investigate';
      state.round = Math.max(state.round, 2);
      if (state.act < 1) state.act = 1;
      if (mode === 'daily') {
        const fallback = { topic: '#档案局夜班纪律#', body: '今日加练：拆穿一则档案局衍生谣言。', source: 'fallback' };
        try {
          const t = await fetch('/api/daily-topic');
          const j = t.ok ? await t.json() : null;
          if (j && (j.topic || j.body)) {
            state.dailyTopic = j;
            chat('sys', '【每日挑战】' + (j.topic || fallback.topic) + ' ' + (j.body || ''), { kind: 'counsel' });
          } else {
            state.dailyTopic = fallback;
            chat('sys', '【每日挑战】' + fallback.topic + '（热榜未接通，使用预置词条）', { kind: 'counsel' });
          }
        } catch (e) {
          state.dailyTopic = fallback;
          chat('sys', '【每日挑战】' + fallback.topic + '（热榜未接通，使用预置词条）', { kind: 'counsel' });
        }
      } else if (mode === 'quick') {
        chat('sys', '【快速局】已跳过破冰，直接搜证/对质。', { kind: 'counsel' });
      }
      try {
        const pid = (window.myPlayerId ? window.myPlayerId() : 'player:1');
        const sr = await fetch('/api/session', {
          method: 'POST', headers: this.llmHeaders(),
          body: JSON.stringify({ mode: mode, player_id: pid })
        });
        if (sr.ok) {
          const sj = await sr.json();
          if (sj.ok && sj.session) {
            state.sessionId = sj.session.session_id;
            state.playerId = pid;
            const wsUrl = partyWsUrl(sj.session.session_id, pid, false);
            await Store.connectParty(wsUrl);
          }
        }
      } catch (e) { /* 无服务则走本地 mock */ }
    },
    async createRoom() {
      if (state.creatingRoom) return false;
      state.creatingRoom = true;
      const pid = (window.myPlayerId ? window.myPlayerId() : 'player:1');
      try {
        const r = await fetch('/api/session', { method: 'POST', headers: this.llmHeaders(),
          body: JSON.stringify({ mode: 'party', player_id: pid }) });
        const j = await r.json();
        if (j.ok && j.session) {
          state.sessionId = j.session.session_id;
          state.roomCode = j.session.room_code || '';
          state.playerId = pid; state.isHost = true; state.isSpectator = false;
          state.roomFull = null; state.mode = 'party';
          state.phase = 'seat';
          const seat = ((j.events || [])[0] || {}).payload && j.events[0].payload.seat;
          if (seat && seat.char_id) this.applyLocalSeat(seat.char_id);
          const wsUrl = partyWsUrl(j.session.session_id, pid, false);
          window.sessionStorage.setItem('party_ws', wsUrl);
          const base = await resolveShareBase();
          state.lanBase = base;
          state.shareUrl = base + '/?room=' + state.roomCode;
          savePartyTicket({ code: state.roomCode, sid: state.sessionId, phase: 'seat', host: true });
          try { history.replaceState(null, '', '/?room=' + encodeURIComponent(state.roomCode)); } catch (e) { }
          await this.connectParty(wsUrl);
          try {
            const vr = await fetch('/api/session/' + encodeURIComponent(state.sessionId));
            if (vr.ok) {
              const vj = await vr.json();
              if (vj.session && vj.session.seats) state.partySeats = vj.session.seats;
            }
          } catch (e) { }
          return true;
        }
      } catch (e) { }
      finally { state.creatingRoom = false; }
      window.Store.toast('建房失败——请确认服务在线', 'warn'); return false;
    },
    async joinRoom(code, opts) {
      code = String(code || '').trim();
      opts = opts || {};
      if (!code) { window.Store.toast('请输入 6 位房间码', 'warn'); return false; }
      const pid = (window.myPlayerId ? window.myPlayerId() : ('player:' + Date.now().toString(36)));
      const role = opts.spectator ? 'spectator' : 'player';
      try {
        const r = await fetch('/api/room/' + encodeURIComponent(code));
        if (r.status !== 200) { window.Store.toast('房间不存在或已过期：' + code, 'warn'); return false; }
        const room = await r.json();
        const sid = room.session_id;
        if (!sid) { window.Store.toast('房间数据异常', 'warn'); return false; }
        let charId = opts.char_id || '';
        try { charId = charId || sessionStorage.getItem('party_char') || ''; } catch (e) { }
        const jr = await fetch('/api/session/' + encodeURIComponent(sid) + '/join', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: code, player_id: pid, role: role, char_id: charId || undefined }) });
        if (jr.status !== 200) {
          let msg = '加入失败';
          try { msg = Labels.apiErr((await jr.json()).detail, msg); } catch (e) { }
          if (jr.status === 409 && !opts.spectator) {
            state.roomFull = { code: code, sid: sid, detail: msg };
            state.mode = 'party'; state.phase = 'party'; state.roomCode = code;
            window.Store.toast(msg, 'warn');
            return false;
          }
          window.Store.toast(msg, 'warn'); return false;
        }
        const joinBody = await jr.json().catch(() => ({}));
        if (joinBody.seats) state.partySeats = joinBody.seats;
        const mySeat = (joinBody.seats || []).find(s => s.player_id === pid);
        if (mySeat && mySeat.char_id) this.applyLocalSeat(mySeat.char_id);
        let ticket = {};
        try { ticket = JSON.parse(sessionStorage.getItem('party_ticket') || '{}'); } catch (e) { }
        const resumePlay = ticket.sid === sid && ticket.phase === 'play';
        const wasHost = !!(ticket.host && ticket.sid === sid);
        state.sessionId = sid; state.roomCode = code; state.playerId = pid;
        state.isHost = wasHost; state.mode = 'party'; state.roomFull = null;
        state.isSpectator = role === 'spectator';
        state.phase = (resumePlay || role === 'spectator') ? 'play' : 'seat';
        if (state.phase === 'play') {
          state.view = 'chat';
          if (state.showtime) state.showtime.step = 'act';
        }
        const wsUrl = partyWsUrl(sid, pid, role === 'spectator');
        window.sessionStorage.setItem('party_ws', wsUrl);
        if (!state.shareUrl) {
          const base = await resolveShareBase();
          state.lanBase = base;
          state.shareUrl = base + '/?room=' + code;
        }
        savePartyTicket({ code: code, sid: sid, phase: state.phase, host: wasHost });
        await this.connectParty(wsUrl);
        return true;
      } catch (e) { window.Store.toast('加入房间失败：' + (e && e.message || ''), 'warn'); return false; }
    },
    /* 用真实房间地址（重新）建立 WS 实时通道；身份 = 本浏览器 player_id。
       页面初始的 Net.init 可能已建了本地 mock 通道，party 就绪后在此切到真实房间。 */
    async connectParty(wsUrl) {
      if (!window.Net || !wsUrl) return false;
      try {
        const info = await window.Net.init({ wsUrl: wsUrl, sessionId: state.sessionId, playerId: state.playerId });
        state.netKind = info.mode;
        // 重新挂载协议事件监听（Net 实例已换）
        ['search_result', 'clue_gained', 'chat', 'memory_unlock', 'counsel_result',
         'hotfeed_refresh', 'faction_skill', 'vote', 'ending', 'danmaku', 'system',
         'achievement_unlocked', 'cocoon_break', 'evidence_pin', 'defect']
          .forEach(t => window.Net.on(t, evt => applyEvent(evt)));
        /* error 事件由服务端定向回传，必须进入聊天记录，不能只打 console。 */
        window.Net.on('system', evt => applyEvent(evt));
        // 连接状态提示也随新实例重挂（否则重连/断线不再有 UI 反馈）
        if (window.__connStatusHook) window.Net.on('_status', window.__connStatusHook);
        if (info.fallback) { window.Store.toast('实时通道未接通，AI 对话不可用；请检查服务器后点重试（未回退本地演示）', 'warn'); return false; }
        try {
          const r = await fetch('/api/session/' + encodeURIComponent(state.sessionId));
          if (r.ok) {
            const raw = await r.json(), saved = raw.session || raw;
            (saved.events || []).filter(e => e.type === 'system' && ['case_intro', 'evidence_composed', 'flaw_progress', 'boss_ready'].includes((e.payload || {}).event)).forEach(applyEvent);
            if (saved.flaw_count !== undefined) state.engineFlawCount = saved.flaw_count;
          }
        } catch (e) { /* live events continue; hydration may be retried on reconnect */ }
        window.Store.toast('已连入房间实时通道', 'ok');
        if (state.phase === 'play') this.requestAiWave({ retries: 2 });
        return true;
      } catch (e) { window.Store.toast('房间通道连接失败：' + (e && e.message || ''), 'warn'); return false; }
    },
    setIdentity(name, avatarSrc) {
      if (name) state.playerHeadline = name;
      if (avatarSrc) state.playerAvatar = avatarSrc;
    },
    startVideo() { state.phase = 'video'; },
    /* 序章视频兜底：主源 opening 失败 → 退 prologue → 再失败直接进游戏。
       此前无任何 error 处理，两个源都缺时 @ended 永不触发，玩家会永久卡在黑屏序章。 */
    introFallback() {
      const v = document.querySelector('.video-phase video');
      if (!v) return this.startGame();
      if (!v.dataset.fallback) {
        v.dataset.fallback = '1';
        v.src = '/assets/videos/prologue.mp4';
        v.load();
        const p = v.play();
        if (p && p.catch) p.catch(() => {});
        return;
      }
      this.startGame();
    },
    startGame() { this.enterBureau(); },
    prologueNext() {
      const n = (M.prologueSteps && M.prologueSteps.length) ? M.prologueSteps.length : 3;
      if (state.prologueStep >= n - 1) { state.phase = 'video'; return; }
      state.prologueStep += 1;
    },
    enterBureau() {
      if (state.mode === 'party' && state.roomCode) savePartyTicket({ phase: 'play', sid: state.sessionId, code: state.roomCode });
      const studioKeep = (state.phase === 'prologue' || state.phase === 'video')
        && !!(state.scenarioId && (state.studioBooks || []).length);
      resetPlayForStudio();
      state.phase = 'play';
      if (!studioKeep) {
        state.studioNeedAdvance = false;
        state.studioModules = null;
        state.studioMeta = null;
        state.scenarioId = '';
        state.studioMinis = null;
        state.studioVibe = '';
        state.studioType = '';
        state.studioCamp = null;
        state.studioBooks = [];
        state.playerBook = null;
        state.bookOpen = false;
      }
      /* V4 综艺流程：开场覆盖层完成后先显示案件卷宗页（环节②），确认后再进破冰圆桌（环节③） */
      if (state.showtime) state.showtime.step = 'case_file';
      state.view = 'chat';
      const skipIce = state.playMode === 'daily' || state.playMode === 'quick';
      if (skipIce) { state.skipIce = true; state.stage = 'investigate'; }
      else if (!studioKeep) state.stage = 'break_ice';
      if (studioKeep) {
        chat('dm', (state.studioMeta && state.studioMeta.hook)
          || '叮——故事本已收下。全员已在圆桌就座，先听听他们的自我介绍。', { name: '系统提示音' });
      } else {
        chat('dm', skipIce
          ? '叮——身份登记完成。破冰已跳过，卷宗确认后直接开搜。'
          : '叮——身份登记完成。欢迎入职，调查员。全员已在大厅集合，先听听他们的自我介绍。', { name: '系统提示音' });
        if (skipIce) this.bootPlayMode(state.playMode);
      }
      save();
      const kickAi = !state.demo && (state.mode === 'party' || state.playMode === 'main'
        || state.playMode === 'daily' || state.playMode === 'quick');
      if (kickAi && state.mode !== 'party' && !this.liveSession()) {
        this.ensureSoloSession().then(() => this.requestAiWave({ retries: 4 }));
      } else if (kickAi) {
        this.requestAiWave({ retries: 4 });
      }
    },
    state, Engine, applyEvent, toast, banner, pushDmaku, chat,
    locClueLeft, locTier, flawCount, ownedClues, hasKc, heartOf, coverage, evidenceCoverage,
    studioMiniCatalog() {
      const reg = (window.Minis && window.Minis.REG) || {};
      const allow = state.studioMinis;
      if (state.scenarioId && Array.isArray(allow)) {
        const out = {};
        allow.forEach(id => { if (reg[id]) out[id] = reg[id]; });
        return out;
      }
      return reg;
    },
    /* V4 综艺流程：卷宗页确认（→第一幕转场→破冰圆桌）/ 幕转场跳过 */
    showtimeNext() {
      if (!state.showtime) return;
      if (state.showtime.step === 'case_file') {
        state.showtime.step = 'act';
        state.view = 'chat';
        if (state.skipIce || state.playMode === 'daily' || state.playMode === 'quick') {
          state.showtime.cut = null;
          chat('sys', state.playMode === 'daily'
            ? '【每日挑战】破冰已跳过，现场搜证已开。今日词条在顶栏。'
            : '【快速局】破冰已跳过，直接搜证/对质。', { kind: 'counsel' });
          if (!state.playerBook) {
            state.bookletForced = 'A';
            this.hydrateBooklet();
          }
          this.requestAiWave({ force: true, retries: 3 });
          return;
        }
        state.showtime.cut = { act: 1 };   // act_t1 转场：进入破冰圆桌（2.5s 自动过或点击跳过）
        chat('sys', state.playerBook
          ? '【环节 · 嫌疑人亮相】当事人已在圆桌就座。故事本可随时从顶栏重读。'
          : '【环节 · 嫌疑人亮相】八位当事人已在圆桌就座。先读你的闭卷，再听自我介绍。', { kind: 'counsel' });
        if (!state.playerBook) {
          state.bookletForced = 'A';
          this.hydrateBooklet();
        }
        this.requestAiWave({ force: true, retries: 3 });
      }
    },
    cutDismiss() { if (state.showtime) state.showtime.cut = null; },
    /* V5 章节独占式：章末条件查询 + 前情提要关闭 */
    chapterProgress,
    recapDismiss() { state.recap = null; },
    iceBlocksSearch() {
      if (state.skipIce || state.demo) return false;
      if (state.studioNeedAdvance) return true;
      if ((state.studioBooks || []).length) return false;
      if (state.stage !== 'break_ice') return false;
      if (!state.dmBookRead) return true;
      const spoken = (state.chat || []).some(m => m.actor === 'npc');
      return !spoken;
    },
    playerCharacterId() {
      if (state.isSpectator) return '';
      const valid = id => id && id !== 'dm' && M.chars.some(c => c.id === id);
      const direct = String(state.partyChar || '').trim();
      if (valid(direct)) return direct;
      const pid = String(state.playerId || '').trim();
      const seat = pid && (state.partySeats || []).find(s => String(s && (s.player_id || s.id) || '') === pid);
      const seated = String(seat && seat.char_id || '').trim();
      if (valid(seated)) return seated;
      const role = String(state.bookletRole || '').trim();
      return valid(role) ? role : '';
    },
    selectChatTarget(id) {
      if (!id || id === Store.playerCharacterId()) return false;
      state.currentNpc = id;
      return true;
    },
    send(action, payload) {
      track('actions', String(action || 'unknown'));
      payload = Object.assign({}, payload || {});
      if (action === 'cocoon_break' || action === 'evidence_pin' || action === 'defect' || action === 'judge_line') {
        payload.kind = payload.kind || action;
        payload.skill = payload.skill || action;
        action = 'skill';
      }
      if (action === 'skill' && payload.kind && !payload.skill) payload.skill = payload.kind;
      if (action === 'counsel') {
        payload.target = payload.target || payload.char_id;
        payload.card = payload.card || payload.kc_id;
      }
      if (action === 'chat') {
        payload.target = payload.target || payload.char_id;
        payload.char_id = payload.char_id || payload.target;
        const mine = Store.playerCharacterId();
        if (mine && [payload.target, payload.char_id].some(id => String(id || '').replace(/^npc:/, '') === mine)) {
          toast('这是你扮演的角色，请选择其他人对话', 'warn');
          return false;
        }
      }
      if ((action === 'search' || (action === 'skill' && (payload.kind === 'stealth_photo' || payload.skill === 'stealth_photo')))
          && Store.iceBlocksSearch()) {
        toast('破冰结束才能搜证', 'warn');
        return false;
      }
      if (action === 'search' && payload.location) {
        const loc = resolveLoc(payload.location);
        payload.location = state.netKind === 'ws' ? (loc.name || loc.scene || loc.id) : loc.id;
      }
      if (state.busy) {
        Store._sendQ = Store._sendQ || [];
        if (Store._sendQ.length < 8) Store._sendQ.push([action, payload]);
        else toast('行动队列已满，请稍候再试', 'warn');
        return 'queued';
      }
      if (action === 'chat' && payload.text && state.netKind === 'ws') {
        archiveEcho(payload.text, payload.target || payload.char_id);
      }
      state.busy = true;
      let ok = false;
      try {
        ok = window.Net.send(action, payload) !== false;
      } catch (e) {
        // 网络层异常时及时释放锁，避免界面永久停在“处理中”。
        state.busy = false;
        toast('行动发送失败，请稍后重试', 'warn');
        return false;
      }
      if (!ok) {
        state.busy = false;
        toast('当前连接不可用，请稍后重试', 'warn');
        return false;
      }
      // MockTransport 的事件延迟为 220–480ms；给真实网络留出余量，
      // 避免 200ms watchdog 过早释放导致同一行动被重复提交。
      setTimeout(() => {
        state.busy = false;
        const next = (Store._sendQ || []).shift();
        if (next) Store.send(next[0], next[1]);
      }, 700);
      return true;
    },
    reset, M, buildTruthProfile, demoRailSteps, startJudgeLine,
    getTelemetry() { return JSON.parse(JSON.stringify(state.telemetry || {})); },
    /* 根据本局行为给出单一下一步建议，帮助玩家保持主循环节奏。 */
    pacingHint() {
      const a = (state.telemetry && state.telemetry.actions) || {};
      const searched = Number(a.search || 0), chatted = Number(a.chat || 0), voted = Number(a.vote || 0);
      if (state.ended || state.showtime && state.showtime.step === 'reveal') return '案件已复盘 · 查看侦探报告';
      if (state.stage === 'accuse' || state.view === 'vote') return '证据链已成形 · 选择嫌疑人指认';
      if (!searched) return '先搜一处现场 · 找到第一张线索卡';
      if (!chatted) return '带着线索去圆桌 · 询问一位当事人';
      if (searched < 3) return '再搜一处关键地点 · 拼出时间线';
      if (chatted < 2) return '继续追问矛盾点 · 观察角色反应';
      return state.ap > 0 ? '行动点充足 · 优先验证未确认的线索' : '本轮行动用尽 · 点击推进进入下一轮';
    },
    startJudgeDemo() {
      playSfx('click');
      this.clearPartySession();
      state.mode = 'solo';
      this.enterBureau();
      return startJudgeLine();
    },
    goDemoRail, grantFinaleFlaw, endingPair,
    clueById, uiClueId, Labels
  };
  window.Store = Store;
  watch(() => [Store.playerCharacterId(), state.currentNpc], ([mine, target]) => {
    if (mine && target === mine) state.currentNpc = 'dm';
  }, { immediate: true });
  /* net.js MockTransport 契约：window.Engine = (action, payload, emit) 可调用包装。
   * （此前从未暴露——Mock 通道 send 必崩；且 Engine 对象本身非函数，需此适配层） */
  window.Engine = function (action, payload, emit) {
    const out = (type, pl, actor) => emit(type, pl, actor);
    const h = Engine[action];
    if (!h) return out('system', { event: 'error', notice: '这个动作现在还不能用' }, 'dm');
    try { h(payload || {}, out); } catch (e) {
      out('system', { event: 'engine_error', notice: '本地裁决出了点岔子，请再试一次' }, 'dm');
    }
  };
  load();
})();
