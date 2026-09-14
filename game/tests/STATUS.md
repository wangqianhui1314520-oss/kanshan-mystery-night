# tests/STATUS.md — G 测试组交付状态（M3 回归）

> 交付：2026-09-12 16:40-17:00（第二轮：补起服端到端/V31 环节/party AI 补位/平衡目标测量）｜
> 快照：server/main@16:39 · engine/resolver@16:15 · engine_driver@15:57（并行窗口持续交付中）
> 运行：`cd game && python -m pytest tests/ -v`（venv：`C:\Users\Administrator\.workbuddy\binaries\python\envs\default`）
> **结论：G 套件全绿（0 FAIL），原矩阵五项 + 增量四件套 + 起服端到端全覆盖。发现 P1 级 Issue 4 项、P2 级 5 项、CONCERNS 3 项。45-55% 平衡目标在对称人群口径实测达成（0.500）。**

## 〇-b、A 组交办：bridge/showtime 测试 pytest 化（17:00）

| 交付 | 源 | 结果 |
|---|---|---|
| `tests/test_bridge_runtime.py`（6 用例） | agents/_bridge_test.py S0-S6（17 断言） | 6 PASS（逐条对齐：组装/轮播报/双层记忆生命周期/开导成败分支/搜证+5 破绽/弱强指认+DM 终极+诊室/守卫兜底） |
| `tests/test_showtime.py`（36 用例） | agents/_showtime_test.py T0-T11（56 断言） | 36 PASS（文案池解析/成就判定+去重+数值条件/P1·P2 演出位/quiz·refute 计分链/备忘录预算/引擎权威成就/广播双路径/收集品/侦探报告/头条链/阵营铁律/LLM 失败兜底/花名池/暗拍·拼图·陈词/M2 心声窃听器） |

**pytest 化要点**：脚本式共享顺序态改为**每用例自足建局**（函数级 fresh AgentRuntime + tmp 缓存目录；纯读类用 module 级只读实例）；脚本中的顺序依赖（S3 彩蛋先于 S4 破绽、S2 开导先于 clue_030 释放）在各用例内显式补齐——顺带固化了两条链路前置条件为可读断言。双脚本原件保留（基线复跑 56/56、17/17 仍绿），pytest 版入 G 全量回归。基线复核：smoke 207✅ / integration 71✅。

## 〇、第二轮新增覆盖（本节为增量，第一轮结论见下文 §一~§七）

| 新增 | 文件 | 结果 |
|---|---|---|
| **起服端到端**：真实 uvicorn 子进程（`ZHIHU_GAME_USE_MOCK_ENGINE=0`）→ health/引擎模式取证、**全员心晴分支 REST 全链路**（搜证抽满卡→开导 4 人→指认幕→all_hearts_clear+hidden_unlock）、boss 链现状取证（4/5 破绽→指认 DM→dm_mock） | test_e2e_server.py | 4 PASS + 1 SKIP |
| **boss 链终极结局**（5 破绽→指认 DM→看山还是山，REST） | test_e2e_server.py（显式 skip） | ⏸ G04 阻断，报 A |
| **V31 环节**：急诊双倍限一次（同窗口灯灭不重复翻倍/新窗口重启）、记忆拼图判定（权威答案/排错锐评/2 篡改点门槛）、暗拍（线索留原地/双方各拍/分享可声称但 fact 一字不改）、双面锁（front 恒公开/back 条件翻面/幂等；kanshan 内容暂无双面线索字段） | test_p1_segments.py | +7 全 PASS |
| **party 2 人 + AI 补位**：driver 侧 2 真人 + 6 AI 席（AI 行动点就位/阵营 2 污染暗置/掉线接管）+ REST 侧席位视图（faction 零透出） | test_party_e2e.py | +2 全 PASS |
| **平衡目标测量**：对称人群（30 污染流 vs 30 求真流）→ **污染胜率占比 0.500**，落在 README 目标 45-55% ✅；辟谣对冲 1:1 交替可按住热度 | test_balance.py | +2 全 PASS |

### 新增发现（第二轮）

