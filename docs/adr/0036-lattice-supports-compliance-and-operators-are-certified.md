# ADR-0036: lattice supports compliance, and operators are the ones certified

**Status:** Proposed
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**For:** #1042 (compliance), #1043

## Context

The owner wants lattice to support GDPR, SOC 2 and HIPAA at least, to widen where it can be used and to hold it to good security and privacy practice. ISO 27001 and the EU AI Act are in scope too.

None of these certifies software:

- **GDPR** binds whoever controls or processes personal data.
- **SOC 2** is an auditor's report on an organisation running a service, and **ISO 27001** certifies an organisation's security management.
- **HIPAA** binds healthcare organisations and the vendors handling health data for them, who sign business associate agreements (BAAs).
- **The EU AI Act** places duties on providers and deployers of AI systems, and the duties depend on the use.

lattice is self-hosted: operators run it through stackr. So the question is what lattice owes them. Without a stated position, two things go wrong: docs drift into claims ("HIPAA-compliant") that are legal statements nobody has earned, and controls get built unevenly, one package at a time.

lattice has many of the parts already, built for other reasons:

- grantr's append-only audit log;
- tenant filtering on every read, and portalr withholding content by default;
- loopback-only defaults and generated secrets in stackr;
- backups with restore drills;
- provenance attestations on releases;
- in the v0.3 designs: erasure across snapshots (ADR-0032), PII classes and policies (ADR-0031), permissions intersected on every query (ADR-0033), and explicit model deployments (ADR-0034).

The owner decided (2026-10-28):

- compliance goes on the roadmap for v0.4, not v0.3;
- the frameworks in scope are GDPR, SOC 2, HIPAA, ISO 27001 and the EU AI Act;
- lattice's stance is "supports, not certified".

## Decision

- **lattice supports compliance; it isn't certified.** It ships controls, safe defaults and evidence that let an operator pass a GDPR assessment, a SOC 2 or ISO 27001 audit, or a HIPAA risk analysis. The operator is assessed, audited or certified.
- **A control matrix is the source of truth** (#1043). Each requirement in scope has a row naming:
  - the lattice control, with links to code, ADRs and settings;
  - the evidence it produces;
  - the owner: lattice, the operator, or shared.
- **Every lattice-owned control produces evidence automatically.** A control without evidence isn't finished. Evidence is collected on a compliance page and exported as a bundle (#1057).
- **Docs never say "compliant", "certified" or "HIPAA-ready".** They say lattice *supports* a framework and link the matrix. A docs check enforces the wording.
- **Data classes drive the controls.** Egress, retention, redaction, residency, audit of reads and HIPAA mode all key off a data's class (#1044). Model providers are treated as subprocessors, and they receive a class only where policy allows. The gateway's PII guardrails apply to every model call, on inputs and outputs, with an action set per class (#1058).
- **Strict modes only narrow.** HIPAA mode (#1055) and high-risk AI declarations (#1056) are settings that make other settings stricter, through the settings model of ADR-0030. They never add a separate build.
- **Order:** GDPR controls first, then the shared SOC 2 and ISO 27001 controls, then HIPAA mode. The EU AI Act items ride alongside.
- **Certifying a hosted lattice is out of scope.** If a hosted offering is ever run, its SOC 2 audit and BAAs are a separate decision.

## Options considered

### Option A: Support compliance, operators certified (chosen)

| Dimension | Assessment |
|---|---|
| Honesty | High: claims match what software can be |
| Effort | High, but spread over controls that are good engineering anyway |
| Value to operators | High: controls, evidence and a clear split of responsibility |

**Pros:** Fits a self-hosted product. Gives every control an owner and evidence. Keeps docs out of legal claims.
**Cons:** No badge to show buyers until an operator, or a future hosted lattice, is audited.

### Option B: Claim compliance in docs and marketing

| Dimension | Assessment |
|---|---|
| Honesty | Low: nothing has been audited |
| Effort | Low |
| Risk | High: a legal claim that an operator's breach could test |

**Pros:** Reads well to buyers.
**Cons:** Unfounded, and it misleads operators about what they still have to do.

### Option C: Leave compliance to operators

| Dimension | Assessment |
|---|---|
| Honesty | High |
| Effort | None for lattice; repeated by every operator |
| Value to operators | Low: some controls, such as erasure from agent memory, are only possible from inside lattice |

**Pros:** No work now.
**Cons:** Uneven controls, gaps no operator can close, and lattice is ruled out of regulated work.

## Trade-off analysis

Option B is a claim lattice can't back. Option C is honest but leaves operators unable to close gaps that only lattice can, above all erasure and data classes across agent memory. Option A costs the most, but most of its controls (an audit log nobody can quietly edit, encryption everywhere, access reviews, scanning) are engineering lattice should have anyway. The matrix keeps the work honest about what remains the operator's.

## Consequences

- **Easier:**
  - operators in regulated sectors can adopt lattice, with evidence ready for their auditors;
  - every new feature has a checklist: its data classes, retention, erasure path and evidence.
- **Harder:**
  - features that store data must implement the data subject request and retention adapters (#1045, #1046);
  - the matrix must be kept current, release by release;
  - HIPAA mode narrows which models can be used for health data.
- **To revisit:**
  - a hosted lattice, with its own SOC 2 Type II audit and BAAs;
  - the EU AI Act's high-risk obligations, as their dates and guidance settle.

## Action items

1. [ ] Write the control matrix and shared-responsibility table, with the wording check (#1043).
2. [ ] Build data classes and the egress policy per class (#1044).
3. [ ] Put the gateway's PII guardrails on every request and route, on inputs and outputs, and measure them (#1058).
4. [ ] Build the remaining controls in the epic's order (#1045–#1056).
5. [ ] Build the compliance page and evidence bundle (#1057).
