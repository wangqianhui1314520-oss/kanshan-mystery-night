/* ============================================================
 * views/kcards.js —— 知识卡图鉴（10 卡收集，卡背=知乎知识蓝）
 * ============================================================ */
(function () {
  const { ref, computed } = Vue;

  const CardBook = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const detail = ref(null);
      const ownedCount = computed(() => Object.keys(S.kcards).length);
      const bindName = kc => {
        if (kc.binds === 'all') return '全队 · 团队 buff';
        if (kc.binds === 'org') return '档案局 · 组织谜题';
        const c = M.chars.find(x => x.id === kc.binds);
        return c ? c.name : '—';
      };
      const effectName = { evidence: '证据', boss_key: '关键钥匙', memory_unlock: '记忆解锁', buff_ap: '行动点加成', plot_fragment: '剧情碎片' };
      const open = kc => { detail.value = kc; };
      const topicOf = kc => (window.ASSETS && window.ASSETS.topicOf(kc.topic_tag)) || { hue: 'focus', mark: '知' };
      return { S, M, detail, ownedCount, bindName, effectName, open, topicOf };
    },
    template: `
    <section class="view kcards-view">
      <header class="view-hd">
        <h2>知识卡图鉴</h2>
        <div class="hd-chips">
          <span class="chip good">已收集 {{ ownedCount }}/10</span>
          <span class="chip">获取：场景图「心晴自习室」抽卡（1AP/张）</span>
        </div>
      </header>
      <ux-state v-if="!ownedCount" dense glyph="🃏" title="一张卡都还没有"
        desc="知识卡是这一局的「求真弹药」：既能拆穿帖子，也能撬开一颗不肯说话的心。去「现场搜证 → 心晴自习室」抽取（1AP/张）。"
        action="去抽卡 ▸" @action="S.view='map'"></ux-state>
      <div class="kc-progress"><div class="kc-bar" :style="{ width: (ownedCount*10) + '%' }"></div></div>

      <div class="kc-grid">
        <kc-card v-for="kc in M.kcards" :key="kc.id" :kc="kc" :owned="!!S.kcards[kc.id]" @open="open"></kc-card>
      </div>

      <ui-modal v-if="detail" :title="'《' + detail.title + '》'" @close="detail=null">
        <div class="kc-detail">
          <div class="kc-detail-crest" :class="'hue-' + topicOf(detail).hue">
            <img v-if="topicOf(detail).emblem" :src="topicOf(detail).emblem" alt="">
            <span v-else>{{ topicOf(detail).mark }}</span>
          </div>
          <p class="kc-meta">知乎知识 · 作者 <b>{{ detail.author }}</b> · 话题 {{ detail.topic_tag }} · 效果 {{ effectName[detail.effect] || '特殊效果' }}</p>
          <p class="kc-meta dim">源自知乎《{{ detail.title }}》 · 答主 @{{ detail.author }}
            <a :href="'https://www.zhihu.com/search?q=' + encodeURIComponent(detail.title)" target="_blank" rel="noopener">去知乎看原文 ↗</a></p>
          <div class="golden-list">
            <blockquote v-for="(g,i) in detail.golden" :key="i" :style="{ animationDelay: (i*0.5)+'s' }">“{{ g }}”</blockquote>
          </div>
          <p class="kc-summary">{{ detail.summary }}</p>
          <div class="cd-row"><span class="lbl">心病匹配</span><b class="match">{{ bindName(detail) }}</b>
            <span class="dim">——开导时选中此卡与该对象，匹配则「先专业后破防」，不匹配则全员群嘲。</span></div>
        </div>
      </ui-modal>
    </section>`
  };

  window.VIEWS.kcards = CardBook;
})();
