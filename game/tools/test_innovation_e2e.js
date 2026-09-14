/* Headless E2E for the 创新冲刺 features (A/B/C/D).
 * 复用 store.js 内部 Engine→applyEvent 管线（与 MockTransport 一致），验证运行期行为。
 * 用法：node tools/test_innovation_e2e.js
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', 'frontend', 'js');

// ---- 最小浏览器 API 模拟 ----
const store = {};
const sandbox = {
  console,
  setTimeout: (fn) => { try { fn(); } catch (e) {} },
  clearTimeout: () => {},
  URLSearchParams: URLSearchParams,
  location: { origin: 'http://localhost', search: '', href: '' },
  navigator: { clipboard: null },
  document: { getElementById: () => null, createElement: () => ({ getContext: () => ({}), toBlob: () => {} }), body: { appendChild() {}, removeChild() {} } },
  fetch: async () => ({ ok: false, json: async () => ({}) }),
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } },
  Vue: {
    reactive: (o) => o,
    ref: (v) => ({ value: v }),
    computed: (f) => f,
    watch: () => {},
    createApp: () => ({ mount() {}, component() {}, config: {} }),
    onMounted: () => {},
  },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function load(file) {
  const code = fs.readFileSync(path.join(ROOT, file), 'utf8');
  vm.runInContext(code, sandbox, { filename: file });
}

let failures = 0;
const assert = (cond, msg) => { if (!cond) { failures++; console.log('  ✗ ' + msg); } else { console.log('  ✓ ' + msg); } };

try {
  load('data.js');
  load('store.js');
} catch (e) {
  console.log('LOAD ERROR:', e.message);
  process.exit(1);
}

const Store = sandbox.window.Store;
const M = sandbox.window.MOCK;
const state = Store.state;
assert(!!Store && !!M, 'data.js + store.js 加载成功');

// emit 直接走 applyEvent（与 MockTransport 同管线）
const emit = (type, pl) => Store.applyEvent({ type, payload: pl || {} });

console.log('\n[A] 信息茧房：入茧 → 破茧');
state.ap = 5;
// 制造偏执画像：直接给 searchBias 灌 2 次命中，再搜一次触发入茧
state.searchBias = { 热搜: 2 };
Store.send ? null : null;
// 走 Engine 内部（不经 Net）：用暴露的 window.Engine 包装
sandbox.window.Engine('search', { location: '监控室', keyword: '看山' }, emit);
assert(state.cocoon.active === true, '偏执达到阈值 → 自动入茧 (cocoon.active)');
const before = state.cocoon.broken;
sandbox.window.Engine('cocoon_break', {}, emit);
assert(state.cocoon.broken === before + 1, '破茧动作使 broken+1');
assert(typeof state.cocoon.revealed === 'number' && state.cocoon.revealed >= 0, '破茧解封真相帖计数 revealed 已计算 (' + state.cocoon.revealed + ')');

console.log('\n[B] 证据拼图：钉线索 → 覆盖度');
// 找一个真实线索并搜到手
const sample = M.clues.find(c => c.linked && c.linked.length);
assert(!!sample, '存在带 linked 的真实线索 (' + (sample ? sample.id : '?') + ')');
state.clues[sample.id] = { at: 1 };
sandbox.window.Engine('evidence_pin', { clueId: sample.id }, emit);
assert(state.evidenceLinks.some(l => l.clueId === sample.id), 'evidence_pin 后 evidenceLinks 含该线索');
const cov1 = Store.evidenceCoverage();
assert(cov1.total >= 1, 'evidenceCoverage 节点数 >= 1 (' + cov1.total + ')');

// 拼到 ≥50% 核心节点，用于后续策反门控
let pinned = 0;
for (const c of M.clues) {
  if (Store.evidenceCoverage().pct >= 50) break;
  if (!state.clues[c.id]) { state.clues[c.id] = { at: 1 }; sandbox.window.Engine('evidence_pin', { clueId: c.id }, emit); pinned++; }
}
const cov2 = Store.evidenceCoverage();
assert(cov2.pct >= 50, '钉入足够线索后核心覆盖度 ≥50% (' + cov2.pct + '%, 共钉 ' + pinned + ' 条)');

console.log('\n[C] 阵营博弈：策反被裹挟者（门控 ≥50%）');
const dBefore = state.defection['char_03'] && state.defection['char_03'].flipped;
sandbox.window.Engine('defect', { charId: 'char_03' }, emit);
assert(state.defection['char_03'] && state.defection['char_03'].flipped === true, '证据充足 → char_03 流量酱 策反成功');
// 反例：不该能策反非被裹挟者
const fb = { threw: false };
try { sandbox.window.Engine('defect', { charId: 'char_01' }, emit); } catch (e) { fb.threw = true; }
assert(!state.defection['char_01'], '非被裹挟者 (char_01) 不被策反');

console.log('\n[D] 求真人格卡：结局时由 buildReport 生成');
state.report = null;
Store.applyEvent({ type: 'ending', payload: { ending_id: 'truth' } });
assert(state.persona && state.persona.name, '结局触发后生成 persona 卡：' + (state.persona ? state.persona.name : 'null'));
assert(state.persona.broke === true, 'persona.broke 反映已破茧=true');
assert(state.persona.flips >= 1, 'persona.flips 反映策反次数=' + state.persona.flips);
assert(state.persona.evidencePct >= 50, 'persona.evidencePct=' + state.persona.evidencePct);

console.log('\n[E] 评委线起步包');
state.phase = 'play'; state.netKind = 'mock'; state.ended = false; state.demo = false;
state.clues = {}; state.evidenceLinks = [];
Store.startJudgeLine();
assert(Store.evidenceCoverage().pct >= 50, '评委线开局覆盖 ≥50% (' + Store.evidenceCoverage().pct + '%)');

console.log('\n' + (failures ? ('❌ 失败 ' + failures + ' 项') : '✅ 全部通过') + ' (A/B/C/D/E E2E)');
process.exit(failures ? 1 : 0);
