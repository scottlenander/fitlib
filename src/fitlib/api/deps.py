"""FastAPI dependencies: the config and the library's stores.

Stores are opened per request. The SQLite catalog shares one connection between threads
without a lock, and FastAPI runs endpoints in a thread pool, so each request gets its own
short-lived catalog. Opening one is cheap, and WAL mode lets the CLI and the server use the
library at the same time.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request

from fitlib.config import Config
from fitlib.store.factory import Stores, open_stores


def get_config(request: Request) -> Config:
    """Return the config the app was created with.

    Args:
        request: The current request.

    Returns:
        The app's config.
    """
    return request.app.state.config


ConfigDep = Annotated[Config, Depends(get_config)]


def get_stores(config: ConfigDep) -> Generator[Stores]:
    """Open the library's stores for one request, and close them afterwards.

    Args:
        config: Which library to open.

    Yields:
        The library's stores.
    """
    with open_stores(config) as stores:
        yield stores


StoresDep = Annotated[Stores, Depends(get_stores)]
