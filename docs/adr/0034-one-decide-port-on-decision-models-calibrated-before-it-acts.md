# ADR-0034: One `decide` port on decision models, calibrated before it acts

**Status:** Proposed
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**For:** #1024; used by #1006, #903, #1020, #837 and #973

## Context

Many parts of lattice need a typed judgement with a probability to act on:

- whether two records are the same entity (#1006);
- whether a new assertion contradicts an existing one (#973);
- whether an event is a billing complaint, as a rule filter (#837);
- whether a tool call looks like exfiltration (#903);
- whether a figure matches a result (#1020).

Asking a generative LLM and parsing its text is costly and unstable, and gives no probability to threshold.

LiteLLM (v1.104.2 and later) serves **decision models** at `/v1/decisions`. They answer `predicate`, `choice` and `score` questions with probabilities, or return a `refusal`. Self-hosted models run on vLLM 0.32 or later, and hosted ones are available from several providers. The docs don't claim the probabilities are calibrated.

The owner decided (2026-10-28):

- one shared capability on the platform epic;
- calibrated, versioned question sets;
- self-hosted and hosted deployments as explicit options, never routed between automatically.

## Decision

- **One `decide` port in lattice-core**, registered in the capability registry. Its first adapter is LiteLLM's `/v1/decisions`. Nothing else calls `/v1/decisions` directly.
- **Question sets are versioned artifacts.** Each holds:
  - the questions;
  - an input template, which renders untrusted content as data, never as instructions;
  - the named deployment;
  - labelled fixtures;
  - thresholds, as settings.
- **A question set acts only once calibrated.**
  - evalr fits a calibration map (isotonic or Platt) for each question and model.
  - Thresholds come from target precision or recall.
  - Until a set is calibrated, it can only log.
  - Changing the model or the question version invalidates the calibration until it is refit.
- **Deployment is chosen explicitly for each question set**: self-hosted vLLM (a stackr `decisions` profile) or a hosted provider behind the vault, egress proxy and integration switches. **There is no automatic routing or escalation between them.**
- **Every decision is logged with its versions and probabilities**, so it can be replayed.
- stackr's LiteLLM moves from v1.103.0 to v1.104.3 or later.

## Options considered

### Option A: One calibrated `decide` port (chosen)

| Dimension | Assessment |
|---|---|
| Consistency | One way to ask, calibrate, threshold and log |
| Reliability | Calibrated probabilities, with versioned replay |
| Effort | Medium: the port, calibration in evalr, fixtures |

**Pros:** Every consumer gets calibration and audit for free.
**Cons:** Calibration needs labels; starter fixtures are required (#1034).

### Option B: Generative LLM judgements with parsed text

| Dimension | Assessment |
|---|---|
| Consistency | Low |
| Reliability | Unstable, with no probability to calibrate |
| Effort | Low at first, high later |

**Pros:** No new model type.
**Cons:** Cost, instability, and thresholds made up per caller.

### Option C: Each package calls decision models itself

| Dimension | Assessment |
|---|---|
| Consistency | Low: duplicated prompts, thresholds and logs |
| Effort | Spread out and repeated |

**Pros:** No shared dependency.
**Cons:** Calibration and audit get done unevenly, or not at all.

## Trade-off analysis

The value of a decision model is a probability you can act on. That needs calibration, and calibration only works when it's done the same way everywhere. Automatic hosted escalation would blur data-egress policy and make calibration depend on which model answered, so deployments are explicit.

## Consequences

- **Easier:**
  - rule filters, guardrails, entity resolution and knowledge gating share one tested path;
  - decisions are auditable and can be replayed.
- **Harder:**
  - starter fixtures and calibrations must ship with every built-in question set (#1034);
  - model upgrades need recalibration.
- **To revisit:** fine-tuned adapters per tenant (#1033), once review queues produce labels.

## Action items

1. [ ] Build the `decide` port, question-set artifacts and calibration in evalr (#1024).
2. [ ] Add the stackr `decisions` profile and upgrade LiteLLM (#1024).
3. [ ] Ship starter fixtures and calibrations (#1034).
