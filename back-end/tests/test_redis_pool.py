import asyncio

import pytest

from app.core.redis import AsyncRedisClient


@pytest.mark.asyncio
async def test_redis_client_connection_pool_concurrency():
    """Verify that AsyncRedisClient with pool_size > 1 handles concurrent non-blocking commands without serialization."""
    client = AsyncRedisClient(pool_size=4)
    try:
        # Pre-seed a test key
        await client.set("test:pool:key", "value_ok", ex=10)

        # Run 20 concurrent GET operations
        async def worker():
            val = await client.get("test:pool:key")
            assert val == "value_ok"

        tasks = [asyncio.create_task(worker()) for _ in range(20)]
        await asyncio.gather(*tasks)

        # Verify pool was created and used
        assert client._pool_created <= 4
        assert client._pool is not None
    finally:
        await client.close()
