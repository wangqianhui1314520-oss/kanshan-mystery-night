"""线索、角色、记忆、热搜、时间轴、幕表。配额锁死，只换文案。"""

from __future__ import annotations

from ..tiers import CHAR_AVATARS, LOCATION_META
from .lexicon import SPEECH


def clues(locs, names, obj, window, device, verb, leftover, signal, quote,
          lock_rule, times, notes, player_crime) -> list[dict]:
    n1, n2, n3 = names["char_01"], names["char_02"], names["char_03"]
    l0, l1, l2, l3, l4, l5 = locs
    note_bit = f" 现场备忘：{notes[:24]}。" if notes else ""
    crime_bit = f" 作者锁定的动作：{player_crime}。" if player_crime else ""
    rows = [
        clue("clue_001", f"{device}【{lock_rule[:8]}】", "public", l0,
             [device[:2], "封控"],
             f"{times['lock']} {l0}上方亮起{device}，全部出口封控。"
             f"控制参数与楼内系统一致。导火索：「{quote}」。{lock_rule}",
             "描写封控压下来的那一秒，不要解释是谁下的令。",
             ["tn_01"], "默认", None),
        clue("clue_002", f"{n1}离席的排班表", "limited", l0,
             ["排班", times["lock"][:2]],
             f"排班表显示{n1} {times['leave']}-{times['back']} 不在{l0}，"
             f"与其『全程都在场安抚』口径冲突。",
             "表格被揉过又展开，褶皱像一句欲盖弥彰。",
             ["tn_06"], "默认", None),
        clue("clue_003", f"{obj}被{verb}的主控记录", "public", l1,
             [obj[:2], verb],
             f"{times['gap_a']}-{times['gap_b']} {l1}留下一次内部{verb}。"
             f"{obj}被内部工具处理，操作账号属{n2}权限组。{crime_bit}",
             "机器的时间戳不会为谁圆谎。",
             ["tn_02", "tn_06"], "默认", None),
        clue("clue_004", f"二次确认与「{signal}」", "hidden", l1,
             ["权限", signal[:2]],
             f"{verb}命令前有一条二次确认，签发备注写着「{signal}」"
             f"——与{l2}留下的{leftover}对得上。",
             "弹窗冷光一闪，像有人在远处清嗓子。",
             ["tn_02"], "memory:char_02:3", None),
        clue("clue_005", f"{leftover}与未送出的纸条", "public", l2,
             [leftover[:2], "纸条"],
             f"{l2}桌面留着{leftover}，压着纸条：『按了就走，别回消息。』"
             f"字迹像{n2}的工牌签名。{note_bit}",
             "物证比道歉先到场。",
             ["tn_03"], "默认", None),
        clue("clue_006", f"{n3}的补打卡截图", "limited", l2,
             ["打卡", times["lock"][:2]],
             f"{n3} {times['late']} 才完成补卡，与其『{times['lock']} 起一直在{l2}』口径冲突。",
             "截图边缘被反复摩挲。",
             ["tn_03"], "默认", None),
        clue("clue_007", f"档案盒被借走（{obj}备份）", "public", l3,
             ["借阅", "备份"],
             f"{times['borrow']} {n2}借走『档案盒·{obj}备份』，归还栏空白，盒内槽位有新插拔痕。",
             "空白比任何否认都响亮。",
             ["tn_04"], "默认", None),
        clue("clue_008", f"被改时间戳的{obj}碎片", "hidden", l3,
             ["时间戳", obj[:2]],
             f"碎片里 {times['crime']} 的哈希还在，明文被替换成『系统例行清理』。"
             f"例行清理从不整段对齐「{window}」。",
             "被擦掉的比留下的整齐。",
             ["tn_04"], "memory:char_03:2", None),
        clue("clue_009", f"人影与{device}同一秒", "public", l4,
             ["监控", "封控"],
             f"{times['lock']}:03 监控拍到有人在{l0}侧门刷内部令牌，{device}在同一秒点亮。",
             "扫描线扫过那一帧，像有人用手抹平脚印。",
             ["tn_01"], "默认", None),
        clue("clue_010", f"{window}空洞的同一账号", "limited", l4,
             ["监控", verb],
             f"{times['gap_a']}-{times['gap_b']} 画面被同一内部账号抹平，"
             f"该账号最后登录设备与{l5}操作机同源。",
             "空洞整齐得像被尺子比过。",
             ["tn_05"], "默认", None),
        clue("clue_011", f"与「{quote[:8]}」同期的设备指纹", "public", l5,
             ["设备", obj[:2]],
             f"与「{quote}」同期冒出的 4 条舆论，创建设备指纹与{n1}常用机重合。",
             "后台不会演戏：同一台设备，两套路人设。",
             ["tn_05", "tn_06"], "默认", None),
        clue("clue_012", f"伪造的{obj}排期", "fake", l5,
             ["伪造", signal[:2]],
             f"一份做旧排期把{verb}写成『{n3} {times['crime']} 独自在{l5}』，纸新墨旧。",
             "栽赃手法很新，心思很旧。",
             [], "默认", "clue_011"),
    ]
    return rows


