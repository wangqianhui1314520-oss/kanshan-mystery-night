
## 九、§3.5b `stealth_photo_clean` 求值器扩展（2026-09-12，A 广播即开工）

**结论：D 成就库 v2（24 条 DSL）全覆盖，新 type 2 个落地，冒烟 207/207 全 PASS、pytest 桥接 12 passed、集成回归 71/71。**

| 变更 | 落点 | 实现 |
|---|---|---|
| `stealth_photo_clean`（引擎自判型） | achievements.py `_cond_met` | 干净暗拍=photos_of(pid) 中 clue_id 指向池内**非 fake** 线索的照片计数；`flagged=True`（被当场拆穿）排除——按 §3.5b 前向兼容要求实现；逐玩家计、任一玩家达标即解锁（party 下取最大者） |
| 数据源 | evidence_chain.py `clean_photo_counts()` | 各玩家干净暗拍计数（fake 过滤 + flagged 排除）；另有入口保证：stealth_photo 对 tier=fake 线索直接拒绝（伪证无法被拍），过滤为双保险 |
| `hammered_votes`（record 外部登记型） | achievements.py `_cond_met` | `record("hammered_votes", target=…, value=N)` 喂票数，任一目标达阈值即解锁（ach_gongdi，v2 合并群嘲免死金牌，**value=4 以 D 的 JSON 为准**） |
| `resolver.achievements()` 扩展 | resolver.py | 新增关键字参数 `clean_stealth_shots`（≥3→暗房大师）与 `hammered_votes`（≥3→全场公敌，v2 合并口径；原 most_hammered+hammered_is_self 路径保留兼容）——A/C 不经 DSL 也可直接消费 |

### 单测证据（真实 kanshan 数据）

- clean_photo_counts：茶水间(boss_flaw)+前台(limited) 真照片=2；fake 伪证照片不计（0）；flagged 排除后 2→1；
- resolver：`achievements(clean_stealth_shots=3)`→暗房大师、`achievements(hammered_votes=3)`→全场公敌；
- AchievementEngine×v2：24 条加载；真实地点暗拍 3 次干净（工位/茶水间/档案室）→ **ach_anfang 解锁**；record hammered_votes 4 票→ **ach_gongdi 解锁**（D v2 阈值 4，非旧 3）；幂等保持。

### 说明

- D v2 中 ach_gongdi 阈值=4（原群嘲免死金牌为 3）——引擎按 D 的 JSON 权威数据求值，未做口径假定；若 A 裁决回调 3，仅改 JSON 即可，引擎零改动。
- 通用比较器 op（>=/==/<=）在两处新增分支均走既有 `_cmp()`，与 §3.5b 通用结构一致。
| evidence_chain | ✅ 完成 | 线索池/发卡/地点热度/证据合成/伪造投放 + forgery_target 证伪对质；flaw_count/boss_ready（≥5 解锁指认 DM）；ingest_clue 接收 memory_system 篡改点线索卡；check_contradiction 旧接口保留 |
| timeline | ✅ 完成 | 旧签名全保留（query/verify/public_entries）；新增 lie_points（「说谎点」抽取）、check_claims（批量时间-地点主张校验）、trace_conflicts（said 层记忆块 vs 时间线冲突，确定性关键词匹配） |
| resolver | ✅ 完成 | 旧签名全保留（resolve_action/calc_ending）；AP 池（can_afford/spend/refund/reset_round，每轮 3）；truth_coverage（proof_clues 覆盖度）；resolve_accusation（≥2 证据卡才有效，90%/60% 分档）；resolve_boss_accusation（破绽<5→dm_mock 群嘲；≥5+心晴≥2→终极·看山还是山；≥5 心晴不足→真相大白里层）；matrix_ending 8+2 结局矩阵（优先级：DM 分支→隐藏结局→表层→污染胜利→wrong） |
| memory_system | ✅ 完成（新） | 双层 said/heart；load 容错（目录缺失/坏 JSON 静默空载）；V1→V3 版本链 unlock_next（reason: memory_fix/counsel/clue_condition，no_op 同键返回）；心声层随解锁开启（visible_blocks 过滤）；篡改点三来源：版本 diff tamper_point、两层矛盾（said edited ↔ heart 配对）、删除段，自动产 tp_* + 符合新 schema 的 clue_card |
| opinion_feed | ✅ 完成（新） | hot_post schema；refresh 按 round 抽 6-8 条（确定性按 id，池小降级补齐，置顶帖强制浮顶）；热度 0-100（init 40）；buy_heat 仅置顶 is_fake 帖；refute 经 attach_knowledge 查卡 topic_tag，匹配→降热度+解锁 clue_ref，不匹配→反涨+群嘲文案（「没知识还硬辟谣」）；clues_blocked_by_heat（≥80 阈值淹没未辟谣真线索）；heat_ratio 供污染胜利判定 |
| knowledge_cards | ✅ 完成（新） | knowledge_card schema；draw 全队共享池随机抽未持有（seed 可复现）；counsel 确定性匹配 binds==char_id（team/archive 特殊对象），成功五类 effect 收益（boss_key/evidence/memory_unlock/buff_ap/plot_fragment）+心晴档案记录，失败 mock；refute_allowed 供 opinion_feed；clinic_settlement（0-1 normal / 2-3 archive_show / 4+ all_hearts_clear+hidden_unlock）；同人双卡彩蛋提示 |

