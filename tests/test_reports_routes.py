"""AUDIT C-16: /reports/medical/{user_id} must not be shadowed by /reports/{user_id}/{report_id}.

The reports router imports app.config, which needs the real ADK (the shared
conftest mocks google.adk), so the check runs in a subprocess with a plain
interpreter. Skipped when the real ADK is not importable there.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import sys, warnings
warnings.filterwarnings("ignore")
try:
    import google.adk  # noqa: F401
except Exception:
    print("SKIP: google.adk not importable"); sys.exit(0)
from fastapi import FastAPI
from fastapi.routing import APIRoute
from app.routers import reports
paths = [r.path for r in reports.router.routes if isinstance(r, APIRoute)]
i_med, i_seed, i_param = (paths.index(p) for p in ("/reports/medical/{user_id}", "/reports/seed", "/reports/{user_id}/{report_id}"))
assert i_med < i_param and i_seed < i_param, paths
# Resolve the way Starlette does: first match wins.
app = FastAPI(); app.include_router(reports.router)
from starlette.routing import Match
scope = {"type": "http", "method": "GET", "path": "/reports/medical/elder_123", "root_path": "", "headers": []}
for route in app.router.routes:
    m, child = route.matches(scope)
    if m == Match.FULL:
        print("MATCHED", route.path); break
"""


@pytest.mark.timeout(180)
def test_medical_reports_route_is_reachable():
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=170,
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "AUTH_MODE": "off"})
    out = (r.stdout or "") + (r.stderr or "")
    if "SKIP:" in out:
        pytest.skip(out.strip().splitlines()[-1])
    assert r.returncode == 0, out[-2000:]
    assert "MATCHED /reports/medical/{user_id}" in out, out[-2000:]
