# 多窗口提示词包（V2 采纳后增量版）

> 使用方法：每个新窗口粘一段即可。所有窗口共用工作区 `D:\Vibe coding\知乎黑客松\game`，契约与设计文档在 `docs/`。
> 现状基线：B/C/D/E/F 基础交付全部完成（E2E 12/12+回放 1/1 全 PASS），本包是**采纳后增量**任务；G 为全新开窗。
> 铁律（每条提示词已内置）：只写自己管辖目录 / faction 禁止透出前端 / 共享文档整文件 UTF-8 重写 / 不直连外部 API / Python 一律用 envs/default venv。

---

## B 引擎组（on-call：按需支持，无硬缺口）

```
你是 B 引擎组窗口（on-call）。工作区：D:\Vibe coding\知乎黑客松\game
你的 engine/ 七模块+party.py+difficulty.py 已交付（176 断言全 PASS），无硬缺口。
本次任务：待命支持 F 的 party 路由联调——F 调 PartyBoard/DifficultyDirector 时若接口不匹配，
按最小增量补方法（不改既有签名），改动记 engine/STATUS.md §七。
若 30 分钟内无联调请求，转做：把 _smoke_test.py 的 176 断言整理成 tests/test_engine_*.py 的
pytest 形式（写 tests/ 需先征得 G 窗口同意，或只产出 engine/_pytest_bridge.py 于 engine/ 内）。
```

## C Agent 组（侦探报告 + 演出层）

```
你是 C Agent 组窗口。工作区：D:\Vibe coding\知乎黑客松\game
先读：docs/MEGA_MODE.md §三、docs/GAMEPLAY_V31.md §二~§五+§七、docs/CONTRACTS.md（§四 faction 铁律）、engine/STATUS.md §六（achievements() 返回结构）。
任务（只写 agents/）：
1. 侦探报告生成器：消费 engine resolver.achievements() 确定性返回值（评分/高光操作/锐评/成就徽章），LLM 只做文笔润色，判定不改判；
2. 演出接口：系统抽风播报、心声广播事故主持、急诊室抢救演出、头条竞标主持（P1）+ 广播台/反诈小剧场/终局陈词锐评/快问快答出题（P2）；
3. 防卡死"档案局备忘录"生成（消费 difficulty.py assist 档输出）。
硬规则：只写 agents/；AI 只演不裁；无 LLM key 时 MockProvider 必须能跑通全部新接口；
完成后 agents/STATUS.md 追加 §七，报告"C 增量完成"。
```

## D 内容组（文案库扩充）

```
你是 D 内容组窗口。工作区：D:\Vibe coding\知乎黑客松\game
先读：docs/GAMEPLAY_V31.md §二~§五+§九、docs/MEGA_MODE.md §三、engine/STATUS.md §六（achievements 枚举）。
任务（只写 content/scenarios/kanshan/）：
1. 成就文案库：看山还是山/心晴医师/带节奏之王/鱼干守护者/防折叠斗士/暗房大师/全场公敌——每条 50 字内标题+描述；
2. scripts/ 补台词埋点：系统抽风池（≥6 条）、急诊室抢救演出、头条竞标主持词、档案局广播台文案、快问快答题库（≥8 题，本案相关知乎式）、反诈小剧场脚本；
3. P3：鱼干收集品 3 处位置定义 + 看山 Bot 隐藏语音文本；minis 文案：看山快跑障碍词库、心声窃听器题库说明、谣言消消乐词条、侦探花名池（≥20 个欢乐警衔）。
硬规则：只写 kanshan/；JSON 对照 schemas/；整文件 UTF-8 重写（禁止追加式半写）；引用官方内容保留署名。
完成后 kanshan/STATUS.md 追加，报告"D 增量完成"。
```

## E 前端组（增量 UI + 小游戏层）

> **阻塞已全部清零（2026-09-12 15:4x A 确认）**：①D 真内容已交付（kanshan/ 121 文件，data.js 可切 fetch scenario.json）②F 8899 真实引擎服务常驻（WS 直连）③B+M1 接线完成（真引擎已替换 mock 裁决）——E 的 STATUS.md §六 三个对接点全部就绪，**增量 UI 无等待依赖，立即开工**；基础九视图已合格，本次为纯增量，不要重做。

