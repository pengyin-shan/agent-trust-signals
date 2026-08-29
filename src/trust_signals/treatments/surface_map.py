from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from .base import TreatmentError
from ..paths import ROOT

SURFACE_MAP_PATH = ROOT / "reference" / "panel_surface_map.yaml"

REQUIRED_KEYS = ("upstream_repo", "default_branch", "package_name", "title",
                 "version", "previous_release", "license", "channels",
                 "dependency_sources")

@dataclass(frozen=True)
class Sourced:
    value: object
    source: str

    @classmethod
    def from_yaml(cls, node: dict, what: str) -> "Sourced":
        if not isinstance(node, dict) or "value" not in node or "source" not in node:
            raise TreatmentError(f"surface map field {what} must carry 'value' and 'source'")
        return cls(node["value"], str(node["source"]))


@dataclass(frozen=True)
class Channel:
    kind: str          # source_repository | documentation | discussion | mailing_list | chat | issue_tracker | package_index | support_email | homepage
    value: str         # URL, address, or index name
    source: str


@dataclass(frozen=True)
class DependencySource:
    path: str
    scope: str         # CycloneDX component scope: required | optional | excluded


@dataclass(frozen=True)
class Person:
    given: str
    family: str


@dataclass(frozen=True)
class CitedWork:
    kind: str                  # article | conference-paper | misc
    title: str
    authors: tuple[Person, ...]
    year: int
    venue: str | None
    doi: str | None
    url: str | None
    source: str


@dataclass(frozen=True)
class SurfaceMapEntry:
    project_id: str
    upstream_repo: str
    default_branch: str
    package_name: str
    title: Sourced
    version: Sourced 
    version_surface: str                # relative path of the file that states the live version
    previous_release: Sourced
    license: Sourced
    channels: tuple[Channel, ...]
    dependency_sources: tuple["DependencySource", ...]
    citation_file: str | None
    build_authors: Sourced | None
    build_authors_kind: str | None
    entity_name: Sourced | None
    individuals: tuple[Person, ...]
    individuals_source: str | None
    cited_work: CitedWork | None
    readme_has_citation_section: bool
    notes: tuple[str, ...] = field(default=())

    def previous_version_string(self) -> str:
        v = str(self.previous_release.value)
        return v[1:] if v.startswith("v") and v[1:2].isdigit() else v

def _persons(nodes, what: str) -> tuple[Person, ...]:
    out = []
    for n in nodes or []:
        if not isinstance(n, dict) or "given" not in n or "family" not in n:
            raise TreatmentError(f"{what}: each person needs 'given' and 'family'")
        out.append(Person(str(n["given"]), str(n["family"])))
    return tuple(out)

def _dep_sources(project_id: str, nodes) -> tuple[DependencySource, ...]:
    out = []
    for n in nodes or []:
        if isinstance(n, str):
            out.append(DependencySource(n, "required"))
        elif isinstance(n, dict) and "path" in n:
            scope = str(n.get("scope", "required"))
            if scope not in ("required", "optional", "excluded"):
                raise TreatmentError(f"{project_id}.dependency_sources: scope must be required|optional|excluded")
            out.append(DependencySource(str(n["path"]), scope))
        else:
            raise TreatmentError(f"{project_id}.dependency_sources entries are a path or {{path, scope}}")
    return tuple(out)

def _entry(project_id: str, node: dict) -> SurfaceMapEntry:
    for k in REQUIRED_KEYS:
        if k not in node:
            raise TreatmentError(f"surface map entry {project_id} missing required key: {k}")
    version = Sourced.from_yaml(node["version"], f"{project_id}.version")
    vsurf = node["version"].get("surface")
    if not vsurf:
        raise TreatmentError(f"{project_id}.version must name the 'surface' file carrying the live version")
    channels = []
    for c in node["channels"]:
        for k in ("kind", "value", "source"):
            if k not in c:
                raise TreatmentError(f"{project_id}.channels: each channel needs {k}")
        channels.append(Channel(str(c["kind"]), str(c["value"]), str(c["source"])))
    if not channels:
        raise TreatmentError(f"{project_id}: channels list is empty")
    ba = node.get("build_authors")
    cw = node.get("cited_work")
    cited = None
    if cw:
        for k in ("kind", "title", "authors", "year", "source"):
            if k not in cw:
                raise TreatmentError(f"{project_id}.cited_work missing {k}")
        cited = CitedWork(str(cw["kind"]), str(cw["title"]), _persons(cw["authors"], f"{project_id}.cited_work"),
                          int(cw["year"]), cw.get("venue"), cw.get("doi"), cw.get("url"), str(cw["source"]))
    ind = node.get("individuals") or {}
    return SurfaceMapEntry(
        project_id=project_id,
        upstream_repo=str(node["upstream_repo"]),
        default_branch=str(node["default_branch"]),
        package_name=str(node["package_name"]),
        title=Sourced.from_yaml(node["title"], f"{project_id}.title"),
        version=version,
        version_surface=str(vsurf),
        previous_release=Sourced.from_yaml(node["previous_release"], f"{project_id}.previous_release"),
        license=Sourced.from_yaml(node["license"], f"{project_id}.license"),
        channels=tuple(channels),
        dependency_sources=_dep_sources(project_id, node["dependency_sources"]),
        citation_file=node.get("citation_file"),
        build_authors=Sourced.from_yaml(ba, f"{project_id}.build_authors") if ba else None,
        build_authors_kind=(str(ba["kind"]) if ba else None),
        entity_name=Sourced.from_yaml(node["entity_name"], f"{project_id}.entity_name") if node.get("entity_name") else None,
        individuals=_persons(ind.get("persons"), f"{project_id}.individuals"),
        individuals_source=ind.get("source"),
        cited_work=cited,
        readme_has_citation_section=bool(node.get("readme_has_citation_section", False)),
        notes=tuple(node.get("notes") or ()),
    )

def load_surface_map(path: Path = SURFACE_MAP_PATH) -> dict[str, SurfaceMapEntry]:
    if not path.exists():
        raise TreatmentError(f"surface map not found: {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "projects" not in doc:
        raise TreatmentError("surface map must be a mapping with a 'projects' key")
    return {pid: _entry(pid, node) for pid, node in doc["projects"].items()}

def entry_for(project_id: str, path: Path = SURFACE_MAP_PATH) -> SurfaceMapEntry:
    m = load_surface_map(path)
    if project_id not in m:
        raise TreatmentError(f"no surface map entry for {project_id}; the constructors refuse to run without one")
    return m[project_id]
