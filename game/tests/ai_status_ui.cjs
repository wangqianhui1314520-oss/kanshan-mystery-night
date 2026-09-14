// Exercise health -> reactive state and compile actual Vue templates without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const front = path.resolve(__dirname, '../frontend');
const context = vm.createContext({setTimeout, clearTimeout, AbortController, console});
context.window = {Store: {state: {sessionId: 'test_session'}}};
vm.runInContext(fs.readFileSync(path.join(front, 'js/vendor/vue.global.prod.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(front, 'js/ux.js'), 'utf8'), context);
const ux = context.window.UX;
async function health(data) {
  context.fetch = async url => { assert.equal(url, '/api/health?session_id=test_session'); return {ok: true, json: async () => data}; };
  await ux.probeEngine();
}
(async () => {
  await health({engine: {mode: 'engine', available: true}, ai: {state: 'configured', npc_provider: '知乎直答'}});
  assert.equal(ux.ai.label, 'AI 已配置 · 待验证');
  assert.equal(ux.engine.probe, 'ok');
  await health({engine: {mode: 'engine', available: false}, ai: {state: 'failed'}});
  assert.equal(ux.engine.probe, 'degraded');
  assert.equal(ux.ai.state, 'failed');
  await health({engine: {mode: 'engine'}});
  assert.equal(ux.ai.state, 'unknown');
  assert.match(ux.ai.detail, /重启/);
  context.fetch = async () => { throw Error('offline'); };
  await ux.probeEngine();
  assert.equal(ux.ai.state, 'offline');
  assert.equal(ux.ai.seats.length, 0);
  let warnings = [];
  context.console = {...console, warn: (...args) => warnings.push(args.join(' '))};
  const main = fs.readFileSync(path.join(front, 'js/main.js'), 'utf8');
  const template = main.slice(main.indexOf('template: `') + 'template: `'.length, main.lastIndexOf('`'));
  assert.match(template, /ai-status-card/);
  assert.match(template, /NPC AI/);
  context.Vue.compile(template, {decodeEntities: value => value.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')});
  assert.deepEqual(warnings, []);
  console.log('PASS: AI configuration, failure, old backend, offline reset, Vue template compilation');
})().catch(e => {console.error(e); process.exitCode = 1;});
