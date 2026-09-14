/* 音频层：43 条 /assets/audio/*.wav。Node smoke 无 Audio/document 时全部空操作。 */
(function () {
  const BASE = '/assets/audio/';
  const MUTE_KEY = 'kanshan_mute_v1';

  const BGM = {
    menu: { file: 'bgm_menu_rain.wav', vol: 0.28 },
    opening: { file: 'bgm_opening.wav', vol: 0.32 },
    roundtable: { file: 'bgm_roundtable.wav', vol: 0.26 },
    map: { file: 'bgm_map.wav', vol: 0.22 }
  };
  const ROOM = {
    loc_reception: 'bgm_room_前台.wav',
    loc_desk: 'bgm_room_看山工位.wav',
    loc_teahouse: 'bgm_room_茶水间.wav',
    loc_locker: 'bgm_room_快递柜.wav',
    loc_monitor: 'bgm_room_监控室.wav',
    loc_server: 'bgm_room_机房.wav',
    loc_archive: 'bgm_room_档案室.wav',
    loc_ac: 'bgm_room_空调机房.wav',
    loc_roof: 'bgm_room_天台.wav'
  };
  const VO = {
    case: 'vo_dm_case.wav',
    act: 'vo_dm_act.wav',
    boss_1: 'vo_boss_1.wav',
    boss_2: 'vo_boss_2.wav',
    boss_3: 'vo_boss_3.wav',
    boss_4: 'vo_boss_4.wav',
    fish_1: 'vo_fish_1.wav',
    fish_2: 'vo_fish_2.wav',
    fish_3: 'vo_fish_3.wav',
    fish_4: 'vo_fish_4.wav',
    fish_5: 'vo_fish_5.wav'
  };
  const SHOT = {
    ding: 'sfx_ding.wav',
    click: 'sfx_ui_click.wav',
    page: 'sfx_page_flip.wav',
    archive: 'sfx_page_flip.wav',
    seat: 'sfx_seat.wav',
    hit: 'sfx_card_hit.wav',
    miss: 'sfx_card_miss.wav',
    camera: 'sfx_camera.wav',
    copy: 'sfx_copy.wav',
    hammer: 'sfx_hammer.wav',
    gavel: 'sfx_hammer.wav',
    countdown: 'sfx_countdown.wav',
    elevator: 'sfx_elevator.wav',
    glitch: 'sfx_glitch.wav',
    auction: 'sfx_auction.wav',
    heat: 'sfx_heat.wav',
    buzz: 'sfx_buzz.wav',
    green: 'sfx_green.wav',
    heal: 'sfx_heal.wav',
    pass: 'sfx_heal.wav',
    fail: 'sfx_buzz.wav',
    tick: 'sfx_tick.wav',
    achievement: 'sfx_achievement.wav',
    cut: 'sfx_ding.wav'
  };

  function canAudio() { return typeof Audio !== 'undefined'; }
  function canDoc() { return typeof document !== 'undefined' && typeof document.addEventListener === 'function'; }
  function url(file) { return encodeURI(BASE + file); }

  let muted = false;
  try { muted = localStorage.getItem(MUTE_KEY) === '1'; } catch (e) { /* ignore */ }

  let unlocked = false;
  let pendingBgm = 'menu';
  let bgmEl = null, bgmKey = null, duck = 1;
  let ambEl = null, ambKey = null;
  let voEl = null;
  let heldEl = null;
  let lastCut = null, lastCase = false, lastElev = null, lastTheater = false;

  function tryPlay(el) {
    if (!el || muted) return Promise.resolve();
    const p = el.play();
    if (p && p.catch) p.catch(function () { /* 未解锁 / 自动播放拦截 */ });
    return p || Promise.resolve();
  }

  function fadeKill(el, ms) {
    if (!el) return;
    const start = el.volume;
    const t0 = Date.now();
    function step() {
      const t = Math.min(1, (Date.now() - t0) / (ms || 400));
      try { el.volume = start * (1 - t); } catch (e) { /* ignore */ }
      if (t < 1 && typeof requestAnimationFrame === 'function') requestAnimationFrame(step);
      else { try { el.pause(); el.src = ''; } catch (e2) { /* ignore */ } }
    }
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(step);
    else { try { el.pause(); } catch (e3) { /* ignore */ } }
  }

  function make(file, loop, vol) {
    if (!canAudio() || !file) return null;
    const a = new Audio(url(file));
    a.loop = !!loop;
    a.preload = 'auto';
    a.volume = vol == null ? 0.7 : vol;
    return a;
  }

  function unlock() {
    if (unlocked) return;
    unlocked = true;
    if (pendingBgm && !muted) setBgm(pendingBgm);
  }

  function attachUnlock() {
    if (!canDoc()) return;
    const once = function () { unlock(); };
    document.addEventListener('pointerdown', once);
    document.addEventListener('keydown', once);
  }

  function setBgm(key) {
    pendingBgm = key;
    if (!unlocked || muted || !canAudio()) {
      if (muted && bgmEl) { fadeKill(bgmEl, 200); bgmEl = null; bgmKey = null; }
      return;
    }
    if (key === bgmKey && bgmEl) return;
    fadeKill(bgmEl, 450);
    bgmKey = key;
    const spec = BGM[key];
    if (!spec) { bgmEl = null; return; }
    bgmEl = make(spec.file, true, 0);
    if (!bgmEl) return;
    tryPlay(bgmEl);
    const target = spec.vol * duck;
    const t0 = Date.now();
    function fadeIn() {
      if (bgmEl && bgmKey === key) {
        const t = Math.min(1, (Date.now() - t0) / 500);
        try { bgmEl.volume = target * t; } catch (e) { /* ignore */ }
        if (t < 1 && typeof requestAnimationFrame === 'function') requestAnimationFrame(fadeIn);
      }
    }
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(fadeIn);
    else try { bgmEl.volume = target; } catch (e2) { /* ignore */ }
  }

  function setAmbient(locId) {
    if (locId === ambKey) return;
    fadeKill(ambEl, 350);
    ambKey = locId || null;
    if (!locId || muted || !unlocked || !canAudio()) { ambEl = null; ambKey = null; return; }
    const file = ROOM[locId];
    if (!file) { ambEl = null; ambKey = null; return; }
    ambEl = make(file, true, 0.20);
    tryPlay(ambEl);
  }

  function setDuck(on) {
    duck = on ? 0.42 : 1;
    if (bgmEl && bgmKey && BGM[bgmKey]) {
      try { bgmEl.volume = BGM[bgmKey].vol * duck; } catch (e) { /* ignore */ }
    }
  }

  function stopVo() {
    if (voEl) { try { voEl.pause(); voEl.src = ''; } catch (e) { /* ignore */ } voEl = null; }
    setDuck(false);
  }

  function vo(id) {
    if (muted || !canAudio() || !unlocked) return;
    const file = VO[id];
    if (!file) return;
    try { if (window.Voice && window.Voice.cancelSpeak) window.Voice.cancelSpeak(); } catch (e) { /* 罐头 VO 优先，不与 TTS 叠播 */ }
    stopVo();
    voEl = make(file, false, 0.88);
    if (!voEl) return;
    setDuck(true);
    voEl.onended = function () { voEl = null; setDuck(false); };
    tryPlay(voEl);
  }

  function stopHeld() {
    if (heldEl) { try { heldEl.pause(); heldEl.src = ''; } catch (e) { /* ignore */ } heldEl = null; }
  }

  function playHeld(kind) {
    stopHeld();
    if (muted || !canAudio()) return;
    const file = SHOT[kind];
    if (!file) return;
    heldEl = make(file, false, 0.72);
    tryPlay(heldEl);
  }

  function oneshot(kind, opt) {
    opt = opt || {};
    if (muted || !canAudio()) return;
    const file = SHOT[kind];
    if (!file) return;
    const a = make(file, false, opt.vol == null ? 0.7 : opt.vol);
    if (!a) return;
    if (opt.stopAt) {
      a.addEventListener('timeupdate', function () {
        if (a.currentTime >= opt.stopAt) {
          a.pause();
          if (opt.then) oneshot(opt.then);
        }
      });
    }
    tryPlay(a);
  }

  function play(kind) {
    if (!kind) return;
    if (kind === 'glitch') { oneshot('glitch', { stopAt: 1.6, then: 'ding' }); return; }
    if (kind === 'countdown' || kind === 'tick') { playHeld(kind); return; }
    if (kind === 'cut') { oneshot('ding'); vo('act'); return; }
    oneshot(kind);
  }

  function stopAll() {
    fadeKill(bgmEl, 200); bgmEl = null; bgmKey = null;
    fadeKill(ambEl, 200); ambEl = null;
    stopVo();
    stopHeld();
  }

  function setMuted(v) {
    muted = !!v;
    try { localStorage.setItem(MUTE_KEY, muted ? '1' : '0'); } catch (e) { /* ignore */ }
    if (muted) {
      stopAll();
      try { if (window.Voice && window.Voice.cancelSpeak) window.Voice.cancelSpeak(); } catch (e2) { /* ignore */ }
    }
    else if (unlocked && pendingBgm) setBgm(pendingBgm);
  }

  function sync(S) {
    if (!S) return;
    const theater = !!(S.antifraud && S.antifraud.active && !S.demo);
    if (theater && !lastTheater) { lastTheater = true; play('tick'); }
    if (!theater && lastTheater) { lastTheater = false; stopHeld(); }

    if (S.phase !== 'play') {
      setAmbient(null);
      setBgm(S.phase === 'video' ? 'opening' : 'menu');
      return;
    }
    if (S.elevator && S.elevator.startedAt && lastElev !== S.elevator.startedAt) {
      lastElev = S.elevator.startedAt;
      play('elevator');
    }
    if (S.showtime && S.showtime.cut) {
      const k = S.showtime.cut.act;
      if (lastCut !== k) { lastCut = k; play('cut'); }
      setBgm('menu');
      return;
    }
    if (S.showtime && S.showtime.step === 'case_file') {
      setBgm('menu');
      if (!lastCase) { lastCase = true; play('page'); vo('case'); }
      return;
    }
    const v = S.view;
    if (v === 'map' || v === 'hotfeed' || v === 'clinic' || v === 'report' || v === 'bag' || v === 'mini') {
      if (v !== 'map') setAmbient(null);
      setBgm('map');
    } else {
      setAmbient(null);
      setBgm('roundtable');
    }
  }

  attachUnlock();
  window.SFX = {
    play: play,
    vo: vo,
    stopVo: stopVo,
    stopHeld: stopHeld,
    bgm: setBgm,
    ambient: setAmbient,
    sync: sync,
    setMuted: setMuted,
    isMuted: function () { return muted; },
    duck: setDuck,
    unlock: unlock,
    status: function () {
      return {
        muted: muted, unlocked: unlocked, bgm: bgmKey, ambient: ambKey,
        pending: pendingBgm,
        bgmPlaying: !!(bgmEl && !bgmEl.paused),
        voPlaying: !!(voEl && !voEl.paused)
      };
    }
  };
})();
