/* ============================================================
 * views/hotfeed.js —— 热搜页 · 剧本杀 UI 重构版（仿参考设计稿 2）
 * 布局：顶部资源条 → 左角色栏 | DM 面板 + 热搜奥搜榜 TOP 大面板（双列卡）
 *       | 右侧：替代热搜小榜 + 买热搜/官方辟谣 + 竞标进度
 *       → 底部：【知乎搜索】搜证 + 对话 发送 合并条
 * 色：底 #0B0F1C · 榜面板红橙渐变 · 知乎蓝 #4E8FF4
 * 保留：辟谣弹窗（卡 tag 匹配）/ 买热搜弹窗 / 头条竞标 / act≥2 门控
 * ============================================================ */
(function () {
  const { ref, computed, watch } = Vue;

  const HotfeedView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const refutePost = ref(null);
      const buyOpen = ref(false);
      const buyTitle = ref('');
      const page = ref(0);
      const kw = ref('');
      const chatText = ref('');
      const listEl = ref(null);
      const officialHot = ref([]), hotBusy = ref(false), hotNotice = ref('');
      const loadOfficialHot = async () => {
        hotBusy.value = true; hotNotice.value = '';
        try { const h={};
          const r=await fetch('/api/zhihu/hot-list?limit=20',{headers:h}), j=await r.json(); if(!r.ok||!j.ok)throw new Error(j.notice||'热榜接口失败');
          const d=j.data||{}; officialHot.value=d.items||d.Data||d.data||[];
        } catch(e){hotNotice.value=e.message;} finally{hotBusy.value=false;}
      };

      /* A 信息茧房：入茧后热搜被算法投喂——折叠与偏好无关的真相帖、伪造帖置顶 */
      const cocoonActive = computed(() => S.cocoon && S.cocoon.active && !(S.cocoon.broken > 0));
      const topBiasTag = () => { const t = Object.entries(S.searchBias || {}).sort((a, b) => b[1] - a[1])[0]; return t ? t[0] : null; };
      const shownPosts = computed(() => {
        let list = S.hotfeedPanel !== null && Array.isArray(S.hotfeedPanel)
          ? S.hotfeedPanel.slice() : M.posts.filter(p => p.round <= S.round);
        if (cocoonActive.value) {
          const top = topBiasTag();
          list = list.slice().sort((a, b) => {
            const fa = a.fake ? 1 : 0, fb = b.fake ? 1 : 0;
            if (fa !== fb) return fb - fa;                       // 伪造帖置顶（算法爱喂你爱看的）
            const ra = (a.tag && a.tag === top) ? 0 : 1, rb = (b.tag && b.tag === top) ? 0 : 1;
            return ra - rb;                                       // 与偏好无关的真相帖沉底（被折叠）
          });
        }
        return list;
      });
      const cocoonSuppressed = computed(() => cocoonActive.value
        ? M.posts.filter(p => p.round <= S.round && !p.fake && p.tag !== topBiasTag()).length : 0);
      const breakCocoon = () => window.Store.send('cocoon_break', {});
      const ownedKcs = computed(() => Object.keys(S.kcards).map(id => M.kcards.find(k => k.id === id)).filter(Boolean));
      const match = (kc, post) => kc.topic_tag === post.tag;

      const openRefute = p => { refutePost.value = p; };
      const doRefute = (kc) => window.Store.send('skill', { kind: 'refute', post: refutePost.value.id, card: kc.id });
      const doBuy = () => {
        const fake = shownPosts.value.find(p => p.fake) || shownPosts.value[0];
        if (!fake) { window.Store.toast('当前没有可置顶的热搜位', 'warn'); return; }
        window.Store.send('skill', { kind: 'buy_heat', post: fake.id });
        buyOpen.value = false; buyTitle.value = '';
      };
      const heatLabel = computed(() => S.heat >= 90 ? '污染临界' : S.heat >= 55 ? '发酵中' : S.heat >= 30 ? '可控' : '降温成功');
      const signalRows = computed(() => {
        const measured = S.hotfeedSignals;
        const refuted = Object.values(S.refuted || {}).filter(r => r.ok).length;
        const signals = measured || {
          exposure: Math.min(100, S.heat + (S.buyHeats || 0) * 3),
          credibility: Math.max(0, Math.min(100, 60 + refuted * 5 - (S.buyHeats || 0) * 4)),
          emotion: Math.min(100, 40 + Math.floor(S.heat / 3) + (S.buyHeats || 0) * 4)
        };
        return [['exposure', '曝光度'], ['credibility', '讨论可信度'], ['emotion', '情绪强度']]
          .map(([id, label]) => ({ id, label, value: Math.max(0, Math.min(100, Number(signals[id]) || 0)) }));
      });
      const refuted = p => !!(p._refuted || (S.refuted[p.id] && S.refuted[p.id].ok));
      const postSignals = p => p.signals || {
        exposure: Math.min(100, 40 + (p.delta || 0) * 4 + (p.pinned ? 20 : 0)),
        emotion: p.pinned ? 55 : 45
      };

      /* 头条竞标（旧单次出价路径：本地演示/mock 保留原样） */
      const bidAmount = ref(1);
      const hl = computed(() => S.headline);
      const doBid = () => {
        if (!targetPost.value) return;
        window.Store.send('skill', { kind: 'bid_headline', post: targetPost.value.id, topic: targetPost.value.title, amount: Number(bidAmount.value) });
      };
      /* 竞价轮次态：仅当服务端 headline_open(window_id) 到达时启用（ui.js countdown-ring 只调用不改） */
      const auctionLive = computed(() => !!(hl.value && hl.value.mode === 'auction' && !hl.value.settled));
      const aucTopic = ref('');
      const aucAmount = ref(1);
      const aucOver = ref(false);
      const minStep = computed(() => (hl.value && hl.value.minBid) || 1);
      const aucFloor = computed(() => {
        const top = (hl.value && hl.value.topAmount) || 0;
        return Math.max(minStep.value, top + minStep.value);
      });
      const bidName = id => !id ? '神秘人' : (id === (S.playerId || 'player:1') ? '你' : ((window.Labels && window.Labels.who(id)) || id));
      watch(auctionLive, live => {
        if (live) {
          aucOver.value = false;
          aucAmount.value = (hl.value && hl.value.minBid) || 1;
          aucTopic.value = (hl.value && hl.value.topics && hl.value.topics[0] && hl.value.topics[0].id) || '';
        }
      });
      const doAuctionBid = () => {
        const t = ((hl.value && hl.value.topics) || []).find(x => x.id === aucTopic.value);
        if (!t) { window.Store.toast('先选一个头条话题', 'warn'); return; }
        const amt = Number(aucAmount.value);
        if (!Number.isInteger(amt) || amt < aucFloor.value) { window.Store.toast('出价需为整数且至少 ' + aucFloor.value + 'AP（当前最高 + ' + minStep.value + ' 步进）', 'warn'); return; }
        if (amt > S.ap) { window.Store.toast('行动点不足（出价=行动点，当前 ' + S.ap + 'AP）', 'warn'); return; }
        window.Store.send('skill', { kind: 'bid_headline', topic: t.title, amount: amt, ap: amt });
      };
      const doBidPass = () => window.Store.send('skill', { kind: 'bid_pass', ap: 0 });
      const aucDone = () => { aucOver.value = true; };

      const locked = computed(() => (S.act || 1) < 2 && !S.demo);
      const opsOpen = computed(() => S.act >= 3 || !!S.demo);
      const selPost = ref(null);
      const targetPost = computed(() => selPost.value || refutePost.value || shownPosts.value[0] || null);
      const pickPost = (p) => { selPost.value = p; };
      const fakeClues = computed(() => {
        const seen = {};
        const list = [];
        const push = (c) => {
          if (!c || c.tier !== 'fake' || seen[c.id]) return;
          seen[c.id] = 1;
          list.push({ id: c.id, name: c.name || c.id });
        };
        if (window.Store.ownedClues) {
          try { (window.Store.ownedClues() || []).forEach(push); } catch (e) { /* 兜底走线索袋 */ }
        }
        Object.keys(S.clues || {}).forEach(id => {
          const base = (window.Store.clueById && window.Store.clueById(id)) || M.clues.find(c => c.id === id);
          if (base) push(base);
          else if (S.clues[id] && S.clues[id].tier === 'fake') push({ id, name: S.clues[id].name || id, tier: 'fake' });
        });
        return list;
      });
      const flood = () => {
        const p = targetPost.value;
        if (!p) { window.Store.toast('先选一条热搜', 'warn'); return; }
        window.Store.send('skill', { kind: 'flood_comments', post: p.id });
      };
      const report = () => {
        const p = targetPost.value;
        if (!p) { window.Store.toast('先选一条热搜', 'warn'); return; }
        window.Store.send('skill', { kind: 'report_spam', post: p.id, evidence_n: Object.keys(S.clues || {}).length });
      };
      const inspectHeat = () => window.Store.send('skill', { kind: 'truth_check' });
      const plantFake = (id) => window.Store.send('skill', { kind: 'plant_fake', clue: id });

      /* 分页：每页 6 卡 */
      const PER = 6;
      const pageCount = computed(() => Math.max(1, Math.ceil(shownPosts.value.length / PER)));
      watch(pageCount, count => { if (page.value >= count) page.value = count - 1; });
      const pagePosts = computed(() => {
        const start = page.value * PER;
        return shownPosts.value.slice(start, start + PER);
      });
      const prevPage = () => { page.value = (page.value - 1 + pageCount.value) % pageCount.value; };
      const nextPage = () => { page.value = (page.value + 1) % pageCount.value; };
      const closeBoard = () => { S.view = 'chat'; };

      const stars = (p) => {
        const n = Math.max(1, Math.min(5, Math.ceil((p.delta || 4) / 3)));
        return '★'.repeat(n) + '☆'.repeat(5 - n);
      };
      const no = (p, i) => '#' + String((p.round || 1) * 100 + i).padStart(2, '0');
      const isBought = (p) => p.author === '水军' || p.pinned;

      const suspects = computed(() => M.chars.filter(c => c.id !== 'dm'));
      const playerCharId = computed(() => window.Store.playerCharacterId());
      const selectTarget = id => window.Store.selectChatTarget(id);
      const cur = computed(() => M.chars.find(c => c.id === S.currentNpc)
        || { id: 'dm', name: '刘看山' });

      const lastDm = computed(() => {
        for (let i = S.chat.length - 1; i >= 0; i--)
          if (S.chat[i].actor === 'dm') return S.chat[i];
        return null;
      });

      const send = () => {
        const t = chatText.value.trim(); if (!t) return;
        if (window.Store.send('chat', { char_id: S.currentNpc, target: S.currentNpc, text: t }) !== false) chatText.value = '';
      };

      const doSearch = () => {
        const keyword = kw.value.trim();
        if (!keyword) { window.Store.toast('先输入或点选一个搜证关键词', 'warn'); return; }
        window.Store.send('search', { location: '监控室', keyword });
      };
      const kwPool = computed(() => {
        const pool = [];
        (M.locations || []).forEach(l => (l.keywords || []).slice(0, 2).forEach(k => pool.push(k)));
        return pool.slice(0, 4);
      });

      return { S, M, refutePost, buyOpen, buyTitle, shownPosts, ownedKcs, officialHot, hotBusy, hotNotice, loadOfficialHot, match, openRefute, doRefute, doBuy,
               heatLabel, signalRows, postSignals, refuted, bidAmount, hl, doBid, locked, page, pageCount, pagePosts, prevPage, nextPage,
               auctionLive, aucTopic, aucAmount, aucOver, aucFloor, minStep, bidName, doAuctionBid, doBidPass, aucDone,
               closeBoard, stars, no, isBought, suspects, cur, lastDm, send, chatText, kw, doSearch, kwPool,
               cocoonActive, cocoonSuppressed, breakCocoon, playerCharId, selectTarget,
               opsOpen, selPost, targetPost, pickPost, fakeClues, flood, report, plantFake, inspectHeat };
    },
    template: `
    <section class="view hotfeed-view hf">

      <div class="hf-grid">
        <section class="rv-card" style="grid-column:1/-1">
          <b>知乎官方实时热榜</b>
          <button class="btn ghost sm" @click="loadOfficialHot" :disabled="hotBusy">{{ hotBusy ? '读取中…' : '刷新官方热榜' }}</button>
          <span class="dim" v-if="hotNotice">{{ hotNotice }}</span>
          <div v-if="officialHot.length" class="hf-post-signals"><span v-for="(h,i) in officialHot.slice(0,8)" :key="i">{{ h.Title || h.title || h.name || h }}</span></div>
        </section>
        <!-- 左侧角色栏 -->
        <div class="hf-rail">
          <button v-for="(c, i) in suspects" :key="c.id" class="hf-rail-ava"
                  :class="{ on: S.currentNpc === c.id }" @click="selectTarget(c.id)"
                  :disabled="c.id === playerCharId" :title="c.name + (c.id === playerCharId ? ' · 你' : '')">
            <em>{{ i + 1 }}</em>
            <img :src="c.avatar" :alt="c.name">
          </button>
        </div>

        <!-- DM 面板 -->
        <div class="hf-dm">
          <div class="hf-dm-tag">DM 面板</div>
          <img class="hf-dm-ava" src="/assets/images/bust/dm_kanshan_holo.png" alt="DM">
          <b class="hf-dm-name">刘看山</b>
          <div class="hf-dm-brief">
            <span class="hf-dm-sub">系统播报</span>
            <p>{{ lastDm ? lastDm.text : '热搜被恶意操纵中。辟谣需要知识，买热搜需要……胆子。' }}</p>
          </div>
        </div>

        <!-- 中央：热搜奥搜榜 TOP 大面板 -->
        <div class="hf-board" :class="{ locked }">
          <div class="hf-board-hd">
            <b>热搜臭榜 TOP</b>
            <button class="hf-x" @click="closeBoard" title="返回对话">✕</button>
          </div>
          <section class="hf-signals" aria-label="舆论观察" aria-live="polite">
            <header><b>舆论观察</b><span>{{ S.hotfeedSignals ? '本局状态' : '本地估算' }}</span></header>
            <div class="hf-signal-grid">
              <div v-for="metric in signalRows" :key="metric.id" class="hf-signal" :class="metric.id">
                <span>{{ metric.label }}</span><strong>{{ metric.value }}<small>/100</small></strong>
                <meter min="0" max="100" :value="metric.value" :aria-label="metric.label"></meter>
              </div>
            </div>
            <p>指数反映传播与讨论状态；单帖真假仍需证据核验。</p>
            <button class="btn ghost" @click="inspectHeat" :disabled="locked || S.ap < 1 || S.busy || S.isSpectator">侦察舆论 · 1AP</button>
            <p v-if="S.heatReport" role="status">{{ S.heatReport.text }} · 被压制线索 {{ S.heatReport.blocked }} 条</p>
          </section>
          <div class="inv-cta" v-if="S.act >= 2 || S.demo">
            <div>
              <b>污染对照</b>
              <p class="dim">一篇知乎原回答被水军改写了。左右对照，圈出真正被植入的 3 处。</p>
            </div>
            <button class="btn primary sm" type="button" @click="S.view='pollution'">开始对照 →</button>
          </div>
          <div v-if="cocoonActive" class="hf-cocoon">
            <span>🫧 算法已为你折叠 <b>{{ cocoonSuppressed }}</b> 条异见——热搜只喂你爱看的。</span>
            <button class="hf-break" type="button" @click="breakCocoon">🦋 破茧</button>
          </div>
          <div v-if="locked" class="hf-locked">
            🔒 热搜系统将在第二幕「心声泄露」后解锁——现在，先听听大家的说法。
          </div>
          <template v-else>
            <template v-if="pagePosts.length">
              <div class="hf-cards">
                <article v-for="(p, i) in pagePosts" :key="p.id" class="hf-card"
                       :class="{ pinned: isBought(p), refuted: refuted(p), red: p.delta >= 8, sel: targetPost && targetPost.id === p.id }"
                       @click="pickPost(p)">
                  <span class="hf-no">{{ no(p, i) }}</span>
                  <span v-if="isBought(p)" class="hf-bought">「买的热搜」</span>
                  <h4>{{ p.title }}</h4>
                  <span class="hf-stars">{{ stars(p) }}</span>
                  <div class="hf-post-signals">
                    <span>曝光 {{ postSignals(p).exposure }}</span><span>情绪 {{ postSignals(p).emotion }}</span>
                    <span>{{ refuted(p) ? '已完成核验' : '可信度待核验' }}</span>
                  </div>
                  <div class="hf-card-ft">
                    <span class="hf-delta" :class="{ hot: p.delta >= 8 }">热度 +{{ p.delta }}</span>
                    <span v-if="refuted(p)" class="hf-ref-ok">✅ 已辟谣</span>
                    <button v-else class="hf-refute" @click.stop="openRefute(p)">辟谣 · 2AP</button>
                  </div>
                </article>
              </div>
              <button class="hf-arrow left" @click="prevPage" aria-label="上一页热搜">◀</button>
              <button class="hf-arrow right" @click="nextPage" aria-label="下一页热搜">▶</button>
              <div class="hf-page">{{ page + 1 }} / {{ pageCount }}</div>
            </template>
            <ux-state v-else dense glyph="🔥" title="榜上还没有今天的帖子"
              desc="热搜榜随轮次刷新——推动「进入下一章 ▸」，或者先在圆桌问出点东西，热度一起来，帖子自己会长出来。"></ux-state>
          </template>
        </div>

        <!-- 右侧：替代热搜小榜 + 操作 + 进度 -->
        <div class="hf-side">
          <div class="hf-side-hd">替代热搜小榜</div>
          <div class="hf-side-list">
            <button v-for="p in shownPosts.slice(0, 4)" :key="'s' + p.id" class="hf-side-item" type="button"
                 :class="{ sel: targetPost && targetPost.id === p.id }" @click="pickPost(p)" :title="p.title">
              {{ p.title }}
            </button>
            <ux-state v-if="!shownPosts.length" dense glyph="◷" title="本轮暂无可辟谣的帖子"
              desc="等热搜刷出来，或者干脆自己买一条——亲眼看着谣言怎么长起来，也是一种求真。"></ux-state>
          </div>
          <button v-if="!S.demo" class="hf-buy" @click="buyOpen = true" :disabled="locked">买 热 搜</button>
          <button class="hf-refute-all" @click="openRefute(targetPost || shownPosts[0])" :disabled="locked || !shownPosts.length">官 方 辟 谣</button>
          <template v-if="opsOpen">
            <button class="hf-refute-all" type="button" :disabled="locked || !targetPost" @click="flood">控 评</button>
            <button class="hf-refute-all" type="button" :disabled="locked || !targetPost" @click="report">举 报</button>
            <p class="dim">控评加热度，举报需已有证据，伪证会进公开池。</p>
            <button v-for="c in fakeClues" :key="c.id" class="hf-side-item" type="button"
                    :disabled="locked" @click="plantFake(c.id)">投放伪证 · {{ c.name }}</button>
            <p class="dim" v-if="!fakeClues.length">尚未持有可投放的伪证。</p>
          </template>
          <div class="hf-progress">
            <span>热度 {{ S.heat }}%</span>
            <div class="bar"><i :style="{ width: S.heat + '%' }"></i></div>
          </div>
          <div class="hf-progress" v-if="!S.demo">
            <b>争取头条</b>
            <template v-if="auctionLive">
              <div class="hl-auction">
                <header class="hl-auc-hd">
                  <countdown-ring :key="hl.windowId" :seconds="hl.deadlineIn || 60" :running="true" label="竞价窗口"></countdown-ring>
                  <span class="hl-auc-top" v-if="hl.top">当前最高：<b>{{ bidName(hl.top) }}</b> · {{ hl.topAmount }}AP</span>
                  <span class="hl-auc-top dim" v-else>暂无人出价 · 底价 {{ hl.minBid }}AP</span>
                </header>
                <div class="hl-auc-topics">
                  <button v-for="t in hl.topics" :key="t.id" class="hf-side-item" type="button"
                          :class="{ sel: aucTopic === t.id }" @click="aucTopic = t.id" :title="t.title">{{ t.title }}</button>
                </div>
                <label class="hl-auc-amt">出价（步进 {{ minStep }}AP，至少 {{ aucFloor }}AP）
                  <input v-model.number="aucAmount" type="number" :min="aucFloor" :step="minStep" :max="Math.min(12, S.ap)" aria-label="头条竞价出价（行动点）">
                </label>
                <div class="hl-auc-btns">
                  <button class="btn primary" @click="doAuctionBid" :disabled="aucOver || S.busy || S.isSpectator || S.ap < aucFloor">出价</button>
                  <button class="btn ghost" @click="doBidPass" :disabled="S.busy || S.isSpectator">弃拍</button>
                </div>
                <p class="dim" v-if="aucOver">竞价窗口已关，等待结算…</p>
                <p class="dim" v-else>出价=行动点 · 被反超可加价或弃拍 · 流拍时头条位空置。</p>
              </div>
            </template>
            <template v-else>
              <p class="dim">{{ targetPost ? targetPost.title : '先选择一条热搜' }}</p>
              <label>投入行动点 <input v-model.number="bidAmount" type="number" min="1" :max="Math.min(12, S.ap)" aria-label="头条出价行动点"></label>
              <button class="btn primary" @click="doBid" :disabled="!opsOpen || S.busy || S.isSpectator || !targetPost || !Number.isInteger(bidAmount) || bidAmount < 1 || bidAmount > Math.min(12, S.ap)">提交出价</button>
              <p class="dim">{{ opsOpen ? '当前为单次出价即时结算；置顶不代表内容真实。' : '第三幕解锁' }}</p>
            </template>
            <p v-if="hl && hl.settled" role="status">{{ hl.result || '本轮头条已结算' }}{{ hl.cost ? ' 消耗 ' + hl.cost + ' AP。' : '' }}</p>
          </div>
          <div class="hf-progress">
            <span>辟谣成功 {{ Object.values(S.refuted || {}).filter(r => r.ok).length }} 次</span>
            <div class="bar"><i :style="{ width: Math.min(100, Object.values(S.refuted || {}).filter(r => r.ok).length * 25) + '%' }"></i></div>
          </div>
        </div>
      </div>

      <!-- 底部：搜证 + 对话 合并条 -->
      <div class="hf-bottom">
        <span class="hf-plus">＋</span>
        <span class="hf-btag">【知乎搜索】搜证</span>
        <input v-model="kw" maxlength="30" placeholder="🔍 搜证关键词…" @keyup.enter="doSearch">
        <voice-mic v-model="kw" :submit="doSearch" :maxlength="30"></voice-mic>
        <button class="hf-chip" @click="doSearch">搜证 1AP</button>
        <span class="hf-div"></span>
        <span class="hf-btag">💬 对话</span>
        <input v-model="chatText" maxlength="60" :placeholder="'请输入内容…（对 ' + cur.name + '）'" @keyup.enter="send">
        <voice-mic v-model="chatText" :submit="send" :maxlength="60"></voice-mic>
        <button class="hf-send" @click="send">发送</button>
      </div>

      <!-- 辟谣弹窗 / 买热搜弹窗（保留既有逻辑） -->
      <ui-modal v-if="refutePost" :title="'辟谣 · ' + refutePost.title" @close="refutePost=null">
        <div class="refute-panel">
          <p class="dim">帖子话题：<b class="hl">#{{ refutePost.tag }}</b> —— 选一张话题对得上的知识卡，对不上会被群嘲。</p>
          <p class="dim" v-if="S.pollution && S.pollution.ammo">对照弹药 {{ S.pollution.ammo }}：匹配成功会再压热度 2 点并消耗 1 发。</p>
          <div class="kc-pick">
            <button v-for="kc in ownedKcs" :key="kc.id" class="kc-pick-item" :class="{match: match(kc, refutePost)}"
                    @click="doRefute(kc)">
              <b>《{{ kc.title }}》</b>
              <span>{{ kc.author }} · 话题 {{ kc.topic_tag }}</span>
              <em>{{ match(kc, refutePost) ? '✅ 匹配' : '❌ 不匹配（会被群嘲）' }}</em>
            </button>
          </div>
          <ux-state v-if="!ownedKcs.length" dense glyph="🃏" title="弹药库是空的——拿什么辟谣？"
            desc="知识卡在「现场搜证 → 心晴自习室」抽（1AP/张）。没有卡也能买热搜，但那只会把水搅得更浑。"
            action="去抽卡 ▸" @action="S.view='map'"></ux-state>
        </div>
      </ui-modal>

      <ui-modal v-if="buyOpen" title="买热搜（1AP）" @close="buyOpen=false">
        <div class="kw-input">
          <input v-model="buyTitle" maxlength="16" placeholder="# 自定义话题 #（默认：#档案局连夜吃瓜#）" />
          <button class="btn warn" @click="doBuy">砸钱上榜 · 热度 +5</button>
        </div>
        <p class="dim">污染阵营常规操作。热度涨了之后，记得留 AP 给辟谣——除非你就是污染阵营（那没事了）。</p>
      </ui-modal>
    </section>`
  };

  window.VIEWS.hotfeed = HotfeedView;
})();
