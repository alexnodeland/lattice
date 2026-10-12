"""Evaluating the bridge's rules: proposal outcomes as feedback, and measures from the logs.

[`Outcomes`][relayr.evals.Outcomes] is the action of ``relayr:proposal-outcome``, which gives
each run whose proposal people resolved a [`ProposalOutcome`][relayr.evals.ProposalOutcome].
[`proposal_rates`][relayr.evals.proposal_rates] counts them by rule,
[`rule_conversion`][relayr.evals.rule_conversion] follows rules from chat from draft to
survival, and [`history`][relayr.evals.history] gives an artifact's versions to evalr's
measures, such as ``measure_rewrites``.
"""

from relayr.evals.measures import ProposalRates, RuleConversion, proposal_rates, rule_conversion
from relayr.evals.outcomes import (
    EVALUATOR,
    PROPOSAL_OUTCOME,
    RULES,
    Outcomes,
    ProposalOutcome,
)
from relayr.evals.revisions import history

__all__ = [
    "EVALUATOR",
    "PROPOSAL_OUTCOME",
    "RULES",
    "Outcomes",
    "ProposalOutcome",
    "ProposalRates",
    "RuleConversion",
    "history",
    "proposal_rates",
    "rule_conversion",
]
