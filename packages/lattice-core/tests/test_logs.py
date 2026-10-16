"""logging_left_alone: the root logger as the application configured it."""

import logging

import pytest

from lattice_core.logs import logging_left_alone


class Closing(logging.NullHandler):
    """A handler that remembers it was closed."""

    closed = False

    def close(self) -> None:
        self.closed = True
        super().close()


def test_handlers_added_in_the_block_are_removed_closed_and_the_level_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = logging.getLogger()
    # A root logger of its own, with no handler yet, as basicConfig expects to find it.
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    added = Closing()
    with logging_left_alone():
        logging.basicConfig(level=logging.DEBUG)
        assert root.handlers, "basicConfig added its handler"
        root.addHandler(added)
    assert (root.handlers, root.level) == ([], logging.WARNING)
    assert added.closed
