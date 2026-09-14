# 线索视频化筛选结论 · Agnes Video 替代方案

> 目标引擎：`agnes-video-2.5-flash`（`game/tools/asset_gen.py :: gen_video`，支持 text / keyframe 双模式）
> 清单文件：`game/tools/video_manifest_phase1.json`（19 条，已通过字段校验）
> 生成日期：2026-09-13

---

## 〇、执行结果（2026-09-13 实跑落地）

**首批 6 条全部生成成功，已完成剥音轨、全量 ffprobe 校验与 HTTP 冒烟，前端地点层已接入。**

| 文件 | 时长 | 规格 | 最终体积 | HTTP |
|---|---|---|---|---|
| `loc_locker.mp4` | 4.46s | h264 1280×720 24fps | 1159 KB | 200 + 206 |
| `loc_archive.mp4` | 4.46s | h264 1280×720 24fps | 1710 KB | 200 + 206 |
| `loc_ac.mp4` | 4.46s | h264 1280×720 24fps | 2127 KB | 200 + 206 |
| `loc_clinic.mp4` | 4.46s | h264 1280×720 24fps | 823 KB | 200 + 206 |
| `clue_009_surveillance.mp4` | 4.46s | h264 1280×720 24fps | 1502 KB | 200 + 206 |
| `clue_001_banner.mp4` | 6.58s | h264 1280×720 24fps | 2617 KB | 200 + 206 |

### 过程中修掉的一个真 Bug（历史 P0）

**现象**：任何 video 任务必在 ~24s 时被 `HTTP 429` 打死，`prologue.mp4` 当初就是这样失败的——**不是接口不通，是轮询被限流**。

**根因**：`asset_gen.py` 的 `_post()` 有 429 指数退避，`_get()` 完全没有。轮询每 2s 打同一端点，免费档极易 429，一崩就丢掉整单。

**修复**（均局部、不影响 image 路径）：
1. `_get()` 补 429/5xx 指数退避 + 熔断（5/10/20/40/80/160s，上限 6 次），失败改抛 RuntimeError 而非裸 HTTPError
2. 抽出 `poll_video()` 并新增 **`--resume <video_id>`**：已提交任务不重复提交即可续拉下載，**不重复计费**（本次正是靠它把崩掉的 `task_cYtKBCJRfmjqZtzvEuJiCG6cJ6bjv0qy` 救回）
3. 提交后强制回显 `video_id` 与 `--resume` 命令；异常信息附带 video_id
4. 轮询间隔 2s → 6s（清单可用 `poll` 覆盖，批量时建议 `poll: 10`）
5. `run_manifest` 对 video 补幂等跳过（原先只跳过 image，重跑会覆盖已付费产出）

**验证**：修复后连续 5 条批量，**8 分 52 秒零失败**（修复前单条 24s 必崩）。

### 产物处理

Agnes 返回的 mp4 **自带 AAC 音轨**。氛围 loop 视频不需要声音，且带音轨会被浏览器 autoplay 策略拦截 → 已用 `ffmpeg -c:v copy -an -movflags +faststart` 剥离，每条瘦身约 73 KB，同时加 faststart 让 `<video>` 边下边播。

### 前端已落地的改动（均带降级兜底）

| 文件 | 改动 |
|---|---|
| `frontend/js/data.js` | 新增 `const VID = '/assets/videos/'`；4 个地点加 `video` 字段 |
| `frontend/js/views/map.js` | `.scene-head` 增加 `<video v-if="openLoc.video" autoplay loop muted playsinline>` + `@error` 降级回 `<img>`，再兜底 `<svg-scene>` |
| `frontend/css/style.css` | `.scene-head video` 并入既有 img 尺寸规则（150px 高、object-fit: cover） |

三级降级链：**video → img → svg-scene**，任一环节失败自动回落，无白屏风险。

### 剩余 13 条

`reception / desk / teahouse / monitor / server / hotfeed / roof` 7 条场景 + `clue_005 / 006 / 011 / 025 / 026` + `B 层候补 4 条`，见 `video_manifest_phase1.json`。沿用本次配置即可（`poll: 10`）。

