# 生产工作台 v2 重构 · E2E 验收报告

> 日期：2026-09-15 01:20 · 验收人：老公（协调者）· 依据：STUDIO_V2_PLAN.md
> 结论：**全链路打通。玩家一句话生成剧本 → 叙事闸门 → 剧本工坊 → 单人模式实玩，全部验证通过。**

## 一、团队分工与交付（4 智能体并行）

| 智能体 | 交付 | 测试证据 | 零副作用 |
|---|---|---|---|
| agent-bridge | `server/zhihu_bridge.py`（黑客松内容 API 直调+24h 缓存+署名台账+Z2 优雅降级+sanitize_excerpt） | 14 passed（零网络 mock） | 仅新增 2 文件 |
| agent-golden | `studio/casebook/distill.py` + kanshan_golden.json（34 线索/14 真相节点/6 伪证/双层心声/35 关系边）+ llm_steps.py 三步注入 few-shot | distill 实跑 + mock 生成 ready | kanshan 哈希基线一致 |
| agent-gate | validate.py 追加 V1 时间线一致性/V2 真相可达性/V3 伪证闭环（NARRATIVE_GATE=0 可关） | 8 passed；坏样本×3 全拦；mutation test 关闸 6 failed → 恢复全绿 | kanshan 副本实测 0 error |
| agent-pipeline | POST /api/studio/generate（202 异步受理+单飞锁）+ GET jobs/catalog + frontend/js/select.js「剧本工坊」+ index.html 1 行 | test_studio_api 6 passed + e2e 9 passed | data.js/store.js 未动 |

协调者串行复跑四套件：**43 passed**（消除并发 tmp 冲突误报）。

## 二、E2E 实操证据（真服务 8891 实例，全程 HTTP 200）

```
1. POST /api/studio/generate {"seed":"深夜自习室，所有课本一夜之间变成空白","use_llm":false}
   → 202 {job_id: job_6a3a1e5fa04f, status: running}
2. GET /api/studio/jobs/job_6a3a1e5fa04f
   → {status: ready, gate.ok: true, provider: mock}   ← 叙事闸门 v2 通过
   → 产出剧本包 gen_pack_ba95e34a_692806（覆盖同 seed 旧 failed 包）
3. GET /api/studio/catalog → 13 个剧本（ready/failed 状态徽标正确）
4. POST /api/session {mode:"quick", player_id:"player:e2e", scenario_id:"gen_pack_ba95e34a_692806"}
   → 200 {session_id: s_20260915_06118996}            ← 单人模式建局成功
5. POST /api/session/{sid}/action {type:"search", payload:{location:"loc_reception", keyword:"前台"}}
   → 200 事件：clue_gained「半块鱼干+纸条：别找了，摸鱼中。」
     + 知识卡《如何走出职业倦怠？》（作者：草芽君Psy）  ← 实玩取证
```

## 三、发现与修复

| # | 发现 | 处置 |
|---|---|---|
| 1 | 8899 端口旧实例（00:56 启动）加载了 agent-gate 编辑中间态 validate.py → generate 报 `NameError: _check_timeline_consistency` | 非代码缺陷：磁盘最终态三检查器可导入验证通过；换 8891 新实例复验通过。**教训：热改动后必须重启服务进程** |
| 2 | 搜证 payload 字段实际为 `location`（非 keyword），keyword 是搜索词 | 已按 engine_driver.py:696 三口径（loc_*/key/中文名）正确调用 |
| 3 | agent-golden 报告并发写冲突（prompt 文件曾被回滚） | 各智能体已自恢复；最终态串行复测 43 passed 证明完好 |
| 4 | git 工作区存在 9/14 会话遗留未提交改动（store.js/llm_client.py/npc_social.py 等） | 与本次改动边界清晰不冲突；注释带 2026-09-14 标记可辨 |

## 四、前端设计对账与二次优化（2026-09-15 01:30 追加）

用户复核"前端是否按方案优化"后发现三处缺口，已处置：

