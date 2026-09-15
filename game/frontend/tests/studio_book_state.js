#!/usr/bin/env node
/* Studio 故事本领取回归：pending 门控、成功入席、失败回滚。 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const storage = new Map();
const session = new Map();
const timers = new Set();
const delayed = (fn, ms) => {
  const id = setTimeout(() => { timers.delete(id); fn(); }, ms);
  timers.add(id);
  return id;
};
const clearDelayed = id => { timers.delete(id); clearTimeout(id); };
const makeStorage = map => ({
  getItem: key => map.has(key) ? map.get(key) : null,
  setItem: (key, value) => map.set(key, String(value)),
  removeItem: key => map.delete(key),
});
const context = {
  console,
  setTimeout: delayed,
  clearTimeout: clearDelayed,
  setInterval,
  clearInterval,
  URL,
  URLSearchParams,
  Math,
  Date,
  JSON,
  Promise,
  Object,
  Array,
  String,
  Number,
  Boolean,
  Error,
  Set,
  Map,
  localStorage: makeStorage(storage),
  sessionStorage: makeStorage(session),
  location: { protocol: 'file:', search: '', pathname: '/', href: 'file:///test/' },
  history: { replaceState() {} },
  document: { addEventListener() {}, removeEventListener() {}, activeElement: null },
  SFX: { play() {}, sync() {}, setMuted() {} },
  UX: {},
  fetch: () => Promise.reject(new Error('fetch not configured')),
};
context.window = context;
context.globalThis = context;
vm.createContext(context);
const load = rel => vm.runInContext(
  fs.readFileSync(path.join(ROOT, rel), 'utf8'),
  context,
  { filename: rel }
);
// The state-machine regression does not render templates, so a tiny Vue host
// keeps the test focused on Store behavior and avoids a browser renderer.
context.Vue = { reactive: value => value, watch: () => {} };
load('js/data.js');
load('js/booklets.js');
load('js/store.js');

const Store = context.Store;
const S = Store.state;
const book = id => ({
  char_id: id,
  name: id === 'char_02' ? '笔上仙' : '流量酱',
  archetype: '测试角色',
  you_are: '这是领取成功后的私密故事本。',
  goals: ['完成测试目标'],
  secrets: ['测试秘密'],
});
const cover = id => ({ char_id: id, name: id, archetype: '测试角色', you_are: '封面' });

function setupSeat(previousId, previousBook) {
  S.phase = 'seat';
  S.mode = 'party';
  S.playMode = 'main';
  S.scenarioId = 'gen_state_test';
  S.studioBooks = [cover('char_01'), cover('char_02'), cover('char_03')];
  S.partyChar = previousId;
  S.playerBook = previousBook;
  S.studioBookLoading = '';
  S.studioBookError = '';
  session.clear();
  if (previousId) session.set('party_char', previousId);
}

async function run() {
  // 静态门控契约：模板必须将 pending 和无故事本都映射为 disabled。
  const mainSource = fs.readFileSync(path.join(ROOT, 'js', 'main.js'), 'utf8');
  assert.match(mainSource, /:disabled="!!S\.studioBookLoading \|\| !S\.playerBook"/);
  assert.match(mainSource, /@click="!S\.studioBookLoading && Store\.pickStudioChar\(b\.char_id\)"/);
  assert.match(mainSource, /故事本领取中…/);

  const previous = book('char_01');
  setupSeat('char_01', previous);
  let resolveFetch;
  context.fetch = () => new Promise(resolve => { resolveFetch = resolve; });
  const pending = Store.pickStudioChar('char_02');
  await Promise.resolve();
  assert.equal(S.studioBookLoading, 'char_02');
  assert.equal(S.playerBook, null);
  assert.equal(Store.studioBookPending('char_02'), true);
  assert.equal(await Store.pickStudioChar('char_03'), false, 'pending 时不能切换角色');
  assert.equal(S.partyChar, 'char_02');
  assert.equal(Store.startPrologue(), false, 'pending 时确认必须被状态机拒绝');
  assert.equal(S.phase, 'seat');

  resolveFetch({ ok: true, json: async () => ({ ok: true, book: book('char_02') }) });
  assert.equal(await pending, true);
  assert.equal(S.studioBookLoading, '');
  assert.equal(S.playerBook.char_id, 'char_02');
  assert.equal(session.get('party_char'), 'char_02');
  Store.startPrologue();
  assert.equal(S.phase, 'prologue', '领取成功后确认进入序章');

  setupSeat('char_01', previous);
  let rejectFetch;
  context.fetch = () => new Promise((resolve, reject) => { rejectFetch = reject; });
  const failed = Store.pickStudioChar('char_03');
  await Promise.resolve();
  assert.equal(S.studioBookLoading, 'char_03');
  rejectFetch(new Error('offline'));
  assert.equal(await failed, false);
  assert.equal(S.studioBookLoading, '');
  assert.equal(S.partyChar, 'char_01', '失败后恢复原角色');
  assert.equal(S.playerBook, previous, '失败后恢复原故事本');
  assert.equal(session.get('party_char'), 'char_01', '失败后恢复原 sessionStorage 身份');
  assert.match(S.studioBookError, /领取故事本失败/);
  assert.equal(Store.startPrologue(), undefined, '失败后仍可用已恢复故事本确认');
  assert.equal(S.phase, 'prologue', '失败回滚后旧故事本仍可进入序章');

  console.log('PASS studio book state: pending lock, success prologue entry and failure rollback');
}
run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
