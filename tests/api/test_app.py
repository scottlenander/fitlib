"""The app itself: health, the OpenAPI description and unknown API paths."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fitlib import __version__


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
    }


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
