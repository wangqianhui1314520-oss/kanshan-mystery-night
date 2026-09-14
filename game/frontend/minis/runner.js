/* ============================================================
 * minis/runner.js —— M1《看山快跑》（GAMEPLAY_V31 §9.4 / minis.md §M1）
 * 横版跑酷：扮演刘看山在档案局走廊狂奔——躲谣言、收鱼干、跑赢热搜。
 * 美术：官方 kanshan.png 30 帧（110×124/帧，3×10 网格）Canvas 切帧跑动；
 * 词库/里程碑/战报模板 = D 组 minis.md §M1 原文；零外链、不上传数据。
 * 安放位：结算页（侦探档案"再玩点别的"）/ 复盘页 / 分享卡附带；#/mini/runner。
 * ============================================================ */
(function () {
  const { ref, computed, onMounted, onBeforeUnmount } = Vue;

  /* D 词库（minis.md §M1 原文） */
  const LOW_WORDS = ['#看山卷款跑路#', '别查了就是意外', '#折叠区的都是造谣犯#', '内部消息：是 Bot 干的'];
  const HIGH_WORDS = ['#看山失踪#', '#谁动了我的鱼干#', '#47个小号同时在线#', '新用户 V587 是谁', '#不出真相不出此门#'];
  const FLY_WORDS = ['知情人透露……', '我朋友的同学的猫说……', 'P 好的长图', '建议关注', '已打码', '叮——'];
  const GAMEOVER_POOL = [
    '被"建议关注"绊倒了。这是本局最弱障碍，耻辱。',
    '谣言没追上你，是金枪鱼背叛了你。',
    '跑完了，横幅说：不出真相，不出此门——但你跑出来了，算你赢。'
  ];
  const MILESTONES = [
    { at: 47, text: '47 号水军在身后骂骂咧咧' },
    { at: 587, text: 'V587 在终点递水：新人报道！' },
    { at: 1000, text: '看山Bot：检测到极限。建议吃鱼干。' }
  ];
  const SPRITE = '../content/assets/official/kanshan/kanshan.png';
  const FW = 110, FH = 124;

  const MiniRunner = {
    setup() {
      const cv = ref(null);
      const state = ref('ready');   // ready | run | over
      const dist = ref(0), fish = ref(0), dodged = ref(0);
      const combo = ref(0);
      const banner = ref('');
      const overReport = ref(null);
      const best = ref(window.Minis.bestOf('runner', 'dist'));
      const reviving = ref(false);

      let raf = 0, ctx = null, ksImg = null, frame = 0, last = 0;
      let G = null;   // 游戏态

      function reset() {
        G = {
          x: 90, y: 0, vy: 0, duck: false, dead: false,
          speed: 5.2, dist: 0, fish: 0, dodged: 0, combo: 0,
          boost: 0, ghost: 0, revive: false, slow: 0,
          obs: [], drops: [], spawnAt: 60, hitFlash: 0,
          milestonesHit: {}, groundY: 0, W: 0, H: 0
        };
      }
      function spawn() {
        const r = Math.random();
        const gy = G.groundY;
        if (r < 0.4) G.obs.push({ kind: 'low', w: 130, h: 42, x: G.W + 40, y: gy - 42, word: LOW_WORDS[Math.floor(Math.random() * LOW_WORDS.length)] });
        else if (r < 0.72) G.obs.push({ kind: 'high', w: 46, h: 96, x: G.W + 40, y: gy - 96, word: HIGH_WORDS[Math.floor(Math.random() * HIGH_WORDS.length)] });
        else G.obs.push({ kind: 'fly', w: 34, h: 34, x: G.W + 60, y: gy - 120 - Math.random() * 40, vy: 1.4, word: FLY_WORDS[Math.floor(Math.random() * FLY_WORDS.length)] });
        if (Math.random() < 0.75) {
          const gold = Math.random() < 0.18;
          G.drops.push({ kind: gold ? 'tuna' : 'salmon', x: G.W + 40 + Math.random() * 120, y: gy - 60 - Math.random() * 130, r: 14, gold });
        }
      }
      function onKey(e) {
        if (state.value !== 'run') { if (e.code === 'Space' || e.type === 'click') start(); return; }
        if (e.code === 'Space' || e.code === 'ArrowUp' || e.type === 'pointerdown') { if (G.y === 0 && !G.duck) { G.vy = -13.2; } }
        if (e.code === 'ArrowDown') { G.duck = true; if (G.y === 0) G.y = 0; }
      }
      function offKey(e) { if (e.code === 'ArrowDown') G.duck = false; }

      function loop(ts) {
        raf = requestAnimationFrame(loop);
        if (!ctx || state.value !== 'run' || !G) return;
        const dt = Math.min(2.4, (ts - last) / 16.7 || 1); last = ts;
        step(dt); draw();
      }
      function step(dt) {
        frame += dt * 0.22;
        const spd = (G.speed + (G.boost > 0 ? 3.4 : 0) - (G.slow > 0 ? 1.8 : 0)) * dt;
        G.dist += spd * 1.9; G.boost = Math.max(0, G.boost - dt); G.slow = Math.max(0, G.slow - dt);
        G.ghost = Math.max(0, G.ghost - dt); G.hitFlash = Math.max(0, G.hitFlash - dt);
        dist.value = Math.floor(G.dist);
        // 物理跳跃
        G.vy += 0.72 * dt; G.y += G.vy * dt;
        const gy = G.groundY - G.duckH();
        if (G.y > 0) { G.y = 0; G.vy = 0; }
        // 生成
        G.spawnAt -= spd;
        if (G.spawnAt <= 0) { spawn(); G.spawnAt = 78 + Math.random() * 70 - Math.min(30, G.dist / 40); }
        // 障碍移动与碰撞
        const px = G.x, ph = G.duck ? 62 : 96;
        const ptop = gy - G.y - ph;
        G.obs.forEach(o => {
          o.x -= (o.kind === 'fly' ? spd + 2.1 : spd);
          if (o.kind === 'fly') { o.y += o.vy * dt; }
          if (o.x < -200) o.dead = true;
          const ox = o.x + 6, ow = o.w - 12, otop = o.kind === 'fly' ? o.y : o.y, oh = o.h;
          const hit = px + 26 < ox + ow && px + 74 > ox && ptop < otop + oh && gy - G.y > otop;
          if (hit && G.ghost <= 0 && !o.scored) {
            o.scored = true;
            if (o.kind === 'fly' || true) {
              if (G.revive) { G.revive = false; G.ghost = 30; banner.value = '哈希残页生效：A3F9-77C2 复活甲已消耗（隐身穿过）'; reviving.value = true; setTimeout(() => reviving.value = false, 1200); }
              else die(o);
            }
          }
          if (!o.counted && o.x + o.w < px) { o.counted = true; G.dodged += 1; dodged.value = G.dodged; }
        });
        G.obs = G.obs.filter(o => !o.dead);
        // 收集
        G.drops.forEach(d => {
          d.x -= spd;
          if (d.x < -40) d.dead = true;
          const dx = d.x - (px + 50), dy = d.y - (gy - G.y - 48);
          if (!d.taken && Math.abs(dx) < 44 && Math.abs(dy) < 56) {
            d.taken = true;
            if (d.kind === 'salmon') { G.fish += 1; G.combo += 1; fish.value = G.fish; combo.value = G.combo; }
            else { G.fish = Math.max(0, G.fish - 1); G.slow = 90; G.combo = 0; combo.value = 0; banner.value = '金枪鱼味的都是异端——减速惩罚（罐身便签原话）'; setTimeout(() => { if (banner.value.startsWith('金枪鱼')) banner.value = ''; }, 1800); }
          }
        });
        G.drops = G.drops.filter(d => !d.dead);
        // 里程碑
        MILESTONES.forEach(m => {
          if (G.dist >= m.at && !G.milestonesHit[m.at]) { G.milestonesHit[m.at] = true; banner.value = m.at + ' 米——' + m.text; setTimeout(() => { if (banner.value.includes(m.text)) banner.value = ''; }, 2600); }
        });
      }
      function die(o) {
        state.value = 'over';
        const word = o && o.word ? String(o.word) : '谣言';
        const report = (word.includes('建议关注') ? GAMEOVER_POOL[0] : Math.random() < 0.5 ? GAMEOVER_POOL[1] : GAMEOVER_POOL[2]);
        const rec = window.Minis.reportScore('runner', { dist: Math.floor(G.dist), fish: G.fish, dodged: G.dodged });
        best.value = window.Minis.bestOf('runner', 'dist');
        overReport.value = { report, dist: Math.floor(G.dist), fish: G.fish, dodged: G.dodged, score: rec, milestones: MILESTONES.filter(m => G.milestonesHit[m.at]).map(m => m.text) };
      }
      function draw() {
        const c = cv.value; if (!c) return;
        const W = G.W = c.width, H = G.H = c.height;
        ctx.clearRect(0, 0, W, H);
        // 背景：走廊（代码绘制，规约③）
        const bg = ctx.createLinearGradient(0, 0, 0, H);
        bg.addColorStop(0, '#0b1224'); bg.addColorStop(1, '#070b14');
        ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = 'rgba(31,44,74,.8)'; ctx.lineWidth = 1;
        const off = (G.dist * 0.5) % 80;
        for (let x = -off; x < W; x += 80) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H - 70); ctx.stroke(); }
        for (let i = 0; i < 3; i++) { ctx.fillStyle = 'rgba(0,132,255,.05)'; ctx.fillRect(((i * 300 - G.dist * 1.4) % (W + 300) + W + 300) % (W + 300) - 200, 40, 180, 120); }
        const gy = G.groundY = H - 90;
        ctx.fillStyle = '#0d1526'; ctx.fillRect(0, gy, W, H - gy);
        ctx.strokeStyle = 'rgba(0,132,255,.4)'; ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
        // 障碍（贴字演出）
        G.obs.forEach(o => {
          ctx.fillStyle = o.kind === 'low' ? 'rgba(255,77,94,.2)' : o.kind === 'high' ? 'rgba(165,139,255,.18)' : 'rgba(245,196,81,.16)';
          ctx.strokeStyle = o.kind === 'low' ? '#ff6b78' : o.kind === 'high' ? '#a58bff' : '#f5c451';
          roundRect(ctx, o.x, o.y, o.w, o.h, 6); ctx.fill(); ctx.stroke();
          ctx.fillStyle = '#dbe6fa'; ctx.font = '11px "Microsoft YaHei"';
          if (o.kind !== 'fly') ctx.fillText(o.word.slice(0, 12), o.x + 6, o.y + (o.kind === 'low' ? 26 : 18), o.w - 8);
          else { ctx.fillText(o.word.slice(0, 5), o.x - 4, o.y - 8); ctx.beginPath(); ctx.arc(o.x + o.w / 2, o.y + o.h / 2, 8, 0, 7); ctx.stroke(); }
        });
        // 收集物
        G.drops.forEach(d => {
          ctx.fillStyle = d.gold ? '#c7b27a' : '#7de3a8';
          ctx.strokeStyle = d.gold ? '#8a6d3b' : '#00e5a8';
          ctx.beginPath(); ctx.ellipse(d.x, d.y, d.r + 6, d.r - 3, -0.5, 0, 7); ctx.fill(); ctx.stroke();
          ctx.fillStyle = '#dbe6fa'; ctx.font = '10px Consolas'; ctx.fillText(d.gold ? '金枪鱼' : '彩虹鳟鱼', d.x - 22, d.y - d.r - 6);
        });
        // 玩家：官方雪碧图切帧（row1 行走帧做跑动；跳跃用 row2；滑蹲压扁）
        if (ksImg && ksImg.width) {
          const col = Math.floor(frame) % 10;
          const row = G.y < 0 ? 2 : 1;
          const ph = G.duck && G.y === 0 ? 62 : 96;
          const pw = ph * FW / FH;
          if (G.ghost > 0) ctx.globalAlpha = 0.45;
          ctx.drawImage(ksImg, col * FW, row * FH, FW, FH, G.x, gy - G.y - ph, pw, ph);
          ctx.globalAlpha = 1;
          if (reviving.value) { ctx.strokeStyle = '#6fe3ff'; ctx.strokeRect(G.x - 4, gy - G.y - ph - 4, pw + 8, ph + 8); }
        }
        // HUD
        ctx.fillStyle = 'rgba(10,16,32,.8)'; roundRect(ctx, 12, 12, 240, 64, 10); ctx.fill();
        ctx.fillStyle = '#6fe3ff'; ctx.font = 'bold 18px Consolas';
        ctx.fillText(Math.floor(G.dist) + ' m', 28, 38);
        ctx.fillStyle = '#f5c451'; ctx.fillText('🐟 ' + G.fish, 120, 38);
        ctx.fillStyle = '#8296bd'; ctx.font = '12px "Microsoft YaHei"';
        ctx.fillText('躲过 ' + G.dodged + ' · 连击 ' + G.combo + (G.revive ? ' · 复活甲✓' : ''), 28, 62);
        if (banner.value) { ctx.fillStyle = 'rgba(245,196,81,.16)'; roundRect(ctx, W / 2 - 260, 18, 520, 40, 10); ctx.fill(); ctx.fillStyle = '#ffe9b8'; ctx.font = 'bold 14px "Microsoft YaHei"'; ctx.textAlign = 'center'; ctx.fillText(banner.value, W / 2, 44); ctx.textAlign = 'left'; }
      }
      function duckH() { return G.duck ? 34 : 0; }
      function roundRect(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }

      function start() {
        reset();
        state.value = 'run';
        const c = cv.value;
        ctx = c.getContext('2d');
        G.W = c.width; G.groundY = c.height - 90;
        last = performance.now();
        if (!ksImg) { ksImg = new Image(); ksImg.src = SPRITE; }
      }
      const doShare = () => window.Minis.download(window.Minis.REG.runner, {
        lines: [['奔跑距离', overReport.value.dist + ' m'], ['鱼干', overReport.value.fish + ' 袋'], ['躲过谣言', overReport.value.dodged + ' 条'], ['历史最佳', best.value + ' m']],
        report: overReport.value.report
      }).then(r => { if (!r.ok) window.alert(r.notice); });
      const replayMilestone = computed(() => MILESTONES.map(m => m.at));

      onMounted(() => {
        reset();
        window.addEventListener('keydown', onKey);
        window.addEventListener('keyup', offKey);
        raf = requestAnimationFrame(loop);
      });
      onBeforeUnmount(() => {
        window.removeEventListener('keydown', onKey);
        window.removeEventListener('keyup', offKey);
        cancelAnimationFrame(raf);
      });

      return { cv, state, dist, fish, dodged, combo, banner, overReport, best, start, onKey, doShare, replayMilestone, MILESTONES };
    },
    template: `
    <div class="mini-runner" @pointerdown="onKey">
      <canvas ref="cv" width="860" height="420" class="runner-cv"></canvas>
      <div class="runner-foot dim">空格/点击=跳跃 · ↓=滑铲躲飞弹 · 彩虹鳟鱼+1 / 金枪鱼-1（异端减速）· 叮=加速 · 哈希残页=复活甲</div>

      <div class="runner-over" v-if="state==='over' && overReport">
        <div class="ro-card">
          <h3>Game Over · 战报</h3>
          <p class="ro-line">{{ overReport.report }}</p>
          <div class="ro-stats">
            <span>距离 <b class="mono">{{ overReport.dist }} m</b></span>
            <span>鱼干 <b class="mono">{{ overReport.fish }}</b></span>
            <span>躲过谣言 <b class="mono">{{ overReport.dodged }}</b></span>
            <span>历史最佳 <b class="mono">{{ best }} m</b></span>
          </div>
          <p class="dim" v-if="overReport.milestones.length">里程碑：{{ overReport.milestones.join(' / ') }}</p>
          <p class="dim ro-share">战报已生成，分享卡带着官方看山一起跑（只导出图片，不做自动发布）。</p>
          <div class="ro-btns">
            <button class="btn primary big" @click="start">再跑一次</button>
            <button class="btn warn" @click="doShare">生成分享卡 → PNG</button>
            <button class="btn ghost" @click="$minisClose">回游戏厅</button>
          </div>
        </div>
      </div>

      <div class="runner-ready" v-if="state==='ready'">
        <div class="ro-card">
          <h3>看山快跑</h3>
          <p>横版跑酷：扮演刘看山在档案局走廊狂奔——躲谣言、收鱼干、跑赢热搜。</p>
          <p class="dim">里程碑：{{ MILESTONES.map(m=>m.at+'m').join(' / ') }}；躲过的每条谣言都计入战报。</p>
          <button class="btn primary big" @click="start">开跑（空格）</button>
        </div>
      </div>
    </div>`
  };

  window.Minis.register({
    id: 'runner', title: '看山快跑', tagline: '横版跑酷——躲谣言、收鱼干、跑赢热搜。',
    entry: '结算页"再玩点别的" / 复盘页 / 分享卡附带', source: '本地 Canvas（官方 kanshan.png 30 帧切帧）',
    component: MiniRunner
  });
})();