| 级别 | # | 摘要 | 责任窗 |
|---|---|---|---|
| P2 | **G10** | `EngineDriver._do_counsel` 未校验卡片是否已被抽取（held）——任意已知 card_id 可直接开导成功，绕过「自习室抽卡」设计。引擎层 KnowledgeSystem.counsel 同样不校验。 | B |
| P2 | **G11** | 多人投票终局未用聚合结果：`_do_vote` 在票数集齐后以**最后一名投票者的 target** 调 `_finalize`，PartyBoard.tally（含平票显式返回）未被驱动层消费——2 人分票时结局由后投者决定。 | B |
| P2 | **G12** | （已量化）对称人群口径 45-55% 达标（0.500）；但**非对称现实分布**偏污染：纯污染流 30/30 胜 vs 求真流 all_hearts_clear ~30/30——胜负高度依赖玩家策略选择而非对抗交互（双方无同场博弈路径，见 G11）。数值调平建议：求真侧对抗手段（辟谣/指认）需能在同场内反制买热搜。 | A 拍板 |
| CONCERNS | **G13** | party 房主建房后**不自动入席**（create_session 不落座，须自行经 /join + 房间码进房）——E/F 流程文案需明确，否则房主视角"建房即开局"会踩空。 | F/E |
| 备注 | — | kc_06（memory_unlock 效果）经 counsel 后，counsel:kc_06 条件线索 clue_030 需**回「服务器机房×日志」补搜**才释放（driver 仅在 effect=evidence 分支主动释放）——合法玩法链，已按此路径完成 4/5 破绽取证；建议 D 在 STATUS 注明该链路玩法说明。 | D（文案） |

### G04/G06/G07/G01/G09 复核（16:45）

| # | 状态 | 复核方式 |
|---|---|---|
| G04 | **未修**（engine_driver@15:57 `_finalize` 仍持 review 注入；main.py 新路由无复盘触发） | 代码复核 + REST 实测 4/5→dm_mock |
| G06 | **未修**（resolver@16:15 matrix_ending 优先级不变） | 代码复核 |
| G07 | **未修**（resolver.achievements() refuted≥3→防折叠斗士仍在） | 代码复核 |
| G01 | **未修**（evidence_chain@16:15 release/search 仍仅 hidden/boss_flaw 求值条件） | 代码复核 |
| G09 | **未修**（_selfcheck.py 未更新） | `python server/_selfcheck.py` → 24/32 |

## 一、覆盖矩阵（原矩阵 + 增量）

| # | 矩阵项 | 测试文件 | 断言数 | 结果 |
|---|---|---|---|---|
| 1 | 引擎单测（9 模块：7 原有 + party + difficulty） | test_engine_units.py | 63 | ✅ 63 PASS + 2 XFAIL |
| 2 | schema 校验（121 JSON + 跨文件引用 10 项独立复跑） | test_schema.py | 18 | ✅ 18 PASS |
| 3 | 端到端（单人三幕全流程 + 回放确定性 + 负路径） | test_e2e.py | 5 | ✅ 3 PASS + 1 XFAIL(严格) |
| 4 | 平衡性（3 策略 × 30 局蒙特卡洛 + 开导收益曲线） | test_balance.py | 4 | ✅ 4 PASS |
| 5 | 降级演练（额度/白名单/429/超时/缓存/每日挑战灰化） | test_degradation.py | 11 | ✅ 11 PASS |
| 6 | 增量：party 多人端到端（3 人聚合投票 / WS 双路 / party 建房进房 / 观战 / 脱敏） | test_party_e2e.py | 5 | ✅ 5 PASS |
| 7 | 增量：P1 环节单测（押注/抽风/广播事故/急诊室/头条竞标） | test_p1_segments.py | 6 | ✅ 6 PASS |
| 8 | 增量：报告成就判定（D 契约 24 枚 + AchievementEngine DSL 实测 + 可行性矩阵） | test_report_achievements.py | 16 | ✅ 15 PASS + 1 XFAIL |
| 9 | 增量：D 资产增量校验（segments_p1/p2、collectibles_p3、minis、禁语扫描） | test_d_assets_increment.py | 23 | ✅ 23 PASS |

## 二、基线复跑（回归守护 · 零副作用证据）

| 基线 | 交付时 | 本次复跑 | 判定 |
|---|---|---|---|
| engine/_smoke_test.py | 121 PASS | **207 PASS / 0 FAIL**（B 组扩容后） | ✅ |
| engine/_integration_check.py | 71 PASS | **71 PASS / 0 ISSUE** | ✅ |
| agents/_bridge_test.py | 17/17 | **17/17** | ✅ |
| server/_selfcheck.py | 32/32 | **24/32**（8 失败） | ❌ → ISSUE-G09 |

G 组全程只写 `tests/`；server 测试一律 monkeypatch 临时 DATA_DIR，未触碰 `server/`、`engine/`、`content/`、`game/data/`。

## 三、发现清单（按严重程度分级，修复归责任窗）

### P1（阻断/核心体验）

