"""空席出手顺序：轮转取本波角色。只排座，不含裁决。"""
from __future__ import annotations


def rotate_roles(roles: list[str], cursor: int, n: int = 3) -> tuple[list[str], int]:
    """从 cursor 起取至多 n 个（不超过空席数）；新 cursor = (start + 取出数) % len。"""
    bag = [str(r) for r in (roles or []) if r]
    if not bag:
        return [], 0
    start = int(cursor or 0) % len(bag)
    take = max(0, min(int(n or 0), len(bag)))
    picked = [bag[(start + i) % len(bag)] for i in range(take)]
    nxt = (start + take) % len(bag)
    return picked, nxt
