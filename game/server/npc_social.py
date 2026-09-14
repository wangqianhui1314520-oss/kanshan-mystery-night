"""NPC social routes: isolated private context and seat-aware public speech."""
import asyncio
import copy
import re
from uuid import uuid4

from fastapi import HTTPException

from .booklet_svc import vacant_ai_roles, chapter_of
from .mock_engine import make_event
from .reply_guard import RETRY_HINT, has_product_identity
from .safety import check_text

# 守卫违规替换句池（2026-09-14 P1-1）：台词触发一致性守卫时的保守收口。
# 按原 reply 长度稳定取样，多席同轮触发也各不相同（不用 random，可复现）。
_VIOLATION_SAFE_LINES = (
    "这件事我还不能确定，先核对已经公开的口供。",
    "（看了你一眼）你说的这个，我暂时不便多讲。",
    "先把我刚才说的公开部分记住，别急着往下问。",
    "这话我得斟酌一下，等大家都把话说清楚再说。",
    "你这么问是想套我的话？公开的部分我再说一遍就是了。",
    "（笑了笑）这个问题，恐怕你自己心里也有数。",
)


def infer_social_phase(session: dict, stage: str) -> str:
    """从最近 DM 引导文本推断社交 phase，让 AI 跟随 DM 引导行动。

    - DM 说"自我介绍/介绍自己" → intro（AI 轮流介绍）
    - DM 说"读本/剧本/证词" → testimony（AI 轮流陈述当晚经历）
    - DM 说"自由讨论/搜证" 或阶段已过破冰 → 空（自由讨论回应模式）
    只读事件流，不改任何状态，供真人发言后的回应路径使用。
    """
    for ev in reversed((session.get("events") or [])[-40:]):
        if str(ev.get("actor") or "") != "dm":
            continue
        payload = ev.get("payload") or {}
        text = str(payload.get("text") or payload.get("summary") or "")
        if not text:
            continue
        if ("自由讨论" in text or "搜证" in text or "开始讨论" in text):
            return ""
        if "读本" in text or "剧本" in text or "证词" in text:
            return "testimony"
        if "介绍" in text:
            return "intro"
        break
    # 无 DM 引导证据时回落讨论回应模式：全员轮流介绍只由显式 phase=intro
    # （前端破冰入口 / DM 面板按钮）触发，避免每条真人发言都整桌刷屏。
    return ""


