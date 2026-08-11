# PGL A2A Extension Profile

## Overview
PGL is designed to operate seamlessly as an extension over the A2A (Agent-to-Agent) protocol. The A2A Agent Card acts as the stable identity anchor, while PGL manages identity resolution, authority, lineage, and execution evidence.

## Advertising PGL Support
Agents advertise their support for PGL by declaring the extension in their A2A Agent Card (`agent-card.json`):

```yaml
extensions:
  - uri: https://pgl.veklom.com/a2a/v1
    required: false
    description: PGL identity, authority, lineage and evidence layer
```

## Semantics of the PGL Extension
By advertising this extension, an agent commits to:
1. **Issuing PGL Evidence**: The agent can wrap its operation results in a `PGLEvidenceEnvelope`.
2. **Accepting PGL Authority References**: The agent can consume requests containing a `PGLDelegation` or `PGLExecutionIdentity`.
3. **Supporting PGL Lineage Queries**: The agent provides endpoints or metadata to resolve its operational lineage (`PGLLineage`).

## Verification Flow
When Agent A initiates a connection to Agent B:
1. Agent A fetches Agent B's Agent Card.
2. Agent A parses the `extensions` array.
3. If `https://pgl.veklom.com/a2a/v1` is present, Agent A knows it can request PGL-compliant evidence for subsequent operations.
4. Agent A sends a request containing a `PGLExecutionIdentity` to Agent B.
5. Agent B validates the execution identity, performs the operation, and returns a `PGLEvidenceEnvelope` to Agent A.