def clue(cid, name, tier, location, tags, fact, flavor, linked, unlock, fake_of) -> dict:
    return {
        "id": cid, "name": name, "tier": tier, "location": location,
        "tags": tags, "fact": fact, "flavor_hint": flavor,
        "linked_truth_nodes": linked, "unlock_condition": unlock,
        "fake_of": fake_of, "flaw_id": None,
    }


def loc_rows(locs: list[str], clues_rows: list[dict], hook: str) -> list[dict]:
    by_name: dict[str, list[str]] = {}
    for c in clues_rows:
        if c.get("tier") == "fake":
            continue
        by_name.setdefault(c["location"], []).extend(c.get("tags") or [])
    rows = []
    for lid, meta in LOCATION_META.items():
        idx = list(LOCATION_META).index(lid)
        name = locs[idx]
        tags = []
        for t in by_name.get(name, []):
            if t and t not in tags:
                tags.append(t)
        rows.append({
            "id": lid,
            "name": name,
            "type": meta["type"],
            "image": meta["image"],
            "keywords": (tags or list(meta.get("keywords") or []))[:3],
            "hint": f"{name}。{hook[:18]}",
        })
    return rows


def characters(names, arches, bios, hooks, obj, verb, leftover, signal, device, times, locs, mood, quote) -> list[dict]:
    speech = SPEECH.get(mood) or SPEECH["comedy"]
    n1, n2, n3, n4 = names["char_01"], names["char_02"], names["char_03"], names["char_04"]
    bio_def = {
        "char_01": bios["char_01"] or f"热度就是安全感。{obj}从{n1}手指缝里长出来。",
        "char_02": bios["char_02"] or f"刚转正的人，工牌还热乎，胆子已经凉了。被点名去碰{obj}。",
        "char_03": bios["char_03"] or "什么都听说过，什么都不敢确认。",
        "char_04": bios["char_04"] or "门禁记录在抽屉里，勇气在门外。",
    }
    return [
        {
            "id": "char_01", "name": n1, "role_type": "npc",
            "archetype": arches["char_01"], "faction": "pollution",
            "public": {
                "avatar": CHAR_AVATARS["char_01"],
                "bio": bio_def["char_01"],
                "speech_style": speech["char_01"],
            },
            "secret": {
                "motive": f"{obj}快被揭穿，先下手{verb}",
                "alibi": f"声称 {times['lock']} 起都在{locs[0]}安抚人心",
                "guilt": f"遥控{n2}按下{verb}，并投放一条嫁祸{n3}的假证",
            },
            "goal": "把现场搅浑，活到终局",
            "heartache": "kc_02",
            "replies": [
                f"删？换？我连后台密码都懒得记。",
                f"{device}落下的第一秒我就在场，你们查别人。",
                f"「{quote}」明显是有人带节奏，建议先查{n3}。",
            ],
            "heartLine": f"（心声）那{obj}是我让{n2}动的。再挖深一点，我就会被点名。",
        },
        {
            "id": "char_02", "name": n2, "role_type": "npc",
            "archetype": arches["char_02"], "faction": "swayable",
            "public": {
                "avatar": CHAR_AVATARS["char_02"],
                "bio": bio_def["char_02"],
                "speech_style": speech["char_02"],
            },
            "secret": {
                "motive": f"把柄在{n1}手里，不敢不按",
                "alibi": f"说自己去{locs[2]}，没进操作间",
                "guilt": f"{times['crime']} 在{locs[1]}执行了{verb}，留下{leftover}",
            },
            "goal": "别被当主谋，有人撑腰就敢跳反",
            "heartache": "kc_03",
            "replies": [
                f"对不起我可能……我是说我好像没进过{locs[1]}。",
                f"{leftover}真的只是路过留下的。大概。",
                "你们别看我，我还没转正满月。",
            ],
            "heartLine": f"（心声）我按了。暗号是「{signal}」。我想说，可没人先保护我。",
        },
        {
            "id": "char_03", "name": n3, "role_type": "npc",
            "archetype": arches["char_03"], "faction": "truth",
            "public": {
                "avatar": CHAR_AVATARS["char_03"],
                "bio": bio_def["char_03"],
                "speech_style": speech["char_03"],
            },
            "secret": {
                "motive": "看见交接却被改了记忆存证，怕说出来没人信",
                "alibi": f"坚称 {times['lock']} 起一直在{locs[2]}",
                "guilt": "代人刷过一次卡，所以不敢作证",
            },
            "goal": "把看见的事说圆，同时藏住代刷卡",
            "heartache": "kc_01",
            "replies": [
                f"我好像在走廊尽头看过一个背影，也可能是{locs[1]}的门。",
                "打卡机没坏就行，人在不在另说。",
                "别投我，我是背景板啊。",
            ],
            "heartLine": f"（心声）我 {times['late']} 才到{locs[2]}。气窗对着门口，我看见有人塞了盒子。",
        },
        {
            "id": "char_04", "name": n4, "role_type": "npc",
            "archetype": arches["char_04"], "faction": "truth",
            "public": {
                "avatar": CHAR_AVATARS["char_04"],
                "bio": bio_def["char_04"],
                "speech_style": speech["char_04"],
            },
            "secret": {
                "motive": "怕公布记录得罪人",
                "alibi": f"说{locs[0]}一切正常",
                "guilt": f"{times['gap_a']} 门禁异常记录了，却对外说风大",
            },
            "goal": "在不得罪人的前提下把记录交出去",
            "heartache": "kc_04",
            "replies": [
                f"您好，今晚是例行盘点，{device}是流程的一部分。",
                "门禁记录我们有，公布这个会不会不太好呢。",
                "您的情绪波动已记录。",
            ],
            "heartLine": f"（心声）打印件就压在{locs[0]}抽屉。可万一是{n1}呢。",
        },
    ]


