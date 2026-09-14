"""python -m studio --seed \"...\" """

from __future__ import annotations

import argparse
import json
import sys

from .pipeline import generate
from .tiers import PRESET_SEEDS


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="一句话生成剧本杀快本")
    p.add_argument("--seed", default=PRESET_SEEDS[0])
    p.add_argument("--tier", default="demo")
    p.add_argument("--llm", action="store_true")
    args = p.parse_args(argv)
    job = generate(args.seed, tier=args.tier, use_llm=args.llm)
    print(json.dumps({
        "id": job["id"],
        "status": job["status"],
        "provider": job["provider"],
        "gate": job["gate"],
        "title": job["world"].get("title"),
    }, ensure_ascii=False, indent=2))
    return 0 if job["gate"]["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
