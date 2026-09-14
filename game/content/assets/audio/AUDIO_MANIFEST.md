# 音频资产清单（AUDIO_MANIFEST）

> 游戏：《求真档案局·看山失踪夜》
> 生成日期：2026-09-13
> 目录：`game/content/assets/audio/`（平铺）
> 格式：WAV（浏览器全兼容）
> 总数：43 条 · P0=16 · P1=18 · P2=9
> 生成方式：T2A（text_to_audio_plus）25 条 · 程序合成（numpy）18 条
> 设计原则：音频作为独立一层，不写回 mp4；前端用 Web Audio / `<audio>` 播放

---

## 一、完整资产表

### P0 — 没有它演示仍像默片（16 条）

| 文件名 | 用途 | 绑定界面 | 时长 | 大小 | 生成方式 | 采样/声道 |
|---|---|---|---|---|---|---|
| `sfx_ding.wav` | **基础短叮，全局最高频复用** | 卷宗末句/幕转场/圆桌DM/头条开标/抽风/急诊/陈词 | 0.4s | 34.5KB | 合成 | 44.1k/mono |
| `bgm_menu_rain.wav` | 封面雨夜城市床垫 | 封面菜单（夜雨大厦） | 30s | 4.6MB | T2A | 40k/stereo |
| `sfx_ui_click.wav` | 按钮点击反馈 | 封面菜单/全局UI | 0.1s | 8.7KB | 合成 | 44.1k/mono |
| `bgm_opening.wav` | 序章 14s 配乐 | 序章 opening.mp4（独立层，不写回mp4） | 14s | 2.1MB | T2A | 40k/stereo |
| `sfx_page_flip.wav` | 翻纸声 | 案件卷宗/复盘/前情提要 | 1.7s | 146.5KB | T2A | 44.1k/mono |
| `vo_dm_case.wav` | DM 读案件卷宗开场四段 | 案件卷宗 | 24.4s | 3.7MB | T2A | 40k/stereo |
| `vo_dm_act.wav` | DM 幕转场播报 | 幕间转场 act1/2/3 | 4.5s | 703KB | T2A | 40k/stereo |
| `bgm_roundtable.wav` | 圆桌低频床垫 | 圆桌对话 | 30s | 4.6MB | T2A | 40k/stereo |
| `sfx_seat.wav` | 发言亮环座位音 | 圆桌对话（席位亮） | 0.9s | 75.8KB | T2A | 44.1k/mono |
| `sfx_card_hit.wav` | 搜证命中：翻卡+入袋 | 搜证命中 | 1.5s | 129.2KB | T2A | 44.1k/mono |
| `sfx_card_miss.wav` | 搜证落空空咔 | 搜证落空 | 0.25s | 21.6KB | 合成 | 44.1k/mono |
| `sfx_camera.wav` | 暗拍快门 | 搜证暗拍 | 0.15s | 13KB | 合成 | 44.1k/mono |
| `sfx_countdown.wav` | 60s 倒计时（后10s加速+终音加重） | 终局指认 60s 陈词 | 62s | 5.2MB | 合成 | 44.1k/mono |
| `sfx_hammer.wav` | 落锤 | 终局指认/头条开标 | 0.3s | 25.9KB | T2A | 44.1k/mono |
| `sfx_elevator.wav` | 电梯复合：关门rumble→楼层叮→门开 | 全屏演出·幕间电梯跨幕 | 3s | 258.4KB | T2A | 44.1k/mono |
| `sfx_glitch.wav` | 故障噪声（引擎侧可裁到1.6s） | 全屏演出·抽风横幅 banner_glitch | 2s | 172.3KB | T2A | 44.1k/mono |

### P1 — 进房间立刻有空间感 / 角色像活人（18 条）

