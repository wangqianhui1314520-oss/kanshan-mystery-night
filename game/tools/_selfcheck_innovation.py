"""活体自检：P0 茧房/图钉/策反 是否已从契约外动作收进 skill。

用法（game/ 目录，服务需已起）：
    python tools/_selfcheck_innovation.py
默认打 127.0.0.1:8900。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8900"
RESULTS: list[tuple[str, bool, str]] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))


def req(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=12) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"detail": raw}


def evs(j: dict, name: str) -> list:
    return [e for e in (j.get("events") or [])
            if (e.get("payload") or {}).get("event") == name]


def act(sid: str, typ: str, payload=None, actor="player:1"):
    return req("POST", f"/api/session/{sid}/action",
               {"type": typ, "actor": actor, "payload": payload or {}})


def main() -> int:
    st, h = req("GET", "/api/health")
    rec("health", st == 200, str((h.get("engine") or {}).get("mode") or h.get("status")))

    st, s = req("POST", "/api/session", {"mode": "main", "player_id": "player:1"})
    sid = (s.get("session") or {}).get("session_id")
    rec("create session", st == 200 and s.get("ok") and bool(sid),
        f"{(s.get('session') or {}).get('engine')} {sid}")
    if not sid:
        return 1

    st, raw = act(sid, "evidence_pin", {"clueId": "clue_001"})
    rec("raw evidence_pin 仍被契约拒", st == 400 and "未支持" in str(raw.get("detail", "")),
        str(raw.get("detail", ""))[:80])

    st, ice = act(sid, "skill", {"kind": "evidence_pin", "clueId": "clue_001"})
    ice_ev = ((ice.get("events") or [{}])[0].get("payload") or {})
    rec("破冰未持有线索 → pin_rejected（不是 locked）",
        st == 200 and ice_ev.get("event") == "pin_rejected",
        f"{ice_ev.get('event')} {ice_ev.get('notice')}")

    st, cb0 = act(sid, "skill", {"kind": "cocoon_break"})
    cbe = ((cb0.get("events") or [{}])[0].get("payload") or {})
    rec("入茧前破茧 → cocoon_rejected",
        st == 200 and cbe.get("event") == "cocoon_rejected",
        f"{cbe.get('event')} {cbe.get('notice')}")

    stage = ""
    for _ in range(8):
        _, a = act(sid, "advance")
        stage = (a.get("session") or {}).get("stage", "")
        if stage in ("investigate", "round_table", "accuse"):
            break
    rec("advance → investigate", stage in ("investigate", "round_table", "accuse"), stage)

    st, miss = act(sid, "skill", {"kind": "evidence_pin", "clueId": "clue_999"})
    rec("未知线索 pin_rejected", st == 200 and bool(evs(miss, "pin_rejected")))

    st, def0 = act(sid, "skill", {"kind": "defect", "charId": "char_03"})
    rec("覆盖不足 defect_rejected", st == 200 and bool(evs(def0, "defect_rejected")),
        ((evs(def0, "defect_rejected") or [{}])[0].get("payload") or {}).get("notice", "")[:80])

    st, sr = act(sid, "search", {"location": "loc_reception", "keyword": "横幅"})
    gained = [e for e in (sr.get("events") or []) if e.get("type") == "clue_gained"]
    rec("搜证 loc_reception/横幅 发线索", st == 200 and bool(gained),
        ",".join(e["payload"].get("clue_id", "") for e in gained))
    cid = gained[0]["payload"]["clue_id"] if gained else "clue_001"
    rec("clue_gained 带 tags", bool(gained and gained[0]["payload"].get("tags")),
        str((gained[0]["payload"].get("tags") if gained else None)))

    st, pin = act(sid, "skill", {"kind": "evidence_pin", "clueId": cid})
    pe = evs(pin, "evidence_pin")
    rec("kind=evidence_pin 持有线索成功", st == 200 and bool(pe),
        json.dumps((pe[0]["payload"] if pe else {}), ensure_ascii=False)[:120])
    links = (pin.get("session") or {}).get("evidence_links") or []
    rec("session.evidence_links 落档",
        any((l.get("clue_id") or l.get("clueId")) == cid for l in links),
        str(links)[:120])

    st, pin2 = act(sid, "skill", {"skill": "evidence_pin", "clueId": cid})
    rec("重复钉入 pin_rejected", st == 200 and bool(evs(pin2, "pin_rejected")))

    for loc, kw in (("loc_desk", "请假"), ("loc_hotfeed", "热搜"), ("loc_archive", "经费")):
        act(sid, "search", {"location": loc, "keyword": kw})
    for cid2 in ("clue_001", "clue_002", "clue_005", "clue_007"):
        act(sid, "skill", {"skill": "evidence_pin", "clueId": cid2})
    st, def1 = act(sid, "skill", {"kind": "defect", "charId": "char_03"})
    d_ok, d_no = evs(def1, "defect"), evs(def1, "defect_rejected")
    rec("钉入后策反有明确裁决", st == 200 and (bool(d_ok) or bool(d_no)),
        "flipped" if d_ok else ((d_no[0]["payload"].get("notice") if d_no else "none")[:100]))

    st, po = act(sid, "skill", {"kind": "pollution_open"})
    rec("kind=pollution_open 仍可用",
        st == 200 and bool(evs(po, "pollution_case") or evs(po, "pollution_done") or evs(po, "locked")),
        ((po.get("events") or [{}])[0].get("payload") or {}).get("event", ""))

    st2, s2 = req("POST", "/api/session", {"mode": "main", "player_id": "player:1"})
    sid2 = (s2.get("session") or {}).get("session_id")
    rec("评委线会话", bool(sid2), sid2 or "")
    if sid2:
        st, jl = act(sid2, "skill", {"kind": "judge_line"})
        ready = evs(jl, "judge_line_ready")
        cov = ((ready[0].get("payload") or {}).get("coverage") or {}) if ready else {}
        rec("破冰 judge_line 覆盖≥50%",
            st == 200 and bool(ready) and int(cov.get("pct") or 0) >= 50,
            f"pct={cov.get('pct')} stage={(jl.get('session') or {}).get('stage')}")
        rec("评委线 session.evidence_links",
            len((jl.get("session") or {}).get("evidence_links") or []) >= 3)
        st, djl = act(sid2, "skill", {"kind": "defect", "charId": "char_03"})
        rec("评委线后可策反", st == 200 and bool(evs(djl, "defect")),
            ((djl.get("events") or [{}])[0].get("payload") or {}).get("event", ""))

    fail = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"=== LIVE {len(RESULTS) - fail} PASS / {fail} FAIL ===")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
