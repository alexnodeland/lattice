# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-typed-verdicts-over-any-pydantic-model.md) | Typed verdicts over any Pydantic model | Accepted |
| [0002](0002-dspy-judges-and-decision-models-as-equals.md) | DSPy judges and decision models as equals | Accepted |
| [0003](0003-datasets-and-experiments-in-langfuse-and-hugging-face.md) | Datasets and experiments in Langfuse and Hugging Face | Accepted |
| [0004](0004-trunk-based-development-with-rfcs-and-adrs.md) | Trunk-based development with RFCs, ADRs and evergreen docs | Accepted |
| [0005](0005-quality-gates-and-license.md) | Quality gates and license | Accepted |
| [0006](0006-ports-and-adapters.md) | Ports and adapters | Accepted |
| [0007](0007-trained-judges-saved-as-json-files.md) | Trained judges saved as JSON files | Accepted |
| [0008](0008-decision-only-views-and-hand-off-by-composition.md) | Decision-only views, and hand-off by composition | Accepted |
| [0009](0009-online-evaluation.md) | Online evaluation: sampling by key, soft budgets, and events as log records | Accepted |

To add a record, copy [`template.md`](template.md) to the next number and add a row above.
