/* 房间对讲：party mesh WebRTC（最多 4 路对端）。
 * 信令走独立 /ws/{session_id}/voice，不进游戏动作。
 * 无 RTCPeerConnection / WebSocket / document 时全部空操作（对齐 sfx.js / voice.js）。
 * STT 互斥：Voice 在 wanted/listening 时静音 RTC 上行；对讲接通时 Voice.pause()。 */
(function () {
  const MAX_PEERS = 4;
  const PING_MS = 20000;
  const SPEAK_MS = 90;
  const SPEAK_ON = 0.048;
  const SPEAK_OFF = 0.022;
  const ICE_FAIL_MS = 12000;
  const DEFAULT_ICE = [
    { urls: ['stun:stun.l.google.com:19302', 'stun:stun.cloudflare.com:3478'] }
  ];

  function canDoc() {
    return typeof document !== 'undefined' && typeof document.createElement === 'function';
  }
  function canRtc() {
    return typeof RTCPeerConnection === 'function'
      && typeof WebSocket === 'function'
      && typeof window !== 'undefined';
  }
  function isSecure() {
    if (typeof window === 'undefined') return false;
    if (window.isSecureContext) return true;
    try {
      const h = (window.location && window.location.hostname) || '';
      return h === 'localhost' || h === '127.0.0.1';
    } catch (e) { return false; }
  }
  function toast(text, kind) {
    try {
      if (window.Store && window.Store.toast) window.Store.toast(text, kind || 'warn');
    } catch (e) { /* ignore */ }
  }
  function wsBase() {
    try {
      const loc = window.location;
      const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      return proto + '//' + loc.host;
    } catch (e) { return ''; }
  }

  const flags = (typeof Vue !== 'undefined' && Vue.reactive)
    ? Vue.reactive({
      live: false, connecting: false, listenOnly: false,
      micOn: true, speakerOn: true, you: '', role: '',
      turnConfigured: false, peerCount: 0, peers: [], speakingIds: []
    })
    : {
      live: false, connecting: false, listenOnly: false,
      micOn: true, speakerOn: true, you: '', role: '',
      turnConfigured: false, peerCount: 0, peers: [], speakingIds: []
    };

  let wanted = false;
  let connecting = false;
  let live = false;
  let listenOnly = false;
  let role = '';
  let me = '';
  let sessionId = '';
  let userMuted = false;
  let speakerOn = true;
  let turnConfigured = false;
  let iceServers = DEFAULT_ICE;
  let failToasted = false;
  let wePausedVoice = false;
  let joinGen = 0;
  let ws = null;
  let pingTimer = 0;
  let speakTimer = 0;
  let retryTimer = 0;
  let retryN = 0;
  let intentionalClose = false;
  let localStream = null;
  let audioCtx = null;
  let voiceUnsub = null;
  let unloadHooked = false;
  const pcs = Object.create(null);
  const stateFns = [];
  const analysers = Object.create(null);

  function supported() {
    return { rtc: canRtc(), secure: isSecure(), mesh: canRtc() && isSecure() };
  }
  function status() {
    return {
      live: !!live,
      connecting: !!connecting,
      wanted: !!wanted,
      listenOnly: !!listenOnly,
      micOn: !userMuted && !listenOnly,
      speakerOn: !!speakerOn,
      you: me,
      role: role,
      sessionId: sessionId,
      turnConfigured: !!turnConfigured,
      peerCount: Object.keys(pcs).length,
      peers: flags.peers.slice(),
      speakingIds: flags.speakingIds.slice(),
      supported: supported()
    };
  }
  function emitState() {
    flags.live = !!live;
    flags.connecting = !!connecting;
    flags.listenOnly = !!listenOnly;
    flags.micOn = !userMuted && !listenOnly;
    flags.speakerOn = !!speakerOn;
    flags.you = me;
    flags.role = role;
    flags.turnConfigured = !!turnConfigured;
    flags.peerCount = Object.keys(pcs).length;
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

  function peerName(pid) {
    const id = String(pid || '');
    if (!id) return '';
    if (id === me) return '我';
    try {
      const S = window.Store && window.Store.state;
      const M = (window.Store && window.Store.M) || window.MOCK;
      const seats = (S && S.partySeats) || [];
      for (let i = 0; i < seats.length; i++) {
        const s = seats[i];
        if (!s) continue;
        if ((s.player_id || s.id) === id) {
          const ch = M && M.chars && M.chars.find(function (c) { return c.id === s.char_id; });
          return s.player_name || s.name || (ch && ch.name) || id;
        }
      }
    } catch (e) { /* ignore */ }
    if (id.indexOf('spectator:') === 0) return '观战·' + id.slice(11, 19);
    return id;
  }

  function syncPeerFlags() {
    const list = [];
    const talking = [];
    Object.keys(pcs).forEach(function (pid) {
      const slot = pcs[pid];
      const speaking = !!(slot && slot.speaking && !slot.muted);
      list.push({
        player_id: pid,
        name: peerName(pid),
        listen_only: !!(slot && slot.listen_only),
        muted: !!(slot && slot.muted),
        speaking: speaking,
        conn: (slot && slot.conn) || 'new'
      });
      if (speaking) talking.push(pid);
    });
    if (live && !listenOnly && !userMuted && localSpeaking()) talking.unshift(me);
    flags.peers = list;
    flags.speakingIds = talking;
    flags.peerCount = list.length;
    duckSfx(talking.some(function (id) { return id && id !== me; }));
    emitState();
  }

  function duckSfx(on) {
    try {
      if (window.SFX && window.SFX.duck) window.SFX.duck(!!on);
    } catch (e) { /* ignore */ }
  }

  function voiceBusy() {
    try {
      const V = window.Voice;
      if (!V || !V.status) return false;
      const st = V.status();
      return !!(st.wanted || st.listening);
    } catch (e) { return false; }
  }

  function applyUplink() {
    if (!localStream || listenOnly) return;
    const send = live && !userMuted && !voiceBusy();
    try {
      (localStream.getAudioTracks() || []).forEach(function (t) { t.enabled = send; });
    } catch (e) { /* ignore */ }
  }

  function applyMutex() {
    applyUplink();
    const V = window.Voice;
    if (!V) return;
    if (!live && !wanted) return;
    const busy = voiceBusy();
    if (busy) {
      if (V.isPaused && V.isPaused() && V.resume) {
        wePausedVoice = false;
        try { V.resume(); } catch (e) { /* ignore */ }
      }
    } else if (V.isPaused && !V.isPaused() && V.pause) {
      wePausedVoice = true;
      try { V.pause(); } catch (e2) { /* ignore */ }
    }
  }

  function hookVoice() {
    if (voiceUnsub || !window.Voice || !window.Voice.onState) return;
    voiceUnsub = window.Voice.onState(function () { applyMutex(); });
  }
  function unhookVoice() {
    if (voiceUnsub) {
      try { voiceUnsub(); } catch (e) { /* ignore */ }
      voiceUnsub = null;
    }
  }

  function pauseVoiceForTalk() {
    const V = window.Voice;
    if (!V || !V.pause) return;
    if (voiceBusy()) return;
    if (V.isPaused && V.isPaused()) return;
    wePausedVoice = true;
    try { V.pause(); } catch (e) { /* ignore */ }
  }
  function resumeVoiceAfterTalk() {
    const V = window.Voice;
    if (wePausedVoice && V && V.resume) {
      try { V.resume(); } catch (e) { /* ignore */ }
    }
    wePausedVoice = false;
  }

  function unlockAudio() {
    if (!canRtc()) return;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!audioCtx) audioCtx = new AC();
      if (audioCtx.state === 'suspended' && audioCtx.resume) audioCtx.resume();
    } catch (e) { /* ignore */ }
  }

  function audioHost() {
    if (!canDoc() || !document.body) return null;
    let el = document.getElementById('voice-rtc-audio');
    if (!el) {
      el = document.createElement('div');
      el.id = 'voice-rtc-audio';
      el.setAttribute('hidden', '');
      el.setAttribute('aria-hidden', 'true');
      el.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;clip:rect(0,0,0,0)';
      document.body.appendChild(el);
    }
    return el;
  }

  function attachAnalyser(key, stream) {
    dropAnalyser(key);
    if (!stream || !audioCtx) return;
    try {
      const src = audioCtx.createMediaStreamSource(stream);
      const an = audioCtx.createAnalyser();
      an.fftSize = 512;
      an.smoothingTimeConstant = 0.4;
      src.connect(an);
      analysers[key] = { an: an, buf: new Uint8Array(an.frequencyBinCount), speaking: false };
    } catch (e) { /* ignore */ }
  }
  function dropAnalyser(key) {
    if (analysers[key]) delete analysers[key];
  }
  function analyserRms(row) {
    if (!row || !row.an) return 0;
    try {
      row.an.getByteTimeDomainData(row.buf);
      let sum = 0;
      for (let i = 0; i < row.buf.length; i++) {
        const v = (row.buf[i] - 128) / 128;
        sum += v * v;
      }
      return Math.sqrt(sum / row.buf.length);
    } catch (e) { return 0; }
  }
  function localSpeaking() {
    const row = analysers.local;
    return !!(row && row.speaking);
  }
  function tickSpeak() {
    let changed = false;
    Object.keys(analysers).forEach(function (key) {
      const row = analysers[key];
      if (key !== 'local' && pcs[key] && pcs[key].muted) {
        if (row.speaking || pcs[key].speaking) {
          row.speaking = false;
          pcs[key].speaking = false;
          changed = true;
        }
        return;
      }
      const rms = analyserRms(row);
      const next = row.speaking ? rms > SPEAK_OFF : rms > SPEAK_ON;
      if (next !== row.speaking) { row.speaking = next; changed = true; }
      if (key !== 'local' && pcs[key] && pcs[key].speaking !== next) {
        pcs[key].speaking = next;
        changed = true;
      }
    });
    if (changed) syncPeerFlags();
  }
  function startSpeakLoop() {
    if (speakTimer) return;
    speakTimer = setInterval(tickSpeak, SPEAK_MS);
  }
  function stopSpeakLoop() {
    if (speakTimer) { clearInterval(speakTimer); speakTimer = 0; }
  }

  function descFromPayload(payload, fallbackType) {
    if (!payload) return null;
    if (payload.sdp && typeof payload.sdp === 'object' && payload.sdp.sdp) return payload.sdp;
    const sdp = typeof payload.sdp === 'string' ? payload.sdp : '';
    const typ = payload.type || fallbackType;
    if (!sdp || !typ) return null;
    return { type: typ, sdp: sdp };
  }

  function sendRaw(text) {
    if (!ws || ws.readyState !== 1) return false;
    try { ws.send(text); return true; } catch (e) { return false; }
  }
  function sendSignal(type, to, payload) {
    if (!sessionId || !me) return false;
    const msg = { type: type, session_id: sessionId, from: me, payload: payload || {} };
    if (to) msg.to = to;
    try { return sendRaw(JSON.stringify(msg)); } catch (e) { return false; }
  }

  function applySpeaker() {
    Object.keys(pcs).forEach(function (pid) {
      const el = pcs[pid] && pcs[pid].audioEl;
      if (el) el.muted = !speakerOn;
    });
  }

  function dropPeer(pid) {
    const slot = pcs[pid];
    if (!slot) return;
    try {
      if (slot.pc) {
        slot.pc.onicecandidate = null;
        slot.pc.ontrack = null;
        slot.pc.onnegotiationneeded = null;
        slot.pc.oniceconnectionstatechange = null;
        slot.pc.close();
      }
    } catch (e) { /* ignore */ }
    try {
      if (slot.audioEl) {
        slot.audioEl.srcObject = null;
        if (slot.audioEl.parentNode) slot.audioEl.parentNode.removeChild(slot.audioEl);
      }
    } catch (e2) { /* ignore */ }
    if (slot.failTimer) clearTimeout(slot.failTimer);
    dropAnalyser(pid);
    delete pcs[pid];
  }
  function teardownPeers() {
    Object.keys(pcs).forEach(dropPeer);
  }

  function toastTurnOnce() {
    if (failToasted || turnConfigured) return;
    failToasted = true;
    toast('对讲打不通，请同网或配置 TURN', 'warn');
  }

  function markConn(slot, pid, state) {
    slot.conn = state;
    if (state === 'failed') toastTurnOnce();
    syncPeerFlags();
  }

  function ensurePeer(pid, meta) {
    if (!pid || pid === me || !canRtc()) return null;
    if (pcs[pid]) {
      if (meta && meta.listen_only != null) pcs[pid].listen_only = !!meta.listen_only;
      return pcs[pid];
    }
    if (Object.keys(pcs).length >= MAX_PEERS) {
      toast('对讲路数已满（最多 4 路）', 'warn');
      return null;
    }
    let pc;
    try {
      pc = new RTCPeerConnection({ iceServers: iceServers });
    } catch (e) {
      toast('当前浏览器无法建立对讲', 'warn');
      return null;
    }
    const slot = {
      pc: pc,
      polite: String(me) < String(pid),
      listen_only: !!(meta && meta.listen_only),
      muted: false,
      speaking: false,
      makingOffer: false,
      ignoreOffer: false,
      settingRemote: false,
      pendingIce: [],
      audioEl: null,
      conn: 'new',
      failTimer: 0
    };
    pcs[pid] = slot;

    pc.onicecandidate = function (ev) {
      const c = ev && ev.candidate;
      sendSignal('ice', pid, c ? {
        candidate: c.candidate,
        sdpMid: c.sdpMid,
        sdpMLineIndex: c.sdpMLineIndex,
        usernameFragment: c.usernameFragment
      } : { candidate: '' });
    };
    pc.ontrack = function (ev) {
      const stream = (ev.streams && ev.streams[0]) || new MediaStream([ev.track]);
      attachRemote(pid, slot, stream);
    };
    pc.onnegotiationneeded = function () {
      if (listenOnly) return;
      makeOffer(pid, slot);
    };
    pc.oniceconnectionstatechange = function () {
      const st = pc.iceConnectionState;
      markConn(slot, pid, st);
      if (st === 'connected' || st === 'completed') {
        if (slot.failTimer) { clearTimeout(slot.failTimer); slot.failTimer = 0; }
      }
      if (st === 'failed') {
        try { pc.restartIce(); } catch (e4) { /* ignore */ }
        toastTurnOnce();
      }
    };
    slot.failTimer = setTimeout(function () {
      if (!pcs[pid]) return;
      const st = pcs[pid].pc && pcs[pid].pc.iceConnectionState;
      if (st && st !== 'connected' && st !== 'completed') toastTurnOnce();
    }, ICE_FAIL_MS);

    if (localStream && !listenOnly) {
      try {
        (localStream.getTracks() || []).forEach(function (t) { pc.addTrack(t, localStream); });
      } catch (e2) { /* ignore */ }
    } else {
      try { pc.addTransceiver('audio', { direction: 'recvonly' }); } catch (e3) { /* ignore */ }
    }

    syncPeerFlags();
    return slot;
  }

  function attachRemote(pid, slot, stream) {
    if (!canDoc()) return;
    try {
      let el = slot.audioEl;
      if (!el) {
        el = document.createElement('audio');
        el.autoplay = true;
        el.setAttribute('playsinline', '');
        el.setAttribute('autoplay', '');
        const host = audioHost();
        if (host) host.appendChild(el);
        slot.audioEl = el;
      }
      el.srcObject = stream;
      el.muted = !speakerOn;
      const p = el.play();
      if (p && p.catch) p.catch(function () { /* 手势已在加入时解锁，失败则等下次 */ });
    } catch (e) { /* ignore */ }
    attachAnalyser(pid, stream);
    startSpeakLoop();
  }

  function flushIce(slot) {
    const pending = slot.pendingIce.splice(0);
    for (let i = 0; i < pending.length; i++) addIce(slot, pending[i]);
  }

  function addIce(slot, payload) {
    if (!slot || !slot.pc) return;
    if (!slot.pc.remoteDescription) {
      slot.pendingIce.push(payload || {});
      return;
    }
    const raw = payload || {};
    const empty = raw.candidate == null || raw.candidate === '';
    const cand = empty ? null : raw;
    slot.pc.addIceCandidate(cand).catch(function () {
      if (!slot.ignoreOffer) { /* 过期候选可忽略 */ }
    });
  }

  function makeOffer(pid, slot) {
    if (!slot || !slot.pc || listenOnly) return Promise.resolve();
    if (slot.makingOffer) return Promise.resolve();
    slot.makingOffer = true;
    return slot.pc.setLocalDescription().catch(function () {
      return slot.pc.createOffer().then(function (off) {
        return slot.pc.setLocalDescription(off);
      });
    }).then(function () {
      const d = slot.pc.localDescription;
      if (d) sendSignal('offer', pid, { type: d.type, sdp: d.sdp });
    }).catch(function () { /* glare / closed */ }).then(function () {
      slot.makingOffer = false;
    });
  }

  function onOffer(from, payload) {
    const slot = ensurePeer(from, {});
    if (!slot) return;
    const desc = descFromPayload(payload, 'offer');
    if (!desc) return;
    const pc = slot.pc;
    const collision = slot.makingOffer || slot.settingRemote || pc.signalingState !== 'stable';
    slot.ignoreOffer = !slot.polite && collision;
    if (slot.ignoreOffer) return;
    slot.settingRemote = true;
    Promise.resolve().then(function () {
      return pc.setRemoteDescription(desc);
    }).then(function () {
      slot.settingRemote = false;
      flushIce(slot);
      if (pc.signalingState !== 'have-remote-offer') return;
      return pc.setLocalDescription().catch(function () {
        return pc.createAnswer().then(function (ans) {
          return pc.setLocalDescription(ans);
        });
      }).then(function () {
        const d = pc.localDescription;
        if (d) sendSignal('answer', from, { type: d.type, sdp: d.sdp });
      });
    }).catch(function () {
      slot.settingRemote = false;
    });
  }

  function onAnswer(from, payload) {
    const slot = pcs[from];
    if (!slot) return;
    const desc = descFromPayload(payload, 'answer');
    if (!desc) return;
    slot.settingRemote = true;
    slot.pc.setRemoteDescription(desc).then(function () {
      slot.settingRemote = false;
      flushIce(slot);
    }).catch(function () { slot.settingRemote = false; });
  }

  function onIce(from, payload) {
    const slot = pcs[from] || ensurePeer(from, {});
    if (!slot) return;
    addIce(slot, payload);
  }

  function onPeers(payload) {
    payload = payload || {};
    me = payload.you || me;
    listenOnly = !!payload.listen_only;
    role = payload.role || role;
    const list = payload.peers || [];
    const seen = {};
    list.forEach(function (p) {
      const pid = p && p.player_id;
      if (!pid) return;
      seen[pid] = true;
      ensurePeer(pid, p);
    });
    Object.keys(pcs).forEach(function (pid) {
      if (!seen[pid]) dropPeer(pid);
    });
    syncPeerFlags();
  }

  function onJoin(from, payload) {
    if (!from || from === me) return;
    ensurePeer(from, payload || {});
    syncPeerFlags();
  }

  function onLeave(from) {
    if (!from) return;
    dropPeer(from);
    syncPeerFlags();
  }

  function onMute(from, payload) {
    const slot = pcs[from];
    if (!slot) return;
    slot.muted = !!(payload && payload.muted);
    if (slot.muted) slot.speaking = false;
    syncPeerFlags();
  }

  function handleMsg(raw) {
    if (raw === 'pong') return;
    let msg;
    try { msg = JSON.parse(raw); } catch (e) { return; }
    if (!msg || typeof msg !== 'object') return;
    const typ = msg.type;
    const from = msg.from;
    const payload = msg.payload && typeof msg.payload === 'object' ? msg.payload : {};
    if (typ === 'pong') return;
    if (typ === 'error') {
      const notice = payload.notice || '对讲信令出错';
      toast(notice, 'warn');
      if (payload.code === 4403 || payload.code === 4404 || payload.code === 4400) leave();
      return;
    }
    if (typ === 'peers') { onPeers(payload); return; }
    if (typ === 'join') { onJoin(from, payload); return; }
    if (typ === 'leave') { onLeave(from); return; }
    if (typ === 'offer') { onOffer(from, payload); return; }
    if (typ === 'answer') { onAnswer(from, payload); return; }
    if (typ === 'ice') { onIce(from, payload); return; }
    if (typ === 'mute') { onMute(from, payload); return; }
  }

  function stopPing() {
    if (pingTimer) { clearInterval(pingTimer); pingTimer = 0; }
  }
  function startPing() {
    stopPing();
    pingTimer = setInterval(function () { sendRaw('ping'); }, PING_MS);
  }

  function closeWs() {
    stopPing();
    const sock = ws;
    ws = null;
    if (!sock) return;
    try { sock.onopen = sock.onmessage = sock.onerror = sock.onclose = null; } catch (e) { /* ignore */ }
    try { if (sock.readyState === 0 || sock.readyState === 1) sock.close(); } catch (e2) { /* ignore */ }
  }

  function scheduleRetry() {
    if (!wanted || intentionalClose) return;
    if (retryN >= 5) {
      toast('对讲通道断开，请再点加入', 'warn');
      leave();
      return;
    }
    const wait = Math.min(800 * Math.pow(2, retryN), 6400);
    retryN += 1;
    connecting = true;
    emitState();
    retryTimer = setTimeout(function () {
      retryTimer = 0;
      if (wanted) openSocket();
    }, wait);
  }

  function openSocket() {
    if (!canRtc() || !sessionId || !me) return;
    closeWs();
    const q = 'player_id=' + encodeURIComponent(me)
      + (listenOnly ? '&listen_only=1' : '');
    const url = wsBase() + '/ws/' + encodeURIComponent(sessionId) + '/voice?' + q;
    let sock;
    try { sock = new WebSocket(url); } catch (e) {
      toast('对讲通道连不上', 'warn');
      scheduleRetry();
      return;
    }
    ws = sock;
    sock.onopen = function () {
      if (ws !== sock) return;
      retryN = 0;
      connecting = false;
      live = true;
      startPing();
      hookVoice();
      pauseVoiceForTalk();
      applyMutex();
      emitState();
    };
    sock.onmessage = function (ev) {
      if (ws !== sock) return;
      handleMsg(typeof ev.data === 'string' ? ev.data : '');
    };
    sock.onerror = function () { /* onclose 会处理 */ };
    sock.onclose = function () {
      if (ws === sock) ws = null;
      stopPing();
      if (intentionalClose || !wanted) return;
      teardownPeers();
      live = false;
      connecting = true;
      emitState();
      scheduleRetry();
    };
  }

  function stopLocal() {
    dropAnalyser('local');
    if (localStream) {
      try {
        (localStream.getTracks() || []).forEach(function (t) { t.stop(); });
      } catch (e) { /* ignore */ }
      localStream = null;
    }
  }

  function fetchIce(sid) {
    return fetch('/api/session/' + encodeURIComponent(sid) + '/voice/ice-servers')
      .then(function (r) {
        if (!r.ok) throw new Error('ice');
        return r.json();
      })
      .then(function (body) {
        if (body && body.ice_servers && body.ice_servers.length) iceServers = body.ice_servers;
        else iceServers = DEFAULT_ICE;
        turnConfigured = !!(body && body.turn_configured);
        return true;
      })
      .catch(function () {
        iceServers = DEFAULT_ICE;
        turnConfigured = false;
        return false;
      });
  }

  function getMic() {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.resolve(null);
    }
    return navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      video: false
    }).then(function (stream) {
      return stream;
    }).catch(function () {
      return null;
    });
  }

  function hookUnload() {
    if (unloadHooked || typeof window === 'undefined') return;
    unloadHooked = true;
    window.addEventListener('pagehide', function () { leave(); });
  }

  function join(opt) {
    opt = opt || {};
    if (!canRtc()) {
      toast('当前环境不支持房间对讲', 'warn');
      return Promise.resolve(false);
    }
    if (!isSecure()) {
      toast('对讲需要 HTTPS（或本机 127.0.0.1）', 'warn');
      return Promise.resolve(false);
    }
    const S = window.Store && window.Store.state;
    const sid = String(opt.sessionId || opt.session_id || (S && S.sessionId) || '').trim();
    const pid = String(opt.playerId || opt.player_id || (S && S.playerId) || '').trim();
    let lo = opt.listenOnly != null ? !!opt.listenOnly : !!(S && S.isSpectator);
    if (!sid || !pid) {
      toast('还没进房间，先加入 party 再对讲', 'warn');
      return Promise.resolve(false);
    }
    if (wanted && live && sid === sessionId && pid === me) return Promise.resolve(true);
    if (wanted) leave();

    const my = ++joinGen;
    wanted = true;
    intentionalClose = false;
    connecting = true;
    live = false;
    sessionId = sid;
    me = pid;
    listenOnly = lo;
    role = lo ? 'spectator' : 'player';
    userMuted = !!lo;
    failToasted = false;
    retryN = 0;
    emitState();
    unlockAudio();
    hookUnload();
    hookVoice();
    pauseVoiceForTalk();

    return fetchIce(sid).then(function () {
      if (my !== joinGen || !wanted) return false;
      if (lo) return true;
      return getMic().then(function (stream) {
        if (my !== joinGen || !wanted) {
          if (stream) try { stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) { /* ignore */ }
          return false;
        }
        if (!stream) {
          toast('麦克风被拒绝，已改为只听', 'warn');
          listenOnly = true;
          userMuted = true;
          role = 'spectator';
          return true;
        }
        localStream = stream;
        applyUplink();
        attachAnalyser('local', stream);
        startSpeakLoop();
        return true;
      });
    }).then(function (ok) {
      if (my !== joinGen || !wanted) return false;
      if (!ok) {
        if (my === joinGen) leave();
        return false;
      }
      openSocket();
      emitState();
      return true;
    }).catch(function () {
      if (my === joinGen) {
        toast('对讲加入失败', 'warn');
        leave();
      }
      return false;
    });
  }

  function leave() {
    joinGen += 1;
    wanted = false;
    intentionalClose = true;
    connecting = false;
    live = false;
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = 0; }
    retryN = 0;
    closeWs();
    teardownPeers();
    stopLocal();
    stopSpeakLoop();
    unhookVoice();
    resumeVoiceAfterTalk();
    duckSfx(false);
    listenOnly = false;
    userMuted = false;
    role = '';
    me = '';
    sessionId = '';
    failToasted = false;
    flags.peers = [];
    flags.speakingIds = [];
    emitState();
  }

  function setMicOn(on) {
    if (listenOnly) return false;
    userMuted = !on;
    applyUplink();
    sendSignal('mute', null, { muted: !!userMuted });
    syncPeerFlags();
    return !userMuted;
  }
  function setSpeakerOn(on) {
    speakerOn = !!on;
    applySpeaker();
    emitState();
    return speakerOn;
  }
  function toggleMic() { return setMicOn(userMuted); }
  function toggleSpeaker() { return setSpeakerOn(!speakerOn); }

  function makeDock() {
    if (typeof Vue === 'undefined') return null;
    const { computed, onBeforeUnmount } = Vue;
    return {
      name: 'voice-rtc-dock',
      setup: function () {
        const S = window.Store.state;
        const F = flags;
        const shown = computed(function () {
          if (!(S.mode === 'party' && S.sessionId && S.playerId)) return false;
          return S.phase === 'play' || S.phase === 'seat' || S.phase === 'party';
        });
        const lobby = computed(function () { return S.phase !== 'play'; });
        const talkLine = computed(function () {
          const ids = F.speakingIds || [];
          if (!ids.length) return '';
          return ids.map(peerName).filter(Boolean).join(' · ');
        });
        function doJoin() {
          join({
            sessionId: S.sessionId,
            playerId: S.playerId,
            listenOnly: !!S.isSpectator
          });
        }
        onBeforeUnmount(function () { /* 根组件常驻；离开对局由 Store/leave 收口 */ });
        return {
          S: S, F: F, shown: shown, lobby: lobby, talkLine: talkLine,
          doJoin: doJoin, doLeave: leave,
          toggleMic: toggleMic, toggleSpeaker: toggleSpeaker
        };
      },
      template: `
        <aside v-if="shown" class="voice-rtc-dock" :class="{ live: F.live, lobby: lobby, listen: F.listenOnly }"
               role="region" aria-label="房间对讲">
          <header class="vrd-hd">
            <b>对讲</b>
            <span class="vrd-count" v-if="F.live">{{ F.peerCount }} 路</span>
            <span class="chip tiny" v-if="F.listenOnly">只听</span>
            <span class="vrd-wait" v-else-if="F.connecting">连接中</span>
            <span class="vrd-talk" v-if="talkLine">{{ talkLine }}</span>
            <span class="vrd-idle" v-else-if="F.live">无人说话</span>
          </header>
          <div class="vrd-acts">
            <button v-if="!F.live && !F.connecting" type="button" class="btn primary sm"
                    @click="doJoin">{{ S.isSpectator ? '加入收听' : '加入对讲' }}</button>
            <button v-else-if="F.connecting && !F.live" type="button" class="btn ghost sm" disabled>连接中…</button>
            <template v-else>
              <button v-if="!F.listenOnly" type="button" class="btn ghost sm" :class="{ on: F.micOn }"
                      :aria-pressed="F.micOn ? 'true' : 'false'" aria-label="麦克风"
                      @click="toggleMic">{{ F.micOn ? '麦开' : '麦关' }}</button>
              <button type="button" class="btn ghost sm" :class="{ on: F.speakerOn }"
                      :aria-pressed="F.speakerOn ? 'true' : 'false'" aria-label="扬声器"
                      @click="toggleSpeaker">{{ F.speakerOn ? '听筒开' : '听筒关' }}</button>
              <button type="button" class="btn ghost sm" @click="doLeave">离开</button>
            </template>
          </div>
          <ul class="vrd-peers" v-if="F.live && F.peers.length">
            <li v-for="p in F.peers" :key="p.player_id" :class="{ talk: p.speaking, mute: p.muted }">
              {{ p.name }}<i v-if="p.speaking">说话</i><i v-else-if="p.muted">静音</i><i v-else-if="p.listen_only">听</i>
            </li>
          </ul>
        </aside>`
    };
  }

  const Dock = makeDock();

  function install(app) {
    if (!app || !Dock || !app.component) return;
    try { app.component('voice-rtc-dock', Dock); } catch (e) { /* ignore */ }
  }

  window.VoiceRTC = {
    supported: supported,
    join: join,
    leave: leave,
    setMicOn: setMicOn,
    setSpeakerOn: setSpeakerOn,
    toggleMic: toggleMic,
    toggleSpeaker: toggleSpeaker,
    isLive: function () { return !!live; },
    isListenOnly: function () { return !!listenOnly; },
    isMicOn: function () { return !userMuted && !listenOnly; },
    isSpeakerOn: function () { return !!speakerOn; },
    isConnecting: function () { return !!connecting; },
    status: status,
    peers: function () { return flags.peers.slice(); },
    onState: onState,
    flags: flags,
    install: install,
    Dock: Dock
  };
})();