def mem(owner: str, version: int, rows: list, diff: list) -> dict:
    blocks = []
    for i, (time, layer, integrity, text) in enumerate(rows, 1):
        blocks.append({
            "id": f"blk_{i}",
            "time": time,
            "layer": layer,
            "text": text,
            "integrity": integrity,
        })
    return {"owner": owner, "version": version, "blocks": blocks, "diff_from_prev": diff}


def memories(names, locs, obj, verb, leftover, signal, device, times, window) -> dict:
    n1, n2, n3, n4 = names["char_01"], names["char_02"], names["char_03"], names["char_04"]
    return {
        "char_01": [
            mem("char_01", 1, [
                (times["speech"], "said", "original", f"我在{locs[0]}发欢迎词，数据表明全员情绪稳定。"),
                (times["crime"], "said", "edited", f"{times['lock']} 后我一步都没离开{locs[0]}。"),
            ], []),
            mem("char_01", 2, [
                (times["speech"], "said", "original", f"我在{locs[0]}发欢迎词。"),
                (times["crime"], "said", "edited", f"我去过一趟{locs[5]}，只是看看{obj}。"),
                (times["crime"], "heart", "original", f"（心声）我让{n2}按「{signal}」办。我自己只站在门口。"),
            ], [{"block": "blk_2", "change": f"否认离席→承认去过{locs[5]}", "tamper_point": "tp_c01"}]),
            mem("char_01", 3, [
                (times["crime"], "heart", "original", f"（心声）{obj}是我点的菜。再被翻出来，我就完了。"),
            ], []),
        ],
        "char_02": [
            mem("char_02", 1, [
                (times["lock"], "said", "edited", f"对不起我去{locs[2]}了，没进操作间。"),
                (times["back"], "said", "original", "后来我在走廊站着，不敢回工位。"),
            ], []),
            mem("char_02", 2, [
                (times["lock"], "said", "edited", "我……可能经过操作间门口。"),
                (times["crime"], "heart", "original", f"（心声）我按了{verb}。{leftover}是我留下的。"),
            ], [{"block": "blk_1", "change": "没进操作间→经过门口", "tamper_point": "tp_c02"}]),
            mem("char_02", 3, [
                (times["crime"], "heart", "original", f"（心声）暗号是「{signal}」。我想跳反，需要有人先接住我。"),
                (times["crime"], "said", "original", f"是我按的。{obj}是我动的。对不起。"),
            ], []),
        ],
        "char_03": [
            mem("char_03", 1, [
                (times["lock"], "said", "edited", f"我 {times['lock']} 就在{locs[2]}，什么都没看见。"),
            ], []),
            mem("char_03", 2, [
                (times["lock"], "said", "edited", "我好像看见过一个背影。"),
                (times["lock"], "heart", "original", f"（心声）其实我 {times['late']} 才到。气窗对着门口。"),
            ], [{"block": "blk_1", "change": "一直在→好像看见", "tamper_point": "tp_c03"}]),
            mem("char_03", 3, [
                (times["crime"], "heart", "original", f"（心声）有人往{locs[1]}塞盒子。{window}里灯不太对。"),
            ], []),
        ],
        "char_04": [
            mem("char_04", 1, [
                (times["lock"], "said", "edited", f"您好，{locs[0]}一切正常，{device}是例行流程。"),
                (times["late"], "said", "original", "后来门禁好像被风吹响了一下。"),
            ], []),
            mem("char_04", 2, [
                (times["lock"], "said", "original", "门禁有一次闪红，我记下来了。"),
                (times["lock"], "heart", "original", f"（心声）打印件在抽屉。我怕是{n1}。"),
            ], [{"block": "blk_1", "change": "没有任何异常→承认闪红", "tamper_point": "tp_c04"}]),
            mem("char_04", 3, [
                (times["gap_a"], "heart", "original", f"（心声）闪红的令牌编号和{verb}账号是同一组。{n4}不该再装风大。"),
            ], []),
        ],
    }