> ⚠️ **踩过的坑**：`--out` 的基准目录是 `GAME_ROOT`（即 `game/`），**不是 cwd**。用 `--out content/assets/videos/x.mp4`，别写成 `../content/...`（会落到项目根的 `content/`，那里也有同名目录，极易混淆且服务端取不到）。

---

## 八、资产自检结果（2026-09-13，用户发起）

新增两个可复跑只读工具：

| 工具 | 作用 |
|---|---|
| `tools/check_assets.py` | 引用提取（字面量/变量拼接/f-string 模板）→ 磁盘 → HTTP 三方比对，输出缺失/孤儿清单 |
| `tools/check_video_smoke.py` | 真机 Chrome 渲染冒烟：走通主菜单→地图→点击地点，检查 `<video>` 的 readyState/videoWidth/paused 等**实际播放状态** |

### 修掉的 3 个 bug

| # | 级别 | 问题 | 修复 |
|---|---|---|---|
| 1 | P1 | 4 处图片引用错：`scene_archive/locker/hvac/study_room` 四张专用场景图早已生成，但 data.js 把 4 个地点全指向 `scene_desk_kanshan.png` 占位图（我上轮误判为"资产债"，实为**引用错**） | `data.js` 改为对应专用图，同时修好视频 poster |
| 2 | **P0 阻断** | 序章视频 `prologue.mp4` 与 `opening.mp4` **双双缺失**，玩家点「单人模式」永久卡黑屏（`@ended` 永不触发 → `startGame()` 永不执行）。实测 `readyState=0 / error.code=4 / MEDIA_ELEMENT_ERROR / paused=true` | 补生成 prologue.mp4（8s）+ opening.mp4（5s，双源冗余）；`main.js` 加 `@error="Store.introFallback()"`（prologue→opening→直接进游戏） |
| 3 | P1 | `server/main.py` 只挂了 `/assets`、`/js`、`/css`，**漏挂 `/minis`**；`index.html` 用相对路径 `minis/*.js` 加载 → 小游戏层 6 个文件全 404（4 件套 + 壳 + main-minis） | 补 `app.mount("/minis", ...)` |

### 最终状态

- ✅ **54 个被引用资产：磁盘存在 + HTTP 200，零缺失、零 0 字节**
- ✅ 4 个地点视频真机验证：`readyState=4 / 1280x720 / muted / loop / paused=false / currentTime 正常推进`
- ✅ **无任何 404/5xx**
- ❌ **音频：完全为零**（见 §四）

### 遗留孤儿资产（12 个，非缺陷）

`scene_hall / corridor / director_office`、`ui_badge_wall / dossier_bg / hud_banner`、`icon_fish / icon_rumor`（当前用 emoji 🐟 代替）、`official/kanshan/*`（`favicon.png` 为 0 字节损坏文件，未引用）、`clue_001_banner.mp4` / `clue_009_surveillance.mp4`（B 层线索视频，待接入 `bag.js`）。

## 九、音频缺口

`content/assets/audio/` 仅有 118 字节的 README（标注「氛围音（雨夜/机房/服务器风扇）」「DM 音效（钟声/阶段切换提示）」为**可选**）；前端**零音频代码**（无 `Audio` / `playSound` / `sfx` 任何引用）。**游戏当前完全无声。**

建议优先级：① 搜证画面已动态化，配台氛围音层级（按地点分轨）ROI 最高；② DM 阶段切换提示音次之。可用本地 IndexTTS 2.5 生成语音/音效（零付费），接入方式同 video：`<audio loop>` + 地点字段。

---

## 一、结论先行

**结论：32 条线索里只有 8 条值得用 Agnes Video 生成，其余 24 条保持静态图。** 但真正的增量不在于给线索加视频，而在于把承载线索的**地点场景层**整体视频化——那是 11 条、零架构改动、收益最大的部分。

| 分层 | 数量 | 是否需要改代码 | 判断 |
|---|---|---|---|
| **A 层：地点氛围视频**（推荐先做） | 11 条 | 否，改 `data.js` 一个字段名即可 | ✅ 强烈建议 |
| **B 层：线索证据视频** | 8 条（S 级筛选后） | 是，需给 `clues` 加 `video` 字段 + 弹层挂载 | ✅ 建议做 |
| **C 层：文字型线索** | 14 条 | — | ❌ 禁止（见 §三硬约束） |
| **D 层：对话/流程型** | 10 条 | — | ❌ 无意义（本身已是动态 UI） |

