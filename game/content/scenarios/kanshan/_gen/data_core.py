# -*- coding: utf-8 -*-
"""kanshan 剧本核心数据：scenario / truth / timeline。仅 kanshan/_gen 内使用。"""

SCENARIO = {
    "id": "kanshan",
    "title": "求真档案局 · 看山失踪夜",
    "genre": "欢乐阵营机制推理 · AI 原生",
    "ip_source": "盐言故事×4（灯灯/凉风有信/反骨/六酒，署名见 scripts/credits.md）+ 知乎知识×10（草芽君Psy/杨毅/曾旻Zeng Min/潘幸知/窦泽南/黛西巫巫/王明伟/刀熊说说/胡慎之心理/杨萃先）+ 刘看山 IP（黑客松官方授权）",
    "player_count_min": 1,
    "player_count_max": 8,
    "ai_npc_count": 8,
    "duration_minutes": 120,
    "difficulty": "进阶（欢乐外壳+三层真相）",
    "summary": "周五盘点夜，知乎拟人都市的求真档案局被全息横幅【不出真相，不出此门】锁死，首席侦探刘看山 21:00 进档案室后人间蒸发。8 名被困者口供对不上、监控 21:07–21:15 被挖空、热搜被水军带偏。玩家在 AI DM『系统提示音』的控场下搜证、修复记忆、开导心病、打舆论战——直到发现：你们破的局，正是看山设的局。",
    "modes": {
        "main": "主线本：三幕全流程 + 隐藏支线（被删的第 7 章）+ 终极层（指认 DM），内容预算约 120 分钟",
        "daily": "每日挑战：以当日知乎热榜词条生成 1 个衍生谣言帖与 1 条知识卡组合题，单幕 30 分钟",
        "quick": "快速局：跳过破冰，直接搜证+心声+舆论，线索池减半、破绽链保留 3 条，约 30 分钟"
    },
    "acts": [
        {"id": "act1", "name": "第一幕·出不去的档案局", "stage": "break_ice", "actions_allocated": 9,
         "brief": "锁门+失踪开场，横幅梗【不出真相，不出此门】与 DM『叮——系统提示音』人格上线（缝合《不提分就出不去的房间》·灯灯）"},
        {"id": "act2", "name": "第二幕·心声泄露", "stage": "investigate", "actions_allocated": 12,
         "brief": "记忆修复解锁 said/heart 双层，篡改点=口供与心声矛盾处（缝合《穿越大明，我被崇祯偷听心声》·凉风有信）"},
        {"id": "act3", "name": "第三幕·披着虎皮的猫", "stage": "round_table", "actions_allocated": 9,
         "brief": "舆论战终局：水军/辟谣/热度值，揭面横幅【原来你是披着虎皮的猫】（缝合《咪假虎威》·反骨）"},
        {"id": "act4", "name": "终局·指认与揭面", "stage": "accuse", "actions_allocated": 3,
         "brief": "指认结算 + 心晴诊室 + 复盘署名区；破绽≥5 解锁【指认：DM 刘看山】"}
    ],
    "scene_map": {
        "desk_kanshan": {"name": "看山工位", "type": "crime_scene",
                         "clue_pool": ["clue_002", "clue_007", "clue_028"], "image": "assets/images/scene_desk_kanshan.png"},
        "server_room": {"name": "服务器机房", "type": "crime_scene",
                        "clue_pool": ["clue_010", "clue_013", "clue_030"], "image": "assets/images/scene_server.png"},
        "roof": {"name": "天台", "type": "base",
                 "clue_pool": ["clue_021"], "image": "assets/images/scene_roof.png"},
        "reception": {"name": "前台", "type": "base",
                      "clue_pool": ["clue_001", "clue_015"], "image": "assets/images/scene_reception.png"},
        "teahouse": {"name": "茶水间", "type": "base",
                     "clue_pool": ["clue_006"], "image": "assets/images/scene_teahouse.png"},
        "archive_room": {"name": "档案室", "type": "crime_scene",
                         "clue_pool": ["clue_004", "clue_017", "clue_018", "clue_020"], "image": "assets/images/scene_archive.png"},
        "monitor_room": {"name": "监控室", "type": "crime_scene",
                         "clue_pool": ["clue_009", "clue_029"], "image": "assets/images/scene_monitor.png"},
        "hotfeed_backstage": {"name": "热搜后台", "type": "crime_scene",
                              "clue_pool": ["clue_005", "clue_012", "clue_014"], "image": "assets/images/scene_hotfeed.png"},
        "hvac_room": {"name": "空调机房", "type": "base",
                      "clue_pool": ["clue_003"], "image": "assets/images/scene_hvac.png",
                      "flavor_note": "环境线索池含『二十年前的大力丸』（欢乐彩蛋，无案情信息）"},
        "parcel_locker": {"name": "快递柜", "type": "base",
                          "clue_pool": ["clue_011", "clue_016"], "image": "assets/images/scene_locker.png"},
        "study_room": {"name": "心晴自习室", "type": "base",
                       "clue_pool": ["clue_008", "clue_019"], "image": "assets/images/scene_study_room.png",
                       "flavor_note": "搜证动作=抽知识卡（10 张，随机未持有卡），对应 KNOWLEDGE_SYSTEM 心病匹配表"},
        "director_office": {"name": "局长办公室", "type": "hidden",
                            "unlock_condition": "持有知识卡 kc_10《打造职业发展的金字塔》并按金字塔层级序输入密码（黄金→砖→泥的倒序）",
                            "clue_pool": [], "image": "assets/images/scene_director_office.png",
                            "flavor_note": "演出用隐藏房间：内有看山的策划手稿《钓鱼执法·卷一》与一袋彩虹鳟鱼味鱼干，供终极层揭面演出，不设可搜线索"}
    },
    "image_map_note": "立绘 avatar 与场景 image 均出自 content/assets/images/（A 组 asset_gen 管线已生成）；2026-09-13 修复：12 房间 image 一一对应专属场景图，scene_hall.png 保留作大厅兜底。",
    "system_npcs": [
        {"id": "archiv3", "name": "Archiv3", "desc": "档案局系统人格，广播腔，负责封控播报与横幅渲染（无角色卡，演出型 NPC）"},
        {"id": "dm", "name": "系统提示音（=刘看山）", "desc": "AI DM 伪装人格：『叮——』腔调控场；终极层揭面为看山本人声音（见 DM_BOSS_DESIGN）"}
    ],
    "condition_grammar": "unlock_condition 语法：『默认』| evidence:<clue_id> | memory:<char_id>:<version> | counsel:<kc_id> | boss:flaw_count>=<n> | chat:keyword_<关键词> | review:credits。chat/review 为本剧本新增语法（对话框触发/复盘页触发），B 组引擎按此实现。",
    "content_safety": "欢乐向：所有角色为知乎拟人化虚构形象，不映射、不攻击任何真实用户；伪造线索与水军帖均标注 is_fake/fake_of 供引擎与前端识别；引用盐言/知乎知识处保留作者署名（见 scripts/credits.md）。",
    "difficulty_note": "三幕 + 终局共 33 行动点；破绽链 5 条、彩蛋碎片 5 枚、辟谣目标帖 10 条，全部可离线由引擎判定；AI 只扩写 flavor 不改 fact。"
}

