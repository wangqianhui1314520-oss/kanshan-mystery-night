/* ============================================================
 * assets.js —— 前端美术注册表（胸像 / 静帧 / 线索证物 / 知识卡话题色）
 * 路径全部落在 /assets/*，禁止外链。
 * ============================================================ */
window.ASSETS = (function () {
  const IMG = '/assets/images/';
  const BUST = '/assets/images/bust/';
  const STILL = '/assets/images/still/';
  const HOLO = IMG + 'dm_kanshan_holo.png';
  const HOLO_BUST = BUST + 'dm_kanshan_holo.png';
  const FISH = IMG + 'icon_fish.png';
  const TRUE_KS = '/assets/official/kanshan/kanshan_portrait.png';

  const CARD = '/assets/images/card/';
  const TOPIC = {
    '流量': { hue: 'flame', mark: '热', emblem: CARD + 'kc_flame.png' },
    '表达': { hue: 'voice', mark: '言', emblem: CARD + 'kc_voice.png' },
    '职场': { hue: 'work', mark: '职', emblem: CARD + 'kc_work.png' },
    '专注': { hue: 'focus', mark: '注', emblem: CARD + 'kc_focus.png' },
    '学习': { hue: 'learn', mark: '学', emblem: CARD + 'kc_learn.png' },
    '倦怠': { hue: 'burn', mark: '倦', emblem: CARD + 'kc_burn.png' },
    '目标': { hue: 'goal', mark: '标', emblem: CARD + 'kc_goal.png' },
    '边界': { hue: 'bound', mark: '界', emblem: CARD + 'kc_bound.png' },
    '规划': { hue: 'plan', mark: '局', emblem: CARD + 'kc_plan.png' }
  };

  const TAG_THUMB = {
    '鱼干': FISH,
    '投放': IMG + 'icon_rumor.png',
    '话题': IMG + 'icon_rumor.png',
    '账号': IMG + 'icon_rumor.png',
    '芯片': IMG + 'ui_chip.png',
    '日志': IMG + 'ui_chip.png',
    '监控': IMG + 'scene_monitor.png',
    '删除': IMG + 'scene_monitor.png',
    '门禁': IMG + 'scene_reception.png',
    '访客': IMG + 'scene_reception.png',
    '值班': IMG + 'scene_reception.png',
    '奶茶': IMG + 'scene_teahouse.png',
    '打卡': IMG + 'scene_teahouse.png',
    '纸条': IMG + 'scene_teahouse.png',
    '手稿': IMG + 'scene_archive.png',
    '借阅': IMG + 'scene_archive.png',
    '便签': IMG + 'scene_desk_kanshan.png',
    '排班': IMG + 'scene_desk_kanshan.png',
    '快递': IMG + 'scene_locker.png',
    '小票': IMG + 'scene_locker.png',
    '空调': IMG + 'scene_hvac.png',
    '机关': IMG + 'scene_hvac.png',
    '终端': IMG + 'scene_hvac.png',
    '锁门': IMG + 'scene_hvac.png',
    '权限': IMG + 'scene_server.png',
    '签名': IMG + 'scene_server.png',
    '风扇': IMG + 'scene_server.png',
    '人影': IMG + 'scene_corridor.png',
    '策划': IMG + 'scene_hotfeed.png',
    '密码': IMG + 'scene_director_office.png',
    '暗号': IMG + 'scene_teahouse.png',
    'V587': BUST + 'char_v587.png',
    '手机': IMG + 'scene_locker.png'
  };

  const LOC_STILL = {
    loc_reception: STILL + 'loc_reception.jpg',
    loc_desk: STILL + 'loc_desk.jpg',
    loc_teahouse: STILL + 'loc_teahouse.jpg',
    loc_locker: STILL + 'loc_locker.jpg',
    loc_monitor: STILL + 'loc_monitor.jpg',
    loc_server: STILL + 'loc_server.jpg',
    loc_archive: STILL + 'loc_archive.jpg',
    loc_hotfeed: STILL + 'loc_hotfeed.jpg',
    loc_ac: STILL + 'loc_ac.jpg',
    loc_roof: STILL + 'loc_roof.jpg',
    loc_clinic: STILL + 'loc_clinic.jpg'
  };

  const LOC_SCENE = {
    loc_reception: IMG + 'scene_reception.png',
    loc_desk: IMG + 'scene_desk_kanshan.png',
    loc_teahouse: IMG + 'scene_teahouse.png',
    loc_locker: IMG + 'scene_locker.png',
    loc_monitor: IMG + 'scene_monitor.png',
    loc_server: IMG + 'scene_server.png',
    loc_archive: IMG + 'scene_archive.png',
    loc_hotfeed: IMG + 'scene_hotfeed.png',
    loc_ac: IMG + 'scene_hvac.png',
    loc_roof: IMG + 'scene_roof.png',
    loc_clinic: IMG + 'scene_study_room.png'
  };

  function topicOf(tag) {
    return TOPIC[tag] || { hue: 'focus', mark: '知', emblem: CARD + 'kc_know.png' };
  }

  function clueThumb(clue) {
    if (!clue) return IMG + 'ui_case_file.png';
    const tags = clue.tags || [];
    for (let i = 0; i < tags.length; i++) {
      if (TAG_THUMB[tags[i]]) return TAG_THUMB[tags[i]];
    }
    if (clue.location && LOC_SCENE[clue.location]) return LOC_SCENE[clue.location];
    return IMG + 'ui_case_file.png';
  }

  function photoStill(loc) {
    return LOC_STILL[loc] || LOC_SCENE[loc] || IMG + 'scene_monitor.png';
  }

  return {
    IMG, BUST, STILL, CARD, HOLO, HOLO_BUST, FISH, TRUE_KS,
    TOPIC, TAG_THUMB, LOC_STILL, LOC_SCENE,
    topicOf, clueThumb, photoStill
  };
})();
