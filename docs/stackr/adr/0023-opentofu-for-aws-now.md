# ADR-0023: OpenTofu for AWS, now

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0001](0001-compose-first-with-profiles.md): Terraform no longer comes later. Records [RFC-0004](../rfcs/0004-hosting-recipes.md)'s H1 and H13.

## Context

ADR-0001 made Compose the first deployment format, and said Kubernetes (Helm) and Terraform come later, from the same service configuration. RFC-0004 brings two hosting recipes into stackr's v0.1: a single host, on Compose, and AWS. The AWS recipe needs infrastructure as code now.

## Decision

- **OpenTofu, now, for AWS:** the modules and roots in `packages/stackr/deploy/aws/`, as RFC-0004 designs them. OpenTofu is Terraform's open fork, under the MPL; Terraform itself is under a business source licence.
- **Helm and Kubernetes still come later,** from the same thin images the AWS recipe runs.
- **Compose stays the first format:** development, the single host, and the AWS recipe's state host all run it.

## Options considered

| Option | For | Against |
|---|---|---|
| **OpenTofu now (chosen)** | An open licence; the AWS provider and modules Terraform uses | A tool and a toolchain plugin more |
| Terraform now | The upstream | A business source licence |
| Helm first | Clusters | Still needs the VPC, RDS and S3 created some other way |

## Consequences

- Easier: an application from the template has a path to AWS that CI tests.
- Harder: stackr keeps OpenTofu's modules current beside `compose.yaml`.
