# 剧本杀一键工作台 · 认约稿（P0 冻结）

> 窗口：A 总控广播 · 2026-09-13
> 目标：一句话 → 世界圣经 → 细节圣经 → 环节剧本 → 编译落盘 → 闸门 → 开一局
> 演示档只做 **快本 demo**（4 人 / 6 地 / 12 线索 / 两幕+指认）。标准本 / 全量本字段预留，P0 不实现。

本文是并发开工的唯一契约。实现与本文冲突时，改实现，不改字段名。

---

## 0. 产品口径（优化后）

1. **工作台做在现有网页里**，启动页加「创一本」，`phase=studio`，不新开站、不进 Godot。
2. **AI 只写中间稿**（world / detail / acts）。落盘 JSON 只许 `studio.compiler` 写。
3. **无 key 必须能演示**：`use_llm=false` 或无 `LLM_API_KEY` 时走 `mock_bible`（种子填空 + 固定骨架），闸门仍要绿。
4. **禁止覆盖** `content/scenarios/kanshan/` 与 `template/`。生成目录只许 `content/scenarios/gen_*`。
5. **知识卡不杜撰作者**：快本从 kanshan 复制 5 张真卡，只改 `binds`。
6. **试玩走真实引擎**：`POST /api/session` 增加 `scenario_id`；`EngineDriver` 换目录。前端「开一局」先拉 `/public` 水合 `window.MOCK` 再进局。
7. **阵营 / 里层真相 / secret.guilt 不得出现在 `/public`。**

评委 30 秒路径：菜单「创一本」→ 预置种子或自打一句 → 出世界海报 → 闸门绿 → 开一局搜证。

---

## 1. 目录所有权（本轮零冲突）

| 目录 / 文件 | 所有者 | 可写 |
|---|---|---|
| `game/docs/STUDIO_WORKBENCH.md` `game/schemas/studio_*.example.json` | A | 冻结，他窗只读 |
| `game/studio/`（除 `llm_steps.py`） | A 已预置 mock 编译器 | S1 可修 bug，禁止推翻签名 |
| `game/studio/llm_steps.py` + `game/agents/prompts/studio_*.md` | **S1 LLM 线** | 只加 LLM 三步 |
| `game/server/main.py` 及相关 session 装载 | **S2 服务端** | 路由 + `scenario_id` 换目录 |
| `game/frontend/`（studio 视图/样式/菜单入口/水合） | **S3 前端** | 不得改引擎协议字段名 |
| `game/tests/test_studio.py` | **S4 测试** | 只新增此文件 |
| `game/content/scenarios/kanshan/` | 只读 | 允许 **复制** knowledge_cards，禁止改原文 |
| `game/engine/` `game/agents/*.py`（prompts 除外） | 禁止 | P0 零改签名 |

---

## 2. 快本配额（闸门硬数）

| 项 | demo |
|---|---|
| 角色 | 4（`char_01` pollution ×1，`char_02` swayable ×1，`char_03` `char_04` truth） |
| 地点 | 6（`loc_reception` / `loc_server` / `loc_teahouse` / `loc_archive` / `loc_monitor` / `loc_hotfeed`） |
| 线索 | 12 = public 6 + limited 3 + hidden 2 + fake 1（**无 boss_flaw**） |
| 真相节点 | 6，每点 `proof_clues` ≥ 2 |
| 幕 | 3：`break_ice`(6AP) → `investigate`(9AP) → `accuse`(3AP) |
| 记忆 | 4×V1-V3；至少 2 人 said/heart 矛盾 |
| 热搜 | 8 帖；其中 ≥4 条 `is_fake` 且 `topic_tag` 能对上已复制知识卡 |
| 知识卡 | 复制 kanshan 的 `kc_02/kc_03/kc_01/kc_04/kc_09`，binds 分别改到 char_01/02/03/04/`team_all` |
| 里层 Boss | P0 默认关 |

地点 **scene_map 的 key 必须是 `loc_*`**（前端搜证发这个 id）。线索落盘 `location` 必须是 scene_map 的 **中文 name**（引擎 `EvidenceChain` 按中文匹配）。`EngineDriver` 已做 key↔中文双口径。

美术：角色立绘 / 地点图复用已有 `content/assets/images/`，禁止灰块、禁止外链。

---

## 3. 公共 Python API（`from studio import ...`）

签名冻结。实现已在 `game/studio/`。

