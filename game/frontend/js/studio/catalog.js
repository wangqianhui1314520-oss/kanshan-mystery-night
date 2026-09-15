/* 工作台目录：步骤、本型、机制、小游戏。视图只读，不写案情。 */
(function (g) {
  const C = g.STUDIO = g.STUDIO || {};

  C.PRESETS = [
    '全员被锁在 24 小时热榜机房里，热搜日志缺了七分钟',
    '盐言房间出不去，横幅写着不出真相不出此门'
  ];

  /* 生产工作台 · 七阶段制作流程（第一性原理：真相先行 → 信息切割 → 闭环验证） */
  C.STEPS = [
    { id: 's1', no: '01', title: '立项', why: '行业第一步 · 选题立项：一句话钩子（可拉知乎热榜议题）+ 定本型基调 + 封局设定（时间盒/空间/出不去的规则）。' },
    { id: 's2', no: '02', title: '真相', why: '行业第二步 · 设计总纲：AI 先写真相草案——表面故事、真凶、动机、手法与真相树。你编辑确认后才能进角色（真相先行铁律）。' },
    { id: 's3', no: '03', title: '角色', why: '行业第三步 · 角色与信息分配：AI 按你锁定的真相写 4 个嫌疑人（每人自带秘密、伪证与记忆版本），名字与人设由你改写。' },
    { id: 's4', no: '04', title: '幕次', why: '行业第四五步 · 线索编排与幕次：AI 把真相切碎成线索、按三幕发放（破冰→搜证→指认），你调节奏、必揭露点与反转。' },
    { id: 's5', no: '05', title: '机制', why: '行业第五步 · 机制与氛围：搜证/记忆/舆论/开导/指认等玩法开关、小游戏挂载与口径。' },
    { id: 's6', no: '06', title: '过闸', why: '行业第六步 · 编译过闸：三段终稿编译成剧本包，结构闸门（4 人/6 地/12 证）+ 叙事闸门（V1 时间线/V2 可达性/V3 伪证）全绿才可开玩。' },
    { id: 's7', no: '07', title: '开局', why: '终审交付：读海报、角色、证据与导演视角，一键开本进序章。' }
  ];

  C.PACK_TYPES = [
    { id: 'fun_mech', name: '欢乐机制本', blurb: '规则好玩，搜证和热搜一起转。', mood: 'comedy', public_camps: false, tone: '欢乐外壳 + 信息操纵',
      modules: { hotfeed: true, memory: true, counsel: true, kcards: true, comedy_search: true, bet: true, headline: true, stealth: true, puzzle: true, antifraud: true, evidence: true, pollution: true, inner_boss: false },
      minis: ['heart', 'refute3', 'runner', 'badge'] },
    { id: 'hard_logic', name: '硬核推理本', blurb: '少综艺，多证据链。', mood: 'grim', public_camps: false, tone: '冷硬推理',
      modules: { hotfeed: false, memory: true, counsel: false, kcards: true, comedy_search: false, bet: false, headline: false, stealth: true, puzzle: true, antifraud: false, evidence: true, pollution: false, inner_boss: false },
      minis: ['heart'] },
    { id: 'faction', name: '阵营对抗本', blurb: '两边赢法不同，阵营名公开。', mood: 'variety', public_camps: true, tone: '阵营拉扯',
      modules: { hotfeed: true, memory: true, counsel: true, kcards: true, comedy_search: true, bet: true, headline: true, stealth: true, puzzle: true, antifraud: true, evidence: true, pollution: true, inner_boss: false },
      minis: ['refute3', 'heart'] },
    { id: 'emotion', name: '情感本', blurb: '开导、心声、关系比机关更重要。', mood: 'grim', public_camps: false, tone: '克制伤感',
      modules: { hotfeed: false, memory: true, counsel: true, kcards: true, comedy_search: false, bet: false, headline: false, stealth: false, puzzle: true, antifraud: false, evidence: true, pollution: false, inner_boss: false },
      minis: ['heart'] },
    { id: 'horror', name: '恐怖本', blurb: '锁门、空档、耳语。关掉笑点和热搜狂欢。', mood: 'horror', public_camps: false, tone: '封闭空间恐怖',
      modules: { hotfeed: false, memory: true, counsel: true, kcards: false, comedy_search: false, bet: false, headline: false, stealth: true, puzzle: true, antifraud: false, evidence: true, pollution: false, inner_boss: true },
      minis: ['heart'] },
    { id: 'variety', name: '综艺本', blurb: '热搜、押注、小游戏全开。', mood: 'variety', public_camps: false, tone: '综艺外壳',
      modules: { hotfeed: true, memory: true, counsel: true, kcards: true, comedy_search: true, bet: true, headline: true, stealth: true, puzzle: true, antifraud: true, evidence: true, pollution: true, inner_boss: false },
      minis: ['runner', 'heart', 'refute3', 'badge'] },
    { id: 'immerse', name: '沉浸本', blurb: '少 HUD，多圆桌和现场。', mood: 'grim', public_camps: false, tone: '沉浸封闭',
      modules: { hotfeed: false, memory: true, counsel: true, kcards: false, comedy_search: false, bet: false, headline: false, stealth: false, puzzle: false, antifraud: false, evidence: true, pollution: false, inner_boss: false },
      minis: [] }
  ];

  C.MOODS = [
    { id: 'comedy', name: '欢乐', hint: '错位腔调、搜错彩蛋、一眼假热搜' },
    { id: 'horror', name: '恐怖', hint: '灯灭、空档、耳语、不该搜到的东西' },
    { id: 'variety', name: '综艺', hint: '热搜、押注、镜头感和群嘲' },
    { id: 'grim', name: '冷硬', hint: '少玩笑，多对质和证据链' }
  ];

  C.CORE_MECHS = [
    { key: 'search', name: '现场搜证', play: '地图', hint: '引擎必开，破冰结束后才能搜。', lock: true },
    { key: 'chat', name: '圆桌对话', play: '聊天', hint: '线上本的社交核。', lock: true },
    { key: 'vote', name: '终局指认', play: '投票', hint: '终局舞台，不能关。', lock: true }
  ];

  C.MECHS = [
    { key: 'hotfeed', name: '热搜舆论', play: '第三章热搜', hint: '假帖、热度、辟谣。' },
    { key: 'memory', name: '记忆修复', play: '第二章记忆台', hint: '口供与心声矛盾。' },
    { key: 'counsel', name: '开导策反', play: '心晴诊室', hint: '把可策反位拉过来。' },
    { key: 'kcards', name: '知识卡', play: '知识弹药', hint: '只复用真知乎作者卡。' },
    { key: 'evidence', name: '证据拼图', play: '证据链', hint: '手连线索对真相节点。' },
    { key: 'pollution', name: '污染对照', play: '第二章对照', hint: '信息操纵对照题。' },
    { key: 'bet', name: '弹幕押注', play: '顶栏赞数', hint: '每轮开盘押对错。' },
    { key: 'headline', name: '头条竞标', play: '热搜头条', hint: '用赞数竞话题。' },
    { key: 'stealth', name: '暗拍', play: '搜证技能', hint: '拍照不入证物袋。' },
    { key: 'puzzle', name: '记忆拼图', play: '技能小关', hint: '攒篡改点后解锁。' },
    { key: 'antifraud', name: '反诈剧场', play: '复盘加练', hint: '三幕判断题。' },
    { key: 'comedy_search', name: '搜错彩蛋', play: '搜证走偏', hint: '搜错仍给喜剧反馈。' },
    { key: 'inner_boss', name: '里层 Boss', play: '默认关', hint: '快本可不展开。' }
  ];

  C.MINIS = [
    { id: 'runner', name: '看山快跑', where: '结算 / 复盘', hint: '词库跑酷，放松用。' },
    { id: 'heart', name: '心声窃听器', where: '第二章热身', hint: '听哪句是心声。' },
    { id: 'refute3', name: '谣言消消乐', where: '复盘 / 辟谣', hint: '消假帖词对。' },
    { id: 'badge', name: '侦探证每日抽', where: '档案页', hint: '欢乐警衔。' }
  ];

  C.ACT_META = {
    act1: { stage: '破冰', verbs: '只许对话，再推进', ap: '6 点行动', lock: '只许圆桌，禁止搜证' },
    act2: { stage: '搜证', verbs: '搜证 / 修记忆 / 开导', ap: '9 点行动', lock: '开门搜证与对质' },
    act3: { stage: '指认', verbs: '辟谣 / 投票', ap: '3 点行动', lock: '对质后指认' }
  };

  C.CAST_AVATAR = {
    char_01: '/assets/images/bust/char_liuliangjiang.png',
    char_02: '/assets/images/bust/char_lurenjia.png',
    char_03: '/assets/images/bust/char_zhizhizhe.png',
    char_04: '/assets/images/bust/char_yanzhijun.png'
  };

  C.emptyMods = function () {
    return { hotfeed: true, memory: true, counsel: true, kcards: true, inner_boss: false, comedy_search: true, bet: true, headline: true, stealth: true, puzzle: true, antifraud: true, evidence: true, pollution: true };
  };
})(typeof window !== 'undefined' ? window : globalThis);
