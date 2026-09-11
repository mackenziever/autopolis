"""Fixtures E2E: HTTP server sulla cartella viewer + replay minimo."""
from __future__ import annotations

import asyncio
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from config import SimConfig
from engine.tick_engine import CivitasEngine

ROOT = Path(__file__).resolve().parents[2]
VIEWER = ROOT / "viewer"

playwright = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def viewer_base_url():
    port = _free_port()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(VIEWER), **kwargs)

        def log_message(self, *_):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture(scope="session")
def replay_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("replay") / "e2e.msgpack"
    cfg = SimConfig(
        num_agents=10,
        total_ticks=20,
        seed=42,
        log_path=str(path),
        llm_record_path=str(path) + ".jsonl",
        delta_log_enabled=True,
        delta_keyframe_every=5,
        spatial_hash_enabled=True,
    )
    asyncio.run(CivitasEngine(cfg).run(realtime=False))
    assert path.exists() and path.stat().st_size > 0
    return path


@pytest.fixture(scope="session")
def browser():
    pw = playwright.sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    try:
        yield browser
    finally:
        browser.close()
        pw.stop()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()
