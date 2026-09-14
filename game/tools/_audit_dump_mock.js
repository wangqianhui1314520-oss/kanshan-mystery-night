/* 叙事审计辅助：把前端 mock 数据层（data.js）的关键字段导出为 JSON。
 * 只读操作，不改动任何游戏数据。输出写到 data/_audit_mock.json。
 * 用法：node tools/_audit_dump_mock.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

global.window = {};
require(path.join(__dirname, '..', 'frontend', 'js', 'data.js'));
const M = global.window.MOCK;
if (!M) { console.error('window.MOCK 未导出'); process.exit(1); }

const out = {
  endings: (M.endings || []).map(e => ({ id: e.id, name: e.name, desc: e.desc })),
  bossFlaws: (M.clues || [])
    .filter(c => c.tier === 'boss_flaw')
    .map(c => ({ id: c.id, flaw_id: c.flaw_id, name: c.name, location: c.location, unlock: c.unlock, fact: c.fact })),
  kcards: (M.kcards || []).map(k => ({ id: k.id, title: k.title || k.name, author: k.author || '', binds: k.binds || '' })),
  creditsSalt: (M.credits && M.credits.salt || []).map(s => s.work),
  reviewTimeline: (M.reviewTimeline || []).map(r => ({ time: r.time, text: r.text })),
  flaw5Credit: M.flavor5Credit || '',
  locations: (M.locations || []).map(l => l.id),
};

const dst = path.join(__dirname, '..', 'data', '_audit_mock.json');
fs.writeFileSync(dst, JSON.stringify(out, null, 2), 'utf-8');
console.log('OK ->', dst);
