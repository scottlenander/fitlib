"""Stopping the server from the browser app: ``POST /api/app/quit``."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Generator
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.config import Config
from tests.clients import LOCAL

OTHER_SITE = "https://evil.example"


@pytest.fixture
def quitting(config: Config) -> Generator[tuple[TestClient, list[str]]]:
    """A client for an app that may be stopped, with a stand-in for stopping the server.

    Args:
        config: The library to serve.

    Yields:
        The client, and a list that gets ``"stopped"`` each time the server is told to stop.
    """
    stops: list[str] = []
    app = create_app(config, workers=1, allow_quit=True)
    app.state.quit = lambda: stops.append("stopped")
    with TestClient(app, base_url=LOCAL) as client:
        yield client, stops


def test_quit_is_not_offered_by_default(client: TestClient):
    """A server run without ``--allow-quit`` can't be stopped from a browser.

    Given: an app made without ``allow_quit``.
    Expect: health says it can't quit; ``POST /api/app/quit`` is 404.
    """
    assert client.get("/api/health").json()["can_quit"] is False
    assert client.post("/api/app/quit").status_code == 404


def test_quit_stops_the_server_after_answering(quitting: tuple[TestClient, list[str]]):
    """The Quit button's request stops the server once the answer has gone out.

    Given: an app made with ``allow_quit``.
    Expect: health says it can quit; the request answers 202 ``{"stopping": true}`` and the
    server is told to stop once.
    """
    client, stops = quitting

    can_quit = client.get("/api/health").json()["can_quit"]
    response = client.post("/api/app/quit")

    assert can_quit is True
    assert (response.status_code, response.json()) == (202, {"stopping": True})
    assert stops == ["stopped"]


def test_quit_without_a_server_to_stop(config: Config):
    """An app not run by ``fitlib serve`` has nothing to stop, and says so.

    Given: an app made with ``allow_quit`` but no way to stop its server.
    Expect: 503.
    """
    with TestClient(create_app(config, workers=1, allow_quit=True), base_url=LOCAL) as client:
        assert client.post("/api/app/quit").status_code == 503


def test_another_site_cannot_stop_the_server(quitting: tuple[TestClient, list[str]]):
    """A page on another site can't stop fitlib.

    Given: ``POST /api/app/quit`` with another site's Origin.
    Expect: 403, and the server not told to stop.
    """
    client, stops = quitting

    response = client.post("/api/app/quit", headers={"origin": OTHER_SITE})

    assert response.status_code == 403
    assert stops == [], "the server should not be stopped"


def free_port() -> int:
    """Find a port nothing is listening on.

    Returns:
        The port.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(url: str, server: subprocess.Popen[bytes], timeout: float = 30) -> None:
    """Wait for a server to answer its health check.

    Args:
        url: The health check's URL.
        server: The server's process, to give up if it exits.
        timeout: Longest to wait, in seconds.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert server.poll() is None, "the server should not exit while starting"
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except URLError, ConnectionError:
            pass
        time.sleep(0.1)
    pytest.fail("the server should answer within 30 s")


def test_a_real_server_exits_when_asked_to_quit(tmp_path: Path):
    """``fitlib serve --allow-quit`` exits cleanly after the Quit button's request.

    Given: a real server process over an empty library, on a free port.
    Expect: 202 to the request, then the process exits with code 0 within 10 s.
    """
    port = free_port()
    config = tmp_path / "config.toml"
    config.write_text(f'library = "{tmp_path / "library"}"\n')
    command = "from fitlib.cli import app; app()"
    server = subprocess.Popen(
        [sys.executable, "-c", command, "--config", str(config), "serve"]
        + ["--port", str(port), "--allow-quit", "--no-watch", "--no-recompute"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        wait_for_health(f"{base}/api/health", server)
        request = urllib.request.Request(f"{base}/api/app/quit", method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
        code = server.wait(10)
    finally:
        if server.poll() is None:
            server.kill()

    assert status == 202
    assert code == 0, "the server should exit cleanly"
