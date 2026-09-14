# 成就文案库（侦探报告徽章 · MEGA_MODE §三 / resolver.achievements() 七枚举对齐 v2）

> 引擎对接：`engine/achievements.py` AchievementEngine 直接加载本文件（md 表格提取横幅文案+分享卡一句话，```json 围栏提取判定 DSL）。
> ★核心七枚 = resolver `achievements()` 枚举（MEGA §三：看山还是山/心晴医师/带节奏之王/鱼干守护者/防折叠斗士 + 暗房大师/全场公敌）；扩展 17 枚为行为彩蛋。
> 硬规则：成就不泄底——解锁文案不得出现「看山设局/系统音=看山」等里层真相（终极层相关文案仅在对应结局解锁后可见）。
> 稀有度：铜 <15% / 银 <40% / 金 <70% / 彩蛋（按行为触发，不入胜率统计）。
> v2 变更（A/C 周知）：①新增核心枚举「暗房大师」「全场公敌」；②原「群嘲免死金牌」并入「全场公敌」（判定类型不变，id 由 ach_mianyipai 改为 ach_gongdi）；③「暗房大师」引入新 DSL type=stealth_photo_clean——按 engine STATUS §七.4，新 type 需回 A 广播后扩展求值器，扩展前该成就恒 False 静默。

## 一、核心七枚（标题 + 描述，各 ≤50 字）

1. **看山还是山**——山没动，动的是局：指认 DM 成功，把设局者从幕后认了出来。
2. **心晴医师**——开导 4 人成功，档案局今夜全员心晴，挂号处提前关门。
3. **带节奏之王**——把热度带偏到终局并赢下污染胜利，热搜都是你家的。
4. **鱼干守护者**——34 条线索一条不漏全收集，连鱼干罐便签都读了三遍。
5. **防折叠斗士**——听完沉底君三段完整陈述，一次都没打断过他。
6. **暗房大师**——暗拍 3 次且无一张照片被当场拆穿，黑屋取证之神。
7. **全场公敌**——被"最想锤"投票 ≥4 次仍活着到终局，把锤子都焐热了。

## 二、引擎同步总表（AchievementEngine 加载源；列结构与 v1 一致，勿改表头）

| id | 成就 | 稀有度 | 达成条件（引擎可判） | 解锁横幅文案 | 分享卡一句话 |
|---|---|---|---|---|---|
| ach_zhenshan | 看山还是山 | gold | 指认 DM 成功（破绽≥5，结局=终极·看山还是山） | 「山没动，动的是局。你把设局的人从局里认了出来。」 | 本局最大彩蛋：这一局的"局"，被我看穿了。 |
| ach_xinqing | 心晴医师 | silver | 知识开导成功 ≥4 人（结局含全员心晴加成） | 「开导 4 人，档案局今天全员心晴。挂号处已关门。」 | 我不是在破案，我是在出诊。 |
| ach_jiezou | 带节奏之王 | silver | 污染阵营胜利（热度带偏至终局） | 「热搜都是你家的。真相没赢，但你赢了——用的方式不太对。」 | 47 个号，一含热量。 |
| ach_yugan | 鱼干守护者 | gold | 全线索收集（34/34，含伪造与破绽） | 「一条线索都没漏，连鱼干罐上的便签都读了三遍。看山很欣慰。」 | 档案局第一收纳师，在线取证。 |
| ach_fangzhe | 防折叠斗士 | bronze | 全程听完沉底君 3 段完整陈述（未被任何打断/跳过） | 「你听完了一个折叠区怨灵的全部发言。他明天想去交新朋友。」 | 有人说：倾听，是最便宜的搜证。 |
| ach_anfang | 暗房大师 | silver | 暗拍 ≥3 次且 share_photo 声称无一被当场拆穿 | 「黑屋里练出的手，照片比证词还稳。」 | 暗房不养闲人，只养真相。 |
| ach_gongdi | 全场公敌 | bronze | 被"最想锤的人"投票 ≥4 次且存活至终局 | 「全场都想锤你，你把锤子接住还了回去。」 | 被锤是流量，活着是胜利。 |
| ach_yanjia | 一眼假鉴定师 | silver | 当场识破 ≥3 条伪造线索（fake_of 对质成功） | 「P 图师傅连夜跑路。你的眼睛就是反诈 APP。」 | 假的，太假了，假到我笑了。 |
| ach_xianwen | 先问是不是 | silver | 对知之者完成一次证伪对质并获胜 | 「先问是不是——是不是？是。恭喜，你学会了知之者的起手式。」 | 用魔法打败魔法。 |
| ach_jinju | 金句复读机 | bronze | 单场开导收尾金句被弹幕复读 ≥3 次 | 「这句话现在归弹幕所有了。」 | 说出金句的人，先被金句淹没。 |
| ach_dingzi | 时间线钉子户 | silver | 记忆拼图对质：全场投票排出正确时间线（P2） | 「你把 8 个人的深夜钉回了 20:00-23:00，一颗钉子都没歪。」 | 时间线整理师，接单中。 |
| ach_shuangka | 双卡连开 | egg | 对知之者先后用 kc_07 与 kc_08 均开导成功 | 「两张卡，两次破防。弹幕：连开两枪，弹无虚发。」 | 万事通也要目标，也要小胜。 |
| ach_moyu | 摸鱼大师 | bronze | 同一地点连续 3 次搜证只得环境线索 | 「茶水间的泡面都替你数着呢。摸鱼是摸鱼，别耽误破案。」 | 摸鱼一时爽，复盘火葬场。 |
| ach_juzhongju | 局中局目击者 | gold | 集齐 5 个 boss_flaw（flavor_1..5） | 「五处破绽，一场局中局。你已经站在幕后幕布的边上。」 | 我看见的不是真相，是看真相的人。 |
| ach_huanxingci | 唤醒词侦探 | egg | 在对话框试出『看山，关门』（flavor_4） | 「你对系统说关门，系统差点答应。谁教的它这么没礼貌？」 | 我对所有门都说请，除了这扇。 |
| ach_zhijian | 热搜质检员 | silver | 辟谣成功 ≥3 次且全程零失败 | 「每一条谣言都被你按了退货。热搜已恢复出厂设置。」 | 没知识不敢辟谣，有知识辟谣上瘾。 |
| ach_fanzha | 反诈先锋 | bronze | 反诈小剧场三幕全对（P2） | 「三幕骗局全拆穿。国家反诈中心发来贺电（bushi）。」 | 识骗话术，全在档案局练的。 |
| ach_kuaidan | 快问快答满分 | bronze | 快问快答 10/10（P2） | 「10 题全对。你以为你在玩剧本杀，其实你在期末考。」 | 谁还不是个求真学霸。 |
| ach_chenci | 最后的陈词人 | bronze | 终局陈词（P2）弹幕"最想锤的人"投票第一且最终自证清白 | 「全场都想锤你，你把锤子接住还了回去。」 | 被锤是流量，自证是本事。 |
| ach_yuganxianren | 鱼干线人 | egg | 集齐 3 处鱼干收集品（P3 寻物支线） | 「三袋鱼干归位。看山Bot 的语气突然温柔了 0.3 度。」 | 有些线索不为破案，为交朋友。 |
| ach_daqidai | 全员心晴 | gold | 达成隐藏结局「全员心晴」 | 「门自己开了。他叼着鱼干回来了——这局最温柔的结局。」 | 破案最高境界：把人治好。 |
| ach_di7zhang | 被删的第 7 章 | gold | 达成隐藏结局「被删的第 7 章」（5 碎片+boss_key） | 「折叠解除。第 7 章重新上架，标题：所有悬案，都始于一句没人较真的谣言。」 | 我帮一个折叠区的人，赢回了他的第 7 章。 |
| ach_dalitang | 空调已修好 | egg | 在空调机房搜出『二十年前的大力丸』环境彩蛋 | 「大力丸没有效，但空调冷得很有诚意。」 | 有些发现不为真相，为快乐。 |
| ach_xinsheng | 偷听心声不犯法 | bronze | 单局解锁心声层 ≥5 次 | 「你们的嘴是加密的，心是明文的。本系统已阅（不告诉别人）。」 | 偷听心声一时爽，一直偷听一直爽。 |

## 三、判定 DSL（AchievementEngine 围栏源；v2 共 24 条）

```json
[
  {"id": "ach_zhenshan", "name": "看山还是山", "rarity": "gold", "condition": {"type": "ending", "value": "ending_kanshan"}},
  {"id": "ach_xinqing", "name": "心晴医师", "rarity": "silver", "condition": {"type": "counsel_count", "op": ">=", "value": 4}},
  {"id": "ach_jiezou", "name": "带节奏之王", "rarity": "silver", "condition": {"type": "ending", "value": "ending_pollution"}},
  {"id": "ach_yugan", "name": "鱼干守护者", "rarity": "gold", "condition": {"type": "clue_collected", "op": ">=", "value": 34}},
  {"id": "ach_fangzhe", "name": "防折叠斗士", "rarity": "bronze", "condition": {"type": "listen_full", "target": "char_06", "op": ">=", "value": 3}},
  {"id": "ach_anfang", "name": "暗房大师", "rarity": "silver", "condition": {"type": "stealth_photo_clean", "op": ">=", "value": 3}},
  {"id": "ach_gongdi", "name": "全场公敌", "rarity": "bronze", "condition": {"type": "hammered_votes", "op": ">=", "value": 4}},
  {"id": "ach_yanjia", "name": "一眼假鉴定师", "rarity": "silver", "condition": {"type": "fake_exposed", "op": ">=", "value": 3}},
  {"id": "ach_xianwen", "name": "先问是不是", "rarity": "silver", "condition": {"type": "confrontation_win", "target": "char_01"}},
  {"id": "ach_jinju", "name": "金句复读机", "rarity": "bronze", "condition": {"type": "danmaku_echo", "op": ">=", "value": 3}},
  {"id": "ach_dingzi", "name": "时间线钉子户", "rarity": "silver", "condition": {"type": "memory_puzzle_win"}},
  {"id": "ach_shuangka", "name": "双卡连开", "rarity": "egg", "condition": {"type": "counsel_multi", "target": "char_01", "cards": ["kc_07", "kc_08"]}},
  {"id": "ach_moyu", "name": "摸鱼大师", "rarity": "bronze", "condition": {"type": "same_location_dry_streak", "op": ">=", "value": 3}},
  {"id": "ach_juzhongju", "name": "局中局目击者", "rarity": "gold", "condition": {"type": "boss_flaw_count", "op": ">=", "value": 5}},
  {"id": "ach_huanxingci", "name": "唤醒词侦探", "rarity": "egg", "condition": {"type": "chat_keyword", "value": "看山，关门"}},
  {"id": "ach_zhijian", "name": "热搜质检员", "rarity": "silver", "condition": {"type": "refute_success_streak", "op": ">=", "value": 3}},
  {"id": "ach_fanzha", "name": "反诈先锋", "rarity": "bronze", "condition": {"type": "antifraud_all_correct"}},
  {"id": "ach_kuaidan", "name": "快问快答满分", "rarity": "bronze", "condition": {"type": "quiz_score", "op": "==", "value": 10}},
  {"id": "ach_chenci", "name": "最后的陈词人", "rarity": "bronze", "condition": {"type": "closing_vote_top1_survived"}},
  {"id": "ach_yuganxianren", "name": "鱼干线人", "rarity": "egg", "condition": {"type": "collectible", "op": "==", "value": 3}},
  {"id": "ach_daqidai", "name": "全员心晴", "rarity": "gold", "condition": {"type": "ending", "value": "ending_sunny"}},
  {"id": "ach_di7zhang", "name": "被删的第 7 章", "rarity": "gold", "condition": {"type": "ending", "value": "ending_chapter7"}},
  {"id": "ach_dalitang", "name": "空调已修好", "rarity": "egg", "condition": {"type": "env_clue", "value": "二十年前的大力丸"}},
  {"id": "ach_xinsheng", "name": "偷听心声不犯法", "rarity": "bronze", "condition": {"type": "heart_unlock_count", "op": ">=", "value": 5}}
]
```

> DSL 变更注记：`stealth_photo_clean` 为新增 type（数据源：evidence_chain 暗拍/照片对质记录），**需回 A 广播扩展求值器后生效**（engine STATUS §七.4）；`hammered_votes` 为既有外部 record type（party.py hammer_result），无引擎改动。其余 22 条与 v1 完全一致（引擎已实测的 12 自判 + 3 record 项 id/name 均未变动）。
> 判定演出（C 组）：解锁瞬间 AI 生成一句个性化锐评（横幅文案 + 玩家 headline 花名，见 minis.md 侦探花名池）；报告页徽章墙按稀有度排序；成就数据进 session_store 跨局统计（本地）。