```
你是 E 前端组窗口。工作区：D:\Vibe coding\知乎黑客松\game
先读：docs/GAMEPLAY_V31.md（§二~§五 环节 + §9.4 安放位图 + §八 裁决）、docs/CONTRACTS.md（§四 美术规约+faction 铁律）、frontend/STATUS.md。
任务（只写 frontend/）：
1. P1 UI：弹幕押注面板 / 系统抽风横幅 / 急诊室红灯 / 头条竞标 / 幕间电梯转场；
2. MEGA：侦探证 UI（登录后，消费 /api/profile/me）+ 侦探报告页 + Canvas 分享卡（复用 logo_badge/scene_exterior）；
3. P2 UI：记忆拼图投票 / 线索暗拍 / 反诈剧场 / 终局陈词计时；
4. 小游戏层（§9.4）：frontend/minis/shell.js 统一壳（计分/战报/分享）+ 四件：runner.js（看山快跑，官方 kanshan.png 30 帧雪碧图 steps() 切帧）、heart.js（心声窃听器，消费 /api/minis/memory-puzzle）、refute3.js（谣言消消乐，/api/minis/hotfeed-pool）、badge.js（侦探证每日抽，/api/profile/me）；
5. 复盘页常驻 flavor_5 署名小字；对话流 DM 形象接入官方 kanshan 雪碧图行走动画；
6. 数据切换：js/data.js 的 mock 换成 fetch content/scenarios/kanshan/scenario.json（D 已交付 121 文件），WS 联调 ?ws=ws://127.0.0.1:8899/ws/{id}（F 服务常驻，真引擎模式）。
硬规则：只写 frontend/；美术仅三白名单（官方素材/content/assets/代码绘制），禁止外链灰占位；#/mini/{id} hash 路由；M2 免登录可达。
完成后浏览器全界面可点 + minis 四件可玩可分享，frontend/STATUS.md 追加，报告"E 增量完成"。
```

## F 服务端组（增量路由 + party）

```
你是 F 服务端组窗口。工作区：D:\Vibe coding\知乎黑客松\game
先读：docs/MEGA_MODE.md §一/§二、docs/GAMEPLAY_V31.md §9.4、docs/CONTRACTS.md §3.6/3.7、engine/STATUS.md §六（PartyBoard/DifficultyDirector 接口）。
任务（只写 server/）：
1. POST /api/session/{id}/login（OAuth code 换 token）+ GET /api/profile/me（代理 openapi.zhihu.com/user，只透出 uid/昵称/头像/headline，email/phone 零透出）；
2. party：WS 房间多人态（接 engine/party.py PartyBoard）、真人私聊路由、掉线 ai_takeover 广播（只说"该角色已由 AI 接管"，不透阵营）、观战视角；
3. GET /api/minis/memory-puzzle 与 /api/minis/hotfeed-pool（脱敏抽样、无鉴权、可缓存、零额度）；
4. 每轮轮转时调用 ks.set_round()（急诊室红灯轮次注入）；确认 GET /assets/* 静态路由已挂载。
硬规则：只写 server/；路由与事件结构按契约；faction 字段零透出；凭证仅环境变量；Python 用
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe（fastapi/uvicorn/httpx 已装）。
完成后重启 8899 服务（ZHIHU_GAME_USE_MOCK_ENGINE=0），curl 实测新路由，server/STATUS.md 追加，报告"F 增量完成"。
```

## G 测试组（全新开窗）

```
你是 G 测试组窗口。工作区：D:\Vibe coding\知乎黑客松\game
先读：docs/CONTRACTS.md、docs/GAME_DESIGN_V3.md、docs/GAMEPLAY_V31.md、docs/DM_BOSS_DESIGN.md、docs/KNOWLEDGE_SYSTEM.md、engine/STATUS.md、server/STATUS.md。
任务（只写 tests/，pytest 形式）：
1. 引擎九模块单测（stage_machine/evidence_chain/timeline/resolver/memory_system/opinion_feed/knowledge_cards/party/difficulty）；
2. D 资产 schema 校验（kanshan/ 全 JSON 对照 schemas/）；
3. 端到端：起服（envs/default venv，ZHIHU_GAME_USE_MOCK_ENGINE=0）跑单人三幕全流程——含 boss 链（5 破绽→指认 DM→看山还是山）与全员心晴分支；
4. party 多人端到端（2 人+AI 补位）；V31 环节单测（押注赔付/急诊双倍限一次/头条竞标/拼图判定/暗拍/双面锁）；
5. 阵营平衡模拟（污染/求真 45-55%）；API 降级演练（直答 429→兜底文案）。
硬规则：只写 tests/；发现契约/实现问题记录 tests/STATUS.md 报给用户转 A，不许自行改其他目录；
Python 用 envs/default venv。完成后 pytest 全绿（允许显式 skip），报告"G 完成"。
```

---

## 里程碑与顺序

M1 ✅（B+F 接线+E2E）→ **现在可同时开：C / D / E / F / G 五窗**（B on-call 可选）→ 各窗 STATUS.md 汇报 → A 集成验收（M3）→ 部署提报（M4，9.15 10:00 截止）。