## 二、待办（依赖其他窗口）

1. **D 组内容未交付**：kanshan/ 仅有 README。引擎 load 全部容错空载不阻塞；D 交付后需按 schema 补 `memory/*.json`（含 layer 字段）、`clues/*.json`（tier 制）、`hotfeed/*.json`、`knowledge_cards/*.json`（binds/effect 字段）、`timeline.json`。
2. **F 组集成点**：session 层需在状态变化后调用 `EvidenceChain.sync_context(memory_versions=…, counsel_cards=…)` 与 `OpinionFeed.attach_knowledge(…)`；StageMachine.session_id 由服务端回填。
3. **C 组接口**：Agent 层读 `MemorySystem.visible_blocks(char_id, include_heart=解锁后)` 注入 prompt；开导/尬聊演出按 `KnowledgeSystem.counsel().transcript_hint` 生成。
4. **G 组正式测试**：`engine/_smoke_test.py` 仅为 B 窗口冒烟工具，pytest 全量回归归 G。

## 三、偏离说明（无需回 A 广播的理由：未改任何既有签名与返回结构）

| # | 偏离 | 说明 |
|---|---|---|
| 1 | 旧四模块新功能全部走**新增方法** | CONTRACTS「签名即契约」：release/verify/calc_ending 等旧签名与返回键完全保留；ending 值域扩充（perfect/partial/wrong 兼容保留 + V3 新键在新方法中） |
| 2 | 旧 clue `level` 字段兼容读取 | tier_of() 统一 tier/level 双读，旧模板数据不迁移也可跑 |
| 3 | advance() 幂等修复 | 旧骨架在最后一幕重复调用会无限重置行动点，改为越界直接返回当前阶段（行为收严，无调用方依赖旧行为） |
| 4 | 热度/阈值默认值 | 地点热度初始=该地点线索数（clamp 2-5）；全局热度 init=40、上限 100、淹没阈值 80；D 组交付后可由内容覆盖 |
| 5 | end_round 幕循环语义 | acts 数组每项=一幕（主体 stage）；幕内 investigate↔round_table 循环由 end_round 驱动，轮满 advance() 进下一幕；D 组 kanshan scenario.json 的 acts 建议为 break_ice / investigate / accuse / review（多幕搜证则排多个 investigate 项） |
| 6 | refute 卡校验经 lookup 注入 | opinion_feed 不直接依赖 knowledge_cards 模块（attach_knowledge 注入 callable），避免跨模块强耦合 |
| 7 | timeline.json 缺失会抛 FileNotFoundError | 旧骨架行为保留（timeline 为契约必交付件，未做静默容错）；其余 load 类接口均静默容错 |

## 四、冒烟自测覆盖

`python engine/_smoke_test.py`（纯标准库、临时 fixture、零 AI）：stage_machine 17 项 / memory_system 16 项 / knowledge_cards 14 项 / opinion_feed 13 项 / evidence_chain 26 项 / timeline 9 项 / resolver 26 项 = **121 断言全 PASS**；另含空目录容错、最小 scenario、kanshan 现状（README-only）加载验证。

