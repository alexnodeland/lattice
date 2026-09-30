# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-typed-verdicts-over-any-pydantic-model.md) | Typed verdicts over any Pydantic model | Accepted |
| [0002](0002-dspy-judges-and-decision-models-as-equals.md) | DSPy judges and decision models as equals | Accepted |
| [0003](0003-datasets-and-experiments-in-langfuse-and-hugging-face.md) | Datasets and experiments in Langfuse and Hugging Face | Accepted |
| [0004](0004-trunk-based-development-with-rfcs-and-adrs.md) | Trunk-based development with RFCs, ADRs and evergreen docs | Accepted, amended by 0014 |
| [0005](0005-quality-gates-and-license.md) | Quality gates and license | Accepted, amended by 0014 |
| [0006](0006-ports-and-adapters.md) | Ports and adapters | Accepted, amended by 0011 |
| [0007](0007-trained-judges-saved-as-json-files.md) | Trained judges saved as JSON files | Accepted |
| [0008](0008-decision-only-views-and-hand-off-by-composition.md) | Decision-only views, and hand-off by composition | Accepted |
| [0009](0009-online-evaluation.md) | Online evaluation: sampling by key, soft budgets, and events as log records | Accepted |
| [0010](0010-documentation-site.md) | The documentation site, and publishing it from main | Accepted, amended by 0013 and 0015 |
| [0011](0011-scores-shared-with-the-libraries.md) | Scores shared with the libraries | Accepted, partly superseded by 0012, and amended by 0014 |
| [0012](0012-langfuse-score-adapters-in-evalr.md) | Langfuse score adapters in evalr | Accepted |
| [0013](0013-docstrings-in-markdown-and-one-docs-build.md) | Docstrings in Markdown, and one docs build | Accepted, amended by 0015 |
| [0014](0014-evalr-in-lattice.md) | evalr in lattice | Accepted |
| [0015](0015-one-site-for-the-family.md) | One site for the family | Accepted |

To add a record, copy [`template.md`](template.md) to the next number and add a row above.
