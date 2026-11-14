"""Serving the browser app: files, ``index.html`` for app routes, and what stays a 404."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.config import Config


@pytest.fixture
def built_app(tmp_path: Path, config: Config) -> Generator[TestClient]:
    """A client for an app serving a small stand-in for a built browser app.

    Args:
        tmp_path: Pytest's per-test temporary folder.
        config: The library to serve.

    Yields:
        The client; closed after the test.
    """
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "main.js").write_text("console.log('app')")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside")
    with TestClient(create_app(config, static_dir=dist)) as test_client:
        yield test_client


def test_root_serves_the_placeholder_page(client: TestClient):
    """Before the browser app is built, ``/`` shows a placeholder page.

    Given: the app with its default static folder.
    Expect: an HTML page saying the server is running.
    """
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "The server is running" in response.text


@pytest.mark.parametrize("path", ["/", "/rides/abc123", "/trends/2025"])
def test_app_routes_serve_index_html(built_app: TestClient, path: str):
    """Deep links into the browser app load its page, which then routes on the client.

    Given: a built app and a request for the root or an app route.
    Expect: the built ``index.html``.
    """
    response = built_app.get(path)

    assert response.status_code == 200
    assert response.text == "<html>app</html>", f"{path} should load the app's page"


@pytest.mark.parametrize(
    ("path", "body"), [("/assets/main.js", "console.log('app')"), ("/favicon.svg", "<svg/>")]
)
def test_files_are_served_as_they_are(built_app: TestClient, path: str, body: str):
    """The app's own files are served directly.

    Given: a built app with a script under ``assets/`` and a favicon at the top.
    Expect: each file's contents.
    """
    response = built_app.get(path)

    assert response.status_code == 200
    assert response.text == body


@pytest.mark.parametrize("path", ["/assets/missing.js", "/e2e/reset"])
def test_missing_assets_and_e2e_paths_are_404s(built_app: TestClient, path: str):
    """A missing script or a test-only path is a 404, not the app's page.

    Given: a built app (with test-only routes off) and a missing asset or an ``/e2e`` path.
    Expect: 404.
    """
    response = built_app.get(path)

    assert response.status_code == 404, f"{path} should not fall back to index.html"


def test_paths_cannot_escape_the_static_folder(built_app: TestClient):
    """A path climbing out of the static folder never reaches other files.

    Given: a file next to the static folder and a request for ``/../secret.txt``.
    Expect: the app's page, not the file.
    """
    response = built_app.get("/%2E%2E/secret.txt")

    assert "outside" not in response.text
