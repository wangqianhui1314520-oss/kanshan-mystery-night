# frontend/STATUS.md —— E 前端组交付状态

> 更新：2026-09-12 · 状态：**E 增量完成**（P1/P2 UI + MEGA + P3 微光点 + minis 小游戏层全量；Mock 跑通全部界面，WS 对接层就绪）
> 验收方式：Chrome/Edge headless 截图逐视图验收 + Node+真实Vue 无头冒烟 **63/63 通过**（`tests/smoke_v31.js`）+ 全部模板编译检查通过。

## 一、交付物

```
frontend/
├── index.html                 # Vue3 单页入口（免构建，file:// 可直开；#/mini/{id} 免登录外链）
├── css/
│   ├── style.css              # 深色档案局 HUD + 知乎蓝 #0084FF，移动端适配
│   ├── v31.css                # V31 增量（押注/抽风/红灯/竞标/电梯/侦探证/报告/拼图/暗拍/剧场/陈词/dm-walk/微光点）——整文件重写维护
│   └── minis.css              # 小游戏层样式
├── js/
│   ├── vendor/vue.global.prod.js  # Vue 3.4.38 本地运行时（断网可跑，非美术外链）
│   ├── data.js                # mock 数据（对齐 CONTRACTS schema）+ V31 文案池（glitch/bet/er/headline/antifraud/dossier/徽章/鱼干收集/隐藏语音/flavor5Credit）
│   ├── store.js               # 响应式状态 + 本地引擎（V31 全动作）+ applyV31SystemEvent + buildReport + localStorage 存档
│   ├── net.js                 # WebSocket 对接层：MockTransport / WSTransport
│   ├── ui.js                  # 共享组件（dm-walk 雪碧图行走 / countdown-ring / elevator-cut / bet-panel / fish-voice / 弹幕层 / 热度仪表 / 卡面 / 手绘SVG场景）
│   ├── main.js                # 根应用（HUD/导航/启动/事件接线/minis hash 路由同步）
│   └── views/                 # 9 视图 + 增量
│       ├── map.js             # 场景图搜证 + P3 微光点锚点（节点角标+场景内锚点）+ 暗拍入口
│       ├── chat.js            # 对话流 + 弹幕 + 押注面板内嵌 + DM 官方雪碧图形象
│       ├── bag.js             # 证物袋 + 暗拍照片墙/流出 + 鱼干收集 tab
│       ├── kcards.js          # 知识卡图鉴
│       ├── memory.js          # 双层记忆 + 记忆拼图对质（60s）
│       ├── hotfeed.js         # 热搜面板 + 头条竞标（8 话题池/欢乐位）
│       ├── vote.js            # 圆桌投票 + 终局陈词 60s 计时 + 锤人分池
│       ├── clinic.js          # 心晴诊室 + 急诊红灯带 + 抢救转绿演出
│       ├── review.js          # 复盘 + Boss 揭示（含鱼干终极层加播）+ flavor_5 常驻署名 + minis 入口
│       ├── report.js          # 侦探档案：侦探证（/api/profile/me 消费）+ 报告 + Canvas 分享卡 + 迷你游戏厅
│       └── antifraud.js       # 反诈剧场全屏演出（30s 倒计时 + 三幕 + 识骗判断）
├── minis/                     # 小游戏层（§9.4 安放位图全做）
│   ├── shell.js               # 统一壳：注册表/hash 路由/计分/战报/Canvas 分享（与侦探报告同管线）
│   ├── main-minis.js          # mini-host 宿主接入主应用
│   ├── runner.js              # M1 看山快跑（官方 kanshan.png 30 帧 Canvas 跑酷）
│   ├── heart.js               # M2 心声窃听器（/api/minis/memory-puzzle + heart-quiz；无后端降级 D 题库）
│   ├── refute3.js             # M3 谣言消消乐（/api/minis/hotfeed-pool + match-3 词条对）
│   └── badge.js               # M4 侦探证每日抽（/api/profile/me；uid+日期确定性签）
├── tests/
│   ├── smoke_v31.js           # Node+真实Vue 无头冒烟 63 断言
│   └── shots/                 # 各轮验收截图
└── STATUS.md                  # 本文件（整文件重写维护——追加式写入曾致 v31.css/本文件损坏）
```

## 二、玩法功能清单（全部可点，Mock 引擎驱动）

