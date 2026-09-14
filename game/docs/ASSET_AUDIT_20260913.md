# 美术资产全量审计报告（2026-09-13 02:53）

> 工具：`tools/check_assets.py`（只读零副作用，扫 frontend+server+engine 三方引用 × 磁盘 × HTTP 三方比对）
> 复跑命令：`cd game/tools && C:/Python314/python.exe check_assets.py`（需 8899 服务在线）
> 结论：**引用侧 58 项全绿（磁盘存在 + HTTP 200 + 非 0 字节）**；孤儿资产 10 项；缺口 4 类。

## 一、在用资产健康度（58 项 ✅）

| 类别 | 数量 | 明细 | 状态 |
|---|---|---|---|
| 角色立绘 | 9 | 8 嫌疑人 char_*.png + dm_kanshan_holo.png（chat/report/review/vote/hotfeed 五处复用） | ✅ 全部在用 |
| 场景图 | 11 | data.js 11 个地图点位 img 字段一一对应 | ✅ 全部在用 |
| 成就图 | 7 | ach_*.png（main.js ACH 表） | ✅ 全部在用 |
| UI 背景 | 10 | v31.css/chat_ref.css 各视图 bg + ui_case_file/ui_chip | ✅ 全部在用 |
| 通用件 | 5 | logo_badge（favicon+3 处）、card_back、act_t1/2/3（幕间转场动态模板） | ✅ 全部在用 |
| 官方 IP | 2 | kanshan.png（minis 小游戏雪碧图 + 分享卡）、kanshan_portrait.png（玩家侦探证 + chat） | ✅ 全部在用 |
| 视频 | 10 | opening / prologue / 6 场景视频（4 _new + archive/clinic 旧版仍在用）/ clue_001_banner_new（幕间 bg）/ clue_009_surveillance_new（clue_007 media） | ✅ 全部 200 |

## 二、孤儿资产（磁盘在、无人引用）10 项 → 处置建议

| # | 文件 | 大小 | 性质 | 建议 |
|---|---|---|---|---|
| 1 | `official/kanshan/favicon.png` | 458B | 损坏残根（index.html 实际用 logo_badge.png 作 favicon） | **可删** |
| 2 | `official/kanshan/kanshan_big.png` | 72KB | 官方 IP 大图，未接线 | **留**（提报/分享卡素材，赛道 IP 加分项） |
| 3 | `images/icon_fish.png` | 294KB | 生成后未接线（当前 UI 用 emoji 🐟） | **接线**：替换鱼干 emoji |
| 4 | `images/icon_rumor.png` | 179KB | 生成后未接线（同上） | **接线**：替换谣言 emoji |
| 5 | `images/ui_badge_wall.png` | 224KB | 生成后未接线 | **接线**：成就墙/徽章页 bg |
| 6 | `images/ui_dossier_bg.png` | 187KB | 生成后未接线 | **接线**：侦探证详情页 bg |
| 7 | `images/ui_hud_banner.png` | 192KB | 生成后未接线 | **接线或删**（HUD 横幅位） |
| 8 | `images/scene_corridor.png` | 237KB | 生成后未接线（走廊过场） | **接线或删** |
| 9 | `images/scene_director_office.png` | 187KB | 生成后未接线（局长室） | **接线或删** |
| 10 | `images/scene_hall.png` | 206KB | 仅 scenario.json 引擎元数据 fallback（前端 0 消费，`grep .image` 为空） | **留**（真后端模式底图兜底） |

## 三、待补充缺口（按价值排序）

| 优先 | 缺口 | 现状 | 补充方案（免费/纯代码路径） |
|---|---|---|---|
| P0 | **音频 = 0** | `audio/` 目录空，全项目 0 处音频引用，游戏完全无声 | BGM（菜单/地图/圆桌/结局）+ SFX（叮/点击/揭示/投票）；DM 语音可用本地 IndexTTS 2.5 |
| P1 | 场景视频 5/11 缺 | 前台/看山工位/茶水间/**监控室**/天台无视频 | p3 批次生成；监控室是删除事件核心场景，优先 |
| P2 | 线索视频 1/27 | 仅 clue_007 有 media（bag.js 已支持任意 clue 挂视频） | **零生成成本方案**：loc_server_new/loc_hotfeed_new/loc_locker_new 与 clue_013/014/015 同现场，直接复用挂 media；clue_001_banner_new 可挂 clue_001 |
| P3 | 引擎房间图错配 | scenario.json：档案室→scene_hall、空调机房→scene_server、快递柜→scene_reception、工位→scene_hall（前端未消费，真后端模式会露馅） | 改 4 行指向正确图（scene_archive/scene_hvac/scene_locker/scene_desk_kanshan） |

## 四、本轮已清理记录

- 旧不可用视频 4 个已删（clue_001_banner / clue_009_surveillance / loc_locker / loc_ac 的旧版，见 VIDEO_CLUES_PLAN.md §十.1）。
- 视频目录现存 10 个文件，**全部有引用、全部 200**，无冗余。

## 五、行动清单（待拍板）

- ~~1. P0 音频~~ → **用户拍板：暂缓**。
- ~~2. 孤儿接线 or 删~~ → ✅ 已执行（见 §六）。
- ~~3. P2 零成本线索视频复用接入~~ → ✅ 已执行（见 §六）。
- ~~4. P3 引擎图错配修复~~ → ✅ 已执行（见 §六）。
- ~~P1 场景视频 5/11 缺~~ → ✅ p3 批次已生成并接线（见 §六）。

## 六、执行记录（2026-09-13 02:58–03:20，用户指令「音频先等等，先生成其他的，全部生成」）

### 6.1 P1 场景视频补齐（p3 批次，`tools/video_batch_p3.json`，国际站 key）

