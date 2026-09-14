// DM 任务卡「打开并阅读本幕剧本」进度打勾契约守护 + mutation test。
// 运行：node tests/dm_task_book_read_ui.cjs
//
// 背景 Bug（2026-09-14 玩家截图）：break_ice 任务卡第 2 步读完剧本不打勾。
// 根因：勾选条件只看瞬态 S.playerBook || S.bookletOpen——看山局 playerBook
// 恒为 null（走 bookletPack），bookletOpen 在 bookletDismiss() 后复位 false，
// 于是"读完并关掉剧本"后进度回退为未完成。游戏本就有持久读本标记
// state.dmBookRead（openBooklet 成功后置 true，iceBlocksSearch 门控同源），
// 但①任务卡条件没用它，②强制弹出的剧本（bookletForced='A'）关闭路径从未置位。
// 修复：main.js 条件加 S.dmBookRead；store.js bookletDismiss 有剧本内容时补置 dmBookRead。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..', 'frontend');

/* ---------- DOM-less 宿主（同 optimization_contract.cjs） ---------- */
const ctx = {
  console, URLSearchParams,
  setTimeout: () => 0, clearTimeout() { }, setInterval: () => 0, clearInterval() { },
  localStorage: { getItem: () => null, setItem() { }, removeItem() { } },
  sessionStorage: { getItem: () => null, setItem() { }, removeItem() { } },
  location: { search: '', hash: '', origin: 'http://localhost', pathname: '/' },
  navigator: {},
  document: {
    createElement: () => ({ set innerHTML(v) { this.textContent = v.replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&'); } }),
    addEventListener() { }, documentElement: { style: { setProperty() { } } }
  },
  addEventListener() { }
};
ctx.window = ctx; ctx.globalThis = ctx; vm.createContext(ctx);
const load = rel => vm.runInContext(fs.readFileSync(path.join(ROOT, rel), 'utf8'), ctx, { filename: rel });
load('js/vendor/vue.global.prod.js');
load('js/data.js');
load('js/booklets.js');
load('js/store.js');
const Store = ctx.Store;
const S = Store.state;

/* ---------- [1] 实跑：强制弹本（break_ice 标准流程）读完关闭 → 读本标记必须置位 ---------- */
console.log('[1] 实跑 store.js：bookletForced 强制读本 → 关闭 → dmBookRead 置位');
S.scenarioId = 'kanshan'; S.act = 1; S.stage = 'break_ice';
S.bookletRole = 'char_01'; S.playerBook = null;
S.dmBookRead = false; S.bookletOpen = false; S.bookletForced = null;
S.studioNeedAdvance = false; S.studioBooks = [];
S.chat = [{ actor: 'npc', text: '各位，我是 DM。' }];   // 步骤 1 已达成的前置

// 复刻 showtimeNext() 破冰入场的强制弹本动作（store.js 同款两行）
S.bookletForced = 'A';
S.dmBookRead = false;                                    // 旧代码下强制路径从不置位
Promise.resolve(Store.hydrateBooklet()).then(() => {
  assert.ok(S.bookletPack && S.bookletPack.covers, 'hydrateBooklet 本地闭包已灌入');
  // 玩家读完点「关闭」
  Store.bookletDismiss();
  assert.equal(S.bookletForced, null, '强制弹窗已收起');
  assert.equal(S.bookletOpen, false, '弹层已关闭');
  assert.equal(S.dmBookRead, true, '修复点①：关闭带内容的剧本 = 已读本幕（dmBookRead 置位）');

  /* ---------- [2] 实跑：读本标记与搜证门控同源同步 ---------- */
  console.log('[2] 实跑：iceBlocksSearch 门控与读本标记同步（不误伤、不放水）');
  S.dmBookRead = false;
  assert.equal(Store.iceBlocksSearch(), true, '未读本 → 搜证仍被破冰门控拦截');
  S.dmBookRead = true;
  assert.equal(Store.iceBlocksSearch(), false, '已读本 + NPC 已发言 → 搜证放行');

  /* ---------- [3] 实跑：手动开本路径（阅读我的剧本按钮）状态不回退 ---------- */
  console.log('[3] 实跑：openBooklet → bookletDismiss 全链路');
  S.dmBookRead = false; S.bookletOpen = false;
  return Promise.resolve(Store.openBooklet()).then(opened => {
    assert.equal(opened, true, 'openBooklet 成功（本地闭包就绪）');
    assert.equal(S.dmBookRead, true, 'openBooklet 成功即置位（原有语义保持）');
    Store.bookletDismiss();
    assert.equal(S.dmBookRead, true, '修复点①旁证：关闭后标记不回退');
  });
}).then(() => {
  /* ---------- [4] 契约 + mutation test：任务卡勾选条件 ---------- */
  console.log('[4] 契约 + mutation：main.js 勾选条件表达式');
  const mainSrc = fs.readFileSync(path.join(ROOT, 'js/main.js'), 'utf8');
  const m = mainSrc.match(/text: '打开并阅读本幕剧本', done: !!\(([^)]*)\)/);
  assert.ok(m, 'main.js 未找到 break_ice 任务卡第 2 步条件（改名/移动需同步本测试）');
  const newExpr = m[1];
  assert.ok(/S\.dmBookRead/.test(newExpr), '修复点②：勾选条件必须包含持久标记 S.dmBookRead');

  // mutation：旧表达式 = git HEAD 上的原实现（bug 版本），同状态求值必须复现"读完不打勾"
  const oldExpr = 'S.playerBook || S.bookletOpen';       // HEAD main.js:205 原文
  const postRead = { dmBookRead: true, playerBook: null, bookletOpen: false };  // 读完关闭后的真实状态
  const evalIn = (expr, st) => vm.runInContext('!!(' + expr + ')', vm.createContext({ S: st }));
  assert.equal(evalIn(oldExpr, postRead), false, 'mutation 复现 Bug：旧条件在「已读完」状态下判 false（进度不变）');
  assert.equal(evalIn(newExpr, postRead), true, '修复后同状态判 true（进度正常打勾）');

  // regression guard：store.js 关闭路径置位不可被移除
  const storeSrc = fs.readFileSync(path.join(ROOT, 'js/store.js'), 'utf8');
  assert.match(storeSrc, /bookletDismiss\(\) \{ state\.bookletForced = null; state\.bookletOpen = false; if \(state\.bookletPack \|\| state\.playerBook\) state\.dmBookRead = true; \}/,
    'store.js bookletDismiss 的 dmBookRead 置位语句缺失（防回退）');

  console.log('\nPASS: dm_task_book_read_ui —— 实跑 3 链路 + 契约 2 项 + mutation 复现 1 项全部通过');
}).catch(e => { console.error('FAIL:', e.message); process.exitCode = 1; });
