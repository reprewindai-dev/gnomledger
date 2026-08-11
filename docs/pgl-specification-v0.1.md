# Proof-Graph Ledger (PGL) Open Specification v0.1

## Overview
PGL is an open standard that standardizes how agents prove identity, delegated authority, lineage, and execution evidence across agent-to-agent interactions. While A2A standardizes *how* agents communicate, PGL standardizes *who* is communicating, under *what* authority, and the cryptographically provable *evidence* of the operation.

## Core Primitives
PGL defines exactly five normative primitives, representing the frozen semantics of the protocol:

1. **PGLIdentity**: The persistent cryptographic identity for an agent, human principal, organization, service, or autonomous controller.
2. **PGLDelegation**: A signed statement defining: principal → delegate → scope → capability → resource → budget → validity window → delegation depth.
3. **PGLExecutionIdentity**: An ephemeral identity created for ONE governed operation. While the agent exists permanently, the ExecutionIdentity exists only for a specific authorized execution.
4. **PGLEvidenceEnvelope**: A portable result object containing: who, what, authority, capability, input_hash, output_hash, policy_ref, timestamps, signatures, settlement_ref, and measurement_refs.
5. **PGLLineage**: A traversable cryptographic chain representing: Organization → Principal → Agent → Delegation → ExecutionIdentity → Capability → Operation → Evidence.

## Design Principles
- **Interoperable, not Veklom-exclusive**: PGL is designed for any policy engine, runtime, payment rail, or storage implementation. Veklom is a reference implementation, but PGL is implementation-agnostic.
- **Complementary to A2A**: PGL leverages A2A Agent Cards (JWS signed) as the stable agent identity anchor, extending rather than replacing them.
- **Reference-Based Extensibility**: External systems such as CAPPO, VNP, and x402 produce *references* into the PGL model but are not required components for a PGL implementation.

## A2A Integration
PGL integrates seamlessly with A2A as an extension. Agents support PGL by advertising the following extension in their Agent Card:
`uri: https://pgl.veklom.com/a2a/v1, required: false`

By advertising PGL support, an agent commits to:
- Issuing PGL evidence for operations.
- Accepting PGL authority references in incoming requests.
- Supporting PGL lineage queries.

PGL uses A2A's JWS-signed Agent Card as the permanent identity anchor.

## Ecosystem Positioning
The following illustrates how PGL fits within the broader autonomous agent stack:

- **MCP**: Agent ↔ Tool
- **A2A**: Agent ↔ Agent
- **Web Bot Auth**: HTTP sender ↔ Origin
- **x402**: Machine ↔ Payment
- **PGL**: Principal ↔ Agent ↔ Authority ↔ Action ↔ Evidence
