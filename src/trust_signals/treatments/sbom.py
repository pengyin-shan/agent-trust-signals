from __future__ import annotations
import configparser
import json
import re
import tomllib
import uuid
from pathlib import Path
from .archive import artifact_name, ensure_archive
from .base import (Treatment, TreatmentContext, TreatmentError, TreatmentManifest,
                   append_readme_section, sha256_file, utc_now, TOOL_ID)

_REQ_SPLIT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*?)\s*(?:;.*)?$")

def _parse_requirement(line: str) -> tuple[str, str] | None:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "git+", "http", "file:", ".")):
        return None
    m = _REQ_SPLIT.match(line)
    if not m:
        return None
    return m.group(1).lower().replace("_", "-"), (m.group(3) or "").strip()

def declared_dependencies(fork: Path, sources) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for ds in sources:
        src, scope = (ds, "required") if isinstance(ds, str) else (ds.path, ds.scope)
        p = fork / src
        if not p.exists():
            raise TreatmentError(f"dependency source listed in surface map is missing from the fork: {src}")
        if p.name == "pyproject.toml":
            doc = tomllib.loads(p.read_text(encoding="utf-8"))
            for line in (doc.get("project") or {}).get("dependencies") or []:
                r = _parse_requirement(line)
                if r:
                    out.append((*r, src, scope))
        elif p.name == "setup.cfg":
            cp = configparser.ConfigParser()
            cp.read(p, encoding="utf-8")
            block = cp.get("options", "install_requires", fallback="")
            for line in block.splitlines():
                r = _parse_requirement(line)
                if r:
                    out.append((*r, src, scope))
        else:  # requirements-style
            for line in p.read_text(encoding="utf-8").splitlines():
                r = _parse_requirement(line)
                if r:
                    out.append((*r, src, scope))
    seen = set()
    dedup = []
    for n, s, f, sc in out:
        if n not in seen:
            seen.add(n)
            dedup.append((n, s, f, sc))
    return dedup

def build_sbom(fork: Path, ctx: TreatmentContext, archive: Path) -> dict:
    proj = ctx.project
    deps = declared_dependencies(fork, proj.dependency_sources)
    ref_main = f"pkg:github/{proj.upstream_repo.lower()}@{ctx.source_commit}"
    components = []
    for name, spec, src, scope in deps:
        components.append({
            "type": "library",
            "bom-ref": f"pkg:pypi/{name}",
            "name": name,
            "scope": scope,
            "purl": f"pkg:pypi/{name}",
            "properties": [
                {"name": "declared_specifier", "value": spec or "(unpinned)"},
                {"name": "declared_in", "value": src},
            ],
        })
    return {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, ref_main + '/sbom')}",
        "version": 1,
        "metadata": {
            "timestamp": utc_now(),
            "tools": {"components": [{"type": "application", "name": "agent-trust-signals treatments",
                                      "bom-ref": TOOL_ID}]},
            "component": {
                "type": "library",
                "bom-ref": ref_main,
                "name": proj.package_name,
                "version": str(proj.version.value),
                "purl": ref_main,
                "licenses": [{"license": {"id": str(proj.license.value)}}]
                if _spdx_like(str(proj.license.value)) else
                [{"license": {"name": str(proj.license.value)}}],
                "externalReferences": [
                    {"type": "vcs", "url": f"https://github.com/{proj.upstream_repo}"},
                    {"type": "distribution", "url": f"dist/{archive.name}",
                     "hashes": [{"alg": "SHA-256", "content": sha256_file(archive)}]},
                ],
            },
        },
        "components": components,
        "dependencies": [{"ref": ref_main, "dependsOn": [c["bom-ref"] for c in components]}],
    }

def _spdx_like(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9.+-]+", s))

class SbomPresent(Treatment):
    condition_id = "sbom_present"

    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:
        m = TreatmentManifest(self.condition_id, ctx.project.project_id, ctx.source_commit)
        archive = ensure_archive(fork, ctx, m)
        name = artifact_name(ctx).replace(".tar.gz", ".cdx.json")
        (fork / "dist" / name).write_text(json.dumps(build_sbom(fork, ctx, archive), indent=2) + "\n",
                                          encoding="utf-8")
        m.record(fork, f"dist/{name}", "added", "sbom", "sbom_opened")
        readme = append_readme_section(fork, "Software bill of materials", [
            f"A CycloneDX 1.6 software bill of materials for this release is published at "
            f"``dist/{name}``. It lists the release artifact ``dist/{archive.name}`` with its "
            f"SHA-256 digest and every dependency this project's checkout declares, with the declaring file and scope recorded per component.",
        ])
        m.record(fork, readme.relative_to(fork).as_posix(), "modified", "sbom", None)
        return m
