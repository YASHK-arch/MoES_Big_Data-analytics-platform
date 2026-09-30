import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisProtocolError(Exception):
    """Raised when Redis server returns an error or malformed RESP response."""

    pass


class AsyncRedisClient:
    """Zero-dependency, resilient asynchronous Redis client implementing RESP2/RESP3 protocol.

    Provides high-performance Redis Stream buffering and queuing primitives without
    external C-extension or binary driver dependencies.
    """

    def __init__(self, redis_url: Optional[str] = None, pool_size: int = 8) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        parsed = urlparse(self.redis_url)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 6379
        self.db = int(parsed.path.lstrip("/") or "0")
        self.password = parsed.password
        self.pool_size = pool_size

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._conn_loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock_obj: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None

        self._pool: Optional[asyncio.Queue[Tuple[asyncio.StreamReader, asyncio.StreamWriter]]] = (
            None
        )
        self._pool_loop: Optional[asyncio.AbstractEventLoop] = None
        self._pool_created: int = 0

    @property
    def _lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock_obj is None or self._lock_loop is not loop:
            self._lock_obj = asyncio.Lock()
            self._lock_loop = loop
        return self._lock_obj

    async def _create_connection(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Create and authenticate a single Redis socket connection."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=5.0,
        )
        if self.password:
            await self._send_command_on_conn(reader, writer, "AUTH", self.password)
        if self.db != 0:
            await self._send_command_on_conn(reader, writer, "SELECT", str(self.db))
        return reader, writer

    async def _acquire_connection(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Acquire a connection from the connection pool."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if self._pool is None or self._pool_loop is not loop:
            self._pool = asyncio.Queue(maxsize=self.pool_size)
            self._pool_loop = loop
            self._pool_created = 0

        if not self._pool.empty():
            return await self._pool.get()

        if self._pool_created < self.pool_size:
            self._pool_created += 1
            try:
                return await self._create_connection()
            except Exception:
                self._pool_created -= 1
                raise

        return await self._pool.get()

    async def _release_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        error: bool = False,
    ) -> None:
        """Release a connection back to the connection pool."""
        if error or writer.is_closing():
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            if self._pool_created > 0:
                self._pool_created -= 1
            return

        if self._pool is not None:
            try:
                self._pool.put_nowait((reader, writer))
            except asyncio.QueueFull:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
                if self._pool_created > 0:
                    self._pool_created -= 1

    async def connect(self) -> None:
        """Establish asynchronous TCP socket connection to Redis server."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if self._conn_loop is not loop:
            self._reader = None
            self._writer = None
            self._conn_loop = loop

        if self._writer is not None and not self._writer.is_closing():
            return

        try:
            self._reader, self._writer = await self._create_connection()
        except Exception as e:
            self._reader = None
            self._writer = None
            raise ConnectionError(f"Could not connect to Redis at {self.host}:{self.port}: {e}")

    async def close(self) -> None:
        """Close Redis connection and pool."""
        async with self._lock:
            if self._writer is not None:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass
                self._writer = None
                self._reader = None

        if self._pool is not None:
            while not self._pool.empty():
                try:
                    _, w = self._pool.get_nowait()
                    w.close()
                    await w.wait_closed()
                except Exception:
                    pass
            self._pool = None
            self._pool_created = 0

    @classmethod
    def _encode_command(cls, *args: Union[str, bytes, int, float]) -> bytes:
        """Encode command arguments into Redis RESP array format."""
        parts = [f"*{len(args)}\r\n".encode("utf-8")]
        for arg in args:
            if isinstance(arg, bytes):
                arg_bytes = arg
            else:
                arg_bytes = str(arg).encode("utf-8")
            parts.append(f"${len(arg_bytes)}\r\n".encode("utf-8"))
            parts.append(arg_bytes)
            parts.append(b"\r\n")
        return b"".join(parts)

    @classmethod
    async def _read_response_from_reader(cls, reader: asyncio.StreamReader) -> Any:
        """Parse RESP response from server reader stream."""
        line = await reader.readline()
        if not line:
            raise ConnectionError("Redis connection closed unexpectedly.")

        prefix = line[0:1]
        content = line[1:-2]  # Strip prefix and \r\n

        # Simple String (+)
        if prefix == b"+":
            return content.decode("utf-8", errors="replace")

        # Error (-)
        if prefix == b"-":
            err_msg = content.decode("utf-8", errors="replace")
            raise RedisProtocolError(err_msg)

        # Integer (:)
        if prefix == b":":
            return int(content)

        # Bulk String ($)
        if prefix == b"$":
            length = int(content)
            if length == -1:
                return None
            data = await reader.readexactly(length + 2)
            return data[:-2].decode("utf-8", errors="replace")

        # Array (*)
        if prefix == b"*":
            num_elements = int(content)
            if num_elements == -1:
                return None
            result: List[Any] = []
            for _ in range(num_elements):
                result.append(await cls._read_response_from_reader(reader))
            return result

        raise RedisProtocolError(f"Unknown RESP prefix: {prefix!r}")

    async def _read_response(self) -> Any:
        """Parse RESP response from default reader."""
        if self._reader is None:
            raise ConnectionError("Redis client is not connected.")
        return await self._read_response_from_reader(self._reader)

    @classmethod
    async def _send_command_on_conn(
        cls,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *args: Union[str, bytes, int, float],
    ) -> Any:
        """Write command and parse response on given stream pair."""
        try:
            cmd_bytes = cls._encode_command(*args)
            writer.write(cmd_bytes)
            await writer.drain()
            return await cls._read_response_from_reader(reader)
        except (ConnectionError, asyncio.TimeoutError, OSError) as e:
            raise ConnectionError(f"Redis transport failure: {e}")

    async def _send_command(self, *args: Union[str, bytes, int, float]) -> Any:
        """Write command and parse response without acquiring self._lock on default connection."""
        if self._writer is None or self._reader is None:
            raise ConnectionError("Redis client is not connected.")
        try:
            return await self._send_command_on_conn(self._reader, self._writer, *args)
        except ConnectionError:
            self._writer = None
            self._reader = None
            raise

    async def _execute_raw(self, *args: Union[str, bytes, int, float]) -> Any:
        """Execute command over socket with connection pooling or single-connection fallback."""
        if self.pool_size > 1:
            reader, writer = await self._acquire_connection()
            has_error = False
            try:
                return await self._send_command_on_conn(reader, writer, *args)
            except Exception:
                has_error = True
                raise
            finally:
                await self._release_connection(reader, writer, error=has_error)
        else:
            async with self._lock:
                await self.connect()
                return await self._send_command(*args)

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            res = await self._execute_raw("PING")
            return res == "PONG" or res is True
        except Exception:
            return False

    async def xadd(
        self,
        stream: str,
        fields: Dict[str, Any],
        max_len: Optional[int] = None,
        approximate: bool = True,
    ) -> str:
        """Append an entry to a Redis stream."""
        cmd: List[Union[str, bytes, int, float]] = ["XADD", stream]
        if max_len is not None:
            cmd.extend(["MAXLEN", "~" if approximate else "=", str(max_len)])
        cmd.append("*")  # Auto-generate message ID

        for k, v in fields.items():
            cmd.append(str(k))
            cmd.append(str(v))

        msg_id = await self._execute_raw(*cmd)
        return str(msg_id)

    async def xgroup_create(
        self,
        stream: str,
        group: str,
        id_str: str = "$",
        mkstream: bool = True,
    ) -> bool:
        """Create a consumer group for a Redis stream."""
        cmd: List[Union[str, bytes, int, float]] = ["XGROUP", "CREATE", stream, group, id_str]
        if mkstream:
            cmd.append("MKSTREAM")
        try:
            res = await self._execute_raw(*cmd)
            return res == "OK"
        except RedisProtocolError as e:
            if "BUSYGROUP" in str(e):
                # Group already exists
                return True
            raise

    def _parse_stream_entries(self, raw_entries: Any) -> List[Tuple[str, Dict[str, str]]]:
        """Parse raw Redis list of stream entries into typed tuples.

        Expected format: [[id, [k1, v1, k2, v2, ...]], ...]
        """
        if not raw_entries or not isinstance(raw_entries, list):
            return []
        parsed: List[Tuple[str, Dict[str, str]]] = []
        for entry in raw_entries:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            m_id = str(entry[0])
            raw_fields = entry[1]
            f_dict: Dict[str, str] = {}
            if isinstance(raw_fields, list):
                for i in range(0, len(raw_fields), 2):
                    if i + 1 < len(raw_fields):
                        f_dict[str(raw_fields[i])] = str(raw_fields[i + 1])
            parsed.append((m_id, f_dict))
        return parsed

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: Dict[str, str],
        count: Optional[int] = None,
        block_ms: Optional[int] = None,
    ) -> List[Tuple[str, List[Tuple[str, Dict[str, str]]]]]:
        """Read entries from a Redis stream via a consumer group.

        Returns list of (stream_name, list_of_(msg_id, fields_dict)).
        """
        cmd: List[Union[str, bytes, int, float]] = ["XREADGROUP", "GROUP", group, consumer]
        if count is not None:
            cmd.extend(["COUNT", str(count)])
        if block_ms is not None and block_ms > 0:
            cmd.extend(["BLOCK", str(block_ms)])

        cmd.append("STREAMS")
        for stream_name in streams.keys():
            cmd.append(stream_name)
        for msg_id in streams.values():
            cmd.append(msg_id)

        raw_response = await self._execute_raw(*cmd)
        if not raw_response or not isinstance(raw_response, list):
            return []

        parsed_streams: List[Tuple[str, List[Tuple[str, Dict[str, str]]]]] = []
        for stream_item in raw_response:
            if not isinstance(stream_item, list) or len(stream_item) < 2:
                continue
            stream_name = str(stream_item[0])
            entries_list = stream_item[1]
            parsed_entries = self._parse_stream_entries(entries_list)
            parsed_streams.append((stream_name, parsed_entries))

        return parsed_streams

    async def xread(
        self,
        streams: Dict[str, str],
        count: Optional[int] = None,
        block_ms: Optional[int] = None,
    ) -> List[Tuple[str, List[Tuple[str, Dict[str, str]]]]]:
        """Read entries from one or more Redis streams directly (standalone streaming/replay).

        Returns list of (stream_name, list_of_(msg_id, fields_dict)).
        """
        cmd: List[Union[str, bytes, int, float]] = ["XREAD"]
        if count is not None:
            cmd.extend(["COUNT", str(count)])
        if block_ms is not None:
            cmd.extend(["BLOCK", str(block_ms)])

        cmd.append("STREAMS")
        for stream_name in streams.keys():
            cmd.append(stream_name)
        for msg_id in streams.values():
            cmd.append(msg_id)

        raw_response = await self._execute_raw(*cmd)
        if not raw_response or not isinstance(raw_response, list):
            return []

        parsed_streams: List[Tuple[str, List[Tuple[str, Dict[str, str]]]]] = []
        for stream_item in raw_response:
            if not isinstance(stream_item, list) or len(stream_item) < 2:
                continue
            stream_name = str(stream_item[0])
            entries_list = stream_item[1]
            parsed_entries = self._parse_stream_entries(entries_list)
            parsed_streams.append((stream_name, parsed_entries))

        return parsed_streams

    async def xrange(
        self,
        stream: str,
        min_id: str = "-",
        max_id: str = "+",
        count: Optional[int] = None,
    ) -> List[Tuple[str, Dict[str, str]]]:
        """Fetch range of entries from stream in ascending order."""
        cmd: List[Union[str, bytes, int, float]] = ["XRANGE", stream, min_id, max_id]
        if count is not None:
            cmd.extend(["COUNT", str(count)])
        raw_response = await self._execute_raw(*cmd)
        return self._parse_stream_entries(raw_response)

    async def xrevrange(
        self,
        stream: str,
        max_id: str = "+",
        min_id: str = "-",
        count: Optional[int] = None,
    ) -> List[Tuple[str, Dict[str, str]]]:
        """Fetch range of entries from stream in descending order."""
        cmd: List[Union[str, bytes, int, float]] = ["XREVRANGE", stream, max_id, min_id]
        if count is not None:
            cmd.extend(["COUNT", str(count)])
        raw_response = await self._execute_raw(*cmd)
        return self._parse_stream_entries(raw_response)

    async def xack(self, stream: str, group: str, *ids: str) -> int:
        """Acknowledge one or more message IDs in a consumer group."""
        if not ids:
            return 0
        cmd: List[Union[str, bytes, int, float]] = ["XACK", stream, group]
        cmd.extend(ids)
        res = await self._execute_raw(*cmd)
        return int(res) if isinstance(res, int) else 0

    async def xpending(self, stream: str, group: str) -> Dict[str, Any]:
        """Fetch pending entries list (PEL) summary for a consumer group."""
        cmd: List[Union[str, bytes, int, float]] = ["XPENDING", stream, group]
        res = await self._execute_raw(*cmd)
        if not res or not isinstance(res, list) or len(res) < 4:
            return {"count": 0, "min_id": None, "max_id": None, "consumers": []}
        return {
            "count": int(res[0]) if res[0] is not None else 0,
            "min_id": res[1],
            "max_id": res[2],
            "consumers": res[3] if isinstance(res[3], list) else [],
        }

    async def xautoclaim(
        self,
        stream: str,
        group: str,
        consumer: str,
        min_idle_time_ms: int,
        start_id: str = "0-0",
        count: Optional[int] = None,
    ) -> Tuple[str, List[Tuple[str, Dict[str, str]]]]:
        """Reclaim pending stream entries idle longer than min_idle_time_ms.

        Returns (next_start_id, list_of_(msg_id, fields_dict)).
        """
        cmd: List[Union[str, bytes, int, float]] = [
            "XAUTOCLAIM",
            stream,
            group,
            consumer,
            str(min_idle_time_ms),
            start_id,
        ]
        if count is not None:
            cmd.extend(["COUNT", str(count)])

        res = await self._execute_raw(*cmd)
        if not res or not isinstance(res, list) or len(res) < 2:
            return ("0-0", [])

        next_start_id = str(res[0]) if res[0] is not None else "0-0"
        entries = self._parse_stream_entries(res[1]) if isinstance(res[1], list) else []
        return (next_start_id, entries)

    async def xpending_detail(
        self,
        stream: str,
        group: str,
        start_id: str = "-",
        end_id: str = "+",
        count: int = 50,
        consumer: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch detailed pending entries (id, consumer, idle_ms, deliveries)."""
        cmd: List[Union[str, bytes, int, float]] = [
            "XPENDING",
            stream,
            group,
            start_id,
            end_id,
            str(count),
        ]
        if consumer is not None:
            cmd.append(consumer)
        res = await self._execute_raw(*cmd)
        if not res or not isinstance(res, list):
            return []
        items = []
        for entry in res:
            if isinstance(entry, list) and len(entry) >= 4:
                items.append(
                    {
                        "id": str(entry[0]),
                        "consumer": str(entry[1]),
                        "idle_ms": int(entry[2]) if entry[2] is not None else 0,
                        "deliveries": int(entry[3]) if entry[3] is not None else 0,
                    }
                )
        return items

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys from Redis."""
        if not keys:
            return 0
        res = await self._execute_raw("DEL", *keys)
        return int(res) if isinstance(res, int) else 0

    async def incr(self, key: str) -> int:
        """Increment integer value of key."""
        res = await self._execute_raw("INCR", key)
        return int(res) if res is not None else 1

    async def expire(self, key: str, seconds: int) -> int:
        """Set a timeout on key."""
        res = await self._execute_raw("EXPIRE", key, str(seconds))
        return int(res) if res is not None else 0

    async def ttl(self, key: str) -> int:
        """Return time-to-live for key in seconds. -2 if not exists, -1 if no expiry."""
        res = await self._execute_raw("TTL", key)
        return int(res) if res is not None else -2

    async def get(self, key: str) -> Optional[str]:
        """Get value of key."""
        res = await self._execute_raw("GET", key)
        if res is None:
            return None
        if isinstance(res, bytes):
            return res.decode("utf-8")
        return str(res)

    async def set(
        self,
        key: str,
        value: Union[str, bytes],
        ex: Optional[int] = None,
        nx: bool = False,
    ) -> bool:
        """Set key to value with optional expiry and NX condition."""
        args: List[Union[str, bytes, int, float]] = ["SET", key, value]
        if ex is not None:
            args.extend(["EX", str(ex)])
        if nx:
            args.append("NX")
        res = await self._execute_raw(*args)
        return res is not None and (res == "OK" or res is True or res == 1)

    async def keys(self, pattern: str = "*") -> List[str]:
        """Return list of keys matching pattern (use sparingly — O(N))."""
        res = await self._execute_raw("KEYS", pattern)
        if not res:
            return []
        return [k.decode("utf-8") if isinstance(k, bytes) else str(k) for k in res]

    async def xinfo_groups(self, stream: str) -> List[Dict[str, Any]]:
        """Return XINFO GROUPS for a stream as a list of dicts."""
        try:
            res = await self._execute_raw("XINFO", "GROUPS", stream)
        except Exception:
            return []
        if not res:
            return []
        groups = []
        for entry in res:
            # RESP2 returns flat list [field, value, field, value, ...]
            if isinstance(entry, (list, tuple)):
                d: Dict[str, Any] = {}
                it = iter(entry)
                for k in it:
                    v = next(it, None)
                    k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                    d[k_str] = v.decode("utf-8") if isinstance(v, bytes) else v
                groups.append(d)
        return groups

    async def xlen(self, stream: str) -> int:
        """Return the number of entries in a stream."""
        try:
            res = await self._execute_raw("XLEN", stream)
            return int(res) if res is not None else 0
        except Exception:
            return 0

    async def llen(self, key: str) -> int:
        """Return the length of a list."""
        try:
            res = await self._execute_raw("LLEN", key)
            return int(res) if res is not None else 0
        except Exception:
            return 0


redis_client = AsyncRedisClient()