| 界面 | 状态 | 说明 |
|---|---|---|
| 场景图搜证 | ✅ | 11 地点、热度三档、关键词建议+自由输入、1AP/次、环境彩蛋 + **P3 微光点（3 处呼吸闪烁/act 门槛/0AP 拾取）** + **暗拍 2AP** |
| 对话流+弹幕 | ✅ | 8 NPC+DM 名册、心声注入、AI 热评、唤醒词彩蛋 + **押注面板内嵌（币种=赞数）** + **DM 官方雪碧图形象** |
| 证物袋 | ✅ | 五级卡面、伪证交叉验证、证据合成 + **暗拍照片墙/流出+声称** + **鱼干收集 tab（n/3）** |
| 知识卡图鉴 | ✅ | 10 卡收集、翻卡动效 |
| 记忆双层 | ✅ | V1-V3 解锁、篡改点高亮转线索 + **记忆拼图对质（2 篡改点/60s 排时间线）** |
| 热搜面板 | ✅ | SVG 仪表、辟谣匹配/反涨、买热搜 + **头条竞标（平价先到先得/流拍+2/欢乐位）** |
| 圆桌投票 | ✅ | ≥2 证据卡、破绽 5/5 指认 DM + **终局陈词 60s 计时 + 锤人分池（most_hammered）** |
| 心晴诊室 | ✅ | 开导 2AP 匹配/群嘲、终局三档、金句回放 + **急诊红灯带（expiry=轮+1/每局一次/抢救双倍/转绿闪光）** |
| 复盘页 | ✅ | 时间线、Boss 全屏演出（集齐鱼干加播第 5 段语音）、破绽回顾、署名区 + **flavor_5 常驻署名小字（两态常驻）** + minis 入口 |
| 结局 | ✅ | 9 种结局 |
| 侦探档案 | ✅ | **侦探证（登录/mock 双路径）**、**侦探报告（WS 事件/mock 同构）**、**Canvas 分享卡（1080×1440）**、徽章墙 11 枚、**迷你游戏厅** |
| 反诈剧场 | ✅ | 辟谣成功 30% 触发（≤2 次/局）、三幕剧本+识骗判断题、30s 总倒计时 |
| 幕间电梯 | ✅ | 跨幕全屏转场：关门→LCD 跳层→门开 DM 走出 |
| 抽风横幅 | ✅ | 惩罚/故障/奖励三池、glitch 抖动→DM 重写、ap_free/heat_bump |
| 押注结算 | ✅ | advance 结算全池按比例赔付、加热 +1~5、连押 3 轮彩蛋、流拍 +2 |
| minis 四件 | ✅ | runner/heart/refute3/badge（见 §九）——可玩/可计分/可分享导出 |

## 三、WebSocket 对接层（对接 F 服务端）

- 协议：CONTRACTS §3.6 事件包络；§3.7 路由。上行 6 类动作 + V31 新 skill kind（place_bet/bid_headline/stealth_photo/share_photo/memory_puzzle/antifraud_answer/closing_speech/hammer_vote/claim_dossier/collect）。
- 下行接线：11 种协议事件 + V31 扩展（headline_result/detective_report/achievement_unlocked/broadcast_accident/collect_result/glitch/er_*/bet_*/memory_puzzle_result/antifraud_result/closing_registered/hammer_result/dossier_ready/photo_*/stealth_photo/elevator_run）。
- 切换：`?ws=ws://host:port/ws/{session_id}` → 自动建对局连 WS；失败自动降级 Mock。`?view=` 直达视图；`#/mini/{id}` 免登录直达小游戏。

## 四、美术合规（规约④全条目核对）

- 真图引用全部存在于 content/assets/（官方 kanshan 系 + Agnes 生成）；零外链、零灰占位、零 lorem。
- minis 分享卡/侦探报告分享卡复用 logo_badge + scene_exterior + 官方 kanshan.png 印章。
- CSS/SVG/Canvas 手绘补位（规约③）：电梯、微光点、拍立得、拼图、计时环、跑酷走廊等全为代码绘制。
- 隐私：/api/profile/me 只取公开三件套，email/phone 忽略；不上传用户数据；分享卡只导出图片不做自动发布。

## 五、验收证据

