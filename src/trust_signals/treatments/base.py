from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

TOOL_ID = "https://github.com/pengyin-shan/agent-trust-signals/treatments"

class TreatmentError(RuntimeError):
    """Raised when a treatment cannot be applied without inventing data."""

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

@dataclass
class FileRecord:
    path: str
    action: str          # "added" | "modified"
    sha256: str
    signal_class: str    # sbom | signed_release | attestation | channel_declaration | metadata_surfaces | release_artifact
    retrieval_event: str | None

@dataclass
class TreatmentManifest:
    condition_id: str
    project_id: str
    source_commit: str
    applied_at: str = field(default_factory=utc_now)
    files: list[FileRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def record(self, fork: Path, rel: str, action: str, signal_class: str,
               retrieval_event: str | None) -> None:
        p = fork / rel
        if not p.exists():
            raise TreatmentError(f"manifest record for missing file: {rel}")
        self.files.append(FileRecord(rel, action, sha256_file(p), signal_class, retrieval_event))

    def merge(self, other: "TreatmentManifest") -> None:
        seen = {f.path for f in self.files}
        for f in other.files:
            if f.path in seen:
                self.files = [x for x in self.files if x.path != f.path]
            self.files.append(f)
            seen.add(f.path)
        self.notes.extend(other.notes)

    def to_dict(self) -> dict:
        return {
            "condition_id": self.condition_id,
            "project_id": self.project_id,
            "source_commit": self.source_commit,
            "applied_at": self.applied_at,
            "tool": TOOL_ID,
            "files": [f.__dict__ for f in self.files],
            "notes": list(self.notes),
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")

@dataclass(frozen=True)
class TreatmentContext:
    project: "SurfaceMapEntry"         
    source_commit: str
    keys: "StudyKeys | None"


class Treatment:
    condition_id: str = ""
    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:  # pragma: no cover - interface
        raise NotImplementedError


def rel(fork: Path, path: Path) -> str:
    return path.relative_to(fork).as_posix()


def readme_path(fork: Path) -> Path:
    for name in ("README.md", "README.rst", "README.markdown", "README.txt", "README"):
        p = fork / name
        if p.exists():
            return p
    raise TreatmentError("fork has no README; treatments that reference the README cannot apply")


def append_readme_section(fork: Path, heading: str, body_lines: Iterable[str]) -> Path:
    p = readme_path(fork)
    text = p.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    body = "\n".join(body_lines)
    if p.suffix == ".rst":
        section = f"\n{heading}\n{'-' * len(heading)}\n\n{body}\n"
    else:
        section = f"\n## {heading}\n\n{body}\n"
    p.write_text(text + section, encoding="utf-8")
    return p
