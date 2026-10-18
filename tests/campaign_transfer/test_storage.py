import pytest
from app.assets.storage import MemoryStorage, StorageUnavailable, UnavailableStorage


async def test_storage_byte_read_and_scoped_delete_contract(monkeypatch):
    store = MemoryStorage()
    await store.put("source/asset", b"source", "image/png")
    await store.put("new/asset", b"copy", "image/png")
    assert await store.get("new/asset", 4) == b"copy"
    with pytest.raises(StorageUnavailable):
        await store.get("source/asset", 2)
    await store.delete("new/asset")
    await store.delete("new/asset")
    assert await store.get("source/asset", 6) == b"source"
    with pytest.raises(StorageUnavailable):
        await store.get("new/asset", 4)
    unavailable = UnavailableStorage()
    with pytest.raises(StorageUnavailable):
        await unavailable.get("any/asset", 4)
    with pytest.raises(StorageUnavailable):
        await unavailable.delete("any/asset")
    import httpx
    from app.assets.storage import SupabasePrivateStorage

    original_client = httpx.AsyncClient
    failed = [False]
    requests = []

    def response(request):
        requests.append(request)
        if failed[0]:
            return httpx.Response(503)
        if request.method == "GET":
            assert request.url.path == "/storage/v1/object/authenticated/vtt-assets/copy/asset"
            return httpx.Response(200, content=b"data")
        assert request.method == "DELETE" and request.url.path == "/storage/v1/object/vtt-assets"
        assert request.content == b'{"prefixes":["copy/asset"]}'
        return httpx.Response(200, json=[])

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(response), **kwargs),
    )
    adapter = SupabasePrivateStorage("https://storage.example.invalid", "fixture-only")
    assert await adapter.get("copy/asset", 4) == b"data"
    with pytest.raises(StorageUnavailable):
        await adapter.get("copy/asset", 3)
    await adapter.delete("copy/asset")
    assert all(r.headers["authorization"] == "Bearer fixture-only" for r in requests)
    failed[0] = True
    with pytest.raises(StorageUnavailable):
        await adapter.get("copy/asset", 4)
    with pytest.raises(StorageUnavailable):
        await adapter.delete("copy/asset")