---

## 二、架构现状（决定方案可行性的关键事实）

1. **线索对象本身没有 media 字段。**
   `frontend/js/data.js` 的 `clues[]` 只有 `id / name / tier / location / tags / fact / flavor / linked / unlock`，**没有任何图像或视频字段**；权威层 `content/scenarios/kanshan/clues/*.json` 同样没有。
   → 严格意义上"线索用视频代替"当前无法直接替换，必须先加字段。

2. **真正挂图的是地点，不是线索。**
   `frontend/js/data.js:15` 定义了 `const IMG = '/assets/images/'`，地点 `loc_*.img` 指向 `scene_*.png`；渲染点在
   `frontend/js/views/map.js:100` → `<img v-if="openLoc.img" :src="openLoc.img" :alt="openLoc.name">`，并有 `<svg-scene v-else>` 兜底。
   → 这是**唯一零成本视频挂载点**。

3. **发现 P0 资产债：4 个地点在复用同一张占位图。**
   `loc_locker`（快递柜）、`loc_archive`（档案室）、`loc_ac`（空调机房）、`loc_clinic`（心晴自习室）目前**全部**指向 `scene_desk_kanshan.png`（看山工位图）。
   → 视频化正好一并还清这笔债，这 4 条优先级最高。

4. **已有视频管线但产物缺失。**
   `asset_manifest.json` 末尾有一条 `prologue.mp4`（8s）任务，但 `content/assets/videos/` 下只有 `opening.mp4`——说明那次 video 生成没跑通或被跳过。`main.js:170` 也做了 prologue→opening 的兜底。
   → **开跑前建议先单独验证一次 gen_video，确认接口通再批量。**（`run_manifest` 对 video 无幂等跳过，重跑会覆盖。）

---

## 三、硬约束（决定 C 层为什么禁用）

`asset_gen.py:26` 的 `STYLE_PREFIX` 明确写死 **"画面中不出现文字"**。这不是建议，是 AI 生图的物理限制——模型生成的文字会糊、乱码、串符。

因此**下述线索的信息本体就是文字，一旦做成视频必然丢失或出错证据内容**：

| 线索 | 名称 | 为什么不能视频化 |
|---|---|---|
| clue_004 | 季度经费盘点表 | 核心是「账实相符的两个数字列」 |
| clue_008 | 借阅登记 | 核心是书名与借阅次数清单 |
| clue_012 | 水军矩阵账号清单 | 核心是「47 个马甲号 + 矩阵_K 监制」落款 |
| clue_017~021 | 彩蛋碎片一~五 | 《修仙世界日报》《监天司通缉令》等，全是设定文本和判词 |
| clue_022 | 匿名快递单（伪造） | 收件人与内件名必须可读 |
| clue_023 | 看山Bot 自爆截图 | 截图式证据，破绽在「署名工整」 |
| clue_024 | 经费亏空爆料长图 | 破绽在「行列宽度不符模板」 |
| clue_032 | 复盘页署名列表 | 核心是最后一行小字 |

> **退路**：这 8 条若一定要动态化，只能拍「载体在动」而不拍内容——比如下图纸张被风翻动、屏幕上有光在扫。**但文字仍必须由 UI 层渲染，视频只做氛围。** 收益低，性价比不足，不推荐。

---

## 四、B 层筛选：8 条 S 级线索证据视频

筛选标准：**视频能表达、静态图表达不了的信息**。命中「时间流逝 / 机械运动 / 屏幕闪烁 / 天气光影 / 人物或物体动作」任一即入选。

