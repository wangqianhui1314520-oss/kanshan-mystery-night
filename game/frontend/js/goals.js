/* Project only the current player's already-unlocked booklet into the task panel. */
(function () {
  const FUN = {
    char_01: '用「先问是不是」开场，向一位玩家追问一次证据出处。',
    char_02: '用章回体为本轮讨论起一个标题。',
    char_03: '给本轮最离谱的推理起一个 #热搜标题#。',
    char_04: '用「我好像看到过」复述一条已公开线索，请别人核对。',
    char_05: '用机器人口吻指出一次发言中的逻辑跳跃。',
    char_06: '在发言末尾加上「该发言已被折叠」，请别人替你复述。',
    char_07: '用官方公告口吻总结本轮争议。',
    char_08: '用新用户的口吻向全桌提出一个看似简单的问题。'
  };
  function project(s) {
    if (s.isSpectator) return { name: '观战席', faction: '旁听公共讨论', personal: '观战席没有私密任务。', secret: '', fun: '', actions: [], milestones: [] };
    const custom = s.scenarioId && s.scenarioId !== 'kanshan';
    const book = custom ? (s.playerBook || {}) : null;
    const pack = custom ? {} : (s.bookletPack || {});
    const key = ['A', 'B', 'C'][Math.max(0, Math.min(2, (Number(s.act) || 1) - 1))];
    const cover = (pack.unlocked || []).includes(key) ? (pack.covers || {})[key] || {} : {};
    const role = s.partyChar || s.bookletRole || 'investigator';
    const goals = book ? (Array.isArray(book.goals) ? book.goals : []) : (cover.milestones || []);
    return {
      name: book ? book.name || '待领取角色' : pack.name || '待领取角色',
      faction: (book && book.faction_goal) || pack.faction_label || s.myFactionHint || '阵营尚未公开，以自己的已开封剧本为准。',
      personal: (book && (book.personal_goal || goals.join('；'))) || cover.task || '先领取角色并打开本幕剧本，任务会在这里同步。',
      secret: book ? (Array.isArray(book.secrets) ? book.secrets.join('；') : '') : cover.never_say || '',
      fun: (book && book.fun_goal) || (custom ? '用一句话为本轮讨论起个标题。' : FUN[role] || '用一句话为本轮推理起个标题，请全桌点评。'),
      milestones: goals,
      actions: s.act < 2 ? [{ view: 'chat', name: '圆桌提问' }, { view: 'map', name: '现场搜证' }] : s.act < 3 ? [{ view: 'chat', name: '追问证词' }, { view: 'memory', name: '记忆修复' }] : [{ view: 'hotfeed', name: '热搜博弈' }, { view: 'vote', name: '终局指认' }]
    };
  }
  window.GoalCards = { project };
})();
