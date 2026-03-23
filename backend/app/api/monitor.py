"""
AI Monitor API — SSE 实时推送 + REST 历史查询
"""

import json
from flask import Response, request, stream_with_context

from . import monitor_bp
from ..utils.llm_monitor import monitor


@monitor_bp.route('/stream')
def stream():
    """SSE 端点：实时推送 LLM 调用记录"""

    def generate():
        for entry in monitor.subscribe():
            if entry is None:
                # 心跳
                yield ": heartbeat\n\n"
            else:
                yield f"data: {json.dumps(entry, ensure_ascii=False, default=str)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@monitor_bp.route('/history')
def history():
    """返回历史记录"""
    limit = request.args.get('limit', 50, type=int)
    records = monitor.get_history(limit)
    return {"success": True, "data": records}


@monitor_bp.route('/clear', methods=['POST'])
def clear():
    """清空缓冲"""
    monitor.clear()
    return {"success": True}
