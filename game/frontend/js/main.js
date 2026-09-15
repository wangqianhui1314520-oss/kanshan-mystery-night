/* ============================================================
 * main.js —— 根应用：HUD / 视图路由 / 启动引导 / WS 事件接线
 * ============================================================ */
(function () {
  const { createApp, computed, ref, watch } = Vue;
  const M = window.MOCK;

  /* V4 综艺流程（G2）：三幕转场 DM 幕引言（act_t1/t2/t3 配文，2.5s 自动过或点击跳过） */
  const CUT_LINES = {
    1: '叮——第一幕 · 破冰圆桌：全员到齐，唯独主角缺席。',
    2: '叮——第二幕 · 记忆对质：记忆会撒谎，时间线不会。',
    3: '叮——第三幕 · 热搜风暴：热度升起时，真相开始缺氧。'
  };
  /* 案件卷宗页三段案情（DM=看山系统音，环节② 对齐 V4_SHOWTIME §一） */
  const CASE_BRIEF = [
    '周五盘点夜。21:00，首席荣誉侦探刘看山进档案室核对最后一柜，之后再未出现。现场没有脚印，没有搏斗痕迹——好像他从来只是「暂时不在」。',
    '监控时间轴 21:07–21:15 被局长级账号 KS-000 挖空。记忆芯片是另一套东西：它存的是目击存证；热度工具改的是存证，不是监控原片。',
    '21:00 大门横幅亮起：【不出真相，不出此门】。23:00 封控确认无法解除。八位当晚在场者已在圆桌就座；特聘席随后被特许入内。请翻阅卷宗，开始提问。'
  ];

  /* V5 章节独占式（CHAPTER_UX_SPEC §二）：章定义 + 本章机制入口（其他章彻底移除出 DOM） */
  const CHAPTERS = {
    1: { name: '第一章 · 出不去的档案局', tag: '搜证章' },
    2: { name: '第二章 · 心声泄露', tag: '对质章' },
    3: { name: '第三章 · 披着虎皮的猫', tag: '舆论章' }
  };
  const CHAPTER_MENUS = {
    1: [ { id: 'map', name: '现场搜证', icon: 'map' }, { id: 'bag', name: '证物袋', icon: 'bag' }, { id: 'kcards', name: '知识卡', icon: 'cards' } ],
    2: [ { id: 'memory', name: '记忆修复', icon: 'memory' }, { id: 'clinic', name: '心晴诊室', icon: 'heart' }, { id: 'pollution', name: '污染对照', icon: 'compare' }, { id: 'kcards', name: '知识弹药', icon: 'cards' } ],
    3: [ { id: 'hotfeed', name: '热搜面板', icon: 'fire' }, { id: 'vote', name: '终局指认', icon: 'table' } ]
  };
  /* 全程公用机制（1.1 表）：对话/押注常驻；复盘/侦探档案=元系统 */
  /* 公用入口分层：圆桌是主循环；其余工具放入次级区，避免首屏像功能大厅。 */
  const COMMON_MENUS = [
    { id: 'chat', name: '圆桌对话', icon: 'chat' },
    { id: 'report', name: '侦探档案', icon: 'badge' }
  ];

  const App = {
    setup() {
      const S = window.Store.state;
      const hostOpen = ref(false);
      const goalOpen = ref(false);
      const taskCard = computed(() => window.GoalCards.project(S));
      const openTaskCard = () => { window.Store.hydrateBooklet(); goalOpen.value = true; };
      watch(() => S.phase, () => { hostOpen.value = false; goalOpen.value = false; });
      const booted = ref(false);
      const bootMsg = ref('连接档案局…');
      const settings = ref(false);
      const leaveAsk = ref(false);
      const settingsAdv = ref(false);
      const askLeave = () => { leaveAsk.value = true; };
      const confirmLeave = () => { leaveAsk.value = false; settings.value = false; window.Store.leaveToMenu(); };
      const wsUrl = ref((typeof location !== 'undefined' && new URLSearchParams(location.search).get('ws')) || '');
      const dossierOpen = ref(false);
      const joinCode = ref('');
      const achOpen = ref(false), helpOpen = ref(false), aboutOpen = ref(false);
      const apiForm = Vue.reactive((() => { try { return JSON.parse(localStorage.getItem('kanshan_api') || '{}'); } catch (e) { return {}; } })());
      apiForm.llmBase = apiForm.llmBase || 'https://developer.zhihu.com/v1';
      apiForm.llmKey = apiForm.llmKey || '';
      apiForm.llmModel = apiForm.llmModel || 'zhida-agent';
      apiForm.zhihuSecret = apiForm.zhihuSecret || '';
      const ACH_IMG = {
        '看山还是山': '/assets/images/ach_mountain.png',
        '心晴医师': '/assets/images/ach_heart_doctor.png',
        '带节奏之王': '/assets/images/ach_rhythm_king.png',
        '鱼干守护者': '/assets/images/ach_fish_guardian.png',
        '防折叠斗士': '/assets/images/ach_antifold.png',
        '暗房大师': '/assets/images/ach_darkroom.png',
        '全场公敌': '/assets/images/ach_public_enemy.png',
        '鱼干线人': '/assets/images/icon_fish.png',
        '反诈先锋': '/assets/images/icon_rumor.png'
      };
      const saveApi = () => { localStorage.setItem('kanshan_api', JSON.stringify(apiForm)); window.Store.toast('API 配置已保存——本局空席开打即可调用', 'good'); settings.value = false; };
      /* 模型切换：选 DeepSeek 系自动切官方兼容端点；切回知乎系恢复默认端点 */
      const onModelChange = () => {
        const m = String(apiForm.llmModel || '');
        if (m.indexOf('deepseek') === 0) {
          apiForm.llmBase = 'https://api.deepseek.com';
        } else if (!apiForm.llmBase || apiForm.llmBase.indexOf('deepseek') >= 0) {
          apiForm.llmBase = 'https://developer.zhihu.com/v1';
        }
      };

      /* ---- 体验层（UX）：引擎状态 / 连接状态 / 首屏引导 ---- */
      const UX = window.UX;
      const eng = UX.engine;
      const ai = UX.ai;
      const aiSeats = computed(() => ai.seats.map(seat => ({...seat,
        name: ((M.chars || []).find(c => c.id === seat.char_id) || {}).name || seat.char_id
      })));
      const aiDecision = computed(() => S.aiLastDecision || null);
      watch(() => S.sessionId, () => UX.probeEngine({silent: true}));
      watch(() => S.chat.length, () => UX.probeEngine({silent: true}));
      const conn = UX.conn;
      const guideOpen = ref(false);
      const guideFired = ref(false);

      /* 裁决来源文案：一律由 /api/health 实测得出，不写死任何模式名 */
      const engineSource = computed(() => ({
        ok: '规则引擎 · 确定性裁决',
        degraded: '降级模式 · 部分演出简化',
        offline: '引擎状态未知（离线）',
        loading: '正在核对引擎…'
      }[eng.probe] || '正在核对引擎…'));
      const transportSource = computed(() => (S.netKind === 'ws' ? 'WebSocket 实时通道' : S.netKind === 'mock' ? '未开局 · 开局后自动连接服务器' : S.netKind === 'error' ? '连接失败' : '尚未连接对局'));
      const connText = computed(() => ({
        reconnecting: '⟳ 正在重连档案局…' + (conn.attempts ? '（第 ' + conn.attempts + ' 次）' : ''),
        offline: conn.note || '⚠ 实时通道已断开，请重连后确认对局状态',
        restoring: '↻ 通道已恢复，正在恢复你的角色席位…',
        restored: '✓ 通道与角色席位均已恢复'
      }[conn.state] || ''));
      const restorePartyAfterReconnect = async () => {
        if (!S.mode || S.mode !== 'party' || S.isSpectator) return true;
        conn.state = 'restoring'; conn.note = '通道已恢复，正在恢复你的角色席位…';
        const ok = await window.Store.restorePartySeat();
        if (ok) {
          conn.state = 'restored'; conn.note = '通道与角色席位均已恢复';
          window.Store.toast('已恢复你的角色席位，AI 接管已解除', 'good');
          setTimeout(() => { if (conn.state === 'restored') conn.state = 'online'; }, 1800);
          return true;
        }
        conn.state = 'offline';
        conn.note = '通道已恢复，但角色仍由 AI 接管；点击“重新入房”恢复席位';
        window.Store.toast('实时通道已恢复，但角色仍由 AI 接管，请重新入房', 'warn');
        return false;
      };

      const recheckEngine = async () => {
        await UX.probeEngine();
        if (apiForm.llmKey || apiForm.zhihuSecret) {
          window.Store.toast('正在发送知乎 Agent 测试请求…', '');
          const ok = await UX.testAi();
          window.Store.toast(ok ? '知乎 Agent 测试成功' : '知乎 Agent 测试失败，请查看健康说明', ok ? 'good' : 'warn');
        }
        window.Store.toast(eng.label, eng.probe === 'ok' ? 'good' : 'warn');
      };
      const retryConn = async () => {
        /* 自动重连后 WS 可能已在线但席位恢复失败；此时直接重试 /join，
           不再调用一个“已在线所以什么都不做”的 retryNow。 */
        if (S.mode === 'party' && conn.note.indexOf('角色仍由 AI') >= 0) {
          await restorePartyAfterReconnect();
          return;
        }
        if (!window.Net.retryNow()) UX.probeEngine();
      };
      /* 首屏自动引导（单人自助：没人讲解流程，只能靠它） */
      function maybeGuide() {
        if (guideFired.value || guideOpen.value) return;
        if (!booted.value || S.phase !== 'play') return;
        if (S.showtime && (S.showtime.step === 'case_file' || S.showtime.cut)) return;
        if (S.recap || S.elevator || S.bookletForced) return;
        if (UX.isOnboarded()) { guideFired.value = true; return; }
        guideFired.value = true;
        setTimeout(() => { guideOpen.value = true; }, 260);
      }
      const replayGuide = () => { UX.resetOnboarded(); guideFired.value = true; guideOpen.value = true; };
      const guideDone = () => { guideOpen.value = false; };
      watch([booted, () => S.phase, () => S.showtime && S.showtime.step, () => S.showtime && S.showtime.cut, () => S.recap, () => S.elevator, () => S.bookletForced], maybeGuide, { immediate: true });

      const STAGE_NAMES = { 1: '搜证章', 2: '对质章', 3: '舆论章' };
      const actName = computed(() => '第' + (S.act || 1) + '幕 · ' + (STAGE_NAMES[S.act] || '调查中'));
      const flawN = computed(() => window.Store.flawCount());
      const kcOwned = computed(() => Object.keys(S.kcards).length);
      const erN = computed(() => Object.keys(S.er || {}).length);
      /* V5 章节独占式：当前章定义 / 本章+公用机制入口 / 章末条件 */
      const chapter = computed(() => {
        const fallback = CHAPTERS[S.act] || CHAPTERS[1];
        const acts = S.studioMeta && S.studioMeta.acts;
        const row = acts && acts[(S.act || 1) - 1];
        if (!row) return fallback;
        const st = row.stage && window.Labels ? window.Labels.stage(row.stage) : (row.stage || fallback.tag);
        return { name: row.name || fallback.name, tag: st || fallback.tag };
      });
      const utilityItems = computed(() => [
        { id: 'quiz', name: '快问快答', icon: 'badge' },
        { id: 'radio', name: '广播台', icon: 'scroll' },
        { id: 'evidence', name: '证据拼图', icon: 'scroll' }
      ]);
      const menuItems = computed(() => {
        let items = (CHAPTER_MENUS[S.act] || CHAPTER_MENUS[1]).concat(COMMON_MENUS);
        const mods = S.studioModules;
        if (!(S.scenarioId && mods)) return items;
        items = items.filter(n => {
          if (n.id === 'hotfeed' && mods.hotfeed === false) return false;
          if (n.id === 'memory' && mods.memory === false) return false;
          if (n.id === 'clinic' && mods.counsel === false) return false;
          if (n.id === 'kcards' && mods.kcards === false) return false;
          if (n.id === 'pollution' && mods.pollution === false) return false;
          if (n.id === 'evidence' && mods.evidence === false) return false;
          return true;
        });
        if (Array.isArray(S.studioMinis) && S.studioMinis.length) {
          items = items.concat([{ id: 'mini', name: '小游戏厅', icon: 'badge' }]);
        }
        if (S.demo && !items.some(n => n.id === 'vote')) {
          items = items.concat([{ id: 'vote', name: '终局指认', icon: 'table' }]);
        }
        return items;
      });
      const playSkin = computed(() => {
        const act = 'act-theme-' + (S.act || 1);
        return S.studioVibe === 'horror' ? act + ' studio-vibe-horror' : act;
      });
      const cutLine = computed(() => {
        const act = S.showtime && S.showtime.cut && S.showtime.cut.act;
        const row = S.studioMeta && S.studioMeta.acts && S.studioMeta.acts[act - 1];
        if (row && (row.brief || row.name)) return row.brief || row.name;
        return CUT_LINES[act] || '';
      });
      const showHeat = computed(() => !(S.scenarioId && S.studioModules && S.studioModules.hotfeed === false));
      const showKcards = computed(() => !(S.scenarioId && S.studioModules && S.studioModules.kcards === false));
      const showFlaw = computed(() => !S.scenarioId);
      const showZans = computed(() => !S.demo && !(S.scenarioId && S.studioModules && S.studioModules.bet === false));
      const rail = computed(() => window.Store.demoRailSteps());
      const railOn = computed(() => S.demo && S.phase === 'play');
      const prog = computed(() => window.Store.chapterProgress());
      const pacingHint = computed(() => window.Store.pacingHint());
      /* DM 导演层：把章节条件翻译成玩家可执行的分步任务。 */
      const dmTasks = computed(() => {
        const a = S.act || 1, stage = S.stage || 'investigate';
        const searched = Object.keys(S.searched || {}).length > 0;
        const clues = Object.keys(S.clues || {}).length;
        const chatCount = (S.chat || []).filter(m => m.actor === 'me' || m.actor === 'peer').length;
        const links = (S.evidenceLinks || []).length;
        if (stage === 'break_ice') return [
          { text: '听完 DM 与角色自我介绍', done: chatCount >= 1 },
          { text: '打开并阅读本幕剧本', done: !!(S.dmBookRead || S.playerBook || S.bookletOpen) },
          { text: '点击「开始搜证」进入现场', done: false }
        ];
        if (a === 1) return [
          { text: '搜查至少一个现场位置', done: searched },
          { text: '取得关键芯片线索', done: !!(S.clues && (S.clues.clue_021 || S.clues.clue_028)) },
          { text: '回到圆桌汇报并确认时间线', done: chatCount >= 2 }
        ];
        if (a === 2) return [
          { text: '修复一段角色记忆', done: Object.keys(S.memories || {}).length > 0 || Object.keys(S.liveMemories || {}).length > 0 },
          { text: '完成一次证据拼图或污染对照', done: links > 0 || !!(S.pollution && S.pollution.done && Object.keys(S.pollution.done).length) },
          { text: '在圆桌完成一次对质', done: !!(S.debate && S.debate.rounds && S.debate.rounds.length) }
        ];
        return [
          { text: '核对热搜与现场证据', done: !!(S.hotfeedSignals || (S.posts && Object.keys(S.posts).length)) },
          { text: '整理证据链并锁定嫌疑人', done: links >= 2 || clues >= 5 },
          { text: '听完 DM 终局播报后提交指认', done: !!S.ended }
        ];
      });
      const dmNext = computed(() => {
        const t = dmTasks.value.find(x => !x.done);
        return t ? t.text : '本幕目标已完成，DM 正在召回全员进入下一环节';
      });
      const dmMini = computed(() => {
        if (S.ended || !window.Minis || S.view === 'mini') return null;
        if (S.act === 1 && S.round === 2 && !S.dmMiniSeen.runner) return { id: 'runner', title: 'DM 插入小游戏：看山快跑', hint: '线索太安静了，先来一局热身，赢取额外行动点。' };
        if (S.act === 2 && S.round === 5 && !S.dmMiniSeen.heart) return { id: 'heart', title: 'DM 插入小游戏：心声窃听', hint: '记忆出现杂音，完成小游戏可获得一条心声片段。' };
        if (S.act === 3 && S.round === 8 && !S.dmMiniSeen.refute3) return { id: 'refute3', title: 'DM 插入小游戏：谣言消消乐', hint: '热搜开始失控，先拆掉一条假消息。' };
        return null;
      });
      const openDmMini = () => { if (dmMini.value && window.Minis) { S.dmMiniSeen[dmMini.value.id] = true; window.Minis.open(dmMini.value.id); } };
      const dmProgress = computed(() => {
        const ts = dmTasks.value || [];
        return ts.length ? Math.round(ts.filter(t => t.done).length / ts.length * 100) : 0;
      });
      const caseBrief = computed(() => {
        if (S.scenarioId && S.studioMeta) {
          const m = S.studioMeta;
          return [
            m.logline || m.summary || '',
            m.hook || '',
            '四位当事人在圆桌就座。调查员，请先听完自我介绍，再点击「开始搜证」。'
          ].filter(Boolean);
        }
        return CASE_BRIEF;
      });
      const caseTitle = computed(() => (S.studioMeta && S.studioMeta.title) ? S.studioMeta.title : '看山失踪夜');

      function wireMinisHash() {
        window.addEventListener('hashchange', () => {
          if (/^#\/mini\//.test(location.hash)) S.view = 'mini';
          else if (S.view === 'mini') S.view = 'report';
        });
        if (/^#\/mini\//.test(location.hash)) S.view = 'mini';
      }
      async function boot() {
        UX.probeEngine();
        window.__connStatusHook = (st) => {
          conn.attempts = st.attempts || 0;
          conn.note = st.note || '';
          if (st.state === 'online' && st.reconnected) {
            restorePartyAfterReconnect();
          } else {
            conn.state = st.state;
          }
          if (st.state === 'online') UX.probeEngine({ silent: true });
        };
        let roomParam = new URLSearchParams(location.search).get('room');
        if (!roomParam) {
          try {
            const ticket = JSON.parse(sessionStorage.getItem('party_ticket') || '{}');
            if (ticket.code && ticket.sid) {
              roomParam = ticket.code;
              try { history.replaceState(null, '', '/?room=' + encodeURIComponent(roomParam)); } catch (e) { }
            }
          } catch (e) { }
        }
        if (roomParam) {
          const ok = await window.Store.joinRoom(roomParam);
          if (ok) {
            S.netKind = window.Net.kind();
            S.sessionId = window.Net.id() || S.sessionId;
            conn.transport = S.netKind || '';
            conn.state = S.netKind === 'ws' ? 'online' : 'idle';
            if (window.Net.on) window.Net.on('_status', window.__connStatusHook);
            wireRoomLifecycle();
            window.Store.chat('dm', '叮——已连入房间 ' + roomParam + '。不出真相，不出此门。', {});
          }
          wireMinisHash();
          booted.value = true;
          return;
        }
        /* 主菜单不预开 mock 通道（http(s) 下）：避免刷新后出现「本地自持 / mock_xxx」，
           真正开局或进房时再 Net.init / connectParty。
           file:// 直开例外：无服务器可言，有意走 mock（评委本地演示），UI 如实标注。 */
        if (wsUrl.value) {
          const info = await window.Net.init({ wsUrl: wsUrl.value || undefined });
          S.netKind = info.mode; S.sessionId = info.session_id;
          conn.transport = info.mode || '';
          conn.state = info.mode === 'ws' ? 'online' : 'idle';
          window.Net.on('_status', window.__connStatusHook);
          wireRoomLifecycle();
          ['search_result', 'clue_gained', 'chat', 'memory_unlock', 'counsel_result', 'hotfeed_refresh', 'faction_skill', 'vote', 'ending', 'danmaku', 'system', 'achievement_unlocked', 'cocoon_break', 'evidence_pin', 'defect']
            .forEach(t => window.Net.on(t, evt => window.Store.applyEvent(evt)));
        } else if (location.protocol === 'file:') {
          const info = await window.Net.init({ mock: true });
          S.netKind = info.mode; S.sessionId = info.session_id;
          conn.transport = info.mode || '';
          conn.state = 'idle';
          ['search_result', 'clue_gained', 'chat', 'memory_unlock', 'counsel_result', 'hotfeed_refresh', 'faction_skill', 'vote', 'ending', 'danmaku', 'system', 'achievement_unlocked', 'cocoon_break', 'evidence_pin', 'defect']
            .forEach(t => window.Net.on(t, evt => window.Store.applyEvent(evt)));
          wireRoomLifecycle();
        } else {
          conn.transport = '';
          conn.state = 'idle';
        }
        wireMinisHash();
        booted.value = true;
      }

      const navGo = (id) => {
        if (S.phase !== 'play') return;
        const allowed = menuItems.value.some(n => n.id === id) || utilityItems.value.some(n => n.id === id);
        if (!allowed && id !== 'chat' && id !== 'report') {
          window.Store.toast('该机制将在后续章节解锁 · 当前请按本章目标推进', 'warn');
          return;
        }
        if (id === 'map' && S.stage === 'break_ice') {
          if (window.Store.iceBlocksSearch && window.Store.iceBlocksSearch()) {
            window.Store.toast('先完成 DM 破冰，再点击「开始搜证」', 'warn');
            S.view = 'chat';
            return;
          }
        }
        if (id === 'map' && S.act === 1 && S.round === 1 && !S.skipIce && S.playMode !== 'daily' && S.playMode !== 'quick'
            && !Object.keys(S.searched || {}).length && !S.scenarioId) {
          window.Store.toast('DM 流程：先读本并听完角色亮相，再进入搜证');
          S.view = 'chat';
          return;
        }
        S.view = id;
      };
      const elevatorDone = () => { S.elevator = null; };
      /* 第一幕转场动态背景：banner 视频加载失败时降级回 act_t1.png（会话内记住，避免重复请求 404） */
      const cutVidErr = Vue.ref(false);
      const audioMuted = ref(window.SFX && window.SFX.isMuted ? window.SFX.isMuted() : false);
      const Voice = window.Voice;
      const voiceOut = ref(Voice && Voice.prefs ? Voice.prefs().output : true);
      const voiceIn = ref(Voice && Voice.prefs ? Voice.prefs().input : false);
      const voiceAuto = ref(Voice && Voice.prefs ? Voice.prefs().auto : false);
      const toggleAudio = () => {
        audioMuted.value = !audioMuted.value;
        if (window.SFX) window.SFX.setMuted(audioMuted.value);
        if (audioMuted.value && window.Voice && window.Voice.cancelSpeak) window.Voice.cancelSpeak();
      };
      const toggleVoiceOut = () => {
        voiceOut.value = !voiceOut.value;
        if (window.Voice) window.Voice.setOutputOn(voiceOut.value);
      };
      const toggleVoiceIn = () => {
        voiceIn.value = !voiceIn.value;
        if (window.Voice) window.Voice.setInputOn(voiceIn.value);
      };
      const toggleVoiceAuto = () => {
        voiceAuto.value = !voiceAuto.value;
        if (window.Voice) window.Voice.setAutoSend(voiceAuto.value);
      };
      /* ---- 房间生命周期事件可视化（player_rejoined / spectator_joined / npc_pending / rt_flow_error）
       * 服务端经 system 事件下发（server/main.py）。不改 store.js：在此经 Net.on('system') 叠加订阅，
       * 不影响 store 既有分发。mock/file:// 通道不产出这些事件 → 状态恒空，UI 不显示任何占位。 ---- */
      const roomLife = Vue.reactive({ spectators: 0, npcPending: '', npcPendingTimer: null, flowError: '', flowErrorTimer: null });
      const lifecycleWho = (pid, seats) => {
        const seat = (seats || []).find(s => s && s.player_id === pid && s.char_id) || null;
        return (seat && window.Labels && window.Labels.who(seat.char_id)) || '一位队友';
      };
      const wireRoomLifecycle = () => {
        if (!window.Net || !window.Net.on) return;
        window.Net.on('system', (evt) => {
          const p = (evt && evt.payload) || {};
          if (p.event === 'player_rejoined') {
            window.Store.toast(lifecycleWho(p.player_id, p.seats) + ' 已重新连入房间，席位恢复', 'ok');
          } else if (p.event === 'spectator_joined') {
            roomLife.spectators += 1;
            window.Store.toast('一位旁听者进入了房间', 'ok');
          } else if (p.event === 'npc_pending') {
            roomLife.npcPending = String(p.target || '').replace(/^npc:/, '');
            clearTimeout(roomLife.npcPendingTimer);
            roomLife.npcPendingTimer = setTimeout(() => { roomLife.npcPending = ''; }, 12000);
          } else if (p.event === 'rt_flow_error') {
            roomLife.flowError = p.notice || '演出流程异常';
            clearTimeout(roomLife.flowErrorTimer);
            roomLife.flowErrorTimer = setTimeout(() => { roomLife.flowError = ''; }, 9000);
          }
        });
      };
      const npcPendingName = computed(() => {
        const c = (M.chars || []).find(x => x.id === roomLife.npcPending) || {};
        return c.name || 'AI';
      });
      const VoiceRTC = window.VoiceRTC;
      const rtcLive = ref(false);
      const rtcListen = ref(false);
      if (VoiceRTC && VoiceRTC.onState) {
        VoiceRTC.onState(function (st) {
          rtcLive.value = !!(st && st.live);
          rtcListen.value = !!(st && st.listenOnly);
        });
      }
      const rtcJoin = () => {
        if (!VoiceRTC || !VoiceRTC.join) return;
        VoiceRTC.join({
          sessionId: S.sessionId,
          playerId: S.playerId,
          listenOnly: !!S.isSpectator
        });
      };
      const rtcLeave = () => { if (VoiceRTC && VoiceRTC.leave) VoiceRTC.leave(); };
      const copyShare = () => {
        const url = S.shareUrl || '';
        if (!url) return;
        if (window.SFX) window.SFX.play('copy');
        const done = () => window.Store.toast('分享链接已复制，发给同一 WiFi 的好友即可', 'ok');
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(done).catch(() => window.Store.toast('复制失败，请手动选中链接复制', 'warn'));
        } else {
          try { const i = document.createElement('input'); i.value = url; document.body.appendChild(i); i.select(); document.execCommand('copy'); document.body.removeChild(i); done(); }
          catch (e) { window.Store.toast('复制失败，请手动选中链接复制', 'warn'); }
        }
      };
      /* V5：章末「进入下一章 ▸」——advance（引擎门控最终裁决）→ actSet 切章 + 转场 + 前情提要；
       * 章三按钮=进入终局指认（终局结算层入口，不推进幕） */
      const goNextChapter = () => {
        if (S.busy) return false;
        /* 破冰结束是第一步推进，不要求先有线索；搜证门槛由服务端在 investigate 阶段裁决。 */
        if (S.stage === 'break_ice') {
          if (window.Store.finishStudioBreakIce && window.Store.finishStudioBreakIce() !== false) S.view = 'chat';
          return false;
        }
        if (S.stage === 'investigate' && S.act === 1 && !S.demo && !Object.keys(S.searched || {}).length) {
          S.view = 'map';
          return true;
        }
        const p = prog.value;
        if (!p.cleared) { window.Store.toast(p.hint, 'warn'); return false; }
        if (S.act >= 3) { S.view = 'vote'; return true; }
        const ok = window.Store.send('advance', S.demo ? { demo_bypass: true } : {});
        if (ok !== false) S.view = 'chat';
        return ok !== false;
      };
      const hostAdvance = () => { if (S.isHost && !S.busy) goNextChapter(); };

      /* V4 综艺流程：幕转场全屏页 2.5s 自动过（点击可提前跳过，跳过后定时器失效） */
      watch(() => S.showtime && S.showtime.cut, (cut) => {
        if (!cut) return;
        setTimeout(() => {
          if (S.showtime && S.showtime.cut === cut) S.showtime.cut = null;
        }, 2500);
      }, { immediate: true });

      watch(() => [
        S.phase, S.view,
        S.showtime && S.showtime.step,
        S.showtime && S.showtime.cut && S.showtime.cut.act,
        S.elevator && S.elevator.startedAt,
        S.antifraud && S.antifraud.active
      ], () => { if (window.SFX && window.SFX.sync) window.SFX.sync(S); }, { immediate: true });

      const showSeatRoles = computed(() => S.mode === 'party' || S.playMode === 'main');
      const seatRoles = computed(() => {
        const seats = S.partySeats || [];
        const mine = S.playerId;
        return (M.chars || []).filter(x => x.id !== 'dm').map(c => {
          const seat = seats.find(s => s && s.char_id === c.id) || {};
          const owner = seat.player_id || '';
          const mineSeat = owner === mine || S.partyChar === c.id;
          const taken = !!(owner && owner !== mine && seat.is_ai === false);
          let status = 'empty', statusLabel = '可领取';
          if (seat.ai_takeover) { status = 'takeover'; statusLabel = 'AI 接管'; }
          else if (seat.is_ai && owner) { status = 'takeover'; statusLabel = 'AI 接管'; }
          else if (seat.is_ai && !owner) { status = 'ai'; statusLabel = 'AI 补位'; }
          else if (seat.connected === true) { status = mineSeat ? 'mine' : 'online'; statusLabel = mineSeat ? '你的席位 · 在线' : '真人在线'; }
          else if (owner) { status = 'offline'; statusLabel = '暂离'; }
          return Object.assign({}, c, {
            taken: taken,
            mine: mineSeat,
            pending: !!(roomLife.npcPending && roomLife.npcPending === c.id),
            status: status,
            statusLabel: statusLabel
          });
        });
      });
      const seatBookChars = computed(() => {
        const books = S.studioBooks || [];
        const avMap = (window.STUDIO && window.STUDIO.CAST_AVATAR) || {};
        return books.map(b => {
          const id = b.char_id || b.id;
          const c = (M.chars || []).find(x => x.id === id) || {};
          const loc = (b.opening && b.opening.location) || '';
          return {
            char_id: id,
            name: b.name || c.name || '在场者',
            archetype: b.archetype || c.archetype || '',
            you_are: b.you_are || '',
            location: loc,
            avatar: c.avatar || avMap[id] || '/assets/images/bust/char_v587.png'
          };
        });
      });
      const seatRolePack = computed(() => {
        const id = S.partyChar || (S.mode !== "party" ? "investigator" : "");
        return id && window.Booklets && window.Booklets.pack ? window.Booklets.pack(id, 1, { mine: true }) : null;
      });

      /* ---- 灵魂匹配局（赛道：社区连接与兴趣社交）----
       * 3 题单选小测 → 推荐「灵魂同频」角色。纯展示 + 选人标记，
       * 不接 store、不改选人流程（Store.pickPartyChar 原样调用）。
       * 状态存 localStorage（kanshan_soul_quiz_ 前缀）；file:// 直开可能受限，读写全程 try/catch。 */
      const SOUL_QUIZ_KEY = 'kanshan_soul_quiz_result';
      const SOUL_QUESTIONS = [
        { q: '深夜睡不着，你一般陷在哪种状态里？', opts: [
          { t: '刷热榜停不下来，越刷越焦虑，总觉得有热度才有一切', c: 'char_03' },
          { t: '群里从来不说话，只潜水围观，怕一开口就说错', c: 'char_04' },
          { t: '到处点赞提问，逢梗必问「这是什么梗」，新号味十足', c: 'char_08' },
          { t: '目标列了一整页，但没有一个小目标真正闭环', c: 'char_01' }
        ] },
        { q: '你最想表达、却一直没说出口的心声是哪句？', opts: [
          { t: '认真写的东西总没人看见，好像每个字都被折叠了', c: 'char_06' },
          { t: '该争取的一直不敢开口，怕得罪人，只敢写「建议关注」', c: 'char_07' },
          { t: '被杠精抬过一次杠，从此总觉得「我一开口就露怯」', c: 'char_04' },
          { t: '想学的东西收藏了一堆，从来没真正开始学', c: 'char_05' }
        ] },
        { q: '如果今晚必须入座，你会因为什么坐下？', opts: [
          { t: '一打开文档就分心，写两行就去刷手机，日更全靠拖', c: 'char_02' },
          { t: '对最爱的事也提不起劲，像被人从背后抽干了电', c: 'char_06' },
          { t: '越忙越觉得缺的不是时间而是机会，手里永远差一步', c: 'char_03' },
          { t: '想当面问问每个人：为什么真话要藏在心声里？', c: 'char_05' }
        ] }
      ];
      /* 心病一句话：与知识卡 topic_tag 对齐（kc_07 目标 / kc_05 注意力 / kc_02 穷人思维 /
       * kc_03 被动 / kc_06 学习 / kc_01 倦怠 / kc_04 加薪即「不敢开口」；char_08 无绑卡走人设梗） */
      const SOUL_TAGLINES = {
        char_01: '你的心病关键词是「目标」——目标要具体、有期限、有意义，缺一不可。',
        char_02: '你的心病关键词是「注意力」——先试 5 分钟：不管多痛苦，5 分钟总还是可以忍受的。',
        char_03: '你的心病关键词是「穷人思维」——稀缺会俘获注意力，先留出余闲，再谈逆袭。',
        char_04: '你的心病关键词是「被动」——先回忆自己「成功」的时刻，把「我不行」改写成行动。',
        char_05: '你的心病关键词是「学习」——万里之路，难在第一步：所有的进步都来源于尝试。',
        char_06: '你的心病关键词是「倦怠」——认清循环困住我们的机制，是走出倦怠的第一步。',
        char_07: '你的心病关键词是「不敢开口」——一旦标准摆上桌，加薪就不再是赏赐，而是合不合理的问题。',
        char_08: '新号报道！没有绑定的心病卡，只有两个真诚的感叹号——全场的活监控非你莫属。'
      };
      const soulQuiz = Vue.reactive({ open: false, step: 0, picks: [], done: false, result: '' });
      try {
        const saved = JSON.parse(localStorage.getItem(SOUL_QUIZ_KEY) || 'null');
        if (saved && saved.result && SOUL_TAGLINES[saved.result]) { soulQuiz.result = saved.result; soulQuiz.done = true; }
      } catch (e) { }
      const soulOpen = () => {
        soulQuiz.open = true;
        if (soulQuiz.result) { soulQuiz.done = true; }
        else { soulQuiz.step = 0; soulQuiz.picks = []; soulQuiz.done = false; }
      };
      const soulFinish = () => {
        const counts = {};
        SOUL_QUESTIONS.forEach((q, qi) => {
          const pick = soulQuiz.picks[qi];
          if (pick == null || !q.opts[pick]) return;
          const cid = q.opts[pick].c;
          counts[cid] = (counts[cid] || 0) + 1;
        });
        let best = ''; let bestN = -1;
        (M.chars || []).forEach(c => {
          if (!SOUL_QUESTIONS.some(q => q.opts.some(o => o.c === c.id))) return;
          const n = counts[c.id] || 0;
          if (n > bestN) { best = c.id; bestN = n; }
        });
        soulQuiz.result = best;
        try { localStorage.setItem(SOUL_QUIZ_KEY, JSON.stringify({ result: best, at: Date.now() })); } catch (e) { }
        soulQuiz.done = true;
      };
      const soulPick = (i) => {
        soulQuiz.picks[soulQuiz.step] = i;
        if (soulQuiz.step < SOUL_QUESTIONS.length - 1) soulQuiz.step += 1;
        else soulFinish();
      };
      const soulRetake = () => { soulQuiz.step = 0; soulQuiz.picks = []; soulQuiz.done = false; };
      const soulSkip = () => { soulQuiz.open = false; };
      const soulResult = computed(() => {
        const c = (M.chars || []).find(x => x.id === soulQuiz.result);
        if (!c) return null;
        return { id: c.id, name: c.name, archetype: c.archetype, avatar: c.avatar, tagline: SOUL_TAGLINES[c.id] || c.bio };
      });
      /* 入座页「推荐你选 TA」标记：仅单人主模式/房间选人时显示，不拦截 Store.pickPartyChar */
      const soulMatchId = computed(() => (S.phase === 'seat' && showSeatRoles.value && soulQuiz.result) ? soulQuiz.result : '');

      /* ---- 我的剧本架：主菜单选局入口（一句话生成 → 随时回放闭环） ---- */
      const shelfOpen = ref(false);
      const shelfState = ref('idle'); /* idle | loading | ready | offline */
      const shelfItems = ref([]);
      const loadShelf = async () => {
        shelfState.value = 'loading';
        try {
          const r = await fetch('/api/studio');
          if (!r.ok) throw new Error('http ' + r.status);
          const j = await r.json();
          shelfItems.value = (j && j.ok && Array.isArray(j.items)) ? j.items : [];
          shelfState.value = 'ready';
        } catch (e) {
          shelfItems.value = [];
          shelfState.value = 'offline'; /* file:// 直开或服务端未启动：空态，不报错 */
        }
      };
      const shelfToggle = () => {
        shelfOpen.value = !shelfOpen.value;
        if (shelfOpen.value) loadShelf();
      };
      const shelfPlayable = (it) => !!it && !!it.ok && it.status === 'ready';
      const shelfTime = (t) => (t || '').slice(5, 16).replace('T', ' ');
      const shelfPlay = (it) => {
        if (!shelfPlayable(it)) { window.Store.toast('这一本闸门未通过，暂不可开玩——可到创作工作台排查', 'warn'); return; }
        window.Store.playStudio(it.id);
      };

      boot();

      const L = window.Labels;
      return { ai, aiSeats, aiDecision, S, M, L, hostOpen, goalOpen, hostAdvance, taskCard, openTaskCard, booted, bootMsg, settings, leaveAsk, settingsAdv, askLeave, confirmLeave, wsUrl, actName, flawN, kcOwned, erN, navGo, dossierOpen, joinCode, copyShare, achOpen, helpOpen, aboutOpen, apiForm, saveApi, onModelChange, ACH_IMG, elevatorDone, Store: window.Store, VIEWS: window.VIEWS, CUT_LINES, CASE_BRIEF, caseBrief, caseTitle, chapter, menuItems, utilityItems, cutLine, playSkin, showHeat, showKcards, showFlaw, showZans, rail, railOn, prog, pacingHint, dmTasks, dmNext, dmMini, openDmMini, goNextChapter, eng, conn, connText, engineSource, transportSource, recheckEngine, retryConn, guideOpen, replayGuide, guideDone, cutVidErr, audioMuted, toggleAudio, Voice, voiceOut, voiceIn, voiceAuto, toggleVoiceOut, toggleVoiceIn, toggleVoiceAuto, seatBookChars, seatRolePack, showSeatRoles, seatRoles, soulQuiz, SOUL_QUESTIONS, soulOpen, soulPick, soulRetake, soulSkip, soulResult, soulMatchId, VoiceRTC, rtcLive, rtcListen, rtcJoin, rtcLeave, shelfOpen, shelfState, shelfItems, shelfToggle, loadShelf, shelfPlayable, shelfTime, shelfPlay, roomLife, npcPendingName };
    },
    template: `
        <!-- 开场覆盖层：封面 → DM 开场 → 领取侦探证（剧本杀标准流程） -->
        <!-- 主菜单 → 房间 → 人物选择 → 序章视频（剧本杀标准流程） -->
    <div class="opening" :class="'phase-' + S.phase" v-if="S.phase !== 'play'">
      <!-- 主菜单 -->
      <div class="card menu" v-if="S.phase === 'menu'">
        <h1>求真档案局 · 看山失踪夜</h1>
        <p class="sub">知乎黑客松 2026 · AI 原生欢乐阵营机制推理本</p>
        <div class="ai-status-card" :class="{ missing: ai.state === 'missing', ready: ai.state === 'configured' || ai.state === 'success' }" role="status" aria-live="polite">
          <div class="ai-status-head"><strong>{{ ai.label }}</strong><span>{{ ai.provider }}</span></div>
          <p>{{ ai.detail }}</p>
          <p class="ai-playable-note" v-if="ai.state === 'missing'">规则引擎仍可正常裁决；AI 对话未配置时，角色不会生成实时回复。</p>
          <div class="ai-status-actions">
            <button class="btn ghost sm" type="button" @click="recheckEngine">重新检测</button>
            <button class="btn ghost sm" type="button" @click="settings=true; settingsAdv=true">配置 AI</button>
          </div>
        </div>
        <p class="dm-line">周五盘点夜。21:00，首席荣誉侦探<b>刘看山</b>进档案室后失踪。大门横幅亮起——【不出真相，不出此门】。23:00，封控确认，调查开始。</p>
        <section class="menu-primary-actions" aria-label="开始游戏">
          <button v-if="S.hasSave" class="btn-start alt" @click="Store.resumeGame()">继续上次对局 ▸</button>
          <button class="btn-start" @click="Store.chooseMode('solo')">开 始 调 查</button>
        </section>
        <section class="core-loop-card" aria-label="游戏核心循环">
          <div class="core-loop-head"><b>一局怎么玩</b><span>每次行动都让真相更近一步</span></div>
          <div class="core-loop-steps">
            <div class="core-loop-step"><i>1</i><b>搜证</b><span>去现场找线索，拼出时间线</span></div>
            <div class="core-loop-arrow" aria-hidden="true">→</div>
            <div class="core-loop-step"><i>2</i><b>对话</b><span>问角色、听心声，验证矛盾</span></div>
            <div class="core-loop-arrow" aria-hidden="true">→</div>
            <div class="core-loop-step"><i>3</i><b>指认</b><span>用证据投票，解锁不同结局</span></div>
          </div>
        </section>
        <section class="soul-card" aria-label="灵魂匹配局">
          <div class="core-loop-head"><b>灵魂匹配局</b><span>在满是 AI 的房间里，找到说真话的人</span></div>
          <p class="dim tiny">3 道题，测测你和今晚哪位在场者灵魂同频——你的公开人设 vs 你的真实心声，会被 AI 读懂，还是被你看穿？</p>
          <button class="btn ghost sm" type="button" @click="soulOpen">{{ soulResult ? '查看我的灵魂匹配结果 ▸' : '开始 3 题灵魂小测 ▸' }}</button>
        </section>
        <section class="first-play-card">
          <div><b>任务卡已更新</b><span>本幕任务 · 私密提醒 · 整活建议</span></div>
          <p>领取角色后，在「目标卡」查看自己的本幕任务。房间创建者可打开「主持人」工具。</p>
        </section>
        <section class="menu-create-actions" aria-label="创作与剧本">
          <button class="btn-start studio-entry" @click="Store.openStudio()">创作一本新剧本 ▸</button>
          <button class="btn-start alt shelf-entry" @click="shelfToggle">{{ shelfOpen ? '收起我的剧本架 ▴' : '我的剧本架 ▾' }}</button>
        </section>
        <section class="menu-shelf" v-if="shelfOpen" aria-label="我的剧本架">
          <p class="dim tiny" v-if="shelfState === 'loading'">正在拉取剧本架…</p>
          <p class="dim tiny" v-else-if="shelfState === 'offline'">需在线服务端可用后加载剧本架 <a href="#" @click.prevent="loadShelf">重试</a></p>
          <template v-else-if="shelfState === 'ready'">
            <p class="dim tiny" v-if="!shelfItems.length">书架还空着——<a href="#" @click.prevent="Store.openStudio()">去创作工作台用一句话生成你的第一本 ▸</a></p>
            <div class="shelf-list" v-else>
              <button type="button" v-for="it in shelfItems" :key="it.id" class="shelf-item"
                      :class="{ playable: shelfPlayable(it) }" :title="it.id" @click="shelfPlay(it)">
                <b>{{ it.title || '未命名本' }}</b>
                <span class="shelf-meta">
                  <em class="shelf-tag" :class="it.provider === 'main' ? 'ai' : 'mock'">{{ it.provider === 'main' ? 'AI 稿' : '骨架稿' }}</em>
                  <em class="shelf-tag" :class="shelfPlayable(it) ? 'ok' : 'bad'">{{ shelfPlayable(it) ? '可玩' : '闸门未过 · 暂不可玩' }}</em>
                  <em class="shelf-tag dim" v-if="it.created_at">{{ shelfTime(it.created_at) }}</em>
                  <em class="shelf-play" v-if="shelfPlayable(it)">开本 ▸</em>
                </span>
              </button>
            </div>
          </template>
        </section>
        <section class="menu-modes" aria-label="更多玩法">
          <div class="menu-section-head"><b>更多玩法</b><span>短局、联机与挑战</span></div>
          <div class="menu-mode-grid">
            <button class="btn-start alt" @click="Store.chooseMode('daily')"><b>每日挑战</b><small>跟着今日热榜办案</small></button>
            <button class="btn-start alt" @click="Store.chooseMode('quick')"><b>快速局</b><small>跳过破冰，直接搜证</small></button>
          </div>
          <button class="btn-start party-entry" @click="Store.chooseMode('party')">
            <b>房间模式（2-5 人）</b><small>邀请好友 · AI 补位 · 实时同步</small>
          </button>
        </section>
        <section class="menu-judge-entry" aria-label="评委演示线">
          <span><b>评委演示线</b><small>约 20 分钟 · 对照 → 回声 → 法官 → 画像</small></span>
          <button class="btn ghost sm" type="button" @click="Store.startJudgeDemo()">直达对照 ▸</button>
        </section>
        <button class="btn-skip" @click="Store.enterBureau()">跳过登录 · 直接进入（实习侦探证）</button>
        <details class="menu-utility">
          <summary>设置与帮助</summary>
          <div class="menu-sub" aria-label="设置与帮助">
            <button type="button" @click="settings=true">设置</button>
            <button type="button" @click="achOpen=true">成就</button>
            <button type="button" @click="helpOpen=true">玩法说明</button>
            <button type="button" @click="aboutOpen=true">关于</button>
          </div>
        </details>
        <p class="dim tiny menu-version">v4.0 · 求真档案局项目组 · 知乎登录后解锁：真名侦探证 / 知乎头像 / 个性化台词</p>
      </div>

      <!-- 房间模式 -->
      <div class="card" v-else-if="S.phase === 'party'">
        <h1>房间模式</h1>
        <p class="sub">房主创建房间 → 好友输房间码加入 → 各自领取嫌疑人身份（AI 补齐空位）</p>
        <button class="btn-start" :disabled="S.creatingRoom" @click="Store.createRoom()">{{ S.creatingRoom ? '建房中…' : '创 建 房 间' }}</button>
        <div class="room-join">
          <input v-model="joinCode" maxlength="6" placeholder="输入 6 位房间码">
          <button class="btn-start alt" @click="Store.joinRoom(joinCode)">加入房间</button>
        </div>
        <p class="dim tiny" v-if="S.roomFull">{{ L.plain(S.roomFull.detail) }}</p>
        <button class="btn-start alt" v-if="S.roomFull" @click="Store.joinRoom(S.roomFull.code, {spectator:true})">房间已满 · 观战旁听</button>
        <div class="room-share" v-if="S.roomCode">
          <p class="dim tiny">房间码：<b style="font-size:1.4em;letter-spacing:2px;">{{ S.roomCode }}</b></p>
          <p class="dim tiny share-note"><b>同一 WiFi 可直接打开</b>下面的链接；跨网段/公网环境请使用已部署的 HTTPS 地址。</p>
          <div class="room-join">
            <input :value="S.shareUrl" readonly aria-label="房间分享链接" onclick="this.select()" style="flex:1;font-size:12px;">
            <button class="btn-start alt" @click="copyShare">复制链接</button>
          </div>
          <p class="dim tiny">也可以让好友输入 6 位房间码。好友到齐后，各自领取角色，再进入序章。</p>
        </div>
        <button class="btn-skip" @click="Store.chooseMode('solo')">返回单人模式</button>
      </div>

      <!-- 人物选择 / 快本领故事本 -->
      <div class="card" :class="{ 'pb-seat': S.studioBooks && S.studioBooks.length }" v-else-if="S.phase === 'seat'">
        <div class="seat-top-actions">
          <button class="btn ghost sm" type="button" @click="askLeave">返回主菜单</button>
        </div>
        <template v-if="S.studioBooks && S.studioBooks.length">
          <h1>领取今晚的故事本</h1>
          <p class="sub">点开一张角色卡，领取仅你可见的一页任务。确认后进入序章。</p>
          <div class="gallery pb-gallery" :aria-busy="!!S.studioBookLoading">
            <div class="g-card pb-cover" v-for="b in seatBookChars" :key="b.char_id"
                 :class="{ on: S.partyChar === b.char_id, loading: S.studioBookLoading === b.char_id }"
                 :aria-disabled="!!S.studioBookLoading"
                 @click="!S.studioBookLoading && Store.pickStudioChar(b.char_id)">
              <img :src="b.avatar" :alt="b.name">
              <b>{{ b.name }}</b>
              <span>{{ b.archetype }}</span>
              <p class="pb-you">{{ b.you_are }}</p>
              <em v-if="S.studioBookLoading === b.char_id" class="pb-loading">故事本领取中…</em>
            </div>
          </div>
          <p v-if="S.studioBookLoading" class="dim tiny pb-loading-note" role="status" aria-live="polite">
            正在读取「{{ S.studioBookLoading }}」的私密故事本，请稍候；领取完成后即可进入序章。
          </p>
          <p v-else-if="S.studioBookError" class="dim tiny pb-loading-note" role="alert">{{ S.studioBookError }}</p>
          <article class="pb-sheet seat-identity-only" v-if="S.playerBook">
            <header class="pb-hd">
              <span class="pb-tag">角色已领取</span>
              <h2>{{ S.playerBook.name }}</h2>
              <p class="pb-arch" v-if="S.playerBook.archetype">{{ S.playerBook.archetype }}</p>
            </header>
            <section class="pb-sec"><h3>你是谁</h3><p>{{ S.playerBook.you_are }}</p></section>
            <p class="dim tiny">任务、秘密和关系将在进入剧情后逐步解锁。</p>
          </article>
          <button class="btn-start" :disabled="!!S.studioBookLoading || !S.playerBook" @click="Store.startPrologue()">{{ S.studioBookLoading ? '故事本领取中…' : (S.playerBook ? '确 认 · 进 入 序 章 ▸' : '先领取一本故事本') }}</button>
        </template>
        <template v-else>
          <h1>{{ showSeatRoles ? '领取今晚身份' : '选择你的形象' }}</h1>
          <p class="sub" v-if="showSeatRoles">点一名角色入座，读你的闭卷再开玩。阵营只对自己可见，终局才揭晓。</p>
          <p class="sub" v-else>官方 IP 家族 6 选 1（也可自定义调查代号）</p>
          <p class="dim tiny" v-if="!showSeatRoles">单人默认领取《特聘调查员》闭卷：公共案情 + 你的提问清单。</p>
          <div class="pp-daily" v-if="S.playMode==='daily'">今日挑战：把一条热搜词改写成档案局里的衍生谣言，再用知识卡拆穿它。</div>
          <div class="pp-daily" v-if="S.playMode==='quick'">快速局：跳过破冰，直接进入搜证/对质。</div>
          <div v-if="showSeatRoles">
            <div class="soul-seat-entry" style="display:flex;align-items:center;gap:10px;margin:0 0 12px;flex-wrap:wrap;">
              <template v-if="soulResult">
                <span class="rb-chip" style="cursor:default;" :title="'灵魂匹配局推荐：' + soulResult.name">灵魂同频 · {{ soulResult.name }}</span>
                <button class="btn ghost sm" type="button" @click="soulOpen">看匹配结果</button>
              </template>
              <template v-else>
                <span class="dim tiny">不知道坐哪？3 题灵魂小测，在满是 AI 的房间里找到和你同频的人。</span>
                <button class="btn ghost sm" type="button" @click="soulOpen">测一测 ▸</button>
              </template>
            </div>
            <div class="pp-seat-char">
              <button type="button" class="g-card" v-for="c in seatRoles" :key="c.id"
                      :class="{ on: S.partyChar === c.id, taken: c.taken }"
                      :disabled="c.taken" @click="Store.pickPartyChar(c.id)">
                <img :src="c.avatar" :alt="c.name"><b>{{ c.name }}</b>
                <span class="seat-status" :class="'seat-status-' + c.status">{{ c.statusLabel }}</span>
                <em v-if="c.pending" class="seat-npc-pending">AI 补位中…</em>
                <em v-if="soulMatchId === c.id" style="display:block;color:#ffd76a;font-size:11px;font-style:normal;">★ 灵魂同频 · 推荐你选 TA</em>
              </button>
            </div>
            <p class="dim tiny" v-if="S.myFactionHint">{{ S.myFactionHint }}</p>
          </div>
          <p class="sub" v-if="showSeatRoles" style="margin-top:16px;">调查形象（仅头像，不是角色）</p>
          <div class="gallery">
            <div class="g-card" v-for="a in M.dossierAvatars" :key="a.id" :class="{ on: S.playerAvatar === a.src }" @click="Store.setIdentity(null, a.src)">
              <img :src="a.src" :alt="a.name"><b>{{ a.name }}</b>
            </div>
          </div>
          <input v-model="S.playerHeadline" maxlength="20" placeholder="调查代号（例：刚下夜班的调查员）">
          <p class="dm-line" v-if="S.mode === 'party' && S.roomCode">房间码：<b>{{ S.roomCode }}</b> —— 队友就位后一起进入序章。</p>
          <div class="room-join" v-if="S.mode === 'party' && S.shareUrl" style="margin:8px 0 12px;">
            <input :value="S.shareUrl" readonly onclick="this.select()" style="flex:1;font-size:12px;">
            <button class="btn-start alt" @click="copyShare">复制链接</button>
          </div>
          <button class="btn-start" :disabled="(showSeatRoles && !S.partyChar) || !!S.studioBookLoading" @click="Store.startPrologue()">{{ S.studioBookLoading ? '故事本领取中…' : (showSeatRoles && !S.partyChar ? '先点一名角色' : '确 认 · 进 入 序 章 ▸') }}</button>
        </template>
      </div>

      <div class="card" v-else-if="S.phase === 'prologue'">
        <h1>系统提示音</h1>
        <p class="dm-line">{{ M.prologueSteps[S.prologueStep] }}</p>
        <p class="dim tiny">{{ S.prologueStep + 1 }} / {{ M.prologueSteps.length }}</p>
        <button class="btn-start" @click="Store.prologueNext()">{{ S.prologueStep >= M.prologueSteps.length - 1 ? '领取侦探证 · 播放序章 ▸' : '下一句 ▸' }}</button>
        <button class="btn-skip" @click="Store.startVideo()">跳过开场白</button>
      </div>

      <!-- 序章视频 -->
      <div class="video-phase" v-else-if="S.phase === 'video'">
        <video src="/assets/videos/opening.mp4" autoplay playsinline
               @error="Store.introFallback()" @ended="Store.startGame()"></video>
        <button class="btn-skip" @click="Store.startGame()">跳过序章 ▸</button>
      </div>

      <!-- Studio 工作台（与菜单同层 opening） -->
      <div class="card studio-card" v-else-if="S.phase === 'studio'">
        <component :is="VIEWS.studio"></component>
      </div>
      <div class="toast-zone" v-if="S.phase === 'seat' || S.phase === 'studio'">
        <transition-group name="tst">
          <div v-for="t in S.toasts" :key="t.id" class="toast" :class="t.kind">{{ t.text }}</div>
        </transition-group>
      </div>

      <!-- 灵魂匹配局：3 题小测弹层（菜单/入座均可打开，可跳过、可重测，不挡任何既有流程） -->
      <div class="recap-mask" v-if="soulQuiz.open" @click.self="soulSkip">
        <div class="recap-panel soul-panel" role="dialog" aria-modal="true" aria-label="灵魂匹配局">
          <template v-if="!soulQuiz.done">
            <span class="rp-tag mono">灵魂匹配局 · 第 {{ soulQuiz.step + 1 }} / {{ SOUL_QUESTIONS.length }} 题</span>
            <h3>{{ SOUL_QUESTIONS[soulQuiz.step].q }}</h3>
            <div class="soul-opts" style="display:flex;flex-direction:column;gap:8px;margin-top:12px;">
              <button v-for="(o, i) in SOUL_QUESTIONS[soulQuiz.step].opts" :key="i" type="button" class="btn ghost sm" style="text-align:left;"
                      @click="soulPick(i)"><b>{{ 'ABCD'[i] }}.</b> {{ o.t }}</button>
            </div>
          </template>
          <template v-else-if="soulResult">
            <span class="rp-tag mono">灵魂共鸣 · 匹配结果</span>
            <h3>你的灵魂和 TA 同频</h3>
            <div style="display:flex;align-items:center;gap:14px;margin-top:12px;">
              <img :src="soulResult.avatar" :alt="soulResult.name" style="width:72px;height:72px;border-radius:50%;object-fit:cover;">
              <div>
                <b style="font-size:18px;">{{ soulResult.name }}</b>
                <span class="dim" style="display:block;">{{ soulResult.archetype }}</span>
              </div>
            </div>
            <p style="margin:10px 0 4px;">「{{ soulResult.tagline }}」</p>
            <p class="dim tiny">入座后在圆桌对质章解锁 TA 的心声——你的公开人设 vs 你的真实心声，被 AI 读懂，还是被你看穿？</p>
          </template>
          <div class="goal-actions" style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
            <button v-if="soulQuiz.done" class="btn ghost sm" type="button" @click="soulRetake">重测一次</button>
            <button class="btn primary sm" type="button" @click="soulSkip">{{ S.phase === 'seat' ? '跳过，直接入座 ▸' : '先不测了 · 返回' }}</button>
          </div>
        </div>
      </div>
    </div>
<div class="app" v-if="S.phase === 'play' && booted" :class="playSkin">
      <!-- V5 跨章资源栏（30px 常驻顶条）：行动点/热度/破绽/知识卡/碎片/侦探证——玩家唯一的全局视野 -->
      <header class="res-bar">
        <div class="rb-brand" data-tour="hud">
          <img class="rb-logo" src="/assets/images/logo_badge.png" alt="求真档案局">
          <span class="rb-chip act-chip" :title="prog.tag"><b>{{ chapter.name }}</b></span>
          <span class="rb-round mono">R{{ S.round }}</span>
          <span class="rb-chip" v-if="S.playMode==='daily'" title="每日挑战">每日</span>
          <span class="rb-chip" v-if="S.playMode==='quick'" title="快速局">快速局</span>
        </div>
        <div class="rb-stats">
          <span class="rb-chip ap" title="行动点：每轮重置（章配额）"><i>行动点</i><ux-num :value="S.ap + '/' + S.apMax"></ux-num></span>
          <span class="rb-chip pacing-hint" :title="pacingHint">{{ pacingHint }}</span>
          <span class="rb-chip heat" v-if="showHeat" :class="{hot: S.heat>=80}" title="热度（章三主战场）"><i>热度</i><ux-num :value="S.heat"></ux-num></span>
          <span class="rb-chip flaw" v-if="showFlaw" :class="{done: flawN>=5}" title="看山破绽：三章各埋，跨章累积"><i>破绽</i><ux-num :value="flawN + '/5'"></ux-num></span>
          <span class="rb-chip" v-if="showKcards" title="知识卡：章一抽取·章二消费"><i>知识卡</i><ux-num :value="kcOwned + '/10'"></ux-num></span>
          <span class="rb-chip" title="盐言碎片"><i>碎片</i><ux-num :value="S.salt + '/5'"></ux-num></span>
          <span class="rb-chip" v-if="S.dailyTopic && S.dailyTopic.topic" :title="S.dailyTopic.body || ''"><i>今日</i><b>{{ S.dailyTopic.topic }}</b></span>
          <span class="rb-chip zans" v-if="showZans" :class="{on: S.bet && S.bet.open}" title="押注币=赞数（弹幕押注）"><i>赞数</i><ux-num :value="S.zans"></ux-num></span>
          <span class="rb-chip er" :class="{hot: erN>0}" v-if="erN>0" title="急诊红灯：下一轮内对口卡抢救=双倍"><i>红灯</i><b>🚨 {{ erN }}</b></span>
          <span class="rb-chip" v-if="S.pollution && S.pollution.ammo" title="污染对照赢得的辟谣弹药"><i>弹药</i><ux-num :value="S.pollution.ammo"></ux-num></span>
          <span class="rb-chip spect-chip" v-if="roomLife.spectators > 0 || S.isSpectator" title="旁听观战者（有人进入房间时实时+1）"><i>👀</i><b>旁听 {{ roomLife.spectators + (S.isSpectator ? 1 : 0) }}</b></span>
        </div>
        <div class="rb-actions">
          <button v-if="!S.isSpectator" class="rb-btn goal-entry" :class="{on: goalOpen}" @click="openTaskCard" aria-label="我的目标卡">目标卡</button>
          <button v-if="S.isHost" class="rb-btn" :class="{on: hostOpen}" @click="hostOpen=!hostOpen" aria-label="主持人控制台">主持人</button>
          <button class="rb-btn engine-btn" :class="eng.tone" type="button" @click="recheckEngine"
                  :aria-label="'引擎状态：' + eng.label + '。' + L.plain(eng.detail)" :title="L.plain(eng.detail)">
            <i class="eng-dot" aria-hidden="true"></i>
          </button>
          <button class="rb-btn ai-status-button" :class="{good: ai.state==='success'}" type="button"
                @click="settings=true; settingsAdv=true" :title="ai.detail">{{ ai.label }}</button>
          <button class="rb-btn" v-if="S.playerBook" :class="{on: S.bookOpen}" type="button" @click="Store.openMyBook()" aria-label="我的本子">我的本子</button>
          <button class="rb-btn" v-else :class="{on: S.bookletOpen || !!S.bookletForced}" @click="Store.openBooklet()" aria-label="我的剧本">我的剧本</button>
          <button class="rb-btn dossier-btn" :class="{on: !!S.dossier}" @click="dossierOpen=true" aria-label="侦探档案">
            <img v-if="S.dossier" :src="S.dossier.avatar" alt="" class="dossier-mini"><ui-icon v-else name="badge"></ui-icon>
            <span class="rb-hide-sm">{{ S.dossier ? S.dossier.name : '登录' }}</span>
          </button>
          <button class="rb-btn" :class="{on: railOn}" @click="Store.startJudgeLine()" aria-label="评委演示线">评委线</button>
          <details class="rb-more">
            <summary class="rb-btn" title="更多" aria-label="更多工具">⋯</summary>
            <div class="rb-more-pop">
              <button class="rb-btn" v-if="S.playerBook" type="button" @click="Store.openMyBook()">我的本子</button>
              <button class="rb-btn guide-btn" type="button" @click="replayGuide">新手引导</button>
              <button class="rb-btn" type="button" @click="S.demo = !S.demo" :class="{on: S.demo}">演示{{ S.demo ? '开' : '关' }}</button>
              <button class="rb-btn" type="button" @click="settings=true" aria-label="打开设置">设置</button>
            </div>
          </details>
          <button class="rb-btn leave-btn" type="button" title="保存进度并返回主菜单" aria-label="返回主菜单" @click="askLeave">返回</button>
        </div>
      </header>
      <ui-modal v-if="hostOpen && S.isHost" title="主持人 · 流程工具" @close="hostOpen=false">
        <p>第{{ S.act }}幕 · R{{ S.round }} · {{ prog.hint }}</p>
        <div class="goal-actions">
          <button class="btn ghost sm" @click="hostOpen=false; Store.openBooklet()">重读本幕剧本</button>
          <button class="btn primary sm" :disabled="S.busy || !prog.cleared" @click="hostAdvance">{{ S.act >= 3 ? '进入终局指认' : '申请推进下一章' }}</button>
        </div>
      </ui-modal>

      <nav class="demo-rail" v-if="railOn" aria-label="评委线五步">
        <button v-for="(st, i) in rail" :key="st.id" type="button" class="dr-step"
                :class="{ done: st.done, on: S.view === st.view }"
                :title="st.hint" @click="Store.goDemoRail(st.id)">
          <i>{{ i + 1 }}</i><b>{{ st.label }}</b>
        </button>
      </nav>

      <!-- 行动处理中的轻量反馈（≤300ms 级微交互） -->
      <div class="ux-busybar" v-if="S.busy" role="status" aria-live="polite"><i></i><span>正在核对行动结果…</span></div>

      <!-- WS 实时通道：重连 / 断线反馈 -->
      <div class="ux-conn" :class="conn.state" v-if="conn.state === 'reconnecting' || conn.state === 'offline' || conn.state === 'restoring' || conn.state === 'restored'" role="status" aria-live="polite">
        <i class="uxs-spin" v-if="conn.state === 'reconnecting' || conn.state === 'restoring'" aria-hidden="true"></i>
        <span>{{ connText }}</span>
        <button type="button" @click="retryConn" v-if="conn.state !== 'restored'">{{ conn.state === 'offline' && S.mode === 'party' ? '重新入房' : '立即重连' }}</button>
      </div>

      <!-- 房间生命周期提示：AI 演出占位（npc_pending）/ 圆桌流程错误（rt_flow_error） -->
      <div class="room-life-bar" v-if="roomLife.npcPending || roomLife.flowError" role="status" aria-live="polite">
        <span class="rl-err" v-if="roomLife.flowError">⚠ 流程错误：{{ roomLife.flowError }}</span>
        <span class="rl-pending" v-else>⏳ 「{{ npcPendingName }}」的 AI 演出补位中…（确定性联动已结算，台词稍后补上）</span>
      </div>

      <!-- 全局横幅 -->
      <div class="banner-zone">
        <transition-group name="bnr">
          <div v-for="b in S.banners" :key="b.id" class="banner" :class="b.cls">{{ b.text }}</div>
        </transition-group>
      </div>

      <!-- 章节舞台：当前章视图独占全屏（其他章机制不在 DOM） -->
      <main class="stage chapter-stage">
        <section class="next-objective" aria-live="polite" data-tour="objective">
          <button v-if="!S.isSpectator" class="btn primary sm script-stage-entry" @click="Store.openRoleScript()">阅读我的剧本 · 第{{ S.act || 1 }}幕</button>
          <div class="objective-kicker">本章目标 · {{ chapter.tag }}</div>
          <strong>{{ dmNext }}</strong>
          <span v-if="!prog.cleared">完成后即可{{ S.act >= 3 ? '进入终局指认' : '进入下一章' }}</span>
          <span v-else>可以查看本章收获并继续推进剧情</span>
          <div class="dm-task-list" aria-label="DM 分步任务">
            <span v-for="(task, i) in dmTasks" :key="i" :class="{done: task.done}"><i>{{ task.done ? '✓' : (i + 1) }}</i>{{ task.text }}</span>
          </div>
          <div v-if="dmMini" class="dm-mini-prompt"><b>{{ dmMini.title }}</b><span>{{ dmMini.hint }}</span><button class="btn ghost sm" @click="openDmMini">接受 DM 安排 ▸</button></div>
          <div class="objective-progress" role="progressbar" :aria-valuenow="dmProgress" aria-valuemin="0" aria-valuemax="100">
            <i :style="{width: dmProgress + '%'}"></i><span>{{ dmProgress }}% 完成</span>
          </div>
        </section>
        <component :is="S.view === 'ending' ? VIEWS.ending : VIEWS[S.view] || VIEWS.chat" :key="S.view"></component>
      </main>

      <!-- V5 章内动作条：本章机制入口 + 公用机制 + 章末「进入下一章」 -->
      <nav class="act-bar">
        <div class="ab-menus">
          <button v-for="n in menuItems" :key="n.id" class="nav-item" :class="{on: S.view===n.id}" :data-tour="n.id"
                  :aria-label="n.name" :aria-current="S.view===n.id ? 'page' : null" @click="navGo(n.id)">
            <ui-icon :name="n.icon"></ui-icon><span>{{ n.name }}</span>
            <em v-if="n.id==='vote' && flawN>=5" class="nav-badge">DM</em>
          </button>
        </div>
        <details class="ab-tools">
          <summary class="nav-item">更多工具</summary>
          <div class="ab-tools-pop">
            <button v-for="n in utilityItems" :key="n.id" class="nav-item" :class="{on: S.view===n.id}" @click="navGo(n.id)">
              <ui-icon :name="n.icon"></ui-icon><span>{{ n.name }}</span>
            </button>
          </div>
        </details>
        <div class="ab-next" v-if="!S.ended" :title="prog.hint" data-tour="next">
          <span class="ab-hint" v-if="!prog.cleared">{{ prog.hint }}</span>
          <button class="btn act-next" :class="{ready: prog.cleared}" :disabled="S.busy" @click="goNextChapter">
            {{ S.act >= 3 ? '进入终局指认 ▸' : '进入下一章 ▸' }}
          </button>
        </div>
      </nav>

      <!-- V5 章首前情提要（消费 G4 memory_doc 跨幕摘要；Mock 本地兜底） -->
      <div class="recap-mask" v-if="S.recap" @click.self="Store.recapDismiss()">
        <div class="recap-panel">
          <span class="rp-tag mono">前情提要 · RECAP</span>
          <h3>{{ chapter.name }}</h3>
          <p class="rp-text">{{ S.recap.text }}</p>
          <div class="rp-gains">
            <span class="chip gold" v-for="(g, i) in (S.recap.gains || [])" :key="i">{{ L.line(g) }}</span>
          </div>
          <button class="btn act-next ready big" @click="Store.recapDismiss()">开始本章 ▸</button>
        </div>
      </div>

      <!-- Toast -->
      <div class="toast-zone">
        <transition-group name="tst">
          <div v-for="t in S.toasts" :key="t.id" class="toast" :class="t.kind">{{ t.text }}</div>
        </transition-group>
      </div>

      <!-- V4 综艺流程（G2）：案件卷宗页（环节②，开场覆盖层完成后先于此展示） -->
      <div class="st-casefile" v-if="S.showtime && S.showtime.step === 'case_file'">
        <div class="st-cf-inner">
          <header class="st-cf-hd">
            <span class="st-cf-no mono">CASE FILE · NO.0912</span>
            <h2>案件卷宗 · {{ caseTitle }}</h2>
            <span class="st-cf-tag">求真档案局 · {{ S.scenarioId ? '工作台快本' : '机密等级 S' }}</span>
          </header>
          <div class="st-cf-body">
            <div class="st-cf-brief">
              <p v-for="(b, i) in caseBrief" :key="i" :class="{ dm: i === caseBrief.length - 1 }">{{ b }}</p>
            </div>
            <figure class="st-cf-evidence" v-if="!S.scenarioId">
              <img src="/assets/images/ui_chip.png" alt="证物照片：被编辑过的记忆芯片">
              <figcaption><b>证物 A-01 · 被编辑过的记忆芯片</b><span>删除段 21:07–21:15 · 000 号权限</span></figcaption>
            </figure>
            <figure class="st-cf-evidence" v-else>
              <img src="/assets/images/scene_hotfeed.png" alt="快本场景：热搜后台">
              <figcaption><b>快本 · {{ L.packCaption(S.scenarioId, S.studioMeta) }}</b><span>{{ S.studioMeta && S.studioMeta.genre ? S.studioMeta.genre : '试玩档' }}</span></figcaption>
            </figure>
          </div>
          <p class="st-cf-dm">DM（看山系统音）：「{{ S.studioMeta && S.studioMeta.hook ? S.studioMeta.hook.slice(0, 80) + '…' : '卷宗已发。当事人已在圆桌就座——接下来，交给你的提问。' }} 叮。」</p>
          <button class="btn-start" @click="Store.showtimeNext()">翻开卷宗 · 进入圆桌 →</button>
          <button class="btn ghost sm st-cf-leave" type="button" @click="askLeave">返回主菜单</button>
        </div>
      </div>

      <!-- V4 综艺流程（G2）：三幕转场全屏页（act_t1/t2/t3 + DM 幕引言，2.5s 自动过或点击跳过） -->
      <div class="st-actcut" v-if="S.showtime && S.showtime.cut" @click="Store.cutDismiss()">
        <!-- 第一幕用「横幅封锁」动态背景（静音循环），失败降级静态图；二三幕仍用静态图 -->
        <video v-if="S.showtime.cut.act === 1 && !cutVidErr" class="st-ac-img st-ac-vid"
               src="/assets/videos/clue_001_banner_new.mp4" autoplay muted loop playsinline
               @error="cutVidErr = true"></video>
        <img v-else class="st-ac-img" :src="'/assets/images/act_t' + S.showtime.cut.act + '.png'" alt="">
        <div class="st-ac-bar">
          <b>第{{ '一二三'[S.showtime.cut.act - 1] }}幕</b>
          <p>{{ cutLine }}</p>
        </div>
        <span class="st-ac-skip">点击跳过 · 2.5s</span>
      </div>

      <!-- V31：幕间电梯转场 -->
      <elevator-cut v-if="S.elevator" :to="S.elevator.to" @done="elevatorDone" style="position:fixed; inset:0; z-index:90;"></elevator-cut>

      <!-- V31 P2：反诈小剧场（辟谣成功触发） -->
      <antifraud-theater v-if="!S.demo"></antifraud-theater>

      <!-- P3：看山Bot 隐藏语音（集齐 3 袋鱼干解锁） -->
      <fish-voice></fish-voice>

      <!-- 首屏新手引导（单人自助：没有主持人，流程自己讲清楚） -->
      <ux-guide :open="guideOpen" @close="guideDone"></ux-guide>

      <!-- V31：侦探证弹窗（登录后） -->
      <ui-modal v-if="dossierOpen" title="侦探档案 · 特聘侦探证" @close="dossierOpen=false">
        <dossier-card></dossier-card>
      </ui-modal>
    </div>

    <div class="boot-screen" v-else-if="S.phase === 'play' && !booted">
      <img src="/assets/images/logo_badge.png" alt="">
      <h1>求真档案局 · 看山失踪夜</h1>
      <p>{{ bootMsg }}</p>
      <div class="boot-bar"><i></i></div>
    </div>
    <voice-rtc-dock v-if="VoiceRTC"></voice-rtc-dock>
    <!-- 读本与选角、游玩页面同级 -->
      <div class="bk-mask" v-if="!S.isSpectator && ((S.phase === 'play' && S.bookletForced) || S.bookletOpen)" role="dialog" aria-modal="true" aria-label="我的角色剧本" @click.self="Store.bookletDismiss()">
        <div class="bk-panel">
          <span class="rp-tag mono">闭卷 · 仅你可见</span>
          <h3>{{ (S.bookletPack && S.bookletPack.name) || '特聘调查员' }}</h3>
          <button class="btn ghost sm script-close" aria-label="关闭我的剧本" @click="Store.bookletDismiss()">关闭</button>
          <p class="bk-meta" v-if="S.bookletPack">{{ S.bookletPack.public_title }} · 已开封 {{ (S.bookletPack.unlocked || []).map(k => L.cover(k)).join(' / ') }}<template v-if="S.bookletPack.faction_label"> · {{ S.bookletPack.faction_label }}</template></p>
          <div class="bk-public" v-if="S.bookletPack && S.bookletPack.public">
            <b>公共剧本</b>
            <p v-for="(p, i) in S.bookletPack.public.pages" :key="'p'+i">{{ L.line(p) }}</p>
          </div>
          <div class="bk-cover" v-for="k in (S.bookletPack && S.bookletPack.unlocked) || []" :key="k" :class="{ fresh: S.bookletForced === k }">
            <b>{{ S.bookletPack.covers[k] && S.bookletPack.covers[k].title }}</b>
            <h4>你是谁</h4><p>{{ S.bookletPack.covers[k] && S.bookletPack.covers[k].you_are }}</p>
            <h4>当晚经历</h4><p>{{ S.bookletPack.covers[k] && S.bookletPack.covers[k].tonight }}</p>
            <p class="bk-task">任务：{{ S.bookletPack.covers[k] && S.bookletPack.covers[k].task }}</p>
            <p v-if="(S.bookletPack.covers[k].milestones || []).length" class="bk-task">本幕行动目标</p>
            <ul v-if="(S.bookletPack.covers[k].milestones || []).length" class="bk-milestones">
              <li v-for="(m, i) in S.bookletPack.covers[k].milestones" :key="k+i">{{ m }}</li>
            </ul>
            <p class="bk-ban">不能说：{{ S.bookletPack.covers[k] && S.bookletPack.covers[k].never_say }}</p>
            <h4 v-if="(S.bookletPack.covers[k].impressions || []).length">人物关系</h4>
            <p v-for="(r,i) in S.bookletPack.covers[k].impressions || []" :key="'relation'+k+i">{{ r.who }}：{{ r.note }}</p>
          </div>
          <button class="btn act-next ready big" @click="Store.bookletDismiss()">{{ S.bookletForced ? '收起闭卷 · 开始本章 ▸' : '收起' }}</button>
        </div>
      </div>
      <div class="pb-mask" v-if="S.bookOpen && S.playerBook" @click.self="Store.closeMyBook()">
        <article class="pb-sheet pb-sheet-modal">
          <header class="pb-hd">
            <span class="pb-tag">我的本子 · 只读</span>
            <h2>{{ S.playerBook.name }}</h2>
            <p class="pb-arch" v-if="S.playerBook.archetype">{{ S.playerBook.archetype }}</p>
          </header>
          <section class="pb-sec">
            <h3>你是谁</h3>
            <p>{{ S.playerBook.you_are }}</p>
            <p v-if="S.playerBook.situation">{{ S.playerBook.situation }}</p>
          </section>
          <section class="pb-sec">
            <h3>你的任务</h3>
            <ul><li v-for="(g, i) in (S.playerBook.goals || [])" :key="'pg'+i">{{ L.line(g) }}</li></ul>
            <p v-if="Store.currentRoleGoals().length" class="pb-sub">本幕行动目标</p>
            <ul v-if="Store.currentRoleGoals().length" class="bk-milestones"><li v-for="(m, i) in Store.currentRoleGoals()" :key="'pmilestone'+i">{{ L.line(m) }}</li></ul>
          </section>
          <section class="pb-sec">
            <h3>你掌握的公开信息</h3>
            <ul><li v-for="(f, i) in (S.playerBook.known_facts || [])" :key="'pk'+i">{{ L.line(f) }}</li></ul>
          </section>
          <section class="pb-sec">
            <h3>你隐瞒的事</h3>
            <ul><li v-for="(s, i) in (S.playerBook.secrets || [])" :key="'ps'+i">{{ L.line(s) }}</li></ul>
            <p class="pb-sub" v-if="(S.playerBook.must_not_say || []).length">绝对不能先开口的</p>
            <ul><li v-for="(s, i) in (S.playerBook.must_not_say || [])" :key="'pm'+i">{{ L.line(s) }}</li></ul>
          </section>
          <section class="pb-sec">
            <h3>开局提示</h3>
            <ul>
              <li v-if="S.playerBook.opening && S.playerBook.opening.time">当前时间：{{ S.playerBook.opening.time }}</li>
              <li v-if="S.playerBook.opening && S.playerBook.opening.location">你所在的场景：{{ S.playerBook.opening.location }}</li>
              <li v-if="S.playerBook.opening && S.playerBook.opening.first_step">建议第一步：{{ S.playerBook.opening.first_step }}</li>
            </ul>
          </section>
          <section class="pb-sec" v-if="(S.playerBook.relations || []).length">
            <h3>关系</h3>
            <ul><li v-for="(r, i) in S.playerBook.relations" :key="'pr'+i"><b>{{ r.name || L.who(r.char_id) }}</b>：{{ L.line(r.hint) }}</li></ul>
          </section>
          <p class="pb-close-hint">点击遮罩关闭</p>
        </article>
      </div>
    <!-- 设置（菜单与对局共用，勿挂在 .app 内） -->
    <ui-modal v-if="settings" title="设置" @close="settings=false">
      <div class="settings">
        <div class="cd-row" v-if="S.phase === 'play'"><span class="lbl">对局</span>
          <div class="set-play-actions">
            <button class="btn primary sm" type="button" @click="askLeave">返回主菜单</button>
            <button class="btn ghost sm" type="button" @click="settings=false; helpOpen=true">玩法说明</button>
            <button class="btn ghost sm" type="button" @click="settings=false; replayGuide()">新手引导</button>
          </div></div>
        <div class="cd-row"><span class="lbl">音频</span>
          <span class="chip" :class="{good: !audioMuted}">{{ audioMuted ? '已静音' : '已开启' }}</span>
          <button class="btn ghost sm" @click="toggleAudio">{{ audioMuted ? '打开声音' : '一键静音' }}</button></div>
        <div class="cd-row" v-if="Voice"><span class="lbl">听台词</span>
          <span class="chip" :class="{good: voiceOut && !audioMuted}">{{ !voiceOut ? '关闭' : (audioMuted ? '已静音' : '开启') }}</span>
          <button class="btn ghost sm" @click="toggleVoiceOut">{{ voiceOut ? '关闭播报' : '开启播报' }}</button></div>
        <div class="cd-row" v-if="Voice"><span class="lbl">语音输入</span>
          <div>
            <span class="chip" :class="{good: voiceIn}">{{ voiceIn ? '开启' : '关闭' }}</span>
            <button class="btn ghost sm" @click="toggleVoiceIn">{{ voiceIn ? '关闭麦克风' : '开启麦克风' }}</button>
            <button class="btn ghost sm" :disabled="!voiceIn" @click="toggleVoiceAuto">{{ voiceAuto ? '识别后自动发送' : '识别后填框确认' }}</button>
          </div></div>
        <div class="cd-row" v-if="VoiceRTC && S.mode==='party' && S.sessionId && (S.phase==='play' || S.phase==='seat' || S.phase==='party')"><span class="lbl">房间对讲</span>
          <div>
            <span class="chip" :class="{good: rtcLive}">{{ rtcLive ? (rtcListen ? '收听中' : '通话中') : '未加入' }}</span>
            <button class="btn ghost sm" v-if="!rtcLive" type="button" @click="rtcJoin">{{ S.isSpectator ? '加入收听' : '加入对讲' }}</button>
            <button class="btn ghost sm" v-else type="button" @click="rtcLeave">离开对讲</button>
            <p class="dim tiny">真人之间说话；对 NPC 仍用圆桌麦。文字私聊保留，不对讲 1:1。</p>
          </div></div>
        <div class="cd-row"><span class="lbl">演示模式</span>
          <div><span class="chip" :class="{good: S.demo}">{{ S.demo ? '开启（功能全解锁 + 跳幕入口）' : '关闭' }}</span>
          <button class="btn ghost sm" @click="S.demo=!S.demo">切换</button>
          <button class="btn primary sm" @click="settings=false; Store.startJudgeDemo()">开评委线（20 分钟）</button></div></div>
        <div class="cd-row"><span class="lbl">存档</span>
          <div><span class="dim">自动存档于本机。返回主菜单后可继续上次对局。</span>
          <button class="btn danger sm" @click="Store.reset()">清档重开</button></div></div>
        <details class="set-adv" :open="settingsAdv">
          <summary @click.prevent="settingsAdv=!settingsAdv">高级 · 引擎与传输</summary>
          <div class="cd-row"><span class="lbl">裁决来源</span>
            <span class="chip" :class="{good: eng.probe === 'ok'}">{{ eng.label }}</span>
            <button class="btn ghost sm" @click="recheckEngine">重新检测</button></div>
          <div class="cd-row"><span class="lbl">健康说明</span><span class="dim">{{ L.plain(eng.detail) }}</span></div>
          <div class="cd-row"><span class="lbl">NPC AI</span><span class="chip" :class="{good: ai.state==='success'}">{{ ai.label }}</span>
            <span class="dim">{{ ai.provider }} · {{ L.plain(ai.detail) }}</span></div>
          <div class="cd-row" v-if="aiDecision"><span class="lbl">最近 AI 行动</span>
            <span class="chip">{{ L.who(aiDecision.role) }} · {{ aiDecision.action }}</span>
            <span class="dim">{{ aiDecision.reason || '按当前阶段规划' }}<template v-if="aiDecision.latency_ms"> · {{ aiDecision.latency_ms }}ms</template></span></div>
          <div class="cd-row" v-if="aiSeats.length"><span class="lbl">席位控制</span>
            <span class="chip" v-for="seat in aiSeats" :key="seat.char_id">{{ seat.name }}：{{ seat.controller }}</span></div>
          <div class="cd-row"><span class="lbl">传输层</span>
            <span class="chip" :class="{ warn: S.netKind !== 'ws' }">{{ transportSource }}</span>
            <span class="chip" v-if="conn.state === 'offline' || conn.state === 'reconnecting'">{{ connText }}</span></div>
          <div class="cd-row"><span class="lbl">会话</span><span>{{ L.session(S.sessionId) }}</span></div>
          <div class="cd-row"><span class="lbl">WS 对接</span>
            <div class="kw-input">
              <input v-model="wsUrl" placeholder="实时通道地址（如 ws://192.168.1.5:8000/ws/）" />
              <button class="btn primary" @click="location.href = location.pathname + (wsUrl ? '?ws=' + encodeURIComponent(wsUrl) : '')">重连</button>
            </div>
            <p class="dim">实时通道未接通时 AI 对话不可用（不回退本地演示），可在此填地址后重连。</p>
          </div>
          <div class="cd-row"><span class="lbl">API 接入</span>
            <div class="api-grid">
            <label>知乎 API Base<input v-model="apiForm.llmBase" placeholder="https://developer.zhihu.com/v1"></label>
              <label>LLM Key<input v-model="apiForm.llmKey" type="password" placeholder="sk-…（仅存本机）"></label>
            <label>AI 模型<select v-model="apiForm.llmModel" @change="onModelChange">
              <optgroup label="知乎直答（默认，无需填 Key）">
              <option value="zhida-agent">zhida-agent · 智能思考（默认）</option>
              <option value="zhida-fast-1p5">zhida-fast-1p5 · 快速回答</option>
              <option value="zhida-thinking-1p5">zhida-thinking-1p5 · 深度思考</option>
              </optgroup>
              <optgroup label="DeepSeek（需填 API Key）">
              <option value="deepseek-v4-flash">deepseek-v4-flash</option>
              <option value="deepseek-chat">deepseek-chat · V3 兼容</option>
              </optgroup>
            </select></label>
              <label>知乎 Secret<input v-model="apiForm.zhihuSecret" type="password" placeholder="Access Secret（可选）"></label>
              <button class="btn primary sm" @click="saveApi">保存 API 配置</button>
              <p class="dim tiny">仅存本机；建局时传入服务端内存，密钥不落盘。</p>
            </div></div>
        </details>
      </div>
    </ui-modal>
    <ui-modal v-if="leaveAsk" title="返回主菜单" @close="leaveAsk=false">
      <div class="leave-ask">
        <p>当前进度会自动保存。回到主菜单后，点「继续上次对局」即可接着查。</p>
        <p class="dim" v-if="S.mode === 'party' && S.roomCode">房间码 {{ S.roomCode }} 会保留，可再连回同一桌。</p>
        <div class="set-play-actions">
          <button class="btn primary" type="button" @click="confirmLeave">保存并返回</button>
          <button class="btn ghost" type="button" @click="leaveAsk=false">继续调查</button>
        </div>
      </div>
    </ui-modal>

    <!-- 成就墙 -->
    <ui-modal v-if="achOpen" title="成就墙 · 侦探徽章" @close="achOpen=false">
      <div class="ach-wall">
        <div v-for="b in M.badgeDefs" :key="b.id" class="ach-item">
          <img v-if="ACH_IMG[b.name]" :src="ACH_IMG[b.name]" :alt="b.name">
          <span v-else class="ach-emoji">{{ b.icon }}</span>
          <b>{{ b.name }}</b><span class="dim">{{ b.desc }}</span>
        </div>
      </div>
    </ui-modal>

    <!-- 玩法说明 -->
    <ui-modal v-if="helpOpen" title="玩法说明" @close="helpOpen=false">
      <div class="help-body">
        <p class="dim">第一次来？建议先看一遍 <button class="btn ghost sm" @click="helpOpen=false; replayGuide()">6 步新手引导 ▸</button></p>
        <p><b>目标</b>：找回失踪的看山，还原档案局之夜的真相。</p>
        <p><b>第一章 搜证</b>：场景图选地点 → 输入关键词搜证（1AP）；搜证附带抽知识卡。</p>
        <p><b>第二章 对质</b>：记忆修复偷听心声；知识开导；<b>污染对照</b>（原文 vs 水军改写，圈出植入段）。</p>
        <p><b>第三章 舆论</b>：热搜面板买热搜/辟谣（引错卡被群嘲）。对照弹药在辟谣成功时再压热度。</p>
        <p><b>终局</b>：回声自证（你说过的话）→ 说服会被热度带偏的 AI 法官 → ≥2 张证据卡指认；集齐 5 破绽可「指认 DM」。通关出五维求真画像。</p>
        <p><b>评委线</b>：顶栏「评委线」按 对照→圆桌留档→回声→法官→画像 走完主创新，约 20 分钟。</p>
        <p class="dim">行动点每轮 3 点；底部动作条可切场景地图/知识卡/记忆修复/指认。</p>
      </div>
    </ui-modal>

    <!-- 关于 -->
    <ui-modal v-if="goalOpen && !S.isSpectator" title="我的目标卡 · 仅你可见" @close="goalOpen=false">
      <div class="goal-title">{{ taskCard.name }} · 第{{ S.act || 1 }}幕</div>
      <div class="goal-row faction"><b>阵营 / 立场提示</b><span>{{ taskCard.faction }}</span></div>
      <div class="goal-row"><b>本幕任务</b><span>{{ taskCard.personal }}</span></div>
      <ul v-if="taskCard.milestones.length" class="bk-milestones"><li v-for="(m, i) in taskCard.milestones" :key="i">{{ L.line(m) }}</li></ul>
      <div v-if="taskCard.secret" class="goal-row"><b>私密提醒</b><span>{{ taskCard.secret }}</span></div>
      <div class="goal-row fun"><b>整活建议</b><span>{{ taskCard.fun }}</span></div>
      <button class="btn primary" @click="goalOpen=false; Store.openRoleScript()">阅读完整的已开封剧本</button>
      <div v-if="S.phase === 'play'" class="goal-actions">
        <button v-for="a in taskCard.actions" :key="a.view" class="btn primary sm" @click="goalOpen=false; navGo(a.view)">{{ a.name }}</button>
      </div>
      <p class="goal-hint">任务来自当前已开封剧本；整活建议不自动计分。</p>
    </ui-modal>
    <ui-modal v-if="aboutOpen" title="关于" @close="aboutOpen=false">
      <div class="help-body">
        <p><b>《求真档案局 · 看山失踪夜》</b> v4.0</p>
        <p>知乎黑客松 2026 校园新锐季 · 跨次元游乐场赛道作品</p>
        <p>AI 原生欢乐阵营机制推理本 —— 规则引擎裁决 + AI 演出</p>
        <p class="dim">刘看山形象 © 知乎 · 剧情设定致敬盐言故事（灯灯/凉风有信/反骨/六酒）· 知识卡引用知乎知识（潘幸知/曾旻 等）</p>
      </div>
    </ui-modal>
`
  };

  const app = createApp(App);
  window.UI.install(app);
  if (window.Voice && window.Voice.install) window.Voice.install(app);
  if (window.VoiceRTC && window.VoiceRTC.install) window.VoiceRTC.install(app);
  if (window.UX && window.UX.install) window.UX.install(app);   // 体验层组件（ux-state / ux-num / ux-guide）
  app.component('boss-reveal', window.VIEWS['boss-reveal']);
  if (window.VIEWS['antifraud-theater']) app.component('antifraud-theater', window.VIEWS['antifraud-theater']);
  if (window.VIEWS['dossier-card']) app.component('dossier-card', window.VIEWS['dossier-card']);
  if (window.VIEWS['truth-radar']) app.component('truth-radar', window.VIEWS['truth-radar']);
  if (window.MinisInstall) window.MinisInstall(app);   // minis 宿主（#/mini/{id}）
  if (window.UI.comps && window.UI.comps['fish-voice']) app.component('fish-voice', window.UI.comps['fish-voice']);
  app.config.errorHandler = (err, vm, info) => console.error('[vue]', err, info);
  window.APP_DEF = App;
  // 浏览器环境挂载；无 DOM 的测试环境只暴露定义
  if (typeof document !== 'undefined' && document.getElementById('app')) {
    app.mount('#app');
  }
  window.VIEWS_MAP = Object.keys(CHAPTER_MENUS).reduce((m, a) => m.concat(CHAPTER_MENUS[a]), []).concat(COMMON_MENUS);
})();

