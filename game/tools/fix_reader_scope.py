"""One-time migration: place readers beside opening and play, never inside play."""
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'frontend/js/main.js'
source = path.read_text(encoding='utf-8')
start = source.index('      <div class="bk-mask"')
end = source.index('      <div class="recap-mask"', start)
readers = source[start:end]
source = source[:start] + source[end:]
anchor = '    <!-- 设置（菜单与对局共用，勿挂在 .app 内） -->'
readers = readers.replace('v-if="S.bookletForced || S.bookletOpen"',
    'v-if="!S.isSpectator && ((S.phase === \'play\' && S.bookletForced) || S.bookletOpen)" role="dialog" aria-modal="true" aria-label="我的角色剧本"')
source = source.replace(anchor, '    <!-- 读本与选角、游玩页面同级 -->\n' + readers + anchor)
path.write_text(source, encoding='utf-8')
