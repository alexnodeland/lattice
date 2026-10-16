"""Logging left as the application configured it."""

import contextlib
import logging
from collections.abc import Generator

__all__ = ["logging_left_alone"]


@contextlib.contextmanager
def logging_left_alone() -> Generator[None]:
    """Put the root logger's handlers and level back as they were when the block ends.

    Some libraries configure logging as they start, such as the MCP SDK's ``MCPServer``, which
    calls ``logging.basicConfig`` as it is built, with no option to skip it: if the root logger
    has no handlers yet, the whole process then logs at INFO through a rich handler. Logging is
    the application's to configure, so the handlers the block added are removed and closed, and
    the level restored.
    """
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        yield
    finally:
        for added in [handler for handler in root.handlers if handler not in handlers]:
            root.removeHandler(added)
            added.close()
        root.setLevel(level)