1. **无头冒烟（Node + 真实 Vue 3.4.38）**：`node frontend/tests/smoke_v31.js` → **63 PASS / 0 FAIL**：
   - 模板编译 17/17（全部视图+V31 增量组件）；V31 数据池完整性（抽风三池/押注话题/红灯 8 NPC 状态词/头条 8 话题/反诈三幕/侦探证映射/徽章 11 枚/flavor5Credit 含盐言三作署名）；
   - Mock 引擎全链路：advance 开盘系/押注扣赞/竞标 headline_result 形态/暗拍/照片流出/拼图门槛与判定/反诈答题/陈词登记/锤人分池/侦探证签发/红灯挂灯与抢救双倍/未知技能容错；
   - 跨幕电梯+抽风；applyEvent 消费（WS 形态回放）；终局报告；
   - P3 微光点全链路（act 门槛拒拾/拾取+Bot 反应/幂等/集齐触发/语音 4+1 段切片规格/锚点定义）；
   - P1/P2 文件对齐核验（话题池 8/流拍+2/红灯转绿/剧场 30s）；
   - minis（四件注册/数据源声明/壳 API/判定入口/盘面挂载/雪碧图切帧/profile-me/宿主）；资产引用完整性。
2. **截图验收**（tests/shots/）：九视图 + 移动端 + bet 开盘 + 头条竞标 + 终局陈词 + 侦探档案（DM 雪碧图）+ 复盘署名 + 微光点地图 + 鱼干收集 + minis 四件免登录直达。
3. 事故修复记录见 §九.4（v31.css 追加式损坏→整文件重写）。

## 六、遗留与对接点（给 A/F/C/D/B）

1. **D 内容组**：`js/data.js` 为 mock（结构=schema）。D 产出后把 data.js 换成 fetch/注入 scenario.json；flavor_5 常驻署名小字文案在 `data.js → flavor5Credit`（D 可直接替换为正式署名表）。
2. **F 服务端**：WSTransport 已按 §3.6/3.7 实现；V31 新 skill kind 需接进 engine_driver/rt（bid_headline/collect 已支持，其余见 store.js 注释）；`detective_report`/`achievement_unlocked`/`broadcast_accident` 等事件前端已全量接线。
3. **C Agent 组**：侦探报告页优先消费服务端 `detective_report` 事件（report_text/badges/achievements），mock 报告仅为保底；成就演出按 `banner`/`share_line` 文案。
4. **B 引擎组**：押注/急诊/暗拍/拼图/陈词的 mock 裁决语义已按 engine 模块对齐（settle_bet 全池赔付/er expiry=轮+1/stealth_photo 2AP/puzzle spend_tamper_points(2)/hammer 分池），真引擎接入时事件形态不变。
5. 移动端「更多」面板含全部视图入口；演示模式开关在 HUD 右上（解锁全功能 + 复盘页模拟结局入口）。

---

## 七、V31/MEGA_MODE 增量交付（2026-09-12 · E 组第二轮）

> 状态：**V31 全量 UI 完成**。无头冒烟 42/42 通过 + Edge headless 截图 9 视图验收。

### 交付清单（对照 GAMEPLAY_V31 §七-E）

