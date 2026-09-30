# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Before lattice]

### Features

- **core**: Own the score mapping and ports the libraries share ([#32](https://github.com/alexnodeland/evalr/pull/32))
- **online**: Run evaluators on live traffic, sampled and within a budget ([#21](https://github.com/alexnodeland/evalr/pull/21))
- **measures**: Define task completion, drop-off and rewrites generically ([#20](https://github.com/alexnodeland/evalr/pull/20))
- **hf**: Publish, pin and import datasets on the Hugging Face Hub ([#19](https://github.com/alexnodeland/evalr/pull/19))
- **langfuse**: Add the Langfuse score sink and experiment tracker ([#18](https://github.com/alexnodeland/evalr/pull/18))
- **langfuse**: Add the Langfuse dataset store ([#16](https://github.com/alexnodeland/evalr/pull/16))
- **decision**: Calibrate decision thresholds on a dataset ([#15](https://github.com/alexnodeland/evalr/pull/15))
- **decision**: Add DecisionEvaluator on a decision-only view ([#14](https://github.com/alexnodeland/evalr/pull/14))
- **dspy**: Save and load versioned judges ([#13](https://github.com/alexnodeland/evalr/pull/13))
- **dspy**: Train judges with GEPA ([#12](https://github.com/alexnodeland/evalr/pull/12))
- **dspy**: Add DspyJudge with signatures derived from its types ([#11](https://github.com/alexnodeland/evalr/pull/11))
- **core**: Add the optimizer port, fallback composition and measurement ([#10](https://github.com/alexnodeland/evalr/pull/10))
- **core**: Add agreement and calibration metrics ([#9](https://github.com/alexnodeland/evalr/pull/9))
- **core**: Add scores, the score sink and experiment tracker ports and their adapters ([#8](https://github.com/alexnodeland/evalr/pull/8))
- **core**: Add the dataset store and feedback source ports and their adapters ([#7](https://github.com/alexnodeland/evalr/pull/7))
- **core**: Add examples, datasets, deterministic splits and formatters ([#5](https://github.com/alexnodeland/evalr/pull/5))
- **core**: Add verdicts, field kinds, the evaluator protocol and function evaluators ([#4](https://github.com/alexnodeland/evalr/pull/4))

### Bug fixes

- Read people's feedback in rates, type experiment verdicts, and drop difflib's autojunk ([#33](https://github.com/alexnodeland/evalr/pull/33)) (**breaking**)
- Build generic results through their parametrized alias on Python 3.12 ([#30](https://github.com/alexnodeland/evalr/pull/30))
- **langfuse**: Match the dataset store and its fake to a real Langfuse ([#29](https://github.com/alexnodeland/evalr/pull/29))
- **core**: Never shorten a list that windowing alone can fit ([#25](https://github.com/alexnodeland/evalr/pull/25))

### Documentation

- Regenerate the changelog, and have the site regenerate it on every build ([#28](https://github.com/alexnodeland/evalr/pull/28))
- Render lists on the site as GitHub does, and gate scripts/ like the library ([#27](https://github.com/alexnodeland/evalr/pull/27))
- Publish the site at evalr.alexnodeland.com from main ([#24](https://github.com/alexnodeland/evalr/pull/24))
- Add the documentation site and brand ([#23](https://github.com/alexnodeland/evalr/pull/23))
- Describe v0.1 in the README and refresh the changelog ([#22](https://github.com/alexnodeland/evalr/pull/22))
- **adr**: Build evalr as ports and adapters ([#6](https://github.com/alexnodeland/evalr/pull/6))
- Add the evalr design: RFC-0001 and ADRs ([#1](https://github.com/alexnodeland/evalr/pull/1))

### Refactoring

- One set of Langfuse score adapters, scores that check their own values, and one docs build ([#34](https://github.com/alexnodeland/evalr/pull/34)) (**breaking**)

### Miscellaneous

- Lay the foundation for the evalr library ([#3](https://github.com/alexnodeland/evalr/pull/3))
- Initial commit
