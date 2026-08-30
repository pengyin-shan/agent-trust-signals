#!/usr/bin/env python3
from __future__ import annotations
import csv
import sys
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "reference" / "inconsistent_surface_patterns.csv"

def classify(row: dict) -> str | None:
    field = row["field"]
    pair = frozenset((row["surface_a"], row["surface_b"]))
    note = (row["note"] or "").lower()
    journal_note = ("journal" in note) or ("article" in note) or ("paper" in note)
    if "cff_preferred" in pair or journal_note:
        if field in ("authors", "title", "doi", "year"):
            return "P1_preferred_citation_journal_redirect"
    if field == "version":
        return "P2_version_divergence"
    if field == "title" and "pypi" in pair:
        return "P3_title_shortname_divergence"
    if field == "authors" and "pypi" in pair:
        return "P4_author_entity_divergence"
    if field == "doi" and ("concept" in note or "version" in note):
        return "P5_concept_vs_versioned_doi"
    if field == "authors" and ("escap" in note or "accent" in note or "'" in row["note"]):
        return "P6_name_encoding_artifact"
    if field == "license":
        return "P7_license_divergence"
    return None

DESCRIPTIONS = {
    "P1_preferred_citation_journal_redirect": (
        "A preferred-citation block (CITATION.cff preferred-citation) or README "
        "bibtex points to a journal article, so authors, title, DOI, and year "
        "diverge between the citation surfaces and the software's own record."
    ),
    "P2_version_divergence": (
        "Version differs between metadata surfaces (archive record vs. registry "
        "listing in the log; stale surface lags the released version)."
    ),
    "P3_title_shortname_divergence": (
        "Registry surface carries a short package name while other surfaces "
        "carry the full or versioned title."
    ),
    "P4_author_entity_divergence": (
        "Author entity type diverges across surfaces: a team or corporate name "
        "on one surface versus an individual list or a different corporate "
        "entity on another."
    ),
    "P5_concept_vs_versioned_doi": (
        "Concept DOI and versioned DOI are mixed across surfaces, so the DOI "
        "field disagrees depending on which surface is read."
    ),
    "P6_name_encoding_artifact": (
        "Author names encoded differently across surfaces (LaTeX-escaped "
        "accents in README bibtex versus Unicode elsewhere), breaking exact "
        "matching."
    ),
    "P7_license_divergence": (
        "License field differs between metadata surfaces."
    ),
}

PROJECTIONS = {
    "P1_preferred_citation_journal_redirect": (
        "CITATION.cff gains a preferred-citation to a journal article whose "
        "authors/title/DOI/year differ from the cff main block; README citation "
        "section carries the same journal bibtex."
    ),
    "P2_version_divergence": (
        "CITATION.cff version differs from pyproject.toml version (registry "
        "metadata is generated from pyproject, so this projects the "
        "doi_record/pypi version conflicts onto in-checkout surfaces)."
    ),
    "P3_title_shortname_divergence": (
        "pyproject.toml name/description carries the short name while "
        "CITATION.cff title and README heading carry the full title."
    ),
    "P4_author_entity_divergence": (
        "CITATION.cff authors list individuals while pyproject.toml authors "
        "carry a team/corporate entity (or vice versa)."
    ),
    "P5_concept_vs_versioned_doi": (
        "CITATION.cff doi carries the versioned DOI while the README badge "
        "and codemeta.json identifier carry the concept DOI."
    ),
    "P6_name_encoding_artifact": (
        "README bibtex spells one author with LaTeX-escaped accents while "
        "CITATION.cff spells the same author in Unicode."
    ),
    "P7_license_divergence": (
        "CITATION.cff license differs from pyproject.toml license/LICENSE file."
    ),
}

def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    log_path = Path(sys.argv[1]) / "verification" / "verification_log.csv"
    with open(log_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    conflicts = [r for r in rows if r["hand_verdict"] == "conflict"]

    fams: dict[str, list[dict]] = defaultdict(list)
    for r in conflicts:
        fam = classify(r)
        if fam:
            fams[fam].append(r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "pattern_id", "description", "fields_observed", "surface_pairs_observed",
            "supporting_conflict_rows", "example_projects", "representative_note",
            "in_checkout_projection", "log_source",
        ])
        for fam in sorted(DESCRIPTIONS):
            evid = fams.get(fam, [])
            if not evid:
                raise SystemExit(f"family {fam} has no supporting log rows; refusing to catalog it")
            fields = sorted({r["field"] for r in evid})
            pairs = sorted({f"{r['surface_a']}<->{r['surface_b']}" for r in evid})
            projects = sorted({r["project_id"] for r in evid})[:6]
            note = next((r["note"] for r in evid if r["note"]), "")
            w.writerow([
                fam, DESCRIPTIONS[fam], ";".join(fields), ";".join(pairs),
                len(evid), ";".join(projects), note, PROJECTIONS[fam],
                "rda-audit-pipeline v0.2.3 verification/verification_log.csv",
            ])
    total = sum(len(v) for v in fams.values())
    print(f"cataloged {len(fams)} pattern families from {total} of {len(conflicts)} conflict rows -> {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
