/* 回归守护：第一幕 DM 任务清单「关键线索」判定必须覆盖引擎 canonical 第一幕键集。
 * 背景：main.js dmTasks 第一幕第二项曾只判 clue_021||clue_028，而真实引擎模式下
 * 引擎 clue_028 会被 migrateEngineClues() 迁移为 UI 键 clue_001，导致任务永不勾选，
 * 与 engine_driver.py PARTY_CH1_KEYS（7 键）门控脱节。此测试防止回退。 */
const fs = require('fs');
const assert = require('assert/strict');
const path = require('path');
const mainSrc = fs.readFileSync(path.resolve(__dirname, '../js/main.js'), 'utf8');

// 1) 定位第一幕 dmTasks 的「关键线索」判定行
const m = mainSrc.match(/\{ text: '取得第一幕关键线索[^']*', done: !!\(S\.clues && \[([^\]]+)\]\.some\(k => S\.clues\[k\]\)\) \}/);
assert.ok(m, '未找到第一幕关键线索判定行（main.js dmTasks act===1）');

// 2) 判定键集必须与 server/engine_driver.py PARTY_CH1_KEYS 一致（7 键）
const keys = m[1].split(',').map(s => s.trim().replace(/^'|'$/g, '')).sort();
const CANONICAL = ['clue_001', 'clue_002', 'clue_004', 'clue_006', 'clue_007', 'clue_021', 'clue_028'].sort();
assert.deepEqual(keys, CANONICAL, `判定键集与 canonical 不一致: ${keys.join(',')}`);

// 3) 不允许残留旧口径「取得关键芯片线索」（含引擎 clue_028 未迁移场景下的两键判定）
assert.ok(!/取得关键芯片/.test(mainSrc), 'main.js 仍残留旧口径「取得关键芯片线索」');

// 4) 与引擎侧键集交叉验证：直接解析 engine_driver.py，防两端口径漂移
const py = fs.readFileSync(path.resolve(__dirname, '../../server/engine_driver.py'), 'utf8');
const pm = py.match(/PARTY_CH1_KEYS = frozenset\(\{([\s\S]*?)\}\)/);
assert.ok(pm, 'engine_driver.py 中未找到 PARTY_CH1_KEYS');
const pyKeys = [...new Set(pm[1].match(/clue_\d+/g) || [])].sort();
assert.deepEqual(pyKeys, CANONICAL, `引擎 PARTY_CH1_KEYS 与前端判定键集漂移: ${pyKeys.join(',')}`);

console.log('PASS: dm_tasks_contract —— 第一幕任务判定与 canonical ' + CANONICAL.length + ' 键一致，无旧口径残留');
