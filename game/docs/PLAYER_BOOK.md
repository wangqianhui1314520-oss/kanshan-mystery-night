# 游玩角色故事本 · 认约

> 窗口：创一本补齐「每人一本可读故事本」
> 依赖：`docs/STUDIO_WORKBENCH.md`（不改其已冻字段名）
> 实现：`studio/player_book.py`（零 LLM）→ compiler 落盘 → 闸门 → 选角读本 → 开局

产品口径补一句：**工作台按需求生成可玩快本之后，每个可认领角色必须有一本仅本人可读的故事本。** 玩家仍不读万字剧本；故事本是一页任务卡（人设 / 任务 / 公开信息 / 隐瞒的事 / 开局提示）。

---

## 1. 落盘（只许 `studio.compiler` 写）

目录：`content/scenarios/gen_*/scripts/`（禁止写 `kanshan/`、`template/`）。

| 文件 | 谁看 | 内容 |
|---|---|---|
| `player_book_{char_id}.json` | 引擎 / API | 故事本源数据 |
| `player_book_{char_id}.md` | 作者 / 打印 | 同一本的可读稿 |

快本配额 4 人 → 必须正好 4 对本（json+md）。`char_id` 与 `characters/{id}.json` 对齐。

角色卡 `role_type` **保持现字段、不改成 player**（引擎 / party 仍按 npc 席 + 真人认领）。故事本覆盖全部 4 席：谁认领谁读。

---

## 2. JSON 字段（只增不改）

对齐 `schemas/player_book.example.json`。

```
char_id, name, archetype, you_are, situation,
goals: [str],
known_facts: [str],
secrets: [str],          # 仅本人 / 作者
must_not_say: [str],     # 仅本人 / 作者
opening: { time, location, first_step },
relations: [{ char_id, name, hint }]
```

- `you_are`：公开人设 + 处境，**禁止**写 guilt / faction / 真凶。
- `situation`：锁局当下人人可知的处境（钩子 / 锁门规则），禁止剧透真凶。
- `known_facts`：该角色开局就知道、且可对圆桌说的事（含表面故事、本人对外口径）。
- `secrets` / `must_not_say`：动机、把柄、guilt、不可主动说出口的话。
- `relations.hint`：对其他人的**公开印象**，禁止写对方 guilt。

---

## 3. 可见性

| 出口 | 带什么 | 禁止 |
|---|---|---|
| `GET /api/studio/{id}/public` 的 `books` | **封面**列表 | `secrets` `must_not_say` `faction` `guilt` `inner_truth` |
| `GET /api/studio/{id}/books` | 同上封面列表 | 同上 |
| `GET /api/studio/{id}/book/{char_id}` | **全本**（单人试玩 / 作者预览） | 不得出现在广播事件里 |
| `POST /api/session` 与 `POST /api/session/{id}/join` 的 HTTP 响应 | 仅当该请求认领了 `char_id` 时带 `player_book` 全本 | **禁止**写入 `broadcast` / `seats_public` / 系统事件 |

封面（`public_cover`）只含：

```
char_id, name, archetype, you_are, opening.location
```

`studio/job.json` 是作者视图，可保留全本（`detail.player_books` 或编译后回写），前端导演台「开局」步可预览。

---

## 4. Python API（`studio.player_book`）

```python
def build_books(world, detail, acts) -> list[dict]: ...
def render_md(book: dict) -> str: ...
def public_cover(book: dict) -> dict: ...
def player_view(book: dict) -> dict: ...   # 全本；缺页则补空列表
def write_books(scenario_dir: Path, books: list[dict]) -> None: ...
def load_book(scenario_dir: Path, char_id: str) -> dict: ...
def list_covers(scenario_dir: Path) -> list[dict]: ...
```

`compiler.compile_bibles` 在写完 `characters/` 后调用 `build_books` + `write_books`。
`validate_dir` 增闸门字面：**`BOOK: 每个角色必须有故事本`**（缺文件、char_id 对不上、`you_are`/`goals` 为空均用此句）。

旧 `gen_*` 目录若尚未重生成，`list_covers` 返回 `[]`，前端走原「直接开玩」路径，不得把旧本闸门打红（闸门只跑在 `generate` / 重编译）。

---

## 5. REST（只增不改已有字段）

```
GET /api/studio/{id}/books
  → 200 { "ok": true, "items": [cover...] }

GET /api/studio/{id}/book/{char_id}
  → 200 { "ok": true, "book": <player_view> }
  → 404 本不存在或该角色无故事本
```

`/public` 包新增键 `books`（封面数组）。`playable` 规则不变。

---

## 6. 前端

1. `applyStudioPack` 把 `pack.books` 写入 `state.studioBooks`。
2. `playStudio`：若 `books.length > 0`，水合后进入 **`phase='seat'`**，不要直接 `play`。
3. 选角页：有故事本封面时，展示 4 张角色卡（立绘 + 名字 + `you_are`）。点选后请求全本，右侧/下方翻开故事本。
4. 确认后走原序章 / 开局。局内可再打开「我的本子」（只读当前 `state.playerBook`）。
5. 看山本（无 `gen_*` / 无 books）选角页保持原样（形象 6 选 1）。
6. 样式写进 `frontend/css/studio.css`，不新增 css 文件、不改 `index.html` 的 link 列表。

---

## 7. 验收

```
cd game
python -m studio --seed "全员被锁在 24 小时热榜机房里，热搜日志缺了七分钟"
# scripts/ 下 4 组 player_book_char_0N.json/.md；gate.ok=true

pytest tests/test_player_book.py tests/test_studio.py -q
```

浏览器：创一本 → 生成 → 开这本新本 → 选角翻开故事本（含隐瞒的事）→ 确认进序章。看山本开局选角不得被带跑。
