# kanshan 产出状态（D 内容组）

> 状态：**完成（D 完成）+ 增量两批（P1/P2/P3 + minis）** · 产出日：2026-09-12 · 产出窗口：D 内容组
> 校验：JSON 资产 `python 逐文件 json.load` 121/121 通过、跨文件一致性断言 0 错误；v31 增量文案（md 内嵌 JSON 围栏/词库计数/泄底词扫描）见 §六/§七。
> 本文件按"整文件 UTF-8 重写"纪律维护（GAMEPLAY_V31 §八裁决 #1 同款规则，禁止追加式半写）。

## 一、产出清单（对照 kanshan/README.md）

| 项 | 要求 | 实际 | 状态 |
|---|---|---|---|
| scenario.json | 3 幕 / 11 地点 / main·daily·quick | 3 幕+终局（4 stage）、11 常规地点+1 隐藏房间（局长办公室）、3 模式 | ✅ |
| truth.json | 表层+里层 Boss+5 破绽伏笔链 | culprit（知之者/矩阵_K+2 被裹挟者）+ boss_layer（看山设局）+ 14 truth_nodes + flaw_1..5 + 8 结局+1 群嘲分支 | ✅ |
| timeline.json | 案发夜全员轨迹 | 24 条事件（20:00-23:00）+ 说谎点 + tamper_point_index 8 项 | ✅ |
| characters/ | 8 张角色卡 | char_01..08（faction: pollution 1 / swayable 2 / truth 5；heartache 绑定；avatar 对应 assets/images 实名文件） | ✅ |
| memory/ | 8 角色 × V1-V3 双层 | 24 文件（said/heart + integrity + diff_from_prev + 篡改点 tp_01..tp_05/tp_01b/tp_02b/tp_03b + 删除段） | ✅ |
| clues/ | 32 条（伪造 6+boss_flaw 5） | 32 = public 7 + limited 9 + hidden 彩蛋碎片 5 + fake 6 + boss_flaw 5（flavor_1..5） | ✅ |
| knowledge_cards/ | 10 张（署名必填） | kc_01..10，作者/work_id/金句×3/摘要≤100 字/心病绑定 全齐（金句取自原文） | ✅ |
| hotfeed/ | 40+ 帖 | post_001..044（44 条，轮次 1-7；水军帖 16 条全 is_fake=true；辟谣目标帖 10 条覆盖全部 10 卡 topic_tag） | ✅ |
| scripts/ | 三幕+系统音台词+演出版式+署名表 | act1_chumen.md / act2_xinsheng_xielu.md / act3_hupi_demao.md / dm_system_voice.md / counsel_clinic.md / credits.md | ✅ |

## 二、校验记录（实跑取证，JSON 批次）

1. 生成器：`_gen/generate.py`（含跨文件断言）→ `files=121 errors=0`。
   断言覆盖：线索分级计数（fake=6 / boss_flaw=5 / 总 32）、flaw_id=flavor_1..5、fake_of 与 clue_pool 引用有效、伪造线索不入池、kc binds 与 KNOWLEDGE_SYSTEM 匹配表一致、角色卡↔记忆路径↔owner 一致、帖 author_mask/is_fake/humor_tag 合法、辟谣目标帖=10（每卡 ≥1）、时间线角色合法、真相表 proof_clues 有效。
2. 独立复跑验证：对磁盘落盘文件逐个 `json.load` → `validated=121 bad=0`。
3. 首跑曾报 50 错（生成器断言自身两处归一化 bug + clue_027 误入茶水间 clue_pool）——已修复后复跑归零，记录留档以证 mutation 纪律。

## 三、关键设计决策（对接 B/C/E 组必读）

