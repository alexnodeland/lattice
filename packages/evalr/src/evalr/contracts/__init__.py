"""Contract suites: what every adapter of a port must do.

Each check takes an adapter, exercises it through its port, and raises ``ContractViolation``
where it behaves differently from the port's contract. evalr runs them against every adapter it
ships; the libraries that implement ``FeedbackSource`` run ``check_feedback_source`` against
theirs::

    async def test_the_feedback_source_meets_the_contract() -> None:
        await check_feedback_source(HelpfulnessFeedback(workspace))

The checks need no test framework.
"""

from evalr.contracts.datasets import check_dataset_store
from evalr.contracts.experiments import ContractOutput, check_experiment_tracker
from evalr.contracts.feedback import check_feedback_source
from evalr.contracts.scores import check_score_sink
from evalr.contracts.support import ContractInput, ContractVerdict, ContractViolation

__all__ = [
    "ContractInput",
    "ContractOutput",
    "ContractVerdict",
    "ContractViolation",
    "check_dataset_store",
    "check_experiment_tracker",
    "check_feedback_source",
    "check_score_sink",
]