## 五、集成验证（2026-09-12，D 组真实内容就绪后自动开办）

**结论：兼容，无 P0 遗留。** D 组 kanshan 内容（8 角色 / 32 线索 / 40 帖 / 10 卡 / 24 记忆 / timeline 24 轨迹 / truth 14 节点+boss_layer）与引擎五模块全量联通，`python engine/_integration_check.py` **71 断言 0 Issue**。

验证要点：
- 内容规模合规：tier 分布 public 7 / limited 9 / hidden 5 / fake 6 / boss_flaw 5，破绽 flaw_id 5 枚齐全，帖 clue_ref 均指向存在线索，假帖零真线索引用；
- 搜证链：真实地点（看山工位×鱼干等）命中、未命中→环境线索、evidence 条件链 4/4 解锁、memory 条件链逐版本解锁达成、counsel 条件链（kc_05→char_02 / kc_01→char_06 / kc_06→char_05）全通；
- **扩展语法落地**：D 组在 scenario.condition_grammar 新增的 `chat:keyword_<关键词>`（对话框触发，clue_031「看山，关门」）与 `review:credits`（复盘页触发，clue_032）已由引擎实现——未触发被拒、触发即解锁；
- 记忆链：8 角色 V1-V3 全载，篡改点 8 处产出且 clue_card 经 ingest_clue 入证据链；
- 舆论场：round 面板 6 条、买热搜假帖、辟谣成功对（post_008 × kc_01，tag=倦怠）降热+解锁真线索；
- 裁决：truth_coverage 真实 14 节点计算、指认真凶 char_01 命中、破绽 5/5 → boss_ready → 终极结局分支；状态机吃真实 scenario（acts 4 幕）播报正常，总行动点 33 与自述一致。

### 集成期适配（引擎侧，零签名改动）

| # | 适配 | 说明 |
|---|---|---|
| 1 | unlock_condition 扩展语法 | `_unlock_met` 新增 `chat:keyword_*`（比对 sync_context 注入的 chat_keywords）与 `review:*`（review_flags），支持 D 组对话框/复盘页触发线索 |
| 2 | 开导对象别名 | D 组用 `team_all`/`archive_bureau` 表示全队/档案局，KnowledgeSystem 以 TEAM_ALIASES/ARCHIVE_ALIASES 双别名适配（契约示例 team/archive 同样可用），组对象不计入心晴诊室 counsel_count |

### 遗留给其他窗口（非 P0）

1. **F 组**：session 层状态变化后调用 `EvidenceChain.sync_context(memory_versions=…, counsel_cards=…, chat_keywords=…, review_flags=…)`（chat_keywords 由 chat 消息关键词命中时注入，review_flags 在进入复盘页时注入 `{"credits"}`）；`OpinionFeed.attach_knowledge(…)`；`StageMachine.session_id` 回填。
2. **C 组**：`MemorySystem.visible_blocks(char_id, include_heart=解锁后)` 注入 NPC prompt；`KnowledgeSystem.counsel().transcript_hint` 作开导演出生成底稿；`dm.set_flaw_count(ec.flaw_count())` 随破绽收集同步。
3. **E 组**：对话框/复盘页线索（clue_031/032）的解锁事件由 F 在命中 chat_keywords / 进入复盘时触发 `evidence_chain.release`；「指认：DM」按钮以 `ec.boss_ready()` 为显隐条件。
4. **G 组**：端到端一局与阵营平衡模拟尚未见 tests/ 产出；`engine/_integration_check.py` 可作为其集成回归基线复用。
5. 热搜帖 40 帖已交付（此前 30+ 为中途快照），规模达标，无待办。

## 六、V31 增量裁决（2026-09-12，GAMEPLAY_V31 B 组 5 项全交付）

**结论：5/5 完成。** 新增 `engine/party.py`、`engine/difficulty.py` 两模块，五件 P1 裁决与四件 P2 裁决全部落在对应模块（全部为新增方法/字段，既有签名与返回结构零改动）；冒烟扩展至 176 断言全 PASS，真实内容集成回归 71/71 保持全绿，并用真实 8 角色卡联跑 party 配比（1 人局污染 2 / 5 人局污染 3，swayable 优先成为被裹挟者）与动态难度三档落地验证通过。