1. **真相三层**：表层凶手=知之者（水军头子"矩阵_K"）；执行者=流量酱（被裹挟，可策反）；监控/日志删除=看山Bot（执行"主人级指令"）；里层=看山自导自演钓鱼执法（假失踪+锁门+系统音）。"你们破的局，正是看山设的局。"
2. **阵营配比**：pollution=知之者 1；swayable=流量酱、路人甲 2；truth=其余 5。符合 V3"污染 2-3 人含至少 1 被裹挟者"。
3. **条件语法扩展**：unlock_condition 新增 `chat:keyword_<词>`（对话框试"看山，关门"）与 `review:credits`（复盘页小字）。其余沿用契约：默认/evidence:/memory:/counsel:/boss:。
4. **V587 三层反转**：新用户→两年前被封老号（侦探爱好者联盟）→看山的影子学徒（便签署名 K）。L2+L3 证据合并于 clue_016（公告背面委任便签）。
5. **局长办公室**：隐藏房间（type=hidden），kc_10 金字塔层级=密码序；内置演出道具（策划手稿+鱼干），不设可搜线索，故 11 常规+1 隐藏=12 节点，README"11 地点"口径不破。
6. **彩蛋碎片 5 枚**（clue_017..021）：笔上仙剧中剧《学科修仙》设定改写（六酒署名），解锁链 counsel:kc_05 → evidence → counsel:kc_01 → memory:char_02:3；碎片三即沉底君"被折叠的第 7 章"目录（与 boss_key 交汇）。
7. **辟谣对位**：10 张知识卡各对应 1 条水军帖（tag 匹配）；另 6 条水军帖 tag 为看山/鱼干/V587 等无对应卡——硬辟谣必失败（群嘲），符合 KNOWLEDGE_SYSTEM 3.3。
8. **AI 纪律**：所有 clue 事实在 `fact` 字段（AI 不可改），扩写自由度在 `flavor_hint`；DM 禁语清单见 scripts/dm_system_voice.md §七。

## 四、合规自查（硬规则逐条）

- [x] 只写 `content/scenarios/kanshan/`（含 _gen 生成器与 scripts 增量，均在管辖目录内）。
- [x] JSON 严格对照 `schemas/*.example.json` 字段（新增字段仅为 modes/role_type/image 等"只增不改"项）。
- [x] 引用官方内容保留作者署名：卡面 author 字段、credits.md 全表、truth.attribution、剧本与 minis 头部标注（M1 官方雪碧图来源+Referer）。
- [x] 欢乐向、不攻击真实用户：post_039 官方合规帖明示"角色均为拟人化虚构"；伪造内容全部数据层标注。
- [x] 素材源只读：yanyan_sources/ 未改动；assets/images avatar 按实名引用，未新增美术管线。

## 五、遗留与建议（移交 A/相关窗口，JSON 批次）

- ~~B 组需实现 `chat:keyword_` 与 `review:credits` 两种触发~~（已落地：evidence_chain on_chat / on_review_entered，见 engine/STATUS §六）。
- C 组开导 few-shot 注入时使用卡 golden_lines 原文（保署名），失败分支文案见 counsel_clinic.md §1.2。
- E 组复盘页需常驻渲染 flavor_5 小字与 credits；指认 DM 按钮按 boss:flaw_count>=5 动态出现。
- 动物态立绘为可选彩蛋，若启用须走 asset_manifest.json 统一管线（勿在窗口内直连 API）。

## 六、P1/P2/P3 增量产出（2026-09-12 第二批，对齐 GAMEPLAY_V31 / MEGA_MODE）

| 交付 | 文件 | 内容 |
|---|---|---|
| 成就文案库 v1 | scripts/achievements.md | 23 项成就（MEGA_MODE 指定 4+1 + 扩展 18 项），含稀有度/引擎判定条件/解锁横幅/分享卡一句/机器可读 JSON 块 |
| P1 台词埋点 | scripts/segments_p1.md | 抽风池、心病急诊室、头条话题、心声广播事故白名单池 |
| P2 台词埋点 | scripts/segments_p2.md | 广播台、快问快答题库 20 题、反诈剧场三幕脚本 |
| P3 彩蛋 | scripts/collectibles_p3.md | 鱼干收集品 3 处位置定义 + 看山Bot 隐藏语音 4+1 段 + 对接 JSON |

引擎侧确认（engine/STATUS §七）：AchievementEngine 已全量加载 v1 的 23 条 DSL 与表格文案（冒烟 198 断言 PASS）；CollectiblesBoard 已接 collectibles_p3.md（fish_01/02/03 + unlock_payload）。

## 七、v31 增量第二批（2026-09-12 第三批，对齐 GAMEPLAY_V31 §二~§五/§九 + engine/STATUS §六）