| # | 任务 | 落点 | 说明 |
|---|---|---|---|
| P1-1 | 押注面板 | ui.js `bet-panel`（chat 底部内嵌）+ store.js `place_bet`/结算 | 币种=赞数（HUD 新增赞数芯片），全池归胜方按比例，猜错充公+AI 锐评；结算加热 +1~5 封顶；连续 3 轮押同一人触发「坚定保皇党」彩蛋；R1 即开盘，advance 每轮重开 |
| P1-2 | 抽风横幅 | data.js glitch 三池（对齐 segments_p1.md）+ applyEvent `glitch` | banner.glitch 故障抖动动画 → 1.6s 后 DM 重写句（glitch-fix 绿色）；effect：ap_free（下次行动免扣）/ heat_bump（热度+3）；每幕至多 2 次 |
| P1-3 | 急诊室红灯 | clinic.js er-strip + HUD 红灯芯片 + store.js er_light/er_rescue/er_expire | 开导失败挂灯（expiry=当前轮+1，每局限一次→第二次只群嘲）；下一轮内对口卡抢救=收益双倍（salt/buff 双倍结算）；红灯脉冲/长明灯双态 CSS |
| P1-4 | 头条竞标 | hotfeed.js headline-bid + store.js `bid_headline` | 出价=行动点、平价先到先得（AI 对手按热度确定性竞价）；中标帖热度翻倍结算；事件形态对齐服务端 `headline_result`（host_line/result_line/settle） |
| P1-5 | 幕间电梯转场 | ui.js `elevator-cut`（main.js 挂载） | 跨幕 advance 触发全屏演出：电梯门关闭→楼层 LCD 跳层（1F→3F·真相层）→门开+dm-walk 出场；点击跳过 |
| P1-6 | 侦探证 UI（登录后） | report.js `dossier-card`（HUD 按钮+弹窗+报告页复用） | mock 登录（WS 联机对接 GET /api/profile/me，失败降级表单）；警衔=简介欢乐映射+兜底池；证件照=官方 IP 家族 6 选 1；dossier_ready 事件+路人甲个性化彩蛋台词 |
| 2a | 侦探报告页 | views/report.js `VIEWS.report`（导航第 10 项） | 终局自动生成（mock buildReport / WS 消费 detective_report 事件同构）：推理评分+高光+徽章 |
| 2b | Canvas 分享卡 | report.js `drawShareCard`（1080×1440） | logo_badge+scene_exterior 合图+数据行+徽章 chips+侦探证头像+雪碧图 DM 印章+flavor_5 署名；toBlob 导出 PNG（file:// 污染时给降级提示）；只导出图片不做自动发布 |
| P2-1 | 记忆拼图投票 | memory.js 拼图对质面板（countdown-ring 60s） | 消耗 2 篡改点（memory_unlock 篡改点自动累积）；5 块已解锁记忆上下移排序，排对发奖励线索+成就「时间线钉子户」，排错 DM 锐评 |
| P2-2 | 暗拍 | map.js 暗拍按钮 + bag.js 照片墙/流出弹窗 + store.js `stealth_photo`/`share_photo` | 2AP：原件留原地（他人仍可搜，不入 state.clues）；照片流出+填「声称」；圆桌对质翻车钩子→成就「暗房大师」 |
| P2-3 | 反诈剧场 | views/antifraud.js `antifraud-theater`（全屏） | 辟谣成功 30% 触发（每局≤2 次）；三幕剧本对齐 segments_p2.md §三，逐行演出+每幕识骗判断题，全对反诈学分+1（成就「反诈先锋」）；可跳过 |
| P2-4 | 终局陈词计时 | vote.js closing-zone + countdown-ring | 60s 环形倒计时+陈词登记+「最想锤的人」分池投票（AI 加权票池）；hammer_result 横幅；不影响指认，供报告/成就（全场公敌/黄金六十秒） |
| 4a | flavor_5 常驻署名小字 | review.js credits 区 + 未解锁态 + data.js flavor5Credit | **D 对接点**：任何状态常驻——flavor_5 策划案落款 + 盐言三作署名（灯灯/凉风有信/反骨）一行小字 |
| 4b | DM 行走动画 | ui.js `dm-walk` | 官方 kanshan.png 3×10=30 帧切帧（A 规范：CSS steps(9) 逐帧横移 110px/帧）；row 0 站立挥手/1 行走挥手/2 赶路；缩放/翻转/速度可调 |

### 本轮修复（渲染/接线期，零副作用）

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 1 | Mock 通道全挂（send 必崩） | `window.Engine` 从未暴露且 Engine 对象非 net.js 期望的可调用签名 | store.js 暴露 `(action,payload,emit)` 可调用包装（未知动作诚实报错） |
| 2 | ui.js 组合式组件降级渲染（bet-panel 恒走 v-else） | ui.js 顶部未解构 `ref/computed`，setup 抛 ReferenceError | 顶部补 `const { ref, computed } = Vue` |
| 3 | R1 无押注/头条可玩 | 开盘只在 advance 后 | R1 初始化开盘（openRoundOne），advance 每轮重开 |

---

## 八、P3 微光点锚点 + P1/P2 文件对齐（2026-09-12 · E 组第三轮）

> 状态：**完成**。无头冒烟扩至 55/55 PASS + map/bag 截图验收。

### 1. P3 鱼干寻物支线（collectibles_p3.md 全链路落地）

| 环节 | 落点 | 说明 |
|---|---|---|
| 微光点锚点 | map.js 节点角标 + 搜证面板场景内锚点 | 3 处（fish_01 快递柜柜缝 / fish_02 天台石下 / fish_03 自习室书脊），CSS glow-dot 呼吸闪烁（周期对齐 D 规格 1s/2s/1.6s）；面板内锚点 hover 显示「拾取鱼干」提示 |
| 显隐规则 | glowVisible() | act 门槛（act1/act2/act3 起显形）+ 已拾取隐藏 + 终局隐藏——与引擎 cb.collect 的 act_no 校验语义一致 |
| 拾取动作 | store.js Engine.skill: collect（0AP） | 事件形态对齐 F 的 rt collect_result：{event:'collect_result', item, collected, all_collected, show}；act 未到/重复拾取/未知 id 诚实拒绝 |
| 拾取反馈 | applyEvent collect_result | 拾取台词（K 的三张便签）+ 看山Bot 反应句 + D 弹幕玩梗，逐条落对话流 |
| 集齐演出 | ui.js fish-voice（全屏组件） | 看山Bot 隐藏语音 4 段逐句打字机演出（切片不合并），成就「鱼干线人」横幅 |
| 终极层加播 | review.js BossReveal | 集齐后 Boss 揭示演出追加第 5 段语音（"主人回来了…"，斜体暖场行） |
| 收集进度 | map 顶部 chip + bag「鱼干收集 n/3」tab | bag 内 3 袋卡片显示锚点文案/拾取台词/幕门槛 |
| 分享卡 | report.js 徽章墙 | 徽章墙扩至 11 枚（+ach_yuganxianren）；engine share_line 字段为后续接入点 |