def posts(hook, names, obj, device, window, leftover, mood) -> list[dict]:
    n1, n2, n3 = names["char_01"], names["char_02"], names["char_03"]
    tag = "玩梗" if mood == "comedy" else ("耳语" if mood == "horror" else "对质")
    fake_tag = "一眼假但好笑" if mood == "comedy" else "一眼假"
    return [
        {"id": "post_001", "round": 1, "title": f"#{hook[:8]}#",
         "body": f"官方：{device}已落下，全员原地待命。{window}尚未回应。",
         "author_mask": "官方", "is_fake": False, "clue_ref": None,
         "topic_tag": "", "heat_delta": 6, "humor_tag": tag},
        {"id": "post_002", "round": 1, "title": f"#我朋友就在{obj[:4]}#",
         "body": f"我朋友的同学说那{window}大家在集体冥想。建议散了吧。",
         "author_mask": "水军", "is_fake": True, "clue_ref": None,
         "topic_tag": "kc_02", "heat_delta": 8, "humor_tag": fake_tag},
        {"id": "post_003", "round": 1, "title": f"#{n3}为什么不说话#",
         "body": f"什么都看见，什么都『我好像』。这届路过的人怎么了？",
         "author_mask": "网友", "is_fake": False, "clue_ref": "clue_006",
         "topic_tag": "kc_03", "heat_delta": 5, "humor_tag": "真线索伪装"},
        {"id": "post_004", "round": 2, "title": f"#{n2}背锅指南#",
         "body": f"转正前夜{obj}被动过，是勇气还是绩效？评论区已经宣判。",
         "author_mask": "水军", "is_fake": True, "clue_ref": None,
         "topic_tag": "kc_03", "heat_delta": 7, "humor_tag": fake_tag},
        {"id": "post_005", "round": 2, "title": f"#{device}不是风#",
         "body": f"值班的人说是风。风会刷内部令牌？{leftover}也会自己走路？",
         "author_mask": "网友", "is_fake": False, "clue_ref": "clue_009",
         "topic_tag": "kc_04", "heat_delta": 6, "humor_tag": "真线索伪装"},
        {"id": "post_006", "round": 2, "title": "#请给领导留面#",
         "body": "有记录也不该公布，和谐最重要。此帖一看就很官方。",
         "author_mask": "水军", "is_fake": True, "clue_ref": None,
         "topic_tag": "kc_04", "heat_delta": 5, "humor_tag": fake_tag},
        {"id": "post_007", "round": 2, "title": "#折叠区老人发言#",
         "body": f"倦怠不是你的错，但动{obj}是。先补给，再甩锅。{n1}今晚特别忙。",
         "author_mask": "网友", "is_fake": False, "clue_ref": None,
         "topic_tag": "kc_01", "heat_delta": 4, "humor_tag": tag},
        {"id": "post_008", "round": 3, "title": "#全员加班到心死#",
         "body": f"锁门第三小时，有人开始讨论下班是不是一种谣言。{window}还没被解释。",
         "author_mask": "水军", "is_fake": True, "clue_ref": None,
         "topic_tag": "kc_01", "heat_delta": 9, "humor_tag": fake_tag},
    ]


