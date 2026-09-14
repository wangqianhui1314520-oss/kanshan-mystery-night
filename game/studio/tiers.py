"""快本配额。P0 只认 demo。"""

from __future__ import annotations

TIERS = ("demo",)

DEMO = {
    "chars": 4,
    "locations": 6,
    "clues": 12,
    "public": 6,
    "limited": 3,
    "hidden": 2,
    "fake": 1,
    "truth_nodes": 6,
    "proof_min": 2,
    "acts": 3,
    "hotfeed": 8,
    "fake_posts_min": 4,
    "kc": 5,
    "memory_files": 12,
    "pollution": 1,
    "swayable_min": 1,
}

QUOTA = {"demo": DEMO}

LOCATION_IDS = (
    "loc_reception",
    "loc_server",
    "loc_teahouse",
    "loc_archive",
    "loc_monitor",
    "loc_hotfeed",
)

LOCATION_META = {
    "loc_reception": {
        "name": "前台",
        "type": "base",
        "image": "assets/images/scene_reception.png",
        "pos": {"x": 50, "y": 87},
        "keywords": ["门禁", "横幅", "值班"],
    },
    "loc_server": {
        "name": "服务器机房",
        "type": "crime_scene",
        "image": "assets/images/scene_server.png",
        "pos": {"x": 46, "y": 33},
        "keywords": ["日志", "风扇", "删除"],
    },
    "loc_teahouse": {
        "name": "茶水间",
        "type": "base",
        "image": "assets/images/scene_teahouse.png",
        "pos": {"x": 11, "y": 57},
        "keywords": ["打卡", "奶茶", "纸条"],
    },
    "loc_archive": {
        "name": "档案室",
        "type": "crime_scene",
        "image": "assets/images/scene_archive.png",
        "pos": {"x": 68, "y": 29},
        "keywords": ["借阅", "芯片", "手稿"],
    },
    "loc_monitor": {
        "name": "监控室",
        "type": "crime_scene",
        "image": "assets/images/scene_monitor.png",
        "pos": {"x": 18, "y": 35},
        "keywords": ["监控", "空洞", "人影"],
    },
    "loc_hotfeed": {
        "name": "热搜后台",
        "type": "crime_scene",
        "image": "assets/images/scene_hotfeed.png",
        "pos": {"x": 86, "y": 43},
        "keywords": ["话题", "投放", "设备"],
    },
}

KC_COPY = (
    ("kc_02", "char_01"),
    ("kc_03", "char_02"),
    ("kc_01", "char_03"),
    ("kc_04", "char_04"),
    ("kc_09", "team_all"),
)

CHAR_AVATARS = {
    "char_01": "assets/images/char_liuliangjiang.png",
    "char_02": "assets/images/char_lurenjia.png",
    "char_03": "assets/images/char_chendijun.png",
    "char_04": "assets/images/char_yanzhijun.png",
}

DM_AVATAR = "assets/images/dm_kanshan_holo.png"

PRESET_SEEDS = (
    "全员被锁在 24 小时热榜机房里，热搜日志缺了七分钟",
    "盐言房间出不去，横幅写着不出真相不出此门",
)
