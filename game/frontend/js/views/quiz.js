/* ============================================================
 * views/quiz.js —— 幕间快问快答（只复述已公开信息，答错不扣进度）
 * ============================================================ */
(function () {
  const FALLBACK = [
    { q: '横幅上写的八个字是？', options: ['不出真相不出此门', '不开门不出门', '真不出门了'] },
    { q: '案发夜 DM 的口头禅是？', options: ['叮——', '汪——', '喵——'] },
    { q: '监控被删除的时段是？', options: ['21:07-21:15', '22:30-22:40', '全删了'] },
    { q: '删除监控用的账号权限是？', options: ['局长级 KS-000', '实习生号', '访客号'] },
    { q: '看山的鱼干口味是？', options: ['彩虹鳟鱼味', '金枪鱼味', '香辣味'] },
    { q: '热搜热度曲线从几点开始"纪律严明"？', options: ['21:10', '22:00', '23:00'] },
    { q: '路人甲的口供把什么说成了什么？', options: ['代班→值班', '值班→代班', '上班→下班'] },
    { q: '水军矩阵有多少个设备指纹同源的号？', options: ['47', '14', '404'] },
    { q: '看山Bot 删日志后留下了什么？', options: ['哈希值 A3F9-77C2', '道歉信', '什么都没留'] },
    { q: '盐值君在门禁系统留言板上写了？', options: ['建议关注', '强烈谴责', '我不管了'] },
    { q: '流量酱真正在后台待了多久？', options: ['15 分钟', '0 分钟', '3 小时'] },
    { q: '笔上仙的剧中剧叫？', options: ['学科修仙', '修仙学科', '学科修罗场'] },
    { q: '沉底君被折叠的答案序号是？', options: ['被折叠的第 7 章', '第 1 章', '第 100 章'] },
    { q: 'V587 的老号曾用什么身份活跃？', options: ['侦探爱好者联盟', '钓鱼佬联盟', '吃瓜联盟'] },
    { q: '集齐几个破绽可以指认 DM？', options: ['5', '3', '2'] },
    { q: '系统唤醒词是？', options: ['看山，关门', '看山，开门', '芝麻关门'] },
    { q: '心晴自习室的正确用法是？', options: ['抽知识卡开导心病', '睡午觉', '避难'] },
    { q: '辟谣需要消耗？', options: ['2AP+对应知识卡', '0AP', '喊得够大声'] },
    { q: '二十年前的大力丸在哪里被搜出？', options: ['空调机房', '茶水间', '天台'] },
    { q: '终极结局的名字是？', options: ['看山还是山', '看山不是山', '看山去哪了'] }
  ];

  const QuizView = {
    setup() {
      const S = window.Store.state;
      const qz = Vue.computed(() => S.quiz || { open: false, q: '', options: [], score: 0, asked: 0, done: false, last: null, seen: [] });
      const localQ = Vue.ref('');
      const localOpts = Vue.ref([]);
      const draw = () => {
        if (window.Store && window.Store.send) {
          window.Store.send('skill', { kind: 'quiz_draw' });
          return;
        }
        const seen = (S.quiz && S.quiz.seen) || [];
        const left = FALLBACK.map((_, i) => i).filter(i => seen.indexOf(i) < 0);
        const idx = left.length ? left[Math.floor(Math.random() * left.length)] : 0;
        localQ.value = FALLBACK[idx].q;
        localOpts.value = FALLBACK[idx].options.slice();
      };
      const pick = (i) => window.Store.send('skill', { kind: 'quiz_answer', choice: i });
      const close = () => { S.view = 'chat'; };
      const q = Vue.computed(() => qz.value.q || localQ.value);
      const options = Vue.computed(() => (qz.value.options && qz.value.options.length) ? qz.value.options : localOpts.value);
      return { S, qz, q, options, draw, pick, close };
    },
    template: `
    <section class="view pp-quiz">
      <header class="view-hd">
        <h2>幕间快问快答</h2>
        <p class="sub">只复述已公开信息，答错不扣进度</p>
        <button class="btn ghost sm" type="button" @click="close">返回圆桌</button>
      </header>
      <div class="pp-quiz-panel">
        <div class="pp-quiz-meta">已问 {{ qz.asked || 0 }}/10 · 得分 {{ qz.score || 0 }}</div>
        <p v-if="qz.done" class="pp-quiz-done">十题已问完。分数已记入本局报告。</p>
        <template v-else-if="q">
          <h3 class="pp-quiz-q">{{ q }}</h3>
          <div class="pp-quiz-opts">
            <button v-for="(o, i) in options" :key="i" class="btn ghost" type="button"
                    :disabled="S.busy" @click="pick(i)">{{ 'ABC'[i] }}. {{ o }}</button>
          </div>
        </template>
        <button v-else class="btn primary big" type="button" :disabled="S.busy || qz.done" @click="draw">下一题</button>
        <p v-if="qz.last" class="pp-quiz-toast" :class="qz.last.ok ? 'ok' : 'bad'">
          {{ qz.last.ok ? '答对。赞数 +2' : '答错。弹幕已经就位，不扣进度。' }}
        </p>
      </div>
    </section>`
  };

  window.VIEWS = window.VIEWS || {};
  window.VIEWS.quiz = QuizView;
})();
