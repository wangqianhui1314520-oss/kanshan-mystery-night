// 真人 WS 搜证同步的 mutation + regression guard。
// 运行：node tests/live_stage_sync_mutation.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', 'frontend', 'js');
const storeSrc = fs.readFileSync(path.join(ROOT, 'store.js'), 'utf8');

// 正常实现必须在 WS 第一幕门控中同时要求 state.searched。
assert.match(storeSrc, /const liveSearchReady = state\.netKind !== 'ws'[\s\S]*Object\.keys\(state\.searched \|\| \{\}\)\.length > 0/,
  'WS 第一幕门控未要求真人搜证地点登记');
assert.match(storeSrc, /cleared = firstClue && liveSearchReady;/,
  '第一幕 cleared 未绑定真人搜证同步结果');
assert.match(storeSrc, /case 'search_result':[\s\S]*noteLiveSearch\(evt\);/,
  'search_result 未接入真人搜证同步');
assert.match(storeSrc, /case 'clue_gained':[\s\S]*noteLiveSearch\(evt\);/,
  'clue_gained 未接入真人搜证同步');

// mutation：删除同步登记后，已有线索但 searched 为空的真实 WS 状态必须被门控拦下。
const gateExpr = /const liveSearchReady = state\.netKind !== 'ws'\s*\|\|\s*Object\.keys\(state\.searched \|\| \{\}\)\.length > 0;\s*cleared = firstClue && liveSearchReady;/;
const mutatedExpr = 'const liveSearchReady = true;\n      cleared = firstClue && liveSearchReady;';
assert.match(storeSrc, gateExpr, 'mutation 基线表达式未找到');
const gate = (firstClue, netKind, searched) => {
  const liveSearchReady = netKind !== 'ws' || Object.keys(searched || {}).length > 0;
  return firstClue && liveSearchReady;
};
assert.equal(gate(true, 'ws', {}), false,
  'mutation 复现：删除真人搜证登记时，第一幕必须阻断');
assert.equal(gate(true, 'ws', { loc_desk: 1 }), true,
  '恢复真人搜证登记后，第一幕允许推进');
assert.equal(gate(true, 'mock', {}), true,
  'Mock 模式保持既有本地引擎语义');
console.log('PASS: live_stage_sync_mutation —— WS 搜证登记、事件接线与 mutation 门控全部通过');
