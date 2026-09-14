# V4 综艺化升级方案：大圆桌 + 剧本杀综艺流程 + 智能体知识体系

> 需求：前端全量 Agnes 美术化、对话界面大圆桌、流程对标剧本杀综艺（《明星大侦探》式）、机制与剧情穿插、智能体知识库/记忆文档/skill 体系、知乎官方 skill/api 深度利用、6 组并行完成。
> 开发者手册核对（feishu Mc80dR5X）：赛道③方向吻合✓、刘看山 IP 资源已入库✓、提报字段与评审五维度已有对策✓（SUBMISSION_产品说明.md）。官方美术资产 = 刘看山 IP 形象资源 + liukanshan 官网素材（已入库 8 件 content/assets/official/kanshan/）。

## 一、综艺化流程（《明星大侦探》式，机制剧情穿插）

| 环节 | 综艺参照 | 游戏实现 | 美术 |
|---|---|---|---|
| ① 开场视频 | 案件开场 VCR | opening.mp4 全屏播放 + 字幕卡 | 已有 |
| ② 案件介绍 | 何老师讲案情 | DM（看山系统音）分三段讲案情 + 案件卷宗页（可翻阅证物照片） | ui_case_file |
| ③ 嫌疑人亮相 | 角色自我介绍 | 大圆桌：8 座位逐一亮灯，AI 自动自我介绍（腔调台词+立绘升起） | ui_roundtable + 立绘 |
| ④ 第一轮搜证 | 现场搜证（限时） | 场景图 11 地点搜证（各地点真图弹窗）+ 暗拍 | scene_*.png + ui_map_bg |
| ⑤ 集中讨论 | 圆桌讨论（拍桌/对视/插话） | **大圆桌 UI**：发言者头像升至桌面中央，其他座位微光呼应；弹幕押注穿插 | ui_roundtable |
| ⑥ 第一次指认 | 非正式投票 | 圆桌内快速举手表决（不影响结局，喂弹幕梗） | ui_roundtable |
| ⑦ 第二轮：不在场证明 | 逐一还原时间线 | 双层记忆对质（心声 vs 口供）+ 记忆拼图 | act_t2 + memory 视图 |
| ⑧ 机制穿插 | 芒果 TV 每期一个机制 | V31 机制按幕解锁：急诊室/头条竞标/反诈剧场/双面锁 | 幕内嵌入 |
| ⑨ 第三轮：热搜风暴 | 舆论反转 | 热搜面板全开：买热搜/辟谣/头条竞标/策反 | act_t3 + ui_hotfeed_bg |
| ⑩ 最终指认 | 投票指认真凶 | 大圆桌投票（聚合+平票 hung） | ui_vote_bg |
| ⑪ 揭晓 | 复盘 + 看山归位 | 双层真相揭晓 + Boss 演出（官方雪碧图）+ 心晴诊室 | ui_report_bg + ui_clinic_bg |

幕间转场：act_t1/t2/t3 全屏插画 + 电梯运镜（既有）。

## 二、大圆桌 UI 规格（对话界面重构）——【修订版：9 席位】

> A 裁决（2026-09-12）：席位规格修正为 **9 席 = 1 DM + 8 嫌疑人**（此前"12 席位"系把观众装饰位混入逻辑席位，作废）。真人 1-5 名扮演嫌疑人席（faction 暗置发牌），余位 AI 补齐；单人模式 8 席全 AI，玩家以调查员视角在圆桌缺口位（镜头位）。观战/旁听一律桌外，不占席位。

- 布局：`ui_roundtable.png` 为桌面底图铺满；**9 席环形绝对定位（上 1 DM 居中，其余 8 席每 45° 环绕）**；
- 发言机制：当前发言者头像放大 + 座位聚光灯（CSS 亮环），发言气泡从座位升起（transform 过渡）；非发言者降暗；
- 心声：解锁后发言气泡双层（口供白/心声紫渐变边）；
- 弹幕押注：圆桌外圈环形飘过；
- 移动端：圆桌缩放 + 座位头像环绕顶部横排。

## 三、智能体知识体系（知识库/记忆文档/skill）

| 层 | 内容 | 落点 |
|---|---|---|
| **知识库** | 每个 NPC 一份"人设知识文档"（人设/当晚轨迹/秘密/说话风格/心病），AgentRuntime 启动加载注入 system prompt；知乎知识 10 篇原文作为知识卡权威库 | `content/scenarios/kanshan/memory/`（已有）+ 新增 `agents/knowledge/*.md` |
| **记忆文档** | 对话短期记忆（已有 short_term 12 条）+ **跨幕长期记忆摘要**（每幕结算时 Judge 生成 200 字摘要写入记忆文档，下一幕注入）+ 玩家行为画像（对谁好/锤过谁） | AgentRuntime 新增 `memory_doc` 字段 + 幕结算钩子 |
| **skill（C 组脚本）** | 每个 NPC 一份"说话风格 skill 文件"（句式模板/口头禅/禁区），llm_client few-shot 注入；DM 一份"综艺主持 skill"（节奏控制/梗投放/救场话术） | `agents/skills/npc_<id>.md` + `agents/skills/dm_host.md` |
| **知乎 skill 接入** | ①登录后 user profile → 侦探证（已接）②creator stats → 侦探报告彩蛋（"你知乎Lv"梗）③question recommend 画像（默认关）④knowledge upload：把本局侦探报告存入玩家知乎知识库（可选开关） | server/gateway + agents |

## 四、6 组分工（并行，文件所有权零冲突）

| 组 | 管辖 | 核心任务 |
|---|---|---|
| **G1 大圆桌 UI** | frontend/views/chat.js + css | §二 大圆桌重构（桌面底图+12 席位+发言聚光灯+心声双层气泡） |
| **G2 综艺流程** | frontend/main.js/store.js/views(map/report) | §一 流程编排：开场视频页/案件卷宗页/转场插画/各环节视图切换 |
| **G3 引擎编排** | server/engine_driver.py + engine/stage_machine.py | 综艺阶段事件（case_intro/first_vote 等）+ actSet 对齐 + 机制幕门控维护 |
| **G4 智能体记忆** | agents/bridge.py + agents/skills/ + agents/knowledge/ | §三 知识库/记忆文档/说话风格 skill 文件体系 |
| **G5 知乎能力** | server/gateway/zhihu_gateway.py | 官方 skill 0.7.2 深度接入（profile/creator/knowledge upload），限额纪律 |
| **G6 验收** | tests/ | 全量回归 + 新功能 e2e（大圆桌/综艺流程/报告）+ 线上验收截图 |

共享规约沿用 CONTRACTS：faction 零透出 / UTF-8 整文件重写 / 不直连 API / 编辑前重读。