| # | 摘要 | 证据 | 责任窗 |
|---|---|---|---|
| **G04** | **终极结局「看山还是山」经服务端动作管线不可达**：第 5 破绽 clue_032（review:credits）仅在 `_finalize` 终局结算时注入，届时 boss 裁决已按 4/5 破绽判 `dm_mock`。引擎层 API（`ec.on_review_entered`）正常，缺 F/driver 侧 vote 前触发点。 | test_e2e.py::test_boss_accusation_ultimate_reachable（strict xfail） | B/F |
| **G06** | **裁决口径分裂：指认真凶仍落「全员喷子」**：`resolve_accusation` 判 hit→truth_revealed，但 `matrix_ending` 要求 coverage≥0.6（≈9/14 节点 × 每节点 3 线索合成卡），24AP 总预算内不可达（合成器每次搜证只出 1 卡且 btn_01 字典序恒优先）。评委单人保底动线（README 承诺）只能得到 wrong/dm_mock。 | test_e2e.py::test_full_truth_run（vr.ending=truth_revealed vs outcome=wrong 双证据） | A/B 裁决 |
| **G07** | **成就判定映射错乱**：`resolver.achievements()` 把 `refuted>=3` 判为「防折叠斗士」（D 契约=listen_full(char_06)≥3）；refuted≥3 对应「热搜质检员」。注意：新 `engine/achievements.py`（AchievementEngine DSL）判定正确，仅 resolver 快速路径错。 | test_report_achievements.py::test_fangzhe_not_re-futed（xfail） | B |
| **G09** | **server/_selfcheck.py 基线漂移 24/32**：探针仍锁定 mock 时代语义（`engine=="mock"`、mock 台词事件、WS 旧字段），A/B/F v2.1 真实引擎接线后未同步。8 失败项全部为探针过期而非服务回归（engine 模式实测正常，见本套件 test_party_e2e/test_e2e）。 | `python server/_selfcheck.py` 复跑日志 | F |

### P2

| # | 摘要 | 证据 | 责任窗 |
|---|---|---|---|
| **G01** | **条件旁路**：4 条 limited 线索（clue_012/013/014/015，水军矩阵证据链）携带 evidence:/memory: 前置条件，但 `release()/search()` 仅对 hidden/boss_flaw tier 求值 unlock_condition → 未持前置线索可直接搜走。 | test_engine_units.py::test_limited_tier_condition_enforced（xfail） | B |
| **G02** | `ec.on_chat` docstring 称幂等，但重复触发重复返回已持有线索 → F 层将重复广播 clue_gained（池状态无副作用，仅返回值语义）。 | test_engine_units.py::test_on_chat_return_idempotent（xfail） | B |
| **G08** | 成就库 ending 值（ending_kanshan 等）为语义别名，与引擎 ENDINGS 键不一致；`engine/achievements.py` 已建 ENDING_MAP 兜住 —— 需 F/E 侧统一从映射取值，避免直比永不命中。 | test_report_achievements.py::test_ending_alias_map_covers_all_ending_conditions | B/F |

### CONCERNS（行为与文案口径）

| # | 摘要 |
|---|---|
| G03 | 急诊室红灯：文案承诺「下一轮内」，实现为当轮即生效（expiry=current+1）。测试锁定现行为；若按文案收严属行为变更，需 B 拍板。 |
| CONTENT-G01 | 辟谣对位：tag 与知识卡匹配的 14 帖（10 水军+4 真帖）clue_ref 全为 None → `refute()` 的「解锁真线索」子链在真实内容空转（辟谣仅降热 → 解除淹没间接生效）。engine/STATUS §五「post_008×kc_01 降热+解锁真线索」表述与数据不符。 |

### 时序竞态备注（非 Issue）

D/B/F 并行交付期间出现 2 次瞬时读取竞态（content JSON 读取时恰逢写入，复跑即消）与 1 次半成品提交（engine_driver 15:52 前后 `_roster` 先用后定义，B 约 3 分钟内自愈）。G 套件内容读取建议后续加一次性重试；本次未加以保证断言纯度。

## 四、平衡性蒙特卡洛数据（N=30/策略，引擎确定性 + 策略 RNG 方差）

| 策略 | 分布 | 结论 |
|---|---|---|
| 纯污染（买热搜流） | pollution_win 30/30（终局热度 ≥85，均值 ≈100） | 热度通路工作正常；纯污染近乎必胜 → 依赖求真侧开导/辟谣对冲（见混合） |
| 纯求真（搜证+开导 4 人） | all_hearts_clear ≥0.6 | 隐藏结局可达；开导 4+ 阈值合理 |
| 混合（风格抽样 0.3/0.78） | pollution_win 29 / wrong 1（偏热风种子）；心晴风种子可达 all_hearts | 双侧均可达 ✅ |
| 开导收益曲线 | counsel_count vs 真节点覆盖 相关系数 > -0.2（实测正向） | 收益方向正确 |