```python
TIERS = ("demo",)  # P0 只认 demo；传入其它值 → ValueError

def generate(seed: str, *, tier: str = "demo", use_llm: bool = False,
             inner_boss: bool = False, llm=None) -> dict:
    """一键：圣经 → 编译 → 闸门 → 返回 job。
    use_llm=True 且 llm_steps 可用才走模型，失败必须回退 mock，不得抛给路由。"""

def load_job(scenario_id: str) -> dict:
    """读 content/scenarios/{id}/_studio/job.json"""

def list_jobs() -> list[dict]:
    """所有 gen_* 的简表（id/title/status/gate.ok）"""

def public_snapshot(scenario_id: str) -> dict:
    """试玩水合包：无 faction / secret / inner_truth / guilt。"""

def compile_bibles(world, detail, acts, *, scenario_id: str) -> dict:
    """重编译（S1 改圣经后）。"""

def validate_dir(scenario_dir, tier: str = "demo") -> dict:
    """返回 {"ok": bool, "errors": [str], "warnings": [str]}"""
```

`job` 顶层键（只增不改）：

```
id, status, tier, seed, world, detail, acts, gate, provider, scenario_dir, created_at
```

- `status`：`ready`（闸门绿，可开玩）| `failed`（闸门红，目录可留作调试）| `draft`
- `provider`：`mock` | `main` | `zhida`
- `id` 形如 `gen_<slug>_<6hex>`，slug 仅 `[a-z0-9_]{1,24}`

---

## 4. REST（S2 实现，只增不改 §3.6 事件）

```
POST /api/studio/generate
  body: { "seed": str, "tier": "demo", "use_llm": bool, "inner_boss": false }
  → 202 { "ok": true, "job_id": str, "scenario_id": null, "status": "running", "notice": str }
  任务只在后台线程执行；客户端不得等待本次 POST 返回完整 job。
  种子空 → 400；tier 非法 → 400

GET  /api/studio/jobs/{job_id}
  → 200 { "ok": true, "job": { "job_id": str, "status": "running|ready|failed", ... } }
  `status=running` 继续轮询；`ready` 才能进入试玩；`failed` 返回 `error` 且禁止开局。
  任务完成后 `job` 是作者视图的精简响应（去掉 `detail.memories`），完整版本仍由下方作者接口读取。
  任务不存在 → 404；服务重启后仍可用 `gen_*` 的 `scenario_id` 回查磁盘 job。

GET  /api/studio
  → { "ok": true, "items": list_jobs(), "presets": [...] }

GET  /api/studio/catalog
  → { "ok": true, "items": [{ "scenario_id": str, "title": str, "status": str, ... }] }

GET  /api/studio/{id}
  → { "ok": true, "job": load_job(id) }   404 if missing
  这是作者视图：包含完整 `world/detail/acts/gate/status`，其中 `detail` 可含角色秘密与记忆稿。

GET  /api/studio/{id}/public
  → { "ok": true, "pack": public_snapshot(id) }   仅 ready 可开玩；failed 仍 200 但 pack.playable=false
  这是试玩水合包：只含前端可见字段，不得用来读取作者真相或闭卷秘密。

POST /api/session
  新增可选字段 scenario_id（缺省 kanshan）
  非法 / 目录不存在 / 黑名单 → 400
  session 必须持久化 scenario_id，get_engine / get_runtime / mock 建局都换目录
```

`GameServer` 默认目录仍是 kanshan。启动探活继续装载 kanshan。只在 **session 级** 换目录。

### Windows 调用约定

Windows `cmd.exe` / PowerShell 不保证能正确解析带嵌套引号、换行和中文的 `curl -d`。统一使用项目内 Python 客户端，客户端会自行编码 UTF-8 JSON，并强制直连本机 loopback：

```text
cd game
python tools/studio_request.py catalog
python tools/studio_request.py generate --seed "深夜自习室，所有课本一夜之间变成空白"
python tools/studio_request.py job gen_xxx
python tools/studio_request.py public gen_xxx
python tools/studio_request.py session --scenario-id gen_xxx --mode quick
```

默认服务地址是 `http://127.0.0.1:8899`。远程服务用 `--base https://你的域名`；不要把远程地址改写成 `127.0.0.1`。

---

## 5. `/public` 水合包（S3 用来替换 MOCK 子集）