| # | 线索 | 名称 | 动态增益点 | 备注 |
|---|---|---|---|---|
| 1 | clue_001 | 全息横幅【不出真相，不出此门】 | 光带由暗到亮启动 + 卷帘门落下 + 警示灯转红 | **招牌镜头**，建议提到 8s |
| 2 | clue_009 | 被删除的监控时段 | 时间码跳到 21:07 卡顿 → 雪花抹去 8 分钟 | 悬疑感最强，必做 |
| 3 | clue_005 | 热搜热度曲线 | 阶梯状一格一格机械爬升 | 「有人按秒表发帖」只能靠动态表现 |
| 4 | clue_010 | 机房风扇负载曲线 | 风扇狂转 + 负载尖峰 + 绿转红高频闪烁 | 机械运动天然适合 |
| 5 | clue_006 | 茶水间两包泡面 | 热气升腾消散 | 「还温着」只有视频能成立 |
| 6 | clue_026 | 机房『20:45 人影』抓拍（伪造） | 马赛克噪点 + 低帧率跳帧 | 视频的劣质质感天然服务「这是假的」 |
| 7 | clue_025 | 路人甲值班打卡照（伪造） | 玻璃上的雨痕与雨声图景 | 破绽是「两点雨一模一样」，可逐帧比对 |
| 8 | clue_011 | 深夜快递与冰袋 | 冷雾外溢 + 未取件红灯闪烁 | 荒诞感来自「无人签收」的冷寂 |

**A 级候补（时间宽裕再补）**：clue_003 电子锁日志滚动、clue_013 Bot 日志滚动+涂黑、clue_027 天台纸条被风吹、clue_007 抽屉拉开。

**明确排除的 D 层**：clue_028（DM 口误）、clue_031（唤醒词对话）、clue_029/030（纯权限逻辑推演）——这些本质是「对话/推理」，做成Loop视频反而稀释张力。

---

## 五、执行方式

```bash
cd game/tools
# 1) 先单独验证一次，确认接口通（这条会真的调 API）
python asset_gen.py --video "测试：深夜档案局走廊，黑白监控画面，时间码跳动" --out ../content/assets/videos/_probe.mp4 --seconds 4

# 2) 通过后批量跑齐 19 条（含 429 指数退避，预计耗时较长）
python asset_gen.py --manifest video_manifest_phase1.json
```

清单字段已对齐 `run_manifest()` 的读取契约：`type / out / prompt / seconds / size / aspect_ratio`；额外的 `_layer / _note` 为人工标注，脚本忽略。

---

## 六、前端接入改动点（生成完成后）

### A 层（改 1 个字段，零风险）

`frontend/js/data.js:19-29`，把 `img:` 改为视频路径即可。由于 CSS 类与 `<img>` 挂载点是绑定在 `openLoc.img` 上的，**建议保留原 png 作为 poster 兜底**：

```js
{ id: 'loc_server', name: '服务器机房', img: IMG + 'scene_server.png',
  video: '/assets/videos/loc_server.mp4', ... }
```

再改 `frontend/js/views/map.js:100`：

```html
<video v-if="openLoc.video" :src="openLoc.video" :poster="openLoc.img"
       autoplay loop muted playsinline></video>
<img v-else-if="openLoc.img" :src="openLoc.img" :alt="openLoc.name">
<svg-scene v-else :loc="openLoc"></svg-scene>
```

> 必须带 `muted`——否则浏览器 autoplay 策略会拦截；`loop` 是氛围视频成立的前提。

### B 层（需加字段 + 挂载）

`frontend/js/data.js` 的 `clues[]` 增加 `video:` 字段；`frontend/js/views/bag.js:128` 的 `.clue-detail` 内、第一个 `cd-row` 之前插入：

```html
<video v-if="detail.video" :src="detail.video" class="cd-video"
       autoplay loop muted playsinline></video>
```

---

## 七、成本与风险

| 项 | 说明 |
|---|---|
| 单条规格 | 4s / 720P / 16:9（可用 keyframe 模式以现有 `scene_*.png` 作首帧，风格一致性更好） |
| 总条数 | 19 条，约 76 秒素材 |
| 速率限制 | `asset_gen.py:_post` 已内置 429 指数退避（30s/60s/120s），免费档批量需耐心 |
| 幂等性 | **video 条目没有 exists 跳过**，`run_manifest` 重跑会覆盖已有 mp4 |
| 建议顺序 | 先跑 4 个资产缺口（locker / archive / ac / clinic）+ clue_009 + clue_001，共 6 条验证效果，再补其余 13 条 |

---

## 十、p2 生成记录（国际站 · 12 秒 · 带人物 · 无文字约束）

