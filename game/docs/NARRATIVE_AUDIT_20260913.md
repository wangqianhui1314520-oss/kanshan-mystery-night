
---

# 修复记录（2026-09-13 00:40 · 全部 9 项已修复并实跑验证）

**口径决策**：权威层 = `content/scenarios/kanshan/` + `engine/`（架构铁律"content 是确定性骨架"）；前端演示层（`data.js/store.js`）全部对齐权威。

## 修复清单

| Issue | 修复内容 | 改动文件 |
|---|---|---|
| C5 双层主谋矛盾 | demo 指认分支 char_03→**char_01 知之者**；跳反者 V587→**流量酱/路人甲**；char_03 secret"水军头子"→"被矩阵_K拿捏把柄的执行者"；char_08 改回 **faction=truth、看山影子学徒**（heartache 置 null）；redeem 文案、复盘时间线重写为权威版（删「V587 受指使送芯片」「看山 21:40 出门买鱼干」「22:31 大门解锁」「587 奶茶备注」） | `frontend/js/data.js`、`frontend/js/store.js` |
| C9 结局 id 协议断裂 | store.js ending 事件增加 **outcome→ending_id 映射**（覆盖 resolver 全部 10 个结局）；前端补 **fish（看山的鱼干）/hung（悬而未决）** 两张结局卡 | `frontend/js/store.js`、`frontend/js/data.js` |
| C1 破绽5复盘悖论 | G04 语义写回数据与文档（不改引擎补丁，实跑已证其 load-bearing）：truth.json reveal_condition 注明"进入终局投票即视为复盘达成"；clue_032 fact 增加与前端策划案落款的互证；DM_BOSS §四写入 G04 说明 + mutation 基线 | `content/scenarios/kanshan/truth.json`、`clues/clue_032.json`、`docs/DM_BOSS_DESIGN.md` |
| C2/C4 结局口径 | 全部统一为 **9 结局**（truth.json/resolver 口径）：GAME_DESIGN_V3 §一/§五 更新全表；DM_BOSS 去掉"(7→8)"、补回看山的鱼干行；KNOWLEDGE_SYSTEM 规模行更新 | `docs/GAME_DESIGN_V3.md`、`docs/DM_BOSS_DESIGN.md`、`docs/KNOWLEDGE_SYSTEM.md` |
| C3 鱼干结局名实不符 | resolver 与前端 fish 卡 desc 增加"最后一袋彩虹鳟鱼味鱼干留在工位"叙事桥接，名实合一 | `engine/resolver.py`、`frontend/js/data.js` |
| C6 双层事实冲突 | 鱼干口味全库统一**彩虹鳟鱼味**（便签/天台袋/快递/DM 口误四条线索）；看山Bot 指令时间统一 **22:30 执行**（破绽 fact/角色 heartLine/记忆块 d1·d2）；门禁记录改为"KS-000 接管后无出入"（删 22:31 大门解锁）；B-17 奶茶小票与 V587 解绑（改为水军暗号复用） | `frontend/js/data.js` |
| C7 署名缺口 | credits.salt 补齐 **4 部盐言**（新增《穿越大明，我被崇祯偷听心声》凉风有信），四部均补作者名 | `frontend/js/data.js` |
| C8 阈值不一致 | 完美还原统一 **≥90%**（前端文案 + 演示裁决 `cov.pct >= 90`；注：6 节点离散覆盖下 85 与 90 行为等价，零行为风险） | `frontend/js/data.js`、`frontend/js/store.js` |

**评估修正（非缺陷）**：原 C6 中"flavor_3 开导卡 kc_05 vs kc_06"实为**两套 kc 编号体系**——前端 kc_05=黛西巫巫《不想学习》→看山Bot，与权威 kc_06 同一语义绑定；8 角色心病绑定逐一核对全部正确，仅编号不同，不做改动。

## 验证证据

1. **回归守护 18/18 PASS**：`python tools/verify_narrative_fix.py`（R1 主谋/跳反 ×4、R2 协议映射 ×2、R3 事实统一 ×5、R4 署名、R5 阈值、R6 文档 ×3、R7 G04 语义、E2E 引擎复跑）。
2. **引擎 E2E**：破绽 4/5（无 G04 注入，clue_032 提前获取被拒）→ `dm_mock`；注入后 5/5 → `kanshan_still_mountain`——补丁语义与数据口径现已互证。
3. **JS 语法**：`node --check` data.js / store.js 通过；mock 重导出成功。
4. **全量测试套件**：`pytest tests/` → **220 passed, 2 skipped, 3 xfailed**（含 engine units/schema/E2E/party，零回归）。

复跑命令：

```bash
node tools/_audit_dump_mock.js
python tools/verify_narrative_fix.py
python -m pytest tests/ -q
```
 -> dm_mock    ← G04 补丁关闭·mutation 基线（终极结局不可达）
G04 注入后: release(clue_032)=OK, 破绽数=5, boss_ready=True,
  resolve_boss_accusation(5, counsel=2) -> kanshan_still_mountain
