/* ============================================================
 * views/pollution.js —— 污染对照：左栏原文 / 右栏水军改写，圈出植入段
 * 事件：skill pollution_open / pollution_mark → system.pollution_case|result
 * ============================================================ */
(function () {
  const { ref, computed, onMounted } = Vue;

  const PollutionView = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const picks = ref([]);
      const locked = computed(() => S.act < 2 && !S.demo);
      const cas = computed(() => S.pollution && S.pollution.case);
      const result = computed(() => S.pollution && S.pollution.result);
      const ammo = computed(() => (S.pollution && S.pollution.ammo) || 0);
      const doneN = computed(() => Object.keys((S.pollution && S.pollution.done) || {}).length);
      const total = computed(() => (M.pollutionCases || []).length || 5);

      const open = () => {
        picks.value = [];
        window.Store.send('skill', { kind: 'pollution_open' });
      };
      const toggle = (id) => {
        if (result.value && result.value.case_id === (cas.value && cas.value.id)) return;
        const ix = picks.value.indexOf(id);
        if (ix >= 0) picks.value.splice(ix, 1);
        else picks.value.push(id);
      };
      const submit = () => {
        if (!cas.value) return;
        const need = (cas.value && cas.value.changed_total) || 3;
        if (picks.value.length !== need) return window.Store.toast('本题请圈出 ' + need + ' 处植入段（已选 ' + picks.value.length + '）', 'warn');
        window.Store.send('skill', { kind: 'pollution_mark', case: cas.value.id, picks: picks.value.slice() });
      };
      const next = () => { picks.value = []; open(); };

      onMounted(() => {
        if (locked.value) return;
        if (!cas.value && doneN.value < total.value) open();
      });

      return { S, M, picks, locked, cas, result, ammo, doneN, total, open, toggle, submit, next };
    },
    template: `
    <section class="view pc-view" data-tour="pollution">
      <header class="view-hd pc-hd">
        <h2>污染对照 · 原文 vs 水军改写</h2>
        <div class="hd-chips">
          <span class="chip">已对照 {{ doneN }}/{{ total }}</span>
          <span class="chip" :class="{ good: ammo > 0 }">辟谣弹药 {{ ammo }}</span>
          <span class="chip">圈出被植入的 3 处</span>
        </div>
        <p class="dim">同一篇知乎真实回答：左栏是作者原句，右栏被水军改过。干扰项「看起来像操纵，其实是原文」——判断操纵不能只靠语感。</p>
      </header>

      <div v-if="locked" class="empty-state">
        <b>第二幕解锁</b>
        <p>对照题在「心声泄露」后开放。演示模式可提前进入。</p>
        <button class="btn ghost sm" @click="S.demo=true; open()">演示模式解锁 →</button>
      </div>

      <template v-else>
        <div class="pc-meta" v-if="cas">
          <span class="chip gold">《{{ cas.title }}》</span>
          <span class="chip">知乎 · {{ cas.author }}</span>
          <span class="chip" v-for="m in (cas.manipulation || [])" :key="m">{{ m }}</span>
        </div>

        <div class="pc-dual" v-if="cas">
          <article class="pc-pane">
            <h3>作者原句</h3>
            <p class="pc-orig">{{ cas.original }}</p>
            <p class="dim" v-if="cas.source_note">{{ cas.source_note }}</p>
          </article>
          <article class="pc-pane polluted">
            <h3>水军改写版 · 点选植入段（已选 {{ picks.length }}）</h3>
            <div class="pc-spans">
              <button v-for="s in cas.spans" :key="s.id" type="button" class="pc-span"
                      :class="{ on: picks.includes(s.id) }" :disabled="!!result"
                      @click="toggle(s.id)">{{ s.text }}</button>
            </div>
          </article>
        </div>

        <div class="pc-actions" v-if="cas && !result">
          <button class="btn primary" :disabled="S.busy || picks.length !== (cas.changed_total || 3)" @click="submit">提交对照</button>
          <span class="dim">圈满 {{ cas.changed_total || 3 }} 处再交。全对：弹药 +1（第三幕辟谣可再压热度）、返还 1 AP、热度 -2。误把原句当操纵：热度 +3。</span>
        </div>

        <div v-if="result" class="pc-result" :class="result.passed ? 'ok' : 'bad'">
          <p>{{ result.text }}</p>
          <ul class="pc-whys" v-if="result.revealed && result.revealed.length">
            <li v-for="(r, i) in result.revealed" :key="i"><b>植入：</b>{{ r.text }} <span class="dim">—— {{ r.why }}</span></li>
          </ul>
          <div class="pc-actions">
            <button class="btn primary sm" @click="next">下一题 →</button>
            <button class="btn ghost sm" @click="S.view = (S.act >= 3 ? 'hotfeed' : 'memory')">返回本章</button>
            <button v-if="S.demo && result.passed" class="btn ghost sm" type="button" @click="S.view='chat'">下一步：去圆桌说两句会被归档的话 →</button>
          </div>
        </div>

        <div v-if="!cas && !result" class="empty-state">
          <b>对照题已清空</b>
          <p>水军话术被你拆完了。弹药可带到第三幕辟谣。</p>
          <button class="btn ghost sm" @click="open()">再核一次题库</button>
        </div>
      </template>
    </section>`
  };

  window.VIEWS = window.VIEWS || {};
  window.VIEWS.pollution = PollutionView;
})();