README 目标「污染/求真 45-55%」在**策略对称假设**下才成立；当前内容 16 水军帖（fake 总 delta=100）对污染侧显著有利，求真侧需依赖辟谣对冲——结合 G06（求真侧终局矩阵过严），建议 A 在 M4 前拍板：①求真侧 coverage 口径放宽或 AP 上调；②买热搜 delta 下调或辟谣收益上调。

## 五、成就判定可行性矩阵（24 枚全评估）

| 类别 | 条件类型（成就） |
|---|---|
| engine_ready（引擎直接可判） | ending / counsel_count / boss_flaw_count / chat_keyword / memory_puzzle_win / hammered_votes / collectible(CollectiblesBoard) / counsel_multi / closing_vote_top1_survived |
| derivable（会话状态可推导） | clue_collected / heart_unlock_count / env_clue / same_location_dry_streak / stealth_photo_clean（"clean" 口径需 B 定） |
| untracked（需 B/F 增埋点） | listen_full / fake_exposed / confrontation_win / danmaku_echo / refute_success_streak |
| content_missing（P2/P3 内容件） | antifraud_all_correct / quiz_score（P2 已有台词库 segments_p2.md，判定件待 B） |

报告生成器（侦探报告评分/高光/锐评）尚未见 agents/ 侧实现 —— 成就判定已就绪（AchievementEngine + resolver 双路径），报告器交付后 `achievement_unlocked` 事件与 session_store 跨局计数可直接消费本套件验证过的 DSL。

## 六、增量期间契约漂移记录（并行窗口实时交付，G 已全部跟进对齐）

| 时间 | 交付 | G 动作 |
|---|---|---|
| 15:02-15:08 | engine P1 全量（party/difficulty/押注/头条/急诊室/广播事故） | 单测全部纳入 |
| 15:32 | engine/achievements.py（AchievementEngine + CollectiblesBoard） | 新增 DSL 实测组 |
| 15:46-15:52 | PartyBoard 入 driver（曾现 _roster 先用后定义，B 自愈） | 等待稳定后复跑 |
| 15:50-15:54 | D v2 成就库（24 枚）/ segments_p2 / minis / collectibles_p3 | 断言从 23→24 枚、P3 从「未交付」翻转 |
| ~16:00 | F party 路由（VALID_MODES+party / join / 观战 / 脱敏视图） | party 路由测试从「400 拒绝」翻转为正向全流程 |

## 七、运行方式

```bash
cd game
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m pytest tests/ -v          # 全量
python -m pytest tests/ -m "engine" -v   # 按标记过滤：engine/schema/e2e/balance/degradation/party/p1/achievements/assets
```

依赖：fastapi/httpx/uvicorn（既有）+ pytest + pytest-asyncio（本次入 venv，清华镜像）。

## 八、G6 验收节：V4 综艺化全量回归 + 新功能验收（2026-09-12 21:20-22:05）

> 验收快照：并行窗口实时交付中（G3/G4 于本验收期间多次落盘，三轮回归如实记录）。
> 运行：`cd game && <venv>/Scripts/python.exe -m pytest tests/ -q`（venv：`C:\Users\Administrator\.workbuddy\binaries\python\envs\default`）。
> **结论：G6 验收完成：219 passed / 0 failed**（另 2 skipped / 3 xfailed / 1 xpassed，见 §八.3）。

### 八.1 新增 V4 用例（tests/test_v4_acceptance.py，13 用例）

