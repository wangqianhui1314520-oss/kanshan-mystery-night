// 一次性：桌面视口(1440x900)进入圆桌页，测量聊天区真实像素并截图
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle' });
  // 尝试点“继续上次对局”或“跳过登录”
  for (const name of ['继续上次对局 ▸', '跳过登录 · 直接进入（实习侦探证）']) {
    const btn = p.getByRole('button', { name });
    if (await btn.count()) { await btn.first().click(); break; }
  }
  await p.waitForTimeout(1200);
  // 关卷宗
  const cf = p.getByRole('button', { name: '翻开卷宗 · 进入圆桌 →' });
  if (await cf.count()) { await cf.first().click(); await p.waitForTimeout(800); }
  // 测量
  const m = await p.evaluate(() => {
    const q = s => document.querySelector(s);
    const rect = el => el ? (r => ({ h: Math.round(r.height), bottom: Math.round(r.bottom) }))(el.getBoundingClientRect()) : null;
    const nav = q('.bottom-nav');
    const navShown = nav ? getComputedStyle(nav).display !== 'none' : false;
    return {
      vh: window.innerHeight,
      chat: rect(q('.cs-chat')),
      stage: rect(q('.cs-stage')),
      bottomNavShown: navShown,
    };
  });
  console.log(JSON.stringify(m, null, 2));
  await p.screenshot({ path: 'frontend/tests/shots/chat_desktop_final.png', fullPage: false });
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
