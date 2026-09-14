#!/usr/bin/env python3
"""宣传片剪辑合成：片头 + 单人 + 联机(PiP 双视角) + 生产工作台 + 片尾。

输入：game/data/_promo/{solo,party_host,party_guest,studio}.webm
输出：D:/Vibe coding/知乎黑客松/游戏宣传片.mp4（+ docs 副本）
"""
from __future__ import annotations

import subprocess
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
ROOT = GAME.parent
OUT = GAME / "data" / "_promo"
FFMPEG = "C:/ProgramData/chocolatey/bin/ffmpeg.exe"
FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe.exe"
W, H = 1920, 1080

TITLE_D = 5.0     # 片头
SOLO_A = 2.0                       # 单人段起点（素材内时间）
P1_A = 2.0                         # 联机段一起点
ST_A = 2.0                         # 工作台段起点
END_D = 8.0

BGMCSS = GAME / "content" / "assets" / "audio" / "bgm_opening.wav"
BGMRT = GAME / "content" / "assets" / "audio" / "bgm_roundtable.wav"

DEMO_URL = "https://qiuzhen-archive-game.app.workbuddy.host/"


def mt(marks: dict, tag: str, name: str, fallback: float) -> float:
    """从 marks.json 取某段某标记的素材内时间；缺失用兜底值。"""
    for m in marks.get(tag, []):
        if m.get("name") == name:
            return float(m["t"])
    return fallback


def cuts() -> dict:
    """按录制 marks 计算各段切点（弹窗加入后时长会变，硬编码会错位）。"""
    import json
    mf = OUT / "marks.json"
    marks = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    solo_b = mt(marks, "solo", "done", 47.0) - 0.3
    solo_mid_a = mt(marks, "solo", "map", 43.0) + 4.8      # 弹窗「现场搜证」收尾
    solo_mid_b = mt(marks, "solo", "search", 93.0) - 2.2   # 提交成功后起
    joined = mt(marks, "party_guest", "joined", 21.0)
    play = mt(marks, "party_host", "play", 121.0)
    chat_done = mt(marks, "party_host", "chat_done", 136.0)
    st_b = mt(marks, "studio", "done", 50.0) - 0.3
    p1_b = max(joined + 22.0, P1_A + 30.0)  # 段一到"双方选人完成"即收，避开跳弹窗/序章长流程
    p2_a = max(play - 3.0, p1_b + 1.0)
    p2_b = chat_done + 1.0
    g1_off = max(0.0, (joined - P1_A) - 7.0)  # guest 晚开录 ~7s
    return {
        "SOLO_B": solo_b, "SOLO_MID_A": solo_mid_a, "SOLO_MID_B": solo_mid_b,
        "P1_B": p1_b, "P2_A": p2_a, "P2_B": p2_b,
        "ST_B": st_b, "JOINED": joined, "G1_OFF": g1_off,
    }