| # | 发现 | 处置 |
|---|---|---|
| 1 | agent-pipeline 的 `frontend/js/select.js` 与 9/14 既有的主菜单「我的剧本架」（main.js shelf 体系，playStudio 接线/闸门标签/offline 空态齐全）完全重叠，且为风格错位的孤立悬浮钮（硬编码知乎蓝，游离于琥珀金卷宗设计体系外） | **已删除** select.js 及 index.html 引用；「我的剧本架」为唯一选本入口 |
| 2 | 剧本架 9/14 有骨无皮：`.menu-shelf/.shelf-item/.shelf-tag` 在全部 CSS 无定义（裸列表） | **已补齐** studio.css 琥珀金卷宗风样式（13 个类 + 移动端适配），与创作工坊视觉同族 |
| 3 | 选本数据源双轨：shelf 走既有 `GET /api/studio`（list_jobs），agent-pipeline 另加 `GET /api/studio/catalog` | catalog 保留为方案 API 契约（幂等只读）；shelf 不动；两源实跑均 13 本一致 |

**复验**（8891 干净实例）：index.html 200 且无 select.js 残留 / studio.css 200 / `/api/studio` 13 本（含今日 E2E 生成的 gen_pack_ba95e34a_692806 · ready）。今日生成的剧本即刻出现在主菜单剧本架。浏览器截图因沙箱限制未执行，以静态资源 200 + 样式定义实查替代。

## 五、前端真实浏览器测试（2026-09-15 01:55 追加，用户授权）

方案：系统 Edge headless + 裸 CDP（Node 内置 WebSocket，零 npm 依赖），脚本 `game/data/_e2e_shots/cdp_test.mjs`，截图 6 张同目录。

| # | 用例 | 结果 | 证据 |
|---|---|---|---|
| T1 | 主菜单渲染 | PASS | h1「求真档案局·看山失踪夜」，截图 T1_menu.png |
| T2 | 剧本架展开+样式生效 | PASS | 14 本全 playable，menu-shelf 边框 1px（补齐样式已生效） |
| T3 | 剧本架开本建局 | PASS | phase menu→seat，进入「领取今晚的故事本」角色选择（截图 T3） |
| T4 | 创作工作台打开 | PASS | 「创一本·开发工作台」 |
| T5 | 知乎热榜选题接入 | PASS | 未配置 Access Secret 时优雅降级提示，不阻塞手写 |
| T6 | **工作台生成全链路（202 异步轮询）** | **PASS** | status=ready + gateOk=true，toast「新本已写成并通过闸门」，自动跳「13 开局」（截图 T6） |
| T7 | 开局步骤四页签 | PASS | 海报/角色/证据/导演视角 |
| T8 | 剧本架含新本 | PASS* | 14→15 本入库；首跑断言按标题找「便利店」失败属测试脚本缺陷（mock 标题池不反映 seed），已用计数复核 |

*T8 首跑 FAIL 为测试脚本断言缺陷 + 首版脚本 phase 状态污染，均已复核排除产品问题。

**测试中发现并记录：**
1. UX：剧本架入口（「我的剧本架 ▾」）位于主菜单折叠线下方，1440×920 视口不可见——用户此前感知"没变"的主因之一；建议后续把入口上移或与「开始调查」并列（涉及 main.js 模板按钮顺序，未擅自改动）。
2. 内容：mock_bible 标题池对 seed 不敏感（不同 seed 产出同名「热榜机房」）——mock 仅用于链路验证，上线生成走 use_llm=true 知乎直答。
## 六、当前状态与后续


- ✅ 可玩通路：一句话 seed → mock/LLM 生成 → 闸门 → 工坊选本 → 单人/quick 实玩
- ⏳ use_llm=true 走知乎直答生成（质量升级，需服务重启后开启；mock 已证明管线健壮）
- ⏳ 知乎热榜/故事素材接入生成（zhihu_bridge 已就绪，generate 的 zhihu 参数已透传占位）
- ⚠️ 提交纪律：8899 旧实例需重启才能加载全部新代码；上线前按 DEPLOY.md 走容器化发布
