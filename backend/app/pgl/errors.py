import time
from typing import Dict, Any, Optional

class PGLEvidenceError(Exception):
    """Base class for PGL Evidence append denials."""
    def __init__(self, error_code: str, message: str, **kwargs):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = kwargs

    def to_evidence(self) -> Dict[str, Any]:
        evidence = {
            "error_code": self.error_code,
            "denial_code": self.error_code,
            "event_type": "PGL_APPEND_DENIED",
            "pgl_append_denied": True,
            "timestamp": int(time.time())
        }
        
        # Add parseable fields from kwargs
        parseable_fields = [
            "p5_operation_id",
            "p5_truth_state",
            "workload_identifier",
            "ephemeral_execution_id",
            "authority_hash",
            "candidate_act_hash"
        ]
        
        for field in parseable_fields:
            if field in self.details and self.details[field] is not None:
                evidence[field] = self.details[field]
                
        return evidence

class MissingTrustDomainError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_TRUST_DOMAIN", "Missing trust_domain_id", **kwargs)

class MissingWorkloadIdentifierError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_WORKLOAD_IDENTIFIER", "Missing workload_identifier", **kwargs)

class MalformedWorkloadIdentifierError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MALFORMED_WORKLOAD_IDENTIFIER", "Malformed workload_identifier", **kwargs)

class MissingProfileIdError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_PROFILE_ID", "Missing profile_id", **kwargs)

class MissingEphemeralExecutionIdError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_EPHEMERAL_EXECUTION_ID", "Missing ephemeral_execution_id", **kwargs)

class MissingAuthorityHashError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_AUTHORITY_HASH", "Missing authority_hash for consequence/truth-transition", **kwargs)

class MissingCandidateActHashError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_CANDIDATE_ACT_HASH", "Missing candidate_act_hash", **kwargs)

class MissingPolicyDecisionHashError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_POLICY_DECISION_HASH", "Missing policy_decision_hash", **kwargs)

class MissingP5OperationIdError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_P5_OPERATION_ID", "Missing p5_operation_id", **kwargs)

class MissingP5TruthStateError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_P5_TRUTH_STATE", "Missing p5_truth_state", **kwargs)

class TruthOverclaimDeniedError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_TRUTH_OVERCLAIM_DENIED", "Truth overclaim denied", **kwargs)

class MissingEventHashError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_EVENT_HASH", "Missing event_hash", **kwargs)

class MissingPreviousEventHashError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_MISSING_PREVIOUS_EVENT_HASH", "Missing previous_event_hash for non-genesis event", **kwargs)

class InvalidSignatureError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_INVALID_SIGNATURE", "Invalid signature", **kwargs)

class UnlabeledPlaceholderSignatureError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_UNLABELED_PLACEHOLDER_SIGNATURE", "Unlabeled placeholder signature", **kwargs)

class IdentityChainHashMismatchError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_IDENTITY_CHAIN_HASH_MISMATCH", "Identity chain hash mismatch", **kwargs)

class AuthorityHashMismatchError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_AUTHORITY_HASH_MISMATCH", "Authority hash mismatch", **kwargs)

class CandidateActHashMismatchError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_CANDIDATE_ACT_HASH_MISMATCH", "Candidate act hash mismatch", **kwargs)

class PolicyDecisionHashMismatchError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_POLICY_DECISION_HASH_MISMATCH", "Policy decision hash mismatch", **kwargs)

class EventHashMismatchError(PGLEvidenceError):
    def __init__(self, **kwargs):
        super().__init__("PGL_EVENT_HASH_MISMATCH", "Event hash mismatch", **kwargs)
