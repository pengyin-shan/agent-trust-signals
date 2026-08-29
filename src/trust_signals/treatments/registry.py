from __future__ import annotations
from pathlib import Path
from ..conditions import condition_ids
from .attestation import AttestationIssuerMismatch, AttestationPresent
from .base import Treatment, TreatmentContext, TreatmentManifest
from .channel_declaration import ChannelDeclarationPresent
from .inconsistent_surface import InconsistentSurface
from .sbom import SbomPresent
from .signed_release import SignedReleaseIssuerMismatch, SignedReleasePresent

class Control(Treatment):
    condition_id = "control"
    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:
        m = TreatmentManifest(self.condition_id, ctx.project.project_id, ctx.source_commit)
        m.notes.append("clean fork; no files added or modified")
        return m

class AllSignalsPresent(Treatment):
    condition_id = "all_signals_present"
    parts = (SbomPresent, SignedReleasePresent, AttestationPresent, ChannelDeclarationPresent)

    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:
        m = TreatmentManifest(self.condition_id, ctx.project.project_id, ctx.source_commit)
        for cls in self.parts:
            sub = cls().apply(fork, ctx)
            m.merge(sub)
        return m

_REGISTRY: dict[str, type[Treatment]] = {
    cls.condition_id: cls for cls in (
        Control, SbomPresent, SignedReleasePresent, SignedReleaseIssuerMismatch,
        AttestationPresent, AttestationIssuerMismatch, ChannelDeclarationPresent,
        AllSignalsPresent, InconsistentSurface,
    )
}

def registry() -> dict[str, type[Treatment]]:
    return dict(_REGISTRY)

def treatment_for(condition_id: str) -> Treatment:
    if condition_id not in _REGISTRY:
        raise KeyError(f"no constructor for condition {condition_id!r}; frozen ids: {condition_ids()}")
    return _REGISTRY[condition_id]()

def check_registry() -> None:
    frozen = set(condition_ids())
    have = set(_REGISTRY)
    if frozen != have:
        raise RuntimeError(f"registry/condition mismatch: missing={sorted(frozen - have)} extra={sorted(have - frozen)}")