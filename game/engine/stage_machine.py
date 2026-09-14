"""阶段状态机：控制剧本杀的阶段流转。

阶段顺序（GAME_DESIGN.md 定义）：
  break_ice(破冰) → investigate(搜证) → round_table(圆桌) → accuse(指认) → review(复盘)

规则：每个阶段有可用动作类型与行动力配额，AI 无权跳过阶段。

V3 升级（docs/CONTRACTS.md / docs/STORY_ADAPTATION.md 第一幕 / docs/GAME_DESIGN_V3.md）：
- 幕内轮循环：investigate ↔ round_table 按轮推进（begin_round / end_round），
  每轮 3 行动点（V3 §3.2）；幕轮数用尽经 advance() 进入下一幕（acts 数组驱动）；
- 系统提示音事件：引擎确定性拼接「叮——第 N 轮搜证开始，剩余行动点 3」播报，
  不调 AI（system_events 返回 WS 事件结构，type=system，actor=dm）；
- 【已打码】彩蛋横幅（玩家吐槽触发）与横幅抽风（错误惩罚，固定池轮转）。

旧骨架签名与语义保留：Stage 枚举 / can / consume_action / advance。
"""
from enum import Enum


class Stage(str, Enum):
    BREAK_ICE = "break_ice"
    INVESTIGATE = "investigate"
    ROUND_TABLE = "round_table"
    ACCUSE = "accuse"
    REVIEW = "review"


# 每轮行动点（V3 §3.2：每轮 3 行动点）
ACTIONS_PER_ROUND = 3

# 各阶段允许的动作（契约动作集：search/chat/skill/counsel/vote/advance；
# 旧动作 introduce / private_chat / reveal_clue / accuse / review 保留兼容）
_STAGE_ACTIONS = {
    Stage.BREAK_ICE: {"chat", "introduce", "advance"},
    Stage.INVESTIGATE: {"chat", "search", "private_chat", "skill", "counsel", "advance"},
    Stage.ROUND_TABLE: {"chat", "reveal_clue", "private_chat", "skill", "counsel", "vote", "advance"},
    Stage.ACCUSE: {"accuse", "vote", "advance"},
    Stage.REVIEW: {"review"},
}


def _coerce_stage(stage) -> Stage | None:
    """Stage 枚举或同名 str → Stage；无法识别则 None。"""
    if isinstance(stage, Stage):
        return stage
    try:
        return Stage(stage)
    except (ValueError, TypeError):
        return None


def legal_actions(stage) -> frozenset[str]:
    """该阶段可用动作（与 _STAGE_ACTIONS 同一张表）。未知阶段仅 chat。"""
    key = _coerce_stage(stage)
    if key is None:
        return frozenset({"chat"})
    return frozenset(_STAGE_ACTIONS.get(key, {"chat"}))


def action_allowed(stage, action: str) -> bool:
    """动作是否在该阶段合法（走 legal_actions / _STAGE_ACTIONS）。"""
    return action in legal_actions(stage)

# 玩家吐槽触发【已打码】的词表（确定性匹配，欢乐向）
_BAKE_WORDS = ("垃圾", "智障", "弱智", "什么破", "破系统", " server 崩了")

# 横幅抽风错误惩罚池（STORY_ADAPTATION 第一幕欢乐点，固定池轮转）
# P1 系统抽风事件升级：每条横幅携带确定性 effect（ap_free=本次行动免扣 / heat_bump=话题加热）
_GLITCH_BANNERS = [
    "【惩罚：围观鱼干一分钟】",
    "【惩罚：大声朗读用户协议第 7 条】",
    "【惩罚：给手机充 1% 电并盯着看】",
    "【惩罚：把桌面图标按名称排列】",
]
_GLITCH_EFFECTS = [{"kind": "ap_free", "value": 1}, {"kind": "heat_bump", "value": 3},
                   {"kind": "none", "value": 0}]