TRUTH = {
    "truth_summary": "表层：资深答主『知之者』因流量焦虑堕落为水军头子（矩阵_K），遥控被裹挟的流量酱刷帖删记录、篡改记忆存证；看山Bot 只是执行『主人级指令』的傀儡。里层：整场失踪与封局是刘看山自导自演的钓鱼执法——他假失踪、锁大门、扮系统提示音，钓出记忆编辑产业链，顺便逼 8 个人直面被信息污染的心病。你们破的局，正是看山设的局。",
    "culprit": {
        "character": "char_01",
        "name": "知之者（真水军头子『矩阵_K』）",
        "crime": "组织水军污染信息 + 指使篡改记忆存证",
        "motive": "十年答主流量下滑，陷入『有热度才有一切』的稀缺心态；怕看山查到记忆编辑灰色产业、掀出当年成名作的数据造假，先下手为强",
        "method": "以 47 个设备指纹同源的马甲号组成水军矩阵带节奏；遥控流量酱在 21:10-21:25 用热搜后台『热度管理工具』刷帖删记录并篡改其本人与路人甲的记忆存证；借 V587 的误会把水军线往新人身上引",
        "accomplices": [
            {"character": "char_03", "name": "流量酱", "role": "执行者（被裹挟者，可策反）", "swayable": True},
            {"character": "char_04", "name": "路人甲", "role": "被忽悠自改口供的目击者（被裹挟者，可策反）", "swayable": True}
        ],
        "evidence_chain": ["clue_005", "clue_012", "clue_014", "clue_015"]
    },
    "boss_layer": {
        "boss": "kanshan（刘看山）",
        "title": "DM = 最大隐藏 Boss（非反派：设局的求真侦探）",
        "motive": "正面动机：发现档案局混入记忆编辑产业链，打草惊蛇会跑——于是自导自演失踪，把所有人锁进『出不去的档案局』，让污染行为在局内自然复发、当场现形，顺便逼 8 个人直面自己被信息污染的心病",
        "method": "假失踪（21:00 从档案室暗门进入局控室）；亲手写【不出真相，不出此门】横幅并启用唤醒词『看山，关门』；扮『叮——系统提示音』DM 人格控场；令看山Bot 删除 21:07-21:15 监控与自身缓存以防穿帮；雇 V587 扮新人做局内眼",
        "reveal_condition": "集齐 5 个 boss_flaw 线索（flavor_1..5）→ 指认阶段解锁【指认：DM 刘看山】",
        "signature_quote": "你们破的局，正是看山设的局。",
        "fail_branch": "破绽不足 5 时指认 DM → 群嘲结局『你连 DM 都想锤？』（欢乐向，不惩罚）",
        "flaws": [
            {"id": "flaw_1", "name": "鱼干口味口误", "clue": "clue_028",
             "desc": "第一幕 DM 吐槽说漏『看山只吃彩虹鳟鱼味』——只有失踪者本人才知道"},
            {"id": "flaw_2", "name": "最高权限删除", "clue": "clue_029",
             "desc": "删除监控的 KS-000 是局长级令牌，全局仅看山掌握"},
            {"id": "flaw_3", "name": "主人级签名", "clue": "clue_030",
             "desc": "看山Bot 被删日志指令头带『主人级指令 KS-000』签名（需知识卡 kc_06 开导看山Bot 后出现）"},
            {"id": "flaw_4", "name": "唤醒词彩蛋", "clue": "clue_031",
             "desc": "玩家在对话框试出『看山，关门』，系统口误回弹"},
            {"id": "flaw_5", "name": "策划签名", "clue": "clue_032",
             "desc": "复盘页署名列表底一行小字：『本局由刘看山亲自策划——策划你的策划。』"}
        ]
    },
    "truth_nodes": [
        {"id": "tn_01", "name": "看山失踪之谜", "desc": "21:00 看山进档案室后消失；请假条、鱼干罐与冰袋快递指向『有计划的离席』",
         "proof_clues": ["clue_002", "clue_004", "clue_007", "clue_011"], "npc_witness": ["char_06", "char_04"]},
        {"id": "tn_02", "name": "锁门与全息横幅", "desc": "【不出真相，不出此门】由内部最高权限令牌 KS-000 下发",
         "proof_clues": ["clue_001", "clue_003"], "npc_witness": ["char_07"]},
        {"id": "tn_03", "name": "监控删除", "desc": "21:07-21:15 监控被局长级账号人为删除，机房同期异常高负载",
         "proof_clues": ["clue_009", "clue_010", "clue_013"], "npc_witness": ["char_05"]},
        {"id": "tn_04", "name": "记忆芯片编辑", "desc": "多人记忆存证被『热度管理工具』篡改，口供与心声矛盾处即篡改点",
         "proof_clues": ["clue_014", "clue_015"], "npc_witness": ["char_03", "char_04"]},
        {"id": "tn_05", "name": "水军带节奏", "desc": "热搜热度 21:10 起非自然阶梯式增长，47 个马甲号设备指纹同源",
         "proof_clues": ["clue_005", "clue_012", "clue_014"], "npc_witness": ["char_03"]},
        {"id": "tn_06", "name": "水军头子真身", "desc": "矩阵_K 监制清单与后台操作链指向知之者",
         "proof_clues": ["clue_012", "clue_014"], "npc_witness": ["char_03"]},
        {"id": "tn_07", "name": "被裹挟者", "desc": "流量酱（把柄+人情）与路人甲（被忽悠改口供）均可策反",
         "proof_clues": ["clue_012", "clue_014", "clue_015"], "npc_witness": ["char_03", "char_04"]},
        {"id": "tn_08", "name": "V587 三层身份", "desc": "新用户→两年前被封的老号『侦探爱好者联盟』→看山的影子学徒",
         "proof_clues": ["clue_016"], "npc_witness": ["char_08"]},
        {"id": "tn_09", "name": "科技伦理·被删日志", "desc": "看山Bot 执行主人级指令删除日志，但固执地留下哈希值",
         "proof_clues": ["clue_010", "clue_013"], "npc_witness": ["char_05"]},
        {"id": "tn_10", "name": "心病图谱", "desc": "全档案局都在借心理学书——每人的心病就是线索本身",
         "proof_clues": ["clue_008", "clue_019"], "npc_witness": ["char_01", "char_02", "char_03", "char_04", "char_05", "char_06", "char_07", "char_08"]},
        {"id": "tn_egg", "name": "彩蛋线·被删的第 7 章", "desc": "笔上仙剧中剧《学科修仙》改写的 5 枚碎片（设定致敬六酒《学科修仙》）",
         "proof_clues": ["clue_017", "clue_018", "clue_019", "clue_020", "clue_021"], "npc_witness": ["char_02", "char_06"]},
        {"id": "btn_01", "name": "里层·看山设局", "desc": "假失踪+锁门+系统音=看山本人",
         "proof_clues": ["clue_028", "clue_031", "clue_032"], "npc_witness": []},
        {"id": "btn_02", "name": "里层·主人级指令链", "desc": "监控删除与日志删除同源 KS-000",
         "proof_clues": ["clue_009", "clue_013", "clue_029", "clue_030"], "npc_witness": ["char_05"]},
        {"id": "btn_03", "name": "里层·钓鱼目的", "desc": "钓出记忆编辑产业链 + 心病开导（知识卡体系）",
         "proof_clues": ["clue_008", "clue_016"], "npc_witness": []}
    ],
    "endings": [
        {"id": "ending_perfect", "name": "完美还原", "condition": "指认知之者命中 + truth_node 覆盖 ≥90%"},
        {"id": "ending_truth", "name": "真相大白", "condition": "指认命中 + 覆盖 60-89%"},
        {"id": "ending_redemption", "name": "沉冤得雪", "condition": "错误指认，但被裹挟者（流量酱/路人甲）跳反成功"},
        {"id": "ending_pollution", "name": "污染胜利", "condition": "污染阵营成功把热度带偏至终局"},
        {"id": "ending_chapter7", "name": "隐藏·被删的第 7 章", "condition": "集齐彩蛋碎片 clue_017..021（5 枚）+ kc_01 开导沉底君成功（boss_key：第 7 章答案重新上架）"},
        {"id": "ending_sunny", "name": "隐藏·全员心晴", "condition": "知识开导成功 ≥4 人：看山自己推门回来（『我就是出去买了袋鱼干，你们倒把我局给破了？』）"},
        {"id": "ending_fish", "name": "隐藏·看山的鱼干", "condition": "沉底君好感拉满 + V587 三层真身揭穿"},
        {"id": "ending_kanshan", "name": "终极·看山还是山", "condition": "指认 DM 成功（破绽 ≥5）+ 心晴诊室开导 ≥2：看山现身承认设局，污染源当场抓获，全员毕业出局——这一局的『局』本身就是最大彩蛋"},
        {"id": "ending_boss_fail", "name": "群嘲分支·你连 DM 都想锤？", "condition": "指认 DM 但破绽 <5：全场群嘲，欢乐复盘，不惩罚"}
    ],
    "attribution": "本剧本缝合改编自盐言故事：《不提分就出不去的房间》作者灯灯、《穿越大明，我被崇祯偷听心声》作者凉风有信、《咪假虎威》作者反骨、彩蛋线致敬《学科修仙》作者六酒；10 张知识卡源自知乎知识 10 篇（作者见 knowledge_cards/ 与 scripts/credits.md）。开场页与复盘页常驻署名。",
    "ai_rule": "Agent 无权改证据事实（fact 字段），只演不裁；AI 扩写仅限 flavor_hint 自由度。"
}