| 文件名 | 用途 | 绑定界面 | 时长 | 大小 | 生成方式 | 采样/声道 |
|---|---|---|---|---|---|---|
| `sfx_copy.wav` | 复制链接咔哒 | 选形象/房间码 | 0.15s | 13KB | 合成 | 44.1k/mono |
| `bgm_map.wav` | 总图弱雨声 | 11 点场景地图（总图） | 30s | 4.6MB | T2A | 40k/stereo |
| `bgm_room_机房.wav` | 服务器机房氛围 | 地图·机房 | 20s | 3.1MB | T2A | 40k/stereo |
| `bgm_room_天台.wav` | 天台夜风氛围 | 地图·天台 | 20s | 3.1MB | T2A | 40k/stereo |
| `bgm_room_茶水间.wav` | 茶水间氛围 | 地图·茶水间 | 20s | 3.1MB | T2A | 40k/stereo |
| `sfx_auction.wav` | 竞标木槌+倒计时 | 热搜/押注/头条开标 | 4.3s | 672KB | T2A | 40k/stereo |
| `sfx_heat.wav` | 买热搜上冲 | 热搜/买热搜 | 7s | 1.1MB | T2A | 40k/stereo |
| `sfx_buzz.wav` | 急诊失败蜂鸣 | 心晴诊室/急诊红灯 | 0.5s | 43.1KB | 合成 | 44.1k/mono |
| `sfx_green.wav` | 抢救转绿叮 | 急诊抢救成功 | 0.6s | 51.7KB | 合成 | 44.1k/mono |
| `sfx_heal.wav` | 开导成功软和弦 | 心晴诊室开导成功 | 2s | 312.5KB | T2A | 40k/stereo |
| `sfx_tick.wav` | 反诈 30s 倒计时滴答 | 全屏演出·反诈剧场 | 31s | 2.6MB | 合成 | 44.1k/mono |
| `sfx_achievement.wav` | 成就解锁荣誉音 | 全屏演出·成就横幅 | 2s | 312.5KB | T2A | 40k/stereo |
| `vo_boss_1.wav` | Boss 现身第一拍 | 复盘/Boss揭示 | 4.5s | 703KB | T2A | 40k/stereo |
| `vo_boss_2.wav` | Boss 自报身份 | 复盘/Boss揭示 | 4.4s | 688KB | T2A | 40k/stereo |
| `vo_boss_3.wav` | Boss 动机揭示 | 复盘/Boss揭示 | 6.5s | 1.0MB | T2A | 40k/stereo |
| `vo_boss_4.wav` | Boss 轻松收尾 | 复盘/Boss揭示 | 6.1s | 950KB | T2A | 40k/stereo |
| `vo_fish_1.wav` | 看山Bot·鱼干归位逻辑 | 鱼干彩蛋·集齐即播 | 9s | 1.4MB | T2A | 40k/stereo |
| `vo_fish_2.wav` | 看山Bot·藏位分析 | 鱼干彩蛋·第2段 | 14s | 2.1MB | T2A | 40k/stereo |

### P1 续 — 鱼干语音（续）

| 文件名 | 用途 | 绑定界面 | 时长 | 大小 | 生成方式 | 采样/声道 |
|---|---|---|---|---|---|---|
| `vo_fish_3.wav` | 看山Bot·诚实/感受协议 | 鱼干彩蛋·第3段 | 10.7s | 1.6MB | T2A | 40k/stereo |
| `vo_fish_4.wav` | 看山Bot·隐藏备注（DM 97.2%匹配） | 鱼干彩蛋·第4段（转折钩子） | 25.4s | 3.9MB | T2A | 40k/stereo |
| `vo_fish_5.wav` | 看山Bot·主人回归（终极层加播） | 鱼干彩蛋·看山现身追加 | 14.3s | 2.2MB | T2A | 40k/stereo |

### P2 — 地点氛围轨补全（9 条）

| 文件名 | 用途 | 绑定界面 | 时长 | 大小 | 生成方式 | 采样/声道 |
|---|---|---|---|---|---|---|
| `bgm_room_监控室.wav` | 监控室 CRT 氛围 | 地图·监控室 | 20s | 3.1MB | T2A | 40k/stereo |
| `bgm_room_档案室.wav` | 档案室纸张氛围 | 地图·档案室 | 20s | 3.1MB | T2A | 40k/stereo |
| `bgm_room_前台.wav` | 前台大厅氛围 | 地图·前台 | 20s | 3.1MB | T2A | 40k/stereo |
| `bgm_room_看山工位.wav` | 看山工位氛围 | 地图·看山工位 | 20s | 3.1MB | T2A | 40k/stereo |
| `bgm_room_空调机房.wav` | 空调机房轰鸣 | 地图·空调机房 | 20s | 3.1MB | T2A | 40k/stereo |
| `bgm_room_快递柜.wav` | 快递柜区域氛围 | 地图·快递柜 | 20s | 3.1MB | T2A | 40k/stereo |

> P2 说明：剩余细碎 SFX（前情提要翻页复用 `sfx_page_flip`、开始本章回叮复用 `sfx_ding`、反诈三幕叮打断复用 `sfx_ding`）均通过复用现有资产覆盖，无需额外生成。

---

## 二、前端接线建议

### 2.1 全局复用映射

| 触发场景 | 播放资产 | 说明 |
|---|---|---|
| DM 任何"叮——"开头台词 | `sfx_ding.wav` | 全局最高频复用，<0.5s 不刺耳 |
| 卷宗末句"叮" | `sfx_ding.wav` | |
| 幕转场"叮——第N幕" | `sfx_ding.wav` + `vo_dm_act.wav` | 叮先响，再接语音 |
| 圆桌 DM 每条发言 | `sfx_ding.wav` | |
| 头条开标"叮——" | `sfx_ding.wav` + `sfx_hammer.wav` | |
| 抽风横幅重写 | `sfx_glitch.wav` → `sfx_ding.wav` | 故障1.6s后叮一声重写 |
| 急诊抢救转绿 | `sfx_green.wav` | |
| 终局指认开场 | `sfx_ding.wav` → `sfx_countdown.wav` | |
| 前情提要翻页 | `sfx_page_flip.wav` | |
| 前情提要"开始本章" | `sfx_ding.wav` | |
| 反诈剧场三幕叮打断 | `sfx_ding.wav` ×3 | |
| 成就横幅 | `sfx_achievement.wav` | 1条复用 |

