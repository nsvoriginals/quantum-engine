"""Unit tests for the cache layer."""
import pytest
from core.cache import InMemoryCache


class TestInMemoryCache:
    @pytest.fixture
    def cache(self):
        return InMemoryCache()

    async def test_get_missing_key_returns_none(self, cache):
        assert await cache.get("no-such-key") is None

    async def test_set_and_get_round_trip(self, cache):
        await cache.set("k", {"score": 0.5})
        assert await cache.get("k") == {"score": 0.5}

    async def test_delete_removes_key(self, cache):
        await cache.set("k", "value")
        await cache.delete("k")
        assert await cache.get("k") is None

    async def test_delete_missing_key_is_noop(self, cache):
        await cache.delete("ghost")  # must not raise

    async def test_overwrite_existing_key(self, cache):
        await cache.set("k", "old")
        await cache.set("k", "new")
        assert await cache.get("k") == "new"

    async def test_close_is_noop(self, cache):
        await cache.close()  # must not raise

    async def test_ttl_parameter_accepted(self, cache):
        await cache.set("k", "v", ttl=60)
        assert await cache.get("k") == "v"
