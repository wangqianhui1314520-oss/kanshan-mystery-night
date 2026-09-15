// Party 自动重连契约守护：网络恢复后必须触发幂等 /join，且失败要显示 AI 接管提示。
// 运行：node tests/party_reconnect_ui.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../frontend/js');
const net = fs.readFileSync(path.join(root, 'net.js'), 'utf8');
const store = fs.readFileSync(path.join(root, 'store.js'), 'utf8');
const main = fs.readFileSync(path.join(root, 'main.js'), 'utf8');

assert.match(net, /const reconnected = !!this\.bootedOnce/);
assert.match(net, /reconnected \? '实时通道已恢复，正在恢复席位' : '实时通道已建立'/);
assert.match(net, /reconnected: reconnected/);
assert.match(store, /async function restorePartySeat\(\)/);
assert.match(store, /partySeatRecoveryPromise/);
assert.match(store, /\/api\/session\/.*\/join/);
assert.match(store, /mine\.connected === false \|\| mine\.is_ai \|\| mine\.ai_takeover/);
assert.match(main, /st\.state === 'online' && st\.reconnected/);
assert.match(main, /restorePartyAfterReconnect\(\)/);
assert.match(main, /角色仍由 AI 接管/);

// mutation：删除重连后的 /join 恢复时，守护必须失败。
const joinBlock = store.match(/async function restorePartySeat\(\)[\s\S]*?partySeatRecoveryPromise = null;/);
assert.ok(joinBlock, '未找到 restorePartySeat 完整实现');
assert.match(joinBlock[0], /method: 'POST'/);
assert.match(joinBlock[0], /role: 'player'/);
console.log('party_reconnect_ui: PASS（重连标记、单飞 /join、席位校验、失败提示）');
