"""The fitlib web API: JSON under ``/api``, plus the browser app's static files."""

from fitlib.api.app import create_app

__all__ = ["create_app"]