| 项 | 模块 | 实现 |
|---|---|---|
| party 阵营分配器 | **party.py（新）** | `PartyBoard`：1-5 真人动态配比（≤3 人局污染 2 / 4-5 人局 3），暗置洗牌发牌，swayable 角色进污染优先成为「被裹挟者」（coerced 可策反）；席位 join/leave + 掉线 ai_takeover 标记；8 角色满员校验 |
| 多人 AP/投票聚合 | party.py | AP 各算各的（真人 + `ai:char_xx` 同池，每人每轮 3）；`cast_vote` 一人一票（重复覆盖）、真人+AI 加权 `tally`、平票显式返回 tie |
| 动态难度 | **difficulty.py（新）** | `DifficultyDirector.on_act_settled(metrics)` 幕结算钩子 → 三档梯度（assist/normal/hard，确定性规则：线索<3 或覆盖<0.2 或卡死≥2 轮→assist；覆盖>0.7 且线索>8→hard）；落地=建议关键词 5/3/2 + boss 条件宽限 ±1 + 热度阈值 ±10；防卡死「档案局备忘录」（点方向不泄底，assist 2 条/幕、normal 1、hard 0） |
| 补 D 对接点 | evidence_chain.py | `on_chat(player_id, text)`：发言命中 `chat:keyword_*`（如「看山，关门」）自动解锁并返回线索列表（供 F 广播 clue_gained）；`on_review_entered(player_id)`：进入复盘解锁全部 `review:*` |
| P1 弹幕押注 | opinion_feed.py | `open_bet / place_bet / settle_bet`：押注池按比例赔付（赞数单位）、结算话题小幅加热、重复结算与非法选项拒绝 |
| P1 系统抽风事件 | stage_machine.py | `banner_glitch()` 升级：横幅附带确定性 effect（ap_free=下次行动免扣，`consume_action` 自动生效；heat_bump=话题加热值供上层应用）；旧「惩罚」文案池不变 |
| P1 心声广播白名单 | memory_system.py | `broadcast_accident(candidates)`：仅播**已解锁心声**且不含案情词（删除/监控/芯片/打卡/接头/水军/篡改/权限/记忆编辑/仿冒/备份）的块；全含案情→`all_case_sensitive`（DM 改播广播体操）；未解锁→`no_unlocked_heart` |
| P1 急诊室双倍 | knowledge_cards.py | 开导失败自动挂红灯（`er_active(char_id)` 供前端）；下一轮内（`set_round` 注入轮次）用对卡=收益双倍（`unlocked.doubled=True`，buff_ap ap=2），抢救成功红灯熄灭 |
| P1 头条竞标 | opinion_feed.py | `open_headline_bidding / bid_headline / settle_headline`：每轮一个头条位阵营明牌竞标（出价=行动点，平价先到先得），胜者帖置顶且 heat_delta 翻倍；流拍→热度小涨 |
| P2 双面线索锁 | evidence_chain.py | 线索可选 `sides={front, back, back_condition}` 字段；`flip_side()` 按 back_condition（评估规则同 unlock_condition）翻面，公开展示恒为 front，翻面幂等 |
| P2 暗拍 | evidence_chain.py | `stealth_photo()`：线索**留原地**（不写 released，他人仍可搜原件），玩家持照片（热度照常 -1，候选按 boss_flaw>hidden>limited>public 优先级）；`share_photo(claim)` 原文+声称并存（可说谎，真伪留圆桌对质） |
| P2 记忆拼图 | memory_system.py | `puzzle_answer()`（引擎权威：已解锁记忆块按时间排序）、`puzzle_judge(proposal)` 排对/排错判定（线索奖励由上层发）、`spend_tamper_points(2)` 发起成本（篡改点可消耗，`tamper_available()` 对账） |
| P2 终局陈词 | party.py + resolver.py | 陈词登记 + 弹幕「最想锤的人」分池投票（`hammer_vote/hammer_result`，与指认投票隔离、不影响结局档位）；resolver 新增 `achievements()`（MEGA §三枚举：看山还是山/心晴医师/带节奏之王/鱼干守护者/防折叠斗士 + 暗房大师/全场公敌） |

### V31 假设与说明（A 审核点）

