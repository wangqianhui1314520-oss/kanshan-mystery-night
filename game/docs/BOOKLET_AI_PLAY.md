# 闭卷与 AI 按本游玩

玩家读本：选角后发封 A，第二章发封 B，第三章发封 C。单人默认《特聘调查员》。房间领嫌疑人本。里层 Boss 不写在任何一本上。

## 玩家 API

```http
GET  /api/booklets?scenario_id=kanshan
GET  /api/session/{sid}/booklet?player_id=player:1
POST /api/session/{sid}/booklet/claim
     {"player_id":"player:1","role_id":"investigator"}
```

`GET booklet` 只返回**当前章已开封**的自己的本，含自己的阵营标签。别人的秘密不会出现。

## AI 按本行动（先 dry_run 再落地）

建局时把 LLM 配在 header（与对话同一套）：`X-LLM-KEY` / `X-LLM-BASE` / `X-LLM-MODEL`。没有 key 时走闭卷 `play_hints` 启发式，不编造。

```bash
# 1) 建局
curl -s -X POST http://127.0.0.1:8899/api/session \
  -H "Content-Type: application/json" \
  -H "X-LLM-KEY: $LLM_API_KEY" \
  -H "X-LLM-BASE: $LLM_BASE_URL" \
  -H "X-LLM-MODEL: $LLM_MODEL" \
  -d '{"mode":"main","player_id":"player:1"}'

# 2) 看调查员本（封 A）
curl -s "http://127.0.0.1:8899/api/session/SID/booklet?player_id=player:1"

# 3) 让流量酱按本想一步（不落库）
curl -s -X POST http://127.0.0.1:8899/api/session/SID/ai_act \
  -H "Content-Type: application/json" \
  -d '{"char_id":"char_03","dry_run":true}'

# 4) 真正执行这一步（写入引擎，广播事件）
curl -s -X POST http://127.0.0.1:8899/api/session/SID/ai_act \
  -H "Content-Type: application/json" \
  -d '{"char_id":"char_03","dry_run":false}'
```

返回：

```json
{
  "ok": true,
  "role_id": "char_03",
  "chapter": 1,
  "stage": "break_ice",
  "decision": {
    "type": "chat",
    "payload": {"text": "…按封A腔调…", "target": "char_01"},
    "reason": "封A破冰：按本自我介绍，不搜证",
    "source": "heuristic"
  },
  "applied": false
}
```

`source=llm` 表示模型在合法动作里挑；`heuristic` 表示纯本上的 play_hints。破冰只会 chat，不会去搜热搜后台。

## 自走棋循环

每步：`ai_act` → 读 `decision` → 需要推进阶段再由玩家或再调一次 `advance`。不要绕过 `/action` 自己改 session。

```
for char in char_01..char_08:
    POST /ai_act {char_id, dry_run:false}
玩家或脚本 POST /action {type:advance}
# 进第二章后 GET booklet 会多出封 B，NPC 对话也会换本
```

NPC 答话走原 `POST /action` 的 chat；服务端会把当前章闭卷注入 `<<<BOOKLET>>>`，所以对话也按本，不只是 `ai_act`。

## 角色 id

| id | 本 |
|---|---|
| investigator | 特聘调查员（单人默认） |
| char_01 … char_08 | 知之者 / 笔上仙 / 流量酱 / 路人甲 / 看山Bot / 沉底君 / 盐值君 / V587 |

不要用 `POST /action` 把 `actor` 设成 `ai:char_xx`——那条路对人关闭。只有 `/ai_act` 会带 `allow_ai`。
