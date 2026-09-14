const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '../frontend/js');
const ctx = { console, URLSearchParams, location: { search: '' },
  localStorage: { getItem: () => null, setItem() {} },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0,
  Vue: { reactive: x => x, watch() {}, ref: x => ({ value: x }),
    computed: f => ({ get value() { return f(); } }), nextTick: async () => {} },
};
ctx.window = ctx;
ctx.VIEWS = {};
vm.createContext(ctx);
for (const f of ['data.js', 'store.js', 'views/chat.js', 'views/memory.js', 'views/hotfeed.js']) vm.runInContext(fs.readFileSync(path.join(root, f), 'utf8'), ctx);
const store = ctx.Store, s = store.state;
Object.assign(s, { sessionId: 'social', netKind: 'ws', playerId: 'player:7', mode: 'solo', partyChar: 'char_01', demo: false, ended: false });
const ui = ctx.VIEWS.chat.setup();
let requests = [], responseEvents = [];
ctx.fetch = async (url, options) => {
  requests.push({ url, body: JSON.parse(options.body) });
  return { ok: true, json: async () => ({ events: responseEvents, count: 1 }) };
};
(async () => {
  assert.equal(ui.canWhisper.value, true, 'single player must see private chat');
  assert(ui.whisperTargets.value.some(p => p.id === 'npc:char_02'));
  responseEvents = [
    { type: 'chat', session_id: 'social', actor: 'player:7', payload: { message_id: 'p', actor_kind: 'player', player_id: 'player:7', whisper: true, to: 'npc:char_02', char_id: 'char_02', text: '你好' } },
    { type: 'chat', session_id: 'social', actor: 'npc:char_02', payload: { message_id: 'n', actor_kind: 'npc', whisper: true, to: 'player:7', char_id: 'char_02', text: '我在这里' } },
  ];
  ui.whisperOn.value = true; ui.whisperTo.value = 'npc:char_02'; ui.input.value = '你好';
  await ui.send();
  assert(requests[0].url.endsWith('/npc-whisper'));
  assert.equal(ui.input.value, '');
  assert.equal(ui.shown.value.filter(m => m.whisper).length, 2, 'both private messages render');
  const count = s.chat.length;
  await store.npcWhisper('npc:char_02', '你好');
  assert.equal(s.chat.length, count, 'HTTP / websocket duplicate events deduplicate');
  responseEvents = [{ type: 'chat', session_id: 'social', actor: 'npc:char_03', payload: { message_id: 'wave', actor_kind: 'npc', char_id: 'char_03', wave: true, text: '大家先核对口供' } }];
  s.currentNpc = 'dm';
  await store.requestNpcWave();
  assert.equal(requests.at(-1).body.player_id, 'player:7');
  assert(ui.shown.value.some(m => m.wave), 'wave shows regardless of selected NPC');
  assert.equal(s.npcWaveBusy, false);
  ctx.fetch = async () => ({ ok: false, json: async () => ({ detail: 'AI 配置缺失' }) });
  ui.input.value = '失败后保留输入'; await ui.send();
  assert.equal(ui.input.value, '失败后保留输入');
  assert.equal(ui.sendingPrivate.value, false);
  s.partySeats = [{ player_id: 'player:2', char_id: 'char_02', connected: true }];
  assert(!ui.whisperTargets.value.some(p => p.id === 'npc:char_02'), 'human seat not listed as AI');
  console.log('PASS: single-player entry, HTTP routing, private rendering, deduplication, wave visibility, failure recovery, human-seat exclusion');
  const sent = [];
  ctx.Net = { send: (action, payload) => { sent.push({ action, payload }); return true; } };
  s.busy = false;
  store.applyEvent({ type: 'memory_unlock', payload: { source: 'engine', owner: 'npc:char_04', unlocked_version: 2,
    blocks: [{ id: 'm1', time: '21:00', text: '在走廊', layer: 'said' }, { id: 'm2', time: '21:10', text: '听见脚步', layer: 'heart' }], heart_unlocked: true, tamper_available: 3, can_repair: true } });
  assert.equal(s.memVer.char_04, 2);
  assert.equal(s.liveMemories.char_04.blocks.length, 2);
  const memory = ctx.VIEWS.memory.setup();
  assert.equal(memory.heart.value.length, 1);
  memory.repair('char_03');
  assert.equal(sent.at(-1).payload.target, 'char_03', 'repair targets clicked card');
  memory.sel.value = 'char_04'; s.busy = false;
  memory.openPuzzle(); memory.submitPuzzle();
  assert.equal(sent.at(-1).payload.skill, 'puzzle');
  assert.deepEqual(Array.from(sent.at(-1).payload.proposal).sort(), ['m1', 'm2']);
  assert(!('ok' in sent.at(-1).payload), 'client never declares the verdict');
  store.applyEvent({ type: 'system', payload: { event: 'puzzle_result', char_id: 'char_04', correct: true, tamper_available: 1, notice: '正确' } });
  assert.equal(s.tamperPts, 1);
  assert.equal(s.memoryPuzzleResult.correct, true);
  store.applyEvent({ type: 'counsel_result', actor: 'player:7', payload: { source: 'engine', target: 'npc:char_04', card: 'kc_03', matched: true } });
  assert.equal(s.counsel.at(-1).char_id, 'char_04');
  assert.equal(s.counsel.at(-1).ok, true);
  s.busy = false; store.send('counsel', { char_id: 'char_02', kc_id: 'kc_01' });
  assert.equal(sent.at(-1).payload.target, 'char_02');
  assert.equal(sent.at(-1).payload.card, 'kc_01');
  s.busy = false; s.act = 3; s.ap = 4;
  const hot = ctx.VIEWS.hotfeed.setup();
  hot.pickPost({ id: 'post_001', title: '帖子一' }); hot.bidAmount.value = 2; hot.doBid();
  assert.equal(sent.at(-1).payload.post, 'post_001');
  assert.equal(sent.at(-1).payload.amount, 2);
  store.applyEvent({ type: 'system', payload: { event: 'heat_report', heat: 80, blocked_clues: ['c1'], text: '当前热度80' } });
  assert.equal(s.heatReport.blocked, 1);
  store.applyEvent({ type: 'system', payload: { event: 'stage_changed', stage: 'accuse', actions_left: 5 } });
  assert.equal(s.stage, 'accuse'); assert.equal(s.ap, 5);
  console.log('PASS: live memory, selected repair target, server puzzle verdict, counsel field mapping, headline post/amount, heat report, stage/AP sync');
})().catch(e => { console.error(e); process.exitCode = 1; });
