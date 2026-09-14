
## 九、M2 心声窃听器对接（2026-09-12 · D 组抄送 F 备注，C 侧数据源就绪）

| 项 | 实现 |
|---|---|
| M2 题库解析 | segments_lib 增 `minis.md §M2` 解析：10 题双层记忆教学题（**tier=open 6 题（无案情词）/ tier=full 4 题（真实记忆剧情）**，said/heart/答案位/教学点齐全） |
| F 路由数据源 | `bridge.memory_puzzle_pool(tier)`：`GET /api/minis/memory-puzzle` 脱敏抽样直接消费——**tier=open 过滤（full 题零泄漏，实测断言）**，确定性洗牌；tier=full 仅登录局内 |
| 判定+演出 | `bridge.heart_quiz_flow(item, answer)`：答案位确定性比对 → `showtime.heart_quiz_show`（D 组结算句原样：答对「窃听成功…温柔使用」/答错「嘴硬版…从来不加班」+ 教学点揭示）；热身关收尾句（第二幕开场）已解析可用 |
| 与 broadcast_accident 一致性 | M2 open 白名单精神与引擎 `memory.broadcast_accident` 案情词黑名单同源——主线广播事故仍走引擎白名单，M2 走 D 组静态题池（双通道互不耦合） |

自测三：**56/56 PASS**；全量回归 bridge 17/17 + selftest 42/42 全绿。
- 说话风格 skill few-shot 注入（花名/口吻匹配，无命中通用档轮转）；`bridge` 构造参数 `player_headline_text`（玩家知乎 headline 原文）→ 自动抽花名 → 成就锐评/报告署名；显式 `player_headline` 参数优先 |

自测三升级：**51/51 PASS**（T10：M4 池 22 枚/关键词匹配/暗拍计数/分享说谎/拼图胜负双路/锤票记账/暗房大师徽章消费）。全量回归 bridge 17/17 + selftest 42/42 全绿，py_compile 通过。
tion 防御剥离**（vote 前输出不得含阵营字段，契约 §四.4）；`_safe_stats` 序列化层同步剥离 | 引擎 + C 演出 |
| C.4 防卡死备忘录 | **消费 difficulty.py assist 档**：`bridge.act_settled()` 幕结算喂 metrics（clue_count/coverage/stuck_rounds）→ 三档梯度 → `apply(ec, opinion)` 落地 → `memo_flow()` 走 `difficulty.memo_for()`（方向词与预算 assist 2/normal 1/hard 0 全引擎权威）；AI 润色强约束——**方向词 hint 必须原样保留，丢失即回退引擎原文**（点方向不泄底） | 引擎（difficulty） |
| 附加：成就判定收编 | bridge 挂 `AchievementEngine`（refs 注入五数据源 + load achievements.md 24 条）与 `CollectiblesBoard`（collectibles_p3.md）；`achievements_flow()` 改为消费 `ae.evaluate(ending_key)`（ending 值↔resolver 键双向尝试），segments 判定降级为引擎空载兜底；`record_event()` 双写 ae.record（listen_full/fake_exposed/confrontation_win/quiz_score 等外部事件项）；`collect_flow()` 集齐 → `collectibles_show()`（看山Bot 隐藏语音 4 段+终极层加播，IndexTTS 按句切片不合并） | 引擎（AchievementEngine） |

