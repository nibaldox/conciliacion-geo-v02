import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import httpx
import pytest

import api.database as db
import api.routers.process as process
import api.ai_agent_write_handlers as agent
from api.main import app
from core import config
from core.ai_v2.agent.models import RunReconciliationArgs


def seed(session):
    db.get_or_create_session(session)
    db.save_sections(session, [{"name": "S", "origin": [0, 0, 0], "azimuth": 0}])


class Probe:
    def __init__(self):
        self.lock = threading.Lock()
        self.started = threading.Event()
        self.release = threading.Event()
        self.active = 0
        self.maximum = 0
        self.calls = []

    def run(self, session, sections, overrides):
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.calls.append(session)
            self.started.set()
        self.release.wait(3)
        with self.lock:
            self.active -= 1
        return {"status": "complete", "total_sections": len(sections), "total_results": 0}


async def wait_for(predicate):
    for _ in range(300):
        if predicate():
            return
        await asyncio.sleep(0.01)
    pytest.fail("timed out waiting for condition")


@pytest.mark.asyncio
async def test_http_limit_and_queued_duplicate(client, monkeypatch):
    monkeypatch.setattr(config, "DEPLOY", replace(config.DEPLOY, process_concurrency=1))
    seed("proc-b")
    seed("proc-a")
    probe = Probe()
    monkeypatch.setattr(process, "_run_pipeline_sync", probe.run)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        async def post(s):
            return await c.post('/api/v1/process', headers={'X-Session-ID': s})
        first = asyncio.create_task(post("proc-b"))
        try:
            await wait_for(probe.started.is_set)
            second = asyncio.create_task(post("proc-a"))
            await wait_for(lambda: db.get_process_status("proc-a")["status"] == "running")
            duplicate = await post("proc-a")
            assert duplicate.status_code == 409
            await asyncio.sleep(0.1)
            assert probe.calls == ["proc-b"]
        finally:
            probe.release.set()
        responses = await asyncio.gather(first, second)
    assert [r.status_code for r in responses] == [200, 200]
    assert probe.maximum == 1


@pytest.mark.asyncio
async def test_ai_and_http_share_limit(client, monkeypatch):
    monkeypatch.setattr(config, "DEPLOY", replace(config.DEPLOY, process_concurrency=1))
    seed("proc-http")
    seed("proc-ai")
    probe = Probe()
    monkeypatch.setattr(process, "_run_pipeline_sync", probe.run)
    monkeypatch.setattr(agent, "_run_pipeline_sync", probe.run)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        first = asyncio.create_task(c.post('/api/v1/process', headers={'X-Session-ID': 'proc-http'}))
        try:
            await wait_for(probe.started.is_set)
            second = asyncio.create_task(agent.run_reconciliation("proc-ai", RunReconciliationArgs()))
            await wait_for(lambda: db.get_process_status("proc-ai")["status"] == "running")
            await asyncio.sleep(0.1)
            assert probe.calls == ["proc-http"]
        finally:
            probe.release.set()
        response, result = await asyncio.gather(first, second)
    assert response.status_code == 200
    assert result['ok']
    assert probe.maximum == 1


def test_pipeline_pool_and_status_throttle(isolated_data_dir, monkeypatch, pit_mesh_design, pit_mesh_asbuilt):
    seed("pipeline")
    meshes = {"design": pit_mesh_design, "topo": pit_mesh_asbuilt}
    monkeypatch.setattr(process, '_load_mesh_from_db', lambda sid, kind: meshes[kind])
    monkeypatch.setattr(process, 'DEPLOY', replace(config.DEPLOY, process_threads=3), raising=False)
    sizes = []
    def pool(*args, **kwargs):
        sizes.append(kwargs.get('max_workers'))
        return ThreadPoolExecutor(*args, **kwargs)
    monkeypatch.setattr(process, 'ThreadPoolExecutor', pool)
    writes = []
    original = db.update_process_status
    def status(*args):
        writes.append(args)
        return original(*args)
    monkeypatch.setattr(db, 'update_process_status', status)
    sections = [{"name": f"S{i}", "origin": [0, 0, 0], "azimuth": 0} for i in range(50)]
    result = process._execute_pipeline_sync("pipeline", sections, {})
    assert result['total_sections'] == 50
    assert sizes == [3]
    intermediate = [w for w in writes if w[1] == 'processing' and w[2] > 0]
    assert len(intermediate) <= 10
    assert intermediate[-1][2:4] == (50, 50)
    assert writes[-1][1:4] == ('complete', 50, 50)


@pytest.mark.parametrize('raw', ['', 'invalid', '0', '-1', '1.5'])
def test_invalid_config_defaults(monkeypatch, raw):
    monkeypatch.setenv('CONCILIACION_PROCESS_THREADS', raw)
    monkeypatch.setenv('CONCILIACION_PROCESS_CONCURRENCY', raw)
    deploy = config.DeployDefaults()
    assert deploy.process_threads == 4
    assert deploy.process_concurrency == 2


def test_valid_config(monkeypatch):
    monkeypatch.setenv('CONCILIACION_PROCESS_THREADS', '7')
    monkeypatch.setenv('CONCILIACION_PROCESS_CONCURRENCY', '3')
    deploy = config.DeployDefaults()
    assert (deploy.process_threads, deploy.process_concurrency) == (7, 3)
