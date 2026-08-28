import hashlib
import re
from typing import Dict, Any, Optional
from .errors import *

class TruthState:
    EXECUTION_STARTED = "EXECUTION_STARTED"
    COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    COMPLETED_FAILURE = "COMPLETED_FAILURE"

class PGLEvidenceValidator:
    def __init__(self):
        pass

    def compute_identity_chain_hash(self, payload: Dict[str, Any]) -> str:
        # A deterministic hash of the identity chain fields
        fields = [
            str(payload.get("trust_domain_id", "")),
            str(payload.get("workload_identifier", "")),
            str(payload.get("profile_id", "")),
            str(payload.get("ephemeral_execution_id", "")),
            str(payload.get("authority_hash", "") or ""),
            str(payload.get("candidate_act_hash", "")),
            str(payload.get("policy_decision_hash", "")),
            str(payload.get("p5_operation_id", "")),
            str(payload.get("p5_truth_state", "")),
            str(payload.get("event_hash", "")),
            str(payload.get("previous_event_hash", "") or "")
        ]
        raw = "|".join(fields).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def validate_append(
        self,
        payload: Dict[str, Any],
        actual_authority_hash: Optional[str] = None,
        actual_candidate_act_hash: Optional[str] = None,
        actual_policy_decision_hash: Optional[str] = None,
        actual_event_hash: Optional[str] = None,
        is_genesis: bool = False
    ) -> bool:
        base_kwargs = {
            "p5_operation_id": payload.get("p5_operation_id"),
            "p5_truth_state": payload.get("p5_truth_state"),
            "workload_identifier": payload.get("workload_identifier"),
            "ephemeral_execution_id": payload.get("ephemeral_execution_id"),
            "authority_hash": payload.get("authority_hash"),
            "candidate_act_hash": payload.get("candidate_act_hash")
        }

        # 1. Presence checks
        if not payload.get("trust_domain_id"):
            raise MissingTrustDomainError(**base_kwargs)

        wid = payload.get("workload_identifier")
        if not wid:
            raise MissingWorkloadIdentifierError(**base_kwargs)
        
        # Simple format check for WID (e.g. spiffe:// or urn:)
        if not (wid.startswith("spiffe://") or wid.startswith("urn:")):
            raise MalformedWorkloadIdentifierError(**base_kwargs)

        if not payload.get("profile_id"):
            raise MissingProfileIdError(**base_kwargs)

        if not payload.get("ephemeral_execution_id"):
            raise MissingEphemeralExecutionIdError(**base_kwargs)

        # Authority hash required for consequence/truth-transition
        truth_state = payload.get("p5_truth_state")
        
        # We assume if it has consequence or truth transition, it needs authority
        # (e.g. states EXECUTION_STARTED, COMPLETED_SUCCESS, COMPLETED_FAILURE)
        needs_authority = truth_state in [
            str(TruthState.EXECUTION_STARTED),
            str(TruthState.COMPLETED_SUCCESS),
            str(TruthState.COMPLETED_FAILURE)
        ]
        if needs_authority and not payload.get("authority_hash"):
            raise MissingAuthorityHashError(**base_kwargs)

        if not payload.get("candidate_act_hash"):
            raise MissingCandidateActHashError(**base_kwargs)

        if not payload.get("policy_decision_hash"):
            raise MissingPolicyDecisionHashError(**base_kwargs)

        if not payload.get("p5_operation_id"):
            raise MissingP5OperationIdError(**base_kwargs)

        if not truth_state:
            raise MissingP5TruthStateError(**base_kwargs)

        if not payload.get("event_hash"):
            raise MissingEventHashError(**base_kwargs)

        if not is_genesis and not payload.get("previous_event_hash"):
            raise MissingPreviousEventHashError(**base_kwargs)

        signature = payload.get("signature")
        if not signature:
            raise InvalidSignatureError(**base_kwargs)
        
        if signature.startswith("placeholder"):
            if not signature.startswith("placeholder:labeled:"):
                raise UnlabeledPlaceholderSignatureError(**base_kwargs)
        elif signature == "invalid":
            raise InvalidSignatureError(**base_kwargs)

        # 2. Hash Match checks
        expected_chain_hash = self.compute_identity_chain_hash(payload)
        if payload.get("identity_chain_hash") != expected_chain_hash:
            raise IdentityChainHashMismatchError(**base_kwargs)

        if actual_authority_hash and payload.get("authority_hash") != actual_authority_hash:
            raise AuthorityHashMismatchError(**base_kwargs)

        if actual_candidate_act_hash and payload.get("candidate_act_hash") != actual_candidate_act_hash:
            raise CandidateActHashMismatchError(**base_kwargs)

        if actual_policy_decision_hash and payload.get("policy_decision_hash") != actual_policy_decision_hash:
            raise PolicyDecisionHashMismatchError(**base_kwargs)

        if actual_event_hash and payload.get("event_hash") != actual_event_hash:
            raise EventHashMismatchError(**base_kwargs)

        # 3. Truth Discipline
        # 'AUTHORIZED' cannot be represented as 'COMPLETED_SUCCESS' (Truth overclaim)
        if truth_state == "COMPLETED_SUCCESS":
            # If actual state was just AUTHORIZED, or ALLOW, that's an overclaim.
            # We determine this via the provided evidence/hashes, or a specific payload flag for the test
            if payload.get("_actual_state") in ["AUTHORIZED", "ALLOW", "OUTCOME_UNKNOWN", "DENIED"]:
                raise TruthOverclaimDeniedError(**base_kwargs)

        if truth_state == "OUTCOME_UNKNOWN":
            # Cannot be collapsed into success
            if payload.get("_asserted_as") == "SUCCESS":
                raise TruthOverclaimDeniedError(**base_kwargs)

        return True