```json
{
  "playable": true,
  "id": "gen_xxx",
  "title": "",
  "genre": "",
  "summary": "",
  "logline": "",
  "hook": "",
  "acts": [{"id":"act1","name":"","stage":"break_ice","brief":""}],
  "locations": [{"id":"loc_reception","name":"前台","type":"base",
                 "img":"/assets/images/scene_reception.png",
                 "pos":{"x":50,"y":87},"hint":"","keywords":[]}],
  "characters": [{"id":"char_01","name":"","archetype":"",
                  "avatar":"/assets/images/char_liuliangjiang.png",
                  "bio":"","speech":"","goal":"","heartache":"kc_02",
                  "replies":["","",""],"heartLine":""}],
  "clues": [{"id":"clue_001","name":"","tier":"public",
             "location":"loc_reception","location_name":"前台",
             "tags":[],"fact":"","flavor":"","linked":[],"unlock":"默认"}],
  "kcards": [{"id":"kc_02","title":"","author":"","topic_tag":"",
              "binds":"char_01","effect":"","golden":[],"summary":""}],
  "posts": [{"id":"post_001","round":1,"title":"","body":"",
             "author":"网友","fake":false,"tag":"","delta":6,"humor":"玩梗"}],
  "truthNodes": [{"id":"tn_01","name":""}],
  "memories": { "char_01": [ {"version":1,"blocks":[],"diff":[]} ] },
  "dm": {"name":"叮——系统提示音","avatar":"/assets/images/dm_kanshan_holo.png"}
}
```

S3 水合时：**只替换** `M.locations / chars（保留原 DM 或用 pack.dm）/ clues / kcards / posts / memories / truthNodes`。其它 MOCK（成就、小游戏、鱼干）保持看山本，避免把 HUD 打穿。章节菜单：快本仍用三章壳，第三章把热搜+指认放一起即可（`accuse` 当第三幕）。

「开一局」：

1. `GET /api/studio/{id}/public` 且 `playable`
2. `Store.applyStudioPack(pack)`
3. `POST /api/session { mode:"quick", scenario_id, player_id }`
4. 能连 WS 则连；失败 toast 后仍可本地 MOCK 玩水合数据
5. `phase='play'`，卷宗文案改用 pack.hook / summary
6. 引擎第一幕是 `break_ice`（只许 chat/advance）。开局先进圆桌；按钮「开始搜证」发 `advance` 后进地图。**不要改 engine/。**

---

## 6. LLM 三步（S1，可后接，不挡 mock 演示）

| 步 | prompt | 输出 |
|---|---|---|
| 1 | `agents/prompts/studio_world.md` | 对齐 `schemas/studio_world.example.json` |
| 2 | `studio_detail.md` | `studio_detail.example.json`（user 必须带已锁 world） |
| 3 | `studio_acts.md` | `studio_acts.example.json`（user 带 world+detail 摘要） |

`llm_steps.generate_bibles(seed, tier, llm, inner_boss=False) -> {world, detail, acts}`

约束写进 system：只输出 JSON；锁定后禁止改真凶与 world_rules；线索拆 fact/flavor_hint；禁止虚构知识卡作者；快本无 boss_flaw。解析失败重试 ≤2，再失败抛给 pipeline 回退 mock。

---

## 7. 闸门错误字面（S4 可断言子串）

- `BLACKLIST: 拒绝写入 kanshan/template`
- `QUOTA: 线索总数应为 12`
- `REF: clue_pool 引用不存在`
- `REF: truth_node 证明不足`
- `FACTION: 需要 1 污染 + ≥1 可策反`
- `FAKE: fake 必须有 fake_of 且不得入 clue_pool`
- `KC: binds 指向不存在角色`
- `TAG: 辟谣帖 topic_tag 无法对齐知识卡`

闸门红：`status=failed`，**禁止**被 `/public.playable=true`，**禁止**被 session 当作可玩本（S2 建局时若 status≠ready → 400）。

---

## 8. 预置种子（无 key 演示）

1. `全员被锁在 24 小时热榜机房里，热搜日志缺了七分钟`
2. `盐言房间出不去，横幅写着不出真相不出此门`

`POST /api/studio/generate` 的 `seed` 用这两句之一即可稳定出 ready。

---

## 9. 验收（P0）

```
cd game
python -m studio --seed "全员被锁在 24 小时热榜机房里，热搜日志缺了七分钟"
# 打印 scenario_id 且 gate.ok=true

pytest tests/test_studio.py -q
# EngineDriver(gen_dir) 能 create_session + search 命中

# 浏览器：菜单「创一本」→ 点预置种子 → 海报 → 开一局 → 地图 6 点可搜
```

看山本回归：`pytest tests/test_schema.py tests/test_engine_units.py -q` 不得因本轮变红（S2 缺省 scenario_id 必须仍是 kanshan）。
