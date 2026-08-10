"""PostgreSQL-backed tenant change notifications with per-worker fan-out."""
from __future__ import annotations

import asyncio
import json
import logging
import select
import threading
import time
from collections import defaultdict
from typing import Any

import psycopg2
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

logger = logging.getLogger("edvatiq.realtime")
CHANNEL = "edvatiq_tenant_changes"


def _driver_dsn() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://", 1)


class RealtimeHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(set)
        self._started = False

    def subscribe(self, tenant_id: str) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers[tenant_id].add((loop, queue))
            if not self._started:
                self._started = True
                threading.Thread(target=self._listen_forever, name="edvatiq-realtime", daemon=True).start()
        return queue

    def unsubscribe(self, tenant_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            entries = self._subscribers.get(tenant_id, set())
            self._subscribers[tenant_id] = {entry for entry in entries if entry[1] is not queue}
            if not self._subscribers[tenant_id]:
                self._subscribers.pop(tenant_id, None)

    @staticmethod
    def _offer(queue: asyncio.Queue, payload: dict[str, Any]) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(payload)

    def _dispatch(self, payload: dict[str, Any]) -> None:
        tenant_id = str(payload.get("tenant_id") or "")
        with self._lock:
            subscribers = list(self._subscribers.get(tenant_id, set()))
        for loop, queue in subscribers:
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._offer, queue, payload)

    def _listen_forever(self) -> None:
        while True:
            connection = None
            try:
                connection = psycopg2.connect(_driver_dsn())
                connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                with connection.cursor() as cursor:
                    cursor.execute(f"LISTEN {CHANNEL}")
                logger.info("realtime_listener_ready")
                while True:
                    if not select.select([connection], [], [], 15)[0]:
                        continue
                    connection.poll()
                    while connection.notifies:
                        notification = connection.notifies.pop(0)
                        try:
                            self._dispatch(json.loads(notification.payload))
                        except (TypeError, ValueError):
                            logger.warning("realtime_invalid_payload")
            except Exception as exc:  # Listener reconnects; polling remains the client fallback.
                logger.warning("realtime_listener_retry error_type=%s", type(exc).__name__)
                time.sleep(2)
            finally:
                if connection is not None:
                    connection.close()


hub = RealtimeHub()


def publish_change(tenant_id: str, path: str) -> None:
    payload = json.dumps({"tenant_id": str(tenant_id), "path": path}, separators=(",", ":"))
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": payload})
