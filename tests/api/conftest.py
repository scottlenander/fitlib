"""Fixtures for the API tests: apps over an empty library or the imported fixture rides.

The fixture folder is imported once per session into a template library. Tests that only
read share it; tests that change anything get their own copy.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.config import Config
from fitlib.importer import Importer
from fitlib.store.factory import open_stores
from tests.fixtures.generate import FIT_DIR


@dataclass(frozen=True)
class Template:
    """A library with the fixture folder imported, to read from or copy.

    Attributes:
        library: The library's folder.
        ids: Ride id for each imported fixture file, e.g. ``"garmin_indoor_no_hr.fit"``.
    """

    library: Path
    ids: dict[str, str]


@dataclass(frozen=True)
class Api:
    """A test client and the rides in the library it serves.

    Attributes:
        client: The test client.
        config: The served library's config.
        ids: Ride id for each imported fixture file.
    """

    client: TestClient
    config: Config
    ids: dict[str, str]


@pytest.fixture(scope="session")
def template(tmp_path_factory: pytest.TempPathFactory) -> Template:
    """Import the fixture folder into a local library, once per session.

    Args:
        tmp_path_factory: Pytest's session temporary folders.

    Returns:
        The library and its ride ids.
    """
    library = tmp_path_factory.mktemp("template") / "library"
    with open_stores(Config(library=library)) as stores:
        report = Importer(stores.catalog, stores.blobs, stores.streams, workers=1).run([FIT_DIR])
    return Template(library=library, ids=dict(report.imported))


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
    """A test client for the app over an empty library.

    Args:
        config: The library to serve.

    Yields:
        The client; closed after the test.
    """
    with TestClient(create_app(config)) as test_client:
        yield test_client


@pytest.fixture
def reader(template: Template) -> Generator[Api]:
    """A client over the shared imported library. Tests using it must not change anything.

    Args:
        template: The imported library.

    Yields:
        The client and the ride ids.
    """
    config = Config(library=template.library)
    with TestClient(create_app(config)) as test_client:
        yield Api(test_client, config, template.ids)


@pytest.fixture
def writer(template: Template, tmp_path: Path) -> Generator[Api]:
    """A client over this test's own copy of the imported library.

    Args:
        template: The imported library to copy.
        tmp_path: Pytest's per-test temporary folder.

    Yields:
        The client and the ride ids.
    """
    library = tmp_path / "library"
    shutil.copytree(template.library, library)
    config = Config(library=library)
    with TestClient(create_app(config)) as test_client:
        yield Api(test_client, config, template.ids)