TIMELINE = {
    "case_time": "案发夜（周五盘点）20:00–23:00；21:00 横幅封控，23:00 确认无法解除后游戏开局",
    "timeline": [
        {"time": "20:00", "character": "archiv3", "location": "大厅", "action": "季度盘点加班开始，系统广播全员到岗", "public": True},
        {"time": "20:05", "character": "kanshan", "location": "大厅", "action": "看山宣布盘点分组，发放『存证芯片巡查表』，说『今晚对完最后一柜就放假』", "public": True},
        {"time": "20:20", "character": "char_01", "location": "大厅", "action": "知之者『顺手』安抚新人 V587，实则套话探底（说谎点：自称只是热心前辈）", "public": False},
        {"time": "20:30", "character": "char_03", "location": "茶水间", "action": "流量酱收到知之者私信暗号『周三加更』，心跳加速", "public": False},
        {"time": "20:45", "character": "char_04", "location": "前台", "action": "路人甲替盐值君代班，开始收发快递（说谎点：口供把代班说成值班）", "public": False},
        {"time": "20:50", "character": "char_07", "location": "仓库", "action": "盐值君去仓库领打印纸，20:50-21:00 有 10 分钟空档", "public": False},
        {"time": "20:55", "character": "char_06", "location": "档案室", "action": "沉底君溜进档案室，用终端给自己被折叠的第 7 章旧答『续命』重新提交", "public": False},
        {"time": "21:00", "character": "kanshan", "location": "档案室", "action": "看山宣布『去核对最后一柜档案，谁都不许跟来』，从暗门进入局控室——人间蒸发", "public": True},
        {"time": "21:00", "character": "archiv3", "location": "大门", "action": "全息横幅【不出真相，不出此门】亮起，全部出口封控；指令来源 KS-000 令牌", "public": True},
        {"time": "21:05", "character": "char_03", "location": "茶水间", "action": "流量酱泡了两包面（第二包是压惊的）", "public": False},
        {"time": "21:07", "character": "kanshan", "location": "局内各处", "action": "看山布置钓鱼现场并移形换位；同期看山Bot 按主人级指令删除该时段监控（21:07-21:15）", "public": False},
        {"time": "21:10", "character": "char_03", "location": "热搜后台", "action": "流量酱进后台批量刷水军帖（21:10-21:25），说谎点：口供称一直在茶水间", "public": False},
        {"time": "21:12", "character": "char_08", "location": "大厅", "action": "V587 在大厅『吃瓜』，实则记录『目标 A 行动』（观察记录 No.7）", "public": False},
        {"time": "21:15", "character": "char_04", "location": "快递柜", "action": "路人甲代签快递时看到一个毛茸茸的背影闪向档案室方向（关键目击，被误扫描受损）", "public": False},
        {"time": "21:20", "character": "char_05", "location": "服务器机房", "action": "服务器组异常高负载 4 分钟（看山Bot 在与指令赛跑备份）", "public": False},
        {"time": "21:28", "character": "char_06", "location": "档案室", "action": "沉底君撞见暗门动静，躲到书架后没敢出声（说谎点：初版口供称『没看清』）", "public": False},
        {"time": "21:40", "character": "char_07", "location": "前台", "action": "盐值君发现门禁被最高权限令牌接管，纠结 7 分钟（说谎点：自称 21:47『立刻』留言）", "public": False},
        {"time": "21:45", "character": "char_02", "location": "天台", "action": "笔上仙抱草稿上天台吹风找灵感", "public": False},
        {"time": "21:47", "character": "char_07", "location": "前台", "action": "盐值君在系统留言板留下『检测到异常，建议关注』", "public": True},
        {"time": "22:00", "character": "char_01", "location": "热搜后台", "action": "知之者借口洗手间溜到后台二次核对数据（说谎点：口供称全程在大厅）", "public": False},
        {"time": "22:10", "character": "char_02", "location": "档案室", "action": "笔上仙回档案室开写剧中剧《学科修仙》，写下『灵感断片』三分钟", "public": False},
        {"time": "22:30", "character": "char_05", "location": "服务器机房", "action": "看山Bot 执行主人级指令：删除 21:07-21:15 备份日志与自身缓存；偷偷留下哈希值", "public": False},
        {"time": "22:40", "character": "char_01", "location": "大厅", "action": "知之者提议全员在大厅休息等天亮；流量酱第一个赞成", "public": True},
        {"time": "23:00", "character": "archiv3", "location": "大厅", "action": "封控确认无法解除，游戏开局：不出真相，不出此门", "public": True}
    ],
    "rules": {
        "npc_statement_must_match": True,
        "player_can_challenge": "当玩家出示线索与 NPC 证词矛盾时，NPC 必须解释或修正（一致性守卫拦截穿帮）",
        "heart_layer_rule": "心声层仅在『记忆修复（2AP）/知识开导（2AP+匹配卡）』解锁后注入 NPC prompt"
    },
    "tamper_point_index": [
        {"id": "tp_01", "owner": "char_03", "desc": "流量酱：删改 21:10-21:25 后台操作记录，口供打包成『一直在茶水间』"},
        {"id": "tp_01b", "owner": "char_03", "desc": "流量酱：删掉『出后台时被知之者撞见』的尴尬细节与删帖记录的心证"},
        {"id": "tp_02", "owner": "char_04", "desc": "路人甲：代班→值班，时间 21:15→20:55 前移"},
        {"id": "tp_02b", "owner": "char_04", "desc": "路人甲：快递柜『毛茸茸背影』目击被批量优化误伤"},
        {"id": "tp_03", "owner": "char_01", "desc": "知之者：把两次短暂离席打包成『全程大厅』"},
        {"id": "tp_03b", "owner": "char_01", "desc": "知之者：22:00『接水』实为后台核对数据"},
        {"id": "tp_04", "owner": "char_05", "desc": "看山Bot：22:30『例行缓存清理』实为主人级指令触发（机器不能撒谎，只能措辞）"},
        {"id": "tp_05", "owner": "char_07", "desc": "盐值君：21:40 发现异常，21:47 才留言——『立刻』是自我美化"}
    ]
}

FILES = {
    "scenario.json": SCENARIO,
    "truth.json": TRUTH,
    "timeline.json": TIMELINE,
}
