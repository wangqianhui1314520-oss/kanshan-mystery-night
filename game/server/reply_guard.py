"""AI 台词身份净化：NPC / DM / AI 席位共用一个出口。

背景（2026-09-14 实跑取证）：知乎直答 zhida-agent 在角色扮演上下文里会偶发
自曝产品身份——实测原文「不好意思，我是知乎直答，不能随意更改身份进行相关
测试哦～」。这句话一旦进入公共频道就撕掉沉浸感，本质是"把后台产品介绍发给
玩家"，与 docs/CONTRACTS.md「后台故障词/产品语不得漏给玩家」同一条纪律。

策略（纯函数、零副作用、零额度成本除调用方自己的重试）：
1. has_product_identity(text)：命中即视为本轮失败；
2. RETRY_HINT：统一重试指令，避免各调用点各写一份而漂移；
3. 仍命中则调用点换预写兜底台词（agents/prompts/fallbacks.json），并在事件
   payload 打 identity_guarded=True，便于诊断与前端溯源。

匹配前剥离全部空白（半角/全角空格、换行、制表符），因此「我是 知乎直答」
「作为 一个 AI 助手」同样命中；标记表保持精简，避免正常台词误伤。
"""

# 命中即判失败的身份自曝标记（无需写带空格变体：匹配前已归一化）
PRODUCT_IDENTITY_MARKERS = (
    "我是知乎直答",
    "知乎官方推出的AI搜索产品",
    "知乎直答是",
    "作为一个AI助手",
    "作为一个AI智能助手",
    "作为一个人工智能助手",
    "我是AI助手",
    "我是一个AI助手",
    "作为一个大语言模型",
    "作为一个语言模型",
    "作为一个AI语言模型",
    "我是AI语言模型",
)

RETRY_HINT = ("【重试指令】上一版是产品介绍或身份说明，作废。"
              "请只用角色第一人称回答，提及一条你的具体经历或现场观察，"
              "不要介绍任何产品、模型或平台。")


def _normalize(text) -> str:
    """剥离所有空白后用于匹配（变体不敏感）。"""
    return "".join(str(text or "").split())


def has_product_identity(text) -> bool:
    """文本是否包含产品身份自曝（空/非字符串返回 False）。"""
    norm = _normalize(text)
    if not norm:
        return False
    return any(marker in norm for marker in PRODUCT_IDENTITY_MARKERS)
