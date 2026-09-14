/* ============================================================
 * views/map.js —— 场景图 12 地点搜证（俯视平面 + 搜证面板 + 局长室密码门）
 * 事件：search → search_result / clue_gained / faction_skill(draw_card)
 * ============================================================ */
(function () {
  const { ref, computed, watch } = Vue;

  const MapView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const openLoc = ref(null);
      const kw = ref('');
      const lastGain = ref(null);
      const searchHint = ref(null);
      const flip = ref(false);
      const officeCode = ref('');
      const officeBox = ref(false);
      const officeUnlocked = computed(() => !!(S.officeOpen || (S.office && S.office.open)));
      const officeLoc = computed(() => M.locations.find(l => l.id === 'loc_office') || null);
      const locVisible = (loc) => !loc.hidden || officeUnlocked.value;
      const visibleLocs = computed(() => M.locations.filter(locVisible));
      const locKeywords = computed(() => {
        const loc = openLoc.value;
        if (!loc) return [];
        const ks = (loc.keywords || []).slice();
        if (loc.id === 'loc_office') {
          ['密码', '手稿', '鱼干'].forEach(k => { if (ks.indexOf(k) < 0) ks.push(k); });
        }
        return ks;
      });
      const submitOffice = () => {
        const code = String(officeCode.value || '').replace(/\D/g, '').slice(0, 4);
        officeCode.value = code;
        if (code.length !== 4) { window.Store.toast('请输入四位密码', 'warn'); return; }
        window.Store.send('skill', { kind: 'unlock_office', code: code });
      };

      const onClue = (evt) => { lastGain.value = evt.payload; flip.value = false; setTimeout(() => flip.value = true, 60); };
      const onSearch = (evt) => {
        const p = evt && evt.payload || {};
        if (!openLoc.value || (p.location && p.location !== openLoc.value.id && p.location !== openLoc.value.name)) return;
        if (evt.actor && evt.actor.startsWith('player:') && evt.actor !== S.playerId) return;
        if (p.hit === false) {
          const hint = p.hint && Array.isArray(p.hint.keywords) ? p.hint.keywords
            : p.source === 'engine' ? [] : locKeywords.value.filter(k => k !== kw.value).slice(0, 3);
          searchHint.value = { keywords: hint, text: hint.length ? '可以从这些方向继续调查' : '当前没有新的公开方向，可以换个地点调查。' };
          lastGain.value = { miss: true, tier: 'warm', name: '现场没有直接命中',
            text: p.text || p.ambient || '这次只翻到环境痕迹。换一个关键词，或把注意力转向另一处地点。',
            tags: ['环境线索', '可继续调查'].concat(hint.map(k => '建议：' + k)) };
          flip.value = false; setTimeout(() => flip.value = true, 60);
        }
      };
      const onSkill = (evt) => { if (evt.payload && evt.payload.kind === 'draw_card' && openLoc.value) lastGain.value = { draw: evt.payload.kc_id }; };
      window.Net.on('clue_gained', onClue);
      watch(() => S.lastSearchResult, evt => { if (evt) onSearch(evt); });
      window.Net.on('faction_skill', onSkill);

      const tierText = { hot: '有发现', warm: '可能有', cold: '一无所获' };
      const locPayload = (loc) => {
        if (!loc) return {};
        return { location: loc.name || loc.id, location_id: loc.id };
      };
      const iceLocked = () => !!(window.Store.iceBlocksSearch && window.Store.iceBlocksSearch());
      const bounceIce = () => {
        window.Store.toast('破冰结束才能搜证', 'warn');
        S.view = 'chat';
        return true;
      };
      const open = (loc) => {
        if (iceLocked()) return bounceIce();
        openLoc.value = loc; kw.value = ''; lastGain.value = null; searchHint.value = null;
        if (window.SFX && window.SFX.ambient) window.SFX.ambient(loc.id);
      };
      const close = () => {
        openLoc.value = null; lastGain.value = null; searchHint.value = null;
        if (window.SFX && window.SFX.ambient) window.SFX.ambient(null);
      };
      if (iceLocked()) bounceIce();
      const submit = () => {
        if (iceLocked()) return bounceIce();
        if (!openLoc.value) return;
        if (openLoc.value.id === 'loc_clinic') { window.Store.send('skill', { kind: 'draw_card' }); return; }
        if (!String(kw.value || '').trim()) { window.Store.toast('先输入搜证关键词', 'warn'); return; }
        searchHint.value = null;
        window.Store.send('search', Object.assign(locPayload(openLoc.value), { keyword: kw.value }));
      };

      const floorSvg = `
      <svg class="floor-svg" viewBox="0 0 100 62" preserveAspectRatio="none" aria-hidden="true">
        <rect x="1" y="1" width="98" height="60" rx="2" fill="rgba(10,16,30,.22)" stroke="#22345c" stroke-width=".35"/>
        <g stroke="#0f1b33" stroke-width=".18">${[12,24,36,48].map(y=>`<line x1="1" y1="${y}" x2="99" y2="${y}"/>`).join('')}</g>
        <text x="4" y="60.5" fill="#2c4a7c" font-size="2.4" font-family="Consolas">求真档案局 · B1 档案层 / 封锁中</text>
      </svg>`;

      const kcOwned = computed(() => Object.keys(S.kcards).length);
      const tierFn = (loc) => window.Store.locTier(loc.id);
      /* ---- V31 P2：暗拍（2AP：原件留原地，玩家持照片；"声称"可说谎，真伪留圆桌对质） ---- */
      const doStealth = () => {
        if (iceLocked()) return bounceIce();
        if (!openLoc.value) return;
        window.Store.send('skill', Object.assign({ kind: 'stealth_photo' }, locPayload(openLoc.value), { keyword: kw.value }));
      };
      const photoTaken = (evt) => {
        const p = evt.payload || {};
        if (p.event === 'stealth_photo' && p.photo) {
          lastGain.value = { tier: 'limited', name: '暗拍 · ' + p.photo.name, text: p.text, tags: ['暗拍', '照片'] };
          flip.value = false; setTimeout(() => flip.value = true, 60);
        }
        if (p.event === 'office_result') {
          if (p.ok) officeBox.value = false;
        }
      };
      window.Net.on('system', photoTaken);

      /* ---- P3：鱼干微光点锚点（collectibles_p3.md：呼吸闪烁 / act 门槛显隐 / 点击拾取 0AP） ---- */
      const fishOf = (loc) => M.fishCollectibles.find(f => f.loc === loc.id) || null;
      const glowVisible = (f) => f && !S.fish[f.id] && S.act >= f.act && !S.ended;
      const hasGlow = (loc) => glowVisible(fishOf(loc));
      const glowHint = computed(() => {
        if (!openLoc.value) return null;
        const f = fishOf(openLoc.value);
        if (!f) return null;
        if (S.fish[f.id]) return { taken: true, text: '这袋鱼干已被你拾取（成就线：' + M.fishAchievement.name + '）' };
        if (S.act < f.act) return { locked: true, text: `微光还很微弱——第 ${'一二三'[f.act - 1]}幕起显形（压着剧情的彩蛋不泄底）` };
        return { ready: true, anchor: f.anchor, text: '点击微光点拾取（0AP · 彩蛋层不进证据链）' };
      });
      const doCollect = (f) => { if (f && glowVisible(f)) window.Store.send('skill', { kind: 'collect', item: f.id }); };
      const fishGot = computed(() => M.fishCollectibles.filter(f => S.fish[f.id]).length);
      const L = window.Labels;
      const drawKc = computed(() => {
        if (!lastGain.value || !lastGain.value.draw) return null;
        return M.kcards.find(k => k.id === lastGain.value.draw) || { title: '知识卡', author: '' };
      });

      return { S, M, L, openLoc, kw, lastGain, searchHint, flip, open, close, submit, tierText, floorSvg, kcOwned, tierFn, doStealth, fishOf, glowVisible, hasGlow, glowHint, doCollect, fishGot, officeCode, officeBox, visibleLocs, submitOffice, officeUnlocked, officeLoc, locKeywords, drawKc };
    },
    template: `
    <section class="view map-view">
      <header class="view-hd map-hd">
        <h2>场景地图 · 搜证</h2>
        <div class="hd-chips">
          <span class="chip gold" title="P3 彩蛋层：集齐解锁看山Bot 隐藏语音">🐟 鱼干微光 {{ fishGot }}/3</span>
          <span class="chip" v-if="fishGot < 3">地图上闪烁的微光点 = 收集品锚点（0AP 点击拾取）</span>
          <span class="chip good" v-else>已集齐——隐藏语音已解锁</span>
        </div>
      </header>
      <div class="floorplan" v-html="floorSvg">
      </div>
      <button v-if="officeLoc && !officeUnlocked" type="button" class="loc-node"
              style="left:96%;top:92%" @click="officeBox = true">
        <span class="loc-dot"></span>
        <span class="loc-name">局长室</span>
        <span class="loc-tier">🔒 密码门</span>
      </button>
      <ui-modal v-if="officeBox && !officeUnlocked" title="局长室 · 金字塔密码门" @close="officeBox = false">
        <div class="pp-office">
          <div class="pp-office-panel">
            <div class="pp-office-hd">
              <h2>金字塔密码门</h2>
              <p class="pp-office-sub">四位数字。层级即秩序，秩序即密码。</p>
            </div>
            <div class="kw-input">
              <input v-model="officeCode" maxlength="4" inputmode="numeric" placeholder="四位密码" @keyup.enter="submitOffice" />
              <button class="btn primary pp-office-btn" type="button" :disabled="S.busy" @click="submitOffice">提交</button>
            </div>
            <p class="dim">黄金→砖→泥的层数。知识卡《打造职业发展的金字塔》也许有用。</p>
          </div>
        </div>
      </ui-modal>
      <button v-for="loc in visibleLocs" :key="loc.id"
              class="loc-node" :class="tierFn(loc)"
              :style="{ left: loc.pos.x + '%', top: loc.pos.y + '%' }"
              @click="open(loc)">
        <img class="loc-thumb" :src="loc.img" :alt="loc.name">
        <span class="glow-dot" v-if="hasGlow(loc)"
              :style="{ animationDuration: fishOf(loc).glow }"
              :title="'微光点：' + fishOf(loc).anchor"
              @click.stop="doCollect(fishOf(loc))"></span>
        <span class="loc-dot"></span>
        <span class="loc-name">{{ loc.name }}</span>
        <span class="loc-tier">{{ tierText[tierFn(loc)] }}</span>
      </button>

      <ui-modal v-if="openLoc" :title="'搜证 · ' + openLoc.name" @close="close">
        <div class="search-panel">
          <div class="scene-head" :style="{position:'relative'}">
            <video v-if="openLoc.video" :src="openLoc.video" :poster="openLoc.img" class="scene-vid"
                   autoplay loop muted playsinline preload="auto"
                   @error="openLoc.video = null"></video>
            <img v-else-if="openLoc.img" :src="openLoc.img" :alt="openLoc.name">
            <svg-scene v-else :loc="openLoc"></svg-scene>
            <span v-if="hasGlow(openLoc)" class="glow-dot big"
                  :style="{ left: fishOf(openLoc).pos.x + '%', top: fishOf(openLoc).pos.y + '%', animationDuration: fishOf(openLoc).glow }"
                  :title="'微光锚点：' + fishOf(openLoc).anchor"
                  @click="doCollect(fishOf(openLoc))"></span>
            <div class="scene-cap"><b>{{ openLoc.name }}</b><span>{{ openLoc.hint }}</span></div>
          </div>
          <p class="glow-hint" v-if="glowHint" :class="glowHint.taken ? 'taken' : glowHint.locked ? 'locked' : 'ready'">
            <b class="mono">✦ 微光锚点</b>
            {{ glowHint.anchor ? '【' + glowHint.anchor + '】' : '' }}{{ glowHint.text }}
          </p>

          <template v-if="openLoc.id !== 'loc_clinic'">
            <div class="kw-row">
              <span class="lbl">系统建议关键词</span>
              <div class="kw-chips">
                <button v-for="k in locKeywords" :key="k" class="chip pick" @click="kw = k">{{ k }}</button>
              </div>
            </div>
            <div class="kw-input">
              <input v-model="kw" @keyup.enter="submit" maxlength="12" placeholder="自由输入搜证关键词（匹配线索 tag）" />
              <voice-mic v-model="kw" :submit="submit" :disabled="S.busy" :maxlength="12"></voice-mic>
              <button class="btn primary" :disabled="S.busy || S.ap < 1" @click="submit">提交搜证 · 1AP</button>
            </div>
            <div class="stealth-row">
              <button class="btn dark sm" :disabled="S.busy || S.ap < 2 || !kw.trim()" @click="doStealth">▣ 暗拍 · 2AP（对准关键词）</button>
              <span class="dim">暗拍=线索<b>原件留原地</b>（他人仍可搜），你持照片可流出+填「声称」——照片是真的，声称可不一定，圆桌见。干净暗拍攒成就「暗房大师」。</span>
            </div>
            <p class="hint-line">行动点 {{ S.ap }}/{{ S.apMax }} · 地点热度三档：有发现 / 可能有 / 一无所获（不剧透）</p>
          </template>

          <template v-else>
            <div class="clinic-draw">
              <p>心晴自习室不搜物证，搜<b>知识</b>。每次抽取 1 张未持有的知乎知识卡（1AP），全队共享卡池。</p>
              <div class="draw-progress">知识卡收集 {{ kcOwned }}/10</div>
              <button class="btn primary big" :disabled="S.busy || S.ap < 1" @click="submit">抽取知识卡 · 1AP</button>
              <button class="btn ghost" @click="S.view='clinic'">前往心晴诊室使用知识卡 →</button>
            </div>
          </template>

          <section v-if="searchHint" class="search-next-hint" role="status">
            <b>下一步调查</b><p>{{ searchHint.text }}</p>
            <div class="kw-chips"><button v-for="k in searchHint.keywords" :key="k" type="button"
              class="chip pick" :disabled="S.busy" @click="kw = k">调查「{{ k }}」</button></div>
            <small v-if="searchHint.keywords.length">点击填入关键词，再提交搜证（1 行动点）。</small>
            <small v-if="S.ap < 1">本轮行动点已用完，请先推进轮次。</small>
          </section>
          <transition name="flip3d">
          <div v-if="lastGain && !lastGain.draw" class="gain-card" :class="{go: flip}">
            <div class="gain-badge" :class="lastGain.tier">{{ lastGain.miss ? '调查反馈' : lastGain.tier==='boss_flaw' ? '看山破绽' : lastGain.tier==='fake' ? '伪造?' : L.tier(lastGain.tier) }}</div>
            <h4>{{ lastGain.name }}</h4>
            <p>{{ lastGain.text }}</p>
            <div class="gain-tags"><i v-for="t in lastGain.tags" :key="t">#{{t}}</i></div>
          </div>
          <div v-else-if="lastGain && lastGain.draw" class="gain-card kc-gain go">
            <img src="/assets/images/card_back.png" alt="">
            <h4>抽中知识卡</h4>
            <p>《{{ drawKc ? drawKc.title : '知识卡' }}》 · {{ drawKc ? drawKc.author : '' }}</p>
            <p class="gain-tags">已收录进图鉴</p>
          </div>
          </transition>
        </div>
      </ui-modal>
    </section>`,
    beforeUnmount() { /* Net listeners 全局幂等，页面级组件卸载无需清理 */ }
  };

  window.VIEWS = window.VIEWS || {};
  window.VIEWS.map = MapView;
})();
