"""Serving the browser app: files, ``index.html`` for app routes, and what stays a 404."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.api.static import PLACEHOLDER_DIR, default_static_dir
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
    with TestClient(create_app(config, static_dir=dist, workers=1)) as test_client:
        yield test_client


def test_placeholder_page_explains_how_to_build_the_app(config: Config):
    """The placeholder page says the server runs and how to build the browser app.

    Given: the app serving the placeholder folder.
    Expect: an HTML page with the build command.
    """
    with TestClient(create_app(config, static_dir=PLACEHOLDER_DIR, workers=1)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "npm --prefix web run build" in response.text


def test_built_app_is_served_when_present(tmp_path: Path):
    """The built browser app is served when there is one, the placeholder otherwise.

    Given: a build folder, first empty, then with an ``index.html``.
    Expect: the placeholder folder, then the build folder.
    """
    dist = tmp_path / "web_dist"
    dist.mkdir()

    before = default_static_dir(dist)
    (dist / "index.html").write_text("<html>app</html>")
    after = default_static_dir(dist)

    assert before == PLACEHOLDER_DIR
    assert after == dist


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