**2026-09-13 02:00–02:25**，改用国际站（`https://apihub.agnes-ai.com/v1`）生成 6 条，全部 `seconds=12`（Agnes Video 2.5 Flash 上限 4–12s）。

### 生成清单

| 文件 | 谁 + 在哪 + 干什么 | 规格 | 大小 |
|---|---|---|---|
| `clue_001_banner_new.mp4` | 盐值君（深蓝马甲+工牌）在门内，冷蓝全息光幕降下、警示灯转红 | 12.25s / 1280×720 / 24fps / 0 音轨 | 5.5 MB |
| `loc_locker_new.mp4` | 路人甲（灰连帽衫）在快递柜前触屏代签 | 12.25s / 1280×720 / 24fps / 0 音轨 | 2.7 MB |
| `loc_hotfeed_new.mp4` | 流量酱（橙卫衣+耳机）背对镜头在工位连续敲击 | 12.25s / 1280×720 / 24fps / 0 音轨 | 5.4 MB |
| `loc_server_new.mp4` | 看山Bot（白色圆机器人）手悬停在红色物理按钮上 | 12.25s / 1280×720 / 24fps / 0 音轨 | 5.3 MB |
| `loc_ac_new.mp4` | 盐值君在空调机房终端前犹豫、手收回 | 12.25s / 1280×720 / 24fps / 0 音轨 | 3.9 MB |
| `clue_009_surveillance_new.mp4` | 深色连帽人背影在监控室，一块屏幕整块变黑 | 12.25s / 1280×720 / 24fps / 0 音轨 | 2.9 MB |

- 命令：`AGNES_BASE_URL=https://apihub.agnes-ai.com/v1 AGNES_API_KEY=... python asset_gen.py --manifest video_batch_p2.json`
- **国际站正确域名 `apihub.agnes-ai.com`**（`api.agnes-ai.com` 的 `/videos` 返回 404）；`asset_gen.py` 已支持环境变量覆盖，明文 `.env` 不动。
- **本次修掉的 bug**：`_strip_audio()` 调用早于定义 + 缺 `import subprocess` → 6 条任务下载成功后全部在剥轨环节 `[FAIL]`（文件已落盘但带音轨）。已补函数定义与 import，并对 6 个文件就地 `-c:v copy -an -movflags +faststart` 剥轨，复验 `audio_streams=0`。

### 接线 + 真实浏览器播放验证

| 地点 | 引用 | readyState | 分辨率 | muted/loop | 状态 |
|---|---|---|---|---|---|
| 快递柜 | `loc_locker_new.mp4` | 4 | 1280×720 | ✅ / ✅ | ✅ 播放中 |
| 空调机房 | `loc_ac_new.mp4` | 4 | 1280×720 | ✅ / ✅ | ✅ 播放中 |
| 服务器机房 | `loc_server_new.mp4` | 4 | 1280×720 | ✅ / ✅ | ✅ 播放中 |
| 热搜后台 | `loc_hotfeed_new.mp4` | 4 | 1280×720 | ✅ / ✅ | ✅ 播放中 |

- 工具：`tools/check_scene_play.py`（`get_by_text` 自动等待 + JS 直点 `button.loc-node`，绕过 floorplan SVG 遮挡）。6 条 URL 全 `200 video/mp4`。
- `data.js` 改动：`loc_locker`/`loc_ac` 替换 video 字段；`loc_server`/`loc_hotfeed` 新增 video 字段。
- ~~旧的 `loc_locker.mp4` / `loc_ac.mp4` 已无人引用（保留作备份）~~ → 2026-09-13 修复批次中已删除（见 §十.1）。

### 逐帧抽检：文字残留（负向约束实际效果）

