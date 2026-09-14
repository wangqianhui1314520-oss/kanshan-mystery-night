"""Read-only AI diagnostics; never return credentials or private role memory."""
from urllib.parse import urlsplit


def describe_ai(env, config=None, session=None):
    config = config or {}
    session = session or {}
    key = config.get('llm_key') or env.get('LLM_API_KEY')
    base = config.get('llm_base') or env.get('LLM_BASE_URL') or ''
    model = config.get('llm_model') or env.get('LLM_MODEL')
    zhihu_key = (config.get('zhihu_secret') or env.get('ZHIHU_APP_KEY')
                 or env.get('ZHIHU_ACCESS_SECRET'))
    # 知乎 Secret 单独填写即可启用官方 Agent 默认通道。
    complete = bool(key and base and model) or bool(zhihu_key)
    zhihu = bool(zhihu_key)
    try:
        host = urlsplit(base).hostname or ''
    except ValueError:
        host = ''
    provider = '知乎直答' if (zhihu_key and (not key or host == 'developer.zhihu.com')) else ('自定义模型' if complete else '未配置')
    state = 'configured' if complete or zhihu else 'missing'
    notice = '已发现模型配置；尚未验证当前接口能否成功响应。' if state == 'configured' else '未发现可用模型配置，请在设置中配置 AI。'
    if session.get('engine') == 'mock':
        state, notice = 'offline_demo', '本局使用离线演示，不能代表实时 AI 游玩。'
    else:
        for event in reversed(session.get('events') or []):
            payload = event.get('payload') or {}
            if payload.get('event') == 'ai_reply_failed':
                state, notice = 'failed', '本局最近一次 AI 对话失败；请检查设置后重试。'
                break
            if event.get('type') == 'chat' and payload.get('source') == 'agent' and payload.get('provider'):
                actual = str(payload['provider'])
                if actual in ('mock', 'fallback'):
                    state, notice = 'failed', '最近返回的是兜底内容，不能视为实时 AI 成功。'
                elif 'cache' in actual:
                    state, notice = 'cache', '本局最近一次回复来自缓存；尚不能确认接口当前在线。'
                else:
                    state, notice = 'success', '本局最近一次 AI 对话调用成功；这不是持续在线保证。'
                break
    seats = []
    for seat in session.get('seats_public') or session.get('seats') or []:
        if not isinstance(seat, dict):
            continue
        seats.append({'char_id': seat.get('char_id'), 'controller':
            'AI 接管' if seat.get('ai_takeover') else
            'AI 席位' if seat.get('is_ai') else '真人玩家'})
    return {'state': state, 'npc_provider': provider, 'default_provider': 'zhida',
            'zhida_available': zhihu,
            'notice': notice, 'seats': seats, 'build': 'ai-status-ui-20260914'}
