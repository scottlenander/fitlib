"""Stopping the server from the browser app."""

from __future__ import annotations

from pydantic import BaseModel


class Stopping(BaseModel):
    """The server's answer to being asked to quit.

    Attributes:
        stopping: Always true: the server stops once this answer has gone out.
    """

    stopping: bool = True
