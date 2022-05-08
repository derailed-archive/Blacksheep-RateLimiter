import hashlib
import time
from typing import TYPE_CHECKING, Coroutine

import orjson
from blacksheep import Request
from .utils import jsonify

if TYPE_CHECKING:
    # NOTE: For some reason the official version has shit typing?
    from aioredis import Redis # type: ignore

class RatelimitingMiddleware:
    def __init__(
        self,
        redis: "Redis",
        expires: int = 1,
        max_tries: int = 50,
    ):
        self._redis: "Redis" = redis
        self._expire_at = expires
        self._max_tries = max_tries

    async def __call__(self, request: Request, handler: Coroutine):
        ip = request.client_ip
        uid = hashlib.md5(ip.encode(), usedforsecurity=True).hexdigest()

        d = await self._redis.get(uid)

        if d is None:
            await self._redis.set(
                uid,
                orjson.dumps({
                    'tries': self._max_tries - 1,
                    'expires_at': time.time() + self._expire_at
                }),
                ex=self._expire_at
            )
        else:
            data = orjson.loads(d)

            if data['tries'] < self._max_tries and data['tries'] != self._max_tries:
                resp = jsonify(
                    {
                        'code': 429,
                        'message': 'Too Many Requests',
                        'retry_after': data['expires_at'] - time.time()
                    },
                    status=429
                )
                return resp

            await self._redis.delete(uid)
            await self._redis.set(
                uid,
                orjson.dumps(
                    {
                        'tries': data['tries'] - 1,
                        'expires_at': data['expires_at']
                    }
                )
            )

            resp = await handler()

            return resp