### 2.2 需要循环播放的资产（loop=true）

| 资产 | 循环场景 | 音量建议 |
|---|---|---|
| `bgm_menu_rain.wav` | 封面菜单 → 选形象/房间码（音量略降） | 0.5 |
| `bgm_opening.wav` | 序章 opening 期间（不写回mp4，独立`<audio loop>`） | 0.6 |
| `bgm_roundtable.wav` | 圆桌对话全程 | 0.35 |
| `bgm_map.wav` | 11点地图总图 | 0.4 |
| `bgm_room_*.wav`（10条） | 进入对应房间时切换，crossfade 1s | 0.45 |

### 2.3 一次性触发的资产（loop=false）

- 所有 `sfx_*.wav`：事件触发即播
- `vo_dm_case.wav` / `vo_dm_act.wav`：对应界面进入时播一次
- `vo_boss_1..4.wav`：按顺序逐句播（打字机出字同步）
- `vo_fish_1..4.wav`：集齐3袋鱼干后按顺序播；`vo_fish_5.wav` 仅在终极层现身时追加
- `sfx_countdown.wav`：终局指认60s开始时播，与环形计时同步
- `sfx_tick.wav`：反诈剧场30s倒计时开始时播

### 2.4 音频层架构建议

```
AudioLayer (独立于视频)
├── BGM_Channel     ← bgm_*.wav（循环，crossfade切换）
├── Ambient_Channel ← bgm_room_*.wav（房间氛围，循环）
├── SFX_Channel     ← sfx_*.wav（事件触发，可叠加）
└── VO_Channel      ← vo_*.wav（语音，播时BGM自动ducking -6dB）
```

- 场景视频（mp4）保持 muted，音频全部由本层提供
- 首次用户交互后解锁 AudioContext（应对浏览器 autoplay 策略）
- VO 播放时 BGM 自动降音量（ducking），VO 结束后恢复

---

## 三、VO 文案索引

### DM 系统音（vo_dm_case / vo_dm_act）
- 人设：「叮——系统提示音」，沉稳无机质略带幽默
- 来源：`content/scenarios/kanshan/scripts/dm_system_voice.md` + `act1_chumen.md`

### Boss 揭示四拍（vo_boss_1..4）
- 人设：刘看山真身，从系统音转为本人，沉稳中带轻松幽默
- 来源：`content/scenarios/kanshan/scripts/act3_hupi_demao.md` §2.3 终极层
- 文案：
  1. "叮——。学了三幕的系统音，是本人了吧。"
  2. "我叫刘看山。你们破的局，正是我设的局。"
  3. "档案局混进了记忆编辑者，打草会惊蛇，所以我把自己弄丢——钓你们上岸。"
  4. "顺便一提，鱼干是我自己买的。谁动了我的鱼干，你们自己反思。"

### 鱼干隐藏语音（vo_fish_1..5）
- 人设：看山Bot，诚实理性底色+0.3度温柔，AI语音质感
- 来源：`content/scenarios/kanshan/scripts/collectibles_p3.md` §三
- 播放规则：集齐3袋鱼干后 vo_fish_1→4 按序逐句播；vo_fish_5 仅在终极层现身时追加
- 硬规则：切片逐句播，不合并

---

## 四、技术备注

1. **WAV 头修复**：T2A 上游返回的流式 WAV 头中 RIFF/data chunk size 曾为占位极大值，已全部按实际文件大小重写，`wave` 模块/ffmpeg/浏览器均可正确识别时长。
2. **采样率不统一**：T2A 产物为 40kHz/stereo，程序合成为 44.1kHz/mono。浏览器 `<audio>` 和 Web Audio API 均自动重采样，无需前端额外处理；如需统一可后续用 ffmpeg 批量转换。
3. **sfx_glitch 时长**：实际生成 2.0s，设计要求 1.6s 后硬切。前端可在 1.6s 处 `stop()` 或用 AudioBufferSourceNode 调度截断。
4. **sfx_countdown 结构**：前50s每秒1声滴答，51-60s每秒2声，60s处一声加重（低频+高频叠加），总长62s含尾部余量。
5. **未覆盖范围**：8 个 NPC 全量配音不在本批范围（用户明确要求先做叮和床垫）；地点氛围轨已覆盖 10 个主要房间，其余小众地点可复用 `bgm_map.wav` 或后续补充。
