"""Rules from chat: a rule drafted in a thread goes live in reflexr once a person accepts it.

The chat agent drafts a rule with [`RuleDrafting`][relayr.rules.RuleDrafting]'s `draft_rule`,
which checks it, previews it and proposes it as a `rule` artifact. When a person who may install
rules accepts it, relayr's `relayr:rules-from-chat` rule installs it in reflexr, through
[`Installer`][relayr.rules.Installer]; archiving the artifact archives the rule.
"""

from relayr.rules.drafting import RuleDrafting
from relayr.rules.drafts import RuleDraft, check_draft
from relayr.rules.installer import (
    ALLOWLISTS,
    RULE_DRIFT,
    RULES,
    RULES_FROM_CHAT,
    Installer,
    MayChange,
    RuleChange,
    anyone,
)
from relayr.rules.preview import Preview, preview

__all__ = [
    "ALLOWLISTS",
    "RULES",
    "RULES_FROM_CHAT",
    "RULE_DRIFT",
    "Installer",
    "MayChange",
    "Preview",
    "RuleChange",
    "RuleDraft",
    "RuleDrafting",
    "anyone",
    "check_draft",
    "preview",
]
