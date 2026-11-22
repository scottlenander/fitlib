"""Other websites can't use the local server: host check, same-origin writes, headers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.api.security import host_name
from fitlib.config import Config
from tests.clients import LOCAL
from tests.fixtures.generate import FIT_DIR

BIKE = {"name": "Cross-site bike", "kind": "road"}
OTHER_SITE = "https://other.example"


def bike_names(client: TestClient) -> list[str]:
    """List the library's bike names.

    Args:
        client: A client for the app.

    Returns:
        Every bike's name.
    """
    return [b["name"] for b in client.get("/api/bikes").json()]


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1", "[::1]:8000", "LOCALHOST"])
def test_loopback_hosts_are_answered(client: TestClient, host: str):
    """Requests naming this computer are answered.

    Given: GET /api/health with a loopback Host header.
    Expect: 200.
    """
    assert client.get("/api/health", headers={"host": host}).status_code == 200


@pytest.mark.parametrize("path", ["/api/health", "/api/rides", "/", "/rides/abc"])
def test_other_hosts_are_refused(client: TestClient, path: str):
    """A request naming another host (DNS rebinding) is refused, pages and API alike.

    Given: A request whose Host is another site's domain, as after DNS rebinding.
    Expect: 421 with a JSON reason, and none of the library in the body.
    """
    response = client.get(path, headers={"host": "rebind.other.example"})

    assert response.status_code == 421
    assert response.json() == {"detail": "This server only answers requests for localhost."}


def test_write_from_another_site_is_refused(client: TestClient):
    """A page on another site can't change the library.

    Given: POST /api/bikes with another site's Origin.
    Expect: 403, and no bike added.
    """
    response = client.post("/api/bikes", json=BIKE, headers={"origin": OTHER_SITE})

    assert response.status_code == 403
    assert "fitlib's own pages" in response.json()["detail"]
    assert BIKE["name"] not in bike_names(client)


def test_upload_from_another_site_is_refused(client: TestClient):
    """The classic cross-site form post (a multipart upload) can't import rides.

    Given: A multipart import from another site's Origin.
    Expect: 403, and the library still empty.
    """
    data = (FIT_DIR / "garmin_indoor_no_hr.fit").read_bytes()

    response = client.post(
        "/api/imports",
        files=[("files", ("ride.fit", data))],
        headers={"origin": OTHER_SITE},
    )

    assert response.status_code == 403
    assert client.get("/api/rides").json()["total"] == 0


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_every_kind_of_write_is_checked(client: TestClient, method: str):
    """PUT, PATCH and DELETE are checked like POST.

    Given: Each method from another site's Origin.
    Expect: 403 before the route runs.
    """
    response = client.request(method, "/api/settings/timezone", headers={"origin": OTHER_SITE})

    assert response.status_code == 403


def test_write_from_the_app_is_accepted(client: TestClient):
    """The app's own pages can change the library.

    Given: POST /api/bikes with the server's own Origin.
    Expect: 201, and the bike added.
    """
    response = client.post("/api/bikes", json=BIKE, headers={"origin": LOCAL})

    assert response.status_code == 201
    assert BIKE["name"] in bike_names(client)


def test_same_host_on_another_port_is_another_site(client: TestClient):
    """Another program on this computer, on another port, is another site.

    Given: POST /api/bikes with Origin ``http://127.0.0.1:5000`` to the server at 127.0.0.1.
    Expect: 403.
    """
    response = client.post("/api/bikes", json=BIKE, headers={"origin": "http://127.0.0.1:5000"})

    assert response.status_code == 403


def test_null_origin_is_refused(client: TestClient):
    """A sandboxed frame or a file page (Origin ``null``) can't write.

    Given: POST with ``Origin: null``.
    Expect: 403.
    """
    response = client.post("/api/bikes", json=BIKE, headers={"origin": "null"})

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("fetch_site", "status"),
    [("cross-site", 403), ("same-site", 403), ("same-origin", 201), ("none", 201)],
)
def test_fetch_metadata_is_used_when_there_is_no_origin(
    client: TestClient, fetch_site: str, status: int
):
    """Without an Origin, the browser's ``Sec-Fetch-Site`` decides.

    Given: POST /api/bikes with only a ``Sec-Fetch-Site`` header.
    Expect: Another site (even a sibling subdomain) refused; the same origin, or the user
        typing the address, accepted.
    """
    body = {**BIKE, "name": f"Bike {fetch_site}"}

    response = client.post("/api/bikes", json=body, headers={"sec-fetch-site": fetch_site})

    assert response.status_code == status


def test_tools_without_browser_headers_can_write(client: TestClient):
    """The command line, curl and scripts send neither header and are allowed.

    Given: POST /api/bikes with no Origin or Sec-Fetch-Site.
    Expect: 201.
    """
    assert client.post("/api/bikes", json=BIKE).status_code == 201


def test_reads_send_no_cors_permission(client: TestClient):
    """Another site's page can send a read but never see the answer.

    Given: GET /api/rides with another site's Origin.
    Expect: Answered (reads change nothing) without any Access-Control-Allow-Origin header,
        so the browser hides the response from that page.
    """
    response = client.get("/api/rides", headers={"origin": OTHER_SITE})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("path", ["/api/health", "/", "/rides/abc", "/api/nope"])
def test_security_headers_on_every_response(client: TestClient, path: str):
    """Pages and API answers carry the security headers, including errors.

    Given: A page, a deep link, an API answer and an API 404.
    Expect: nosniff, no framing, no referrer, and a CSP with only the app's own scripts.
    """
    headers = client.get(path).headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    csp = headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp


def test_refusals_carry_the_security_headers(client: TestClient):
    """Refused requests get the headers too.

    Given: A request for another host.
    Expect: ``X-Frame-Options: DENY`` on the 421.
    """
    response = client.get("/", headers={"host": "other.example"})

    assert response.headers["x-frame-options"] == "DENY"


def test_api_docs_go_without_the_content_security_policy(client: TestClient):
    """FastAPI's docs load from a CDN, so they're left without the policy (still local only).

    Given: GET /docs.
    Expect: 200, other security headers, no CSP.
    """
    response = client.get("/docs")

    assert response.status_code == 200
    assert response.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" not in response.headers


def test_any_host_when_serving_on_a_network_address(tmp_path: Path):
    """On a network address it answers any host, but still only takes its own pages' writes.

    Given: An app with ``allowed_hosts=None`` (serving on an address the user chose), asked
        as 192.168.1.5.
    Expect: Reads answered; a write from another site refused; one from its own page accepted.
    """
    app = create_app(Config(library=tmp_path / "library"), workers=1, allowed_hosts=None)
    with TestClient(app, base_url="http://192.168.1.5:8000") as client:
        assert client.get("/api/health").status_code == 200
        refused = client.post("/api/bikes", json=BIKE, headers={"origin": OTHER_SITE})
        accepted = client.post(
            "/api/bikes", json=BIKE, headers={"origin": "http://192.168.1.5:8000"}
        )

    assert refused.status_code == 403
    assert accepted.status_code == 201


@pytest.mark.parametrize(
    ("header", "name"),
    [
        ("localhost:8000", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("[::1]:8000", "::1"),
        ("[::1]", "::1"),
        ("::1", "::1"),
        ("Example.COM:443", "example.com"),
    ],
)
def test_host_name_strips_port_and_brackets(header: str, name: str):
    """Host headers are reduced to the host name.

    Given: Host headers with and without ports, IPv6 in brackets, mixed case.
    Expect: The bare, lower-case host name.
    """
    assert host_name(header) == name
