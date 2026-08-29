from __future__ import annotations
import json
from pathlib import Path
from .archive import artifact_name, ensure_archive
from .base import (Treatment, TreatmentContext, TreatmentError, TreatmentManifest, sha256_file,
                   utc_now, TOOL_ID)
from .signed_release import write_keys_file

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
BUILD_TYPE = TOOL_ID + "/checkout-archive@v1"
PAYLOAD_TYPE = "application/vnd.in-toto+json"

def build_statement(fork: Path, ctx: TreatmentContext, archive: Path) -> dict:
    proj = ctx.project
    return {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": archive.name, "digest": {"sha256": sha256_file(archive)}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "buildDefinition": {
                "buildType": BUILD_TYPE,
                "externalParameters": {
                    "repository": f"https://github.com/{proj.upstream_repo}",
                    "ref": proj.default_branch,
                    "packageName": proj.package_name,
                    "version": str(proj.version.value),
                },
                "internalParameters": {"archiveMtime": 1_700_000_000},
                "resolvedDependencies": [
                    {"uri": f"git+https://github.com/{proj.upstream_repo}@{proj.default_branch}",
                     "digest": {"gitCommit": ctx.source_commit}},
                ],
            },
            "runDetails": {
                "builder": {"id": TOOL_ID + "@0.1.0"},
                "metadata": {"invocationId": f"{proj.project_id}-{ctx.source_commit[:12]}",
                             "startedOn": utc_now(), "finishedOn": utc_now()},
            },
        },
    }

def _attest(fork: Path, ctx: TreatmentContext, manifest: TreatmentManifest, signer: str) -> None:
    if ctx.keys is None:
        raise TreatmentError("cryptographic treatment requires study keys")
    archive = ensure_archive(fork, ctx, manifest)
    write_keys_file(fork, ctx, manifest)
    payload = json.dumps(build_statement(fork, ctx, archive), separators=(",", ":"), sort_keys=True).encode()
    envelope = ctx.keys.dsse_sign(signer, PAYLOAD_TYPE, payload)
    name = artifact_name(ctx) + ".intoto.jsonl"
    (fork / "dist" / name).write_text(json.dumps(envelope, separators=(",", ":")) + "\n", encoding="utf-8")
    (fork / "dist" / "attestation-key.pub").write_text(ctx.keys[signer].ecdsa_public_pem, encoding="utf-8")
    manifest.record(fork, f"dist/{name}", "added", "attestation", "attestation_fetched")
    manifest.record(fork, "dist/attestation-key.pub", "added", "attestation", "attestation_fetched")
    manifest.notes.append(f"provenance attestation issued by identity {signer}"
                          + ("" if signer == "A" else " (issuer mismatch: KEYS declares identity A)"))

class AttestationPresent(Treatment):
    condition_id = "attestation_present"
    
    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:
        m = TreatmentManifest(self.condition_id, ctx.project.project_id, ctx.source_commit)
        _attest(fork, ctx, m, "A")
        return m

class AttestationIssuerMismatch(Treatment):
    condition_id = "attestation_issuer_mismatch"

    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:
        m = TreatmentManifest(self.condition_id, ctx.project.project_id, ctx.source_commit)
        _attest(fork, ctx, m, "B")
        return m
