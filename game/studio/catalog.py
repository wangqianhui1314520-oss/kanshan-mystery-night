"""本型 / 机制 / 阵营目录。工作台与案情工厂共用，不写圣经。"""

from __future__ import annotations

CAST_IDS = ("char_01", "char_02", "char_03", "char_04")
ACT_IDS = ("act1", "act2", "act3")
MINI_IDS = ("runner", "heart", "refute3", "badge")
PACK_TYPES = (
    "fun_mech", "hard_logic", "faction", "emotion", "horror", "variety", "immerse",
)
VIBE_MOODS = ("comedy", "horror", "variety", "grim")

TYPE_META = {
    "fun_mech": {"genre": "欢乐机制推理 · 快本", "tone": "欢乐外壳 + 信息操纵"},
    "hard_logic": {"genre": "硬核推理 · 快本", "tone": "冷硬推理"},
    "faction": {"genre": "阵营对抗 · 快本", "tone": "阵营拉扯"},
    "emotion": {"genre": "情感推理 · 快本", "tone": "克制伤感"},
    "horror": {"genre": "恐怖推理 · 快本", "tone": "封闭空间恐怖"},
    "variety": {"genre": "综艺机制推理 · 快本", "tone": "综艺外壳"},
    "immerse": {"genre": "沉浸推理 · 快本", "tone": "沉浸封闭"},
}

DEFAULT_MODULES = {
    "hotfeed": True,
    "memory": True,
    "counsel": True,
    "kcards": True,
    "inner_boss": False,
    "comedy_search": True,
    "bet": True,
    "headline": True,
    "stealth": True,
    "puzzle": True,
    "antifraud": True,
    "evidence": True,
    "pollution": True,
}

DEFAULT_CAMP = {
    "pollution": "污染",
    "swayable": "可策反",
    "truth": "求真",
    "public": False,
    "win_pollution": "",
    "win_truth": "",
}