```

## 三、修复方向（结论先行）

1. **C5（最高优先）**：定一个真主谋。若评审玩的是前端演示局 → 把 demo 对齐权威（主谋改知之者、跳反者改流量酱/路人甲、V587 恢复学徒定位、reviewTimeline 重写）；若 demo 就是最终口径 → 反向改 truth.json/resolver，二选一，不能两套并存。
2. **C9**：在 `store.js` 的 ending 事件处理加映射表 `{perfect_restoration:'perfect', truth_revealed:'truth', vindicated:'redeem', pollution_win:'pollution', deleted_chapter7:'chapter7', all_hearts_clear:'sunshine', kanshan_still_mountain:'kanshan', dm_mock:'mock_dm', kanshan_fish:→需新增卡}`，或服务端统一发 `ending_id`。
3. **C1**：G04 补丁语义（进终局即视为复盘达成）写回 `truth.json` reveal_condition 与 DM_BOSS 文档；或把 clue_032 改为指认前可达的门控，删掉补丁。
4. **C2/C3/C4**：以 truth.json(9 结局) 为唯一口径，回写三份文档；「看山的鱼干」要么删除（同步删 resolver.kanshan_fish）要么改条件，前端补/删结局卡。
5. **C6**：以 content/ 为权威逐条改 `data.js`（口味、kc_06、22:30、flavor_5 位置与解锁、flavor_2/4 条件、时间线 21:40/22:31 两条）。
6. **C7**：`data.js` credits.salt 补《穿越大明，我被崇祯偷听心声》凉风有信（flavor5Credit 常驻小字里已有，正文署名区漏了）。
7. **C8**：前端文案 85%→90%。

## 四、无问题项（复核通过，避免误伤）

- 时间线主干自洽：21:00 暗门/锁门(KS-000) → 21:07-15 监控删除 → 22:30 备份日志删除留哈希 → 21:10-25 流量酱刷帖。
- 阵营划分一致：污染=知之者；摇摆可策反=流量酱、路人甲；其余求真。被裹挟者 2 人，符合 V3 §二。
- 看山Bot「绝不说谎 vs 执行删除指令留哈希」为刻意科技伦理张力，非 bug。
- 三幕盐言缝合与机制映射（锁门横幅/双层记忆/披虎皮揭面）一致。

---

## 六、修复复核 20260913（当前权威状态 · 覆盖第一节历史结论）

> 方法：以「权威 truth.json 为准」定案（主谋=知之者 char_01），逐项修复 + 实跑复核。
> 复跑：`node tools/_audit_dump_mock.js && python tools/verify_narrative_audit.py`
> **审计脚本结果：9/9 全部 NOT-REPRO（已修复），E2E PASS，CONFIRMED = 0。**

### 本轮实际改动（2 处真实缺口）

**C6 · 前端知识卡编号体系对齐权威**（`frontend/js/data.js`）
- 症结：前端 kc_01–kc_06 的编号相对 content/ 权威整体错位（标题/绑定/effect 都对不上），形成两套不自洽的知识卡体系。
- 修复（按内容语义重编号，保留各卡剧情文案自洽）：
  - kc_01↔穷人思维→**kc_02**；心理被动→**kc_03**；升职加薪→**kc_04**；注意力分散→**kc_05**；逼迫学习(char_05)→**kc_06**(effect boss_key→memory_unlock)；职业倦怠(char_06)→**kc_01**。
  - 同步 8 个角色 `heartache`：char_02=kc_05 / char_03=kc_02 / char_04=kc_03 / char_05=kc_06 / char_06=kc_01 / char_07=kc_04（char_01=kc_07|kc_08 不变）。
  - 同步 counsel 解锁：flavor_3 `kc_05→kc_06`、接头供词 `kc_01→kc_02`、门禁记录 `kc_03→kc_04`、第7章手稿 `kc_04→kc_05`。
- 复核：改后前端 kc binds/effect 与权威逐项一致；引擎侧 kc_06 正确解锁 flavor_3、错卡 kc_05 被拒绝。

**C1 · 破绽五门控悖论固化到数据层**（`clue_032.json` + `engine_driver.py` + `truth.json`）
- 症结：clue_032 锁 review:credits（指认之后），破绽5正常流程拿不到，只靠 engine_driver 硬编码前缀的隐式补丁兜底，补丁回归即致命。
- 修复：给 `clue_032` 新增契约字段 `auto_grant_on_boss_final: true` + `_note_c1` 说明，把「进入终局裁决即视为复盘达成」的语义写入数据层；`engine_driver._finalize` 改为**读取该字段**发放（兼容旧 review: 前缀）；`truth.json.reveal_condition` 同步指向该字段。
- 复核：E2E 仍 PASS（终局→clue_032 发放→破绽数 5→kanshan_still_mountain）。

### 已在前几轮修复、本轮实跑确认无需再动（C2/C3/C4/C5/C7/C8/C9）
- C5 主谋：前端已无 `target==='char_03'` 主谋分支，已对齐权威 char_01。
- C9 协议：前端已读 `p.ending_id` 且含 id 映射表。
- C7 署名：creditsSalt 已含《穿越大明，我被崇祯偷听心声》。
- C8 阈值：前端 perfect 文案已统一 ≥90%。
- C2/C3/C4：结局清单口径已收敛。

### 全量回归验证（本轮）
- 引擎+服务端测试套件：`tests/ + engine/test_engine_suite.py` → **232 passed, 2 skipped, 3 xfailed, 0 failed**。
- 前端无头冒烟：`frontend/tests/smoke_v31.js` → **63 PASS / 0 FAIL**（含开导红灯/转绿逻辑；因 kc_01 现正确绑 char_06，测试错配用例改用 kc_02）。
- 只读审计脚本：**9/9 NOT-REPRO，E2E PASS**。
- 语法校验：data.js `node --check` OK；clue_032/truth.json JSON OK；engine_driver.py AST OK。

> 备注：本轮为在沙箱运行测试补装了 pytest / pytest-asyncio / starlette / fastapi 等依赖（原 10 项 test_degradation 失败纯属沙箱缺 pytest-asyncio 插件的环境误报，补装后全绿，非代码缺陷）。项目上线前唯一真实待办仍是配置 4 个知乎 OAuth 环境变量以解除 degraded。
