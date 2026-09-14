// AI 来源徽章映射契约守护（chat payload.ai_provider → 徽章文案）。
// 运行：node tests/reply_badge_ui.cjs
//
// 为什么不整组件挂载：chat.js 的 setup() 依赖全局 S/M/L/Store 与网络层，
// 这里锁定真正会被评委看到的映射表本身（契约层），避免为跑一条断言搭整套应用壳。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.resolve(__dirname, '../frontend/js/views/chat.js'), 'utf8');
const m = src.match(/const aiSrcBadge = \(p\) => \{[\s\S]*?\n {6}\};/);
assert.ok(m, 'chat.js 未找到 aiSrcBadge 定义（改名/移动需同步本测试）');
const aiSrcBadge = eval('(' + m[0].replace(/^const aiSrcBadge = /, '').replace(/;$/, '') + ')');

const cases = [
  ['zhida', '知乎直答'],
  ['zhida(cache)', '缓存'],
  ['main', '自建模型'],
  ['mock', '本地'],
  ['fallback', '兜底'],
  ['', 'AI'],
  [null, 'AI'],
];
for (const [input, expected] of cases) {
  const got = aiSrcBadge(input);
  assert.equal(got.text, expected, `ai_provider=${JSON.stringify(input)} 期望「${expected}」，实际「${got.text}」`);
}
// 缓存必须优先于通道名（provider 形如 zhida(cache)）
assert.equal(aiSrcBadge('zhida(cache)').cls, 'blue');
assert.equal(aiSrcBadge('zhida').cls, 'good');
assert.equal(aiSrcBadge('main').cls, 'blue');
console.log('reply_badge_ui: ' + cases.length + ' 项映射断言全部通过');