### 2. P1/P2 文件对齐（segments_p1.md / segments_p2.md 逐条核对）

| 项 | 对齐内容 |
|---|---|
| 头条话题池 | 替换为 D §3.3 的 8 话题（#8《本局最想请客吃饭的人》为纯欢乐位——中标不进热度结算） |
| 竞标文案 | 开标成功句/流拍句（"热度自己涨了 2"，流拍 +2 落账）/竞标失败句（"出价慢了半拍"）取自 D §3.1/3.4；阵营立场句（§3.2）按 A 裁决 #4 不在前端区分阵营，由 C 组生成后走 result_line 透出 |
| 红灯转绿 | 抢救成功 → erGreen 演出态：诊室红灯区"啪"转绿闪光（0.5s pop×2），文案对齐 §2.2 |
| 反诈剧场 | 头部加 30 秒总倒计时（数字+进度条，≤10s 变红），超时演出自动收束——对齐 §三"30 秒 AI 演出" |

---

## 九、minis 小游戏层 + MEGA 对接 + 全量 CSS 修复（2026-09-12 · E 组第四轮）

> 状态：**E 增量完成**。无头冒烟 **63/63 PASS**；#/mini/* 免登录外链截图验收 4 件 + 对话流 DM 雪碧图验收通过。

### 1. 小游戏层（frontend/minis/ · GAMEPLAY_V31 §9.2 架构约定 + minis.md 安放位图全做）

| 件 | 文件 | 玩法/数据源 | 安放位 |
|---|---|---|---|
| 统一壳 | minis/shell.js | 注册表（id/标题/入口位/数据源声明）+ `#/mini/{id}` hash 路由 + 计分/战报（localStorage kanshan_minis_v1）+ Canvas 分享卡（logo_badge+scene_exterior+雪碧图印章+flavor_5 署名，只导出不发布） | main-minis.js 挂 mini-host 视图 |
| M1 看山快跑 | minis/runner.js | Canvas 横版跑酷：官方 kanshan.png 30 帧切帧（110×124）跑动/跳跃/滑铲；D 词库 3 类障碍（低栏水军横幅/高栏热搜牌/飞弹纸团）+ 彩虹鳟鱼+1/金枪鱼-1 减速/叮加速/哈希复活甲；里程碑 47/587/1000m + Game Over 池 + 战报模板（minis.md §M1 原文） | 结算页"再玩点别的"/复盘页/分享卡附带；#/mini/runner |
| M2 心声窃听器 | minis/heart.js | 两句指认真心声（展示随机换位，回传题库坐标）；GET /api/minis/memory-puzzle?tier=open（免登录）/full（登录局内）→ POST /api/minis/heart-quiz 判定（answer/teaching 零透出）；无后端降级 D 题库本地判定（minis.md §M2 十题原文） | 免登录外链 #/mini/heart + 第二幕热身关 + 复盘页 |
| M3 谣言消消乐 | minis/refute3.js | 7×7 match-3：谣言块×辟谣标签块三连消除（D §3.1 十对词条，辟谣块带知乎知识署名）；叮块（万能）/折叠块/哈希块（×2）/金枪鱼异端块（扣分）；GET /api/minis/hotfeed-pool?n=8 作"今日谣言头条"轮换；无后端降级本地词条 | 复盘页 + 每日挑战"辟谣加练"；#/mini/refute3 |
| M4 侦探证每日抽 | minis/badge.js | uid+日期确定性抽签（今日警衔花名/运势/幸运话题，每日唯一可分享）；GET /api/profile/me（真实三件套+authorize_url 引导）；无后端降级 mock 档案 + D 花名池 | 侦探档案页（登录后建局前）；#/mini/badge |

