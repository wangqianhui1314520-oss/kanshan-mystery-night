#!/usr/bin/env node
/* ============================================================
 * smoke_v31.js —— E 前端组 V31 增量无头冒烟（Node + 真实 Vue 3.4.38）
 * 覆盖：模板编译（全视图+V31 组件）/ V31 动作与事件流断言 / 数据完整性
 * 运行：node frontend/tests/smoke_v31.js
 * ============================================================ */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
let pass = 0, fail = 0;
const ok = (cond, name) => { if (cond) { pass++; console.log('  PASS ' + name); } else { fail++; console.error('  FAIL ' + name); } };

/* ---------- DOM-less 宿主 ---------- */
function makeEl() {
  // Vue 3.4 编译器 decodeEntities：
  //   属性值路径 → el.innerHTML = `<div foo="...">` 后取 el.children[0].getAttribute('foo')
  //   文本路径  → el.innerHTML = raw 后取 el.textContent
  const el = { style: {}, children: [], _h: '' };
  el.getAttribute = k => (k === 'foo' ? el._decoded : null);
  el.setAttribute = () => { };
  el.remove = () => { };
  el.hasAttribute = () => false;
  el.addEventListener = () => { };
  el.appendChild = () => { };
  Object.defineProperty(el, 'innerHTML', {
    set(v) {
      el._h = String(v);
      const m = el._h.match(/^<div foo="([\s\S]*)">$/);
      if (m) {
        el._decoded = m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
        el.children = [el];
      } else {
        el._plain = el._h.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ');
        el.children = [];
      }
    },
    get() { return el._h; }
  });
  Object.defineProperty(el, 'textContent', { get() { return el._plain != null ? el._plain : (el._h || ''); }, set(v) { el._h = String(v); } });
  return el;
}
const sandbox = {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  URLSearchParams, Image: function () { return {}; },
  fetch: () => Promise.reject(new Error('no-net')),
  location: { protocol: 'file:', search: '', pathname: '/', href: 'file:///test/' },
  localStorage: { getItem: () => null, setItem: () => { }, removeItem: () => { } },
  document: { getElementById: () => null, createElement: () => makeEl(), createTextNode: t => ({ textContent: t }), addEventListener: () => { } },
  Math, Date, JSON, Promise, Object, Array, String, Number, Boolean, Error, Set, Map
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
const load = (rel) => vm.runInContext(fs.readFileSync(path.join(ROOT, rel), 'utf8'), sandbox, { filename: rel });

/* ---------- 装载（顺序同 index.html） ---------- */
load('js/vendor/vue.global.prod.js');
load('js/data.js');
  load('js/booklets.js');
  load('js/pollution_data.js');
load('js/sfx.js');
load('js/voice.js');
load('js/voice_rtc.js');
load('js/store.js');
load('js/net.js');
load('js/assets.js');
load('js/ui.js');
['map', 'chat', 'bag', 'kcards', 'memory', 'hotfeed', 'vote', 'clinic', 'pollution', 'review', 'report', 'antifraud']
  .forEach(v => load('js/views/' + v + '.js'));
load('js/studio/catalog.js');
load('js/studio/brief.js');
load('js/views/studio.js');
load('minis/shell.js');
load('minis/runner.js');
load('minis/heart.js');
load('minis/refute3.js');
load('minis/badge.js');
load('minis/main-minis.js');
load('js/main.js');
load('js/goals.js');

  const { Vue, Store, Net, VIEWS, MOCK: M } = sandbox.window;

const projectGoal = sandbox.GoalCards.project;
const privateState = { act: 1, partyChar: 'char_01', bookletPack: sandbox.Booklets.pack('char_01', 1, { mine: true }) };
ok(projectGoal(privateState).personal === privateState.bookletPack.covers.A.task, '目标卡使用本人已开封任务');
ok(!JSON.stringify(projectGoal(privateState)).includes('你的记忆没被改'), '目标卡不泄露第二幕秘密');
ok(projectGoal({ ...privateState, act: 2 }).personal.includes('先领取角色'), '未开封下一幕不回退到错误任务');
ok(projectGoal({ ...privateState, isSpectator: true }).secret === '', '观战者不显示私密任务');
const customGoal = projectGoal({ ...privateState, scenarioId: 'custom', playerBook: {name: '原创角色', goals: ['寻找钥匙'], secrets: ['原创新秘密']} });
ok(customGoal.personal === '寻找钥匙' && customGoal.secret === '原创新秘密' && !customGoal.fun.includes('先问是不是'), '原创剧本不串入看山任务');

(async () => {
  // 无 DOM 下 app.mount 不执行（setup/boot 不跑）→ 手动初始化 MockTransport
  if (!Net.t) await Net.init({});
  if (!Net.t || Net.t.kind !== 'mock') { console.error('Net.init 失败'); process.exit(2); }

  /* ===== [1] 模板编译 ===== */
  console.log('\n[1] 模板编译（真实 Vue 编译器）');
  const comps = [];
  try {
    const app = Vue.createApp({ template: '<div/>' });
    sandbox.window.UI.install(app);
    if (sandbox.window.Voice && sandbox.window.Voice.install) sandbox.window.Voice.install(app);
    if (sandbox.window.VoiceRTC && sandbox.window.VoiceRTC.install) sandbox.window.VoiceRTC.install(app);
    app.component('boss-reveal', VIEWS['boss-reveal']);
    app.component('antifraud-theater', VIEWS['antifraud-theater']);
    app.component('dossier-card', VIEWS['dossier-card']);
    if (VIEWS['truth-radar']) app.component('truth-radar', VIEWS['truth-radar']);
    Object.entries(app._context.components).forEach(([name, def]) => { if (def && def.template) comps.push([name, def.template]); });
    comps.push(['app-root', sandbox.window.APP_DEF.template]);
  } catch (e) { console.error('collect error', e); }
  let cOK = 0;
  for (const [name, tpl] of comps) {
    try { Vue.compile(tpl); cOK++; } catch (e) { console.error('  compile FAIL ' + name + ': ' + e.message); fail++; }
  }
  ok(cOK === comps.length && comps.length >= 16, `模板编译 ${cOK}/${comps.length}（全部视图 + V31 增量组件）`);

  /* ===== [2] V31 数据池完整性 ===== */
  console.log('\n[2] V31 数据池完整性');
  ok(M.glitch && M.glitch.punish.length >= 5 && M.glitch.fault.length >= 4 && M.glitch.bonus.length >= 3, '抽风三池（惩罚/故障/奖励）');
  ok(M.betLines.subjects.length >= 5, '押注话题池 >=5');
  ok(M.erLines.status && Object.keys(M.erLines.status).length === 8, '急诊红灯 8 NPC 状态词');
  ok(M.headlineTopics.length >= 5, '头条话题池 >=5');
  ok(M.antifraudScript.length === 3 && M.antifraudScript.every(a => a.quiz && a.lines.length >= 3), '反诈剧场三幕+判断题');
  ok(M.dossierRanks.length >= 8 && M.dossierAvatars.length === 6, '侦探证警衔映射+官方头像 6 枚');
  ok(M.badgeDefs.length === 11 && M.badgeDefs.some(b => b.id === 'ach_yuganxianren'), '成就徽章 11 枚（含鱼干线人）');
  ok(typeof M.flavor5Credit === 'string' && M.flavor5Credit.includes('flavor_5') && M.flavor5Credit.includes('灯灯') && M.flavor5Credit.includes('凉风有信') && M.flavor5Credit.includes('反骨'), 'flavor_5 常驻署名小字（D 对接点，含盐言三作署名）');

  /* ===== [3] Mock 引擎 V31 动作流 ===== */
  console.log('\n[3] Mock 引擎 V31 动作流（发→收 全链路）');
  const S = Store.state;
  const events = [];
  const evOf = (event) => events.find(e => (e.payload || {}).event === event);
  const drive = (action, payload) => new Promise(res => {
    Net.t.engine(action, payload, (type, pl) => {
      const evt = { type, payload: pl };
      events.push(evt);
      Store.applyEvent(evt);   // 事件照常入 Store（roundSet/apDelta 等状态同步走真实链路）
    });
    setTimeout(res, 10);
  });

  await drive('advance', {});
  ok(!!evOf('bet_open'), 'advance → 押注开盘 bet_open');
  ok(!!evOf('headline_open'), 'advance → 头条开标 headline_open');
  ok(!evOf('elevator_run'), '同幕推进不出电梯（跨幕才有）');
  ok(S.round === 2, '轮次推进 → R2');

  const bet = S.bet;
  await drive('skill', { kind: 'place_bet', option: bet.options[0], amount: 2 });
  ok(!!evOf('bet_placed') && S.zans === 8, '押注扣赞（10→8）+ bet_placed');

  await drive('skill', { kind: 'bid_headline', topic: S.headline.topic, amount: 2 });
  const hl = events.filter(e => (e.payload || {}).event === 'headline_result').pop();
  ok(!!hl && hl.payload.settle && String(hl.payload.host_line).includes('头条'), 'bid_headline → headline_result（事件形态对齐服务端）');

  S.ap = 3;
  await drive('skill', { kind: 'stealth_photo', location: 'loc_monitor', keyword: '监控' });
  const sp = evOf('stealth_photo');
  ok(!!sp && !!sp.payload.photo && S.photos.length === 1, '暗拍成功 → 照片入袋（原件留场，不入 state.clues）');

  await drive('skill', { kind: 'share_photo', photo_id: S.photos[0].id, claim: '我拍到 V587 了' });
  ok(!!evOf('photo_shared') && S.photos[0].shared && S.photos[0].claim === '我拍到 V587 了', '照片流出 + 声称登记');

  S.tamperPts = 0;
  await drive('skill', { kind: 'memory_puzzle' });
  ok(S.tamperPts === 0, '篡改点 <2 → 拼图拒绝（零副作用）');
  S.tamperPts = 2;
  await drive('skill', { kind: 'memory_puzzle' });
  ok(S.tamperPts === 0, '篡改点 2 → 拼图放行并扣减');
  await drive('skill', { kind: 'memory_puzzle_submit', ok: true });
  const pr = evOf('memory_puzzle_result');
  ok(!!pr && pr.payload.ok === true && !!pr.payload.clue, '拼图排对 → 发奖励线索');

  await drive('skill', { kind: 'antifraud_answer', right: true });
  ok(!!evOf('antifraud_result') && S.antifraud.score === 1, '反诈答对 → 学分 +1');

  await drive('skill', { kind: 'closing_speech', text: '我不想赢，我只想赢的光明正大' });
  ok(!!evOf('closing_registered'), '终局陈词登记');

  await drive('skill', { kind: 'hammer_vote', target: 'char_03' });
  const hm = evOf('hammer_result');
  ok(!!hm && hm.payload.most_hammered === 'char_03' && S.hammer && S.hammer.most === 'char_03', '锤人分池 → hammer_result（most_hammered）');

  await drive('skill', { kind: 'claim_dossier', name: '王乾辉', headline: '一名debug人生的码农', avatar: M.dossierAvatars[0].src });
  const dr = evOf('dossier_ready');
  ok(!!dr && S.dossier && S.dossier.rank.includes('调试人生'), '侦探证签发（警衔=简介欢乐映射）');

  S.ap = 6; S.kcards['kc_02'] = { at: 1 };
  await drive('counsel', { char_id: 'char_06', kc_id: 'kc_02' });
  const er = evOf('er_light');
  ok(!!er && S.er['char_06'] === S.round + 1 && S.erLimit['char_06'] === true, '开导失败 → 挂红灯（expiry=当前轮+1，每局一次）');
  await drive('skill', { kind: 'unknown_x' });
  ok(true, '未知技能不崩溃（系统容错）');

  /* ===== [4] 跨幕电梯 + 抽风 ===== */
  console.log('\n[4] 跨幕电梯 + 抽风');
  S.act = 2; S.round = 6; S.glitchPerAct = {}; events.length = 0;
  await drive('advance', {});
  const el = events.find(e => (e.payload || {}).event === 'elevator_run');
  ok(!!el && el.payload.to === 3, '跨幕 advance → elevator_run（to=3）');
  ok(!!evOf('bet_open') && !!evOf('headline_open'), '跨幕轮仍重开押注/头条');

  /* ===== [5] applyEvent 消费（WS 形态回放） ===== */
  console.log('\n[5] applyEvent 消费（WS 形态回放）');
  Store.applyEvent({ type: 'system', payload: { event: 'glitch', glitch: '【惩罚：本条已打码】', rewrite: '【惩罚：认真搜证】', effect: 'ap_free' } });
  ok(S.glitchFree === true && S.banners.some(b => b.cls === 'glitch'), '抽风横幅入列 + ap_free 记账');
  Store.applyEvent({ type: 'system', payload: { event: 'detective_report', report_text: '评分 88', badges: ['ach_kanshan'], achievements: ['看山还是山'] } });
  ok(S.report && S.report.report_text === '评分 88', 'detective_report 事件消费（服务端形态）');
  Store.applyEvent({ type: 'achievement_unlocked', payload: { achievement: { id: 'ach_xinqing', name: '心晴医师' } } });
  ok(S.banners.some(b => String(b.text).includes('心晴医师')), 'achievement_unlocked 横幅');
  Store.applyEvent({ type: 'system', payload: { event: 'broadcast_accident', text: '（心声）今晚的泡面是自热的还是自欺欺人的。' } });
  ok(S.banners.some(b => b.cls === 'broadcast'), '心声广播事故横幅（白名单演出）');

  /* ===== [6] 终局报告 ===== */
  console.log('\n[6] 终局报告');
  Store.applyEvent({ type: 'vote', payload: { target: 'char_03', evidence: [], coverage: { pct: 80, hit: [] }, ending: 'truth' } });
  Store.applyEvent({ type: 'ending', payload: { ending_id: 'truth' } });
  ok(S.ended === true && !!S.report, 'ending → mock 侦探报告自动生成');
  ok(Array.isArray(S.report.badges), '报告徽章按统计产出');

  /* ===== [7] P3 鱼干微光点（collectibles_p3.md 全链路） ===== */
  console.log('\n[7] P3 鱼干微光点全链路');
  S.act = 1; events.length = 0;
  await drive('skill', { kind: 'collect', item: 'fish_02' });
  ok(!evOf('collect_result').payload.collected, '第二幕收集品在第一幕被拒（act 门槛显隐语义一致）');
  await drive('skill', { kind: 'collect', item: 'fish_01' });
  const c1 = events.filter(e => (e.payload || {}).event === 'collect_result').pop();
  ok(!!c1 && c1.payload.collected === true && !!c1.payload.show.bot, '微光点拾取 fish_01（0AP + 台词 + Bot 反应）');
  ok(Object.keys(S.fish).length === 1, '收集进度 1/3 落账');
  await drive('skill', { kind: 'collect', item: 'fish_01' });
  ok(!evOf('collect_result').payload.collected, '重复拾取被拒（幂等）');
  S.act = 2;
  await drive('skill', { kind: 'collect', item: 'fish_02' });
  S.act = 3;
  await drive('skill', { kind: 'collect', item: 'fish_03' });
  const c3 = events.filter(e => (e.payload || {}).event === 'collect_result').pop();
  ok(!!c3 && c3.payload.all_collected === true, '集齐 3 袋 → all_collected 触发');
  ok(S.fishVoice && S.fishVoice.line === 0, '看山Bot 隐藏语音演出启动（4 段切片）');
  ok(M.fishVoiceLines.length === 4 && typeof M.fishVoiceBossExtra === 'string' && M.fishVoiceBossExtra.includes('金枪鱼味'), '语音 4 段 + 终极层加播 1 段（切片规格）');
  ok(M.fishCollectibles.length === 3 && M.fishCollectibles.every(f => f.anchor && f.pos && f.glow), '3 个微光点锚点定义完整（位置+闪烁周期）');

  /* ===== [8] 红灯转绿 / 竞标对齐 / 剧场 30s ===== */
  console.log('\n[8] P1/P2 文件对齐核验');
  ok(M.headlineTopics.length === 8 && M.headlineTopics[7].fun === true, '头条话题池=8（含纯欢乐位，对齐 segments_p1 §3.3）');
  ok(M.headlineLines.lose.includes('热度自己涨了 2') && M.headlineLines.outbid.includes('出价慢了半拍'), '流拍 +2 / 竞标失败句（对齐 §3.1/3.4）');
  S.ap = 6; S.headline = { round: 1, topic: M.headlineTopics[0].topic, note: '', bids: [], settled: false, winner: null }; events.length = 0;
  await drive('skill', { kind: 'bid_headline', topic: M.headlineTopics[0].topic, amount: 2 });
  ok(!!evOf('headline_result') && S.heat > 0, '竞标成交结算（热度翻倍口径）');
  Store.applyEvent({ type: 'system', payload: { event: 'er_rescue', char_id: 'char_06', text: M.erLines.rescue, tag: M.erLines.rescueTag, statusWord: '数据回来了，人回来了。' } });
  ok(!!S.erGreen && S.erGreen.cid === 'char_06', '红灯"啪"转绿演出态落账（0.5s 闪光）');
  ok(M.antifraudScript.length === 3, '剧场三幕（30s 总倒计时由视图层承载）');

  /* ===== [9] minis 小游戏层（shell + 四件） ===== */
  console.log('\n[9] minis 小游戏层（shell 壳 + 四件注册 + 玩法逻辑）');
  const Minis = sandbox.window.Minis;
  ok(!!Minis && ['runner', 'heart', 'refute3', 'badge'].every(id => Minis.REG[id]), '四件 mini 注册齐全（runner/heart/refute3/badge）');
  ok(Minis.REG.heart.source.includes('/api/minis/memory-puzzle') && Minis.REG.refute3.source.includes('/api/minis/hotfeed-pool'), '数据源声明对齐 F 只读路由');
  ok(typeof Minis.reportScore === 'function' && typeof Minis.bestOf === 'function' && typeof Minis.download === 'function', '统一壳 API：计分/战报/分享导出');
  ok(!!Minis.REG.heart.component && Minis.REG.heart.component.template.includes('answerPicked'), 'heart 组件可挂载（answerPicked 判定入口）');
  ok(Minis.REG.refute3.component.template.includes('r3-grid'), 'refute3 消消乐盘面挂载点');
  ok(Minis.REG.runner.source.includes('kanshan.png'), 'runner 使用官方 kanshan.png 切帧（A 切帧规范）');
  ok(Minis.REG.badge.source.includes('/api/profile/me'), 'badge 数据源=GET /api/profile/me（每日抽）');
  ok(sandbox.window.VIEWS.mini && typeof sandbox.window.MinisInstall === 'function', '#/mini/{id} 宿主已注册（免登录可达）');

  /* ===== [10] 资产引用完整性 ===== */
  console.log('\n[10] 数据引用完整性（V31/minis 组件引用的资产存在）');
  const fsOk = p => fs.existsSync(path.join(ROOT, '..', p));  // 前端相对路径 ../content → game/content
  ok(fsOk('content/assets/official/kanshan/kanshan.png'), '官方 kanshan.png 雪碧图存在');
  // 侦探证头像 src 为绝对路径 /assets/...（运行时由静态服务映射 /assets → content/assets）；
  // 归一化：先去掉可能的 ../ 前缀，再把开头的 /assets/ 或 assets/ 映射到 content/assets/ 后核验落盘。
  const toRepoPath = src => src.replace(/\.\.\//g, '').replace(/^\/?assets\//, 'content/assets/');
  M.dossierAvatars.forEach(a => ok(fsOk(toRepoPath(a.src)), '侦探证头像存在：' + a.src));
  ok(fsOk('content/assets/images/dm_kanshan_holo.png'), 'DM 全息图存在（分享卡兜底头像）');
  ok(fsOk('content/assets/images/bust/dm_kanshan_holo.png'), 'DM 胸像存在（头像层）');
  ok(fsOk('content/assets/images/bust/char_zhizhizhe.png'), '角色胸像存在');
  ok(fsOk('content/assets/images/still/loc_monitor.jpg'), '暗拍静帧存在');
  ok(typeof sandbox.window.ASSETS.clueThumb === 'function', 'ASSETS.clueThumb 注册');
  ok(!!sandbox.window.ASSETS.TOPIC['流量'].emblem && sandbox.window.ASSETS.TOPIC['流量'].emblem.includes('card/kc_flame'), 'TOPIC 注册无字纹章路径');
  ok(typeof sandbox.window.ASSETS.topicOf('流量').emblem === 'string', 'topicOf 回传 emblem');
  ok(sandbox.window.UI.comps['kc-card'].template.includes('topic.emblem'), 'kc-card 正面接线纹章');
  ok(VIEWS.kcards.template.includes('kc-detail-crest'), '知识卡详情展示纹章');
  ok(VIEWS.clinic.template.includes('healed'), '诊室选人开导态 class');
  ['kc_flame', 'kc_voice', 'kc_work', 'kc_focus', 'kc_learn', 'kc_burn', 'kc_goal', 'kc_bound', 'kc_plan', 'kc_know']
    .forEach(n => ok(fsOk('content/assets/images/card/' + n + '.png'), '纹章存在：' + n));

  /* ===== [11] 反操纵三件套（污染对照 / 回声 / 法官 / 求真画像） ===== */
  console.log('\n[11] 反操纵三件套（Mock 与引擎事件名对齐）');
  ok(!!VIEWS.pollution && typeof VIEWS.pollution.template === 'string' && VIEWS.pollution.template.includes('污染对照'), '污染对照视图已注册');
  ok(Array.isArray(M.pollutionCases) && M.pollutionCases.length === 5 && M.pollutionCases.every(c => c.spans && c.spans.length === 5), '题库 5 道 × 5 span');
  ok(!!VIEWS.vote.template.includes('echo-wall') && VIEWS.vote.template.includes('debate-bench'), '终局页含回声墙 + 法官席');
  ok(!!VIEWS['truth-radar'], '五维雷达组件已注册');
  S.act = 2; S.demo = true; S.pollution = { case: null, result: null, ammo: 0, done: {}, summary: null }; events.length = 0;
  await drive('skill', { kind: 'pollution_open' });
  const pc = evOf('pollution_case');
  ok(!!pc && pc.payload.case && pc.payload.case.spans.length === 5, 'pollution_open → pollution_case');
  const raw = M.pollutionCases.find(c => c.id === pc.payload.case.id);
  const truthIds = raw.spans.filter(s => s.changed).map(s => s.id);
  await drive('skill', { kind: 'pollution_mark', case: raw.id, picks: truthIds });
  const pm = events.filter(e => (e.payload || {}).event === 'pollution_result').pop();
  ok(!!pm && pm.payload.passed === true && S.pollution.ammo === 1, '对照全对 → 弹药 +1');
  S.echo = { log: [], seq: 0, challenge: null, result: null, defended: false, tease: 0 };
  await drive('chat', { char_id: 'char_03', target: 'char_03', text: '我相信流量酱清白' });
  await drive('chat', { char_id: 'char_03', target: 'char_03', text: '我怀疑流量酱在撒谎' });
  events.length = 0;
  await drive('skill', { kind: 'echo_open' });
  const ech = evOf('echo_challenge');
  ok(!!ech && ech.payload.challenge && ech.payload.challenge.mode === 'contradiction', '回声检出先信后疑');
  const pair = ech.payload.challenge.pair;
  await drive('skill', { kind: 'echo_defend', picks: [pair.a, pair.b] });
  const ed = events.filter(e => (e.payload || {}).event === 'echo_defend_result').pop();
  ok(!!ed && ed.payload.passed === true && S.echo.defended === true, '点选矛盾对 → 自证成功');
  S.heat = 70; S.debate = { open: false, stance: 'open', score: 0, need: 4, rounds: [], convinced: false, text: '' };
  events.length = 0;
  await drive('skill', { kind: 'debate_open' });
  const dbo = evOf('debate_open');
  ok(!!dbo && dbo.payload.stance === 'skeptical', '热度 70 → 法官初始怀疑');
  S.clues['clue_001'] = { at: 1 };
  const evName = (M.clues.find(c => c.id === 'clue_001') || {}).name || '';
  S.kcards['kc_01'] = { at: 1 };
  const kcTitle = (M.kcards.find(k => k.id === 'kc_01') || {}).title || '';
  await drive('skill', { kind: 'debate_submit', claim: '出示实证：' + evName + '。引用知识卡：' + kcTitle + '。我承认我曾经动摇过。' });
  const dbr1 = events.filter(e => (e.payload || {}).event === 'debate_result').pop();
  ok(!!dbr1 && dbr1.payload.gain >= 3 && dbr1.payload.convinced === false, '首轮引用封顶 +3（采信阈值 4，需第二轮）');
  await drive('skill', { kind: 'debate_submit', claim: '继续出示实证：' + evName + '。本庭应当采信这条线索。' });
  const dbr = events.filter(e => (e.payload || {}).event === 'debate_result').pop();
  ok(!!dbr && dbr.payload.convinced === true, '第二轮继续引用实证 → 法官采信');
  const prof = Store.buildTruthProfile({ accused_dm: true, ending: 'kanshan' });
  ok(prof && prof.scores && prof.archetype && prof.highlights.length >= 1 && prof.overall >= 0, '求真画像五维可生成');
  ok(typeof Store.startJudgeLine === 'function' && Store.demoRailSteps().length === 5, '评委线五步已导出');
  S.phase = 'play'; S.ended = false; S.ending = null; S.truthProfile = null; S.voteResult = null; S.netKind = 'mock';
  S.echo = { open: false, log: [], seq: 0, challenge: null, result: null, defended: false };
  if (S.showtime) S.showtime.step = 'case_file';
  Store.startJudgeLine();
  ok(!S.showtime || S.showtime.step === 'act', '评委线跳过卷宗遮罩');
  ok(Store.evidenceCoverage().pct >= 50, '评委线开局核心覆盖 ≥50%');
  Store.goDemoRail('profile');
  ok(!!S.truthProfile && S.ended === true && (S.ending === 'truth' || S.ending === 'perfect'), '评委线第五步自动结案并生成画像');
  ok(Store.endingPair('truth_revealed').ending_id === 'truth' && Store.endingPair('kanshan').outcome === 'kanshan_still_mountain', '结局键 UI/引擎双向映射');
  S.ended = false; S.ending = null; S.truthProfile = null; S.demo = false; S.voteResult = null; S.voteTarget = ''; S.voteEvidence = [];
  ok(VIEWS.pollution.template.includes('picks.length !== (cas.changed_total || 3)'), '对照提交需圈满 3 处');
  ok(VIEWS.vote.template.includes('extraFinale') && VIEWS.vote.template.includes('更多终局玩法'), '终局陈词/锤票默认折叠');
  S.pollution.ammo = 1; S.pollution.earned = 1; S.ap = 3; S.kcards['kc_02'] = { at: 1 }; S.refuted = {};
  events.length = 0;
  await drive('skill', { kind: 'refute', post: 'post_002', card: 'kc_02' });
  const rr = events.filter(e => (e.payload || {}).event === 'refute_result').pop();
  ok(!!rr && rr.payload.ok === true && rr.payload.ammo_spent === 1 && S.pollution.ammo === 0, '对照弹药在辟谣成功时消耗并加码');
  ok(VIEWS.hotfeed.template.includes('!S.demo') && VIEWS.review.template.includes('mini-entry-row') && VIEWS.review.template.includes('v-if="!S.demo"'), '评委线隐藏头条竞标/复盘小游戏');
  ok(sandbox.window.APP_DEF.template.includes('antifraud-theater v-if="!S.demo"'), '评委线不挂反诈剧场');
  ok(sandbox.window.APP_DEF.template.includes('开 始 调 查') && sandbox.window.APP_DEF.template.includes('更多玩法'), '首页主 CTA 开始调查，房间/创一本收进更多');
  ok(sandbox.window.APP_DEF.template.includes('menu-primary-actions') && sandbox.window.APP_DEF.template.includes('menu-judge-entry'), '首页主操作与评委线分组');
  ok(!VIEWS.chat.template.includes('上帝正俯视视角') && !VIEWS.chat.template.includes('#0B0F1C') && !VIEWS.hotfeed.template.includes('#0B0F1C') && !VIEWS.memory.template.includes('#0B0F1C'), '圆桌/热搜/诊室去掉色号泄漏');
  ok(typeof Store.startJudgeDemo === 'function' && sandbox.window.APP_DEF.template.includes('直达对照'), '首页可一键直达评委线');
  S.clues = {}; S.flaws = {};
  Store.applyEvent({ type: 'clue_gained', payload: { clue_id: 'clue_028', name: '破绽一·鱼干', text: '彩虹鳟鱼味', tier: 'boss_flaw', flaw_id: 'flavor_1' } });
  ok(!!S.clues.clue_001 && !S.clues.clue_028 && !!S.flaws.flavor_1, '引擎 clue_028 映射到前端鱼干破绽');
  ok(Store.clueById('clue_028') && Store.clueById('clue_028').id === 'clue_001' && String(Store.clueById('clue_028').name).includes('鱼干'), 'clueById 兼容引擎 id 并显示引擎文案');
  Store.applyEvent({ type: 'clue_gained', payload: { clue_id: 'clue_004', name: '季度经费盘点表', text: '账实相符', tier: 'public', tags: ['经费'] } });
  ok(Store.clueById('clue_004') && Store.clueById('clue_004').name === '季度经费盘点表', '引擎独有线索按正文入袋');
  S.mode = 'party'; S.roomCode = '123456'; S.shareUrl = '/?room=123456';
  Store.chooseMode('solo');
  ok(S.mode === 'solo' && !S.roomCode && S.phase === 'seat', '单人开局清掉房间码');
  ok(sandbox.window.APP_DEF.template.includes("S.mode === 'party' && S.roomCode"), '选角页房间码仅房间模式显示');
  ok(sandbox.window.APP_DEF.template.includes("S.mode === 'party' && S.shareUrl"), '选角页展示局域网分享链接');
  ok(sandbox.window.APP_DEF.template.includes('showSeatRoles') && sandbox.window.APP_DEF.template.includes('seatRoles'), '主线/房间选角卡已挂上');
  ok(typeof Store.pickPartyChar === 'function' && typeof Store.applyLocalSeat === 'function', '选角入席 API 已导出');
  ok(sandbox.window.APP_DEF.template.includes('video-phase') && sandbox.window.APP_DEF.template.includes('跳过序章'), '序章可跳过');
  ok(sandbox.window.APP_DEF.template.includes('我的剧本') && sandbox.window.APP_DEF.template.includes('特聘调查员'), '读本页与顶栏闭卷入模板');
  ok(typeof Store.hydrateBooklet === 'function' && Store.bookletRoleId() === 'investigator', '单人默认调查员闭卷');
  S.clues['clue_001'] = { at: 1 }; S.evidenceLinks = []; events.length = 0;
  await drive('skill', { kind: 'evidence_pin', clueId: 'clue_001' });
  ok(S.evidenceLinks.some(l => l.clueId === 'clue_001'), 'skill.evidence_pin → 钉入拼图');
  ok(S.evidenceLinks.some(l => l.clueId === 'clue_001' && (l.nodes || []).includes('tn_02')), 'clue_001 钉入核心 tn_02');
  S.cocoon = { active: false, broken: 0, revealed: 0 }; S.searchBias = {};
  Store.applyEvent({ type: 'system', payload: { event: 'cocoon_enter', bias: { 热搜: 2 } } });
  ok(S.cocoon.active === true, 'WS 形态 cocoon_enter 入茧');
  Store.applyEvent({ type: 'system', payload: { event: 'cocoon_break' } });
  ok(S.cocoon.broken >= 1, 'WS 形态 cocoon_break 破茧');
  const sent = [];
  const oldSend = Net.send.bind(Net);
  Net.send = (a, p) => { sent.push([a, p]); return true; };
  S.busy = false; Store._sendQ = [];
  Store.send('evidence_pin', { clueId: 'clue_007' });
  ok(sent[0] && sent[0][0] === 'skill' && sent[0][1].skill === 'evidence_pin', 'Store.send 把 evidence_pin 映射为 skill');
  sent.length = 0; S.busy = false; Store._sendQ = [];
  Store.send('judge_line', {});
  ok(sent[0] && sent[0][0] === 'skill' && sent[0][1].skill === 'judge_line', 'Store.send 把 judge_line 映射为 skill');
  S.ended = true; S.ending = 'kanshan'; S.clues = { clue_001: { at: 1 } }; S.demo = true;
  Store.startGame();
  ok(S.ended === false && !S.ending && !S.clues.clue_001 && S.demo === false && S.phase === 'play', '新开局清掉上一局结局/线索/演示态');
  ok(sandbox.window.APP_DEF.template.includes('askLeave') && sandbox.window.APP_DEF.template.includes('返回主菜单'), '对局顶栏/设置可返回主菜单');
  ok(sandbox.window.APP_DEF.template.includes('aria-label="打开设置"'), '对局顶栏有可见设置按钮');
  S.phase = 'play'; S.clues = { clue_007: { at: 1 } }; S.ended = false;
  Store.leaveToMenu();
  ok(S.phase === 'menu' && S.clues.clue_007 && S.hasSave, '返回主菜单保留进度，不清档');
  const sfx = sandbox.window.SFX;
  ok(sfx && typeof sfx.play === 'function' && typeof sfx.sync === 'function' && typeof sfx.setMuted === 'function', 'SFX 音频层 API 可调用');
  sfx.play('ding'); sfx.sync(S); sfx.setMuted(true); sfx.setMuted(false);
  ok(true, 'SFX.play/sync/mute 在无 Audio 宿主不抛');
  const voice = sandbox.window.Voice;
  ok(voice && typeof voice.pause === 'function' && typeof voice.onState === 'function', 'Voice STT/TTS API 可调用');
  const rtc = sandbox.window.VoiceRTC;
  ok(rtc && typeof rtc.join === 'function' && typeof rtc.leave === 'function' && typeof rtc.onState === 'function', 'VoiceRTC mesh API 可调用');
  rtc.join({}); rtc.leave(); rtc.setMicOn(false); rtc.setSpeakerOn(true);
  ok(!rtc.isLive(), 'VoiceRTC 无 RTCPeerConnection 空操作');
  ok(sandbox.window.APP_DEF.template.includes('voice-rtc-dock') && sandbox.window.APP_DEF.template.includes('房间对讲'), 'party 对讲浮层与设置行已挂入');
  Net.send = oldSend;

  /* ===== [6] 空席 AI 事件：角色在行动，不当玩家自己 ===== */
  console.log('\n[6] 空席 AI applyEvent（角色在行动）');
  const prevPid = S.playerId;
  const prevAp = S.ap;
  const prevApMax = S.apMax;
  const prevKcards = Object.assign({}, S.kcards);
  const prevClues = Object.assign({}, S.clues);
  S.playerId = 'player:1';
  S.ap = 3;
  S.apMax = 3;
  const waitForChatText = async (text, timeout = 5000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const hit = S.chat.slice().reverse().find(line => line && line.text === text);
      if (hit) return hit;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    return null;
  };

  Store.applyEvent({
    type: 'chat', actor: 'ai:char_03',
    payload: { actor_kind: 'player', player_id: 'ai:char_03', text: '旧协议误判台词', char_id: 'char_01' }
  });
  const aiOld = await waitForChatText('旧协议误判台词');
  ok(aiOld && aiOld.actor === 'npc' && aiOld.name === '流量酱',
    'actor=ai:char_03 + actor_kind=player → npc/流量酱，不进 me');

  Store.applyEvent({
    type: 'chat', actor: 'player:ai:char_03',
    payload: { actor_kind: 'player', player_id: 'player:ai:char_03', text: '单人空席台词' }
  });
  const aiSolo = await waitForChatText('单人空席台词');
  ok(aiSolo && aiSolo.actor === 'npc' && aiSolo.name === '流量酱' && aiSolo.actor !== 'me',
    'actor=player:ai:char_03 → npc/流量酱');

  Store.applyEvent({
    type: 'chat', actor: 'ai:char_03',
    payload: { actor_kind: 'npc', booklet_act: true, booklet_role: 'char_03', char_id: 'char_03', text: '按本自我介绍', faction: 'swayable' }
  });
  const aiBook = await waitForChatText('按本自我介绍');
  ok(aiBook && aiBook.actor === 'npc' && aiBook.name === '流量酱' && aiBook.aiAct === true && !aiBook.faction,
    'booklet_act chat → npc 名=闭卷角色，不渲染 faction');

  Store.applyEvent({
    type: 'chat', actor: 'player:1',
    payload: { actor_kind: 'player', player_id: 'player:1', text: '我自己说的', char_id: 'char_02' }
  });
  const meLine = S.chat[S.chat.length - 1];
  ok(meLine && meLine.actor === 'me' && meLine.text === '我自己说的', '真人 player 发言仍进 me');

  const clueKeysBefore = Object.keys(S.clues).slice();
  Store.applyEvent({
    type: 'clue_gained', actor: 'ai:char_03',
    payload: {
      booklet_act: true, booklet_role: 'char_03',
      clue_id: 'clue_ai_private', name: 'AI私证', text: '不该进玩家袋',
      location: 'loc_monitor', keyword: '监控'
    }
  });
  const searchLine = S.chat[S.chat.length - 1];
  ok(!S.clues.clue_ai_private && Object.keys(S.clues).length === clueKeysBefore.length,
    'booklet_act clue_gained 不进玩家 state.clues');
  ok(searchLine && searchLine.actor === 'sys' && /流量酱去监控室搜了监控/.test(searchLine.text),
    'booklet_act 搜证 sys：某某去某地搜了某某');

  Store.applyEvent({
    type: 'search_result', actor: 'ai:char_03',
    payload: { booklet_act: true, booklet_role: 'char_03', hit: false }
  });
  const missLine = S.chat[S.chat.length - 1];
  ok(missLine && missLine.actor === 'sys' && missLine.text === '流量酱在现场搜证',
    'booklet_act search 无地点关键词 → 某某在现场搜证');

  Store.applyEvent({
    type: 'clue_gained', actor: 'ai:char_03',
    payload: {
      booklet_act: true, booklet_role: 'char_03', player_id: 'player:1',
      clue_id: 'clue_ai_for_me', name: '转交给我的', text: '可以进袋'
    }
  });
  ok(!!S.clues.clue_ai_for_me, 'booklet_act 但 player_id=当前玩家 → 线索仍入袋');

  const hadKc01 = !!S.kcards.kc_01;
  Store.applyEvent({
    type: 'faction_skill', actor: 'ai:char_03',
    payload: { booklet_act: true, booklet_role: 'char_03', kind: 'draw_card', kc_id: 'kc_01' }
  });
  const skillLine = S.chat[S.chat.length - 1];
  ok(skillLine && skillLine.actor === 'sys' && skillLine.text === '流量酱使用了技能',
    'booklet_act faction_skill → sys 某某使用了技能');
  ok(!!S.kcards.kc_01 === hadKc01 && S.ap === 3, 'AI 技能不记玩家卡/AP');

  Store.applyEvent({
    type: 'counsel_result', actor: 'ai:char_03',
    payload: { booklet_act: true, booklet_role: 'char_03', ok: true, reward: 'buff', char_id: 'char_06', kc_id: 'kc_02', lines: ['不该当玩家开导'] }
  });
  const counselLine = S.chat[S.chat.length - 1];
  ok(counselLine && counselLine.text === '流量酱使用了技能' && S.ap === 3 && S.apMax === 3,
    'booklet_act counsel_result → 技能一句，不加玩家 AP');

  Store.applyEvent({
    type: 'system', actor: 'ai:char_03',
    payload: { booklet_act: true, booklet_role: 'char_03', apDelta: -1 }
  });
  ok(S.ap === 3, 'AI system.apDelta 不扣玩家行动点');

  const sendLog = [];
  let aiActHit = false;
  const oldSend2 = Net.send.bind(Net);
  const oldFetch = sandbox.fetch;
  Net.send = (a, p) => { sendLog.push([a, p]); return true; };
  sandbox.fetch = (url) => {
    if (String(url).indexOf('ai_act') >= 0) aiActHit = true;
    return Promise.reject(new Error('no-net'));
  };
  S.busy = false; Store._sendQ = [];
  Store.send('chat', { char_id: 'char_01', text: '真人发言' });
  ok(!aiActHit && sendLog[0] && sendLog[0][0] === 'chat', 'Store.send 不 POST /ai_act（服务端动作后自动 wave）');
  Net.send = oldSend2;
  sandbox.fetch = oldFetch;

  ok(typeof Store.requestAiWave === 'function' && typeof Store.llmHeaders === 'function',
    '进局踢波 / LLM header 已导出');
  S.sessionId = 's_wave_live';
  S.netKind = 'ws';
  S.playerId = 'player:1';
  S.aiWaveKicked = '';
  S.demo = false;
  let waveHit = false;
  let waveHdr = {};
  sandbox.fetch = (url, opts) => {
    if (String(url).indexOf('ai_wave') >= 0) {
      waveHit = true;
      waveHdr = (opts && opts.headers) || {};
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, events: [], acted: ['char_01'] }) });
  };
  sandbox.localStorage.getItem = (k) => (k === 'kanshan_api'
    ? JSON.stringify({ llmKey: 'sk-test', llmBase: 'http://x/v1', llmModel: 'm' }) : null);
  await Store.requestAiWave();
  ok(waveHit && S.aiWaveKicked === 's_wave_live', 'liveSession 时 POST /ai_wave');
  ok(waveHdr['X-LLM-KEY'] === 'sk-test' && waveHdr['X-LLM-MODEL'] === 'm',
    '踢波带上设置面板 LLM header');
  sandbox.fetch = oldFetch;
  sandbox.localStorage.getItem = () => null;
  S.sessionId = '-';
  S.netKind = 'mock';
  S.aiWaveKicked = '';

  ok(VIEWS.chat.template.includes('m.name') && !VIEWS.chat.template.includes('faction'),
    '圆桌气泡用角色名，不渲染 faction');

  S.playerId = prevPid;
  S.ap = prevAp;
  S.apMax = prevApMax;
  S.kcards = prevKcards;
  S.clues = prevClues;
  delete S.clues.clue_ai_for_me;
  delete S.clues.clue_ai_private;

  console.log('\n[自我对话保护]');
  const identityBefore = { partyChar: S.partyChar, partySeats: S.partySeats, playerId: S.playerId,
    bookletRole: S.bookletRole, isSpectator: S.isSpectator, currentNpc: S.currentNpc, busy: S.busy };
  const ownRole = M.chars.find(c => c.id !== 'dm').id;
  const otherRole = M.chars.find(c => c.id !== 'dm' && c.id !== ownRole).id;
  Object.assign(S, { partyChar: ownRole, isSpectator: false, currentNpc: 'dm', busy: false });
  ok(!Store.selectChatTarget(ownRole) && S.currentNpc === 'dm', '不能选择自己的角色对话');
  ok(Store.selectChatTarget(otherRole) && S.currentNpc === otherRole, '仍能选择其他角色');
  const netSendBefore = Net.send;
  let delivered = 0;
  Net.send = () => { delivered++; return true; };
  ok(Store.send('chat', { target: ownRole, text: '不能发给自己' }) === false && !S.busy,
    '发送层阻止向自己发送，且不占用忙碌状态');
  ok(Store.send('chat', { target: 'dm', char_id: 'npc:' + ownRole, text: '别名不能绕过' }) === false && delivered === 0,
    '兼容目标别名，拦截前不调用传输层');
  const chatView = VIEWS.chat.setup();
  S.currentNpc = ownRole;
  chatView.input.value = '保留输入';
  chatView.send();
  ok(chatView.input.value === '保留输入' && delivered === 0, '自我对话被拒后保留输入');
  await Vue.nextTick();
  ok(S.currentNpc === 'dm', '旧存档或角色变化选中自己时自动回到 DM');
  ok(Store.send('chat', { target: otherRole, text: '正常提问' }) === true && delivered === 1,
    '其他角色仍可正常收取对话');
  S.partyChar = ''; S.playerId = 'player:selfcheck';
  S.partySeats = [{ player_id: S.playerId, char_id: ownRole }];
  ok(Store.playerCharacterId() === ownRole && !Store.selectChatTarget(ownRole), '房间席位恢复身份也禁止自我对话');
  S.partySeats = []; S.bookletRole = ownRole;
  ok(Store.playerCharacterId() === ownRole && !Store.selectChatTarget(ownRole), '角色本恢复身份也禁止自我对话');
  Net.send = netSendBefore;
  Object.assign(S, identityBefore);

  console.log('\n[分幕目标可见性回归]');
  const goalsBefore = Object.assign({}, S);
  const fetchBefore = sandbox.fetch;
  S.netKind = 'mock'; S.scenarioId = 'kanshan'; S.mode = 'solo'; S.partyChar = '';
  for (const rid of Object.keys(sandbox.BOOKLET_DATA).filter(id => id !== 'public')) {
    S.bookletRole = rid;
    for (let act = 1; act <= 3; act++) {
      S.act = act;
      await Store.hydrateBooklet();
      const asset = JSON.parse(fs.readFileSync(path.join(ROOT, '../content/scenarios/kanshan/booklets', rid + '.json'), 'utf8'));
      ok(JSON.stringify(Store.currentRoleGoals()) === JSON.stringify(asset.covers[['A','B','C'][act-1]].milestones)
        && Store.currentRoleGoals().length >= 2 && Object.keys(S.bookletPack.covers).length === act,
        rid + ' 第' + act + '幕任务与正式资产一致且未提前开封');
    }
  }
  S.act = 1; S.bookletRole = 'investigator'; S.sessionId = 'regression-only'; S.netKind = 'ws';
  const oldPack = JSON.parse(JSON.stringify(sandbox.Booklets.pack('investigator', 1)));
  delete oldPack.covers.A.milestones;
  sandbox.fetch = () => Promise.resolve({ok: true, json: () => Promise.resolve({booklet: oldPack})});
  await Store.hydrateBooklet();
  ok(Store.currentRoleGoals().length >= 2 && !S.bookletPack.covers.B, '旧服务端响应补齐本幕任务且不解锁后续幕');
  S.scenarioId = 'generated-test'; S.playerBook = {goals: ['新剧本独有目标']};
  ok(Store.currentRoleGoals()[0] === '新剧本独有目标', '创作剧本不串入看山案件任务');
  sandbox.fetch = fetchBefore;
  Object.assign(S, goalsBefore);

  console.log(`\n=== E 组 V31 无头冒烟：${pass} PASS / ${fail} FAIL ===`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('SMOKE CRASH:', e); process.exit(2); });
