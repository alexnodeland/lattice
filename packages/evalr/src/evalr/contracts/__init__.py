"""Contract suites: what every adapter of a port must do.

Each check takes an adapter, exercises it through its port, and raises ``ContractViolation``
where it behaves differently from the port's contract. evalr runs them against every adapter it
ships; the libraries run them against theirs, such as ``check_feedback_source`` against their
feedback sources:

```python
async def test_the_feedback_source_meets_the_contract() -> None:
    await check_feedback_source(HelpfulnessFeedback(workspace))
```

The checks need no test framework.
"""

from evalr.contracts.datasets import check_dataset_store
from evalr.contracts.evaluators import check_evaluator, check_optimizer
from evalr.contracts.experiments import ContractOutput, check_experiment_tracker
from evalr.contracts.feedback import check_feedback_source
from evalr.contracts.scores import check_score_config_store, check_score_sink
from evalr.contracts.support import ContractInput, ContractVerdict, ContractViolation

__all__ = [
    "ContractInput",
    "ContractOutput",
    "ContractVerdict",
    "ContractViolation",
    "check_dataset_store",
    "check_evaluator",
    "check_experiment_tracker",
    "check_feedback_source",
    "check_optimizer",
    "check_score_config_store",
    "check_score_sink",
]
