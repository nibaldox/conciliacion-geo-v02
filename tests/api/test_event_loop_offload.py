import ast
import asyncio
from pathlib import Path
import threading
import time

import httpx
import pytest

from api import database as db
from api.main import app


ROOT = Path(__file__).resolve().parents[2]
FILES = [
    *(ROOT / 'api' / 'routers' / f'{name}.py' for name in
      ('blast', 'export', 'simulations', 'sections', 'process', 'ai')),
    ROOT / 'api' / 'ai_agent_handlers.py',
]


def test_async_functions_do_not_call_db_directly():
    violations = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.in_async = False

        def visit_AsyncFunctionDef(self, node):
            previous = self.in_async
            self.in_async = True
            self.generic_visit(node)
            self.in_async = previous

        def visit_FunctionDef(self, node):
            previous = self.in_async
            self.in_async = False
            self.generic_visit(node)
            self.in_async = previous

        def visit_Call(self, node):
            if (self.in_async and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'db'):
                violations.append(f'{path.relative_to(ROOT)}:{node.lineno}: db.{node.func.attr}')
            self.generic_visit(node)

    for path in FILES:
        Visitor().visit(ast.parse(path.read_text()))
    assert not violations, '\n' + '\n'.join(violations)


@pytest.mark.parametrize(('method', 'path', 'result'), [
    ('get_settings', '/api/v1/blast/test-session/summary', {}),
    ('get_results', '/api/v1/process/results', []),
])
def test_slow_db_does_not_block_health(api_isolated_db, monkeypatch, method, path, result):
    started = threading.Event()

    def slow(*args, **kwargs):
        started.set()
        time.sleep(0.5)
        return result

    monkeypatch.setattr(db, method, slow)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test',
                                     headers={'X-Session-ID': 'test-session'}) as client:
            task = asyncio.create_task(client.get(path))
            before = time.monotonic()
            while not started.is_set():
                await asyncio.sleep(0.005)
            health = await client.get('/api/v1/health')
            elapsed = time.monotonic() - before
            response = await task
            assert response.status_code == 200, response.text
            assert health.status_code == 200
            assert elapsed < 0.25, f'health completed after {elapsed:.3f}s'

    asyncio.run(exercise())
