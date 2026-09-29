"""In-memory adapters of every port, for tests and prototypes.

They behave like the real adapters, as the contract suites in ``evalr.contracts`` check, but keep
everything in the process. Applications and the sibling libraries use them to test their own
evaluation code without a network.
"""

from evalr.memory.datasets import InMemoryDatasetStore
from evalr.memory.experiments import InMemoryExperimentTracker
from evalr.memory.feedback import InMemoryFeedbackSource
from evalr.memory.optimizers import BestOf
from evalr.memory.scores import InMemoryScoreSink

__all__ = [
    "BestOf",
    "InMemoryDatasetStore",
    "InMemoryExperimentTracker",
    "InMemoryFeedbackSource",
    "InMemoryScoreSink",
]
