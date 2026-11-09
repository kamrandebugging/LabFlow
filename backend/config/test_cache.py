"""Test-only cache backend with a prefix-scoped ``clear()``.

Django's built-in ``RedisCache.clear()`` executes ``FLUSHDB``, which wipes the
entire Redis database rather than just the keys owned by that cache instance.
The suite runs under pytest-xdist with every worker sharing one Redis database,
and many test modules clear the cache in autouse fixtures. A FLUSHDB from one
worker therefore deletes another worker's in-flight TOTP challenge, refresh
rotation marker, or throttle counter mid-test, producing intermittent 401/400
failures that never reproduce when the same tests run sequentially.

``ScopedRedisCache`` keeps upstream semantics but limits ``clear()`` to keys
matching this cache's ``KEY_PREFIX``/version. Combined with the per-worker
``KEY_PREFIX`` set in ``config.settings.test`` it makes cache clears local to
the worker that issued them.
"""

from typing import Any, cast

from django.core.cache.backends.redis import RedisCache


class ScopedRedisCache(RedisCache):
    """``RedisCache`` whose ``clear()`` only removes this cache's own keys."""

    def clear(self) -> None:
        client: Any = cast(Any, self._cache).get_client(None, write=True)
        pattern = self.make_key("*")
        keys = list(client.scan_iter(match=pattern, count=1000))
        if keys:
            client.delete(*keys)
