from __future__ import annotations

import secrets
import time
from typing import Protocol
from urllib.parse import quote

import httpx


class StorageUnavailable(Exception):  # noqa: N818 - adapter boundary, not an HTTP error
    pass


class PrivateStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def sign_download(self, key: str, ttl: int) -> str: ...
    async def get(self, key: str, max_bytes: int) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class SupabasePrivateStorage:
    """Server-only Storage authority; no browser service-role or public URLs."""

    def __init__(self, url: str, service_key: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    async def get(self, key: str, max_bytes: int) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "GET",
                    f"{self._url}/storage/v1/object/authenticated/vtt-assets/"
                    f"{quote(key, safe='/')}",
                    headers=self._headers,
                    follow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > max_bytes:
                            raise StorageUnavailable
                        data.extend(chunk)
                    return bytes(data)
        except httpx.HTTPError as error:
            raise StorageUnavailable from error

    async def delete(self, key: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.request(
                    "DELETE",
                    f"{self._url}/storage/v1/object/vtt-assets",
                    headers=self._headers,
                    json={"prefixes": [key]},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise StorageUnavailable from error

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self._url}/storage/v1/object/vtt-assets/{quote(key, safe='/')}",
                    headers={**self._headers, "Content-Type": content_type, "x-upsert": "true"},
                    content=data,
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise StorageUnavailable from error

    async def sign_download(self, key: str, ttl: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self._url}/storage/v1/object/sign/vtt-assets/{quote(key, safe='/')}",
                    headers=self._headers,
                    json={"expiresIn": ttl},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise StorageUnavailable
                path = payload.get("signedURL")
                if not isinstance(path, str) or not path.startswith("/object/sign/"):
                    raise StorageUnavailable
                return f"{self._url}/storage/v1{path}"
        except (httpx.HTTPError, ValueError) as error:
            raise StorageUnavailable from error


class UnavailableStorage:
    async def get(self, key: str, max_bytes: int) -> bytes:
        raise StorageUnavailable

    async def delete(self, key: str) -> None:
        raise StorageUnavailable

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise StorageUnavailable

    async def sign_download(self, key: str, ttl: int) -> str:
        raise StorageUnavailable


class MemoryStorage:
    """Explicit isolated test adapter, never selected by production dependencies."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self._grants: dict[str, tuple[str, float]] = {}
        self.put_count = 0
        self.unavailable = False

    async def get(self, key: str, max_bytes: int) -> bytes:
        if self.unavailable or key not in self.objects or len(self.objects[key][0]) > max_bytes:
            raise StorageUnavailable
        return self.objects[key][0]

    async def delete(self, key: str) -> None:
        if self.unavailable:
            raise StorageUnavailable
        self.objects.pop(key, None)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.unavailable:
            raise StorageUnavailable
        self.objects[key] = (data, content_type)
        self.put_count += 1

    async def sign_download(self, key: str, ttl: int) -> str:
        if self.unavailable or key not in self.objects:
            raise StorageUnavailable
        token = secrets.token_urlsafe(32)
        self._grants[token] = (key, time.monotonic() + ttl)
        return f"/__test_storage/{token}"

    def read_grant(self, token: str) -> tuple[bytes, str]:
        grant = self._grants.get(token)
        if self.unavailable or grant is None or grant[1] <= time.monotonic():
            raise StorageUnavailable
        return self.objects[grant[0]]