- 入口：侦探档案页新增"迷你游戏厅"四卡；复盘页"再玩点别的"四入口；主线内 `#/mini/{id}` 免登录直达（M2 open 题零额度零案情词）。

### 2. MEGA 对接（/api/profile/me 消费）

- dossier-card 登录流程升级：WS 联机时先 GET `/api/profile/me?session_id&player_id` —— ok:true 直接消费真实公开三件套（badge_no/rank/owner/avatar_path 映射进侦探证，来源标记 zhihu）；未登录时透出 authorize_url 引导 + 降级登记表单；claim_dossier 引擎动作支持 uid6/rank 透传（对齐 F 的 ZhihuOAuth.dossier 结构）。

### 3. 对话流 DM 形象接官方雪碧图

- chat.js：头部 DM 形象 = dm-walk row0 站立挥手待机；气泡头像 = dm-walk row1 行走帧；roster/官方头像不变——全部官方 kanshan.png，零外链。

### 4. 事故记录：追加式写入损坏（本轮发现并修复）

- **症状**：chat 视图押注选项立绘裸奔 736×1312（.bet-opt img 约束失效）。
- **根因**：v31.css 与本文件此前经多次 shell `>>` 追加式写入，旧内容被截断（v31.css 前部整段丢失、大括号 169/170 不平衡；本文件 §七/§八 丢失且 §九 前插）——A 裁决"禁止追加式半写"的教训在 CSS/MD 上复现。
- **修复**：两文件均整文件 UTF-8 重写恢复（大括号 211/211 平衡；本文件含 §一~§九 全量），并在 v31.css 头注释固化规约：**本文件任何修改必须整文件重写**。
- 防御：本轮起所有长文件写入统一走整文件 Write，弃用 shell `>>` 追加。

### 验收
- `node frontend/tests/smoke_v31.js` → **63 PASS / 0 FAIL**（[9] minis 段：四件注册/数据源声明/壳 API/判定入口/盘面挂载/雪碧图切帧/profile-me 声明/宿主注册）。
- 截图：`tests/shots/fin_mini_{runner,heart,refute3,badge}.png`（免登录外链直达）+ `chat_fixed.png`（DM 雪碧图 + 押注面板约束正常）。
- M2 免登录链路：`#/mini/heart` 直开 → open 题面（无案情词）→ 答题 → 战报 → 分享卡导出。

---

## 十、V4 大圆桌对话界面重构（2026-09-12 · G1 大圆桌 UI 组）

> 状态：**完成**。真实引擎（8899 常驻服务）+ Playwright 浏览器实测验收，console 零圆桌相关报错。
> 依据：docs/V4_SHOWTIME.md §二（修订版：**9 席 = 1 DM 桌心 + 8 嫌疑人 45° 环绕**，调查员在桌外缺口镜头位观战）。

### 交付内容

| 项 | 落点 | 说明 |
|---|---|---|
| 圆桌舞台 | chat.js `.rt-stage` + v31.css §九 | 背景铺 `/assets/images/ui_roundtable.png`（同源圆桌俯视图，cover + 径向暗角），DM 席居中、8 嫌疑人席按 RING 坐标每 45° 绝对定位（百分比），每席 = 圆形头像（object-fit:cover）+ 名牌；席位点击即切换对话对象（替代原 roster 侧栏，换 NPC 功能保留） |
| 发言聚光灯 | chat.js `lastSpeak/speakingId` + `.rt-seat.speaking/.dimmed` | 最近一条 NPC/DM 发言驱动：发言者头像 scale(1.15) + 蓝色亮环（box-shadow 双层），其余席位与名牌降暗 opacity .55，全部 0.3s 过渡 |
| 座位升起气泡 | `.rt-bubble` + `bPos()` 朝向算法 | 发言气泡从座位上方升起（rt-rise keyframes，translate 12px→0 + opacity，0.3s ease-out）；顶部席位自动向下展开（.down）、左右边缘席位向内收（.bl/.br），箭头随动，零裁剪 |
| 心声双层气泡 | `.h-on` / `.heart-on` + `.rt-b-heart` 角标 | 解锁心声后该 NPC 气泡 = 口供层白边 + 紫渐变左边框（#b79bff→#6e50e6）+「心声」角标；席位头像右上角挂「心声」紫徽章；下方聊天列表内同步生效（::before/::after 实现） |
| 桌外镜头位 | `.rt-cam` | 舞台右下角常驻「调查员 · 桌外镜头位」标识（玩家观战位，无席位） |
| 既有功能保留 | 押注面板 / 弹幕层 / 输入框 / chat-hd | bet-panel 仍内嵌底部；danmaku-layer 改挂圆桌外圈上空（top 3%/height 50%）；输入框、唤醒词彩蛋、chat-hd 心声 chip、DM 雪碧图形象全部不动 |
| 移动端 ≤640px | v31.css @media 段 | 圆桌缩放（background 170%），DM 席顶部居中一行，8 席改 4 列×2 行 grid 横排，座位气泡/镜头位标签隐藏（聊天列表承载），聚光灯亮环保留 |

