/* 语音游玩层：浏览器 STT/TTS。音频不出域、不上传。
 * 无 SpeechRecognition / speechSynthesis / document 时全部空操作（对齐 sfx.js）。
 * RTC 预留：isListening / onState / pause / resume —— 二期对讲可据此静音上行或暂停识别。 */
(function () {
  const IN_KEY = 'kanshan_voice_in';
  const OUT_KEY = 'kanshan_voice_out';
  const AUTO_KEY = 'kanshan_voice_auto';

  const VOICE_BY_CHAR = {
    char_01: { rate: 0.96, pitch: 0.95 },
    char_02: { rate: 0.90, pitch: 1.04 },
    char_03: { rate: 1.18, pitch: 1.16 },
    char_04: { rate: 1.00, pitch: 1.00 },
    char_05: { rate: 0.82, pitch: 0.68 },
    char_06: { rate: 0.88, pitch: 0.84 },
    char_07: { rate: 1.02, pitch: 1.08 },
    char_08: { rate: 1.08, pitch: 1.18 },
    dm: { rate: 1.04, pitch: 0.88 },
    sys: { rate: 1.00, pitch: 0.86, volume: 0.78 }
  };

  function RecCtor() {
    if (typeof window === 'undefined') return null;
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }
  function canSTT() { return !!RecCtor(); }
  function canTTS() {
    return typeof window !== 'undefined' && !!window.speechSynthesis && typeof window.SpeechSynthesisUtterance === 'function';
  }
  function isSecure() {
    if (typeof window === 'undefined') return false;
    if (window.isSecureContext) return true;
    try {
      const h = (window.location && window.location.hostname) || '';
      return h === 'localhost' || h === '127.0.0.1';
    } catch (e) { return false; }
  }
  function loadFlag(key, fallback) {
    try {
      const v = localStorage.getItem(key);
      if (v === '1') return true;
      if (v === '0') return false;
    } catch (e) { /* ignore */ }
    return fallback;
  }
  function saveFlag(key, val) {
    try { localStorage.setItem(key, val ? '1' : '0'); } catch (e) { /* ignore */ }
  }
  function toast(text, kind) {
    try {
      if (window.Store && window.Store.toast) window.Store.toast(text, kind || 'warn');
    } catch (e) { /* ignore */ }
  }
  function sfxMuted() {
    try { return !!(window.SFX && window.SFX.isMuted && window.SFX.isMuted()); } catch (e) { return false; }
  }
  function voPlaying() {
    try { return !!(window.SFX && window.SFX.status && window.SFX.status().voPlaying); } catch (e) { return false; }
  }
  function setDuck(on) {
    try {
      if (window.SFX && window.SFX.duck) window.SFX.duck(!!on || voPlaying());
    } catch (e) { /* ignore */ }
  }

  const flags = (typeof Vue !== 'undefined' && Vue.reactive)
    ? Vue.reactive({
      input: loadFlag(IN_KEY, true),
      output: loadFlag(OUT_KEY, true),
      auto: loadFlag(AUTO_KEY, false)
    })
    : {
      input: loadFlag(IN_KEY, true),
      output: loadFlag(OUT_KEY, true),
      auto: loadFlag(AUTO_KEY, false)
    };

  let rec = null;
  let listenWanted = false;
  let paused = false;
  let listening = false;
  let granted = false;
  let token = 0;
  let cbs = {};
  let zhVoice = null;
  let voicesHooked = false;
  const speakQ = [];
  let speaking = false;
  let utter = null;
  let voWaitTimer = 0;
  let voWaitN = 0;
  const stateFns = [];

  function prefs() {
    return { input: !!flags.input, output: !!flags.output, auto: !!flags.auto };
  }
  function supported() {
    return { stt: canSTT(), tts: canTTS(), secure: isSecure() };
  }
  function status() {
    return {
      listening: !!listening,
      paused: !!paused,
      wanted: !!listenWanted,
      speaking: !!speaking,
      granted: !!granted,
      prefs: prefs(),
      supported: supported()
    };
  }
  function emitState() {
    const snap = status();
    for (let i = 0; i < stateFns.length; i++) {
      try { stateFns[i](snap); } catch (e) { /* ignore */ }
    }
  }
  function onState(fn) {
    if (typeof fn !== 'function') return function () {};
    stateFns.push(fn);
    try { fn(status()); } catch (e) { /* ignore */ }
    return function () {
      const i = stateFns.indexOf(fn);
      if (i >= 0) stateFns.splice(i, 1);
    };
  }

  function setInputOn(v) {
    flags.input = !!v;
    saveFlag(IN_KEY, flags.input);
    if (!flags.input) stop();
    emitState();
  }
  function setOutputOn(v) {
    flags.output = !!v;
    saveFlag(OUT_KEY, flags.output);
    if (!flags.output) cancelSpeak();
    emitState();
  }
  function setAutoSend(v) {
    flags.auto = !!v;
    saveFlag(AUTO_KEY, flags.auto);
    emitState();
  }

  function errText(code) {
    if (code === 'not-allowed' || code === 'service-not-allowed') return '麦克风被拒绝，请在浏览器地址栏允许后重试';
    if (code === 'no-speech') return '没听清，再说一次或改打字';
    if (code === 'audio-capture') return '找不到麦克风';
    if (code === 'network') return '识别服务暂时不可用，请打字';
    if (code === 'insecure') return '语音识别需要 HTTPS（或本机 127.0.0.1）';
    return '当前浏览器不支持语音识别，请用 Chrome/Edge 或继续打字';
  }

  function requestMic() {
    if (!canSTT()) {
      toast(errText('no-support'), 'warn');
      return Promise.resolve(false);
    }
    if (!isSecure()) {
      toast(errText('insecure'), 'warn');
      return Promise.resolve(false);
    }
    if (typeof navigator === 'undefined' || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      granted = true;
      return Promise.resolve(true);
    }
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      try {
        (stream.getTracks() || []).forEach(function (t) { t.stop(); });
      } catch (e) { /* 立即释放：音频不落盘、不上传 */ }
      granted = true;
      return true;
    }).catch(function () {
      toast(errText('not-allowed'), 'warn');
      return false;
    });
  }

  function haltRec() {
    listening = false;
    if (!rec) { emitState(); return; }
    try { rec.onresult = null; rec.onerror = null; rec.onend = null; } catch (e) { /* ignore */ }
    try { rec.abort(); } catch (e2) {
      try { rec.stop(); } catch (e3) { /* ignore */ }
    }
    rec = null;
    emitState();
  }

  function armRec() {
    if (paused || !listenWanted) return false;
    const Ctor = RecCtor();
    if (!Ctor) {
      toast(errText('no-support'), 'warn');
      if (cbs.onError) try { cbs.onError('no-support'); } catch (e) { /* ignore */ }
      return false;
    }
    if (!isSecure()) {
      toast(errText('insecure'), 'warn');
      if (cbs.onError) try { cbs.onError('insecure'); } catch (e2) { /* ignore */ }
      return false;
    }
    haltRec();
    const my = ++token;
    let r;
    try { r = new Ctor(); } catch (e3) {
      toast(errText('no-support'), 'warn');
      return false;
    }
    rec = r;
    r.lang = 'zh-CN';
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.onresult = function (ev) {
      if (my !== token) return;
      let interim = '', finalText = '';
      const res = ev && ev.results;
      if (!res) return;
      for (let i = ev.resultIndex || 0; i < res.length; i++) {
        const row = res[i];
        const piece = row && row[0] && row[0].transcript ? String(row[0].transcript) : '';
        if (row.isFinal) finalText += piece;
        else interim += piece;
      }
      if (interim && cbs.onInterim) try { cbs.onInterim(interim); } catch (e4) { /* ignore */ }
      if (finalText) {
        listenWanted = false;
        if (cbs.onFinal) try { cbs.onFinal(finalText); } catch (e5) { /* ignore */ }
        haltRec();
      }
    };
    r.onerror = function (ev) {
      if (my !== token) return;
      const code = (ev && ev.error) || 'error';
      if (code !== 'aborted' && code !== 'no-speech') toast(errText(code), 'warn');
      if (cbs.onError) try { cbs.onError(code); } catch (e6) { /* ignore */ }
      listenWanted = false;
      haltRec();
    };
    r.onend = function () {
      if (my !== token) return;
      listening = false;
      rec = null;
      if (listenWanted && !paused) {
        try { armRec(); } catch (e7) { listenWanted = false; emitState(); }
        return;
      }
      emitState();
      if (cbs.onEnd) try { cbs.onEnd(); } catch (e8) { /* ignore */ }
    };
    try {
      r.start();
      listening = true;
      emitState();
      if (cbs.onStart) try { cbs.onStart(); } catch (e9) { /* ignore */ }
      return true;
    } catch (e10) {
      toast(errText('no-support'), 'warn');
      listenWanted = false;
      haltRec();
      return false;
    }
  }

  function listen(opt) {
    cbs = opt || {};
    if (!canSTT()) {
      toast(errText('no-support'), 'warn');
      if (cbs.onError) try { cbs.onError('no-support'); } catch (e0) { /* ignore */ }
      return false;
    }
    if (!flags.input) {
      toast('先在设置里打开「语音输入」', 'warn');
      return false;
    }
    listenWanted = true;
    if (paused) { emitState(); return true; }
    if (granted) return armRec();
    requestMic().then(function (ok) {
      if (!ok || !listenWanted || paused) {
        if (!ok) listenWanted = false;
        emitState();
        return;
      }
      armRec();
    });
    return true;
  }

  function stop() {
    listenWanted = false;
    token += 1;
    haltRec();
    if (cbs.onEnd) try { cbs.onEnd(); } catch (e) { /* ignore */ }
  }

  function pause() {
    paused = true;
    haltRec();
  }
  function resume() {
    paused = false;
    if (listenWanted) armRec();
    else emitState();
  }

  function hookVoices() {
    if (voicesHooked || !canTTS()) return;
    voicesHooked = true;
    const pick = function () {
      try {
        const list = window.speechSynthesis.getVoices() || [];
        zhVoice = list.filter(function (v) {
          const tag = ((v && v.lang) || '') + ' ' + ((v && v.name) || '');
          return /zh-CN|zh_CN|zh-Hans|Chinese|中文|普通话/.test(tag);
        })[0] || null;
      } catch (e) { zhVoice = null; }
    };
    pick();
    try { window.speechSynthesis.addEventListener('voiceschanged', pick); } catch (e2) {
      try { window.speechSynthesis.onvoiceschanged = pick; } catch (e3) { /* ignore */ }
    }
  }

  function cannedText(text) {
    const t = String(text || '').replace(/\s+/g, '');
    if (!t) return true;
    const M = (window.Store && window.Store.M) || window.MOCK;
    if (!M) return false;
    const pool = (M.bossLines || []).concat(
      (M.fishVoiceLines || []).map(function (x) { return x && x.text; }),
      M.fishVoiceBossExtra || ''
    );
    for (let i = 0; i < pool.length; i++) {
      const n = String(pool[i] || '').replace(/\s+/g, '');
      if (n && (t === n || (n.length > 12 && t.indexOf(n.slice(0, 18)) === 0))) return true;
    }
    return false;
  }

  function voiceOf(charId, actor, heart) {
    const id = charId || (actor === 'dm' ? 'dm' : actor === 'sys' ? 'sys' : '');
    const base = VOICE_BY_CHAR[id] || VOICE_BY_CHAR.sys || { rate: 1, pitch: 1 };
    const out = { rate: base.rate || 1, pitch: base.pitch || 1, volume: base.volume == null ? 0.92 : base.volume };
    if (heart) {
      out.rate = Math.max(0.7, (out.rate || 1) * 0.88);
      out.pitch = Math.max(0.5, (out.pitch || 1) * 0.86);
      out.volume = 0.52;
    }
    return out;
  }

  function clipHeart(text) {
    const s = String(text || '').trim();
    if (s.length <= 56) return s;
    return s.slice(0, 56) + '…';
  }

  function pumpSpeak() {
    if (speaking || !speakQ.length) return;
    if (!flags.output || sfxMuted() || !canTTS()) { speakQ.length = 0; return; }
    /* 罐头 VO 播放中不丢队：等切片结束后再播 TTS（避免翻开卷宗时 sys 行被吃掉） */
    if (voPlaying() && voWaitN < 40) {
      voWaitN += 1;
      if (!voWaitTimer) {
        voWaitTimer = setTimeout(function () { voWaitTimer = 0; pumpSpeak(); }, 350);
      }
      return;
    }
    voWaitN = 0;
    const job = speakQ.shift();
    hookVoices();
    let u;
    try { u = new window.SpeechSynthesisUtterance(job.text); } catch (e) { return; }
    const spec = voiceOf(job.charId, job.actor, job.heart);
    u.lang = 'zh-CN';
    u.rate = spec.rate;
    u.pitch = spec.pitch;
    u.volume = spec.volume;
    if (zhVoice) u.voice = zhVoice;
    utter = u;
    speaking = true;
    setDuck(true);
    emitState();
    u.onend = u.onerror = function () {
      speaking = false;
      utter = null;
      setDuck(false);
      emitState();
      pumpSpeak();
    };
    try { window.speechSynthesis.speak(u); } catch (e2) {
      speaking = false;
      utter = null;
      setDuck(false);
      emitState();
    }
  }

  function speak(text, opt) {
    opt = opt || {};
    if (!flags.output || sfxMuted() || !canTTS()) return false;
    let t = String(text || '').replace(/\s+/g, ' ').trim();
    if (!t || cannedText(t)) return false;
    if (opt.heart) t = clipHeart(t);
    if (!t) return false;
    if (speakQ.length >= 4) speakQ.shift();
    speakQ.push({
      text: t,
      actor: opt.actor || '',
      charId: opt.charId || opt.char_id || '',
      heart: !!opt.heart
    });
    pumpSpeak();
    return true;
  }

  function cancelSpeak() {
    if (voWaitTimer) { clearTimeout(voWaitTimer); voWaitTimer = 0; }
    voWaitN = 0;
    speakQ.length = 0;
    speaking = false;
    utter = null;
    if (canTTS()) {
      try { window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
    }
    setDuck(false);
    emitState();
  }

  function clip(s, max) {
    s = String(s == null ? '' : s);
    if (max && s.length > max) return s.slice(0, max);
    return s;
  }

  function makeMic() {
    if (typeof Vue === 'undefined') return null;
    const { ref, computed, onBeforeUnmount, nextTick } = Vue;
    return {
      name: 'voice-mic',
      props: {
        modelValue: { type: String, default: '' },
        submit: { type: Function, default: null },
        disabled: { type: Boolean, default: false },
        maxlength: { type: Number, default: 200 }
      },
      emits: ['update:modelValue', 'final'],
      setup: function (props, ctx) {
        const live = ref(false);
        const shown = computed(function () { return !!flags.input; });
        let holdTimer = 0;
        let hold = false;
        let t0 = 0;
        let unwatch = null;
        unwatch = onState(function (st) { live.value = !!(st.wanted && !st.paused); });
        function fill(text, done) {
          const next = clip(text, props.maxlength);
          ctx.emit('update:modelValue', next);
          if (!done) return;
          ctx.emit('final', next);
          if (flags.auto && typeof props.submit === 'function') {
            nextTick(function () { try { props.submit(); } catch (e) { /* ignore */ } });
          }
        }
        function start() {
          if (props.disabled) return;
          // 某些内嵌浏览器不会派发 pointer 事件；click 兜底时避免重复启动。
          if (listening || listenWanted) return;
          listen({
            onInterim: function (t) { fill(t, false); },
            onFinal: function (t) { live.value = false; fill(t, true); },
            onError: function () { live.value = false; },
            onEnd: function () { live.value = false; },
            onStart: function () { live.value = true; }
          });
        }
        function onDown(e) {
          if (props.disabled) return;
          hold = false;
          t0 = Date.now();
          clearTimeout(holdTimer);
          holdTimer = setTimeout(function () { hold = true; start(); }, 260);
          try { if (e && e.currentTarget && e.pointerId != null) e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
        }
        function onUp() {
          clearTimeout(holdTimer);
          const dt = Date.now() - t0;
          if (hold || dt >= 260) stop();
          else if (listening || listenWanted) stop();
          else start();
        }
        onBeforeUnmount(function () {
          clearTimeout(holdTimer);
          if (unwatch) unwatch();
          if (live.value) stop();
        });
        return { live, shown, onDown, onUp, start };
      },
      template: `
        <button v-if="shown" type="button" class="voice-mic" :class="{ on: live }"
                :disabled="disabled" :aria-pressed="live ? 'true' : 'false'"
                aria-label="语音输入"
                title="点按说一段话，或按住说话。默认填入输入框，需再点发送。"
                @pointerdown.prevent="onDown" @pointerup="onUp" @pointercancel="onUp"
                @click="start">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3"/>
            <path d="M6 11a6 6 0 0 0 12 0M12 17v3M8 21h8"/>
          </svg>
        </button>`
    };
  }

  const Mic = makeMic();

  function install(app) {
    if (!app || !Mic || !app.component) return;
    try { app.component('voice-mic', Mic); } catch (e) { /* ignore */ }
  }

  if (canTTS()) hookVoices();

  window.Voice = {
    supported: supported,
    requestMic: requestMic,
    listen: listen,
    stop: stop,
    pause: pause,
    resume: resume,
    speak: speak,
    cancelSpeak: cancelSpeak,
    setOutputOn: setOutputOn,
    setInputOn: setInputOn,
    setAutoSend: setAutoSend,
    prefs: prefs,
    flags: flags,
    status: status,
    isListening: function () { return !!listening; },
    isPaused: function () { return !!paused; },
    isSpeaking: function () { return !!speaking; },
    onState: onState,
    install: install,
    Mic: Mic
  };
})();
