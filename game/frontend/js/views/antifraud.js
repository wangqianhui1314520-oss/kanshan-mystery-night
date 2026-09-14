/* ============================================================
 * views/antifraud.js —— 反诈小剧场（P2：官方辟谣成功触发 · 30 秒识骗演出）
 * 三幕剧本对齐 D 内容组 segments_p2.md §三；每幕尾 1 道识骗判断题，
 * 全对 → 反诈学分 +1（成就：反诈先锋）。全屏演出，可跳过（跳过=放弃答题）。
 * ============================================================ */
(function () {
  const { ref, computed, onMounted, nextTick } = Vue;
  const M = window.Store.M;

  const AntifraudTheater = {
    setup() {
      const S = window.Store.state, M = window.Store.M;
      const act = ref(0);           // 当前幕
      const lineN = ref(0);         // 已显示行数
      const quizDone = ref(false);
      const picked = ref(-1);
      const bodyEl = ref(null);
      const cur = computed(() => M.antifraudScript[act.value] || null);
      const lines = computed(() => cur.value ? cur.value.lines.slice(0, lineN.value) : []);
      const allLines = computed(() => cur.value && lineN.value >= cur.value.lines.length);
      const finished = computed(() => act.value >= M.antifraudScript.length);

      const nextLine = () => {
        if (!cur.value) return;
        if (lineN.value < cur.value.lines.length) { lineN.value += 1; scrollDown(); }
      };
      const scrollDown = async () => { await nextTick(); if (bodyEl.value) bodyEl.value.scrollTop = bodyEl.value.scrollHeight; };
      const nextAct = () => {
        if (!quizDone.value) return;  // 答完题才能进下一幕
        quizDone.value = false; picked.value = -1;
        act.value += 1; lineN.value = 0;
      };
      const pick = (i) => {
        if (picked.value >= 0) return;
        picked.value = i;
        quizDone.value = true;
        window.Store.send('skill', { kind: 'antifraud_answer', right: i === cur.value.quiz.ans });
        setTimeout(scrollDown, 50);
      };
      const close = () => {
        if (window.SFX && window.SFX.stopHeld) window.SFX.stopHeld();
        S.antifraud.active = false;
      };
      const auto = setInterval(() => {
        if (!S.antifraud.active || finished.value) { clearInterval(auto); return; }
        nextLine();
      }, 1500);
      /* 30 秒总倒计时（segments_p2 §三：30 秒 AI 演出；超时=演出结束，未答题视作跳过） */
      const sec = ref(30);
      const secTimer = setInterval(() => {
        if (!S.antifraud.active) { clearInterval(secTimer); return; }
        sec.value = Math.max(0, sec.value - 1);
        if (sec.value === 0) { clearInterval(secTimer); S.antifraud.active = false; }
      }, 1000);
      onMounted(() => { setTimeout(nextLine, 500); });
      const rewatch = computed(() => act.value);
      return { S, M, act, lineN, lines, cur, allLines, finished, quizDone, picked, bodyEl, nextLine, nextAct, pick, close, rewatch, auto, sec };
    },
    beforeUnmount() {
      clearInterval(this.auto); clearInterval(this.secTimer);
      if (window.SFX && window.SFX.stopHeld) window.SFX.stopHeld();
    },
    template: `
    <transition name="fade">
    <div class="antifraud-theater" v-if="S.antifraud.active && !finished && !S.demo">
      <div class="at-curtain"></div>
      <div class="at-stage">
        <header class="at-hd">
          <span class="chip gold">反诈小剧场 · 30 秒识骗演出（公益向，全角色虚构）</span>
          <span class="chip mono">第 {{ act + 1 }}/{{ M.antifraudScript.length }} 幕</span>
          <span class="at-timer mono" :class="{urgent: sec <= 10}">⏱ {{ sec }}s</span>
          <button class="btn ghost sm" @click="close">跳过（放弃反诈学分）</button>
        </header>
        <div class="at-secline"><i :style="{ width: (sec / 30 * 100) + '%' }"></i></div>
        <div class="at-body" ref="bodyEl">
          <h3>{{ cur.title }}</h3>
          <transition-group name="atline">
            <p v-for="(l, i) in lines" :key="act + '-' + i" class="at-line" :class="{dm: l.includes('叮——'), crowd: l.includes('弹幕')}">{{ l }}</p>
          </transition-group>
          <div v-if="allLines && !quizDone" class="at-quiz">
            <p class="at-quiz-title">识骗判断（答对反诈学分 +1）：</p>
            <b>{{ cur.quiz.q }}</b>
            <div class="at-quiz-opts">
              <button v-for="(o, i) in cur.quiz.opts" :key="i" class="btn ghost" :class="{on: picked===i, right: picked>=0 && i===cur.quiz.ans, wrong: picked===i && i!==cur.quiz.ans}" @click="pick(i)">{{ 'ABC'[i] }}. {{ o }}</button>
            </div>
          </div>
          <p v-if="picked >= 0" class="at-verdict" :class="picked === cur.quiz.ans ? 'good' : 'warn'">
            {{ picked === cur.quiz.ans ? '✅ 拆解正确——话术 +1 分不亏。' : '❌ 慌，就是话术的一部分（记住了）。' }}
          </p>
        </div>
        <footer class="at-ft">
          <button v-if="allLines && quizDone && act < M.antifraudScript.length - 1" class="btn primary big" @click="nextAct">下一幕 →</button>
          <button v-else-if="allLines && quizDone" class="btn primary big" @click="close">谢幕（真相不转发，谣言必被辟）</button>
          <button v-else-if="!allLines" class="btn ghost" @click="nextLine">继续 ▸</button>
        </footer>
      </div>
    </div>
    </transition>`
  };

  window.VIEWS['antifraud-theater'] = AntifraudTheater;
})();
