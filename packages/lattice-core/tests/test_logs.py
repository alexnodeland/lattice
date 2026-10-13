"""logging_left_alone: the root logger as the application configured it."""

import logging

from lattice_core.logs import logging_left_alone


def test_handlers_added_in_the_block_are_removed_and_the_level_restored() -> None:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    with logging_left_alone():
        logging.basicConfig(level=logging.DEBUG, force=False)
        root.addHandler(logging.NullHandler())
        root.setLevel(logging.DEBUG)
    assert (root.handlers, root.level) == (handlers, level)