def sh(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg 失败:\n{r.stderr[-2400:]}")


def probe(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def make_cards() -> None:
    base = f"""
    html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;
      background:
        radial-gradient(1300px 640px at 50% -10%, rgba(0,132,255,.22), transparent 60%),
        radial-gradient(900px 480px at 50% 118%, rgba(245,196,81,.10), transparent 55%),
        #05080f;
      color:#e8f0ff;font-family:"Microsoft YaHei","PingFang SC",sans-serif}}
    .wrap{{height:100%;display:flex;flex-direction:column;align-items:center;
      justify-content:center;text-align:center}}
    .chip{{padding:9px 22px;border:1px solid rgba(0,132,255,.5);border-radius:999px;
      color:#4da8ff;letter-spacing:.16em;font-size:21px;margin-bottom:34px}}
    h1{{font-size:96px;margin:0;font-weight:800;letter-spacing:.02em;
      text-shadow:0 0 70px rgba(0,132,255,.55)}}
    h1 span{{color:#0084ff}}
    h2{{font-size:34px;margin:20px 0 0;color:#f5c451;font-weight:700;letter-spacing:.08em}}
    .feats{{margin-top:52px;display:flex;gap:26px}}
    .feat{{width:360px;padding:26px 22px;border-radius:16px;
      background:rgba(10,18,32,.72);border:1px solid rgba(0,132,255,.28)}}
    .feat b{{display:block;font-size:27px;color:#f2f6ff;margin-bottom:10px}}
    .feat span{{font-size:19px;color:#a9bcd8;line-height:1.5}}
    .foot{{position:absolute;bottom:64px;width:100%;text-align:center;
      color:#7f93ba;font-size:19px;letter-spacing:.1em}}
    """
    title_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{base}</style></head>
<body><div class="wrap">
  <div class="chip">知乎黑客松 2026 · 跨次元游乐场 · AI 游戏与互动叙事</div>
  <h1>求真档案局 · <span>看山失踪夜</span></h1>
  <h2>AI 原生欢乐阵营机制推理本</h2>
  <div class="feats">
    <div class="feat"><b>单人模式</b><span>八个 AI 当事人同席<br>口供会漏，心声漏得更多</span></div>
    <div class="feat"><b>联机模式</b><span>房间码一贴，真人入座<br>空白席位 AI 补齐</span></div>
    <div class="feat"><b>生产工作台</b><span>一句话编译一本剧本<br>闸门通过，立刻开玩</span></div>
  </div>
</div>
<div class="foot">规则引擎裁决 · AI 只负责演出 · 求真档案局项目组</div></body></html>"""

    end_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{base}</style></head>
<body><div class="wrap">
  <div class="chip" style="border-color:rgba(245,196,81,.55);color:#f5c451">
    单人 · 联机 · 创作一本 —— 现在就开始</div>
  <h1 style="font-size:64px">线上 Demo · 免安装</h1>
  <div style="margin:30px 0 8px;padding:16px 26px;display:inline-block;border-radius:12px;
    border:1px solid rgba(0,132,255,.4);background:rgba(0,132,255,.08);
    font-family:Consolas,monospace;font-size:27px;color:#4da8ff">{DEMO_URL}</div>
  <p style="font-size:22px;color:#a9bcd8;margin-top:26px">
    八个知乎生态拟人嫌疑人已经入席 —— <b style="color:#f5c451">不出真相，不出此门。</b></p>
</div>
<div class="foot">求真档案局 · 看山失踪夜 · 知乎黑客松 2026</div></body></html>"""

    (OUT / "promo_title.html").write_text(title_html, encoding="utf-8")
    (OUT / "promo_end.html").write_text(end_html, encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.set_content(title_html)
        pg.wait_for_timeout(250)
        pg.screenshot(path=str(OUT / "promo_title.png"))
        pg.set_content(end_html)
        pg.wait_for_timeout(250)
        pg.screenshot(path=str(OUT / "promo_end.png"))
        b.close()
    print("cards ok", flush=True)


def compose() -> Path:
    make_cards()
    solo = OUT / "solo.webm"
    host = OUT / "party_host.webm"
    guest = OUT / "party_guest.webm"
    studio = OUT / "studio.webm"
    for f in (solo, host, guest, studio):
        if not f.exists():
            raise SystemExit(f"缺素材：{f}")

    C = cuts()
    SOLO_B = C["SOLO_B"]
    SOLO_MID_A = C["SOLO_MID_A"]      # 搜证面板+弹窗 结束刀口
    SOLO_MID_B = C["SOLO_MID_B"]      # 搜证提交成功 起刀口
    P1_B = C["P1_B"]
    P2_A = C["P2_A"]
    P2_B = C["P2_B"]
    ST_B = C["ST_B"]
    print("cuts:", {k: round(v, 2) for k, v in C.items()}, flush=True)

    d1 = P1_B - P1_A                      # 联机段一长度
    d2 = P2_B - P2_A                      # 联机段二长度
    dsolo = (SOLO_MID_A - SOLO_A) + (SOLO_B - SOLO_MID_B)
    dst = ST_B - ST_A
    total = TITLE_D + dsolo + d1 + d2 + dst + END_D
    print(f"total={total:.1f}s", flush=True)

    # guest PiP：从 guest 有画面起叠到段一结束
    G1_OFF = min(C["G1_OFF"], max(0.0, d1 - 12.0))
    G1_IN, G1_OUT = 0.0, min(d1 - G1_OFF, 120.0)

    fc = f"""
[0:v]loop=loop=-1:size=1:start=0,trim=duration={TITLE_D},setpts=PTS-STARTPTS,fps=30,
  scale={W}:{H},format=yuv420p,
  fade=t=in:st=0:d=0.4,fade=t=out:st={TITLE_D-0.5:.2f}:d=0.5[v0];
[1:v]trim=start={SOLO_A}:end={SOLO_MID_A},setpts=PTS-STARTPTS,fps=30,format=yuv420p,
  fade=t=out:st={SOLO_MID_A-SOLO_A-0.35:.2f}:d=0.35[s1a];
[1:v]trim=start={SOLO_MID_B}:end={SOLO_B},setpts=PTS-STARTPTS,fps=30,format=yuv420p,
  fade=t=in:st=0:d=0.3,fade=t=out:st={SOLO_B-SOLO_MID_B-0.5:.2f}:d=0.5[s1b];
[s1a][s1b]concat=n=2:v=1:a=0[v1];
[2:v]split=2[h1][h2];
[h1]trim=start={P1_A}:end={P1_B},setpts=PTS-STARTPTS,fps=30,format=yuv420p[h1t];
[h2]trim=start={P2_A}:end={P2_B},setpts=PTS-STARTPTS,fps=30,format=yuv420p[h2t];
[3:v]trim=start={G1_IN}:end={G1_OUT},setpts=PTS-STARTPTS,fps=30,
  scale=520:292,pad=526:298:3:3:color=0x0A84FF[pip1];
[h1t][pip1]overlay=x={W-526-36}:y={H-298-100}:enable='between(t,{G1_OFF},{d1})'[v2a];
[h2t]fade=t=in:st=0:d=0.4[v2b];
[4:v]trim=start={ST_A}:end={ST_B},setpts=PTS-STARTPTS,fps=30,format=yuv420p,
  fade=t=in:st=0:d=0.4,fade=t=out:st={dst-0.5:.2f}:d=0.5[v4];
[5:v]loop=loop=-1:size=1:start=0,trim=duration={END_D},setpts=PTS-STARTPTS,fps=30,
  scale={W}:{H},format=yuv420p,
  fade=t=in:st=0:d=0.4,fade=t=out:st={END_D-0.7:.2f}:d=0.7[v5];
[v0][v1][v2a][v2b][v4][v5]concat=n=6:v=1:a=0,fade=t=in:st=0:d=0.3[vout]
"""
    silent = OUT / "promo_silent.mp4"
    sh([
        FFMPEG, "-y",
        "-i", str(OUT / "promo_title.png"),
        "-i", str(solo), "-i", str(host), "-i", str(guest),
        "-i", str(studio),
        "-i", str(OUT / "promo_end.png"),
        "-filter_complex", fc,
        "-map", "[vout]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
        str(silent),
    ])
    print("video ok", probe(silent), flush=True)

    rt_d = total - 32.0
    af = (
        f"[1:a]aloop=loop=-1:size=20000000,atrim=0:32,volume=0.20,"
        f"afade=t=in:st=0:d=1.0,afade=t=out:st=30.4:d=1.4[a1];"
        f"[2:a]aloop=loop=-1:size=20000000,atrim=0:{rt_d:.2f},volume=0.135,"
        f"afade=t=in:st=0:d=1.4,afade=t=out:st={rt_d-2.0:.2f}:d=1.8,adelay=32000|32000[a2];"
        f"[a1][a2]amix=inputs=2:duration=longest:dropout_transition=3,"
        f"apad=whole_dur={total:.2f}[aout]"
    )
    final = ROOT / "游戏宣传片.mp4"
    sh([
        FFMPEG, "-y", "-i", str(silent), "-i", str(BGMCSS), "-i", str(BGMRT),
        "-filter_complex", af,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-t", f"{total:.2f}", str(final),
    ])
    print("FINAL", final, probe(final), flush=True)
    return final


if __name__ == "__main__":
    f = compose()
    docs = GAME / "docs" / "游戏宣传片.mp4"
    try:
        import shutil
        shutil.copy2(f, docs)
    except Exception:
        pass
    print("done", flush=True)
