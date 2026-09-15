/* ============================================================
 * views/report.js —— 侦探档案：侦探证（登录后）+ 侦探报告页 + Canvas 分享卡
 * MEGA_MODE：侦探证=知乎公开三件套（昵称/头像/headline）+ AI 欢乐警衔；
 * 侦探报告=终局后消费 detective_report 事件（WS）或本地 buildReport()（Mock）；
 * 分享卡=前端 Canvas 合图导出 PNG（只导出图片，不做自动发布——知乎开放平台无写入接口）。
 * ============================================================ */
(function () {
  const { ref, computed } = Vue;   // （V4/G2 修复：此前误引未导入的 onMounted，报 ReferenceError）
  const M = window.Store.M;

  const AXES = [
    { key: 'rigor', label: '严谨' }, { key: 'skepticism', label: '怀疑' },
    { key: 'empathy', label: '共情' }, { key: 'courage', label: '勇气' },
    { key: 'independence', label: '独立' }
  ];
  const TruthRadar = {
    props: { profile: { type: Object, default: null } },
    setup(props) {
      const pts = computed(() => {
        const scores = (props.profile && props.profile.scores) || {};
        return AXES.map((a, i) => {
          const ang = -Math.PI / 2 + i * 2 * Math.PI / 5;
          const r = ((scores[a.key] || 0) / 100) * 70;
          return { x: +(100 + r * Math.cos(ang)).toFixed(1), y: +(100 + r * Math.sin(ang)).toFixed(1),
            lx: +(100 + 86 * Math.cos(ang)).toFixed(1), ly: +(100 + 86 * Math.sin(ang)).toFixed(1),
            label: a.label, score: scores[a.key] || 0 };
        });
      });
      const poly = computed(() => pts.value.map(p => p.x + ',' + p.y).join(' '));
      const grids = [0.35, 0.7, 1].map(s => AXES.map((_, i) => {
        const ang = -Math.PI / 2 + i * 2 * Math.PI / 5;
        return (100 + 70 * s * Math.cos(ang)).toFixed(1) + ',' + (100 + 70 * s * Math.sin(ang)).toFixed(1);
      }).join(' '));
      return { pts, poly, grids, overall: computed(() => (props.profile && props.profile.overall) || 0) };
    },
    template: `
    <svg class="tp-radar" viewBox="0 0 200 200" role="img" :aria-label="'五维求真力 ' + overall">
      <polygon v-for="(g, i) in grids" :key="i" class="grid" :points="g"></polygon>
      <polygon class="poly" :points="poly"></polygon>
      <circle v-for="(p, i) in pts" :key="i" class="dot" :cx="p.x" :cy="p.y" r="3"></circle>
      <text v-for="(p, i) in pts" :key="'t'+i" :x="p.lx" :y="p.ly" text-anchor="middle" dominant-baseline="middle">{{ p.label }} {{ p.score }}</text>
    </svg>`
  };

  /* ---------- 侦探证卡片（HUD 弹窗 / 报告页复用） ---------- */
  const DossierCard = {
    props: { mini: Boolean },
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const open = ref(false);
      const name = ref('');
      const headline = ref('');
      const avatar = ref(M.dossierAvatars[0].src);
      const busy = ref(false);

      const claim = () => {
        if (!name.value.trim()) { window.Store.toast('先署名——档案局不发匿名侦探证', 'warn'); return; }
        // MEGA_MODE：真实授权路径——已登录局内优先消费 GET /api/profile/me（隐私三件套）
        const tryProfile = S.netKind === 'ws' && /^https?:/.test(location.protocol);
        if (tryProfile) {
          fetch(`${location.origin}/api/profile/me?session_id=${encodeURIComponent(S.sessionId)}&player_id=player:1`)
            .then(r => r.json()).then(j => {
              if (j.ok && j.profile) {
                const p = j.profile, d = j.dossier || {};
                window.Store.send('skill', {
                  kind: 'claim_dossier', name: d.owner || p.fullname || name.value,
                  headline: p.headline || headline.value,
                  avatar: p.avatar_path || avatar.value, source: 'zhihu',
                  uid6: d.badge_no, rank: d.rank
                });
                window.Store.toast('已用你的公开资料签发侦探证', 'good');
                open.value = false;
              } else {
                window.Store.toast(j.notice || '本局尚未完成 OAuth 登录——先用登记表签发', 'warn');
                doMockClaim();
              }
            }).catch(doMockClaim);
          return;
        }
        doMockClaim();
      };
      const doMockClaim = () => {
        busy.value = true;
        window.Store.send('skill', { kind: 'claim_dossier', name: name.value, headline: headline.value, avatar: avatar.value, source: 'mock' });
        setTimeout(() => { busy.value = false; open.value = false; }, 600);
      };
      const pick = a => { avatar.value = a.src; };
      return { S, M, open, name, headline, avatar, busy, claim, pick };
    },
    template: `
    <div class="dossier-card" :class="{mini}">
      <template v-if="S.dossier">
        <div class="dossier-body">
          <div class="dossier-photo"><img :src="S.dossier.avatar" alt="证件照"></div>
          <div class="dossier-info">
            <span class="dossier-org">求真档案局 · 特聘侦探证</span>
            <b class="dossier-name">{{ S.dossier.name }}</b>
            <span class="dossier-rank">警衔：{{ S.dossier.rank }}</span>
            <span class="dossier-meta mono">编号 ZH-{{ S.dossier.uid6 }} · 签发 {{ S.dossier.issued }} · {{ S.dossier.source === 'zhihu' ? '知乎授权登录' : '档案局现场登记' }}</span>
            <span class="dossier-headline" v-if="S.dossier.headline">简介烙印：「{{ S.dossier.headline }}」</span>
          </div>
          <dm-walk :row="0" :scale="0.34" :speed="1.4" class="dossier-dm"></dm-walk>
        </div>
        <p class="dossier-note dim">隐私声明：仅使用公开三件套（昵称/头像/简介），email/phone 一律忽略；session 外不落盘。</p>
      </template>
      <template v-else>
        <div class="dossier-body">
          <div class="dossier-photo"><img :src="avatar" alt="证件照"></div>
          <div class="dossier-info">
            <span class="dossier-org">求真档案局 · 实习侦探证</span>
            <b class="dossier-name">实习调查员</b>
            <span class="dossier-rank">警衔：见习求真员</span>
            <span class="dossier-meta mono">编号 ZH-000000 · 签发 档案局现场登记</span>
          </div>
          <dm-walk :row="0" :scale="0.34" :speed="1.4" class="dossier-dm"></dm-walk>
        </div>
        <p class="dossier-note dim">知乎登录后升级《特聘侦探证》：真名+知乎头像+专属花名警衔，解锁个性化台词彩蛋与报告署名。只读公开三件套，不上传任何用户数据。</p>
        <button class="btn primary big" @click="open = true">知乎登录 · 升级特聘侦探证</button>
      </template>

      <ui-modal v-if="open" title="知乎登录 · 侦探证登记" @close="open=false">
        <div class="dossier-form">
          <p class="dim">联机时会尝试读取你的公开昵称、头像和简介签发证件；读不到就用下面这张登记表。</p>
          <div class="kw-input"><input v-model="name" maxlength="16" placeholder="昵称（公开三件套①）" /></div>
          <div class="kw-input"><input v-model="headline" maxlength="30" placeholder="一句话简介（公开三件套③，警衔由它生成）" /></div>
          <p class="dim">证件照（演示用官方 IP 家族；真实登录=知乎头像）：</p>
          <div class="dossier-avatars">
            <button v-for="a in M.dossierAvatars" :key="a.id" class="dossier-ava" :class="{on: avatar===a.src}" @click="pick(a)">
              <img :src="a.src" :alt="a.name"><span>{{ a.name }}</span>
            </button>
          </div>
          <p class="dim">警衔预览：<b class="hl">{{ (M.dossierRanks.find(r=>r.test.test(headline)) || {rank:'随机欢乐警衔'}).rank }}</b></p>
          <button class="btn primary big" :disabled="busy" @click="claim">签发侦探证</button>
        </div>
      </ui-modal>
    </div>`
  };

  /* ---------- Canvas 分享卡（报告+徽章+结局海报 合图导出） ---------- */
  const SHARE_W = 1080, SHARE_H = 1440;
  function drawShareCard(dossier) {
    const cv = document.createElement('canvas');
    cv.width = SHARE_W; cv.height = SHARE_H;
    const ctx = cv.getContext('2d');
    const S = window.Store.state, M = window.Store.M;
    const ending = M.endings.find(e => e.id === S.ending) || M.endings[0];
    const img = src => new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });

    const roundRect = (x, y, w, h, r) => { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); };

    return Promise.all([
      img('/assets/images/scene_exterior.png'),
      img('/assets/images/logo_badge.png'),
      img(dossier ? dossier.avatar : '/assets/images/dm_kanshan_holo.png')
    ]).then(([bg, logo, ava]) => {
      // 底图 + 压暗
      if (bg) { const s = Math.max(SHARE_W / bg.width, SHARE_H / bg.height); ctx.drawImage(bg, (SHARE_W - bg.width * s) / 2, (SHARE_H - bg.height * s) / 2, bg.width * s, bg.height * s); }
      const grad = ctx.createLinearGradient(0, 0, 0, SHARE_H);
      grad.addColorStop(0, 'rgba(5,9,20,.88)'); grad.addColorStop(.45, 'rgba(5,9,20,.72)'); grad.addColorStop(1, 'rgba(5,9,20,.94)');
      ctx.fillStyle = grad; ctx.fillRect(0, 0, SHARE_W, SHARE_H);
      // 框
      ctx.strokeStyle = 'rgba(0,132,255,.5)'; ctx.lineWidth = 3; roundRect(28, 28, SHARE_W - 56, SHARE_H - 56, 22); ctx.stroke();
      // 头部
      if (logo) ctx.drawImage(logo, 72, 64, 96, 96);
      ctx.fillStyle = '#dbe6fa'; ctx.font = 'bold 44px "Microsoft YaHei"';
      ctx.fillText('求真档案局 · 看山失踪夜', 190, 108);
      ctx.fillStyle = '#4da8ff'; ctx.font = '24px Consolas';
      ctx.fillText('DETECTIVE REPORT / 知乎黑客松 2026', 190, 148);
      // 结局
      ctx.fillStyle = '#f5c451'; ctx.font = 'bold 64px "Microsoft YaHei"';
      ctx.fillText(ending.name, 72, 280);
      ctx.fillStyle = '#8296bd'; ctx.font = '26px "Microsoft YaHei"';
      wrapText(ctx, ending.desc, 72, 330, SHARE_W - 150, 38);
      const tp = S.truthProfile;
      if (tp) {
        ctx.fillStyle = '#f5c451'; ctx.font = 'bold 28px "Microsoft YaHei"';
        ctx.fillText('求真画像 · ' + tp.archetype + ' · ' + tp.overall + ' 分', 72, 430);
      }
      // 数据行
      const flawN = Object.keys(S.flaws).length;
      const okN = S.counsel.filter(r => r.ok).length;
      const rows = [
        ['推理轮数', '第 ' + S.round + ' 轮'], ['线索入袋', Object.keys(S.clues).length + ' 条'],
        ['看山破绽', flawN + '/5'], ['心晴开导', okN + ' 人'],
        ['暗拍照片', S.photos.length + ' 张'], ['反诈学分', String(S.antifraud.score)],
        ['赞数余额', S.zans + ' 赞']
      ];
      ctx.font = '26px "Microsoft YaHei"';
      rows.forEach((r, i) => {
        const x = 72 + (i % 2) * 480, y = 480 + Math.floor(i / 2) * 74;
        ctx.fillStyle = 'rgba(0,132,255,.12)'; roundRect(x, y - 30, 440, 56, 12); ctx.fill();
        ctx.fillStyle = '#8296bd'; ctx.fillText(r[0], x + 20, y + 8);
        ctx.fillStyle = '#6fe3ff'; ctx.font = 'bold 26px Consolas'; ctx.fillText(r[1], x + 220, y + 8);
        ctx.font = '26px "Microsoft YaHei"';
      });
      // 徽章
      const report = S.report || { badges: [], achievements: [] };
      const defs = (report.badges || []).map(id => M.badgeDefs.find(b => b.id === id)).filter(Boolean);
      ctx.fillStyle = '#dbe6fa'; ctx.font = 'bold 30px "Microsoft YaHei"'; ctx.fillText('本局徽章', 72, 800);
      defs.slice(0, 6).forEach((b, i) => {
        const x = 72 + (i % 3) * 312, y = 826 + Math.floor(i / 3) * 96;
        ctx.fillStyle = 'rgba(245,196,81,.14)'; roundRect(x, y, 290, 76, 14); ctx.fill();
        ctx.strokeStyle = 'rgba(245,196,81,.5)'; ctx.lineWidth = 1.5; roundRect(x, y, 290, 76, 14); ctx.stroke();
        ctx.fillStyle = '#f5c451'; ctx.font = 'bold 24px "Microsoft YaHei"';
        ctx.fillText(b.icon + ' ' + b.name.slice(0, 9), x + 18, y + 46);
      });
      if (!defs.length) { ctx.fillStyle = '#8296bd'; ctx.font = '24px "Microsoft YaHei"'; ctx.fillText('本局无徽章——档案局表示：参与奖是袋鱼干。', 72, 860); }
      // 侦探证签名区
      const dy = 1070;
      if (ava) { ctx.save(); ctx.beginPath(); ctx.arc(140, dy + 40, 62, 0, Math.PI * 2); ctx.closePath(); ctx.clip(); ctx.drawImage(ava, 78, dy - 22, 124, 124); ctx.restore(); }
      ctx.strokeStyle = 'rgba(0,132,255,.6)'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(140, dy + 40, 62, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = '#dbe6fa'; ctx.font = 'bold 32px "Microsoft YaHei"';
      ctx.fillText(dossier ? dossier.name : '匿名侦探', 230, dy + 20);
      ctx.fillStyle = '#4da8ff'; ctx.font = '24px "Microsoft YaHei"';
      ctx.fillText(dossier ? dossier.rank + ' · 编号 ZH-' + dossier.uid6 : '（登录后可署名领证）', 230, dy + 58);
      // flavor_5 常驻署名小字（D 对接点）
      ctx.fillStyle = 'rgba(130,150,189,.85)'; ctx.font = '20px "Microsoft YaHei"';
      wrapText(ctx, M.flavor5Credit, 72, 1240, SHARE_W - 150, 28);
      // dm-walk 印章
      const ks = new Image();
      return { cv, ks };
    });
  }
  function wrapText(ctx, text, x, y, maxW, lh) {
    let line = '', yy = y;
    for (const ch of String(text)) {
      if (ctx.measureText(line + ch).width > maxW) { ctx.fillText(line, x, yy); line = ch; yy += lh; }
      else line += ch;
    }
    if (line) ctx.fillText(line, x, yy);
  }

  /* ---------- 侦探报告页 ---------- */
  const ReportView = {
    components: { 'dossier-card': DossierCard, 'truth-radar': TruthRadar },
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const exporting = ref(false);
      const exportTip = ref('');
      const ending = computed(() => M.endings.find(e => e.id === S.ending));
      const hasEnding = computed(() => !!S.ending);
      const badgeDefs = computed(() => ((S.report || {}).badges || []).map(id => M.badgeDefs.find(b => b.id === id)).filter(Boolean));
      const reportText = computed(() => (S.report || {}).report_text || '');
      const persona = computed(() => (S.report || {}).persona || null);
      const profile = computed(() => S.truthProfile || (S.report && S.report.profile) || null);
      const recommendations = ref([]), recBusy = ref(false), recNotice = ref('');
      const loadRecommendations = async () => {
        recBusy.value = true; recNotice.value = '';
        try {
          const h = {};
          const r = await fetch('/api/zhihu/recommendations?count=5', {headers:h});
          const j = await r.json(); if (!r.ok || !j.ok) throw new Error(j.notice || '推荐接口失败');
          recommendations.value = j.data || [];
        } catch (e) { recNotice.value = e.message; }
        finally { recBusy.value = false; }
      };
      const exportCard = async () => {
        exporting.value = true; exportTip.value = '合图生成中…';
        try {
          const { cv, ks } = await drawShareCard(S.dossier);
          // 雪碧图印章（DM 走查分享卡右下角）
          try {
            await new Promise(res => { ks.onload = res; ks.onerror = res; ks.src = '/assets/official/kanshan/kanshan.png'; });
            if (ks.width) {
              const fw = 110 * 0.6, fh = 124 * 0.6, row = 1;
              cv.getContext('2d').drawImage(ks, 0, 124 * row, 110, 124, SHARE_W - fw - 90, SHARE_H - fh - 96, fw, fh);
            }
          } catch (e) { /* 印章失败不影响导出 */ }
          const done = blob => {
            exporting.value = false; exportTip.value = '';
            if (!blob) { exportTip.value = '导出失败（file:// 直开受 Canvas 安全限制）——用 http 服务打开本页，或直接截图分享。'; return; }
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'detective_report_' + (S.dossier ? S.dossier.uid6 : S.sessionId) + '.png';
            a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
            window.Store.toast('分享卡已导出（只导出图片，不做自动发布）', 'good');
          };
          if (cv.toBlob) cv.toBlob(done, 'image/png');
          else { try { done(dataURLtoBlob(cv.toDataURL('image/png'))); } catch (e) { done(null); } }
        } catch (e) {
          exporting.value = false; exportTip.value = '合图异常：' + e.message + '（http 服务打开可正常导出）';
        }
      };
      const dataURLtoBlob = dataurl => {
        const [h, b64] = dataurl.split(','), mime = h.match(/:(.*?);/)[1];
        const bin = atob(b64), u8 = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        return new Blob([u8], { type: mime });
      };
      const miniCatalog = computed(() => window.Store.studioMiniCatalog());
      const showMinis = computed(() => !S.demo && Object.keys(miniCatalog.value || {}).length > 0);
      return { S, M, ending, hasEnding, badgeDefs, reportText, persona, profile, exportCard, exporting, exportTip, recommendations, recBusy, recNotice, loadRecommendations, Minis: window.Minis, miniCatalog, showMinis };
    },
    template: `
    <section class="view report-view">
      <header class="view-hd">
        <h2>侦探档案 · 报告与分享</h2>
        <div class="hd-chips">
          <span class="chip gold">MEGA_MODE · 传播系统</span>
          <span class="chip" v-if="hasEnding" :class="ending.cls">{{ ending.name }}</span>
          <span class="chip" v-else>终局后出完整报告（可先领证）</span>
        </div>
      </header>

      <div class="report-grid">
        <div class="rv-card">
          <h3>知乎问题推荐 · 兴趣彩蛋</h3>
          <p class="dim">基于官方推荐接口生成，仅影响彩蛋内容，不改变推理公平性。</p>
          <button class="btn ghost sm" @click="loadRecommendations" :disabled="recBusy">{{ recBusy ? '读取中…' : '读取我的推荐' }}</button>
          <p class="dim" v-if="recNotice">{{ recNotice }}</p>
          <ul v-if="recommendations.length"><li v-for="(r,i) in recommendations" :key="i">{{ r.title || r.name || r.question || r }}</li></ul>
        </div>
        <div class="rv-card">
          <h3>侦探证（登录后）</h3>
          <dossier-card></dossier-card>
        </div>

        <div class="rv-card">
          <h3>侦探报告（终局生成）</h3>
          <template v-if="hasEnding">
            <p class="report-text" v-if="reportText">{{ reportText }}</p>
            <div class="report-badges">
              <span v-for="b in badgeDefs" :key="b.id" class="badge-item"><i>{{ b.icon }}</i><b>{{ b.name }}</b><em>{{ b.desc }}</em></span>
              <span v-if="!badgeDefs.length" class="dim">本局无徽章——参与奖：袋鱼干。</span>
            </div>
            <div v-if="profile" class="tp-card">
              <truth-radar :profile="profile"></truth-radar>
              <div>
                <h4 class="tp-arch">{{ profile.archetype }} · {{ profile.overall }} 分</h4>
                <p class="tp-verdict">{{ profile.verdict }}</p>
                <ul class="tp-hi">
                  <li v-for="(h, i) in (profile.highlights || [])" :key="i">{{ h }}</li>
                </ul>
                <div class="tp-scores">
                  <span class="chip">严谨 {{ profile.scores.rigor }}</span>
                  <span class="chip">怀疑 {{ profile.scores.skepticism }}</span>
                  <span class="chip">共情 {{ profile.scores.empathy }}</span>
                  <span class="chip">勇气 {{ profile.scores.courage }}</span>
                  <span class="chip">独立 {{ profile.scores.independence }}</span>
                </div>
              </div>
            </div>
            <div v-else-if="persona" class="persona-card">
              <h4>🧭 你的求真人格</h4>
              <div class="persona-name">{{ persona.name }}</div>
              <p class="persona-desc">{{ persona.desc }}</p>
            </div>
            <button class="btn primary big" :disabled="exporting" @click="exportCard">{{ exporting ? '生成中…' : '生成 Canvas 分享卡 → PNG 下载' }}</button>
            <p class="dim" v-if="exportTip">{{ exportTip }}</p>
            <p class="dim">分享卡=报告+徽章+结局海报合图（logo_badge + scene_exterior + 侦探证头像 + flavor_5 署名）。知乎开放平台无写入接口，只导出图片、不做自动发布。</p>
          </template>
          <div v-else class="empty-state small">
            <b>报告待终局</b>
            <p>圆桌指认结算后，AI 生成《侦探报告》：推理评分、高光操作回放、人格化锐评、成就徽章。</p>
            <div class="demo-row" v-if="S.demo">
              <button class="btn ghost sm" @click="S.view='review'">去复盘页模拟结局 →</button>
            </div>
          </div>
        </div>

        <div class="rv-card wide">
          <h3>成就徽章墙（11 枚）</h3>
          <div class="badge-wall">
            <span v-for="b in M.badgeDefs" :key="b.id" class="badge-item" :class="{got: (S.report||{badges:[]}).badges.includes(b.id)}">
              <i>{{ b.icon }}</i><b>{{ b.name }}</b><em>{{ b.desc }}</em>
            </span>
          </div>
        </div>
        <div class="rv-card wide" v-if="showMinis">
          <h3>迷你游戏厅（P3 · 安放位图 §9.4）</h3>
          <div class="mini-lobby-grid">
            <button v-for="(d, id) in miniCatalog" :key="id" class="mini-card" @click="Minis.open(id)">
              <b>{{ d.title }}</b>
              <span class="dim">{{ d.tagline }}</span>
              <em class="dim">{{ d.entry }}</em>
            </button>
          </div>
          <p class="dim">计分和战报只存在本机。分享卡只导出图片，不会自动发到任何平台。</p>
        </div>
      </div>
      <div class="review-walk-strip"><dm-walk :row="1" :scale="0.5" :speed="1.1"></dm-walk><dm-walk :row="2" :scale="0.5" :speed="0.8" :flip="true"></dm-walk></div>
    </section>`
  };

  window.VIEWS.report = ReportView;
  window.VIEWS['dossier-card'] = DossierCard;
  window.VIEWS['truth-radar'] = TruthRadar;
})();
