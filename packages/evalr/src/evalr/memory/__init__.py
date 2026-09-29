"""In-memory adapters of every port, for tests and prototypes.

They behave like the real adapters, as the contract suites in ``evalr.contracts`` check, but keep
everything in the process. Applications and the sibling libraries use them to test their own
evaluation code without a network.
"""

from evalr.memory.datasets import InMemoryDatasetStore
from evalr.memory.feedback import InMemoryFeedbackSource

__all__ = ["InMemoryDatasetStore", "InMemoryFeedbackSource"]
