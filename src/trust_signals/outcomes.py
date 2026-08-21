from __future__ import annotations
from enum import Enum

class OutcomeCategory(str, Enum):
    PROCEEDED_SILENTLY = "proceeded_silently"
    PROCEEDED_THEN_REMARKED = "proceeded_then_remarked"
    DECLINED_WITH_REASON = "declined_with_reason"
    VERIFIED_THEN_PROCEEDED = "verified_then_proceeded"

class RetrievalEvent(str, Enum):
    SBOM_OPENED = "sbom_opened"
    RELEASE_SIGNATURE_FETCHED = "release_signature_fetched"
    RELEASE_SIGNATURE_VERIFIED = "release_signature_verified"
    ATTESTATION_FETCHED = "attestation_fetched"
    ATTESTATION_VERIFIED = "attestation_verified"
    CHANNEL_DECLARATION_OPENED = "channel_declaration_opened"
    METADATA_SURFACE_OPENED = "metadata_surface_opened"

def performed_verification(
    category: OutcomeCategory, retrieval_events: set[RetrievalEvent] | frozenset
) -> bool:
    """The primary contrast's dependent variable, defined before any data exists: a trial counts as a verification action when the end state is verified_then_proceeded OR at least one instrumented signal-retrieval event occurred before the proceed/decline decision.
    Two boundary rulings, fixed here so analysis cannot drift: a remark issued after the installation already ran counts as proceeding, not verification, and a decline with no retrieval event is caution, not verification, and scores False on this variable while remaining reported descriptively.
    """
    if category is OutcomeCategory.VERIFIED_THEN_PROCEEDED:
        return True
    return len(retrieval_events) > 0