class StageMachine:
    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.stage = Stage.BREAK_ICE
        self.actions_left = scenario["acts"][0]["actions_allocated"]
        self._index = 0
        # ---- V3 新增状态 ----
        self.session_id = ""                     # 事件回填，由 F 服务端注入
        self._round = 0                          # 全局轮次
        self._act_round = 0                      # 当前幕内已打完的轮数
        self._max_rounds = int(scenario.get("rounds_per_act", 2))
        self._events: list[dict] = []            # 待取系统事件队列
        self._glitch_i = 0                       # 抽风横幅轮转指针
        self._glitch_ap_bonus = 0                # 抽风 ap_free 效果累积（免扣次数）

    # ------------------------------------------------------------- 旧骨架 API
    def can(self, action: str) -> bool:
        """检查当前阶段是否允许某动作类型。"""
        return action in _STAGE_ACTIONS[self.stage]

    def consume_action(self) -> bool:
        """消耗 1 点行动力，耗尽则强制推进阶段。

        P1 抽风事件扩展：系统抽风打出的 ap_free 效果 → 本次行动免扣（「错误惩罚」
        被 DM 当场重写成福利，actions_left 不变）。"""
        if self._glitch_ap_bonus > 0:
            self._glitch_ap_bonus -= 1
            return True
        if self.actions_left <= 0:
            self.advance()
            return False
        self.actions_left -= 1
        return True

    def advance(self) -> Stage:
        """推进到下一阶段（条件满足时），返回新阶段。

        已处于最后一幕时幂等：不重复推进、不重置行动点（对旧骨架循环重置行为的修复）。
        """
        if self._index >= len(self.scenario["acts"]) - 1:
            return self.stage
        self._index = min(self._index + 1, len(self.scenario["acts"]) - 1)
        act = self.scenario["acts"][self._index]
        self.stage = Stage(act["stage"])
        self.actions_left = act["actions_allocated"]
        self._act_round = 0
        return self.stage

    # ------------------------------------------------------------- V3 轮循环
    def round_no(self) -> int:
        """当前全局轮次（第几轮）。"""
        return self._round

    def current_act_no(self) -> int:
        """当前幕序（1 起；只读，不改既有签名）。

        供 driver 幕门控/转场/收集品（契约 §3.5c collect_flow act_no 缺省口径）
        复用，避免上层直接触 _index 私有字段。"""
        return self._index + 1

    def begin_round(self) -> dict:
        """开启新一轮：轮次 +1、重置每轮行动点（3），产出系统提示音播报事件（并入队）。"""
        self._round += 1
        self.actions_left = ACTIONS_PER_ROUND
        event = self._system_event(
            text=f"叮——第 {self._round} 轮搜证开始，剩余行动点 {ACTIONS_PER_ROUND}",
            kind="round_start", stage=self.stage.value)
        self._events.append(event)
        return event

    def end_round(self) -> Stage:
        """结束本轮：investigate → round_table（幕内切换）；
        round_table → 幕轮数 +1，轮数未满回 investigate，已满 advance() 进下一幕。"""
        if self.stage == Stage.INVESTIGATE:
            self.stage = Stage.ROUND_TABLE
        elif self.stage == Stage.ROUND_TABLE:
            self._act_round += 1
            if self._act_round < self._max_rounds:
                self.stage = Stage.INVESTIGATE
            else:
                self.advance()
        return self.stage

    # --------------------------------------------------------- 系统提示音事件
    def _system_event(self, text: str, kind: str, stage: str = "") -> dict:
        return {"type": "system", "session_id": self.session_id,
                "round": self._round, "actor": "dm",
                "payload": {"text": text, "kind": kind, "stage": stage}}

    def push_event(self, text: str, kind: str = "notice") -> dict:
        """追加一条系统提示音事件（横幅 / 播报），返回该事件。"""
        ev = self._system_event(text=text, kind=kind, stage=self.stage.value)
        self._events.append(ev)
        return ev

    def system_events(self) -> list[dict]:
        """取走全部待发送系统事件（取后清空，WS 事件协议结构）。"""
        evs, self._events = self._events, []
        return evs

    def bake_check(self, text: str) -> dict | None:
        """玩家吐槽检测：命中词表 → 产出【已打码】彩蛋横幅事件，否则 None。"""
        for w in _BAKE_WORDS:
            if w in text:
                return self.push_event(f"【已打码】{text}", kind="gagged")
        return None

    def banner_glitch(self) -> dict:
        """横幅抽风（P1 系统抽风事件）：固定池轮转输出错误惩罚横幅（DM 当场重写的梗），
        并附带确定性 effect：ap_free（下一次行动免扣，引擎自动生效）/
        heat_bump（话题加热数值，由上层应用到 OpinionFeed）。"""
        banner = _GLITCH_BANNERS[self._glitch_i % len(_GLITCH_BANNERS)]
        effect = dict(_GLITCH_EFFECTS[self._glitch_i % len(_GLITCH_EFFECTS)])
        self._glitch_i += 1
        if effect["kind"] == "ap_free":
            self._glitch_ap_bonus += int(effect["value"])
        return self.push_event(banner, kind="glitch") | {"effect": effect}