def timeline(names, locs, obj, verb, leftover, device, times) -> dict:
    return {
        "case_time": f"案发夜 {times['open']}-23:00；{times['lock']} 锁门，"
                     f"{times['gap_a']}-{times['gap_b']} {obj}空洞",
        "timeline": [
            {"time": times["open"], "character": "char_04", "location": locs[0],
             "action": "盘点加班广播，请全员到岗", "public": True},
            {"time": times["borrow"], "character": "char_02", "location": locs[3],
             "action": f"借走{obj}备份（说谎点：后称只是路过）", "public": False},
            {"time": times["speech"], "character": "char_01", "location": locs[0],
             "action": "当众喊话安抚，实则观察谁会听话", "public": True},
            {"time": times["lock"], "character": "char_04", "location": locs[0],
             "action": f"{device}点亮，大门封控", "public": True},
            {"time": times["leave"], "character": "char_01", "location": locs[5],
             "action": f"离席到操作口给执行者使眼色（说谎点：自称在{locs[0]}）", "public": False},
            {"time": times["crime"], "character": "char_02", "location": locs[5],
             "action": f"执行{verb}（说谎点：声称在{locs[2]}）", "public": False},
            {"time": times["crime"], "character": "char_03", "location": locs[2],
             "action": f"从气窗看见门口交接（说谎点：称 {times['lock']} 已在{locs[2]}）", "public": False},
            {"time": times["gap_a"], "character": "char_04", "location": locs[0],
             "action": "门禁闪红，记下编号后不敢公布", "public": False},
            {"time": times["back"], "character": "char_01", "location": locs[0],
             "action": "回到现场继续搅局", "public": True},
            {"time": times["late"], "character": "char_03", "location": locs[2],
             "action": "补打卡", "public": False},
            {"time": times["late"], "character": "char_02", "location": locs[2],
             "action": f"留下{leftover}与纸条", "public": False},
            {"time": times["fake"], "character": "char_01", "location": locs[5],
             "action": f"投放嫁祸{names['char_03']}的假证", "public": False},
        ],
        "rules": {"npc_statement_must_match": True},
    }