已知边界：①ach_dalitang（大力丸）/摸鱼大师等引擎自判项数据源在 ec 内部，C 组 record_event 只记报告侧集合，判定以引擎为准；②`opinion.attach_knowledge` 契约为 lookup(card_id)→topic_tag 单参；③D 组 v2 文案（segments_p1 §1.1 惩罚池/§2.5 白名单/achievements 24 条）解析已适配，后续 D 追加条目自动生效。
_stats()` 引擎数据注入，数字不改写 |
| P0 成就判定+播报 | `ACHIEVEMENTS` 10 项确定性判定表 + `achievements_flow()`（去重后逐个播报） | 判定纯数据（first_blood/劳模/猎人/编织者/倾听者/全员心晴/破绽×3/局中局×5/已打码/唤醒词） |
| P1 抽风重写 | `glitch_rewrite(banner)`：横幅出错→系统音重写更离谱惩罚 | 输入横幅来自引擎 banner_glitch |
| P1 广播事故 | `broadcast_accident(ctx)`：串台→自我修正→漏无害可疑细节 | 细节仅从 context 素材取 |
| P1 急诊室抢救 | `emergency_rescue(ctx)`：诊断书→机制处置建议→签字梗 | 只提名不宣判结果 |
| P1 头条竞标主持 | `headline_auction(posts, heat)`：念帖+叫卖+起拍价 | 成交由引擎 buy_heat 裁决，演出不宣布 |
| P2 广播台 | `radio_station(ctx)`：寻物启事/点歌素材必须来自输入 | 丢失物真实存在于输入 |
| P2 反诈剧场 | `anti_fraud_theater(fake)`：伪证/水军帖改编反诈短剧 | 只引用输入事实（fake_of/水军机制特征） |
| P2 终局陈词锐评 | `final_verdict(ending, npc_reports)`：逐人一行引用真实数据 | 欢乐向不惩罚，不剧透未触发线 |
| P2 快问快答 | `quick_quiz(stats)`：题面/选项/答案**全确定性**（地点题/标签题轮换，素材=已发放线索） | 零幻觉：answer_index 直接可判，AI 不出题 |
| 防卡死备忘录 | `bridge.stuck_level()`（idle 轮数→0-3 级）+ `memo_flow()`：L1 模糊/L2 方向（地点）/L3 明示（地点+关键词） | 素材只指向已存在地点与 suggest_keywords，绝不发明事实；L0 不生成 |

bridge 同步新增：`collect_stats()`（含 search/hit/bake/violations/wake_word 计数）、`achievements_flow()`、`stuck_level()`、`memo_flow()`；search_flow/npc_chat 自动累计计数。

## B 引擎接线（bridge.py，2026-09-12）

`AgentRuntime`（`bridge.bootstrap()` 便捷入口）= C↔B 装配层：**零 engine 修改、零 Agent 签名改动**，运行时裁决全部走引擎（只演不裁）。B 组 STATUS 遗留待办 #3 全部落地：

| B 组对接点 | bridge 落地 | 自测 |
|---|---|---|
| MemorySystem.visible_blocks → NPC prompt | `sync_memory(char_id)`：heart 探测 → npc.update_memory；未解锁 heart 零注入 | S1×4 |
| 解锁链 | `unlock_memory()`：unlock_next → 篡改点 clue_card ingest 入证据链 → sync_context(memory_versions) → NPC 重注入 | S1 |
| KnowledgeSystem.counsel().transcript_hint | `counsel_flow()`：引擎匹配裁决 → 成功演出/尬聊 → effect 联动（memory_unlock 链、sync_context(counsel_cards) → counsel: 条件线索） | S2×3 |
| EvidenceChain.flaw_count → dm.set_flaw_count | `sync_flaws()` 随搜证/开导自动同步 | S4 |
| sync_context(chat_keywords/review_flags) | `npc_chat` 自动注入聊天关键词（clue_031 唤醒词链）；`enter_review("credits")` | S4/S5 |
| 搜证/指认/诊室 | `search_flow`（引擎裁决 → fact 原文反馈+弹幕）、`accuse_flow`（表层 resolve_accusation / 终极 resolve_boss_accusation + boss_reveal 演出）、`clinic_flow` | S4/S5 |

接线自测 17 项（真实 kanshan：8 NPC / 32 线索 / 10 卡 / truth 14 节点，mock LLM）：双层记忆锁前后、篡改点入链、开导双路、counsel 条件链（clue_030）、破绽 5 枚条件链（默认×2/counsel/chat 唤醒词/review）、证据卡 1/2 判无效 → 2/2 命中真凶（truth_revealed·partial）、指认 DM → kanshan_still_mountain + 现身演出、心晴诊室、守卫兜底拦截误注入 heart 块。

## 交付清单

| 文件 | 内容 |
|---|---|
| `llm_client.py` | Provider 抽象统一入口：`main`（OpenAI 兼容自建 LLM）/ `zhida`（直答低频高光）/ `mock`（零 key 离线回放）；预生成缓存（内存+JSON 落盘）；zhida 限额 DailyBudget（默认 2 次/日落盘计数）；降级链 zhida→main→mock；`fallback(scene)` 预写兜底。骨架四方法签名原样保留 |
| `dm_agent.py` | DM=刘看山伪装"系统提示音"人格：叮——播报、scene_desc、action_feedback（fact 原文一字不改）；**破绽计数注入**（set_flaw_count 0-5，3+违和口误尾缀/5+迟疑演出）；`danmaku()` 知乎热评弹幕 3-5 条；`boss_reveal()` 终极层现身演出（触发判定归引擎，Agent 只演）；`daily_briefing()` 走 zhida 低频位 |
| `npc_agent.py` | NPC 双层记忆：said 层常态注入；**heart 层仅在 update_memory(heart_unlocked=True) 后注入 prompt**，未解锁期间 heart 文本零出口；信任梯度保密（<30 回避 / 30-59 松口细节 / 60-84 motive/alibi / 85+ 才可 guilt）；兼容 V3 角色卡与旧模板字段 |
| `judge_agent.py` | 只演不裁落地：target/motive/method/coverage 全部对 truth.json **确定性比对**（2-gram 启发 + linked_truth_nodes/proof_clues 双兼容），LLM 只补 logic_quality/misleading_points；指认 DM 分支（boss_flaw 证据 ≥5 才命中）；`heart_clinic()` 心晴诊室结算（normal/archive/all_clear/roast 四档） |
| `consistency_guard.py` | 最后一道闸：①心声拦截（heart 未解锁时转述心声 2-gram≥2 即拦）②秘密/里层真相泄密检测 ③档案局 11 地点时间线校验 ④sanitize 清洗提示词痕迹；守卫只拦截不裁决 |
| `bridge.py` | **C↔B 接线层**（AgentRuntime/bootstrap）：engine 七模块 + agents 四模块装配；npc_chat（守卫兜底+【已打码】彩蛋+chat_keywords 注入）/ search_flow / counsel_flow / unlock_memory / accuse_flow / clinic_flow / sync_flaws / enter_review / begin_round；演出统计（collect_stats/achievements_flow/stuck_level/memo_flow） |
| `showtime.py` | **演出导演**：侦探报告/成就判定+播报（10 项确定性成就表）/P1 四演出位（抽风重写·广播事故·急诊抢救·头条竞标）/P2 四演出位（广播台·反诈剧场·终局锐评·快问快答）/防卡死备忘录三档 |
| `_showtime_test.py` | 演出批次自测（19 项：成就确定性/演出位文案/快问快答题面/备忘录三档/失败兜底） |
| `prompts/` | dm_system（系统音人格+破绽注入块）/ dm_boss_reveal（终极层六拍分镜）/ dm_danmaku / dm_daily_briefing / npc_system（双层记忆+阵营+保密梯度）/ judge_system / counsel_system（开导成功·尬聊双分支）/ clinic_system / showtime_report / showtime_p1 / showtime_p2 / showtime_memo / **fallbacks.json**（25 类兜底台词库，show_* 与 kind 一一对应） |
| `selftest.py` | mock 模式全链路自测（42 项，幂等，临时缓存目录，零 key 零网络） |
| `__init__.py` | 包导出，集成方 `from agents import LLMClient, DMAgent, ...` |

## 自测结果（mock 模式，实跑取证）

```
SELFTEST ALL PASS: 42/42 passed  (python 3.13.12, exit 0)
P0 Provider 状态（无 key → mock）  P1 缓存/流式/降级链
P2 DM 全演出（播报/破绽注入/命中反馈 fact 保真/弹幕/终极层/导读）
P3 NPC 双层记忆（未解锁零心声注入 / 解锁后注入 / 腔调锚点）
P4 Judge（错指/命中/覆盖度 2/3/boss 2 vs 5 破绽/诊室四档）
P5 守卫（时间线/心声拦截·放行/guilt 泄密·高信任不误伤/里层真相/sanitize）
P6 旧式 chat(system,user) 网关兼容   P7 配假 key+坏 URL → 兜底不抛异常
P8 安全（无硬编码 key，凭证仅 os.environ）
```

## 环境变量契约（key 只从环境变量读）

| 变量 | 用途 | 缺省行为 |
|---|---|---|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | main 自建 LLM（OpenAI 兼容） | 缺失 → mock |
| `LLM_TIMEOUT` | 请求超时秒数 | 30 |
| `ZHIHU_APP_KEY` / `ZHIHU_ZHIDA_URL` | 直答 Agent | 缺失 → 降级 main→mock |
| `ZHIDA_DAILY_LIMIT` | 直答日限额 | 2 |
| `LLM_CACHE_DIR` | 缓存目录 | agents/cache/（运行时产物，勿入库） |

## 集成说明（给 A/B/E/F）

- Agent 构造第一参 `gateway`：传 `LLMClient` 实例即可；也兼容 F 窗口 `chat(system,user)` 网关（call_gateway 自适配）。
- B 引擎接线：NPC 记忆解锁后调 `npc.update_memory(blocks, version, heart_unlocked)`；破绽解锁调 `dm.set_flaw_count(n)`；boss_layer 触发时调 `dm.boss_reveal(ctx)`；守卫 context 里带 `memory_state={"heart_unlocked":…, "blocks":[…]}`。
- 预生成：开局把开场白/固定证词/金句演出塞 `llm.pregenerate([{cache_key, system, user}…])`，运行时 `cached(key)` 命中零成本。
- `stream=True` 当前语义=全量取回后分片迭代（SSE 升级留给 F 网关层，已注明）。
- 直答 header 按 Bearer ZHIHU_APP_KEY 预留，实际鉴权字段以 F 窗口网关为准，可直接替换。

## 已知边界

- D 组 kanshan 内容未就绪，selftest 用 schema 对齐的样例数据；D 内容入库后无需改 Agent。
- motive/method 命中为确定性启发（2-gram≥2），resolver 可按需覆写。
- 语义级泄密比对（向量）留待引擎扩展，当前为词面+2-gram 双阈值。

## 十、智能体记忆体系（G4 · V4 §三 知识库/记忆文档/skill，2026-09-12）

三层知识体系落地（V4_SHOWTIME §三）：**零 LLM 确定性组装**（润色才走 LLM）、零 Agent 签名改动、纯 bridge 组装层实现。

| 层 | 落点 | 实现 |
|---|---|---|
| 知识库 | `agents/knowledge/char_01..08.md`（8 份） | 每 NPC 一份人设知识档案：身份/当晚轨迹（时间线锚点）/秘密（信任梯度）/说话风格/心病（kc 绑定）/对其他角色态度；数据源=characters+memory V1-V3+truth+knowledge_cards（只读引用）；文件头标注"内部档案，禁止向玩家透出" |
| skill | `agents/skills/npc_char_01..08.md` + `skills/dm_host.md`（9 份） | 每 NPC：句式模板×5/口头禅×3/禁区×3/示例台词×3（禁区与一致性守卫拦截项对齐）；dm_host.md：节奏控制/梗投放/救场话术/冷场自嘲 + 人格红线（fact 不改/裁决不归 DM/boss_reveal 前不摘系统音面具） |
| 记忆文档 | `AgentRuntime.memory_doc: dict[char_id, [{act, summary}]]` | 跨幕长期记忆：每幕结算 200 字内关键事件摘要（`build_act_summary` 确定性拼装，≤200 字硬截断），`settle_act()` 写入并注入下一幕上下文（NPC system 模板尾，滑动窗口仅留最近 3 幕，同幕重复结算幂等覆盖） |

bridge.py 增量（不影响已交付接口 record_event/achievements_flow/report_flow）：
- `_inject_agent_docs()`：启动时 knowledge/skills 确定性拼进 npc.system / dm.system 模板尾（`<<<KNOWLEDGE/SPEECH_SKILL/DM_HOST>>>` 标记判重，幂等）；NPC/DM 每次 render 自动携带，无需改 npc_agent/dm_agent。
- `record_act_event(note)` / `_note_act_event()`：幕内关键事件流水（record_event 尾部挂点纯追加，记账语义不变；unlock_memory/counsel_flow 成功事件同步入流水）。
- `settle_act(act, notes)` / `build_act_summary()`：幕结算钩子——上层显式 notes 优先 + 流水去重保序，零 LLM；返回值即权威底稿，上层如需润色另走 LLM 不得增删事实。

自测：selftest.py 新增 P9（知识注入：8 NPC 全量/内容抽查/skill 结构/DM skill/渲染可达/幂等）+ P10（跨幕摘要：≤200 字/事件含入/memory_doc 落账/下一幕渲染可达/自定义 notes/同幕幂等/record_event 挂点/滑动窗口/settle 后对话）共 18 项 → **60/60 PASS**；全量回归 bridge **17/17** + showtime **56/56** 全绿。
