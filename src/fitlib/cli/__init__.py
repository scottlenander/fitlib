"""The ``fitlib`` command line: rides, training, the athlete history, bikes and tags.

Command help shown by ``--help`` comes from each command's ``help=`` argument; the docstrings
are for developers. Importing this package registers every command on ``app``.
"""

from fitlib.cli import (  # noqa: F401 - registers commands
    athlete,
    bikes,
    rides,
    serve,
    timezone,
    trends,
    watch,
)
from fitlib.cli.common import EXIT_ERROR, EXIT_IMPORT_FAILURES, app

__all__ = ["EXIT_ERROR", "EXIT_IMPORT_FAILURES", "app"]
