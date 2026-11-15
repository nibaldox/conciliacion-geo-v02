import asyncio
from dataclasses import replace

import api._async_db as async_db
import core.config as config


def test_upload_slots_limit_per_loop(monkeypatch):
    monkeypatch.setattr(config, 'DEPLOY', replace(config.DEPLOY, upload_parse_concurrency=1))

    async def run():
        entered = asyncio.Event()
        release = asyncio.Event()
        active = 0
        maximum = 0

        async def worker():
            nonlocal active, maximum
            async with async_db.upload_parse_slot():
                active += 1
                maximum = max(maximum, active)
                entered.set()
                await release.wait()
                active -= 1

        tasks = [asyncio.create_task(worker()) for _ in range(3)]
        await entered.wait()
        await asyncio.sleep(0)
        assert maximum == 1
        release.set()
        await asyncio.gather(*tasks)
        assert maximum == 1

    asyncio.run(run())


def test_three_uploads_serialize_parse(isolated_data_dir, stl_bytes, monkeypatch):
    import threading
    import httpx
    import api.routers.meshes as router
    from api.main import app

    monkeypatch.setattr(config, "DEPLOY", replace(config.DEPLOY, upload_parse_concurrency=1))
    original = router.load_mesh
    entered = threading.Event()
    release = threading.Event()
    guard = threading.Lock()
    active = 0
    maximum = 0
    calls = 0
    def parse(path):
        nonlocal active, maximum, calls
        with guard:
            active += 1
            calls += 1
            maximum = max(maximum, active)
            entered.set()
        assert release.wait(10)
        try:
            return original(path)
        finally:
            with guard:
                active -= 1
    monkeypatch.setattr(router, "load_mesh", parse)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async def upload(i):
                return await client.post("/api/v1/meshes/upload", headers={"X-Session-ID": f"concurrent-{i}"}, files={"file": ("test.stl", stl_bytes)}, data={"type": "design"})
            tasks = [asyncio.create_task(upload(i)) for i in range(3)]
            assert await asyncio.to_thread(entered.wait, 5)
            await asyncio.sleep(0.05)
            assert maximum == 1
            release.set()
            responses = await asyncio.gather(*tasks)
            assert all(r.status_code == 200 for r in responses)
    try:
        asyncio.run(run())
    finally:
        release.set()
    assert calls == 3
    assert maximum == 1
