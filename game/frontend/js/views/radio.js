/* ============================================================
 * views/radio.js —— 档案局内部广播台
 * ============================================================ */
(function () {
  const FALLBACK = [
    '【广播台】现在是档案局时间。封控第 {n} 小时，泡面消耗 4 桶，线索 {c} 条，真相进度：本台不便透露。',
    '【广播台】天气预报：档案局今夜有雾，能见度不足一条热搜。请各位不要出门——反正门也锁着。',
    '【广播台】本台提醒：折叠区怨灵沉底君的发言没有被折叠，请大家正常倾听，不要围观。',
    '【广播台】寻物启事：一袋彩虹鳟鱼味鱼干，最后出现于 21:00 前的档案室。知情者请勿私聊，直接喊出来。',
    '【广播台】寻人启事：首席侦探刘看山，男，北极狐，最后出现时说「谁都不许跟来」。',
    '【广播台】点播台规则：1 行动点 = 30 秒广播时间。本台保留因内容太尬而提前掐断的权利。'
  ];

  const RadioView = {
    setup() {
      const S = window.Store.state;
      const rd = Vue.computed(() => S.radio || { open: false, text: '', log: [], requestLeft: 3 });
      const note = Vue.ref('');
      const fill = (tpl) => tpl.replace('{n}', String(S.round || 1)).replace('{c}', String(Object.keys(S.clues || {}).length));
      const tune = () => window.Store.send('skill', { kind: 'radio_tune' });
      const request = () => {
        if ((rd.value.requestLeft || 0) <= 0 && !S.demo) {
          window.Store.toast('本局点播次数用完了', 'warn');
          return;
        }
        window.Store.send('skill', { kind: 'radio_request', note: note.value });
        note.value = '';
      };
      const current = Vue.computed(() => rd.value.text || fill(FALLBACK[(S.round || 1) % FALLBACK.length]));
      const log = Vue.computed(() => (rd.value.log || []).slice(-8));
      return { S, rd, note, tune, request, current, log };
    },
    template: `
    <section class="view pp-radio">
      <header class="view-hd">
        <h2>档案局内部广播台</h2>
        <p class="sub">电台刻度 · 封控夜班</p>
        <button class="btn ghost sm" type="button" @click="S.view='chat'">返回圆桌</button>
      </header>
      <div class="pp-radio-panel">
        <p class="pp-radio-now">{{ current }}</p>
        <ul class="pp-radio-log">
          <li v-for="(line, i) in log" :key="i">{{ line }}</li>
        </ul>
        <div class="pp-radio-actions">
          <button class="btn ghost" type="button" :disabled="S.busy" @click="tune">整点收听 · 0AP</button>
          <div class="kw-input">
            <input v-model="note" maxlength="40" placeholder="点播附言（可选）">
            <voice-mic v-model="note" :maxlength="40"></voice-mic>
            <button class="btn primary" type="button" :disabled="S.busy || S.ap < 1" @click="request">点播 · 1AP</button>
          </div>
        </div>
        <p class="dim">剩余点播约 {{ rd.requestLeft == null ? 3 : rd.requestLeft }} 次</p>
      </div>
    </section>`
  };

  window.VIEWS = window.VIEWS || {};
  window.VIEWS.radio = RadioView;
})();
