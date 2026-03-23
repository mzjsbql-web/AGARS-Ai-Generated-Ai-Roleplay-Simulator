"""
LLM 调用监控服务

内存中存储最近的 LLM 请求/响应记录，通过 SSE 实时推送给前端面板。
"""

import threading
import time
import uuid
from collections import deque
from queue import Queue, Empty


class LLMMonitor:
    """LLM 调用监控（线程安全，内存 deque）"""

    def __init__(self, maxlen: int = 200):
        self._records = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._subscribers: list[Queue] = []
        self._sub_lock = threading.Lock()

    # ── 记录 ──────────────────────────────────────────────

    def log_full(
        self,
        *,
        source: str,
        model: str,
        messages: list | None = None,
        kwargs: dict | None = None,
        response: str | None = None,
        duration_ms: float | None = None,
        tokens: dict | None = None,
        error: str | None = None,
    ):
        """一次调用记录完整请求 + 响应"""
        entry = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": time.time(),
            "type": "llm",
            "source": source,
            "model": model or "",
            "messages": messages,
            "kwargs": kwargs,
            "response": response,
            "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
            "tokens": tokens,
            "error": error,
        }
        with self._lock:
            self._records.append(entry)
        self._broadcast(entry)

    # ── 历史 / 清空 ──────────────────────────────────────

    def get_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            items = list(self._records)
        return items[-limit:]

    def clear(self):
        with self._lock:
            self._records.clear()

    # ── SSE 订阅 ─────────────────────────────────────────

    def subscribe(self):
        """返回 SSE 生成器。调用方 close 时自动退订。"""
        q: Queue = Queue()
        with self._sub_lock:
            self._subscribers.append(q)
        try:
            while True:
                try:
                    entry = q.get(timeout=30)
                    yield entry
                except Empty:
                    # 发送心跳保持连接
                    yield None
        finally:
            with self._sub_lock:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass

    def _broadcast(self, entry: dict):
        with self._sub_lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(entry)
                except Exception:
                    dead.append(q)
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass


# 单例
monitor = LLMMonitor()
