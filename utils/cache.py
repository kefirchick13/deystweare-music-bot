"""
In-memory cache pool with TTL. Удобно управлять: get/set/delete, авто-истечение по времени.
"""
import time
from typing import Any, Optional, Dict


class CachePool:
    """
    In-memory key-value cache с TTL (time-to-live).
    При get() просроченные записи считаются отсутствующими и удаляются.
    """

    __slots__ = ("_data", "_ttl_sec")

    def __init__(self, ttl_sec: float):
        self._data: Dict[str, tuple] = {}  # key -> (value, timestamp)
        self._ttl_sec = ttl_sec

    def get(self, key: str) -> Optional[Any]:
        """Возвращает значение или None, если ключа нет или запись просрочена."""
        entry = self._data.get(key)
        if not entry:
            return None
        value, ts = entry
        if time.time() - ts > self._ttl_sec:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Сохраняет значение с текущим временем."""
        if key:
            self._data[key] = (value, time.time())

    def delete(self, key: str) -> None:
        """Удаляет запись по ключу."""
        self._data.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def cleanup_expired(self) -> int:
        """Удаляет все просроченные записи. Возвращает количество удалённых."""
        now = time.time()
        expired = [k for k, (_, ts) in self._data.items() if now - ts > self._ttl_sec]
        for k in expired:
            del self._data[k]
        return len(expired)

    def clear(self) -> None:
        """Очищает весь кэш."""
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
