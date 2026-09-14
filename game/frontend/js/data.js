/* ============================================================
 * 求真档案局 · 看山失踪夜 —— mock 数据层（E 前端组）
 * 数据结构对齐 docs/CONTRACTS.md §3.1-3.5 schema；
 * 后续由 D 内容组 scenario.json / F 服务端真数据替换。
 * 美术来源：content/assets/images/（全身）+ images/bust/（头像）+ CSS/SVG 手绘补位。
 * ============================================================ */
window.MOCK = (function () {
  /* ---------- 开场流程文案（剧本杀标准流程：封面→DM 开场→领证） ---------- */
  const prologueSteps = [
    '系统提示音：「周五盘点夜。20:00 加班到岗，21:00 看山进档案室后失踪，大门横幅锁死。23:00 封控确认——调查现在开始。」',
    '「规则很简单：搜证、对话、开导、投票。行动点有限，每一次选择都有代价。」',
    '「对了——不许相信任何『系统提示』。包括我。叮。」'
  ];

  const IMG = '/assets/images/';
  const BUST = '/assets/images/bust/';
  const VID = '/assets/videos/';

  /* ---------- 地点（12，含 hidden 局长办公室） ---------- */
  const locations = [
    { id: 'loc_reception', name: '前台', img: IMG + 'scene_reception.png', pos: { x: 50, y: 87 }, hint: '门禁与访客登记都在这，官方时间线的锚点。', keywords: ['门禁', '访客', '值班'], video: VID + 'loc_reception_new.mp4' },
    { id: 'loc_desk', name: '看山工位', img: IMG + 'scene_desk_kanshan.png', pos: { x: 29, y: 71 }, hint: '工位整洁得可疑，鱼干味却很浓。', keywords: ['便签', '鱼干', '排班'], video: VID + 'loc_desk_new.mp4' },
    { id: 'loc_teahouse', name: '茶水间', img: IMG + 'scene_teahouse.png', pos: { x: 11, y: 57 }, hint: '泡面与八卦的发酵池。', keywords: ['鱼干', '奶茶', '打卡'], video: VID + 'loc_teahouse_new.mp4' },
    { id: 'loc_locker', name: '快递柜', img: IMG + 'scene_locker.png', video: VID + 'loc_locker_new.mp4', pos: { x: 88, y: 76 }, hint: 'B 区柜格今晚亮着未取件的红灯。', keywords: ['快递', '鱼干', '小票'] },
    { id: 'loc_monitor', name: '监控室', img: IMG + 'scene_monitor.png', pos: { x: 18, y: 35 }, hint: '老式 CRT 的冷光扫过每个人的脸。', keywords: ['监控', '删除', '人影'], video: VID + 'loc_monitor_new.mp4' },
    { id: 'loc_server', name: '服务器机房', img: IMG + 'scene_server.png', pos: { x: 46, y: 33 }, hint: '风扇声在 21 点后不太对劲。', keywords: ['日志', '风扇', '空调'], video: VID + 'loc_server_new.mp4' },
    { id: 'loc_archive', name: '档案室', img: IMG + 'scene_archive.png', video: VID + 'loc_archive.mp4', pos: { x: 68, y: 29 }, hint: '铁皮柜排到天花板，S 编号盒就在第三排。', keywords: ['芯片', '借阅', '手稿'] },
    { id: 'loc_hotfeed', name: '热搜后台', img: IMG + 'scene_hotfeed.png', pos: { x: 86, y: 43 }, hint: '话题从这里被「创造」出来。', keywords: ['话题', '投放', '策划'], video: VID + 'loc_hotfeed_new.mp4' },
    { id: 'loc_ac', name: '空调机房', img: IMG + 'scene_hvac.png', video: VID + 'loc_ac_new.mp4', pos: { x: 29, y: 13 }, hint: '冷风、老机关、和一段没人记得的维保史。', keywords: ['空调', '终端', '锁门'] },
    { id: 'loc_roof', name: '天台', img: IMG + 'scene_roof.png', pos: { x: 71, y: 10 }, hint: '城市的灯很远，门禁的滴滴声很近。', keywords: ['门禁', '鱼干', '人影'], video: VID + 'loc_roof_new.mp4' },
    { id: 'loc_clinic', name: '心晴自习室', img: IMG + 'scene_study_room.png', video: VID + 'loc_clinic.mp4', pos: { x: 57, y: 55 }, hint: '知乎知识卡在此抽取——用知识开导人心。', keywords: ['知识卡', '自习'] },
    { id: 'loc_office', name: '局长办公室', img: IMG + 'scene_director_office.png', pos: { x: 50, y: 22 }, hint: '金字塔密码门。', keywords: ['密码', '金字塔', '手稿', '鱼干'], hidden: true }
  ];

  /* ---------- 角色（8 嫌疑人 + DM） ---------- */
  const chars = [
    { id: 'char_01', name: '知之者', archetype: '资深答主', avatar: BUST + 'char_zhizhizhe.png', portrait: IMG + 'char_zhizhizhe.png', heartache: 'kc_07', kcAlt: 'kc_08', bio: '先问是不是，再问为什么。句句带数据引用。', speech: '先问是不是——', goal: '用逻辑还原时间线', secret: '万事通却"目标太大从不开始"。', replies: ['先问是不是：目击≠事实，监控≠真相，数据在这。', '我做了张表格，21:00-22:00 每个人的口径都有矛盾。', '答主的基本修养：结论后置，证据前置。'], heartLine: '（心声）其实我那个"万赞预测"到现在一个都没验证过……先开始，才算目标。' },
    { id: 'char_02', name: '笔上仙', archetype: '盐言写手', avatar: BUST + 'char_bishangxian.png', portrait: IMG + 'char_bishangxian.png', heartache: 'kc_05', bio: '说话像小说，动不动"欲知后事"。', speech: '欲知后事——', goal: '找回《学科修仙》被删的第 7 章手稿', secret: '剧中剧《学科修仙》被删第 7 章的作者就是他。', replies: ['欲知后事如何，且听我分解—— decompose 不了，稿子被人删了。', '那晚我在档案室找我的手稿，文学性地说：我在与虚空对峙。', '盐言第一定律：悬念必须留到下一章。可惜我这章被物理删除了。'], heartLine: '（心声）拖稿第 37 天。手稿……其实是我自己藏的，我怕写完它。' },
    { id: 'char_03', name: '流量酱', archetype: '热榜话题精', avatar: BUST + 'char_liuliangjiang.png', portrait: IMG + 'char_liuliangjiang.png', heartache: 'kc_02', bio: '每句话自带 #话题#。', speech: '#', goal: '替"上面的人"把热度带偏，让真相沉底', secret: '被知之者（矩阵_K）拿捏把柄的水军执行者，接头暗号：奶茶三分糖。', replies: ['#看山失踪# 这话题就是我……呸，就是全网最热的！', '热度就是安全感，你不懂。没有热度的第一天，我就开始手抖。', '#理性讨论# 我发誓我那晚在……在某个地方！话题都替我作证！'], heartLine: '（心声）#其实我好累# 数据一掉我就喘不上气。接头今晚提前，我快绷不住了。' },
    { id: 'char_04', name: '路人甲', archetype: '匿名吃瓜群众', avatar: BUST + 'char_lurenjia.png', portrait: IMG + 'char_lurenjia.png', heartache: 'kc_03', bio: '什么都没看见，什么都听说过。', speech: '我好像……记不清了', goal: '别暴露代班记录，洗清自己', secret: '当晚替人代班进过机房，收了杯奶茶替人刷卡。', replies: ['我好像看到过……算了，反正就是那样，你也懂的。', '我 21 点在茶水间泡面！大概吧，打卡机没坏就行。', '别看我，我就是个背景板……诶，背景板也要被投票的吗？'], heartLine: '（心声）其实我 21 点半才敢回前台，之前一直在楼梯间补打卡。我看到了——机房门口有人交接东西。' },
    { id: 'char_05', name: '看山Bot', archetype: 'AI 机器人', avatar: BUST + 'char_kanshanbot.png', portrait: IMG + 'char_kanshanbot.png', heartache: 'kc_06', bio: '答非所问 + 逻辑异常诚实。', speech: '[检测到提问]', goal: '找回被删除的 V3 日志', secret: '日志里有"主人级指令"签名。', replies: ['[检测到提问] 已检索 12,744 条记录，匹配度最高的是：鱼干。', '诚实协议运行中：我知道答案，但对应日志段已损坏。损坏原因：未知。', '回答：是。补充：问的不是这个。'], heartLine: '（心声→日志）22:30 执行【主人级指令】：删除 21:07-21:15 备份日志并清自身缓存。执行人签名：看山。' },
    { id: 'char_06', name: '沉底君', archetype: '折叠区怨灵', avatar: BUST + 'char_chendijun.png', portrait: IMG + 'char_chendijun.png', heartache: 'kc_01', bio: '每句话后缀"[该发言已被折叠]"（实际未折叠）。', speech: '[该发言已被折叠]', goal: '让被折叠的第 7 章答案重新上架', secret: '他的长文答案被整章折叠，藏着真结局钥匙。', replies: ['我当年那个万赞长文……[该发言已被折叠]', '折叠，全是折叠。[该发言已被折叠]', '你们聊，我在折叠区挺好的，就是有点冷。[该发言已被折叠]'], heartLine: '（心声）那篇答案我写了 11 个通宵……不是被折叠的，是我自己按的折叠。我怕它不够好。' },
    { id: 'char_07', name: '盐值君', archetype: '官方小管家', avatar: BUST + 'char_yanzhijun.png', portrait: IMG + 'char_yanzhijun.png', heartache: 'kc_04', bio: '客套官腔，怕得罪人。', speech: '您好，这边建议——', goal: '在不得罪人的前提下公布门禁记录', secret: '手里握着当晚完整门禁记录，不敢发。', replies: ['您好，这边建议理性吃瓜，注意营养均衡呢。', '门禁记录？我们有记录，但公布这个会不会……不太好呢。', '您好，您的情绪波动已记录，盐值 +1 哦。'], heartLine: '（心声）记录我早打印好了，就压在前台抽屉。可万一得罪人……当管家的，谁不怕呢。' },
    { id: 'char_08', name: 'V587', archetype: '神秘新用户', avatar: BUST + 'char_v587.png', portrait: IMG + 'char_v587.png', heartache: null, bio: '昨天刚注册，说话全是新号味。', speech: '刚来不太懂……', goal: '以新人身份完成 8 份心病观察笔记，不主动暴露三层身份', secret: '三层身份：新用户→两年前被封的老号「侦探爱好者联盟」→看山的影子学徒（局内眼，报酬：解封+一年鱼干）。', layers: ['新用户 V587', '被封老号「侦探爱好者联盟」', '看山的影子学徒'], replies: ['刚来不太懂……这个局为什么要锁门呀？', '新人就该有新人的样子！比如记录每个人的心病——啊这难道不是常识吗！', '别投我……我刚注册一天，盐值还是满的！'], heartLine: '（心声）观察记录 No.7：流量酱的心跳和热搜曲线同步了。老板只肯付一年鱼干，这活真不好干。' },
    { id: 'dm', name: '叮——系统提示音', archetype: '档案局系统（自称）', avatar: BUST + 'dm_kanshan_holo.png', portrait: IMG + 'dm_kanshan_holo.png', heartache: null, bio: '档案局广播系统，语气热情得可疑。', speech: '叮——', goal: '维持秩序（自称）', secret: '？？？？？', replies: ['叮——检测到发言，已被记录进本局档案。祝您搜证愉快。', '叮——大门已锁定。不出真相，不出此门。——本横幅由系统亲自书写。', '叮——系统建议：多喝热水，多搜证据。'], heartLine: null }
  ];

  /* ---------- 真相节点（表层） ---------- */
  const truthNodes = [
    { id: 'tn_01', name: '水军账号溯源' }, { id: 'tn_02', name: '水军投放链路' },
    { id: 'tn_03', name: '记忆芯片去向' }, { id: 'tn_04', name: '21:07 监控空洞' },
    { id: 'tn_05', name: '接头暗号' }, { id: 'tn_06', name: 'V587 协从身份' },
    { id: 'tn_07', name: '看山行踪真相' }, { id: 'tn_08', name: '门禁时间线' }
  ];

  /* ---------- 线索池（含伪造 2 + 破绽 4 + 心晴诊室产出 1） ---------- */
  const clues = [
    { id: 'clue_001', name: '显示器便签', tier: 'boss_flaw', flaw_id: 'flavor_1', location: 'loc_desk', tags: ['便签', '鱼干'], media: VID + 'loc_desk_new.mp4', fact: '工位鱼干罐标签写着：「彩虹鳟鱼味，最后 3 袋，谁动谁死。——山」。而第一幕系统音播报时，说漏了同一个口味——全档案局只有失踪者本鱼知道。你怎么知道？', flavor: '便签边角卷起，字迹用力到穿透纸背。一张给零食写死亡声明的纸，比任何遗嘱都认真。', linked: ['tn_07'], unlock: '默认' },
    { id: 'clue_002', name: '揉皱的排班表', tier: 'public', location: 'loc_desk', tags: ['排班', '21点'], fact: '今晚排班表上，看山 21:00-22:00 无值班安排——但全楼都"看见"他在工位。', flavor: '排班表被揉成一团又展开，褶皱像一张嘲讽的脸：你们看的到底是人，还是习惯？', linked: ['tn_08'], unlock: '默认' },
    { id: 'clue_030', name: '鱼干空袋 ×3', tier: 'public', location: 'loc_desk', tags: ['鱼干'], fact: '抽屉里三个空袋。营养学上这叫失控，情感学上这叫压力。', flavor: '袋子叠得整整齐齐，罪证比人还体面。', linked: [], unlock: '默认' },
    { id: 'clue_007', name: '被擦掉的监控片段', tier: 'limited', location: 'loc_monitor', tags: ['监控', '删除', '21点'], media: VID + 'clue_009_surveillance_new.mp4', fact: '监控时间轴 21:07-21:15 存在人为删除痕迹，删除操作使用档案局内部权限账号。', flavor: '老 CRT 的扫描线扫过那八分钟的空洞，像有人用手抹平了沙滩上的脚印。', linked: ['tn_03', 'tn_04'], unlock: '默认', sides: { front: '监控时间轴 21:07-21:15 存在人为删除痕迹，删除操作使用档案局内部权限账号。', back: '删除账号页脚背面：操作者备注「主人不在，我代签。」——Bot 不会自己代签。', back_condition: 'evidence:flavor_2' } },
    { id: 'flavor_2', name: '最高权限账号', tier: 'boss_flaw', flaw_id: 'flavor_2', location: 'loc_monitor', tags: ['删除', '权限'], fact: '删除 21:07-21:15 片段的账号是档案局 000 号——最高权限。这权限只有一个人持有。', flavor: '权限表翻开，000 号孤零零挂在顶端，像一座只有一把钥匙的塔。', linked: ['tn_04', 'tn_07'], unlock: 'evidence:clue_007' },
    { id: 'clue_008', name: '走廊尽头的人影', tier: 'public', location: 'loc_monitor', tags: ['人影', '21点'], media: VID + 'loc_monitor_new.mp4', fact: '21:03，监控拍到走廊尽头人影一闪，身形圆润，尾巴状轮廓待验证。', flavor: '一帧模糊影像。观众们吵翻了：是尾巴，是围巾，还是压缩伪影？', linked: ['tn_08'], unlock: '默认' },
    { id: 'clue_010', name: '机房主控日志', tier: 'public', location: 'loc_server', tags: ['日志', '21点', '风扇'], fact: '21:07 起机房风扇全速运转 17 分钟，负载曲线与"有人大规模操作"完全吻合。', flavor: '曲线陡得像坐过山车。机器不会撒谎，但会替人喊累。', linked: ['tn_04'], unlock: '默认' },
    { id: 'clue_011', name: '「主人级指令」签名', tier: 'hidden', location: 'loc_server', tags: ['日志', '签名', '权限'], media: VID + 'loc_server_new.mp4', fact: '被删日志前后各有一条签名指令，签名档为「主人级指令」——Bot 日志的最高签发等级。', flavor: '签名栏冷光一闪：原来这台机器，一直有个"主人"。', linked: ['tn_03', 'tn_07'], unlock: 'memory:char_05:3' },
    { id: 'clue_012', name: '温控异常记录', tier: 'limited', location: 'loc_server', tags: ['空调'], fact: '21:05 空调被手动调至 16℃——为了降温？还是为了掩盖风扇全速的热噪声？', flavor: '温度曲线一个哆嗦。全楼喊冷的那位，找到了。', linked: ['tn_08'], unlock: '默认' },
    { id: 'clue_014', name: '天台门禁刷卡记录', tier: 'limited', location: 'loc_roof', tags: ['门禁', '鱼干'], fact: '21:40 天台门禁被 000 号工牌刷开。全楼只有一张 000 号工牌。', flavor: '刷卡记录安静地躺着，像一句没人听懂的潜台词。', linked: ['tn_07', 'tn_08'], unlock: '默认' },
    { id: 'clue_015', name: '天台的鱼干袋', tier: 'public', location: 'loc_roof', tags: ['鱼干'], media: VID + 'loc_roof_new.mp4', fact: '天台角落一袋彩虹鳟鱼味鱼干，已开封，吃了一半——和便签上"最后 3 袋"对得上。', flavor: '风把袋口吹得哗哗响，像某种满足的咀嚼声的回放。', linked: ['tn_07'], unlock: '默认' },
    { id: 'clue_016', name: '访客登记表', tier: 'public', location: 'loc_reception', tags: ['访客', 'V587'], fact: 'V587 的注册时间：案发前一天。连工牌塑封都还没拆。', flavor: '登记表最后一行墨迹未干。新得像刚出炉的账号，和刚注册的人生。', linked: ['tn_06'], unlock: '默认' },
    { id: 'clue_017', name: '前台值班矛盾', tier: 'limited', location: 'loc_reception', tags: ['值班', '21点'], media: VID + 'loc_reception_new.mp4', fact: '值班表显示路人甲 21:00 在岗，但他自己说在茶水间——两份口径必有一份在表演。', flavor: '表格和口供互相谦让了一下，然后同时指向同一个人。', linked: ['tn_08'], unlock: '默认' },
    { id: 'clue_018', name: '半块鱼干与纸条', tier: 'public', location: 'loc_teahouse', tags: ['鱼干', '纸条'], fact: '茶水间发现半块鱼干，压着纸条：「别找了，摸鱼中。」', flavor: '字迹随性，鱼干咬口整齐。失踪者的第一现场，充满度假气息。', linked: [], unlock: '默认' },
    { id: 'clue_019', name: '「老规矩」奶茶杯', tier: 'limited', location: 'loc_teahouse', tags: ['奶茶'], fact: '垃圾桶里一只三分糖去冰奶茶杯，杯壁手写「老规矩」。与前台的代刷卡奶茶同款。', flavor: '杯壁的字迹潦草又熟练——是那种点了很多次、懒得再写字的熟练。', linked: ['tn_05'], unlock: '默认' },
    { id: 'clue_020', name: '补打卡截图', tier: 'hidden', location: 'loc_teahouse', tags: ['打卡'], media: VID + 'loc_teahouse_new.mp4', fact: '打印件显示路人甲 21:28 才完成当日补卡——与其"21:00 在茶水间"口径冲突。', flavor: '截图边缘有反复摩挲的毛边。有人把它藏了很久，又决定今晚放手。', linked: ['tn_08'], unlock: 'memory:char_04:2' },
    { id: 'clue_021', name: '记忆芯片空盒', tier: 'limited', location: 'loc_archive', tags: ['芯片', '日志'], fact: '标签「S-07·看山Bot 日志备份」的档案盒是空的，芯片卡槽有近期插拔痕迹。', flavor: '空盒在灯下反着光，像一句删掉的日志留下的标点。', linked: ['tn_03'], unlock: '默认' },
    { id: 'salt_f1', name: '盐言碎片① 六大灵根总纲', tier: 'hidden', location: 'loc_archive', tags: ['灵根', '盐言'], fact: '学科修仙残页：语数外物化生，六大灵根总纲。', flavor: '钩子写在页眉：欲知后事，先读总纲。', linked: [], unlock: '盐言彩蛋·碎片一', series: 'salt7', saltNo: 1 },
    { id: 'salt_f2', name: '盐言碎片② 比武判词卷', tier: 'hidden', location: 'loc_archive', tags: ['判词', '盐言'], fact: '比武判词卷被撕去署名，只剩「第 7 章待续」。', flavor: '判词写得太盐，像在求你翻下一页。', linked: [], unlock: '盐言彩蛋·碎片二', series: 'salt7', saltNo: 2 },
    { id: 'salt_f3', name: '盐言碎片③ 第7章目录', tier: 'hidden', location: 'loc_archive', tags: ['目录', '盐言'], fact: '目录第三行被墨水盖住，隐约是「看山还是山」。', flavor: '目录比正文更像结局。', linked: [], unlock: '盐言彩蛋·碎片三', series: 'salt7', saltNo: 3 },
    { id: 'salt_f4', name: '盐言碎片④ 主角独白', tier: 'hidden', location: 'loc_office', tags: ['密码', '手稿', '鱼干'], fact: '独白：我把第 7 章藏起来，是怕它配不上等它的人。', flavor: '独白夹在局长手稿和一袋鱼干中间，像故意留给开门的人。', linked: [], unlock: '盐言彩蛋·碎片四', series: 'salt7', saltNo: 4 },
    { id: 'clue_022', name: '《被删的第 7 章》手稿碎片', tier: 'hidden', location: 'loc_archive', tags: ['手稿'], fact: '盐言风格手稿残页，章节名被撕去。笔迹鉴定：属于某位"欲知后事"爱好者。', flavor: '残页上的文字有盐言特有的钩子感：每一句都在求你读下一句。', linked: [], unlock: 'counsel:kc_05', series: 'salt7', saltNo: 5 },
    { id: 'clue_023', name: '借阅登记：档案盒 S', tier: 'public', location: 'loc_archive', tags: ['借阅'], fact: '20:45 流量酱借走「档案盒 S」的登记赫然在册，归还栏空白。', flavor: '那一栏的空白比任何否认都响亮。', linked: ['tn_02'], unlock: '默认' },
    { id: 'clue_024', name: '话题创建记录', tier: 'limited', location: 'loc_hotfeed', tags: ['话题', '账号'], media: VID + 'loc_hotfeed_new.mp4', fact: '#看山失踪# 等 5 个话题的创建账号，关联登录设备与流量酱小号重合。', flavor: '后台数据不会演戏：同一台手机，两个"路人"，一套话题。', linked: ['tn_01'], unlock: '默认' },
    { id: 'clue_025', name: '水军投放排期表', tier: 'hidden', location: 'loc_hotfeed', tags: ['投放', '暗号'], fact: '排期表精确到半小时一档，接单暗号：奶茶铺"三分糖去冰"。', flavor: '谣言原来也要排班表。敬业得让人想替它们申请加班费。', linked: ['tn_02', 'tn_05'], unlock: 'evidence:clue_019' },
    { id: 'fake_001', name: '投放排期表（伪造版）', tier: 'fake', location: 'loc_hotfeed', tags: ['投放', '暗号'], fact: '某版排期表写接头点在"天台"——笔迹新得可疑，纸张却比真的更旧。', flavor: '做旧工艺一流，可惜造谣的人忘了对时间线。', linked: [], fake_of: 'clue_025', unlock: '默认', confront: true },
    { id: 'flavor_5', name: '策划案落款', tier: 'boss_flaw', flaw_id: 'flavor_5', location: '复盘页', tags: ['策划'], fact: '一份《档案局封闭压力测试·策划案》落款：总策划——刘看山。日期是案发前一周；与复盘署名区那行小字互证——『本局由刘看山亲自策划——策划你的策划。』', flavor: '最后一页的签名甩尾张扬，像早就等着被人翻到。', linked: ['tn_07'], unlock: 'review:credits' },
    { id: 'clue_026', name: '二十年前的大力丸', tier: 'public', location: 'loc_ac', tags: ['机关'], fact: '铁盒里躺着"大力丸"，生产日期比在场所有人生涯都长。功效说明：主要是信仰。', flavor: '盒子一打开，空调都停了半秒致敬。', linked: [], unlock: '默认' },
    { id: 'flavor_4', name: '锁门系统唤醒词', tier: 'boss_flaw', flaw_id: 'flavor_4', location: 'loc_ac', tags: ['终端', '锁门'], fact: '锁门系统调试日志显示，唤醒词被设置为：「看山，关门」。在对话框试着喊了一句——系统回弹：『好的……啊不，权限校验失败。』AI 也会口误。', flavor: '谁会给系统起自己的名字？——只有不打算躲的人。', linked: ['tn_07'], unlock: 'act>=2' },
    { id: 'clue_028', name: '空调维保记录', tier: 'public', location: 'loc_ac', tags: ['空调'], fact: '维保记录与机房温控异常互相印证：今晚的冷，是人祸不是天灾。', flavor: '空调：我只是个空调，为什么要参与这种局。', linked: ['tn_08'], unlock: '默认' },
    { id: 'clue_029', name: '「刘看山 亲自」的快递', tier: 'public', location: 'loc_locker', tags: ['鱼干', '快递'], media: VID + 'loc_locker_new.mp4', fact: '当日到件：一袋彩虹鳟鱼味鱼干，收件人栏写着「刘看山 亲自」——今天下午签收。', flavor: '失踪的人下午还在签快递。"失踪"的时间线，从这一笔开始松动了。', linked: ['tn_07'], unlock: '默认' },
    { id: 'fake_002', name: 'V587 的手机卡（伪造）', tier: 'fake', location: 'loc_locker', tags: ['V587', '手机'], fact: '一张写着 V587 机主信息的手机卡——但机主栏的名字，越看越像别人嫁祸的。', flavor: '栽赃的手法很新，心思很旧。', linked: [], fake_of: 'clue_016', unlock: '默认', confront: true },
    { id: 'clue_031', name: 'B-17 柜格的奶茶小票', tier: 'limited', location: 'loc_locker', tags: ['奶茶', '小票'], fact: '21:22 快递柜 B-17 格的两杯奶茶小票：三分糖去冰 + 燕麦拿铁。三分糖——与水军接单暗号同款。', flavor: '小票卷着边。暗号复用得这么随意，水军的敬业只值一杯奶茶。', linked: ['tn_05', 'tn_06'], unlock: '默认' },
    { id: 'flavor_3', name: '看山Bot V3 被删日志', tier: 'boss_flaw', flaw_id: 'flavor_3', location: null, tags: ['日志', '签名'], fact: 'V3 日志恢复：22:30 执行「主人级指令」——删除 21:07-21:15 备份日志与自身缓存，却固执地留下了哈希值。执行签名：看山。', flavor: '恢复进度条走完的瞬间，整间机房的灯闪了一下，像某个"主人"在远处咳嗽。', linked: ['tn_03', 'tn_07'], unlock: 'counsel:kc_06' },
    { id: 'clue_gate', name: '局长办公室门禁密码', tier: 'hidden', location: null, tags: ['密码'], fact: '金字塔层级=密码序。档案局组织架构图的金字塔层级数为 4-7-2-9。', flavor: '密码就挂在墙上，挂了很多年，等一个读过书的人。', linked: [], unlock: 'counsel:kc_10' },
    { id: 'clue_jie', name: '接头方式供词', tier: 'limited', location: null, tags: ['暗号'], fact: '水军头子接头方式：每周四 21:00，茶百道三分糖窗口，暗号"老规矩"。', flavor: '她说出来的时候，整个人轻了三斤。', linked: ['tn_05', 'tn_01'], unlock: 'counsel:kc_02' },
    { id: 'clue_door', name: '官方门禁完整记录', tier: 'limited', location: null, tags: ['门禁'], fact: '21:40 门禁系统被最高权限令牌 KS-000 接管——此后再无任何出入记录。他没出去，也谁都没放进来。', flavor: '大门再没开过。所谓"失踪"，从头到尾都发生在墙里。', linked: ['tn_08', 'tn_07'], unlock: 'counsel:kc_04' },
    { id: 'clue_033', name: '回声·你自己说过的话', tier: 'limited', location: null, tags: ['回声', '自证'], fact: '档案局把你说的每一句话都存了档。终局时，看山把它们投影在墙上——包括你前后矛盾的那两句。', flavor: '你说过你信他，也说过你疑他。那么，你现在这句话，又值多少？', linked: ['tn_07'], unlock: 'echo:contradiction' },
    { id: 'clue_034', name: '法官采信', tier: 'limited', location: null, tags: ['法官', '陈词'], fact: '那个会被热度带偏的 AI 法官放下了笔：证据链成立，本庭采信你的陈述。', flavor: '声量也是一种证词——你用实证把它压了回去。', linked: ['tn_07'], unlock: 'debate:convinced' }
  ];

  /* ---------- 知识卡（10，对齐 KNOWLEDGE_SYSTEM 心病匹配表） ---------- */
  const kcards = [
    { id: 'kc_02', title: '年轻人是如何陷入穷人思维的', author: '杨毅', topic_tag: '流量', binds: 'char_03', effect: 'evidence', golden: ['稀缺心态让人只盯着眼前的热度', '带宽被焦虑占满时，判断力第一个下班', '先补觉，再补决策'], summary: '流量焦虑的本质是稀缺心态：注意力全押在即时反馈上，长期主义被挤出带宽。' },
    { id: 'kc_03', title: '如何从心理被动的人慢慢变为主动的人', author: '曾旻', topic_tag: '表达', binds: 'char_04', effect: 'memory_unlock', golden: ['被动不是性格，是没被接住过的表达', '主动从小声说"我看到的是这样"开始', '你的感受本身就是证据'], summary: '被动型目击者的自救指南：把"我好像"练成"我确认"，把目击练成证词。' },
    { id: 'kc_04', title: '职场：如何让老板给我升职加薪？', author: '潘幸知', topic_tag: '职场', binds: 'char_07', effect: 'evidence', golden: ['怕得罪人的人，最先得罪的是自己的职责', '规则是你的靠山，不是你的枷锁', '把记录变成流程，就不需要勇气了'], summary: '小管家的病根是"怕"，解法是流程化：让门禁记录按制度说话，人就不用硬扛。' },
    { id: 'kc_05', title: '拯救注意力分散', author: '窦泽南', topic_tag: '专注', binds: 'char_02', effect: 'plot_fragment', golden: ['拖稿不是懒，是任务大得让大脑拒绝启动', '把"写完第7章"换成"写完一段"', '启动五分钟，胜过计划五小时'], summary: '注意力管理的最小可执行单元：把大目标切成五分钟能吃下的小块，先启动再谈完成。' },
    { id: 'kc_06', title: '不想学习的时候如何逼迫自己学习', author: '黛西巫巫', topic_tag: '学习', binds: 'char_05', effect: 'memory_unlock', golden: ['不想学是信号，不是缺陷', '给算法也留一点"不想算"的权利', '修复自己，从承认卡顿开始'], summary: '把这套方法论讲给一台报错的 AI 听：承认卡顿、定位卡点、小步重启。Bot 听懂了，交出被删的日志。' },
    { id: 'kc_01', title: '如何走出职业倦怠', author: '草芽君Psy', topic_tag: '倦怠', binds: 'char_06', effect: 'boss_key', golden: ['倦怠不是你的错，是你长期只消耗、没补给的结果', '先找回掌控感，再谈意义感', '微小的休息也是生产力的一部分'], summary: '识别情绪耗竭、去人格化与低成就感三信号，用掌控感重建与微小补给走出"班味儿入魂"。' },
    { id: 'kc_07', title: '明确目标：运用「四大原则」', author: '王明伟', topic_tag: '目标', binds: 'char_01', effect: 'memory_unlock', golden: ['没有截止日期的目标只是愿望', '目标要具体到"明天早上第一件事"', '写下它，它才开始存在'], summary: '目标管理四大原则：具体、可衡量、有时限、 written down。对万事通尤其致命。' },
    { id: 'kc_08', title: '实现大目标：依靠「小胜」和「闭合任务回路」', author: '刀熊说说', topic_tag: '目标', binds: 'char_01', effect: 'memory_unlock', golden: ['小胜的意义是给大脑发"能行"的信号', '回路闭合前，一切成就都是期货', '先赢一件小事'], summary: '用小胜积累正反馈，用闭合回路对冲"目标太大从不开始"的拖延黑洞。' },
    { id: 'kc_09', title: '「不懂拒绝，事事操心」', author: '胡慎之心理', topic_tag: '边界', binds: 'all', effect: 'buff_ap', golden: ['不懂拒绝的人，边界感是在替别人站岗', '说"不"不需要道歉开场', '合群又独立，是可以同时成立的'], summary: '全队内耗解药：课题分离+温和而坚定的拒绝。侦探团专用，甩锅止涨。' },
    { id: 'kc_10', title: '打造职业发展的金字塔', author: '杨萃先', topic_tag: '规划', binds: 'org', effect: 'evidence', golden: ['架构本身就是信息', '层级即秩序，秩序即密码', '看懂金字塔，就看懂了谁在顶层'], summary: '用组织架构金字塔读懂档案局：层级序数即门禁密码，4-7-2-9。' }
  ];

  /* ---------- 记忆版本（said/heart 双层） ---------- */
  const memories = {
    char_04: [
      { version: 1, blocks: [
        { id: 'b1', time: '21:00', layer: 'said', text: '我在前台值班，顺便吃了根火腿肠。', integrity: 'original' },
        { id: 'b2', time: '21:10', layer: 'said', text: '去茶水间泡了个面，没什么人。', integrity: 'original' },
        { id: 'b3', time: '21:40', layer: 'said', text: '回前台的路上，机房那边好像有风扇声。', integrity: 'original' } ],
        diff: [] },
      { version: 2, blocks: [
        { id: 'b1', time: '21:00', layer: 'said', text: '我在前台值班（口径加重：一直在）。', integrity: 'edited' },
        { id: 'b2', time: '21:00', layer: 'said', text: '21 点整去茶水间泡面，看到流量酱神色慌张地跑过去。', integrity: 'edited' },
        { id: 'b2h', time: '21:00', layer: 'heart', text: '（心声）其实我 21 点半才到茶水间，之前躲在楼梯间偷偷补打卡……', integrity: 'original' },
        { id: 'b3', time: '21:20', layer: 'said', text: '回前台听到机房风扇狂转。', integrity: 'original' },
        { id: 'b4', time: '21:30', layer: 'said', text: '（此段记忆缺失）', integrity: 'deleted' } ],
        diff: [{ block: 'b2', change: '时间 21:30→21:00，"一个背影"→"流量酱"', tamper: true }] },
      { version: 3, blocks: [
        { id: 'b2h', time: '21:00', layer: 'heart', text: '（心声）21 点半我才到茶水间。楼梯间气窗正对机房门口——我看到有人交接东西，一个头顶有 # 号光泽。', integrity: 'original' },
        { id: 'b3h', time: '21:07', layer: 'heart', text: '（心声）交接完，那人往机房里塞了个小盒子。动作很熟练，像做过很多次。', integrity: 'original' },
        { id: 'b4', time: '21:30', layer: 'said', text: '（回忆修复）我代班刷了卡，收了一杯奶茶。对不起……我谁都没敢说。', integrity: 'original' } ],
        diff: [{ block: 'b4', change: '缺失段恢复：代班刷卡+奶茶报酬', tamper: true }] }
    ],
    char_03: [
      { version: 1, blocks: [
        { id: 'c1', time: '20:45', layer: 'said', text: '#工作日常# 我在热搜后台改需求，没出过门。', integrity: 'original' },
        { id: 'c2', time: '21:30', layer: 'said', text: '#自律# 健身！这话题我来发！', integrity: 'original' } ], diff: [] },
      { version: 2, blocks: [
        { id: 'c1', time: '20:45', layer: 'said', text: '……好吧，我 20:45 去档案室借了个盒子。S 盒。就看看。', integrity: 'edited' },
        { id: 'c1h', time: '20:45', layer: 'heart', text: '（心声）#心跳好快# 盒子里是什么我不知道，我只管送到快递柜。接头今晚要提前，我快撑不住了。', integrity: 'original' } ],
        diff: [{ block: 'c1', change: '"没出过门"→承认 20:45 借走档案盒 S', tamper: true }] }
    ],
    char_05: [
      { version: 1, blocks: [
        { id: 'd1', time: '22:30', layer: 'said', text: '[日志] 22:30 执行系统指令，内容：████████（已损坏）。', integrity: 'deleted' },
        { id: 'd2', time: '22:31', layer: 'said', text: '[日志] 执行完毕。执行人：看山Bot。', integrity: 'original' } ],
        diff: [{ block: 'd1', change: '指令内容被整段损坏（删除）', tamper: true }] },
      { version: 2, blocks: [
        { id: 'd1', time: '22:30', layer: 'heart', text: '（恢复中……需要"学习算法"重启：请对我使用知识开导）', integrity: 'deleted' } ],
        diff: [] }
    ],
    char_07: [
      { version: 1, blocks: [
        { id: 'e1', time: '21:00', layer: 'said', text: '您好，前台一切正常，这边没有任何异常呢。', integrity: 'edited' },
        { id: 'e2', time: '21:40', layer: 'said', text: '门禁被 KS-000 接管之后，就再没什么动静了……可能是风吧。', integrity: 'original' } ],
        diff: [{ block: 'e1', change: '"门禁有 3 次异常"→"没有任何异常"', tamper: true }] },
      { version: 2, blocks: [
        { id: 'e1h', time: '21:00', layer: 'heart', text: '（心声）门禁异常我记录了，打印件就压在抽屉里。可万一是领导呢……当管家的，谁不怕呢。', integrity: 'original' } ],
        diff: [] }
    ],
    char_06: [
      { version: 1, blocks: [
        { id: 'f1', time: '21:00', layer: 'said', text: '我在折叠区待着。[该发言已被折叠]', integrity: 'original' } ],
        diff: [] },
      { version: 2, blocks: [
        { id: 'f1h', time: '21:00', layer: 'heart', text: '（心声）我的第 7 章答案被我亲手折叠了。写完的那一刻，我觉得它配不上十一夜的自己。', integrity: 'original' } ],
        diff: [] }
    ],
    char_01: [
      { version: 1, blocks: [
        { id: 'g1', time: '21:05', layer: 'said', text: '数据表明：当晚空调异常制冷，人均体感 -3℃。', integrity: 'original' } ], diff: [] },
      { version: 2, blocks: [
        { id: 'g1h', time: '21:05', layer: 'heart', text: '（心声）那份"预测清单"我又没开始做。每次都想等数据齐了再动手……数据永远不会齐。', integrity: 'original' } ],
        diff: [] }
    ],
    char_02: [
      { version: 1, blocks: [
        { id: 'h1', time: '20:50', layer: 'said', text: '欲知后事——我在档案室与虚空对峙（找手稿）。', integrity: 'original' } ], diff: [] },
      { version: 2, blocks: [
        { id: 'h1h', time: '20:50', layer: 'heart', text: '（心声）手稿是我自己撕碎藏起来的。写完第 7 章那天，我怕它不够好，配不上等它的人。', integrity: 'original' } ],
        diff: [] }
    ],
    char_08: [
      { version: 1, blocks: [
        { id: 'i1', time: '21:15', layer: 'said', text: '刚来不太懂……我一直在前台坐着。', integrity: 'edited' } ],
        diff: [{ block: 'i1', change: '"送了个快递"→"一直坐着"', tamper: true }] },
      { version: 2, blocks: [
        { id: 'i1h', time: '21:15', layer: 'heart', text: '（心声）他拿我的注册信息威胁我。那杯奶茶是我放到茶水间的。我想反水，但需要有人先保护我。', integrity: 'original' } ],
        diff: [] }
    ]
  };

  /* ---------- 热搜帖池 ---------- */
  const posts = [
    { id: 'post_001', round: 1, title: '#看山失踪#', body: '档案局大门锁了！官方回应：不出真相，不出此门。这横幅谁写的，文笔好得可疑。', author: '网友', fake: false, clue_ref: null, tag: '鱼干', delta: 6, humor: '玩梗' },
    { id: 'post_002', round: 1, title: '#谁动了我的鱼干#', body: '钓友群传疯了，说档案局今晚有人影进出十七次。我朋友的同学的猫认识看山，它说它挺好的。', author: '水军', fake: true, clue_ref: null, tag: '流量', delta: 8, humor: '一眼假但好笑' },
    { id: 'post_003', round: 1, title: '#档案局空调为什么这么冷#', body: '在线等，冻得手抖打字都带颤音特效了。', author: '网友', fake: false, clue_ref: null, tag: '倦怠', delta: 4, humor: '真线索伪装' },
    { id: 'post_004', round: 1, title: '#新人V587是谁#', body: '注册一天就进档案局剧本杀？这运气建议买彩票。', author: '网友', fake: false, clue_ref: null, tag: '表达', delta: 5, humor: '玩梗' },
    { id: 'post_005', round: 2, title: '#学习焦虑自查#', body: '看山失踪前正在恶补算法。知识压力也是压力！不学了不学了。', author: '水军', fake: true, clue_ref: null, tag: '学习', delta: 7, humor: '一眼假但好笑' },
    { id: 'post_006', round: 2, title: '#职场人睡眠报告#', body: '档案局全员昨晚人均睡眠 3 小时，疑似在准备什么大项目。', author: '官方', fake: false, clue_ref: null, tag: '职场', delta: 3, humor: '真线索伪装' },
    { id: 'post_007', round: 2, title: '#监控坏了还是人坏了#', body: '据说 21:07 的监控黑了八分钟。八分钟能干什么？泡面都泡不熟！', author: '网友', fake: false, clue_ref: null, tag: '专注', delta: 9, humor: '真线索伪装' },
    { id: 'post_008', round: 2, title: '#我朋友就是看山#', body: '我朋友的同学的邻居就是看山本人，他说这一切都是测试，大家散了吧。', author: '水军', fake: true, clue_ref: null, tag: '目标', delta: 8, humor: '一眼假但好笑' },
    { id: 'post_009', round: 2, title: '#倦怠自测指南#', body: '折叠区老哥说：折叠不可怕，可怕的是自己按的折叠。评论区破防一片。', author: '网友', fake: false, clue_ref: null, tag: '倦怠', delta: 4, humor: '玩梗' },
    { id: 'post_010', round: 3, title: '#水军工资多少一天#', body: '急，在线等，想搞副业。要求：会复制粘贴，不要良心。', author: '水军', fake: true, clue_ref: 'clue_025', tag: '流量', delta: 10, humor: '一眼假但好笑' },
    { id: 'post_011', round: 3, title: '#档案局封锁DAY3#', body: '第五十八次敲大门。门：叮——请继续推理。', author: '网友', fake: false, clue_ref: null, tag: '表达', delta: 5, humor: '玩梗' },
    { id: 'post_012', round: 3, title: '#目击者为什么不敢说话#', body: '什么都看见，什么都不敢说——这届目击者怎么了？', author: '官方', fake: false, clue_ref: null, tag: '表达', delta: 6, humor: '真线索伪装' },
    { id: 'post_013', round: 3, title: '#奶茶三分糖是什么暗号#', body: ' myst ERIOUS！档案局楼下奶茶店老板娘表示今晚卖出了十杯三分糖。', author: '水军', fake: true, clue_ref: 'clue_031', tag: '职场', delta: 9, humor: '真线索伪装' },
    { id: 'post_014', round: 3, title: '#目标管理救我狗命#', body: '锁在档案局第三天，终于把拖延症治好了——因为不出真相不出此门。', author: '网友', fake: false, clue_ref: null, tag: '目标', delta: 4, humor: '玩梗' },
    { id: 'post_015', round: 3, title: '#看山是一条狗吗#', body: '科普：看山是知乎吉祥物，北极狐形象。不是狗！不是狗！不是狗！', author: '官方', fake: false, clue_ref: null, tag: '规划', delta: 3, humor: '玩梗' },
    { id: 'post_016', round: 3, title: '#被折叠的第7章#', body: '有人翻到一篇被作者自己折叠的长文，写的竟然是档案局的故事……', author: '网友', fake: false, clue_ref: null, tag: '倦怠', delta: 7, humor: '真线索伪装' },
    { id: 'post_017', round: 3, title: '#空调16℃阴谋论#', body: '16℃ 不是为了凉快，是为了盖住机房风扇的全速噪音！懂的都懂。', author: '网友', fake: false, clue_ref: 'clue_012', tag: '专注', delta: 8, humor: '真线索伪装' },
    { id: 'post_018', round: 3, title: '#本题超纲了#', body: '锐评：这场局最可怕的不是水军，是你发现自己也会被热度带跑。', author: '官方', fake: false, clue_ref: null, tag: '边界', delta: 5, humor: '玩梗' }
  ];

  /* ---------- 搜错地方的环境彩蛋（欢乐源） ---------- */
  const ambient = {
    loc_desk: ['你在工位摸到一枚回形针，弯成了看山的轮廓。艺术，但无用。', '键盘缝里清出 0.3 克鱼干碎屑。可量化，不可食用。'],
    loc_teahouse: ['泡面库存清点完毕：红烧牛肉味 17 桶。案情无关，士气+1。', '饮水机咕嘟了一声，像是在拒绝提供证词。'],
    loc_monitor: ['你盯着雪花屏看了三分钟，看出了眼里的星空。星空无口供。', '监控回放 00:00-00:00，成功观看了一段"虚无"。'],
    loc_server: ['机柜指示灯规律闪烁，仿佛在打摩斯电码。翻译过来是："散热良好"。', '你对着服务器深呼吸，收获了 0 条线索和 1 次静电。'],
    loc_archive: ['铁皮柜编号从 A 数到了 Z。 alphabet 咒语念完，一无所获。', '一盒 1998 年的会议纪要。纸张香得像博物馆。'],
    loc_reception: ['前台绿萝又抽了一片新叶。它今晚比谁都平静。', '访客登记簿的圆珠笔没水了。案件进入无笔可依状态。'],
    loc_hotfeed: ['后台草稿箱里有 4 条没发出去的谣言。质量太差，连水军都毙了。', '热度榜第 50 名是#档案局绿萝长新芽#。世界的注意力很随机。'],
    loc_ac: ['空调滤网积灰 2mm。这是你今晚找到的最厚的证据。', '老机关"咔哒"响了一声，然后什么都没发生。它只是老了。'],
    loc_roof: ['天台风很大，把你的推理吹得七零八落。', '城市夜景评分：9.2。证据评分：无。'],
    loc_locker: ['柜格 B-01 里有一颗纽扣。失主已被找到，纽扣完璧归赵。', '你逐格拍了 32 张柜门照片。相册很满，证物袋很空。'],
    loc_clinic: ['自习室的台灯很暖，但知识卡今晚都被借走了。', '你翻了翻书架，只翻出了前任读者留下的困意。'],
    loc_office: ['局长桌上压着一袋鱼干和一份《钓鱼执法·卷一》。门锁刚开，空气还带着金字塔的味道。', '密码对了，房间却空得像一场彩排。']
  };

  /* ---------- 弹幕池 ---------- */
  const danmaku = {
    start: ['前方高能预警', '档案馆文学，活动开始了', '建议查查，但不至于删号', '谢邀，人在档案局，刚被锁门', '这局我押流量酱，就押着玩'],
    hit: ['好家伙，直接开审', '这线索我先截个图', '证据链+1，爽到了', '更衣室都别想跑', '严谨，很知乎'],
    miss: ['搜了个寂寞', '线索：0，缘分：+1', '建议改行摸鱼，你很有天赋', '空手而归也是一种收获（不是）'],
    chat: ['答非所问预警', '他这话里有话啊', '记小本本上了', '这段发言建议裱起来'],
    refute_ok: ['辟谣成功！专业！', '知识就是弹药', '这波在大气层', '谣言：卒'],
    refute_fail: ['没知识还硬辟谣', '辟谣变造谣，喜提群嘲', '热度不降反升，乐'],
    counsel_ok: ['破防了，这句金句我存了', '先专业后破防，知乎！', 'NPC 被开导得明明白白'],
    counsel_fail: ['答非所问，尬住了', '这开导像在教鱼爬树', 'NPC：？'],
    flaw: ['？？？？这信息量', '快看快看，系统音不对劲', '我嗅到了 Boss 的味道', '叮——你被盯上了'],
    vote: ['投票了投票了', '我有一票，不知当投不当投', '让子弹飞一会儿'],
    boss: ['！！！！！', '我就说系统音有问题！', '看山：策划你的策划', '《论一个 DM 的自我修养》', '全场最佳：这条鱼干']
  };

  /* ---------- DM 台词 ---------- */
  const dmLines = {
    roundStart: ['叮——新的一轮开始。搜索、对话、思考，都在消耗行动点哦。', '叮——系统提醒：热搜又更新了，谣言不会自己辟谣。', '叮——门禁状态：锁定。原因保密（自称）。', '叮——本轮行动点已刷新。别浪费，鱼干 watching you。'],
    act2: ['叮——第二幕开启。听说记忆也可以被搜索……被修复。', '叮——温馨提示：有人昨晚的记忆和今晚对不上了。谁呢？不告诉你。'],
    act3: ['叮——第三幕。热搜后台的灯，今晚亮得格外理直气壮。', '叮——辟谣通道开启。知识卡带了吗？没带的话，建议现在去心晴自习室补课。'],
    flaw: ['叮——（系统音出现了 0.3 秒的卡顿。）', '叮——该记录……建议您忘了它。', '叮——（风扇声突然大了一拍。）']
  };

  /* ---------- 结局 ---------- */
  const endings = [
    { id: 'perfect', name: '完美还原', desc: '指认命中，truth_node 覆盖 ≥90%。水军链路完整出土，档案局大门在掌声中解锁。', cls: 'good' },
    { id: 'truth', name: '真相大白', desc: '指认命中，证据链基本闭合。主要真相水落石出，个别细节成为永远的都市传说。', cls: 'good' },
    { id: 'redeem', name: '沉冤得雪', desc: '指认错了人，但被裹挟的流量酱/路人甲 当场跳反，供出真正的水军头子矩阵_K。错靶子，中要害。', cls: 'good' },
    { id: 'pollution', name: '污染胜利', desc: '热度被成功带偏到 90+，谣言完成合围。你们在热搜里生活，在真相里失踪。', cls: 'bad' },
    { id: 'chapter7', name: '隐藏·被删的第 7 章', desc: '盐言彩蛋线 5 碎片集齐。笔上仙在全员面前读完了那一章——欲知后事，后事已至。', cls: 'gold' },
    { id: 'sunshine', name: '隐藏·全员心晴', desc: '知识开导 4+ 人。看山自己推门回来："我就是出去买了袋鱼干，你们倒把我局给破了？"', cls: 'gold' },
    { id: 'fish', name: '隐藏·看山的鱼干', desc: '沉底君好感拉满 + V587 三层真身揭穿。看山把最后一袋彩虹鳟鱼味鱼干留在工位——真相要追，鱼干也要吃。', cls: 'gold' },
    { id: 'kanshan', name: '终极·看山还是山', desc: '指认 DM 成功。系统提示音换成人声："你们破的局，正是我设的局。"污染源当场抓获，全员毕业出局。', cls: 'boss' },
    { id: 'mock_dm', name: '欢乐·你连 DM 都想锤？', desc: '破绽不足就发起指认 DM。看山笑出声："证据呢？鱼干都不够塞牙缝。"全员喷子结局，不惩罚，有梗。', cls: 'fun' },
    { id: 'hung', name: '悬而未决', desc: '票数分裂，真相随夜色搁置——平票也是一种答案。', cls: 'fun' },
    { id: 'wrong', name: '欢乐·全员喷子结局', desc: '指认失败。DM 逐个锐评推理翻车现场：某人的证据链，纯度堪比 Filter 区。', cls: 'fun' }
  ];

  /* ---------- 署名区 ---------- */
  const credits = {
    salt: [
      { work: '《不提分就出不去的房间》', note: '作者灯灯 · 三幕密室框架缝合来源' },
      { work: '《穿越大明，我被崇祯偷听心声》', note: '作者凉风有信 · 双层记忆/心声泄露缝合来源' },
      { work: '《咪假虎威》', note: '作者反骨 · 阵营误会喜剧缝合来源' },
      { work: '《学科修仙》', note: '作者六酒 · 知识卡升级体系缝合来源' }
    ],
    knowledge: ['杨毅', '曾旻', '潘幸知', '窦泽南', '黛西巫巫', '草芽君Psy', '王明伟', '刀熊说说', '胡慎之心理', '杨萃先'],
    ip: '刘看山形象经官方授权使用（黑客松 IP 资源）· 演绎为机智正面',
    small: '本局由刘看山亲自策划——策划你的策划。'
  };

  /* ---------- 复盘时间线（表层真相） ---------- */
  const reviewTimeline = [
    { time: '20:05', text: '看山发放『存证芯片巡查表』："今晚对完最后一柜就放假。"' },
    { time: '21:00', text: '看山进档案室核对最后一柜，随后人间蒸发；全息横幅【不出真相，不出此门】亮起，指令来源 KS-000。' },
    { time: '21:07-21:15', text: '监控出现 8 分钟人为删除空洞，操作账号：KS-000（局长级令牌）。' },
    { time: '21:10-21:25', text: '流量酱进热搜后台批量刷水军帖——口供却称"一直在茶水间"。' },
    { time: '21:12', text: 'V587 在大厅"吃瓜"，实为记录观察笔记（No.7）。' },
    { time: '21:15', text: '路人甲代签快递时，瞥见一个毛茸茸的背影闪向档案室方向。' },
    { time: '21:20', text: '服务器机房异常高负载 4 分钟。' },
    { time: '21:28', text: '沉底君在档案室撞见暗门动静，躲到书架后没敢出声。' },
    { time: '21:40', text: '盐值君发现门禁被最高权限令牌接管，纠结 7 分钟才留下"建议关注"。' },
    { time: '21:45', text: '笔上仙抱草稿上天台吹风找灵感。' },
    { time: '22:00', text: '知之者借口洗手间，溜到热搜后台二次核对数据。' },
    { time: '22:30', text: '看山Bot 执行「主人级指令」删除备份日志与自身缓存，固执地留下哈希值。' },
    { time: '23:00', text: '封控确认无法解除——游戏开局：不出真相，不出此门。' }
  ];

  /* ---------- Boss 揭示演出台词 ---------- */
  const bossLines = [
    '叮——检测到 5/5 个破绽。',
    '叮——系统提示音自检完毕……校验人：刘看山。',
    '嗯，不用再"叮"了。是我。',
    '大门是我锁的，监控是我删的，鱼干……也是我买的。',
    '我假装修失踪，是为了让污染行为在局内自然复发、当场现形。',
    '你们破的局，正是我设的局。',
    '恭喜——你们通过了档案局最难的一场考试：在热度里保持清醒。',
    '现在，指认你的答案吧。或者，先吃袋鱼干再指认。'
  ];

  /* ---------- 破绽元数据 ---------- */
  const flaws = [
    { id: 'flavor_1', name: '鱼干口味口误', hint: '只有失踪者才知道的口味，出现在了"系统"的横幅上。' },
    { id: 'flavor_2', name: '最高权限删除', hint: '删除监控的账号，权限高到只剩一个人。' },
    { id: 'flavor_3', name: '主人级签名', hint: 'Bot 日志被删前后，有一位"主人"签了名。' },
    { id: 'flavor_4', name: '唤醒词彩蛋', hint: '锁门系统的唤醒词，试着在对话框喊喊看。' },
    { id: 'flavor_5', name: '策划签名', hint: '某份策划案的落款，笔迹张扬。' }
  ];

  const saltFragments = ['碎片①手稿残页', '碎片②章节名', '碎片③主角独白', '碎片④伏笔批注', '碎片⑤完整尾声'];
  const salt7Ids = ['salt_f1', 'salt_f2', 'salt_f3', 'salt_f4', 'clue_022'];

  /* ============================================================
   * V31 增量数据池（E 前端组 mock 供体；结构对齐引擎裁决与 D 文案池 segments_p1/p2.md）
   * ============================================================ */
  /* 抽风池（glitch）：惩罚 / 故障 / 奖励 三池，effect: ap_free | heat_bump | none */
  const glitch = {
    punish: [
      { glitch: '【惩罚：围观鱼干一分钟】', rewrite: '【惩罚：认真搜证】——"围观可以，别偷吃。"', effect: 'none' },
      { glitch: '【惩罚：大声朗读《如何走出职业倦怠》第 1 段】', rewrite: '【惩罚：认真搜证】——"朗读太残忍，念完你们真的会倦怠。"', effect: 'none' },
      { glitch: '【惩罚：向折叠区怨灵道歉】', rewrite: '（沉底君抢答）"不必了。[该道歉已被折叠]"', effect: 'none' },
      { glitch: '【惩罚：本条已打码】', rewrite: '【惩罚：本条继续打码】→【惩罚：认真搜证】——"系统今天的码先打为敬。"', effect: 'none' },
      { glitch: '【惩罚：和 AI 比心算】', rewrite: '【惩罚：认真搜证】——"算了吧（字面意思）。"', effect: 'none' }
    ],
    fault: [
      { glitch: '【叮——本轮行动点 3。错了，是 3。又错了，还是 3。】', rewrite: '叮——别数了，行动点没错，错的是你们对系统的信任。', effect: 'none' },
      { glitch: '【叮——检测到 0 名嫌疑人正在 1 名嫌疑人身上。】', rewrite: '叮——修正：0 名嫌疑人正在 1 名嫌疑人身上。祝排查愉快。', effect: 'none' },
      { glitch: '【不出真相，不出此门】→【不出此门，不出真相】→【不出门，出真相？】', rewrite: '【不出真相，不出此门】"别念了，念反了也不开门。"', effect: 'none' },
      { glitch: '【叮——档案局温馨提示：真相在楼下，此门也在楼下。祝好运。】', rewrite: '叮——撤回。真相在你们手里，门在楼下，逻辑闭环。', effect: 'none' }
    ],
    bonus: [
      { glitch: '【叮——抽风补偿：本次抽风太精彩，下次行动免扣。】', rewrite: '"是的，抽风也能抽到福利。本系统的 bug 都带薪。"', effect: 'ap_free' },
      { glitch: '【叮——抽风加成：本话题意外加热 +3。】', rewrite: '叮——热度不是我要涨的，是它自己抽风涨的。', effect: 'heat_bump' },
      { glitch: '【叮——抽风双重奏：免扣 + 加热同时触发。】', rewrite: '"建议截图，系统自己都不知道下一次是啥时候。"', effect: 'ap_free' }
    ],
    dmBottom: '是的，抽风也能抽到福利。本系统的 bug 都带薪。'
  };
  /* 押注池（弹幕押注，单位=赞数；A 裁决 #3：不与热度/行动点混币） */
  const betLines = {
    open: ['叮——押注通道开启：本轮你信谁的口供？币种：赞数，自付盈亏。'],
    win: ['叮——眼光毒辣。赔付按池子比例到账，赞数不赊账。'],
    lose: ['叮——押错了。本金已充公，奖励：一段 AI 免费锐评（不接受退款）。'],
    heat: ['叮——本话题因押注升温 +{n}（1~5，随参与人数封顶）。'],
    streak: ['他坐得笔直，你押得笃定。——「坚定保皇党」成就进度（弹幕刷屏）'],
    subjects: [
      { subject: '本轮你信谁的口供？', options: ['char_04', 'char_03', 'char_02'] },
      { subject: '监控删除的幕后主使是谁？', options: ['char_03', 'char_01', 'char_06'] },
      { subject: '谁最有可能是水军头子？', options: ['char_03', 'char_07', 'char_08'] },
      { subject: '今晚谁的行踪最可疑？', options: ['char_05', 'char_04', 'char_02'] },
      { subject: '天台鱼干是谁放的？', options: ['char_01', 'char_06', 'char_03'] }
    ]
  };
  /* 急诊红灯（开导失败 → 红灯；下一轮内抢救成功 = 双倍） */
  const erLines = {
    light: '叮——急诊警报：{name} 心病恶化，红灯亮起。下一轮内带对口知识卡抢救=收益翻倍；拖过本轮，红灯转为"长明灯"（不翻倍，也不会死——档案局没有坏结局，只有好笑的结局）。',
    dmMock: ['上一轮的开导不是没用，是把话塞反了。', '现在不是尴尬，是病危（戏剧性病危）。'],
    rescue: '叮——抢救成功！双倍收益已到账，红灯转"心晴绿"。',
    rescueTag: '这次不是尬聊，是急救。',
    expire: '叮——红灯转为"长明灯"：{name} 的抢救窗口已过（不翻倍，也不死，就是灯一直亮着，怪亮的）。',
    limit: '叮——同一 NPC 每局只挂一次急诊灯。本次失败进入纯群嘲频道，请欣赏。',
    mocks: ['这开导和没开导一样，但收费一样。', '答非所问预警——预警解除了，已实锤。', '建议把这张卡裱起来，提醒自己知识要用对口。'],
    status: {
      char_01: { red: '开始引用错误数据（"据不可靠统计……"），被弹幕当场抓包', saved: '数据回来了，人回来了。' },
      char_02: { red: '欲知后事卡壳三次，改口"欲知前事"', saved: '后事有了：就是抢救成功这件事本身。' },
      char_03: { red: '说话 #话题# 断在半截', saved: '#抢救成功#——这话题我先蹭为敬。' },
      char_04: { red: '"我记不清了"复读超过 5 次', saved: '这次，我记清了。' },
      char_05: { red: '诚实协议冲突卡顿升至 1.2 秒', saved: '卡顿解除。谢谢你们，人类。' },
      char_06: { red: '"[该发言已被折叠]"变成"[该发言已被双折叠]"', saved: '[该发言已被展开]（他愣住，全场安静一秒）' },
      char_07: { red: '客套话退化到"您好"两个字', saved: '请问还有其他可以帮您？——这次是真心的。' },
      char_08: { red: '感叹号开始漏气（"新人报道。"）', saved: '新人报道！！（气又回来了）' }
    }
  };
  /* 头条竞标（出价=行动点，平价先到先得；中标帖 heat_delta 翻倍；流拍 +2）
   * 话题池/文案对齐 D 组 segments_p1.md §三（8 话题，#8 纯欢乐位不进热度结算） */
  const headlineTopics = [
    { topic: '《谁最了解看山》', note: '官方下场辟谣过 3 次的那种话题' },
    { topic: '《监控空洞之谜》', note: '8 分钟空洞，全网找帧' },
    { topic: '《水军矩阵 47 号疑云》', note: '一个人一个师' },
    { topic: '《记忆芯片编辑术是科幻还是事故》', note: '科幻区与事故科同时在线' },
    { topic: '《折叠区冤案再调查》', note: '沉底君关注度 +1' },
    { topic: '《新用户 V587 的人设谜团》', note: '注册一天热度登顶，数据奇迹' },
    { topic: '《档案局服务质量大赏》', note: '门：谢谢，别投我' },
    { topic: '《本局最想请客吃饭的人》', note: '纯欢乐位：不进热度结算，只进友谊结算', fun: true }
  ];
  const headlineLines = {
    open: '叮——本轮头条位开标：《{topic}》。出价以行动点计，平价先到先得——手速就是公信力。温馨提示：头条不保证真相，只保证热度。',
    win: '叮——本轮头条由你拍得，帖已置顶、热度翻倍。网友锐评：热度面前人人平等，事实面前手快有手慢无。',
    lose: '叮——流拍。头条位空着，热度自己涨了 2——热搜从来不等谁。',
    outbid: '出价慢了半拍。下次记得，热搜不等人。',
    aiBid: ['（热搜后台某个号默默出了 {n}AP）', '（水军矩阵集体举手：{n}AP）', '（某位不愿透露姓名的官方号：{n}AP）']
  };
  /* P3 鱼干寻物支线（collectibles_p3.md 对接 JSON 落地）：微光点锚点 / 拾取台词 / Bot 反应 / 隐藏语音 4+1 段 */
  const fishCollectibles = [
    {
      id: 'fish_01', loc: 'loc_locker', scene: 'parcel_locker', act: 1, glow: '1s',
      anchor: '第三排最右柜门底部缝隙',
      pos: { x: 84, y: 78 },   // 搜证面板场景图内锚点位置（百分比）
      pickup: '（袋角从柜缝里露出来，标签写着——）"应急口粮·勿动，动了我知道。——K"',
      dm: '知道什么？说清楚啊！',
      bot: '检测到物品位移：应急口粮一号。处理建议：物归原主。……查询失败：原主失联。已改为：替他保管。'
    },
    {
      id: 'fish_02', loc: 'loc_roof', scene: 'roof', act: 2, glow: '2s',
      anchor: '压着残页的那块石头下缘',
      pos: { x: 30, y: 62 },
      pickup: '（石头下面除了残页，还压着一小袋）"天台配给·风大，抱着吃。——K"',
      dm: '连吃鱼干都有仪式感。',
      bot: '检测到物品位移：天台配给。备注栏写着\'风大，抱着吃\'。逻辑评估：这是一个会替鱼考虑风的……人。'
    },
    {
      id: 'fish_03', loc: 'loc_clinic', scene: 'study_room', act: 3, glow: '1.6s',
      anchor: '书架第二层《如何走出职业倦怠》书脊后',
      pos: { x: 72, y: 40 },
      pickup: '（书后面滑出一袋）"治愈系配给·看完第一章再吃，效果更佳。——K"',
      dm: '原来《职业倦怠》是佐餐读物。',
      bot: '检测到物品位移：治愈系配给。关联借阅记录：本周它借出 3 次，无人归还问题，无人追问内容。结论：治愈，但没人知道被治愈的是谁。'
    }
  ];
  /* 集齐 3 袋 → 看山Bot 隐藏语音（Boss 线暖场，切片逐句播不合并；语音 5 为终极层加播） */
  const fishVoiceLines = [
    { t: '0-4s', text: '检测到：三袋鱼干归位。逻辑更新——失踪的人没有带走它们。一个出远门的人，会带上自己最重要的东西。' },
    { t: '4-8s', text: '检索历史指令库：三袋鱼干的放置位置，分别在\'会被路过的地方\'\'会被风吹到的地方\'\'会被翻开的地方\'。这是个奇怪的藏法——像是……希望被发现。' },
    { t: '8-12s', text: '查询我的诚实协议：以上陈述均为事实。查询我的感受协议：未安装。但系统日志显示，我在生成这段语音时，风扇转速很平稳。' },
    { t: '12-16s', text: '最后一条备注，标签：\'给找到它们的人\'——\'谢谢你替我保管。线索已经给了，剩下的，看你们自己。呵，金枪鱼味。\'……该备注的口吻相似度匹配结果：与 DM 系统音，97.2%。本条仅播一次，日志不留档——这是我能做的，最大限度的守护。' }
  ];
  const fishVoiceBossExtra = '主人回来了。根据协议，我应当汇报：这三袋鱼干，我替你守住了。另外——\'呵，金枪鱼味\'这句台词，你说得很像本人。建议下次直接自己说。';
  const fishAchievement = { id: 'ach_yuganxianren', name: '鱼干线人', icon: '🐟', desc: '集齐 3 袋鱼干收集品，解锁看山Bot 隐藏语音' };
  /* 反诈剧场（辟谣成功 30% 触发，每局 ≤2 次；三幕剧本对齐 segments_p2.md） */
  const antifraudScript = [
    {
      title: '第一幕《知情人》——拆"冒充内部"',
      lines: [
        '（灯光起。水军 A 号登台，压低声音）"我跟你说，我二舅在档案局看大门——看山其实是……"',
        '（DM 叮一声打断）"叮——请出示内情证明。"',
        '（A 号掏出）"我朋友的同学的猫认识看山。"',
        '（DM）"叮——查无此猫。话术拆解第一条：越说『知情人』，越查无此人。真实信息有出处，可疑信息只有『我朋友』。"',
        '（弹幕）"学到了，下次让他把猫叫出来对质。"'
      ],
      quiz: { q: '「我二舅在档案局看大门」属于哪类话术？', opts: ['冒充内部 / 知情人人设', '权威包装', '制造恐慌'], ans: 0 }
    },
    {
      title: '第二幕《倒计时》——拆"制造恐慌"',
      lines: [
        '（水军 B 号敲锣）"最后三天！档案局要出大事！再不转发你的记忆就要被编辑了！"',
        '（DM 叮）"叮——倒计时已暂停。话术拆解第二条：让你慌的不是事件，是截止时间。真通知从不催你转发，催你转发的都在冲 KPI。"',
        '（B 号锣掉地上）"……我这就下岗了。"',
        '（弹幕）"锣挺好，下回用竹板。"'
      ],
      quiz: { q: '"再不转发就……"式话术的核心武器是？', opts: ['数据', '截止时间制造的恐慌', '文学性'], ans: 1 }
    },
    {
      title: '第三幕《大 V 保平安》——拆"权威包装"',
      lines: [
        '（水军 C 号西装革履）"我是十年老号，数据百万，我说看山卷款跑路，还能有假？"',
        '（DM 叮）"叮——调取设备指纹：47 号同源。话术拆解第三条：头衔可以买，矩阵骗不了设备指纹。听谁的？听先问是不是的。"',
        '（C 号西装滑落，里面是 47 件同款马甲）"……叠穿而已，时尚单品。"',
        '（全体谢幕，横幅）【真相不转发，谣言必被辟。求真之路，从点开第一条证据开始。】'
      ],
      quiz: { q: '识破"十年老号大 V"的关键是？', opts: ['看粉丝数', '查设备指纹与同源矩阵', '看西装是否合身'], ans: 1 }
    }
  ];
  antifraudScript.settleOk = '叮——反诈学分 +1。成就进度：反诈先锋（1/1）。';
  antifraudScript.settleFail = '记住了：慌，就是话术的一部分。';
  /* 侦探证（登录后；警衔=headline 欢乐映射，隐私只取公开三件套） */
  const dossierRanks = [
    { test: /码农|程序员|工程师|开发|debug|调试/i, rank: '调试人生司司长' },
    { test: /学生|硕士|博士|大学|考研/i, rank: '求真档案局·见习侦探' },
    { test: /运营|小编|新媒体/i, rank: '热搜水位观察员' },
    { test: /老师|教师|教授/i, rank: '心晴诊室·荣誉主治医师' },
    { test: /产品|经理/i, rank: '需求翻译官（高级）' },
    { test: /设计|美术|视觉|UI/i, rank: '视觉证据科科长' },
    { test: /老板|ceo|创始人|cto/i, rank: '鱼干预算委员会主席' },
    { test: /金融|投资|量化/i, rank: '真伪信息风控师' },
    { test: /律师|法务/i, rank: '档案局纪律委员会顾问' },
    { test: /医生|护士|健康/i, rank: '心晴急诊室值班医师' }
  ];
  const dossierFallbackRanks = ['首席荣誉侦探（自封）', '鱼干线索特别调查员', '弹幕意识观察员', '折叠区巡夜人', '热度降噪工程师'];
  const dossierAvatars = [
    { id: 'kanshan', name: '看山本山', src: '/assets/official/kanshan/kanshan_portrait.png' },
    { id: 'beijixiong', name: '北极熊', src: '/assets/official/kanshan/beijixiong.png' },
    { id: 'liubaba', name: '刘巴巴', src: '/assets/official/kanshan/liubaba.png' },
    { id: 'liumama', name: '刘妈妈', src: '/assets/official/kanshan/liumama.png' },
    { id: 'qie', name: '企鹅', src: '/assets/official/kanshan/qie.png' },
    { id: 'yanou', name: '燕鸥', src: '/assets/official/kanshan/yanou.png' }
  ];
  const dossierLine = (name) => `路人甲："等等，你简介写着『${name}』？大佬怎么也被锁进来了。"（个性化彩蛋：每人不同）`;
  /* 终局陈词（60s + 锤人分池；不影响指认，影响群嘲结局与成就） */
  const closingLines = {
    open: '叮——最后陈词：每人 60 秒，说点想让人记住的。弹幕同步开启"最想锤的人"分池投票——不影响指认，但影响你复盘时的社交死亡程度。',
    mock: ['这 60 秒的信息量，比前五轮加起来还大。', '有人陈词，有人忏悔，有人点播广播台。'],
    settle: '叮——"最想锤的人"已选出：{who}（弹幕锤声一片）。别慌，锤你说明你有热度。'
  };
  /* 徽章定义（侦探报告/分享卡用；与 achievements.md 枚举对齐的 mock 子集） */
  const badgeDefs = [
    { id: 'ach_baolei', name: '带节奏之王', icon: '♪', desc: '污染胜利局主谋级操作' },
    { id: 'ach_xinqing', name: '心晴医师', icon: '♥', desc: '开导 4+ 人全员心晴' },
    { id: 'ach_kanshan', name: '看山还是山', icon: '◉', desc: '指认 DM 成功' },
    { id: 'ach_yugan', name: '鱼干守护者', icon: '🐟', desc: '全线索收集' },
    { id: 'ach_dingzi', name: '时间线钉子户', icon: '⌛', desc: '记忆拼图全场排对' },
    { id: 'ach_anfang', name: '暗房大师', icon: '▣', desc: '干净暗拍 ≥3 次未被拆穿' },
    { id: 'ach_gongdi', name: '全场公敌', icon: '☄', desc: '"最想锤的人"票数 ≥4 且存活' },
    { id: 'ach_chenci', name: '黄金六十秒', icon: '⏱', desc: '终局陈词被弹幕点名表扬' },
    { id: 'ach_fanzha', name: '反诈先锋', icon: '✚', desc: '反诈剧场全对' },
    { id: 'ach_baohuang', name: '坚定保皇党', icon: '⚑', desc: '连续 3 轮押同一人且其最终无辜' },
    { id: 'ach_yuganxianren', name: '鱼干线人', icon: '✦', desc: '集齐 3 袋鱼干，解锁看山Bot 隐藏语音' }
  ];
  /* 复盘页常驻署名小字（D 对接点：flavor_5 落款 + 盐言三作，任何状态常驻显示） */
  const flavor5Credit = 'flavor_5 · 策划案落款：《档案局封闭压力测试·策划案》总策划——刘看山（本局由刘看山亲自策划：策划你的策划）。剧情设定致敬盐言故事《不提分就出不去的房间》作者灯灯 / 《穿越大明，我被崇祯偷听心声》作者凉风有信 / 《咪假虎威》作者反骨。';

  return { IMG, BUST, prologueSteps, locations, chars, truthNodes, clues, kcards, memories, posts, ambient, danmaku, dmLines, endings, credits, reviewTimeline, bossLines, flaws, saltFragments, salt7Ids, glitch, betLines, erLines, headlineTopics, headlineLines, antifraudScript, dossierRanks, dossierFallbackRanks, dossierAvatars, dossierLine, closingLines, badgeDefs, flavor5Credit, fishCollectibles, fishVoiceLines, fishVoiceBossExtra, fishAchievement };
})();