### 截图说明（Playwright 实测，`?view` 直达 chat 视图）

- `g1_chat_final.png`（桌面 1080p）：圆桌底图铺满、9 席环形（V587/瓜上仙/流量酱/路人甲/看山Bot/沉底君/盐值君/笔上仙 + DM 桌心）、流量酱发言聚光（放大+蓝亮环+他席降暗）、心声双层气泡（白边+紫左边框+心声角标）从其座位升起、弹幕外圈飘过、右下「调查员 · 桌外镜头位」、下方对话列表/输入框/押注面板齐全。
- `g1_chat_mobile.png`（390×780）：圆桌缩放，DM 顶部居中，8 席两行横排，聚光灯与心声徽章保持，底部导航正常。
- `g1_spotlight.png`：聚光灯中间态（发言者亮环与其余席位 .55 降暗对比）。

### 本轮修复与事故

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 1 | `.rt-stage` 背景 none、席位立绘裸奔成整屏海报 | v31.css 为多组共享文件，本组 §九 追加后被其他窗口整文件重写覆盖丢失（服务器侧规则数 248→无 .rt-stage） | 按契约重读最新版后合并回 §九（保留他组 V4 综艺段与 minis 段），复验 rules 281、背景生效——**共享 css 写入冲突需各组注意** |
| 2 | dm-walk 雪碧图 404（chat 视图 DM 形象消失） | v31.css 中 `url("..//assets/official/kanshan/kanshan.png")` 相对路径解析到 frontend/assets/（不存在） | 改绝对路径 `/assets/official/kanshan/kanshan.png`（content/assets 同源托管） |

### 验收结果