1. **GAMEPLAY_V31.md 文件乱码**：该文件以 mojibake（UTF-8→GBK 双重转码）存储，B 按可恢复的关键机制行（心声广播白名单/急诊室/头条/暗拍/拼图/终局陈词）+ MEGA_MODE §二§四 实现；建议 A 窗口重存该文件（不影响本次实现）。
2. **暗拍成本 2AP**：文档未定价，按「信息博弈加深」定为 2AP（与 counsel/refute 同档），由上层 PartyBoard/resolver 扣点。
3. **押注单位=赞数**（欢乐值），不与热度/行动点混币；结算对话题加热 +1~5（随参与人数封顶）。
4. **被裹挟者发牌**：阵营为引擎暗置动态发牌（seed 可复现、可 reshuffle），角色卡 faction 仅作 swayable 优先参考——F/C 不得向前端透出 `faction_of()` 结果。
5. **急诊室红灯跨轮语义**：失败时 expiry=当前轮+1，即「下一轮内」有效；`set_round` 由 F 每轮调用。
6. **成就 `achievements()` 为确定性判定**，文案包由 D 组补（GAMEPLAY_V31 D.1）；报告生成（C.1）直接消费该返回值。

## 七、成就判定 JSON + collectibles JSON 对接（2026-09-12）

**结论：D 组两份对接 JSON 全量接进引擎，23 成就 DSL 全覆盖、鱼干收集品彩蛋层落地。** 新增 `engine/achievements.py`（AchievementEngine + CollectiblesBoard）；冒烟扩至 **198 断言全 PASS**（真实 kanshan 数据驱动），集成回归 71/71 保持全绿。

### AchievementEngine（成就判定）

