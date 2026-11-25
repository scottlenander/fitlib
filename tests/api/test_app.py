"""The app itself: health, the OpenAPI description and unknown API paths."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi.testclient import TestClient

from fitlib import __version__
from fitlib.api import create_app
from fitlib.config import Config
from fitlib.services.recompute import BackgroundRecompute, RecomputeState
from tests.clients import LOCAL


def test_health_reports_ok_and_the_ride_count(client: TestClient):
    """The health check answers without any rides imported.

    Given: an app over an empty library.
    Expect: 200 with status ``ok``, fitlib's version, 0 rides and none outdated.
    """
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "rides": 0,
        "outdated_rides": 0,
        "recompute": None,
    }


class FakeRecompute:
    """Stands in for the server's background recompute, partway through."""

    def start(self) -> None:
        """Pretend to start."""

    def stop(self) -> None:
        """Pretend to stop."""

    def state(self) -> RecomputeState:
        """Report two of five rides done.

        Returns:
            The progress.
        """
        return RecomputeState(total=5, done=2)


def test_health_reports_the_background_recompute(config: Config):
    """While the server recomputes outdated rides, health says how far it has got.

    Given: an app whose background recompute has done 2 of 5 rides.
    Expect: ``recompute`` is ``{"total": 5, "done": 2}``.
    """
    app = create_app(config, workers=1, recomputer=cast(BackgroundRecompute, FakeRecompute()))
    with TestClient(app, base_url=LOCAL) as client:
        body = client.get("/api/health").json()

    assert body["recompute"] == {"total": 5, "done": 2}


def test_openapi_description_lists_the_api(client: TestClient):
    """The API describes itself, for the docs page and the browser app's types.

    Given: the app.
    Expect: ``/openapi.json`` lists ``/api/health`` and not the catch-all routes.
    """
    response = client.get("/openapi.json")

    paths = response.json()["paths"]
    assert "/api/health" in paths
    assert not any("{path}" in p for p in paths), "catch-all routes should stay out of the docs"


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_unknown_api_path_is_a_json_404(client: TestClient, method: str):
    """A wrong API path is a JSON 404 whatever the method, never the browser app's page.

    Given: a request to ``/api/nope``.
    Expect: 404 with a JSON body.
    """
    response = client.request(method, "/api/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