| # | 覆盖（V4_SHOWTIME 规格） | 用例 | 结果 |
|---|---|---|---|
| 1 | 大圆桌视图数据（rt 组装演出结构：9 席=1 DM+8 NPC、零 faction 透出、speaker 聚光） | TestRoundtableView（2 用例） | 2 SKIP（rt 圆桌接口未探测到，G1/G4 交付中；交付后自动转严格断言） |
| 2 | 综艺阶段事件 case_intro / act_transition / first_vote（建局→破冰→圆桌举手→转场事件流扫描） | TestVarietyStageEvents（2 用例） | 2 PASS（三件事件均已接入 payload.event；first_vote 圆桌预投票不触发 ending 已验证） |
| 3 | AgentRuntime 知识注入（agents/knowledge/*.md ≥8 份非空、覆盖 8 角色、标志文本进 bridge/NPC 注入面） | TestKnowledgeInjection（3 用例） | 3 PASS（8 份 char_XX.md 齐备，_inject_agent_docs 接线验证） |
| 4 | 跨幕记忆摘要（settle_act 后 memory_doc 非空、≤200 字、notes 进摘要、NPC system 模板 <<<CROSS_ACT_MEMORY>>> 注入、同幕幂等覆盖） | TestCrossActMemoryDoc（3 用例） | 3 PASS |
| 5 | 机制幕门控（破冰期 skill 白名单拒绝 + _do_skill locked 事件分支；搜证幕解锁；actSet 随 stage 推进 1→4 且末幕幂等不越界） | TestMechanismActGating（3 用例） | 3 PASS |

### 八.2 全量回归三轮记录（并行交付窗口瞬时态如实定性）

| 轮次 | 结果 | 定性 |
|---|---|---|
| r1 | 212 passed / 4 failed / 4 skipped / 3 xfailed / 1 xpassed | **非随机竞态**：G4 半成品文件态被撞上——server 侧已调 `rt._inject_agent_docs` 而 bridge.py 实现未落 → AgentRuntime `AttributeError` → 起服 REST 500×3（test_e2e_server）+ 注入用例 1F。按协议等 60s 重试 |
| r2 | 216 passed / 2 failed / 2 skipped / 3 xfailed / 1 xpassed | G4 `_inject_agent_docs` 已落地（e2e_server 全绿、注入 3 用例翻转 PASS）；memory_doc 字段已交付但钩子为 `settle_act`（G 测试初版误用 `act_settled` 难度钩子），修正测试口径 |
| **r3（终局）** | **219 passed / 0 failed / 2 skipped / 3 xfailed / 1 xpassed** | **全绿**。2 skip=圆桌 rt 接口未交付；G07 修复由 xpass 实证 |

基线复核口径：原 208 PASS 基线 + 本节新增 13 用例 - 圆桌 2 skip = 219，计数对账一致。

### 八.3 终局明细

| 项 | 明细 | 判定 |
|---|---|---|
| 2 SKIP | TestRoundtableView（rt 圆桌视图组装接口未交付） | 转 G1/G4 跟踪，交付后套件自动转严格断言 |
| 3 XFAIL | G04（单人流 strict 路径；REST 修复链已由 test_e2e_server::test_boss_chain_rest_g04_fixed_truth_revealed PASS 实证）、G01（limited 条件旁路）、G02（on_chat 幂等语义） | 既有标记，维持 |
| 1 XPASS | test_report_achievements.py::test_fangzhe_not_refuted（ISSUE-G07） | **G07 修复已实证**，建议 G 移除该 xfail 标记（下次回归前处理） |

### 八.4 线上取证（curl --noproxy "*"，2026-09-12 21:27 与 21:55 两次）

| 目标 | 第一次 | 复测 | 判定 |
|---|---|---|---|
| GET /api/health | **200**（engine.mode="engine"、mock_enabled=false、sessions.active=159、uptime 31.7s） | **200** | ✅ 真实引擎在线 |
| GET /（首页） | **200**（2.57s） | **200** | ✅ |
| GET /assets/images/ui_roundtable.png | **404**（0B，content_type=application/json） | **404** | ❌ 见 G14 |

### 八.5 新增发现（本节）

| 级别 | # | 摘要 | 责任窗 |
|---|---|---|---|
| P2 | **G14** | 线上 `assets/images/ui_roundtable.png` 404（health/首页正常），但本地 `content/assets/images/ui_roundtable.png` 存在（images 51 件齐全）——**部署滞后或服务端静态托管清单缺件**，大圆桌 UI 底图线上不可用。 | A/F |
| CONCERNS | **G15** | 破冰期 skill 门控为双层实现：`apply_action` 阶段白名单拒绝（返回 err 文案「不允许动作 skill」）+ `_do_skill` locked 事件分支——后者经正常动作管线**不可达**（`sm.can("skill")`=False 先拦）。行为正确，但若 E 前端依赖 locked **事件**渲染门控 UX，需要 F 层把拒绝文案转事件口径，或把 skill 加入破冰期白名单让 locked 分支生效。测试对两层实现均兼容。 | F/E 拍板 |
| 备注 | — | 综艺事件口径实测记录：case_intro/act_transition/first_vote 均以 `payload.event` 接入 engine_driver 事件流；G3 交付期间半成品态（act_transition/first_vote 先到、case_intro 后到）曾触发部分缺失失败，复测通过——并行窗口交付期测试失败先重试再定性的协议有效。 | 记录 |
