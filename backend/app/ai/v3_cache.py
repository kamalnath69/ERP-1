"""Small process-local caches for non-sensitive V3 metadata."""
from collections import OrderedDict
from threading import RLock
from time import monotonic
from typing import Generic, TypeVar


T = TypeVar("T")


class BoundedTTLCache(Generic[T]):
    def __init__(self, *, maxsize: int, ttl_seconds: int):
        self.maxsize = max(1, maxsize)
        self.ttl_seconds = max(1, ttl_seconds)
        self._items: OrderedDict[object, tuple[float, T]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: object) -> T | None:
        now = monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: object, value: T) -> T:
        with self._lock:
            self._items[key] = (monotonic() + self.ttl_seconds, value)
            self._items.move_to_end(key)
            while len(self._items) > self.maxsize:
                self._items.popitem(last=False)
        return value

    def delete(self, key: object) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


PLAN_CACHE = BoundedTTLCache(maxsize=512, ttl_seconds=600)
CAPABILITY_CACHE = BoundedTTLCache(maxsize=512, ttl_seconds=60)
ACADEMIC_REFERENCE_CACHE = BoundedTTLCache(maxsize=256, ttl_seconds=300)
QUERY_EMBEDDING_CACHE = BoundedTTLCache(maxsize=256, ttl_seconds=1800)