def acts(player_acts, pack, hook, obj, device, names, brief) -> dict:
    want = {a.get("id"): a for a in player_acts if isinstance(a, dict)}
    mods = brief.get("modules") or {}
    act3_brief = (
        "对质后提交证据卡指认。"
        if mods.get("hotfeed") is False
        else "舆论对质后提交证据卡指认。"
    )
    defaults = [
        {
            "id": "act1", "name": f"第一幕·{device}落下", "stage": "break_ice",
            "actions_allocated": 6,
            "brief": f"锁门开场。导火索：{hook[:24]}。先对话，再搜公开线索。",
            "info_budget": 4,
            "must_reveal": [f"{device}锁门", f"监控缺了一截"],
            "must_not_reveal": [f"主谋就是{names['char_01']}", f"{names['char_02']}按下操作"],
            "player_verbs": ["chat", "search"],
            "twist_beat": f"公开线索证明{device}来自楼内",
            "comedy_beat": "搜错地点只摸到过期零食",
            "oh_moment": "舆论冒出一眼假的辟谣",
            "dm_notes": "叮——只播报 fact，不点名真凶",
        },
        {
            "id": "act2", "name": f"第二幕·被改过的{obj}", "stage": "investigate",
            "actions_allocated": 9,
            "brief": "记忆修复与开导，said/heart 对质。",
            "info_budget": 5,
            "must_reveal": [f"{names['char_03']}打卡矛盾", f"{obj}备份被借走"],
            "must_not_reveal": [],
            "player_verbs": ["search", "memory_fix", "counsel"],
            "twist_beat": f"心声揭开{names['char_02']}被拿捏",
            "comedy_beat": f"{names['char_04']}官腔把自己绕进去",
            "oh_moment": "篡改点自动进证物袋",
            "dm_notes": "心声未解锁不得泄",
        },
        {
            "id": "act3", "name": "终局·指认", "stage": "accuse",
            "actions_allocated": 3,
            "brief": act3_brief,
            "info_budget": 2,
            "must_reveal": ["投放设备同源"],
            "must_not_reveal": [],
            "player_verbs": ["refute", "vote"],
            "twist_beat": "伪证与真设备指纹对撞",
            "comedy_beat": "群嘲错指",
            "oh_moment": "指认结算",
            "dm_notes": "只演不裁",
        },
    ]
    if (brief.get("vibe") or {}).get("dm"):
        for row in defaults:
            row["dm_notes"] = brief["vibe"]["dm"]
    out = []
    for row in defaults:
        w = want.get(row["id"]) or {}
        merged = dict(row)
        if w.get("name"):
            merged["name"] = w["name"]
        if w.get("brief"):
            merged["brief"] = w["brief"]
        if w.get("must_reveal"):
            merged["must_reveal"] = w["must_reveal"] if isinstance(w["must_reveal"], list) else [w["must_reveal"]]
        if w.get("must_not_reveal"):
            merged["must_not_reveal"] = (
                w["must_not_reveal"] if isinstance(w["must_not_reveal"], list) else [w["must_not_reveal"]]
            )
        if w.get("twist") or w.get("twist_beat"):
            merged["twist_beat"] = w.get("twist") or w.get("twist_beat")
        if w.get("comedy") or w.get("comedy_beat"):
            merged["comedy_beat"] = w.get("comedy") or w.get("comedy_beat")
        out.append(merged)
    return {"acts": out}
