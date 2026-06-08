"""Async response cache with optional Redis and in-process single-flight locks.

FIX 7: _memory_set no longer calls _persist_disk_cache() synchronously on
        every write. Disk persistence is now debounced — it runs at most once
        every DISK_PERSIST_INTERVAL_S seconds via a background asyncio task.
        This avoids blocking the event loop with file I/O on every cache hit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_memory_cache: dict[str, dict[str, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}
_refresh_tasks: dict[str, asyncio.Task] = {}
_redis_client: Any = None
_redis_checked = False
_disk_loaded = False
_disk_cache_file = Path(settings.job_detail_cache_dir) / "response_cache.json"

# FIX 7: Debounce disk writes — persist at most once every 60 seconds
DISK_PERSIST_INTERVAL_S = 60
_last_disk_persist: float = 0.0
_persist_task: asyncio.Task | None = None


def _load_disk_cache() -> None:
    global _disk_loaded

    if _disk_loaded:
        return
    _disk_loaded = True

    try:
        if not _disk_cache_file.exists():
            return
        data = json.loads(_disk_cache_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key, entry in data.items():
                if (
                    isinstance(entry, dict)
                    and "data" in entry
                    and isinstance(entry.get("expires_at"), (int, float))
                ):
                    _memory_cache[str(key)] = entry
    except Exception as exc:
        logger.warning("Could not load response cache file: %s", exc)


def _persist_disk_cache() -> None:
    """Write memory cache to disk. Called from background task only."""
    try:
        _disk_cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = _disk_cache_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(_memory_cache), encoding="utf-8")
        tmp_file.replace(_disk_cache_file)
    except Exception as exc:
        logger.warning("Could not persist response cache file: %s", exc)


def _schedule_disk_persist() -> None:
    """FIX 7: Schedule a debounced background disk persist."""
    global _last_disk_persist, _persist_task

    now = time.monotonic()
    if now - _last_disk_persist < DISK_PERSIST_INTERVAL_S:
        return  # Already persisted recently — skip

    if _persist_task is not None and not _persist_task.done():
        return  # Already scheduled

    async def _do_persist() -> None:
        global _last_disk_persist
        await asyncio.to_thread(_persist_disk_cache)
        _last_disk_persist = time.monotonic()

    try:
        loop = asyncio.get_running_loop()
        _persist_task = loop.create_task(_do_persist())
    except RuntimeError:
        # No running event loop (e.g. startup sync code) — persist inline
        _persist_disk_cache()
        _last_disk_persist = time.monotonic()


def _memory_get(key: str, *, allow_stale: bool = False) -> Any | None:
    _load_disk_cache()

    cached = _memory_cache.get(key)
    if not cached:
        return None
    if time.time() >= cached["expires_at"]:
        if allow_stale:
            return cached["data"]
        return None
    return cached["data"]


def _memory_set(key: str, data: Any, ttl: int) -> None:
    _memory_cache[key] = {"data": data, "expires_at": time.time() + ttl}
    # FIX 7: debounced disk persist instead of immediate blocking write
    _schedule_disk_persist()


_load_disk_cache()


async def _get_redis() -> Any | None:
    global _redis_checked, _redis_client

    if not settings.redis_url:
        return None
    if _redis_checked:
        return _redis_client

    _redis_checked = True
    try:
        from redis.asyncio import Redis

        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        await _redis_client.ping()
        logger.info("Redis response cache enabled")
    except Exception as exc:
        _redis_client = None
        logger.warning("Redis response cache unavailable; using in-process cache: %s", exc)
    return _redis_client


async def cached_response(
    key: str,
    ttl: int,
    builder: Callable[[], Awaitable[Any]],
) -> Any:
    """Return cached JSON-compatible data and collapse concurrent rebuilds."""

    if ttl <= 0:
        return await builder()

    memory_hit = _memory_get(key)
    if memory_hit is not None:
        return memory_hit

    redis = await _get_redis()
    if redis is not None:
        cached = await redis.get(key)
        if cached:
            data = json.loads(cached)
            _memory_set(key, data, min(ttl, 30))
            return data

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        memory_hit = _memory_get(key)
        if memory_hit is not None:
            return memory_hit

        redis = await _get_redis()
        if redis is not None:
            cached = await redis.get(key)
            if cached:
                data = json.loads(cached)
                _memory_set(key, data, min(ttl, 30))
                return data

            lock_key = f"lock:{key}"
            got_lock = await redis.set(lock_key, "1", nx=True, ex=60)
            if not got_lock:
                for _ in range(40):
                    await asyncio.sleep(0.25)
                    cached = await redis.get(key)
                    if cached:
                        data = json.loads(cached)
                        _memory_set(key, data, min(ttl, 30))
                        return data

            try:
                data = jsonable_encoder(await builder())
                _memory_set(key, data, ttl)
                jitter = random.randint(0, max(1, ttl // 10))
                await redis.set(key, json.dumps(data), ex=ttl + jitter)
                return data
            finally:
                if got_lock:
                    await redis.delete(lock_key)

        data = jsonable_encoder(await builder())
        _memory_set(key, data, ttl)

        return data


def _schedule_refresh(
    key: str,
    ttl: int,
    builder: Callable[[], Awaitable[Any]],
) -> None:
    task = _refresh_tasks.get(key)
    if task is not None and not task.done():
        return

    async def refresh() -> None:
        try:
            lock = _locks.setdefault(key, asyncio.Lock())
            async with lock:
                data = jsonable_encoder(await builder())
                _memory_set(key, data, ttl)

                redis = await _get_redis()
                if redis is not None:
                    jitter = random.randint(0, max(1, ttl // 10))
                    await redis.set(key, json.dumps(data), ex=ttl + jitter)
        except Exception as exc:
            logger.warning("Background cache refresh failed for %s: %s", key, exc)
        finally:
            _refresh_tasks.pop(key, None)

    _refresh_tasks[key] = asyncio.create_task(refresh())


async def cached_response_fast(
    key: str,
    ttl: int,
    builder: Callable[[], Awaitable[Any]],
) -> Any:
    """Return cached data immediately and refresh stale values in the background."""

    if ttl <= 0:
        return await builder()

    memory_hit = _memory_get(key)
    if memory_hit is not None:
        return memory_hit

    stale_hit = _memory_get(key, allow_stale=True)
    if stale_hit is not None:
        _schedule_refresh(key, ttl, builder)
        return stale_hit

    redis = await _get_redis()
    if redis is not None:
        cached = await redis.get(key)
        if cached:
            data = json.loads(cached)
            _memory_set(key, data, ttl)
            return data

    return await cached_response(key, ttl, builder)


async def invalidate_prefix(prefix: str) -> None:
    """Best-effort invalidation for local memory and Redis keys."""

    for key in list(_memory_cache):
        if key.startswith(prefix):
            _memory_cache.pop(key, None)

    redis = await _get_redis()
    if redis is None:
        return

    async for key in redis.scan_iter(f"{prefix}*"):
        await redis.delete(key)