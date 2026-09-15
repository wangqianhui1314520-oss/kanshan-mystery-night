/* ============================================================
 * views/bag.js —— 个人证物袋（线索分级 + 证据合成 + 交叉验证）
 * ============================================================ */
(function () {
  const { ref, computed } = Vue;

  const BagView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const detail = ref(null);
      const tab = ref('clues');

      const resolve = id => (window.Store.clueById && window.Store.clueById(id)) || M.clues.find(c => c.id === id);
      const owned = computed(() => Object.keys(S.clues).map(id => resolve(id) || {
        id, name: id.startsWith('tamper_') ? '篡改点' : ((window.Labels && window.Labels.clue(id)) || '线索'),
        tier: id.startsWith('tamper_') ? 'hidden' : 'public',
        tags: [], text: '引擎固化的记忆矛盾线索。', linked: ['tn_08'], fake_of: null
      }).filter(Boolean));

      const byTier = t => owned.value.filter(c => c.tier === t);
      const synth = computed(() => S.synth);
      const nodeById = id => (window.Labels && window.Labels.node(id)) || '真相节点';
      const saltIds = computed(() => (M.salt7Ids && M.salt7Ids.length) ? M.salt7Ids : ['salt_f1', 'salt_f2', 'salt_f3', 'salt_f4', 'clue_022']);
      const saltN = computed(() => saltIds.value.filter(id => S.clues[id]).length);
      const saltCard = id => resolve(id) || { id, name: (window.Labels && window.Labels.clue(id)) || '盐言碎片', fact: '', unlock: '' };
      const flippedOf = (c) => !!(c && ((S.flipped && S.flipped[c.id]) || c.back));
      const sideBack = (c) => {
        if (!c) return '';
        if (c.back) return c.back;
        const rec = S.flipped && S.flipped[c.id];
        return (rec && rec.back) || (c.sides && c.sides.back) || '';
      };
      const open = c => { detail.value = c; };
      const flipSide = () => window.Store.send('skill', { kind: 'flip_side', clue_id: detail.value.id });
      /* 缺口2：WS 走服务端 cross_check 裁决；通道不可用（send=false）回退本地演示并明确提示 */
      const crossCheck = () => {
        const ok = window.Store.send('skill', { kind: 'cross_check', clue_id: detail.value.id });
        if (!ok) window.Store.toast('服务端通道不可用：交叉验证已回退本地演示判定（结果不同步）', 'warn');
      };
      const onFlip = (evt) => {
        const p = evt.payload || {};
        if (p.event !== 'flip_result' || !p.clue_id) return;
        if (!S.flipped) S.flipped = {};
        S.flipped[p.clue_id] = { back: p.back, at: S.round };
        if (p.text) window.Store.toast(p.text, 'gold');
      };
      window.Net.on('system', onFlip);
      const exposed = c => !!S.exposedFakes[c.id];
      const realOf = c => c.fake_of ? resolve(c.fake_of) : null;
      const realOwned = c => { const r = realOf(c); return r && !!S.clues[r.id]; };

      const counts = computed(() => ({
        all: owned.value.length,
        fake: byTier('fake').length,
        flaw: byTier('boss_flaw').length,
        synth: synth.value.length
      }));

      /* ---- V31 P2：暗拍照片墙（照片=持有人专属；流出=分享+声称，真伪留圆桌对质） ---- */
      const shareFor = ref(null);
      const claimText = ref('');
      const doShare = () => {
        /* 缺口1：WS 走服务端 share_photo（owner 校验 + photo_shared 广播）；
           通道不可用（send=false）回退本地演示并明确提示 */
        const target = shareFor.value, claim = claimText.value;
        const ok = window.Store.send('skill', { kind: 'share_photo', photo_id: target.id, claim });
        if (!ok) {
          const ph = S.photos.find(x => x.id === target.id);
          if (ph) { ph.shared = true; ph.claim = String(claim || '').slice(0, 60) || '（未填声称）'; }
          window.Store.toast('服务端通道不可用：照片流出已回退本地演示（结果不同步）', 'warn');
        }
        shareFor.value = null; claimText.value = '';
      };
      const photoLocName = id => (window.Labels && window.Labels.place(id)) || (M.locations.find(l => l.id === id) || {}).name || '现场';

      /* ---- P3：鱼干收藏（微光点拾取的收集品） ---- */
      const fishGot = computed(() => M.fishCollectibles.filter(f => S.fish[f.id]).length);
      const fishLocName = f => (window.Labels && window.Labels.place(f.loc)) || '现场';
      const stillOf = loc => (window.ASSETS && window.ASSETS.photoStill(loc)) || '/assets/images/scene_monitor.png';
      const fishIcon = '/assets/images/icon_fish.png';

      const L = window.Labels;
      return { S, M, L, owned, byTier, synth, detail, tab, open, crossCheck, flipSide, flippedOf, sideBack, saltIds, saltN, saltCard, exposed, realOf, realOwned, nodeById, counts, shareFor, claimText, doShare, photoLocName, fishGot, fishLocName, stillOf, fishIcon };
    },
    template: `
    <section class="view bag-view">
      <header class="view-hd">
        <h2>个人证物袋</h2>
        <div class="hd-chips">
          <span class="chip">共 {{ counts.all }}</span>
          <span class="chip warn" v-if="counts.fake">伪证 {{ counts.fake }}（需交叉验证）</span>
          <span class="chip flaw" v-if="counts.flaw">破绽 {{ counts.flaw }}/5</span>
          <span class="chip good" v-if="counts.synth">证据卡 {{ counts.synth }}</span>
          <span class="chip gold" v-if="S.photos.length">▣ 暗拍 {{ S.photos.length }}</span>
          <span class="chip purple" v-if="S.tamperPts">篡改点 {{ S.tamperPts }}</span>
          <span class="chip gold">盐言 {{ saltN }}/5</span>
        </div>
      </header>

      <div class="seg">
        <button :class="{on: tab==='clues'}" @click="tab='clues'">线索卡</button>
        <button :class="{on: tab==='salt'}" @click="tab='salt'">盐言碎片（{{ saltN }}/5）</button>
        <button :class="{on: tab==='synth'}" @click="tab='synth'">合成证据卡（圆桌弹药）</button>
        <button :class="{on: tab==='photos'}" @click="tab='photos'">暗拍照片（{{ S.photos.length }}）</button>
        <button :class="{on: tab==='fish'}" @click="tab='fish'">🐟 鱼干收集（{{ fishGot }}/3）</button>
      </div>

      <div v-if="tab==='clues'" class="clue-grid">
        <clue-card v-for="c in owned" :key="c.id" :clue="c" @open="open"></clue-card>
        <ux-state v-if="!owned.length" glyph="▦" title="证物袋还是空的"
          desc="去「现场搜证」挑个地点，输个关键词试试。搜不到也别急——看山保证，至少有一句好笑的环境描写。"
          action="去现场搜证 ▸" @action="S.view='map'"></ux-state>
      </div>

      <div v-else-if="tab==='salt'" class="fish-wall">
        <div v-for="id in saltIds" :key="id" class="fish-card" :class="{got: !!S.clues[id], locked: !S.clues[id]}">
          <span class="fish-icon" :class="{ locked: !S.clues[id] }">{{ S.clues[id] ? '✦' : '🔒' }}</span>
          <div class="fish-meta">
            <b>{{ saltCard(id).name }}</b>
            <span class="dim" v-if="S.clues[id]">已入手——{{ saltCard(id).fact }}</span>
            <span class="dim" v-else>未入手{{ L.unlock(saltCard(id).unlock) ? ' · ' + L.unlock(saltCard(id).unlock) : '' }}</span>
          </div>
          <button v-if="S.clues[id]" class="btn ghost sm" type="button" @click="open(saltCard(id))">查看</button>
        </div>
        <p class="dim">进度 {{ saltN }}/5 —— 集齐可走向隐藏结局「被删的第 7 章」。</p>
      </div>

      <!-- P3：鱼干收藏（微光点拾取） -->
      <div v-else-if="tab==='fish'" class="fish-wall">
        <div v-for="f in M.fishCollectibles" :key="f.id" class="fish-card" :class="{got: S.fish[f.id], locked: S.act < f.act}">
          <span class="fish-icon" :class="{ locked: !S.fish[f.id] }">
            <img v-if="S.fish[f.id] || S.act >= f.act" :src="fishIcon" alt="鱼干">
            <template v-else>🔒</template>
          </span>
          <div class="fish-meta">
            <b>{{ fishLocName(f) }} · {{ f.anchor }}</b>
            <span class="dim" v-if="S.fish[f.id]">已拾取（R{{ S.fish[f.id].at }}）——{{ f.pickup }}</span>
            <span class="dim" v-else-if="S.act >= f.act">微光已显形：回场景图点击微光点拾取（0AP）</span>
            <span class="dim" v-else>第 {{ '一二三'[f.act - 1] }}幕起显形（微光点锚点不剧透）</span>
          </div>
          <button v-if="S.act >= f.act && !S.fish[f.id]" class="btn dark sm" @click="S.view='map'">去寻微光 →</button>
        </div>
        <p class="dim" v-if="fishGot >= 3">🏆 成就「{{ M.fishAchievement.name }}」已解锁——看山Bot 隐藏语音 4 段播毕；若触发 Boss 揭示演出，将加播终极层语音。</p>
        <p class="dim" v-else>彩蛋层规则：不占行动点、不进证据链、不影响结局判定——只加温度，不泄底。集齐 3 袋解锁看山Bot 隐藏语音（成就：{{ M.fishAchievement.name }}）。</p>
      </div>

      <div v-else-if="tab==='photos'" class="photo-wall">
        <div v-for="ph in S.photos" :key="ph.id" class="photo-card" :class="{shared: ph.shared}">
          <div class="photo-frame">
            <img :src="stillOf(ph.loc)" :alt="ph.name">
            <i class="photo-shine"></i>
          </div>
          <div class="photo-meta">
            <b>{{ ph.name }}</b>
            <span class="dim">摄于 {{ photoLocName(ph.loc) }} · R{{ ph.at }} · 原件留原地（他人仍可搜）</span>
            <span v-if="ph.shared" class="chip tiny warn">已流出 · 声称「{{ ph.claim }}」</span>
            <span v-else class="chip tiny">未流出</span>
          </div>
          <button v-if="!ph.shared" class="btn warn sm" @click="shareFor=ph">流出 + 填声称</button>
        </div>
        <ux-state v-if="!S.photos.length" dense glyph="▣" title="还没有暗拍照片"
          desc="在「现场搜证」面板用「▣ 暗拍 · 2AP」对准关键词拍一张。原件留原地不消耗线索供给；照片在手想流就流——声称可以说谎，圆桌对质见真章（成就：暗房大师）。"></ux-state>
      </div>

      <div v-else class="synth-list">
        <div v-for="ev in synth" :key="ev.id" class="synth-card">
          <div class="synth-top"><span class="chip good">证据卡</span><b>{{ ev.name }}</b></div>
          <p>互证线索 {{ ev.clueIds.length }} 条 · 覆盖真相节点【{{ nodeById(ev.node) }}】</p>
          <div class="synth-refs">
            <span v-for="cid in ev.clueIds" :key="cid" class="chip tiny">{{ ((Store.clueById && Store.clueById(cid)) || {}).name || L.clue(cid) }}</span>
          </div>
        </div>
        <ux-state v-if="!synth.length" dense glyph="◈" title="暂无合成证据卡"
          desc="凑齐 3 条共享同一真相节点的线索，引擎会自动合成。指认时递交它，比散着的三张单卡更有杀伤力。"></ux-state>
      </div>

      <ui-modal v-if="detail" :title="detail.name" @close="detail=null">
        <div class="clue-detail" :class="detail.tier">
          <!-- 证据影像层：clues.media 存在则挂静音循环视频，加载失败自动降级为纯文本 -->
          <figure class="cd-media" v-if="detail.media">
            <video :src="detail.media" loop muted playsinline autoplay @error="detail.media = null"></video>
            <figcaption>▣ 现场影像还原 · 档案局监控存档</figcaption>
          </figure>
          <div class="cd-row"><span class="lbl">级别</span>
            <span class="chip" :class="detail.tier==='boss_flaw' ? 'flaw' : detail.tier==='fake' ? 'warn' : ''">
              {{ detail.tier==='boss_flaw' ? '看山破绽（隐藏 Boss 伏笔）' : detail.tier==='fake' ? '疑似伪造' : L.tier(detail.tier) }}</span>
          </div>
          <div class="cd-row"><span class="lbl">事实</span><p>{{ (detail.sides && detail.sides.front) || detail.fact || detail.text }}</p></div>
          <div class="cd-row" v-if="detail.sides">
            <span class="lbl">双面锁</span>
            <button class="btn ghost sm" type="button" @click="flipSide">翻面</button>
            <p v-if="flippedOf(detail)">背面：{{ sideBack(detail) }}</p>
            <p v-else class="dim">背面尚未解锁。条件达成后再翻。</p>
          </div>
          <div class="cd-row" v-if="detail.flavor"><span class="lbl">扩写</span><p class="flavor">{{ detail.flavor }}</p></div>
          <div class="cd-row"><span class="lbl">标签</span><div><i v-for="t in detail.tags" :key="t" class="chip tiny">#{{t}}</i></div></div>
          <div class="cd-row"><span class="lbl">真相节点</span>
            <div><span v-for="n in (detail.linked||[])" :key="n" class="chip tiny blue">{{ nodeById(n) }}</span>
            <span v-if="!(detail.linked||[]).length" class="dim">无（欢乐向卡，不入证据链）</span></div>
          </div>
          <div class="cd-row" v-if="detail.fake_of"><span class="lbl">疑似指向</span>
            <p>伪造对象：《{{ (realOf(detail)||{}).name }}》
            <template v-if="realOwned(detail)">——你已持有真线索，可交叉验证！</template>
            <template v-else>（尚未持有真线索，验证暂无实锤）</template></p>
            <button class="btn warn" @click="crossCheck">交叉验证（免费）</button>
            <button v-if="detail.confront" class="btn primary sm" type="button" @click="crossCheck">提起证伪对质</button>
            <p v-if="exposed(detail)" class="exposed">⛔ 已被交叉验证拆穿：伪证实锤，自动从证据链除名。</p>
          </div>
        </div>
      </ui-modal>

      <!-- V31：照片流出弹窗（分享 + 填声称） -->
      <ui-modal v-if="shareFor" title="照片流出 · 填声称" @close="shareFor=null">
        <div class="share-photo-form">
          <p><b>{{ shareFor.name }}</b> <span class="dim">（照片是真的，「声称」可不一定）</span></p>
          <div class="kw-input">
            <input v-model="claimText" maxlength="60" placeholder="例：这是我在监控室拍到的高清图，上面清楚拍到了 V587…" />
            <button class="btn warn" @click="doShare">流出</button>
          </div>
          <p class="dim">流出的照片会进圆桌对质池：声称与事实不符会被当场拆穿，照片属于你，谎言也属于你（成就「暗房大师」只计干净暗拍）。</p>
        </div>
      </ui-modal>
    </section>`
  };

  window.VIEWS.bag = BagView;
})();