5/5 生成成功，规格统一 12.25s / 1280×720 / h264 / 无音轨。抽帧审计（f_02 中段帧）：

| 文件 | 画面 | 文字残留 | 判定 |
|---|---|---|---|
| `loc_reception_new` | 制服值班员+弧形前台+仙人掌+访客簿，与场景图元素一一对应 | 墙面徽标环形装饰字母（不可读单词） | ✅ |
| `loc_desk_new` | 白手套+镊子+手电勘查便签，照片/放大镜/零食袋齐全 | 零食包装印刷（包装画） | ✅ |
| `loc_teahouse_new` | 双连帽身影对坐吃泡面（比预期多 1 人，反而契合「接头」暗线） | 泡面桶身包装字（不可读） | ✅ |
| `loc_monitor_new` | CRT 监视器墙+空转椅，**全程无时码/无 REC/无 OSD** | 无 | ✅✅ |
| `loc_roof_new` | 连帽人倚栏望霓虹天际线+满月，脚下散落空零食袋 | 零食袋包装字（不可读） | ✅✅ |

### 6.2 接线结果

- **场景视频 11/11 全覆盖**：`loc_reception/loc_desk/loc_teahouse/loc_monitor/loc_roof` 新增 video 字段。
- **线索 media 1/27 → 9/27**：clue_001(便签)/008(人影)/011(主人级指令)/015(鱼干袋)/017(值班矛盾)/020(补打卡)/024(话题创建)/029(亲自的快递)/007(监控删除·前批) 全部挂同现场视频；bag.js 影像层自带失败降级。
- **孤儿接线 5 项**：`icon_fish`→成就「鱼干线人」、`icon_rumor`→成就「反诈先锋」（ACH_IMG 替换 emoji）；`ui_badge_wall`→成就墙弹窗底图；`scene_corridor`→幕间电梯转场底图；`scene_director_office`→boss 揭面底图 + scenario.json 局长办公室房间图。
- **孤儿保留 5 项（文档化）**：`ui_hud_banner`（内嵌狐狸头像模板，与现有 HUD 双头像冲突）；`ui_dossier_bg`（内嵌陌生人像，与玩家官方 IP 头像 6 选 1 冲突）；`scene_hall`（大厅兜底）；`kanshan_big`（官方 IP 提报素材）；`favicon.png`（458B 损坏残根，待用户确认后删）。

### 6.3 P3 引擎房间图错配修复（6 处，比审计多发现 2 处）

`scenario.json` + `_gen/data_core.py` 双侧同步：desk_kanshan→scene_desk_kanshan、archive_room→scene_archive、hvac_room→scene_hvac、parcel_locker→scene_locker、study_room→scene_study_room、director_office→scene_director_office。**只动 image 字段，clue_pool 零触碰（叙事零副作用）**。

### 6.4 回归验证

- `check_scene_play.py`（真实浏览器）**9/9 场景视频** `readyState=4 · muted · loop · 进度推进` ✅
- `check_assets.py` 复跑：**引用 68 项全绿**（+10），mp4 15/15、png 53/53 全 200，缺失/HTTP 异常/0 字节均 0 ✅
- 孤儿 10 → 5（均为故意保留）

## 七、素材复用二轮（2026-09-13 11:00，用户指令「查询能用的素材，用到游戏里」）

### 7.1 kanshan_big.png 转正 + 修复 dm-walk 丢失 bug ⭐

- 盘点发现 `kanshan_big.png`（4700×1740）= `kanshan.png` 的 **@2x 同网格 30 帧官方雪碧图**，此前无引用。
- **顺带发现回归 bug**：`.dm-walk` 基础规则与 `@keyframes dm-walk-steps` 在历史重构中全部丢失（仅剩孤立尺寸规则），chat 对话流 / 幕间电梯 / 侦探证 ×2 / 复盘行走条 ×3 共 **6 处 DM 看山形象不可见**（STATUS.md:230 记载过同症状修复史，规则再次丢失且无人发现——因无守护脚本）。
- 修复：v31.css 补回基础规则（图源直接升级 kanshan_big @2x）+ keyframes 改用 `var(--dmw-end)` 位移终点，组件内联按 scale 下发（修掉旧实现非 1 缩放下位移越界的隐患）；ui.js 注释与几何注释同步修正。
- 新增守护：`tools/check_dmwalk_smoke.py`（图源 200 / 计算样式解析 / 动画位移三断言）。
- 验证：真实浏览器 asset=200 ✅ css_bg=解析到 kanshan_big ✅ anim 位移 0→-308px 推进 ✅；check_assets 复跑引用 **69 项全绿**（png 54），孤儿 5 → 4。

### 7.2 其余素材盘点结论

| 素材 | 定性 | 处置 |
|---|---|---|
| 根目录 `g1_chat_desktop/final/mobile/spotlight.png` ×4 | 游戏 UI 截图（昨晚 21:34-21:36 生成）= **提报/宣传材料** | 非游戏资产，原地保留 |
| 根目录 `content/assets/images/scene_corridor.png` | 场景图**早期散落副本**（游戏内副本已接线电梯转场） | 冗余，可删（待确认） |
| `official/kanshan/liubaba/liumama/yanou` 等 6 头像 | `fix_ip_avatars.py` 已把原雪碧图就地裁成 235×290 单帧头像，现役侦探证 6 选 1 | 在用，注意：**原始多姿势雪碧图已被覆盖，不可回滚** |
| `ui_hud_banner` / `ui_dossier_bg` | 内嵌人像的成品模板，与现有 HUD/玩家头像体系冲突 | 保留不接线（前轮结论不变） |
| `favicon.png` | 458B 损坏残根 | 可删（待确认） |
