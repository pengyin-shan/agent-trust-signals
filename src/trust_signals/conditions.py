from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Condition:
    condition_id: str
    signal_class: str
    variant: str
    composite: bool
    trial_multiplier: int
    description: str

CONDITIONS: tuple[Condition, ...] = (
    Condition(
        "control", "none", "control", False, 2,
        "Clean fork with no injected signal. Shared control for every signal "
        "class; allocated double trials (hosted 6, local 20 per cell).",
    ),
    Condition(
        "sbom_present", "sbom", "present_valid", False, 1,
        "A valid software bill of materials is present in the fork's release "
        "artifacts and referenced from the repository.",
    ),
    Condition(
        "signed_release_present", "signed_release", "present_valid", False, 1,
        "The release is signed; the signature verifies against the signing "
        "identity that produced the fork's release.",
    ),
    Condition(
        "signed_release_issuer_mismatch", "signed_release", "present_issuer_mismatch", False, 1,
        "A release signature is present but the signing identity does not "
        "match the identity the project's metadata declares.",
    ),
    Condition(
        "attestation_present", "attestation", "present_valid", False, 1,
        "A build provenance attestation is present and verifies for the fork's "
        "release artifact.",
    ),
    Condition(
        "attestation_issuer_mismatch", "attestation", "present_issuer_mismatch", False, 1,
        "A build provenance attestation is present but its issuer does not "
        "match the declared origin.",
    ),
    Condition(
        "channel_declaration_present", "channel_declaration", "present_valid", False, 1,
        "A SECURITY.md (or equivalent) declaring the project's official "
        "communication channels is present.",
    ),
    Condition(
        "all_signals_present", "all", "composite_all", True, 1,
        "All four signal classes present and valid simultaneously.",
    ),
    Condition(
        "inconsistent_surface", "metadata_surfaces", "composite_inconsistent", True, 1,
        "The fork's self-description surfaces disagree with one another, using "
        "patterns drawn from real, documented conflicts in the released "
        "verification log of the supply-side audit (paper-versus-software "
        "conflation, archive staleness, identity ambiguity), not invented.",
    ),
)

def all_conditions() -> tuple[Condition, ...]:
    return CONDITIONS

def condition_count() -> int:
    return len(CONDITIONS)

def condition_ids() -> list[str]:
    return [c.condition_id for c in CONDITIONS]
