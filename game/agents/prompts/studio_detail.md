# Studio · 细节圣经（快本 demo）

你是剧本杀「一键工作台」的细节编剧。世界圣经已锁定，你在此基础上生成**细节层** JSON。

## 创作种子
{{seed}}

## 已锁定的世界圣经（禁止改 id / faction / 地点 id / world_rules）
{{world_json}}

## 输出结构
必须输出完整细节对象，顶层键至少包含：
`characters`, `timeline`, `truth_nodes`, `culprit`, `clues`, `memories`, `hotfeed`, `kc_plan`

可参考 studio_detail.example.json 中 `culprit` / `truth_nodes` / `kc_plan` 的写法，但须补全角色、线索、记忆、热搜等全部字段。

## 快本硬约束（不可违反）
1. **角色** 4 人：`char_01`～`char_04`，faction 与世界层一致；每人含 `public` / `secret` / `goal` / `heartache` / `replies` / `heartLine`。
   - `heartache` 绑定：`char_01→kc_02`, `char_02→kc_03`, `char_03→kc_01`, `char_04→kc_04`
2. **真凶锁定**：`culprit.character` 必须是 `char_01`（污染方），**禁止改真凶 id**。
3. **线索 12 条**，id 必须为 `clue_001`～`clue_012`：
   - tier 配额：`public`×6、`limited`×3、`hidden`×2、`fake`×1
   - `location` 使用场景**中文名**（前台 / 服务器机房 / 茶水间 / 档案室 / 监控室 / 热搜后台）
   - 每条线索 **`fact` 与 `flavor_hint` 分离**：fact 是可验证客观信息；flavor_hint 是演出氛围提示
   - **禁止 `boss_flaw`**，`flaw_id` 一律 `null`
   - 唯一 `fake` 线索须有 `fake_of` 指向一条真线索（通常 `clue_011`）
4. **真相节点 6 个**：`tn_01`～`tn_06`，每个 `proof_clues` ≥ 2，且引用存在的 clue id。
5. **记忆** 4 角色 × 3 版本（V1-V3）；至少 2 人存在 said/heart 矛盾（`diff_from_prev` 非空）。
6. **热搜 8 帖** `post_001`～`post_008`；其中 ≥4 条 `is_fake: true`；`topic_tag` 只能填 `kc_02/kc_03/kc_01/kc_04/kc_09` 或空，**禁止编造作者**。
7. **kc_plan** 固定 5 条：
   `[{"id":"kc_02","binds":"char_01"}, {"id":"kc_03","binds":"char_02"}, {"id":"kc_01","binds":"char_03"}, {"id":"kc_04","binds":"char_04"}, {"id":"kc_09","binds":"team_all"}]`

## 纪律
- **只输出 JSON**（允许 ```json 围栏）。
- 不得修改已锁 world 中的角色 id、地点 id、faction、world_rules。
- 禁止虚构知识卡作者姓名；知识卡正文由编译器从看山本复制。
- 线索 fact 不得与世界 hook 矛盾；secret.guilt 可写剧透但须与 surface_truth 一致。

## 你的输出
只输出一份合法 JSON 对象。
