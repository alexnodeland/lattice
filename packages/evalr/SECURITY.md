# Security policy

## Supported versions

evalr is pre-release (0.x). Security fixes are made on `main` and released in the next version. Once 1.0 ships, the latest minor release receives fixes.

## Reporting a vulnerability

Please do not open a public issue. Report vulnerabilities privately through GitHub's [private vulnerability reporting](https://github.com/alexnodeland/evalr/security/advisories/new).

Include what you can of:

- the affected package (`core`, `dspy`, `decision`, `langfuse`, `hf`) and version or commit
- a description of the issue and its impact
- steps to reproduce, or a proof of concept

You can expect an acknowledgement within a week. Once a fix is available, we will publish an advisory crediting you, unless you prefer otherwise.

## Scope notes

evalr reads the inputs it judges (threads, runs, artifacts) and sends them to the evaluators the application configures: a language model, TypeSafe's API, Langfuse or the Hugging Face Hub. Any way for evalr to send data somewhere the application did not configure is a vulnerability, as is loading a saved judge or dataset in a way that executes code from it. API keys are the application's to supply; evalr never logs them or records them on spans.
