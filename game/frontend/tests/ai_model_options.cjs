/* 前端契约守护：设置面板的 DeepSeek 模型名必须与上游 /models 实测一致。
 *
 * 背景（2026-09-15 实跑取证）：面板曾写死 deepseek-chat / deepseek-v4-flash，
 * 而 DeepSeek 现网 /models 只返回 deepseek-flash 与 deepseek-v4-pro——玩家照面板
 * 选完保存，请求必然失败（模型不存在）。模型名是外部契约，改动必须由这里兜住。
 *
 * 运行：node frontend/tests/ai_model_options.cjs
 */
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const mainSrc = fs.readFileSync(path.join(root, 'js', 'main.js'), 'utf8');

let pass = 0, fail = 0;
function ok(cond, name, extra) {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra ? ' — ' + extra : '')); }
}

// DeepSeek 官方 /models 实测可用 id（2026-09-15）
const REAL = ['deepseek-flash', 'deepseek-v4-pro'];
// 历史遗留/虚构 id：出现即判失败
const STALE = ['deepseek-chat', 'deepseek-v4-flash', 'deepseek-coder'];

console.log('AI 模型选项契约：');

const section = mainSrc.split('DeepSeek（需填 API Key）')[1] || '';
const options = [...section.matchAll(/<option value="([^"]+)"/g)].map(m => m[1]);

ok(options.length > 0, '面板存在 DeepSeek 模型选项', 'options=' + JSON.stringify(options));
for (const id of REAL) {
  ok(options.includes(id), `面板包含实测可用模型 ${id}`, 'options=' + JSON.stringify(options));
}
for (const id of STALE) {
  ok(!options.includes(id), `面板不含已失效模型 ${id}`, 'options=' + JSON.stringify(options));
}
// 端点自动切换：所有 DeepSeek 模型都要能命中 api.deepseek.com 分支
ok(/m\.indexOf\('deepseek'\)\s*===\s*0/.test(mainSrc),
  'onModelChange 仍按 deepseek 前缀切换端点');

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