| 文件 | 人物 | 文字残留 | 判定 |
|---|---|---|---|
| `clue_001_banner_new` | ✅ 盐值君 | 无 —— 旧版幻觉汉字「北庭析国」已消失 | ✅ 可用（替换旧版） |
| `loc_hotfeed_new` | ✅ 流量酱 | 无（屏幕纯抽象波形） | ✅ 可用 |
| `loc_server_new` | ✅ 看山Bot | 仅设备小铭牌 | ✅ 可用 |
| `loc_locker_new` | ✅ 路人甲 | ⚠️ 柜体生成西语铭牌「Servicios Postales」 | ⚠️ 小字，可接受 / 可重生成 |
| `loc_ac_new` | ✅ 盐值君 | ⚠️ 终端屏似有 UI 文本；**画风为动画风**（其余 5 条写实） | ⚠️ 画风不一致，建议重生成 |
| `clue_009_surveillance_new` | ✅ 连帽人 | ❌ `REC 15 M` + 时间码 `00/02/26-01:1S`（与游戏 21:07–21:15 冲突） | ❌ 时间码须由 UI 覆盖渲染 |

**结构性结论（复证）**：负向约束能消掉**主体区域的幻觉汉字**（clue_001 已修复），但对**设备铭牌 / CCTV 时间码 / 屏幕 UI** 三类"模型强关联场景"无效；CCTV 类必带时间码且不可控。→ 沿用审计结论：证据层的精确文字必须由 UI 渲染，AI 视频只做氛围。

### 待办

- ~~`clue_001_banner_new` / `clue_009_surveillance_new` 尚未接入~~ → 已接入（见 §十.1：`main.js` 幕间转场 + `data.js` clue_007 media，展示位本就存在，仅指向旧文件）。
- ~~`loc_ac_new` 画风不一致，建议重生成~~ → 已重生成并审计通过（见 §十.1）。

### §十.1 修复批次：重生成 3 条 + 删除全部不可用版（2026-09-13 02:33–02:55）

用户指令「重新生成，删掉用不了的」。修复 manifest：`tools/video_batch_p2_fix.json`（`overwrite: true`，就地覆盖），国际站 key 走环境变量。

**重生成结果（3/3 成功，规格均 12.25s / 1280×720 / h264 / 无音轨）**：

| 文件 | 修复目标 | 抽帧审计（f_01/f_03/f_06） | 判定 |
|---|---|---|---|
| `loc_ac_new` | 消除动画风 | 真人实拍电影感全程一致；终端屏仅抽象光条与绿色进度块；制服徽标为不可读小字 | ✅ 通过 |
| `loc_locker_new` | 消除西语铭牌 | 全程无「Servicios Postales」；柜面仅真实感小贴纸道具（不可读）；红色未取件灯 ✅ | ✅ 通过 |
| `clue_009_surveillance_new` | 消除错误时码 | **无可读日期/时间码**（旧版致命缺陷已消除）；残留 `REC 03/04/07` 计数 + 取景框角标 + 电池图标 | ✅ 通过（REC 层判定为监控证据题材自洽滤镜；各显示器角标文字均不可读，与 21:07–21:15 无冲突） |

**接线修正（展示位本就存在，此前仅指向旧文件）**：

| 引用点 | 旧 | 新 |
|---|---|---|
| `main.js` 幕间转场（act 1 背景） | `clue_001_banner.mp4`（含幻觉汉字） | `clue_001_banner_new.mp4` |
| `data.js:59` clue_007 `media`（证据袋影像层，`bag.js` 渲染 + 失败降级） | `clue_009_surveillance.mp4`（错误时码） | `clue_009_surveillance_new.mp4` |

**删除清单（旧不可用版，删除前已备份至 `data/_trash_p2/`，审计通过后连同备份一并清除）**：
`clue_001_banner.mp4`、`clue_009_surveillance.mp4`、`loc_locker.mp4`、`loc_ac.mp4` —— 4 个旧文件全删，`grep` 复核前端与工具脚本**零残留引用**。

**回归验证**：
- `tools/check_scene_play.py`（真实浏览器）：快递柜 / 空调机房 / 服务器机房 / 热搜后台 4 条 `readyState=4 · 1280×720 · muted · loop · 进度推进` ✅（含重生成 2 条）。
- 2 条 B 层接线 URL 均 `200 video/mp4` ✅。

**遗留结论修正**：CCTV OSD（REC/取景框）经两轮负向约束仍无法根除——「监控 + CRT + 低清颗粒」词组必然触发摄像机录制层；但对本条证据题材反而自洽，故采纳保留。若后续要求零 OSD，需改用「普通深夜办公室多屏工位」类去监控化提示词再生成。
