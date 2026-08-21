# agent-trust-signals

A measurement study of how automated coding assistants respond to project quality and provenance metadata: do assistants retrieve and act on positive, defense-side trust signals (software bills of materials, signed releases, build provenance attestations, declared official communication channels) before installing or adopting research software?

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Relationship to other artifacts

- Corpus: rda-audit-pipeline v0.2.3 (10.5281/zenodo.21969695)
- supply-side audit: arXiv:2608.17159
- Motivating pilot: pilot-agent v1.0.2 (10.5281/zenodo.21861996)
- This repository is a new instrument in a new repository, per the standing one-instrument-one-repo policy.

## Notes