async def social_request(server, session_id, body, *, private=False,
                         max_roles: int = 0):
    """公开社交波：真人一句话触发后，全体空席 AI 按席位顺序「串联逐个」回复。

    每席独立调用一次 API（一席一句），后手 AI 的上下文包含玩家原话与
    前面全部 AI 的回复，保证衔接连贯；每个 AI 可选择保持沉默
    （回复【沉默】标记时不产出消息）。max_roles 保留参数兼容旧调用，
    但默认 0 = 不限波次，一次请求全员依次回复完毕（知乎直答比赛模式
    已取消本地 QPS 限流，见 llm_client / zhihu_gateway 同步改动）。"""
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
        # 未显式指定 phase 时跟随 DM 引导：真人发言后的回应路径不传 phase，
        # 由 DM 最近引导文本决定 AI 该"轮流介绍"还是"自由讨论回应"。
        if not phase and not private:
            phase = infer_social_phase(session, stage)
        # max_roles 解析：body 显式 > 签名默认。0 = 不限波次——一次请求全员
        # 按席位顺序串联回复完毕（比赛模式已取消本地 QPS 限流：llm_client
        # 取消强制间隔、zhihu_gateway 节流改为等待，官方 429 由退避重试兜住，
        # 不再需要分波规避）。仅当 body 显式传正整数时才截断席位（旧调用兼容）。
        if body.get("max_roles") is not None:
            max_roles = int(body.get("max_roles") or 0)
        else:
            max_roles = int(max_roles or 0)
        # 自动回应（真人公开发言后）：同样全员一轮串联回复；DM 引导环节
        # （intro/testimony）轮过一轮后回落自由讨论回应模式，不重复介绍。
        auto_respond = bool(body.get("respond_trigger")) and not private
        if auto_respond:
            done = set(session.get("social_phases_done") or [])
            if phase in ("intro", "testimony") and phase not in done:
                pass                     # 引导轮：全员轮流跟随
            else:
                phase = ""               # 引导已轮过 / 自由讨论：回应模式
        # 全员串联回复：严格按席位池顺序（vacant_ai_roles 返回序）逐个调用，
        # 不再轮转截断/分波（比赛模式已取消本地 QPS 限流，官方 429 由退避
        # 重试兜住）。served_map/track_key 保留用于引导轮 covered 记账与
        # remaining 汇报；social_wave_cursor 历史字段不再使用。
        served_map = session.setdefault("social_served", {})
        vacant_at_start = len(roles)
        track_key = phase if phase in ("intro", "testimony") else (
            "reply" if auto_respond else "free")
        if body.get("max_roles") is None or int(body.get("max_roles") or 0) <= 0:
            take = len(roles)            # 默认：全员一轮
        else:
            take = min(int(body["max_roles"]), len(roles))  # 旧调用显式截断兼容
        prompts = {
            "break_ice": "按公开身份简短自我介绍，不透露秘密。",
            "investigate": "针对刚才玩家们的公开发言做出回应：可直接回答、提出追问、表达质疑，或补充你视角的信息；不虚构发现的证据。",
            "round_table": "针对刚才玩家们的公开发言表态：赞同就给出理由，怀疑就抛出待核实的质问；不替引擎宣布结局。",
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
        # 玩家刚发言的原文（public_lines 里 player: 开头的最后一条），
        # 供 context 强调"正面回应"，让 AI 围绕聊天内容沟通而非自说自话。
        last_human_line = next(
            (ln for ln in reversed(public_lines)
             if ln.split("：", 1)[0].startswith("player:")), "")
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
                       "当前阶段：" + stage + "。只引用已知信息；公开讨论最近发言：\n" + "\n".join(public_lines)
                       + ("\n（下面这句话是玩家私聊原话）" if private else "\n（下面这句话是主持人的邀请原文）"))
            if not private and last_human_line:
                context += ("\n（最近一条真人玩家发言：" + last_human_line
                            + " ——请优先正面回应它：回答、反问、质疑，或结合你的经历补充；不要复读别人说过的话。）")
            if not private:
                context += ("\n（你可以选择是否发言：若有值得说的话请给出实质回复；"
                            "若此刻你的角色确实无需表态、插话会显得刻意，就只回复【沉默】两个字，"
                            "表示保持安静。除【沉默】外不要输出任何旁白或说明。）")
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
                if has_product_identity(reply):
                    # 重新请求一次角色化回答，避免把产品介绍展示给玩家。
                    if npc.memory["short_term"]:
                        npc.memory["short_term"].pop()  # 丢弃被作废的首版草稿，只留玩家原话
                    retry_context = context + "\n" + RETRY_HINT
                    reply = await asyncio.to_thread(npc.respond, prompt, trust=0, context=retry_context)
                    provider = getattr(llm, "last_provider", "")
                if violations:
                    # P1-1（2026-09-14）：扩池+稳定轮换，按原 reply 长度取样——
                    # 多席同时触发也各不相同，不再单句复读。
                    npc.last_reply_kind = "violations"
                    reply = _VIOLATION_SAFE_LINES[
                        len(str(reply)) % len(_VIOLATION_SAFE_LINES)]
                if not check_text(reply)[0]:
                    raise ValueError("unsafe reply")
            except Exception as exc:
                last_error = str(exc)[:180]
                failures.append(cid)
                continue
            # 选择性回复：AI 声明保持沉默（只回【沉默】标记）时，本席不产出
            # 任何消息（不出现在聊天流），短期记忆保留「（沉默）」——它记得
            # 自己这轮没说话；随后轮到下一席继续。
            if not private and re.fullmatch(r"[（(【\s]*沉默[）)】\s]*", reply.strip()):
                npc.memory["short_term"][-1]["npc"] = "（沉默）"
                rt.npcs[cid].memory = npc.memory
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
            # P1-2 诚实化：守卫层替换（identity_guarded/violations）标 fallback:*
            kind = getattr(npc, "last_reply_kind", "llm")
            if kind != "llm":
                payload["provider"] = payload["ai_provider"] = f"fallback:{kind}"
                payload["degraded"] = True
            if private:
                payload.update(whisper=True, to=sender, reply_to=sender)
            events.append(event("npc:" + cid, payload))
            if not private:
                public_lines = (public_lines + [reply])[-8:]
                # 上下文串联：本席回复立即进入公开最近发言，下一席 AI 的
                # prompt 会带上它（逐席衔接、连贯自然）；节流已按比赛模式
                # 取消，连续调用由 llm_client/gateway 的等待型限流兜底。
                # 逐席实时广播：玩家即时看到「AI 一句接一句」的串联节奏，
                # 无需等全员生成完毕才齐刷上屏（HTTP 响应仍带全量 events，
                # 前端按 message_id 去重，不会重复上屏）。
                await server.broadcast(session_id, [events[-1]])
        if not events and failures:
            detail = "AI 接口未能返回回复，请检查 API 配置与额度后重试"
            if last_error:
                detail += "；诊断：" + last_error
            raise HTTPException(503, detail)
        # 按实际发言数回写该用途的已服务席位（respond 失败不计），并据此前推
        # 引导轮是否覆盖满一轮空席（covered → social_phases_done）。
        if not private and events:
            spoke = sum(1 for e in events
                        if e.get("type") == "chat" and str(e.get("actor") or "").startswith("npc:"))
            served_map[track_key] = int(served_map.get(track_key) or 0) + spoke
            if auto_respond and phase in ("intro", "testimony") \
                    and served_map.get(track_key, 0) >= vacant_at_start:
                done = set(session.get("social_phases_done") or [])
                done.add(phase)
                session["social_phases_done"] = sorted(done)
        session.setdefault("events", []).extend(events)
        server.store.save_session(session_id, session)
    if private:
        await server.broadcast_to(session_id, [sender], events)
    # 公开路径已逐席实时广播，无需整批重发（前端按 message_id 去重双保险）。
    return {"ok": True, "count": sum(e["payload"].get("actor_kind") == "npc" for e in events),
            "remaining": max(0, vacant_at_start - int(served_map.get(track_key) or 0)) if not private else 0,
            "events": events, "failed_roles": failures,
            "event": events[-1] if private and events else None}
