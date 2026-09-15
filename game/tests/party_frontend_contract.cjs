// 联机前端 UX 契约守护：房间入口、AI 降级说明、分享边界、席位状态。
// 运行：node tests/party_frontend_contract.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../frontend');
const main = fs.readFileSync(path.join(root, 'js/main.js'), 'utf8');
const ux = fs.readFileSync(path.join(root, 'css/ux.css'), 'utf8');
const v31 = fs.readFileSync(path.join(root, 'css/v31.css'), 'utf8');

assert.match(main, /class="btn-start party-entry"/);
assert.match(main, /邀请好友 · AI 补位 · 实时同步/);
assert.match(main, /规则引擎仍可正常裁决；AI 对话未配置时/);
assert.match(main, /同一 WiFi 可直接打开/);
assert.match(main, /seat-status/);
assert.match(main, /statusLabel/);
assert.match(ux, /\.ai-status-card\.missing/);
assert.match(ux, /\.ux-conn\.restoring/);
assert.match(v31, /\.seat-status-takeover/);
assert.match(v31, /\.party-entry/);
console.log('party_frontend_contract: PASS（入口、AI 状态、分享边界、席位状态）');
