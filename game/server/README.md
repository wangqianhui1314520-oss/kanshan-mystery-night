# 服务端（基础设施层）

- main.py: WebSocket 入口（骨架）
- gateway/zhihu_gateway.py: 知乎 API 网关（限额缓存/降级）
- store/session_store.py: 对局存档与长期记忆

实现顺序：先 gateway（限额是硬约束）→ store → main。