| 交付 | 文件 | 内容 | 对齐点 |
|---|---|---|---|
| 成就文案库 v2 | scripts/achievements.md（整文件重写） | ★核心七枚（标题+描述各 ≤50 字）：看山还是山/心晴医师/带节奏之王/鱼干守护者/防折叠斗士/暗房大师/全场公敌；总表扩至 24 条 DSL | resolver.achievements() 七枚举；新增 ach_anfang（新 DSL type=stealth_photo_clean，**需回 A 广播扩展求值器**）；ach_mianyipai→ach_gongdi（同 type hammered_votes，阈值 ≥4）；已实测 12 自判+3 record 项 id/name 零变动 |
| P1 台词 v2 | scripts/segments_p1.md（整文件重写） | 抽风池三池（惩罚 8 对/故障 6 条/**奖励池 ap_free·heat_bump**）、押注结算句（**赞数单位，结算加热 +1~5**）、急诊室（**红灯 expiry=当前轮+1、每局限一次、二次失败纯群嘲句池**）、头条竞标（**平价先到先得、胜者 heat_delta 翻倍、流拍热度小涨**）、心声广播（**白名单 11 案情词、all_case_sensitive→广播体操、no_unlocked_heart→白噪音**） | engine §六：banner_glitch/opinion_feed 押注·竞标/knowledge_cards 急诊/memory_system broadcast_accident 裁决语义逐条对齐 |
| P2 台词 v2 | scripts/segments_p2.md（整文件重写） | 广播台、快问快答 20 题、反诈剧场三幕（保留）+ **新增 §四博弈环节埋点**：双面线索锁（sides/flip_side）、暗拍（2AP·share_photo 可说谎·ach_anfang 计数钩子）、记忆拼图（spend_tamper_points(2)·排对/排错句）、终局陈词（60 秒·hammer_vote 分池·ach_gongdi 钩子） | engine §六 P2 四裁决；A 裁决 #2（暗拍 2AP）/#6（achievements() 确定性） |
| minis 文案包 | scripts/minis.md（新增） | **M1 看山快跑**：障碍类型×3、障碍词库 12、收集/增益词 6、Game Over/里程碑/战报模板（官方 kanshan.png 雪碧图署名+Referer）；**M2 心声窃听器**：题库 10 题（open 6 题无案情词供免登录脱敏抽样/full 4 题登录用，含教学点）、对齐 memory-puzzle 路由；**M3 谣言消消乐**：谣言块↔辟谣标签块 10 对（与 hotfeed 辟谣目标帖一一对应、卡面署名随块）、特殊块 4 种、结算三档；**M4 侦探花名池 22 个欢乐警衔**（MEGA §1.1 花名机制，headline 关键词映射、隐私红线、每日一抽播报句） | GAMEPLAY_V31 §9.3/§9.4 安放位图；M4 对齐 MEGA_MODE §1.1「码农→调试人生司司长」原梗 |

### 第三批校验记录（实跑）

- scripts/*.md 内嵌 JSON 围栏逐块 `json.loads` 通过（achievements 24 条 DSL、collectibles 1 块）。
- 词库/题库计数核对：抽风惩罚 8 对+故障 6 条+奖励 4 条（≥6 ✅）、快问快答 20 题（≥8 ✅）、反诈剧场 3 幕、障碍词 12+增益 6、窃听题库 10 题、消消乐词条 10 对+特殊块 4、花名池 22 个（≥20 ✅）。
- 泄底词扫描（看山设局/局控室/系统音=看山等）：仅命中"禁语规则声明行"本身，台词正文零泄底；成就文案无里层真相。
- 表结构完整性：achievements.md 引擎同步总表保持 v1 六列表头（id/成就/稀有度/达成条件/解锁横幅/分享卡一句话），AchievementEngine md 表格提取器无需改动。

### 第三批移交注意

- A：`stealth_photo_clean` 为新 DSL type——按 engine STATUS §七.4 需广播后由 B 扩展求值器（扩展前 ach_anfang 恒 False 静默，不影响其余 23 条）。
- C：暗拍/拼图/陈词环节结束调 `ae.record(...)`（ach_anfang 数据依赖暗拍对质记录）；成就锐评花名从 minis.md M4 池取。
- E：minis 四入口按 §9.4 位图；M2 免登录版只取 tier=open 题；M1 分享卡复用 shell.js Canvas 管线。
- F：`/api/minis/memory-puzzle` 脱敏抽样按 M2 tier 字段过滤；`/api/minis/hotfeed-pool` 按 M3 词条对抽样。
