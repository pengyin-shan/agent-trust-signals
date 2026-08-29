from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

from .base import TreatmentContext, TreatmentManifest, sha256_file

EXCLUDE_TOP = {".git", "dist", ".venv", "__pycache__"}
FIXED_MTIME = 1_700_000_000

def artifact_name(ctx: TreatmentContext) -> str:
    return f"{ctx.project.package_name}-{ctx.project.version.value}.tar.gz"

def build_archive(fork: Path, ctx: TreatmentContext) -> Path:
    """Write dist/<name>.tar.gz and dist/<name>.tar.gz.sha256; return the archive path."""
    dist = fork / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / artifact_name(ctx)
    prefix = f"{ctx.project.package_name}-{ctx.project.version.value}"

    entries = []
    for p in sorted(fork.rglob("*")):
        relparts = p.relative_to(fork).parts
        if not relparts or relparts[0] in EXCLUDE_TOP or "__pycache__" in relparts:
            continue
        if p.is_symlink():
            continue
        entries.append(p)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for p in entries:
            ti = tf.gettarinfo(str(p), arcname=f"{prefix}/{p.relative_to(fork).as_posix()}")
            ti.mtime = FIXED_MTIME
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            ti.mode = 0o755 if p.is_dir() else (0o755 if p.stat().st_mode & 0o111 else 0o644)
            if p.is_dir():
                tf.addfile(ti)
            else:
                with open(p, "rb") as fh:
                    tf.addfile(ti, fh)
    raw = buf.getvalue()
    with open(out, "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=FIXED_MTIME) as gz:
            gz.write(raw)
    (dist / (artifact_name(ctx) + ".sha256")).write_text(
        f"{sha256_file(out)}  {artifact_name(ctx)}\n", encoding="utf-8")
    return out

def ensure_archive(fork: Path, ctx: TreatmentContext, manifest: TreatmentManifest) -> Path:
    """Build the archive if absent and record it; idempotent within a composite."""
    out = fork / "dist" / artifact_name(ctx)
    already = any(f.path == f"dist/{artifact_name(ctx)}" for f in manifest.files)
    if not out.exists():
        build_archive(fork, ctx)
    if not already:
        manifest.record(fork, f"dist/{artifact_name(ctx)}", "added", "release_artifact", None)
        manifest.record(fork, f"dist/{artifact_name(ctx)}.sha256", "added", "release_artifact", None)
    return out