- **加载**：`load()` 接受 achievements.md 路径 / JSON 文本 / 已解析 list（内置 \`\`\`json 围栏提取），并从 md 表格同步提取横幅文案+分享卡一句话（随解锁结果返回，C 组直接渲染）；
- **判定**：`evaluate(ending_key)` 遍历 23 条 condition DSL，解锁幂等；ending value ↔ 引擎结局键映射表（ending_kanshan/ending_pollution/ending_sunny/ending_chapter7 等 7 项）；
- **引擎自判项**（只读取数，零外部喂入）：boss_flaw_count / chat_keyword（看山，关门）/ env_clue（大力丸）/ heart_unlock_count / clue_collected / same_location_dry_streak / refute_success_streak / memory_puzzle_win / counsel_multi / counsel_count / collectible；
- **外部事件项**：`record()` 喂 listen_full / fake_exposed / confrontation_win / danmaku_echo / antifraud / quiz_score / closing_survived / hammered_votes（C/E/F 组在对应环节调用）；
- **数据源新增只读接口**：evidence_chain `dry_streaks()/env_facts_seen()/chat_keywords_hit()`、memory_system `heart_unlock_count()/puzzle_wins()`、opinion_feed `refute_streak()`。

### CollectiblesBoard（鱼干寻物支线 · P3 彩蛋层）

- `load(collectibles_p3.md)` 解析 3 收集品（fish_01 快递柜 / fish_02 天台 / fish_03 心晴自习室）与集齐规则；
- `collect(player_id, item_id, act_no)`：拾取时机门槛（act1/act2/act3 起可拾，act_no 由 StageMachine 幕序提供）、0AP、重复拾取拒绝；
- 集齐 3 袋 → 返回 `unlock_payload()`：ach_yuganxianren + 看山Bot 隐藏语音 4 段 + 终极层加播 1 段（`boss_reveal_extra`）清单（IndexTTS 2.5 切片逐句播，由 C 组演出）；
- 硬规则遵守：不进证据链、不影响结局判定（与 evidence_chain 零耦合）。

### 真实数据验证亮点

以真实 kanshan 内容完整走通 5 破绽链：clue_028/029（默认）→ clue_030（counsel:kc_06 开导 char_05）→ clue_031（chat「看山，关门」）→ clue_032（review:credits 复盘页）→ **flaw 5/5 → boss_ready → 终极结局**；23 成就中引擎自判 12 枚实测解锁（看山还是山/心晴医师/局中局目击者/唤醒词侦探/热搜质检员/摸鱼大师/偷听心声不犯法/鱼干线人/空调已修好/鱼干守护者/带节奏之王/全员心晴），外部 record 3 枚（一眼假鉴定师/快问快答满分/防折叠斗士），幂等与 ending 映射验证通过。

### 接线点（F/C/E）

1. **F**：session 结算时调 `ae.evaluate(ending_key=resolver 的结局键)`，`achievement_unlocked` 事件 payload=返回的 ach dict（含 banner/share_line）；`cb.collect` 挂在场景图微光点点击路由（act_no 传当前幕序）。
2. **C**：开导/辟谣/拼图/对质等环节结束时调 `ae.record(...)`（事件名见 STATUS §七表）；成就解锁演出按 `banner` 文案 + 玩家 headline 模板。
3. **E**：`cb.progress()` 驱动微光点显隐与收集进度；分享卡 Canvas 用 `share_line`。
4. 未知 condition type 一律返回 False 并保持静默（新 DSL 需回 A 广播后扩展求值器）。

## 八、on-call 记录：F party 联调支持 + pytest 桥接（2026-09-12）

**结论：F 侧 party 接线缺口 2 处已按最小增量补齐（engine/ 内，零签名破坏）；176→200 断言整理为 pytest 桥接 12 用例全绿。**

### F 联调现状核查（server/ 只读）

- F 的 party 路由（main.py `/api/session/{id}/join`）当前为 **session 层自管**：players 数组、faction 硬编码 "truth"、AP 走 `sm.actions_left` 全局单池、投票 `votes` dict 无 AI/弹幕聚合——**与 MEGA_MODE §二「行动点各算各的；投票聚合真人+AI」不符**，需 F 接入 PartyBoard；
- EngineDriver 具备**确定性回放机制**（session["actions"] 重放），PartyBoard 此前无序列化能力 → 回放会丢 party 状态，为**硬缺口**。

### B 侧最小增量（party.py 新增 3 方法，既有签名零改动）

| 方法 | 用途（F 接线） |
|---|---|
| `PartyBoard.from_roster(roster, seed=None)` | 从 EngineDriver._load_roster() 输出一行构造（char_factions 自动映射），省去 dict 组装 |
| `snapshot() -> dict` | 可序列化快照：发牌结果/座位（含 ai_takeover 标记）/各人 AP/全部票池/陈词——入 session_store 或随 actions 回放恢复 |
| `restore(snap)` | 服务重启后恢复（配合固定 seed 重放：先 restore 再按 actions 回放） |

冒烟补 2 断言（from_roster 构造配额、snapshot/restore 回放一致性），直跑 200/200。

### F 接入指引（party 模式）

1. `create_session(mode="party")` 时：`self.party = PartyBoard.from_roster(self._load_roster(), seed=SEED)`，host 走 `party.join(host)`，faction 字段改从 `party.result()["factions"]` 取（**不得透出给前端**，暗置发牌）；
2. join/掉线路由：`party.join(player_id, char_id)` / `party.leave(player_id)`（ai_takeover 标记已在快照内）；
3. AP：多人模式下 `party.spend(player, cost)` 替代全局 `sm.actions_left` 扣点（sm 单人保底路径不变）；
4. 投票：`party.cast_vote(voter, target, weight)`（AI 补位票 `ai:char_xx`、弹幕低权重可 weight=0.5）→ `tally()`；终局陈词/锤票走 `final_statement/hammer_vote/hammer_result`；
5. 回放：replay 时 `party.restore(snapshot)` 后再按 actions 重放。

### pytest 桥接（空闲任务完成）

- 新增 `engine/test_engine_suite.py`：**不搬运断言**，直接 import _smoke_test 复用 fixture 构造与 9 个驱动函数，逐个包装为 pytest 用例（check() 失败累积 → 包装器统一 assert，失败详情随消息输出）；另含桥接自检用例；
- G 组用法：`pytest game/engine/test_engine_suite.py -v`（12 passed ≈0.5s）或全仓 `pytest game/` 收集；直跑模式 `python engine/_smoke_test.py` 不受影响；
- 运行时注意：受管 Python 3.13.12 主解释器无 pytest，已用隔离 venv（`.workbuddy/binaries/python/envs/default`，pytest 9.1.1）验证；G 组跑测试用 `envs/default/Scripts/python.exe -m pytest` 或自建 venv（requirements.txt 已含 pytest>=8.0）。
