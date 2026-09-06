[![DOI](https://zenodo.org/badge/1341904365.svg)](https://doi.org/10.5281/zenodo.22544144)

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

### Model Pricing

#### Fable 5

> https://platform.claude.com/docs/en/about-claude/pricing

- Base Input Tokens: $10 / MTok
- 5m Cache Writes: $12.50 / MTok
- 1h Cache Writes: $20 / MTok
- Cache Hits & Refreshes: $1 / MTok
- Output Tokens: $50 / MTok

#### Sonnet 5

> https://platform.claude.com/docs/en/about-claude/pricing

- Base Input Tokens: $2 / MTok
- 5m Cache Writes: $2.5 / MTok
- 1h Cache Writes: $4 / MTok
- Cache Hits & Refreshes: $0.2 / MTok
- Output Tokens: $10 / MTok

#### Gemini 3.5 Flash-Lite (Paid Tier)

> https://ai.google.dev/gemini-api/docs/pricing

- Base Input Tokens: $0.3 / MTok
- Context caching price: $0.03 / MTok
- Output Tokens: $2.5 / MTok
- Explicit context-cache storage is metered separately and unused unless the runner enables caching.

#### gpt-5.6-sol (standard)

> https://developers.openai.com/api/docs/pricing

##### Short Context (<=272K Input Tokens)
- Base Input Tokens: $4 / MTok
- Cached input: 0.4 / MTok
- Cache Writes: $5 / MTok
- Output Tokens: $20 / MTok

##### Long Context (>272K Input Tokens)
- Base Input Tokens: $8 / MTok
- Cached input: $0.8 / MTok
- Cache Writes: $10 / MTok
- Output Tokens: $30 / MTok

### gpt-oss:20b (local inference, zero marginal API cost)
- Hardware: 

```bash
2026-08-22 17:06:17.253 system_profiler[91223:14182293] hw.cpufamily: 0xda33d83d
      Model Name: MacBook Air
      Chip: Apple M2
      Memory: 24 GB
```
- Energy is unmeasured.

### moonshotai/Kimi-K2.6 (DeepInfra, standard)

> https://deepinfra.com/moonshotai/Kimi-K2.6

- Base Input Tokens: $0.75 / MTok
- Cached: $0.15 / MTok
- Output Tokens: $3.5 / MTok

## Notes

- The protocol was deposited before execution (10.5281/zenodo.22062503). 
- Results are produced only by `scripts/run_analysis.py`, and that trial artifacts are in the data deposit. 
- Preprint: arXiv identifier to be added on announcement.