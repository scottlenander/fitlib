"""Fixtures for the API tests: an app over a temporary library, and a client for it."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """Settings for an empty library in a temporary folder.

    Args:
        tmp_path: Pytest's per-test temporary folder.

    Returns:
        A config pointing at ``tmp_path / "library"``.
    """
    return Config(library=tmp_path / "library")


@pytest.fixture
def client(config: Config) -> Generator[TestClient]:
    """A test client for the app over ``config``'s library.

    Args:
        config: The library to serve.

    Yields:
        The client; closed after the test.
    """
    with TestClient(create_app(config)) as test_client:
        yield test_client
