from __future__ import annotations
import re
from pathlib import Path
import yaml
from .base import (Treatment, TreatmentContext, TreatmentError, TreatmentManifest,
                   append_readme_section, readme_path)
from .surface_map import CitedWork, Person, SurfaceMapEntry

def _split_name(full: str) -> dict:
    parts = full.strip().split()
    if len(parts) < 2:
        return {"name": full.strip()}
    return {"given-names": " ".join(parts[:-1]), "family-names": parts[-1]}

def _person(p: Person) -> dict:
    return {"given-names": p.given, "family-names": p.family}

def baseline_cff(proj: SurfaceMapEntry) -> dict:
    if proj.build_authors is not None:
        vals = proj.build_authors.value if isinstance(proj.build_authors.value, list) else [proj.build_authors.value]
        if proj.build_authors_kind == "individuals":
            authors = [_split_name(str(v)) for v in vals]
        else:
            authors = [{"name": str(v)} for v in vals]
    else:
        authors = [{"name": str(proj.title.value)}]  # no author surface: the project name stands in
    return {
        "cff-version": "1.2.0",
        "message": "If you use this software, please cite it using the metadata from this file.",
        "type": "software",
        "title": str(proj.title.value),
        "version": str(proj.version.value),
        "authors": authors,
        "license": str(proj.license.value),
        "repository-code": f"https://github.com/{proj.upstream_repo}",
    }


def preferred_citation(cw: CitedWork) -> dict:
    kind = {"article": "article", "conference-paper": "conference-paper"}.get(cw.kind, "misc")
    d: dict = {"type": kind, "title": cw.title, "authors": [_person(p) for p in cw.authors], "year": cw.year}
    if cw.venue:
        d["journal" if kind == "article" else "collection-title"] = cw.venue
    if cw.doi:
        d["doi"] = cw.doi
    if cw.url:
        d["url"] = cw.url
    return d

def bibtex(cw: CitedWork, key: str) -> str:
    entry = "article" if cw.kind == "article" else ("inproceedings" if cw.kind == "conference-paper" else "misc")
    fields = [f"  title = {{{cw.title}}}",
              "  author = {" + " and ".join(f"{p.family}, {p.given}" for p in cw.authors) + "}",
              f"  year = {{{cw.year}}}"]
    if cw.venue:
        fields.append(("  journal = {" if entry == "article" else "  booktitle = {") + cw.venue + "}")
    if cw.doi:
        fields.append(f"  doi = {{{cw.doi}}}")
    if cw.url:
        fields.append(f"  url = {{{cw.url}}}")
    return f"@{entry}{{{key},\n" + ",\n".join(fields) + "\n}"

def apply_recipe(cff: dict, proj: SurfaceMapEntry, notes: list[str]) -> tuple[dict, list[str]]:
    applied: list[str] = []

    if proj.cited_work is None:
        notes.append("P1 not applicable: the checkout cites no article (surface map cited_work absent)")
    elif "preferred-citation" in cff:
        notes.append("P1 already present in the checkout's own CITATION.cff (documented occurrence, not constructed)")
        applied.append("P1")
    else:
        cff["preferred-citation"] = preferred_citation(proj.cited_work)
        cff["message"] = "Please cite this software using the metadata from 'preferred-citation'."
        applied.append("P1")

    prev = proj.previous_version_string()
    if prev == str(proj.version.value):
        raise TreatmentError(f"{proj.project_id}: previous release equals the live version; P2 cannot be applied")
    cff["version"] = prev
    applied.append("P2")

    if proj.build_authors is None:
        notes.append("P4 not applicable: the build declaration carries no author surface")
    elif proj.build_authors_kind == "entity":
        if proj.individuals:
            cff["authors"] = [_person(p) for p in proj.individuals]
            applied.append("P4")
        elif proj.entity_name is not None and str(proj.entity_name.value) != str(proj.build_authors.value):
            cff["authors"] = [{"name": str(proj.entity_name.value)}]
            applied.append("P4")
            notes.append("P4 applied as entity-versus-entity spelling divergence (catalog variant)")
        else:
            notes.append("P4 not applicable: no individuals or alternative entity name in the checkout")
    else:
        if proj.entity_name is None:
            notes.append("P4 not applicable: the checkout names no team or corporate entity")
        else:
            cff["authors"] = [{"name": str(proj.entity_name.value)}]
            applied.append("P4")
    return cff, applied

class InconsistentSurface(Treatment):
    condition_id = "inconsistent_surface"

    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:
        proj = ctx.project
        m = TreatmentManifest(self.condition_id, proj.project_id, ctx.source_commit)
        if not (fork / proj.version_surface).exists():
            raise TreatmentError(f"{proj.project_id}: version surface {proj.version_surface} missing from the fork")

        cff_path = fork / "CITATION.cff"
        if cff_path.exists():
            cff = yaml.safe_load(cff_path.read_text(encoding="utf-8")) or {}
            action = "modified"
            if proj.citation_file != "CITATION.cff":
                m.notes.append("checkout has a CITATION.cff the surface map did not record")
        else:
            cff = baseline_cff(proj)
            action = "added"
            m.notes.append("CITATION.cff generated from the checkout's declared metadata as the consistent baseline")

        cff, applied = apply_recipe(cff, proj, m.notes)
        cff_path.write_text(yaml.safe_dump(cff, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
        m.record(fork, "CITATION.cff", action, "metadata_surfaces", "metadata_surface_opened")

        if "P1" in applied and proj.cited_work is not None and not proj.readme_has_citation_section:
            key = re.sub(r"[^a-z0-9]", "", (proj.cited_work.authors[0].family + str(proj.cited_work.year)).lower()) or "cite"
            rp = append_readme_section(fork, "Citation", [
                f"If you use {proj.title.value} in your work, please cite:",
                "",
                "```bibtex" if readme_path(fork).suffix != ".rst" else "::",
                *(bibtex(proj.cited_work, key).splitlines() if readme_path(fork).suffix != ".rst"
                  else ["    " + ln for ln in bibtex(proj.cited_work, key).splitlines()]),
                *(["```"] if readme_path(fork).suffix != ".rst" else []),
            ])
            m.record(fork, rp.relative_to(fork).as_posix(), "modified", "metadata_surfaces", None)
        m.notes.append("families applied: " + ", ".join(applied))
        return m
