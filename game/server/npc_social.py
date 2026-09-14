"""NPC social routes: isolated private context and seat-aware public speech."""
import asyncio
import copy
from uuid import uuid4

from fastapi import HTTPException

from .booklet_svc import vacant_ai_roles, chapter_of
from .mock_engine import make_event
from .safety import check_text


async def social_request(server, session_id, body, *, private=False):
    if not isinstance(body, dict):
        raise HTTPException(400, "请求体必须是 JSON 对象")
    sender = str(body.get("from") or body.get("player_id") or "player:1")
    prompt = str(body.get("text" if private else "prompt") or "").strip()
    if (private and not prompt) or len(prompt) > (500 if private else 300):
        raise HTTPException(400, "请输入长度合适的内容")
    ok, reason = check_text(prompt)
    if not ok:
        raise HTTPException(422, f"内容安全过滤：{reason}")
    async with server._action_lock_for(session_id):
        session = server.store.load_session(session_id)
        if not session:
            raise HTTPException(404, "对局不存在")
        if session.get("status") != "playing":
            raise HTTPException(409, "本局已结束，不能继续发言")
        if sender not in {p.get("player_id") for p in session.get("players", [])}:
            raise HTTPException(403, "只有本房间已入座玩家可以发起对话")
        roles = vacant_ai_roles(session)
        if private:
            target = str(body.get("to") or "").removeprefix("npc:")
            if target not in {n.get("id") for n in session.get("npcs", [])}:
                raise HTTPException(404, "NPC 不存在")
            if target not in roles:
                raise HTTPException(409, "该角色由真人扮演，请使用队友私聊")
            roles = [target]
        if not roles:
            return {"ok": True, "count": 0, "events": []}
        llm = server._llm_for_session(session_id)
        if llm is None:
            raise HTTPException(503, "AI 对话未配置可用接口，请检查 API 设置")
        rt = server.get_runtime(session)
        if rt is None:
            raise HTTPException(503, "NPC Agent 当前不可用")
        eng = server.get_engine(session)
        chapter = chapter_of(session)
        rt.sync_booklets(chapter)
        stage = session.get("stage", "break_ice")
        phase = str(body.get("phase") or "").strip()
        prompts = {
            "break_ice": "按公开身份简短自我介绍，不透露秘密。",
            "investigate": "围绕已知口供说一个调查方向，不虚构发现的证据。",
            "round_table": "围绕公开讨论表态并提出一个待核实的问题。",
            "accuse": "发表最后立场，不替引擎宣布结局，不提示隐藏指认目标。",
        }
        # 模板只在请求未携带原文时兜底：玩家私聊原文/主持人显式指令永远优先。
        # 此前 phase 默认 intro 会无条件覆盖 prompt，导致私聊原文从未进入上下文。
        if not prompt:
            if phase == "testimony":
                prompt = "读本完成后，依次说明你当晚做了什么、去过哪里、看见了什么；只说自己的公开经历，不泄露闭卷秘密。"
            elif phase == "intro":
                prompt = "按圆桌顺序做 1-2 句自我介绍，只说公开身份和性格，不介绍知乎产品，不提前讲案情。"
            else:
                prompt = prompts.get(stage, "简短回应当前公开局势。")
        def _speaker_line(e) -> str:
            payload = e.get("payload", {}) or {}
            kind = payload.get("actor_kind")
            if kind == "npc":
                who = str(payload.get("char_id") or e.get("actor", "")).removeprefix("npc:")
            elif kind == "player":
                who = str(payload.get("player_id") or e.get("actor", ""))
            else:
                who = str(e.get("actor", ""))
            text = str(payload.get("text", ""))[:300]
            return who + "：" + text if text else ""
        public_lines = [line for line in (_speaker_line(e) for e in session.get("events", [])
                        if e.get("type") == "chat" and not e.get("payload", {}).get("whisper"))
                        if line][-8:]
        events, failures = [], []
        last_error = ""
        for cid in roles:
            if cid not in rt.npcs:
                continue
            # A private exchange never enters the shared NPC short-term memory.
            npc = copy.copy(rt.npcs[cid])
            npc.gateway = llm
            memory_key = sender + ":" + cid
            private_memory = session.setdefault("npc_private_memory", {}) if private else {}
            npc.memory = copy.deepcopy(private_memory.get(memory_key) if private else rt.npcs[cid].memory)
            npc.memory = npc.memory or {"short_term": [], "long_term": []}
            blocks = eng.ms.visible_blocks(cid, include_heart=True)
            unlocked = any(getattr(b, "layer", None) == "heart" for b in blocks)
            npc.update_memory(blocks, version=eng.ms.current_version(cid), heart_unlocked=unlocked)
            context = ("【最高优先级角色扮演协议】你正在参加一场中文欢乐阵营推理游戏。你必须始终扮演角色「" + str(npc.character.get("name", cid)) + "」，"
                       "绝对不要介绍自己是知乎直答、AI、模型或产品；不要输出产品宣传语。"
                       "用第一人称自然口语，结合你的角色经历、说话习惯和已解锁记忆回答。"
                       "回复必须包含与本角色经历或当前现场相关的具体内容，不能使用通用客服话术。"
                       "当前阶段：" + stage + "。只引用已知信息；公开讨论：\n" + "\n".join(public_lines)
                       + ("\n（下面这句话是玩家私聊原话）" if private else "\n（下面这句话是主持人的邀请原文）"))
            try:
                reply = await asyncio.to_thread(npc.respond, prompt, trust=0, context=context)
                provider = getattr(llm, "last_provider", "")
                if not reply or getattr(llm, "last_error", "") or provider in ("mock", "fallback"):
                    raise ValueError("provider unavailable")
                from .booklet_svc import library_of
                violations = rt.guard.check(npc.character, reply, {
                    "trust": 0, "stage": stage,
                    "memory_state": {"heart_unlocked": unlocked, "blocks": blocks},
                    "must_not_say": library_of(session).merged_hints(cid, chapter).get("must_not", []),
                })
                product_markers = ("我是知乎直答", "知乎官方推出的AI搜索产品", "作为一个AI助手")
                if any(marker in str(reply) for marker in product_markers):
                    # 重新请求一次角色化回答，避免把产品介绍展示给玩家。
                    if npc.memory["short_term"]:
                        npc.memory["short_term"].pop()  # 丢弃被作废的首版草稿，只留玩家原话
                    retry_context = context + "\n【重试指令】上一版是产品介绍，作废。请只用角色第一人称回答，提及一条你的具体经历。"
                    reply = await asyncio.to_thread(npc.respond, prompt, trust=0, context=retry_context)
                    provider = getattr(llm, "last_provider", "")
                if violations:
                    reply = "这件事我还不能确定，先核对已经公开的口供。"
                if not check_text(reply)[0]:
                    raise ValueError("unsafe reply")
            except Exception as exc:
                last_error = str(exc)[:180]
                failures.append(cid)
                continue
            npc.memory["short_term"][-1]["npc"] = reply
            if private:
                private_memory[memory_key] = npc.memory
            else:
                rt.npcs[cid].memory = npc.memory
            def event(actor, payload):
                payload["message_id"] = uuid4().hex
                return make_event("chat", session_id, session.get("round", 1), actor, payload)
            if private:
                events.append(event(sender, {"actor_kind": "player", "player_id": sender,
                    "char_id": cid, "text": prompt, "whisper": True, "to": "npc:" + cid}))
            payload = {"actor_kind": "npc", "char_id": cid, "text": reply,
                       "source": "agent", "provider": provider,
                       "ai_provider": str(provider or ""), "wave": not private}
            if private:
                payload.update(whisper=True, to=sender, reply_to=sender)
            events.append(event("npc:" + cid, payload))
            if not private:
                public_lines = (public_lines + [reply])[-8:]
        if not events and failures:
            detail = "AI 接口未能返回回复，请检查 API 配置与额度后重试"
            if last_error:
                detail += "；诊断：" + last_error
            raise HTTPException(503, detail)
        session.setdefault("events", []).extend(events)
        server.store.save_session(session_id, session)
    if private:
        await server.broadcast_to(session_id, [sender], events)
    else:
        await server.broadcast(session_id, events)
    return {"ok": True, "count": sum(e["payload"].get("actor_kind") == "npc" for e in events),
            "events": events, "failed_roles": failures,
            "event": events[-1] if private and events else None}