- Playwright（Chromium）实测 8899 真实引擎：DOM 断言 9 席位/DM 桌心/镜头位/背景图全过；console 仅剩 6 条 minis/*.js 404（既有遗留，与本轮无关），圆桌相关零报错。
- 桌面 + 移动端双视口截图通过；faction 数据零透出（席位/气泡/名牌仅用 public 三件套）。

---

## 十一、V4 综艺流程编排 + 全视图背景真图化（2026-09-12 · G2 综艺流程组）

> 状态：**G2 流程完成**。Playwright（Chromium）实测 Mock 全链「开场→卷宗→圆桌→搜证→幕转场→指认→复盘」零断点、console 零报错；v31.css 与 G1 双写冲突已按契约合并复验。
> 依据：docs/V4_SHOWTIME.md §一（11 环节综艺流程表）。管辖：main.js / store.js / views(map,report) / css。

### 1. showtime 状态机（store.js）

- `S.showtime = { step, cut }`：`intro`（开场覆盖层 cover/prologue/license）→ `case_file`（案件卷宗页）→ `act`（正常游玩）→ `accuse`（最终指认，vote 事件置入）→ `reveal`（揭晓复盘，ending 事件置入）；`cut={act:1|2|3}` 为幕转场全屏页瞬时演出态。
- 接线：`enterBureau()` 不再直进圆桌——先置 `case_file`（环节② 案件介绍先于环节③ 嫌疑人亮相）；`applyEvent` 的 `actSet` 分支插入 `cut`（幕切换自动触发转场）；`vote`/`ending` 事件分别切换 `accuse`/`reveal`。
- API：`Store.showtimeNext()`（卷宗确认 → act_t1 转场 → 破冰圆桌）、`Store.cutDismiss()`（转场跳过）。
- 纯演出态不入存档；默认 `step:'act'`，回访玩家（localStorage 直进）不重播卷宗页。

### 2. 新增环节视图（main.js）

| 视图 | 落点 | 说明 |
|---|---|---|
| 案件卷宗页 | `.st-casefile`（z-92 全屏） | 背景 `ui_case_file.png` 案卷底图；CASE FILE NO.0912 卷宗头 + 三段 DM 讲案情（机密等级 S 标签）+ 证物照片 `ui_chip.png`（证物 A-01 · 被编辑过的记忆芯片，删除段 21:07–21:15 · 000 号权限）+ DM 引言 + 「翻开卷宗 · 进入圆桌」按钮 |
| 三幕转场全屏页 | `.st-actcut`（z-93 全屏） | `act_t1/t2/t3.png` 按幕序全屏铺陈（缓慢推镜 actcut-pan 动画）+ DM 幕引言条（第一幕·破冰圆桌 / 第二幕·记忆对质 / 第三幕·热搜风暴）；**2.5s 自动过或点击跳过**（main.js watch 定时清除，跳过后定时器失效） |

### 3. 各视图背景真图化（v31.css §尾段，内容浮于其上）

| 视图 | 背景图 | 处理 |
|---|---|---|
| 场景地图 | `ui_map_bg.png` | 蓝图底图 cover；手绘 floor-svg 线稿弱化 opacity .32 作辅助层；**11 地点光点坐标沿用 data.js pos**（loc-node 不动）；地图顶 chips 等内容浮于其上 |
| 复盘/侦探档案 | `ui_report_bg.png` | 根容器背景 + 双层渐变压暗（.84/.9）保证可读性，圆角 14px |
| 心晴诊室 | `ui_clinic_bg.png` | 同上 |
| 圆桌投票 | `ui_vote_bg.png` | 同上 |
| 热搜面板 | `ui_hotfeed_bg.png` | 同上 |
| minis 入口（迷你游戏厅） | `ui_minis_lobby.png` | `.mini-lobby-grid` 背景 + 入口四卡半透明底 |

### 4. 存量修复

- report.js：`onMounted` 未从 Vue 解构即调用（`ReferenceError`）→ ReportView setup 抛错、侦探档案页整页空白；删除该空调用并注释标注（V4/G2 修复）。修复后 console 零报错。

### 5. 验收（Playwright Chromium · 本地静态服务 / → frontend/、/assets → content/assets）

- 全链状态机断言：cover(`step:act`) → enterBureau(`case_file`) → showtimeNext(`cut:{act:1}`+view:chat) → advance R2（地图可进）→ actSet:2（`cut:{act:2}` 自动插入）→ vote(`accuse`) → ending(`reveal`+view:ending)——**全链无断点**。
- 截图（tests/shots/g2_*.png，11 张）：01 封面 / 02 卷宗页 / 03 act_t1 转场 / 04 圆桌 / 05 蓝图地图 / 06 act_t2 转场 / 07 热搜 / 08 投票 / 09 诊室 / 10 侦探档案 / 11 揭晓复盘。
- 冒烟回归：`node frontend/tests/smoke_v31.js` → **63 PASS / 0 FAIL**（2026-09-12 复测更新）。此前记录的 57 PASS / 6 FAIL 已定性为**测试脚本 bug**（非素材缺失）：官方 kanshan 家族 6 图（kanshan_portrait/beijixiong/liubaba/liumama/qie/yanou）本就在 `content/assets/official/kanshan/` 齐全，是脚本第 252 行对绝对路径 `/assets/...` 做 `path.join(ROOT,'..',src)` 被当作盘根拼成 `D:\assets\...` 导致误报。已修复为 `toRepoPath()` 把 `/assets/` 归一化到 `content/assets/` 再核验落盘。模板编译与引擎链路始终零 FAIL。
- v31.css 共享冲突：G1 报告的本组段落覆盖事故已按契约「重读最新版→合并→复验」处理，双方段落（.rt-stage 系 + .st-* 系）共存且背景/转场截图复验生效。

### 6. 遗留与对接点

1. ~~**A/资产**：官方 IP 家族 6 图未入库~~ → **已澄清并解决（2026-09-12 复测）**：6 图（beijixiong/liubaba/liumama/qie/yanou/kanshan_portrait）实际已在 `content/assets/official/kanshan/` 齐全；此前的"未入库/6 FAIL"系冒烟脚本路径拼接 bug 误报，脚本已修复，侦探证证件照六选一素材完整可用。
2. **G3/F**：真实引擎接入时 `actSet`/`vote`/`ending` 事件形态不变，showtime 状态机自动跟随；如需服务端驱动卷宗/转场，按 `system` 事件扩展 `case_file`/`act_cut` payload 即可。
3. 8898 端口 G2 验证静态服务（/→frontend、/assets→content/assets）暂留供各组联调复用；8899 为 F 真实引擎服务（/api/health 与 /assets 正常，前端静态页未托管，前端验证请用 8898 或 file:// 不适用——绝对路径 /assets 需 http 服务）。
